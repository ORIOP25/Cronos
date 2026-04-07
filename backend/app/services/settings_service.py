"""Serviço para OrganizationSettings e SchoolCalendarEvent.

Responsável por:
  - CRUD de configurações anuais (OrganizationSettings)
  - CRUD de eventos do calendário escolar (SchoolCalendarEvent)
  - Importação automática de feriados via package `holidays`
"""
from __future__ import annotations

from datetime import date
from typing import Sequence

import holidays as pt_holidays_lib
from sqlalchemy import select, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas

# --- Mensagens de erro reutilizadas ---
SETTINGS_NOT_FOUND = "Configurações para o ano letivo indicado não encontradas"


# ==========================================
#  ORGANIZATION SETTINGS
# ==========================================

async def list_settings(db: AsyncSession, org_id: int) -> Sequence[models.OrganizationSettings]:
    """Lista todas as configurações (um registo por ano letivo) da organização."""
    result = await db.execute(
        select(models.OrganizationSettings)
        .where(models.OrganizationSettings.org_id == org_id)
        .order_by(models.OrganizationSettings.academic_year.desc())
    )
    return result.scalars().all()


async def get_settings_by_year(
    db: AsyncSession, org_id: int, academic_year: str
) -> models.OrganizationSettings | None:
    result = await db.execute(
        select(models.OrganizationSettings).where(
            and_(
                models.OrganizationSettings.org_id == org_id,
                models.OrganizationSettings.academic_year == academic_year,
            )
        )
    )
    return result.scalar_one_or_none()


async def upsert_settings(
    db: AsyncSession, org_id: int, data: schemas.OrganizationSettingsUpsert
) -> models.OrganizationSettings:
    """Cria ou actualiza o registo de configuração para um dado ano letivo."""
    existing = await get_settings_by_year(db, org_id, data.academic_year)
    if existing:
        if data.school_start_date is not None:
            existing.school_start_date = data.school_start_date
        if data.school_target_end_date is not None:
            existing.school_target_end_date = data.school_target_end_date
        if data.school_hard_end_date is not None:
            existing.school_hard_end_date = data.school_hard_end_date
        if data.region_code is not None:
            existing.region_code = data.region_code
        if data.lunch_window_start is not None:
            existing.lunch_window_start = data.lunch_window_start
        if data.lunch_window_end is not None:
            existing.lunch_window_end = data.lunch_window_end
        if data.lunch_min_duration_minutes is not None:
            existing.lunch_min_duration_minutes = data.lunch_min_duration_minutes
        await db.commit()
        await db.refresh(existing)
        return existing

    new_settings = models.OrganizationSettings(
        org_id=org_id,
        academic_year=data.academic_year,
        school_start_date=data.school_start_date,
        school_target_end_date=data.school_target_end_date,
        school_hard_end_date=data.school_hard_end_date,
        region_code=data.region_code,
        lunch_window_start=data.lunch_window_start,
        lunch_window_end=data.lunch_window_end,
        lunch_min_duration_minutes=data.lunch_min_duration_minutes,
    )
    db.add(new_settings)
    await db.commit()
    await db.refresh(new_settings)
    return new_settings


async def delete_settings(db: AsyncSession, org_id: int, academic_year: str) -> bool:
    existing = await get_settings_by_year(db, org_id, academic_year)
    if not existing:
        return False
    await db.delete(existing)
    await db.commit()
    return True


# ==========================================
#  SCHOOL CALENDAR EVENTS
# ==========================================

async def list_calendar_events(
    db: AsyncSession,
    org_id: int,
    academic_year: str | None = None,
) -> Sequence[models.SchoolCalendarEvent]:
    """Lista eventos do calendário, opcionalmente filtrados por ano letivo."""
    query = select(models.SchoolCalendarEvent).where(
        models.SchoolCalendarEvent.org_id == org_id
    )
    if academic_year:
        query = query.where(models.SchoolCalendarEvent.academic_year == academic_year)
    query = query.order_by(models.SchoolCalendarEvent.start_date)
    result = await db.execute(query)
    return result.scalars().all()


async def create_calendar_event(
    db: AsyncSession, org_id: int, data: schemas.SchoolCalendarEventCreate
) -> models.SchoolCalendarEvent:
    event = models.SchoolCalendarEvent(
        org_id=org_id,
        academic_year=data.academic_year,
        name=data.name,
        start_date=data.start_date,
        end_date=data.end_date,
        event_type=data.event_type,
        source=models.CalendarEventSource.manual,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


async def delete_calendar_event(db: AsyncSession, org_id: int, event_id: int) -> bool:
    result = await db.execute(
        select(models.SchoolCalendarEvent).where(
            and_(
                models.SchoolCalendarEvent.id == event_id,
                models.SchoolCalendarEvent.org_id == org_id,
            )
        )
    )
    event = result.scalar_one_or_none()
    if not event:
        return False
    await db.delete(event)
    await db.commit()
    return True


# ==========================================
#  IMPORTAÇÃO DE FERIADOS (via package `holidays`)
# ==========================================

def _get_pt_holidays(years: list[int], region_code: str | None) -> dict[date, str]:
    """Obtém feriados de Portugal para os anos indicados, com subdivisão regional."""
    if region_code:
        return pt_holidays_lib.Portugal(years=years, subdiv=region_code)
    return pt_holidays_lib.Portugal(years=years)


async def sync_holidays(
    db: AsyncSession,
    org_id: int,
    academic_year: str,
    region_code: str | None,
) -> int:
    """Importa feriados nacionais/regionais para o calendário da escola.

    Remove todos os eventos AUTO existentes para o ano letivo e recria-os.
    Garante idempotência: pode ser chamado várias vezes sem duplicados.
    Retorna o número de feriados importados.
    """
    # 1. Determinar os anos calendário cobertos pelo ano letivo (ex: 2025/2026 → [2025, 2026])
    years = _parse_calendar_years(academic_year)

    # 2. Eliminar todos os events AUTO existentes para este (org, academic_year)
    await db.execute(
        delete(models.SchoolCalendarEvent).where(
            and_(
                models.SchoolCalendarEvent.org_id == org_id,
                models.SchoolCalendarEvent.academic_year == academic_year,
                models.SchoolCalendarEvent.source == models.CalendarEventSource.auto,
            )
        )
    )

    # 3. Obter feriados
    holiday_map = _get_pt_holidays(years, region_code)

    # 4. Criar novos eventos AUTO
    count = 0
    for holiday_date, holiday_name in sorted(holiday_map.items()):
        event = models.SchoolCalendarEvent(
            org_id=org_id,
            academic_year=academic_year,
            name=holiday_name,
            start_date=holiday_date,
            end_date=holiday_date,
            event_type=models.CalendarEventType.national_holiday,
            source=models.CalendarEventSource.auto,
        )
        db.add(event)
        count += 1

    await db.commit()
    return count


def _parse_calendar_years(academic_year: str) -> list[int]:
    """Extrai os dois anos de um academic_year no formato '2025/2026'."""
    parts = academic_year.split("/")
    if len(parts) == 2:
        try:
            return [int(parts[0]), int(parts[1])]
        except ValueError:
            pass
    # Fallback: tentar interpreter como ano único
    try:
        year = int(academic_year)
        return [year, year + 1]
    except ValueError:
        return []


def list_available_regions() -> list[str]:
    """Retorna a lista de subdivisões portuguesas suportadas pelo package holidays."""
    return sorted(pt_holidays_lib.Portugal.subdivisions)
