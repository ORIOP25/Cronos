"""Serviço para OrganizationSettings, OrganizationGridSettings e SchoolCalendarEvent.

Responsável por:
  - CRUD de configurações da escola (OrganizationSettings)
  - CRUD de configurações de grelha (OrganizationGridSettings)
  - CRUD de eventos do calendário escolar (SchoolCalendarEvent)
  - Importação automática de feriados via package `holidays`
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Sequence

import holidays as pt_holidays_lib
from sqlalchemy import select, and_, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas

SETTINGS_NOT_FOUND = "Configurações da escola não encontradas"

# ==========================================
#  ORGANIZATION SETTINGS
# ==========================================

async def get_settings(db: AsyncSession, org_id: int) -> models.OrganizationSettings | None:
    """Retorna a configuração única da escola."""
    result = await db.execute(
        select(models.OrganizationSettings).where(
            models.OrganizationSettings.organization_id == org_id
        )
    )
    return result.scalar_one_or_none()

async def upsert_settings(
    db: AsyncSession, org_id: int, data: schemas.OrganizationSettingsUpsert
) -> models.OrganizationSettings:
    """Cria ou actualiza o registo único de configuração."""
    existing = await get_settings(db, org_id)
    if existing:
        if data.school_start_date is not None:
            existing.school_start_date = data.school_start_date
        if data.school_target_end_date is not None:
            existing.school_target_end_date = data.school_target_end_date
        if data.school_hard_end_date is not None:
            existing.school_hard_end_date = data.school_hard_end_date
        if data.repair_stability_window_days is not None:
            existing.repair_stability_window_days = data.repair_stability_window_days
        await db.commit()
        await db.refresh(existing)
        return existing

    new_settings = models.OrganizationSettings(
        organization_id=org_id,
        school_start_date=data.school_start_date,
        school_target_end_date=data.school_target_end_date,
        school_hard_end_date=data.school_hard_end_date,
        repair_stability_window_days=data.repair_stability_window_days,
    )
    db.add(new_settings)
    await db.commit()
    await db.refresh(new_settings)
    return new_settings

# ==========================================
#  ORGANIZATION GRID SETTINGS
# ==========================================

async def get_grid_settings(db: AsyncSession, org_id: int) -> models.OrganizationGridSettings | None:
    """Retorna as configurações únicas da grelha da escola."""
    result = await db.execute(
        select(models.OrganizationGridSettings).where(
            models.OrganizationGridSettings.organization_id == org_id
        )
    )
    return result.scalar_one_or_none()

async def upsert_grid_settings(
    db: AsyncSession, org_id: int, data: schemas.OrganizationGridSettingsUpsert
) -> models.OrganizationGridSettings:
    """Cria ou actualiza as configurações únicas da grelha."""
    existing = await get_grid_settings(db, org_id)
    if existing:
        if data.lunch_window_start is not None:
            existing.lunch_window_start = data.lunch_window_start
        if data.lunch_window_end is not None:
            existing.lunch_window_end = data.lunch_window_end
        if data.lunch_min_duration_minutes is not None:
            existing.lunch_min_duration_minutes = data.lunch_min_duration_minutes
        await db.commit()
        await db.refresh(existing)
        return existing

    new_settings = models.OrganizationGridSettings(
        organization_id=org_id,
        lunch_window_start=data.lunch_window_start,
        lunch_window_end=data.lunch_window_end,
        lunch_min_duration_minutes=data.lunch_min_duration_minutes,
    )
    db.add(new_settings)
    await db.commit()
    await db.refresh(new_settings)
    return new_settings


# ==========================================
#  SCHOOL CALENDAR EVENTS
# ==========================================

async def list_calendar_events(
    db: AsyncSession,
    org_id: int,
    from_date: date | None = None,
    to_date: date | None = None,
) -> Sequence[models.SchoolCalendarEvent]:
    """Lista eventos do calendário, opcionalmente filtrados por intervalo de datas."""
    query = select(models.SchoolCalendarEvent).where(
        models.SchoolCalendarEvent.organization_id == org_id
    )
    if from_date:
        query = query.where(models.SchoolCalendarEvent.end_date >= from_date)
    if to_date:
        query = query.where(models.SchoolCalendarEvent.start_date <= to_date)
    query = query.order_by(models.SchoolCalendarEvent.start_date)
    result = await db.execute(query)
    return result.scalars().all()


async def create_calendar_event(
    db: AsyncSession, org_id: int, data: schemas.SchoolCalendarEventCreate
) -> models.SchoolCalendarEvent:
    settings = await get_settings(db, org_id)
    if settings:
        min_date = settings.school_start_date
        max_date = settings.school_hard_end_date
        
        if min_date and (data.start_date < min_date or data.end_date < min_date):
            raise ValueError(f"Evento fora do intervalo permitido. O calendário escolar começa a {min_date.isoformat()}.")
        if max_date and (data.start_date > max_date or data.end_date > max_date):
            raise ValueError(f"Evento fora do intervalo permitido. O calendário escolar termina a {max_date.isoformat()}.")

    event = models.SchoolCalendarEvent(
        organization_id=org_id,
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
                models.SchoolCalendarEvent.organization_id == org_id,
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

def _get_pt_holidays(years: list[int]) -> dict[date, str]:
    """Obtém feriados de Portugal para os anos indicados, sem subdivisão regional."""
    return pt_holidays_lib.Portugal(years=years)


async def sync_holidays(
    db: AsyncSession,
    org_id: int,
) -> int:
    """Importa feriados nacionais para o calendário da escola.

    Remove todos os eventos AUTO existentes e recria-os.
    Garante idempotência: pode ser chamado várias vezes sem duplicados.
    Retorna o número de feriados importados.
    """
    settings = await get_settings(db, org_id)
    if not settings or not settings.school_start_date:
        current_year = date.today().year
        years = [current_year, current_year + 1]
    else:
        start_year = settings.school_start_date.year
        end_year = settings.school_hard_end_date.year if settings.school_hard_end_date else start_year + 1
        years = list(range(start_year, end_year + 1))

    await db.execute(
        delete(models.SchoolCalendarEvent).where(
            and_(
                models.SchoolCalendarEvent.organization_id == org_id,
                models.SchoolCalendarEvent.source == models.CalendarEventSource.auto,
            )
        )
    )

    holiday_map = _get_pt_holidays(years)

    # Filtrar feriados pelo intervalo configurado [start_date, hard_end_date]
    min_date = settings.school_start_date if settings and settings.school_start_date else None
    max_date = settings.school_hard_end_date if settings and settings.school_hard_end_date else None

    count = 0
    for holiday_date, holiday_name in sorted(holiday_map.items()):
        if min_date and holiday_date < min_date:
            continue
        if max_date and holiday_date > max_date:
            continue

        event = models.SchoolCalendarEvent(
            organization_id=org_id,
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

# ==========================================
#  SOFT-RESET DO ANO LETIVO
# ==========================================

async def soft_reset_year(db: AsyncSession, org_id: int) -> bool:
    """Limpa todas as instâncias dinâmicas e reinicia o progresso,
    mantendo professores, turmas, cursos, disciplinas, módulos e salas.
    """
    # 1. Apagar Timesheets semanais
    await db.execute(delete(models.TeacherWeeklyTimesheet).where(models.TeacherWeeklyTimesheet.organization_id == org_id))

    # 2. Apagar Eventos Operacionais e Ocorrências
    await db.execute(delete(models.OccurrenceOperationalEvent).where(models.OccurrenceOperationalEvent.organization_id == org_id))
    await db.execute(delete(models.TeacherEndpointOperationalEvent).where(models.TeacherEndpointOperationalEvent.organization_id == org_id))
    await db.execute(delete(models.LessonOccurrence).where(models.LessonOccurrence.organization_id == org_id))

    # 3. Apagar Substituições (não têm org_id direto, usar lesson_id como pivot)
    await db.execute(
        delete(models.Substitution).where(
            models.Substitution.lesson_id.in_(
                select(models.Lesson.id).where(models.Lesson.organization_id == org_id)
            )
        )
    )

    # 4. Apagar Registos de Aulas (LessonLog tem org_id direto)
    await db.execute(delete(models.LessonLog).where(models.LessonLog.organization_id == org_id))

    # 5. Apagar ScheduleOutput (blocos gerados pelo Solver)
    await db.execute(delete(models.ScheduleOutput).where(models.ScheduleOutput.organization_id == org_id))

    # 6. Resetar ClassProgress (hours_completed = 0.0) — preserva a estrutura de turmas/módulos
    await db.execute(
        update(models.ClassProgress)
        .where(
            models.ClassProgress.class_id.in_(
                select(models.Class.id).where(models.Class.organization_id == org_id)
            )
        )
        .values(
            hours_completed=0.0,
            hours_debt=0.0,
            is_completed=False,
            updated_at=datetime.now(timezone.utc)
        )
    )

    await db.commit()
    return True
