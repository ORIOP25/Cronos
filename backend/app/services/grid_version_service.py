"""Tenant-scoped resolution and persistence of date-effective grid versions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.scheduler.domain.grid_versions import (
    GridVersionRef,
    build_grid_configuration,
    select_effective_grid_version,
)

GridSignature = tuple[int, time, time]


@dataclass(frozen=True)
class ResolvedGrid:
    version: models.GridVersion | None
    blocks: tuple[models.Timeslot, ...]


async def school_today(db: AsyncSession, organization_id: int) -> date:
    """Today in the school's own timezone (falls back to the server date)."""
    timezone_name = await db.scalar(
        select(models.SchedulerSchoolYear.timezone)
        .where(
            models.SchedulerSchoolYear.organization_id == organization_id,
            models.SchedulerSchoolYear.is_active.is_(True),
        )
        .limit(1)
    )
    if not timezone_name:
        return date.today()
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return date.today()
    return datetime.now(zone).date()


async def list_grid_versions(db: AsyncSession, organization_id: int) -> list[models.GridVersion]:
    result = await db.execute(
        select(models.GridVersion)
        .where(models.GridVersion.organization_id == organization_id)
        .order_by(models.GridVersion.effective_date, models.GridVersion.id)
    )
    return list(result.scalars().all())


async def get_grid_version(
    db: AsyncSession, organization_id: int, version_id: int
) -> models.GridVersion | None:
    return await db.scalar(
        select(models.GridVersion).where(
            models.GridVersion.organization_id == organization_id,
            models.GridVersion.id == version_id,
        )
    )


async def resolve_grid_version(
    db: AsyncSession,
    organization_id: int,
    on_date: date,
    pending_version_id: int | None = None,
) -> models.GridVersion | None:
    """Return the version valid on ``on_date`` (or the referenced pending one)."""
    versions = await list_grid_versions(db, organization_id)
    if not versions:
        return None
    references = [
        GridVersionRef(
            id=version.id,
            effective_date=version.effective_date,
            state=version.state.value,
        )
        for version in versions
    ]
    selected_id = select_effective_grid_version(references, on_date, pending_version_id)
    if selected_id is None:
        return None
    return next(version for version in versions if version.id == selected_id)


async def _blocks_of_version(
    db: AsyncSession, organization_id: int, version_id: int
) -> list[models.Timeslot]:
    result = await db.execute(
        select(models.Timeslot)
        .where(
            models.Timeslot.organization_id == organization_id,
            models.Timeslot.grid_version_id == version_id,
        )
        .order_by(models.Timeslot.day_of_week, models.Timeslot.start_time)
    )
    return list(result.scalars().all())


async def get_version_blocks(
    db: AsyncSession, organization_id: int, version_id: int
) -> tuple[models.Timeslot, ...]:
    """Blocks stored for an explicit version, regardless of its state."""
    return tuple(await _blocks_of_version(db, organization_id, version_id))


async def _unversioned_blocks(db: AsyncSession, organization_id: int) -> list[models.Timeslot]:
    result = await db.execute(
        select(models.Timeslot)
        .where(
            models.Timeslot.organization_id == organization_id,
            models.Timeslot.grid_version_id.is_(None),
        )
        .order_by(models.Timeslot.day_of_week, models.Timeslot.start_time)
    )
    return list(result.scalars().all())


async def resolve_grid(
    db: AsyncSession,
    organization_id: int,
    on_date: date,
    pending_version_id: int | None = None,
) -> ResolvedGrid:
    """Resolve the version and its blocks for a date.

    A pending version never falls back to unversioned blocks: only the job that
    references it can use it, and an empty proposal must fail explicitly.
    """
    version = await resolve_grid_version(
        db, organization_id, on_date, pending_version_id=pending_version_id
    )
    if version is not None:
        blocks = await _blocks_of_version(db, organization_id, version.id)
        if not blocks and pending_version_id is None:
            # ponytail: legacy null-version rows belong to the initial version.
            blocks = await _unversioned_blocks(db, organization_id)
        return ResolvedGrid(version=version, blocks=tuple(blocks))
    return ResolvedGrid(version=None, blocks=tuple(await _unversioned_blocks(db, organization_id)))


async def _default_effective_date(db: AsyncSession, organization_id: int) -> date:
    start_date = await db.scalar(
        select(models.OrganizationSettings.school_start_date).where(
            models.OrganizationSettings.organization_id == organization_id
        )
    )
    return start_date or date.today()


async def get_active_grid_version(
    db: AsyncSession, organization_id: int
) -> models.GridVersion | None:
    versions = await list_grid_versions(db, organization_id)
    actives = [version for version in versions if version.state == models.GridVersionState.ACTIVE]
    if not actives:
        return None
    return max(actives, key=lambda version: (version.effective_date, version.id))


async def active_grid_configuration(db: AsyncSession, organization_id: int) -> dict:
    """Configuration of the visible grid, from the version or legacy blocks."""
    today = await school_today(db, organization_id)
    resolved = await resolve_grid(db, organization_id, today)
    version = resolved.version
    base = {
        "version_id": version.id if version is not None else None,
        "effective_date": version.effective_date if version is not None else None,
        "state": version.state.value if version is not None else None,
    }
    if version is not None and version.configuration_json is not None:
        return {**base, "configuration": version.configuration_json, "source": "VERSION"}
    if resolved.blocks:
        configuration = build_grid_configuration(
            tuple(
                (block.day_of_week, block.start_time, block.end_time) for block in resolved.blocks
            )
        )
        if configuration is not None:
            return {**base, "configuration": configuration, "source": "BLOCKS"}
    return {**base, "configuration": None, "source": "NONE"}


async def week_grid_versions(
    db: AsyncSession,
    organization_id: int,
    from_date: date,
    to_date: date,
) -> dict:
    """Per-date blocks for a week, using the version valid on each date.

    Returns one entry per date plus the first school date whose version differs
    from the previous school date inside the range. Pending versions never
    appear here; only ACTIVE versions (and legacy unversioned blocks).
    """
    if from_date > to_date:
        raise ValueError("O intervalo de datas é inválido.")
    if (to_date - from_date).days > 31:
        raise ValueError("O intervalo não pode exceder 31 dias.")

    versions = await list_grid_versions(db, organization_id)
    references = [
        GridVersionRef(
            id=version.id,
            effective_date=version.effective_date,
            state=version.state.value,
        )
        for version in versions
    ]
    blocks_by_version: dict[int, tuple[models.Timeslot, ...]] = {}
    unversioned: tuple[models.Timeslot, ...] | None = None
    days: list[dict] = []
    last_school_version_id: int | None = None
    transition_date: date | None = None
    current = from_date
    while current <= to_date:
        selected_id = select_effective_grid_version(references, current)
        version = (
            next((item for item in versions if item.id == selected_id), None)
            if selected_id is not None
            else None
        )
        if version is not None:
            if version.id not in blocks_by_version:
                blocks_by_version[version.id] = tuple(
                    await get_version_blocks(db, organization_id, version.id)
                )
            blocks = blocks_by_version[version.id]
        else:
            blocks = ()
        if version is None or not blocks:
            if unversioned is None:
                unversioned = tuple(await _unversioned_blocks(db, organization_id))
            blocks = unversioned

        if blocks:
            if last_school_version_id is not None and selected_id != last_school_version_id:
                transition_date = transition_date or current
            last_school_version_id = selected_id
        days.append(
            {
                "date": current,
                "version_id": None if version is None else version.id,
                "effective_date": None if version is None else version.effective_date,
                "blocks": [
                    {
                        "id": block.id,
                        "day_of_week": block.day_of_week,
                        "start_time": block.start_time,
                        "end_time": block.end_time,
                    }
                    for block in blocks
                    if block.day_of_week == current.weekday()
                ],
            }
        )
        current += timedelta(days=1)
    return {"days": days, "transition_date": transition_date}


async def ensure_active_grid_version(
    db: AsyncSession,
    organization_id: int,
    effective_date: date | None = None,
) -> models.GridVersion:
    """Return the active version, creating the initial one when absent."""
    version = await get_active_grid_version(db, organization_id)
    if version is not None:
        return version
    version = models.GridVersion(
        organization_id=organization_id,
        effective_date=effective_date or await _default_effective_date(db, organization_id),
        state=models.GridVersionState.ACTIVE,
        configuration_json=None,
    )
    db.add(version)
    await db.flush()
    return version


async def activate_pending_grid_version(
    db: AsyncSession, organization_id: int, version_id: int
) -> models.GridVersion:
    """Promote the proposal to the active grid inside the caller transaction."""
    version = await get_grid_version(db, organization_id, version_id)
    if version is None:
        raise ValueError("Grid version was not found.")
    if version.state != models.GridVersionState.PENDING:
        raise ValueError("Only a pending grid version can be activated.")
    version.state = models.GridVersionState.ACTIVE
    await db.flush()
    return version


async def reject_pending_grid_version(
    db: AsyncSession, organization_id: int, version_id: int
) -> models.GridVersion | None:
    """Mark the proposal as rejected without deleting its blocks."""
    version = await get_grid_version(db, organization_id, version_id)
    if version is None or version.state == models.GridVersionState.ACTIVE:
        return None
    version.state = models.GridVersionState.REJECTED
    await db.flush()
    return version


def configuration_from_bulk(settings: schemas.TimeslotBulkCreate) -> dict:
    """Build the stored configuration payload for a bulk grid command."""
    return {
        "opening_time": settings.start_time.strftime("%H:%M"),
        "closing_time": settings.end_time.strftime("%H:%M"),
        "slot_duration_minutes": settings.slot_duration_minutes,
        "break_duration_minutes": settings.break_duration_minutes,
        "break_overrides": [
            {
                "after_slot": override.after_slot,
                "duration_minutes": override.duration_minutes,
            }
            for override in settings.break_overrides
        ],
        "days_of_week": sorted(settings.days_of_week),
    }
