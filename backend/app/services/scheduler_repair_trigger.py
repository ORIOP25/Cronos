from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app import models


@dataclass(frozen=True)
class RepairTriggerClassification:
    trigger_type: models.ScheduleGenerationTrigger
    unresolved_debt_minutes: int
    scheduler_state_version: int
    approved_scheduler_state_version: int
    use_recovery_ladder: bool
    use_adaptation_ladder: bool
    summary: str


class RepairTriggerClassifier:
    def classify(
        self,
        generation_snapshot: dict[str, Any],
        debt_snapshot: dict[str, Any] | None,
        *,
        declared_trigger: models.ScheduleGenerationTrigger | None = None,
    ) -> RepairTriggerClassification:
        unresolved = sum(
            max(0, int(row.get("unresolved_debt_minutes", 0)))
            for row in (debt_snapshot or {}).get("items", [])
        )
        state_version = int(generation_snapshot["scheduler_state_version"])
        approved_value = generation_snapshot.get("approved_scheduler_state_version")
        if approved_value is None:
            raise ValueError("Published repair requires an approved scheduler state version.")
        approved_version = int(approved_value)
        has_change = state_version > approved_version
        has_debt = unresolved > 0
        if has_debt and has_change:
            trigger = models.ScheduleGenerationTrigger.MIXED
            summary = (
                "Adaptive repair is responding to unresolved explicit debt and "
                "scheduler-relevant changes."
            )
        elif has_debt:
            trigger = models.ScheduleGenerationTrigger.EXPLICIT_DEBT
            summary = "Adaptive repair is responding to unresolved explicit debt."
        elif has_change:
            trigger = models.ScheduleGenerationTrigger.SCHEDULER_CHANGE
            summary = "Adaptive repair is responding to scheduler-relevant changes."
        else:
            raise ValueError("No unresolved explicit debt or scheduler-relevant change exists.")
        if declared_trigger is not None and declared_trigger != trigger:
            raise ValueError(
                f"Declared repair trigger {declared_trigger.value} does not match {trigger.value}."
            )
        return RepairTriggerClassification(
            trigger_type=trigger,
            unresolved_debt_minutes=unresolved,
            scheduler_state_version=state_version,
            approved_scheduler_state_version=approved_version,
            use_recovery_ladder=has_debt,
            use_adaptation_ladder=has_change,
            summary=summary,
        )
