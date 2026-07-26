from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class BlockDisruption:
    stable_block_key: str
    change_type: str
    stakeholder_scope: str
    score: float


@dataclass(frozen=True)
class DisruptionScore:
    total: float
    changed_blocks: int
    affected_classes: int
    affected_teachers: int
    room_only_changes: int
    date_time_changes: int
    ripple_blocks: int
    details: tuple[BlockDisruption, ...]

    def to_metrics(self) -> dict[str, int | float]:
        return {
            "disruption_score": self.total,
            "changed_blocks": self.changed_blocks,
            "affected_classes": self.affected_classes,
            "affected_teachers": self.affected_teachers,
            "room_only_changes": self.room_only_changes,
            "date_time_changes": self.date_time_changes,
            "ripple_blocks": self.ripple_blocks,
        }


class DisruptionScorer:
    BASE = {
        "UNCHANGED": 0.0,
        "ROOM_ONLY": 1.0,
        "TEACHER_CHANGE": 4.0,
        "TIME_CHANGE": 6.0,
        "DATE_CHANGE": 8.0,
        "REMOVED": 10.0,
        "ADDED": 2.0,
    }
    SCOPE_MULTIPLIER = {"AFFECTED": 1.0, "RELATED": 1.75, "UNRELATED": 3.0}

    def score(
        self,
        original_blocks: list[dict[str, Any]] | tuple[dict[str, Any], ...],
        proposed_blocks: list[dict[str, Any]] | tuple[dict[str, Any], ...],
        *,
        school_today: date,
        affected_class_ids: set[int],
        affected_teacher_ids: set[int],
    ) -> DisruptionScore:
        original = {row["stable_block_key"]: row for row in original_blocks}
        proposed = {row["stable_block_key"]: row for row in proposed_blocks}
        details = []
        changed_classes: set[int] = set()
        changed_teachers: set[int] = set()
        room_only = 0
        date_time = 0
        ripple = 0
        for key in sorted(original.keys() | proposed.keys()):
            before = original.get(key)
            after = proposed.get(key)
            change = self._change_type(before, after)
            row = after or before
            scope = self._scope(row, affected_class_ids, affected_teacher_ids)
            urgency = self._urgency(before, after, school_today)
            score = self.BASE[change] * self.SCOPE_MULTIPLIER[scope] * urgency
            if change != "UNCHANGED":
                changed_classes.add(row["class_id"])
                changed_teachers.add(row["teacher_id"])
                if scope != "AFFECTED":
                    ripple += 1
            if change == "ROOM_ONLY":
                room_only += 1
            if change in {"TIME_CHANGE", "DATE_CHANGE"}:
                date_time += 1
            details.append(
                BlockDisruption(
                    stable_block_key=key,
                    change_type=change,
                    stakeholder_scope=scope,
                    score=round(score, 3),
                )
            )
        changed = [row for row in details if row.change_type != "UNCHANGED"]
        return DisruptionScore(
            total=round(sum(row.score for row in changed), 3),
            changed_blocks=len(changed),
            affected_classes=len(changed_classes),
            affected_teachers=len(changed_teachers),
            room_only_changes=room_only,
            date_time_changes=date_time,
            ripple_blocks=ripple,
            details=tuple(details),
        )

    @staticmethod
    def _change_type(before: dict | None, after: dict | None) -> str:
        if before is None:
            return "ADDED"
        if after is None:
            return "REMOVED"
        if before["date"] != after["date"]:
            return "DATE_CHANGE"
        if before["timeslot_id"] != after["timeslot_id"]:
            return "TIME_CHANGE"
        if before["teacher_id"] != after["teacher_id"]:
            return "TEACHER_CHANGE"
        if before["room_id"] != after["room_id"]:
            return "ROOM_ONLY"
        return "UNCHANGED"

    @staticmethod
    def _scope(
        row: dict[str, Any],
        affected_classes: set[int],
        affected_teachers: set[int],
    ) -> str:
        if row["class_id"] in affected_classes or row["teacher_id"] in affected_teachers:
            return "AFFECTED"
        if row.get("is_recovery_block"):
            return "RELATED"
        return "UNRELATED"

    @staticmethod
    def _urgency(before: dict | None, after: dict | None, school_today: date) -> float:
        dates = [date.fromisoformat(row["date"]) for row in (before, after) if row is not None]
        days_away = max(0, min((value - school_today).days for value in dates))
        if days_away <= 7:
            return 2.0
        if days_away <= 28:
            return 1.5
        return 1.0
