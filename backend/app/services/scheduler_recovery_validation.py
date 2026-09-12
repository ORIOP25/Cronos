"""Pure identity checks for explicit recovery targets."""

from __future__ import annotations

from collections.abc import Mapping, Set
from typing import Any

from app.scheduler.domain.contracts import DraftBlockSpec


def validate_recovery_identity(
    block: DraftBlockSpec,
    debt_item: Mapping[str, Any],
    assignments: Mapping[tuple[int, int], int | None],
    qualifications: Set[tuple[int, int]],
    *,
    requested_minutes: int | None = None,
) -> tuple[str, ...]:
    """Return violations binding a recovery block to its debt source identity."""

    violations: list[str] = []
    if block.recovery_source_occurrence_id != debt_item.get(
        "occurrence_id"
    ) or block.recovery_source_occurrence_revision != debt_item.get("occurrence_revision"):
        violations.append("Recovery block does not match its debt occurrence revision.")
    if block.class_id != debt_item.get("class_id"):
        violations.append("Recovery block class does not match its debt source class.")
    if block.subject_id != debt_item.get("subject_id"):
        violations.append("Recovery block subject does not match its debt source subject.")
    if assignments.get((block.class_id, block.subject_id)) != block.teacher_id:
        violations.append("Recovery teacher is not the current class-subject assignment.")
    if (block.teacher_id, block.subject_id) not in qualifications:
        violations.append("Recovery teacher is not eligible for the target subject.")
    minutes = block.duration_minutes if requested_minutes is None else requested_minutes
    if minutes <= 0 or minutes > int(debt_item.get("unresolved_debt_minutes", 0)):
        violations.append("Recovery minutes exceed the unresolved debt ceiling.")
    return tuple(violations)


__all__ = ["validate_recovery_identity"]
