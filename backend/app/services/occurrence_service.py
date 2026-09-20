"""Serviço de Ocorrências de Aulas (Sprint 2).

Responsabilidades:
- Registar faltas (GAP) e substituições (SUBSTITUTED) manualmente
- Calcular dívida curricular a partir do ledger e do horário ativo
- Encontrar professores disponíveis para substituição num slot
"""

from __future__ import annotations

import uuid as _uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from functools import partial
from types import SimpleNamespace

import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, joinedload

from app import models, schemas
from app.core.exceptions import AppError
from app.core.logging import safe_exception_frames
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
OCCURRENCE_REPORTED = "OCCURRENCE_REPORTED"
DECISION_GIVEN = "DECISION_GIVEN"
DECISION_GAP = "DECISION_GAP"
DECISION_SUBSTITUTED = "DECISION_SUBSTITUTED"
ADMINISTRATIVE_REVERSAL = "ADMINISTRATIVE_REVERSAL"
ERR_SCHEDULE_OUTPUT_NOT_FOUND = "Bloco planeado não encontrado"
ERR_SCHEDULE_OUTPUT_IS_DRAFT = "Bloco de rascunho não pode iniciar ocorrência operacional"
ERR_SCHEDULE_OUTPUT_NO_DATE = "Bloco sem data válida para criação de ocorrência"

ERR_ACTIVE_BLOCK_NOT_FOUND = "Bloco ativo nao encontrado"
ERR_STALE_VERSION = "OCCURRENCE_STALE_VERSION"
ERR_INACTIVE = "OCCURRENCE_INACTIVE"
ERR_SUBSTITUTE_LOG_LOCKED = "SUBSTITUTE_LOG_LOCKED"

ALLOWED_STATE_TRANSITIONS: dict[
    models.LessonOccurrenceStatus, set[models.LessonOccurrenceStatus]
] = {
    # Undecided (decided_at IS NULL): any transition allowed (handled by early return)
    # Decided states below — only re-decision to allowed targets
    models.LessonOccurrenceStatus.GIVEN: {
        models.LessonOccurrenceStatus.GIVEN,  # idempotent retry only
    },
    models.LessonOccurrenceStatus.GAP: {
        models.LessonOccurrenceStatus.GAP,  # idempotent retry
        models.LessonOccurrenceStatus.SUBSTITUTED,  # re-decision
    },
    models.LessonOccurrenceStatus.SUBSTITUTED: {
        models.LessonOccurrenceStatus.SUBSTITUTED,  # idempotent retry
        models.LessonOccurrenceStatus.GAP,  # re-decision
    },
    models.LessonOccurrenceStatus.REVOKED: set(),  # terminal — imutável
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


@dataclass(frozen=True, slots=True)
class OccurrenceTransitionPlan:
    """Pure decision for an occurrence state transition.

    The database mutation and accounting remain in the application service; this
    value object keeps the state-machine contract independently testable.
    """

    previous_status: models.LessonOccurrenceStatus | None
    next_status: models.LessonOccurrenceStatus
    is_redecision: bool
    reverses_accounting: bool
    requires_substitute: bool


@dataclass(frozen=True, slots=True)
class ProgressLedgerContext:
    organization_id: int
    source_type: str
    source_id: int
    source_revision: int | None
    class_id: int
    status: models.LessonOccurrenceStatus
    planned_module_id: int | None
    executed_module_id: int | None
    planned_hours: float
    direction: int
    actor_membership_id: int | None = None
    operation_id: str | None = None
    accounting_deltas: list[tuple[int | None, float, float]] | None = None


def build_occurrence_transition_plan(
    occurrence: models.LessonOccurrence,
    payload: schemas.LessonOccurrenceUpdate,
) -> OccurrenceTransitionPlan:
    if not occurrence.is_active:
        raise _occurrence_error(status_code=409, detail=ERR_INACTIVE)

    if occurrence.status == models.LessonOccurrenceStatus.REVOKED:
        raise _occurrence_error(status_code=409, detail="OCCURRENCE_REVOKED")

    is_redecision = occurrence.decided_at is not None
    if is_redecision:
        allowed_targets = ALLOWED_STATE_TRANSITIONS.get(occurrence.status, set())
        if payload.status not in allowed_targets:
            raise _occurrence_error(
                status_code=422,
                detail=(
                    f"Transição de {occurrence.status.value} para "
                    f"{payload.status.value} não é permitida."
                ),
            )

    return OccurrenceTransitionPlan(
        previous_status=occurrence.status,
        next_status=payload.status,
        is_redecision=is_redecision,
        reverses_accounting=is_redecision,
        requires_substitute=payload.status == models.LessonOccurrenceStatus.SUBSTITUTED,
    )


OBS_EVENT_CREATE = "CREATE_OCCURRENCE"
OBS_EVENT_DECIDE = "DECIDE_OCCURRENCE"

OBS_RESULT_SUCCESS = "SUCCESS"
OBS_RESULT_VALIDATION_FAILURE = "VALIDATION_FAILURE"
OBS_RESULT_CONFLICT = "CONFLICT"
OBS_RESULT_ERROR = "ERROR"

logger = structlog.get_logger(__name__)


def _occurrence_error(*, status_code: int, detail: str) -> AppError:
    kind = {
        400: "bad_request",
        404: "not_found",
        409: "conflict",
        422: "validation",
    }.get(status_code, "unexpected_error")
    code = {
        404: "resource_not_found",
        409: "conflict",
        422: "validation_error",
    }.get(status_code, "bad_request")
    return AppError(kind=kind, code=code, detail=detail)


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
        raise _occurrence_error(status_code=409, detail=ERR_STALE_VERSION)


def _active_block_occurrence_filter(
    organization_id: int, active_schedule_block_id: int, target_date: date
):
    return and_(
        models.LessonOccurrence.organization_id == organization_id,
        models.LessonOccurrence.active_schedule_block_id == active_schedule_block_id,
        models.LessonOccurrence.date == target_date,
        models.LessonOccurrence.is_active.is_(True),
    )


def _resolve_planned_context(
    db: Session,
    occurrence: models.LessonOccurrence,
) -> SimpleNamespace | None:
    block_id = occurrence.active_schedule_block_id
    if block_id is None:
        return None
    block = occurrence.active_schedule_block or db.get(models.ActiveScheduleBlock, block_id)
    if block is None:
        return None
    return SimpleNamespace(
        active_block=block,
        class_id=block.class_id,
        subject_id=block.subject_id,
        teacher_id=block.teacher_id,
        timeslot_id=block.timeslot_id,
        room_id=block.room_id,
        date=block.date,
        subject=db.get(models.Subject, block.subject_id),
        teacher=db.get(models.Teacher, block.teacher_id),
        class_model=db.get(models.Class, block.class_id),
        timeslot=db.get(models.Timeslot, block.timeslot_id),
        room=db.get(models.Room, block.room_id),
        planned_generation_id=block.schedule_version_id,
    )


def _sanitize_event_detail(detail: str | None) -> str | None:
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
    actor_membership_id: int | None = None,
    occurrence_id: int | None = None,
    active_schedule_block_id: int | None = None,
    decision_status: models.LessonOccurrenceStatus | None = None,
    detail: str | None = None,
) -> None:
    """Persist observability without poisoning the request transaction on failure."""
    try:
        with db.begin_nested():
            db.add(
                models.OccurrenceOperationalEvent(
                    organization_id=organization_id,
                    event_type=event_type,
                    result=result,
                    actor_membership_id=actor_membership_id,
                    occurrence_id=occurrence_id,
                    active_schedule_block_id=active_schedule_block_id,
                    decision_status=decision_status.value if decision_status else None,
                    detail=_sanitize_event_detail(detail),
                )
            )
            db.flush()
    except Exception as exc:
        logger.warning(
            "occurrence_observability_write_failed",
            error_type=type(exc).__name__,
            exception_frames=safe_exception_frames(exc),
        )


def get_occurrence_observability_summary_sync(
    db: Session,
    *,
    organization_id: int,
    window_days: int,
) -> dict:
    window_days = max(1, int(window_days))
    start_at = datetime.now(UTC) - timedelta(days=window_days)

    rows = db.execute(
        select(
            models.OccurrenceOperationalEvent.event_type,
            models.OccurrenceOperationalEvent.result,
            func.count(models.OccurrenceOperationalEvent.id),
        )
        .where(
            and_(
                models.OccurrenceOperationalEvent.organization_id == organization_id,
                models.OccurrenceOperationalEvent.created_at >= start_at,
            )
        )
        .group_by(
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
) -> models.LessonOccurrence:
    """Devolve uma ocorrência pelo ID, validando o tenant."""
    occurrence = _get_occurrence_with_context_sync(db, occurrence_id, organization_id)
    if occurrence is None:
        raise _occurrence_error(status_code=404, detail=OCCURRENCE_NOT_FOUND)
    _attach_occurrence_read_context(occurrence)
    return occurrence


def _get_occurrence_for_update_sync(
    db: Session,
    occurrence_id: int,
    organization_id: int,
) -> models.LessonOccurrence | None:
    return db.execute(
        select(models.LessonOccurrence)
        .where(
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
) -> models.LessonOccurrence | None:
    return (
        db.execute(
            select(models.LessonOccurrence)
            .options(
                joinedload(models.LessonOccurrence.active_schedule_block),
                joinedload(models.LessonOccurrence.decided_by_membership),
                joinedload(models.LessonOccurrence.planned_teacher),
                joinedload(models.LessonOccurrence.executed_teacher),
                joinedload(models.LessonOccurrence.substitute_teacher),
                joinedload(models.LessonOccurrence.class_),
                joinedload(models.LessonOccurrence.subject),
                joinedload(models.LessonOccurrence.planned_timeslot),
            )
            .where(
                models.LessonOccurrence.id == occurrence_id,
                models.LessonOccurrence.organization_id == organization_id,
            )
        )
        .unique()
        .scalar_one_or_none()
    )


def _attach_occurrence_read_context(occurrence: models.LessonOccurrence) -> None:
    """Attach response-only labels from the immutable occurrence snapshot."""
    executed_teacher = occurrence.executed_teacher or occurrence.substitute_teacher
    decided_by = occurrence.decided_by_membership
    occurrence.operational_state = get_operational_state(occurrence)
    occurrence.class_name = occurrence.class_.name if occurrence.class_ else None
    occurrence.subject_name = occurrence.subject.name if occurrence.subject else None
    occurrence.timeslot_id = occurrence.planned_timeslot_id
    occurrence.timeslot_start_time = (
        occurrence.planned_timeslot.start_time if occurrence.planned_timeslot else None
    )
    occurrence.timeslot_end_time = (
        occurrence.planned_timeslot.end_time if occurrence.planned_timeslot else None
    )
    occurrence.planned_teacher_name = (
        occurrence.planned_teacher.name if occurrence.planned_teacher else None
    )
    occurrence.executed_teacher_name = executed_teacher.name if executed_teacher else None
    occurrence.decided_by_membership_name = (
        decided_by.organization_display_name if decided_by else None
    )
    occurrence.lesson_log_summary = None
    occurrence.lesson_log_notes = None


def _resolve_repair_window_days(db: Session, organization_id: int) -> int:
    row = db.execute(
        select(models.OrganizationSettings.repair_stability_window_days)
        .where(models.OrganizationSettings.organization_id == organization_id)
        .order_by(models.OrganizationSettings.id.desc())
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
    organization_id: int,
    teacher_id: int,
    timeslot_id: int,
    target_date: date,
    exclude_active_schedule_block_id: int | None = None,
) -> bool:
    active_stmt = select(models.ActiveScheduleBlock.id).where(
        models.ActiveScheduleBlock.organization_id == organization_id,
        models.ActiveScheduleBlock.teacher_id == teacher_id,
        models.ActiveScheduleBlock.timeslot_id == timeslot_id,
        models.ActiveScheduleBlock.date == target_date,
        models.ActiveScheduleBlock.status == models.ActiveScheduleBlockStatus.ACTIVE,
    )
    if exclude_active_schedule_block_id is not None:
        active_stmt = active_stmt.where(
            models.ActiveScheduleBlock.id != exclude_active_schedule_block_id
        )
    if db.execute(active_stmt).first() is not None:
        return True

    if (
        db.execute(
            select(models.OperationalScheduleBlock.id).where(
                models.OperationalScheduleBlock.organization_id == organization_id,
                models.OperationalScheduleBlock.teacher_id == teacher_id,
                models.OperationalScheduleBlock.date == target_date,
                models.OperationalScheduleBlock.timeslot_id == timeslot_id,
                models.OperationalScheduleBlock.status == models.OperationalBlockStatus.ACTIVE,
            )
        ).first()
        is not None
    ):
        return True

    return (
        db.execute(
            select(models.LessonOccurrence.id).where(
                models.LessonOccurrence.organization_id == organization_id,
                models.LessonOccurrence.status == models.LessonOccurrenceStatus.SUBSTITUTED,
                models.LessonOccurrence.substitute_teacher_id == teacher_id,
                models.LessonOccurrence.date == target_date,
                models.LessonOccurrence.planned_timeslot_id == timeslot_id,
                models.LessonOccurrence.is_active.is_(True),
            )
        ).first()
        is not None
    )


def _is_room_compatible(
    room: models.Room | None,
    subject: models.Subject,
) -> bool:
    if room is None:
        return True
    return room.type == subject.required_room_type


def _validate_substitute_for_occurrence(
    db: Session,
    organization_id: int,
    occurrence: models.LessonOccurrence,
    substitute_teacher_id: int,
    substitute_subject_id: int,
) -> None:
    context = _resolve_planned_context(db, occurrence)
    if context is None or context.timeslot is None or context.subject is None:
        raise _occurrence_error(status_code=422, detail=ERR_MISSING_SCHEDULE_CONTEXT)

    class_id = context.class_id

    if substitute_teacher_id == context.teacher_id:
        raise _occurrence_error(status_code=409, detail=ERR_SUBSTITUTE_SAME_PLANNED_TEACHER)

    # Regra de domínio: substituição exige disciplina diferente da planeada.
    # O substituto dá a sua própria disciplina na mesma turma.
    if substitute_subject_id == context.subject_id:
        raise _occurrence_error(status_code=422, detail=ERR_SUBSTITUTE_SAME_SUBJECT)

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
        raise _occurrence_error(status_code=409, detail=ERR_SUBSTITUTE_NOT_ELIGIBLE)

    subject = _resolve_subject_for_org(db, organization_id, substitute_subject_id)
    if not _is_room_compatible(context.room, subject):
        raise _occurrence_error(status_code=409, detail=ERR_SUBSTITUTE_ROOM_MISMATCH)

    if not _teacher_is_available_for_slot(db, substitute_teacher_id, context.timeslot_id):
        raise _occurrence_error(status_code=409, detail=ERR_SUBSTITUTE_IMPOSSIBLE_AVAILABILITY)

    if _teacher_is_busy_in_slot(
        db,
        organization_id=organization_id,
        teacher_id=substitute_teacher_id,
        timeslot_id=context.timeslot_id,
        target_date=occurrence.date,
        exclude_active_schedule_block_id=(
            context.active_block.id if context.active_block is not None else None
        ),
    ):
        raise _occurrence_error(status_code=409, detail=ERR_SUBSTITUTE_SLOT_CONFLICT)


def _compute_daily_load_hours(
    db: Session,
    organization_id: int,
    teacher_ids: set[int],
    target_date: date,
) -> dict[int, float]:
    if not teacher_ids:
        return {}
    rows = db.execute(
        select(
            models.ActiveScheduleBlock.teacher_id,
            models.Timeslot.start_time,
            models.Timeslot.end_time,
        )
        .join(models.Timeslot, models.ActiveScheduleBlock.timeslot_id == models.Timeslot.id)
        .where(
            models.ActiveScheduleBlock.organization_id == organization_id,
            models.ActiveScheduleBlock.status == models.ActiveScheduleBlockStatus.ACTIVE,
            models.ActiveScheduleBlock.date == target_date,
            models.ActiveScheduleBlock.teacher_id.in_(teacher_ids),
        )
    ).all()
    rows += db.execute(
        select(
            models.OperationalScheduleBlock.teacher_id,
            models.Timeslot.start_time,
            models.Timeslot.end_time,
        )
        .join(models.Timeslot, models.OperationalScheduleBlock.timeslot_id == models.Timeslot.id)
        .where(
            models.OperationalScheduleBlock.organization_id == organization_id,
            models.OperationalScheduleBlock.status == models.OperationalBlockStatus.ACTIVE,
            models.OperationalScheduleBlock.date == target_date,
            models.OperationalScheduleBlock.teacher_id.in_(teacher_ids),
        )
    ).all()
    totals: dict[int, float] = defaultdict(float)
    for teacher_id, start_time, end_time in rows:
        duration = datetime.combine(target_date, end_time) - datetime.combine(
            target_date, start_time
        )
        totals[int(teacher_id)] += max(0.0, duration.total_seconds() / 3600)
    return dict(totals)


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
        .where(
            models.LessonOccurrence.organization_id == organization_id,
            models.LessonOccurrence.status == models.LessonOccurrenceStatus.SUBSTITUTED,
            models.LessonOccurrence.substitute_teacher_id.in_(teacher_ids),
            models.LessonOccurrence.date.between(date_from, date_to),
            models.LessonOccurrence.class_id == class_id,
        )
        .group_by(models.LessonOccurrence.substitute_teacher_id)
    ).all()
    return {int(teacher_id): int(count) for teacher_id, count in rows}


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
        .where(
            models.LessonOccurrence.organization_id == organization_id,
            models.LessonOccurrence.status == models.LessonOccurrenceStatus.SUBSTITUTED,
            models.LessonOccurrence.substitute_teacher_id.in_(teacher_ids),
            models.LessonOccurrence.date <= date_to,
            models.LessonOccurrence.class_id == class_id,
        )
        .group_by(models.LessonOccurrence.substitute_teacher_id)
    ).all()
    return {int(teacher_id): value for teacher_id, value in rows if value is not None}


def _duration_hours(target_date: date, timeslot: models.Timeslot | None) -> float:
    if timeslot is None:
        return 0.0
    start_dt = datetime.combine(target_date, timeslot.start_time)
    end_dt = datetime.combine(target_date, timeslot.end_time)
    return max(0.0, (end_dt - start_dt).total_seconds() / 3600.0)


def _resolve_occurrence_planned_hours(
    occurrence: models.LessonOccurrence,
) -> float:
    return max(0.0, float(occurrence.planned_hours or occurrence.hours_given or 0.0))


def _resolve_subject_for_org(
    db: Session,
    organization_id: int,
    subject_id: int,
) -> models.Subject:
    subject = (
        db.execute(
            select(models.Subject)
            .options(joinedload(models.Subject.modules))
            .where(
                and_(
                    models.Subject.id == subject_id,
                    models.Subject.organization_id == organization_id,
                )
            )
        )
        .unique()
        .scalar_one_or_none()
    )
    if subject is None:
        raise _occurrence_error(status_code=422, detail=ERR_SUBJECT_OUTSIDE_ORG)
    return subject


def _resolve_active_module_id_for_subject(
    db: Session,
    class_id: int,
    subject: models.Subject,
) -> int | None:
    modules = sorted(subject.modules, key=lambda module: module.order)
    if not modules:
        return None
    totals = {
        module_id: int(minutes or 0)
        for module_id, minutes in db.execute(
            select(
                models.ProgressLedgerEntry.module_id,
                func.sum(models.ProgressLedgerEntry.completed_minutes_delta),
            )
            .where(
                models.ProgressLedgerEntry.class_id == class_id,
                models.ProgressLedgerEntry.module_id.in_([module.id for module in modules]),
            )
            .group_by(models.ProgressLedgerEntry.module_id)
        ).all()
    }
    for module in modules:
        if totals.get(module.id, 0) < module.hours_total * 60:
            return module.id
    return modules[-1].id


def _resolve_active_module_id_by_subject_id(
    db: Session,
    organization_id: int,
    class_id: int,
    subject_id: int,
) -> int | None:
    subject = _resolve_subject_for_org(db, organization_id, subject_id)
    return _resolve_active_module_id_for_subject(db, class_id, subject)


def _ledger_totals_minutes(
    db: Session,
    organization_id: int,
    class_id: int,
    module_id: int,
) -> tuple[int, int]:
    row = db.execute(
        select(
            func.coalesce(func.sum(models.ProgressLedgerEntry.completed_minutes_delta), 0),
            func.coalesce(func.sum(models.ProgressLedgerEntry.debt_minutes_delta), 0),
        ).where(
            models.ProgressLedgerEntry.organization_id == organization_id,
            models.ProgressLedgerEntry.class_id == class_id,
            models.ProgressLedgerEntry.module_id == module_id,
        )
    ).one()
    return int(row[0]), int(row[1])


def _apply_module_delta(
    db: Session,
    organization_id: int,
    class_id: int,
    module_id: int | None,
    completed_delta: float,
    debt_delta: float,
) -> tuple[float, float]:
    if module_id is None:
        return (0.0, 0.0)
    if db.get(models.Module, module_id) is None:
        raise _occurrence_error(status_code=422, detail=ERR_MISSING_EXECUTED_MODULE)
    completed_minutes = int(round(completed_delta * 60))
    debt_minutes = int(round(debt_delta * 60))
    current_completed, current_debt = _ledger_totals_minutes(
        db, organization_id, class_id, module_id
    )
    if current_completed + completed_minutes < 0 or current_debt + debt_minutes < 0:
        raise _occurrence_error(status_code=409, detail=ERR_NEGATIVE_ACCOUNTING)
    return completed_minutes / 60.0, debt_minutes / 60.0


def _load_sequential_modules(
    db: Session,
    *,
    organization_id: int,
    anchor_module_id: int,
) -> list[models.Module]:
    anchor = db.get(models.Module, anchor_module_id)
    if anchor is None or anchor.organization_id != organization_id:
        raise _occurrence_error(status_code=422, detail=ERR_MISSING_EXECUTED_MODULE)
    return list(
        db.scalars(
            select(models.Module)
            .where(
                models.Module.organization_id == organization_id,
                models.Module.subject_id == anchor.subject_id,
            )
            .order_by(models.Module.order, models.Module.id)
        )
    )


def _allocate_sequential_completed_hours(
    db: Session,
    *,
    organization_id: int,
    class_id: int,
    modules: list[models.Module],
    hours_delta: float,
) -> list[tuple[int, float, float]]:
    remaining = abs(int(round(hours_delta * 60)))
    if remaining == 0:
        return []
    allocations = []
    ordered = modules if hours_delta > 0 else list(reversed(modules))
    for module in ordered:
        completed, _ = _ledger_totals_minutes(db, organization_id, class_id, module.id)
        available = (
            max(0, module.hours_total * 60 - completed) if hours_delta > 0 else max(0, completed)
        )
        applied = min(remaining, available)
        if not applied:
            continue
        signed = applied if hours_delta > 0 else -applied
        allocations.append((module.id, signed / 60.0, 0.0))
        remaining -= applied
        if not remaining:
            break
    if remaining:
        if hours_delta < 0:
            raise _occurrence_error(status_code=409, detail=ERR_NEGATIVE_ACCOUNTING)
        allocations.append((modules[-1].id, remaining / 60.0, 0.0))
    return allocations


def _apply_sequential_completed_hours(
    db: Session,
    *,
    organization_id: int,
    class_id: int,
    anchor_module_id: int,
    hours_delta: float,
) -> list[tuple[int, float, float]]:
    modules = _load_sequential_modules(
        db,
        organization_id=organization_id,
        anchor_module_id=anchor_module_id,
    )
    if not modules:
        return []
    return _allocate_sequential_completed_hours(
        db,
        organization_id=organization_id,
        class_id=class_id,
        modules=modules,
        hours_delta=hours_delta,
    )


def _ensure_operational_schedule_block(
    db: Session,
    *,
    organization_id: int,
    occurrence: models.LessonOccurrence,
    class_id: int,
    substitute_teacher_id: int,
    substitute_subject_id: int,
    executed_module_id: int | None,
    source_active_block: models.ActiveScheduleBlock,
    created_by_membership_id: int | None = None,
) -> models.OperationalScheduleBlock:
    existing = db.execute(
        select(models.OperationalScheduleBlock).where(
            models.OperationalScheduleBlock.organization_id == organization_id,
            models.OperationalScheduleBlock.source_occurrence_id == occurrence.id,
            models.OperationalScheduleBlock.source_occurrence_revision == occurrence.revision,
            models.OperationalScheduleBlock.status == models.OperationalBlockStatus.ACTIVE,
        )
    ).scalar_one_or_none()
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
        planned_active_schedule_block_id=source_active_block.id,
        date=occurrence.date,
        timeslot_id=source_active_block.timeslot_id,
        room_id=source_active_block.room_id,
        class_id=class_id,
        teacher_id=substitute_teacher_id,
        subject_id=substitute_subject_id,
        module_id=executed_module_id,
        status=models.OperationalBlockStatus.ACTIVE,
        execution_status=models.OperationalBlockExecutionStatus.PENDING_LOG,
        created_by_membership_id=created_by_membership_id,
        created_at=datetime.now(UTC),
    )
    db.add(block)
    db.flush()
    return block


def _cancel_operational_blocks_for_occurrence(
    db: Session,
    occurrence: models.LessonOccurrence,
    *,
    organization_id: int,
    cancelled_by_membership_id: int | None = None,
    cancel_completed_substitute_log: bool = False,
) -> None:
    """Cancela blocos operacionais de uma ocorrência SUBSTITUTED.

    Se houver LessonLog COMPLETED, verifica timesheet e compensa progresso.
    """
    blocks = list(
        db.execute(
            select(models.OperationalScheduleBlock).where(
                and_(
                    models.OperationalScheduleBlock.source_occurrence_id == occurrence.id,
                    models.OperationalScheduleBlock.source_occurrence_revision
                    == occurrence.revision,
                    models.OperationalScheduleBlock.status == models.OperationalBlockStatus.ACTIVE,
                )
            )
        ).scalars()
    )
    now = datetime.now(UTC)
    for block in blocks:
        block_operation_id = str(_uuid.uuid4())
        op_log = (
            db.execute(
                select(models.LessonLog).where(
                    models.LessonLog.operational_block_id == block.id,
                )
            )
            .scalars()
            .first()
        )
        if op_log is not None and op_log.status == models.LessonLogStatus.COMPLETED:
            next_log_revision = int(op_log.version or 1) + 1
            week_start = block.date - timedelta(days=block.date.weekday())
            timesheet = (
                db.execute(
                    select(models.TeacherWeeklyTimesheet).where(
                        and_(
                            models.TeacherWeeklyTimesheet.organization_id == organization_id,
                            models.TeacherWeeklyTimesheet.teacher_id == block.teacher_id,
                            models.TeacherWeeklyTimesheet.week_start_date == week_start,
                        )
                    )
                )
                .scalars()
                .first()
            )
            if timesheet and timesheet.status in (
                models.TimesheetStatus.SUBMITTED,
                models.TimesheetStatus.APPROVED,
            ):
                raise _occurrence_error(status_code=409, detail=ERR_SUBSTITUTE_LOG_LOCKED)
            if not cancel_completed_substitute_log:
                raise _occurrence_error(status_code=409, detail=ERR_SUBSTITUTE_LOG_LOCKED)
            block_hours = _duration_hours(block.date, block.timeslot)
            if block_hours > 0 and block.module_id is not None:
                accounting_deltas = _apply_state_accounting(
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
                    ProgressLedgerContext(
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
                        actor_membership_id=cancelled_by_membership_id,
                        operation_id=block_operation_id,
                        accounting_deltas=accounting_deltas,
                    ),
                )
            op_log.status = models.LessonLogStatus.PENDING
            op_log.version = next_log_revision
            op_log.logged_by_membership_id = cancelled_by_membership_id
            op_log.logged_at = now
        block.status = models.OperationalBlockStatus.CANCELLED
        block.execution_status = models.OperationalBlockExecutionStatus.CANCELLED
        block.cancelled_at = now


def _apply_state_accounting(
    db: Session,
    organization_id: int,
    class_id: int,
    status: models.LessonOccurrenceStatus,
    planned_module_id: int | None,
    executed_module_id: int | None,
    planned_hours: float,
    direction: int,
) -> list[tuple[int | None, float, float]]:
    if direction not in (-1, 1):
        raise ValueError("direction must be -1 or 1")

    delta = planned_hours * direction

    if status == models.LessonOccurrenceStatus.GIVEN:
        if planned_module_id is None:
            return []
        return _apply_sequential_completed_hours(
            db,
            organization_id=organization_id,
            class_id=class_id,
            anchor_module_id=planned_module_id,
            hours_delta=delta,
        )

    if status == models.LessonOccurrenceStatus.GAP:
        _apply_module_delta(
            db,
            organization_id=organization_id,
            class_id=class_id,
            module_id=planned_module_id,
            completed_delta=0.0,
            debt_delta=delta,
        )
        return [(planned_module_id, 0.0, delta)] if planned_module_id is not None else []

    if status == models.LessonOccurrenceStatus.SUBSTITUTED:
        if executed_module_id is None:
            raise _occurrence_error(status_code=422, detail=ERR_MISSING_EXECUTED_MODULE)

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

        return [(planned_module_id, 0.0, delta)] if planned_module_id is not None else []

    return []


def _ledger_deltas_for_state(
    status: models.LessonOccurrenceStatus,
    planned_module_id: int | None,
    executed_module_id: int | None,
    planned_hours: float,
    direction: int,
) -> list[tuple[int | None, float, float]]:
    delta = planned_hours * direction
    if status == models.LessonOccurrenceStatus.GIVEN:
        return [(planned_module_id, delta, 0.0)]
    if status == models.LessonOccurrenceStatus.GAP:
        return [(planned_module_id, 0.0, delta)]
    if status == models.LessonOccurrenceStatus.SUBSTITUTED:
        return [(planned_module_id, 0.0, delta)]
    return []


def _record_progress_ledger_entries(
    db: Session,
    context: ProgressLedgerContext,
) -> None:
    op_id = context.operation_id or str(_uuid.uuid4())

    deltas = context.accounting_deltas
    if deltas is None:
        deltas = _ledger_deltas_for_state(
            context.status,
            context.planned_module_id,
            context.executed_module_id,
            context.planned_hours,
            context.direction,
        )
    for index, (module_id, completed_delta, debt_delta) in enumerate(deltas):
        if module_id is None:
            continue
        idempotency_key = (
            f"{context.organization_id}:{context.source_type}:{context.source_id}:"
            f"{context.source_revision or 0}:{context.status.value}:{context.direction}:"
            f"{module_id}:{index}:"
            f"{op_id}"
        )
        exists = (
            db.query(models.ProgressLedgerEntry)
            .filter(models.ProgressLedgerEntry.idempotency_key == idempotency_key)
            .first()
        )
        if exists is not None:
            continue
        db.add(
            models.ProgressLedgerEntry(
                organization_id=context.organization_id,
                source_type=context.source_type,
                source_id=context.source_id,
                source_revision=context.source_revision,
                class_id=context.class_id,
                module_id=module_id,
                completed_minutes_delta=int(round(completed_delta * 60)),
                debt_minutes_delta=int(round(debt_delta * 60)),
                idempotency_key=idempotency_key,
                created_by_membership_id=context.actor_membership_id,
                created_at=datetime.now(UTC),
            )
        )


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
) -> OccurrenceTransitionPlan:
    return build_occurrence_transition_plan(occurrence, payload)


def create_occurrence_from_active_block_sync(
    db: Session,
    organization_id: int,
    active_schedule_block_id: int,
    created_by_membership_id: int | None = None,
    creation_source: str = "lesson_log",
    reason: str = OCCURRENCE_REPORTED,
) -> tuple[models.LessonOccurrence, bool]:
    """Create or reuse an operational occurrence for a published active block."""
    block = db.execute(
        select(models.ActiveScheduleBlock).where(
            and_(
                models.ActiveScheduleBlock.id == active_schedule_block_id,
                models.ActiveScheduleBlock.organization_id == organization_id,
                models.ActiveScheduleBlock.status == models.ActiveScheduleBlockStatus.ACTIVE,
            )
        )
    ).scalar_one_or_none()
    if block is None:
        raise _occurrence_error(status_code=404, detail=ERR_ACTIVE_BLOCK_NOT_FOUND)

    completed_log = (
        db.query(models.LessonLog)
        .filter(
            models.LessonLog.organization_id == organization_id,
            models.LessonLog.active_schedule_block_id == block.id,
            models.LessonLog.status == models.LessonLogStatus.COMPLETED,
        )
        .first()
    )
    if completed_log is not None:
        raise _occurrence_error(
            status_code=409,
            detail="Esta aula ja foi registada como dada. Reverta o registo primeiro.",
        )

    existing = (
        db.execute(
            select(models.LessonOccurrence).where(
                _active_block_occurrence_filter(organization_id, block.id, block.date)
            )
        )
        .unique()
        .scalar_one_or_none()
    )
    if existing is not None:
        existing_with_context = _get_occurrence_with_context_sync(db, existing.id, organization_id)
        if existing_with_context is not None:
            _attach_occurrence_read_context(existing_with_context)
            return existing_with_context, False
        return existing, False

    subject = db.get(models.Subject, block.subject_id)
    if subject is None:
        raise _occurrence_error(status_code=422, detail=ERR_MISSING_SCHEDULE_CONTEXT)

    planned_module_id = _resolve_active_module_id_for_subject(
        db,
        class_id=block.class_id,
        subject=subject,
    )
    max_revision = (
        db.execute(
            select(func.max(models.LessonOccurrence.revision)).where(
                and_(
                    models.LessonOccurrence.organization_id == organization_id,
                    models.LessonOccurrence.active_schedule_block_id == block.id,
                    models.LessonOccurrence.date == block.date,
                )
            )
        ).scalar_one_or_none()
        or 0
    )

    occurrence = models.LessonOccurrence(
        organization_id=organization_id,
        active_schedule_block_id=block.id,
        date=block.date,
        status=None,
        revision=int(max_revision) + 1,
        is_active=True,
        version=1,
        class_id=block.class_id,
        subject_id=block.subject_id,
        planned_timeslot_id=block.timeslot_id,
        planned_room_id=block.room_id,
        planned_generation_id=block.schedule_version_id,
        planned_hours=round(float(block.duration_minutes) / 60.0, 4),
        planned_teacher_id=block.teacher_id,
        executed_teacher_id=None,
        planned_module_id=planned_module_id,
        executed_module_id=None,
        substitute_teacher_id=None,
        substitute_subject_id=None,
        hours_given=0.0,
        decided_by_membership_id=None,
        decided_at=None,
        created_by_membership_id=created_by_membership_id,
        creation_source=creation_source,
        reason=reason,
        created_at=datetime.now(UTC),
    )
    db.add(occurrence)

    try:
        db.flush()
        db.refresh(occurrence)
        occurrence_with_context = _get_occurrence_with_context_sync(
            db, occurrence.id, organization_id
        )
        if occurrence_with_context is not None:
            _attach_occurrence_read_context(occurrence_with_context)
            return occurrence_with_context, True
        return occurrence, True
    except IntegrityError:
        existing_after_race = db.execute(
            select(models.LessonOccurrence).where(
                _active_block_occurrence_filter(organization_id, block.id, block.date)
            )
        ).scalar_one_or_none()
        if existing_after_race is not None:
            existing_with_context = _get_occurrence_with_context_sync(
                db, existing_after_race.id, organization_id
            )
            if existing_with_context is not None:
                _attach_occurrence_read_context(existing_with_context)
                return existing_with_context, False
            return existing_after_race, False
        raise


def cancel_open_occurrence_for_active_block_sync(
    db: Session,
    organization_id: int,
    active_schedule_block_id: int,
) -> bool:
    occurrence = (
        db.query(models.LessonOccurrence)
        .filter(
            models.LessonOccurrence.organization_id == organization_id,
            models.LessonOccurrence.active_schedule_block_id == active_schedule_block_id,
            models.LessonOccurrence.decided_at.is_(None),
            models.LessonOccurrence.is_active.is_(True),
        )
        .first()
    )

    if occurrence is None:
        return False

    occurrence.status = models.LessonOccurrenceStatus.REVOKED
    occurrence.is_active = False
    occurrence.revoked_at = datetime.now(UTC)
    occurrence.revoked_reason = ADMINISTRATIVE_REVERSAL
    _touch_occurrence_version(occurrence)
    db.flush()
    return True


def cancel_occurrence_sync(
    db: Session,
    organization_id: int,
    occurrence_id: int,
    cancelled_by_membership_id: int,
    version: int = 1,
    reason: str = ADMINISTRATIVE_REVERSAL,
    cancel_completed_substitute_log: bool = False,
) -> dict:
    """Marca uma LessonOccurrence como REVOKED e reverte o LessonLog.

    - Se a ocorrência já foi decidida: reverte a contabilidade
    - Se era SUBSTITUTED: cancela blocos operacionais do substituto
    - Marca a ocorrência como REVOKED (persiste para auditoria)
    - Reverte o LessonLog associado para PENDING

    Retorna o identificador canónico do bloco publicado.
    """
    now = datetime.now(UTC)

    occurrence = _get_occurrence_for_update_sync(db, occurrence_id, organization_id)

    if occurrence is None:
        raise _occurrence_error(status_code=404, detail=OCCURRENCE_NOT_FOUND)

    # V4: REVOKED é imutável
    if occurrence.status == models.LessonOccurrenceStatus.REVOKED:
        raise _occurrence_error(status_code=409, detail="OCCURRENCE_REVOKED")

    _assert_occurrence_version(occurrence, version)

    if not occurrence.is_active:
        raise _occurrence_error(status_code=409, detail=ERR_INACTIVE)

    active_schedule_block_id = occurrence.active_schedule_block_id
    planned_context = _resolve_planned_context(db, occurrence)

    try:
        cancel_operation_id = str(_uuid.uuid4())
        # Reverter contabilidade se a ocorrência foi decidida
        if occurrence.decided_at is not None:
            if planned_context is not None:
                class_id = planned_context.class_id
                planned_module_id = occurrence.planned_module_id
                executed_module_id = occurrence.executed_module_id
                planned_hours = occurrence.planned_hours or 0.0

                if planned_module_id is None and planned_context.subject is not None:
                    planned_module_id = _resolve_active_module_id_for_subject(
                        db,
                        class_id=class_id,
                        subject=planned_context.subject,
                    )

                if planned_hours > 0 and planned_module_id is not None:
                    accounting_deltas = _apply_state_accounting(
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
                        ProgressLedgerContext(
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
                            actor_membership_id=cancelled_by_membership_id,
                            operation_id=cancel_operation_id,
                            accounting_deltas=accounting_deltas,
                        ),
                    )

            # Se era SUBSTITUTED, cancela os blocos operacionais do substituto.
            if occurrence.status == models.LessonOccurrenceStatus.SUBSTITUTED:
                _cancel_operational_blocks_for_occurrence(
                    db,
                    occurrence,
                    organization_id=organization_id,
                    cancelled_by_membership_id=cancelled_by_membership_id,
                    cancel_completed_substitute_log=cancel_completed_substitute_log,
                )

        # Reverter LessonLog para PENDING
        lesson_log = (
            db.execute(
                select(models.LessonLog).where(
                    models.LessonLog.active_schedule_block_id == active_schedule_block_id,
                )
            )
            .scalars()
            .first()
        )
        if lesson_log is not None:
            lesson_log.status = models.LessonLogStatus.PENDING
            lesson_log.version = int(lesson_log.version or 1) + 1
            lesson_log.logged_by_membership_id = cancelled_by_membership_id
            lesson_log.logged_at = now

        # V4: Marcar REVOKED em vez de apagar (auditoria)
        occurrence.status = models.LessonOccurrenceStatus.REVOKED
        occurrence.is_active = False
        occurrence.decided_by_membership_id = cancelled_by_membership_id
        occurrence.revoked_at = now
        occurrence.revoked_by_membership_id = cancelled_by_membership_id
        occurrence.revoked_reason = reason
        _touch_occurrence_version(occurrence)
        db.flush()

    except AppError:
        raise
    except Exception:
        raise

    return {
        "cancelled": True,
        "active_schedule_block_id": active_schedule_block_id,
        "revision": occurrence.revision,
    }


def list_occurrences_sync(
    db: Session,
    organization_id: int,
    class_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    skip: int = 0,
    limit: int = 100,
    status_filter: str | None = None,
    as_page: bool = False,
) -> dict | list[models.LessonOccurrence]:
    if date_from is not None and date_to is not None and date_from > date_to:
        raise _occurrence_error(status_code=422, detail="OCCURRENCE_INVALID_DATE_RANGE")
    stmt = select(models.LessonOccurrence).where(
        models.LessonOccurrence.organization_id == organization_id
    )
    if class_id is not None:
        stmt = stmt.where(models.LessonOccurrence.class_id == class_id)
    if date_from is not None:
        stmt = stmt.where(models.LessonOccurrence.date >= date_from)
    if date_to is not None:
        stmt = stmt.where(models.LessonOccurrence.date <= date_to)
    if status_filter is not None:
        normalized = status_filter.upper()
        if normalized in {"OPEN", OP_STATE_OPEN}:
            stmt = stmt.where(
                models.LessonOccurrence.is_active.is_(True),
                models.LessonOccurrence.status.is_(None),
                models.LessonOccurrence.decided_at.is_(None),
            )
        elif normalized in {"GIVEN", "GAP", "SUBSTITUTED", "REVOKED"}:
            stmt = stmt.where(
                models.LessonOccurrence.status == models.LessonOccurrenceStatus(normalized)
            )
        else:
            raise _occurrence_error(status_code=422, detail="OCCURRENCE_INVALID_STATUS")
    stmt = stmt.order_by(models.LessonOccurrence.date, models.LessonOccurrence.id)
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    rows = list(db.execute(stmt.offset(max(0, skip)).limit(min(500, max(1, limit)))).scalars())
    for row in rows:
        hydrated = _get_occurrence_with_context_sync(db, row.id, organization_id)
        if hydrated is not None:
            _attach_occurrence_read_context(hydrated)
    if not as_page:
        return rows
    return {"items": rows, "total": int(total or 0), "limit": limit, "offset": skip}


def update_occurrence_sync(
    db: Session,
    occurrence_id: int,
    organization_id: int,
    payload: schemas.LessonOccurrenceUpdate,
    decided_by_membership_id: int | None = None,
) -> models.LessonOccurrence:
    """Aplica decisão operacional com máquina de estados e contabilização transacional."""
    occurrence = _get_occurrence_for_update_sync(db, occurrence_id, organization_id)
    if occurrence is None:
        raise _occurrence_error(status_code=404, detail=OCCURRENCE_NOT_FOUND)

    if _is_idempotent_payload(occurrence, payload):
        occurrence_with_context = _get_occurrence_with_context_sync(
            db, occurrence.id, organization_id
        )
        if occurrence_with_context is not None:
            _attach_occurrence_read_context(occurrence_with_context)
            return occurrence_with_context
        return occurrence

    _assert_occurrence_version(occurrence, payload.version)

    transition = _validate_state_transition(occurrence, payload)

    # SUBSTITUTED -> SUBSTITUTED redecision: only allow if identical (idempotent retry).
    # If teacher/subject differ and a completed operational log exists, block.
    if (
        occurrence.status == models.LessonOccurrenceStatus.SUBSTITUTED
        and occurrence.decided_at is not None
        and payload.status == models.LessonOccurrenceStatus.SUBSTITUTED
    ):
        is_identical = (
            occurrence.substitute_teacher_id == payload.substitute_teacher_id
            and occurrence.substitute_subject_id == payload.substitute_subject_id
        )
        if not is_identical:
            has_completed_log = (
                db.execute(
                    select(models.LessonLog.id)
                    .join(
                        models.OperationalScheduleBlock,
                        models.LessonLog.operational_block_id == models.OperationalScheduleBlock.id,
                    )
                    .where(
                        and_(
                            models.OperationalScheduleBlock.source_occurrence_id == occurrence.id,
                            models.OperationalScheduleBlock.source_occurrence_revision
                            == occurrence.revision,
                            models.LessonLog.status == models.LessonLogStatus.COMPLETED,
                        )
                    )
                ).first()
                is not None
            )
            if has_completed_log:
                raise _occurrence_error(
                    status_code=409,
                    detail="SUBSTITUTE_LOG_LOCKED",
                )

    planned_context = _resolve_planned_context(db, occurrence)
    if planned_context is None:
        raise _occurrence_error(status_code=422, detail=ERR_MISSING_SCHEDULE_CONTEXT)

    class_id = planned_context.class_id
    if planned_context.subject is None:
        raise _occurrence_error(status_code=422, detail=ERR_MISSING_PLANNED_MODULE)

    planned_hours = _resolve_occurrence_planned_hours(occurrence)

    planned_module_id = occurrence.planned_module_id
    if planned_module_id is None:
        planned_module_id = _resolve_active_module_id_for_subject(
            db,
            class_id=class_id,
            subject=planned_context.subject,
        )
    if planned_module_id is None:
        raise _occurrence_error(status_code=422, detail=ERR_MISSING_PLANNED_MODULE)

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
            raise _occurrence_error(status_code=422, detail=ERR_MISSING_EXECUTED_MODULE)
        executed_teacher_id = payload.substitute_teacher_id
        hours_given = 0.0
    elif payload.status == models.LessonOccurrenceStatus.GAP:
        executed_module_id = None
        executed_teacher_id = None
        hours_given = 0.0
    else:
        executed_module_id = planned_module_id
        executed_teacher_id = planned_context.teacher_id
        hours_given = planned_hours

    try:
        decision_operation_id = str(_uuid.uuid4())
        # PRD §6.6: GIVEN progresso apenas se nao existir log completed equivalente
        has_completed_lesson_log = False
        if payload.status == models.LessonOccurrenceStatus.GIVEN:
            completed_log = db.execute(
                select(models.LessonLog.id).where(
                    and_(
                        models.LessonLog.active_schedule_block_id
                        == occurrence.active_schedule_block_id,
                        models.LessonLog.status == models.LessonLogStatus.COMPLETED,
                    )
                )
            ).first()
            has_completed_lesson_log = completed_log is not None

        if transition.reverses_accounting:
            accounting_deltas = _apply_state_accounting(
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
                ProgressLedgerContext(
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
                    actor_membership_id=decided_by_membership_id,
                    operation_id=decision_operation_id,
                    accounting_deltas=accounting_deltas,
                ),
            )

        # PRD §6.6: GIVEN progresso apenas se nao existir log completed equivalente
        if not (payload.status == models.LessonOccurrenceStatus.GIVEN and has_completed_lesson_log):
            accounting_deltas = _apply_state_accounting(
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
                ProgressLedgerContext(
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
                    actor_membership_id=decided_by_membership_id,
                    operation_id=decision_operation_id,
                    accounting_deltas=accounting_deltas,
                ),
            )

        occurrence.status = payload.status
        occurrence.planned_hours = planned_hours
        occurrence.planned_teacher_id = planned_context.teacher_id
        occurrence.executed_teacher_id = executed_teacher_id
        occurrence.planned_module_id = planned_module_id
        occurrence.executed_module_id = executed_module_id
        occurrence.substitute_teacher_id = payload.substitute_teacher_id
        occurrence.substitute_subject_id = payload.substitute_subject_id
        occurrence.hours_given = hours_given
        occurrence.decided_by_membership_id = decided_by_membership_id
        occurrence.decided_at = datetime.now(UTC)
        occurrence.reason = {
            models.LessonOccurrenceStatus.GIVEN: DECISION_GIVEN,
            models.LessonOccurrenceStatus.GAP: DECISION_GAP,
            models.LessonOccurrenceStatus.SUBSTITUTED: DECISION_SUBSTITUTED,
        }[payload.status]

        if payload.status == models.LessonOccurrenceStatus.SUBSTITUTED:
            _ensure_operational_schedule_block(
                db,
                organization_id=organization_id,
                occurrence=occurrence,
                class_id=class_id,
                substitute_teacher_id=payload.substitute_teacher_id,
                substitute_subject_id=payload.substitute_subject_id,
                executed_module_id=executed_module_id,
                source_active_block=planned_context.active_block,
                created_by_membership_id=decided_by_membership_id,
            )
        else:
            _cancel_operational_blocks_for_occurrence(
                db,
                occurrence,
                organization_id=organization_id,
                cancelled_by_membership_id=decided_by_membership_id,
            )

        _touch_occurrence_version(occurrence)

        db.flush()
        db.refresh(occurrence)
    except AppError:
        raise
    except Exception:
        raise

    occurrence_with_context = _get_occurrence_with_context_sync(db, occurrence.id, organization_id)
    if occurrence_with_context is not None:
        _attach_occurrence_read_context(occurrence_with_context)
        return occurrence_with_context
    return occurrence


# ---------------------------------------------------------------------------
# Confirmação automática diária (chamada pelo cron Celery Beat)
# ---------------------------------------------------------------------------


def get_debts_sync(
    db: Session, organization_id: int, class_id: int | None = None
) -> schemas.DebtListRead:
    stmt = (
        select(models.LessonOccurrence)
        .options(
            joinedload(models.LessonOccurrence.class_),
            joinedload(models.LessonOccurrence.subject),
            joinedload(models.LessonOccurrence.planned_teacher),
            joinedload(models.LessonOccurrence.planned_timeslot),
        )
        .where(
            models.LessonOccurrence.organization_id == organization_id,
            models.LessonOccurrence.status.in_(DEBT_STATUSES),
        )
    )
    if class_id is not None:
        stmt = stmt.where(models.LessonOccurrence.class_id == class_id)
    occurrences = list(db.execute(stmt).scalars().unique())
    today = date.today()
    counts = defaultdict(int)
    hours = defaultdict(float)
    overdue_counts = defaultdict(int)
    overdue_hours = defaultdict(float)
    meta = {}
    for occurrence in occurrences:
        if occurrence.class_id is None or occurrence.subject_id is None:
            continue
        key = (occurrence.class_id, occurrence.subject_id)
        debt_hours = _resolve_occurrence_planned_hours(occurrence)
        counts[key] += 1
        hours[key] += debt_hours
        if occurrence.date <= today:
            overdue_counts[key] += 1
            overdue_hours[key] += debt_hours
        meta[key] = {
            "class_name": occurrence.class_.name if occurrence.class_ else "—",
            "subject_name": occurrence.subject.name if occurrence.subject else "—",
            "teacher_id": occurrence.planned_teacher_id,
            "teacher_name": occurrence.planned_teacher.name if occurrence.planned_teacher else None,
        }
    items = [
        schemas.DebtItem(
            class_id=key[0],
            class_name=meta[key]["class_name"],
            subject_id=key[1],
            subject_name=meta[key]["subject_name"],
            teacher_id=meta[key]["teacher_id"],
            teacher_name=meta[key]["teacher_name"],
            gap_occurrences=counts[key],
            hours_owed=round(hours[key], 2),
            gap_occurrences_overdue=overdue_counts[key],
            hours_owed_overdue=round(overdue_hours[key], 2),
        )
        for key in sorted(counts)
    ]
    return schemas.DebtListRead(
        total_gaps=sum(counts.values()),
        total_hours_owed=round(sum(hours.values()), 2),
        total_gaps_overdue=sum(overdue_counts.values()),
        total_hours_owed_overdue=round(sum(overdue_hours.values()), 2),
        as_of_date=today,
        items=items,
    )


def get_substitute_recommendations_sync(
    db: Session,
    organization_id: int,
    occurrence_id: int,
) -> list[schemas.SubstituteRecommendationRead]:
    occurrence = _get_occurrence_with_context_sync(db, occurrence_id, organization_id)
    if occurrence is None:
        raise _occurrence_error(status_code=404, detail=OCCURRENCE_NOT_FOUND)

    planned_context = _resolve_planned_context(db, occurrence)
    if planned_context is None or planned_context.timeslot is None:
        raise _occurrence_error(status_code=422, detail=ERR_MISSING_SCHEDULE_CONTEXT)

    if planned_context.class_model is None:
        raise _occurrence_error(status_code=422, detail=ERR_MISSING_SCHEDULE_CONTEXT)

    class_id = planned_context.class_id
    planned_subject_id = planned_context.subject_id
    planned_teacher_id = planned_context.teacher_id
    timeslot_id = planned_context.timeslot_id
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

        if link.subject_id == planned_subject_id:
            continue

        if not _is_room_compatible(planned_context.room, link.subject):
            continue

        if not _teacher_is_available_for_slot(db, teacher_id, timeslot_id):
            continue

        if _teacher_is_busy_in_slot(
            db,
            organization_id=organization_id,
            teacher_id=teacher_id,
            timeslot_id=timeslot_id,
            target_date=target_date,
            exclude_active_schedule_block_id=(
                planned_context.active_block.id
                if planned_context.active_block is not None
                else None
            ),
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
    2. Não têm já um bloco ativo ou operacional nessa data.

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

    # 3. Professores já ocupados nesta data/timeslot.
    busy_teacher_ids = {
        row.teacher_id
        for row in db.execute(
            select(models.ActiveScheduleBlock.teacher_id).where(
                and_(
                    models.ActiveScheduleBlock.organization_id == organization_id,
                    models.ActiveScheduleBlock.timeslot_id == timeslot_id,
                    models.ActiveScheduleBlock.date == target_date,
                    models.ActiveScheduleBlock.status == models.ActiveScheduleBlockStatus.ACTIVE,
                )
            )
        ).all()
    }
    busy_teacher_ids.update(
        {
            row.teacher_id
            for row in db.execute(
                select(models.OperationalScheduleBlock.teacher_id).where(
                    and_(
                        models.OperationalScheduleBlock.organization_id == organization_id,
                        models.OperationalScheduleBlock.status
                        == models.OperationalBlockStatus.ACTIVE,
                        models.OperationalScheduleBlock.timeslot_id == timeslot_id,
                        models.OperationalScheduleBlock.date == target_date,
                    )
                )
            ).all()
        }
    )

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


# ---------------------------------------------------------------------------
# Async application entry points
# ---------------------------------------------------------------------------


async def get_occurrence(
    db: AsyncSession, occurrence_id: int, organization_id: int
) -> models.LessonOccurrence:
    return await db.run_sync(
        partial(
            get_occurrence_sync,
            occurrence_id=occurrence_id,
            organization_id=organization_id,
        )
    )


async def list_occurrences(
    db: AsyncSession,
    organization_id: int,
    *,
    class_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    skip: int = 0,
    limit: int = 100,
    status_filter: str | None = None,
    as_page: bool = False,
):
    return await db.run_sync(
        partial(
            list_occurrences_sync,
            organization_id=organization_id,
            class_id=class_id,
            date_from=date_from,
            date_to=date_to,
            skip=skip,
            limit=limit,
            status_filter=status_filter,
            as_page=as_page,
        )
    )


async def create_occurrence_from_active_block(
    db: AsyncSession,
    organization_id: int,
    active_schedule_block_id: int,
    *,
    created_by_membership_id: int | None = None,
    creation_source: str = "lesson_log",
    reason: str = OCCURRENCE_REPORTED,
) -> tuple[models.LessonOccurrence, bool]:
    return await db.run_sync(
        partial(
            create_occurrence_from_active_block_sync,
            organization_id=organization_id,
            active_schedule_block_id=active_schedule_block_id,
            created_by_membership_id=created_by_membership_id,
            creation_source=creation_source,
            reason=reason,
        )
    )


async def get_debts(
    db: AsyncSession, organization_id: int, class_id: int | None = None
) -> schemas.DebtListRead:
    return await db.run_sync(
        partial(
            get_debts_sync,
            organization_id=organization_id,
            class_id=class_id,
        )
    )


async def get_occurrence_observability_summary(
    db: AsyncSession, *, organization_id: int, window_days: int
) -> dict:
    return await db.run_sync(
        partial(
            get_occurrence_observability_summary_sync,
            organization_id=organization_id,
            window_days=window_days,
        )
    )


async def get_available_substitutes(
    db: AsyncSession, organization_id: int, timeslot_id: int, target_date: date
) -> list[schemas.AvailableSubstituteRead]:
    return await db.run_sync(
        partial(
            get_available_substitutes_sync,
            organization_id=organization_id,
            timeslot_id=timeslot_id,
            target_date=target_date,
        )
    )


async def get_substitute_recommendations(
    db: AsyncSession, *, organization_id: int, occurrence_id: int
) -> list[schemas.SubstituteRecommendationRead]:
    return await db.run_sync(
        partial(
            get_substitute_recommendations_sync,
            organization_id=organization_id,
            occurrence_id=occurrence_id,
        )
    )


async def update_occurrence(
    db: AsyncSession,
    occurrence_id: int,
    organization_id: int,
    payload: schemas.LessonOccurrenceUpdate,
    *,
    decided_by_membership_id: int | None = None,
) -> models.LessonOccurrence:
    return await db.run_sync(
        partial(
            update_occurrence_sync,
            occurrence_id=occurrence_id,
            organization_id=organization_id,
            payload=payload,
            decided_by_membership_id=decided_by_membership_id,
        )
    )


async def cancel_occurrence(
    db: AsyncSession,
    *,
    organization_id: int,
    occurrence_id: int,
    cancelled_by_membership_id: int | None,
    version: int,
    reason: str = ADMINISTRATIVE_REVERSAL,
    cancel_completed_substitute_log: bool = False,
) -> models.LessonOccurrence:
    return await db.run_sync(
        partial(
            cancel_occurrence_sync,
            organization_id=organization_id,
            occurrence_id=occurrence_id,
            cancelled_by_membership_id=cancelled_by_membership_id,
            version=version,
            reason=reason,
            cancel_completed_substitute_log=cancel_completed_substitute_log,
        )
    )


async def log_occurrence_event_safe(
    db: AsyncSession,
    *,
    organization_id: int,
    event_type: str,
    result: str,
    actor_membership_id: int | None = None,
    occurrence_id: int | None = None,
    active_schedule_block_id: int | None = None,
    decision_status: models.LessonOccurrenceStatus | None = None,
    detail: str | None = None,
) -> None:
    await db.run_sync(
        partial(
            log_occurrence_event_safe_sync,
            organization_id=organization_id,
            event_type=event_type,
            result=result,
            actor_membership_id=actor_membership_id,
            occurrence_id=occurrence_id,
            active_schedule_block_id=active_schedule_block_id,
            decision_status=decision_status,
            detail=detail,
        )
    )
