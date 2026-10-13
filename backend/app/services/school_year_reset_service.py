from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.scheduler.infrastructure.models import (
    JOB_ACTIVE_STATUSES,
    CurricularAssignment,
    SchedulerJobV1,
    SchedulerProposalV1,
    SchedulerVersionV1,
)
from app.scheduler.infrastructure.progress import (
    reverse_outstanding_credits,
    settle_open_debt,
)
from app.services.scheduler_state_service import SchedulerStateService

logger = structlog.get_logger(__name__)

RESET_REASON = "Reinício do ano letivo pelo administrador."


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
        state_service = SchedulerStateService(self._db)
        # The year state lock is taken before any transition so a concurrent
        # generation cannot publish old data between cleanup steps.
        state = (
            await state_service.get_state(organization_id, active_year.id, for_update=True)
            if active_year is not None
            else None
        )

        logger.info(
            "school_year_destructive_reset_started",
            organization_id=organization_id,
            actor_membership_id=reset_by_membership_id,
            school_year_id=previous_school_year_id,
        )

        now = datetime.now(UTC)
        affected: dict[str, int] = {}
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
        if active_year is not None:
            affected.update(
                await self._reset_v1_year(
                    organization_id,
                    active_year.id,
                    reset_by_membership_id=reset_by_membership_id,
                    now=now,
                )
            )

        reset_progress_rows = await self._append_progress_reversals(
            organization_id,
            school_year_id=previous_school_year_id,
            reset_by_membership_id=reset_by_membership_id,
        )
        if state is not None and active_year is not None:
            state = await state_service.reset_year(
                organization_id,
                active_year.id,
                reset_by_membership_id=reset_by_membership_id,
                reset_at=now,
            )
            state.input_revision = 0
            state.planning_revision = 0
            state.last_completed_planning_revision = None
            state.last_successful_generation_at = None
            state.scheduler_state_version += 1

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

    async def _reset_v1_year(
        self,
        organization_id: int,
        school_year_id: int,
        *,
        reset_by_membership_id: int,
        now: datetime,
    ) -> dict[str, int]:
        """Discard the active v1 generation and its operational progress."""
        summary: dict[str, int] = {}
        result = await self._db.execute(
            update(SchedulerVersionV1)
            .where(
                SchedulerVersionV1.organization_id == organization_id,
                SchedulerVersionV1.school_year_id == school_year_id,
                SchedulerVersionV1.status == "ACTIVE",
            )
            .values(status="SUPERSEDED")
        )
        summary["v1_versions_superseded"] = result.rowcount or 0

        result = await self._db.execute(
            update(SchedulerProposalV1)
            .where(
                SchedulerProposalV1.organization_id == organization_id,
                SchedulerProposalV1.school_year_id == school_year_id,
                SchedulerProposalV1.status == "PENDING",
            )
            .values(
                status="SUPERSEDED",
                reason="school_year_reset",
                decided_at=now,
                decided_by_membership_id=reset_by_membership_id,
            )
        )
        summary["v1_proposals_superseded"] = result.rowcount or 0

        jobs = list(
            (
                await self._db.scalars(
                    select(SchedulerJobV1)
                    .where(
                        SchedulerJobV1.organization_id == organization_id,
                        SchedulerJobV1.school_year_id == school_year_id,
                        SchedulerJobV1.status.in_(JOB_ACTIVE_STATUSES),
                    )
                    .with_for_update()
                )
            ).all()
        )
        grid_version_ids = sorted(
            {job.grid_version_id for job in jobs if job.grid_version_id is not None}
        )
        for job in jobs:
            job.status = "CANCELLED"
            job.result_code = "CANCELLED"
            job.stop_reason = "CANCELLED"
            job.cancellation_requested_at = now
            job.finished_at = now
        summary["v1_jobs_cancelled"] = len(jobs)
        rejected_grid_versions = 0
        if grid_version_ids:
            rejected = await self._db.execute(
                update(models.GridVersion)
                .where(
                    models.GridVersion.organization_id == organization_id,
                    models.GridVersion.id.in_(grid_version_ids),
                    models.GridVersion.state == models.GridVersionState.PENDING,
                )
                .values(state=models.GridVersionState.REJECTED)
            )
            rejected_grid_versions = rejected.rowcount or 0
        summary["v1_grid_versions_rejected"] = rejected_grid_versions

        reversed_executions, settled_minutes = await self._reverse_v1_progress(
            organization_id,
            school_year_id,
            reset_by_membership_id=reset_by_membership_id,
            now=now,
        )
        summary["v1_executions_reversed"] = reversed_executions
        summary["v1_debt_settled_minutes"] = settled_minutes
        return summary

    async def _reverse_v1_progress(
        self,
        organization_id: int,
        school_year_id: int,
        *,
        reset_by_membership_id: int,
        now: datetime,
    ) -> tuple[int, int]:
        assignment_ids = list(
            (
                await self._db.scalars(
                    select(CurricularAssignment.id)
                    .where(
                        CurricularAssignment.organization_id == organization_id,
                        CurricularAssignment.school_year_id == school_year_id,
                    )
                    .order_by(CurricularAssignment.id)
                )
            ).all()
        )
        if not assignment_ids:
            return 0, 0
        settled_minutes = 0
        for assignment_id in assignment_ids:
            settled_minutes += await settle_open_debt(
                self._db,
                organization_id,
                school_year_id,
                assignment_id,
                membership_id=reset_by_membership_id,
                reason=RESET_REASON,
                now_utc=now,
            )
        reversed_executions = 0
        for assignment_id in assignment_ids:
            reversed_executions += await reverse_outstanding_credits(
                self._db,
                organization_id,
                school_year_id,
                assignment_id,
                membership_id=reset_by_membership_id,
                reason=RESET_REASON,
                now_utc=now,
            )
        return reversed_executions, settled_minutes

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
