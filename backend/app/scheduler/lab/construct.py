"""Independent constructive witnesses for viable laboratory cases.

The constructor lives in the infrastructure package because the production
search reuses it as an initial incumbent. This module keeps the historical lab
import path.
"""

from __future__ import annotations

from app.scheduler.infrastructure.constructive import construct_schedule

__all__ = ["construct_schedule"]
