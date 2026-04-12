"""Serviço de Ocorrências de Aulas (Sprint 2).

Responsabilidades:
- Confirmar automaticamente aulas como GIVEN (cron diário)
- Registar faltas (GAP) e substituições (SUBSTITUTED) manualmente
- Calcular dívidas de horas (ClassProgress vs. previsto até hoje)
- Encontrar professores disponíveis para substituição num slot
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, and_, func
from sqlalchemy.orm import Session, joinedload

from app import models
from app import schemas

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
OCCURRENCE_NOT_FOUND = "Ocorrência não encontrada"
ERR_INVALID_TRANSITION = "Transição inválida de estado da ocorrência"
ERR_DESTRUCTIVE_OVERWRITE = "Ocorrência já finalizada; alteração destrutiva bloqueada"
ERR_MISSING_SCHEDULE_CONTEXT = "Ocorrência sem contexto de aula planeada"
ERR_SUBJECT_OUTSIDE_ORG = "Disciplina substituta inválida para esta organização"
ERR_MISSING_PLANNED_MODULE = "Não foi possível determinar o módulo planeado"
ERR_MISSING_EXECUTED_MODULE = "Não foi possível determinar o módulo executado"
ERR_NEGATIVE_ACCOUNTING = "Operação gerou contabilização negativa (progresso/dívida)"
ERR_SUBSTITUTE_NOT_ELIGIBLE = "Candidato não elegível para esta turma/disciplinas"
ERR_SUBSTITUTE_SLOT_CONFLICT = "Candidato em conflito de horário no mesmo slot"
ERR_SUBSTITUTE_IMPOSSIBLE_AVAILABILITY = "Candidato indisponível para o slot (IMPOSSIBLE)"
ERR_SUBSTITUTE_ROOM_MISMATCH = "Tipo de sala incompatível com a disciplina substituta"
ERR_SUBSTITUTE_SAME_PLANNED_TEACHER = "Docente previsto não pode ser confirmado como substituto"

ALLOWED_STATE_TRANSITIONS: dict[models.LessonOccurrenceStatus, set[models.LessonOccurrenceStatus]] = {
    models.LessonOccurrenceStatus.GIVEN: {
        models.LessonOccurrenceStatus.GIVEN,
        models.LessonOccurrenceStatus.GAP,
        models.LessonOccurrenceStatus.SUBSTITUTED,
    },
    models.LessonOccurrenceStatus.GAP: {models.LessonOccurrenceStatus.GAP},
    models.LessonOccurrenceStatus.SUBSTITUTED: {models.LessonOccurrenceStatus.SUBSTITUTED},
}

DEBT_STATUSES = {
    models.LessonOccurrenceStatus.GAP,
    models.LessonOccurrenceStatus.SUBSTITUTED,
}

DEFAULT_REPAIR_WINDOW_DAYS = 14


class OccurrenceServiceError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


# ---------------------------------------------------------------------------
# Funções de leitura
# ---------------------------------------------------------------------------

def get_occurrence_sync(
    db: Session, occurrence_id: int, org_id: int
) -> Optional[models.LessonOccurrence]:
    """Devolve uma ocorrência pelo ID, validando o tenant."""
    return db.execute(
        select(models.LessonOccurrence).where(
            and_(
                models.LessonOccurrence.id == occurrence_id,
                models.LessonOccurrence.org_id == org_id,
            )
        )
    ).scalar_one_or_none()


def _get_occurrence_for_update_sync(
    db: Session,
    occurrence_id: int,
    org_id: int,
) -> Optional[models.LessonOccurrence]:
    return db.execute(
        select(models.LessonOccurrence).where(
            and_(
                models.LessonOccurrence.id == occurrence_id,
                models.LessonOccurrence.org_id == org_id,
            )
        )
        .with_for_update()
    ).scalar_one_or_none()


def _get_occurrence_with_context_sync(
    db: Session,
    occurrence_id: int,
    org_id: int,
) -> Optional[models.LessonOccurrence]:
    return db.execute(
        select(models.LessonOccurrence)
        .options(
            joinedload(models.LessonOccurrence.schedule_output)
            .joinedload(models.ScheduleOutput.lesson)
            .joinedload(models.Lesson.subject),
            joinedload(models.LessonOccurrence.schedule_output)
            .joinedload(models.ScheduleOutput.lesson)
            .joinedload(models.Lesson.class_model),
            joinedload(models.LessonOccurrence.schedule_output)
            .joinedload(models.ScheduleOutput.lesson)
            .joinedload(models.Lesson.teacher),
            joinedload(models.LessonOccurrence.schedule_output).joinedload(
                models.ScheduleOutput.timeslot
            ),
            joinedload(models.LessonOccurrence.schedule_output).joinedload(
                models.ScheduleOutput.room
            ),
        )
        .where(
            and_(
                models.LessonOccurrence.id == occurrence_id,
                models.LessonOccurrence.org_id == org_id,
            )
        )
    ).scalar_one_or_none()


def _resolve_repair_window_days(db: Session, org_id: int) -> int:
    row = db.execute(
        select(models.OrganizationSettings.repair_stability_window_days)
        .where(models.OrganizationSettings.org_id == org_id)
        .order_by(models.OrganizationSettings.academic_year.desc(), models.OrganizationSettings.id.desc())
    ).first()

    if row is None or row[0] is None:
        return DEFAULT_REPAIR_WINDOW_DAYS

    return max(1, int(row[0]))


def _teacher_is_available_for_slot(
    db: Session,
    teacher_id: int,
    timeslot_id: int,
) -> bool:
    availability = db.execute(
        select(models.Availability.score).where(
            and_(
                models.Availability.teacher_id == teacher_id,
                models.Availability.timeslot_id == timeslot_id,
            )
        )
    ).scalar_one_or_none()

    if availability is None:
        return False

    return availability >= 0


def _teacher_is_busy_in_slot(
    db: Session,
    org_id: int,
    teacher_id: int,
    timeslot_id: int,
    target_date: date,
    exclude_schedule_output_id: Optional[int] = None,
) -> bool:
    stmt = (
        select(models.ScheduleOutput.id)
        .join(models.Lesson, models.ScheduleOutput.lesson_id == models.Lesson.id)
        .where(
            and_(
                models.ScheduleOutput.organization_id == org_id,
                models.ScheduleOutput.is_draft.is_(False),
                models.ScheduleOutput.timeslot_id == timeslot_id,
                models.ScheduleOutput.date == target_date,
                models.Lesson.teacher_id == teacher_id,
            )
        )
    )

    if exclude_schedule_output_id is not None:
        stmt = stmt.where(models.ScheduleOutput.id != exclude_schedule_output_id)

    return db.execute(stmt).first() is not None


def _is_subject_room_compatible(
    schedule_output: models.ScheduleOutput,
    subject: models.Subject,
) -> bool:
    if schedule_output.room is None:
        return True
    return schedule_output.room.type == subject.required_room_type


def _validate_substitute_for_occurrence(
    db: Session,
    org_id: int,
    occurrence: models.LessonOccurrence,
    substitute_teacher_id: int,
    substitute_subject_id: int,
) -> None:
    schedule_output = occurrence.schedule_output
    if schedule_output is None or schedule_output.lesson is None or schedule_output.timeslot is None:
        raise OccurrenceServiceError(status_code=422, detail=ERR_MISSING_SCHEDULE_CONTEXT)

    lesson = schedule_output.lesson
    class_id = lesson.class_id
    planned_subject_id = lesson.subject_id

    if substitute_teacher_id == lesson.teacher_id:
        raise OccurrenceServiceError(status_code=409, detail=ERR_SUBSTITUTE_SAME_PLANNED_TEACHER)

    if substitute_subject_id == planned_subject_id:
        raise OccurrenceServiceError(status_code=409, detail=ERR_SUBSTITUTE_NOT_ELIGIBLE)

    link = db.execute(
        select(models.ClassSubjectLink)
        .join(models.Class, models.ClassSubjectLink.class_id == models.Class.id)
        .where(
            and_(
                models.Class.id == class_id,
                models.Class.organization_id == org_id,
                models.Class.is_archived.is_(False),
                models.ClassSubjectLink.teacher_id == substitute_teacher_id,
                models.ClassSubjectLink.subject_id == substitute_subject_id,
                models.ClassSubjectLink.grade_level == models.Class.grade_level,
            )
        )
    ).scalar_one_or_none()
    if link is None:
        raise OccurrenceServiceError(status_code=409, detail=ERR_SUBSTITUTE_NOT_ELIGIBLE)

    subject = _resolve_subject_for_org(db, org_id, substitute_subject_id)
    if not _is_subject_room_compatible(schedule_output, subject):
        raise OccurrenceServiceError(status_code=409, detail=ERR_SUBSTITUTE_ROOM_MISMATCH)

    if not _teacher_is_available_for_slot(db, substitute_teacher_id, schedule_output.timeslot_id):
        raise OccurrenceServiceError(status_code=409, detail=ERR_SUBSTITUTE_IMPOSSIBLE_AVAILABILITY)

    if _teacher_is_busy_in_slot(
        db,
        org_id=org_id,
        teacher_id=substitute_teacher_id,
        timeslot_id=schedule_output.timeslot_id,
        target_date=occurrence.date,
        exclude_schedule_output_id=schedule_output.id,
    ):
        raise OccurrenceServiceError(status_code=409, detail=ERR_SUBSTITUTE_SLOT_CONFLICT)


def _compute_daily_load_hours(
    db: Session,
    org_id: int,
    teacher_ids: set[int],
    target_date: date,
) -> dict[int, float]:
    if not teacher_ids:
        return {}

    rows = db.execute(
        select(models.Lesson.teacher_id, models.Timeslot.start_time, models.Timeslot.end_time)
        .join(models.ScheduleOutput, models.ScheduleOutput.lesson_id == models.Lesson.id)
        .join(models.Timeslot, models.ScheduleOutput.timeslot_id == models.Timeslot.id)
        .where(
            and_(
                models.ScheduleOutput.organization_id == org_id,
                models.ScheduleOutput.is_draft.is_(False),
                models.ScheduleOutput.date == target_date,
                models.Lesson.teacher_id.in_(teacher_ids),
            )
        )
    ).all()

    hours_by_teacher: dict[int, float] = defaultdict(float)
    for teacher_id, start_time, end_time in rows:
        start_dt = datetime.combine(target_date, start_time)
        end_dt = datetime.combine(target_date, end_time)
        hours_by_teacher[int(teacher_id)] += max(0.0, (end_dt - start_dt).total_seconds() / 3600.0)
    return dict(hours_by_teacher)


def _compute_substitution_counts_in_period(
    db: Session,
    org_id: int,
    class_id: int,
    teacher_ids: set[int],
    date_from: date,
    date_to: date,
) -> dict[int, int]:
    if not teacher_ids:
        return {}

    rows = db.execute(
        select(
            models.LessonOccurrence.substitute_teacher_id,
            func.count(models.LessonOccurrence.id),
        )
        .join(models.ScheduleOutput, models.LessonOccurrence.schedule_output_id == models.ScheduleOutput.id)
        .join(models.Lesson, models.ScheduleOutput.lesson_id == models.Lesson.id)
        .where(
            and_(
                models.LessonOccurrence.org_id == org_id,
                models.LessonOccurrence.status == models.LessonOccurrenceStatus.SUBSTITUTED,
                models.LessonOccurrence.substitute_teacher_id.in_(teacher_ids),
                models.LessonOccurrence.date >= date_from,
                models.LessonOccurrence.date <= date_to,
                models.Lesson.class_id == class_id,
            )
        )
        .group_by(models.LessonOccurrence.substitute_teacher_id)
    ).all()

    return {int(teacher_id): int(count) for teacher_id, count in rows if teacher_id is not None}


def _compute_last_substitution_dates(
    db: Session,
    org_id: int,
    class_id: int,
    teacher_ids: set[int],
    date_to: date,
) -> dict[int, date]:
    if not teacher_ids:
        return {}

    rows = db.execute(
        select(
            models.LessonOccurrence.substitute_teacher_id,
            func.max(models.LessonOccurrence.date),
        )
        .join(models.ScheduleOutput, models.LessonOccurrence.schedule_output_id == models.ScheduleOutput.id)
        .join(models.Lesson, models.ScheduleOutput.lesson_id == models.Lesson.id)
        .where(
            and_(
                models.LessonOccurrence.org_id == org_id,
                models.LessonOccurrence.status == models.LessonOccurrenceStatus.SUBSTITUTED,
                models.LessonOccurrence.substitute_teacher_id.in_(teacher_ids),
                models.LessonOccurrence.date <= date_to,
                models.Lesson.class_id == class_id,
            )
        )
        .group_by(models.LessonOccurrence.substitute_teacher_id)
    ).all()

    return {
        int(teacher_id): last_date
        for teacher_id, last_date in rows
        if teacher_id is not None and last_date is not None
    }


def _duration_hours(target_date: date, timeslot: Optional[models.Timeslot]) -> float:
    if timeslot is None:
        return 0.0
    start_dt = datetime.combine(target_date, timeslot.start_time)
    end_dt = datetime.combine(target_date, timeslot.end_time)
    return max(0.0, (end_dt - start_dt).total_seconds() / 3600.0)


def _resolve_occurrence_planned_hours(occurrence: models.LessonOccurrence) -> float:
    if occurrence.planned_hours > 0:
        return float(occurrence.planned_hours)

    if occurrence.schedule_output is not None:
        return _duration_hours(occurrence.date, occurrence.schedule_output.timeslot)

    return max(0.0, float(occurrence.hours_given))


def _resolve_subject_for_org(
    db: Session,
    org_id: int,
    subject_id: int,
) -> models.Subject:
    subject = db.execute(
        select(models.Subject)
        .options(joinedload(models.Subject.modules))
        .where(
            and_(
                models.Subject.id == subject_id,
                models.Subject.organization_id == org_id,
            )
        )
    ).unique().scalar_one_or_none()
    if subject is None:
        raise OccurrenceServiceError(status_code=422, detail=ERR_SUBJECT_OUTSIDE_ORG)
    return subject


def _resolve_active_module_id_for_subject(
    db: Session,
    class_id: int,
    subject: models.Subject,
) -> Optional[int]:
    ordered_modules = sorted(subject.modules, key=lambda m: m.order)
    if not ordered_modules:
        return None

    for module in ordered_modules:
        progress = db.execute(
            select(models.ClassProgress).where(
                and_(
                    models.ClassProgress.class_id == class_id,
                    models.ClassProgress.module_id == module.id,
                )
            )
        ).scalar_one_or_none()
        hours_done = float(progress.hours_completed if progress is not None else 0.0)
        if hours_done < float(module.hours_total):
            return module.id

    return ordered_modules[-1].id


def _resolve_active_module_id_by_subject_id(
    db: Session,
    org_id: int,
    class_id: int,
    subject_id: int,
) -> Optional[int]:
    subject = _resolve_subject_for_org(db, org_id, subject_id)
    return _resolve_active_module_id_for_subject(db, class_id, subject)


def _get_or_create_progress(
    db: Session,
    class_id: int,
    module_id: int,
) -> models.ClassProgress:
    progress = db.execute(
        select(models.ClassProgress).where(
            and_(
                models.ClassProgress.class_id == class_id,
                models.ClassProgress.module_id == module_id,
            )
        )
    ).scalar_one_or_none()

    if progress is not None:
        return progress

    progress = models.ClassProgress(
        class_id=class_id,
        module_id=module_id,
        hours_completed=0.0,
        hours_debt=0.0,
        is_completed=False,
    )
    db.add(progress)
    db.flush()
    return progress


def _apply_module_delta(
    db: Session,
    class_id: int,
    module_id: Optional[int],
    completed_delta: float,
    debt_delta: float,
) -> None:
    if module_id is None:
        return

    module = db.get(models.Module, module_id)
    if module is None:
        raise OccurrenceServiceError(status_code=422, detail=ERR_MISSING_EXECUTED_MODULE)

    progress = _get_or_create_progress(db, class_id, module_id)

    new_completed = float(progress.hours_completed) + completed_delta
    new_debt = float(progress.hours_debt) + debt_delta
    if new_completed < 0 or new_debt < 0:
        raise OccurrenceServiceError(status_code=409, detail=ERR_NEGATIVE_ACCOUNTING)

    progress.hours_completed = round(new_completed, 4)
    progress.hours_debt = round(new_debt, 4)
    progress.is_completed = progress.hours_completed >= float(module.hours_total)


def _apply_state_accounting(
    db: Session,
    class_id: int,
    status: models.LessonOccurrenceStatus,
    planned_module_id: Optional[int],
    executed_module_id: Optional[int],
    planned_hours: float,
    direction: int,
) -> None:
    if direction not in (-1, 1):
        raise ValueError("direction must be -1 or 1")

    delta = planned_hours * direction

    if status == models.LessonOccurrenceStatus.GIVEN:
        _apply_module_delta(
            db,
            class_id=class_id,
            module_id=planned_module_id,
            completed_delta=delta,
            debt_delta=0.0,
        )
        return

    if status == models.LessonOccurrenceStatus.GAP:
        _apply_module_delta(
            db,
            class_id=class_id,
            module_id=planned_module_id,
            completed_delta=0.0,
            debt_delta=delta,
        )
        return

    if status == models.LessonOccurrenceStatus.SUBSTITUTED:
        if executed_module_id is None:
            raise OccurrenceServiceError(status_code=422, detail=ERR_MISSING_EXECUTED_MODULE)

        _apply_module_delta(
            db,
            class_id=class_id,
            module_id=planned_module_id,
            completed_delta=0.0,
            debt_delta=delta,
        )
        _apply_module_delta(
            db,
            class_id=class_id,
            module_id=executed_module_id,
            completed_delta=delta,
            debt_delta=0.0,
        )
        return


def _is_idempotent_payload(
    occurrence: models.LessonOccurrence,
    payload: schemas.LessonOccurrenceUpdate,
) -> bool:
    return (
        occurrence.status == payload.status
        and occurrence.substitute_teacher_id == payload.substitute_teacher_id
        and occurrence.substitute_subject_id == payload.substitute_subject_id
    )


def _validate_state_transition(
    occurrence: models.LessonOccurrence,
    payload: schemas.LessonOccurrenceUpdate,
) -> None:
    current_status = occurrence.status
    allowed = ALLOWED_STATE_TRANSITIONS.get(current_status, set())

    if payload.status not in allowed:
        raise OccurrenceServiceError(
            status_code=409,
            detail=(
                f"{ERR_INVALID_TRANSITION}: {current_status.value} -> {payload.status.value}"
            ),
        )

    if current_status == payload.status and not _is_idempotent_payload(occurrence, payload):
        raise OccurrenceServiceError(status_code=409, detail=ERR_DESTRUCTIVE_OVERWRITE)


def list_occurrences_sync(
    db: Session,
    org_id: int,
    class_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> list[models.LessonOccurrence]:
    """Lista ocorrências com filtros opcionais."""
    stmt = (
        select(models.LessonOccurrence)
        .options(
            joinedload(models.LessonOccurrence.schedule_output).joinedload(
                models.ScheduleOutput.lesson
            )
        )
        .where(models.LessonOccurrence.org_id == org_id)
    )
    if class_id is not None:
        stmt = stmt.join(
            models.ScheduleOutput,
            models.LessonOccurrence.schedule_output_id == models.ScheduleOutput.id,
        ).join(
            models.Lesson,
            models.ScheduleOutput.lesson_id == models.Lesson.id,
        ).where(models.Lesson.class_id == class_id)
    if date_from is not None:
        stmt = stmt.where(models.LessonOccurrence.date >= date_from)
    if date_to is not None:
        stmt = stmt.where(models.LessonOccurrence.date <= date_to)
    stmt = stmt.order_by(models.LessonOccurrence.date.desc())
    return list(db.execute(stmt).scalars().unique())


# ---------------------------------------------------------------------------
# Actualização pelo diretor
# ---------------------------------------------------------------------------

def update_occurrence_sync(
    db: Session,
    occurrence_id: int,
    org_id: int,
    payload: schemas.LessonOccurrenceUpdate,
    decided_by_user_id: Optional[int] = None,
) -> models.LessonOccurrence:
    """Aplica decisão operacional com máquina de estados e contabilização transacional."""
    occurrence = _get_occurrence_for_update_sync(db, occurrence_id, org_id)
    if occurrence is None:
        raise OccurrenceServiceError(status_code=404, detail=OCCURRENCE_NOT_FOUND)

    if _is_idempotent_payload(occurrence, payload):
        return occurrence

    _validate_state_transition(occurrence, payload)

    if occurrence.schedule_output is None or occurrence.schedule_output.lesson is None:
        raise OccurrenceServiceError(status_code=422, detail=ERR_MISSING_SCHEDULE_CONTEXT)

    lesson = occurrence.schedule_output.lesson
    class_id = lesson.class_id
    if lesson.subject is None:
        raise OccurrenceServiceError(status_code=422, detail=ERR_MISSING_PLANNED_MODULE)

    planned_hours = _resolve_occurrence_planned_hours(occurrence)

    planned_module_id = occurrence.planned_module_id
    if planned_module_id is None:
        planned_module_id = _resolve_active_module_id_for_subject(
            db,
            class_id=class_id,
            subject=lesson.subject,
        )
    if planned_module_id is None:
        raise OccurrenceServiceError(status_code=422, detail=ERR_MISSING_PLANNED_MODULE)

    if payload.status == models.LessonOccurrenceStatus.SUBSTITUTED:
        _validate_substitute_for_occurrence(
            db,
            org_id=org_id,
            occurrence=occurrence,
            substitute_teacher_id=payload.substitute_teacher_id,
            substitute_subject_id=payload.substitute_subject_id,
        )

        executed_module_id = _resolve_active_module_id_by_subject_id(
            db,
            org_id=org_id,
            class_id=class_id,
            subject_id=payload.substitute_subject_id,
        )
        if executed_module_id is None:
            raise OccurrenceServiceError(status_code=422, detail=ERR_MISSING_EXECUTED_MODULE)
        executed_teacher_id = payload.substitute_teacher_id
        hours_given = planned_hours
    elif payload.status == models.LessonOccurrenceStatus.GAP:
        executed_module_id = None
        executed_teacher_id = None
        hours_given = 0.0
    else:
        executed_module_id = planned_module_id
        executed_teacher_id = lesson.teacher_id
        hours_given = planned_hours

    try:
        _apply_state_accounting(
            db,
            class_id=class_id,
            status=occurrence.status,
            planned_module_id=planned_module_id,
            executed_module_id=occurrence.executed_module_id,
            planned_hours=planned_hours,
            direction=-1,
        )

        _apply_state_accounting(
            db,
            class_id=class_id,
            status=payload.status,
            planned_module_id=planned_module_id,
            executed_module_id=executed_module_id,
            planned_hours=planned_hours,
            direction=1,
        )

        occurrence.status = payload.status
        occurrence.planned_hours = planned_hours
        occurrence.planned_teacher_id = lesson.teacher_id
        occurrence.executed_teacher_id = executed_teacher_id
        occurrence.planned_module_id = planned_module_id
        occurrence.executed_module_id = executed_module_id
        occurrence.substitute_teacher_id = payload.substitute_teacher_id
        occurrence.substitute_subject_id = payload.substitute_subject_id
        occurrence.hours_given = hours_given
        occurrence.decided_by_user_id = decided_by_user_id
        occurrence.decided_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(occurrence)
    except Exception:
        db.rollback()
        raise

    return occurrence


# ---------------------------------------------------------------------------
# Confirmação automática diária (chamada pelo cron Celery Beat)
# ---------------------------------------------------------------------------

def auto_confirm_daily_sync(db: Session, org_id: int, target_date: date) -> int:
    """Cria registos GIVEN para todos os ScheduleOutputs do dia sem ocorrência.

    Retorna o número de registos criados.
    Returns 0 se não houver slots planeados para essa data.
    """
    # 1. Buscar todos os ScheduleOutputs planeados para target_date
    scheduled_slots = list(
        db.execute(
            select(models.ScheduleOutput)
            .options(
                joinedload(models.ScheduleOutput.timeslot),
                joinedload(models.ScheduleOutput.lesson)
                .joinedload(models.Lesson.subject)
                .joinedload(models.Subject.modules),
                joinedload(models.ScheduleOutput.lesson).joinedload(models.Lesson.teacher),
            )
            .where(
                and_(
                    models.ScheduleOutput.organization_id == org_id,
                    models.ScheduleOutput.date == target_date,
                    models.ScheduleOutput.is_draft.is_(False),
                )
            )
        )
        .scalars()
        .unique()
    )

    created_count = 0
    for slot in scheduled_slots:
        # 2. Verificar se já existe uma ocorrência manual para este slot
        existing = db.execute(
            select(models.LessonOccurrence).where(
                and_(
                    models.LessonOccurrence.schedule_output_id == slot.id,
                    models.LessonOccurrence.date == target_date,
                )
            )
        ).scalar_one_or_none()

        if existing is not None:
            continue  # Diretor já registou manualmente — respeitar

        # 3. Calcular horas do timeslot
        planned_hours = _duration_hours(target_date, slot.timeslot)

        planned_teacher_id = slot.lesson.teacher_id if slot.lesson is not None else None

        planned_module_id = None
        if slot.lesson is not None and slot.lesson.subject is not None:
            planned_module_id = _resolve_active_module_id_for_subject(
                db,
                class_id=slot.lesson.class_id,
                subject=slot.lesson.subject,
            )

        # 4. Criar ocorrência GIVEN
        occurrence = models.LessonOccurrence(
            org_id=org_id,
            schedule_output_id=slot.id,
            date=target_date,
            status=models.LessonOccurrenceStatus.GIVEN,
            planned_hours=planned_hours,
            planned_teacher_id=planned_teacher_id,
            executed_teacher_id=planned_teacher_id,
            planned_module_id=planned_module_id,
            executed_module_id=planned_module_id,
            hours_given=planned_hours,
            decided_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
        )
        db.add(occurrence)

        # 5. Incrementar ClassProgress de forma consistente com a regra oficial
        if slot.lesson is not None:
            _apply_state_accounting(
                db,
                class_id=slot.lesson.class_id,
                status=models.LessonOccurrenceStatus.GIVEN,
                planned_module_id=planned_module_id,
                executed_module_id=planned_module_id,
                planned_hours=planned_hours,
                direction=1,
            )

        created_count += 1

    db.commit()
    return created_count


# ---------------------------------------------------------------------------
# Dívidas de horas
# ---------------------------------------------------------------------------

def get_debts_sync(
    db: Session, org_id: int, class_id: Optional[int] = None
) -> schemas.DebtListRead:
    """Calcula dívidas: GAP e SUBSTITUTED em slots passados por turma/disciplina."""
    # Buscar ocorrências com dívida (GAP/SUBSTITUTED) com data ≤ hoje
    today = date.today()
    stmt = (
        select(models.LessonOccurrence)
        .options(
            joinedload(models.LessonOccurrence.schedule_output)
            .joinedload(models.ScheduleOutput.lesson)
            .joinedload(models.Lesson.class_model),
            joinedload(models.LessonOccurrence.schedule_output)
            .joinedload(models.ScheduleOutput.lesson)
            .joinedload(models.Lesson.subject),
            joinedload(models.LessonOccurrence.schedule_output)
            .joinedload(models.ScheduleOutput.lesson)
            .joinedload(models.Lesson.teacher),
            joinedload(models.LessonOccurrence.schedule_output).joinedload(
                models.ScheduleOutput.timeslot
            ),
        )
        .where(
            and_(
                models.LessonOccurrence.org_id == org_id,
                models.LessonOccurrence.status.in_(DEBT_STATUSES),
                models.LessonOccurrence.date <= today,
            )
        )
    )
    if class_id is not None:
        stmt = (
            stmt
            .join(
                models.ScheduleOutput,
                models.LessonOccurrence.schedule_output_id == models.ScheduleOutput.id,
            )
            .join(models.Lesson, models.ScheduleOutput.lesson_id == models.Lesson.id)
            .where(models.Lesson.class_id == class_id)
        )

    occurrences = list(db.execute(stmt).scalars().unique())

    # Agregar por (class_id, subject_id)
    key_counts: dict[tuple[int, int], int] = defaultdict(int)
    key_hours: dict[tuple[int, int], float] = defaultdict(float)
    key_meta: dict[tuple[int, int], dict] = {}

    for occ in occurrences:
        so = occ.schedule_output
        if so is None or so.lesson is None:
            continue
        lesson = so.lesson
        debt_hours = (
            float(occ.planned_hours)
            if occ.planned_hours > 0
            else _duration_hours(occ.date, so.timeslot)
        )
        if debt_hours <= 0:
            debt_hours = max(0.0, float(occ.hours_given))

        key = (lesson.class_id, lesson.subject_id)
        key_counts[key] += 1
        key_hours[key] += debt_hours
        if key not in key_meta:
            key_meta[key] = {
                "class_name": lesson.class_model.name if lesson.class_model else "—",
                "subject_name": lesson.subject.name if lesson.subject else "—",
                "teacher_id": lesson.teacher_id,
                "teacher_name": lesson.teacher.name if lesson.teacher else None,
            }

    items = [
        schemas.DebtItem(
            class_id=k[0],
            class_name=key_meta[k]["class_name"],
            subject_id=k[1],
            subject_name=key_meta[k]["subject_name"],
            teacher_id=key_meta[k]["teacher_id"],
            teacher_name=key_meta[k]["teacher_name"],
            gap_occurrences=key_counts[k],
            hours_owed=round(key_hours[k], 2),
        )
        for k in sorted(key_counts.keys())
    ]

    return schemas.DebtListRead(
        total_gaps=sum(key_counts.values()),
        total_hours_owed=round(sum(key_hours.values()), 2),
        items=items,
    )


# ---------------------------------------------------------------------------
# Encontrar substitutos disponíveis
# ---------------------------------------------------------------------------

def get_substitute_recommendations_sync(
    db: Session,
    org_id: int,
    occurrence_id: int,
) -> list[schemas.SubstituteRecommendationRead]:
    occurrence = _get_occurrence_with_context_sync(db, occurrence_id, org_id)
    if occurrence is None:
        raise OccurrenceServiceError(status_code=404, detail=OCCURRENCE_NOT_FOUND)

    schedule_output = occurrence.schedule_output
    if schedule_output is None or schedule_output.lesson is None or schedule_output.timeslot is None:
        raise OccurrenceServiceError(status_code=422, detail=ERR_MISSING_SCHEDULE_CONTEXT)

    lesson = schedule_output.lesson
    if lesson.class_model is None:
        raise OccurrenceServiceError(status_code=422, detail=ERR_MISSING_SCHEDULE_CONTEXT)

    class_id = lesson.class_id
    planned_subject_id = lesson.subject_id
    planned_teacher_id = lesson.teacher_id
    timeslot_id = schedule_output.timeslot_id
    target_date = occurrence.date

    candidates = list(
        db.execute(
            select(models.ClassSubjectLink)
            .options(
                joinedload(models.ClassSubjectLink.teacher),
                joinedload(models.ClassSubjectLink.subject),
                joinedload(models.ClassSubjectLink.class_),
            )
            .join(models.Class, models.ClassSubjectLink.class_id == models.Class.id)
            .where(
                and_(
                    models.Class.id == class_id,
                    models.Class.organization_id == org_id,
                    models.Class.is_archived.is_(False),
                    models.ClassSubjectLink.grade_level == models.Class.grade_level,
                    models.ClassSubjectLink.subject_id != planned_subject_id,
                    models.ClassSubjectLink.teacher_id.is_not(None),
                )
            )
        )
        .scalars()
        .unique()
    )

    eligible_candidates: list[dict] = []
    for link in candidates:
        if link.teacher is None or link.subject is None or link.class_ is None:
            continue

        teacher_id = link.teacher_id
        if teacher_id is None:
            continue

        if teacher_id == planned_teacher_id:
            continue

        if not _is_subject_room_compatible(schedule_output, link.subject):
            continue

        if not _teacher_is_available_for_slot(db, teacher_id, timeslot_id):
            continue

        if _teacher_is_busy_in_slot(
            db,
            org_id=org_id,
            teacher_id=teacher_id,
            timeslot_id=timeslot_id,
            target_date=target_date,
            exclude_schedule_output_id=schedule_output.id,
        ):
            continue

        eligible_candidates.append(
            {
                "teacher_id": teacher_id,
                "teacher_name": link.teacher.name,
                "subject_id": link.subject_id,
                "subject_name": link.subject.name,
                "class_id": link.class_id,
                "class_name": link.class_.name,
            }
        )

    if not eligible_candidates:
        return []

    teacher_ids = {int(c["teacher_id"]) for c in eligible_candidates}
    repair_window_days = _resolve_repair_window_days(db, org_id)
    period_start = target_date - timedelta(days=repair_window_days)

    substitutions_in_period = _compute_substitution_counts_in_period(
        db,
        org_id=org_id,
        class_id=class_id,
        teacher_ids=teacher_ids,
        date_from=period_start,
        date_to=target_date,
    )
    daily_load_hours = _compute_daily_load_hours(
        db,
        org_id=org_id,
        teacher_ids=teacher_ids,
        target_date=target_date,
    )
    last_substitution_dates = _compute_last_substitution_dates(
        db,
        org_id=org_id,
        class_id=class_id,
        teacher_ids=teacher_ids,
        date_to=target_date,
    )

    enriched: list[dict] = []
    for candidate in eligible_candidates:
        teacher_id = int(candidate["teacher_id"])
        subs_count = int(substitutions_in_period.get(teacher_id, 0))
        day_hours = round(float(daily_load_hours.get(teacher_id, 0.0)), 2)
        last_date = last_substitution_dates.get(teacher_id)
        days_since_last = None if last_date is None else (target_date - last_date).days
        days_sort = days_since_last if days_since_last is not None else 10_000

        justification = (
            f"substituicoes_periodo={subs_count}; "
            f"carga_dia_h={day_hours}; "
            f"dias_desde_ultima={days_since_last if days_since_last is not None else 'sem_historico'}; "
            f"desempate_teacher_id={teacher_id}"
        )

        enriched.append(
            {
                **candidate,
                "substitutions_in_period": subs_count,
                "daily_load_hours": day_hours,
                "days_since_last_substitution": days_since_last,
                "_days_sort": days_sort,
                "justification": justification,
            }
        )

    ranked = sorted(
        enriched,
        key=lambda item: (
            item["substitutions_in_period"],
            item["daily_load_hours"],
            -item["_days_sort"],
            item["teacher_id"],
        ),
    )

    return [
        schemas.SubstituteRecommendationRead(
            rank=index,
            teacher_id=item["teacher_id"],
            teacher_name=item["teacher_name"],
            subject_id=item["subject_id"],
            subject_name=item["subject_name"],
            class_id=item["class_id"],
            class_name=item["class_name"],
            substitutions_in_period=item["substitutions_in_period"],
            daily_load_hours=item["daily_load_hours"],
            days_since_last_substitution=item["days_since_last_substitution"],
            justification=item["justification"],
        )
        for index, item in enumerate(ranked, start=1)
    ]


def get_available_substitutes_sync(
    db: Session, org_id: int, timeslot_id: int, target_date: date
) -> list[schemas.AvailableSubstituteRead]:
    """Devolve professores assignados à organização que:
    1. Têm disponibilidade (score ≥ 0) no timeslot indicado.
    2. Não têm já uma aula agendada (ScheduleOutput) para essa data.

    Retorna uma lista de candidatos com a disciplina que leccionam.
    """
    # 1. Timeslot info (para saber o dia da semana)
    ts = db.execute(
        select(models.Timeslot).where(
            and_(
                models.Timeslot.id == timeslot_id,
                models.Timeslot.organization_id == org_id,
            )
        )
    ).scalar_one_or_none()

    if ts is None:
        return []

    day_of_week = ts.day_of_week

    # 2. Professores com availability score ≥ 0 (não impossível) para este timeslot
    available_teacher_ids = {
        row.teacher_id
        for row in db.execute(
            select(models.Availability.teacher_id).where(
                and_(
                    models.Availability.timeslot_id == timeslot_id,
                    models.Availability.score >= 0,
                )
            )
        ).all()
    }

    if not available_teacher_ids:
        return []

    # 3. Professores já ocupados nesta data/timeslot (têm ScheduleOutput)
    busy_teacher_ids = {
        row.teacher_id
        for row in db.execute(
            select(models.Lesson.teacher_id)
            .join(models.ScheduleOutput, models.ScheduleOutput.lesson_id == models.Lesson.id)
            .where(
                and_(
                    models.ScheduleOutput.organization_id == org_id,
                    models.ScheduleOutput.timeslot_id == timeslot_id,
                    models.ScheduleOutput.date == target_date,
                    models.ScheduleOutput.is_draft.is_(False),
                )
            )
        ).all()
    }

    free_teacher_ids = available_teacher_ids - busy_teacher_ids

    if not free_teacher_ids:
        return []

    # 4. Buscar ClassSubjectLinks para os professores livres (para saber que disciplina dão)
    links = list(
        db.execute(
            select(models.ClassSubjectLink)
            .options(
                joinedload(models.ClassSubjectLink.teacher),
                joinedload(models.ClassSubjectLink.subject),
                joinedload(models.ClassSubjectLink.class_),
            )
            .where(
                and_(
                    models.ClassSubjectLink.teacher_id.in_(free_teacher_ids),
                )
            )
            .join(
                models.Class,
                models.ClassSubjectLink.class_id == models.Class.id,
            )
            .where(
                and_(
                    models.Class.organization_id == org_id,
                    models.Class.is_archived.is_(False),
                )
            )
        )
        .scalars()
        .unique()
    )

    results = [
        schemas.AvailableSubstituteRead(
            teacher_id=link.teacher_id,
            teacher_name=link.teacher.name if link.teacher else "—",
            subject_id=link.subject_id,
            subject_name=link.subject.name if link.subject else "—",
            class_id=link.class_id,
            class_name=link.class_.name if link.class_ else "—",
        )
        for link in links
        if link.teacher_id is not None
    ]

    return results
