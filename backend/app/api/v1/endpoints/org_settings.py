"""Endpoints para ConfiguraÃ§Ãµes da Escola e CalendÃ¡rio Escolar.

Rotas:
  GET    /settings/                          â€” obtÃ©m a configuraÃ§Ã£o da escola
  POST   /settings/                          â€” cria/atualiza configuraÃ§Ã£o da escola
  GET    /grid-settings/                     â€” obtÃ©m a configuraÃ§Ã£o da grelha horÃ¡ria
  POST   /grid-settings/                     â€” cria/atualiza configuraÃ§Ã£o da grelha horÃ¡ria
  POST   /grid-settings/regenerate           â€” guarda e regenera a grelha atomicamente
  POST   /settings/sync-holidays             â€” importa feriados automÃ¡ticos
  GET    /calendar-events/                   â€” lista eventos do calendÃ¡rio
  POST   /calendar-events/                   â€” cria evento manual
  DELETE /calendar-events/{event_id}         â€” elimina evento
"""

from datetime import date
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.api import deps
from app.core.exceptions import AppError
from app.core.logging import safe_exception_frames
from app.scheduler.application.contracts import SchedulerTaskDispatcher
from app.services import (
    grid_change_service,
    grid_version_service,
    internship_flow_service,
    settings_service,
)
from app.services.school_year_reset_service import SchoolYearResetService

router = APIRouter()
logger = structlog.get_logger(__name__)

# ==========================================
#  ORGANIZATION SETTINGS
# ==========================================


async def _settings_read(
    db: AsyncSession,
    organization_id: int,
    settings: models.OrganizationSettings,
) -> schemas.OrganizationSettingsRead:
    preferred = await settings_service.get_preferred_end_date(db, organization_id)
    return schemas.OrganizationSettingsRead.model_validate(settings).model_copy(
        update={"preferred_end_date": preferred}
    )


@router.get(
    "/settings/",
    summary="Obter configuraÃ§Ãµes da escola",
)
async def get_org_settings(
    db: deps.DbSession,
    current_user: deps.AdminActor,
) -> schemas.OrganizationSettingsRead:
    settings = await settings_service.get_settings(db, current_user.organization_id)
    if not settings:
        raise AppError(
            kind="not_found", code="settings_not_found", detail=settings_service.SETTINGS_NOT_FOUND
        )
    return await _settings_read(db, current_user.organization_id, settings)


@router.post(
    "/settings/",
    summary="Criar ou atualizar configuraÃ§Ã£o da escola",
)
async def upsert_org_settings(
    payload: schemas.OrganizationSettingsUpsert,
    db: deps.DbSession,
    current_user: deps.AdminActor,
) -> schemas.OrganizationSettingsRead:
    try:
        settings = await settings_service.upsert_settings(
            db,
            current_user.organization_id,
            payload,
            changed_by_membership_id=current_user.membership_id,
        )
        return await _settings_read(db, current_user.organization_id, settings)
    except ValueError as exc:
        raise AppError(kind="validation", code="settings_invalid", detail=str(exc)) from exc
    except settings_service.HolidaySyncError as exc:
        raise AppError(
            kind="unavailable",
            code=exc.code,
            detail=str(exc),
            public_retryable=True,
        ) from exc


class SoftResetRequest(BaseModel):
    confirm_phrase: str


@router.post(
    "/settings/soft-reset",
    summary="Soft-Reset do Ano Letivo",
)
async def soft_reset_year_endpoint(
    payload: SoftResetRequest,
    db: deps.DbSession,
    current_user: deps.AdminActor,
):
    if payload.confirm_phrase != "Confirmo":
        raise AppError(
            kind="bad_request",
            code="soft_reset_confirmation_required",
            detail="A frase de confirmaÃ§Ã£o deve ser exatamente 'Confirmo'.",
        )

    try:
        result = await SchoolYearResetService(db).reset_year(
            current_user.organization_id,
            reset_by_membership_id=current_user.membership_id,
        )
        await db.flush()
    except Exception as exc:
        logger.error(
            "school_year_destructive_reset_failed",
            organization_id=current_user.organization_id,
            actor_membership_id=current_user.membership_id,
            error_type=type(exc).__name__,
            exception_frames=safe_exception_frames(exc),
        )
        raise

    logger.info(
        "school_year_destructive_reset_committed",
        organization_id=current_user.organization_id,
        actor_membership_id=current_user.membership_id,
        deleted_rows=result.deleted_rows,
        reset_progress_rows=result.reset_progress_rows,
        new_school_year_id=result.new_school_year_id,
    )
    return {"message": "Soft-reset efetuado com sucesso."}


# ==========================================
#  ORGANIZATION GRID SETTINGS
# ==========================================


@router.get(
    "/grid-settings/",
    summary="Obter configuraÃ§Ãµes da grelha horÃ¡ria",
)
async def get_grid_settings(
    db: deps.DbSession,
    current_user: deps.AdminActor,
) -> schemas.OrganizationGridSettingsRead:
    settings = await settings_service.get_grid_settings(db, current_user.organization_id)
    if not settings:
        raise AppError(
            kind="not_found",
            code="grid_settings_not_found",
            detail="ConfiguraÃ§Ãµes da grelha nÃ£o encontradas",
        )
    return settings


@router.post(
    "/grid-settings/",
    summary="Criar ou atualizar configuraÃ§Ã£o da grelha horÃ¡ria",
)
async def upsert_grid_settings(
    payload: schemas.OrganizationGridSettingsUpsert,
    db: deps.DbSession,
    current_user: deps.AdminActor,
) -> schemas.OrganizationGridSettingsRead:
    try:
        return await settings_service.upsert_grid_settings(
            db,
            current_user.organization_id,
            payload,
            changed_by_membership_id=current_user.membership_id,
        )
    except ValueError as exc:
        raise AppError(kind="validation", code="grid_settings_invalid", detail=str(exc)) from exc


@router.post(
    "/grid-settings/regenerate",
    response_model=schemas.GridConfigurationResponse,
    summary="Guardar configuraÃ§Ã£o e regenerar grelha atomicamente",
)
async def regenerate_grid_settings(
    payload: schemas.GridConfigurationCommand,
    db: deps.DbSession,
    current_user: deps.AdminActor,
) -> schemas.GridConfigurationResponse:
    try:
        return await settings_service.save_and_regenerate_grid(
            db,
            current_user.organization_id,
            payload,
            current_user.membership_id,
        )
    except ValueError as exc:
        raise AppError(kind="validation", code="grid_settings_invalid", detail=str(exc)) from exc


@router.get(
    "/grid-configuration/",
    response_model=schemas.GridConfigurationRead,
    summary="Obter a configuraÃ§Ã£o da grelha visÃ­vel (versÃ£o ativa)",
)
async def get_grid_configuration(
    db: deps.DbSession,
    current_user: deps.AdminActor,
) -> schemas.GridConfigurationRead:
    return schemas.GridConfigurationRead.model_validate(
        await grid_version_service.active_grid_configuration(db, current_user.organization_id)
    )


@router.post(
    "/grid-changes/preview",
    response_model=schemas.GridChangePreviewResponse,
    summary="Analisar uma alteraÃ§Ã£o da grelha sem escrever dados",
)
async def preview_grid_change(
    payload: schemas.GridChangePreviewRequest,
    db: deps.DbSession,
    current_user: deps.AdminActor,
) -> schemas.GridChangePreviewResponse:
    try:
        return await grid_change_service.preview_grid_change(
            db, current_user.organization_id, payload
        )
    except grid_change_service.GridChangeError as exc:
        raise AppError(kind="validation", code=exc.code, detail=str(exc)) from exc


@router.post(
    "/grid-changes",
    response_model=schemas.GridChangeProposalResponse,
    summary="Propor uma alteraÃ§Ã£o da grelha e iniciar a geraÃ§Ã£o",
)
async def create_grid_change(
    payload: schemas.GridChangeProposeRequest,
    db: deps.DbSession,
    current_user: deps.AdminActor,
    dispatcher: Annotated[SchedulerTaskDispatcher, Depends(deps.get_scheduler_task_dispatcher)],
) -> schemas.GridChangeProposalResponse:
    try:
        response = await grid_change_service.propose_grid_change(
            db,
            current_user.organization_id,
            payload,
            membership_id=current_user.membership_id,
        )
    except grid_change_service.GridChangeError as exc:
        kind = (
            "conflict"
            if exc.code
            in {
                "GRID_CHANGE_STALE",
                "GRID_CHANGE_BLOCKED",
                "pending_draft_replacement_required",
                "grid_change_requires_published_schedule",
                "grid_change_unavailable",
                "active_job",
            }
            else "validation"
        )
        raise AppError(kind=kind, code=exc.code, detail=str(exc)) from exc

    if not response.created:
        return response

    try:
        dispatcher.dispatch(
            organization_id=current_user.organization_id,
            job_id=response.job_id,
            task_id=f"scheduler-v1-job-{response.job_id}",
        )
    except Exception as dispatch_error:
        logger.exception(
            "scheduler_v1_grid_change_dispatch_failed",
            organization_id=current_user.organization_id,
            job_id=response.job_id,
        )
        raise AppError(
            kind="unavailable",
            code="generation_dispatch_failed",
            detail="A alteração da grelha ficou em fila e será retomada automaticamente.",
            public_context={"job_id": response.job_id},
            public_retryable=True,
        ) from dispatch_error
    return response


@router.get(
    "/grid-changes/pending",
    response_model=schemas.GridChangePendingResponse | None,
    summary="Obter a proposta de grelha pendente",
)
async def get_pending_grid_change(
    db: deps.DbSession,
    current_user: deps.AdminActor,
) -> schemas.GridChangePendingResponse | None:
    return await grid_change_service.pending_grid_change(db, current_user.organization_id)


@router.post(
    "/settings/sync-holidays",
    summary="Importar feriados nacionais automaticamente",
)
async def sync_holidays(
    db: deps.DbSession,
    current_user: deps.AdminActor,
) -> schemas.HolidaysSyncResponse:
    """Importa feriados via package `holidays` (Portugal).
    Elimina todos os eventos AUTO anteriores e recria-os (idempotente).
    """
    try:
        count = await settings_service.sync_holidays(
            db,
            organization_id=current_user.organization_id,
            changed_by_membership_id=current_user.membership_id,
        )
    except settings_service.HolidaySyncError as exc:
        raise AppError(
            kind="unavailable",
            code=exc.code,
            detail=str(exc),
            public_retryable=True,
        ) from exc
    return schemas.HolidaysSyncResponse(
        imported_count=count,
        message=f"{count} feriados importados com sucesso.",
    )


# ==========================================
#  SCHOOL CALENDAR EVENTS
# ==========================================


@router.get(
    "/calendar-events/",
    summary="Listar eventos do calendÃ¡rio escolar",
)
async def list_calendar_events(
    db: deps.DbSession,
    current_user: deps.ActiveActor,
    from_date: Annotated[
        date | None, Query(description="Filtrar eventos a partir desta data")
    ] = None,
    to_date: Annotated[date | None, Query(description="Filtrar eventos atÃ© a esta data")] = None,
) -> list[schemas.SchoolCalendarEventRead]:
    return await settings_service.list_calendar_events(
        db, current_user.organization_id, from_date, to_date
    )


def _raise_calendar_event_error(exc: Exception) -> None:
    if isinstance(exc, internship_flow_service.InternshipFlowError):
        kind = (
            "conflict"
            if exc.code
            in {
                "CALENDAR_EVENT_CONFIRMATION_REQUIRED",
                "CALENDAR_EVENT_STALE",
            }
            else "bad_request"
        )
        code = exc.code
    else:
        kind = "bad_request"
        code = "calendar_event_invalid"
    raise AppError(kind=kind, code=code, detail=str(exc)) from exc


@router.post(
    "/calendar-events/preview",
    response_model=schemas.CalendarEventChangePreviewRead,
    responses={409: {"description": "Evento desatualizado ou não encontrado"}},
    summary="Pré-visualizar as aulas afetadas por um fluxo de estágio",
)
async def preview_calendar_event_change(
    payload: schemas.CalendarEventChangePreviewRequest,
    db: deps.DbSession,
    current_user: deps.AdminActor,
) -> schemas.CalendarEventChangePreviewRead:
    try:
        return await settings_service.preview_calendar_event_change(
            db, current_user.organization_id, payload
        )
    except internship_flow_service.InternshipFlowError as exc:
        _raise_calendar_event_error(exc)


@router.post(
    "/calendar-events/",
    summary="Criar evento manual (pausa escolar, exames, fluxo de estágio)",
)
async def create_calendar_event(
    payload: schemas.SchoolCalendarEventCreate,
    db: deps.DbSession,
    current_user: deps.AdminActor,
) -> schemas.SchoolCalendarEventRead:
    try:
        return await settings_service.create_calendar_event(
            db,
            current_user.organization_id,
            payload,
            changed_by_membership_id=current_user.membership_id,
        )
    except (internship_flow_service.InternshipFlowError, ValueError) as exc:
        _raise_calendar_event_error(exc)


@router.put(
    "/calendar-events/{event_id}",
    responses={
        404: {"description": "Evento não encontrado"},
        409: {"description": "Aulas afetadas mudaram desde a pré-visualização"},
    },
    summary="Editar um fluxo de estágio",
)
async def update_calendar_event(
    event_id: int,
    payload: schemas.SchoolCalendarEventUpdate,
    db: deps.DbSession,
    current_user: deps.AdminActor,
) -> schemas.SchoolCalendarEventRead:
    try:
        return await settings_service.update_calendar_event(
            db,
            current_user.organization_id,
            event_id,
            payload,
            changed_by_membership_id=current_user.membership_id,
        )
    except (internship_flow_service.InternshipFlowError, ValueError) as exc:
        _raise_calendar_event_error(exc)


@router.delete(
    "/calendar-events/{event_id}",
    responses={404: {"description": "Evento nÃ£o encontrado"}},
    summary="Eliminar evento do calendÃ¡rio",
)
async def delete_calendar_event(
    event_id: int,
    db: deps.DbSession,
    current_user: deps.AdminActor,
) -> dict:
    success = await settings_service.delete_calendar_event(
        db,
        current_user.organization_id,
        event_id,
        changed_by_membership_id=current_user.membership_id,
    )
    if not success:
        raise AppError(
            kind="not_found", code="calendar_event_not_found", detail="Evento nÃ£o encontrado"
        )
    return {"ok": True}
