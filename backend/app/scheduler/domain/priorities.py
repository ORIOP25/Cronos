"""Shared schedule-priority levels and weights."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import time
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.scheduler.domain.candidate import LunchRule

CRITERION_KEYS = (
    "finish_early",
    "teacher_gaps",
    "class_gaps",
    "teacher_single_lessons",
    "class_single_lessons",
    "teacher_preferences",
    "class_preferences",
    "class_same_room",
    "weekly_stability",
    "subject_pace",
    "update_stability",
)
DEFAULT_LEVELS = MappingProxyType(
    dict(zip(CRITERION_KEYS, (4, 3, 2, 2, 2, 3, 2, 2, 2, 3, 3), strict=True))
)
PRIORITY_MULTIPLIERS = (0, 1, 2, 4, 8)
UNIT_COSTS = MappingProxyType(dict.fromkeys(CRITERION_KEYS, 1))


@dataclass(frozen=True, init=False)
class PriorityWeights:
    """Validated immutable levels with named access for scheduler policies."""

    finish_early: int
    teacher_gaps: int
    class_gaps: int
    teacher_single_lessons: int
    class_single_lessons: int
    teacher_preferences: int
    class_preferences: int
    class_same_room: int
    weekly_stability: int
    subject_pace: int
    update_stability: int

    def __init__(self, levels: Mapping[str, int]):
        if not isinstance(levels, Mapping) or set(levels) != set(CRITERION_KEYS):
            raise ValueError("Priority levels must contain exactly the 11 known criteria.")
        if any(type(levels[key]) is not int or not 0 <= levels[key] <= 4 for key in CRITERION_KEYS):
            raise ValueError("Priority levels must be integers from 0 to 4.")
        for key in CRITERION_KEYS:
            object.__setattr__(self, key, levels[key])

    def to_dict(self) -> dict[str, int]:
        return {key: getattr(self, key) for key in CRITERION_KEYS}


def shift_of(
    start_local: time,
    lunch_rule: LunchRule | None,
    *,
    lunch_required: bool = True,
) -> str:
    """Return the lesson's school shift, using the lunch-window midpoint."""
    if not isinstance(start_local, time) or start_local.tzinfo is not None:
        raise ValueError("The lesson start must be a naive local time.")
    if lunch_rule is None or not lunch_required:
        return "day"
    midpoint = (
        lunch_rule.window_start.hour * 60
        + lunch_rule.window_start.minute
        + lunch_rule.window_end.hour * 60
        + lunch_rule.window_end.minute
    ) // 2
    start_minutes = start_local.hour * 60 + start_local.minute
    return "morning" if start_minutes < midpoint else "afternoon"
