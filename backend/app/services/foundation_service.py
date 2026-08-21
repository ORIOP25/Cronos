"""Foundation service managing optimistic draft state and monotonic foundation activation."""

from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.services import settings_service

logger = structlog.get_logger(__name__)


class FoundationError(Exception):
    """Base exception for foundation operations."""


class FoundationDraftVersionConflictError(FoundationError):
    def __init__(self, current_version: int, message: str = "Versão do rascunho desatualizada"):
        super().__init__(message)
        self.current_version = current_version


class FoundationAlreadyCompletedError(FoundationError):
    pass


class FoundationIncompleteDraftError(FoundationError):
    pass


def validate_foundation_snapshot(data: schemas.FoundationDraftData) -> None:
    """Validate the complete Foundation snapshot before any database mutation."""
    required = {
        "school_start_date": data.school_start_date,
        "school_hard_end_date": data.school_hard_end_date,
        "repair_stability_window_days": data.repair_stability_window_days,
        "days_of_week": data.days_of_week,
        "opening_time": data.opening_time,
        "closing_time": data.closing_time,
        "slot_duration_minutes": data.slot_duration_minutes,
        "break_duration_minutes": data.break_duration_minutes,
        "lunch_window_start": data.lunch_window_start,
        "lunch_window_end": data.lunch_window_end,
        "lunch_min_duration_minutes": data.lunch_min_duration_minutes,
    }
    missing = [name for name, value in required.items() if value is None]
    if missing:
        raise ValueError(f"Campos obrigatórios em falta: {', '.join(missing)}")
    if data.school_hard_end_date <= data.school_start_date:
        raise ValueError("A data-limite deve ser posterior à data de início")
    if not 1 <= data.repair_stability_window_days <= 60:
        raise ValueError("A janela de estabilidade deve estar entre 1 e 60 dias")
    if (
        not data.days_of_week
        or len(data.days_of_week) > 7
        or len(set(data.days_of_week)) != len(data.days_of_week)
        or any(day < 0 or day > 6 for day in data.days_of_week)
    ):
        raise ValueError("Os dias letivos devem ser únicos e estar entre 0 e 6")
    if data.closing_time <= data.opening_time:
        raise ValueError("A hora de fecho deve ser posterior à hora de abertura")
    if not 15 <= data.slot_duration_minutes <= 120:
        raise ValueError("A duração do bloco deve estar entre 15 e 120 minutos")
    if not 0 <= data.break_duration_minutes <= 60:
        raise ValueError("O intervalo deve estar entre 0 e 60 minutos")
    if data.lunch_window_start < data.opening_time or data.lunch_window_end > data.closing_time:
        raise ValueError("A janela de almoço deve ficar dentro do horário da escola")
    schemas.validate_lunch_window(
        data.lunch_window_start,
        data.lunch_window_end,
        data.lunch_min_duration_minutes,
    )
    available_minutes = (
        data.closing_time.hour * 60
        + data.closing_time.minute
        - data.opening_time.hour * 60
        - data.opening_time.minute
    )
    if available_minutes < data.slot_duration_minutes:
        raise ValueError("O horário não permite um bloco completo")


class FoundationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_status(self, organization_id: int) -> schemas.FoundationStatusResponse:
        org = await self.db.get(models.Organization, organization_id)
        if org is None:
            raise RuntimeError(f"Organization {organization_id} not found")

        return schemas.FoundationStatusResponse(
            foundation_status=org.foundation_status.value,
            foundation_completed_at=org.foundation_completed_at,
            first_real_schedule_approved_at=org.first_real_schedule_approved_at,
            organization_name=org.name,
        )

    async def get_draft(self, organization_id: int) -> schemas.FoundationDraftRead:
        draft = await self.db.scalar(
            select(models.OrganizationFoundationDraft).where(
                models.OrganizationFoundationDraft.organization_id == organization_id
            )
        )
        if draft is None:
            return schemas.FoundationDraftRead(
                version=0,
                current_step=1,
                data=schemas.FoundationDraftData(),
                updated_at=None,
            )

        data = schemas.FoundationDraftData.model_validate(draft.payload_json or {})
        return schemas.FoundationDraftRead(
            version=draft.version,
            current_step=draft.current_step,
            data=data,
            updated_at=draft.updated_at,
        )

    async def save_draft(
        self,
        organization_id: int,
        write: schemas.FoundationDraftWrite,
        membership_id: int,
    ) -> schemas.FoundationDraftRead:
        org = await self.db.scalar(
            select(models.Organization)
            .where(models.Organization.id == organization_id)
            .with_for_update()
        )
        if org is None:
            raise RuntimeError(f"Organization {organization_id} not found")

        if org.foundation_status == models.OrganizationFoundationStatus.COMPLETED:
            raise FoundationAlreadyCompletedError(
                "A fundação desta organização já se encontra concluída."
            )

        draft = await self.db.scalar(
            select(models.OrganizationFoundationDraft)
            .where(models.OrganizationFoundationDraft.organization_id == organization_id)
            .with_for_update()
        )

        current_version = draft.version if draft is not None else 0
        if write.expected_version != current_version:
            raise FoundationDraftVersionConflictError(current_version=current_version)

        if org.foundation_status == models.OrganizationFoundationStatus.NOT_STARTED:
            org.foundation_status = models.OrganizationFoundationStatus.IN_PROGRESS

        new_version = current_version + 1
        now = datetime.now(UTC)
        payload = write.data.model_dump(mode="json")

        if draft is None:
            draft = models.OrganizationFoundationDraft(
                organization_id=organization_id,
                version=new_version,
                current_step=write.current_step,
                payload_json=payload,
                updated_by_membership_id=membership_id,
                updated_at=now,
            )
            self.db.add(draft)
        else:
            draft.version = new_version
            draft.current_step = write.current_step
            draft.payload_json = payload
            draft.updated_by_membership_id = membership_id
            draft.updated_at = now

        await self.db.flush()
        return schemas.FoundationDraftRead(
            version=new_version,
            current_step=write.current_step,
            data=write.data,
            updated_at=now,
        )

    async def complete_foundation(
        self,
        organization_id: int,
        command: schemas.FoundationCompleteCommand,
        membership_id: int,
    ) -> schemas.FoundationCompleteResponse:
        org = await self.db.scalar(
            select(models.Organization)
            .where(models.Organization.id == organization_id)
            .with_for_update()
        )
        if org is None:
            raise RuntimeError(f"Organization {organization_id} not found")

        if org.foundation_status == models.OrganizationFoundationStatus.COMPLETED:
            # Idempotent response
            timeslot_count = len(
                await settings_service.timeslot_service.get_timeslots_by_org(
                    self.db, organization_id
                )
            )
            if org.foundation_completed_at is None:
                raise RuntimeError(
                    f"Organization {organization_id} is COMPLETED but foundation_completed_at is NULL"
                )
            return schemas.FoundationCompleteResponse(
                foundation_status=org.foundation_status.value,
                foundation_completed_at=org.foundation_completed_at,
                generated_timeslot_count=timeslot_count,
            )

        draft = await self.db.scalar(
            select(models.OrganizationFoundationDraft)
            .where(models.OrganizationFoundationDraft.organization_id == organization_id)
            .with_for_update()
        )
        current_version = draft.version if draft is not None else 0
        if command.expected_version != current_version:
            raise FoundationDraftVersionConflictError(current_version=current_version)

        if draft is None:
            raise FoundationIncompleteDraftError("Rascunho da fundação não encontrado")

        data = schemas.FoundationDraftData.model_validate(draft.payload_json or {})

        try:
            validate_foundation_snapshot(data)
        except ValueError as exc:
            raise FoundationIncompleteDraftError(str(exc)) from exc

        # 1. Upsert settings
        await settings_service.upsert_settings(
            self.db,
            organization_id,
            schemas.OrganizationSettingsUpsert(
                school_start_date=data.school_start_date,
                school_hard_end_date=data.school_hard_end_date,
                repair_stability_window_days=data.repair_stability_window_days,
            ),
            changed_by_membership_id=membership_id,
        )

        # 2. Generate and save grid
        grid_command = schemas.GridConfigurationCommand(
            grid_settings=schemas.OrganizationGridSettingsUpsert(
                lunch_window_start=data.lunch_window_start,
                lunch_window_end=data.lunch_window_end,
                lunch_min_duration_minutes=data.lunch_min_duration_minutes,
            ),
            timeslots=schemas.TimeslotBulkCreate(
                days_of_week=data.days_of_week,
                start_time=data.opening_time,
                end_time=data.closing_time,
                slot_duration_minutes=data.slot_duration_minutes,
                break_duration_minutes=data.break_duration_minutes,
            ),
        )
        grid_res = await settings_service.save_and_regenerate_grid(
            self.db,
            organization_id,
            grid_command,
            changed_by_membership_id=membership_id,
        )
        if grid_res.generated_count <= 0:
            raise FoundationIncompleteDraftError(
                "Nenhum bloco de horário pôde ser gerado com a configuração fornecida"
            )

        # 3. Transition to COMPLETED
        now = datetime.now(UTC)
        org.foundation_status = models.OrganizationFoundationStatus.COMPLETED
        org.foundation_completed_at = now
        await self.db.flush()

        return schemas.FoundationCompleteResponse(
            foundation_status="COMPLETED",
            foundation_completed_at=now,
            generated_timeslot_count=grid_res.generated_count,
        )
