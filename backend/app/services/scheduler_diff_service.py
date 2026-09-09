from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models

if TYPE_CHECKING:
    from app.services.scheduler_job_runtime import (
        DraftBlockSpec,
        GenerationExecutionContext,
    )


@dataclass(frozen=True)
class DraftDiff:
    id: int
    change_type: str
    impact_scope: str
    class_id: int
    subject_id: int
    teacher_id: int
    before_active_block_id: int | None
    after_draft_block_id: int | None
    before_snapshot: dict[str, Any] | None
    after_snapshot: dict[str, Any] | None
    reason_code: str | None
    reason_message: str | None
    recovery_link_impact: dict[str, Any] | None


class SchedulerDiffService:
    def __init__(self, db: AsyncSession):
        self._db = db

    def build_entries(
        self,
        context: GenerationExecutionContext,
        draft: models.ScheduleDraft,
        specs: tuple[DraftBlockSpec, ...],
        blocks: list[models.ScheduleDraftBlock],
    ) -> list[models.ScheduleDiffEntry]:
        active = {
            row["id"]: row
            for row in context.immutable_snapshot["generation_input"].get("active_schedule", [])
        }
        target_sources = {
            spec.source_active_block_id for spec in specs if spec.source_active_block_id is not None
        }
        entries: list[models.ScheduleDiffEntry] = []
        for spec, block in zip(specs, blocks, strict=True):
            if spec.change_type == models.ScheduleDraftBlockChangeType.UNCHANGED:
                continue
            before = active.get(spec.source_active_block_id)
            diff_type = (
                models.ScheduleDiffChangeType.ADDED
                if before is None
                else models.ScheduleDiffChangeType.MOVED
                if spec.change_type == models.ScheduleDraftBlockChangeType.MOVED
                else models.ScheduleDiffChangeType.CHANGED
            )
            entries.append(
                models.ScheduleDiffEntry(
                    organization_id=context.organization_id,
                    school_year_id=context.school_year_id,
                    generation_job_id=context.job_id,
                    draft_id=draft.id,
                    class_id=spec.class_id,
                    subject_id=spec.subject_id,
                    teacher_id=spec.teacher_id,
                    before_active_block_id=spec.source_active_block_id,
                    after_draft_block_id=block.id,
                    before_date=None if before is None else self._date(before["date"]),
                    before_timeslot_id=None if before is None else before["timeslot_id"],
                    before_room_id=None if before is None else before["room_id"],
                    after_date=spec.date,
                    after_timeslot_id=spec.timeslot_id,
                    after_room_id=spec.room_id,
                    before_snapshot_json=(
                        None if before is None else self._active_snapshot(before)
                    ),
                    after_snapshot_json=self._draft_snapshot(spec),
                    change_type=diff_type,
                    impact_scope=models.ScheduleDiffScope.AFFECTED,
                    reason_code=spec.reason_code,
                    reason_message=self._reason_message(spec),
                    recovery_link_impact_json=self._recovery_impact(spec),
                )
            )
        for source_id, before in sorted(active.items()):
            if source_id in target_sources:
                continue
            entries.append(
                models.ScheduleDiffEntry(
                    organization_id=context.organization_id,
                    school_year_id=context.school_year_id,
                    generation_job_id=context.job_id,
                    draft_id=draft.id,
                    class_id=before["class_id"],
                    subject_id=before["subject_id"],
                    teacher_id=before["teacher_id"],
                    before_active_block_id=source_id,
                    after_draft_block_id=None,
                    before_date=self._date(before["date"]),
                    before_timeslot_id=before["timeslot_id"],
                    before_room_id=before["room_id"],
                    before_snapshot_json=self._active_snapshot(before),
                    after_snapshot_json=None,
                    change_type=models.ScheduleDiffChangeType.REMOVED,
                    impact_scope=models.ScheduleDiffScope.AFFECTED,
                    reason_code="ABSENT_FROM_TARGET",
                    reason_message="The active block is absent from the approved target state.",
                    recovery_link_impact_json=(
                        {"planned_recovery_removed": True}
                        if before.get("is_recovery_block")
                        else None
                    ),
                )
            )
        return entries

    async def list_diff(
        self,
        organization_id: int,
        draft_id: int,
    ) -> tuple[DraftDiff, ...] | None:
        draft = await self._db.scalar(
            select(models.ScheduleDraft).where(
                models.ScheduleDraft.id == draft_id,
                models.ScheduleDraft.organization_id == organization_id,
            )
        )
        if draft is None:
            return None
        rows = (
            await self._db.scalars(
                select(models.ScheduleDiffEntry)
                .where(
                    models.ScheduleDiffEntry.organization_id == organization_id,
                    models.ScheduleDiffEntry.school_year_id == draft.school_year_id,
                    models.ScheduleDiffEntry.draft_id == draft_id,
                )
                .order_by(models.ScheduleDiffEntry.id)
            )
        ).all()
        return tuple(
            DraftDiff(
                id=row.id,
                change_type=row.change_type.value,
                impact_scope=row.impact_scope.value,
                class_id=row.class_id,
                subject_id=row.subject_id,
                teacher_id=row.teacher_id,
                before_active_block_id=row.before_active_block_id,
                after_draft_block_id=row.after_draft_block_id,
                before_snapshot=row.before_snapshot_json,
                after_snapshot=row.after_snapshot_json,
                reason_code=row.reason_code,
                reason_message=row.reason_message,
                recovery_link_impact=row.recovery_link_impact_json,
            )
            for row in rows
        )

    @staticmethod
    def _active_snapshot(row: dict[str, Any]) -> dict[str, Any]:
        return {
            key: row.get(key)
            for key in (
                "id",
                "stable_block_key",
                "class_id",
                "subject_id",
                "teacher_id",
                "room_id",
                "date",
                "timeslot_id",
                "duration_minutes",
                "is_recovery_block",
                "recovery_source_occurrence_id",
                "recovery_source_occurrence_revision",
            )
        }

    @staticmethod
    def _draft_snapshot(spec: DraftBlockSpec) -> dict[str, Any]:
        return {
            "stable_block_key": spec.stable_block_key,
            "class_id": spec.class_id,
            "subject_id": spec.subject_id,
            "teacher_id": spec.teacher_id,
            "room_id": spec.room_id,
            "date": spec.date.isoformat(),
            "timeslot_id": spec.timeslot_id,
            "duration_minutes": spec.duration_minutes,
            "is_recovery_block": spec.is_recovery_block,
            "recovery_source_occurrence_id": spec.recovery_source_occurrence_id,
            "recovery_source_occurrence_revision": spec.recovery_source_occurrence_revision,
        }

    @staticmethod
    def _reason_message(spec: DraftBlockSpec) -> str:
        if spec.reason_code == "NEW_CURRICULUM_DEMAND":
            return "A new curriculum demand block was added."
        return {
            models.ScheduleDraftBlockChangeType.ADDED: "A new target block was added.",
            models.ScheduleDraftBlockChangeType.MOVED: "The active block was moved.",
            models.ScheduleDraftBlockChangeType.ROOM_ONLY: "The room was changed.",
            models.ScheduleDraftBlockChangeType.REPLACED: "The assigned resource was replaced.",
        }[spec.change_type]

    @staticmethod
    def _recovery_impact(spec: DraftBlockSpec) -> dict[str, Any] | None:
        if not spec.is_recovery_block:
            return None
        return {
            "occurrence_id": spec.recovery_source_occurrence_id,
            "occurrence_revision": spec.recovery_source_occurrence_revision,
            "planned_recovery_minutes": spec.duration_minutes,
        }

    @staticmethod
    def _date(value):
        return value if isinstance(value, date) else date.fromisoformat(value)
