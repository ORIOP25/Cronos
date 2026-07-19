from datetime import UTC, date, datetime, timedelta

from sqlalchemy import and_
from sqlalchemy.orm import Session, joinedload

from app import models
from app.core.exceptions import DomainError, NotFoundError


def get_or_create_timesheet_sync(
    db: Session, organization_id: int, teacher_id: int, week_start_date: date
) -> models.TeacherWeeklyTimesheet:
    """ObtÃ©m ou cria a timesheet de uma determinada semana para o professor."""
    timesheet = (
        db.query(models.TeacherWeeklyTimesheet)
        .filter(
            models.TeacherWeeklyTimesheet.organization_id == organization_id,
            models.TeacherWeeklyTimesheet.teacher_id == teacher_id,
            models.TeacherWeeklyTimesheet.week_start_date == week_start_date,
        )
        .first()
    )

    if not timesheet:
        timesheet = models.TeacherWeeklyTimesheet(
            organization_id=organization_id,
            teacher_id=teacher_id,
            week_start_date=week_start_date,
            status=models.TimesheetStatus.OPEN,
        )
        db.add(timesheet)
        db.flush()
        db.refresh(timesheet)

    return timesheet


def submit_timesheet_sync(
    db: Session,
    organization_id: int,
    teacher_id: int,
    week_start_date: date,
) -> models.TeacherWeeklyTimesheet:
    """Submit a week only after every published block is resolved."""
    timesheet = get_or_create_timesheet_sync(db, organization_id, teacher_id, week_start_date)
    if timesheet.status != models.TimesheetStatus.OPEN:
        raise DomainError("A semana jÃ¡ nÃ£o estÃ¡ aberta para submissÃ£o.", status_code=400)

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
        raise DomainError("Sem aulas planeadas nesta semana.", status_code=400)
    now = datetime.now()
    for block, timeslot, lesson_log in rows:
        if datetime.combine(block.date, timeslot.end_time) > now:
            raise DomainError("NÃ£o pode submeter semanas com aulas no futuro.", status_code=400)
        if lesson_log is None or lesson_log.status == models.LessonLogStatus.PENDING:
            raise DomainError(
                "Todas as aulas devem estar concluÃ­das ou registadas como ocorrÃªncia.",
                status_code=400,
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


# TransiÃ§Ãµes vÃ¡lidas do ciclo de vida do fecho semanal
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
        raise NotFoundError("Timesheet nÃ£o encontrada.")

    current = timesheet.status
    allowed = ALLOWED_TIMESHEET_TRANSITIONS.get(current, set())
    if status not in allowed:
        raise DomainError(
            f"TransiÃ§Ã£o de estado invÃ¡lida: {current.value} â†’ {status.value}.",
            status_code=400,
        )

    timesheet.status = status
    if status == models.TimesheetStatus.APPROVED:
        timesheet.approved_at = datetime.now(UTC)
        timesheet.approved_by_membership_id = admin_membership_id

        # Ocorrencias comunicadas pelo professor permanecem pendentes para decisao admin.
    elif status == models.TimesheetStatus.OPEN:
        # Se for reaberta, limpa os campos de aprovaÃ§Ã£o mas preserva a data de submissÃ£o
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


def get_open_occurrences_for_timesheet_sync(
    db: Session,
    organization_id: int,
    timesheet_id: int,
) -> list[dict]:
    timesheet = (
        db.query(models.TeacherWeeklyTimesheet)
        .filter(
            models.TeacherWeeklyTimesheet.id == timesheet_id,
            models.TeacherWeeklyTimesheet.organization_id == organization_id,
        )
        .first()
    )
    if timesheet is None:
        raise NotFoundError("Timesheet nÃ£o encontrada.")
    week_end = timesheet.week_start_date + timedelta(days=6)
    occurrences = (
        db.query(models.LessonOccurrence)
        .join(
            models.ActiveScheduleBlock,
            models.LessonOccurrence.active_schedule_block_id == models.ActiveScheduleBlock.id,
        )
        .filter(
            models.LessonOccurrence.organization_id == organization_id,
            models.ActiveScheduleBlock.organization_id == organization_id,
            models.ActiveScheduleBlock.teacher_id == timesheet.teacher_id,
            models.ActiveScheduleBlock.status == models.ActiveScheduleBlockStatus.ACTIVE,
            models.LessonOccurrence.date.between(timesheet.week_start_date, week_end),
            models.LessonOccurrence.decided_at.is_(None),
            models.LessonOccurrence.is_active.is_(True),
        )
        .all()
    )
    return [
        {
            "occurrence_id": occurrence.id,
            "active_schedule_block_id": occurrence.active_schedule_block_id,
            "date": occurrence.date.isoformat(),
            "subject_name": (
                db.get(models.Subject, occurrence.subject_id).name
                if occurrence.subject_id
                else None
            ),
            "teacher_name": (
                db.get(models.Teacher, occurrence.planned_teacher_id).name
                if occurrence.planned_teacher_id
                else None
            ),
            "created_at": occurrence.created_at.isoformat() if occurrence.created_at else None,
        }
        for occurrence in occurrences
    ]
