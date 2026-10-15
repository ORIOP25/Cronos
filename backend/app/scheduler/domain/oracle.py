"""Enumerative oracle for minimal scheduling instances.

The oracle shares the domain definitions with the generator but not the
CP-SAT implementation. It fixes protected lessons first, subtracts their
credit from the demand to enumerate, and explores only the remaining
placements. The final candidates are accepted by the independent validator.

Scope of the certified optimum: only the completion vector currently
implemented by :func:`oracle_objective`. It does not certify future quality
priorities such as gaps, preferences, disruption or room continuity.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from itertools import combinations, product

from app.scheduler.domain.calendar import Period
from app.scheduler.domain.candidate import (
    Assignment,
    CandidateSchedule,
    PlanningSnapshot,
    ScheduledLesson,
    allocate_lesson_identity,
)
from app.scheduler.domain.candidate_validation import validate_candidate
from app.scheduler.domain.capacity import is_physically_protected
from app.scheduler.domain.projection import FutureLesson, project_module_slices

MAX_ENUMERATED_COMBINATIONS = 50_000


class OracleBudgetExceededError(RuntimeError):
    """The instance is too large for complete enumeration; it is not infeasible."""


@dataclass(frozen=True)
class OracleResult:
    candidates: tuple[CandidateSchedule, ...]
    explored_combinations: int
    objective_scope: str = "COMPLETION_VECTOR_ONLY"

    @property
    def feasible(self) -> bool:
        return bool(self.candidates)


def _protected_credit(
    snapshot: PlanningSnapshot,
) -> dict[int, dict[int, int]]:
    credited: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for lesson in snapshot.protected_lessons:
        for slice_ in lesson.slices:
            credited[lesson.assignment_id][slice_.module_id] += slice_.credit_minutes
    return credited


def _residual_modules(
    snapshot: PlanningSnapshot,
    assignment: Assignment,
    protected_credit: dict[int, dict[int, int]],
) -> dict[int, int]:
    executed = snapshot.executed_for(assignment.assignment_id)
    residual = {}
    for module in assignment.modules:
        remaining = (
            module.required_minutes
            - executed.get(module.module_id, 0)
            - protected_credit.get(assignment.assignment_id, {}).get(module.module_id, 0)
        )
        if remaining < 0:
            raise ValueError("Protected or executed credit exceeds the module requirement.")
        residual[module.module_id] = remaining
    return residual


def _fixed_periods(
    snapshot: PlanningSnapshot, assignment: Assignment
) -> tuple[list[Period], list[Period], dict[int, list[Period]]]:
    by_class: list[Period] = []
    by_teacher: list[Period] = []
    by_room: dict[int, list[Period]] = defaultdict(list)
    member_classes = set(assignment.class_ids)
    for lesson in snapshot.protected_lessons:
        owner = snapshot.assignment_for(lesson.assignment_id)
        if owner is None:
            continue
        by_room[lesson.room_id].append(lesson.period)
        if member_classes & set(owner.class_ids):
            by_class.append(lesson.period)
        teacher = lesson.teacher_id if lesson.teacher_id is not None else owner.teacher_id
        if teacher == assignment.teacher_id:
            by_teacher.append(lesson.period)
    return by_class, by_teacher, by_room


def _overlaps(period: Period, fixed: list[Period]) -> bool:
    return any(
        period.start_utc < other.end_utc and other.start_utc < period.end_utc for other in fixed
    )


def _unavailable_overlap(
    snapshot: PlanningSnapshot, assignment: Assignment, period: Period, room_id: int
) -> bool:
    resources = {("teacher", assignment.teacher_id), ("room", room_id)}
    resources.update(("class", class_id) for class_id in assignment.class_ids)
    return any(
        (row.resource_type.value, row.resource_id) in resources and row.overlaps(period)
        for row in snapshot.unavailable
    )


def _eligible_pairs(
    snapshot: PlanningSnapshot,
    assignment: Assignment,
    periods: tuple[Period, ...],
) -> tuple[tuple[Period, int], ...]:
    by_class, by_teacher, by_room = _fixed_periods(snapshot, assignment)
    pairs = []
    for period in periods:
        if (
            period.timezone_name != snapshot.timezone_name
            or period.school_date < snapshot.origin
            or period.school_date > snapshot.hard_end_date
            or any(
                snapshot.blocked_on(class_id, period.school_date)
                for class_id in assignment.class_ids
            )
            or is_physically_protected(snapshot, period)
            or not any(slot.matches(period) for slot in snapshot.grid_slots)
            or _overlaps(period, by_class)
            or _overlaps(period, by_teacher)
        ):
            continue
        for room_id in sorted(assignment.eligible_room_ids):
            if _overlaps(period, by_room.get(room_id, [])):
                continue
            if _unavailable_overlap(snapshot, assignment, period, room_id):
                continue
            pairs.append((period, room_id))
    return tuple(pairs)


def _assignment_options(
    snapshot: PlanningSnapshot,
    assignment: Assignment,
    periods: tuple[Period, ...],
    protected_credit: dict[int, dict[int, int]],
    budget: list[int],
    reserved: frozenset[int],
) -> tuple[tuple[ScheduledLesson, ...], ...]:
    residual = _residual_modules(snapshot, assignment, protected_credit)
    if sum(residual.values()) == 0:
        return ((),)
    pairs = _eligible_pairs(snapshot, assignment, periods)
    completed = {
        module.module_id: snapshot.executed_for(assignment.assignment_id).get(module.module_id, 0)
        + protected_credit.get(assignment.assignment_id, {}).get(module.module_id, 0)
        for module in assignment.modules
    }
    options: list[tuple[ScheduledLesson, ...]] = []
    for size in range(1, len(pairs) + 1):
        for combo in combinations(pairs, size):
            budget[0] += 1
            if budget[0] > MAX_ENUMERATED_COMBINATIONS:
                raise OracleBudgetExceededError(
                    "The instance is too large for complete enumeration."
                )
            if len({period.start_utc for period, _ in combo}) != size:
                continue
            ordered = sorted(
                combo, key=lambda pair: (pair[0].school_date, pair[0].start_local, pair[1])
            )
            durations = [period.duration_minutes for period, _ in ordered]
            total = sum(residual.values())
            filled = sum(durations[:-1])
            if not filled < total <= sum(durations):
                continue
            credits = [*durations[:-1], total - filled]
            used = set(reserved)
            lessons = tuple(
                FutureLesson(
                    allocate_lesson_identity(assignment.assignment_id, position, used),
                    period.school_date,
                    period.start_local.hour * 60 + period.start_local.minute,
                    duration,
                    credit,
                )
                for position, ((period, _), duration, credit) in enumerate(
                    zip(ordered, durations, credits, strict=True), start=1
                )
            )
            slices = project_module_slices(
                assignment.modules,
                completed_minutes=completed,
                lessons=lessons,
            )
            by_lesson: dict[int, list] = {}
            for slice_ in slices:
                by_lesson.setdefault(slice_.lesson_id, []).append(slice_)
            options.append(
                tuple(
                    ScheduledLesson(
                        lesson_id=lesson.lesson_id,
                        assignment_id=assignment.assignment_id,
                        period=ordered[index][0],
                        room_id=ordered[index][1],
                        credit_minutes=lesson.credit_minutes,
                        slices=tuple(by_lesson.get(lesson.lesson_id, ())),
                    )
                    for index, lesson in enumerate(lessons)
                )
            )
    return tuple(options)


def enumerate_candidates(
    snapshot: PlanningSnapshot,
    periods: tuple[Period, ...],
) -> OracleResult:
    """Enumerate accepted complete candidates for a minimal instance.

    Protected lessons are fixed first; their credit is not enumerated again.
    Raises :class:`OracleBudgetExceededError` instead of returning an empty
    candidate set when the instance exceeds the laboratory budget.
    """
    if type(snapshot) is not PlanningSnapshot:
        raise ValueError("The oracle needs a planning snapshot.")
    protected_credit = _protected_credit(snapshot)
    reserved = frozenset(lesson.lesson_id for lesson in snapshot.protected_lessons)
    budget = [0]
    options = [
        _assignment_options(snapshot, row, periods, protected_credit, budget, reserved)
        for row in snapshot.assignments
    ]
    total = 1
    for rows in options:
        total *= len(rows)
    if total > MAX_ENUMERATED_COMBINATIONS:
        raise OracleBudgetExceededError("The instance is too large for complete enumeration.")

    accepted: list[CandidateSchedule] = []
    for combination in product(*options):
        lessons = tuple(lesson for option in combination for lesson in option)
        candidate = CandidateSchedule(
            tuple(sorted((*snapshot.protected_lessons, *lessons), key=_lesson_order))
        )
        if validate_candidate(snapshot, candidate).valid:
            accepted.append(candidate)
    return OracleResult(tuple(accepted), total)


def _lesson_order(lesson: ScheduledLesson) -> tuple:
    return (lesson.period.school_date, lesson.period.start_utc, lesson.lesson_id)


def oracle_objective(snapshot: PlanningSnapshot, candidate: CandidateSchedule) -> tuple[int, ...]:
    """Certified objective: collective completion vector, latest class first.

    Only this vector is exhaustively certified on minimal instances. Future
    quality components are outside the scope of the oracle.
    """
    completion: dict[int, date] = {}
    for lesson in candidate.lessons:
        assignment = snapshot.assignment_for(lesson.assignment_id)
        if assignment is None:
            continue
        for class_id in assignment.class_ids:
            previous = completion.get(class_id)
            if previous is None or lesson.period.school_date > previous:
                completion[class_id] = lesson.period.school_date
    class_ids = sorted({class_id for row in snapshot.assignments for class_id in row.class_ids})
    for class_id in class_ids:
        completion.setdefault(class_id, snapshot.origin)
    return tuple(
        sorted(
            ((completion[class_id] - snapshot.origin).days for class_id in class_ids),
            reverse=True,
        )
    )


def optimal_candidate(
    snapshot: PlanningSnapshot,
    periods: tuple[Period, ...],
) -> CandidateSchedule | None:
    """Return the completion-vector optimum, or None only when proven infeasible."""
    result = enumerate_candidates(snapshot, periods)
    if not result.candidates:
        return None
    return min(result.candidates, key=lambda candidate: oracle_objective(snapshot, candidate))
