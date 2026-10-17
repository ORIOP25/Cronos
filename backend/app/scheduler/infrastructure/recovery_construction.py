"""Repair published positions using current resources and residual demand."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import datetime
from fractions import Fraction
from time import monotonic

from app.scheduler.domain.availability_priority import AvailabilityLedger
from app.scheduler.domain.calendar import Period
from app.scheduler.domain.candidate import (
    Assignment,
    CandidateSchedule,
    PlanningSnapshot,
    continuous_break_minutes,
)
from app.scheduler.domain.candidate_validation import validate_candidate
from app.scheduler.domain.capacity import (
    available_rooms,
    canonical_periods,
    eligible_periods,
    residual_minutes,
)
from app.scheduler.infrastructure.constructive import (
    _continues_open_presence,
    _local_interval,
    _minimum_presence_teachers,
    _select_period,
    _slots_by_day,
)
from app.scheduler.infrastructure.placement_model import _build_candidate


def construct_recovery(
    snapshot: PlanningSnapshot,
    periods: tuple[Period, ...],
    *,
    deadline: float,
    should_cancel: Callable[[], bool] | None = None,
) -> CandidateSchedule | None:
    """Retain valid positions, then fill missing credit at the earliest capacity.

    All current hard rules apply, including newly changed school data.
    The frozen prefix stays physical; future module slices are reprojected.
    An Evitar option is refused while its resource has spare hours (T08). If that
    leaves no schedule, one relaxed pass repeats the recovery without the refusal (T09).
    """
    candidate, refused = _construct_recovery(
        snapshot, periods, deadline=deadline, should_cancel=should_cancel, strict=True
    )
    if candidate is None and refused and not _interrupted(deadline, should_cancel):
        candidate, _ = _construct_recovery(
            snapshot, periods, deadline=deadline, should_cancel=should_cancel, strict=False
        )
    return candidate


def _interrupted(deadline: float, should_cancel: Callable[[], bool] | None) -> bool:
    return monotonic() >= deadline or (should_cancel is not None and should_cancel())


def _construct_recovery(
    snapshot: PlanningSnapshot,
    periods: tuple[Period, ...],
    *,
    deadline: float,
    should_cancel: Callable[[], bool] | None,
    strict: bool,
) -> tuple[CandidateSchedule | None, int]:
    """One recovery pass. Strict refuses Evitar options (T08) and counts the refusals."""
    assignments = {row.assignment_id: row for row in snapshot.assignments}
    remaining = {identity: residual_minutes(snapshot, identity) for identity in assignments}
    canonical = canonical_periods(periods)
    eligible = {}
    busy: dict[tuple, list[Period]] = defaultdict(list)
    occupancy: dict[tuple, list[tuple[int, int]]] = defaultdict(list)
    selections: dict[int, list[tuple[Period, int, int]]] = defaultdict(list)
    protected_ids = {row.lesson_id for row in snapshot.protected_lessons}
    patterns: dict[tuple, int] = {}
    dispensed_teachers = snapshot.lunch_dispensed_teacher_ids
    minimum_teachers = _minimum_presence_teachers(snapshot)
    slots_by_day = _slots_by_day(snapshot)

    def interrupted() -> bool:
        return _interrupted(deadline, should_cancel)

    predecessors: dict[int, list[int]] = defaultdict(list)
    for source, target in snapshot.precedences:
        predecessors[target].append(source)
    last_end: dict[int, datetime] = {}

    def ready(identity: int, period: Period) -> bool:
        """All predecessor units are finished before the period (WBS 3.4)."""
        return all(
            remaining[source] <= 0 and last_end.get(source, period.start_utc) <= period.start_utc
            for source in predecessors.get(identity, ())
        )

    def occupy(assignment: Assignment, period: Period, room: int, teacher: int) -> None:
        for kind, identity in (
            *(("class", class_id) for class_id in assignment.class_ids),
            ("teacher", teacher),
            ("room", room),
        ):
            key = (kind, identity, period.school_date)
            busy[key].append(period)
            if kind != "room":
                occupancy[key].append(_local_interval(period))

    def free_rooms(assignment: Assignment, period: Period) -> tuple[int, ...]:
        for kind, identity in (
            *(("class", class_id) for class_id in assignment.class_ids),
            ("teacher", assignment.teacher_id),
        ):
            key = (kind, identity, period.school_date)
            if any(
                period.start_utc < row.end_utc and row.start_utc < period.end_utc
                for row in busy[key]
            ):
                return ()
            lunch = snapshot.lunch_rule
            if (
                lunch is not None
                and not (kind == "teacher" and identity in dispensed_teachers)
                and continuous_break_minutes(
                    (*occupancy[key], _local_interval(period)),
                    lunch,
                )
                < lunch.minimum_minutes
            ):
                return ()
        preferred = patterns.get(
            (assignment.assignment_id, period.school_date.weekday(), period.start_local)
        )
        return tuple(
            sorted(
                (
                    room
                    for room in available_rooms(snapshot, assignment, period)
                    if not any(
                        period.start_utc < row.end_utc and row.start_utc < period.end_utc
                        for row in busy[("room", room, period.school_date)]
                    )
                ),
                key=lambda room: (room != preferred, room),
            )
        )

    def retain(assignment: Assignment, period: Period, room: int) -> int:
        credit = min(remaining[assignment.assignment_id], period.duration_minutes)
        selections[assignment.assignment_id].append((period, room, credit))
        remaining[assignment.assignment_id] -= credit
        current_end = last_end.get(assignment.assignment_id)
        if current_end is None or period.end_utc > current_end:
            last_end[assignment.assignment_id] = period.end_utc
        occupy(assignment, period, room, assignment.teacher_id)
        return credit

    for row in snapshot.protected_lessons:
        assignment = assignments[row.assignment_id]
        occupy(assignment, row.period, row.room_id, row.teacher_id or assignment.teacher_id)
        current_end = last_end.get(row.assignment_id)
        if current_end is None or row.period.end_utc > current_end:
            last_end[row.assignment_id] = row.period.end_utc
    for identity, assignment in assignments.items():
        if interrupted():
            return None, 0
        eligible[identity] = set(eligible_periods(snapshot, assignment, canonical))
    for row in sorted(
        snapshot.baseline_lessons, key=lambda row: (row.period.start_utc, row.lesson_id)
    ):
        if interrupted():
            return None, 0
        assignment = assignments.get(row.assignment_id)
        if (
            assignment is None
            or row.lesson_id in protected_ids
            or remaining[row.assignment_id] <= 0
            or not ready(row.assignment_id, row.period)
        ):
            continue
        patterns.setdefault(
            (row.assignment_id, row.period.school_date.weekday(), row.period.start_local),
            row.room_id,
        )
        if row.period not in eligible[row.assignment_id]:
            continue
        rooms = free_rooms(assignment, row.period)
        if rooms:
            retain(assignment, row.period, row.room_id if row.room_id in rooms else rooms[0])

    ledger = AvailabilityLedger.build(
        snapshot,
        eligible,
        remaining,
        occupied=(
            (assignments[identity], period)
            for identity, rows in selections.items()
            for period, _room, _credit in rows
        ),
    )
    options_by_period: dict[Period, list[Assignment]] = defaultdict(list)
    for identity, assignment in assignments.items():
        if remaining[identity] > 0:
            for period in eligible[identity]:
                options_by_period[period].append(assignment)
    for period in canonical:
        if interrupted():
            return None, ledger.refused
        options = [
            (row, rooms)
            for row in options_by_period[period]
            if remaining[row.assignment_id] > 0
            and ready(row.assignment_id, period)
            and (rooms := free_rooms(row, period))
            and (not strict or ledger.allows(row, period))
        ]
        options.sort(
            key=lambda item: (
                ledger.priority(item[0], period),
                ledger.unfavorable(item[0], period),
                -Fraction(
                    remaining[item[0].assignment_id],
                    sum(module.required_minutes for module in item[0].modules),
                ),
                not _continues_open_presence(
                    slots_by_day, occupancy, item[0].teacher_id, period, minimum_teachers
                ),
                item[0].assignment_id,
            )
        )
        for assignment, room in _select_period(options, deadline=deadline):
            ledger.place(assignment, retain(assignment, period, room))
        if not any(remaining.values()):
            break
    if interrupted() or any(remaining.values()):
        return None, ledger.refused

    # New periods can precede retained periods. Only the final editable lesson
    # may be partial, so redistribute exact credit over their physical capacity.
    for identity, rows in selections.items():
        residual = residual_minutes(snapshot, identity)
        normalized = []
        for period, room, _credit in sorted(rows, key=lambda row: row[0].start_utc):
            if residual <= 0:
                break
            credit = min(residual, period.duration_minutes)
            normalized.append((period, room, credit))
            residual -= credit
        selections[identity] = normalized
    candidate = _build_candidate(snapshot, selections)
    valid = validate_candidate(snapshot, candidate).valid
    return (candidate if valid else None), ledger.refused
