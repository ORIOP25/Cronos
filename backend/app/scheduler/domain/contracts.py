from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True)
class DraftBlockSpec:
    stable_block_key: str
    class_id: int
    subject_id: int
    teacher_id: int
    room_id: int
    room_type_id: Any
    date: date
    timeslot_id: int
    duration_minutes: int
    change_type: Any
    source_active_block_id: int | None = None
    module_sequence_index: int | None = None
    is_recovery_block: bool = False
    recovery_source_occurrence_id: int | None = None
    recovery_source_occurrence_revision: int | None = None
    reason_code: str | None = None


@dataclass(frozen=True)
class ValidatedGenerationResult:
    result_category: Any
    projected_completion_date: date
    hard_end_date: date
    blocks: tuple[DraftBlockSpec, ...]
    summary: dict[str, Any]
    recovery_escalation_level: str | None = None
    adaptation_level: str | None = None
    partial_recovery_blocker_type: str | None = None
    main_blocker_message: str | None = None
    recommended_actions: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NoValidGenerationOutput:
    blockers: tuple[str, ...]
    metrics: dict[str, Any] = field(default_factory=dict)
