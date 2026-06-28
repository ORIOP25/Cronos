from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.services.scheduler_debt_service import SchedulerDebtService


class SchedulerRecoveryError(RuntimeError):
    pass


class RecoveryDebtUnavailableError(SchedulerRecoveryError):
    pass


class RecoveryLinkIntegrityError(SchedulerRecoveryError):
    pass


class SchedulerRecoveryService:
    def __init__(self, db: AsyncSession):
        self._db = db
        self._debt = SchedulerDebtService(db)

    async def plan_draft_recovery(
        self,
        organization_id: int,
        school_year_id: int,
        draft_block_id: int,
        *,
        recovery_minutes: int | None = None,
    ) -> models.PlannedRecoveryLink:
        block = await self._db.scalar(
            select(models.ScheduleDraftBlock)
            .join(models.ScheduleDraft, models.ScheduleDraft.id == models.ScheduleDraftBlock.draft_id)
            .where(
                models.ScheduleDraftBlock.id == draft_block_id,
                models.ScheduleDraftBlock.organization_id == organization_id,
                models.ScheduleDraftBlock.school_year_id == school_year_id,
                models.ScheduleDraftBlock.is_recovery_block.is_(True),
                models.ScheduleDraft.organization_id == organization_id,
                models.ScheduleDraft.school_year_id == school_year_id,
                models.ScheduleDraft.draft_state == models.ScheduleDraftState.PENDING,
                models.ScheduleDraft.strategy == models.ScheduleGenerationStrategy.ADAPTIVE_REPAIR,
            )
            .with_for_update()
        )
        if block is None:
            raise RecoveryLinkIntegrityError(
                "Recovery planning requires a pending Adaptive Repair recovery block."
            )
        if (
            block.recovery_source_occurrence_id is None
            or block.recovery_source_occurrence_revision is None
        ):
            raise RecoveryLinkIntegrityError("Recovery block has no debt source revision.")

        existing = await self._db.scalar(
            select(models.PlannedRecoveryLink).where(
                models.PlannedRecoveryLink.organization_id == organization_id,
                models.PlannedRecoveryLink.school_year_id == school_year_id,
                models.PlannedRecoveryLink.planned_draft_block_id == block.id,
            )
        )
        requested_minutes = (
            block.duration_minutes if recovery_minutes is None else recovery_minutes
        )
        if requested_minutes <= 0 or requested_minutes > block.duration_minutes:
            raise RecoveryLinkIntegrityError(
                "Recovery minutes must be positive and cannot exceed the draft block duration."
            )
        if existing is not None:
            if (
                existing.debt_occurrence_id == block.recovery_source_occurrence_id
                and existing.debt_occurrence_revision
                == block.recovery_source_occurrence_revision
                and existing.planned_recovery_minutes == requested_minutes
            ):
                return existing
            raise RecoveryLinkIntegrityError(
                "Draft recovery block is already linked to different debt evidence."
            )

        ledger = await self._debt.active_debt_ledger(organization_id, school_year_id)
        debt_entry = next(
            (
                entry
                for entry in ledger.entries
                if entry.occurrence_id == block.recovery_source_occurrence_id
                and entry.occurrence_revision
                == block.recovery_source_occurrence_revision
            ),
            None,
        )
        if debt_entry is None:
            raise RecoveryDebtUnavailableError(
                "The referenced debt is no longer unresolved at this revision."
            )

        pending_reserved = await self._db.scalars(
            select(models.PlannedRecoveryLink).where(
                models.PlannedRecoveryLink.organization_id == organization_id,
                models.PlannedRecoveryLink.school_year_id == school_year_id,
                models.PlannedRecoveryLink.debt_occurrence_id == debt_entry.occurrence_id,
                models.PlannedRecoveryLink.debt_occurrence_revision
                == debt_entry.occurrence_revision,
                models.PlannedRecoveryLink.status
                == models.PlannedRecoveryLinkStatus.PLANNED,
                models.PlannedRecoveryLink.planned_active_block_id.is_(None),
                models.PlannedRecoveryLink.planned_draft_block_id.is_not(None),
            )
        )
        reserved_minutes = sum(link.planned_recovery_minutes for link in pending_reserved)
        available_minutes = max(0, debt_entry.remaining_minutes - reserved_minutes)
        if requested_minutes > available_minutes:
            raise RecoveryDebtUnavailableError(
                f"Only {available_minutes} unresolved debt minutes remain available."
            )

        link = models.PlannedRecoveryLink(
            organization_id=organization_id,
            school_year_id=school_year_id,
            debt_occurrence_id=debt_entry.occurrence_id,
            debt_occurrence_revision=debt_entry.occurrence_revision,
            planned_draft_block_id=block.id,
            planned_recovery_minutes=requested_minutes,
            class_id=block.class_id,
            subject_id=block.subject_id,
            teacher_id=block.teacher_id,
            status=models.PlannedRecoveryLinkStatus.PLANNED,
        )
        self._db.add(link)
        await self._db.flush()
        return link

    async def reconcile_approved_recovery_links(
        self,
        organization_id: int,
        school_year_id: int,
        draft_id: int,
        active_block_by_draft_block: dict[int, int],
    ) -> tuple[int, int]:
        links = (
            await self._db.scalars(
                select(models.PlannedRecoveryLink)
                .join(
                    models.ScheduleDraftBlock,
                    models.ScheduleDraftBlock.id
                    == models.PlannedRecoveryLink.planned_draft_block_id,
                )
                .where(
                    models.PlannedRecoveryLink.organization_id == organization_id,
                    models.PlannedRecoveryLink.school_year_id == school_year_id,
                    models.ScheduleDraftBlock.organization_id == organization_id,
                    models.ScheduleDraftBlock.school_year_id == school_year_id,
                    models.ScheduleDraftBlock.draft_id == draft_id,
                    models.PlannedRecoveryLink.status
                    == models.PlannedRecoveryLinkStatus.PLANNED,
                )
                .with_for_update()
            )
        ).all()
        activated = 0
        canceled = 0
        for link in links:
            active_block_id = active_block_by_draft_block.get(link.planned_draft_block_id)
            if active_block_id is None:
                link.status = models.PlannedRecoveryLinkStatus.CANCELED
                canceled += 1
                continue
            active_block = await self._db.scalar(
                select(models.ActiveScheduleBlock).where(
                    models.ActiveScheduleBlock.id == active_block_id,
                    models.ActiveScheduleBlock.organization_id == organization_id,
                    models.ActiveScheduleBlock.school_year_id == school_year_id,
                    models.ActiveScheduleBlock.source_draft_block_id
                    == link.planned_draft_block_id,
                    models.ActiveScheduleBlock.is_recovery_block.is_(True),
                    models.ActiveScheduleBlock.status
                    == models.ActiveScheduleBlockStatus.ACTIVE,
                )
            )
            if active_block is None:
                raise RecoveryLinkIntegrityError(
                    "Approved recovery target is not the matching active recovery block."
                )
            link.planned_active_block_id = active_block.id
            link.planned_draft_block_id = None
            activated += 1
        await self._db.flush()
        return activated, canceled

    async def cancel_draft_recovery_links(
        self,
        organization_id: int,
        school_year_id: int,
        draft_id: int,
    ) -> int:
        links = (
            await self._db.scalars(
                select(models.PlannedRecoveryLink)
                .join(
                    models.ScheduleDraftBlock,
                    models.ScheduleDraftBlock.id
                    == models.PlannedRecoveryLink.planned_draft_block_id,
                )
                .where(
                    models.PlannedRecoveryLink.organization_id == organization_id,
                    models.PlannedRecoveryLink.school_year_id == school_year_id,
                    models.ScheduleDraftBlock.organization_id == organization_id,
                    models.ScheduleDraftBlock.school_year_id == school_year_id,
                    models.ScheduleDraftBlock.draft_id == draft_id,
                    models.PlannedRecoveryLink.status
                    == models.PlannedRecoveryLinkStatus.PLANNED,
                    models.PlannedRecoveryLink.planned_active_block_id.is_(None),
                )
                .with_for_update()
            )
        ).all()
        for link in links:
            link.status = models.PlannedRecoveryLinkStatus.CANCELED
        await self._db.flush()
        return len(links)

    async def reconcile_active_recovery_links(
        self,
        organization_id: int,
        school_year_id: int,
        replacements: dict[int, int],
        removed_active_block_ids: set[int],
    ) -> tuple[int, int]:
        source_ids = set(replacements) | removed_active_block_ids
        if not source_ids:
            return 0, 0
        links = (
            await self._db.scalars(
                select(models.PlannedRecoveryLink)
                .where(
                    models.PlannedRecoveryLink.organization_id == organization_id,
                    models.PlannedRecoveryLink.school_year_id == school_year_id,
                    models.PlannedRecoveryLink.planned_active_block_id.in_(source_ids),
                )
                .with_for_update()
            )
        ).all()
        transferred = 0
        canceled = 0
        for link in links:
            source_id = link.planned_active_block_id
            replacement_id = replacements.get(source_id)
            if replacement_id is not None:
                if link.status == models.PlannedRecoveryLinkStatus.DELIVERED:
                    raise RecoveryLinkIntegrityError(
                        "Delivered recovery evidence cannot move to another active block."
                    )
                link.planned_active_block_id = replacement_id
                transferred += 1
            elif source_id in removed_active_block_ids:
                if link.status == models.PlannedRecoveryLinkStatus.DELIVERED:
                    raise RecoveryLinkIntegrityError(
                        "A delivered recovery block cannot be removed from the active schedule."
                    )
                link.status = models.PlannedRecoveryLinkStatus.CANCELED
                canceled += 1
        await self._db.flush()
        return transferred, canceled

    async def cancel_active_recovery_links(
        self,
        organization_id: int,
        school_year_id: int,
        active_block_ids: set[int],
    ) -> int:
        if not active_block_ids:
            return 0
        links = (
            await self._db.scalars(
                select(models.PlannedRecoveryLink)
                .where(
                    models.PlannedRecoveryLink.organization_id == organization_id,
                    models.PlannedRecoveryLink.school_year_id == school_year_id,
                    models.PlannedRecoveryLink.planned_active_block_id.in_(active_block_ids),
                    models.PlannedRecoveryLink.status
                    == models.PlannedRecoveryLinkStatus.PLANNED,
                )
                .with_for_update()
            )
        ).all()
        for link in links:
            link.status = models.PlannedRecoveryLinkStatus.CANCELED
        await self._db.flush()
        return len(links)

    async def record_delivery(
        self,
        organization_id: int,
        school_year_id: int,
        active_block_id: int,
        lesson_log_id: int,
        *,
        delivered_minutes: int | None = None,
        delivered_at: datetime | None = None,
    ) -> models.PlannedRecoveryLink:
        link = await self._db.scalar(
            select(models.PlannedRecoveryLink)
            .where(
                models.PlannedRecoveryLink.organization_id == organization_id,
                models.PlannedRecoveryLink.school_year_id == school_year_id,
                models.PlannedRecoveryLink.planned_active_block_id == active_block_id,
            )
            .with_for_update()
        )
        if link is None:
            raise RecoveryLinkIntegrityError("Active block has no planned recovery link.")
        if link.status == models.PlannedRecoveryLinkStatus.DELIVERED:
            if (
                link.delivered_lesson_log_id == lesson_log_id
                and (
                    delivered_minutes is None
                    or delivered_minutes == link.delivered_recovery_minutes
                )
            ):
                return link
            raise RecoveryLinkIntegrityError("Recovery was already delivered by other evidence.")
        if link.status != models.PlannedRecoveryLinkStatus.PLANNED:
            raise RecoveryLinkIntegrityError("Only a planned recovery can be delivered.")

        active_block = await self._db.scalar(
            select(models.ActiveScheduleBlock).where(
                models.ActiveScheduleBlock.id == active_block_id,
                models.ActiveScheduleBlock.organization_id == organization_id,
                models.ActiveScheduleBlock.school_year_id == school_year_id,
                models.ActiveScheduleBlock.status == models.ActiveScheduleBlockStatus.ACTIVE,
                models.ActiveScheduleBlock.is_recovery_block.is_(True),
            )
        )
        lesson_log = await self._db.scalar(
            select(models.LessonLog).where(
                models.LessonLog.id == lesson_log_id,
                models.LessonLog.organization_id == organization_id,
                models.LessonLog.active_schedule_block_id == active_block_id,
                models.LessonLog.status == models.LessonLogStatus.COMPLETED,
            )
        )
        if active_block is None or lesson_log is None:
            raise RecoveryLinkIntegrityError(
                "Delivery evidence must be a completed log for the active recovery block."
            )
        minutes = (
            min(active_block.duration_minutes, link.planned_recovery_minutes)
            if delivered_minutes is None
            else delivered_minutes
        )
        if minutes <= 0 or minutes > link.planned_recovery_minutes:
            raise RecoveryLinkIntegrityError("Delivered recovery minutes are out of range.")

        delivery_time = delivered_at or datetime.now(timezone.utc)
        if delivery_time.tzinfo is None or delivery_time.utcoffset() is None:
            raise RecoveryLinkIntegrityError("Delivery time must be timezone-aware.")

        link.status = models.PlannedRecoveryLinkStatus.DELIVERED
        link.delivered_recovery_minutes = minutes
        link.delivered_lesson_log_id = lesson_log.id
        link.delivered_at = delivery_time
        await self._db.flush()
        return link
