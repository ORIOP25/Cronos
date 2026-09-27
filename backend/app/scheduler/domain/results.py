"""Typed search outcomes shared across scheduler layers.

The values here carry only domain types, so the application can depend on them
without importing CP-SAT, SQLAlchemy or the concrete search implementation.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.scheduler.domain.candidate import CandidateSchedule
from app.scheduler.domain.quality import InitialQualityMetrics, SearchEvidence

OUTCOME_COMPLETE = "COMPLETE"
OUTCOME_INFEASIBLE = "INFEASIBLE"
OUTCOME_INCONCLUSIVE = "INCONCLUSIVE"
OUTCOME_CANCELLED = "CANCELLED"
OUTCOME_STALE = "STALE"
OUTCOME_FAILED = "FAILED"
OUTCOME_INVALID_INPUT = "INVALID_INPUT"


@dataclass(frozen=True)
class SearchOutcome:
    status: str
    candidate: CandidateSchedule | None
    objective_days: int | None
    evidence: SearchEvidence | None
    message: str
    wall_time_seconds: float
    statistics: Mapping[str, int]
    quality: InitialQualityMetrics | None = None
