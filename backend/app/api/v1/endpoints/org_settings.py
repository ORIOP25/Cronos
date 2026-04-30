"""Endpoints para Configurações da Escola e Calendário Escolar.

Rotas:
  GET    /settings/                          — obtém a configuração da escola
  POST   /settings/                          — cria/atualiza configuração da escola
  GET    /grid-settings/                     — obtém a configuração da grelha horária
  POST   /grid-settings/                     — cria/atualiza configuração da grelha horária
  POST   /settings/sync-holidays             — importa feriados automáticos
  GET    /calendar-events/                   — lista eventos do calendário
  POST   /calendar-events/                   — cria evento manual
  DELETE /calendar-events/{event_id}         — elimina evento
"""
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from pydantic import BaseModel
from app import models, schemas
from app.api import deps
from app.services import settings_service

router = APIRouter()

# ==========================================
#  ORGANIZATION SETTINGS
# ==========================================

@router.get(
    "/settings/",
    response_model=schemas.OrganizationSettingsRead,
    summary="Obter configurações da escola",
)
async def get_org_settings(
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
) -> schemas.OrganizationSettingsRead:
    settings = await settings_service.get_settings(db, current_user.organization_id)
    if not settings:
        raise HTTPException(status_code=404, detail=settings_service.SETTINGS_NOT_FOUND)
    return settings


@router.post(
    "/settings/",
    response_model=schemas.OrganizationSettingsRead,
    summary="Criar ou atualizar configuração da escola",
)
async def upsert_org_settings(
    payload: schemas.OrganizationSettingsUpsert,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
) -> schemas.OrganizationSettingsRead:
    return await settings_service.upsert_settings(db, current_user.organization_id, payload)


class SoftResetRequest(BaseModel):
    confirm_phrase: str

@router.post(
    "/settings/soft-reset",
    summary="Soft-Reset do Ano Letivo",
)
async def soft_reset_year_endpoint(
    payload: SoftResetRequest,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
):
    if payload.confirm_phrase != "Confirmo":
        raise HTTPException(status_code=400, detail="A frase de confirmação deve ser exatamente 'Confirmo'.")
        
    await settings_service.soft_reset_year(db, current_user.organization_id)
    return {"message": "Soft-reset efetuado com sucesso."}

# ==========================================
#  ORGANIZATION GRID SETTINGS
# ==========================================

@router.get(
    "/grid-settings/",
    response_model=schemas.OrganizationGridSettingsRead,
    summary="Obter configurações da grelha horária",
)
async def get_grid_settings(
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
) -> schemas.OrganizationGridSettingsRead:
    settings = await settings_service.get_grid_settings(db, current_user.organization_id)
    if not settings:
        raise HTTPException(status_code=404, detail="Configurações da grelha não encontradas")
    return settings


@router.post(
    "/grid-settings/",
    response_model=schemas.OrganizationGridSettingsRead,
    summary="Criar ou atualizar configuração da grelha horária",
)
async def upsert_grid_settings(
    payload: schemas.OrganizationGridSettingsUpsert,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
) -> schemas.OrganizationGridSettingsRead:
    return await settings_service.upsert_grid_settings(db, current_user.organization_id, payload)


@router.post(
    "/settings/sync-holidays",
    response_model=schemas.HolidaysSyncResponse,
    summary="Importar feriados nacionais automaticamente",
)
async def sync_holidays(
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
) -> schemas.HolidaysSyncResponse:
    """Importa feriados via package `holidays` (Portugal).
    Elimina todos os eventos AUTO anteriores e recria-os (idempotente).
    """
    count = await settings_service.sync_holidays(
        db,
        org_id=current_user.organization_id,
    )
    return schemas.HolidaysSyncResponse(
        imported_count=count,
        message=f"{count} feriados importados com sucesso.",
    )


# ==========================================
#  SCHOOL CALENDAR EVENTS
# ==========================================

@router.get(
    "/calendar-events/",
    response_model=list[schemas.SchoolCalendarEventRead],
    summary="Listar eventos do calendário escolar",
)
async def list_calendar_events(
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_user)],
    from_date: date | None = Query(None, description="Filtrar eventos a partir desta data"),
    to_date: date | None = Query(None, description="Filtrar eventos até a esta data"),
) -> list[schemas.SchoolCalendarEventRead]:
    return await settings_service.list_calendar_events(
        db, current_user.organization_id, from_date, to_date
    )


@router.post(
    "/calendar-events/",
    response_model=schemas.SchoolCalendarEventRead,
    summary="Criar evento manual (pausa escolar, exames, etc.)",
)
async def create_calendar_event(
    payload: schemas.SchoolCalendarEventCreate,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
) -> schemas.SchoolCalendarEventRead:
    try:
        return await settings_service.create_calendar_event(db, current_user.organization_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete(
    "/calendar-events/{event_id}",
    responses={404: {"description": "Evento não encontrado"}},
    summary="Eliminar evento do calendário",
)
async def delete_calendar_event(
    event_id: int,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
) -> dict:
    success = await settings_service.delete_calendar_event(db, current_user.organization_id, event_id)
    if not success:
        raise HTTPException(status_code=404, detail="Evento não encontrado")
    return {"ok": True}
