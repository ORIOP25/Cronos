from datetime import date, datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_
from fastapi import HTTPException

from app import models, schemas
from typing import List, Optional

def get_or_create_timesheet_sync(
    db: Session,
    organization_id: int,
    teacher_id: int,
    week_start_date: date
) -> models.TeacherWeeklyTimesheet:
    """Obtém ou cria a timesheet de uma determinada semana para o professor."""
    timesheet = db.query(models.TeacherWeeklyTimesheet).filter(
        models.TeacherWeeklyTimesheet.organization_id == organization_id,
        models.TeacherWeeklyTimesheet.teacher_id == teacher_id,
        models.TeacherWeeklyTimesheet.week_start_date == week_start_date
    ).first()

    if not timesheet:
        week_end_date = week_start_date + timedelta(days=6)
        timesheet = models.TeacherWeeklyTimesheet(
            organization_id=organization_id,
            teacher_id=teacher_id,
            week_start_date=week_start_date,
            week_end_date=week_end_date,
            status=models.TimesheetStatus.OPEN,
        )
        db.add(timesheet)
        db.commit()
        db.refresh(timesheet)
        
    return timesheet

def submit_timesheet_sync(
    db: Session,
    organization_id: int,
    teacher_id: int,
    week_start_date: date
) -> models.TeacherWeeklyTimesheet:
    """O professor submete a sua semana."""
    timesheet = get_or_create_timesheet_sync(db, organization_id, teacher_id, week_start_date)
    
    if timesheet.status != models.TimesheetStatus.OPEN:
        raise HTTPException(status_code=400, detail="A semana já não está aberta para submissão.")

    # Validate that all slots are logged and no future slots exist.
    # We fetch all schedule outputs for this teacher in this week.
    week_end_date = week_start_date + timedelta(days=6)
    
    outputs = db.query(models.ScheduleOutput).join(
        models.Lesson, models.ScheduleOutput.lesson_id == models.Lesson.id
    ).filter(
        models.ScheduleOutput.organization_id == organization_id,
        models.Lesson.teacher_id == teacher_id,
        models.ScheduleOutput.is_draft == False,
        models.ScheduleOutput.date.between(week_start_date, week_end_date)
    ).all()
    
    if not outputs:
        raise HTTPException(status_code=400, detail="Sem aulas planeadas nesta semana.")
        
    output_ids = [o.id for o in outputs]
    
    logs = db.query(models.LessonLog).filter(
        models.LessonLog.schedule_output_id.in_(output_ids)
    ).all()
    
    log_map = {log.schedule_output_id: log.status for log in logs}
    
    now = datetime.now()
    
    for o in outputs:
        # Check if in future
        end_datetime = datetime.combine(o.date, o.timeslot.end_time)
        if end_datetime > now:
            raise HTTPException(status_code=400, detail="Não pode submeter semanas com aulas no futuro.")
            
        status = log_map.get(o.id)
        if not status or status == models.LessonLogStatus.PENDING:
            raise HTTPException(status_code=400, detail="Todas as aulas devem estar concluídas ou registadas como ocorrência.")
            
    timesheet.status = models.TimesheetStatus.SUBMITTED
    timesheet.submitted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(timesheet)
    
    return timesheet

def _compute_slot_counts_for_teachers(
    db: Session,
    organization_id: int,
    teacher_ids: list[int],
    week_start_date: date,
) -> dict[int, dict]:
    """Retorna contagens de slots por teacher_id para uma semana específica.

    total_slots: outputs não-draft do professor na semana
    registered_slots: com LessonLog.status != PENDING
    completed_slots: com LessonLog.status == COMPLETED
    occurrence_slots: com LessonLog.status == OCCURRENCE OU LessonOccurrence ativa
    """
    from sqlalchemy import case, func
    week_end_date = week_start_date + timedelta(days=6)

    registered_expr = func.sum(
        case(
            (
                models.LessonLog.status.isnot(None)
                & (models.LessonLog.status != models.LessonLogStatus.PENDING),
                1,
            ),
            else_=0,
        )
    ).label("registered")

    completed_expr = func.sum(
        case(
            (models.LessonLog.status == models.LessonLogStatus.COMPLETED, 1),
            else_=0,
        )
    ).label("completed")

    occurrence_expr = func.sum(
        case(
            (
                (models.LessonLog.status == models.LessonLogStatus.OCCURRENCE)
                | (models.LessonOccurrence.id.isnot(None)),
                1,
            ),
            else_=0,
        )
    ).label("occurrence")

    rows = db.query(
        models.Lesson.teacher_id,
        func.count(models.ScheduleOutput.id).label("total"),
        registered_expr,
        completed_expr,
        occurrence_expr,
    ).join(
        models.Lesson, models.ScheduleOutput.lesson_id == models.Lesson.id
    ).outerjoin(
        models.LessonLog,
        models.LessonLog.schedule_output_id == models.ScheduleOutput.id,
    ).outerjoin(
        models.LessonOccurrence,
        models.LessonOccurrence.schedule_output_id == models.ScheduleOutput.id,
    ).filter(
        models.ScheduleOutput.organization_id == organization_id,
        models.Lesson.teacher_id.in_(teacher_ids),
        models.ScheduleOutput.is_draft.is_(False),
        models.ScheduleOutput.date.between(week_start_date, week_end_date),
    ).group_by(
        models.Lesson.teacher_id
    ).all()

    return {
        row.teacher_id: {
            "total_slots": row.total or 0,
            "registered_slots": row.registered or 0,
            "completed_slots": row.completed or 0,
            "occurrence_slots": row.occurrence or 0,
        }
        for row in rows
    }


def list_timesheets_sync(
    db: Session,
    organization_id: int,
    week_start_date: Optional[date] = None,
    status: Optional[models.TimesheetStatus] = None
) -> List[dict]:
    """Admin lista as timesheets, podendo filtrar por semana ou estado."""
    query = db.query(models.TeacherWeeklyTimesheet).join(
        models.Teacher, models.TeacherWeeklyTimesheet.teacher_id == models.Teacher.id
    ).filter(models.TeacherWeeklyTimesheet.organization_id == organization_id)
    
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
        result.append({
            "id": t.id,
            "organization_id": t.organization_id,
            "teacher_id": t.teacher_id,
            "teacher_name": t.teacher.name,
            "week_start_date": t.week_start_date,
            "week_end_date": t.week_end_date,
            "status": t.status,
            "submitted_at": t.submitted_at,
            "approved_at": t.approved_at,
            "approved_by_user_id": t.approved_by_user_id,
            "created_at": t.created_at,
            "total_slots": counts.get("total_slots", 0),
            "registered_slots": counts.get("registered_slots", 0),
            "completed_slots": counts.get("completed_slots", 0),
            "occurrence_slots": counts.get("occurrence_slots", 0),
        })
    return result

# Transições válidas do ciclo de vida do fecho semanal
ALLOWED_TIMESHEET_TRANSITIONS = {
    models.TimesheetStatus.OPEN: {models.TimesheetStatus.OPEN, models.TimesheetStatus.SUBMITTED},
    models.TimesheetStatus.SUBMITTED: {models.TimesheetStatus.SUBMITTED, models.TimesheetStatus.APPROVED, models.TimesheetStatus.OPEN},
    models.TimesheetStatus.APPROVED: {models.TimesheetStatus.APPROVED, models.TimesheetStatus.OPEN},
}


def update_timesheet_status_sync(
    db: Session,
    organization_id: int,
    timesheet_id: int,
    status: models.TimesheetStatus,
    admin_user_id: int
) -> dict:
    timesheet = db.query(models.TeacherWeeklyTimesheet).filter(
        models.TeacherWeeklyTimesheet.id == timesheet_id,
        models.TeacherWeeklyTimesheet.organization_id == organization_id
    ).first()

    if not timesheet:
        raise HTTPException(status_code=404, detail="Timesheet não encontrada.")

    current = timesheet.status
    allowed = ALLOWED_TIMESHEET_TRANSITIONS.get(current, set())
    if status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Transição de estado inválida: {current.value} → {status.value}."
        )

    timesheet.status = status
    if status == models.TimesheetStatus.APPROVED:
        timesheet.approved_at = datetime.now(timezone.utc)
        timesheet.approved_by_user_id = admin_user_id
    elif status == models.TimesheetStatus.OPEN:
        # Se for reaberta, limpa os campos de aprovação mas preserva a data de submissão
        timesheet.approved_at = None
        timesheet.approved_by_user_id = None
        
    db.commit()
    db.refresh(timesheet)
    
    # Reload with teacher name
    db.refresh(timesheet, ['teacher'])
    
    return {
        "id": timesheet.id,
        "organization_id": timesheet.organization_id,
        "teacher_id": timesheet.teacher_id,
        "teacher_name": timesheet.teacher.name if timesheet.teacher else None,
        "week_start_date": timesheet.week_start_date,
        "week_end_date": timesheet.week_end_date,
        "status": timesheet.status,
        "submitted_at": timesheet.submitted_at,
        "approved_at": timesheet.approved_at,
        "approved_by_user_id": timesheet.approved_by_user_id,
        "created_at": timesheet.created_at,
    }
