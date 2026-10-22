"""Integer value of one constructive schedule option, and its weekly-stability reference (T06)."""

from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import date, time
from enum import Enum

from app.scheduler.domain.calendar import grid_dates
from app.scheduler.domain.candidate import PlanningSnapshot
from app.scheduler.domain.priorities import PRIORITY_MULTIPLIERS, UNIT_COSTS, PriorityWeights


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
