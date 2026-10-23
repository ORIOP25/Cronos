"""Chronological construction with parallel curricular progress.

Teachers and classes with less availability take priority while on pace, then
lessons outside Evitar blocks, then subjects with less progress (D32, D33).
Repeating the weekly pattern may compensate for one lesson of progress.
Free resource combinations remain eligible even when other subjects must wait.
Construction failure is inconclusive; every returned plan is independently valid.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime
from fractions import Fraction
from time import monotonic

from ortools.graph.python import min_cost_flow
from ortools.sat.python import cp_model

from app.scheduler.domain.availability_priority import (
    AvailabilityLedger,
    PaceWatch,
)
from app.scheduler.domain.calendar import Period
from app.scheduler.domain.candidate import (
    Assignment,
    CandidateSchedule,
    PlanningSnapshot,
    ScheduledLesson,
    UnavailableResource,
    allocate_lesson_identity,
    continuous_break_minutes,
)
from app.scheduler.domain.candidate_validation import validate_candidate
from app.scheduler.domain.capacity import (
    available_rooms,
    canonical_periods,
    eligible_periods,
    residual_minutes,
)
from app.scheduler.domain.class_day_gaps import class_day_excess_value
from app.scheduler.domain.priorities import PriorityWeights
from app.scheduler.domain.priority_value import (
    WeeklyHistory,
    option_value,
)
from app.scheduler.domain.priority_value import (
    _fills_hour as _fills_hour,
)
from app.scheduler.domain.priority_value import (
    _gap_minutes as _gap_minutes,
)
from app.scheduler.domain.priority_value import (
    _gap_option_measure as _gap_option_measure,
)
from app.scheduler.domain.priority_value import (
    _joined_day_gain as _joined_day_gain,
)
from app.scheduler.domain.priority_value import (
    _local_interval as _local_interval,
)
from app.scheduler.domain.priority_value import (
    _option_measures as _option_measures,
)
from app.scheduler.domain.priority_value import (
    _pace_lag as _pace_lag,
)
from app.scheduler.domain.priority_value import (
    _pace_peers as _pace_peers,
)
from app.scheduler.domain.priority_value import (
    _preference_value as _preference_value,
)
from app.scheduler.domain.priority_value import (
    _room_value as _room_value,
)
from app.scheduler.domain.projection import ModuleSlice
from app.scheduler.infrastructure.construction_support import (
    _continues_open_presence as _continues_open_presence,
)
from app.scheduler.infrastructure.construction_support import (
    _evitar_kinds as _evitar_kinds,
)
from app.scheduler.infrastructure.construction_support import (
    _gives_up as _gives_up,
)
from app.scheduler.infrastructure.construction_support import (
    _grid_intervals_by_day as _grid_intervals_by_day,
)
from app.scheduler.infrastructure.construction_support import (
    _longest_presences as _longest_presences,
)
from app.scheduler.infrastructure.construction_support import (
    _minimum_presence_teachers as _minimum_presence_teachers,
)
from app.scheduler.infrastructure.construction_support import (
    _next_module as _next_module,
)
from app.scheduler.infrastructure.construction_support import (
    _predecessors_ready,
)
from app.scheduler.infrastructure.construction_support import (
    _presence_day_complies as _presence_day_complies,
)
from app.scheduler.infrastructure.construction_support import (
    _presence_left_fits as _presence_left_fits,
)
from app.scheduler.infrastructure.construction_support import (
    _resource_keys as _resource_keys,
)
from app.scheduler.infrastructure.construction_support import (
    _scarcity as _scarcity,
)
from app.scheduler.infrastructure.construction_support import (
    _slots_by_day as _slots_by_day,
)


def _flow_selection(
    options: list[tuple[Assignment, tuple[int, ...]]],
) -> list[tuple[Assignment, int]] | None:
    """Match resources; validate each selected subject's actual room domain.

    The flow model assumes a unit occupies one class. A joint unit falls back to
    the small CP-SAT repair in :func:`_select_period` (WBS 3.3.1).
    """
    if any(len(row.class_ids) != 1 for row, _rooms in options):
        return None
    rooms_by_class: dict[int, tuple[int, ...]] = {}
    rooms_by_assignment = {row.assignment_id: rooms for row, rooms in options}
    for assignment, rooms in options:
        class_id = assignment.class_ids[0]
        rooms_by_class[class_id] = tuple(dict.fromkeys((*rooms_by_class.get(class_id, ()), *rooms)))
    flow = min_cost_flow.SimpleMinCostFlow()
    nodes: dict[tuple, int] = {}

    def node(kind: str, identity: int = 0) -> int:
        return nodes.setdefault((kind, identity), len(nodes))

    source, sink = node("source"), node("sink")
    teachers = sorted({row.teacher_id for row, _rooms in options})
    rooms = sorted({room for _row, values in options for room in values})
    for teacher in teachers:
        flow.add_arc_with_capacity_and_unit_cost(source, node("teacher", teacher), 1, 0)
    for class_id in sorted(rooms_by_class):
        flow.add_arc_with_capacity_and_unit_cost(
            node("class", class_id), node("class_out", class_id), 1, 0
        )
    for room in rooms:
        flow.add_arc_with_capacity_and_unit_cost(node("room", room), sink, 1, 0)
    assignment_arcs = []
    for rank, (assignment, _rooms) in enumerate(options):
        arc = flow.add_arc_with_capacity_and_unit_cost(
            node("teacher", assignment.teacher_id),
            node("class", assignment.class_ids[0]),
            1,
            rank,
        )
        assignment_arcs.append((assignment, arc))
    room_arcs = {
        (class_id, room): flow.add_arc_with_capacity_and_unit_cost(
            node("class_out", class_id), node("room", room), 1, 0
        )
        for class_id, values in sorted(rooms_by_class.items())
        for room in values
    }
    upper = min(len(teachers), len(rooms_by_class), len(rooms))
    flow.set_node_supply(source, upper)
    flow.set_node_supply(sink, -upper)
    status = flow.solve_max_flow_with_min_cost()
    if status != flow.OPTIMAL:
        raise RuntimeError(f"Period resource matching failed: {status}.")
    selected = [
        (
            assignment,
            next(
                room
                for room in rooms_by_class[assignment.class_ids[0]]
                if flow.flow(room_arcs[(assignment.class_ids[0], room)])
            ),
        )
        for assignment, arc in assignment_arcs
        if flow.flow(arc)
    ]
    if any(room not in rooms_by_assignment[row.assignment_id] for row, room in selected):
        # Selected classes are unique. A second flow assigns their actual rooms.
        refined = _flow_selection(
            [(row, rooms_by_assignment[row.assignment_id]) for row, _room in selected]
        )
        return refined if refined is not None and len(refined) == len(selected) else None
    return selected


# ponytail: deterministic-time budget for one period repair. A repair that reaches it keeps
# the greedy fill's feasible choices. Raise it only with a measured period that needs more.
PERIOD_REPAIR_DETERMINISTIC_TIME = 0.02


def _greedy_period_selection(
    options: list[tuple[Assignment, tuple[int, ...]]],
) -> list[tuple[Assignment, int]]:
    """Choose the first available resource combination in option order."""
    selected = []
    classes: set[int] = set()
    teachers: set[int] = set()
    rooms: set[int] = set()
    for assignment, available in options:
        room = next((value for value in available if value not in rooms), None)
        if classes & set(assignment.class_ids) or assignment.teacher_id in teachers or room is None:
            continue
        selected.append((assignment, room))
        classes.update(assignment.class_ids)
        teachers.add(assignment.teacher_id)
        rooms.add(room)
    return selected


def _period_resource_upper_bound(options: list[tuple[Assignment, tuple[int, ...]]]) -> int:
    return min(
        len({class_id for row, _ in options for class_id in row.class_ids}),
        len({row.teacher_id for row, _ in options}),
        len({room for _, available in options for room in available}),
    )


def _period_objective_weights(
    options: list[tuple[Assignment, tuple[int, ...]]],
    scores: Mapping[tuple[int, int], tuple[bool, int, int]] | None,
    fill_admitted: bool,
) -> tuple[dict[int, int], int, int, int]:
    """Keep count, urgency, fill and school values in their original integer scale."""
    total_value = (
        sum(
            abs(value)
            for assignment, available in options
            for room in available
            for _necessary, value, _priority in (
                scores.get((assignment.assignment_id, room), (False, 0, 0)),
            )
        )
        if scores is not None
        else 0
    )
    # Urgency enters the objective as a rank, so school-sized capacities in minutes
    # cannot push the coefficient sum past int64 and invalidate the model.
    urgencies = (
        sorted(
            {
                priority
                for assignment, available in options
                for room in available
                for necessary, _value, priority in (
                    scores.get((assignment.assignment_id, room), (False, 0, 0)),
                )
                if necessary
            }
        )
        if scores is not None
        else []
    )
    urgency_rank = {priority: len(urgencies) - index for index, priority in enumerate(urgencies)}
    max_rank = len(urgencies)
    fill_weight = (2 * total_value + 1) if fill_admitted else 0
    priority_weight = len(options) * fill_weight + 2 * total_value + 1
    priority_bound = len(options) * max_rank * priority_weight + len(options) * fill_weight
    count_weight = (
        priority_bound + 2 * total_value + 1 if scores is not None else len(options) ** 2 + 1
    )
    return urgency_rank, fill_weight, priority_weight, count_weight


def _period_repair_model(
    options: list[tuple[Assignment, tuple[int, ...]]],
    selected: list[tuple[Assignment, int]],
    scores: Mapping[tuple[int, int], tuple[bool, int, int]] | None,
    fill_admitted: bool,
) -> tuple[cp_model.CpModel, dict[tuple, tuple[Assignment, cp_model.IntVar]]]:
    """Build the period model in its original variable and constraint order."""
    model = cp_model.CpModel()
    choices: dict[tuple, tuple[Assignment, cp_model.IntVar]] = {}
    resource_choices: dict[tuple[str, int], list] = defaultdict(list)
    preferred = {(row.assignment_id, room) for row, room in selected}
    choice_variables: list[cp_model.IntVar] = []
    coefficients: list[int] = []
    urgency_rank, fill_weight, priority_weight, count_weight = _period_objective_weights(
        options, scores, fill_admitted
    )
    for rank, (assignment, available) in enumerate(options):
        for room in available:
            key = (assignment.class_ids, assignment.teacher_id, room)
            # Identical resource choices retain the highest-priority subject.
            if key in choices:
                continue
            variable = model.new_bool_var(f"choice_{assignment.assignment_id}_{room}")
            choices[key] = (assignment, variable)
            identities = [
                ("teacher", assignment.teacher_id),
                ("room", room),
                *(("class", class_id) for class_id in assignment.class_ids),
            ]
            for kind, identity in identities:
                resource_choices[(kind, identity)].append(variable)
            if scores is None:
                coefficient = count_weight + len(options) - rank
            else:
                necessary, value, priority = scores.get(
                    (assignment.assignment_id, room), (False, 0, 0)
                )
                coefficient = (
                    int(necessary) * count_weight
                    + urgency_rank.get(priority, 0) * priority_weight * int(necessary)
                    + fill_weight
                    + value
                )
            choice_variables.append(variable)
            coefficients.append(coefficient)
            model.add_hint(variable, int((assignment.assignment_id, room) in preferred))
    for variables in resource_choices.values():
        model.add_at_most_one(variables)
    # An empty period keeps the constant objective it always had.
    objective = (
        cp_model.LinearExpr.weighted_sum(choice_variables, coefficients) if choice_variables else 0
    )
    model.maximize(objective)
    return model, choices


def _solve_period_repair(
    model: cp_model.CpModel,
    choices: dict[tuple, tuple[Assignment, cp_model.IntVar]],
    selected: list[tuple[Assignment, int]],
    *,
    deadline: float | None,
    scores: Mapping[tuple[int, int], tuple[bool, int, int]] | None,
) -> list[tuple[Assignment, int]]:
    """Use the original budgets and preserve greedy fallback and choice order."""
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 1
    if scores is None:
        # ponytail: each period gets a short repair; unresolved choices keep the
        # feasible greedy selection and final coverage still needs validation.
        solver.parameters.max_time_in_seconds = 0.1
        if deadline is not None:
            solver.parameters.max_time_in_seconds = min(0.1, max(0.0, deadline - monotonic()))
    else:
        # Weighted repairs stop in deterministic solver time, so a loaded machine cannot
        # change the schedule (I03). A global deadline still bounds wall time.
        solver.parameters.max_deterministic_time = PERIOD_REPAIR_DETERMINISTIC_TIME
        if deadline is not None:
            solver.parameters.max_time_in_seconds = max(0.0, deadline - monotonic())
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return selected
    return [
        (assignment, key[2])
        for key, (assignment, variable) in choices.items()
        if solver.Value(variable)
    ]


def _select_period(
    options: list[tuple[Assignment, tuple[int, ...]]],
    *,
    deadline: float | None,
    scores: Mapping[tuple[int, int], tuple[bool, int, int]] | None = None,
    fill_admitted: bool = False,
) -> list[tuple[Assignment, int]]:
    """Fill a period; repair greedy resource choices with a small native model.

    With ``fill_admitted`` (relaxed and fill passes) every option the pass admitted
    counts for filling the hour before its value: an admitted option with a negative
    value is still taught rather than left out (T07, T11).
    """
    selected = _greedy_period_selection(options)
    upper = _period_resource_upper_bound(options)
    if scores is None and len(selected) == upper:
        return selected

    if scores is None:
        matched = _flow_selection(options)
        if matched is not None:
            return matched

    # ponytail: resolve only this period, without annual placement variables.
    # A construction dead end still falls back to the existing complete search.
    model, choices = _period_repair_model(options, selected, scores, fill_admitted)
    return _solve_period_repair(model, choices, selected, deadline=deadline, scores=scores)


def _interrupted(deadline: float | None, should_cancel: Callable[[], bool] | None) -> bool:
    return (should_cancel is not None and should_cancel()) or (
        deadline is not None and monotonic() >= deadline
    )


def strict_window_periods(
    snapshot: PlanningSnapshot, periods: tuple[Period, ...], weights: PriorityWeights | None
) -> tuple[Period, ...]:
    """T09: a weighted strict pass places no lesson after the preferred end date.

    Without weights the strict pass keeps every period (I02). The relaxed and fill
    passes always keep every period.
    """
    if weights is None:
        return periods
    return tuple(row for row in periods if row.school_date <= snapshot.preferred_end_date)


def construct_schedule(
    snapshot: PlanningSnapshot,
    periods: tuple[Period, ...],
    *,
    deadline: float | None = None,
    should_cancel: Callable[[], bool] | None = None,
    weekly_reference: CandidateSchedule | None = None,
    weights: PriorityWeights | None = None,
) -> CandidateSchedule | None:
    """Construct one complete plan, preserving hard rules and protected credit.

    The strict pass skips an Evitar block that a teacher or class needs for its
    own hours (tech spec T08). If that filter refused an option and the pass
    failed, one relaxed pass repeats the construction without it (T09).
    """
    strict_periods = strict_window_periods(snapshot, periods, weights)
    candidate, refused, paced_out = _construct_pass(
        snapshot,
        strict_periods,
        deadline=deadline,
        should_cancel=should_cancel,
        weekly_reference=weekly_reference,
        weights=weights,
        strict=weights is None or bool(weights.teacher_preferences or weights.class_preferences),
    )
    if (
        candidate is None
        and (refused or paced_out or strict_periods != periods)
        and not _interrupted(deadline, should_cancel)
    ):
        candidate, _refused, _paced_out = _construct_pass(
            snapshot,
            periods,
            deadline=deadline,
            should_cancel=should_cancel,
            weekly_reference=weekly_reference,
            weights=weights,
            strict=False,
        )
    if candidate is None and weights is not None and not _interrupted(deadline, should_cancel):
        candidate, _refused, _paced_out = _construct_pass(
            snapshot,
            periods,
            deadline=deadline,
            should_cancel=should_cancel,
            weekly_reference=weekly_reference,
            weights=weights,
            strict=False,
            fill=True,
        )
    return candidate


class _ConstructionPass:
    """One generation pass owns committed resources and tentative presence previews."""

    def __init__(
        self,
        snapshot: PlanningSnapshot,
        periods: tuple[Period, ...],
        *,
        deadline: float | None,
        should_cancel: Callable[[], bool] | None,
        weekly_reference: CandidateSchedule | None,
        weights: PriorityWeights | None,
        strict: bool,
        fill: bool,
    ) -> None:
        self.snapshot = snapshot
        self.periods = periods
        self.deadline = deadline
        self.should_cancel = should_cancel
        self.weekly_reference = weekly_reference
        self.weights = weights
        self.strict = strict
        self.fill = fill
        self.initialize_calendar()
        self.initialize_progress()
        self.initialize_weekly_reference()
        self.initialize_identities()
        self.initialize_protected()
        self.initialize_precedence()

    def initialize_calendar(self):
        self.canonical = canonical_periods(self.periods)
        slots = sorted(
            self.snapshot.grid_slots,
            key=lambda slot: (slot.day_of_week, slot.start_local, slot.end_local),
        )
        self.preceding_ends = {
            (right.day_of_week, right.start_local, right.end_local): left.end_local.hour * 60
            + left.end_local.minute
            for left, right in zip(slots, slots[1:], strict=False)
            if left.day_of_week == right.day_of_week and left.end_local <= right.start_local
        }

    def initialize_progress(self):
        self.assignments = {row.assignment_id: row for row in self.snapshot.assignments}
        self.home_rooms = {row.class_id: row.room_id for row in self.snapshot.home_rooms}
        self.pace_peers = _pace_peers(self.assignments) if self.weights is not None else {}
        self.evitar_kinds = _evitar_kinds(self.weights)
        self.required = {
            identity: sum(module.required_minutes for module in row.modules)
            for identity, row in self.assignments.items()
        }
        self.remaining = {
            identity: residual_minutes(self.snapshot, identity) for identity in self.assignments
        }
        self.initial_remaining = dict(self.remaining)
        self.cursor = {
            identity: {
                module.module_id: self.snapshot.executed_minutes.get(identity, {}).get(
                    module.module_id, 0
                )
                for module in row.modules
            }
            for identity, row in self.assignments.items()
        }

    def initialize_weekly_reference(self):
        self.busy: dict[tuple, list[Period]] = defaultdict(list)
        self.occupancy: dict[tuple, list[tuple[int, int]]] = defaultdict(list)
        self.weekly_pattern: dict[tuple, tuple[int, int]] = {}
        # Weighted weekly stability compares with the previous teaching day, as the metric
        # does; the unweighted ordering keeps its first-week pattern (I02).
        self.weekly_history = WeeklyHistory(self.snapshot)
        if self.weekly_reference is not None:
            for row in self.weekly_reference.lessons:
                assignment = self.assignments.get(row.assignment_id)
                if assignment is not None:
                    for class_id in assignment.class_ids:
                        self.weekly_pattern.setdefault(
                            (
                                class_id,
                                row.period.school_date.weekday(),
                                row.period.start_local,
                                row.period.end_local,
                            ),
                            (row.assignment_id, row.room_id),
                        )
                        if self.weights is not None:
                            self.weekly_history.record(
                                class_id,
                                row.period.school_date,
                                row.period.start_local,
                                row.period.end_local,
                                row.assignment_id,
                            )

    def initialize_identities(self):
        self.used_ids = {row.lesson_id for row in self.snapshot.protected_lessons} | set(
            self.snapshot.reserved_lesson_ids
        )
        self.started_classes = {
            class_id
            for identity, row in self.assignments.items()
            if self.remaining[identity] < self.required[identity]
            for class_id in row.class_ids
        }

    def initialize_protected(self):
        self.protected_intervals: dict[tuple, set[tuple[int, int]]] = defaultdict(set)
        for lesson in self.snapshot.protected_lessons:
            assignment = self.assignments[lesson.assignment_id]
            teacher = lesson.teacher_id or assignment.teacher_id
            self.occupy(assignment, lesson.period, lesson.room_id, teacher)
            self.protected_intervals[("teacher", teacher, lesson.period.school_date)].add(
                _local_interval(lesson.period)
            )
            for module_slice in lesson.slices:
                self.cursor[lesson.assignment_id][module_slice.module_id] += (
                    module_slice.credit_minutes
                )

    def initialize_precedence(self):
        self.predecessors: dict[int, list[int]] = defaultdict(list)
        for source, target in self.snapshot.precedences:
            self.predecessors[target].append(source)
        self.last_end: dict[int, datetime] = {}
        for lesson in self.snapshot.protected_lessons:
            current = self.last_end.get(lesson.assignment_id)
            if current is None or lesson.period.end_utc > current:
                self.last_end[lesson.assignment_id] = lesson.period.end_utc

    def prepare_options(self):
        self.options_by_period: dict[Period, list[Assignment]] = defaultdict(list)
        self.eligible_by_assignment: dict[int, tuple[Period, ...]] = {}
        self.room_pressure: dict[int, Fraction] = defaultdict(Fraction)
        self.class_remaining: dict[int, int] = defaultdict(int)
        self.teacher_remaining: dict[int, int] = defaultdict(int)
        for identity, assignment in self.assignments.items():
            if _interrupted(self.deadline, self.should_cancel):
                return False
            if self.remaining[identity] <= 0:
                continue
            eligible = eligible_periods(self.snapshot, assignment, self.canonical)
            self.eligible_by_assignment[identity] = eligible
            for period in eligible:
                self.options_by_period[period].append(assignment)
            for class_id in assignment.class_ids:
                self.class_remaining[class_id] += self.remaining[identity]
            self.teacher_remaining[assignment.teacher_id] += self.remaining[identity]
            for room in assignment.eligible_room_ids:
                self.room_pressure[room] += Fraction(
                    self.remaining[identity], len(assignment.eligible_room_ids)
                )
        return True

    def initialize_presence(self):
        self._ledger = AvailabilityLedger.build(
            self.snapshot, self.eligible_by_assignment, self.remaining
        )
        self.ranks: dict[int, int] = defaultdict(int)
        self.lessons: list[ScheduledLesson] = []
        self.dispensed_teachers = self.snapshot.lunch_dispensed_teacher_ids
        self.presence_rules = _minimum_presence_teachers(self.snapshot)
        self.slots_by_day = _slots_by_day(self.snapshot)
        self.longest_presence = _longest_presences(
            self.snapshot, self.presence_rules, self.slots_by_day
        )
        self.grid_intervals = _grid_intervals_by_day(self.slots_by_day)
        self.periods_by_date: dict[date, list[Period]] = defaultdict(list)
        for day_period in self.canonical:
            self.periods_by_date[day_period.school_date].append(day_period)
        self.assignments_by_teacher: dict[int, list[Assignment]] = defaultdict(list)
        for row in self.snapshot.assignments:
            self.assignments_by_teacher[row.teacher_id].append(row)

    def occupy(self, assignment: Assignment, period: Period, room: int, teacher: int) -> None:
        for class_id in assignment.class_ids:
            slot_key = (
                class_id,
                period.school_date.weekday(),
                period.start_local,
                period.end_local,
            )
            self.weekly_pattern.setdefault(slot_key, (assignment.assignment_id, room))
            if self.weights is not None:
                self.weekly_history.record(
                    class_id,
                    period.school_date,
                    period.start_local,
                    period.end_local,
                    assignment.assignment_id,
                )
        for key in _resource_keys(assignment, room, teacher, period.school_date):
            self.busy[key].append(period)
            if key[0] != "room":
                self.occupancy[key].append(_local_interval(period))

    def ready(self, identity: int, period: Period) -> bool:
        """All predecessor units are finished before the period (WBS 3.3.2)."""
        return _predecessors_ready(
            self.predecessors, self.remaining, self.last_end, identity, period
        )

    def place(self, assignment: Assignment, period: Period, room: int) -> bool:
        """Book one lesson and its module slices; False when no module credit is left."""
        identity = assignment.assignment_id
        credit = min(self.remaining[identity], period.duration_minutes)
        self.ranks[identity] += 1
        lesson_id = allocate_lesson_identity(identity, self.ranks[identity], self.used_ids)
        slices = []
        unallocated = credit
        while unallocated > 0:
            module_index = _next_module(assignment.modules, self.cursor[identity])
            if module_index is None:
                return False
            module = assignment.modules[module_index]
            offset = self.cursor[identity][module.module_id]
            take = min(unallocated, module.required_minutes - offset)
            slices.append(ModuleSlice(lesson_id, module.module_id, offset, take))
            self.cursor[identity][module.module_id] += take
            unallocated -= take
        self.lessons.append(
            ScheduledLesson(lesson_id, identity, period, room, credit, tuple(slices))
        )
        self.remaining[identity] -= credit
        self._ledger.place(assignment, credit)
        for class_id in assignment.class_ids:
            self.class_remaining[class_id] -= credit
            self.started_classes.add(class_id)
        self.teacher_remaining[assignment.teacher_id] -= credit
        current_end = self.last_end.get(identity)
        if current_end is None or period.end_utc > current_end:
            self.last_end[identity] = period.end_utc
        self.occupy(assignment, period, room, assignment.teacher_id)
        return True

    def presence_complies(
        self, teacher_id: int, school_date: date, booked: Sequence[Period]
    ) -> bool:
        """True when the teacher's day, with the booked periods, meets the presence rule."""
        key = ("teacher", teacher_id, school_date)
        return _presence_day_complies(
            (*self.occupancy[key], *(_local_interval(period) for period in booked)),
            self.protected_intervals[key],
            self.presence_rules[teacher_id],
            self.snapshot.lunch_rule,
            self.grid_intervals.get(school_date.weekday(), ()),
        )

    def open_rooms(
        self,
        assignment: Assignment,
        period: Period,
        pending: Mapping[tuple, list[Period]],
        planned: Sequence[tuple[Assignment, int]] = (),
    ) -> tuple[int, ...]:
        """Rooms where the assignment may teach the period, empty when a rule blocks it.

        ``pending`` and ``planned`` describe lessons tentatively booked by a presence
        run; the main loop passes none. Every hard check runs here, so both paths share it.
        """
        school_date = period.school_date

        def booked(key: tuple) -> list[Period]:
            return [*self.busy[key], *pending.get(key, ())]

        keys = (
            ("teacher", assignment.teacher_id, school_date),
            *(("class", class_id, school_date) for class_id in assignment.class_ids),
        )
        if any(period.overlaps(occupied) for key in keys for occupied in booked(key)):
            return ()
        if self.snapshot.lunch_rule is not None and any(
            continuous_break_minutes(
                [*(_local_interval(occupied) for occupied in booked(key)), _local_interval(period)],
                self.snapshot.lunch_rule,
            )
            < self.snapshot.lunch_rule.minimum_minutes
            for key in keys
            if not (key[0] == "teacher" and key[1] in self.dispensed_teachers)
        ):
            return ()
        rooms = tuple(
            room
            for room in available_rooms(self.snapshot, assignment, period)
            if not any(
                period.overlaps(occupied) for occupied in booked(("room", room, school_date))
            )
        )
        preference_avoided = (
            self.weights is None
            or (
                self.weights.teacher_preferences > 0
                and any(
                    row.overlaps(period)
                    for row in self.snapshot.soft_unavailable_on(
                        UnavailableResource.TEACHER, assignment.teacher_id, period.school_date
                    )
                )
            )
            or (
                self.weights is not None
                and self.weights.class_preferences > 0
                and any(
                    row.overlaps(period)
                    for class_id in assignment.class_ids
                    for row in self.snapshot.soft_unavailable_on(
                        UnavailableResource.CLASS, class_id, period.school_date
                    )
                )
            )
        )
        if not rooms or (
            self.strict
            and preference_avoided
            and not self._ledger.allows(assignment, period, planned, evitar_kinds=self.evitar_kinds)
        ):
            return ()
        return rooms

    def plan_presence_run(self, assignment: Assignment, period: Period, room: int):
        """Preview later lessons without committing resources or curricular credit."""
        teacher_id = assignment.teacher_id
        school_date = period.school_date
        self.preview_booked = []
        self.preview_pending = defaultdict(list)
        self.preview_planned = []
        self.preview_credited = defaultdict(int)
        self.add_preview((assignment, period, room), teacher_id)
        for later in self.periods_by_date[school_date]:
            if later.start_utc <= period.start_utc:
                continue
            choice = self.next_presence_lesson(teacher_id, later)
            if choice is None:
                continue
            self.add_preview((choice[0], later, choice[1]), teacher_id)
            if self.preview_complete(teacher_id, school_date):
                return self.preview_booked
        return None

    def add_preview(self, row, teacher_id):
        self.preview_booked.append(row)
        assignment, period, room = row
        identity = assignment.assignment_id
        credit = min(
            self.remaining[identity] - self.preview_credited[identity], period.duration_minutes
        )
        self.preview_credited[identity] += credit
        self.preview_planned.append((assignment, credit))
        for key in _resource_keys(assignment, room, teacher_id, period.school_date):
            self.preview_pending[key].append(period)

    def preview_complete(self, teacher_id, school_date):
        left = self.teacher_remaining[teacher_id] - sum(self.preview_credited.values())
        return self.presence_complies(
            teacher_id,
            school_date,
            [period for _a, period, _r in self.preview_booked],
        ) and _presence_left_fits(
            left, self.presence_rules[teacher_id], self.longest_presence[teacher_id]
        )

    def next_presence_lesson(self, teacher_id, later):
        previous = self.preview_booked[-1][0].assignment_id
        candidates = sorted(
            (
                row
                for row in self.assignments_by_teacher[teacher_id]
                if self.remaining[row.assignment_id] - self.preview_credited[row.assignment_id] > 0
                and later in self.eligible_by_assignment.get(row.assignment_id, ())
            ),
            key=lambda row: (
                row.assignment_id != previous,
                -(self.remaining[row.assignment_id] - self.preview_credited[row.assignment_id]),
                row.assignment_id,
            ),
        )
        for row in candidates:
            if not self.ready(row.assignment_id, later):
                continue
            rooms = self.open_rooms(row, later, self.preview_pending, self.preview_planned)
            if rooms:
                return row, min(rooms, key=lambda room: (self.room_pressure[room], room))
        return None

    def presence_run(
        self, assignment: Assignment, period: Period, room: int
    ) -> list[tuple[Assignment, Period, int]] | None:
        """The lessons that book this option, or None when a presence rule forbids it.

        A lesson that leaves its day short of the presence minimum is booked only with
        the later run that completes it. Extending a compliant presence must not strand
        minutes that no split into valid presences could ever teach.
        """
        teacher_id = assignment.teacher_id
        if teacher_id not in self.presence_rules:
            return [(assignment, period, room)]
        if not self.presence_complies(teacher_id, period.school_date, [period]):
            return self.plan_presence_run(assignment, period, room)
        credit = min(self.remaining[assignment.assignment_id], period.duration_minutes)
        left = self.teacher_remaining[teacher_id] - credit
        if not _presence_left_fits(
            left, self.presence_rules[teacher_id], self.longest_presence[teacher_id]
        ):
            return None
        return [(assignment, period, room)]

    def run(self) -> tuple[CandidateSchedule | None, int, bool]:
        if not self.prepare_options():
            return None, 0, False
        self.initialize_presence()
        self.pace_watch = PaceWatch() if self.weights is not None and self.strict else None
        for period in self.canonical:
            stop, paced_out = self.stop_before_period(period)
            if stop:
                return None, self._ledger.refused, paced_out
            options = self.period_options(period)
            if options is None:
                continue
            if not self.place_period(period, *options):
                return None, self._ledger.refused, False
            if not any(self.remaining.values()):
                break
        return self.build_candidate()

    def stop_before_period(self, period):
        if _interrupted(self.deadline, self.should_cancel):
            return True, False
        if _gives_up(self._ledger, period, strict=self.strict):
            return True, False
        if self.pace_watch is not None and self.pace_watch.gives_up(self._ledger, period):
            return True, True
        return False, False

    def build_candidate(self):
        if any(self.remaining.values()):
            return None, self._ledger.refused, False
        candidate = CandidateSchedule((*self.snapshot.protected_lessons, *self.lessons))
        valid = validate_candidate(self.snapshot, candidate).valid
        return (candidate if valid else None), self._ledger.refused, False

    def rooms_for_option(self, assignment, period, signature):
        preferred = self.weekly_preferred(assignment, signature)
        preferred_room = (
            preferred[1]
            if preferred is not None and preferred[0] == assignment.assignment_id
            else None
        )
        return tuple(
            sorted(
                self.open_rooms(assignment, period, {}),
                key=lambda room: (room != preferred_room, self.room_pressure[room], room),
            )
        )

    def period_options(self, period):
        active = [
            row
            for row in self.options_by_period[period]
            if self.remaining[row.assignment_id] > 0 and self.ready(row.assignment_id, period)
        ]
        if not active:
            return None
        preceding_end = self.preceding_ends.get(
            (period.school_date.weekday(), period.start_local, period.end_local)
        )
        signature = (period.school_date.weekday(), period.start_local, period.end_local)
        options = []
        scores = {} if self.weights is not None else None
        for assignment in sorted(
            active, key=lambda row: self.priority(row, period, preceding_end, signature)
        ):
            rooms = self.rooms_for_option(assignment, period, signature)
            if not rooms or self.presence_run(assignment, period, rooms[0]) is None:
                continue
            if self.weights is None:
                options.append((assignment, rooms))
                continue
            admitted = self.weighted_rooms(assignment, period, rooms, scores)
            if admitted:
                options.append((assignment, admitted))
        if scores is not None:
            self.sort_weighted_options(options, scores)
        return options, scores

    def place_period(self, period, options, scores):
        for assignment, room in _select_period(
            options,
            deadline=self.deadline,
            scores=scores,
            fill_admitted=scores is not None and not self.strict,
        ):
            run = self.presence_run(assignment, period, room)
            if run is None:
                continue
            for run_assignment, run_period, run_room in run:
                if not self.place(run_assignment, run_period, run_room):
                    return False
        return True

    def weekly_preferred(self, assignment: Assignment, current_signature: tuple):
        for class_id in assignment.class_ids:
            preferred = self.weekly_pattern.get((class_id, *current_signature))
            if preferred is not None:
                return preferred
        return None

    def priority(self, assignment, current_period, previous_end, current_signature):
        identity = assignment.assignment_id
        preferred = self.weekly_preferred(assignment, current_signature)
        repeats = preferred is not None and preferred[0] == identity
        continues = _continues_open_presence(
            self.slots_by_day,
            self.occupancy,
            assignment.teacher_id,
            current_period,
            self.presence_rules,
        )
        adjacent = sum(
            any(
                end == previous_end
                for _start, end in self.occupancy[(kind, resource, current_period.school_date)]
            )
            for kind, resource in (
                *(("class", class_id) for class_id in assignment.class_ids),
                ("teacher", assignment.teacher_id),
            )
        )
        return (
            self._ledger.priority(assignment, current_period),
            self._ledger.unfavorable(assignment, current_period, evitar_kinds=self.evitar_kinds),
            any(class_id in self.started_classes for class_id in assignment.class_ids),
            self.initial_remaining[identity] != self.remaining[identity],
            Fraction(
                self.required[identity]
                - self.remaining[identity]
                - (
                    min(self.remaining[identity], current_period.duration_minutes) if repeats else 0
                ),
                self.required[identity],
            ),
            not continues,
            -adjacent,
            preferred is None,
            not repeats,
            -self.teacher_remaining[assignment.teacher_id],
            -sum(self.class_remaining[class_id] for class_id in assignment.class_ids),
            len(assignment.eligible_room_ids),
            identity,
        )

    def weighted_rooms(self, assignment, period, rooms, scores):
        """Admit rooms using necessity, scarcity, school values and pass policy."""
        identity = assignment.assignment_id
        necessary = self._ledger.is_necessary(assignment, period, evitar_kinds=self.evitar_kinds)
        urgency = self._ledger.urgency(assignment, period)
        allowed_rooms = []
        credit = min(self.remaining[identity], period.duration_minutes)
        measures = _option_measures(
            self.snapshot,
            assignment,
            period,
            credit=credit,
            needed_evitar=self._ledger.needed_evitar(
                assignment, period, evitar_kinds=self.evitar_kinds
            ),
            occupancy=self.occupancy,
            day_slots=self.slots_by_day.get(period.school_date.weekday(), ()),
            counts_teacher_single_lessons=assignment.teacher_id not in self.presence_rules,
            weekly_references=tuple(
                self.weekly_history.reference(
                    class_id, period.school_date, period.start_local, period.end_local
                )
                for class_id in assignment.class_ids
            ),
            pace_lag=_pace_lag(identity, self.pace_peers[identity], self.required, self.remaining),
        )
        scarcity = _scarcity(self._ledger, assignment, period, credit)
        base_value = option_value(self.weights, measures) + class_day_excess_value(
            (
                self.occupancy[("class", class_id, period.school_date)]
                for class_id in assignment.class_ids
            ),
            _local_interval(period),
            self.slots_by_day.get(period.school_date.weekday(), ()),
            self.snapshot.lunch_rule,
        )
        same_room_value = option_value(self.weights, {"class_same_room": -credit})
        preference_value = _preference_value(self.weights, measures)
        for room in rooms:
            value = _room_value(base_value, same_room_value, assignment, room, self.home_rooms)
            if necessary or _fills_hour(
                value + scarcity, preference_value, strict=self.strict, fill=self.fill
            ):
                allowed_rooms.append(room)
                scores[(identity, room)] = (necessary, value, urgency)
        return tuple(allowed_rooms)

    def sort_weighted_options(self, options, scores):
        options.sort(
            key=lambda row: max(
                (
                    int(scores[(row[0].assignment_id, room)][0]),
                    -scores[(row[0].assignment_id, room)][2]
                    if scores[(row[0].assignment_id, room)][0]
                    else 0,
                    scores[(row[0].assignment_id, room)][1],
                )
                for room in row[1]
            ),
            reverse=True,
        )


def _construct_pass(
    snapshot: PlanningSnapshot,
    periods: tuple[Period, ...],
    *,
    deadline: float | None,
    should_cancel: Callable[[], bool] | None,
    weekly_reference: CandidateSchedule | None,
    weights: PriorityWeights | None,
    strict: bool,
    fill: bool = False,
) -> tuple[CandidateSchedule | None, int, bool]:
    """One construction pass.

    Returns the plan, the options the Evitar filter refused, and whether the weekly pace
    check stopped the pass (SCHEDULE_PRIORITIES T07).
    """
    return _ConstructionPass(
        snapshot,
        periods,
        deadline=deadline,
        should_cancel=should_cancel,
        weekly_reference=weekly_reference,
        weights=weights,
        strict=strict,
        fill=fill,
    ).run()
