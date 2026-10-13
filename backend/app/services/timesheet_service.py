from datetime import UTC, date, datetime, timedelta

from sqlalchemy import and_, or_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, joinedload

from app import models
from app.core.exceptions import AppError
from app.scheduler.infrastructure.models import (
    CurricularAssignment,
    SchedulerLessonLogV1,
    SchedulerLessonV1,
    SchedulerVersionV1,
)


def _active_v1_year_and_version(
    db: Session, organization_id: int
) -> tuple[int | None, SchedulerVersionV1 | None]:
    """One indexed lookup for the active year's published v1 version."""
    row = (
        db.query(models.SchedulerSchoolYear.id, SchedulerVersionV1)
        .join(
            SchedulerVersionV1,
            and_(
                SchedulerVersionV1.organization_id == models.SchedulerSchoolYear.organization_id,
                SchedulerVersionV1.school_year_id == models.SchedulerSchoolYear.id,
            ),
        )
        .filter(
            models.SchedulerSchoolYear.organization_id == organization_id,
            models.SchedulerSchoolYear.is_active.is_(True),
            SchedulerVersionV1.status == "ACTIVE",
        )
        .first()
    )
    if row is None:
        return None, None
    return int(row[0]), row[1]


def _v1_week_lessons(
    db: Session,
    organization_id: int,
    year_id: int,
    version: SchedulerVersionV1,
    teacher_ids: list[int],
    week_start_date: date,
):
    week_end = week_start_date + timedelta(days=6)
    return (
        db.query(CurricularAssignment.teacher_id, SchedulerLessonV1, SchedulerLessonLogV1)
        .join(
            CurricularAssignment,
            and_(
                CurricularAssignment.organization_id == SchedulerLessonV1.organization_id,
                CurricularAssignment.school_year_id == SchedulerLessonV1.school_year_id,
                CurricularAssignment.id == SchedulerLessonV1.assignment_id,
            ),
        )
        .outerjoin(
            SchedulerLessonLogV1,
            and_(
                SchedulerLessonLogV1.organization_id == organization_id,
                SchedulerLessonLogV1.lesson_id == SchedulerLessonV1.id,
            ),
        )
        .filter(
            SchedulerLessonV1.organization_id == organization_id,
            SchedulerLessonV1.school_year_id == year_id,
            SchedulerLessonV1.version_id == version.id,
            CurricularAssignment.teacher_id.in_(teacher_ids),
            SchedulerLessonV1.school_date.between(week_start_date, week_end),
        )
        .all()
    )


def _v1_week_operational_blocks(
    db: Session,
    organization_id: int,
    year_id: int,
    teacher_ids: list[int],
    week_start_date: date,
):
    """Active v1 substitute blocks with their source lesson and execution log."""
    week_end = week_start_date + timedelta(days=6)
    return (
        db.query(models.OperationalScheduleBlock, SchedulerLessonV1, models.LessonLog)
        .join(
            SchedulerLessonLogV1,
            and_(
                SchedulerLessonLogV1.organization_id == organization_id,
                SchedulerLessonLogV1.id == models.OperationalScheduleBlock.source_v1_lesson_log_id,
            ),
        )
        .join(
            SchedulerLessonV1,
            and_(
                SchedulerLessonV1.organization_id == SchedulerLessonLogV1.organization_id,
                SchedulerLessonV1.school_year_id == SchedulerLessonLogV1.school_year_id,
                SchedulerLessonV1.id == SchedulerLessonLogV1.lesson_id,
                SchedulerLessonV1.school_year_id == year_id,
            ),
        )
        .outerjoin(
            models.LessonLog,
            and_(
                models.LessonLog.organization_id == organization_id,
                models.LessonLog.operational_block_id == models.OperationalScheduleBlock.id,
            ),
        )
        .filter(
            models.OperationalScheduleBlock.organization_id == organization_id,
            models.OperationalScheduleBlock.origin_kind == models.OperationalBlockOrigin.V1,
            models.OperationalScheduleBlock.status == models.OperationalBlockStatus.ACTIVE,
            models.OperationalScheduleBlock.teacher_id.in_(teacher_ids),
            models.OperationalScheduleBlock.date.between(week_start_date, week_end),
        )
        .all()
    )


def _v1_slot_counts(
    db: Session,
    organization_id: int,
    year_id: int,
    version: SchedulerVersionV1,
    teacher_ids: list[int],
    week_start_date: date,
) -> dict[int, dict]:
    counts = {
        teacher_id: {
            "total_slots": 0,
            "registered_slots": 0,
            "completed_slots": 0,
            "occurrence_slots": 0,
        }
        for teacher_id in teacher_ids
    }
    if not teacher_ids:
        return counts
    for teacher_id, _lesson, lesson_log in _v1_week_lessons(
        db, organization_id, year_id, version, teacher_ids, week_start_date
    ):
        item = counts[teacher_id]
        item["total_slots"] += 1
        status = None if lesson_log is None else lesson_log.status
        if status in ("COMPLETED", "OCCURRENCE"):
            item["registered_slots"] += 1
        if status == "COMPLETED":
            item["completed_slots"] += 1
        if status == "OCCURRENCE":
            item["occurrence_slots"] += 1
    for block, _lesson, lesson_log in _v1_week_operational_blocks(
        db, organization_id, year_id, teacher_ids, week_start_date
    ):
        item = counts[block.teacher_id]
        item["total_slots"] += 1
        status = None if lesson_log is None else lesson_log.status.value
        if status in ("COMPLETED", "OCCURRENCE"):
            item["registered_slots"] += 1
        if status == "COMPLETED":
            item["completed_slots"] += 1
        if status == "OCCURRENCE":
            item["occurrence_slots"] += 1
    return counts


def week_slot_counts_sync(
    db: Session,
    organization_id: int,
    teacher_id: int,
    week_start_date: date,
) -> dict:
    """Slot counts for one teacher, following the v1 ledger when published."""
    return _compute_slot_counts_for_teachers(db, organization_id, [teacher_id], week_start_date)[
        teacher_id
    ]


def get_or_create_timesheet_sync(
    db: Session, organization_id: int, teacher_id: int, week_start_date: date
) -> models.TeacherWeeklyTimesheet:
    """Obtém ou cria a timesheet de uma determinada semana para o professor."""
    filters = (
        models.TeacherWeeklyTimesheet.organization_id == organization_id,
        models.TeacherWeeklyTimesheet.teacher_id == teacher_id,
        models.TeacherWeeklyTimesheet.week_start_date == week_start_date,
    )
    timesheet = db.query(models.TeacherWeeklyTimesheet).filter(*filters).first()
    if timesheet is not None:
        return timesheet

    # Concurrent first reads race on this week; the unique constraint keeps one
    # row and the loser reads it back instead of failing the request.
    db.execute(
        pg_insert(models.TeacherWeeklyTimesheet)
        .values(
            organization_id=organization_id,
            teacher_id=teacher_id,
            week_start_date=week_start_date,
            status=models.TimesheetStatus.OPEN,
        )
        .on_conflict_do_nothing(
            index_elements=["organization_id", "teacher_id", "week_start_date"],
        )
    )
    return db.query(models.TeacherWeeklyTimesheet).filter(*filters).one()


def submit_timesheet_sync(
    db: Session,
    organization_id: int,
    teacher_id: int,
    week_start_date: date,
) -> models.TeacherWeeklyTimesheet:
    """Submit a week only after every published lesson is resolved."""
    timesheet = get_or_create_timesheet_sync(db, organization_id, teacher_id, week_start_date)
    if timesheet.status != models.TimesheetStatus.OPEN:
        raise AppError(
            kind="bad_request",
            code="bad_request",
            detail="A semana já não está aberta para submissão.",
        )

    year_id, version = _active_v1_year_and_version(db, organization_id)
    if version is not None:
        return _submit_v1_week(
            db, timesheet, organization_id, year_id, version, teacher_id, week_start_date
        )

    week_end = week_start_date + timedelta(days=6)
    rows = (
        db.query(models.ActiveScheduleBlock, models.Timeslot, models.LessonLog)
        .join(models.Timeslot, models.ActiveScheduleBlock.timeslot_id == models.Timeslot.id)
        .outerjoin(
            models.LessonLog,
            and_(
                models.LessonLog.organization_id == organization_id,
                models.LessonLog.active_schedule_block_id == models.ActiveScheduleBlock.id,
            ),
        )
        .filter(
            models.ActiveScheduleBlock.organization_id == organization_id,
            models.ActiveScheduleBlock.teacher_id == teacher_id,
            models.ActiveScheduleBlock.status == models.ActiveScheduleBlockStatus.ACTIVE,
            models.ActiveScheduleBlock.date.between(week_start_date, week_end),
        )
        .all()
    )
    if not rows:
        raise AppError(
            kind="bad_request", code="bad_request", detail="Sem aulas planeadas nesta semana."
        )
    now = datetime.now()
    for block, timeslot, lesson_log in rows:
        if datetime.combine(block.date, timeslot.end_time) > now:
            raise AppError(
                kind="bad_request",
                code="bad_request",
                detail="Não pode submeter semanas com aulas no futuro.",
            )
        if lesson_log is None or lesson_log.status == models.LessonLogStatus.PENDING:
            raise AppError(
                kind="bad_request",
                code="bad_request",
                detail="Todas as aulas devem estar concluídas ou registadas como ocorrência.",
            )
    timesheet.status = models.TimesheetStatus.SUBMITTED
    timesheet.submitted_at = datetime.now(UTC)
    db.flush()
    db.refresh(timesheet)
    return timesheet


def _submit_v1_week(
    db: Session,
    timesheet: models.TeacherWeeklyTimesheet,
    organization_id: int,
    year_id: int,
    version: SchedulerVersionV1,
    teacher_id: int,
    week_start_date: date,
) -> models.TeacherWeeklyTimesheet:
    """Submit against the published v1 lessons and their execution ledger."""
    rows = _v1_week_lessons(db, organization_id, year_id, version, [teacher_id], week_start_date)
    blocks = _v1_week_operational_blocks(
        db, organization_id, year_id, [teacher_id], week_start_date
    )
    if not rows and not blocks:
        raise AppError(
            kind="bad_request", code="bad_request", detail="Sem aulas planeadas nesta semana."
        )
    now = datetime.now(UTC)
    for _teacher_id, lesson, lesson_log in rows:
        if lesson.ends_at > now:
            raise AppError(
                kind="bad_request",
                code="bad_request",
                detail="Não pode submeter semanas com aulas no futuro.",
            )
        if lesson_log is None or lesson_log.status == "REVOKED":
            raise AppError(
                kind="bad_request",
                code="bad_request",
                detail="Todas as aulas devem estar concluídas ou registadas como ocorrência.",
            )
    for _block, lesson, lesson_log in blocks:
        if lesson.ends_at > now:
            raise AppError(
                kind="bad_request",
                code="bad_request",
                detail="Não pode submeter semanas com aulas no futuro.",
            )
        if lesson_log is None or lesson_log.status != models.LessonLogStatus.COMPLETED:
            raise AppError(
                kind="bad_request",
                code="bad_request",
                detail="Todas as aulas devem estar concluídas ou registadas como ocorrência.",
            )
    timesheet.status = models.TimesheetStatus.SUBMITTED
    timesheet.submitted_at = datetime.now(UTC)
    db.flush()
    db.refresh(timesheet)
    return timesheet


def _compute_slot_counts_for_teachers(
    db: Session,
    organization_id: int,
    teacher_ids: list[int],
    week_start_date: date,
) -> dict[int, dict]:
    year_id, version = _active_v1_year_and_version(db, organization_id)
    if version is not None:
        return _v1_slot_counts(db, organization_id, year_id, version, teacher_ids, week_start_date)
    week_end = week_start_date + timedelta(days=6)
    rows = (
        db.query(
            models.ActiveScheduleBlock.teacher_id,
            models.ActiveScheduleBlock.id,
            models.LessonLog.status,
            models.LessonOccurrence.id.label("occurrence_id"),
        )
        .outerjoin(
            models.LessonLog,
            and_(
                models.LessonLog.organization_id == organization_id,
                models.LessonLog.active_schedule_block_id == models.ActiveScheduleBlock.id,
            ),
        )
        .outerjoin(
            models.LessonOccurrence,
            and_(
                models.LessonOccurrence.organization_id == organization_id,
                models.LessonOccurrence.active_schedule_block_id == models.ActiveScheduleBlock.id,
                models.LessonOccurrence.is_active.is_(True),
            ),
        )
        .filter(
            models.ActiveScheduleBlock.organization_id == organization_id,
            models.ActiveScheduleBlock.teacher_id.in_(teacher_ids),
            models.ActiveScheduleBlock.status == models.ActiveScheduleBlockStatus.ACTIVE,
            models.ActiveScheduleBlock.date.between(week_start_date, week_end),
        )
        .all()
    )
    counts = {
        teacher_id: {
            "total_slots": 0,
            "registered_slots": 0,
            "completed_slots": 0,
            "occurrence_slots": 0,
        }
        for teacher_id in teacher_ids
    }
    seen = set()
    for row in rows:
        key = (row.teacher_id, row.id)
        if key in seen:
            continue
        seen.add(key)
        item = counts[row.teacher_id]
        item["total_slots"] += 1
        if row.status is not None and row.status != models.LessonLogStatus.PENDING:
            item["registered_slots"] += 1
        if row.status == models.LessonLogStatus.COMPLETED:
            item["completed_slots"] += 1
        if row.status == models.LessonLogStatus.OCCURRENCE or row.occurrence_id is not None:
            item["occurrence_slots"] += 1
    return counts


def list_timesheets_sync(
    db: Session,
    organization_id: int,
    week_start_date: date | None = None,
    status: models.TimesheetStatus | None = None,
) -> list[dict]:
    """Admin lista as timesheets, podendo filtrar por semana ou estado."""
    if week_start_date is not None:
        roster_query = (
            db.query(
                models.Teacher.id.label("teacher_id"),
                models.Teacher.organization_id.label("organization_id"),
                models.OrganizationMembership.organization_display_name.label("teacher_name"),
                models.TeacherWeeklyTimesheet.id.label("timesheet_id"),
                models.TeacherWeeklyTimesheet.status.label("timesheet_status"),
                models.TeacherWeeklyTimesheet.submitted_at.label("submitted_at"),
                models.TeacherWeeklyTimesheet.approved_at.label("approved_at"),
                models.TeacherWeeklyTimesheet.approved_by_membership_id.label(
                    "approved_by_membership_id"
                ),
                models.TeacherWeeklyTimesheet.created_at.label("created_at"),
            )
            .join(
                models.OrganizationMembership,
                and_(
                    models.OrganizationMembership.id == models.Teacher.organization_membership_id,
                    models.OrganizationMembership.organization_id == organization_id,
                ),
            )
            .outerjoin(
                models.TeacherWeeklyTimesheet,
                and_(
                    models.TeacherWeeklyTimesheet.organization_id == organization_id,
                    models.TeacherWeeklyTimesheet.teacher_id == models.Teacher.id,
                    models.TeacherWeeklyTimesheet.week_start_date == week_start_date,
                ),
            )
            .filter(
                models.Teacher.organization_id == organization_id,
                models.OrganizationMembership.lifecycle_status
                == models.MembershipLifecycleStatus.active,
                models.OrganizationMembership.can_teach.is_(True),
            )
        )

        if status is not None:
            if status == models.TimesheetStatus.OPEN:
                roster_query = roster_query.filter(
                    or_(
                        models.TeacherWeeklyTimesheet.id.is_(None),
                        models.TeacherWeeklyTimesheet.status == status,
                    )
                )
            else:
                roster_query = roster_query.filter(models.TeacherWeeklyTimesheet.status == status)

        rows = roster_query.all()
        teacher_ids = [row.teacher_id for row in rows]
        slot_counts = (
            _compute_slot_counts_for_teachers(
                db,
                organization_id,
                teacher_ids,
                week_start_date,
            )
            if teacher_ids
            else {}
        )

        result = []
        for row in rows:
            counts = slot_counts.get(row.teacher_id, {})
            result.append(
                {
                    "id": row.timesheet_id,
                    "organization_id": row.organization_id,
                    "teacher_id": row.teacher_id,
                    "teacher_name": row.teacher_name,
                    "week_start_date": week_start_date,
                    "week_end_date": week_start_date + timedelta(days=6),
                    "status": row.timesheet_status or models.TimesheetStatus.OPEN,
                    "submitted_at": row.submitted_at,
                    "approved_at": row.approved_at,
                    "approved_by_membership_id": row.approved_by_membership_id,
                    "created_at": row.created_at,
                    "total_slots": counts.get("total_slots", 0),
                    "registered_slots": counts.get("registered_slots", 0),
                    "completed_slots": counts.get("completed_slots", 0),
                    "occurrence_slots": counts.get("occurrence_slots", 0),
                }
            )
        return result

    query = (
        db.query(models.TeacherWeeklyTimesheet)
        .options(joinedload(models.TeacherWeeklyTimesheet.teacher))
        .filter(models.TeacherWeeklyTimesheet.organization_id == organization_id)
    )

    if week_start_date:
        query = query.filter(models.TeacherWeeklyTimesheet.week_start_date == week_start_date)
    if status:
        query = query.filter(models.TeacherWeeklyTimesheet.status == status)

    timesheets = query.all()

    # WBS Fase 7.3: enriquecer com contagens de slots
    slot_counts: dict[int, dict] = {}
    if timesheets and week_start_date:
        teacher_ids = [t.teacher_id for t in timesheets]
        slot_counts = _compute_slot_counts_for_teachers(
            db, organization_id, teacher_ids, week_start_date
        )

    result = []
    for t in timesheets:
        counts = slot_counts.get(t.teacher_id, {})
        result.append(
            {
                "id": t.id,
                "organization_id": t.organization_id,
                "teacher_id": t.teacher_id,
                "teacher_name": t.teacher.name,
                "week_start_date": t.week_start_date,
                "week_end_date": t.week_start_date + timedelta(days=6),
                "status": t.status,
                "submitted_at": t.submitted_at,
                "approved_at": t.approved_at,
                "approved_by_membership_id": t.approved_by_membership_id,
                "created_at": t.created_at,
                "total_slots": counts.get("total_slots", 0),
                "registered_slots": counts.get("registered_slots", 0),
                "completed_slots": counts.get("completed_slots", 0),
                "occurrence_slots": counts.get("occurrence_slots", 0),
            }
        )
    return result


# Transições válidas do ciclo de vida do fecho semanal
ALLOWED_TIMESHEET_TRANSITIONS = {
    models.TimesheetStatus.OPEN: {models.TimesheetStatus.OPEN, models.TimesheetStatus.SUBMITTED},
    models.TimesheetStatus.SUBMITTED: {
        models.TimesheetStatus.SUBMITTED,
        models.TimesheetStatus.APPROVED,
        models.TimesheetStatus.OPEN,
    },
    models.TimesheetStatus.APPROVED: {models.TimesheetStatus.APPROVED, models.TimesheetStatus.OPEN},
}


def update_timesheet_status_sync(
    db: Session,
    organization_id: int,
    timesheet_id: int,
    status: models.TimesheetStatus,
    admin_membership_id: int,
) -> dict:
    timesheet = (
        db.query(models.TeacherWeeklyTimesheet)
        .filter(
            models.TeacherWeeklyTimesheet.id == timesheet_id,
            models.TeacherWeeklyTimesheet.organization_id == organization_id,
        )
        .first()
    )

    if not timesheet:
        raise AppError(
            kind="not_found", code="resource_not_found", detail="Timesheet não encontrada."
        )

    current = timesheet.status
    allowed = ALLOWED_TIMESHEET_TRANSITIONS.get(current, set())
    if status not in allowed:
        raise AppError(
            kind="bad_request",
            code="bad_request",
            detail=f"Transição de estado inválida: {current.value} â†’ {status.value}.",
        )

    timesheet.status = status
    if status == models.TimesheetStatus.APPROVED:
        timesheet.approved_at = datetime.now(UTC)
        timesheet.approved_by_membership_id = admin_membership_id

        # Ocorrencias comunicadas pelo professor permanecem pendentes para decisao admin.
    elif status == models.TimesheetStatus.OPEN:
        # Se for reaberta, limpa os campos de aprovação mas preserva a data de submissão
        timesheet.approved_at = None
        timesheet.approved_by_membership_id = None

    db.flush()
    db.refresh(timesheet)

    # Reload with teacher name
    db.refresh(timesheet, ["teacher"])

    return {
        "id": timesheet.id,
        "organization_id": timesheet.organization_id,
        "teacher_id": timesheet.teacher_id,
        "teacher_name": timesheet.teacher.name if timesheet.teacher else None,
        "week_start_date": timesheet.week_start_date,
        "week_end_date": timesheet.week_start_date + timedelta(days=6),
        "status": timesheet.status,
        "submitted_at": timesheet.submitted_at,
        "approved_at": timesheet.approved_at,
        "approved_by_membership_id": timesheet.approved_by_membership_id,
        "created_at": timesheet.created_at,
    }
