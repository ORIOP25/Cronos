"""Internal gaps of a class day: one tolerated hour, then a fixed cost per excess minute.

Owner rules (23 Oct 2026): one internal gap hour in a class day is tolerated; two or more
in the same day is forbidden at every slider level. The gap is the class_gaps rule, with
lunch excluded and only gaps between the first and last lesson of the day.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from app.scheduler.domain.priority_value import _gap_minutes

TOLERATED_CLASS_DAY_GAP_MINUTES = 60
# Fixed and level-independent, in the T06 currency. One excess hour costs 120 000 units,
# more than one hour of teacher gap, Evitar or single-lesson day at the highest levels.
EXCESS_GAP_MINUTE_COST = 2_000
# T06 value of one excess minute removed from a class day during construction. Level-independent.
CLASS_DAY_EXCESS_UNIT = 192


def class_day_excess_minutes(gap_minutes: int) -> int:
    """Minutes of internal gap above the tolerated hour of one class day."""
    if type(gap_minutes) is not int or gap_minutes < 0:
        raise ValueError("Gap minutes must be a nonnegative integer.")
    return max(0, gap_minutes - TOLERATED_CLASS_DAY_GAP_MINUTES)


def class_day_excess_cost(gap_minutes: int) -> int:
    """Integer cost of the excess gap minutes of one class day."""
    return class_day_excess_minutes(gap_minutes) * EXCESS_GAP_MINUTE_COST


def class_day_excess_value(
    class_intervals: Iterable[Sequence[tuple[int, int]]],
    interval: tuple[int, int],
    slots: Sequence,
    lunch_rule,
) -> int:
    """T06 value of putting a lesson at ``interval``: excess minutes removed, per class, times the unit.

    ``class_intervals`` holds the occupied intervals of each class of the option on that day.
    """
    removed = 0
    for intervals in class_intervals:
        before = class_day_excess_minutes(_gap_minutes(intervals, slots, lunch_rule))
        after = class_day_excess_minutes(_gap_minutes((*intervals, interval), slots, lunch_rule))
        removed += before - after
    return CLASS_DAY_EXCESS_UNIT * removed


def class_day_gap_worsened(
    class_intervals: Iterable[Sequence[tuple[int, int]]],
    interval: tuple[int, int],
    slots: Sequence,
    lunch_rule,
) -> bool:
    """True when a lesson at ``interval`` adds excess gap minutes to any class day it joins.

    A day that already has excess gap may still receive a lesson that shrinks it.
    """
    return any(
        class_day_excess_minutes(_gap_minutes((*intervals, interval), slots, lunch_rule))
        > class_day_excess_minutes(_gap_minutes(intervals, slots, lunch_rule))
        for intervals in class_intervals
    )
