"""Same-day compaction after a weighted construction (owner rules, 23 Oct 2026).

An edge lesson (the first or the last of a class day with an internal gap) moves into an
empty hour of the same classes on the same date when every hard rule still holds and the
priced cost of the classes and the teacher falls. The date never changes, so day counts,
finish dates and subject pace are unchanged by a move.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import date

import structlog

from app.scheduler.domain.calendar import normalize_period
from app.scheduler.domain.candidate import (
    Assignment,
    CandidateSchedule,
    GridSlot,
    PlanningSnapshot,
    ScheduledLesson,
    UnavailableResource,
    continuous_break_minutes,
)
from app.scheduler.domain.candidate_validation import lesson_violations, validate_candidate
from app.scheduler.domain.capacity import available_rooms
from app.scheduler.domain.class_day_gaps import class_day_excess_cost
from app.scheduler.domain.priorities import PRIORITY_MULTIPLIERS, UNIT_COSTS, PriorityWeights
from app.scheduler.domain.priority_metrics import _preference_minutes
from app.scheduler.domain.priority_value import _gap_minutes, _local_interval
from app.scheduler.domain.teacher_presence import PresenceLesson, teacher_day_complies
from app.scheduler.infrastructure.construction_support import _slots_by_day

logger = structlog.get_logger(__name__)

CLASS = "class"
TEACHER = "teacher"
ROOM = "room"


def compact_class_days(
    snapshot: PlanningSnapshot, candidate: CandidateSchedule, weights: PriorityWeights
) -> CandidateSchedule:
    """Return the candidate with its class days compacted, or the input when that is invalid."""
    compacted = _Compaction(snapshot, candidate, weights).run()
    if compacted is candidate:
        return candidate
    report = validate_candidate(snapshot, compacted)
    if report.valid:
        return compacted
    logger.warning(
        "class_day_compaction_fallback",
        reasons=[row.message for row in report.violations[:3]],
    )
    return candidate


class _Compaction:
    def __init__(
        self, snapshot: PlanningSnapshot, candidate: CandidateSchedule, weights: PriorityWeights
    ) -> None:
        self._snapshot = snapshot
        self._weights = weights
        self._source = candidate
        self._assignments = {row.assignment_id: row for row in snapshot.assignments}
        self._protected = frozenset(row.lesson_id for row in snapshot.protected_lessons)
        self._slots = _slots_by_day(snapshot)
        self._linked: defaultdict[int, set[int]] = defaultdict(set)
        for source, target in snapshot.precedences:
            self._linked[source].add(target)
            self._linked[target].add(source)
        self._lessons: dict[int, ScheduledLesson] = {}
        # (kind, resource id, date) -> {lesson id: local interval in minutes}
        self._occupancy: defaultdict[tuple[str, int, date], dict[int, tuple[int, int]]] = (
            defaultdict(dict)
        )
        self._moved = False
        for lesson in candidate.lessons:
            self._lessons[lesson.lesson_id] = lesson
            self._index(lesson)

    def run(self) -> CandidateSchedule:
        """Apply the best improving move per class day until no class day improves."""
        improved = True
        while improved:
            improved = False
            for key in self._class_days_with_gaps():
                while (move := self._best_move(key)) is not None:
                    self._apply(*move)
                    improved = True
        if not self._moved:
            return self._source
        return CandidateSchedule(
            tuple(self._lessons[row.lesson_id] for row in self._source.lessons)
        )

    def _class_days_with_gaps(self) -> list[tuple[int, date]]:
        gaps = {}
        for kind, class_id, school_date in self._occupancy:
            if kind == CLASS:
                intervals = self._intervals(CLASS, class_id, school_date)
                gap = self._gap(CLASS, class_id, school_date, intervals)
                if gap > 0:
                    gaps[(class_id, school_date)] = gap
        # Most excess gap first, then date and class, so the order is deterministic.
        return sorted(gaps, key=lambda key: (-gaps[key], key[1], key[0]))

    def _best_move(self, key: tuple[int, date]):
        class_id, school_date = key
        intervals = self._occupancy[(CLASS, class_id, school_date)]
        if len(intervals) < 2:
            return None
        ordered = sorted(intervals, key=lambda lesson_id: intervals[lesson_id])
        first_start = intervals[ordered[0]][0]
        last_start = intervals[ordered[-1]][0]
        occupied = set(intervals.values())
        targets = [
            slot
            for slot in self._slots.get(school_date.weekday(), ())
            if first_start < _minutes(slot.start_local) < last_start
            and (_minutes(slot.start_local), _minutes(slot.end_local)) not in occupied
        ]
        best = None
        for lesson_id in {ordered[0], ordered[-1]}:
            for slot in targets:
                move = self._evaluate(lesson_id, slot)
                if move is not None and (best is None or move[0] < best[0]):
                    best = move
        return None if best is None or best[0] >= 0 else (best[1], best[2])

    def _evaluate(self, lesson_id: int, slot: GridSlot):
        """Return (cost change, lesson id, moved lesson) when the move is feasible, else None."""
        if lesson_id in self._protected:
            return None
        lesson = self._lessons[lesson_id]
        if lesson.period.duration_minutes != slot.duration_minutes:
            return None
        assignment = self._assignments[lesson.assignment_id]
        school_date = lesson.period.school_date
        period = normalize_period(
            school_date, slot.start_local, slot.end_local, lesson.period.timezone_name
        )
        new_interval = _local_interval(period)
        if not self._feasible(lesson, assignment, period, new_interval):
            return None
        room_id = self._free_room(lesson, assignment, period)
        if room_id is None:
            return None
        moved = replace(lesson, period=period, room_id=room_id)
        if lesson_violations(
            self._snapshot, moved, assignments=self._assignments, protected_ids=self._protected
        ):
            return None
        gap_change, evitar_change = self._teacher_change(lesson, moved, assignment)
        if gap_change > 0 or evitar_change > 0:
            return None
        return (self._cost_change(lesson, moved, assignment), lesson_id, moved)

    def _teacher_change(
        self, lesson: ScheduledLesson, moved: ScheduledLesson, assignment: Assignment
    ) -> tuple[int, int]:
        """Gap and Evitar minutes the moved lesson adds to its teacher; zero or less is safe."""
        school_date = lesson.period.school_date
        teacher_id = _teacher_for(lesson, assignment)
        new_interval = _local_interval(moved.period)
        before = self._intervals(TEACHER, teacher_id, school_date)
        after = self._intervals_after(TEACHER, teacher_id, lesson, new_interval)
        gap_change = self._gap(TEACHER, teacher_id, school_date, after) - self._gap(
            TEACHER, teacher_id, school_date, before
        )
        evitar_before = _preference_minutes(self._snapshot, assignment, lesson)[0]
        evitar_after = _preference_minutes(self._snapshot, assignment, moved)[0]
        return gap_change, evitar_after - evitar_before

    def _feasible(
        self,
        lesson: ScheduledLesson,
        assignment: Assignment,
        period,
        new_interval: tuple[int, int],
    ) -> bool:
        school_date = period.school_date
        teacher_id = _teacher_for(lesson, assignment)
        for kind, identity in self._resources(lesson, assignment):
            if self._hard_blocked(kind, identity, period):
                return False
            if any(
                _overlaps(interval, new_interval)
                for other, interval in self._occupancy[(kind, identity, school_date)].items()
                if other != lesson.lesson_id
            ):
                return False
        if not self._order_kept(lesson, assignment, new_interval):
            return False
        for kind, identity in self._resources(lesson, assignment):
            if not self._lunch_kept(kind, identity, lesson, new_interval):
                return False
        return self._presence_kept(lesson, teacher_id, new_interval)

    def _resources(self, lesson: ScheduledLesson, assignment: Assignment):
        yield TEACHER, _teacher_for(lesson, assignment)
        for class_id in assignment.class_ids:
            yield CLASS, class_id

    def _hard_blocked(self, kind: str, identity: int, period) -> bool:
        resource = UnavailableResource.TEACHER if kind == TEACHER else UnavailableResource.CLASS
        return any(
            row.overlaps(period)
            for row in self._snapshot.hard_unavailable_on(resource, identity, period.school_date)
        )

    def _order_kept(
        self, lesson: ScheduledLesson, assignment: Assignment, new_interval: tuple[int, int]
    ) -> bool:
        """No lesson of the same or a precedence-linked assignment lies between old and new hour."""
        old_start = _local_interval(lesson.period)[0]
        low, high = sorted((old_start, new_interval[0]))
        linked = {assignment.assignment_id, *self._linked[assignment.assignment_id]}
        for class_id in assignment.class_ids:
            intervals = self._occupancy[(CLASS, class_id, lesson.period.school_date)]
            for other_id, (start, _end) in intervals.items():
                if (
                    other_id != lesson.lesson_id
                    and self._lessons[other_id].assignment_id in linked
                    and low < start < high
                ):
                    return False
        return True

    def _lunch_kept(
        self, kind: str, identity: int, lesson: ScheduledLesson, new_interval: tuple[int, int]
    ) -> bool:
        rule = self._snapshot.lunch_rule
        if rule is None or (
            kind == TEACHER and identity in self._snapshot.lunch_dispensed_teacher_ids
        ):
            return True
        intervals = self._intervals_after(kind, identity, lesson, new_interval)
        return continuous_break_minutes(intervals, rule) >= rule.minimum_minutes

    def _presence_kept(
        self, lesson: ScheduledLesson, teacher_id: int, new_interval: tuple[int, int]
    ) -> bool:
        rule = next(
            (row for row in self._snapshot.teacher_presence if row.teacher_id == teacher_id),
            None,
        )
        if rule is None:
            return True
        school_date = lesson.period.school_date
        lessons = [
            PresenceLesson(start, end, protected=False)
            for start, end in self._intervals_after(TEACHER, teacher_id, lesson, new_interval)
        ]
        grid = tuple(
            (_minutes(slot.start_local), _minutes(slot.end_local))
            for slot in self._slots.get(school_date.weekday(), ())
        )
        return teacher_day_complies(
            lessons, rule, lunch_rule=self._snapshot.lunch_rule, grid_slots=grid
        )

    def _free_room(self, lesson: ScheduledLesson, assignment: Assignment, period) -> int | None:
        new_interval = _local_interval(period)
        free = [
            room_id
            for room_id in available_rooms(self._snapshot, assignment, period)
            if not any(
                _overlaps(interval, new_interval)
                for other, interval in self._occupancy[(ROOM, room_id, period.school_date)].items()
                if other != lesson.lesson_id
            )
        ]
        if lesson.room_id in free:
            return lesson.room_id
        return free[0] if free else None

    def _cost_change(
        self, lesson: ScheduledLesson, moved: ScheduledLesson, assignment: Assignment
    ) -> int:
        """Priced change of the class and teacher costs. Same-date moves keep lesson counts."""
        new_interval = _local_interval(moved.period)
        change = 0
        for class_id in assignment.class_ids:
            change += self._day_cost_change(CLASS, class_id, lesson, new_interval)
        teacher_id = _teacher_for(lesson, assignment)
        change += self._day_cost_change(TEACHER, teacher_id, lesson, new_interval)
        evitar_before = _preference_minutes(self._snapshot, assignment, lesson)
        evitar_after = _preference_minutes(self._snapshot, assignment, moved)
        change += _penalty(self._weights, "teacher_preferences", evitar_after[0] - evitar_before[0])
        change += _penalty(self._weights, "class_preferences", evitar_after[1] - evitar_before[1])
        return change

    def _day_cost_change(
        self, kind: str, identity: int, lesson: ScheduledLesson, new_interval: tuple[int, int]
    ) -> int:
        """Gap change priced with its level, plus the excess-gap cost of a class day."""
        school_date = lesson.period.school_date
        before = self._gap(
            kind, identity, school_date, self._intervals(kind, identity, school_date)
        )
        after = self._gap(
            kind,
            identity,
            school_date,
            self._intervals_after(kind, identity, lesson, new_interval),
        )
        key = "class_gaps" if kind == CLASS else "teacher_gaps"
        change = _penalty(self._weights, key, after - before)
        if kind == CLASS:
            change += class_day_excess_cost(after) - class_day_excess_cost(before)
        return change

    def _intervals(self, kind: str, identity: int, school_date: date) -> list[tuple[int, int]]:
        return list(self._occupancy[(kind, identity, school_date)].values())

    def _intervals_after(
        self, kind: str, identity: int, lesson: ScheduledLesson, new_interval: tuple[int, int]
    ) -> list[tuple[int, int]]:
        others = self._occupancy[(kind, identity, lesson.period.school_date)]
        return [interval for other, interval in others.items() if other != lesson.lesson_id] + [
            new_interval
        ]

    def _gap(self, kind: str, identity: int, school_date: date, intervals) -> int:
        """Internal gap minutes of one resource day; a teacher exempt from lunch keeps no break."""
        rule = self._snapshot.lunch_rule
        if kind == TEACHER and identity in self._snapshot.lunch_dispensed_teacher_ids:
            rule = None
        return _gap_minutes(intervals, self._slots.get(school_date.weekday(), ()), rule)

    def _apply(self, lesson_id: int, moved: ScheduledLesson) -> None:
        self._unindex(self._lessons[lesson_id])
        self._lessons[lesson_id] = moved
        self._index(moved)
        self._moved = True

    def _index(self, lesson: ScheduledLesson) -> None:
        assignment = self._assignments[lesson.assignment_id]
        for kind, identity in (*self._resources(lesson, assignment), (ROOM, lesson.room_id)):
            self._occupancy[(kind, identity, lesson.period.school_date)][lesson.lesson_id] = (
                _local_interval(lesson.period)
            )

    def _unindex(self, lesson: ScheduledLesson) -> None:
        assignment = self._assignments[lesson.assignment_id]
        for kind, identity in (*self._resources(lesson, assignment), (ROOM, lesson.room_id)):
            del self._occupancy[(kind, identity, lesson.period.school_date)][lesson.lesson_id]


def _teacher_for(lesson: ScheduledLesson, assignment: Assignment) -> int:
    return lesson.teacher_id if lesson.teacher_id is not None else assignment.teacher_id


def _penalty(weights: PriorityWeights, key: str, minutes: int) -> int:
    """Priced cost of minutes of one criterion, positive when worse (T13 currency)."""
    return PRIORITY_MULTIPLIERS[getattr(weights, key)] * UNIT_COSTS[key] * minutes


def _minutes(value) -> int:
    return value.hour * 60 + value.minute


def _overlaps(first: tuple[int, int], second: tuple[int, int]) -> bool:
    return first[0] < second[1] and second[0] < first[1]
