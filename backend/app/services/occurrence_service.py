"""Serviço de Ocorrências de Aulas (Sprint 2).

Responsabilidades:
- Confirmar automaticamente aulas como GIVEN (cron diário)
- Registar faltas (GAP) e substituições (SUBSTITUTED) manualmente
- Calcular dívidas de horas (ClassProgress vs. previsto até hoje)
- Encontrar professores disponíveis para substituição num slot
"""
from __future__ import annotations

import uuid as _uuid
from collections import defaultdict
from datetime import date, datetime, timezone, timedelta
from types import SimpleNamespace
from typing import Optional

import structlog
from sqlalchemy import select, and_, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app import models
from app import schemas
from app.core.task_keys import DEFAULT_REPAIR_WINDOW_DAYS

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
OCCURRENCE_NOT_FOUND = "OCCURRENCE_NOT_FOUND"
ERR_INVALID_TRANSITION = "OCCURRENCE_INVALID_TRANSITION"
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
ERR_SUBSTITUTE_SAME_SUBJECT = "Disciplina substituta não pode ser igual à disciplina planeada"
ERR_SCHEDULE_OUTPUT_NOT_FOUND = "Bloco planeado não encontrado"
ERR_SCHEDULE_OUTPUT_IS_DRAFT = "Bloco de rascunho não pode iniciar ocorrência operacional"
ERR_SCHEDULE_OUTPUT_NO_DATE = "Bloco sem data válida para criação de ocorrência"

ERR_STALE_VERSION = "OCCURRENCE_STALE_VERSION"
ERR_INACTIVE = "OCCURRENCE_INACTIVE"
ERR_SUBSTITUTE_LOG_LOCKED = "SUBSTITUTE_LOG_LOCKED"

ALLOWED_STATE_TRANSITIONS: dict[models.LessonOccurrenceStatus, set[models.LessonOccurrenceStatus]] = {
    # Undecided (decided_at IS NULL): any transition allowed (handled by early return)
    # Decided states below — only re-decision to allowed targets
    models.LessonOccurrenceStatus.GIVEN: {
        models.LessonOccurrenceStatus.GIVEN,        # idempotent retry only
    },
    models.LessonOccurrenceStatus.GAP: {
        models.LessonOccurrenceStatus.GAP,           # idempotent retry
        models.LessonOccurrenceStatus.SUBSTITUTED,   # re-decision
    },
    models.LessonOccurrenceStatus.SUBSTITUTED: {
        models.LessonOccurrenceStatus.SUBSTITUTED,   # idempotent retry
        models.LessonOccurrenceStatus.GAP,           # re-decision
    },
    models.LessonOccurrenceStatus.REVOKED: set(),   # terminal — imutável
}

DEBT_STATUSES = {
    models.LessonOccurrenceStatus.GAP,
    models.LessonOccurrenceStatus.SUBSTITUTED,
}

OP_STATE_OPEN = "OPEN_PENDING"
OP_STATE_REVOKED = "REVOKED"
OP_STATE_BY_STATUS = {
    models.LessonOccurrenceStatus.GIVEN: "DECIDED_GIVEN",
    models.LessonOccurrenceStatus.GAP: "DECIDED_GAP",
    models.LessonOccurrenceStatus.SUBSTITUTED: "DECIDED_SUBSTITUTED",
    models.LessonOccurrenceStatus.REVOKED: OP_STATE_REVOKED,
}

MAX_EVENT_DETAIL_LENGTH = 240

OBS_EVENT_CREATE = "CREATE_OCCURRENCE"
OBS_EVENT_DECIDE = "DECIDE_OCCURRENCE"

OBS_RESULT_SUCCESS = "SUCCESS"
OBS_RESULT_VALIDATION_FAILURE = "VALIDATION_FAILURE"
OBS_RESULT_CONFLICT = "CONFLICT"
OBS_RESULT_ERROR = "ERROR"

logger = structlog.get_logger(__name__)


class OccurrenceServiceError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def classify_occurrence_error_result(status_code: int) -> str:
    if status_code == 409:
        return OBS_RESULT_CONFLICT
    if status_code in (400, 404, 422):
        return OBS_RESULT_VALIDATION_FAILURE
    return OBS_RESULT_ERROR


def get_operational_state(occurrence: models.LessonOccurrence) -> str:
    if occurrence.status == models.LessonOccurrenceStatus.REVOKED or not occurrence.is_active:
        return OP_STATE_REVOKED
    if occurrence.status is None or occurrence.decided_at is None:
        return OP_STATE_OPEN
    return OP_STATE_BY_STATUS.get(occurrence.status, OP_STATE_OPEN)


def _touch_occurrence_version(occurrence: models.LessonOccurrence) -> None:
    occurrence.version = int(occurrence.version or 1) + 1


def _assert_occurrence_version(occurrence: models.LessonOccurrence, version: int) -> None:
    if int(occurrence.version or 1) != int(version):
        raise OccurrenceServiceError(status_code=409, detail=ERR_STALE_VERSION)


def _active_occurrence_filter(organization_id: int, schedule_output_id: int, target_date: date):
    return and_(
        models.LessonOccurrence.organization_id == organization_id,
        models.LessonOccurrence.schedule_output_id == schedule_output_id,
        models.LessonOccurrence.date == target_date,
        models.LessonOccurrence.is_active.is_(True),
    )


def _sanitize_event_detail(detail: Optional[str]) -> Optional[str]:
    if detail is None:
        return None
    text = str(detail).strip()
    if not text:
        return None
    return text[:MAX_EVENT_DETAIL_LENGTH]


def log_occurrence_event_safe_sync(
    db: Session,
    *,
    organization_id: int,
    event_type: str,
    result: str,
    actor_user_id: Optional[int] = None,
    occurrence_id: Optional[int] = None,
    schedule_output_id: Optional[int] = None,
    decision_status: Optional[models.LessonOccurrenceStatus] = None,
    detail: Optional[str] = None,
) -> None:
    """Regista evento operacional sem bloquear o fluxo principal em caso de falha."""
    try:
        event = models.OccurrenceOperationalEvent(
            organization_id=organization_id,
            occurrence_id=occurrence_id,
            schedule_output_id=schedule_output_id,
            actor_user_id=actor_user_id,
            event_type=event_type,
            result=result,
            decision_status=decision_status.value if decision_status is not None else None,
            detail=_sanitize_event_detail(detail),
            created_at=datetime.now(timezone.utc),
        )
        db.add(event)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning(
            "occurrence_observability_emit_failed",
            organization_id=organization_id,
            event_type=event_type,
            result=result,
            error=str(exc),
        )


def get_occurrence_observability_summary_sync(
    db: Session,
    *,
    organization_id: int,
    window_days: int,
) -> dict:
    window_days = max(1, int(window_days))
    start_at = datetime.now(timezone.utc) - timedelta(days=window_days)

    rows = db.execute(
        select(
            models.OccurrenceOperationalEvent.event_type,
            models.OccurrenceOperationalEvent.result,
            func.count(models.OccurrenceOperationalEvent.id),
        ).where(
            and_(
                models.OccurrenceOperationalEvent.organization_id == organization_id,
                models.OccurrenceOperationalEvent.created_at >= start_at,
            )
        ).group_by(
            models.OccurrenceOperationalEvent.event_type,
            models.OccurrenceOperationalEvent.result,
        )
    ).all()

    total_events = 0
    decisions_success = 0
    validation_failures = 0
    conflicts = 0

    for event_type, result, count in rows:
        count_value = int(count)
        total_events += count_value
        if event_type == OBS_EVENT_DECIDE and result == OBS_RESULT_SUCCESS:
            decisions_success += count_value
        if result == OBS_RESULT_VALIDATION_FAILURE:
            validation_failures += count_value
        if result == OBS_RESULT_CONFLICT:
            conflicts += count_value

    return {
        "window_days": window_days,
        "total_events": total_events,
        "decisions_success": decisions_success,
        "validation_failures": validation_failures,
        "conflicts": conflicts,
    }


# ---------------------------------------------------------------------------
# Funções de leitura
# ---------------------------------------------------------------------------

def get_occurrence_sync(
    db: Session, occurrence_id: int, organization_id: int
) -> Optional[models.LessonOccurrence]:
    """Devolve uma ocorrência pelo ID, validando o tenant."""
    occurrence = _get_occurrence_with_context_sync(db, occurrence_id, organization_id)
    if occurrence is None:
        return None
    _attach_occurrence_read_context(occurrence)
    return occurrence


def _get_occurrence_for_update_sync(
    db: Session,
    occurrence_id: int,
    organization_id: int,
) -> Optional[models.LessonOccurrence]:
    return db.execute(
        select(models.LessonOccurrence).where(
            and_(
                models.LessonOccurrence.id == occurrence_id,
                models.LessonOccurrence.organization_id == organization_id,
            )
        )
        .with_for_update()
    ).scalar_one_or_none()


def _get_occurrence_with_context_sync(
    db: Session,
    occurrence_id: int,
    organization_id: int,
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
            joinedload(models.LessonOccurrence.schedule_output).joinedload(
                models.ScheduleOutput.lesson_logs
            ),
            joinedload(models.LessonOccurrence.decided_by_user),
            joinedload(models.LessonOccurrence.planned_teacher),
            joinedload(models.LessonOccurrence.executed_teacher),
            joinedload(models.LessonOccurrence.substitute_teacher),
            joinedload(models.LessonOccurrence.class_),
            joinedload(models.LessonOccurrence.subject),
            joinedload(models.LessonOccurrence.planned_timeslot),
        )
        .where(
            and_(
                models.LessonOccurrence.id == occurrence_id,
                models.LessonOccurrence.organization_id == organization_id,
            )
        )
    ).unique().scalar_one_or_none()


def _attach_occurrence_read_context(occurrence: models.LessonOccurrence) -> None:
    """Anexa campos derivados para o response model sem alterar a fonte de verdade."""
    schedule_output = occurrence.schedule_output
    lesson = schedule_output.lesson if schedule_output is not None else None
    timeslot = schedule_output.timeslot if schedule_output is not None else occurrence.planned_timeslot

    class_model = lesson.class_model if lesson is not None else occurrence.class_
    subject = lesson.subject if lesson is not None else occurrence.subject

    planned_teacher = occurrence.planned_teacher
    if planned_teacher is None and lesson is not None:
        planned_teacher = lesson.teacher

    executed_teacher = occurrence.executed_teacher
    if executed_teacher is None:
        executed_teacher = occurrence.substitute_teacher

    decided_by_user = occurrence.decided_by_user
    if decided_by_user is not None:
        decided_by_name = decided_by_user.name or decided_by_user.email
    else:
        decided_by_name = None

    occurrence.operational_state = get_operational_state(occurrence)
    occurrence.class_id = occurrence.class_id or (lesson.class_id if lesson is not None else None)
    occurrence.class_name = class_model.name if class_model is not None else None
    occurrence.subject_id = occurrence.subject_id or (lesson.subject_id if lesson is not None else None)
    occurrence.subject_name = subject.name if subject is not None else None
    occurrence.timeslot_id = occurrence.planned_timeslot_id or (schedule_output.timeslot_id if schedule_output is not None else None)
    occurrence.timeslot_start_time = timeslot.start_time if timeslot is not None else None
    occurrence.timeslot_end_time = timeslot.end_time if timeslot is not None else None
    occurrence.planned_teacher_name = planned_teacher.name if planned_teacher is not None else None
    occurrence.executed_teacher_name = executed_teacher.name if executed_teacher is not None else None
    occurrence.decided_by_user_name = decided_by_name
    llog = None
    if schedule_output is not None:
        llog = next(iter(schedule_output.lesson_logs), None) if hasattr(schedule_output, "lesson_logs") else None
    occurrence.lesson_log_summary = llog.summary if llog is not None else None
    occurrence.lesson_log_notes = llog.notes if llog is not None else None


def _resolve_repair_window_days(db: Session, organization_id: int) -> int:
    row = db.execute(
        select(models.OrganizationSettings.repair_stability_window_days)
        .where(models.OrganizationSettings.organization_id == organization_id)
        .order_by(models.OrganizationSettings.id.desc())
    ).first()

    if row is None or row[0] is None:
        return DEFAULT_REPAIR_WINDOW_DAYS

    return max(1, int(row[0]))


def _auto_confirm_allowed_now(db: Session, organization_id: int, now: datetime) -> bool:
    settings = db.execute(
        select(models.OrganizationSettings)
        .where(models.OrganizationSettings.organization_id == organization_id)
        .order_by(models.OrganizationSettings.id.desc())
    ).scalars().first()
    if settings is None:
        return True
    if settings.auto_confirm_enabled is False:
        return False
    if settings.auto_confirm_cutoff_time is None:
        return True
    return now.time() >= settings.auto_confirm_cutoff_time


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
    organization_id: int,
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
                models.ScheduleOutput.organization_id == organization_id,
                models.ScheduleOutput.is_draft.is_(False),
                models.ScheduleOutput.timeslot_id == timeslot_id,
                models.ScheduleOutput.date == target_date,
                models.Lesson.teacher_id == teacher_id,
            )
        )
    )

    if exclude_schedule_output_id is not None:
        stmt = stmt.where(models.ScheduleOutput.id != exclude_schedule_output_id)

    has_planned_conflict = db.execute(stmt).first() is not None
    if has_planned_conflict:
        return True

    operational_conflict = db.execute(
        select(models.OperationalScheduleBlock.id).where(
            and_(
                models.OperationalScheduleBlock.organization_id == organization_id,
                models.OperationalScheduleBlock.teacher_id == teacher_id,
                models.OperationalScheduleBlock.date == target_date,
                models.OperationalScheduleBlock.timeslot_id == timeslot_id,
                models.OperationalScheduleBlock.status == models.OperationalBlockStatus.ACTIVE,
            )
        )
    ).first() is not None
    if operational_conflict:
        return True

    # Also block teachers already confirmed as substitutes in the same slot/date.
    substitution_stmt = (
        select(models.LessonOccurrence.id)
        .join(
            models.ScheduleOutput,
            models.LessonOccurrence.schedule_output_id == models.ScheduleOutput.id,
        )
        .where(
            and_(
                models.LessonOccurrence.organization_id == organization_id,
                models.LessonOccurrence.status == models.LessonOccurrenceStatus.SUBSTITUTED,
                models.LessonOccurrence.substitute_teacher_id == teacher_id,
                models.ScheduleOutput.organization_id == organization_id,
                models.ScheduleOutput.is_draft.is_(False),
                models.ScheduleOutput.timeslot_id == timeslot_id,
                models.ScheduleOutput.date == target_date,
            )
        )
    )

    if exclude_schedule_output_id is not None:
        substitution_stmt = substitution_stmt.where(
            models.ScheduleOutput.id != exclude_schedule_output_id
        )

    return db.execute(substitution_stmt).first() is not None


def _is_subject_room_compatible(
    schedule_output: models.ScheduleOutput,
    subject: models.Subject,
) -> bool:
    if schedule_output.room is None:
        return True
    return schedule_output.room.type == subject.required_room_type


def _validate_substitute_for_occurrence(
    db: Session,
    organization_id: int,
    occurrence: models.LessonOccurrence,
    substitute_teacher_id: int,
    substitute_subject_id: int,
) -> None:
    schedule_output = occurrence.schedule_output
    if schedule_output is None or schedule_output.lesson is None or schedule_output.timeslot is None:
        raise OccurrenceServiceError(status_code=422, detail=ERR_MISSING_SCHEDULE_CONTEXT)

    lesson = schedule_output.lesson
    class_id = lesson.class_id

    if substitute_teacher_id == lesson.teacher_id:
        raise OccurrenceServiceError(status_code=409, detail=ERR_SUBSTITUTE_SAME_PLANNED_TEACHER)

    # Regra de domínio: substituição exige disciplina diferente da planeada.
    # O substituto dá a sua própria disciplina na mesma turma.
    if substitute_subject_id == lesson.subject_id:
        raise OccurrenceServiceError(status_code=422, detail=ERR_SUBSTITUTE_SAME_SUBJECT)

    link = db.execute(
        select(models.ClassSubjectLink)
        .join(models.Class, models.ClassSubjectLink.class_id == models.Class.id)
        .where(
            and_(
                models.Class.id == class_id,
                models.Class.organization_id == organization_id,
                models.Class.is_archived.is_(False),
                models.ClassSubjectLink.teacher_id == substitute_teacher_id,
                models.ClassSubjectLink.subject_id == substitute_subject_id,
                models.ClassSubjectLink.grade_level == models.Class.grade_level,
            )
        )
    ).scalar_one_or_none()
    if link is None:
        raise OccurrenceServiceError(status_code=409, detail=ERR_SUBSTITUTE_NOT_ELIGIBLE)

    subject = _resolve_subject_for_org(db, organization_id, substitute_subject_id)
    if not _is_subject_room_compatible(schedule_output, subject):
        raise OccurrenceServiceError(status_code=409, detail=ERR_SUBSTITUTE_ROOM_MISMATCH)

    if not _teacher_is_available_for_slot(db, substitute_teacher_id, schedule_output.timeslot_id):
        raise OccurrenceServiceError(status_code=409, detail=ERR_SUBSTITUTE_IMPOSSIBLE_AVAILABILITY)

    if _teacher_is_busy_in_slot(
        db,
        organization_id=organization_id,
        teacher_id=substitute_teacher_id,
        timeslot_id=schedule_output.timeslot_id,
        target_date=occurrence.date,
        exclude_schedule_output_id=schedule_output.id,
    ):
        raise OccurrenceServiceError(status_code=409, detail=ERR_SUBSTITUTE_SLOT_CONFLICT)


def _compute_daily_load_hours(
    db: Session,
    organization_id: int,
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
                models.ScheduleOutput.organization_id == organization_id,
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

    operational_rows = db.execute(
        select(
            models.OperationalScheduleBlock.teacher_id,
            models.Timeslot.start_time,
            models.Timeslot.end_time,
        )
        .join(models.Timeslot, models.OperationalScheduleBlock.timeslot_id == models.Timeslot.id)
        .where(
            and_(
                models.OperationalScheduleBlock.organization_id == organization_id,
                models.OperationalScheduleBlock.status == models.OperationalBlockStatus.ACTIVE,
                models.OperationalScheduleBlock.date == target_date,
                models.OperationalScheduleBlock.teacher_id.in_(teacher_ids),
            )
        )
    ).all()
    for teacher_id, start_time, end_time in operational_rows:
        start_dt = datetime.combine(target_date, start_time)
        end_dt = datetime.combine(target_date, end_time)
        hours_by_teacher[int(teacher_id)] += max(0.0, (end_dt - start_dt).total_seconds() / 3600.0)
    return dict(hours_by_teacher)


def _compute_substitution_counts_in_period(
    db: Session,
    organization_id: int,
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
                models.LessonOccurrence.organization_id == organization_id,
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
    organization_id: int,
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
                models.LessonOccurrence.organization_id == organization_id,
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
    organization_id: int,
    subject_id: int,
) -> models.Subject:
    subject = db.execute(
        select(models.Subject)
        .options(joinedload(models.Subject.modules))
        .where(
            and_(
                models.Subject.id == subject_id,
                models.Subject.organization_id == organization_id,
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
    organization_id: int,
    class_id: int,
    subject_id: int,
) -> Optional[int]:
    subject = _resolve_subject_for_org(db, organization_id, subject_id)
    return _resolve_active_module_id_for_subject(db, class_id, subject)


def _get_or_create_progress(
    db: Session,
    organization_id: int,
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
        organization_id=organization_id,
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
    organization_id: int,
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

    progress = _get_or_create_progress(db, organization_id, class_id, module_id)

    new_completed = float(progress.hours_completed) + completed_delta
    new_debt = float(progress.hours_debt) + debt_delta

    # Bug #3: Reconcilia dívida pendente quando horas são completadas.
    # Cada hora completada "reembolsa" uma hora de dívida no mesmo módulo.
    if completed_delta > 0 and new_debt > 0:
        debt_reduction = min(new_debt, completed_delta)
        new_debt -= debt_reduction

    if new_completed < 0 or new_debt < 0:
        raise OccurrenceServiceError(status_code=409, detail=ERR_NEGATIVE_ACCOUNTING)

    progress.hours_completed = round(new_completed, 4)
    progress.hours_debt = round(new_debt, 4)
    progress.is_completed = progress.hours_completed >= float(module.hours_total)


def _ensure_operational_schedule_block(
    db: Session,
    *,
    organization_id: int,
    occurrence: models.LessonOccurrence,
    class_id: int,
    substitute_teacher_id: int,
    substitute_subject_id: int,
    executed_module_id: Optional[int],
    source_output: models.ScheduleOutput,
    created_by_user_id: Optional[int],
) -> models.OperationalScheduleBlock:
    existing = db.execute(
        select(models.OperationalScheduleBlock).where(
            and_(
                models.OperationalScheduleBlock.organization_id == organization_id,
                models.OperationalScheduleBlock.source_occurrence_id == occurrence.id,
                models.OperationalScheduleBlock.source_occurrence_revision == occurrence.revision,
                models.OperationalScheduleBlock.status == models.OperationalBlockStatus.ACTIVE,
            )
        )
    ).unique().scalar_one_or_none()
    if existing is not None:
        existing.teacher_id = substitute_teacher_id
        existing.subject_id = substitute_subject_id
        existing.module_id = executed_module_id
        existing.execution_status = models.OperationalBlockExecutionStatus.PENDING_LOG
        return existing

    block = models.OperationalScheduleBlock(
        organization_id=organization_id,
        source_occurrence_id=occurrence.id,
        source_occurrence_revision=occurrence.revision,
        planned_schedule_output_id=source_output.id,
        date=occurrence.date,
        timeslot_id=source_output.timeslot_id,
        room_id=source_output.room_id,
        class_id=class_id,
        teacher_id=substitute_teacher_id,
        subject_id=substitute_subject_id,
        module_id=executed_module_id,
        status=models.OperationalBlockStatus.ACTIVE,
        execution_status=models.OperationalBlockExecutionStatus.PENDING_LOG,
        created_by_user_id=created_by_user_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(block)
    db.flush()
    return block


def _cancel_operational_blocks_for_occurrence(
    db: Session,
    occurrence: models.LessonOccurrence,
    *,
    organization_id: int,
    cancelled_by_user_id: Optional[int] = None,
    cancel_completed_substitute_log: bool = False,
) -> None:
    """Cancela blocos operacionais de uma ocorrência SUBSTITUTED.

    Se houver LessonLog COMPLETED, verifica timesheet e compensa progresso.
    """
    blocks = list(db.execute(
        select(models.OperationalScheduleBlock).where(
            and_(
                models.OperationalScheduleBlock.source_occurrence_id == occurrence.id,
                models.OperationalScheduleBlock.source_occurrence_revision == occurrence.revision,
                models.OperationalScheduleBlock.status == models.OperationalBlockStatus.ACTIVE,
            )
        )
    ).scalars())
    now = datetime.now(timezone.utc)
    for block in blocks:
        block_operation_id = str(_uuid.uuid4())
        op_log = db.execute(
            select(models.LessonLog).where(
                models.LessonLog.operational_block_id == block.id,
            )
        ).scalars().first()
        if op_log is not None and op_log.status == models.LessonLogStatus.COMPLETED:
            next_log_revision = int(op_log.version or 1) + 1
            week_start = block.date - timedelta(days=block.date.weekday())
            timesheet = db.execute(
                select(models.TeacherWeeklyTimesheet).where(
                    and_(
                        models.TeacherWeeklyTimesheet.organization_id == organization_id,
                        models.TeacherWeeklyTimesheet.teacher_id == block.teacher_id,
                        models.TeacherWeeklyTimesheet.week_start_date == week_start,
                    )
                )
            ).scalars().first()
            if timesheet and timesheet.status in (models.TimesheetStatus.SUBMITTED, models.TimesheetStatus.APPROVED):
                raise OccurrenceServiceError(status_code=409, detail=ERR_SUBSTITUTE_LOG_LOCKED)
            if not cancel_completed_substitute_log:
                raise OccurrenceServiceError(status_code=409, detail=ERR_SUBSTITUTE_LOG_LOCKED)
            block_hours = _duration_hours(block.date, block.timeslot)
            if block_hours > 0 and block.module_id is not None:
                _apply_state_accounting(
                    db,
                    organization_id=organization_id,
                    class_id=block.class_id,
                    status=models.LessonOccurrenceStatus.GIVEN,
                    planned_module_id=block.module_id,
                    executed_module_id=block.module_id,
                    planned_hours=block_hours,
                    direction=-1,
                )
                _record_progress_ledger_entries(
                    db,
                    organization_id=organization_id,
                    source_type="LESSON_LOG",
                    source_id=op_log.id,
                    source_revision=next_log_revision,
                    class_id=block.class_id,
                    status=models.LessonOccurrenceStatus.GIVEN,
                    planned_module_id=block.module_id,
                    executed_module_id=block.module_id,
                    planned_hours=block_hours,
                    direction=-1,
                    actor_user_id=cancelled_by_user_id,
                    operation_id=block_operation_id,
                )
            op_log.status = models.LessonLogStatus.PENDING
            op_log.version = next_log_revision
            op_log.logged_by_user_id = cancelled_by_user_id
            op_log.logged_at = now
        block.status = models.OperationalBlockStatus.CANCELLED
        block.execution_status = models.OperationalBlockExecutionStatus.CANCELLED
        block.cancelled_at = now


def _apply_state_accounting(
    db: Session,
    organization_id: int,
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
            organization_id=organization_id,
            class_id=class_id,
            module_id=planned_module_id,
            completed_delta=delta,
            debt_delta=0.0,
        )
        return

    if status == models.LessonOccurrenceStatus.GAP:
        _apply_module_delta(
            db,
            organization_id=organization_id,
            class_id=class_id,
            module_id=planned_module_id,
            completed_delta=0.0,
            debt_delta=delta,
        )
        return

    if status == models.LessonOccurrenceStatus.SUBSTITUTED:
        if executed_module_id is None:
            raise OccurrenceServiceError(status_code=422, detail=ERR_MISSING_EXECUTED_MODULE)

        if executed_module_id == planned_module_id:
            return

        _apply_module_delta(
            db,
            organization_id=organization_id,
            class_id=class_id,
            module_id=planned_module_id,
            completed_delta=0.0,
            debt_delta=delta,
        )
        # V4: O módulo do substituto NÃO é creditado aqui.
        # As horas são creditadas quando o professor substituto regista "Aula Dada"
        # no bloco de substituição, via LessonLog COMPLETED → _apply_state_accounting(GIVEN).
        


def _ledger_deltas_for_state(
    status: models.LessonOccurrenceStatus,
    planned_module_id: Optional[int],
    executed_module_id: Optional[int],
    planned_hours: float,
    direction: int,
) -> list[tuple[Optional[int], float, float]]:
    delta = planned_hours * direction
    if status == models.LessonOccurrenceStatus.GIVEN:
        return [(planned_module_id, delta, 0.0)]
    if status == models.LessonOccurrenceStatus.GAP:
        return [(planned_module_id, 0.0, delta)]
    if status == models.LessonOccurrenceStatus.SUBSTITUTED:
        if executed_module_id == planned_module_id:
            return []
        return [(planned_module_id, 0.0, delta)]
    return []


def _record_progress_ledger_entries(
    db: Session,
    *,
    organization_id: int,
    source_type: str,
    source_id: int,
    source_revision: Optional[int],
    class_id: int,
    status: models.LessonOccurrenceStatus,
    planned_module_id: Optional[int],
    executed_module_id: Optional[int],
    planned_hours: float,
    direction: int,
    actor_user_id: Optional[int] = None,
    operation_id: Optional[str] = None,
) -> None:
    op_id = operation_id or str(_uuid.uuid4())

    for index, (module_id, completed_delta, debt_delta) in enumerate(
        _ledger_deltas_for_state(status, planned_module_id, executed_module_id, planned_hours, direction)
    ):
        if module_id is None:
            continue
        idempotency_key = (
            f"{organization_id}:{source_type}:{source_id}:"
            f"{source_revision or 0}:{status.value}:{direction}:{module_id}:{index}:"
            f"{op_id}"
        )
        exists = db.query(models.ProgressLedgerEntry).filter(
            models.ProgressLedgerEntry.idempotency_key == idempotency_key
        ).first()
        if exists is not None:
            continue
        db.add(models.ProgressLedgerEntry(
            organization_id=organization_id,
            source_type=source_type,
            source_id=source_id,
            source_revision=source_revision,
            class_id=class_id,
            module_id=module_id,
            completed_delta=completed_delta,
            debt_delta=debt_delta,
            idempotency_key=idempotency_key,
            created_by_user_id=actor_user_id,
            created_at=datetime.now(timezone.utc),
        ))


def _is_idempotent_payload(
    occurrence: models.LessonOccurrence,
    payload: schemas.LessonOccurrenceUpdate,
) -> bool:
    if occurrence.decided_at is None:
        return False

    decision_matches = (
        occurrence.status == payload.status
        and occurrence.substitute_teacher_id == payload.substitute_teacher_id
        and occurrence.substitute_subject_id == payload.substitute_subject_id
    )
    if not decision_matches:
        return False

    current_version = int(occurrence.version or 1)
    payload_version = int(payload.version)

    # A retry can arrive after the first identical request committed and
    # bumped the occurrence version. Accept only the current version or the
    # immediately previous version for an identical payload.
    return payload_version in {current_version, current_version - 1}


def _validate_state_transition(
    occurrence: models.LessonOccurrence,
    payload: schemas.LessonOccurrenceUpdate,
) -> None:
    # V4: REVOKED é terminal — imutável
    if not occurrence.is_active:
        raise OccurrenceServiceError(status_code=409, detail=ERR_INACTIVE)

    if occurrence.status == models.LessonOccurrenceStatus.REVOKED:
        raise OccurrenceServiceError(status_code=409, detail="OCCURRENCE_REVOKED")

    if occurrence.decided_at is None:
        return

    # V4: Enforce ALLOWED_STATE_TRANSITIONS for re-decisions
    allowed_targets = ALLOWED_STATE_TRANSITIONS.get(occurrence.status, set())
    if payload.status not in allowed_targets:
        raise OccurrenceServiceError(
            status_code=422,
            detail=f"Transição de {occurrence.status.value} para {payload.status.value} não é permitida.",
        )



def create_occurrence_from_block_sync(
    db: Session,
    organization_id: int,
    schedule_output_id: int,
    created_by_user_id: Optional[int] = None,
    creation_source: str = "manual_admin",
    reason: Optional[str] = None,
) -> tuple[models.LessonOccurrence, bool]:
    """Cria (ou reutiliza) ocorrência operacional para um bloco planeado.

    Retorna (occurrence, created_now).
    """
    schedule_output = db.execute(
        select(models.ScheduleOutput)
        .options(
            joinedload(models.ScheduleOutput.lesson).joinedload(models.Lesson.subject),
            joinedload(models.ScheduleOutput.lesson).joinedload(models.Lesson.teacher),
            joinedload(models.ScheduleOutput.timeslot),
        )
        .where(
            and_(
                models.ScheduleOutput.id == schedule_output_id,
                models.ScheduleOutput.organization_id == organization_id,
            )
        )
    ).unique().scalar_one_or_none()

    if schedule_output is None:
        raise OccurrenceServiceError(status_code=404, detail=ERR_SCHEDULE_OUTPUT_NOT_FOUND)

    if schedule_output.is_draft:
        raise OccurrenceServiceError(status_code=409, detail=ERR_SCHEDULE_OUTPUT_IS_DRAFT)

    if schedule_output.date is None:
        raise OccurrenceServiceError(status_code=409, detail=ERR_SCHEDULE_OUTPUT_NO_DATE)

    # WBS V3 Fase 1.4: Rejeitar criação de ocorrência sobre LessonLog COMPLETED
    completed_log = db.query(models.LessonLog).filter(
        models.LessonLog.schedule_output_id == schedule_output_id,
        models.LessonLog.status == models.LessonLogStatus.COMPLETED,
    ).first()
    if completed_log is not None:
        raise OccurrenceServiceError(
            status_code=409,
            detail="Esta aula já foi registada como dada. Reverta o registo primeiro.",
        )

    existing = db.execute(
        select(models.LessonOccurrence).where(
            _active_occurrence_filter(organization_id, schedule_output.id, schedule_output.date)
        )
    ).unique().scalar_one_or_none()

    if existing is not None:
        existing_with_context = _get_occurrence_with_context_sync(db, existing.id, organization_id)
        if existing_with_context is not None:
            _attach_occurrence_read_context(existing_with_context)
            return existing_with_context, False
        return existing, False

    if schedule_output.lesson is None or schedule_output.lesson.subject is None:
        raise OccurrenceServiceError(status_code=422, detail=ERR_MISSING_SCHEDULE_CONTEXT)

    planned_hours = _duration_hours(schedule_output.date, schedule_output.timeslot)
    planned_module_id = _resolve_active_module_id_for_subject(
        db,
        class_id=schedule_output.lesson.class_id,
        subject=schedule_output.lesson.subject,
    )

    max_revision = db.execute(
        select(func.max(models.LessonOccurrence.revision)).where(
            and_(
                models.LessonOccurrence.organization_id == organization_id,
                models.LessonOccurrence.schedule_output_id == schedule_output.id,
                models.LessonOccurrence.date == schedule_output.date,
            )
        )
    ).scalar_one_or_none() or 0

    occurrence = models.LessonOccurrence(
        organization_id=organization_id,
        schedule_output_id=schedule_output.id,
        date=schedule_output.date,
        status=None,
        revision=int(max_revision) + 1,
        is_active=True,
        version=1,
        class_id=schedule_output.lesson.class_id,
        subject_id=schedule_output.lesson.subject_id,
        planned_timeslot_id=schedule_output.timeslot_id,
        planned_room_id=schedule_output.room_id,
        planned_generation_id=schedule_output.generation_id,
        planned_hours=planned_hours,
        planned_teacher_id=schedule_output.lesson.teacher_id,
        executed_teacher_id=None,
        planned_module_id=planned_module_id,
        executed_module_id=None,
        substitute_teacher_id=None,
        substitute_subject_id=None,
        hours_given=0.0,
        decided_by_user_id=None,
        decided_at=None,
        created_by_user_id=created_by_user_id,
        creation_source=creation_source,
        reason=reason,
        created_at=datetime.now(timezone.utc),
    )

    db.add(occurrence)

    try:
        db.commit()
        db.refresh(occurrence)
        occurrence_with_context = _get_occurrence_with_context_sync(db, occurrence.id, organization_id)
        if occurrence_with_context is not None:
            _attach_occurrence_read_context(occurrence_with_context)
            return occurrence_with_context, True
        return occurrence, True
    except IntegrityError:
        db.rollback()
        existing_after_race = db.execute(
            select(models.LessonOccurrence).where(
                _active_occurrence_filter(organization_id, schedule_output.id, schedule_output.date)
            )
        ).scalar_one_or_none()
        if existing_after_race is not None:
            existing_with_context = _get_occurrence_with_context_sync(db, existing_after_race.id, organization_id)
            if existing_with_context is not None:
                _attach_occurrence_read_context(existing_with_context)
                return existing_with_context, False
            return existing_after_race, False
        raise


def cancel_open_occurrence_for_block_sync(
    db: Session,
    organization_id: int,
    schedule_output_id: int,
) -> bool:
    """Marca como REVOKED uma LessonOccurrence não decidida associada a um bloco.

    Apenas atua sobre ocorrências com decided_at IS NULL (OPEN/indecisas).
    Ocorrências já decididas (GAP, SUBSTITUTED, GIVEN com decided_at preenchido)
    NÃO são afetadas — essas requerem a ação de "Reverter" do admin em /absences.

    Retorna True se marcou alguma ocorrência, False caso contrário.
    """
    occurrence = db.query(models.LessonOccurrence).filter(
        models.LessonOccurrence.organization_id == organization_id,
        models.LessonOccurrence.schedule_output_id == schedule_output_id,
        models.LessonOccurrence.decided_at.is_(None),
        models.LessonOccurrence.is_active.is_(True),
    ).first()

    if occurrence is None:
        return False

    occurrence.status = models.LessonOccurrenceStatus.REVOKED
    occurrence.is_active = False
    occurrence.revoked_at = datetime.now(timezone.utc)
    occurrence.revoked_reason = "Revertido pelo professor"
    _touch_occurrence_version(occurrence)
    db.flush()
    return True


def cancel_occurrence_sync(
    db: Session,
    organization_id: int,
    occurrence_id: int,
    cancelled_by_user_id: int,
    version: int = 1,
    reason: str = "Reversao administrativa",
    cancel_completed_substitute_log: bool = False,
) -> dict:
    """Marca uma LessonOccurrence como REVOKED e reverte o LessonLog.

    - Se a ocorrência já foi decidida: reverte a contabilidade
    - Se era SUBSTITUTED: cancela blocos operacionais do substituto
    - Marca a ocorrência como REVOKED (persiste para auditoria)
    - Reverte o LessonLog associado para PENDING

    Retorna {"cancelled": True, "schedule_output_id": int}
    """
    now = datetime.now(timezone.utc)

    occurrence = _get_occurrence_for_update_sync(db, occurrence_id, organization_id)

    if occurrence is None:
        raise OccurrenceServiceError(status_code=404, detail=OCCURRENCE_NOT_FOUND)

    # V4: REVOKED é imutável
    if occurrence.status == models.LessonOccurrenceStatus.REVOKED:
        raise OccurrenceServiceError(status_code=409, detail="OCCURRENCE_REVOKED")

    _assert_occurrence_version(occurrence, version)

    if not occurrence.is_active:
        raise OccurrenceServiceError(status_code=409, detail=ERR_INACTIVE)

    schedule_output_id = occurrence.schedule_output_id

    try:
        cancel_operation_id = str(_uuid.uuid4())
        # Reverter contabilidade se a ocorrência foi decidida
        if occurrence.decided_at is not None:
            schedule_output = occurrence.schedule_output
            if schedule_output is not None and schedule_output.lesson is not None:
                class_id = schedule_output.lesson.class_id
                planned_module_id = occurrence.planned_module_id
                executed_module_id = occurrence.executed_module_id
                planned_hours = occurrence.planned_hours or 0.0

                if planned_module_id is None and schedule_output.lesson.subject is not None:
                    planned_module_id = _resolve_active_module_id_for_subject(
                        db,
                        class_id=class_id,
                        subject=schedule_output.lesson.subject,
                    )

                if planned_hours > 0 and planned_module_id is not None:
                    _apply_state_accounting(
                        db,
                        organization_id=organization_id,
                        class_id=class_id,
                        status=occurrence.status,
                        planned_module_id=planned_module_id,
                        executed_module_id=executed_module_id,
                        planned_hours=planned_hours,
                        direction=-1,
                    )
                    _record_progress_ledger_entries(
                        db,
                        organization_id=organization_id,
                        source_type="OCCURRENCE_REVERSAL",
                        source_id=occurrence.id,
                        source_revision=occurrence.revision,
                        class_id=class_id,
                        status=occurrence.status,
                        planned_module_id=planned_module_id,
                        executed_module_id=executed_module_id,
                        planned_hours=planned_hours,
                        direction=-1,
                        actor_user_id=cancelled_by_user_id,
                        operation_id=cancel_operation_id,
                    )

            # Se era SUBSTITUTED, cancela os blocos operacionais do substituto.
            if occurrence.status == models.LessonOccurrenceStatus.SUBSTITUTED:
                _cancel_operational_blocks_for_occurrence(
                    db, occurrence,
                    organization_id=organization_id,
                    cancelled_by_user_id=cancelled_by_user_id,
                    cancel_completed_substitute_log=cancel_completed_substitute_log,
                )

        # Reverter LessonLog para PENDING
        lesson_log = db.execute(
            select(models.LessonLog).where(
                models.LessonLog.schedule_output_id == schedule_output_id,
            )
        ).scalars().first()
        if lesson_log is not None:
            lesson_log.status = models.LessonLogStatus.PENDING
            lesson_log.version = int(lesson_log.version or 1) + 1
            lesson_log.logged_by_user_id = cancelled_by_user_id
            lesson_log.logged_at = now

        # V4: Marcar REVOKED em vez de apagar (auditoria)
        occurrence.status = models.LessonOccurrenceStatus.REVOKED
        occurrence.is_active = False
        occurrence.decided_by_user_id = cancelled_by_user_id
        occurrence.revoked_at = now
        occurrence.revoked_by_user_id = cancelled_by_user_id
        occurrence.revoked_reason = reason
        _touch_occurrence_version(occurrence)
        db.commit()

    except OccurrenceServiceError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    return {"cancelled": True, "schedule_output_id": schedule_output_id, "revision": occurrence.revision}


def list_occurrences_sync(
    db: Session,
    organization_id: int,
    class_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    skip: int = 0,
    limit: int = 100,
    status_filter: Optional[str] = None,
    as_page: bool = False,
) -> dict | list[models.LessonOccurrence]:
    """Lista ocorrências com filtros opcionais."""
    if date_from is not None and date_to is not None and date_from > date_to:
        raise OccurrenceServiceError(status_code=422, detail="OCCURRENCE_INVALID_DATE_RANGE")

    skip = max(0, int(skip))
    limit = max(1, min(int(limit), 500))

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
            joinedload(models.LessonOccurrence.decided_by_user),
            joinedload(models.LessonOccurrence.planned_teacher),
            joinedload(models.LessonOccurrence.executed_teacher),
            joinedload(models.LessonOccurrence.substitute_teacher),
            joinedload(models.LessonOccurrence.class_),
            joinedload(models.LessonOccurrence.subject),
            joinedload(models.LessonOccurrence.planned_timeslot),
        )
        .where(models.LessonOccurrence.organization_id == organization_id)
    )

    stmt = stmt.outerjoin(
        models.ScheduleOutput,
        models.LessonOccurrence.schedule_output_id == models.ScheduleOutput.id,
    ).outerjoin(
        models.Timeslot,
        models.ScheduleOutput.timeslot_id == models.Timeslot.id,
    )

    if class_id is not None:
        stmt = stmt.outerjoin(
            models.Lesson,
            models.ScheduleOutput.lesson_id == models.Lesson.id,
        ).where(
            or_(
                models.LessonOccurrence.class_id == class_id,
                models.Lesson.class_id == class_id,
            )
        )
    if date_from is not None:
        stmt = stmt.where(models.LessonOccurrence.date >= date_from)
    if date_to is not None:
        stmt = stmt.where(models.LessonOccurrence.date <= date_to)
    # WBS V3 Fase 6: filter by status. OPEN = decided_at IS NULL
    if status_filter is not None:
        normalized_status = status_filter.upper()
        if normalized_status in {"OPEN", OP_STATE_OPEN}:
            stmt = stmt.where(
                and_(
                    models.LessonOccurrence.is_active.is_(True),
                    models.LessonOccurrence.status.is_(None),
                    models.LessonOccurrence.decided_at.is_(None),
                )
            )
        elif normalized_status in {"GIVEN", "GAP", "SUBSTITUTED", "REVOKED"}:
            enum_val = models.LessonOccurrenceStatus(normalized_status)
            stmt = stmt.where(models.LessonOccurrence.status == enum_val)
        else:
            raise OccurrenceServiceError(status_code=422, detail="OCCURRENCE_INVALID_STATUS")

    stmt = stmt.order_by(
        models.LessonOccurrence.date.asc(),
        models.Timeslot.start_time.asc().nulls_last(),
        models.LessonOccurrence.id.asc(),
    )
    count_stmt = select(func.count()).select_from(
        stmt.with_only_columns(models.LessonOccurrence.id).order_by(None).subquery()
    )
    total = int(db.execute(count_stmt).scalar_one())
    occurrences = list(db.execute(stmt.offset(skip).limit(limit)).scalars().unique())
    for occurrence in occurrences:
        _attach_occurrence_read_context(occurrence)
    if not as_page:
        return occurrences
    return {
        "items": occurrences,
        "total": int(total),
        "limit": int(limit),
        "offset": int(skip),
    }


# ---------------------------------------------------------------------------
# Actualização pelo diretor
# ---------------------------------------------------------------------------

def update_occurrence_sync(
    db: Session,
    occurrence_id: int,
    organization_id: int,
    payload: schemas.LessonOccurrenceUpdate,
    decided_by_user_id: Optional[int] = None,
) -> models.LessonOccurrence:
    """Aplica decisão operacional com máquina de estados e contabilização transacional."""
    occurrence = _get_occurrence_for_update_sync(db, occurrence_id, organization_id)
    if occurrence is None:
        raise OccurrenceServiceError(status_code=404, detail=OCCURRENCE_NOT_FOUND)

    if _is_idempotent_payload(occurrence, payload):
        occurrence_with_context = _get_occurrence_with_context_sync(db, occurrence.id, organization_id)
        if occurrence_with_context is not None:
            _attach_occurrence_read_context(occurrence_with_context)
            return occurrence_with_context
        return occurrence

    _assert_occurrence_version(occurrence, payload.version)

    _validate_state_transition(occurrence, payload)

    # SUBSTITUTED -> SUBSTITUTED redecision: only allow if identical (idempotent retry).
    # If teacher/subject differ and a completed operational log exists, block.
    if (occurrence.status == models.LessonOccurrenceStatus.SUBSTITUTED
            and occurrence.decided_at is not None
            and payload.status == models.LessonOccurrenceStatus.SUBSTITUTED):
        is_identical = (
            occurrence.substitute_teacher_id == payload.substitute_teacher_id
            and occurrence.substitute_subject_id == payload.substitute_subject_id
        )
        if not is_identical:
            has_completed_log = db.execute(
                select(models.LessonLog.id).join(
                    models.OperationalScheduleBlock,
                    models.LessonLog.operational_block_id == models.OperationalScheduleBlock.id,
                ).where(
                    and_(
                        models.OperationalScheduleBlock.source_occurrence_id == occurrence.id,
                        models.OperationalScheduleBlock.source_occurrence_revision == occurrence.revision,
                        models.LessonLog.status == models.LessonLogStatus.COMPLETED,
                    )
                )
            ).first() is not None
            if has_completed_log:
                raise OccurrenceServiceError(
                    status_code=409,
                    detail="SUBSTITUTE_LOG_LOCKED",
                )

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
            organization_id=organization_id,
            occurrence=occurrence,
            substitute_teacher_id=payload.substitute_teacher_id,
            substitute_subject_id=payload.substitute_subject_id,
        )

        executed_module_id = _resolve_active_module_id_by_subject_id(
            db,
            organization_id=organization_id,
            class_id=class_id,
            subject_id=payload.substitute_subject_id,
        )
        if executed_module_id is None:
            raise OccurrenceServiceError(status_code=422, detail=ERR_MISSING_EXECUTED_MODULE)
        executed_teacher_id = payload.substitute_teacher_id
        hours_given = 0.0
    elif payload.status == models.LessonOccurrenceStatus.GAP:
        executed_module_id = None
        executed_teacher_id = None
        hours_given = 0.0
    else:
        executed_module_id = planned_module_id
        executed_teacher_id = lesson.teacher_id
        hours_given = planned_hours

    try:
        decision_operation_id = str(_uuid.uuid4())
        # PRD §6.6: GIVEN progresso apenas se nao existir log completed equivalente
        has_completed_lesson_log = False
        if payload.status == models.LessonOccurrenceStatus.GIVEN:
            completed_log = db.execute(
                select(models.LessonLog.id).where(
                    and_(
                        models.LessonLog.schedule_output_id == occurrence.schedule_output_id,
                        models.LessonLog.status == models.LessonLogStatus.COMPLETED,
                    )
                )
            ).first()
            has_completed_lesson_log = completed_log is not None

        if occurrence.decided_at is not None:
            _apply_state_accounting(
                db,
                organization_id=organization_id,
                class_id=class_id,
                status=occurrence.status,
                planned_module_id=planned_module_id,
                executed_module_id=occurrence.executed_module_id,
                planned_hours=planned_hours,
                direction=-1,
            )
            _record_progress_ledger_entries(
                db,
                organization_id=organization_id,
                source_type="OCCURRENCE_REVERSAL",
                source_id=occurrence.id,
                source_revision=occurrence.revision,
                class_id=class_id,
                status=occurrence.status,
                planned_module_id=planned_module_id,
                executed_module_id=occurrence.executed_module_id,
                planned_hours=planned_hours,
                direction=-1,
                actor_user_id=decided_by_user_id,
                operation_id=decision_operation_id,
            )

        # PRD §6.6: GIVEN progresso apenas se nao existir log completed equivalente
        if not (payload.status == models.LessonOccurrenceStatus.GIVEN and has_completed_lesson_log):
            _apply_state_accounting(
                db,
                organization_id=organization_id,
                class_id=class_id,
                status=payload.status,
                planned_module_id=planned_module_id,
                executed_module_id=executed_module_id,
                planned_hours=planned_hours,
                direction=1,
            )
            _record_progress_ledger_entries(
                db,
                organization_id=organization_id,
                source_type="OCCURRENCE_DECISION",
                source_id=occurrence.id,
                source_revision=occurrence.revision,
                class_id=class_id,
                status=payload.status,
                planned_module_id=planned_module_id,
                executed_module_id=executed_module_id,
                planned_hours=planned_hours,
                direction=1,
                actor_user_id=decided_by_user_id,
                operation_id=decision_operation_id,
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

        if payload.status == models.LessonOccurrenceStatus.SUBSTITUTED:
            _ensure_operational_schedule_block(
                db,
                organization_id=organization_id,
                occurrence=occurrence,
                class_id=class_id,
                substitute_teacher_id=payload.substitute_teacher_id,
                substitute_subject_id=payload.substitute_subject_id,
                executed_module_id=executed_module_id,
                source_output=occurrence.schedule_output,
                created_by_user_id=decided_by_user_id,
            )
        else:
            _cancel_operational_blocks_for_occurrence(
                db, occurrence,
                organization_id=organization_id,
                cancelled_by_user_id=decided_by_user_id,
            )

        _touch_occurrence_version(occurrence)

        db.commit()
        db.refresh(occurrence)
    except OccurrenceServiceError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    occurrence_with_context = _get_occurrence_with_context_sync(db, occurrence.id, organization_id)
    if occurrence_with_context is not None:
        _attach_occurrence_read_context(occurrence_with_context)
        return occurrence_with_context
    return occurrence


# ---------------------------------------------------------------------------
# Confirmação automática diária (chamada pelo cron Celery Beat)
# ---------------------------------------------------------------------------

def auto_confirm_daily_sync(
    db: Session,
    organization_id: int,
    target_date: date,
    now: Optional[datetime] = None,
) -> int:
    """Cria registos GIVEN para todos os ScheduleOutputs do dia sem ocorrência.

    Retorna o número de registos criados.
    Returns 0 se não houver slots planeados para essa data.
    """
    now = now or datetime.now(timezone.utc)
    if not _auto_confirm_allowed_now(db, organization_id, now):
        return 0

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
                    models.ScheduleOutput.organization_id == organization_id,
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
                _active_occurrence_filter(organization_id, slot.id, target_date)
            )
        ).scalar_one_or_none()

        if existing is not None:
            continue  # Diretor já registou manualmente — respeitar

        # 3. Calcular horas do timeslot
        existing_lesson_log = db.query(models.LessonLog).filter(
            models.LessonLog.organization_id == organization_id,
            models.LessonLog.schedule_output_id == slot.id,
        ).first()
        if existing_lesson_log is not None and existing_lesson_log.status == models.LessonLogStatus.COMPLETED:
            continue
        if existing_lesson_log is not None and existing_lesson_log.status == models.LessonLogStatus.OCCURRENCE:
            try:
                create_occurrence_from_block_sync(
                    db,
                    organization_id=organization_id,
                    schedule_output_id=slot.id,
                    created_by_user_id=existing_lesson_log.logged_by_user_id,
                    creation_source="lesson_log",
                )
            except OccurrenceServiceError:
                pass
            continue

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
        max_revision = db.execute(
            select(func.max(models.LessonOccurrence.revision)).where(
                and_(
                    models.LessonOccurrence.organization_id == organization_id,
                    models.LessonOccurrence.schedule_output_id == slot.id,
                    models.LessonOccurrence.date == target_date,
                )
            )
        ).scalar_one_or_none() or 0

        occurrence = models.LessonOccurrence(
            organization_id=organization_id,
            schedule_output_id=slot.id,
            date=target_date,
            status=models.LessonOccurrenceStatus.GIVEN,
            revision=int(max_revision) + 1,
            is_active=True,
            version=1,
            class_id=slot.lesson.class_id if slot.lesson is not None else None,
            subject_id=slot.lesson.subject_id if slot.lesson is not None else None,
            planned_timeslot_id=slot.timeslot_id,
            planned_room_id=slot.room_id,
            planned_generation_id=slot.generation_id,
            planned_hours=planned_hours,
            planned_teacher_id=planned_teacher_id,
            executed_teacher_id=planned_teacher_id,
            planned_module_id=planned_module_id,
            executed_module_id=planned_module_id,
            hours_given=planned_hours,
            decided_at=datetime.now(timezone.utc),
            creation_source="auto_confirm",
            created_at=datetime.now(timezone.utc),
        )
        db.add(occurrence)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            continue

        # 5. Incrementar ClassProgress de forma consistente com a regra oficial
        if slot.lesson is not None:
            _apply_state_accounting(
                db,
                organization_id=organization_id,
                class_id=slot.lesson.class_id,
                status=models.LessonOccurrenceStatus.GIVEN,
                planned_module_id=planned_module_id,
                executed_module_id=planned_module_id,
                planned_hours=planned_hours,
                direction=1,
            )
            db.flush()
            _record_progress_ledger_entries(
                db,
                organization_id=organization_id,
                source_type="AUTO_CONFIRM",
                source_id=occurrence.id,
                source_revision=occurrence.revision,
                class_id=slot.lesson.class_id,
                status=models.LessonOccurrenceStatus.GIVEN,
                planned_module_id=planned_module_id,
                executed_module_id=planned_module_id,
                planned_hours=planned_hours,
                direction=1,
                operation_id=str(_uuid.uuid4()),
            )

        try:
            db.commit()
            created_count += 1
        except IntegrityError:
            db.rollback()
            continue

    return created_count


# ---------------------------------------------------------------------------
# Dívidas de horas
# ---------------------------------------------------------------------------

def get_debts_sync(
    db: Session, organization_id: int, class_id: Optional[int] = None
) -> schemas.DebtListRead:
    """Calcula dívidas operacionais por turma/disciplina.

    Regra: dívida é reconhecida no momento da decisão (GAP/SUBSTITUTED),
    sem depender de a data da aula já ter passado.
    """
    # Buscar ocorrências com dívida (GAP/SUBSTITUTED), sem corte por data.
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
                models.LessonOccurrence.organization_id == organization_id,
                models.LessonOccurrence.status.in_(DEBT_STATUSES),
            )
        )
    )
    if class_id is not None:
        stmt = (
            stmt
            .outerjoin(
                models.ScheduleOutput,
                models.LessonOccurrence.schedule_output_id == models.ScheduleOutput.id,
            )
            .outerjoin(models.Lesson, models.ScheduleOutput.lesson_id == models.Lesson.id)
            .where(
                or_(
                    models.LessonOccurrence.class_id == class_id,
                    models.Lesson.class_id == class_id,
                )
            )
        )

    occurrences = list(db.execute(stmt).scalars().unique())

    today = date.today()

    # Agregar por (class_id, subject_id)
    key_counts: dict[tuple[int, int], int] = defaultdict(int)
    key_hours: dict[tuple[int, int], float] = defaultdict(float)
    key_overdue_counts: dict[tuple[int, int], int] = defaultdict(int)
    key_overdue_hours: dict[tuple[int, int], float] = defaultdict(float)
    key_meta: dict[tuple[int, int], dict] = {}

    for occ in occurrences:
        if (
            occ.status == models.LessonOccurrenceStatus.SUBSTITUTED
            and occ.executed_module_id is not None
            and occ.executed_module_id == occ.planned_module_id
        ):
            continue
        so = occ.schedule_output
        lesson = so.lesson if so is not None else None
        debt_class_id = occ.class_id or (lesson.class_id if lesson is not None else None)
        debt_subject_id = occ.subject_id or (lesson.subject_id if lesson is not None else None)
        if debt_class_id is None or debt_subject_id is None:
            continue
        debt_hours = (
            float(occ.planned_hours)
            if occ.planned_hours > 0
            else _duration_hours(occ.date, so.timeslot if so is not None else occ.planned_timeslot)
        )
        if debt_hours <= 0:
            debt_hours = max(0.0, float(occ.hours_given))

        key = (debt_class_id, debt_subject_id)
        key_counts[key] += 1
        key_hours[key] += debt_hours
        if occ.date <= today:
            key_overdue_counts[key] += 1
            key_overdue_hours[key] += debt_hours
        if key not in key_meta:
            if lesson is None:
                lesson = SimpleNamespace(
                    class_model=occ.class_,
                    subject=occ.subject,
                    teacher_id=occ.planned_teacher_id,
                    teacher=occ.planned_teacher,
                )
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
            gap_occurrences_overdue=key_overdue_counts[k],
            hours_owed_overdue=round(key_overdue_hours[k], 2),
        )
        for k in sorted(key_counts.keys())
    ]

    return schemas.DebtListRead(
        total_gaps=sum(key_counts.values()),
        total_hours_owed=round(sum(key_hours.values()), 2),
        total_gaps_overdue=sum(key_overdue_counts.values()),
        total_hours_owed_overdue=round(sum(key_overdue_hours.values()), 2),
        as_of_date=today,
        items=items,
    )


# ---------------------------------------------------------------------------
# Encontrar substitutos disponíveis
# ---------------------------------------------------------------------------

def get_substitute_recommendations_sync(
    db: Session,
    organization_id: int,
    occurrence_id: int,
) -> list[schemas.SubstituteRecommendationRead]:
    occurrence = _get_occurrence_with_context_sync(db, occurrence_id, organization_id)
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
                    models.Class.organization_id == organization_id,
                    models.Class.is_archived.is_(False),
                    models.ClassSubjectLink.grade_level == models.Class.grade_level,
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
            organization_id=organization_id,
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
    repair_window_days = _resolve_repair_window_days(db, organization_id)
    period_start = target_date - timedelta(days=repair_window_days)

    substitutions_in_period = _compute_substitution_counts_in_period(
        db,
        organization_id=organization_id,
        class_id=class_id,
        teacher_ids=teacher_ids,
        date_from=period_start,
        date_to=target_date,
    )
    daily_load_hours = _compute_daily_load_hours(
        db,
        organization_id=organization_id,
        teacher_ids=teacher_ids,
        target_date=target_date,
    )
    last_substitution_dates = _compute_last_substitution_dates(
        db,
        organization_id=organization_id,
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
    db: Session, organization_id: int, timeslot_id: int, target_date: date
) -> list[schemas.AvailableSubstituteRead]:
    """Devolve professores assignados à organização que:
    1. Têm disponibilidade (score ≥ 0) no timeslot indicado.
    2. Não têm já uma aula agendada (ScheduleOutput) para essa data.

    Retorna uma lista de candidatos com a disciplina que leccionam.
    """
    # 1. Timeslot info
    ts = db.execute(
        select(models.Timeslot).where(
            and_(
                models.Timeslot.id == timeslot_id,
                models.Timeslot.organization_id == organization_id,
            )
        )
    ).scalar_one_or_none()

    if ts is None:
        return []

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
                    models.ScheduleOutput.organization_id == organization_id,
                    models.ScheduleOutput.timeslot_id == timeslot_id,
                    models.ScheduleOutput.date == target_date,
                    models.ScheduleOutput.is_draft.is_(False),
                )
            )
        ).all()
    }
    busy_teacher_ids.update({
        row.teacher_id
        for row in db.execute(
            select(models.OperationalScheduleBlock.teacher_id).where(
                and_(
                    models.OperationalScheduleBlock.organization_id == organization_id,
                    models.OperationalScheduleBlock.status == models.OperationalBlockStatus.ACTIVE,
                    models.OperationalScheduleBlock.timeslot_id == timeslot_id,
                    models.OperationalScheduleBlock.date == target_date,
                )
            )
        ).all()
    })

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
                    models.Class.organization_id == organization_id,
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
