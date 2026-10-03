import uuid as _uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.exceptions import AppError
from app.scheduler.domain.lesson_time import execution_allowed
from app.services import occurrence_service, schedule_service


def _lesson_end_datetime(db: Session, organization_id: int, lesson_date, end_time) -> datetime:
    """Normalize a legacy lesson end to the configured school timezone."""
    timezone_name = db.scalar(
        select(models.SchedulerSchoolYear.timezone).where(
            models.SchedulerSchoolYear.organization_id == organization_id,
            models.SchedulerSchoolYear.is_active.is_(True),
        )
    )
    zone = ZoneInfo(timezone_name or "Europe/Lisbon")
    return datetime.combine(lesson_date, end_time, tzinfo=zone)


def _require_lesson_finished(
    db: Session, organization_id: int, lesson_date, end_time, status: models.LessonLogStatus
) -> None:
    if status != models.LessonLogStatus.COMPLETED:
        return
    end_datetime = _lesson_end_datetime(db, organization_id, lesson_date, end_time)
    if not execution_allowed(datetime.now(UTC), end_datetime):
        raise AppError(
            kind="validation",
            code="lesson_not_finished",
            detail="Só pode concluir esta aula depois do seu término.",
        )


def _get_active_module_id(db: Session, class_id: int, subject_id: int) -> int | None:
    """Helper to find the active module for a class/subject pair."""
    active_modules = schedule_service._fetch_active_modules(db, [(class_id, subject_id)])
    mod_data = active_modules.get((class_id, subject_id))
    return mod_data["id"] if mod_data else None


def _get_timeslot_duration_hours(timeslot: models.Timeslot) -> float:
    start_minutes = timeslot.start_time.hour * 60 + timeslot.start_time.minute
    end_minutes = timeslot.end_time.hour * 60 + timeslot.end_time.minute
    duration_minutes = max(0, end_minutes - start_minutes)
    return round(duration_minutes / 60.0, 4)


def _update_recovery_delivery_sync(
    db: Session,
    block: models.ActiveScheduleBlock,
    lesson_log: models.LessonLog,
    old_status: models.LessonLogStatus,
) -> None:
    if not block.is_recovery_block or old_status == lesson_log.status:
        return
    link = (
        db.query(models.PlannedRecoveryLink)
        .filter(
            models.PlannedRecoveryLink.organization_id == block.organization_id,
            models.PlannedRecoveryLink.school_year_id == block.school_year_id,
            models.PlannedRecoveryLink.planned_active_block_id == block.id,
        )
        .with_for_update()
        .first()
    )
    if link is None:
        raise AppError(
            kind="conflict",
            code="conflict",
            detail="Bloco de recuperacao sem ligacao de divida valida.",
        )

    if lesson_log.status == models.LessonLogStatus.COMPLETED:
        if link.status not in (
            models.PlannedRecoveryLinkStatus.PLANNED,
            models.PlannedRecoveryLinkStatus.DELIVERED,
        ):
            raise AppError(
                kind="conflict",
                code="conflict",
                detail="A recuperacao ja nao esta disponivel para entrega.",
            )
        if (
            link.status == models.PlannedRecoveryLinkStatus.DELIVERED
            and link.delivered_lesson_log_id != lesson_log.id
        ):
            raise AppError(
                kind="conflict",
                code="conflict",
                detail="A recuperacao ja foi entregue por outro registo.",
            )
        link.status = models.PlannedRecoveryLinkStatus.DELIVERED
        link.delivered_recovery_minutes = min(block.duration_minutes, link.planned_recovery_minutes)
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
    membership_id: int,
    active_schedule_block_id: int,
    payload: schemas.LessonLogCreate,
) -> models.LessonLog:
    block = (
        db.query(models.ActiveScheduleBlock)
        .filter(
            models.ActiveScheduleBlock.id == active_schedule_block_id,
            models.ActiveScheduleBlock.organization_id == organization_id,
            models.ActiveScheduleBlock.status == models.ActiveScheduleBlockStatus.ACTIVE,
        )
        .with_for_update()
        .first()
    )
    if block is None:
        raise AppError(
            kind="not_found",
            code="resource_not_found",
            detail="Bloco do horario ativo nao encontrado.",
        )

    timeslot = db.get(models.Timeslot, block.timeslot_id)
    if timeslot is None:
        raise AppError(kind="conflict", code="conflict", detail="Bloco ativo sem horario valido.")
    _require_lesson_finished(db, organization_id, block.date, timeslot.end_time, payload.status)

    week_start_date = block.date - timedelta(days=block.date.weekday())
    timesheet = (
        db.query(models.TeacherWeeklyTimesheet)
        .filter(
            models.TeacherWeeklyTimesheet.organization_id == organization_id,
            models.TeacherWeeklyTimesheet.teacher_id == block.teacher_id,
            models.TeacherWeeklyTimesheet.week_start_date == week_start_date,
        )
        .first()
    )
    if timesheet and timesheet.status in (
        models.TimesheetStatus.SUBMITTED,
        models.TimesheetStatus.APPROVED,
    ):
        raise AppError(
            kind="bad_request",
            code="bad_request",
            detail="Esta semana ja foi submetida ou aprovada. Nao e possivel alterar registos.",
        )

    occurrence = (
        db.query(models.LessonOccurrence)
        .filter(
            models.LessonOccurrence.organization_id == organization_id,
            models.LessonOccurrence.active_schedule_block_id == block.id,
            models.LessonOccurrence.is_active.is_(True),
            models.LessonOccurrence.status.in_(
                [
                    models.LessonOccurrenceStatus.GAP,
                    models.LessonOccurrenceStatus.SUBSTITUTED,
                    models.LessonOccurrenceStatus.GIVEN,
                ]
            ),
        )
        .first()
    )
    if payload.status == models.LessonLogStatus.COMPLETED and occurrence:
        raise AppError(
            kind="conflict",
            code="conflict",
            detail="Nao pode concluir uma aula que tem uma ocorrencia ativa registada.",
        )

    lesson_log = (
        db.query(models.LessonLog)
        .filter(
            models.LessonLog.organization_id == organization_id,
            models.LessonLog.active_schedule_block_id == block.id,
        )
        .with_for_update()
        .first()
    )
    old_status = lesson_log.status if lesson_log else models.LessonLogStatus.PENDING
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
    lesson_log.logged_by_membership_id = membership_id
    lesson_log.logged_at = datetime.now(UTC)
    db.flush()

    if old_status != payload.status:
        planned_module_id = _get_active_module_id(db, block.class_id, block.subject_id)
        planned_hours = round(block.duration_minutes / 60.0, 4)
        log_revision = int(lesson_log.version or 1)
        operation_id = str(
            _uuid.uuid5(
                _uuid.NAMESPACE_URL,
                f"active_lesson_log:{block.id}:{log_revision}:"
                f"{old_status.value}->{payload.status.value}",
            )
        )
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
                occurrence_service.ProgressLedgerContext(
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
                    actor_membership_id=membership_id,
                    operation_id=operation_id,
                    accounting_deltas=deltas,
                ),
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
                occurrence_service.ProgressLedgerContext(
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
                    actor_membership_id=membership_id,
                    operation_id=operation_id,
                    accounting_deltas=deltas,
                ),
            )

        if payload.status == models.LessonLogStatus.OCCURRENCE:
            occurrence_service.create_occurrence_from_active_block_sync(
                db,
                organization_id=organization_id,
                active_schedule_block_id=block.id,
                created_by_membership_id=membership_id,
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

    db.flush()
    db.refresh(lesson_log)
    return lesson_log


def upsert_operational_lesson_log_sync(
    db: Session,
    organization_id: int,
    membership_id: int,
    operational_block_id: int,
    payload: schemas.LessonLogCreate,
) -> models.LessonLog:
    block = (
        db.query(models.OperationalScheduleBlock)
        .filter(
            models.OperationalScheduleBlock.id == operational_block_id,
            models.OperationalScheduleBlock.organization_id == organization_id,
            models.OperationalScheduleBlock.status == models.OperationalBlockStatus.ACTIVE,
        )
        .with_for_update()
        .first()
    )
    if block is None:
        raise AppError(
            kind="not_found", code="resource_not_found", detail="Bloco operacional nao encontrado."
        )

    if payload.status == models.LessonLogStatus.OCCURRENCE:
        raise AppError(
            kind="validation",
            code="validation_error",
            detail="Blocos operacionais nao podem originar novas ocorrencias.",
        )

    timeslot = db.get(models.Timeslot, block.timeslot_id)
    if timeslot is None:
        raise AppError(
            kind="conflict", code="conflict", detail="Bloco operacional sem horario valido."
        )
    _require_lesson_finished(db, organization_id, block.date, timeslot.end_time, payload.status)

    week_start_date = block.date - timedelta(days=block.date.weekday())
    timesheet = (
        db.query(models.TeacherWeeklyTimesheet)
        .filter(
            models.TeacherWeeklyTimesheet.organization_id == organization_id,
            models.TeacherWeeklyTimesheet.teacher_id == block.teacher_id,
            models.TeacherWeeklyTimesheet.week_start_date == week_start_date,
        )
        .first()
    )
    if timesheet and timesheet.status in (
        models.TimesheetStatus.SUBMITTED,
        models.TimesheetStatus.APPROVED,
    ):
        raise AppError(
            kind="bad_request",
            code="bad_request",
            detail="Esta semana ja foi submetida ou aprovada. Nao e possivel alterar registos.",
        )

    old_log = (
        db.query(models.LessonLog)
        .filter(
            models.LessonLog.operational_block_id == operational_block_id,
        )
        .with_for_update()
        .first()
    )
    old_status = old_log.status if old_log else models.LessonLogStatus.PENDING

    if old_log is None:
        old_log = models.LessonLog(
            organization_id=organization_id,
            operational_block_id=operational_block_id,
            status=payload.status,
            summary=payload.summary,
            notes=payload.notes,
            logged_by_membership_id=membership_id,
            logged_at=datetime.now(UTC),
            version=1,
        )
        db.add(old_log)
    else:
        old_log.version = int(old_log.version or 1) + 1
        old_log.status = payload.status
        old_log.summary = payload.summary
        old_log.notes = payload.notes
        old_log.logged_by_membership_id = membership_id
        old_log.logged_at = datetime.now(UTC)

    if old_status != payload.status:
        log_revision = int(old_log.version or 1)
        op_log_operation_id = str(
            _uuid.uuid5(
                _uuid.NAMESPACE_URL,
                f"op_log:{operational_block_id}:{log_revision}:{old_status.value}->{payload.status.value}",
            )
        )
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
                occurrence_service.ProgressLedgerContext(
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
                    actor_membership_id=membership_id,
                    operation_id=op_log_operation_id,
                    accounting_deltas=accounting_deltas,
                ),
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
                occurrence_service.ProgressLedgerContext(
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
                    actor_membership_id=membership_id,
                    operation_id=op_log_operation_id,
                    accounting_deltas=accounting_deltas,
                ),
            )
            block.execution_status = models.OperationalBlockExecutionStatus.PENDING_LOG

    db.flush()
    db.refresh(old_log)
    return old_log
