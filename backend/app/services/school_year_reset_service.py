from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import structlog
from sqlalchemy import delete, select, update
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
    """Destructively clears one tenant's operational academic-year data."""

    def __init__(self, db: AsyncSession):
        self._db = db

    async def reset_year(
        self,
        organization_id: int,
        *,
        reset_by_user_id: int,
    ) -> SchoolYearResetResult:
        await self._lock_organization(organization_id)
        settings = await self._load_settings(organization_id)
        active_year = await self._load_active_year_for_update(organization_id)
        previous_school_year_id = active_year.id if active_year is not None else None

        logger.info(
            "school_year_destructive_reset_started",
            organization_id=organization_id,
            actor_user_id=reset_by_user_id,
            school_year_id=previous_school_year_id,
        )

        deleted: dict[str, int] = {}
        for label, model in (
            ("teacher_weekly_timesheets", models.TeacherWeeklyTimesheet),
            ("occurrence_operational_events", models.OccurrenceOperationalEvent),
            ("teacher_endpoint_operational_events", models.TeacherEndpointOperationalEvent),
            ("substitutions", models.Substitution),
            ("planned_recovery_links", models.PlannedRecoveryLink),
            ("progress_ledger_entries", models.ProgressLedgerEntry),
            ("lesson_logs", models.LessonLog),
            ("operational_schedule_blocks", models.OperationalScheduleBlock),
        ):
            deleted[label] = await self._delete_for_organization(model, organization_id)

        # Occurrences live outside the scheduler-year aggregate and therefore
        # must stop referencing active blocks before that aggregate is removed.
        await self._db.execute(
            update(models.LessonOccurrence)
            .where(models.LessonOccurrence.organization_id == organization_id)
            .values(active_schedule_block_id=None)
        )

        if active_year is not None:
            result = await self._db.execute(
                delete(models.SchedulerSchoolYear).where(
                    models.SchedulerSchoolYear.id == active_year.id,
                    models.SchedulerSchoolYear.organization_id == organization_id,
                )
            )
            deleted["scheduler_school_years"] = result.rowcount or 0
        else:
            deleted["scheduler_school_years"] = 0

        # The school-year cascade removes scheduler rows that reference the
        # occurrences before the occurrences themselves are deleted.
        deleted["lesson_occurrences"] = await self._delete_for_organization(
            models.LessonOccurrence,
            organization_id,
        )
        deleted["schedule_outputs"] = await self._delete_for_organization(
            models.ScheduleOutput,
            organization_id,
        )

        progress_result = await self._db.execute(
            update(models.ClassProgress)
            .where(models.ClassProgress.organization_id == organization_id)
            .values(
                hours_completed=0.0,
                hours_debt=0.0,
                is_completed=False,
                updated_at=datetime.now(timezone.utc),
            )
        )
        reset_progress_rows = progress_result.rowcount or 0

        new_school_year_id = await self._recreate_clean_school_year(
            organization_id,
            settings,
        )
        await self._db.flush()

        reset_result = SchoolYearResetResult(
            deleted_rows=deleted,
            reset_progress_rows=reset_progress_rows,
            previous_school_year_id=previous_school_year_id,
            new_school_year_id=new_school_year_id,
        )
        logger.info(
            "school_year_destructive_reset_ready_to_commit",
            organization_id=organization_id,
            actor_user_id=reset_by_user_id,
            deleted_rows=deleted,
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

    async def _delete_for_organization(self, model, organization_id: int) -> int:
        result = await self._db.execute(
            delete(model).where(model.organization_id == organization_id)
        )
        return result.rowcount or 0

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
        school_year, _ = await SchedulerStateService(
            self._db
        ).get_or_create_active_state(
            organization_id,
            start_date=settings.school_start_date,
            hard_end_date=settings.school_hard_end_date,
        )
        return school_year.id
