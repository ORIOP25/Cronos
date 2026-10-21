"""Joint physical eligibility, residual demand and aggregate capacity checks.

Pure domain logic: no clock, database, solver or environment access. The same
rules feed the necessary-capacity precheck, the annual relaxation and the
detailed placement, so a period that the validator rejects can never become a
placement candidate. Periods are canonicalized in chronological order and
duplicates are collapsed before any model uses them.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date

from app.scheduler.domain.calendar import Period
from app.scheduler.domain.candidate import (
    Assignment,
    PlanningSnapshot,
    SchedulingStrategy,
    UnavailableResource,
)


@dataclass(frozen=True)
class CapacityCheck:
    deficits: Mapping[int, int]
    class_deficits: Mapping[int, int] = field(default_factory=dict)
    teacher_deficits: Mapping[int, int] = field(default_factory=dict)
    evidence_kind: str = "PROVEN_LOWER_BOUND"

    @property
    def proven_infeasible(self) -> bool:
        return any(
            minutes > 0
            for deficit_map in (self.deficits, self.class_deficits, self.teacher_deficits)
            for minutes in deficit_map.values()
        )


def protected_credit_minutes(snapshot: PlanningSnapshot, assignment_id: int) -> int:
    return sum(
        lesson.credit_minutes
        for lesson in snapshot.protected_lessons
        if lesson.assignment_id == assignment_id
    )


def residual_minutes(snapshot: PlanningSnapshot, assignment_id: int) -> int:
    assignment = snapshot.assignment_for(assignment_id)
    if assignment is None:
        raise ValueError("The assignment does not belong to the snapshot.")
    executed = sum(snapshot.executed_for(assignment_id).values())
    required = sum(module.required_minutes for module in assignment.modules)
    return required - executed - protected_credit_minutes(snapshot, assignment_id)


def _overlaps(period: Period, other: Period) -> bool:
    return period.start_utc < other.end_utc and other.start_utc < period.end_utc


def canonical_periods(periods: tuple[Period, ...]) -> tuple[Period, ...]:
    """Chronological order with duplicate UTC intervals collapsed."""
    seen: set[tuple] = set()
    canonical = []
    for period in sorted(periods, key=lambda row: (row.start_utc, row.end_utc)):
        key = (period.start_utc, period.end_utc)
        if key in seen:
            continue
        seen.add(key)
        canonical.append(period)
    return tuple(canonical)


def is_physically_protected(snapshot: PlanningSnapshot, period: Period) -> bool:
    """Past instants and protected dates cannot receive new lessons."""
    if period.school_date in snapshot.protected_dates:
        return True
    return snapshot.now_utc is not None and period.start_utc <= snapshot.now_utc


def _is_unavailable(snapshot: PlanningSnapshot, assignment: Assignment, period: Period) -> bool:
    resources = [(UnavailableResource.TEACHER, assignment.teacher_id)]
    resources.extend((UnavailableResource.CLASS, class_id) for class_id in assignment.class_ids)
    for resource_type, resource_id in resources:
        if any(
            row.overlaps(period)
            for row in snapshot.hard_unavailable_on(resource_type, resource_id, period.school_date)
        ):
            return True
    return False


def room_free(snapshot: PlanningSnapshot, room_id: int, period: Period) -> bool:
    """A room is free when no hard unavailability or protected lesson occupies it."""
    if any(
        row.overlaps(period)
        for row in snapshot.hard_unavailable_on(
            UnavailableResource.ROOM, room_id, period.school_date
        )
    ):
        return False
    return not any(
        lesson.room_id == room_id and _overlaps(period, lesson.period)
        for lesson in snapshot.protected_on(period.school_date)
    )


def available_rooms(
    snapshot: PlanningSnapshot, assignment: Assignment, period: Period
) -> tuple[int, ...]:
    """Rooms of an assignment that are concrete, eligible and still free."""
    return tuple(
        room_id
        for room_id in sorted(assignment.eligible_room_ids)
        if room_free(snapshot, room_id, period)
    )


def fixed_periods(snapshot: PlanningSnapshot, assignment: Assignment) -> tuple[Period, ...]:
    """Periods already occupied by protected lessons for the same resources.

    A unit clashes with a protected lesson when they share the unit, any member
    class or the teacher (WBS 2.3.3).
    """
    member_classes = set(assignment.class_ids)
    return tuple(
        lesson.period
        for lesson in snapshot.protected_lessons
        if lesson.assignment_id == assignment.assignment_id
        or member_classes
        & set((snapshot.assignment_for(lesson.assignment_id) or assignment).class_ids)
        or (
            (
                lesson.teacher_id
                or (snapshot.assignment_for(lesson.assignment_id) or assignment).teacher_id
            )
            == assignment.teacher_id
        )
    )


def eligible_periods(
    snapshot: PlanningSnapshot,
    assignment: Assignment,
    periods: tuple[Period, ...],
) -> tuple[Period, ...]:
    """Chronological periods where class, teacher and one eligible room are free."""
    limit = (
        snapshot.preferred_end_date
        if snapshot.strategy is SchedulingStrategy.COMPLETE_GENERATION
        else snapshot.hard_end_date
    )
    fixed = fixed_periods(snapshot, assignment)
    fixed_by_date: dict[date, list[Period]] = {}
    for occupied in fixed:
        fixed_by_date.setdefault(occupied.school_date, []).append(occupied)
    protected_end = max(
        (
            lesson.period.end_utc
            for lesson in snapshot.protected_lessons
            if lesson.assignment_id == assignment.assignment_id
        ),
        default=None,
    )
    eligible = []
    for period in canonical_periods(periods):
        if (
            period.timezone_name != snapshot.timezone_name
            or period.school_date < snapshot.origin
            or period.school_date > limit
            or any(
                snapshot.blocked_on(class_id, period.school_date)
                for class_id in assignment.class_ids
            )
            or is_physically_protected(snapshot, period)
            or not any(slot.matches(period) for slot in snapshot.grid_slots)
            or _is_unavailable(snapshot, assignment, period)
            or not any(
                room_free(snapshot, room_id, period) for room_id in assignment.eligible_room_ids
            )
            or any(
                _overlaps(period, occupied)
                for occupied in fixed_by_date.get(period.school_date, ())
            )
            or (protected_end is not None and period.start_utc < protected_end)
        ):
            continue
        eligible.append(period)
    return tuple(eligible)


def _add_union_minutes(union: dict[tuple, int], periods: tuple[Period, ...]) -> None:
    for period in periods:
        union[(period.start_utc, period.end_utc)] = period.duration_minutes


def aggregate_capacity_check(
    snapshot: PlanningSnapshot, periods: tuple[Period, ...]
) -> CapacityCheck:
    """Per-assignment, per-class and per-teacher proven deficits in one pass.

    A class or a teacher only takes one lesson at a time, so the periods where
    their residual demand fits are the union of their assignments' eligible
    periods, counted once. These lower bounds never use the lunch rule, so they
    only name a resource when the shortage is demonstrated. A teacher is named
    only when its shortage is larger than the shortages of its own assignments,
    so one lone short assignment is not reported twice.
    """
    deficits: dict[int, int] = {}
    class_remaining: dict[int, int] = {}
    class_periods: dict[int, dict[tuple, int]] = {}
    teacher_remaining: dict[int, int] = {}
    teacher_periods: dict[int, dict[tuple, int]] = {}
    teacher_assignment_deficits: dict[int, int] = {}
    for assignment in snapshot.assignments:
        remaining = residual_minutes(snapshot, assignment.assignment_id)
        if remaining <= 0:
            continue
        eligible = eligible_periods(snapshot, assignment, periods)
        available = sum(period.duration_minutes for period in eligible)
        if available < remaining:
            deficits[assignment.assignment_id] = remaining - available
        teacher_id = assignment.teacher_id
        teacher_remaining[teacher_id] = teacher_remaining.get(teacher_id, 0) + remaining
        teacher_assignment_deficits[teacher_id] = teacher_assignment_deficits.get(
            teacher_id, 0
        ) + deficits.get(assignment.assignment_id, 0)
        _add_union_minutes(teacher_periods.setdefault(teacher_id, {}), eligible)
        for class_id in assignment.class_ids:
            class_remaining[class_id] = class_remaining.get(class_id, 0) + remaining
            _add_union_minutes(class_periods.setdefault(class_id, {}), eligible)
    class_deficits: dict[int, int] = {}
    for class_id, remaining in class_remaining.items():
        shared = sum(class_periods[class_id].values())
        if shared < remaining:
            class_deficits[class_id] = remaining - shared
    teacher_deficits: dict[int, int] = {}
    for teacher_id, remaining in teacher_remaining.items():
        shortage = remaining - sum(teacher_periods[teacher_id].values())
        if shortage > teacher_assignment_deficits[teacher_id]:
            teacher_deficits[teacher_id] = shortage
    return CapacityCheck(deficits, class_deficits, teacher_deficits)
