"""Serviço para OrganizationSettings, OrganizationGridSettings e SchoolCalendarEvent.

Responsável por:
  - CRUD de configurações da escola (OrganizationSettings)
  - CRUD de configurações de grelha (OrganizationGridSettings)
  - CRUD de eventos do calendário escolar (SchoolCalendarEvent)
  - Importação automática de feriados via package `holidays`
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import holidays as pt_holidays_lib
import structlog
from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.services import timeslot_service
from app.services.scheduler_state_service import (
    SchedulerStateService,
    record_scheduler_change,
)

SETTINGS_NOT_FOUND = "Configurações da escola não encontradas"
logger = structlog.get_logger(__name__)


def _calendar_settings_snapshot(settings: models.OrganizationSettings) -> dict:
    return {
        "start_date": settings.school_start_date,
        "hard_end_date": settings.school_hard_end_date,
    }


def _repair_policy_snapshot(settings: models.OrganizationSettings) -> dict:
    return {"stability_window_days": settings.repair_stability_window_days}


def _grid_settings_snapshot(settings: models.OrganizationGridSettings) -> dict:
    return {
        "lunch_window_start": settings.lunch_window_start,
        "lunch_window_end": settings.lunch_window_end,
        "lunch_min_duration_minutes": settings.lunch_min_duration_minutes,
    }


def _calendar_event_snapshot(event: models.SchoolCalendarEvent) -> dict:
    return {
        "name": event.name,
        "start_date": event.start_date,
        "end_date": event.end_date,
        "event_type": event.event_type,
        "source": event.source,
    }


def _sorted_calendar_snapshots(events) -> list[dict]:
    return sorted(
        (_calendar_event_snapshot(event) for event in events),
        key=lambda item: (item["start_date"], item["end_date"], item["name"]),
    )


async def _sync_school_year_and_record_settings_changes(
    db: AsyncSession,
    organization_id: int,
    settings: models.OrganizationSettings,
    *,
    before_calendar: dict | None,
    before_policy: dict | None,
    changed_by_membership_id: int | None,
) -> None:
    state_service = SchedulerStateService(db)
    if settings.school_start_date is not None and settings.school_hard_end_date is not None:
        school_year, _ = await state_service.get_or_create_active_state(
            organization_id,
            start_date=settings.school_start_date,
            hard_end_date=settings.school_hard_end_date,
        )
        school_year.start_date = settings.school_start_date
        school_year.hard_end_date = settings.school_hard_end_date

    operation = (
        models.SchedulerStateChangeOperation.CREATE
        if before_calendar is None
        else models.SchedulerStateChangeOperation.UPDATE
    )
    await record_scheduler_change(
        db,
        organization_id,
        entity_type="SCHOOL_YEAR_CALENDAR",
        entity_id=settings.id,
        operation=operation,
        before=before_calendar,
        after=_calendar_settings_snapshot(settings),
        changed_by_membership_id=changed_by_membership_id,
    )
    await record_scheduler_change(
        db,
        organization_id,
        entity_type="REPAIR_POLICY",
        entity_id=settings.id,
        operation=operation,
        before=before_policy,
        after=_repair_policy_snapshot(settings),
        changed_by_membership_id=changed_by_membership_id,
        repair_policy_change=True,
    )


# ==========================================
#  ORGANIZATION SETTINGS
# ==========================================


async def get_settings(
    db: AsyncSession, organization_id: int
) -> models.OrganizationSettings | None:
    """Retorna a configuração única da escola."""
    result = await db.execute(
        select(models.OrganizationSettings).where(
            models.OrganizationSettings.organization_id == organization_id
        )
    )
    return result.scalar_one_or_none()


async def upsert_settings(
    db: AsyncSession,
    organization_id: int,
    data: schemas.OrganizationSettingsUpsert,
    changed_by_membership_id: int | None = None,
) -> models.OrganizationSettings:
    """Cria ou actualiza o registo único de configuração."""
    existing = await get_settings(db, organization_id)
    if existing:
        before_calendar = _calendar_settings_snapshot(existing)
        before_policy = _repair_policy_snapshot(existing)
        next_start_date = (
            data.school_start_date
            if data.school_start_date is not None
            else existing.school_start_date
        )
        next_hard_end_date = (
            data.school_hard_end_date
            if data.school_hard_end_date is not None
            else existing.school_hard_end_date
        )
        schemas.OrganizationSettingsUpsert._validate_school_dates(
            next_start_date,
            next_hard_end_date,
        )

        if data.school_start_date is not None:
            existing.school_start_date = data.school_start_date
        if data.school_hard_end_date is not None:
            existing.school_hard_end_date = data.school_hard_end_date
        if data.repair_stability_window_days is not None:
            existing.repair_stability_window_days = data.repair_stability_window_days
        await db.flush()
        await _sync_school_year_and_record_settings_changes(
            db,
            organization_id,
            existing,
            before_calendar=before_calendar,
            before_policy=before_policy,
            changed_by_membership_id=changed_by_membership_id,
        )
        await db.flush()
        await db.refresh(existing)
        return existing

    new_settings = models.OrganizationSettings(
        organization_id=organization_id,
        school_start_date=data.school_start_date,
        school_hard_end_date=data.school_hard_end_date,
        repair_stability_window_days=data.repair_stability_window_days,
        auto_confirm_enabled=False,
    )
    db.add(new_settings)
    await db.flush()
    await _sync_school_year_and_record_settings_changes(
        db,
        organization_id,
        new_settings,
        before_calendar=None,
        before_policy=None,
        changed_by_membership_id=changed_by_membership_id,
    )
    await db.flush()
    await db.refresh(new_settings)
    return new_settings


# ==========================================
#  ORGANIZATION GRID SETTINGS
# ==========================================


async def get_grid_settings(
    db: AsyncSession, organization_id: int
) -> models.OrganizationGridSettings | None:
    """Retorna as configurações únicas da grelha da escola."""
    result = await db.execute(
        select(models.OrganizationGridSettings).where(
            models.OrganizationGridSettings.organization_id == organization_id
        )
    )
    return result.scalar_one_or_none()


async def upsert_grid_settings(
    db: AsyncSession,
    organization_id: int,
    data: schemas.OrganizationGridSettingsUpsert,
    changed_by_membership_id: int | None = None,
) -> models.OrganizationGridSettings:
    """Legacy transactional wrapper for lunch settings."""
    try:
        settings, _ = await prepare_grid_settings(
            db,
            organization_id,
            data,
            changed_by_membership_id=changed_by_membership_id,
        )
        await db.flush()
        await db.refresh(settings)
        return settings
    except Exception:
        raise


async def prepare_grid_settings(
    db: AsyncSession,
    organization_id: int,
    data: schemas.OrganizationGridSettingsUpsert,
    changed_by_membership_id: int | None = None,
) -> tuple[models.OrganizationGridSettings, bool]:
    """Prepare lunch settings and audit without committing."""
    existing = await get_grid_settings(db, organization_id)
    if existing:
        before = _grid_settings_snapshot(existing)
        next_lunch_start = (
            data.lunch_window_start
            if data.lunch_window_start is not None
            else existing.lunch_window_start
        )
        next_lunch_end = (
            data.lunch_window_end
            if data.lunch_window_end is not None
            else existing.lunch_window_end
        )
        next_lunch_min = (
            data.lunch_min_duration_minutes
            if data.lunch_min_duration_minutes is not None
            else existing.lunch_min_duration_minutes
        )
        schemas.OrganizationGridSettingsUpsert._validate_lunch_inputs(
            next_lunch_start,
            next_lunch_end,
            next_lunch_min,
        )

        if data.lunch_window_start is not None:
            existing.lunch_window_start = data.lunch_window_start
        if data.lunch_window_end is not None:
            existing.lunch_window_end = data.lunch_window_end
        if data.lunch_min_duration_minutes is not None:
            existing.lunch_min_duration_minutes = data.lunch_min_duration_minutes
        after = _grid_settings_snapshot(existing)
        if before == after:
            return existing, False
        await record_scheduler_change(
            db,
            organization_id,
            entity_type="LUNCH_SETTINGS",
            entity_id=existing.id,
            operation=models.SchedulerStateChangeOperation.UPDATE,
            before=before,
            after=after,
            changed_by_membership_id=changed_by_membership_id,
        )
        await db.flush()
        return existing, True

    new_settings = models.OrganizationGridSettings(
        organization_id=organization_id,
        lunch_window_start=data.lunch_window_start,
        lunch_window_end=data.lunch_window_end,
        lunch_min_duration_minutes=data.lunch_min_duration_minutes,
    )
    db.add(new_settings)
    await db.flush()
    await record_scheduler_change(
        db,
        organization_id,
        entity_type="LUNCH_SETTINGS",
        entity_id=new_settings.id,
        operation=models.SchedulerStateChangeOperation.CREATE,
        before=None,
        after=_grid_settings_snapshot(new_settings),
        changed_by_membership_id=changed_by_membership_id,
    )
    await db.flush()
    return new_settings, True


async def save_and_regenerate_grid(
    db: AsyncSession,
    organization_id: int,
    command: schemas.GridConfigurationCommand,
    changed_by_membership_id: int,
) -> schemas.GridConfigurationResponse:
    """Commit lunch settings and a protected timetable-grid replacement atomically."""
    try:
        plan = await timeslot_service.preflight_grid_regeneration(
            db,
            command.timeslots,
            organization_id,
            changed_by_membership_id,
        )
        _, settings_changed = await prepare_grid_settings(
            db,
            organization_id,
            command.grid_settings,
            changed_by_membership_id,
        )
        generated_count = await timeslot_service.apply_grid_regeneration(
            db,
            plan,
            changed_by_membership_id,
        )
        await db.flush()
    except Exception:
        raise

    changed = settings_changed or plan.changed
    logger.info(
        "grid_regeneration_committed",
        organization_id=organization_id,
        actor_membership_id=changed_by_membership_id,
        previous_count=len(plan.before_grid),
        generated_count=generated_count,
        changed=changed,
        grid_regenerated=plan.changed,
    )
    return schemas.GridConfigurationResponse(
        message=(
            "Grelha configurada e regenerada com sucesso."
            if changed
            else "A configuração da grelha já estava atualizada."
        ),
        generated_count=generated_count,
        changed=changed,
        grid_regenerated=plan.changed,
    )


# ==========================================
#  SCHOOL CALENDAR EVENTS
# ==========================================


async def list_calendar_events(
    db: AsyncSession,
    organization_id: int,
    from_date: date | None = None,
    to_date: date | None = None,
) -> Sequence[models.SchoolCalendarEvent]:
    """Lista eventos do calendário, opcionalmente filtrados por intervalo de datas."""
    query = select(models.SchoolCalendarEvent).where(
        models.SchoolCalendarEvent.organization_id == organization_id
    )
    if from_date:
        query = query.where(models.SchoolCalendarEvent.end_date >= from_date)
    if to_date:
        query = query.where(models.SchoolCalendarEvent.start_date <= to_date)
    query = query.order_by(models.SchoolCalendarEvent.start_date)
    result = await db.execute(query)
    return result.scalars().all()


async def create_calendar_event(
    db: AsyncSession,
    organization_id: int,
    data: schemas.SchoolCalendarEventCreate,
    changed_by_membership_id: int | None = None,
) -> models.SchoolCalendarEvent:
    settings = await get_settings(db, organization_id)
    if settings:
        min_date = settings.school_start_date
        max_date = settings.school_hard_end_date

        if min_date and (data.start_date < min_date or data.end_date < min_date):
            raise ValueError(
                f"Evento fora do intervalo permitido. O calendário escolar começa a {min_date.isoformat()}."
            )
        if max_date and (data.start_date > max_date or data.end_date > max_date):
            raise ValueError(
                f"Evento fora do intervalo permitido. O calendário escolar termina a {max_date.isoformat()}."
            )

    event = models.SchoolCalendarEvent(
        organization_id=organization_id,
        name=data.name,
        start_date=data.start_date,
        end_date=data.end_date,
        event_type=data.event_type,
        source=models.CalendarEventSource.manual,
    )
    db.add(event)
    await db.flush()
    await record_scheduler_change(
        db,
        organization_id,
        entity_type="CALENDAR_EVENT",
        entity_id=event.id,
        operation=models.SchedulerStateChangeOperation.CREATE,
        before=None,
        after=_calendar_event_snapshot(event),
        changed_by_membership_id=changed_by_membership_id,
    )
    await db.flush()
    await db.refresh(event)
    return event


async def delete_calendar_event(
    db: AsyncSession,
    organization_id: int,
    event_id: int,
    changed_by_membership_id: int | None = None,
) -> bool:
    result = await db.execute(
        select(models.SchoolCalendarEvent).where(
            and_(
                models.SchoolCalendarEvent.id == event_id,
                models.SchoolCalendarEvent.organization_id == organization_id,
            )
        )
    )
    event = result.scalar_one_or_none()
    if not event:
        return False
    before = _calendar_event_snapshot(event)
    await db.delete(event)
    await record_scheduler_change(
        db,
        organization_id,
        entity_type="CALENDAR_EVENT",
        entity_id=event.id,
        operation=models.SchedulerStateChangeOperation.DELETE,
        before=before,
        after=None,
        changed_by_membership_id=changed_by_membership_id,
    )
    await db.flush()
    return True


# ==========================================
#  IMPORTAÇÃO DE FERIADOS (via package `holidays`)
# ==========================================


def _get_pt_holidays(years: list[int]) -> dict[date, str]:
    """Obtém feriados de Portugal para os anos indicados, sem subdivisão regional."""
    return pt_holidays_lib.Portugal(years=years)


async def sync_holidays(
    db: AsyncSession,
    organization_id: int,
    changed_by_membership_id: int | None = None,
) -> int:
    """Importa feriados nacionais para o calendário da escola.

    Remove todos os eventos AUTO existentes e recria-os.
    Garante idempotência: pode ser chamado várias vezes sem duplicados.
    Retorna o número de feriados importados.
    """
    settings = await get_settings(db, organization_id)
    if not settings or not settings.school_start_date:
        current_year = date.today().year
        years = [current_year, current_year + 1]
    else:
        start_year = settings.school_start_date.year
        end_year = (
            settings.school_hard_end_date.year if settings.school_hard_end_date else start_year + 1
        )
        years = list(range(start_year, end_year + 1))

    existing_auto_events = await db.scalars(
        select(models.SchoolCalendarEvent).where(
            models.SchoolCalendarEvent.organization_id == organization_id,
            models.SchoolCalendarEvent.source == models.CalendarEventSource.auto,
        )
    )
    before = _sorted_calendar_snapshots(existing_auto_events.all())
    await db.execute(
        delete(models.SchoolCalendarEvent).where(
            and_(
                models.SchoolCalendarEvent.organization_id == organization_id,
                models.SchoolCalendarEvent.source == models.CalendarEventSource.auto,
            )
        )
    )

    holiday_map = _get_pt_holidays(years)

    # Filtrar feriados pelo intervalo configurado [start_date, hard_end_date]
    min_date = settings.school_start_date if settings and settings.school_start_date else None
    max_date = settings.school_hard_end_date if settings and settings.school_hard_end_date else None

    count = 0
    created_events: list[models.SchoolCalendarEvent] = []
    for holiday_date, holiday_name in sorted(holiday_map.items()):
        if min_date and holiday_date < min_date:
            continue
        if max_date and holiday_date > max_date:
            continue

        event = models.SchoolCalendarEvent(
            organization_id=organization_id,
            name=holiday_name,
            start_date=holiday_date,
            end_date=holiday_date,
            event_type=models.CalendarEventType.national_holiday,
            source=models.CalendarEventSource.auto,
        )
        db.add(event)
        created_events.append(event)
        count += 1

    await db.flush()
    await record_scheduler_change(
        db,
        organization_id,
        entity_type="CALENDAR_EVENT",
        entity_id=None,
        operation=models.SchedulerStateChangeOperation.BULK_IMPORT,
        before=before,
        after=_sorted_calendar_snapshots(created_events),
        changed_by_membership_id=changed_by_membership_id,
        metadata={"imported_count": count, "source": "AUTO"},
    )
    await db.flush()
    return count
