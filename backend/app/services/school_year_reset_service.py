from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.services.scheduler_state_service import SchedulerStateService

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class SchoolYearResetResult:
    deleted_rows: dict[str, int]
    reset_progress_rows: int
    previous_school_year_id: int | None
    new_school_year_id: int | None


class SchoolYearResetService:
    """Reset the active scheduler state while preserving immutable history."""

    def __init__(self, db: AsyncSession):
        self._db = db

    async def reset_year(
        self,
        organization_id: int,
        *,
        reset_by_membership_id: int,
    ) -> SchoolYearResetResult:
        await self._lock_organization(organization_id)
        settings = await self._load_settings(organization_id)
        active_year = await self._load_active_year_for_update(organization_id)
        previous_school_year_id = active_year.id if active_year is not None else None

        logger.info(
            "school_year_destructive_reset_started",
            organization_id=organization_id,
            actor_membership_id=reset_by_membership_id,
            school_year_id=previous_school_year_id,
        )

        now = datetime.now(UTC)
        affected: dict[str, int] = {}
        result = await self._db.execute(
            update(models.ActiveScheduleBlock)
            .where(
                models.ActiveScheduleBlock.organization_id == organization_id,
                models.ActiveScheduleBlock.status == models.ActiveScheduleBlockStatus.ACTIVE,
            )
            .values(status=models.ActiveScheduleBlockStatus.REMOVED, updated_at=now)
        )
        affected["active_schedule_blocks"] = result.rowcount or 0
        result = await self._db.execute(
            update(models.OperationalScheduleBlock)
            .where(
                models.OperationalScheduleBlock.organization_id == organization_id,
                models.OperationalScheduleBlock.status == models.OperationalBlockStatus.ACTIVE,
            )
            .values(
                status=models.OperationalBlockStatus.CANCELLED,
                execution_status=models.OperationalBlockExecutionStatus.CANCELLED,
                cancelled_at=now,
            )
        )
        affected["operational_schedule_blocks"] = result.rowcount or 0
        result = await self._db.execute(
            update(models.PlannedRecoveryLink)
            .where(
                models.PlannedRecoveryLink.organization_id == organization_id,
                models.PlannedRecoveryLink.status == models.PlannedRecoveryLinkStatus.PLANNED,
            )
            .values(status=models.PlannedRecoveryLinkStatus.CANCELED, updated_at=now)
        )
        affected["planned_recovery_links"] = result.rowcount or 0

        pending_drafts = list(
            await self._db.scalars(
                select(models.ScheduleDraft).where(
                    models.ScheduleDraft.organization_id == organization_id,
                    models.ScheduleDraft.draft_state == models.ScheduleDraftState.PENDING,
                )
            )
        )
        for draft in pending_drafts:
            draft.draft_state = models.ScheduleDraftState.INVALIDATED
            draft.invalidated_reason = "School year reset by an administrator."
            draft.decided_by_membership_id = reset_by_membership_id
            draft.decided_at = now
        affected["pending_drafts"] = len(pending_drafts)

        reset_progress_rows = await self._append_progress_reversals(
            organization_id,
            school_year_id=previous_school_year_id,
            reset_by_membership_id=reset_by_membership_id,
        )
        if active_year is not None:
            state = await SchedulerStateService(self._db).get_state(
                organization_id,
                active_year.id,
                for_update=True,
            )
            if state is not None:
                state.pending_draft_id = None
                state.school_year_publication_state = models.SchoolYearPublicationState.UNPUBLISHED
                state.active_schedule_version_id = None
                state.approved_scheduler_state_version = None
                state.scheduler_state_version += 1
                state.lock_version += 1

        new_school_year_id = (
            active_year.id
            if active_year is not None
            else await self._recreate_clean_school_year(organization_id, settings)
        )
        await self._db.flush()

        reset_result = SchoolYearResetResult(
            deleted_rows=affected,
            reset_progress_rows=reset_progress_rows,
            previous_school_year_id=previous_school_year_id,
            new_school_year_id=new_school_year_id,
        )
        logger.info(
            "school_year_destructive_reset_ready_to_commit",
            organization_id=organization_id,
            actor_membership_id=reset_by_membership_id,
            deleted_rows=affected,
            reset_progress_rows=reset_progress_rows,
            previous_school_year_id=previous_school_year_id,
            new_school_year_id=new_school_year_id,
        )
        return reset_result

    async def _lock_organization(self, organization_id: int) -> None:
        organization = await self._db.scalar(
            select(models.Organization)
            .where(models.Organization.id == organization_id)
            .with_for_update()
        )
        if organization is None:
            raise ValueError("Organization does not exist.")

    async def _load_settings(
        self,
        organization_id: int,
    ) -> models.OrganizationSettings | None:
        return await self._db.scalar(
            select(models.OrganizationSettings).where(
                models.OrganizationSettings.organization_id == organization_id
            )
        )

    async def _load_active_year_for_update(
        self,
        organization_id: int,
    ) -> models.SchedulerSchoolYear | None:
        return await self._db.scalar(
            select(models.SchedulerSchoolYear)
            .where(
                models.SchedulerSchoolYear.organization_id == organization_id,
                models.SchedulerSchoolYear.is_active.is_(True),
            )
            .with_for_update()
        )

    async def _append_progress_reversals(
        self,
        organization_id: int,
        *,
        school_year_id: int | None,
        reset_by_membership_id: int,
    ) -> int:
        totals = list(
            await self._db.execute(
                select(
                    models.ProgressLedgerEntry.class_id,
                    models.ProgressLedgerEntry.module_id,
                    func.sum(models.ProgressLedgerEntry.completed_minutes_delta),
                    func.sum(models.ProgressLedgerEntry.debt_minutes_delta),
                )
                .where(models.ProgressLedgerEntry.organization_id == organization_id)
                .group_by(
                    models.ProgressLedgerEntry.class_id,
                    models.ProgressLedgerEntry.module_id,
                )
            )
        )
        count = 0
        for class_id, module_id, completed, debt in totals:
            completed_minutes = int(completed or 0)
            debt_minutes = int(debt or 0)
            if completed_minutes == 0 and debt_minutes == 0:
                continue
            self._db.add(
                models.ProgressLedgerEntry(
                    organization_id=organization_id,
                    source_type="school_year_reset",
                    source_id=school_year_id or 0,
                    class_id=class_id,
                    module_id=module_id,
                    completed_minutes_delta=-completed_minutes,
                    debt_minutes_delta=-debt_minutes,
                    idempotency_key=(
                        f"school-year-reset:{school_year_id or 0}:{class_id}:{module_id}"
                    ),
                    created_by_membership_id=reset_by_membership_id,
                )
            )
            count += 1
        return count

    async def _recreate_clean_school_year(
        self,
        organization_id: int,
        settings: models.OrganizationSettings | None,
    ) -> int | None:
        if (
            settings is None
            or settings.school_start_date is None
            or settings.school_hard_end_date is None
        ):
            return None
        school_year, _ = await SchedulerStateService(self._db).get_or_create_active_state(
            organization_id,
            start_date=settings.school_start_date,
            hard_end_date=settings.school_hard_end_date,
        )
        return school_year.id
