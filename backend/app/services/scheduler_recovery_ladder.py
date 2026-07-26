from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.services.scheduler_editable_boundary import EditableBoundary


class RecoveryLevel(StrEnum):
    APPEND_ONLY = "APPEND_ONLY_RECOVERY"
    AFFECTED_CLASS = "AFFECTED_CLASS_RECOVERY"
    AFFECTED_TEACHER_CLASS = "AFFECTED_TEACHER_CLASS_RECOVERY"
    CONTROLLED_SCHOOL_WIDE = "CONTROLLED_SCHOOL_WIDE_REPAIR"
    DEADLINE_RESCUE = "DEADLINE_RESCUE"
    IMPOSSIBLE = "IMPOSSIBLE_WITH_EXPLANATION"


@dataclass(frozen=True)
class RecoveryScope:
    level: RecoveryLevel
    fixed_blocks: tuple[dict[str, Any], ...]
    movable_blocks: tuple[dict[str, Any], ...]
    affected_class_ids: tuple[int, ...]
    affected_teacher_ids: tuple[int, ...]
    allow_workload_override: bool
    description: str


class RecoveryEscalationLadder:
    def scopes(
        self,
        boundary: EditableBoundary,
        debt_snapshot: dict[str, Any],
    ) -> tuple[RecoveryScope, ...]:
        debt_items = [
            row
            for row in debt_snapshot.get("items", [])
            if int(row.get("unresolved_debt_minutes", 0)) > 0
        ]
        affected_classes = tuple(
            sorted({row["class_id"] for row in debt_items if row.get("class_id") is not None})
        )
        affected_teachers = tuple(
            sorted({row["teacher_id"] for row in debt_items if row.get("teacher_id") is not None})
        )
        immutable = list(boundary.immutable_blocks)
        editable = list(boundary.editable_blocks)

        def scope(
            level: RecoveryLevel,
            movable_predicate,
            description: str,
            *,
            overload: bool = False,
        ) -> RecoveryScope:
            movable = [row for row in editable if movable_predicate(row)]
            movable_ids = {row["id"] for row in movable}
            fixed = immutable + [row for row in editable if row["id"] not in movable_ids]
            return RecoveryScope(
                level=level,
                fixed_blocks=tuple(sorted(fixed, key=lambda row: (row["date"], row["id"]))),
                movable_blocks=tuple(sorted(movable, key=lambda row: (row["date"], row["id"]))),
                affected_class_ids=affected_classes,
                affected_teacher_ids=affected_teachers,
                allow_workload_override=overload,
                description=description,
            )

        scopes = [
            scope(
                RecoveryLevel.APPEND_ONLY,
                lambda _row: False,
                "Add recovery blocks without moving the published schedule.",
            ),
            scope(
                RecoveryLevel.AFFECTED_CLASS,
                lambda row: row["class_id"] in affected_classes,
                "Reorganize editable blocks belonging to affected classes.",
            ),
            scope(
                RecoveryLevel.AFFECTED_TEACHER_CLASS,
                lambda row: (
                    row["class_id"] in affected_classes or row["teacher_id"] in affected_teachers
                ),
                "Reorganize editable blocks tied to affected classes or teachers.",
            ),
            scope(
                RecoveryLevel.CONTROLLED_SCHOOL_WIDE,
                lambda _row: True,
                "Conservatively rebalance all editable future blocks.",
            ),
            scope(
                RecoveryLevel.DEADLINE_RESCUE,
                lambda _row: True,
                "Prioritize mandatory recovery before the hard end over workload comfort.",
                overload=True,
            ),
        ]
        scopes.append(
            RecoveryScope(
                level=RecoveryLevel.IMPOSSIBLE,
                fixed_blocks=tuple(boundary.immutable_blocks),
                movable_blocks=(),
                affected_class_ids=affected_classes,
                affected_teacher_ids=affected_teachers,
                allow_workload_override=False,
                description="No valid recovery scope can resolve all explicit debt.",
            )
        )
        return tuple(scopes)
