"""Shared schedule-priority levels and weights."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

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
UNIT_COSTS = MappingProxyType(
    {
        **dict.fromkeys(CRITERION_KEYS, 1),
        "teacher_gaps": 3,
        "teacher_single_lessons": 5,
        "class_single_lessons": 10,
        "teacher_preferences": 10,
        "class_preferences": 5,
        "subject_pace": 20,
    }
)


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
