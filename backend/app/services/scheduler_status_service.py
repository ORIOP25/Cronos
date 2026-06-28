from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.services.scheduler_fingerprint_service import SchedulerFingerprintService
from app.services.scheduler_state_service import SchedulerStateService


NO_TRIGGER_MESSAGE = (
    "No schedule generation needed.\n\n"
    "There are no declared missed hours to recover and no schedule-relevant "
    "changes since the last approved schedule."
)
NOT_CONFIGURED_MESSAGE = "The scheduler school year is not configured."


@dataclass(frozen=True)
class SchedulerStatus:
    school_year_id: int | None
    school_year_publication_state: str | None
    pending_draft_id: int | None
    primary_action: str
    can_generate_new_draft: bool
    can_regenerate_with_confirmation: bool
    blocked_reason: str | None
    trigger_type: str | None
    unresolved_debt_hours: float
    scheduler_state_version: int | None
    approved_scheduler_state_version: int | None


class SchedulerStatusService:
    def __init__(self, db: AsyncSession):
        self._state = SchedulerStateService(db)
        self._fingerprints = SchedulerFingerprintService(db)

    async def get_status(self, organization_id: int) -> SchedulerStatus:
        school_year = await self._state.get_active_school_year(organization_id)
        if school_year is None:
            return self._unconfigured()
        state = await self._state.get_state(organization_id, school_year.id)
        if state is None:
            return self._unconfigured(school_year.id)
        pending = await self._state.get_pending_draft(
            organization_id,
            school_year.id,
        )
        debt = None
        if (
            state.school_year_publication_state
            == models.SchoolYearPublicationState.PUBLISHED
        ):
            debt = await self._fingerprints.debt_basis_fingerprint(
                organization_id,
                school_year.id,
            )
        debt_minutes = 0 if debt is None else debt.unresolved_debt_minutes
        trigger = self._trigger(state, debt_minutes)
        common = {
            "school_year_id": school_year.id,
            "school_year_publication_state": state.school_year_publication_state.value,
            "unresolved_debt_hours": debt_minutes / 60,
            "scheduler_state_version": state.scheduler_state_version,
            "approved_scheduler_state_version": state.approved_scheduler_state_version,
        }
        if pending is not None:
            return SchedulerStatus(
                **common,
                pending_draft_id=pending.id,
                primary_action="REVIEW_PENDING_DRAFT",
                can_generate_new_draft=False,
                can_regenerate_with_confirmation=trigger is not None,
                blocked_reason=None,
                trigger_type=None if trigger is None else trigger.value,
            )
        if trigger is not None:
            return SchedulerStatus(
                **common,
                pending_draft_id=None,
                primary_action="GENERATE_SCHEDULE",
                can_generate_new_draft=True,
                can_regenerate_with_confirmation=False,
                blocked_reason=None,
                trigger_type=trigger.value,
            )
        return SchedulerStatus(
            **common,
            pending_draft_id=None,
            primary_action="GENERATION_UNAVAILABLE",
            can_generate_new_draft=False,
            can_regenerate_with_confirmation=False,
            blocked_reason=NO_TRIGGER_MESSAGE,
            trigger_type=None,
        )

    @staticmethod
    def _unconfigured(school_year_id: int | None = None) -> SchedulerStatus:
        return SchedulerStatus(
            school_year_id=school_year_id,
            school_year_publication_state=None,
            pending_draft_id=None,
            primary_action="GENERATION_UNAVAILABLE",
            can_generate_new_draft=False,
            can_regenerate_with_confirmation=False,
            blocked_reason=NOT_CONFIGURED_MESSAGE,
            trigger_type=None,
            unresolved_debt_hours=0.0,
            scheduler_state_version=None,
            approved_scheduler_state_version=None,
        )

    @staticmethod
    def _trigger(
        state: models.SchedulerSchoolYearState,
        debt_minutes: int,
    ) -> models.ScheduleGenerationTrigger | None:
        if (
            state.school_year_publication_state
            == models.SchoolYearPublicationState.UNPUBLISHED
        ):
            return models.ScheduleGenerationTrigger.FIRST_GENERATION
        approved = state.approved_scheduler_state_version
        changed = approved is not None and state.scheduler_state_version > approved
        if debt_minutes > 0 and changed:
            return models.ScheduleGenerationTrigger.MIXED
        if debt_minutes > 0:
            return models.ScheduleGenerationTrigger.EXPLICIT_DEBT
        if changed:
            return models.ScheduleGenerationTrigger.SCHEDULER_CHANGE
        return None
