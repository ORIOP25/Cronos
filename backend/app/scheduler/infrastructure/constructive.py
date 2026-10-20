"""Chronological construction with parallel curricular progress.

Teachers and classes with less availability take priority while on pace, then
lessons outside Evitar blocks, then subjects with less progress (D32, D33).
Repeating the weekly pattern may compensate for one lesson of progress.
Free resource combinations remain eligible even when other subjects must wait.
Construction failure is inconclusive; every returned plan is independently valid.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from datetime import date, datetime, time
from fractions import Fraction
from time import monotonic

from ortools.graph.python import min_cost_flow
from ortools.sat.python import cp_model

from app.scheduler.domain.availability_priority import (
    CLASS,
    RESOURCE_KINDS,
    TEACHER,
    AvailabilityLedger,
)
from app.scheduler.domain.calendar import Period
from app.scheduler.domain.candidate import (
    Assignment,
    CandidateSchedule,
    GridSlot,
    LunchRule,
    PlanningSnapshot,
    ScheduledLesson,
    TeacherPresenceRule,
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
from app.scheduler.domain.priorities import PriorityWeights, shift_of
from app.scheduler.domain.priority_value import option_value
from app.scheduler.domain.projection import ModuleSlice
from app.scheduler.domain.quality import lunch_minutes_in
from app.scheduler.domain.teacher_presence import (
    PresenceLesson,
    longest_presence_minutes,
    presence_minutes_fit,
    teacher_day_complies,
)


def _local_interval(period: Period) -> tuple[int, int]:
    return (
        period.start_local.hour * 60 + period.start_local.minute,
        period.end_local.hour * 60 + period.end_local.minute,
    )


def _grid_interval(slot: GridSlot) -> tuple[int, int]:
    return (
        slot.start_local.hour * 60 + slot.start_local.minute,
        slot.end_local.hour * 60 + slot.end_local.minute,
    )


def _gap_minutes(
    intervals: Iterable[tuple[int, int]],
    slots: Sequence[GridSlot],
    lunch_rule: LunchRule | None = None,
) -> int:
    """Free minutes between the first and last lesson: empty grid slots minus lunch."""
    grid = [_grid_interval(slot) for slot in slots]
    positions = {interval: index for index, interval in enumerate(grid)}
    occupied = {positions[interval] for interval in intervals if interval in positions}
    if len(occupied) < 2:
        return 0
    empty = [
        grid[index] for index in range(min(occupied) + 1, max(occupied)) if index not in occupied
    ]
    return sum(end - start for start, end in empty) - lunch_minutes_in(empty, lunch_rule)


def _gap_option_measure(
    intervals: Sequence[tuple[int, int]],
    interval: tuple[int, int],
    slots: Sequence[GridSlot],
    *,
    credit: int,
    lunch_rule: LunchRule | None = None,
) -> int:
    """T06: the gap minutes a lesson removes, plus its credit when it continues a neighbour.

    A neighbour is the previous or next grid slot, whatever break separates them.
    """
    removed = _gap_minutes(intervals, slots, lunch_rule) - _gap_minutes(
        (*intervals, interval), slots, lunch_rule
    )
    grid = [_grid_interval(slot) for slot in slots]
    position = grid.index(interval) if interval in grid else None
    continues = position is not None and any(
        neighbour in intervals
        for neighbour in grid[max(0, position - 1) : position + 2]
        if neighbour != interval
    )
    return removed + (credit if continues else 0)


def _single_shift_count(
    intervals: Iterable[tuple[int, int]], lunch_rule: LunchRule | None, *, lunch_required: bool
) -> int:
    shifts: dict[str, int] = defaultdict(int)
    for start, _end in intervals:
        shift = shift_of(time(start // 60, start % 60), lunch_rule, lunch_required=lunch_required)
        shifts[shift] += 1
    return sum(count == 1 for count in shifts.values())


def _joined_shift_gain(
    intervals: Sequence[tuple[int, int]],
    interval: tuple[int, int],
    lunch_rule: LunchRule | None,
    *,
    lunch_required: bool,
) -> int:
    """One when the lesson joins a shift that held exactly one lesson, else zero.

    The first lesson of a shift is not penalised (owner decision, 19 Oct 2026).
    """
    before = _single_shift_count(intervals, lunch_rule, lunch_required=lunch_required)
    after = _single_shift_count((*intervals, interval), lunch_rule, lunch_required=lunch_required)
    return max(0, before - after)


def _pace_peers(assignments: Mapping[int, Assignment]) -> dict[int, tuple[int, ...]]:
    """The assignments that share a class with each assignment, itself included."""
    return {
        identity: tuple(
            other_id
            for other_id, other in assignments.items()
            if set(other.class_ids) & set(row.class_ids)
        )
        for identity, row in assignments.items()
    }


def _pace_lag(
    identity: int,
    peers: Sequence[int],
    required: Mapping[int, int],
    remaining: Mapping[int, int],
) -> Fraction | None:
    """T06: how far a subject is behind the mean progress of its class subjects."""
    if len(peers) < 2:
        return None
    progress = {peer: Fraction(required[peer] - remaining[peer], required[peer]) for peer in peers}
    return sum(progress.values(), Fraction()) / len(peers) - progress[identity]


def _option_measures(
    snapshot: PlanningSnapshot,
    assignment: Assignment,
    period: Period,
    *,
    credit: int,
    needed_evitar: frozenset[tuple[str, int]],
    occupancy: Mapping[tuple, Sequence[tuple[int, int]]],
    day_slots: Sequence[GridSlot],
    counts_teacher_single_lessons: bool,
    weekly_assignment_id: int | None,
    pace_lag: Fraction | None,
) -> dict[str, int]:
    """T06: the room-independent measures of one option, in lesson minutes.

    Generation and updates share this function, so a level means the same in both.
    """
    interval = _local_interval(period)
    teacher_intervals = occupancy[("teacher", assignment.teacher_id, period.school_date)]
    measures = {
        "finish_early": credit,
        "teacher_gaps": _gap_option_measure(
            teacher_intervals,
            interval,
            day_slots,
            credit=credit,
            lunch_rule=(
                None
                if assignment.teacher_id in snapshot.lunch_dispensed_teacher_ids
                else snapshot.lunch_rule
            ),
        ),
    }
    if counts_teacher_single_lessons:
        lunch_required = assignment.teacher_id not in snapshot.lunch_dispensed_teacher_ids
        measures["teacher_single_lessons"] = (
            _joined_shift_gain(
                teacher_intervals, interval, snapshot.lunch_rule, lunch_required=lunch_required
            )
            * credit
        )
    if (TEACHER, assignment.teacher_id) not in needed_evitar and _soft_overlap(
        snapshot, UnavailableResource.TEACHER, assignment.teacher_id, period
    ):
        measures["teacher_preferences"] = -credit
    for class_id in assignment.class_ids:
        class_intervals = occupancy[("class", class_id, period.school_date)]
        measures["class_gaps"] = measures.get("class_gaps", 0) + _gap_option_measure(
            class_intervals, interval, day_slots, credit=credit, lunch_rule=snapshot.lunch_rule
        )
        measures["class_single_lessons"] = measures.get("class_single_lessons", 0) + (
            _joined_shift_gain(class_intervals, interval, snapshot.lunch_rule, lunch_required=True)
            * credit
        )
        if (CLASS, class_id) not in needed_evitar and _soft_overlap(
            snapshot, UnavailableResource.CLASS, class_id, period
        ):
            measures["class_preferences"] = measures.get("class_preferences", 0) - credit
    if weekly_assignment_id is not None:
        measures["weekly_stability"] = (
            credit if weekly_assignment_id == assignment.assignment_id else -credit
        )
    if pace_lag is not None:
        measures["subject_pace"] = round(pace_lag * credit)
    return measures


def _room_value(
    weights: PriorityWeights,
    measures: Mapping[str, int],
    assignment: Assignment,
    room: int,
    home_rooms: Mapping[int, int],
    *,
    credit: int,
) -> int:
    """T06: the option value in one room; only the home-room measure depends on it."""
    room_measures = dict(measures)
    if not assignment.needs_special_room and any(
        class_id in home_rooms
        and home_rooms[class_id] in assignment.eligible_room_ids
        and home_rooms[class_id] != room
        for class_id in assignment.class_ids
    ):
        room_measures["class_same_room"] = -credit
    return option_value(weights, room_measures)


_PREFERENCE_KEYS = ("teacher_preferences", "class_preferences")


def _fills_hour(
    weights: PriorityWeights,
    measures: Mapping[str, int],
    value: int,
    *,
    strict: bool,
    fill: bool = False,
) -> bool:
    """T07: whether an option's value is worth teaching instead of leaving the hour empty.

    The relaxed pass runs because the strict pass proved some Evitar unavoidable.
    There Evitar still orders the options through ``value``, but it no longer
    leaves an hour empty, as in the construction without weights. The fill pass
    runs when leaving hours empty made both passes fail: every hour that can be
    taught is taught, and the priorities only choose which lesson (T11).
    """
    if fill:
        return True
    if strict:
        return value > 0
    preferences = {key: measures[key] for key in _PREFERENCE_KEYS if key in measures}
    return value - option_value(weights, preferences) > 0


def _soft_overlap(
    snapshot: PlanningSnapshot, resource: UnavailableResource, identity: int, period: Period
) -> bool:
    return any(
        row.overlaps(period)
        for row in snapshot.soft_unavailable_on(resource, identity, period.school_date)
    )


def _evitar_kinds(weights: PriorityWeights | None) -> frozenset[str]:
    """The resource kinds whose Evitar blocks steer the construction (D01, I05).

    Without weights the construction keeps its availability rules for both kinds.
    """
    if weights is None:
        return RESOURCE_KINDS
    return frozenset(
        kind
        for kind, level in (
            (TEACHER, weights.teacher_preferences),
            (CLASS, weights.class_preferences),
        )
        if level > 0
    )


def _minimum_presence_teachers(snapshot: PlanningSnapshot) -> dict[int, TeacherPresenceRule]:
    """Teachers with a presence minimum, keyed by teacher id."""
    return {
        row.teacher_id: row for row in snapshot.teacher_presence if row.minimum_minutes is not None
    }


def _longest_presences(
    snapshot: PlanningSnapshot,
    rules: Mapping[int, TeacherPresenceRule],
    slots_by_day: Mapping[int, Sequence[GridSlot]],
) -> dict[int, int]:
    """The longest presence each teacher with a minimum can hold on any grid day."""
    return {
        teacher_id: max(
            (
                longest_presence_minutes(
                    rule, [_grid_interval(slot) for slot in slots], lunch_rule=snapshot.lunch_rule
                )
                for slots in slots_by_day.values()
            ),
            default=0,
        )
        for teacher_id, rule in rules.items()
    }


def _presence_left_fits(left: int, rule: TeacherPresenceRule, longest: int) -> bool:
    """Minutes left to a teacher must still split into valid presences (no stranded hours)."""
    return presence_minutes_fit(left, minimum=rule.minimum_minutes, longest=longest)


def _grid_intervals_by_day(
    slots_by_day: Mapping[int, Sequence[GridSlot]],
) -> dict[int, tuple[tuple[int, int], ...]]:
    return {
        day: tuple(_grid_interval(slot) for slot in day_slots)
        for day, day_slots in slots_by_day.items()
    }


def _presence_day_complies(
    intervals: Iterable[tuple[int, int]],
    protected: AbstractSet[tuple[int, int]],
    rule: TeacherPresenceRule,
    lunch_rule: LunchRule | None,
    grid_slots: Sequence[tuple[int, int]],
) -> bool:
    """True when a teacher's booked intervals on one day meet the presence rule."""
    lessons = [PresenceLesson(start, end, (start, end) in protected) for start, end in intervals]
    return teacher_day_complies(lessons, rule, lunch_rule=lunch_rule, grid_slots=grid_slots)


def _resource_keys(
    assignment: Assignment, room: int, teacher: int, school_date: date
) -> tuple[tuple, ...]:
    """Busy keys of one lesson: its teacher, room and classes on the date."""
    return (
        ("teacher", teacher, school_date),
        ("room", room, school_date),
        *(("class", class_id, school_date) for class_id in assignment.class_ids),
    )


def _slots_by_day(snapshot: PlanningSnapshot) -> dict[int, tuple[GridSlot, ...]]:
    by_day: dict[int, list[GridSlot]] = defaultdict(list)
    for slot in snapshot.grid_slots:
        by_day[slot.day_of_week].append(slot)
    return {
        day: tuple(sorted(rows, key=lambda slot: (slot.start_local, slot.end_local)))
        for day, rows in by_day.items()
    }


def _slot_position_for_interval(slots: Sequence[GridSlot], interval: tuple[int, int]) -> int | None:
    start, end = interval
    for position, slot in enumerate(slots):
        if (
            slot.start_local.hour * 60 + slot.start_local.minute == start
            and slot.end_local.hour * 60 + slot.end_local.minute == end
        ):
            return position
    return None


def _continues_open_presence(
    slots_by_day: dict[int, tuple[GridSlot, ...]],
    occupancy: dict,
    teacher_id: int,
    period: Period,
    presence_rules: dict[int, TeacherPresenceRule],
) -> bool:
    """True when the period extends an open presence of a minimum teacher.

    Adjacency is by grid position, not by wall-clock minutes, so the default
    grid's short inter-block break still counts as continuing. The exact
    minimum/gap semantics live in ``domain/teacher_presence.py`` and the
    validator; this only prefers extending an open run so a presence reaches the
    minimum instead of fragmenting the day.
    """
    if teacher_id not in presence_rules:
        return False
    slots = slots_by_day.get(period.school_date.weekday(), ())
    position = _slot_position_for_interval(slots, _local_interval(period))
    if position is None:
        return False
    return any(
        (other := _slot_position_for_interval(slots, row)) is not None
        and abs(other - position) == 1
        for row in occupancy[("teacher", teacher_id, period.school_date)]
    )


def _next_module(modules, cursor: dict[int, int]) -> int | None:
    for index, module in enumerate(modules):
        if cursor[module.module_id] < module.required_minutes:
            return index
    return None


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


def _select_period(
    options: list[tuple[Assignment, tuple[int, ...]]],
    *,
    deadline: float | None,
    scores: Mapping[tuple[int, int], tuple[bool, int, int]] | None = None,
) -> list[tuple[Assignment, int]]:
    """Fill a period; repair greedy resource choices with a small native model."""
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
    upper = min(
        len({class_id for row, _ in options for class_id in row.class_ids}),
        len({row.teacher_id for row, _ in options}),
        len({room for _, available in options for room in available}),
    )
    if scores is None and len(selected) == upper:
        return selected

    if scores is None:
        matched = _flow_selection(options)
        if matched is not None:
            return matched

    # ponytail: resolve only this period, without annual placement variables.
    # A construction dead end still falls back to the existing complete search.
    model = cp_model.CpModel()
    choices: dict[tuple, tuple[Assignment, cp_model.IntVar]] = {}
    resource_choices: dict[tuple[str, int], list] = defaultdict(list)
    preferred = {(row.assignment_id, room) for row, room in selected}
    terms = []
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
    priority_weight = 2 * total_value + 1
    priority_bound = len(options) * max_rank * priority_weight + 2 * total_value
    count_weight = priority_bound + 1 if scores is not None else len(options) ** 2 + 1
    for rank, (assignment, available) in enumerate(options):
        for room in available:
            key = (assignment.class_ids, assignment.teacher_id, room)
            # Identical resource choices retain the highest-priority subject.
            if key in choices:
                continue
            variable = model.NewBoolVar(f"choice_{assignment.assignment_id}_{room}")
            choices[key] = (assignment, variable)
            identities = [
                ("teacher", assignment.teacher_id),
                ("room", room),
                *(("class", class_id) for class_id in assignment.class_ids),
            ]
            for kind, identity in identities:
                resource_choices[(kind, identity)].append(variable)
            if scores is None:
                terms.append((count_weight + len(options) - rank) * variable)
            else:
                necessary, value, priority = scores.get(
                    (assignment.assignment_id, room), (False, 0, 0)
                )
                terms.append(
                    (
                        int(necessary) * count_weight
                        + urgency_rank.get(priority, 0) * priority_weight * int(necessary)
                        + value
                    )
                    * variable
                )
            model.AddHint(variable, int((assignment.assignment_id, room) in preferred))
    for variables in resource_choices.values():
        model.AddAtMostOne(variables)
    model.Maximize(sum(terms))
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


def _interrupted(deadline: float | None, should_cancel: Callable[[], bool] | None) -> bool:
    return (should_cancel is not None and should_cancel()) or (
        deadline is not None and monotonic() >= deadline
    )


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
    candidate, refused = _construct_pass(
        snapshot,
        periods,
        deadline=deadline,
        should_cancel=should_cancel,
        weekly_reference=weekly_reference,
        weights=weights,
        strict=weights is None or bool(weights.teacher_preferences or weights.class_preferences),
    )
    if candidate is None and refused and not _interrupted(deadline, should_cancel):
        candidate, _refused = _construct_pass(
            snapshot,
            periods,
            deadline=deadline,
            should_cancel=should_cancel,
            weekly_reference=weekly_reference,
            weights=weights,
            strict=False,
        )
    if candidate is None and weights is not None and not _interrupted(deadline, should_cancel):
        candidate, _refused = _construct_pass(
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
) -> tuple[CandidateSchedule | None, int]:
    """One construction pass; returns the plan and the options the Evitar filter refused."""
    canonical = canonical_periods(periods)
    slots = sorted(
        snapshot.grid_slots, key=lambda slot: (slot.day_of_week, slot.start_local, slot.end_local)
    )
    preceding_ends = {
        (right.day_of_week, right.start_local, right.end_local): left.end_local.hour * 60
        + left.end_local.minute
        for left, right in zip(slots, slots[1:], strict=False)
        if left.day_of_week == right.day_of_week and left.end_local <= right.start_local
    }
    assignments = {row.assignment_id: row for row in snapshot.assignments}
    home_rooms = {row.class_id: row.room_id for row in snapshot.home_rooms}
    pace_peers = _pace_peers(assignments) if weights is not None else {}
    evitar_kinds = _evitar_kinds(weights)
    required = {
        identity: sum(module.required_minutes for module in row.modules)
        for identity, row in assignments.items()
    }
    remaining = {identity: residual_minutes(snapshot, identity) for identity in assignments}
    initial_remaining = dict(remaining)
    cursor = {
        identity: {
            module.module_id: snapshot.executed_minutes.get(identity, {}).get(module.module_id, 0)
            for module in row.modules
        }
        for identity, row in assignments.items()
    }
    busy: dict[tuple, list[Period]] = defaultdict(list)
    occupancy: dict[tuple, list[tuple[int, int]]] = defaultdict(list)
    weekly_pattern: dict[tuple, tuple[int, int]] = {}
    if weekly_reference is not None:
        for row in weekly_reference.lessons:
            assignment = assignments.get(row.assignment_id)
            if assignment is not None:
                for class_id in assignment.class_ids:
                    weekly_pattern.setdefault(
                        (
                            class_id,
                            row.period.school_date.weekday(),
                            row.period.start_local,
                            row.period.end_local,
                        ),
                        (row.assignment_id, row.room_id),
                    )
    used_ids = {row.lesson_id for row in snapshot.protected_lessons} | set(
        snapshot.reserved_lesson_ids
    )
    started_classes = {
        class_id
        for identity, row in assignments.items()
        if remaining[identity] < required[identity]
        for class_id in row.class_ids
    }

    def occupy(assignment: Assignment, period: Period, room: int, teacher: int) -> None:
        for class_id in assignment.class_ids:
            weekly_pattern.setdefault(
                (
                    class_id,
                    period.school_date.weekday(),
                    period.start_local,
                    period.end_local,
                ),
                (assignment.assignment_id, room),
            )
        for key in _resource_keys(assignment, room, teacher, period.school_date):
            busy[key].append(period)
            if key[0] != "room":
                occupancy[key].append(_local_interval(period))

    protected_intervals: dict[tuple, set[tuple[int, int]]] = defaultdict(set)
    for lesson in snapshot.protected_lessons:
        assignment = assignments[lesson.assignment_id]
        teacher = lesson.teacher_id or assignment.teacher_id
        occupy(assignment, lesson.period, lesson.room_id, teacher)
        protected_intervals[("teacher", teacher, lesson.period.school_date)].add(
            _local_interval(lesson.period)
        )
        for module_slice in lesson.slices:
            cursor[lesson.assignment_id][module_slice.module_id] += module_slice.credit_minutes

    predecessors: dict[int, list[int]] = defaultdict(list)
    for source, target in snapshot.precedences:
        predecessors[target].append(source)
    last_end: dict[int, datetime] = {}
    for lesson in snapshot.protected_lessons:
        current = last_end.get(lesson.assignment_id)
        if current is None or lesson.period.end_utc > current:
            last_end[lesson.assignment_id] = lesson.period.end_utc

    def ready(identity: int, period: Period) -> bool:
        """All predecessor units are finished before the period (WBS 3.3.2)."""
        return all(
            remaining[source] <= 0 and last_end.get(source, period.start_utc) <= period.start_utc
            for source in predecessors.get(identity, ())
        )

    options_by_period: dict[Period, list[Assignment]] = defaultdict(list)
    eligible_by_assignment: dict[int, tuple[Period, ...]] = {}
    room_pressure: dict[int, Fraction] = defaultdict(Fraction)
    class_remaining: dict[int, int] = defaultdict(int)
    teacher_remaining: dict[int, int] = defaultdict(int)
    for identity, assignment in assignments.items():
        if _interrupted(deadline, should_cancel):
            return None, 0
        if remaining[identity] <= 0:
            continue
        eligible = eligible_periods(snapshot, assignment, canonical)
        eligible_by_assignment[identity] = eligible
        for period in eligible:
            options_by_period[period].append(assignment)
        for class_id in assignment.class_ids:
            class_remaining[class_id] += remaining[identity]
        teacher_remaining[assignment.teacher_id] += remaining[identity]
        for room in assignment.eligible_room_ids:
            room_pressure[room] += Fraction(remaining[identity], len(assignment.eligible_room_ids))

    ledger = AvailabilityLedger.build(snapshot, eligible_by_assignment, remaining)
    ranks: dict[int, int] = defaultdict(int)
    lessons: list[ScheduledLesson] = []
    dispensed_teachers = snapshot.lunch_dispensed_teacher_ids
    presence_rules = _minimum_presence_teachers(snapshot)
    slots_by_day = _slots_by_day(snapshot)
    longest_presence = _longest_presences(snapshot, presence_rules, slots_by_day)
    grid_intervals = _grid_intervals_by_day(slots_by_day)
    periods_by_date: dict[date, list[Period]] = defaultdict(list)
    for day_period in canonical:
        periods_by_date[day_period.school_date].append(day_period)
    assignments_by_teacher: dict[int, list[Assignment]] = defaultdict(list)
    for row in snapshot.assignments:
        assignments_by_teacher[row.teacher_id].append(row)

    def place(assignment: Assignment, period: Period, room: int) -> bool:
        """Book one lesson and its module slices; False when no module credit is left."""
        identity = assignment.assignment_id
        credit = min(remaining[identity], period.duration_minutes)
        ranks[identity] += 1
        lesson_id = allocate_lesson_identity(identity, ranks[identity], used_ids)
        slices = []
        unallocated = credit
        while unallocated > 0:
            module_index = _next_module(assignment.modules, cursor[identity])
            if module_index is None:
                return False
            module = assignment.modules[module_index]
            offset = cursor[identity][module.module_id]
            take = min(unallocated, module.required_minutes - offset)
            slices.append(ModuleSlice(lesson_id, module.module_id, offset, take))
            cursor[identity][module.module_id] += take
            unallocated -= take
        lessons.append(ScheduledLesson(lesson_id, identity, period, room, credit, tuple(slices)))
        remaining[identity] -= credit
        ledger.place(assignment, credit)
        for class_id in assignment.class_ids:
            class_remaining[class_id] -= credit
            started_classes.add(class_id)
        teacher_remaining[assignment.teacher_id] -= credit
        current_end = last_end.get(identity)
        if current_end is None or period.end_utc > current_end:
            last_end[identity] = period.end_utc
        occupy(assignment, period, room, assignment.teacher_id)
        return True

    def presence_complies(teacher_id: int, school_date: date, booked: Sequence[Period]) -> bool:
        """True when the teacher's day, with the booked periods, meets the presence rule."""
        key = ("teacher", teacher_id, school_date)
        return _presence_day_complies(
            (*occupancy[key], *(_local_interval(period) for period in booked)),
            protected_intervals[key],
            presence_rules[teacher_id],
            snapshot.lunch_rule,
            grid_intervals.get(school_date.weekday(), ()),
        )

    def open_rooms(
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
            return [*busy[key], *pending.get(key, ())]

        keys = (
            ("teacher", assignment.teacher_id, school_date),
            *(("class", class_id, school_date) for class_id in assignment.class_ids),
        )
        if any(period.overlaps(occupied) for key in keys for occupied in booked(key)):
            return ()
        if snapshot.lunch_rule is not None and any(
            continuous_break_minutes(
                [*(_local_interval(occupied) for occupied in booked(key)), _local_interval(period)],
                snapshot.lunch_rule,
            )
            < snapshot.lunch_rule.minimum_minutes
            for key in keys
            if not (key[0] == "teacher" and key[1] in dispensed_teachers)
        ):
            return ()
        rooms = tuple(
            room
            for room in available_rooms(snapshot, assignment, period)
            if not any(
                period.overlaps(occupied) for occupied in booked(("room", room, school_date))
            )
        )
        preference_avoided = (
            weights is None
            or (
                weights.teacher_preferences > 0
                and any(
                    row.overlaps(period)
                    for row in snapshot.soft_unavailable_on(
                        UnavailableResource.TEACHER, assignment.teacher_id, period.school_date
                    )
                )
            )
            or (
                weights is not None
                and weights.class_preferences > 0
                and any(
                    row.overlaps(period)
                    for class_id in assignment.class_ids
                    for row in snapshot.soft_unavailable_on(
                        UnavailableResource.CLASS, class_id, period.school_date
                    )
                )
            )
        )
        if not rooms or (
            strict
            and preference_avoided
            and not ledger.allows(assignment, period, planned, evitar_kinds=evitar_kinds)
        ):
            return ()
        return rooms

    def plan_presence_run(
        assignment: Assignment, period: Period, room: int
    ) -> list[tuple[Assignment, Period, int]] | None:
        """Plan the later lessons that make the teacher's day meet the presence rule.

        Returns the lessons to book, starting with the given one, or None when the
        rest of the date cannot reach the rule. Booked lessons are not applied here.
        """
        teacher_id = assignment.teacher_id
        school_date = period.school_date
        booked: list[tuple[Assignment, Period, int]] = []
        pending: dict[tuple, list[Period]] = defaultdict(list)
        planned: list[tuple[Assignment, int]] = []
        credited: dict[int, int] = defaultdict(int)

        def add(row: tuple[Assignment, Period, int]) -> None:
            booked.append(row)
            row_assignment, row_period, row_room = row
            identity = row_assignment.assignment_id
            credit = min(remaining[identity] - credited[identity], row_period.duration_minutes)
            credited[identity] += credit
            planned.append((row_assignment, credit))
            for key in _resource_keys(row_assignment, row_room, teacher_id, row_period.school_date):
                pending[key].append(row_period)

        def run_complete() -> bool:
            left = teacher_remaining[teacher_id] - sum(credited.values())
            return presence_complies(
                teacher_id, school_date, [row_period for _a, row_period, _r in booked]
            ) and _presence_left_fits(
                left, presence_rules[teacher_id], longest_presence[teacher_id]
            )

        def next_lesson(later: Period) -> tuple[Assignment, int] | None:
            previous = booked[-1][0].assignment_id
            candidates = sorted(
                (
                    row
                    for row in assignments_by_teacher[teacher_id]
                    if remaining[row.assignment_id] - credited[row.assignment_id] > 0
                    and later in eligible_by_assignment.get(row.assignment_id, ())
                ),
                key=lambda row: (
                    row.assignment_id != previous,
                    -(remaining[row.assignment_id] - credited[row.assignment_id]),
                    row.assignment_id,
                ),
            )
            for row in candidates:
                if not ready(row.assignment_id, later):
                    continue
                rooms = open_rooms(row, later, pending, planned)
                if rooms:
                    return row, min(rooms, key=lambda value: (room_pressure[value], value))
            return None

        add((assignment, period, room))
        for later in periods_by_date[school_date]:
            if later.start_utc <= period.start_utc:
                continue
            choice = next_lesson(later)
            if choice is None:
                continue
            add((choice[0], later, choice[1]))
            if run_complete():
                return booked
        return None

    for period in canonical:
        if _interrupted(deadline, should_cancel):
            return None, ledger.refused
        active = [
            row
            for row in options_by_period[period]
            if remaining[row.assignment_id] > 0 and ready(row.assignment_id, period)
        ]
        if not active:
            continue
        preceding_end = preceding_ends.get(
            (period.school_date.weekday(), period.start_local, period.end_local)
        )
        signature = (period.school_date.weekday(), period.start_local, period.end_local)

        def weekly_preferred(assignment: Assignment, current_signature: tuple):
            for class_id in assignment.class_ids:
                preferred = weekly_pattern.get((class_id, *current_signature))
                if preferred is not None:
                    return preferred
            return None

        def priority(
            assignment: Assignment,
            current_period: Period = period,
            previous_end: int | None = preceding_end,
            current_signature: tuple = signature,
        ):
            identity = assignment.assignment_id
            preferred = weekly_preferred(assignment, current_signature)
            repeats = preferred is not None and preferred[0] == identity
            continues = _continues_open_presence(
                slots_by_day, occupancy, assignment.teacher_id, current_period, presence_rules
            )
            adjacent = sum(
                any(
                    end == previous_end
                    for _start, end in occupancy[(kind, resource, current_period.school_date)]
                )
                for kind, resource in (
                    *(("class", class_id) for class_id in assignment.class_ids),
                    ("teacher", assignment.teacher_id),
                )
            )
            return (
                ledger.priority(assignment, current_period),
                ledger.unfavorable(assignment, current_period, evitar_kinds=evitar_kinds),
                any(class_id in started_classes for class_id in assignment.class_ids),
                initial_remaining[identity] != remaining[identity],
                Fraction(
                    required[identity]
                    - remaining[identity]
                    - (min(remaining[identity], current_period.duration_minutes) if repeats else 0),
                    required[identity],
                ),
                not continues,
                -adjacent,
                preferred is None,
                not repeats,
                -teacher_remaining[assignment.teacher_id],
                -sum(class_remaining[class_id] for class_id in assignment.class_ids),
                len(assignment.eligible_room_ids),
                identity,
            )

        options = []
        scores: dict[tuple[int, int], tuple[bool, int, int]] | None = (
            {} if weights is not None else None
        )
        for assignment in sorted(active, key=priority):
            identity = assignment.assignment_id
            preferred = weekly_preferred(assignment, signature)
            preferred_room = (
                preferred[1] if preferred is not None and preferred[0] == identity else None
            )
            rooms = tuple(
                sorted(
                    open_rooms(assignment, period, {}),
                    key=lambda room: (room != preferred_room, room_pressure[room], room),
                )
            )
            if rooms:
                if weights is None:
                    options.append((assignment, rooms))
                    continue
                necessary = ledger.is_necessary(assignment, period, evitar_kinds=evitar_kinds)
                allowed_rooms = []
                credit = min(remaining[identity], period.duration_minutes)
                measures = _option_measures(
                    snapshot,
                    assignment,
                    period,
                    credit=credit,
                    needed_evitar=ledger.needed_evitar(
                        assignment, period, evitar_kinds=evitar_kinds
                    ),
                    occupancy=occupancy,
                    day_slots=slots_by_day.get(period.school_date.weekday(), ()),
                    counts_teacher_single_lessons=assignment.teacher_id not in presence_rules,
                    weekly_assignment_id=None if preferred is None else preferred[0],
                    pace_lag=_pace_lag(identity, pace_peers[identity], required, remaining),
                )
                for room in rooms:
                    value = _room_value(
                        weights, measures, assignment, room, home_rooms, credit=credit
                    )
                    if necessary or _fills_hour(weights, measures, value, strict=strict, fill=fill):
                        allowed_rooms.append(room)
                        scores[(identity, room)] = (
                            necessary,
                            value,
                            ledger.urgency(assignment, period),
                        )
                if allowed_rooms:
                    options.append((assignment, tuple(allowed_rooms)))
        if scores is not None:
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
        for assignment, room in _select_period(options, deadline=deadline, scores=scores):
            teacher_id = assignment.teacher_id
            if teacher_id in presence_rules and not presence_complies(
                teacher_id, period.school_date, [period]
            ):
                # A lesson that leaves the day short of the presence minimum is
                # placed only with the later run that completes it.
                run = plan_presence_run(assignment, period, room)
                if run is None:
                    continue
            else:
                # Extending a compliant presence must not strand minutes that no
                # split into valid presences could ever teach.
                credit = min(remaining[assignment.assignment_id], period.duration_minutes)
                left = teacher_remaining[teacher_id] - credit
                if teacher_id in presence_rules and not _presence_left_fits(
                    left, presence_rules[teacher_id], longest_presence[teacher_id]
                ):
                    continue
                run = [(assignment, period, room)]
            for run_assignment, run_period, run_room in run:
                if not place(run_assignment, run_period, run_room):
                    return None, ledger.refused
        if not any(remaining.values()):
            break
    if any(remaining.values()):
        return None, ledger.refused
    candidate = CandidateSchedule((*snapshot.protected_lessons, *lessons))
    valid = validate_candidate(snapshot, candidate).valid
    return (candidate if valid else None), ledger.refused
