"""Shared priority configuration contracts."""

import pytest
from pydantic import ValidationError

from app.scheduler.domain.candidate import LunchRule
from app.scheduler.domain.priorities import (
    CRITERION_KEYS,
    DEFAULT_LEVELS,
    PRIORITY_MULTIPLIERS,
    UNIT_COSTS,
    PriorityWeights,
    shift_of,
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
    assert set(UNIT_COSTS.values()) == {1}


def test_shift_of_splits_at_midpoint_and_handles_whole_day():
    from datetime import time

    lunch = LunchRule(time(12), time(14), 30)

    assert shift_of(time(11, 0), lunch) == "morning"
    assert shift_of(time(14, 0), lunch) == "afternoon"
    assert shift_of(time(9), None) == "day"
    assert shift_of(time(15), lunch, lunch_required=False) == "day"
