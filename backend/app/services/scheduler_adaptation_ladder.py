from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any

from app.services.scheduler_editable_boundary import EditableBoundary


class AdaptationLevel(StrEnum):
    SAME_TIME_RESOURCE = "SAME_TIME_RESOURCE_ADAPTATION"
    AFFECTED_RESOURCE_REFIT = "AFFECTED_RESOURCE_CLASS_TEACHER_REFIT"
    CALENDAR_GRID_REFLOW = "CALENDAR_GRID_REFLOW"
    CONTROLLED_SCHOOL_WIDE = "CONTROLLED_SCHOOL_WIDE_ADAPTATION"
    IMPOSSIBLE = "IMPOSSIBLE_WITH_EXPLANATION"


@dataclass(frozen=True)
class ChangedBlockImpact:
    block: dict[str, Any]
    reasons: tuple[str, ...]
    category: str
    immutable: bool


@dataclass(frozen=True)
class SchedulerChangeImpact:
    affected: tuple[ChangedBlockImpact, ...]

    @property
    def immutable_invalid(self) -> tuple[ChangedBlockImpact, ...]:
        return tuple(row for row in self.affected if row.immutable)


@dataclass(frozen=True)
class AdaptationScope:
    level: AdaptationLevel
    fixed_blocks: tuple[dict[str, Any], ...]
    adaptable_blocks: tuple[dict[str, Any], ...]
    keep_date_and_time: bool
    description: str


class SchedulerChangeImpactAnalyzer:
    def analyze(
        self,
        snapshot: dict[str, Any],
        boundary: EditableBoundary,
    ) -> SchedulerChangeImpact:
        classes = {row["id"]: row for row in snapshot.get("classes", [])}
        subjects = {row["id"]: row for row in snapshot.get("subjects", [])}
        teachers = {row["id"] for row in snapshot.get("teachers", [])}
        rooms = {row["id"]: row for row in snapshot.get("rooms", [])}
        assignments = {
            (row["class_id"], row["subject_id"]): row.get("teacher_id")
            for row in snapshot.get("class_subject_requirements", [])
        }
        qualifications = {
            (row["teacher_id"], row["subject_id"])
            for row in snapshot.get("teacher_subject_eligibility", [])
        }
        grid = {
            row["id"]: row for row in snapshot.get("timetable_grid", [])
        }
        impossible = {
            (row["teacher_id"], row["timeslot_id"])
            for row in snapshot.get("teacher_availability", [])
            if row.get("score") == -1
        }
        blocked_dates = self._blocked_dates(snapshot.get("calendar_events", []))
        hard_end = date.fromisoformat(snapshot["hard_end_date"])
        scoped = {row.block["id"]: row for row in boundary.blocks}
        impacts = []
        for block in snapshot.get("active_schedule", []):
            reasons: list[str] = []
            category = "RESOURCE"
            block_date = date.fromisoformat(block["date"])
            class_row = classes.get(block["class_id"])
            subject_row = subjects.get(block["subject_id"])
            room_row = rooms.get(block["room_id"])
            if class_row is None or subject_row is None:
                reasons.append("Class or subject is no longer schedulable.")
                category = "ASSIGNMENT"
            if assignments.get((block["class_id"], block["subject_id"])) != block["teacher_id"]:
                reasons.append("Class-subject teacher assignment changed.")
                category = "ASSIGNMENT"
            if block["teacher_id"] not in teachers or (
                qualifications
                and (block["teacher_id"], block["subject_id"]) not in qualifications
            ):
                reasons.append("Assigned teacher is no longer eligible.")
            if (block["teacher_id"], block["timeslot_id"]) in impossible:
                reasons.append("Teacher availability is now impossible at this time.")
            if room_row is None:
                reasons.append("Assigned room no longer exists.")
            elif class_row is not None and subject_row is not None and (
                room_row.get("capacity", 0) < class_row["size"]
                or self._value(room_row.get("type"))
                != self._value(subject_row.get("required_room_type"))
            ):
                reasons.append("Assigned room is no longer compatible.")
            slot = grid.get(block["timeslot_id"])
            if (
                block_date > hard_end
                or block_date in blocked_dates
                or slot is None
                or slot["day_of_week"] != block_date.weekday()
            ):
                reasons.append("Block no longer fits the calendar or timetable grid.")
                category = "CALENDAR_GRID"
            if reasons:
                scope = scoped.get(block["id"])
                impacts.append(
                    ChangedBlockImpact(
                        block=block,
                        reasons=tuple(reasons),
                        category=category,
                        immutable=scope is None or not scope.is_editable,
                    )
                )
        return SchedulerChangeImpact(
            affected=tuple(sorted(impacts, key=lambda row: row.block["id"]))
        )

    @staticmethod
    def _blocked_dates(rows: list[dict[str, Any]]) -> set[date]:
        blocked = set()
        for row in rows:
            current = date.fromisoformat(row["start_date"])
            end = date.fromisoformat(row["end_date"])
            while current <= end:
                blocked.add(current)
                current = current.fromordinal(current.toordinal() + 1)
        return blocked

    @staticmethod
    def _value(value: Any) -> str:
        return str(getattr(value, "value", value))


class SchedulerChangeAdaptationLadder:
    def scopes(
        self,
        boundary: EditableBoundary,
        impact: SchedulerChangeImpact,
    ) -> tuple[AdaptationScope, ...]:
        editable = list(boundary.editable_blocks)
        immutable = list(boundary.immutable_blocks)
        affected = [row.block for row in impact.affected if not row.immutable]
        resource_affected = {
            row.block["id"]
            for row in impact.affected
            if not row.immutable and row.category == "RESOURCE"
        }
        all_affected = {row["id"] for row in affected}
        related_classes = {row["class_id"] for row in affected}
        related_teachers = {row["teacher_id"] for row in affected}

        def make(
            level: AdaptationLevel,
            selected: list[dict[str, Any]],
            keep_time: bool,
            description: str,
        ) -> AdaptationScope:
            selected_ids = {row["id"] for row in selected}
            fixed = immutable + [row for row in editable if row["id"] not in selected_ids]
            return AdaptationScope(
                level=level,
                fixed_blocks=tuple(sorted(fixed, key=lambda row: (row["date"], row["id"]))),
                adaptable_blocks=tuple(sorted(selected, key=lambda row: (row["date"], row["id"]))),
                keep_date_and_time=keep_time,
                description=description,
            )

        return (
            make(
                AdaptationLevel.SAME_TIME_RESOURCE,
                [row for row in editable if row["id"] in resource_affected],
                True,
                "Replace incompatible resources while preserving dates and times.",
            ),
            make(
                AdaptationLevel.AFFECTED_RESOURCE_REFIT,
                [
                    row
                    for row in editable
                    if row["id"] in all_affected
                    or row["class_id"] in related_classes
                    or row["teacher_id"] in related_teachers
                ],
                False,
                "Refit blocks related to affected resources, classes, or teachers.",
            ),
            make(
                AdaptationLevel.CALENDAR_GRID_REFLOW,
                [row for row in editable if row["id"] in all_affected],
                False,
                "Reflow affected blocks across the latest calendar and timetable grid.",
            ),
            make(
                AdaptationLevel.CONTROLLED_SCHOOL_WIDE,
                editable,
                False,
                "Conservatively rebalance all editable future blocks.",
            ),
            AdaptationScope(
                level=AdaptationLevel.IMPOSSIBLE,
                fixed_blocks=tuple(boundary.immutable_blocks),
                adaptable_blocks=(),
                keep_date_and_time=False,
                description="No valid future adaptation exists under current conditions.",
            ),
        )
