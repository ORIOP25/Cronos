from __future__ import annotations

from datetime import time
from typing import Any

from app import models
from app.scheduler.domain.contracts import DraftBlockSpec
from app.scheduler.domain.validation import TargetHardConstraintValidator
from app.services.scheduler_complete_demand import CompleteDemandLedgerBuilder
from app.services.scheduler_curriculum_validation import validate_curriculum_coverage


class SchedulerTargetValidationError(RuntimeError):
    pass


class SchedulerTargetValidator:
    @classmethod
    def validate(
        cls,
        snapshot: dict[str, Any],
        specs: tuple[DraftBlockSpec, ...],
        *,
        complete: bool,
    ) -> None:
        violations = TargetHardConstraintValidator.validate(snapshot, specs)
        if violations:
            raise SchedulerTargetValidationError(violations[0].message)
        if complete:
            cls._validate_complete(snapshot, specs)

    @staticmethod
    def _validate_complete(snapshot, specs) -> None:
        if any(
            block.change_type != models.ScheduleDraftBlockChangeType.ADDED
            or block.source_active_block_id is not None
            or block.is_recovery_block
            for block in specs
        ):
            raise SchedulerTargetValidationError(
                "A complete first schedule contains repair-only target semantics."
            )
        ledger = CompleteDemandLedgerBuilder().build(snapshot)
        if not ledger.is_complete:
            raise SchedulerTargetValidationError(
                "Complete draft was produced from an incomplete demand ledger."
            )
        items = {(item.class_id, item.subject_id): item for item in ledger.items}
        for block in specs:
            item = items.get((block.class_id, block.subject_id))
            if item is None or item.teacher_id != block.teacher_id:
                raise SchedulerTargetValidationError(
                    "Draft violates class-subject-teacher assignment."
                )
            if block.room_id not in item.eligible_room_ids:
                raise SchedulerTargetValidationError("Draft uses an ineligible room.")
            if block.module_sequence_index is None or block.module_sequence_index not in {
                module.sequence for module in item.modules
            }:
                raise SchedulerTargetValidationError("Draft module sequence is invalid.")
        violations = validate_curriculum_coverage(
            ledger,
            specs,
            slot_start_values={
                row["id"]: str(row.get("start_time", ""))
                for row in snapshot.get("timetable_grid", [])
            },
        )
        if violations:
            raise SchedulerTargetValidationError(violations[0].message)

    @staticmethod
    def _minute(value: str | time) -> int:
        parsed = value if isinstance(value, time) else time.fromisoformat(value)
        return parsed.hour * 60 + parsed.minute
