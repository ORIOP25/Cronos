"""Endpoints para Configurações da Escola e Calendário Escolar.

Rotas:
  GET    /settings/                          — lista os anos letivos configurados
  POST   /settings/                          — cria/atualiza configuração de um ano letivo
  DELETE /settings/{academic_year}           — elimina configuração de um ano letivo
  GET    /settings/regions                   — lista regiões disponíveis (package holidays)
  POST   /settings/{academic_year}/sync-holidays — importa feriados automáticos
  GET    /calendar-events/                   — lista eventos do calendário
  POST   /calendar-events/                   — cria evento manual
  DELETE /calendar-events/{event_id}         — elimina evento
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.api import deps
from app.services import settings_service

router = APIRouter()

# ==========================================
#  ORGANIZATION SETTINGS
# ==========================================

@router.get(
    "/settings/",
    response_model=list[schemas.OrganizationSettingsRead],
    summary="Listar configurações por ano letivo",
)
async def list_org_settings(
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
) -> list[schemas.OrganizationSettingsRead]:
    return await settings_service.list_settings(db, current_user.organization_id)


@router.post(
    "/settings/",
    response_model=schemas.OrganizationSettingsRead,
    summary="Criar ou atualizar configuração de ano letivo",
)
async def upsert_org_settings(
    payload: schemas.OrganizationSettingsUpsert,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
) -> schemas.OrganizationSettingsRead:
    return await settings_service.upsert_settings(db, current_user.organization_id, payload)


@router.delete(
    "/settings/{academic_year}",
    responses={404: {"description": "Configurações não encontradas"}},
    summary="Eliminar configuração de um ano letivo",
)
async def delete_org_settings(
    academic_year: str,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
) -> dict:
    success = await settings_service.delete_settings(db, current_user.organization_id, academic_year)
    if not success:
        raise HTTPException(status_code=404, detail=settings_service.SETTINGS_NOT_FOUND)
    return {"ok": True}


@router.get(
    "/settings/regions",
    response_model=schemas.AvailableRegionsResponse,
    summary="Listar regiões disponíveis para feriados municipais (Portugal)",
)
def list_regions() -> schemas.AvailableRegionsResponse:
    """Endpoint síncrono — a lista vem do package holidays em memória, sem I/O."""
    return schemas.AvailableRegionsResponse(regions=settings_service.list_available_regions())


@router.post(
    "/settings/{academic_year}/sync-holidays",
    response_model=schemas.HolidaysSyncResponse,
    responses={404: {"description": "Configurações não encontradas para o ano indicado"}},
    summary="Importar feriados nacionais/regionais automaticamente",
)
async def sync_holidays(
    academic_year: str,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
) -> schemas.HolidaysSyncResponse:
    """Importa feriados via package `holidays` (Portugal + região).
    Usa o region_code guardado nas OrganizationSettings do ano letivo indicado.
    Elimina todos os eventos AUTO anteriores e recria-os (idempotente).
    """
    org_settings = await settings_service.get_settings_by_year(
        db, current_user.organization_id, academic_year
    )
    if not org_settings:
        raise HTTPException(status_code=404, detail=settings_service.SETTINGS_NOT_FOUND)

    count = await settings_service.sync_holidays(
        db,
        org_id=current_user.organization_id,
        academic_year=academic_year,
        region_code=org_settings.region_code,
    )
    return schemas.HolidaysSyncResponse(
        academic_year=academic_year,
        imported_count=count,
        message=f"{count} feriados importados com sucesso para {academic_year}.",
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
    academic_year: str | None = Query(None, description="Filtrar por ano letivo (ex: '2025/2026')"),
) -> list[schemas.SchoolCalendarEventRead]:
    return await settings_service.list_calendar_events(
        db, current_user.organization_id, academic_year
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
    return await settings_service.create_calendar_event(db, current_user.organization_id, payload)


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
