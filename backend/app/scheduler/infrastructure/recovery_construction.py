"""Repair published positions using current resources and residual demand."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import date, datetime
from fractions import Fraction
from time import monotonic
from typing import NamedTuple

from app.scheduler.domain.availability_priority import AvailabilityLedger, is_avoided
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
from app.scheduler.domain.priorities import PriorityWeights
from app.scheduler.domain.priority_value import WeeklyHistory
from app.scheduler.infrastructure.constructive import (
    _continues_open_presence,
    _evitar_kinds,
    _fills_hour,
    _gives_up,
    _grid_intervals_by_day,
    _local_interval,
    _longest_presences,
    _minimum_presence_teachers,
    _option_measures,
    _pace_lag,
    _pace_peers,
    _presence_day_complies,
    _presence_left_fits,
    _resource_keys,
    _room_value,
    _scarcity,
    _select_period,
    _slots_by_day,
    strict_window_periods,
)
from app.scheduler.infrastructure.placement_model import _build_candidate


class _Booking(NamedTuple):
    """One lesson booked by a recovery pass, with the credit that undo returns."""

    assignment: Assignment
    period: Period
    room: int
    credit: int


def construct_recovery(
    snapshot: PlanningSnapshot,
    periods: tuple[Period, ...],
    *,
    deadline: float,
    should_cancel: Callable[[], bool] | None = None,
    weights: PriorityWeights | None = None,
) -> CandidateSchedule | None:
    """Retain valid positions, then fill missing credit at the earliest capacity.

    All current hard rules apply, including newly changed school data.
    The frozen prefix stays physical; future module slices are reprojected.
    An Evitar option is refused while its resource has spare hours (T08). If that
    leaves no schedule, one relaxed pass repeats the recovery without the refusal (T09).
    """
    strict_periods = strict_window_periods(snapshot, periods, weights)
    candidate, refused = _construct_recovery(
        snapshot,
        strict_periods,
        deadline=deadline,
        should_cancel=should_cancel,
        weights=weights,
        strict=weights is None or bool(weights.teacher_preferences or weights.class_preferences),
    )
    if (
        candidate is None
        and (refused or strict_periods != periods)
        and not _interrupted(deadline, should_cancel)
    ):
        candidate, _ = _construct_recovery(
            snapshot,
            periods,
            deadline=deadline,
            should_cancel=should_cancel,
            weights=weights,
            strict=False,
        )
    if candidate is None and weights is not None and not _interrupted(deadline, should_cancel):
        candidate, _ = _construct_recovery(
            snapshot,
            periods,
            deadline=deadline,
            should_cancel=should_cancel,
            weights=weights,
            strict=False,
            fill=True,
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
    weights: PriorityWeights | None,
    strict: bool,
    fill: bool = False,
) -> tuple[CandidateSchedule | None, int]:
    """One recovery pass. Strict refuses Evitar options (T08) and counts the refusals."""
    assignments = {row.assignment_id: row for row in snapshot.assignments}
    remaining = {identity: residual_minutes(snapshot, identity) for identity in assignments}
    canonical = canonical_periods(periods)
    eligible = {}
    busy: dict[tuple, list[Period]] = defaultdict(list)
    occupancy: dict[tuple, list[tuple[int, int]]] = defaultdict(list)
    protected_intervals: dict[tuple, set[tuple[int, int]]] = defaultdict(set)
    selections: dict[int, list[tuple[Period, int, int]]] = defaultdict(list)
    protected_ids = {row.lesson_id for row in snapshot.protected_lessons}
    patterns: dict[tuple, int] = {}
    evitar_kinds = _evitar_kinds(weights)
    home_rooms = {row.class_id: row.room_id for row in snapshot.home_rooms}
    required = {
        identity: sum(module.required_minutes for module in row.modules)
        for identity, row in assignments.items()
    }
    pace_peers = _pace_peers(assignments) if weights is not None else {}
    # Weekly stability compares a slot with the previous teaching day, as the metric does:
    # retained published lessons and lessons booked so far both count.
    weekly_history = WeeklyHistory(snapshot)
    for row in (*snapshot.protected_lessons, *snapshot.baseline_lessons):
        if row.assignment_id in assignments:
            for class_id in assignments[row.assignment_id].class_ids:
                weekly_history.record(
                    class_id,
                    row.period.school_date,
                    row.period.start_local,
                    row.period.end_local,
                    row.assignment_id,
                )

    dispensed_teachers = snapshot.lunch_dispensed_teacher_ids
    minimum_teachers = _minimum_presence_teachers(snapshot)
    slots_by_day = _slots_by_day(snapshot)
    longest_presence = _longest_presences(snapshot, minimum_teachers, slots_by_day)
    grid_intervals = _grid_intervals_by_day(slots_by_day)
    assignments_by_teacher: dict[int, list[Assignment]] = defaultdict(list)
    for row in snapshot.assignments:
        assignments_by_teacher[row.teacher_id].append(row)
    periods_by_date: dict[date, list[Period]] = defaultdict(list)
    for day_period in canonical:
        periods_by_date[day_period.school_date].append(day_period)

    def interrupted() -> bool:
        return _interrupted(deadline, should_cancel)

    predecessors: dict[int, list[int]] = defaultdict(list)
    for source, target in snapshot.precedences:
        predecessors[target].append(source)

    def ready(identity: int, period: Period) -> bool:
        """All predecessor units are finished before the period (WBS 3.4)."""
        return all(
            remaining[source] <= 0 and last_end.get(source, period.start_utc) <= period.start_utc
            for source in predecessors.get(identity, ())
        )

    def occupy(assignment: Assignment, period: Period, room: int, teacher: int) -> None:
        for key in _resource_keys(assignment, room, teacher, period.school_date):
            busy[key].append(period)
            if key[0] != "room":
                occupancy[key].append(_local_interval(period))
        for class_id in assignment.class_ids:
            weekly_history.record(
                class_id,
                period.school_date,
                period.start_local,
                period.end_local,
                assignment.assignment_id,
            )

    def release(assignment: Assignment, period: Period, room: int, teacher: int) -> None:
        for key in _resource_keys(assignment, room, teacher, period.school_date):
            busy[key].remove(period)
            if key[0] != "room":
                occupancy[key].remove(_local_interval(period))
        for class_id in assignment.class_ids:
            weekly_history.release(
                class_id, period.school_date, period.start_local, period.end_local
            )

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

    def retain(assignment: Assignment, period: Period, room: int) -> _Booking:
        identity = assignment.assignment_id
        credit = min(remaining[identity], period.duration_minutes)
        selections[identity].append((period, room, credit))
        remaining[identity] -= credit
        current_end = last_end.get(identity)
        if current_end is None or period.end_utc > current_end:
            last_end[identity] = period.end_utc
        occupy(assignment, period, room, assignment.teacher_id)
        return _Booking(assignment, period, room, credit)

    def refresh_last_end(identity: int) -> None:
        ends = [period.end_utc for period, _room, _credit in selections[identity]]
        if identity in protected_end:
            ends.append(protected_end[identity])
        if ends:
            last_end[identity] = max(ends)
        else:
            last_end.pop(identity, None)

    def undo(booking: _Booking) -> None:
        """Reverse one retain exactly, so the booking leaves no trace in the pass."""
        assignment, period, room, credit = booking
        identity = assignment.assignment_id
        selections[identity].remove((period, room, credit))
        remaining[identity] += credit
        release(assignment, period, room, assignment.teacher_id)
        refresh_last_end(identity)

    protected_end: dict[int, datetime] = {}
    for row in snapshot.protected_lessons:
        assignment = assignments[row.assignment_id]
        teacher = row.teacher_id or assignment.teacher_id
        occupy(assignment, row.period, row.room_id, teacher)
        protected_intervals[("teacher", teacher, row.period.school_date)].add(
            _local_interval(row.period)
        )
        current_end = protected_end.get(row.assignment_id)
        if current_end is None or row.period.end_utc > current_end:
            protected_end[row.assignment_id] = row.period.end_utc
    last_end: dict[int, datetime] = dict(protected_end)
    for identity, assignment in assignments.items():
        if interrupted():
            return None, 0
        eligible[identity] = set(eligible_periods(snapshot, assignment, canonical))

    def complies(teacher_id: int, school_date: date, extra: Sequence[Period] = ()) -> bool:
        """True when the teacher's day, with the extra periods booked, meets the presence rule."""
        key = ("teacher", teacher_id, school_date)
        return _presence_day_complies(
            (*occupancy[key], *(_local_interval(period) for period in extra)),
            protected_intervals[key],
            minimum_teachers[teacher_id],
            snapshot.lunch_rule,
            grid_intervals.get(school_date.weekday(), ()),
        )

    def release_broken_presence_days(retained: Sequence[_Booking]) -> None:
        """Undo the retained lessons of a minimum teacher's day that breaks the rule.

        The main loop books them again, so a short retained presence cannot block a full one.
        """
        days = {
            (booking.assignment.teacher_id, booking.period.school_date)
            for booking in retained
            if booking.assignment.teacher_id in minimum_teachers
        }
        broken = {day for day in days if not complies(*day)}
        for booking in reversed(retained):
            if (booking.assignment.teacher_id, booking.period.school_date) in broken:
                undo(booking)

    retained: list[_Booking] = []
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
        if strict and is_avoided(snapshot, assignment, row.period, evitar_kinds=evitar_kinds):
            # D10: a published lesson now in Evitar moves while the strict pass can
            # place it elsewhere; the relaxed pass keeps the published position.
            continue
        rooms = free_rooms(assignment, row.period)
        if rooms:
            retained.append(
                retain(assignment, row.period, row.room_id if row.room_id in rooms else rooms[0])
            )
    release_broken_presence_days(retained)

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

    def minutes_left(teacher_id: int) -> int:
        return sum(remaining[row.assignment_id] for row in assignments_by_teacher[teacher_id])

    def next_presence_lesson(
        teacher_id: int, later: Period, booked: Sequence[_Booking]
    ) -> tuple[Assignment, int] | None:
        """The teacher's next assignment that can teach the later period, with its room."""
        previous = booked[-1].assignment.assignment_id
        candidates = sorted(
            (
                row
                for row in assignments_by_teacher[teacher_id]
                if remaining[row.assignment_id] > 0 and later in eligible[row.assignment_id]
            ),
            key=lambda row: (
                row.assignment_id != previous,
                -remaining[row.assignment_id],
                row.assignment_id,
            ),
        )
        planned = [(booking.assignment, booking.credit) for booking in booked]
        for row in candidates:
            if not ready(row.assignment_id, later):
                continue
            rooms = free_rooms(row, later)
            if rooms and (
                not strict or ledger.allows(row, later, planned, evitar_kinds=evitar_kinds)
            ):
                return row, rooms[0]
        return None

    def plan_presence_run(assignment: Assignment, period: Period, room: int) -> list[_Booking]:
        """Retain the later lessons that complete the teacher's day, or undo them all.

        Returns the retained run starting with the given lesson, or an empty list when the
        rest of the date cannot reach the presence minimum.
        """
        teacher_id = assignment.teacher_id
        booked = [retain(assignment, period, room)]
        for later in periods_by_date[period.school_date]:
            if later.start_utc <= period.start_utc:
                continue
            choice = next_presence_lesson(teacher_id, later, booked)
            if choice is None:
                continue
            booked.append(retain(choice[0], later, choice[1]))
            left = minutes_left(teacher_id)
            if complies(teacher_id, period.school_date) and _presence_left_fits(
                left, minimum_teachers[teacher_id], longest_presence[teacher_id]
            ):
                return booked
        for booking in reversed(booked):
            undo(booking)
        return []

    def book(assignment: Assignment, period: Period, room: int) -> list[_Booking]:
        """Retain a selected lesson, or the presence run that completes its teacher's day.

        Returns the lessons to commit, or an empty list when the lesson must wait.
        """
        teacher_id = assignment.teacher_id
        if teacher_id not in minimum_teachers:
            return [retain(assignment, period, room)]
        if not complies(teacher_id, period.school_date, (period,)):
            return plan_presence_run(assignment, period, room)
        # Extending a compliant presence must not strand minutes that no split into
        # valid presences could ever teach.
        credit = min(remaining[assignment.assignment_id], period.duration_minutes)
        left = minutes_left(teacher_id) - credit
        if not _presence_left_fits(
            left, minimum_teachers[teacher_id], longest_presence[teacher_id]
        ):
            return []
        return [retain(assignment, period, room)]

    for period in canonical:
        if interrupted() or _gives_up(ledger, period, strict=strict):
            return None, ledger.refused
        options = [
            (row, rooms)
            for row in options_by_period[period]
            if remaining[row.assignment_id] > 0
            and ready(row.assignment_id, period)
            and (rooms := free_rooms(row, period))
            and (not strict or ledger.allows(row, period, evitar_kinds=evitar_kinds))
        ]
        scores: dict[tuple[int, int], tuple[bool, int, int]] | None = (
            {} if weights is not None else None
        )
        if weights is None:
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
        else:
            weighted_options = []
            for assignment, rooms in options:
                identity = assignment.assignment_id
                necessary = ledger.is_necessary(assignment, period, evitar_kinds=evitar_kinds)
                urgency = ledger.urgency(assignment, period)
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
                    counts_teacher_single_lessons=assignment.teacher_id not in minimum_teachers,
                    weekly_references=tuple(
                        weekly_history.reference(
                            class_id, period.school_date, period.start_local, period.end_local
                        )
                        for class_id in assignment.class_ids
                    ),
                    pace_lag=_pace_lag(identity, pace_peers[identity], required, remaining),
                )
                allowed_rooms = []
                scarcity = _scarcity(weights, ledger, assignment, period, credit)
                for room in rooms:
                    value = _room_value(
                        weights, measures, assignment, room, home_rooms, credit=credit
                    )
                    if necessary or _fills_hour(
                        weights, measures, value + scarcity, strict=strict, fill=fill
                    ):
                        allowed_rooms.append((room, value))
                        scores[(identity, room)] = (necessary, value, urgency)
                if allowed_rooms:
                    allowed_rooms.sort(key=lambda pair: (-pair[1], pair[0]))
                    weighted_options.append(
                        (
                            (
                                not necessary,
                                urgency if necessary else 0,
                                -allowed_rooms[0][1],
                                identity,
                            ),
                            (assignment, tuple(room for room, _value in allowed_rooms)),
                        )
                    )
            options = [item for _key, item in sorted(weighted_options, key=lambda row: row[0])]
        for assignment, room in _select_period(
            options,
            deadline=deadline,
            scores=scores,
            fill_admitted=scores is not None and not strict,
        ):
            for booking in book(assignment, period, room):
                ledger.place(booking.assignment, booking.credit)
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
