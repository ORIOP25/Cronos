"""Integer value of one constructive schedule option, and its weekly-stability reference (T06)."""

from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, time
from enum import Enum
from fractions import Fraction

from app.scheduler.domain.availability_priority import CLASS, TEACHER
from app.scheduler.domain.calendar import Period, grid_dates
from app.scheduler.domain.candidate import (
    Assignment,
    GridSlot,
    LunchRule,
    PlanningSnapshot,
    UnavailableResource,
)
from app.scheduler.domain.priorities import PRIORITY_MULTIPLIERS, UNIT_COSTS, PriorityWeights
from app.scheduler.domain.quality import lunch_minutes_in


class WeeklyReference(Enum):
    """What a class's weekly reference says when no lesson names an assignment."""

    NO_PREVIOUS_DAY = "no_previous_day"
    EMPTY = "empty"


def option_value(weights: PriorityWeights, measures: Mapping[str, int]) -> int:
    """Combine signed per-option measures using the configured priority levels."""
    if type(weights) is not PriorityWeights or not isinstance(measures, Mapping):
        raise ValueError("Option values need priority weights and a measure mapping.")
    if any(key not in UNIT_COSTS for key in measures):
        raise ValueError("Option measures must use known priority criteria.")
    if any(type(value) is not int for value in measures.values()):
        raise ValueError("Option measures must be integers.")
    return sum(
        PRIORITY_MULTIPLIERS[getattr(weights, key)] * UNIT_COSTS[key] * value
        for key, value in measures.items()
    )


def weekly_stability_measure(
    assignment_id: int, references: Iterable[int | WeeklyReference], credit: int
) -> int:
    """T06: one credit per class that keeps the subject, minus one per class left empty.

    A reference is the assignment a class had in the slot on its previous teaching day.
    A different lesson counts nothing, and a class with no previous teaching day is not
    measured. Empty last time counts as a change, as the weekly-stability metric counts it.
    """
    total = 0
    for reference in references:
        if reference == assignment_id:
            total += credit
        elif reference is WeeklyReference.EMPTY:
            total -= credit
    return total


class WeeklyHistory:
    """The lesson each class had in each slot on each date, read as weekly references (T06).

    A teaching day is a grid date of the schedule that the class is not blocked on. The
    reference uses the previous teaching day of the same weekday, not the latest lesson.
    """

    def __init__(self, snapshot: PlanningSnapshot) -> None:
        self._snapshot = snapshot
        self._teaching_days: dict[tuple[int, int], tuple[date, ...]] = {}
        self._lessons: defaultdict[tuple[int, int, time, time], dict[date, int]] = defaultdict(dict)

    def record(
        self, class_id: int, school_date: date, start: time, end: time, assignment_id: int
    ) -> None:
        self._lessons[(class_id, school_date.weekday(), start, end)][school_date] = assignment_id

    def release(self, class_id: int, school_date: date, start: time, end: time) -> None:
        self._lessons[(class_id, school_date.weekday(), start, end)].pop(school_date, None)

    def reference(
        self, class_id: int, school_date: date, start: time, end: time
    ) -> int | WeeklyReference:
        weekday = school_date.weekday()
        days = self._teaching_days_of(class_id, weekday)
        index = bisect_left(days, school_date)
        if index == 0:
            return WeeklyReference.NO_PREVIOUS_DAY
        lessons = self._lessons.get((class_id, weekday, start, end), {})
        return lessons.get(days[index - 1], WeeklyReference.EMPTY)

    def _teaching_days_of(self, class_id: int, weekday: int) -> tuple[date, ...]:
        key = (class_id, weekday)
        if key not in self._teaching_days:
            self._teaching_days[key] = tuple(
                day
                for day in grid_dates(
                    self._snapshot.origin, self._snapshot.hard_end_date, {weekday}
                )
                if not self._snapshot.blocked_on(class_id, day)
            )
        return self._teaching_days[key]


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
    occupied_intervals = [grid[index] for index in occupied]
    empty = [
        grid[index] for index in range(min(occupied) + 1, max(occupied)) if index not in occupied
    ]
    return sum(end - start for start, end in empty) - lunch_minutes_in(
        empty, lunch_rule, occupied_intervals
    )


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


def _joined_day_gain(intervals: Sequence[tuple[int, int]], interval: tuple[int, int]) -> int:
    """One when the lesson joins a day that held exactly one lesson, else zero.

    The first lesson of a day is not penalised (owner, 19 Oct 2026), and a single
    lesson counts per whole day, not per morning or afternoon (owner, 21 Oct 2026).
    """
    return int(len(intervals) == 1 and interval not in intervals)


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
    weekly_references: Sequence[int | WeeklyReference],
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
        measures["teacher_single_lessons"] = _joined_day_gain(teacher_intervals, interval) * credit
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
            _joined_day_gain(class_intervals, interval) * credit
        )
        if (CLASS, class_id) not in needed_evitar and _soft_overlap(
            snapshot, UnavailableResource.CLASS, class_id, period
        ):
            measures["class_preferences"] = measures.get("class_preferences", 0) - credit
    weekly_stability = weekly_stability_measure(assignment.assignment_id, weekly_references, credit)
    if weekly_stability:
        measures["weekly_stability"] = weekly_stability
    if pace_lag is not None:
        measures["subject_pace"] = round(pace_lag * credit)
    return measures


def _room_value(
    base_value: int,
    same_room_value: int,
    assignment: Assignment,
    room: int,
    home_rooms: Mapping[int, int],
) -> int:
    """T06: the option value in one room; only the home-room measure depends on it.

    ``base_value`` is the option value without that measure, and ``same_room_value``
    is the measure's value when the room is not the class's home room.
    """
    if not assignment.needs_special_room and any(
        class_id in home_rooms
        and home_rooms[class_id] in assignment.eligible_room_ids
        and home_rooms[class_id] != room
        for class_id in assignment.class_ids
    ):
        return base_value + same_room_value
    return base_value


_PREFERENCE_KEYS = ("teacher_preferences", "class_preferences")


def _preference_value(weights: PriorityWeights, measures: Mapping[str, int]) -> int:
    """The option value of its Evitar measures alone, the part that never changes by room."""
    return option_value(
        weights, {key: measures[key] for key in _PREFERENCE_KEYS if key in measures}
    )


def _fills_hour(
    value: int,
    preference_value: int,
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
    return value - preference_value > 0


def _soft_overlap(
    snapshot: PlanningSnapshot, resource: UnavailableResource, identity: int, period: Period
) -> bool:
    return any(
        row.overlaps(period)
        for row in snapshot.soft_unavailable_on(resource, identity, period.school_date)
    )
