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
from app.scheduler.domain.priority_value import (
    WeeklyHistory,
    _fills_hour,
    _local_interval,
    _option_measures,
    _pace_lag,
    _pace_peers,
    _preference_value,
    _room_value,
    option_value,
)
from app.scheduler.infrastructure.construction_support import (
    _continues_open_presence,
    _evitar_kinds,
    _gives_up,
    _grid_intervals_by_day,
    _longest_presences,
    _minimum_presence_teachers,
    _predecessors_ready,
    _presence_day_complies,
    _presence_left_fits,
    _resource_keys,
    _scarcity,
    _slots_by_day,
    class_day_excess_option_value,
    class_day_gap_refused,
)
from app.scheduler.infrastructure.constructive import _select_period, strict_window_periods
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


class _RecoveryPass:
    """One recovery pass owns retained bookings, reversible credit and resources."""

    def __init__(
        self,
        snapshot: PlanningSnapshot,
        periods: tuple[Period, ...],
        *,
        deadline: float,
        should_cancel: Callable[[], bool] | None,
        weights: PriorityWeights | None,
        strict: bool,
        fill: bool,
    ) -> None:
        self.snapshot = snapshot
        self.periods = periods
        self.deadline = deadline
        self.should_cancel = should_cancel
        self.weights = weights
        self.strict = strict
        self.fill = fill
        self.initialize_progress()
        self.initialize_reference()
        self.initialize_presence()
        self.initialize_precedence()
        self.initialize_protected()

    def initialize_progress(self):
        self.assignments = {row.assignment_id: row for row in self.snapshot.assignments}
        self.remaining = {
            identity: residual_minutes(self.snapshot, identity) for identity in self.assignments
        }
        self.canonical = canonical_periods(self.periods)
        self.eligible = {}
        self.busy: dict[tuple, list[Period]] = defaultdict(list)
        self.occupancy: dict[tuple, list[tuple[int, int]]] = defaultdict(list)
        self.protected_intervals: dict[tuple, set[tuple[int, int]]] = defaultdict(set)
        self.selections: dict[int, list[tuple[Period, int, int]]] = defaultdict(list)
        self.protected_ids = {row.lesson_id for row in self.snapshot.protected_lessons}
        self.patterns: dict[tuple, int] = {}
        self.evitar_kinds = _evitar_kinds(self.weights)
        self.home_rooms = {row.class_id: row.room_id for row in self.snapshot.home_rooms}
        self.required = {
            identity: sum(module.required_minutes for module in row.modules)
            for identity, row in self.assignments.items()
        }
        self.pace_peers = _pace_peers(self.assignments) if self.weights is not None else {}

    def initialize_reference(self):
        # Weekly stability compares a slot with the previous teaching day, as the metric does:
        # retained published lessons and lessons booked so far both count.
        self.weekly_history = WeeklyHistory(self.snapshot)
        for row in (*self.snapshot.protected_lessons, *self.snapshot.baseline_lessons):
            if row.assignment_id in self.assignments:
                for class_id in self.assignments[row.assignment_id].class_ids:
                    self.weekly_history.record(
                        class_id,
                        row.period.school_date,
                        row.period.start_local,
                        row.period.end_local,
                        row.assignment_id,
                    )

    def initialize_presence(self):
        self.dispensed_teachers = self.snapshot.lunch_dispensed_teacher_ids
        self.minimum_teachers = _minimum_presence_teachers(self.snapshot)
        self.slots_by_day = _slots_by_day(self.snapshot)
        self.longest_presence = _longest_presences(
            self.snapshot, self.minimum_teachers, self.slots_by_day
        )
        self.grid_intervals = _grid_intervals_by_day(self.slots_by_day)
        self.assignments_by_teacher: dict[int, list[Assignment]] = defaultdict(list)
        for row in self.snapshot.assignments:
            self.assignments_by_teacher[row.teacher_id].append(row)
        self.periods_by_date: dict[date, list[Period]] = defaultdict(list)
        for day_period in self.canonical:
            self.periods_by_date[day_period.school_date].append(day_period)

    def initialize_precedence(self):
        self.predecessors: dict[int, list[int]] = defaultdict(list)
        for source, target in self.snapshot.precedences:
            self.predecessors[target].append(source)

    def initialize_protected(self):
        self.protected_end: dict[int, datetime] = {}
        for row in self.snapshot.protected_lessons:
            assignment = self.assignments[row.assignment_id]
            teacher = row.teacher_id or assignment.teacher_id
            self.occupy(assignment, row.period, row.room_id, teacher)
            self.protected_intervals[("teacher", teacher, row.period.school_date)].add(
                _local_interval(row.period)
            )
            current_end = self.protected_end.get(row.assignment_id)
            if current_end is None or row.period.end_utc > current_end:
                self.protected_end[row.assignment_id] = row.period.end_utc
        self.last_end: dict[int, datetime] = dict(self.protected_end)

    def prepare_eligible(self):
        for identity, assignment in self.assignments.items():
            if self.interrupted():
                return False
            self.eligible[identity] = set(
                eligible_periods(self.snapshot, assignment, self.canonical)
            )
        return True

    def retain_baseline(self):
        retained: list[_Booking] = []
        for row in sorted(
            self.snapshot.baseline_lessons, key=lambda row: (row.period.start_utc, row.lesson_id)
        ):
            if self.interrupted():
                return False
            assignment = self.assignments.get(row.assignment_id)
            if (
                assignment is None
                or row.lesson_id in self.protected_ids
                or self.remaining[row.assignment_id] <= 0
                or not self.ready(row.assignment_id, row.period)
            ):
                continue
            self.patterns.setdefault(
                (row.assignment_id, row.period.school_date.weekday(), row.period.start_local),
                row.room_id,
            )
            if row.period not in self.eligible[row.assignment_id]:
                continue
            if self.strict and is_avoided(
                self.snapshot, assignment, row.period, evitar_kinds=self.evitar_kinds
            ):
                # D10: a published lesson now in Evitar moves while the strict pass can
                # place it elsewhere; the relaxed pass keeps the published position.
                continue
            rooms = self.free_rooms(assignment, row.period)
            if not rooms:
                continue
            retained.append(
                self.retain(
                    assignment, row.period, row.room_id if row.room_id in rooms else rooms[0]
                )
            )
        self.release_broken_presence_days(retained)
        return True

    def initialize_options(self):
        self._ledger = AvailabilityLedger.build(
            self.snapshot,
            self.eligible,
            self.remaining,
            occupied=(
                (self.assignments[identity], period)
                for identity, rows in self.selections.items()
                for period, _room, _credit in rows
            ),
        )
        self.options_by_period: dict[Period, list[Assignment]] = defaultdict(list)
        for identity, assignment in self.assignments.items():
            if self.remaining[identity] > 0:
                for period in self.eligible[identity]:
                    self.options_by_period[period].append(assignment)

    def interrupted(self) -> bool:
        return _interrupted(self.deadline, self.should_cancel)

    def ready(self, identity: int, period: Period) -> bool:
        """All predecessor units are finished before the period (WBS 3.4)."""
        return _predecessors_ready(
            self.predecessors, self.remaining, self.last_end, identity, period
        )

    def occupy(self, assignment: Assignment, period: Period, room: int, teacher: int) -> None:
        for key in _resource_keys(assignment, room, teacher, period.school_date):
            self.busy[key].append(period)
            if key[0] != "room":
                self.occupancy[key].append(_local_interval(period))
        for class_id in assignment.class_ids:
            self.weekly_history.record(
                class_id,
                period.school_date,
                period.start_local,
                period.end_local,
                assignment.assignment_id,
            )

    def release(self, assignment: Assignment, period: Period, room: int, teacher: int) -> None:
        for key in _resource_keys(assignment, room, teacher, period.school_date):
            self.busy[key].remove(period)
            if key[0] != "room":
                self.occupancy[key].remove(_local_interval(period))
        for class_id in assignment.class_ids:
            self.weekly_history.release(
                class_id, period.school_date, period.start_local, period.end_local
            )

    def free_rooms(self, assignment: Assignment, period: Period) -> tuple[int, ...]:
        for kind, identity in (
            *(("class", class_id) for class_id in assignment.class_ids),
            ("teacher", assignment.teacher_id),
        ):
            key = (kind, identity, period.school_date)
            if any(
                period.start_utc < row.end_utc and row.start_utc < period.end_utc
                for row in self.busy[key]
            ):
                return ()
            lunch = self.snapshot.lunch_rule
            if (
                lunch is not None
                and not (kind == "teacher" and identity in self.dispensed_teachers)
                and continuous_break_minutes(
                    (*self.occupancy[key], _local_interval(period)),
                    lunch,
                )
                < lunch.minimum_minutes
            ):
                return ()
        preferred = self.patterns.get(
            (assignment.assignment_id, period.school_date.weekday(), period.start_local)
        )
        return tuple(
            sorted(
                (
                    room
                    for room in available_rooms(self.snapshot, assignment, period)
                    if not any(
                        period.start_utc < row.end_utc and row.start_utc < period.end_utc
                        for row in self.busy[("room", room, period.school_date)]
                    )
                ),
                key=lambda room: (room != preferred, room),
            )
        )

    def retain(self, assignment: Assignment, period: Period, room: int) -> _Booking:
        identity = assignment.assignment_id
        credit = min(self.remaining[identity], period.duration_minutes)
        self.selections[identity].append((period, room, credit))
        self.remaining[identity] -= credit
        current_end = self.last_end.get(identity)
        if current_end is None or period.end_utc > current_end:
            self.last_end[identity] = period.end_utc
        self.occupy(assignment, period, room, assignment.teacher_id)
        return _Booking(assignment, period, room, credit)

    def refresh_last_end(self, identity: int) -> None:
        ends = [period.end_utc for period, _room, _credit in self.selections[identity]]
        if identity in self.protected_end:
            ends.append(self.protected_end[identity])
        if ends:
            self.last_end[identity] = max(ends)
        else:
            self.last_end.pop(identity, None)

    def undo(self, booking: _Booking) -> None:
        """Reverse one retain exactly, so the booking leaves no trace in the pass."""
        assignment, period, room, credit = booking
        identity = assignment.assignment_id
        self.selections[identity].remove((period, room, credit))
        self.remaining[identity] += credit
        self.release(assignment, period, room, assignment.teacher_id)
        self.refresh_last_end(identity)

    def complies(self, teacher_id: int, school_date: date, extra: Sequence[Period] = ()) -> bool:
        """True when the teacher's day, with the extra periods booked, meets the presence rule."""
        key = ("teacher", teacher_id, school_date)
        return _presence_day_complies(
            (*self.occupancy[key], *(_local_interval(period) for period in extra)),
            self.protected_intervals[key],
            self.minimum_teachers[teacher_id],
            self.snapshot.lunch_rule,
            self.grid_intervals.get(school_date.weekday(), ()),
        )

    def release_broken_presence_days(self, retained: Sequence[_Booking]) -> None:
        """Undo the retained lessons of a minimum teacher's day that breaks the rule.

        The main loop books them again, so a short retained presence cannot block a full one.
        """
        days = {
            (booking.assignment.teacher_id, booking.period.school_date)
            for booking in retained
            if booking.assignment.teacher_id in self.minimum_teachers
        }
        broken = {day for day in days if not self.complies(*day)}
        for booking in reversed(retained):
            if (booking.assignment.teacher_id, booking.period.school_date) in broken:
                self.undo(booking)

    def minutes_left(self, teacher_id: int) -> int:
        return sum(
            self.remaining[row.assignment_id] for row in self.assignments_by_teacher[teacher_id]
        )

    def next_presence_lesson(
        self, teacher_id: int, later: Period, booked: Sequence[_Booking]
    ) -> tuple[Assignment, int] | None:
        """The teacher's next assignment that can teach the later period, with its room."""
        previous = booked[-1].assignment.assignment_id
        candidates = sorted(
            (
                row
                for row in self.assignments_by_teacher[teacher_id]
                if self.remaining[row.assignment_id] > 0
                and later in self.eligible[row.assignment_id]
            ),
            key=lambda row: (
                row.assignment_id != previous,
                -self.remaining[row.assignment_id],
                row.assignment_id,
            ),
        )
        planned = [(booking.assignment, booking.credit) for booking in booked]
        for row in candidates:
            if not self.ready(row.assignment_id, later):
                continue
            rooms = self.free_rooms(row, later)
            if rooms and (
                not self.strict
                or self._ledger.allows(row, later, planned, evitar_kinds=self.evitar_kinds)
            ):
                return row, rooms[0]
        return None

    def plan_presence_run(
        self, assignment: Assignment, period: Period, room: int
    ) -> list[_Booking]:
        """Retain the later lessons that complete the teacher's day, or undo them all.

        Returns the retained run starting with the given lesson, or an empty list when the
        rest of the date cannot reach the presence minimum.
        """
        teacher_id = assignment.teacher_id
        booked = [self.retain(assignment, period, room)]
        for later in self.periods_by_date[period.school_date]:
            if later.start_utc <= period.start_utc:
                continue
            choice = self.next_presence_lesson(teacher_id, later, booked)
            if choice is None:
                continue
            booked.append(self.retain(choice[0], later, choice[1]))
            left = self.minutes_left(teacher_id)
            if self.complies(teacher_id, period.school_date) and _presence_left_fits(
                left, self.minimum_teachers[teacher_id], self.longest_presence[teacher_id]
            ):
                return booked
        for booking in reversed(booked):
            self.undo(booking)
        return []

    def book(self, assignment: Assignment, period: Period, room: int) -> list[_Booking]:
        """Retain a selected lesson, or the presence run that completes its teacher's day.

        Returns the lessons to commit, or an empty list when the lesson must wait.
        """
        teacher_id = assignment.teacher_id
        if teacher_id not in self.minimum_teachers:
            return [self.retain(assignment, period, room)]
        if not self.complies(teacher_id, period.school_date, (period,)):
            return self.plan_presence_run(assignment, period, room)
        # Extending a compliant presence must not strand minutes that no split into
        # valid presences could ever teach.
        credit = min(self.remaining[assignment.assignment_id], period.duration_minutes)
        left = self.minutes_left(teacher_id) - credit
        if not _presence_left_fits(
            left, self.minimum_teachers[teacher_id], self.longest_presence[teacher_id]
        ):
            return []
        return [self.retain(assignment, period, room)]

    def run(self) -> tuple[CandidateSchedule | None, int]:
        if not self.prepare_eligible() or not self.retain_baseline():
            return None, 0
        self.initialize_options()
        for period in self.canonical:
            if self.interrupted() or _gives_up(self._ledger, period, strict=self.strict):
                return None, self._ledger.refused
            options, scores = self.period_options(period)
            self.book_period(period, options, scores)
            if not any(self.remaining.values()):
                break
        return self.finish()

    def finish(self):
        if self.interrupted() or any(self.remaining.values()):
            return None, self._ledger.refused
        self.normalize_selections()
        candidate = _build_candidate(self.snapshot, self.selections)
        valid = validate_candidate(self.snapshot, candidate).valid
        return (candidate if valid else None), self._ledger.refused

    def admits_class_days(self, assignment, period) -> bool:
        """Owner rule: no weighted lesson adds a second gap hour to a class day.

        A necessary lesson is admitted regardless of value, so the rule must hold before
        that check. The final fill pass and the unweighted route keep their existing rules.
        """
        if self.weights is None or self.fill:
            return True
        return not class_day_gap_refused(
            self.occupancy,
            assignment,
            period,
            self.slots_by_day.get(period.school_date.weekday(), ()),
            self.snapshot.lunch_rule,
        )

    def period_options(self, period):
        options = [
            (row, rooms)
            for row in self.options_by_period[period]
            if self.remaining[row.assignment_id] > 0
            and self.ready(row.assignment_id, period)
            and (rooms := self.free_rooms(row, period))
            and self.admits_class_days(row, period)
            and (
                not self.strict or self._ledger.allows(row, period, evitar_kinds=self.evitar_kinds)
            )
        ]
        scores = {} if self.weights is not None else None
        if self.weights is None:
            self.sort_unweighted_options(options, period)
        else:
            options = self.weighted_options(options, period, scores)
        return options, scores

    def weighted_options(self, options, period, scores):
        weighted = []
        for assignment, rooms in options:
            option = self.weighted_option(assignment, rooms, period, scores)
            if option is not None:
                weighted.append(option)
        return [item for _key, item in sorted(weighted, key=lambda row: row[0])]

    def book_period(self, period, options, scores):
        for assignment, room in _select_period(
            options,
            deadline=self.deadline,
            scores=scores,
            fill_admitted=scores is not None and not self.strict,
        ):
            for booking in self.book(assignment, period, room):
                self._ledger.place(booking.assignment, booking.credit)

    def sort_unweighted_options(self, options, period):
        options.sort(
            key=lambda item: (
                self._ledger.priority(item[0], period),
                self._ledger.unfavorable(item[0], period),
                -Fraction(
                    self.remaining[item[0].assignment_id],
                    sum(module.required_minutes for module in item[0].modules),
                ),
                not _continues_open_presence(
                    self.slots_by_day,
                    self.occupancy,
                    item[0].teacher_id,
                    period,
                    self.minimum_teachers,
                ),
                item[0].assignment_id,
            )
        )

    def weighted_option(self, assignment, rooms, period, scores):
        """Keep recovery's value-first room and assignment ordering explicit."""
        identity = assignment.assignment_id
        necessary = self._ledger.is_necessary(assignment, period, evitar_kinds=self.evitar_kinds)
        urgency = self._ledger.urgency(assignment, period)
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
            counts_teacher_single_lessons=assignment.teacher_id not in self.minimum_teachers,
            weekly_references=tuple(
                self.weekly_history.reference(
                    class_id, period.school_date, period.start_local, period.end_local
                )
                for class_id in assignment.class_ids
            ),
            pace_lag=_pace_lag(identity, self.pace_peers[identity], self.required, self.remaining),
        )
        allowed_rooms = []
        scarcity = _scarcity(self._ledger, assignment, period, credit)
        base_value = option_value(self.weights, measures) + class_day_excess_option_value(
            self.occupancy,
            assignment,
            period,
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
                allowed_rooms.append((room, value))
                scores[(identity, room)] = (necessary, value, urgency)
        if not allowed_rooms:
            return None
        allowed_rooms.sort(key=lambda pair: (-pair[1], pair[0]))
        return (
            (not necessary, urgency if necessary else 0, -allowed_rooms[0][1], identity),
            (assignment, tuple(room for room, _value in allowed_rooms)),
        )

    def normalize_selections(self):
        for identity, rows in self.selections.items():
            residual = residual_minutes(self.snapshot, identity)
            normalized = []
            for period, room, _credit in sorted(rows, key=lambda row: row[0].start_utc):
                if residual <= 0:
                    break
                credit = min(residual, period.duration_minutes)
                normalized.append((period, room, credit))
                residual -= credit
            self.selections[identity] = normalized


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
    return _RecoveryPass(
        snapshot,
        periods,
        deadline=deadline,
        should_cancel=should_cancel,
        weights=weights,
        strict=strict,
        fill=fill,
    ).run()
