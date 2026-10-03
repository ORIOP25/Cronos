"""Temporal rule for lesson execution.

A lesson can only be registered as executed after its planned end instant.
The rule is pure: callers pass the clock instant and the lesson end instant.
"""

from __future__ import annotations

from datetime import datetime


def execution_allowed(now_utc: datetime, ends_at_utc: datetime) -> bool:
    """Return whether execution may be registered at ``now_utc``.

    Both instants must be timezone-aware. The exact end instant is allowed.
    """
    if now_utc.tzinfo is None or ends_at_utc.tzinfo is None:
        raise ValueError("Execution instants must be timezone-aware.")
    return now_utc >= ends_at_utc
