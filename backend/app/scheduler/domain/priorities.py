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
        **dict.fromkeys(CRITERION_KEYS, 4),
        "finish_early": 1,
        "teacher_gaps": 12,
        "teacher_single_lessons": 60,
        "class_single_lessons": 40,
        "teacher_preferences": 80,
        "class_preferences": 20,
        "weekly_stability": 8,
        "subject_pace": 80,
        # One moved lesson at "Muito importante" (4 x 4800) equals one hour of Evitar (4 x 80 x 60).
        "update_stability": 4800,
    }
)
# One day past the preferred end: 600 moved lessons at equal levels (4 x 2 880 000 against 4 x 4 800).
LATE_DAY_COST = 2_880_000
# An empty hour in a fully booked calendar is not free, because the lesson must still be taught later.
SCARCITY_UNIT_COST = 32


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
