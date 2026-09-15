from datetime import date, timedelta
from time import perf_counter
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.api import deps
from app.core.exceptions import AppError, status_code_for_kind
from app.core.ratelimit import limiter
from app.services import schedule_service, teacher_observability_service
from app.services.school_year_reset_service import SchoolYearResetService

router = APIRouter()
logger = structlog.get_logger(__name__)
ERR_TEACHER_PROFILE_REQUIRED = "Professor sem perfil associado"
ERR_TEACHER_OWN_SCHEDULE_ONLY = "Professor sÃ³ pode consultar o prÃ³prio horÃ¡rio"
ERR_TEACHER_HORIZON_NOT_FOUND = "NÃ£o existe horizonte semanal configurado para a organizaÃ§Ã£o"
ERR_SCHEDULE_RESET_FORBIDDEN = "Sem permissÃµes para apagar os dados de horÃ¡rio"


def _raise_schedule_error(status_code: int, code: str, detail: str) -> None:
    kind = {
        400: "bad_request",
        403: "forbidden",
        404: "not_found",
        422: "validation",
    }.get(status_code, "bad_request")
    raise AppError(kind=kind, code=code, detail=detail)


def _extract_request_id(request: Request) -> str | None:
    return request.headers.get("x-request-id") or request.headers.get("x-correlation-id")


def _log_schedule_reset_audit(
    request: Request,
    *,
    organization_id: int | None,
    membership_id: int | None,
    role: str | None,
    status_code: int,
    detail: str,
) -> None:
    logger.info(
        "schedule_reset_audit",
        organization_id=organization_id,
        actor_membership_id=membership_id,
        actor_role=role,
        method=request.method,
        path=str(request.url.path),
        request_id=_extract_request_id(request),
        http_status=status_code,
        detail=detail,
    )


async def _require_admin_for_schedule_reset(
    request: Request,
    current_user: Annotated[deps.Actor, Depends(deps.get_current_active_user)],
) -> deps.Actor:
    """Aplica gate admin-only com trilho de auditoria para tentativas negadas."""
    try:
        return deps.get_current_active_admin(current_user)
    except HTTPException as exc:
        detail = str(exc.detail)
        if exc.status_code == 403:
            detail = ERR_SCHEDULE_RESET_FORBIDDEN
        _log_schedule_reset_audit(
            request,
            organization_id=getattr(current_user, "organization_id", None),
            membership_id=getattr(current_user, "membership_id", None),
            role=deps.actor_role(current_user),
            status_code=exc.status_code,
            detail=detail,
        )
        raise AppError(
            kind="forbidden" if exc.status_code == 403 else "unauthorized",
            code="schedule_reset_forbidden",
            detail=detail,
        ) from exc


# --- CONSTRAINTS (Regras) ---
@router.post("/constraints/", response_model=schemas.ConstraintRead)
async def create_constraint(
    item: schemas.ConstraintCreate,
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
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


@router.get("/constraints/", response_model=list[schemas.ConstraintRead])
async def read_constraints(
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.ActiveActor,
):
    return await schedule_service.get_constraints_by_org(db, current_user.organization_id)


@router.delete(
    "/constraints/{constraint_id}", responses={404: {"description": "Regra nÃ£o encontrada"}}
)
async def delete_constraint(
    constraint_id: int,
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.AdminActor,
):
    success = await schedule_service.delete_constraint(
        db,
        constraint_id,
        current_user.organization_id,
        changed_by_membership_id=current_user.membership_id,
    )
    if not success:
        _raise_schedule_error(404, "constraint_not_found", "Regra nÃ£o encontrada")
    return {"ok": True}


@router.delete(
    "/reset",
    responses={
        200: {"description": "Dados de horÃ¡rio apagados com sucesso"},
        401: {"description": "Credenciais invÃ¡lidas"},
        403: {"description": ERR_SCHEDULE_RESET_FORBIDDEN},
    },
    summary="Apagar dados operacionais de horÃ¡rio (admin-only)",
)
async def reset_all_data(
    request: Request,
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: Annotated[deps.Actor, Depends(_require_admin_for_schedule_reset)],
):
    status_code = 200
    detail = "Dados de horÃ¡rio apagados com sucesso."

    try:
        result = await SchoolYearResetService(db).reset_year(
            current_user.organization_id,
            reset_by_membership_id=current_user.membership_id,
        )
        return {
            "msg": "Dados de horÃ¡rio apagados com sucesso.",
            "deleted_rows": result.deleted_rows,
            "new_school_year_id": result.new_school_year_id,
        }
    except Exception as exc:
        status_code = 500
        detail = f"Falha ao apagar dados de horÃ¡rio: {exc}"
        raise
    finally:
        _log_schedule_reset_audit(
            request,
            organization_id=current_user.organization_id,
            membership_id=current_user.membership_id,
            role="admin" if current_user.can_admin else "teacher",
            status_code=status_code,
            detail=detail,
        )


# ==========================================
#  SPRINT 4 â€” VISUALIZAÃ‡ÃƒO SEMANAL
# ==========================================

WEEK_FILTER_REQUIRED_MSG = "Indique class_id ou teacher_id para filtrar o horÃ¡rio."
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
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.ActiveActor,
):
    start_ts = perf_counter()
    status_code = 200
    active_generation_id = None

    try:
        if not deps.user_has_teacher_capability(current_user):
            status_code = 403
            _raise_schedule_error(403, "teacher_schedule_forbidden", ERR_TEACHER_OWN_SCHEDULE_ONLY)
        if current_user.teacher_id is None:
            status_code = 403
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
            status_code = 404
            _raise_schedule_error(404, "teacher_horizon_not_found", ERR_TEACHER_HORIZON_NOT_FOUND)

        active_generation_id = horizon_payload.get("active_generation_id")
        return horizon_payload
    except AppError as exc:
        status_code = status_code_for_kind(exc.kind, exc.code)
        raise
    except Exception:
        status_code = 500
        raise
    finally:
        elapsed_ms = max(1, int((perf_counter() - start_ts) * 1000))

        def _emit(sync_db):
            teacher_observability_service.log_teacher_endpoint_event_safe_sync(
                sync_db,
                organization_id=current_user.organization_id,
                actor_membership_id=current_user.membership_id,
                actor_role=deps.actor_role(current_user),
                endpoint_key=teacher_observability_service.ENDPOINT_SCHEDULE_ME_HORIZON_READ,
                http_status=status_code,
                latency_ms=elapsed_ms,
                active_generation_id=active_generation_id,
            )

        await db.run_sync(_emit)


@router.get(
    "/week",
    response_model=list[schemas.WeekSlotRead],
    responses={
        400: {"description": WEEK_FILTER_REQUIRED_MSG},
        403: {"description": ERR_TEACHER_OWN_SCHEDULE_ONLY},
        429: {"description": "Limite temporÃ¡rio de proteÃ§Ã£o do endpoint excedido."},
    },
    summary="HorÃ¡rio de uma semana (turma ou professor)",
)
@limiter.limit(WEEK_SCHEDULE_RATE_LIMIT)
async def get_week_schedule(
    week_start: Annotated[
        date, Query(description="Data de inÃ­cio da semana (segunda-feira, YYYY-MM-DD)")
    ],
    request: Request,
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.ActiveActor,
    class_id: Annotated[int | None, Query(description="ID da turma")] = None,
    teacher_id: Annotated[int | None, Query(description="ID do professor")] = None,
):
    """Retorna os slots da semana indicada, enriquecidos com o estado de ocorrÃªncia para dias passados."""
    start_ts = perf_counter()
    status_code = 200
    should_log_teacher_observability = deps.user_has_teacher_capability(current_user)

    effective_class_id = class_id
    effective_teacher_id = teacher_id

    try:
        is_admin = deps.user_has_admin_capability(current_user)
        is_teacher = deps.user_has_teacher_capability(current_user)

        if not is_admin and not is_teacher:
            status_code = 403
            _raise_schedule_error(403, "teacher_schedule_forbidden", ERR_TEACHER_OWN_SCHEDULE_ONLY)

        if is_teacher and not is_admin:
            if current_user.teacher_id is None:
                status_code = 403
                _raise_schedule_error(403, "teacher_profile_required", ERR_TEACHER_PROFILE_REQUIRED)
            if class_id is not None:
                status_code = 403
                _raise_schedule_error(
                    403, "teacher_schedule_forbidden", ERR_TEACHER_OWN_SCHEDULE_ONLY
                )
            if teacher_id is not None and teacher_id != current_user.teacher_id:
                status_code = 403
                _raise_schedule_error(
                    403, "teacher_schedule_forbidden", ERR_TEACHER_OWN_SCHEDULE_ONLY
                )
            effective_teacher_id = current_user.teacher_id

        if effective_class_id is None and effective_teacher_id is None:
            status_code = 400
            _raise_schedule_error(400, "week_filter_required", WEEK_FILTER_REQUIRED_MSG)

        def _run(sync_db):
            from app.services import schedule_service as svc

            return svc.get_week_schedule_sync(
                sync_db,
                organization_id=current_user.organization_id,
                week_start=week_start,
                class_id=effective_class_id,
                teacher_id=effective_teacher_id,
            )

        return await db.run_sync(_run)
    except AppError as exc:
        status_code = status_code_for_kind(exc.kind, exc.code)
        raise
    except Exception:
        status_code = 500
        raise
    finally:
        if should_log_teacher_observability:
            elapsed_ms = max(1, int((perf_counter() - start_ts) * 1000))

            def _emit(sync_db):
                teacher_observability_service.log_teacher_endpoint_event_safe_sync(
                    sync_db,
                    organization_id=current_user.organization_id,
                    actor_membership_id=current_user.membership_id,
                    actor_role=deps.actor_role(current_user),
                    endpoint_key=teacher_observability_service.ENDPOINT_SCHEDULE_WEEK_TEACHER_READ,
                    http_status=status_code,
                    latency_ms=elapsed_ms,
                    active_generation_id=None,
                )

            await db.run_sync(_emit)


# ==========================================
#  AUDITORIA TÃ‰CNICA POR GERAÃ‡ÃƒO
# ==========================================

# ==========================================
#  WBS FASE 1/2 â€” REGISTO DE AULAS (LESSON LOG)
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
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.ActiveActor,
):
    is_admin = _require_lesson_log_actor(current_user)

    def _run(sync_db):
        from app.services import lesson_log_service

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
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.ActiveActor,
):
    is_admin = _require_lesson_log_actor(current_user)

    def _run(sync_db):
        from app.services import lesson_log_service

        block = (
            sync_db.query(models.OperationalScheduleBlock)
            .filter(
                models.OperationalScheduleBlock.id == operational_block_id,
                models.OperationalScheduleBlock.organization_id == current_user.organization_id,
                models.OperationalScheduleBlock.status == models.OperationalBlockStatus.ACTIVE,
            )
            .first()
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

        return lesson_log_service.upsert_operational_lesson_log_sync(
            sync_db,
            organization_id=current_user.organization_id,
            membership_id=current_user.membership_id,
            operational_block_id=operational_block_id,
            payload=payload,
        )

    return await db.run_sync(_run)
