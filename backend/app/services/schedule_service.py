from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app import models, schemas
from app.services import grid_version_service
from app.services.scheduler_state_service import record_scheduler_change


class ConstraintSemanticValidationError(ValueError):
    """A scheduler constraint references unavailable tenant data."""


# ==========================================
#  ASYNC (API / FRONTEND)
# ==========================================


# --- TIMESLOTS ---
async def get_timeslots_by_org(db: AsyncSession, organization_id: int):
    resolved = await grid_version_service.resolve_grid(
        db,
        organization_id,
        await grid_version_service.school_today(db, organization_id),
    )
    return list(resolved.blocks)


async def create_timeslot(
    db: AsyncSession,
    item: schemas.TimeslotCreate,
    organization_id: int,
    changed_by_membership_id: int | None = None,
):
    # O item.model_dump() já vai ter 'start_time' como objeto time.
    version = await grid_version_service.ensure_active_grid_version(db, organization_id)
    db_item = models.Timeslot(
        **item.model_dump(),
        organization_id=organization_id,
        grid_version_id=version.id,
    )
    db.add(db_item)
    await db.flush()
    await record_scheduler_change(
        db,
        organization_id,
        entity_type="TIMESLOT",
        entity_id=db_item.id,
        operation=models.SchedulerStateChangeOperation.CREATE,
        before=None,
        after=item.model_dump(),
        changed_by_membership_id=changed_by_membership_id,
    )
    await db.flush()
    await db.refresh(db_item)
    return db_item


# --- LESSONS ---
async def _owned_constraint_reference(
    db: AsyncSession,
    model,
    entity_id: int,
    organization_id: int,
):
    return await db.scalar(
        select(model).where(
            model.id == entity_id,
            model.organization_id == organization_id,
        )
    )


async def _load_constraint_class_subject(
    db: AsyncSession,
    payload: dict,
    organization_id: int,
):
    class_row = await _owned_constraint_reference(
        db, models.Class, payload["class_id"], organization_id
    )
    subject_row = await _owned_constraint_reference(
        db, models.Subject, payload["subject_id"], organization_id
    )
    if class_row is None or class_row.is_archived or subject_row is None:
        return None
    relationship = await db.scalar(
        select(models.ClassSubjectLink.id).where(
            models.ClassSubjectLink.organization_id == organization_id,
            models.ClassSubjectLink.class_id == payload["class_id"],
            models.ClassSubjectLink.subject_id == payload["subject_id"],
            models.ClassSubjectLink.grade_level == class_row.grade_level,
        )
    )
    return (class_row, subject_row) if relationship is not None else None


async def _validate_constraint_references(
    db: AsyncSession,
    item: schemas.ConstraintCreate,
    organization_id: int,
) -> None:
    payload = item.rule_payload.model_dump()
    rule_type = item.rule_type.value
    invalid = False

    timeslot_id = payload.get("timeslot_id")
    if (
        timeslot_id is not None
        and await _owned_constraint_reference(db, models.Timeslot, timeslot_id, organization_id)
        is None
    ):
        invalid = True

    teacher_id = payload.get("teacher_id")
    if (
        teacher_id is not None
        and await _owned_constraint_reference(db, models.Teacher, teacher_id, organization_id)
        is None
    ):
        invalid = True

    class_subject = None
    if rule_type in {"specific_room", "lock_time"}:
        class_subject = await _load_constraint_class_subject(db, payload, organization_id)
        if class_subject is None:
            invalid = True

    if rule_type == "specific_room" and class_subject is not None:
        class_row, subject_row = class_subject
        room = await _owned_constraint_reference(
            db, models.Room, payload["room_id"], organization_id
        )
        if (
            room is None
            or room.capacity < class_row.size
            or room.room_type_id != subject_row.room_type_id
        ):
            invalid = True

    if invalid:
        raise ConstraintSemanticValidationError(
            "One or more scheduler constraint references are unavailable."
        )


def _constraint_affects_future(payload: dict) -> bool:
    """A rule tied to one past date cannot change the editable future."""
    constraint_date = payload.get("date")
    if constraint_date is None:
        return True
    if isinstance(constraint_date, str):
        constraint_date = date.fromisoformat(constraint_date)
    return constraint_date >= date.today()


async def create_constraint(
    db: AsyncSession,
    item: schemas.ConstraintCreate,
    organization_id: int,
    changed_by_membership_id: int | None = None,
):
    await _validate_constraint_references(db, item, organization_id)
    rule_payload = item.rule_payload.model_dump(exclude_none=True)
    db_item = models.Constraint(
        rule_type=models.ConstraintType(item.rule_type.value),
        organization_id=organization_id,
        class_id=rule_payload.get("class_id"),
        subject_id=rule_payload.get("subject_id"),
        teacher_id=rule_payload.get("teacher_id"),
        room_id=rule_payload.get("room_id"),
        timeslot_id=rule_payload.get("timeslot_id"),
        constraint_date=rule_payload.get("date"),
        day_of_week=rule_payload.get("day_of_week"),
    )
    db.add(db_item)
    await db.flush()
    await record_scheduler_change(
        db,
        organization_id,
        entity_type="SCHEDULER_CONSTRAINT",
        entity_id=db_item.id,
        operation=models.SchedulerStateChangeOperation.CREATE,
        before=None,
        after={"rule_type": db_item.rule_type, "rule_payload": db_item.rule_payload},
        changed_by_membership_id=changed_by_membership_id,
        future_impacting=_constraint_affects_future(rule_payload),
    )
    await db.flush()
    await db.refresh(db_item)
    return db_item
