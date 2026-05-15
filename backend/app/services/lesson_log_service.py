from datetime import datetime, date, timezone, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from app.core.exceptions import DomainError, NotFoundError, ConflictError

from app import models, schemas
from app.services import occurrence_service, schedule_service

def _get_active_module_id(db: Session, class_id: int, subject_id: int) -> Optional[int]:
    """Helper to find the active module for a class/subject pair."""
    active_modules = schedule_service._fetch_active_modules(db, [(class_id, subject_id)])
    mod_data = active_modules.get((class_id, subject_id))
    return mod_data["id"] if mod_data else None

def _get_timeslot_duration_hours(timeslot: models.Timeslot) -> float:
    start_minutes = timeslot.start_time.hour * 60 + timeslot.start_time.minute
    end_minutes = timeslot.end_time.hour * 60 + timeslot.end_time.minute
    duration_minutes = max(0, end_minutes - start_minutes)
    return round(duration_minutes / 60.0, 4)

def upsert_lesson_log_sync(
    db: Session,
    organization_id: int,
    user_id: int,
    schedule_output_id: int,
    payload: schemas.LessonLogCreate
) -> models.LessonLog:
    """Cria ou atualiza o LessonLog de um bloco gerado pelo Solver."""
    
    # 1. Obter o ScheduleOutput e garantir que é da Org e não draft
    output = db.query(models.ScheduleOutput).filter(
        models.ScheduleOutput.id == schedule_output_id,
        models.ScheduleOutput.organization_id == organization_id,
        models.ScheduleOutput.is_draft == False
    ).first()
    
    if not output:
        raise NotFoundError("Bloco planeado não encontrado.")
        
    if not output.date:
        raise DomainError("Bloco planeado não tem data válida.", status_code=400)

    # 2. Bloqueio no tempo (Viagens ao futuro)
    timeslot = output.timeslot
    from datetime import timezone
    end_datetime = datetime.combine(output.date, timeslot.end_time, tzinfo=timezone.utc)
    if payload.status == models.LessonLogStatus.COMPLETED:
        if end_datetime > datetime.now(timezone.utc):
            raise DomainError("Não é possível registar estado para uma aula que ainda não terminou.", status_code=400)

    # 3. Check if the timesheet for this week is submitted/approved
    week_start_date = output.date - timedelta(days=output.date.weekday())
    timesheet = db.query(models.TeacherWeeklyTimesheet).filter(
        models.TeacherWeeklyTimesheet.organization_id == organization_id,
        models.TeacherWeeklyTimesheet.teacher_id == output.lesson.teacher_id,
        models.TeacherWeeklyTimesheet.week_start_date == week_start_date
    ).first()
    
    if timesheet and timesheet.status in (models.TimesheetStatus.SUBMITTED, models.TimesheetStatus.APPROVED):
        raise DomainError("Esta semana já foi submetida ou aprovada. Não é possível alterar registos.", status_code=400)

    # 4. Proteção contra sobrescrita de Ocorrência existente (GAP / SUBSTITUTED)
    # Se o user tenta meter COMPLETED, e há uma Ocorrência GAP/SUBSTITUTED, bloquear.
    occurrence = db.query(models.LessonOccurrence).filter(
        models.LessonOccurrence.schedule_output_id == schedule_output_id,
        models.LessonOccurrence.status.in_([
            models.LessonOccurrenceStatus.GAP,
            models.LessonOccurrenceStatus.SUBSTITUTED
        ])
    ).first()
    
    if payload.status == models.LessonLogStatus.COMPLETED and occurrence:
        raise ConflictError("Não pode concluir uma aula que tem uma Falta/Substituição registada.")

    # V4: Blocos de substituição são interativos — o substituto pode registar normalmente.

    # 5. Obter ou criar LessonLog
    llog = db.query(models.LessonLog).filter(
        models.LessonLog.schedule_output_id == schedule_output_id
    ).first()
    
    old_status = llog.status if llog else models.LessonLogStatus.PENDING

    if not llog:
        llog = models.LessonLog(
            organization_id=organization_id,
            schedule_output_id=schedule_output_id,
            status=payload.status,
            summary=payload.summary,
            notes=payload.notes,
            logged_by_user_id=user_id,
            logged_at=datetime.now(timezone.utc),
        )
        db.add(llog)
    else:
        llog.status = payload.status
        llog.summary = payload.summary
        llog.notes = payload.notes
        llog.logged_by_user_id = user_id
        llog.logged_at = datetime.now(timezone.utc)
        
    # 6. Refatorizar o Progresso da Disciplina
    # Se mudou de estado, aplicar contabilidade
    if old_status != payload.status:
        class_id = output.lesson.class_id
        subject_id = output.lesson.subject_id
        planned_module_id = _get_active_module_id(db, class_id, subject_id)
        planned_hours = _get_timeslot_duration_hours(timeslot)
        
        # PENDING/OCCURRENCE -> COMPLETED (+1)
        if payload.status == models.LessonLogStatus.COMPLETED:
            occurrence_service._apply_state_accounting(
                db,
                class_id=class_id,
                status=models.LessonOccurrenceStatus.GIVEN, # Usamos GIVEN para simular o delta positivo no modulo
                planned_module_id=planned_module_id,
                executed_module_id=planned_module_id,
                planned_hours=planned_hours,
                direction=1
            )
        # COMPLETED -> PENDING/OCCURRENCE (-1)
        elif old_status == models.LessonLogStatus.COMPLETED:
            occurrence_service._apply_state_accounting(
                db,
                class_id=class_id,
                status=models.LessonOccurrenceStatus.GIVEN, 
                planned_module_id=planned_module_id,
                executed_module_id=planned_module_id,
                planned_hours=planned_hours,
                direction=-1
            )

        # WBS V3 Fase 1.1: Auto-create LessonOccurrence OPEN when teacher marks OCCURRENCE
        if payload.status == models.LessonLogStatus.OCCURRENCE:
            db.flush()  # ensure the LessonLog status change is visible to downstream queries
            existing_occ = db.query(models.LessonOccurrence).filter(
                models.LessonOccurrence.schedule_output_id == schedule_output_id,
                models.LessonOccurrence.status != models.LessonOccurrenceStatus.REVOKED,
            ).first()
            if existing_occ is None:
                occurrence_service.create_occurrence_from_block_sync(
                    db,
                    organization_id=organization_id,
                    schedule_output_id=schedule_output_id,
                )

        # WBS V3 Fase 1.2: Cleanup OPEN occurrence when reverting from OCCURRENCE
        if old_status == models.LessonLogStatus.OCCURRENCE and payload.status != models.LessonLogStatus.OCCURRENCE:
            occurrence_service.cancel_open_occurrence_for_block_sync(
                db,
                organization_id=organization_id,
                schedule_output_id=schedule_output_id,
            )

    db.commit()
    db.refresh(llog)
    return llog
