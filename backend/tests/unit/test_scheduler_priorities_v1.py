"""Shared priority configuration contracts."""

import pytest
from pydantic import ValidationError

from app.scheduler.domain.priorities import (
    CRITERION_KEYS,
    DEFAULT_LEVELS,
    LATE_DAY_COST,
    PRIORITY_MULTIPLIERS,
    UNIT_COSTS,
    PriorityWeights,
)
from app.schemas import SchedulePrioritiesUpdate


def test_priority_weights_accepts_exact_levels_and_exposes_named_values():
    weights = PriorityWeights(DEFAULT_LEVELS)

    assert tuple(weights.to_dict()) == CRITERION_KEYS
    assert weights.finish_early == 4
    assert weights.teacher_gaps == 3
    assert weights.class_gaps == 2
    assert weights.update_stability == 3
    assert tuple(DEFAULT_LEVELS.values()) == (4, 3, 2, 2, 2, 3, 2, 2, 2, 3, 3)


@pytest.mark.parametrize(
    "change",
    [
        lambda levels: levels.pop("finish_early"),
        lambda levels: levels.update(unexpected=1),
        lambda levels: levels.update(finish_early=5),
        lambda levels: levels.update(finish_early=-1),
        lambda levels: levels.update(finish_early=True),
        lambda levels: levels.update(finish_early=1.0),
    ],
    ids=("missing", "extra", "above-range", "below-range", "bool", "float"),
)
def test_priority_weights_rejects_invalid_level_mappings(change):
    levels = dict(DEFAULT_LEVELS)
    change(levels)

    with pytest.raises(ValueError):
        PriorityWeights(levels)


def test_priority_schema_reuses_strict_domain_validation():
    valid = SchedulePrioritiesUpdate(levels=dict(DEFAULT_LEVELS))

    assert valid.levels == dict(DEFAULT_LEVELS)
    with pytest.raises(ValidationError):
        SchedulePrioritiesUpdate(levels={**DEFAULT_LEVELS, "finish_early": True})
    with pytest.raises(ValidationError):
        SchedulePrioritiesUpdate(levels={**DEFAULT_LEVELS, "finish_early": 1.0})
    with pytest.raises(ValidationError):
        SchedulePrioritiesUpdate(levels={**DEFAULT_LEVELS, "unexpected": 1})


def test_priority_multipliers_and_unit_costs_are_complete():
    assert PRIORITY_MULTIPLIERS == (0, 1, 2, 4, 8)
    assert tuple(UNIT_COSTS) == CRITERION_KEYS
    # T15: S7 scaled these on the realistic pilot school; the rest stay at 4.
    assert {key: cost for key, cost in UNIT_COSTS.items() if cost != 4} == {
        "finish_early": 1,
        "teacher_gaps": 12,
        "teacher_single_lessons": 60,
        "class_single_lessons": 40,
        "teacher_preferences": 80,
        "class_preferences": 20,
        "weekly_stability": 8,
        "subject_pace": 80,
        "update_stability": 4800,
    }
    assert LATE_DAY_COST == 2_880_000


def test_unit_costs_keep_the_update_rates_of_the_calibration():
    # One moved lesson at "Muito importante" (4 x 4 800) equals one hour of teacher Evitar (4 x 80 x 60).
    assert 4 * UNIT_COSTS["update_stability"] == 4 * UNIT_COSTS["teacher_preferences"] * 60
    # One late day equals 600 moved lessons at equal levels.
    assert LATE_DAY_COST == 600 * UNIT_COSTS["update_stability"]
