"""Pure incremental curriculum demand contracts for adaptive scheduling."""

from dataclasses import dataclass
from typing import Any

from app.services.scheduler_complete_demand import (
    CompleteDemandItem,
    CompleteDemandLedgerBuilder,
)


@dataclass(frozen=True)
class IncrementalDemandLedger:
    """Remaining curriculum demand for class-subject assignments absent from the schedule."""

    items: tuple[CompleteDemandItem, ...]
    blockers: tuple[str, ...]

    @property
    def required_minutes(self) -> int:
        return sum(item.required_minutes for item in self.items)

    @property
    def is_complete(self) -> bool:
        return not self.blockers


class IncrementalDemandLedgerBuilder:
    """Build curriculum demand introduced after a published schedule exists."""

    def build(self, snapshot: dict[str, Any]) -> IncrementalDemandLedger:
        active_pairs = {
            (row["class_id"], row["subject_id"]) for row in snapshot.get("active_schedule", [])
        }
        assignments = [
            row
            for row in snapshot.get("class_subject_requirements", [])
            if (row["class_id"], row["subject_id"]) not in active_pairs
        ]
        ledger = CompleteDemandLedgerBuilder().build_for_assignments(
            snapshot,
            assignments,
            allow_empty=True,
            ignore_zero_remaining=True,
        )
        return IncrementalDemandLedger(
            items=ledger.items,
            blockers=ledger.blockers,
        )


# Keep the domain wording available to callers without duplicating the implementation.
IncrementalCurriculumDemandLedger = IncrementalDemandLedger
IncrementalCurriculumDemandLedgerBuilder = IncrementalDemandLedgerBuilder

__all__ = [
    "IncrementalCurriculumDemandLedger",
    "IncrementalCurriculumDemandLedgerBuilder",
    "IncrementalDemandLedger",
    "IncrementalDemandLedgerBuilder",
]
