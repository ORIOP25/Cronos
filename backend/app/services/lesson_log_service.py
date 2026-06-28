from datetime import datetime, timezone, timedelta
from typing import Optional
import uuid as _uuid
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
    ).with_for_update().first()
    
    if not output:
        raise NotFoundError("Bloco planeado não encontrado.")
        
    if not output.date:
        raise DomainError("Bloco planeado não tem data válida.", status_code=400)

    # 2. Bloqueio no tempo (Viagens ao futuro)
    timeslot = output.timeslot
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

    # 4. Proteção contra sobrescrita de Ocorrência existente (GAP / SUBSTITUTED / GIVEN)
    # Se o user tenta meter COMPLETED, e há uma Ocorrência ativa, bloquear.
    occurrence = db.query(models.LessonOccurrence).filter(
        models.LessonOccurrence.schedule_output_id == schedule_output_id,
        models.LessonOccurrence.is_active.is_(True),
        models.LessonOccurrence.status.in_([
            models.LessonOccurrenceStatus.GAP,
            models.LessonOccurrenceStatus.SUBSTITUTED,
            models.LessonOccurrenceStatus.GIVEN,
        ])
    ).first()
    
    if payload.status == models.LessonLogStatus.COMPLETED and occurrence:
        raise ConflictError("Não pode concluir uma aula que tem uma ocorrência ativa registada.")

    # V4: Blocos de substituição são interativos — o substituto pode registar normalmente.

    # 5. Obter ou criar LessonLog (with row lock to prevent concurrent double-count)
    llog = db.query(models.LessonLog).filter(
        models.LessonLog.schedule_output_id == schedule_output_id
    ).with_for_update().first()
    
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
            version=1,
        )
        db.add(llog)
    else:
        llog.version = int(llog.version or 1) + 1
        llog.status = payload.status
        llog.summary = payload.summary
        llog.notes = payload.notes
        llog.logged_by_user_id = user_id
        llog.logged_at = datetime.now(timezone.utc)
        
    # 6. Refatorizar o Progresso da Disciplina
    # Se mudou de estado, aplicar contabilidade
    if old_status != payload.status:
        log_revision = int(llog.version or 1)
        log_operation_id = str(_uuid.uuid5(_uuid.NAMESPACE_URL, f"lesson_log:{schedule_output_id}:{log_revision}:{old_status.value}->{payload.status.value}"))
        class_id = output.lesson.class_id
        subject_id = output.lesson.subject_id
        planned_module_id = _get_active_module_id(db, class_id, subject_id)
        planned_hours = _get_timeslot_duration_hours(timeslot)
        
        # PENDING/OCCURRENCE -> COMPLETED (+1)
        if payload.status == models.LessonLogStatus.COMPLETED:
            accounting_deltas = occurrence_service._apply_state_accounting(
                db,
                organization_id=organization_id,
                class_id=class_id,
                status=models.LessonOccurrenceStatus.GIVEN, # Usamos GIVEN para simular o delta positivo no modulo
                planned_module_id=planned_module_id,
                executed_module_id=planned_module_id,
                planned_hours=planned_hours,
                direction=1
            )
            db.flush()
            occurrence_service._record_progress_ledger_entries(
                db,
                organization_id=organization_id,
                source_type="LESSON_LOG",
                source_id=llog.id,
                source_revision=log_revision,
                class_id=class_id,
                status=models.LessonOccurrenceStatus.GIVEN,
                planned_module_id=planned_module_id,
                executed_module_id=planned_module_id,
                planned_hours=planned_hours,
                direction=1,
                actor_user_id=user_id,
                operation_id=log_operation_id,
                accounting_deltas=accounting_deltas,
            )
        # COMPLETED -> PENDING/OCCURRENCE (-1)
        elif old_status == models.LessonLogStatus.COMPLETED:
            accounting_deltas = occurrence_service._apply_state_accounting(
                db,
                organization_id=organization_id,
                class_id=class_id,
                status=models.LessonOccurrenceStatus.GIVEN,
                planned_module_id=planned_module_id,
                executed_module_id=planned_module_id,
                planned_hours=planned_hours,
                direction=-1
            )
            occurrence_service._record_progress_ledger_entries(
                db,
                organization_id=organization_id,
                source_type="LESSON_LOG",
                source_id=llog.id,
                source_revision=log_revision,
                class_id=class_id,
                status=models.LessonOccurrenceStatus.GIVEN,
                planned_module_id=planned_module_id,
                executed_module_id=planned_module_id,
                planned_hours=planned_hours,
                direction=-1,
                actor_user_id=user_id,
                operation_id=log_operation_id,
                accounting_deltas=accounting_deltas,
            )

        # WBS V3 Fase 1.1: Auto-create LessonOccurrence OPEN when teacher marks OCCURRENCE
        if payload.status == models.LessonLogStatus.OCCURRENCE:
            db.flush()  # ensure the LessonLog status change is visible to downstream queries
            existing_occ = db.query(models.LessonOccurrence).filter(
                models.LessonOccurrence.organization_id == organization_id,
                models.LessonOccurrence.schedule_output_id == schedule_output_id,
                models.LessonOccurrence.is_active.is_(True),
            ).first()
            if existing_occ is None:
                occurrence_service.create_occurrence_from_block_sync(
                    db,
                    organization_id=organization_id,
                    schedule_output_id=schedule_output_id,
                    created_by_user_id=user_id,
                    creation_source="lesson_log",
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


def _update_recovery_delivery_sync(
    db: Session,
    block: models.ActiveScheduleBlock,
    lesson_log: models.LessonLog,
    old_status: models.LessonLogStatus,
) -> None:
    if not block.is_recovery_block or old_status == lesson_log.status:
        return
    link = db.query(models.PlannedRecoveryLink).filter(
        models.PlannedRecoveryLink.organization_id == block.organization_id,
        models.PlannedRecoveryLink.school_year_id == block.school_year_id,
        models.PlannedRecoveryLink.planned_active_block_id == block.id,
    ).with_for_update().first()
    if link is None:
        raise ConflictError("Bloco de recuperacao sem ligacao de divida valida.")

    if lesson_log.status == models.LessonLogStatus.COMPLETED:
        if link.status not in (
            models.PlannedRecoveryLinkStatus.PLANNED,
            models.PlannedRecoveryLinkStatus.DELIVERED,
        ):
            raise ConflictError("A recuperacao ja nao esta disponivel para entrega.")
        if (
            link.status == models.PlannedRecoveryLinkStatus.DELIVERED
            and link.delivered_lesson_log_id != lesson_log.id
        ):
            raise ConflictError("A recuperacao ja foi entregue por outro registo.")
        link.status = models.PlannedRecoveryLinkStatus.DELIVERED
        link.delivered_recovery_minutes = min(
            block.duration_minutes, link.planned_recovery_minutes
        )
        link.delivered_lesson_log_id = lesson_log.id
        link.delivered_at = lesson_log.logged_at
    elif old_status == models.LessonLogStatus.COMPLETED:
        if (
            link.status == models.PlannedRecoveryLinkStatus.DELIVERED
            and link.delivered_lesson_log_id == lesson_log.id
        ):
            link.status = models.PlannedRecoveryLinkStatus.PLANNED
            link.delivered_recovery_minutes = 0
            link.delivered_lesson_log_id = None
            link.delivered_at = None


def upsert_active_lesson_log_sync(
    db: Session,
    organization_id: int,
    user_id: int,
    active_schedule_block_id: int,
    payload: schemas.LessonLogCreate,
) -> models.LessonLog:
    block = db.query(models.ActiveScheduleBlock).filter(
        models.ActiveScheduleBlock.id == active_schedule_block_id,
        models.ActiveScheduleBlock.organization_id == organization_id,
        models.ActiveScheduleBlock.status == models.ActiveScheduleBlockStatus.ACTIVE,
    ).with_for_update().first()
    if block is None:
        raise NotFoundError("Bloco do horario ativo nao encontrado.")

    timeslot = db.get(models.Timeslot, block.timeslot_id)
    if timeslot is None:
        raise DomainError("Bloco ativo sem horario valido.", status_code=409)
    end_datetime = datetime.combine(block.date, timeslot.end_time, tzinfo=timezone.utc)
    if (
        payload.status == models.LessonLogStatus.COMPLETED
        and end_datetime > datetime.now(timezone.utc)
    ):
        raise DomainError(
            "Nao e possivel registar estado para uma aula que ainda nao terminou.",
            status_code=400,
        )

    week_start_date = block.date - timedelta(days=block.date.weekday())
    timesheet = db.query(models.TeacherWeeklyTimesheet).filter(
        models.TeacherWeeklyTimesheet.organization_id == organization_id,
        models.TeacherWeeklyTimesheet.teacher_id == block.teacher_id,
        models.TeacherWeeklyTimesheet.week_start_date == week_start_date,
    ).first()
    if timesheet and timesheet.status in (
        models.TimesheetStatus.SUBMITTED,
        models.TimesheetStatus.APPROVED,
    ):
        raise DomainError(
            "Esta semana ja foi submetida ou aprovada. Nao e possivel alterar registos.",
            status_code=400,
        )

    occurrence = db.query(models.LessonOccurrence).filter(
        models.LessonOccurrence.organization_id == organization_id,
        models.LessonOccurrence.active_schedule_block_id == block.id,
        models.LessonOccurrence.is_active.is_(True),
        models.LessonOccurrence.status.in_([
            models.LessonOccurrenceStatus.GAP,
            models.LessonOccurrenceStatus.SUBSTITUTED,
            models.LessonOccurrenceStatus.GIVEN,
        ]),
    ).first()
    if payload.status == models.LessonLogStatus.COMPLETED and occurrence:
        raise ConflictError(
            "Nao pode concluir uma aula que tem uma ocorrencia ativa registada."
        )

    lesson_log = db.query(models.LessonLog).filter(
        models.LessonLog.organization_id == organization_id,
        models.LessonLog.active_schedule_block_id == block.id,
    ).with_for_update().first()
    old_status = (
        lesson_log.status if lesson_log else models.LessonLogStatus.PENDING
    )
    if lesson_log is None:
        lesson_log = models.LessonLog(
            organization_id=organization_id,
            active_schedule_block_id=block.id,
            status=payload.status,
            version=1,
        )
        db.add(lesson_log)
    else:
        lesson_log.version = int(lesson_log.version or 1) + 1
        lesson_log.status = payload.status
    lesson_log.summary = payload.summary
    lesson_log.notes = payload.notes
    lesson_log.logged_by_user_id = user_id
    lesson_log.logged_at = datetime.now(timezone.utc)
    db.flush()

    if old_status != payload.status:
        planned_module_id = _get_active_module_id(
            db, block.class_id, block.subject_id
        )
        planned_hours = round(block.duration_minutes / 60.0, 4)
        log_revision = int(lesson_log.version or 1)
        operation_id = str(_uuid.uuid5(
            _uuid.NAMESPACE_URL,
            f"active_lesson_log:{block.id}:{log_revision}:"
            f"{old_status.value}->{payload.status.value}",
        ))
        if payload.status == models.LessonLogStatus.COMPLETED:
            deltas = occurrence_service._apply_state_accounting(
                db,
                organization_id=organization_id,
                class_id=block.class_id,
                status=models.LessonOccurrenceStatus.GIVEN,
                planned_module_id=planned_module_id,
                executed_module_id=planned_module_id,
                planned_hours=planned_hours,
                direction=1,
            )
            occurrence_service._record_progress_ledger_entries(
                db,
                organization_id=organization_id,
                source_type="LESSON_LOG",
                source_id=lesson_log.id,
                source_revision=log_revision,
                class_id=block.class_id,
                status=models.LessonOccurrenceStatus.GIVEN,
                planned_module_id=planned_module_id,
                executed_module_id=planned_module_id,
                planned_hours=planned_hours,
                direction=1,
                actor_user_id=user_id,
                operation_id=operation_id,
                accounting_deltas=deltas,
            )
        elif old_status == models.LessonLogStatus.COMPLETED:
            deltas = occurrence_service._apply_state_accounting(
                db,
                organization_id=organization_id,
                class_id=block.class_id,
                status=models.LessonOccurrenceStatus.GIVEN,
                planned_module_id=planned_module_id,
                executed_module_id=planned_module_id,
                planned_hours=planned_hours,
                direction=-1,
            )
            occurrence_service._record_progress_ledger_entries(
                db,
                organization_id=organization_id,
                source_type="LESSON_LOG",
                source_id=lesson_log.id,
                source_revision=log_revision,
                class_id=block.class_id,
                status=models.LessonOccurrenceStatus.GIVEN,
                planned_module_id=planned_module_id,
                executed_module_id=planned_module_id,
                planned_hours=planned_hours,
                direction=-1,
                actor_user_id=user_id,
                operation_id=operation_id,
                accounting_deltas=deltas,
            )

        if payload.status == models.LessonLogStatus.OCCURRENCE:
            occurrence_service.create_occurrence_from_active_block_sync(
                db,
                organization_id=organization_id,
                active_schedule_block_id=block.id,
                created_by_user_id=user_id,
            )
        if (
            old_status == models.LessonLogStatus.OCCURRENCE
            and payload.status != models.LessonLogStatus.OCCURRENCE
        ):
            occurrence_service.cancel_open_occurrence_for_active_block_sync(
                db,
                organization_id=organization_id,
                active_schedule_block_id=block.id,
            )
        _update_recovery_delivery_sync(db, block, lesson_log, old_status)

    db.commit()
    db.refresh(lesson_log)
    return lesson_log


def upsert_operational_lesson_log_sync(
    db: Session,
    organization_id: int,
    user_id: int,
    operational_block_id: int,
    payload: schemas.LessonLogCreate,
) -> models.LessonLog:
    block = db.query(models.OperationalScheduleBlock).filter(
        models.OperationalScheduleBlock.id == operational_block_id,
        models.OperationalScheduleBlock.organization_id == organization_id,
        models.OperationalScheduleBlock.status == models.OperationalBlockStatus.ACTIVE,
    ).with_for_update().first()
    if block is None:
        raise NotFoundError("Bloco operacional nao encontrado.")

    if payload.status == models.LessonLogStatus.OCCURRENCE:
        raise DomainError(
            "Blocos operacionais nao podem originar novas ocorrencias.",
            status_code=422,
        )

    week_start_date = block.date - timedelta(days=block.date.weekday())
    timesheet = db.query(models.TeacherWeeklyTimesheet).filter(
        models.TeacherWeeklyTimesheet.organization_id == organization_id,
        models.TeacherWeeklyTimesheet.teacher_id == block.teacher_id,
        models.TeacherWeeklyTimesheet.week_start_date == week_start_date,
    ).first()
    if timesheet and timesheet.status in (models.TimesheetStatus.SUBMITTED, models.TimesheetStatus.APPROVED):
        raise DomainError("Esta semana ja foi submetida ou aprovada. Nao e possivel alterar registos.", status_code=400)

    old_log = db.query(models.LessonLog).filter(
        models.LessonLog.operational_block_id == operational_block_id,
    ).with_for_update().first()
    old_status = old_log.status if old_log else models.LessonLogStatus.PENDING

    if old_log is None:
        old_log = models.LessonLog(
            organization_id=organization_id,
            operational_block_id=operational_block_id,
            status=payload.status,
            summary=payload.summary,
            notes=payload.notes,
            logged_by_user_id=user_id,
            logged_at=datetime.now(timezone.utc),
            version=1,
        )
        db.add(old_log)
    else:
        old_log.version = int(old_log.version or 1) + 1
        old_log.status = payload.status
        old_log.summary = payload.summary
        old_log.notes = payload.notes
        old_log.logged_by_user_id = user_id
        old_log.logged_at = datetime.now(timezone.utc)

    if old_status != payload.status:
        log_revision = int(old_log.version or 1)
        op_log_operation_id = str(_uuid.uuid5(_uuid.NAMESPACE_URL, f"op_log:{operational_block_id}:{log_revision}:{old_status.value}->{payload.status.value}"))
        planned_hours = _get_timeslot_duration_hours(block.timeslot)
        if payload.status == models.LessonLogStatus.COMPLETED:
            accounting_deltas = occurrence_service._apply_state_accounting(
                db,
                organization_id=organization_id,
                class_id=block.class_id,
                status=models.LessonOccurrenceStatus.GIVEN,
                planned_module_id=block.module_id,
                executed_module_id=block.module_id,
                planned_hours=planned_hours,
                direction=1,
            )
            db.flush()
            occurrence_service._record_progress_ledger_entries(
                db,
                organization_id=organization_id,
                source_type="LESSON_LOG",
                source_id=old_log.id,
                source_revision=log_revision,
                class_id=block.class_id,
                status=models.LessonOccurrenceStatus.GIVEN,
                planned_module_id=block.module_id,
                executed_module_id=block.module_id,
                planned_hours=planned_hours,
                direction=1,
                actor_user_id=user_id,
                operation_id=op_log_operation_id,
                accounting_deltas=accounting_deltas,
            )
            block.execution_status = models.OperationalBlockExecutionStatus.COMPLETED
        elif old_status == models.LessonLogStatus.COMPLETED:
            accounting_deltas = occurrence_service._apply_state_accounting(
                db,
                organization_id=organization_id,
                class_id=block.class_id,
                status=models.LessonOccurrenceStatus.GIVEN,
                planned_module_id=block.module_id,
                executed_module_id=block.module_id,
                planned_hours=planned_hours,
                direction=-1,
            )
            occurrence_service._record_progress_ledger_entries(
                db,
                organization_id=organization_id,
                source_type="LESSON_LOG",
                source_id=old_log.id,
                source_revision=log_revision,
                class_id=block.class_id,
                status=models.LessonOccurrenceStatus.GIVEN,
                planned_module_id=block.module_id,
                executed_module_id=block.module_id,
                planned_hours=planned_hours,
                direction=-1,
                actor_user_id=user_id,
                operation_id=op_log_operation_id,
                accounting_deltas=accounting_deltas,
            )
            block.execution_status = models.OperationalBlockExecutionStatus.PENDING_LOG

    db.commit()
    db.refresh(old_log)
    return old_log
