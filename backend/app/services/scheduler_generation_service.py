from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.services.scheduler_fingerprint_service import (
    DebtBasisFingerprint,
    SchedulerFingerprintService,
)
from app.services.scheduler_state_service import (
    SchedulerStateIntegrityError,
    SchedulerStateService,
)


class GenerationSelectionError(RuntimeError):
    code = "generation_selection_failed"

    def __init__(self, message: str, *, pending_draft_id: int | None = None):
        super().__init__(message)
        self.pending_draft_id = pending_draft_id


class GenerationConfigurationError(GenerationSelectionError):
    code = "scheduler_state_not_configured"


class NoOperationalTriggerError(GenerationSelectionError):
    code = "no_operational_trigger"


class PendingDraftReplacementRequiredError(GenerationSelectionError):
    code = "pending_draft_replacement_required"


class GridChangeUnavailableError(GenerationSelectionError):
    code = "grid_change_requires_published_schedule"


@dataclass(frozen=True)
class GenerationSelection:
    organization_id: int
    school_year_id: int
    strategy: models.ScheduleGenerationStrategy
    trigger_type: models.ScheduleGenerationTrigger
    scheduler_state_version: int
    approved_scheduler_state_version: int | None
    debt_basis: DebtBasisFingerprint | None
    pending_draft_id: int | None
    replaces_pending_draft: bool
    grid_version_id: int | None = None

    @property
    def reason(self) -> str:
        return {
            models.ScheduleGenerationTrigger.FIRST_GENERATION: (
                "No schedule has been published for this school year."
            ),
            models.ScheduleGenerationTrigger.EXPLICIT_DEBT: (
                "Unresolved explicit teaching debt is available for recovery."
            ),
            models.ScheduleGenerationTrigger.SCHEDULER_CHANGE: (
                "Scheduler-relevant conditions changed after the last approval."
            ),
            models.ScheduleGenerationTrigger.MIXED: (
                "Unresolved explicit debt and scheduler-relevant changes both require repair."
            ),
            models.ScheduleGenerationTrigger.GRID_CHANGE: (
                "An administrator proposed a new weekly grid for this school year."
            ),
        }[self.trigger_type]


class SchedulerGenerationService:
    def __init__(self, db: AsyncSession):
        self._state = SchedulerStateService(db)
        self._fingerprints = SchedulerFingerprintService(db)

    async def select_strategy(
        self,
        organization_id: int,
        *,
        replace_pending_draft: bool = False,
    ) -> GenerationSelection:
        school_year = await self._state.get_active_school_year(organization_id)
        if school_year is None:
            raise GenerationConfigurationError("No active scheduler school year is configured.")
        state = await self._state.get_state(organization_id, school_year.id)
        if state is None:
            raise GenerationConfigurationError(
                "The active school year has no scheduler lifecycle state."
            )

        pending_draft = await self._state.get_pending_draft(
            organization_id,
            school_year.id,
        )
        if pending_draft is not None and not replace_pending_draft:
            raise PendingDraftReplacementRequiredError(
                "A pending draft exists. Confirm replacement to generate a new draft.",
                pending_draft_id=pending_draft.id,
            )

        if state.school_year_publication_state == models.SchoolYearPublicationState.UNPUBLISHED:
            return GenerationSelection(
                organization_id=organization_id,
                school_year_id=school_year.id,
                strategy=models.ScheduleGenerationStrategy.COMPLETE_GENERATION,
                trigger_type=models.ScheduleGenerationTrigger.FIRST_GENERATION,
                scheduler_state_version=state.scheduler_state_version,
                approved_scheduler_state_version=state.approved_scheduler_state_version,
                debt_basis=None,
                pending_draft_id=(pending_draft.id if pending_draft is not None else None),
                replaces_pending_draft=pending_draft is not None,
            )

        approved_version = state.approved_scheduler_state_version
        if approved_version is None:
            raise SchedulerStateIntegrityError(
                "Published scheduler state requires an approved scheduler version."
            )
        if state.scheduler_state_version < approved_version:
            raise SchedulerStateIntegrityError(
                "Approved scheduler version cannot exceed the current version."
            )

        debt_basis = await self._fingerprints.debt_basis_fingerprint(
            organization_id,
            school_year.id,
        )
        has_debt = debt_basis is not None
        has_scheduler_change = state.scheduler_state_version > approved_version
        if not has_debt and not has_scheduler_change:
            raise NoOperationalTriggerError(
                "Generation is unavailable because there is no unresolved explicit debt "
                "and no scheduler-relevant change since the last approved schedule."
            )

        if has_debt and has_scheduler_change:
            trigger_type = models.ScheduleGenerationTrigger.MIXED
        elif has_debt:
            trigger_type = models.ScheduleGenerationTrigger.EXPLICIT_DEBT
        else:
            trigger_type = models.ScheduleGenerationTrigger.SCHEDULER_CHANGE

        return GenerationSelection(
            organization_id=organization_id,
            school_year_id=school_year.id,
            strategy=models.ScheduleGenerationStrategy.ADAPTIVE_REPAIR,
            trigger_type=trigger_type,
            scheduler_state_version=state.scheduler_state_version,
            approved_scheduler_state_version=approved_version,
            debt_basis=debt_basis,
            pending_draft_id=(pending_draft.id if pending_draft is not None else None),
            replaces_pending_draft=pending_draft is not None,
        )

    async def select_grid_change_strategy(
        self,
        organization_id: int,
    ) -> GenerationSelection:
        """Selection for an administrator-proposed grid change (W04)."""
        school_year = await self._state.get_active_school_year(organization_id)
        if school_year is None:
            raise GenerationConfigurationError("No active scheduler school year is configured.")
        state = await self._state.get_state(organization_id, school_year.id)
        if state is None:
            raise GenerationConfigurationError(
                "The active school year has no scheduler lifecycle state."
            )
        if state.school_year_publication_state != models.SchoolYearPublicationState.PUBLISHED:
            raise GridChangeUnavailableError("A grid change requires a published schedule.")
        pending_draft = await self._state.get_pending_draft(
            organization_id,
            school_year.id,
        )
        if pending_draft is not None:
            raise PendingDraftReplacementRequiredError(
                "A pending draft exists. Review or reject it before proposing a grid change.",
                pending_draft_id=pending_draft.id,
            )
        return GenerationSelection(
            organization_id=organization_id,
            school_year_id=school_year.id,
            strategy=models.ScheduleGenerationStrategy.GRID_CHANGE,
            trigger_type=models.ScheduleGenerationTrigger.GRID_CHANGE,
            scheduler_state_version=state.scheduler_state_version,
            approved_scheduler_state_version=state.approved_scheduler_state_version,
            debt_basis=None,
            pending_draft_id=None,
            replaces_pending_draft=False,
        )
