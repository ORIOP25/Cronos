from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import and_, case, func, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import Session

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
            or room.type != subject_row.required_room_type
        ):
            invalid = True

    if invalid:
        raise ConstraintSemanticValidationError(
            "One or more scheduler constraint references are unavailable."
        )


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
    )
    await db.flush()
    await db.refresh(db_item)
    return db_item


async def get_constraints_by_org(db: AsyncSession, organization_id: int):
    """Lista todas as restrições."""
    result = await db.execute(
        select(models.Constraint).where(models.Constraint.organization_id == organization_id)
    )
    return result.scalars().all()


async def delete_constraint(
    db: AsyncSession,
    constraint_id: int,
    organization_id: int,
    changed_by_membership_id: int | None = None,
):
    """Apaga uma regra de horário."""
    query = select(models.Constraint).where(
        models.Constraint.id == constraint_id, models.Constraint.organization_id == organization_id
    )
    result = await db.execute(query)
    item = result.scalars().first()

    if item:
        before = {"rule_type": item.rule_type, "rule_payload": item.rule_payload}
        await db.delete(item)
        await record_scheduler_change(
            db,
            organization_id,
            entity_type="SCHEDULER_CONSTRAINT",
            entity_id=item.id,
            operation=models.SchedulerStateChangeOperation.DELETE,
            before=before,
            after=None,
            changed_by_membership_id=changed_by_membership_id,
        )
        await db.flush()
        return True
    return False


def get_modules_by_subject_sync(db: Session, organization_id: int) -> dict:
    """Retorna {subject_id: [Module ordenado]} para todos os subjects da org."""
    modules = (
        db.query(models.Module)
        .join(models.Subject, models.Module.subject_id == models.Subject.id)
        .filter(models.Subject.organization_id == organization_id)
        .filter(models.Module.organization_id == organization_id)
        .order_by(models.Module.subject_id, models.Module.order)
        .all()
    )
    result: dict = defaultdict(list)
    for module in modules:
        result[module.subject_id].append(module)
    return dict(result)


def get_class_progress_map_sync(db: Session, organization_id: int) -> dict:
    """Return derived completed hours without a mutable summary table."""
    rows = (
        db.query(
            models.ProgressLedgerEntry.class_id,
            models.ProgressLedgerEntry.module_id,
            func.sum(models.ProgressLedgerEntry.completed_minutes_delta),
        )
        .filter(
            models.ProgressLedgerEntry.organization_id == organization_id,
        )
        .group_by(
            models.ProgressLedgerEntry.class_id,
            models.ProgressLedgerEntry.module_id,
        )
        .all()
    )
    return {(row[0], row[1]): int(row[2] or 0) / 60 for row in rows}


def get_org_settings_sync(db: Session, organization_id: int):
    """Retorna as OrganizationSettings desta org, da mais recente para a mais antiga."""
    return (
        db.query(models.OrganizationSettings)
        .filter(models.OrganizationSettings.organization_id == organization_id)
        .order_by(models.OrganizationSettings.id.desc())
        .all()
    )


def get_grid_settings_sync(db: Session, organization_id: int):
    """Retorna as OrganizationGridSettings desta org (única por org), ou None."""
    return (
        db.query(models.OrganizationGridSettings)
        .filter(models.OrganizationGridSettings.organization_id == organization_id)
        .first()
    )


def get_calendar_events_sync(db: Session, organization_id: int):
    """Retorna todos os SchoolCalendarEvents desta org."""
    return (
        db.query(models.SchoolCalendarEvent)
        .filter(models.SchoolCalendarEvent.organization_id == organization_id)
        .all()
    )


def update_class_projected_end_date_sync(
    db: Session, organization_id: int, class_id: int, end_date: date
) -> None:
    """Atualiza projected_end_date de uma turma."""
    db.query(models.Class).filter(
        models.Class.id == class_id,
        models.Class.organization_id == organization_id,
    ).update({"projected_end_date": end_date})


def _find_active_module(modules: list, progress_map: dict):
    """Returns the first non-completed module, or the last if all done."""
    for module in modules:
        prog = progress_map.get(module.id)
        if int(prog or 0) < module.hours_total * 60:
            return module
    return modules[-1] if modules else None


def _fetch_active_modules(db: Session, pairs: list[tuple]) -> dict[tuple, dict | None]:
    """Fetches active module data per (class_id, subject_id) pair without N+1 queries."""
    active: dict[tuple, dict | None] = {}
    if not pairs:
        return active

    unique_pairs = list(set(pairs))
    subject_ids = {subject_id for _, subject_id in unique_pairs}
    class_ids = {class_id for class_id, _ in unique_pairs}

    modules_rows = (
        db.query(models.Module)
        .filter(models.Module.subject_id.in_(subject_ids))
        .order_by(models.Module.subject_id, models.Module.order)
        .all()
    )

    modules_by_subject: dict[int, list[models.Module]] = {}
    module_ids: list[int] = []
    for module in modules_rows:
        modules_by_subject.setdefault(module.subject_id, []).append(module)
        module_ids.append(module.id)

    progress_lookup: dict[tuple[int, int], int] = {}
    if module_ids and class_ids:
        progress_rows = (
            db.query(
                models.ProgressLedgerEntry.class_id,
                models.ProgressLedgerEntry.module_id,
                func.sum(models.ProgressLedgerEntry.completed_minutes_delta),
            )
            .filter(
                models.ProgressLedgerEntry.class_id.in_(class_ids),
                models.ProgressLedgerEntry.module_id.in_(module_ids),
            )
            .group_by(
                models.ProgressLedgerEntry.class_id,
                models.ProgressLedgerEntry.module_id,
            )
            .all()
        )
        progress_lookup = {(row.class_id, row.module_id): int(row[2] or 0) for row in progress_rows}

    for cls_id, subj_id in unique_pairs:
        modules = modules_by_subject.get(subj_id, [])
        if not modules:
            active[(cls_id, subj_id)] = None
            continue

        progress_map = {module.id: progress_lookup.get((cls_id, module.id)) for module in modules}
        mod = _find_active_module(modules, progress_map)
        active[(cls_id, subj_id)] = (
            {"id": mod.id, "name": mod.name, "hours_total": mod.hours_total} if mod else None
        )

    return active


def _build_operational_week_slot(
    row: tuple,
    today: date,
) -> dict:
    (
        block,
        timeslot,
        subject,
        teacher,
        class_model,
        room,
        source_occurrence,
        lesson_log,
        module_id,
        module_name,
        module_minutes,
        timesheet_status,
        timesheet_id,
    ) = row
    module = (
        {"id": module_id, "name": module_name, "hours_total": module_minutes / 60}
        if module_id is not None
        else None
    )

    return {
        "operational_block_id": block.id,
        "block_source": "operational",
        "date": block.date.isoformat(),
        "timeslot": {
            "id": timeslot.id,
            "day_of_week": timeslot.day_of_week,
            "start_time": str(timeslot.start_time)[:5],
            "end_time": str(timeslot.end_time)[:5],
        },
        "subject": {"id": subject.id, "name": subject.name},
        "teacher": {"id": teacher.id, "name": teacher.name},
        "room": {"id": room.id, "name": room.name} if room else None,
        "class_info": {"id": class_model.id, "name": class_model.name},
        "module": module,
        "is_past": block.date < today,
        "occurrence_status": models.LessonOccurrenceStatus.SUBSTITUTED.value,
        "hours_given": 0.0,
        "occurrence_id": block.source_occurrence_id,
        "occurrence_decided_at": source_occurrence.decided_at if source_occurrence else None,
        "can_create_occurrence": False,
        "can_decide_occurrence": False,
        "lesson_log_id": lesson_log.id if lesson_log else None,
        "lesson_log_status": lesson_log.status.value if lesson_log else None,
        "lesson_log_summary": lesson_log.summary if lesson_log else None,
        "lesson_log_notes": lesson_log.notes if lesson_log else None,
        "lesson_log_logged_at": lesson_log.logged_at if lesson_log else None,
        "week_timesheet_status": timesheet_status.value if timesheet_status else "OPEN",
        "timesheet_id": timesheet_id,
        "is_substituted_block": True,
    }


def _build_active_week_slot(
    row: tuple,
    today: date,
) -> dict:
    (
        block,
        timeslot,
        subject,
        teacher,
        class_model,
        room,
        occurrence,
        lesson_log,
        module_id,
        module_name,
        module_minutes,
        timesheet_status,
        timesheet_id,
    ) = row
    module = (
        {"id": module_id, "name": module_name, "hours_total": module_minutes / 60}
        if module_id is not None
        else None
    )

    return {
        "active_schedule_block_id": block.id,
        "operational_block_id": None,
        "block_source": "active",
        "date": block.date.isoformat(),
        "timeslot": {
            "id": timeslot.id,
            "day_of_week": timeslot.day_of_week,
            "start_time": str(timeslot.start_time)[:5],
            "end_time": str(timeslot.end_time)[:5],
        },
        "subject": {"id": subject.id, "name": subject.name},
        "teacher": {"id": teacher.id, "name": teacher.name},
        "room": {"id": room.id, "name": room.name},
        "class_info": {"id": class_model.id, "name": class_model.name},
        "module": module,
        "is_past": block.date < today,
        "occurrence_status": (
            occurrence.status.value if occurrence and occurrence.status is not None else None
        ),
        "hours_given": occurrence.hours_given if occurrence else None,
        "occurrence_id": occurrence.id if occurrence else None,
        "occurrence_decided_at": occurrence.decided_at if occurrence else None,
        "can_create_occurrence": occurrence is None,
        "can_decide_occurrence": occurrence is not None,
        "lesson_log_id": lesson_log.id if lesson_log else None,
        "lesson_log_status": lesson_log.status.value if lesson_log else None,
        "lesson_log_summary": lesson_log.summary if lesson_log else None,
        "lesson_log_notes": lesson_log.notes if lesson_log else None,
        "lesson_log_logged_at": lesson_log.logged_at if lesson_log else None,
        "week_timesheet_status": timesheet_status.value if timesheet_status else "OPEN",
        "timesheet_id": timesheet_id,
        "is_substituted_block": False,
    }


def get_week_schedule_sync(
    db: Session,
    organization_id: int,
    week_start: date,
    class_id: int | None = None,
    teacher_id: int | None = None,
) -> list[dict]:
    """Return the published schedule and operational overrides for one week."""
    week_end = week_start + timedelta(days=6)
    today = date.today()

    def active_module(class_column, subject_column, correlate_model):
        completed_minutes = (
            select(func.coalesce(func.sum(models.ProgressLedgerEntry.completed_minutes_delta), 0))
            .where(
                models.ProgressLedgerEntry.class_id == class_column,
                models.ProgressLedgerEntry.module_id == models.Module.id,
            )
            .correlate(models.Module, correlate_model)
            .scalar_subquery()
        )
        incomplete = completed_minutes < models.Module.required_minutes
        return (
            select(
                models.Module.id.label("module_id"),
                models.Module.name.label("module_name"),
                models.Module.required_minutes.label("module_minutes"),
            )
            .where(models.Module.subject_id == subject_column)
            .order_by(
                case((incomplete, 0), else_=1),
                case((incomplete, models.Module.order), else_=-models.Module.order),
            )
            .limit(1)
            .lateral()
        )

    active_module_row = active_module(
        models.ActiveScheduleBlock.class_id,
        models.ActiveScheduleBlock.subject_id,
        models.ActiveScheduleBlock,
    )
    active_q = (
        db.query(
            models.ActiveScheduleBlock,
            models.Timeslot,
            models.Subject,
            models.Teacher,
            models.Class,
            models.Room,
            models.LessonOccurrence,
            models.LessonLog,
            active_module_row.c.module_id,
            active_module_row.c.module_name,
            active_module_row.c.module_minutes,
            models.TeacherWeeklyTimesheet.status,
            models.TeacherWeeklyTimesheet.id,
        )
        .join(models.Timeslot, models.ActiveScheduleBlock.timeslot_id == models.Timeslot.id)
        .join(models.Subject, models.ActiveScheduleBlock.subject_id == models.Subject.id)
        .join(models.Teacher, models.ActiveScheduleBlock.teacher_id == models.Teacher.id)
        .join(models.Class, models.ActiveScheduleBlock.class_id == models.Class.id)
        .join(models.Room, models.ActiveScheduleBlock.room_id == models.Room.id)
        .outerjoin(
            models.LessonOccurrence,
            and_(
                models.LessonOccurrence.organization_id == organization_id,
                models.LessonOccurrence.active_schedule_block_id == models.ActiveScheduleBlock.id,
                models.LessonOccurrence.is_active.is_(True),
            ),
        )
        .outerjoin(
            models.LessonLog,
            and_(
                models.LessonLog.organization_id == organization_id,
                models.LessonLog.active_schedule_block_id == models.ActiveScheduleBlock.id,
            ),
        )
        .outerjoin(active_module_row, true())
        .outerjoin(
            models.TeacherWeeklyTimesheet,
            and_(
                models.TeacherWeeklyTimesheet.organization_id == organization_id,
                models.TeacherWeeklyTimesheet.teacher_id == models.ActiveScheduleBlock.teacher_id,
                models.TeacherWeeklyTimesheet.week_start_date == week_start,
            ),
        )
        .filter(
            models.ActiveScheduleBlock.organization_id == organization_id,
            models.ActiveScheduleBlock.status == models.ActiveScheduleBlockStatus.ACTIVE,
            models.ActiveScheduleBlock.date.between(week_start, week_end),
            models.Timeslot.organization_id == organization_id,
            models.Subject.organization_id == organization_id,
            models.Teacher.organization_id == organization_id,
            models.Class.organization_id == organization_id,
            models.Room.organization_id == organization_id,
        )
    )
    if class_id is not None:
        active_q = active_q.filter(models.ActiveScheduleBlock.class_id == class_id)
    if teacher_id is not None:
        active_q = active_q.filter(models.ActiveScheduleBlock.teacher_id == teacher_id)
    active_rows = active_q.all()

    operational_module_row = active_module(
        models.OperationalScheduleBlock.class_id,
        models.OperationalScheduleBlock.subject_id,
        models.OperationalScheduleBlock,
    )
    operational_q = (
        db.query(
            models.OperationalScheduleBlock,
            models.Timeslot,
            models.Subject,
            models.Teacher,
            models.Class,
            models.Room,
            models.LessonOccurrence,
            models.LessonLog,
            operational_module_row.c.module_id,
            operational_module_row.c.module_name,
            operational_module_row.c.module_minutes,
            models.TeacherWeeklyTimesheet.status,
            models.TeacherWeeklyTimesheet.id,
        )
        .join(models.Timeslot, models.OperationalScheduleBlock.timeslot_id == models.Timeslot.id)
        .join(models.Subject, models.OperationalScheduleBlock.subject_id == models.Subject.id)
        .join(models.Teacher, models.OperationalScheduleBlock.teacher_id == models.Teacher.id)
        .join(models.Class, models.OperationalScheduleBlock.class_id == models.Class.id)
        .outerjoin(models.Room, models.OperationalScheduleBlock.room_id == models.Room.id)
        .join(
            models.LessonOccurrence,
            and_(
                models.LessonOccurrence.organization_id == organization_id,
                models.LessonOccurrence.id == models.OperationalScheduleBlock.source_occurrence_id,
            ),
        )
        .outerjoin(
            models.LessonLog,
            and_(
                models.LessonLog.organization_id == organization_id,
                models.LessonLog.operational_block_id == models.OperationalScheduleBlock.id,
            ),
        )
        .outerjoin(operational_module_row, true())
        .outerjoin(
            models.TeacherWeeklyTimesheet,
            and_(
                models.TeacherWeeklyTimesheet.organization_id == organization_id,
                models.TeacherWeeklyTimesheet.teacher_id
                == models.OperationalScheduleBlock.teacher_id,
                models.TeacherWeeklyTimesheet.week_start_date == week_start,
            ),
        )
        .filter(
            models.OperationalScheduleBlock.organization_id == organization_id,
            models.OperationalScheduleBlock.status == models.OperationalBlockStatus.ACTIVE,
            models.OperationalScheduleBlock.date.between(week_start, week_end),
        )
    )
    if class_id is not None:
        operational_q = operational_q.filter(models.OperationalScheduleBlock.class_id == class_id)
    if teacher_id is not None:
        operational_q = operational_q.filter(
            models.OperationalScheduleBlock.teacher_id == teacher_id
        )
    operational_rows = operational_q.all()

    return [_build_active_week_slot(row, today) for row in active_rows] + [
        _build_operational_week_slot(row, today) for row in operational_rows
    ]
