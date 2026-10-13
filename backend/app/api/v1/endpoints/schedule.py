from datetime import UTC, date, datetime, timedelta
from typing import Annotated

import structlog
from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from app import models, schemas
from app.api import deps
from app.core.exceptions import AppError
from app.core.ratelimit import limiter
from app.scheduler.infrastructure import operations
from app.scheduler.infrastructure.models import SchedulerVersionV1
from app.services import lesson_log_service, schedule_service

router = APIRouter()
logger = structlog.get_logger(__name__)
ERR_TEACHER_PROFILE_REQUIRED = "Professor sem perfil associado"
ERR_TEACHER_OWN_SCHEDULE_ONLY = "Professor só pode consultar o próprio horário"
ERR_TEACHER_HORIZON_NOT_FOUND = "Não existe horizonte semanal configurado para a organização"


def _raise_schedule_error(status_code: int, code: str, detail: str) -> None:
    kind = {
        400: "bad_request",
        403: "forbidden",
        404: "not_found",
        422: "validation",
    }.get(status_code, "bad_request")
    raise AppError(kind=kind, code=code, detail=detail)


# --- CONSTRAINTS (Regras) ---
@router.post("/constraints/", response_model=schemas.ConstraintRead)
async def create_constraint(
    item: schemas.ConstraintCreate,
    db: deps.DbSession,
    current_user: deps.AdminActor,
):
    # Garante que usamos o organization_id do utilizador logado
    try:
        return await schedule_service.create_constraint(
            db,
            item,
            current_user.organization_id,
            changed_by_membership_id=current_user.membership_id,
        )
    except schedule_service.ConstraintSemanticValidationError as exc:
        raise AppError(kind="validation", code="constraint_invalid", detail=str(exc)) from exc


# ==========================================
#  SPRINT 4 — VISUALIZAÇÃO SEMANAL
# ==========================================

WEEK_FILTER_REQUIRED_MSG = "Indique class_id ou teacher_id para filtrar o horário."
WEEK_SCHEDULE_RATE_LIMIT = "60/minute;600/hour"


def _to_week_monday(target_date: date) -> date:
    return target_date - timedelta(days=target_date.weekday())


def _resolve_teacher_horizon_payload(
    settings_rows: list[models.OrganizationSettings],
) -> dict[str, date] | None:
    if not settings_rows:
        return None

    today = date.today()
    today_monday = _to_week_monday(today)
    candidates: list[tuple[date, date]] = []

    for org_settings in settings_rows:
        hard_end_date = org_settings.school_hard_end_date
        if hard_end_date is None:
            continue

        start_reference = org_settings.school_start_date or hard_end_date
        if start_reference > hard_end_date:
            continue

        candidates.append((start_reference, hard_end_date))

    if not candidates:
        return None

    selected_start_reference: date | None = None
    selected_hard_end_date: date | None = None

    for start_reference, hard_end_date in candidates:
        if start_reference <= today <= hard_end_date:
            selected_start_reference = start_reference
            selected_hard_end_date = hard_end_date
            break

    if selected_start_reference is None or selected_hard_end_date is None:
        future_candidates = [item for item in candidates if today < item[0]]
        if future_candidates:
            selected_start_reference, selected_hard_end_date = min(
                future_candidates,
                key=lambda item: item[0],
            )

    if selected_start_reference is None or selected_hard_end_date is None:
        selected_start_reference, selected_hard_end_date = max(
            candidates,
            key=lambda item: item[1],
        )

    min_week_start = _to_week_monday(selected_start_reference)
    max_week_start = _to_week_monday(selected_hard_end_date)
    recommended_week_start = today_monday

    if recommended_week_start < min_week_start:
        recommended_week_start = min_week_start
    if recommended_week_start > max_week_start:
        recommended_week_start = max_week_start

    return {
        "min_week_start": min_week_start,
        "week_start_recommended": recommended_week_start,
        "hard_end_date": selected_hard_end_date,
    }


@router.get(
    "/me/horizon",
    response_model=schemas.TeacherScheduleHorizonRead,
    responses={
        403: {"description": ERR_TEACHER_OWN_SCHEDULE_ONLY},
        404: {"description": ERR_TEACHER_HORIZON_NOT_FOUND},
    },
    summary="Metadados de horizonte semanal para o professor autenticado",
)
@limiter.limit("300/hour")
async def get_teacher_schedule_horizon(
    request: Request,
    db: deps.DbSession,
    current_user: deps.ActiveActor,
):
    if not deps.user_has_teacher_capability(current_user):
        _raise_schedule_error(403, "teacher_schedule_forbidden", ERR_TEACHER_OWN_SCHEDULE_ONLY)
    if current_user.teacher_id is None:
        _raise_schedule_error(403, "teacher_profile_required", ERR_TEACHER_PROFILE_REQUIRED)

    def _run(sync_db):
        settings_rows = (
            sync_db.query(models.OrganizationSettings)
            .filter(models.OrganizationSettings.organization_id == current_user.organization_id)
            .order_by(models.OrganizationSettings.id.desc())
            .all()
        )
        payload = _resolve_teacher_horizon_payload(settings_rows)
        if payload is None:
            return None

        v1_version_id = sync_db.execute(
            select(SchedulerVersionV1.id).where(
                SchedulerVersionV1.organization_id == current_user.organization_id,
                SchedulerVersionV1.status == "ACTIVE",
            )
        ).scalar()
        if v1_version_id is not None:
            payload["active_generation_id"] = f"v1-{v1_version_id}"
            return payload
        latest_generation_row = (
            sync_db.query(models.ActiveScheduleBlock.schedule_version_id)
            .filter(
                models.ActiveScheduleBlock.organization_id == current_user.organization_id,
                models.ActiveScheduleBlock.status == models.ActiveScheduleBlockStatus.ACTIVE,
            )
            .order_by(models.ActiveScheduleBlock.id.desc())
            .first()
        )
        payload["active_generation_id"] = (
            latest_generation_row[0] if latest_generation_row else None
        )
        return payload

    horizon_payload = await db.run_sync(_run)
    if horizon_payload is None:
        _raise_schedule_error(404, "teacher_horizon_not_found", ERR_TEACHER_HORIZON_NOT_FOUND)

    return horizon_payload


@router.get(
    "/week",
    response_model=list[schemas.WeekSlotRead],
    responses={
        400: {"description": WEEK_FILTER_REQUIRED_MSG},
        403: {"description": ERR_TEACHER_OWN_SCHEDULE_ONLY},
        429: {"description": "Limite temporário de proteção do endpoint excedido."},
    },
    summary="Horário de uma semana (turma ou professor)",
)
@limiter.limit(WEEK_SCHEDULE_RATE_LIMIT)
async def get_week_schedule(
    week_start: Annotated[
        date, Query(description="Data de início da semana (segunda-feira, YYYY-MM-DD)")
    ],
    request: Request,
    db: deps.DbSession,
    current_user: deps.ActiveActor,
    class_id: Annotated[int | None, Query(description="ID da turma")] = None,
    teacher_id: Annotated[int | None, Query(description="ID do professor")] = None,
):
    """Retorna os slots da semana indicada, enriquecidos com o estado de ocorrência para dias passados."""
    effective_class_id = class_id
    effective_teacher_id = teacher_id
    is_admin = deps.user_has_admin_capability(current_user)
    is_teacher = deps.user_has_teacher_capability(current_user)

    if not is_admin and not is_teacher:
        _raise_schedule_error(403, "teacher_schedule_forbidden", ERR_TEACHER_OWN_SCHEDULE_ONLY)

    if is_teacher and not is_admin:
        if current_user.teacher_id is None:
            _raise_schedule_error(403, "teacher_profile_required", ERR_TEACHER_PROFILE_REQUIRED)
        if class_id is not None:
            _raise_schedule_error(403, "teacher_schedule_forbidden", ERR_TEACHER_OWN_SCHEDULE_ONLY)
        if teacher_id is not None and teacher_id != current_user.teacher_id:
            _raise_schedule_error(403, "teacher_schedule_forbidden", ERR_TEACHER_OWN_SCHEDULE_ONLY)
        effective_teacher_id = current_user.teacher_id

    if effective_class_id is None and effective_teacher_id is None:
        _raise_schedule_error(400, "week_filter_required", WEEK_FILTER_REQUIRED_MSG)

    v1_slots = await operations.week_schedule(
        db,
        current_user.organization_id,
        week_start=week_start,
        class_id=effective_class_id,
        teacher_id=effective_teacher_id,
    )
    if v1_slots is not None:
        return v1_slots

    def _run(sync_db):
        return schedule_service.get_week_schedule_sync(
            sync_db,
            organization_id=current_user.organization_id,
            week_start=week_start,
            class_id=effective_class_id,
            teacher_id=effective_teacher_id,
        )

    return await db.run_sync(_run)


# ==========================================
#  WBS FASE 1/2 — REGISTO DE AULAS (LESSON LOG)
# ==========================================

LESSON_LOG_ACCESS_DENIED = "Acesso negado."
LESSON_LOG_OTHER_TEACHER_DENIED = "Nao pode alterar registos de outros professores."


def _require_lesson_log_actor(current_user: deps.Actor) -> bool:
    """Return whether the actor is an admin, rejecting unsupported capabilities."""
    is_admin = deps.user_has_admin_capability(current_user)
    if not is_admin and not deps.user_has_teacher_capability(current_user):
        _raise_schedule_error(403, "lesson_log_access_denied", LESSON_LOG_ACCESS_DENIED)
    return is_admin


def _authorize_lesson_log_teacher(
    current_user: deps.Actor,
    *,
    block_teacher_id: int,
    is_admin: bool,
) -> None:
    """Restrict teacher-only actors to blocks assigned to their teacher profile."""
    if not is_admin and block_teacher_id != current_user.teacher_id:
        _raise_schedule_error(403, "lesson_log_teacher_mismatch", LESSON_LOG_OTHER_TEACHER_DENIED)


@router.put(
    "/active-blocks/{active_schedule_block_id}/log",
    response_model=schemas.LessonLogRead,
    summary="Registar execucao de bloco do horario ativo",
)
async def upsert_active_lesson_log(
    active_schedule_block_id: int,
    payload: schemas.LessonLogCreate,
    db: deps.DbSession,
    current_user: deps.ActiveActor,
):
    is_admin = _require_lesson_log_actor(current_user)

    def _run(sync_db):
        block = (
            sync_db.query(models.ActiveScheduleBlock)
            .filter(
                models.ActiveScheduleBlock.id == active_schedule_block_id,
                models.ActiveScheduleBlock.organization_id == current_user.organization_id,
                models.ActiveScheduleBlock.status == models.ActiveScheduleBlockStatus.ACTIVE,
            )
            .first()
        )
        if block is None:
            _raise_schedule_error(
                404, "active_schedule_block_not_found", "Bloco do horario ativo nao encontrado."
            )

        _authorize_lesson_log_teacher(
            current_user,
            block_teacher_id=block.teacher_id,
            is_admin=is_admin,
        )

        return lesson_log_service.upsert_active_lesson_log_sync(
            sync_db,
            organization_id=current_user.organization_id,
            membership_id=current_user.membership_id,
            active_schedule_block_id=active_schedule_block_id,
            payload=payload,
        )

    return await db.run_sync(_run)


@router.put(
    "/operational-blocks/{operational_block_id}/log",
    response_model=schemas.LessonLogRead,
    summary="Registar execucao de bloco operacional",
)
async def upsert_operational_lesson_log(
    operational_block_id: int,
    payload: schemas.LessonLogCreate,
    db: deps.DbSession,
    current_user: deps.ActiveActor,
):
    is_admin = _require_lesson_log_actor(current_user)

    block = await db.scalar(
        select(models.OperationalScheduleBlock).where(
            models.OperationalScheduleBlock.id == operational_block_id,
            models.OperationalScheduleBlock.organization_id == current_user.organization_id,
            models.OperationalScheduleBlock.status == models.OperationalBlockStatus.ACTIVE,
        )
    )
    if block is None:
        _raise_schedule_error(
            404, "operational_schedule_block_not_found", "Bloco operacional nao encontrado."
        )

    _authorize_lesson_log_teacher(
        current_user,
        block_teacher_id=block.teacher_id,
        is_admin=is_admin,
    )

    if block.origin_kind == models.OperationalBlockOrigin.V1:
        try:
            return await operations.record_operational_lesson_log(
                db,
                current_user.organization_id,
                membership_id=current_user.membership_id,
                operational_block_id=operational_block_id,
                payload=payload,
                now_utc=datetime.now(UTC),
            )
        except operations.OperationsError as exc:
            _raise_operations_error(exc)

    def _run(sync_db):
        return lesson_log_service.upsert_operational_lesson_log_sync(
            sync_db,
            organization_id=current_user.organization_id,
            membership_id=current_user.membership_id,
            operational_block_id=operational_block_id,
            payload=payload,
        )

    return await db.run_sync(_run)


@router.put(
    "/lessons/{lesson_id}/log",
    response_model=schemas.SchedulerV1LessonLogResponse,
    summary="Registar execucao ou ocorrencia de uma aula do horario v1",
)
async def upsert_scheduler_v1_lesson_log(
    lesson_id: int,
    payload: schemas.SchedulerV1LessonLogRequest,
    db: deps.DbSession,
    current_user: deps.ActiveActor,
):
    is_admin = _require_lesson_log_actor(current_user)
    try:
        context = await operations.lesson_context(db, current_user.organization_id, lesson_id)
    except operations.OperationsError as exc:
        _raise_operations_error(exc)
    _authorize_lesson_log_teacher(
        current_user,
        block_teacher_id=context.assignment.teacher_id,
        is_admin=is_admin,
    )
    try:
        return await operations.record_lesson_log(
            db,
            current_user.organization_id,
            membership_id=current_user.membership_id,
            lesson_id=lesson_id,
            status=payload.status,
            summary=payload.summary,
            notes=payload.notes,
            now_utc=datetime.now(UTC),
            planning_relevant=payload.status == "OCCURRENCE",
        )
    except operations.OperationsError as exc:
        _raise_operations_error(exc)


def _raise_operations_error(exc: operations.OperationsError) -> None:
    kinds = {400: "bad_request", 403: "forbidden", 404: "not_found", 409: "conflict"}
    raise AppError(
        kind=kinds.get(exc.status_code, "validation"),
        code=exc.code,
        detail=str(exc),
    ) from exc
