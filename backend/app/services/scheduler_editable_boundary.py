from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

IMMUTABLE_PAST = "PAST"
IMMUTABLE_EXECUTED = "EXECUTED"
IMMUTABLE_STABILITY_WINDOW = "STABILITY_WINDOW"


@dataclass(frozen=True)
class RepairBlockScope:
    block: dict[str, Any]
    immutable_reason: str | None

    @property
    def is_editable(self) -> bool:
        return self.immutable_reason is None


@dataclass(frozen=True)
class EditableBoundary:
    school_today: date
    editable_start_date: date
    stability_window_days: int
    blocks: tuple[RepairBlockScope, ...]

    @property
    def immutable_blocks(self) -> tuple[dict[str, Any], ...]:
        return tuple(row.block for row in self.blocks if not row.is_editable)

    @property
    def editable_blocks(self) -> tuple[dict[str, Any], ...]:
        return tuple(row.block for row in self.blocks if row.is_editable)


class EditableBoundaryBuilder:
    def build(
        self,
        generation_snapshot: dict[str, Any],
        repair_policy_snapshot: dict[str, Any],
    ) -> EditableBoundary:
        school_today = date.fromisoformat(repair_policy_snapshot["school_today"])
        editable_start = date.fromisoformat(repair_policy_snapshot["editable_start_date"])
        stability_days = int(repair_policy_snapshot["repair_stability_window_days"])
        if stability_days < 0:
            raise ValueError("Repair stability window cannot be negative.")
        if editable_start < school_today:
            raise ValueError("Editable boundary cannot precede the school-local date.")

        scoped = []
        for block in generation_snapshot.get("active_schedule", []):
            block_date = date.fromisoformat(block["date"])
            log_status = self._enum_value(block.get("lesson_log_status"))
            reason = None
            if block_date < school_today:
                reason = IMMUTABLE_PAST
            elif log_status in {"COMPLETED", "OCCURRENCE"}:
                reason = IMMUTABLE_EXECUTED
            elif block_date < editable_start:
                reason = IMMUTABLE_STABILITY_WINDOW
            scoped.append(RepairBlockScope(block=block, immutable_reason=reason))
        return EditableBoundary(
            school_today=school_today,
            editable_start_date=editable_start,
            stability_window_days=stability_days,
            blocks=tuple(
                sorted(
                    scoped,
                    key=lambda row: (row.block["date"], row.block["id"]),
                )
            ),
        )

    @staticmethod
    def _enum_value(value: Any) -> str | None:
        if value is None:
            return None
        return str(getattr(value, "value", value))
