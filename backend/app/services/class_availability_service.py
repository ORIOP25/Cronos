"""Weekly availability of classes, scoped to the visible grid version.

A stored row carries a level different from NEUTRAL. A missing row means NEUTRAL
(D07), so the service only inserts meaningful rows and replaces the class grid in
the blocks of the grid version visible on ``on_date``.
"""

from datetime import date

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.core.exceptions import AppError
from app.models import ClassAvailability, PreferenceLevel
from app.schemas import AvailabilitySelfCreate
from app.services import grid_version_service
from app.services.scheduler_state_service import record_scheduler_change


def _availability_snapshot(rows) -> list[dict]:
    return sorted(
        ({"timeslot_id": int(row[0]), "score": int(row[1])} for row in rows),
        key=lambda item: item["timeslot_id"],
    )


async def _get_class(db: AsyncSession, class_id: int, organization_id: int) -> models.Class:
    db_class = await db.scalar(
        select(models.Class).where(
            models.Class.id == class_id,
            models.Class.organization_id == organization_id,
        )
    )
    if db_class is None:
        raise AppError(
            kind="not_found",
            code="resource_not_found",
            detail=f"Class {class_id} was not found in organization {organization_id}.",
        )
    return db_class


async def _class_is_scheduled(db: AsyncSession, organization_id: int, class_id: int) -> bool:
    assignment_id = await db.scalar(
        select(models.ClassSubjectLink.id)
        .where(
            models.ClassSubjectLink.organization_id == organization_id,
            models.ClassSubjectLink.class_id == class_id,
        )
        .limit(1)
    )
    return assignment_id is not None


async def _visible_blocks(
    db: AsyncSession, organization_id: int, on_date: date | None
) -> list[models.Timeslot]:
    resolved = await grid_version_service.resolve_grid(
        db,
        organization_id,
        on_date or await grid_version_service.school_today(db, organization_id),
    )
    return sorted(resolved.blocks, key=lambda ts: (ts.day_of_week, ts.start_time, ts.id))


async def _visible_rows(
    db: AsyncSession, organization_id: int, class_id: int, timeslot_ids: set[int]
) -> list[dict]:
    if not timeslot_ids:
        return []
    result = await db.execute(
        select(ClassAvailability.timeslot_id, ClassAvailability.score).where(
            ClassAvailability.organization_id == organization_id,
            ClassAvailability.class_id == class_id,
            ClassAvailability.timeslot_id.in_(timeslot_ids),
        )
    )
    return _availability_snapshot(result.all())


def _record_metadata(item_count: int, on_date: date | None) -> dict:
    return {"item_count": item_count, **({"on_date": on_date.isoformat()} if on_date else {})}


async def get_class_availability(
    db: AsyncSession,
    class_id: int,
    organization_id: int,
    on_date: date | None = None,
) -> list[dict]:
    """Read the class grid. A block without a row is NEUTRAL."""
    await _get_class(db, class_id, organization_id)
    blocks = await _visible_blocks(db, organization_id, on_date)
    rows = await db.execute(
        select(ClassAvailability.timeslot_id, ClassAvailability.score).where(
            ClassAvailability.organization_id == organization_id,
            ClassAvailability.class_id == class_id,
        )
    )
    scores = {int(timeslot_id): int(score) for timeslot_id, score in rows.all()}
    return [
        {
            "timeslot_id": block.id,
            "score": scores.get(block.id, PreferenceLevel.NEUTRAL.value),
        }
        for block in blocks
    ]


async def replace_class_availability(
    db: AsyncSession,
    class_id: int,
    availabilities: list[AvailabilitySelfCreate],
    organization_id: int,
    changed_by_membership_id: int | None = None,
    on_date: date | None = None,
) -> dict:
    """Replace the class grid in the visible version, keeping only non-NEUTRAL rows."""
    db_class = await _get_class(db, class_id, organization_id)
    if db_class.is_archived:
        raise AppError(
            kind="bad_request",
            code="bad_request",
            detail=f"Class {class_id} is archived and cannot change availability.",
        )
    active_resource = await _class_is_scheduled(db, organization_id, class_id)

    visible_ids = {block.id for block in await _visible_blocks(db, organization_id, on_date)}
    timeslot_ids = [item.timeslot_id for item in availabilities]
    if len(timeslot_ids) != len(set(timeslot_ids)):
        raise AppError(
            kind="bad_request",
            code="duplicate_timeslot",
            detail=f"Class {class_id} submitted duplicate timeslots.",
        )
    if set(timeslot_ids) != visible_ids:
        raise AppError(
            kind="bad_request",
            code="bad_request",
            detail=f"Class {class_id} submitted an invalid timeslot set.",
        )

    before = await _visible_rows(db, organization_id, class_id, visible_ids)
    await db.execute(
        delete(ClassAvailability).where(
            ClassAvailability.organization_id == organization_id,
            ClassAvailability.class_id == class_id,
            ClassAvailability.timeslot_id.in_(visible_ids),
        )
    )
    rows = [
        {
            "organization_id": organization_id,
            "class_id": class_id,
            "timeslot_id": item.timeslot_id,
            "score": item.score.value,
        }
        for item in availabilities
        if item.score.value != PreferenceLevel.NEUTRAL.value
    ]
    if rows:
        await db.execute(insert(ClassAvailability).values(rows))
    await record_scheduler_change(
        db,
        organization_id,
        entity_type="CLASS_AVAILABILITY",
        entity_id=class_id,
        operation=models.SchedulerStateChangeOperation.BULK_IMPORT,
        before=before,
        after=_availability_snapshot((row["timeslot_id"], row["score"]) for row in rows),
        changed_by_membership_id=changed_by_membership_id,
        metadata=_record_metadata(len(rows), on_date),
        active_resource=active_resource,
    )
    await db.flush()
    return {"status": "success", "count": len(rows)}


async def copy_class_availability(
    db: AsyncSession,
    class_id: int,
    target_class_ids: list[int],
    organization_id: int,
    changed_by_membership_id: int | None = None,
    on_date: date | None = None,
) -> dict:
    """Copy the origin grid to every target after validating all of them first."""
    await _get_class(db, class_id, organization_id)
    if len(target_class_ids) != len(set(target_class_ids)):
        raise AppError(
            kind="bad_request",
            code="bad_request",
            detail="The target class list contains duplicates.",
        )
    if class_id in target_class_ids:
        raise AppError(
            kind="bad_request",
            code="bad_request",
            detail=f"The origin class {class_id} cannot be a copy target.",
        )

    targets = (
        (
            await db.execute(
                select(models.Class).where(
                    models.Class.organization_id == organization_id,
                    models.Class.id.in_(target_class_ids),
                )
            )
        )
        .scalars()
        .all()
    )
    targets_by_id = {target.id: target for target in targets}
    for target_id in target_class_ids:
        target = targets_by_id.get(target_id)
        if target is None:
            raise AppError(
                kind="not_found",
                code="resource_not_found",
                detail=f"Class {target_id} was not found in organization {organization_id}.",
            )
        if target.is_archived:
            raise AppError(
                kind="bad_request",
                code="bad_request",
                detail=f"Class {target_id} is archived and cannot change availability.",
            )

    blocks = await _visible_blocks(db, organization_id, on_date)
    source_rows = await db.execute(
        select(ClassAvailability.timeslot_id, ClassAvailability.score).where(
            ClassAvailability.organization_id == organization_id,
            ClassAvailability.class_id == class_id,
        )
    )
    scores = {int(timeslot_id): int(score) for timeslot_id, score in source_rows.all()}
    source_payload = [
        AvailabilitySelfCreate(
            timeslot_id=block.id,
            score=PreferenceLevel(scores.get(block.id, PreferenceLevel.NEUTRAL.value)),
        )
        for block in blocks
    ]

    updated_class_ids: list[int] = []
    for target_id in target_class_ids:
        await replace_class_availability(
            db,
            target_id,
            source_payload,
            organization_id,
            changed_by_membership_id=changed_by_membership_id,
            on_date=on_date,
        )
        updated_class_ids.append(target_id)
    return {"updated_class_ids": updated_class_ids}
