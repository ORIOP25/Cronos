from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.services.scheduler_recovery_service import SchedulerRecoveryService


class SchedulerLifecycleError(RuntimeError):
    pass


class SchedulerLifecycleNotFoundError(SchedulerLifecycleError):
    pass


class SchedulerLifecycleConflictError(SchedulerLifecycleError):
    pass


@dataclass(frozen=True)
class DraftRejectionResult:
    draft_id: int
    draft_state: str


@dataclass(frozen=True)
class ResetYearResult:
    school_year_id: int
    school_year_publication_state: str
    canceled_jobs: int
    invalidated_drafts: int
    canceled_active_blocks: int
    canceled_recovery_links: int


class SchedulerLifecycleService:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def reject_draft(
        self,
        organization_id: int,
        draft_id: int,
        *,
        decided_by_user_id: int,
        now: datetime | None = None,
    ) -> DraftRejectionResult:
        instant = self._instant(now)
        draft = await self._db.scalar(
            select(models.ScheduleDraft)
            .where(
                models.ScheduleDraft.id == draft_id,
                models.ScheduleDraft.organization_id == organization_id,
            )
            .with_for_update()
        )
        if draft is None:
            raise SchedulerLifecycleNotFoundError("Schedule draft was not found.")
        if draft.draft_state not in (
            models.ScheduleDraftState.PENDING,
            models.ScheduleDraftState.STALE,
            models.ScheduleDraftState.INVALIDATED,
        ):
            raise SchedulerLifecycleConflictError(
                "Only pending, stale, or invalidated drafts can be rejected."
            )
        state = await self._locked_state(organization_id, draft.school_year_id)
        if draft.draft_state == models.ScheduleDraftState.PENDING:
            if state.pending_draft_id != draft.id:
                raise SchedulerLifecycleConflictError(
                    "Pending draft pointer does not match the rejected draft."
                )
            state.pending_draft_id = None
            state.lock_version += 1
        elif state.pending_draft_id == draft.id:
            raise SchedulerLifecycleConflictError(
                "A terminal draft cannot remain the pending draft pointer."
            )
        await SchedulerRecoveryService(self._db).cancel_draft_recovery_links(
            organization_id,
            draft.school_year_id,
            draft.id,
        )
        draft.draft_state = models.ScheduleDraftState.REJECTED
        draft.stale_reason = None
        draft.invalidated_reason = None
        draft.decided_by_user_id = decided_by_user_id
        draft.decided_at = instant
        await self._db.flush()
        return DraftRejectionResult(draft_id=draft.id, draft_state="REJECTED")

    async def reset_year(
        self,
        organization_id: int,
        *,
        reset_by_user_id: int,
        confirmed: bool,
        now: datetime | None = None,
    ) -> ResetYearResult:
        if not confirmed:
            raise SchedulerLifecycleConflictError(
                "Reset-year requires explicit administrator confirmation."
            )
        instant = self._instant(now)
        school_year = await self._db.scalar(
            select(models.SchedulerSchoolYear)
            .where(
                models.SchedulerSchoolYear.organization_id == organization_id,
                models.SchedulerSchoolYear.is_active.is_(True),
            )
            .with_for_update()
        )
        if school_year is None:
            raise SchedulerLifecycleNotFoundError(
                "No active scheduler school year exists."
            )
        state = await self._locked_state(organization_id, school_year.id)
        jobs = list(
            await self._db.scalars(
                select(models.ScheduleGenerationJob)
                .where(
                    models.ScheduleGenerationJob.organization_id == organization_id,
                    models.ScheduleGenerationJob.school_year_id == school_year.id,
                    models.ScheduleGenerationJob.job_status.in_(
                        (
                            models.ScheduleGenerationJobStatus.QUEUED,
                            models.ScheduleGenerationJobStatus.RUNNING,
                            models.ScheduleGenerationJobStatus.CANCEL_REQUESTED,
                        )
                    ),
                )
                .with_for_update()
            )
        )
        for job in jobs:
            job.job_status = models.ScheduleGenerationJobStatus.CANCELED
            job.result_category = None
            job.cancellation_requested_at = instant
            job.started_at = job.started_at or instant
            job.finished_at = instant
            job.failure_code = "RESET_YEAR"
            job.failure_message = "Generation was canceled by scheduler school-year reset."

        drafts = list(
            await self._db.scalars(
                select(models.ScheduleDraft)
                .where(
                    models.ScheduleDraft.organization_id == organization_id,
                    models.ScheduleDraft.school_year_id == school_year.id,
                    models.ScheduleDraft.draft_state == models.ScheduleDraftState.PENDING,
                )
                .with_for_update()
            )
        )
        recovery = SchedulerRecoveryService(self._db)
        for draft in drafts:
            await recovery.cancel_draft_recovery_links(
                organization_id,
                school_year.id,
                draft.id,
            )
            draft.draft_state = models.ScheduleDraftState.INVALIDATED
            draft.invalidated_reason = "The scheduler school year was reset."
            draft.decided_by_user_id = reset_by_user_id
            draft.decided_at = instant

        active_blocks = list(
            await self._db.scalars(
                select(models.ActiveScheduleBlock)
                .where(
                    models.ActiveScheduleBlock.organization_id == organization_id,
                    models.ActiveScheduleBlock.school_year_id == school_year.id,
                    models.ActiveScheduleBlock.status
                    == models.ActiveScheduleBlockStatus.ACTIVE,
                )
                .with_for_update()
            )
        )
        active_ids = {row.id for row in active_blocks}
        canceled_links = await recovery.cancel_active_recovery_links(
            organization_id,
            school_year.id,
            active_ids,
        )
        for block in active_blocks:
            block.status = models.ActiveScheduleBlockStatus.CANCELED

        state.pending_draft_id = None
        state.school_year_publication_state = models.SchoolYearPublicationState.UNPUBLISHED
        state.active_schedule_version_id = None
        state.approved_scheduler_state_version = None
        state.reset_at = instant
        state.reset_by_user_id = reset_by_user_id
        state.lock_version += 1
        await self._db.flush()
        return ResetYearResult(
            school_year_id=school_year.id,
            school_year_publication_state="UNPUBLISHED",
            canceled_jobs=len(jobs),
            invalidated_drafts=len(drafts),
            canceled_active_blocks=len(active_blocks),
            canceled_recovery_links=canceled_links,
        )

    async def _locked_state(self, organization_id: int, school_year_id: int):
        state = await self._db.scalar(
            select(models.SchedulerSchoolYearState)
            .where(
                models.SchedulerSchoolYearState.organization_id == organization_id,
                models.SchedulerSchoolYearState.school_year_id == school_year_id,
            )
            .with_for_update()
        )
        if state is None:
            raise SchedulerLifecycleNotFoundError(
                "Scheduler school-year state was not found."
            )
        return state

    @staticmethod
    def _instant(value: datetime | None) -> datetime:
        instant = value or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise SchedulerLifecycleError("Lifecycle decision time must be timezone-aware.")
        return instant
