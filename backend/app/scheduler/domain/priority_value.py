"""Integer value of one constructive schedule option."""

from __future__ import annotations

from collections.abc import Mapping

from app.scheduler.domain.priorities import PRIORITY_MULTIPLIERS, UNIT_COSTS, PriorityWeights


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
