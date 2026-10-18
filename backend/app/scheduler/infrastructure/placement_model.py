"""CP-SAT detailed placement, room matching and initial-quality stages.

The horizon is solved one school week at a time (a single scope when no quota
distribution is supplied). Windows are independent once the distribution fixes
the per-week counts, so a window can be reopened or reused without refreezing
the whole year.

Quality is optimized in lexicographic stages. The completion vector is
minimized through its threshold counts, from the latest day to the earliest,
for every class in scope; the resulting counts are frozen before any subordinate
objective runs, so a gap, preference or room improvement can never degrade a
completion day. A stage value is fixed heuristically when the solver does not
prove it, and the evidence marks the contiguous certified prefix.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from time import monotonic
from typing import Any

from ortools.sat.python import cp_model

from app.scheduler.domain.calendar import Period
from app.scheduler.domain.candidate import (
    Assignment,
    CandidateSchedule,
    GridSlot,
    PlanningSnapshot,
    ScheduledLesson,
    UnavailableResource,
    allocate_lesson_identity,
)
from app.scheduler.domain.candidate_validation import validate_candidate
from app.scheduler.domain.capacity import (
    available_rooms,
    canonical_periods,
    eligible_periods,
    residual_minutes,
)
from app.scheduler.domain.projection import FutureLesson, project_module_slices
from app.scheduler.domain.quality import (
    SearchEvidence,
    StageEvidence,
    measure_initial_quality,
)
from app.scheduler.domain.teacher_presence import lunch_options
from app.scheduler.infrastructure import diagnostics
from app.scheduler.infrastructure.annual_model import (
    QuotaDistribution,
    week_index,
)
from app.scheduler.infrastructure.solver_cancellation import solve_with_cancellation

STATUS_COMPLETE = "COMPLETE"
STATUS_INFEASIBLE = "INFEASIBLE"
STATUS_INCONCLUSIVE = "INCONCLUSIVE"
STATUS_FAILED = "FAILED"
STATUS_CANCELLED = "CANCELLED"

STAGE_THRESHOLD = "COMPLETION_THRESHOLD"
STAGE_ROOM_DISRUPTION = "RECOVERY_ROOM_DISRUPTION"
STAGE_TEACHER_GAPS = "TEACHER_GAP_MINUTES"
STAGE_CLASS_GAPS = "CLASS_GAP_MINUTES"
STAGE_PREFERENCES = "PREFERENCE_COST_MINUTES"
STAGE_ROOM_CHANGES = "ROOM_CHANGE_COST"

OBJECTIVE_SCOPE_CONDITIONAL = "CONDITIONAL_ON_QUOTA_DISTRIBUTION"
OBJECTIVE_SCOPE_UNRESTRICTED = "UNRESTRICTED_EXACT_MODEL"
PROVEN_SCOPE = OBJECTIVE_SCOPE_UNRESTRICTED

STOP_OPTIMAL = "OPTIMAL_CONDITIONAL"
STOP_FEASIBLE = "FEASIBLE"
STOP_SAFETY = "SAFETY_LIMIT"

MIN_STAGE_SECONDS = 0.05
# ponytail: calibrated on production 2026-10-17, whose logs count all model
# variables: 0.63 M peaked near 3.2 GB and 3.96 M were OOM-killed at 8 GB. The cap
# compares only the option variables of _estimated_variables, the bulk of a model,
# so it stays below the killed size. Upgrade path: measure peak memory per
# variable on the worker and derive this cap from the container memory limit.
MAX_PLACEMENT_VARIABLES = 1_000_000

_COMPONENT_ORDER = {
    STAGE_THRESHOLD: 0,
    STAGE_ROOM_DISRUPTION: 1,
    STAGE_TEACHER_GAPS: 2,
    STAGE_CLASS_GAPS: 3,
    STAGE_PREFERENCES: 4,
    STAGE_ROOM_CHANGES: 5,
}


class NoEligiblePeriodsError(RuntimeError):
    """An assignment with residual demand has no eligible placement fact."""


@dataclass(frozen=True)
class PlacementOutcome:
    status: str
    candidate: CandidateSchedule | None
    objective_days: int | None
    wall_time_seconds: float
    proven_scope: str
    statistics: Mapping[str, int]
    evidence: SearchEvidence | None = None
    message: str = ""


@dataclass(frozen=True)
class _AssignmentScope:
    assignment: Assignment
    periods: tuple[Period, ...]
    groups: tuple[tuple[int, int], ...] | None
    credit_target: int
    waste_target: int | None
    final_periods: tuple[Period, ...]
    last_window: bool


@dataclass(frozen=True)
class _WindowScope:
    week: int | None
    periods: tuple[Period, ...]
    assignments: Mapping[int, _AssignmentScope]
    completing_classes: tuple[int, ...]
    protected_days: Mapping[int, int]


@dataclass
class _ScopeState:
    model: cp_model.CpModel
    snapshot: PlanningSnapshot
    scope: _WindowScope
    x: dict[tuple[int, Period], Any] = field(default_factory=dict)
    last: dict[tuple[int, Period], Any] = field(default_factory=dict)
    waste: dict[tuple[int, Period], Any] = field(default_factory=dict)
    room_choice: dict[tuple[int, Period, int], Any] = field(default_factory=dict)
    rooms_of: dict[tuple[int, Period], tuple[int, ...]] = field(default_factory=dict)
    assignment_by_id: dict[int, Assignment] = field(default_factory=dict)
    slots_by_day: dict[int, tuple[GridSlot, ...]] = field(default_factory=dict)
    position_of: dict[Period, int] = field(default_factory=dict)
    days: dict[int, Any] = field(default_factory=dict)
    threshold_counts: dict[int, Any] = field(default_factory=dict)
    room_pairs: dict[tuple[int, int], dict[int, list[Any]]] = field(default_factory=dict)


@dataclass(frozen=True)
class _StageRecord:
    stage: str
    value: int
    proven: bool
    window: int | None
    threshold: int | None = None
    reused: bool = False


@dataclass(frozen=True)
class _CachedWindow:
    selections: Mapping[int, tuple]
    records: tuple[_StageRecord, ...]
    room_continuity: bool = False


def _scope_cache_key(scope: _WindowScope, salt: str = "") -> tuple:
    """Identity of one window subproblem, including everything that conditions it.

    The salt binds the cache to the published baseline, protected facts and
    editable frontier, so a proven window is never reused under changed inputs.
    """
    assignments = tuple(
        (
            assignment_id,
            tuple((period.start_utc, period.end_utc) for period in row.periods),
            row.groups,
            row.credit_target,
            row.waste_target,
            tuple((period.start_utc, period.end_utc) for period in row.final_periods),
            row.last_window,
        )
        for assignment_id, row in sorted(scope.assignments.items())
    )
    return (
        salt,
        scope.week,
        assignments,
        tuple(scope.completing_classes),
        tuple(sorted(scope.protected_days.items())),
    )


def _lunch_cache_salt(snapshot: PlanningSnapshot, salt: str) -> str:
    """Bind cached windows to the lunch rule and every presence rule.

    Both constrain the same windows, so a changed rule must change the key.
    """
    result = salt
    lunch = snapshot.lunch_rule
    if lunch is not None:
        result = (
            f"{result}|lunch:{lunch.window_start_minutes}-{lunch.window_end_minutes}"
            f":{lunch.minimum_minutes}"
        )
    if snapshot.teacher_presence:
        rules = ",".join(
            f"{row.teacher_id}:{int(row.lunch_required)}:{row.minimum_minutes}:{row.max_gap_minutes}"
            for row in snapshot.teacher_presence
        )
        result = f"{result}|presence:{rules}"
    return result


def _module_completed(snapshot: PlanningSnapshot, assignment_id: int) -> dict[int, int]:
    completed: dict[int, int] = defaultdict(int)
    for module_id, minutes in snapshot.executed_for(assignment_id).items():
        completed[module_id] += minutes
    for lesson in snapshot.protected_lessons:
        if lesson.assignment_id != assignment_id:
            continue
        for slice_ in lesson.slices:
            completed[slice_.module_id] += slice_.credit_minutes
    return completed


def _baseline_sources(snapshot: PlanningSnapshot) -> dict[tuple, int]:
    """Published lesson identity per assignment and physical interval."""
    protected_ids = {lesson.lesson_id for lesson in snapshot.protected_lessons}
    sources: dict[tuple, int] = {}
    for lesson in snapshot.baseline_lessons:
        if lesson.lesson_id in protected_ids:
            continue
        key = (lesson.assignment_id, lesson.period.start_utc, lesson.period.end_utc)
        sources.setdefault(key, lesson.lesson_id)
    return sources


def _build_candidate(
    snapshot: PlanningSnapshot,
    selections: Mapping[int, list[tuple[Period, int, int]]],
) -> CandidateSchedule:
    lessons: list[ScheduledLesson] = []
    used = {lesson.lesson_id for lesson in snapshot.protected_lessons} | set(
        snapshot.reserved_lesson_ids
    )
    sources = _baseline_sources(snapshot)
    for assignment in snapshot.assignments:
        rows = sorted(
            selections.get(assignment.assignment_id, ()),
            key=lambda row: (row[0].school_date, row[0].start_local),
        )
        if not rows:
            continue
        identities = [
            allocate_lesson_identity(assignment.assignment_id, rank, used)
            for rank in range(1, len(rows) + 1)
        ]
        futures = tuple(
            FutureLesson(
                identity,
                period.school_date,
                period.start_local.hour * 60 + period.start_local.minute,
                period.duration_minutes,
                credit,
            )
            for identity, (period, _room, credit) in zip(identities, rows, strict=True)
        )
        slices = project_module_slices(
            assignment.modules,
            completed_minutes=_module_completed(snapshot, assignment.assignment_id),
            lessons=futures,
        )
        by_lesson: dict[int, list] = defaultdict(list)
        for slice_ in slices:
            by_lesson[slice_.lesson_id].append(slice_)
        for identity, ((period, room_id, credit), future) in zip(
            identities, zip(rows, futures, strict=True), strict=True
        ):
            source = sources.get((assignment.assignment_id, period.start_utc, period.end_utc))
            lessons.append(
                ScheduledLesson(
                    lesson_id=identity,
                    assignment_id=assignment.assignment_id,
                    period=period,
                    room_id=room_id,
                    credit_minutes=credit,
                    slices=tuple(by_lesson.get(future.lesson_id, ())),
                    source_lesson_id=source,
                )
            )
    combined = (*snapshot.protected_lessons, *lessons)
    combined = _pair_published_identities(snapshot, combined)
    return CandidateSchedule(
        tuple(
            sorted(
                combined,
                key=lambda lesson: (
                    lesson.period.school_date,
                    lesson.period.start_local,
                    lesson.lesson_id,
                ),
            )
        )
    )


def _lesson_order(lesson: ScheduledLesson) -> tuple:
    return (lesson.period.school_date, lesson.period.start_utc, lesson.lesson_id)


def _pair_published_identities(
    snapshot: PlanningSnapshot, lessons: tuple[ScheduledLesson, ...]
) -> tuple[ScheduledLesson, ...]:
    """Attach the published identity of a moved lesson without a source.

    Exact positions already carry their source. The remaining generated lessons
    are paired, per assignment and in chronological order, with the remaining
    published lessons, so a displacement keeps its identity and is priced as a
    movement instead of a removal plus an insertion.
    """
    protected_ids = {lesson.lesson_id for lesson in snapshot.protected_lessons}
    generated = [lesson for lesson in lessons if lesson.lesson_id not in protected_ids]
    used_sources = {
        lesson.source_lesson_id for lesson in generated if lesson.source_lesson_id is not None
    }
    base_by_assignment: dict[int, list[ScheduledLesson]] = defaultdict(list)
    for lesson in snapshot.baseline_lessons:
        if lesson.lesson_id in protected_ids or lesson.lesson_id in used_sources:
            continue
        base_by_assignment[lesson.assignment_id].append(lesson)
    new_by_assignment: dict[int, list[ScheduledLesson]] = defaultdict(list)
    for lesson in generated:
        if lesson.source_lesson_id is None:
            new_by_assignment[lesson.assignment_id].append(lesson)
    paired: dict[int, int] = {}
    for assignment_id, new_rows in sorted(new_by_assignment.items()):
        base_rows = sorted(base_by_assignment.get(assignment_id, ()), key=_lesson_order)
        for lesson, source in zip(sorted(new_rows, key=_lesson_order), base_rows, strict=False):
            paired[lesson.lesson_id] = source.lesson_id
    if not paired:
        return lessons
    return tuple(
        replace(lesson, source_lesson_id=paired.get(lesson.lesson_id, lesson.source_lesson_id))
        for lesson in lessons
    )


def _soft_overlaps(
    snapshot: PlanningSnapshot,
    resource_type: UnavailableResource,
    resource_id: int,
    period: Period,
) -> bool:
    return any(
        row.overlaps(period)
        for row in snapshot.soft_unavailable_on(resource_type, resource_id, period.school_date)
    )


def _slot_position(slots_by_day: Mapping[int, tuple[GridSlot, ...]], period: Period) -> int | None:
    for position, slot in enumerate(slots_by_day.get(period.school_date.weekday(), ())):
        if slot.matches(period):
            return position
    return None


def _slot_duration_minutes(slot: GridSlot) -> int:
    start = slot.start_local.hour * 60 + slot.start_local.minute
    end = slot.end_local.hour * 60 + slot.end_local.minute
    return end - start


def _slot_start_minutes(slot: GridSlot) -> int:
    return slot.start_local.hour * 60 + slot.start_local.minute


def _slot_end_minutes(slot: GridSlot) -> int:
    return slot.end_local.hour * 60 + slot.end_local.minute


def _or_expressions(model: cp_model.CpModel, name: str, values: list[Any]) -> Any:
    if not values:
        return 0
    if any(type(value) is int for value in values):
        if any(type(value) is int and value == 1 for value in values):
            return 1
        values = [value for value in values if type(value) is not int]
        if not values:
            return 0
    if len(values) == 1:
        return values[0]
    result = model.NewBoolVar(name)
    model.AddMaxEquality(result, values)
    return result


def _sorted_slots(snapshot: PlanningSnapshot) -> dict[int, tuple[GridSlot, ...]]:
    by_day: dict[int, list[GridSlot]] = defaultdict(list)
    for slot in snapshot.grid_slots:
        by_day[slot.day_of_week].append(slot)
    return {
        day: tuple(sorted(rows, key=lambda slot: (slot.start_local, slot.end_local)))
        for day, rows in by_day.items()
    }


def _assignment_scopes(
    snapshot: PlanningSnapshot,
    periods: tuple[Period, ...],
    distribution: QuotaDistribution,
) -> tuple[dict[int, dict[int, _AssignmentScope]], dict[int, int], dict[int, int]]:
    canonical = canonical_periods(periods)
    weeks: dict[int, dict[int, _AssignmentScope]] = defaultdict(dict)
    protected_days: dict[int, int] = defaultdict(int)
    for lesson in snapshot.protected_lessons:
        assignment = snapshot.assignment_for(lesson.assignment_id)
        if assignment is None:
            continue
        day = (lesson.period.school_date - snapshot.origin).days
        for class_id in assignment.class_ids:
            protected_days[class_id] = max(protected_days[class_id], day)
    completion_week: dict[int, int] = {}
    for assignment in snapshot.assignments:
        remaining = residual_minutes(snapshot, assignment.assignment_id)
        if remaining <= 0:
            continue
        final_group = distribution.final_groups.get(assignment.assignment_id)
        if final_group is None:
            raise ValueError("Every active assignment needs a final group.")
        grouped: dict[int, dict[int, int]] = defaultdict(dict)
        for (owner, week, duration), count in distribution.counts.items():
            if owner == assignment.assignment_id:
                grouped[week][duration] = count
        if final_group[0] not in grouped:
            raise ValueError("The final group needs a positive quota.")
        if any(week > final_group[0] for week in grouped):
            raise ValueError("No quota may follow the final week.")
        physical = sum(
            duration * count
            for durations in grouped.values()
            for duration, count in durations.items()
        )
        waste = physical - remaining
        if waste < 0:
            raise ValueError("The distribution does not cover the residual demand.")
        eligible = eligible_periods(snapshot, assignment, canonical)
        if not eligible:
            raise NoEligiblePeriodsError(
                f"Assignment {assignment.assignment_id} has no eligible period."
            )
        for class_id in assignment.class_ids:
            completion_week[class_id] = max(
                completion_week.get(class_id, 0),
                final_group[0],
                protected_days.get(class_id, 0) // 7,
            )
        for week, durations in sorted(grouped.items()):
            week_periods = tuple(
                period
                for period in eligible
                if week_index(snapshot.origin, period) == week
                and period.duration_minutes in durations
            )
            if not week_periods:
                raise ValueError("The distribution needs eligible periods in the window.")
            last_window = week == final_group[0]
            credit = sum(duration * count for duration, count in durations.items())
            if last_window:
                credit -= waste
            weeks[week][assignment.assignment_id] = _AssignmentScope(
                assignment=assignment,
                periods=week_periods,
                groups=tuple(sorted(durations.items())),
                credit_target=credit,
                waste_target=waste if last_window else None,
                final_periods=(
                    tuple(
                        period
                        for period in week_periods
                        if period.duration_minutes == final_group[1]
                    )
                    if last_window
                    else ()
                ),
                last_window=last_window,
            )
    return weeks, completion_week, protected_days


def _window_scopes(
    snapshot: PlanningSnapshot, periods: tuple[Period, ...], distribution: QuotaDistribution
) -> tuple[_WindowScope, ...]:
    weeks, completion_week, protected_days = _assignment_scopes(snapshot, periods, distribution)
    canonical = canonical_periods(periods)
    return tuple(
        _WindowScope(
            week=week,
            periods=tuple(
                period for period in canonical if week_index(snapshot.origin, period) == week
            ),
            assignments=assignments,
            completing_classes=tuple(
                sorted(class_id for class_id, target in completion_week.items() if target == week)
            ),
            protected_days={
                class_id: protected_days.get(class_id, 0)
                for class_id, target in completion_week.items()
                if target == week
            },
        )
        for week, assignments in sorted(weeks.items())
    )


def _unrestricted_scope(snapshot: PlanningSnapshot, periods: tuple[Period, ...]) -> _WindowScope:
    canonical = canonical_periods(periods)
    assignments: dict[int, _AssignmentScope] = {}
    protected_days: dict[int, int] = defaultdict(int)
    for lesson in snapshot.protected_lessons:
        assignment = snapshot.assignment_for(lesson.assignment_id)
        if assignment is None:
            continue
        day = (lesson.period.school_date - snapshot.origin).days
        for class_id in assignment.class_ids:
            protected_days[class_id] = max(protected_days[class_id], day)
    for assignment in snapshot.assignments:
        remaining = residual_minutes(snapshot, assignment.assignment_id)
        if remaining <= 0:
            continue
        eligible = eligible_periods(snapshot, assignment, canonical)
        if not eligible:
            raise NoEligiblePeriodsError(
                f"Assignment {assignment.assignment_id} has no eligible period."
            )
        assignments[assignment.assignment_id] = _AssignmentScope(
            assignment=assignment,
            periods=eligible,
            groups=None,
            credit_target=remaining,
            waste_target=None,
            final_periods=eligible,
            last_window=True,
        )
    completing = tuple(
        sorted({class_id for row in snapshot.assignments for class_id in row.class_ids})
    )
    return _WindowScope(
        week=None,
        periods=canonical,
        assignments=assignments,
        completing_classes=completing,
        protected_days={class_id: protected_days.get(class_id, 0) for class_id in completing},
    )


def _add_assignment_options(state, assignment_id, row):
    model = state.model
    snapshot = state.snapshot
    assignment = state.assignment_by_id[assignment_id]
    for period in row.periods:
        key = (assignment_id, period)
        state.x[key] = model.NewBoolVar(f"x_{assignment_id}_{period.start_utc.isoformat()}")
        rooms = available_rooms(snapshot, assignment, period)
        if not rooms:
            raise NoEligiblePeriodsError(f"Assignment {assignment_id} lost its eligible rooms.")
        state.rooms_of[key] = rooms
        room_variables = {}
        for room_id in rooms:
            variable = model.NewBoolVar(
                f"r_{assignment_id}_{period.start_utc.isoformat()}_{room_id}"
            )
            state.room_choice[(assignment_id, period, room_id)] = variable
            room_variables[room_id] = variable
            for class_id in assignment.class_ids:
                pair = (class_id, assignment.subject_id)
                state.room_pairs.setdefault(pair, {}).setdefault(room_id, []).append(variable)
        model.Add(sum(room_variables.values()) == state.x[key])
        if row.last_window:
            state.last[key] = model.NewBoolVar(f"l_{assignment_id}_{period.start_utc.isoformat()}")
            state.waste[key] = model.NewIntVar(
                0,
                period.duration_minutes - 1,
                f"u_{assignment_id}_{period.start_utc.isoformat()}",
            )
            model.Add(state.waste[key] <= (period.duration_minutes - 1) * state.last[key])
            model.Add(state.last[key] <= state.x[key])
        position = _slot_position(state.slots_by_day, period)
        if position is not None:
            state.position_of[period] = position


def _add_assignment_credit(state, assignment_id, row):
    model = state.model
    keys = [(assignment_id, period) for period in row.periods]
    if row.groups is not None:
        model.Add(sum(state.x[key] for key in keys) == sum(count for _, count in row.groups))
        for duration, count in row.groups:
            group_keys = [key for key in keys if key[1].duration_minutes == duration]
            if len(group_keys) < count:
                raise ValueError("A quota distribution does not fit the snapshot.")
            model.Add(sum(state.x[key] for key in group_keys) == count)
    if row.last_window:
        model.Add(sum(state.last[key] for key in keys) == 1)
        if row.final_periods:
            final_keys = [key for key in keys if key[1] in row.final_periods]
            model.Add(sum(state.last[key] for key in final_keys) == 1)
        last_position = model.NewIntVar(0, len(keys) - 1, f"lp_{assignment_id}")
        model.Add(last_position == sum(index * state.last[key] for index, key in enumerate(keys)))
        for index, key in enumerate(keys):
            model.Add(last_position >= index).OnlyEnforceIf(state.x[key])
        if row.waste_target is not None:
            model.Add(sum(state.waste[key] for key in keys) == row.waste_target)
        model.Add(
            sum(key[1].duration_minutes * state.x[key] - state.waste[key] for key in keys)
            == row.credit_target
        )
    else:
        model.Add(sum(key[1].duration_minutes * state.x[key] for key in keys) == row.credit_target)


def _estimated_variables(scope: _WindowScope) -> int:
    """Upper bound on the option variables, computed from the scope without a build.

    Mirrors _add_assignment_options: one assignment bit per period, one room bit
    per eligible room, and the last and waste variables in the last window.
    """
    return sum(
        len(row.periods)
        * (1 + len(row.assignment.eligible_room_ids) + (2 if row.last_window else 0))
        for row in scope.assignments.values()
    )


def _build_scope_state(snapshot: PlanningSnapshot, scope: _WindowScope) -> _ScopeState:
    state = _ScopeState(model=cp_model.CpModel(), snapshot=snapshot, scope=scope)
    state.assignment_by_id = {row.assignment_id: row for row in snapshot.assignments}
    state.slots_by_day = _sorted_slots(snapshot)
    for assignment_id, row in sorted(scope.assignments.items()):
        _add_assignment_options(state, assignment_id, row)
        _add_assignment_credit(state, assignment_id, row)
    _add_conflicts(state)
    lunch_options_by_resource = _add_lunch(state)
    _add_teacher_presence(state, lunch_options_by_resource)
    _add_completion_measure(state)
    _add_precedence_constraints(state)
    return state


def _absolute_minutes(snapshot: PlanningSnapshot, period: Period) -> tuple[int, int]:
    """Local (start, end) minutes counted from the snapshot origin's school date."""
    day = (period.school_date - snapshot.origin).days
    base = day * 24 * 60
    start = base + period.start_local.hour * 60 + period.start_local.minute
    end = base + period.end_local.hour * 60 + period.end_local.minute
    return start, end


def _add_precedence_constraints(state: _ScopeState) -> None:
    """Stagger a successor after its predecessor inside one window (WBS 3.6.2).

    ``last_end[u]`` is the end of the latest selected (or protected) lesson of
    the predecessor; ``first_start[v]`` is the start of the earliest selected
    lesson of the successor. The relation is linear in the number of periods.
    Protected target lessons are facts and stay outside the constraint.
    """
    snapshot = state.snapshot
    if not snapshot.precedences:
        return
    model = state.model
    scope_assignments = state.scope.assignments
    horizon = 0
    for row in scope_assignments.values():
        for period in row.periods:
            horizon = max(horizon, _absolute_minutes(snapshot, period)[1])
    for lesson in snapshot.protected_lessons:
        horizon = max(horizon, _absolute_minutes(snapshot, lesson.period)[1])
    if horizon <= 0:
        return
    for source, target in snapshot.precedences:
        if source not in scope_assignments or target not in scope_assignments:
            continue
        source_periods = scope_assignments[source].periods
        target_periods = scope_assignments[target].periods
        if not source_periods or not target_periods:
            continue
        last_end = model.NewIntVar(0, horizon, f"last_end_{source}_{target}")
        for period in source_periods:
            end = _absolute_minutes(snapshot, period)[1]
            model.Add(last_end >= end).OnlyEnforceIf(state.x[(source, period)])
        for lesson in snapshot.protected_lessons:
            if lesson.assignment_id != source:
                continue
            if (
                state.scope.week is not None
                and week_index(snapshot.origin, lesson.period) != state.scope.week
            ):
                continue
            model.Add(last_end >= _absolute_minutes(snapshot, lesson.period)[1])
        first_start = model.NewIntVar(0, horizon, f"first_start_{source}_{target}")
        for period in target_periods:
            start = _absolute_minutes(snapshot, period)[0]
            model.Add(first_start <= start + horizon * (1 - state.x[(target, period)]))
        model.Add(last_end <= first_start)


def _add_resource_exclusivity(model: cp_model.CpModel, rows: Sequence[tuple[Period, Any]]) -> None:
    """At most one option per resource and period, without one restriction per pair.

    Options with the same exact interval form one group. Partially overlapping
    groups share one restriction over the union of their literals. Groups that
    overlap only through transitivity are never merged, so the ends of an
    overlap chain stay available. Repeated constants stay conflicting.
    """
    groups: dict[tuple, list[Any]] = defaultdict(list)
    for period, literal in rows:
        groups[(period.start_utc, period.end_utc)].append(literal)
    ordered = sorted(groups.items())
    for _interval, literals in ordered:
        if len(literals) >= 2:
            model.AddAtMostOne(literals)
    for index in range(len(ordered)):
        _start, end = ordered[index][0]
        literals = ordered[index][1]
        other = index + 1
        while other < len(ordered) and ordered[other][0][0] < end:
            model.AddAtMostOne([*literals, *ordered[other][1]])
            other += 1


def _add_conflicts(state: _ScopeState) -> None:
    model = state.model
    by_class: dict[int, list[tuple[Period, Any]]] = defaultdict(list)
    by_teacher: dict[int, list[tuple[Period, Any]]] = defaultdict(list)
    by_room: dict[int, list[tuple[Period, Any]]] = defaultdict(list)
    for assignment_id, row in state.scope.assignments.items():
        assignment = state.assignment_by_id[assignment_id]
        for period in row.periods:
            variable = state.x[(assignment_id, period)]
            for class_id in assignment.class_ids:
                by_class[class_id].append((period, variable))
            by_teacher[assignment.teacher_id].append((period, variable))
            for room_id in state.rooms_of[(assignment_id, period)]:
                by_room[room_id].append(
                    (period, state.room_choice[(assignment_id, period, room_id)])
                )
    for rows in by_class.values():
        _add_resource_exclusivity(model, rows)
    for rows in by_teacher.values():
        _add_resource_exclusivity(model, rows)
    for _room_id, rows in sorted(by_room.items()):
        _add_resource_exclusivity(model, rows)


def _period_minutes(period: Period) -> tuple[int, int]:
    return (
        period.start_local.hour * 60 + period.start_local.minute,
        period.end_local.hour * 60 + period.end_local.minute,
    )


def _lunch_resource_rows(state):
    by_resource: dict[tuple[str, int, date], list[tuple[Period, Any]]] = defaultdict(list)
    for (assignment_id, period), variable in state.x.items():
        assignment = state.assignment_by_id[assignment_id]
        for class_id in assignment.class_ids:
            by_resource[("class", class_id, period.school_date)].append((period, variable))
        by_resource[("teacher", assignment.teacher_id, period.school_date)].append(
            (period, variable)
        )
    for lesson in state.snapshot.protected_lessons:
        assignment = state.assignment_by_id.get(lesson.assignment_id)
        if assignment is None:
            continue
        if (
            state.scope.week is not None
            and week_index(state.snapshot.origin, lesson.period) != state.scope.week
        ):
            continue
        teacher_id = lesson.teacher_id if lesson.teacher_id is not None else assignment.teacher_id
        for class_id in assignment.class_ids:
            by_resource[("class", class_id, lesson.period.school_date)].append((lesson.period, 1))
        by_resource[("teacher", teacher_id, lesson.period.school_date)].append((lesson.period, 1))
    return by_resource


def _lunch_overlap_terms(rows, option_start, option_end):
    terms = []
    blocked = False
    for period, variable in rows:
        period_start, period_end = _period_minutes(period)
        if period_start < option_end and option_start < period_end:
            if type(variable) is int:
                blocked = True
                break
            terms.append(variable)
    return terms, blocked


def _add_resource_lunch(state, resource, rows) -> list[tuple[Any, int, int]]:
    """Add one free-option per resource and return ``(flag, start, end)`` options.

    The presence minimum reuses these options to designate one free lunch choice
    that splits the day; a resource with no free option is infeasible.
    """
    model = state.model
    rule = state.snapshot.lunch_rule
    window_start = rule.window_start_minutes
    window_end = rule.window_end_minutes
    kind, resource_id, school_date = resource
    boundaries = {window_start, window_end}
    for period, _variable in rows:
        period_start, period_end = _period_minutes(period)
        if window_start < period_start < window_end:
            boundaries.add(period_start)
        if window_start < period_end < window_end:
            boundaries.add(period_end)
    options: list[tuple[Any, int, int]] = []
    for option_start, option_end in lunch_options(
        sorted(boundaries), window_end, rule.minimum_minutes
    ):
        terms, blocked = _lunch_overlap_terms(rows, option_start, option_end)
        if blocked:
            continue
        flag = model.NewBoolVar(
            f"lunch_{kind}_{resource_id}_{school_date.isoformat()}_{option_start}"
        )
        for term in terms:
            model.Add(flag + term <= 1)
        options.append((flag, option_start, option_end))
    if options:
        model.Add(sum(flag for flag, _start, _end in options) >= 1)
    else:
        model.AddBoolOr([])
    return options


def _add_lunch(state: _ScopeState) -> dict[tuple[str, int, date], list[tuple[Any, int, int]]]:
    """Require one continuous lunch window per class and teacher on active days.

    Each option is a boolean "this interval is free". It is forced off whenever
    a lesson overlapping it is placed, so at least one option must remain free.
    Protected lessons can block an option permanently; a resource with no free
    option makes the window infeasible instead of silently ignoring the rule.
    A teacher dispensed from lunch is skipped; classes always keep the rule.
    """
    rule = state.snapshot.lunch_rule
    if rule is None:
        return {}
    dispensed = state.snapshot.lunch_dispensed_teacher_ids
    by_resource = _lunch_resource_rows(state)
    lunch_options_by_resource: dict[tuple[str, int, date], list[tuple[Any, int, int]]] = {}
    for (kind, resource_id, school_date), rows in sorted(by_resource.items()):
        if kind == "teacher" and resource_id in dispensed:
            continue
        lunch_options_by_resource[(kind, resource_id, school_date)] = _add_resource_lunch(
            state, (kind, resource_id, school_date), rows
        )
    return lunch_options_by_resource


def _teacher_presence_occupancy(state: _ScopeState):
    """Split a teacher's day into editable variables and protected positions.

    Protected lessons stay constants, so a presence made only of protected
    lessons is exempt from the minimum; a presence with any editable lesson
    counts both. A substitute lesson uses its own teacher id, never the unit's.
    """
    editable: dict[tuple[int, date], dict[int, list[Any]]] = defaultdict(lambda: defaultdict(list))
    protected: dict[tuple[int, date], set[int]] = defaultdict(set)
    for (assignment_id, period), variable in state.x.items():
        assignment = state.assignment_by_id[assignment_id]
        position = state.position_of.get(period)
        if position is not None:
            editable[(assignment.teacher_id, period.school_date)][position].append(variable)
    for lesson in state.snapshot.protected_lessons:
        assignment = state.assignment_by_id.get(lesson.assignment_id)
        if assignment is None:
            continue
        if (
            state.scope.week is not None
            and week_index(state.snapshot.origin, lesson.period) != state.scope.week
        ):
            continue
        position = _slot_position(state.slots_by_day, lesson.period)
        if position is not None:
            protected[(lesson.teacher_id or assignment.teacher_id, lesson.period.school_date)].add(
                position
            )
    return editable, protected


def _add_presence_segment(
    state: _ScopeState,
    rule: Any,
    slots: Sequence[GridSlot],
    positions: Sequence[int],
    editable: Mapping[int, list[Any]],
    protected: set[int],
    *,
    tag: str,
    enforce: Any | None,
) -> None:
    """Enforce the minimum minutes and grid-block gap of one presence segment.

    The segment is a contiguous slot range. ``enforce`` is the designated lunch
    choice when the day is split, or ``None`` for the whole day. A segment with
    no editable lesson is a protected-only (or empty) presence and is exempt.
    """
    model = state.model
    protected_minutes = 0
    editable_minutes: list[Any] = []
    editable_literals: list[Any] = []
    occupied: list[Any] = []
    for position in positions:
        variables = editable.get(position, ())
        is_protected = position in protected
        occupied.append(
            _or_expressions(
                model, f"occ_{tag}_{position}", [*variables, *([1] if is_protected else [])]
            )
        )
        if variables:
            editable_literals.extend(variables)
            editable_minutes.append(
                _slot_duration_minutes(slots[position])
                * _or_expressions(model, f"edt_{tag}_{position}", list(variables))
            )
        if is_protected:
            protected_minutes += _slot_duration_minutes(slots[position])
    if not editable_literals and protected_minutes == 0:
        return
    has_editable = model.NewBoolVar(f"has_{tag}")
    if editable_literals:
        model.AddMaxEquality(has_editable, editable_literals)
    else:
        model.Add(has_editable == 0)
    active = [enforce, has_editable] if enforce is not None else [has_editable]
    model.Add(protected_minutes + sum(editable_minutes) >= rule.minimum_minutes).OnlyEnforceIf(
        active
    )
    gap_terms: list[Any] = []
    for index in range(1, len(positions) - 1):
        before = _or_expressions(model, f"before_{tag}_{positions[index]}", occupied[:index])
        after = _or_expressions(model, f"after_{tag}_{positions[index]}", occupied[index + 1 :])
        if (type(before) is int and before == 0) or (type(after) is int and after == 0):
            continue
        current = occupied[index]
        gap = model.NewBoolVar(f"gap_{tag}_{positions[index]}")
        model.Add(gap <= before)
        model.Add(gap <= after)
        model.Add(gap + current <= 1)
        model.Add(gap >= before + after - 1 - current)
        gap_terms.append(_slot_duration_minutes(slots[positions[index]]) * gap)
    if gap_terms:
        model.Add(sum(gap_terms) <= rule.max_gap_minutes).OnlyEnforceIf(active)


def _add_teacher_presence(
    state: _ScopeState,
    lunch_options_by_resource: Mapping[tuple[str, int, date], list[tuple[Any, int, int]]],
) -> None:
    """Apply the minimum hours and maximum gap per presence to the exact model.

    A required lunch designates exactly one free option per teacher and day; the
    designated choice splits the day into a morning and an afternoon presence.
    Without a lunch rule (or when dispensed) the whole day is one presence.
    """
    rules = {
        row.teacher_id: row
        for row in state.snapshot.teacher_presence
        if row.minimum_minutes is not None
    }
    if not rules:
        return
    editable, protected = _teacher_presence_occupancy(state)
    for teacher_id, school_date in sorted(set(editable) | set(protected)):
        rule = rules.get(teacher_id)
        if rule is None:
            continue
        slots = state.slots_by_day.get(school_date.weekday(), ())
        if not slots:
            continue
        by_position = dict(editable.get((teacher_id, school_date), {}))
        protected_positions = protected.get((teacher_id, school_date), set())
        tag = f"tp_{teacher_id}_{school_date.isoformat()}"
        if not rule.lunch_required or state.snapshot.lunch_rule is None:
            _add_presence_segment(
                state,
                rule,
                slots,
                range(len(slots)),
                by_position,
                protected_positions,
                tag=f"{tag}_day",
                enforce=None,
            )
            continue
        options = lunch_options_by_resource.get(("teacher", teacher_id, school_date), [])
        if not options:
            continue
        chosen = []
        for index, (flag, _start, _end) in enumerate(options):
            choice = state.model.NewBoolVar(f"choice_{tag}_{index}")
            state.model.Add(choice <= flag)
            chosen.append(choice)
        state.model.Add(sum(chosen) == 1)
        starts = [_slot_start_minutes(slot) for slot in slots]
        ends = [_slot_end_minutes(slot) for slot in slots]
        for choice, (_flag, option_start, option_end) in zip(chosen, options, strict=True):
            morning = [position for position, end in enumerate(ends) if end <= option_start]
            afternoon = [position for position, start in enumerate(starts) if start >= option_end]
            _add_presence_segment(
                state,
                rule,
                slots,
                morning,
                by_position,
                protected_positions,
                tag=f"{tag}_{option_start}_am",
                enforce=choice,
            )
            _add_presence_segment(
                state,
                rule,
                slots,
                afternoon,
                by_position,
                protected_positions,
                tag=f"{tag}_{option_start}_pm",
                enforce=choice,
            )


def _add_completion_measure(state: _ScopeState) -> None:
    model = state.model
    if not state.scope.completing_classes:
        return
    values: set[int] = {0, *state.scope.protected_days.values()}
    for (assignment_id, period), _variable in state.x.items():
        if set(state.assignment_by_id[assignment_id].class_ids) & set(
            state.scope.completing_classes
        ):
            values.add((period.school_date - state.snapshot.origin).days)
    upper = max(values)
    for class_id in state.scope.completing_classes:
        terms = [
            (period.school_date - state.snapshot.origin).days * variable
            for (assignment_id, period), variable in state.x.items()
            if class_id in state.assignment_by_id[assignment_id].class_ids
        ]
        day = model.NewIntVar(0, upper, f"day_{class_id}")
        model.AddMaxEquality(day, [*terms, state.scope.protected_days.get(class_id, 0)])
        state.days[class_id] = day
    for value in sorted(values):
        if value <= 0:
            continue
        flags = []
        for class_id, day in sorted(state.days.items()):
            flag = model.NewBoolVar(f"ge_{class_id}_{value}")
            model.Add(day >= value).OnlyEnforceIf(flag)
            model.Add(day <= value - 1).OnlyEnforceIf(flag.Not())
            flags.append(flag)
        count = model.NewIntVar(0, len(state.days), f"count_ge_{value}")
        model.Add(count == sum(flags))
        state.threshold_counts[value] = count


def _preference_terms(state: _ScopeState) -> list[Any]:
    """One dispreferred lesson counts its duration once, regardless of matches."""
    model = state.model
    terms: list[Any] = []
    for (assignment_id, period), variable in state.x.items():
        assignment = state.assignment_by_id[assignment_id]
        duration = period.duration_minutes
        if any(
            _soft_overlaps(state.snapshot, UnavailableResource.CLASS, class_id, period)
            for class_id in assignment.class_ids
        ) or _soft_overlaps(
            state.snapshot, UnavailableResource.TEACHER, assignment.teacher_id, period
        ):
            terms.append(duration * variable)
            continue
        room_flags = [
            state.room_choice[(assignment_id, period, room_id)]
            for room_id in state.rooms_of[(assignment_id, period)]
            if _soft_overlaps(state.snapshot, UnavailableResource.ROOM, room_id, period)
        ]
        if not room_flags:
            continue
        unfavourable = _or_expressions(
            model,
            f"unfavourable_{assignment_id}_{period.start_utc.isoformat()}",
            room_flags,
        )
        terms.append(duration * unfavourable)
    return terms


def _room_disruption_expression(
    state: _ScopeState, room_cost: Callable[[Assignment, Period, int], int]
) -> Any | None:
    """Cost of using a room other than the published one at a published period."""
    terms: list[Any] = []
    for (assignment_id, period), _variable in state.x.items():
        assignment = state.assignment_by_id[assignment_id]
        for room_id in state.rooms_of[(assignment_id, period)]:
            cost = room_cost(assignment, period, room_id)
            if cost:
                terms.append(cost * state.room_choice[(assignment_id, period, room_id)])
    if not terms:
        return None
    return sum(terms)


def _gap_resource_rows(state, kind):
    groups: dict[tuple[int, date], dict[int, list[Any]]] = defaultdict(lambda: defaultdict(list))
    for (assignment_id, period), variable in state.x.items():
        assignment = state.assignment_by_id[assignment_id]
        resource_ids = [assignment.teacher_id] if kind == "teacher" else list(assignment.class_ids)
        position = state.position_of.get(period)
        if position is not None:
            for resource_id in resource_ids:
                groups[(resource_id, period.school_date)][position].append(variable)
    for lesson in state.snapshot.protected_lessons:
        assignment = state.assignment_by_id.get(lesson.assignment_id)
        if assignment is None:
            continue
        if (
            state.scope.week is not None
            and week_index(state.snapshot.origin, lesson.period) != state.scope.week
        ):
            continue
        resource_ids = (
            [lesson.teacher_id or assignment.teacher_id]
            if kind == "teacher"
            else list(assignment.class_ids)
        )
        position = _slot_position(state.slots_by_day, lesson.period)
        if position is not None:
            for resource_id in resource_ids:
                groups[(resource_id, lesson.period.school_date)][position].append(1)
    return groups


def _resource_gap_terms(state, kind, resource_id, school_date, by_position):
    model = state.model
    terms = []
    slots = state.slots_by_day.get(school_date.weekday(), ())
    if len(slots) < 3:
        return terms
    occupancies: list[Any] = [
        _or_expressions(
            model,
            f"{kind}_occ_{resource_id}_{school_date.isoformat()}_{position}",
            by_position.get(position, []),
        )
        for position in range(len(slots))
    ]
    for position in range(1, len(slots) - 1):
        prefix = f"{kind}_{resource_id}_{school_date.isoformat()}_{position}"
        before = _or_expressions(model, f"{prefix}_before", occupancies[:position])
        after = _or_expressions(model, f"{prefix}_after", occupancies[position + 1 :])
        if (type(before) is int and before == 0) or (type(after) is int and after == 0):
            continue
        occupied = occupancies[position]
        gap = model.NewBoolVar(f"{prefix}_gap")
        model.Add(gap <= before)
        model.Add(gap <= after)
        model.Add(gap + occupied <= 1)
        model.Add(gap >= before + after - 1 - occupied)
        terms.append(_slot_duration_minutes(slots[position]) * gap)
    return terms


def _gap_expression(state: _ScopeState, kind: str) -> Any | None:
    groups = _gap_resource_rows(state, kind)
    terms = []
    for (resource_id, school_date), by_position in sorted(groups.items()):
        terms.extend(_resource_gap_terms(state, kind, resource_id, school_date, by_position))
    if not terms:
        return None
    return sum(terms)


def _evidence_order(record: _StageRecord) -> tuple:
    rank = _COMPONENT_ORDER[record.stage.split(":", 1)[0]]
    if rank == 0:
        return (rank, -(record.threshold or 0), -(record.window or 0))
    return (rank, 0, -(record.window or 0))


def _room_continuity_expression(state: _ScopeState) -> Any:
    """Exact room count while temporal choices are still free in one scope."""
    pairs = {
        pair: {room: list(values) for room, values in rooms.items()}
        for pair, rooms in state.room_pairs.items()
    }
    for lesson in state.snapshot.protected_lessons:
        assignment = state.assignment_by_id.get(lesson.assignment_id)
        if assignment is not None:
            for class_id in assignment.class_ids:
                pair = (class_id, assignment.subject_id)
                pairs.setdefault(pair, {}).setdefault(lesson.room_id, []).append(1)
    return sum(
        sum(
            _or_expressions(state.model, f"used_{pair}_{room}", values)
            for room, values in rooms.items()
        )
        - 1
        for pair, rooms in pairs.items()
    )


def _assemble_evidence(
    records: list[_StageRecord], *, objective_scope: str, stop_reason: str
) -> SearchEvidence:
    ordered = sorted(records, key=_evidence_order)
    if stop_reason == STOP_SAFETY:
        # An interrupted stage may have no record. Later window/room proofs
        # cannot bridge that missing priority; conservatively certify no prefix.
        ordered = [replace(record, proven=False) for record in ordered]
    certified = 0
    for record in ordered:
        if not record.proven:
            break
        certified += 1
    stages = tuple(
        StageEvidence(
            stage=record.stage,
            value=record.value,
            proven=record.proven,
            reused=record.reused,
        )
        for record in ordered
    )
    return SearchEvidence(
        objective_scope=objective_scope,
        stages=stages,
        certified_stages=certified,
        stop_reason=stop_reason,
    )


def _extract_selections(state: _ScopeState, solver: cp_model.CpSolver) -> dict[int, list]:
    selections: dict[int, list[tuple[Period, int, int]]] = defaultdict(list)
    for (assignment_id, period), variable in state.x.items():
        if solver.Value(variable) != 1:
            continue
        room_id = next(
            room
            for room in state.rooms_of[(assignment_id, period)]
            if solver.Value(state.room_choice[(assignment_id, period, room)]) == 1
        )
        credit = (
            period.duration_minutes
            if (assignment_id, period) not in state.waste
            else period.duration_minutes - solver.Value(state.waste[(assignment_id, period)])
        )
        selections[assignment_id].append((period, room_id, credit))
    return selections


def _solve_with_cancellation(
    solver: cp_model.CpSolver,
    model: cp_model.CpModel,
    should_cancel: Callable[[], bool] | None,
) -> int:
    if should_cancel is not None and should_cancel():
        return cp_model.UNKNOWN
    return solve_with_cancellation(lambda: solver.Solve(model), solver.StopSearch, should_cancel)


def _solve_scope(
    state: _ScopeState,
    *,
    deadline: float,
    solver: cp_model.CpSolver,
    stop_at_first_complete: bool = False,
    optimize_room_continuity: bool = False,
    should_cancel: Callable[[], bool] | None = None,
    room_cost: Callable[[Assignment, Period, int], int] | None = None,
) -> tuple[str, dict[int, list] | None, list[_StageRecord], str]:
    """Solve one window: completion thresholds, freeze, then subordinate stages."""
    model = state.model
    records: list[_StageRecord] = []
    selections: dict[int, list] | None = None
    stop_reason = STOP_OPTIMAL
    window = state.scope.week
    solver.parameters.stop_after_first_solution = stop_at_first_complete

    def run_solve(stage: str):
        diagnostics.phase_started("PLACEMENT_SOLVE", window=window, stage=stage)
        started = monotonic()
        result = _solve_with_cancellation(solver, model, should_cancel)
        diagnostics.phase_finished(
            "PLACEMENT_SOLVE",
            window=window,
            stage=stage,
            started_at=started,
            status=solver.StatusName(result),
        )
        return result

    if should_cancel is not None and should_cancel():
        return STATUS_CANCELLED, None, records, "CANCELLED"
    pre_solve_budget = deadline - monotonic()
    if pre_solve_budget > MIN_STAGE_SECONDS:
        model.Minimize(0)
        # Feasibility comes before the lexicographic quality stages. A window
        # that cannot find any selection is worth less than a lower-quality one,
        # so the probe gets a real share of the window instead of a fixed 2s.
        solver.parameters.max_time_in_seconds = (
            pre_solve_budget
            if stop_at_first_complete
            else min(pre_solve_budget, max(2.0, pre_solve_budget * 0.5))
        )
        pre_status = run_solve("FEASIBILITY")
        if should_cancel is not None and should_cancel():
            return STATUS_CANCELLED, None, records, "CANCELLED"
        if pre_status == cp_model.INFEASIBLE:
            return STATUS_INFEASIBLE, None, records, STOP_SAFETY
        if pre_status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            selections = _extract_selections(state, solver)

    if should_cancel is not None and should_cancel():
        return STATUS_CANCELLED, None, records, "CANCELLED"
    if stop_at_first_complete:
        if selections is None:
            return STATUS_INCONCLUSIVE, None, records, STOP_SAFETY
        return STATUS_COMPLETE, selections, records, STOP_FEASIBLE

    def run_stages(stages: list[tuple[str, Any, int | None]]) -> str:
        nonlocal selections, stop_reason
        for name, expression, threshold in stages:
            if should_cancel is not None and should_cancel():
                return "CANCELLED"
            remaining = deadline - monotonic()
            if remaining <= MIN_STAGE_SECONDS:
                stop_reason = STOP_SAFETY
                return "INTERRUPTED"
            model.Minimize(expression)
            solver.parameters.max_time_in_seconds = remaining
            status = run_solve(name)
            if should_cancel is not None and should_cancel():
                return "CANCELLED"
            if status == cp_model.INFEASIBLE and selections is None:
                return "INFEASIBLE"
            if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                stop_reason = STOP_SAFETY
                return "INTERRUPTED"
            value = int(round(solver.ObjectiveValue()))
            proven = status == cp_model.OPTIMAL
            records.append(
                _StageRecord(
                    stage=name,
                    value=value,
                    proven=proven,
                    window=state.scope.week,
                    threshold=threshold,
                )
            )
            if not proven and stop_reason == STOP_OPTIMAL:
                stop_reason = STOP_FEASIBLE
            selections = _extract_selections(state, solver)
            model.Add(expression == value)
        return "OK"

    if should_cancel is not None and should_cancel():
        return STATUS_CANCELLED, None, records, "CANCELLED"
    thresholds = [
        (f"{STAGE_THRESHOLD}:{value}", expression, value)
        for value, expression in sorted(state.threshold_counts.items(), reverse=True)
    ]
    if thresholds:
        threshold_status = run_stages(thresholds)
        if threshold_status == "CANCELLED":
            return STATUS_CANCELLED, None, records, "CANCELLED"
        if threshold_status == "INFEASIBLE":
            return STATUS_INFEASIBLE, None, records, STOP_SAFETY
        if threshold_status == "INTERRUPTED":
            if selections is None:
                return STATUS_INCONCLUSIVE, None, records, STOP_SAFETY
            return STATUS_COMPLETE, selections, records, stop_reason
    for expression in state.threshold_counts.values():
        model.Add(expression == solver.Value(expression))
    subordinate: list[tuple[str, Any, int | None]] = []
    if room_cost is not None:
        room_disruption = _room_disruption_expression(state, room_cost)
        if room_disruption is not None:
            subordinate.append((STAGE_ROOM_DISRUPTION, room_disruption, None))
    teacher_gaps = _gap_expression(state, "teacher")
    if teacher_gaps is not None:
        subordinate.append((STAGE_TEACHER_GAPS, teacher_gaps, None))
    class_gaps = _gap_expression(state, "class")
    if class_gaps is not None:
        subordinate.append((STAGE_CLASS_GAPS, class_gaps, None))
    if state.x:
        terms = _preference_terms(state)
        if terms:
            subordinate.append((STAGE_PREFERENCES, sum(terms), None))
    if optimize_room_continuity:
        subordinate.append((STAGE_ROOM_CHANGES, _room_continuity_expression(state), None))
    if not subordinate and selections is None:
        remaining = deadline - monotonic()
        if remaining <= MIN_STAGE_SECONDS:
            return STATUS_INCONCLUSIVE, None, records, STOP_SAFETY
        model.Minimize(0)
        solver.parameters.max_time_in_seconds = remaining
        status = run_solve("FEASIBILITY")
        if should_cancel is not None and should_cancel():
            return STATUS_CANCELLED, None, records, "CANCELLED"
        if status == cp_model.INFEASIBLE:
            return STATUS_INFEASIBLE, None, records, STOP_SAFETY
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return STATUS_INCONCLUSIVE, None, records, STOP_SAFETY
        selections = _extract_selections(state, solver)
        return STATUS_COMPLETE, selections, records, stop_reason
    subordinate_status = run_stages(subordinate)
    if subordinate_status == "CANCELLED":
        return STATUS_CANCELLED, None, records, "CANCELLED"
    if subordinate_status == "INFEASIBLE" and selections is None:
        return STATUS_INFEASIBLE, None, records, STOP_SAFETY
    if selections is None:
        return STATUS_INCONCLUSIVE, None, records, STOP_SAFETY
    return STATUS_COMPLETE, selections, records, stop_reason


def _room_change_value(
    lessons: Sequence[Any],
    assignment_by_id: Mapping[int, Assignment],
    rooms: Mapping[int, int],
) -> int:
    pairs: dict[tuple[int, int], set[int]] = defaultdict(set)
    for lesson in lessons:
        assignment = assignment_by_id.get(lesson.assignment_id)
        if assignment is None:
            continue
        for class_id in assignment.class_ids:
            pairs[(class_id, assignment.subject_id)].add(rooms[lesson.lesson_id])
    return sum(max(0, len(values) - 1) for values in pairs.values())


def _optimize_rooms(
    snapshot: PlanningSnapshot,
    candidate: CandidateSchedule,
    *,
    deadline: float,
    num_workers: int,
    random_seed: int,
    should_cancel: Callable[[], bool] | None = None,
    room_cost: Callable[[Assignment, Period, int], int] | None = None,
) -> tuple[CandidateSchedule, _StageRecord]:
    room_start = monotonic()
    lessons = candidate.lessons
    lesson_by_id = {lesson.lesson_id: lesson for lesson in lessons}
    protected_ids = {lesson.lesson_id for lesson in snapshot.protected_lessons}
    assignment_by_id = {row.assignment_id: row for row in snapshot.assignments}
    fixed: dict[int, int] = {}
    variable_rooms: dict[int, tuple[int, ...]] = {}
    current_rooms = {row.lesson_id: row.room_id for row in lessons}
    for lesson in lessons:
        if lesson.lesson_id in protected_ids:
            fixed[lesson.lesson_id] = lesson.room_id
            continue
        assignment = assignment_by_id.get(lesson.assignment_id)
        rooms = available_rooms(snapshot, assignment, lesson.period) if assignment else ()
        if lesson.room_id not in rooms:
            return candidate, _StageRecord(
                stage=STAGE_ROOM_CHANGES,
                value=_room_change_value(lessons, assignment_by_id, current_rooms),
                proven=False,
                window=None,
            )
        if len(rooms) == 1:
            fixed[lesson.lesson_id] = rooms[0]
        else:
            variable_rooms[lesson.lesson_id] = rooms
    if not variable_rooms:
        value = _room_change_value(lessons, assignment_by_id, current_rooms)
        return candidate, _StageRecord(
            stage=STAGE_ROOM_CHANGES,
            value=value,
            proven=value == 0,
            window=None,
        )
    model = cp_model.CpModel()
    diagnostics.phase_started("ROOMS")
    choice = {
        (lesson_id, room_id): model.NewBoolVar(f"room_{lesson_id}_{room_id}")
        for lesson_id, rooms in variable_rooms.items()
        for room_id in rooms
    }
    for lesson_id, rooms in variable_rooms.items():
        model.Add(sum(choice[(lesson_id, room_id)] for room_id in rooms) == 1)
    exclusive: dict[int, list[tuple[Period, Any]]] = defaultdict(list)
    for lesson in lessons:
        for room_id in (
            (current_rooms[lesson.lesson_id],)
            if lesson.lesson_id in fixed
            else variable_rooms[lesson.lesson_id]
        ):
            exclusive[room_id].append(
                (
                    lesson.period,
                    choice[(lesson.lesson_id, room_id)]
                    if lesson.lesson_id in variable_rooms
                    else 1,
                )
            )
    for _room_id, rows in exclusive.items():
        _add_resource_exclusivity(model, rows)

    room_preference = 0
    for lesson in lessons:
        assignment = assignment_by_id.get(lesson.assignment_id)
        if assignment is None:
            continue
        if any(
            _soft_overlaps(snapshot, UnavailableResource.CLASS, class_id, lesson.period)
            for class_id in assignment.class_ids
        ) or _soft_overlaps(
            snapshot,
            UnavailableResource.TEACHER,
            lesson.teacher_id or assignment.teacher_id,
            lesson.period,
        ):
            # Its cost is constant whatever room is chosen.
            continue
        rooms = (
            (current_rooms[lesson.lesson_id],)
            if lesson.lesson_id in fixed
            else variable_rooms[lesson.lesson_id]
        )
        for room_id in rooms:
            if not _soft_overlaps(snapshot, UnavailableResource.ROOM, room_id, lesson.period):
                continue
            weight = lesson.period.duration_minutes
            if lesson.lesson_id in fixed:
                room_preference += weight
            else:
                room_preference += weight * choice[(lesson.lesson_id, room_id)]

    continuity_terms: dict[tuple[tuple[int, int], int], list[Any]] = defaultdict(list)
    for lesson in lessons:
        assignment = assignment_by_id.get(lesson.assignment_id)
        if assignment is None:
            continue
        rooms = (
            (current_rooms[lesson.lesson_id],)
            if lesson.lesson_id in fixed
            else variable_rooms[lesson.lesson_id]
        )
        for room_id in rooms:
            for class_id in assignment.class_ids:
                continuity_terms[((class_id, assignment.subject_id), room_id)].append(
                    choice[(lesson.lesson_id, room_id)] if lesson.lesson_id in variable_rooms else 1
                )
    used_by_pair: dict[tuple[int, int], list[Any]] = defaultdict(list)
    for (pair_key, room_id), terms in sorted(continuity_terms.items()):
        used_by_pair[pair_key].append(
            _or_expressions(model, f"used_{pair_key[0]}_{pair_key[1]}_{room_id}", terms)
        )
    continuity_expressions = []
    for pair_key, used in sorted(used_by_pair.items()):
        if len(used) < 2:
            continue
        excess = model.NewIntVar(0, len(used), f"continuity_{pair_key[0]}_{pair_key[1]}")
        model.Add(excess >= sum(used) - 1)
        model.Add(excess >= 0)
        model.Add(excess <= len(used))
        continuity_expressions.append(excess)

    diagnostics.model_built("ROOMS", model)
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = num_workers
    solver.parameters.random_seed = random_seed
    proven = True
    stages: list[Any] = []
    if room_cost is not None:
        disruption_terms: list[Any] = []
        for lesson_id, rooms in sorted(variable_rooms.items()):
            lesson = lesson_by_id[lesson_id]
            assignment = assignment_by_id.get(lesson.assignment_id)
            if assignment is None:
                continue
            for room_id in rooms:
                cost = room_cost(assignment, lesson.period, room_id)
                if cost:
                    disruption_terms.append(cost * choice[(lesson_id, room_id)])
        if disruption_terms:
            stages.append(sum(disruption_terms))
    if not (type(room_preference) is int and room_preference == 0):
        stages.append(room_preference)
    if continuity_expressions:
        stages.append(sum(continuity_expressions))
    if stages:
        incumbent = None
        for stage_index, expression in enumerate(stages):
            remaining = deadline - monotonic()
            if remaining <= MIN_STAGE_SECONDS:
                proven = False
                break
            model.Minimize(expression)
            solver.parameters.max_time_in_seconds = remaining
            diagnostics.phase_started("ROOMS", stage=f"STAGE_{stage_index}")
            solve_start = monotonic()
            status = _solve_with_cancellation(solver, model, should_cancel)
            diagnostics.phase_finished(
                "ROOMS",
                stage=f"STAGE_{stage_index}",
                started_at=solve_start,
                status=solver.StatusName(status),
            )
            if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                proven = False
                break
            if status != cp_model.OPTIMAL:
                proven = False
            model.Add(expression == int(round(solver.ObjectiveValue())))
            incumbent = {
                lesson_id: next(
                    room_id for room_id in rooms if solver.Value(choice[(lesson_id, room_id)]) == 1
                )
                for lesson_id, rooms in variable_rooms.items()
            }
        if incumbent is not None:
            current_rooms = {**current_rooms, **incumbent}
    candidate = CandidateSchedule(
        tuple(replace(row, room_id=current_rooms[row.lesson_id]) for row in lessons)
    )
    diagnostics.phase_finished("ROOMS", started_at=room_start, status=STAGE_ROOM_CHANGES)
    return candidate, _StageRecord(
        stage=STAGE_ROOM_CHANGES,
        value=_room_change_value(lessons, assignment_by_id, current_rooms),
        # Fixed temporal positions only prove a global room optimum at zero.
        proven=proven and _room_change_value(lessons, assignment_by_id, current_rooms) == 0,
        window=None,
    )


MAX_ROOM_REFINEMENT_MOVES = 50


def _quality_vector(snapshot: PlanningSnapshot, candidate: CandidateSchedule):
    return measure_initial_quality(snapshot, candidate).vector(
        origin=snapshot.origin, preferred_end_date=snapshot.preferred_end_date
    )


def _replace_lesson(candidate: CandidateSchedule, lesson: ScheduledLesson) -> CandidateSchedule:
    return CandidateSchedule(
        tuple(
            sorted(
                (lesson if row.lesson_id == lesson.lesson_id else row for row in candidate.lessons),
                key=lambda row: (row.period.school_date, row.period.start_local, row.lesson_id),
            )
        )
    )


def _refine_room_positions(
    snapshot: PlanningSnapshot,
    periods: tuple[Period, ...],
    candidate: CandidateSchedule,
    *,
    deadline: float,
    quality_of: Callable[[CandidateSchedule], Any] | None = None,
) -> CandidateSchedule:
    """Reopen same-week positions that allow an avoidable room change.

    A trial is accepted only when the full quality vector improves
    lexicographically, so completion, gaps and preferences never degrade. The
    caller may supply the adaptive recovery vector so repair never trades away
    its own priorities.
    """
    vector_of = quality_of or (lambda row: _quality_vector(snapshot, row))
    assignments = {row.assignment_id: row for row in snapshot.assignments}
    eligible = {
        row.assignment_id: eligible_periods(snapshot, row, periods) for row in snapshot.assignments
    }
    protected_ids = {row.lesson_id for row in snapshot.protected_lessons}
    current = candidate
    current_vector = vector_of(current)
    moves = 0
    improved = True
    while improved and moves < MAX_ROOM_REFINEMENT_MOVES and monotonic() < deadline:
        improved = False
        for lesson in sorted(
            current.lessons,
            key=lambda row: (row.assignment_id, row.period.start_utc, row.lesson_id),
        ):
            if lesson.lesson_id in protected_ids or monotonic() >= deadline:
                continue
            assignment = assignments.get(lesson.assignment_id)
            if assignment is None:
                continue
            week = week_index(snapshot.origin, lesson.period)
            for period in eligible.get(assignment.assignment_id, ()):
                if (
                    week_index(snapshot.origin, period) != week
                    or period.duration_minutes != lesson.period.duration_minutes
                    or period == lesson.period
                ):
                    continue
                for room_id in available_rooms(snapshot, assignment, period):
                    if monotonic() >= deadline:
                        break
                    trial = _replace_lesson(
                        current, replace(lesson, period=period, room_id=room_id)
                    )
                    if not validate_candidate(snapshot, trial).valid:
                        continue
                    vector = vector_of(trial)
                    if vector < current_vector:
                        current, current_vector = trial, vector
                        moves += 1
                        improved = True
                        break
                if improved:
                    break
            if improved:
                break
    return current


def _verify_materialization(
    snapshot: PlanningSnapshot,
    selections: Mapping[int, list[tuple[Period, int, int]]],
    distribution: QuotaDistribution,
) -> str | None:
    counts: Counter = Counter()
    for assignment_id, rows in selections.items():
        for period, _room, _credit in rows:
            counts[
                (assignment_id, week_index(snapshot.origin, period), period.duration_minutes)
            ] += 1
    expected = dict(distribution.counts)
    if dict(counts) != expected:
        differences = sorted(
            (key, counts.get(key, 0), expected.get(key, 0))
            for key in set(counts) | set(expected)
            if counts.get(key, 0) != expected.get(key, 0)
        )
        return f"period counts do not match the annual distribution: {differences[:4]}"
    for assignment_id, (week, duration) in distribution.final_groups.items():
        rows = sorted(selections.get(assignment_id, ()), key=lambda row: row[0].start_utc)
        if not rows:
            return "the final group has no materialized lesson"
        last = rows[-1][0]
        if week_index(snapshot.origin, last) != week or last.duration_minutes != duration:
            return "the partial lesson is not in the final group"
    return None


def _objective_days(snapshot: PlanningSnapshot, candidate: CandidateSchedule) -> int:
    if not candidate.lessons:
        return 0
    return max((lesson.period.school_date - snapshot.origin).days for lesson in candidate.lessons)


def solve_placement(
    snapshot: PlanningSnapshot,
    periods: tuple[Period, ...],
    *,
    distribution: QuotaDistribution | None = None,
    time_limit_seconds: float = 10.0,
    num_workers: int = 1,
    random_seed: int = 1,
    reuse: dict | None = None,
    cache_salt: str = "",
    should_cancel: Callable[[], bool] | None = None,
    quality_of: Callable[[CandidateSchedule], Any] | None = None,
    room_cost: Callable[[Assignment, Period, int], int] | None = None,
    stop_at_first_complete: bool = False,
) -> PlacementOutcome:
    if type(snapshot) is not PlanningSnapshot:
        raise ValueError("Placement needs a planning snapshot.")
    if time_limit_seconds <= 0:
        raise ValueError("The time limit must be positive.")
    if num_workers < 1:
        raise ValueError("At least one worker is required.")
    start = monotonic()
    deadline = start + time_limit_seconds
    if distribution is None:
        scopes = (_unrestricted_scope(snapshot, periods),)
        objective_scope = OBJECTIVE_SCOPE_UNRESTRICTED
    else:
        scopes = _window_scopes(snapshot, periods, distribution)
        objective_scope = OBJECTIVE_SCOPE_CONDITIONAL
    combined: dict[int, list] = defaultdict(list)
    records: list[_StageRecord] = []
    statistics = {
        "windows": len(scopes),
        "variables": 0,
        "build_ms": 0,
        "solve_ms": 0,
        "room_ms": 0,
    }
    cache = {} if reuse is None else reuse
    global_stop = STOP_OPTIMAL
    incomplete = False
    optimize_room_continuity = len(scopes) == 1 and not stop_at_first_complete
    ordered_scopes = sorted(scopes, key=lambda row: -(row.week or 0))
    reserve = min(2.0, max(0.0, deadline - start) * 0.1)
    try:
        for index, scope in enumerate(ordered_scopes):
            if should_cancel is not None and should_cancel():
                return PlacementOutcome(
                    STATUS_CANCELLED,
                    None,
                    None,
                    monotonic() - start,
                    objective_scope,
                    statistics,
                    message="The request was cancelled before the next window.",
                )
            now = monotonic()
            remaining = deadline - reserve - now
            if remaining <= MIN_STAGE_SECONDS:
                global_stop = STOP_SAFETY
                incomplete = True
                break
            window_deadline = now + remaining / (len(ordered_scopes) - index)
            cache_key = _scope_cache_key(scope, _lunch_cache_salt(snapshot, cache_salt))
            cached = cache.get(cache_key)
            if (
                cached is not None
                and cached.room_continuity == optimize_room_continuity
                and all(record.proven for record in cached.records)
            ):
                records.extend(replace(record, reused=True) for record in cached.records)
                for assignment_id, rows in cached.selections.items():
                    combined[assignment_id].extend(rows)
                continue
            estimated = _estimated_variables(scope)
            if estimated > MAX_PLACEMENT_VARIABLES:
                diagnostics.model_too_large(
                    "PLACEMENT", estimated, MAX_PLACEMENT_VARIABLES, window=scope.week
                )
                statistics["oversized_scopes"] = statistics.get("oversized_scopes", 0) + 1
                return PlacementOutcome(
                    STATUS_INCONCLUSIVE,
                    None,
                    None,
                    monotonic() - start,
                    objective_scope,
                    statistics,
                    message="The exact placement model exceeds the worker memory budget.",
                )
            build_start = monotonic()
            diagnostics.phase_started("PLACEMENT", window=scope.week)
            state = _build_scope_state(snapshot, scope)
            diagnostics.model_built("PLACEMENT", state.model, window=scope.week)
            statistics["build_ms"] += int((monotonic() - build_start) * 1000)
            statistics["variables"] += len(state.model.Proto().variables)
            solver = cp_model.CpSolver()
            solver.parameters.num_search_workers = num_workers
            solver.parameters.random_seed = random_seed
            solve_start = monotonic()
            status, selections, scope_records, stop_reason = _solve_scope(
                state,
                deadline=window_deadline,
                solver=solver,
                optimize_room_continuity=optimize_room_continuity,
                should_cancel=should_cancel,
                room_cost=room_cost,
                stop_at_first_complete=stop_at_first_complete,
            )
            statistics["solve_ms"] += int((monotonic() - solve_start) * 1000)
            if selections is not None and "first_candidate_ms" not in statistics:
                statistics["first_candidate_ms"] = int((monotonic() - start) * 1000)
            records.extend(scope_records)
            if (
                selections is not None
                and stop_reason == STOP_OPTIMAL
                and all(record.proven for record in scope_records)
            ):
                cache[cache_key] = _CachedWindow(
                    selections={key: tuple(rows) for key, rows in selections.items()},
                    records=tuple(scope_records),
                    room_continuity=optimize_room_continuity,
                )
            if status == STATUS_CANCELLED:
                return PlacementOutcome(
                    STATUS_CANCELLED,
                    None,
                    None,
                    monotonic() - start,
                    objective_scope,
                    statistics,
                    message="The request was cancelled during the search.",
                )
            if status == STATUS_INFEASIBLE:
                return PlacementOutcome(
                    STATUS_INFEASIBLE,
                    None,
                    None,
                    monotonic() - start,
                    objective_scope,
                    statistics,
                    message="The detailed model is infeasible for this distribution.",
                )
            if selections is None:
                global_stop = STOP_SAFETY
                incomplete = True
                break
            if stop_reason == STOP_SAFETY:
                global_stop = STOP_SAFETY
            elif stop_reason != STOP_OPTIMAL and global_stop == STOP_OPTIMAL:
                global_stop = stop_reason
            for assignment_id, rows in selections.items():
                combined[assignment_id].extend(rows)
    except NoEligiblePeriodsError as error:
        return PlacementOutcome(
            STATUS_INFEASIBLE,
            None,
            None,
            monotonic() - start,
            objective_scope,
            statistics,
            message=str(error),
        )
    if incomplete:
        return PlacementOutcome(
            STATUS_INCONCLUSIVE,
            None,
            None,
            monotonic() - start,
            objective_scope,
            statistics,
            evidence=_assemble_evidence(
                records, objective_scope=objective_scope, stop_reason=global_stop
            ),
            message="The search stopped before a complete candidate.",
        )
    if distribution is not None:
        mismatch = _verify_materialization(snapshot, combined, distribution)
        if mismatch is not None:
            return PlacementOutcome(
                STATUS_FAILED,
                None,
                None,
                monotonic() - start,
                objective_scope,
                statistics,
                message=mismatch,
            )
    candidate = _build_candidate(snapshot, combined)
    room_start = monotonic()
    if not optimize_room_continuity and not stop_at_first_complete:
        candidate, room_record = _optimize_rooms(
            snapshot,
            candidate,
            deadline=deadline,
            num_workers=num_workers,
            random_seed=random_seed,
            room_cost=room_cost,
            should_cancel=should_cancel,
        )
        if should_cancel is not None and should_cancel():
            return PlacementOutcome(
                STATUS_CANCELLED,
                None,
                None,
                monotonic() - start,
                objective_scope,
                statistics,
                message="The request was cancelled during room optimization.",
            )
        if room_record.value > 0 and deadline - monotonic() > MIN_STAGE_SECONDS:
            refined = _refine_room_positions(
                snapshot, periods, candidate, deadline=deadline, quality_of=quality_of
            )
            if refined != candidate:
                candidate = refined
                room_value = measure_initial_quality(snapshot, candidate).room_change_cost
                room_record = replace(room_record, value=room_value, proven=room_value == 0)
        records.append(room_record)
        if not room_record.proven and global_stop == STOP_OPTIMAL:
            global_stop = STOP_FEASIBLE
    statistics["room_ms"] += int((monotonic() - room_start) * 1000)
    return PlacementOutcome(
        STATUS_COMPLETE,
        candidate,
        _objective_days(snapshot, candidate),
        monotonic() - start,
        objective_scope,
        statistics,
        evidence=_assemble_evidence(
            records, objective_scope=objective_scope, stop_reason=global_stop
        ),
    )
