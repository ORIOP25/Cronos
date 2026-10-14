"""Joint physical eligibility, residual demand and aggregate capacity checks.

Pure domain logic: no clock, database, solver or environment access. The same
rules feed the necessary-capacity precheck, the annual relaxation and the
detailed placement, so a period that the validator rejects can never become a
placement candidate. Periods are canonicalized in chronological order and
duplicates are collapsed before any model uses them.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
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
    evidence_kind: str = "PROVEN_LOWER_BOUND"

    @property
    def proven_infeasible(self) -> bool:
        return any(minutes > 0 for minutes in self.deficits.values())


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
    for resource_type, resource_id in (
        (UnavailableResource.CLASS, assignment.class_id),
        (UnavailableResource.TEACHER, assignment.teacher_id),
    ):
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
    """Periods already occupied by protected lessons for the same resources."""
    return tuple(
        lesson.period
        for lesson in snapshot.protected_lessons
        if lesson.assignment_id == assignment.assignment_id
        or (snapshot.assignment_for(lesson.assignment_id) or assignment).class_id
        == assignment.class_id
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
            or snapshot.blocked_on(assignment.class_id, period.school_date)
            or is_physically_protected(snapshot, period)
            or not any(slot.matches(period) for slot in snapshot.grid_slots)
            or _is_unavailable(snapshot, assignment, period)
            or not available_rooms(snapshot, assignment, period)
            or any(
                _overlaps(period, occupied)
                for occupied in fixed_by_date.get(period.school_date, ())
            )
            or (protected_end is not None and period.start_utc < protected_end)
        ):
            continue
        eligible.append(period)
    return tuple(eligible)


def aggregate_capacity_check(
    snapshot: PlanningSnapshot, periods: tuple[Period, ...]
) -> CapacityCheck:
    deficits: dict[int, int] = {}
    for assignment in snapshot.assignments:
        remaining = residual_minutes(snapshot, assignment.assignment_id)
        if remaining <= 0:
            continue
        available = sum(
            period.duration_minutes for period in eligible_periods(snapshot, assignment, periods)
        )
        if available < remaining:
            deficits[assignment.assignment_id] = remaining - available
    return CapacityCheck(deficits)
