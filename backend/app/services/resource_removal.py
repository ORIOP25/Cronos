"""Removal decisions and configuration cleanup for catalog resources.

The domain rule is shared by rooms, subjects, classes and courses:

- a resource published or operating right now cannot leave the current
  management (the caller raises an explicit conflict);
- a resource with preserved history is archived so old schedules, summaries
  and progress keep resolving;
- only a resource with no reference at all is physically deleted.

This module owns the reference queries (persistence) so the services decide
the outcome and the endpoints translate it to HTTP.
"""

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.scheduler.infrastructure import models as scheduler_models

_ACTIVE_OPERATIONAL = models.OperationalBlockStatus.ACTIVE


async def _any(db: AsyncSession, statements: list) -> bool:
    for statement in statements:
        if await db.scalar(statement.limit(1)) is not None:
            return True
    return False


def _references(model, organization_id: int, column) -> object:
    return select(model.id).where(model.organization_id == organization_id, column)


def _published_lessons(organization_id: int):
    return (
        select(scheduler_models.SchedulerLessonV1.id)
        .join(
            scheduler_models.SchedulerVersionV1,
            (
                scheduler_models.SchedulerVersionV1.id
                == scheduler_models.SchedulerLessonV1.version_id
            )
            & (scheduler_models.SchedulerVersionV1.organization_id == organization_id),
        )
        .join(
            scheduler_models.CurricularAssignment,
            (
                scheduler_models.CurricularAssignment.id
                == scheduler_models.SchedulerLessonV1.assignment_id
            )
            & (scheduler_models.CurricularAssignment.organization_id == organization_id),
        )
        .where(
            scheduler_models.SchedulerLessonV1.organization_id == organization_id,
            scheduler_models.SchedulerVersionV1.status == "ACTIVE",
        )
    )


# --- ROOMS ---
async def room_in_use(db: AsyncSession, organization_id: int, room_id: int) -> bool:
    return await _any(
        db,
        [
            _published_lessons(organization_id).where(
                scheduler_models.SchedulerLessonV1.room_id == room_id
            ),
            select(models.OperationalScheduleBlock.id).where(
                models.OperationalScheduleBlock.organization_id == organization_id,
                models.OperationalScheduleBlock.room_id == room_id,
                models.OperationalScheduleBlock.status == _ACTIVE_OPERATIONAL,
            ),
        ],
    )


async def room_has_history(db: AsyncSession, organization_id: int, room_id: int) -> bool:
    return await _any(
        db,
        [
            _references(
                models.OperationalScheduleBlock,
                organization_id,
                models.OperationalScheduleBlock.room_id == room_id,
            ),
            _references(
                models.LessonOccurrence,
                organization_id,
                models.LessonOccurrence.planned_room_id == room_id,
            ),
            select(scheduler_models.SchedulerLessonV1.id).where(
                scheduler_models.SchedulerLessonV1.organization_id == organization_id,
                scheduler_models.SchedulerLessonV1.room_id == room_id,
            ),
        ],
    )


# --- SUBJECTS ---
async def subject_in_use(db: AsyncSession, organization_id: int, subject_id: int) -> bool:
    return await _any(
        db,
        [
            _published_lessons(organization_id).where(
                scheduler_models.CurricularAssignment.subject_id == subject_id
            ),
            select(models.OperationalScheduleBlock.id).where(
                models.OperationalScheduleBlock.organization_id == organization_id,
                models.OperationalScheduleBlock.subject_id == subject_id,
                models.OperationalScheduleBlock.status == _ACTIVE_OPERATIONAL,
            ),
            select(models.JointLessonGroup.id).where(
                models.JointLessonGroup.organization_id == organization_id,
                models.JointLessonGroup.subject_id == subject_id,
            ),
        ],
    )


async def subject_has_history(db: AsyncSession, organization_id: int, subject_id: int) -> bool:
    progress = (
        select(models.ProgressLedgerEntry.id)
        .join(models.Module, models.Module.id == models.ProgressLedgerEntry.module_id)
        .where(
            models.ProgressLedgerEntry.organization_id == organization_id,
            models.Module.subject_id == subject_id,
        )
    )
    module_ids = select(models.Module.id).where(
        models.Module.organization_id == organization_id,
        models.Module.subject_id == subject_id,
    )
    return await _any(
        db,
        [
            _references(
                models.OperationalScheduleBlock,
                organization_id,
                models.OperationalScheduleBlock.subject_id == subject_id,
            ),
            _references(
                models.LessonOccurrence,
                organization_id,
                models.LessonOccurrence.subject_id == subject_id,
            ),
            progress,
            select(scheduler_models.CurricularAssignment.id).where(
                scheduler_models.CurricularAssignment.organization_id == organization_id,
                scheduler_models.CurricularAssignment.subject_id == subject_id,
            ),
            select(scheduler_models.CurricularRequirement.id).where(
                scheduler_models.CurricularRequirement.organization_id == organization_id,
                scheduler_models.CurricularRequirement.module_id.in_(module_ids),
            ),
            select(scheduler_models.CurricularExecutionCredit.id).where(
                scheduler_models.CurricularExecutionCredit.organization_id == organization_id,
                scheduler_models.CurricularExecutionCredit.module_id.in_(module_ids),
            ),
            select(scheduler_models.SchedulerLessonSliceV1.id).where(
                scheduler_models.SchedulerLessonSliceV1.organization_id == organization_id,
                scheduler_models.SchedulerLessonSliceV1.module_id.in_(module_ids),
            ),
            select(models.OperationalScheduleBlock.id).where(
                models.OperationalScheduleBlock.organization_id == organization_id,
                models.OperationalScheduleBlock.module_id.in_(module_ids),
            ),
            select(models.LessonOccurrence.id).where(
                models.LessonOccurrence.organization_id == organization_id,
                or_(
                    models.LessonOccurrence.planned_module_id.in_(module_ids),
                    models.LessonOccurrence.executed_module_id.in_(module_ids),
                ),
            ),
        ],
    )


# --- ROOM TYPES ---
def _room_type_references(model, organization_id: int, room_type_id: int):
    return select(model.id).where(
        model.organization_id == organization_id,
        model.room_type_id == room_type_id,
    )


async def room_type_active_references(
    db: AsyncSession, organization_id: int, room_type_id: int
) -> dict[str, list[str]]:
    """Names of the active rooms and subjects that still use this type."""
    rooms = (
        await db.scalars(
            select(models.Room.name)
            .where(
                models.Room.organization_id == organization_id,
                models.Room.room_type_id == room_type_id,
                models.Room.is_archived.is_(False),
            )
            .order_by(models.Room.name)
        )
    ).all()
    subjects = (
        await db.scalars(
            select(models.Subject.name)
            .where(
                models.Subject.organization_id == organization_id,
                models.Subject.room_type_id == room_type_id,
                models.Subject.is_archived.is_(False),
            )
            .order_by(models.Subject.name)
        )
    ).all()
    return {"rooms": list(rooms), "subjects": list(subjects)}


async def room_type_has_history(db: AsyncSession, organization_id: int, room_type_id: int) -> bool:
    return await _any(
        db,
        [
            _room_type_references(models.Room, organization_id, room_type_id),
            _room_type_references(models.Subject, organization_id, room_type_id),
        ],
    )


# --- CLASSES ---
async def class_in_use(db: AsyncSession, organization_id: int, class_id: int) -> bool:
    return await _any(
        db,
        [
            _published_lessons(organization_id).where(
                scheduler_models.CurricularAssignment.class_id == class_id
            ),
            select(models.OperationalScheduleBlock.id).where(
                models.OperationalScheduleBlock.organization_id == organization_id,
                models.OperationalScheduleBlock.class_id == class_id,
                models.OperationalScheduleBlock.status == _ACTIVE_OPERATIONAL,
            ),
            select(models.joint_lesson_group_member.c.class_subject_link_id)
            .join(
                models.ClassSubjectLink,
                models.ClassSubjectLink.id
                == models.joint_lesson_group_member.c.class_subject_link_id,
            )
            .where(
                models.joint_lesson_group_member.c.organization_id == organization_id,
                models.ClassSubjectLink.organization_id == organization_id,
                models.ClassSubjectLink.class_id == class_id,
            ),
        ],
    )


async def joint_module_ids(db: AsyncSession, organization_id: int, module_ids) -> set[int]:
    """Modules that belong to a joint lesson group and cannot be removed."""
    identifiers = list(module_ids)
    if not identifiers:
        return set()
    rows = await db.execute(
        select(models.joint_lesson_group_module.c.module_id).where(
            models.joint_lesson_group_module.c.organization_id == organization_id,
            models.joint_lesson_group_module.c.module_id.in_(identifiers),
        )
    )
    return {row[0] for row in rows.all()}


async def class_has_history(db: AsyncSession, organization_id: int, class_id: int) -> bool:
    return await _any(
        db,
        [
            _references(
                models.OperationalScheduleBlock,
                organization_id,
                models.OperationalScheduleBlock.class_id == class_id,
            ),
            _references(
                models.LessonOccurrence,
                organization_id,
                models.LessonOccurrence.class_id == class_id,
            ),
            _references(
                models.ProgressLedgerEntry,
                organization_id,
                models.ProgressLedgerEntry.class_id == class_id,
            ),
            _references(
                models.SchoolCalendarEventClass,
                organization_id,
                models.SchoolCalendarEventClass.class_id == class_id,
            ),
            select(scheduler_models.CurricularAssignment.id).where(
                scheduler_models.CurricularAssignment.organization_id == organization_id,
                scheduler_models.CurricularAssignment.class_id == class_id,
            ),
        ],
    )


# --- CONFIGURATION CLEANUP ---
async def remove_room_configuration(db: AsyncSession, organization_id: int, room_id: int) -> None:
    await db.execute(
        delete(models.Constraint).where(
            models.Constraint.organization_id == organization_id,
            models.Constraint.room_id == room_id,
        )
    )


async def remove_subject_configuration(
    db: AsyncSession, organization_id: int, subject_id: int
) -> None:
    await db.execute(
        delete(models.ClassSubjectLink).where(
            models.ClassSubjectLink.organization_id == organization_id,
            models.ClassSubjectLink.subject_id == subject_id,
        )
    )
    await db.execute(
        delete(models.course_subject_link).where(
            models.course_subject_link.c.organization_id == organization_id,
            models.course_subject_link.c.subject_id == subject_id,
        )
    )
    await db.execute(
        delete(models.Constraint).where(
            models.Constraint.organization_id == organization_id,
            models.Constraint.subject_id == subject_id,
        )
    )
    await db.execute(
        delete(models.teacher_subject_link).where(
            models.teacher_subject_link.c.organization_id == organization_id,
            models.teacher_subject_link.c.subject_id == subject_id,
        )
    )


async def remove_class_configuration(db: AsyncSession, organization_id: int, class_id: int) -> None:
    await db.execute(
        delete(models.ClassSubjectLink).where(
            models.ClassSubjectLink.organization_id == organization_id,
            models.ClassSubjectLink.class_id == class_id,
        )
    )
    await db.execute(
        delete(models.Constraint).where(
            models.Constraint.organization_id == organization_id,
            models.Constraint.class_id == class_id,
        )
    )


async def remove_course_configuration(
    db: AsyncSession, organization_id: int, course_id: int
) -> None:
    await db.execute(
        delete(models.course_subject_link).where(
            models.course_subject_link.c.organization_id == organization_id,
            models.course_subject_link.c.course_id == course_id,
        )
    )
