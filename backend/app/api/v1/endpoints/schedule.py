from datetime import date, timedelta
from statistics import mean, pstdev
from time import perf_counter
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import desc, func, select as sa_select
from celery.result import AsyncResult
from typing import Annotated, List
import json
import redis
import structlog
from app import schemas, models
from app.api import deps
from app.services import schedule_service, settings_service, teacher_observability_service
from app.services.preflight_service import (
    _preflight_check,
    _resolve_preflight_hard_end_date,
)
from app.services.scheduler_generation_service import (
    GenerationConfigurationError,
    GenerationSelectionError,
    SchedulerGenerationService,
)
from app.services.scheduler_state_service import SchedulerStateError
from app.services.scheduler_job_service import (
    SchedulerJobError,
    SchedulerJobNotFoundError,
    SchedulerJobService,
)
from app.scheduler_worker import run_schedule_generation_job_task
from app.config import settings
from app.core.ratelimit import limiter
from app.core.task_keys import (
    resolve_solver_engine_version as _resolve_solver_engine_version,
    task_cancel_key as _task_cancel_key,
    active_task_by_org_key as _active_task_by_org_key,
)

router = APIRouter()
logger = structlog.get_logger(__name__)
ERR_DRAFT_NOT_FOUND = "Rascunho não encontrado"
ERR_TEACHER_PROFILE_REQUIRED = "Professor sem perfil associado"
ERR_TEACHER_OWN_SCHEDULE_ONLY = "Professor só pode consultar o próprio horário"
ERR_TEACHER_HORIZON_NOT_FOUND = "Não existe horizonte semanal configurado para a organização"
ERR_SCHEDULE_RESET_FORBIDDEN = "Sem permissões para apagar os dados de horário"
TASK_KEY_TTL_SECONDS = 60 * 60 * 24
TASK_ORG_KEY_PREFIX = "schedule_task_org:"


def _task_org_key(task_id: str) -> str:
    return f"{TASK_ORG_KEY_PREFIX}{task_id}"


def _get_redis_client() -> redis.Redis:
    if not hasattr(_get_redis_client, "_client"):
        _get_redis_client._client = redis.Redis.from_url(
            str(settings.REDIS_URL), decode_responses=True, socket_connect_timeout=2
        )
    return _get_redis_client._client


def _extract_request_id(request: Request) -> str | None:
    return (
        request.headers.get("x-request-id")
        or request.headers.get("x-correlation-id")
    )


def _log_schedule_reset_audit(
    request: Request,
    *,
    organization_id: int | None,
    user_id: int | None,
    role: str | None,
    status_code: int,
    detail: str,
) -> None:
    logger.info(
        "schedule_reset_audit",
        organization_id=organization_id,
        actor_user_id=user_id,
        actor_role=role,
        method=request.method,
        path=str(request.url.path),
        request_id=_extract_request_id(request),
        http_status=status_code,
        detail=detail,
    )


async def _require_admin_for_schedule_reset(
    request: Request,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_user)],
) -> models.User:
    """Aplica gate admin-only com trilho de auditoria para tentativas negadas."""
    try:
        active_user = await deps.get_current_active_user(db, current_user)
        return deps.get_current_active_admin(active_user)
    except HTTPException as exc:
        detail = str(exc.detail)
        if exc.status_code == 403:
            detail = ERR_SCHEDULE_RESET_FORBIDDEN
        _log_schedule_reset_audit(
            request,
            organization_id=getattr(current_user, "organization_id", None),
            user_id=getattr(current_user, "id", None),
            role=getattr(getattr(current_user, "role", None), "value", getattr(current_user, "role", None)),
            status_code=exc.status_code,
            detail=detail,
        )
        raise HTTPException(status_code=exc.status_code, detail=detail)


def _validate_task_ownership(task_id: str, organization_id: int) -> redis.Redis:
    try:
        r = _get_redis_client()
        org_value = r.get(_task_org_key(task_id))
        if not org_value:
            raise HTTPException(status_code=404, detail="Task não encontrada")
        if org_value != str(organization_id):
            raise HTTPException(status_code=403, detail="Sem permissões para esta task")
        return r
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="Validação de task indisponível")

# --- CONSTRAINTS (Regras) ---
@router.post("/constraints/", response_model=schemas.ConstraintRead)
async def create_constraint(
    item: schemas.ConstraintCreate, 
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_user)]
):
    # Garante que usamos o organization_id do utilizador logado
    return await schedule_service.create_constraint(
        db, item, current_user.organization_id,
        changed_by_user_id=current_user.id,
    )

@router.get("/constraints/", response_model=List[schemas.ConstraintRead])
async def read_constraints(
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_user)]
):
    return await schedule_service.get_constraints_by_org(db, current_user.organization_id)

@router.delete("/constraints/{constraint_id}", responses={404: {"description": "Regra não encontrada"}})
async def delete_constraint(
    constraint_id: int, 
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_user)]
):
    success = await schedule_service.delete_constraint(
        db, constraint_id, current_user.organization_id,
        changed_by_user_id=current_user.id,
    )
    if not success:
        raise HTTPException(status_code=404, detail="Regra não encontrada")
    return {"ok": True}


# --- GERAÇÃO (Celery) — preflight movido para app.services.preflight_service ---


@router.post(
    "/generate",
    response_model=schemas.SchedulerGenerateResponse,
    responses={
        400: {"description": "Preflight falhou — dados insuficientes para gerar horário"},
    },
)
async def start_generation_request(
    request: Request,
    payload: schemas.ScheduleGenerateRequest,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
):
    """Valida pré-condições e inicia a geração de horário em background."""
    organization_id = current_user.organization_id

    try:
        selection = await SchedulerGenerationService(db).select_strategy(
            organization_id,
            replace_pending_draft=payload.replace_pending_draft,
        )
    except GenerationConfigurationError as exc:
        preflight_errors, preflight_summary = await _preflight_check(
            db,
            organization_id,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "error": "preflight_failed",
                "problems": preflight_errors or [str(exc)],
                "preflight": jsonable_encoder(preflight_summary),
            },
        ) from exc
    except GenerationSelectionError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": exc.code,
                "message": str(exc),
                "pending_draft_id": exc.pending_draft_id,
            },
        ) from exc
    except SchedulerStateError as exc:
        raise HTTPException(
            status_code=409,
            detail={"error": "scheduler_state_invalid", "message": str(exc)},
        ) from exc

    preflight_errors, preflight_summary = await _preflight_check(
        db,
        organization_id,
        selection.strategy,
        replace_pending_draft=payload.replace_pending_draft,
    )
    encoded_preflight = jsonable_encoder(preflight_summary)
    if preflight_errors:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "preflight_failed",
                "problems": preflight_errors,
                "preflight": encoded_preflight,
            },
        )

    jobs = SchedulerJobService(db)
    try:
        handle = await jobs.create_or_get_job(
            selection,
            requested_by_user_id=current_user.id,
            idempotency_key=payload.idempotency_key,
        )
        await db.commit()
    except SchedulerJobError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"error": exc.code, "message": str(exc)},
        ) from exc

    task_id = jobs.worker_task_id(handle.job.id)
    if handle.created:
        try:
            run_schedule_generation_job_task.apply_async(
                args=[handle.job.id],
                task_id=task_id,
            )
        except Exception as dispatch_error:
            await jobs.mark_dispatch_failed(
                organization_id,
                handle.job.id,
                f"Could not dispatch generation job: {dispatch_error}",
            )
            await db.commit()
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "generation_dispatch_failed",
                    "message": "Generation could not be queued.",
                    "job_id": handle.job.id,
                },
            ) from dispatch_error
    try:
        r = _get_redis_client()
        r.setex(_task_org_key(task_id), TASK_KEY_TTL_SECONDS, str(organization_id))
        r.setex(_active_task_by_org_key(organization_id), TASK_KEY_TTL_SECONDS, task_id)
    except Exception as redis_err:
        logger.warning(
            "Redis indisponível ao registar task",
            task_id=task_id,
            error=str(redis_err),
        )
    return {
        "job_id": handle.job.id,
        "strategy": selection.strategy.value,
        "trigger_type": selection.trigger_type.value,
        "status": handle.job.job_status.value,
    }

@router.get("/status/{task_id}", responses={404: {"description": "Task não encontrada"}, 403: {"description": "Sem permissões para esta task"}, 503: {"description": "Validação de task indisponível"}})
@limiter.limit("60/minute")
async def get_status(
    request: Request,
    task_id: str,
    current_user: Annotated[models.User, Depends(deps.get_current_user)]
):
    """Verifica o progresso da geração."""
    r = _validate_task_ownership(task_id, current_user.organization_id)

    task_result = AsyncResult(task_id)
    task_payload = task_result.result if isinstance(task_result.result, dict) else {}
    progress = task_payload.get("progress") if isinstance(task_payload, dict) else None
    cancel_requested = bool(r.get(_task_cancel_key(task_id)))
    solver_version = _resolve_solver_engine_version()
    if isinstance(task_payload, dict):
        solver_version = task_payload.get("solver_version", solver_version)

    if task_result.status in {"SUCCESS", "FAILURE", "REVOKED"}:
        active_key = _active_task_by_org_key(current_user.organization_id)
        active_task_value = r.get(active_key)
        if active_task_value and active_task_value == task_id:
            r.delete(active_key)
        r.delete(_task_cancel_key(task_id))

    detail = task_payload.get("detail") if isinstance(task_payload, dict) else None
    if task_result.status == "REVOKED" and not detail:
        detail = "Geração cancelada pelo utilizador."

    response = {
        "task_id": task_id,
        "status": task_result.status,
        "result": task_result.result,
        "detail": detail,
        "phase": task_payload.get("phase") if isinstance(task_payload, dict) else None,
        "progress": progress,
        "cancel_requested": cancel_requested,
        "solver_version": solver_version,
    }
    return response


@router.post(
    "/cancel/{task_id}",
    responses={
        404: {"description": "Task não encontrada"},
        403: {"description": "Sem permissões para esta task"},
        503: {"description": "Validação de task indisponível"},
    },
    summary="Solicitar cancelamento da geração de horário",
)
@limiter.limit("20/minute")
async def cancel_generation(
    request: Request,
    task_id: str,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
):
    """Cancela uma geração em curso sem deixar resultados parciais persistidos."""
    if task_id.startswith("scheduler-job-"):
        try:
            job_id = int(task_id.removeprefix("scheduler-job-"))
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Task não encontrada") from exc
        try:
            job = await SchedulerJobService(db).request_cancellation(
                current_user.organization_id,
                job_id,
            )
            await db.commit()
        except SchedulerJobNotFoundError as exc:
            await db.rollback()
            raise HTTPException(status_code=404, detail="Task não encontrada") from exc
        if job.job_status != models.ScheduleGenerationJobStatus.CANCEL_REQUESTED:
            return {
                "task_id": task_id,
                "job_id": job.id,
                "status": "Already finished",
                "current_status": job.job_status.value,
            }
        try:
            _get_redis_client().setex(
                _task_cancel_key(task_id),
                TASK_KEY_TTL_SECONDS,
                "1",
            )
        except Exception:
            pass
        return {
            "task_id": task_id,
            "job_id": job.id,
            "status": "Cancel requested",
        }

    r = _validate_task_ownership(task_id, current_user.organization_id)

    task_result = AsyncResult(task_id)
    if task_result.status in {"SUCCESS", "FAILURE", "REVOKED"}:
        return {
            "task_id": task_id,
            "status": "Already finished",
            "current_status": task_result.status,
        }

    r.setex(_task_cancel_key(task_id), TASK_KEY_TTL_SECONDS, "1")
    try:
        # terminate=True interrompe rapidamente fases longas (ex.: CP-SAT).
        task_result.revoke(terminate=True, signal="SIGTERM")
    except Exception:
        # Se o revoke falhar, a task ainda será cancelada por flag cooperativa.
        pass

    return {
        "task_id": task_id,
        "status": "Cancel requested",
    }

# --- RESULTADOS ---
@router.get("/latest", response_model=List[schemas.ScheduleOutputRead])
async def get_schedule(
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_user)]
):
    """
    Retorna o horário mais recente.
    Usa padrão 'Write-Through Cache' com Redis:
    1. Tenta ler do Redis.
    2. Se falhar, lê da BD e grava no Redis.
    """
    # Definimos a chave única para esta organização
    CACHE_KEY = f"schedule_latest_data_{current_user.organization_id}"

    try:
        r = _get_redis_client()
        cached_data = r.get(CACHE_KEY)

        if cached_data:
            logger.debug("Cache HIT", cache_key=CACHE_KEY)
            return json.loads(cached_data)
    except Exception as e:
        logger.warning("Erro ao ler cache Redis", error=str(e), cache_key=CACHE_KEY)

    logger.debug("Cache MISS", cache_key=CACHE_KEY)

    latest_schedule = await schedule_service.get_latest_schedule_by_org(db, current_user.organization_id)

    if latest_schedule:
        try:
            json_data = jsonable_encoder(latest_schedule)
            r.set(CACHE_KEY, json.dumps(json_data), ex=60)
        except Exception as e:
            logger.warning("Erro ao gravar cache Redis", error=str(e))

    return latest_schedule

@router.delete(
    "/reset",
    responses={
        200: {"description": "Dados de horário apagados com sucesso"},
        401: {"description": "Credenciais inválidas"},
        403: {"description": ERR_SCHEDULE_RESET_FORBIDDEN},
    },
    summary="Apagar dados operacionais de horário (admin-only)",
)
async def reset_all_data(
    request: Request,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(_require_admin_for_schedule_reset)],
):
    status_code = 200
    detail = "Dados de horário apagados com sucesso."

    try:
        await schedule_service.delete_all_schedule_data(db, current_user.organization_id)

        # Se apagamos os dados, também devemos limpar a cache.
        try:
            r = redis.Redis.from_url(str(settings.REDIS_URL))
            cache_key = f"schedule_latest_data_{current_user.organization_id}"
            r.delete(cache_key)
        except Exception as cache_exc:
            detail = f"Dados apagados, mas falhou a invalidação de cache: {cache_exc}"

        return {"msg": "Dados de horário apagados com sucesso."}
    except Exception as exc:
        status_code = 500
        detail = f"Falha ao apagar dados de horário: {exc}"
        raise
    finally:
        _log_schedule_reset_audit(
            request,
            organization_id=current_user.organization_id,
            user_id=current_user.id,
            role=getattr(current_user.role, "value", str(current_user.role)),
            status_code=status_code,
            detail=detail,
        )


# ==========================================
#  RASCUNHOS — Sprint 3
# ==========================================

@router.get(
    "/drafts",
    response_model=list[schemas.ScheduleDraftRead],
    summary="Listar rascunhos pendentes de aprovação",
)
async def list_drafts(
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
):
    """Retorna todos os rascunhos pendentes de aprovação."""

    def _run(sync_db):
        from app.services import schedule_service as svc
        return svc.list_draft_gen_ids_sync(sync_db, current_user.organization_id)

    rows = await db.run_sync(_run)
    return [
        schemas.ScheduleDraftRead(
            generation_id=r["generation_id"],
            count=r["count"],
            earliest_date=r["earliest_date"],
            latest_date=r["latest_date"],
        )
        for r in rows
    ]


@router.get(
    "/drafts/{gen_id}/diff",
    response_model=schemas.ScheduleDiffRead,
    responses={404: {"description": ERR_DRAFT_NOT_FOUND}},
    summary="Diff entre rascunho e horário ativo",
)
async def get_draft_diff(
    gen_id: str,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
):
    """Calcula quantos blocos foram adicionados, removidos e mantidos."""

    def _run(sync_db):
        from app.services import schedule_service as svc
        from app.services import solver_v2_diff_service as diff_svc
        drafts = svc.list_draft_gen_ids_sync(sync_db, current_user.organization_id)
        if not any(d["generation_id"] == gen_id for d in drafts):
            return None
        base_diff = svc.get_diff_sync(sync_db, current_user.organization_id, gen_id)
        stats = diff_svc.get_diff_summary_sync(sync_db, current_user.organization_id, gen_id)
        base_diff["statistics"] = stats
        return base_diff

    result = await db.run_sync(_run)
    if result is None:
        raise HTTPException(status_code=404, detail=ERR_DRAFT_NOT_FOUND)
    return schemas.ScheduleDiffRead(generation_id=gen_id, **result)


@router.post(
    "/drafts/{gen_id}/approve",
    responses={
        404: {"description": ERR_DRAFT_NOT_FOUND},
        200: {"description": "Rascunho aprovado e ativado"},
    },
    summary="Aprovar e ativar rascunho de horário",
)
async def approve_draft(
    gen_id: str,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
):
    """Promove o rascunho a horário ativo. Elimina o horário ativo anterior."""

    def _run(sync_db):
        from app.services import schedule_service as svc
        drafts = svc.list_draft_gen_ids_sync(sync_db, current_user.organization_id)
        if not any(d["generation_id"] == gen_id for d in drafts):
            return None
        count = svc.approve_draft_sync(sync_db, current_user.organization_id, gen_id)
        return count

    count = await db.run_sync(_run)
    if count is None:
        raise HTTPException(status_code=404, detail=ERR_DRAFT_NOT_FOUND)

    # Invalidar cache após aprovação
    try:
        r = redis.Redis.from_url(str(settings.REDIS_URL))
        r.delete(f"schedule_latest_data_{current_user.organization_id}")
    except Exception:
        pass

    return {"msg": "Rascunho aprovado e ativado com sucesso.", "blocks_activated": count}


@router.delete(
    "/drafts/{gen_id}",
    responses={404: {"description": ERR_DRAFT_NOT_FOUND}},
    summary="Rejeitar e eliminar rascunho de horário",
)
async def reject_draft(
    gen_id: str,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
):
    """Elimina o rascunho sem alterar o horário ativo."""

    def _run(sync_db):
        from app.services import schedule_service as svc
        drafts = svc.list_draft_gen_ids_sync(sync_db, current_user.organization_id)
        if not any(d["generation_id"] == gen_id for d in drafts):
            return None
        return svc.reject_draft_sync(sync_db, current_user.organization_id, gen_id)

    count = await db.run_sync(_run)
    if count is None:
        raise HTTPException(status_code=404, detail=ERR_DRAFT_NOT_FOUND)
    return {"msg": "Rascunho rejeitado e eliminado.", "blocks_deleted": count}


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
        hard_end_date = _resolve_preflight_hard_end_date(org_settings)
        if hard_end_date is None:
            continue

        start_reference = (
            org_settings.school_start_date
            or hard_end_date
        )
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
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_user)],
):
    start_ts = perf_counter()
    status_code = 200
    active_generation_id = None

    try:
        if current_user.role != models.UserRole.teacher:
            status_code = 403
            raise HTTPException(status_code=403, detail=ERR_TEACHER_OWN_SCHEDULE_ONLY)
        if current_user.teacher_id is None:
            status_code = 403
            raise HTTPException(status_code=403, detail=ERR_TEACHER_PROFILE_REQUIRED)

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
                sync_db.query(models.ScheduleOutput.generation_id)
                .filter(
                    models.ScheduleOutput.organization_id == current_user.organization_id,
                    models.ScheduleOutput.is_draft.is_(False),
                )
                .order_by(models.ScheduleOutput.id.desc())
                .first()
            )
            payload["active_generation_id"] = latest_generation_row[0] if latest_generation_row else None
            return payload

        horizon_payload = await db.run_sync(_run)
        if horizon_payload is None:
            status_code = 404
            raise HTTPException(status_code=404, detail=ERR_TEACHER_HORIZON_NOT_FOUND)

        active_generation_id = horizon_payload.get("active_generation_id")
        return horizon_payload
    except HTTPException as exc:
        status_code = exc.status_code
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
                actor_user_id=current_user.id,
                actor_role=current_user.role,
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
        429: {"description": "Limite temporário de proteção do endpoint excedido."},
    },
    summary="Horário de uma semana (turma ou professor)",
)
@limiter.limit(WEEK_SCHEDULE_RATE_LIMIT)
async def get_week_schedule(
    week_start: Annotated[date, Query(description="Data de início da semana (segunda-feira, YYYY-MM-DD)")],
    request: Request,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_user)],
    class_id: Annotated[int | None, Query(description="ID da turma")] = None,
    teacher_id: Annotated[int | None, Query(description="ID do professor")] = None,
):
    """Retorna os slots da semana indicada, enriquecidos com o estado de ocorrência para dias passados."""
    start_ts = perf_counter()
    status_code = 200
    should_log_teacher_observability = current_user.role == models.UserRole.teacher

    effective_class_id = class_id
    effective_teacher_id = teacher_id

    try:
        is_admin = bool(current_user.is_superuser or current_user.role == models.UserRole.admin)
        is_teacher = current_user.role == models.UserRole.teacher

        if not is_admin and not is_teacher:
            status_code = 403
            raise HTTPException(status_code=403, detail=ERR_TEACHER_OWN_SCHEDULE_ONLY)

        if current_user.role == models.UserRole.teacher:
            if current_user.teacher_id is None:
                status_code = 403
                raise HTTPException(status_code=403, detail=ERR_TEACHER_PROFILE_REQUIRED)
            if class_id is not None:
                status_code = 403
                raise HTTPException(status_code=403, detail=ERR_TEACHER_OWN_SCHEDULE_ONLY)
            if teacher_id is not None and teacher_id != current_user.teacher_id:
                status_code = 403
                raise HTTPException(status_code=403, detail=ERR_TEACHER_OWN_SCHEDULE_ONLY)
            effective_teacher_id = current_user.teacher_id

        if effective_class_id is None and effective_teacher_id is None:
            status_code = 400
            raise HTTPException(status_code=400, detail=WEEK_FILTER_REQUIRED_MSG)

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
    except HTTPException as exc:
        status_code = exc.status_code
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
                    actor_user_id=current_user.id,
                    actor_role=current_user.role,
                    endpoint_key=teacher_observability_service.ENDPOINT_SCHEDULE_WEEK_TEACHER_READ,
                    http_status=status_code,
                    latency_ms=elapsed_ms,
                    active_generation_id=None,
                )

            await db.run_sync(_emit)


# ==========================================
#  AUDITORIA TÉCNICA POR GERAÇÃO
# ==========================================

GENERATION_NOT_FOUND_MSG = "Geração não encontrada para esta organização."


def _build_distribution_stats(values: list[int]) -> tuple[int, int, float, float]:
    if not values:
        return (0, 0, 0.0, 0.0)
    return (
        min(values),
        max(values),
        round(float(mean(values)), 2),
        round(float(pstdev(values)), 2),
    )


@router.get(
    "/audit/generations",
    response_model=list[schemas.AuditGenerationSummaryRead],
    summary="Listar gerações ativas para auditoria técnica",
)
async def list_generation_audit_entries(
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
):
    rows = await db.execute(
        sa_select(
            models.ScheduleOutput.generation_id,
            func.count(models.ScheduleOutput.id).label("blocks_count"),
            func.min(models.ScheduleOutput.date).label("start_date"),
            func.max(models.ScheduleOutput.date).label("end_date"),
            func.max(models.ScheduleOutput.id).label("max_id"),
        )
        .where(
            models.ScheduleOutput.organization_id == current_user.organization_id,
            models.ScheduleOutput.is_draft.is_(False),
        )
        .group_by(models.ScheduleOutput.generation_id)
        .order_by(func.max(models.ScheduleOutput.id).desc())
        .limit(50)
    )

    return [
        schemas.AuditGenerationSummaryRead(
            generation_id=row.generation_id,
            blocks_count=row.blocks_count,
            start_date=row.start_date,
            end_date=row.end_date,
        )
        for row in rows.all()
    ]


@router.get(
    "/audit/summary",
    response_model=schemas.ScheduleGenerationAuditRead,
    responses={404: {"description": GENERATION_NOT_FOUND_MSG}},
    summary="Métricas técnicas de auditoria por geração",
)
async def get_generation_audit_summary(
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
    generation_id: Annotated[str | None, Query(description="ID da geração a auditar")] = None,
):
    organization_id = current_user.organization_id

    if generation_id is None:
        latest_row = await db.execute(
            sa_select(models.ScheduleOutput.generation_id)
            .where(
                models.ScheduleOutput.organization_id == organization_id,
                models.ScheduleOutput.is_draft.is_(False),
            )
            .order_by(desc(models.ScheduleOutput.id))
            .limit(1)
        )
        generation_id = latest_row.scalar_one_or_none()

    if generation_id is None:
        raise HTTPException(status_code=404, detail=GENERATION_NOT_FOUND_MSG)

    generation_exists = await db.scalar(
        sa_select(func.count(models.ScheduleOutput.id)).where(
            models.ScheduleOutput.organization_id == organization_id,
            models.ScheduleOutput.is_draft.is_(False),
            models.ScheduleOutput.generation_id == generation_id,
        )
    )
    if not generation_exists:
        raise HTTPException(status_code=404, detail=GENERATION_NOT_FOUND_MSG)

    overview_row = await db.execute(
        sa_select(
            func.count(models.ScheduleOutput.id).label("blocks_count"),
            func.min(models.ScheduleOutput.date).label("start_date"),
            func.max(models.ScheduleOutput.date).label("end_date"),
        ).where(
            models.ScheduleOutput.organization_id == organization_id,
            models.ScheduleOutput.is_draft.is_(False),
            models.ScheduleOutput.generation_id == generation_id,
        )
    )
    overview = overview_row.one()

    week_start = date.today() - timedelta(days=date.today().weekday())
    week_end = week_start + timedelta(days=6)

    class_ids_result = await db.execute(
        sa_select(models.Class.id).where(
            models.Class.organization_id == organization_id,
            models.Class.is_archived == False,  # noqa: E712
        )
    )
    class_ids = [row[0] for row in class_ids_result.all()]
    classes_total = len(class_ids)

    class_week_rows = await db.execute(
        sa_select(models.Lesson.class_id, func.count(models.ScheduleOutput.id).label("slots_count"))
        .join(models.ScheduleOutput, models.ScheduleOutput.lesson_id == models.Lesson.id)
        .where(
            models.ScheduleOutput.organization_id == organization_id,
            models.ScheduleOutput.is_draft.is_(False),
            models.ScheduleOutput.generation_id == generation_id,
            models.ScheduleOutput.date.between(week_start, week_end),
        )
        .group_by(models.Lesson.class_id)
    )
    class_week_map = {row.class_id: row.slots_count for row in class_week_rows.all()}
    class_week_values = [class_week_map.get(class_id, 0) for class_id in class_ids] if class_ids else []
    week_slots_min, week_slots_max, week_slots_avg, week_fairness_spread = _build_distribution_stats(class_week_values)
    classes_with_week_slots = sum(1 for value in class_week_values if value > 0)
    classes_empty_week = classes_total - classes_with_week_slots

    duplicate_teacher_rows = await db.execute(
        sa_select(
            models.Lesson.teacher_id,
            models.ScheduleOutput.date,
            models.ScheduleOutput.timeslot_id,
            func.count(models.ScheduleOutput.id).label("dup_count"),
        )
        .join(models.Lesson, models.ScheduleOutput.lesson_id == models.Lesson.id)
        .where(
            models.ScheduleOutput.organization_id == organization_id,
            models.ScheduleOutput.is_draft.is_(False),
            models.ScheduleOutput.generation_id == generation_id,
        )
        .group_by(models.Lesson.teacher_id, models.ScheduleOutput.date, models.ScheduleOutput.timeslot_id)
        .having(func.count(models.ScheduleOutput.id) > 1)
    )
    duplicate_teacher_slots = len(duplicate_teacher_rows.all())

    duplicate_class_rows = await db.execute(
        sa_select(
            models.Lesson.class_id,
            models.ScheduleOutput.date,
            models.ScheduleOutput.timeslot_id,
            func.count(models.ScheduleOutput.id).label("dup_count"),
        )
        .join(models.Lesson, models.ScheduleOutput.lesson_id == models.Lesson.id)
        .where(
            models.ScheduleOutput.organization_id == organization_id,
            models.ScheduleOutput.is_draft.is_(False),
            models.ScheduleOutput.generation_id == generation_id,
        )
        .group_by(models.Lesson.class_id, models.ScheduleOutput.date, models.ScheduleOutput.timeslot_id)
        .having(func.count(models.ScheduleOutput.id) > 1)
    )
    duplicate_class_slots = len(duplicate_class_rows.all())

    teacher_week_rows = await db.execute(
        sa_select(models.Lesson.teacher_id, func.count(models.ScheduleOutput.id).label("slots_count"))
        .join(models.ScheduleOutput, models.ScheduleOutput.lesson_id == models.Lesson.id)
        .where(
            models.ScheduleOutput.organization_id == organization_id,
            models.ScheduleOutput.is_draft.is_(False),
            models.ScheduleOutput.generation_id == generation_id,
            models.ScheduleOutput.date.between(week_start, week_end),
        )
        .group_by(models.Lesson.teacher_id)
    )
    teacher_week_values = [row.slots_count for row in teacher_week_rows.all()]
    teacher_week_slots_min, teacher_week_slots_max, _, _ = _build_distribution_stats(teacher_week_values)
    teachers_with_week_slots = len(teacher_week_values)

    room_usage_rows = await db.execute(
        sa_select(models.Room.type, func.count(models.ScheduleOutput.id).label("blocks_count"))
        .join(models.ScheduleOutput, models.ScheduleOutput.room_id == models.Room.id)
        .where(
            models.ScheduleOutput.organization_id == organization_id,
            models.ScheduleOutput.is_draft.is_(False),
            models.ScheduleOutput.generation_id == generation_id,
        )
        .group_by(models.Room.type)
    )
    room_type_usage = [
        schemas.AuditRoomUsageRead(room_type=row.type.value, blocks_count=row.blocks_count)
        for row in room_usage_rows.all()
    ]

    return schemas.ScheduleGenerationAuditRead(
        generation_id=generation_id,
        blocks_count=overview.blocks_count,
        start_date=overview.start_date,
        end_date=overview.end_date,
        classes_total=classes_total,
        classes_with_week_slots=classes_with_week_slots,
        classes_empty_week=classes_empty_week,
        week_slots_min=week_slots_min,
        week_slots_max=week_slots_max,
        week_slots_avg=week_slots_avg,
        weekly_fairness_spread=week_fairness_spread,
        duplicate_teacher_slots=duplicate_teacher_slots,
        duplicate_class_slots=duplicate_class_slots,
        teachers_with_week_slots=teachers_with_week_slots,
        teacher_week_slots_min=teacher_week_slots_min,
        teacher_week_slots_max=teacher_week_slots_max,
        room_type_usage=room_type_usage,
    )


# ==========================================
#  WBS FASE 1/2 — REGISTO DE AULAS (LESSON LOG)
# ==========================================

@router.put(
    "/outputs/{schedule_output_id}/log",
    response_model=schemas.LessonLogRead,
    summary="Registar execução de aula",
)
async def upsert_lesson_log(
    schedule_output_id: int,
    payload: schemas.LessonLogCreate,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_user)],
):
    """Atualiza o estado de execução (LessonLog) de um bloco de aula."""
    is_admin = bool(current_user.is_superuser or current_user.role == models.UserRole.admin)
    is_teacher = current_user.role == models.UserRole.teacher

    if not is_admin and not is_teacher:
        raise HTTPException(status_code=403, detail="Acesso negado.")
        
    def _run(sync_db):
        from app.services import lesson_log_service
        
        # 1. Verificar permissões sobre o bloco se for professor
        output = sync_db.get(models.ScheduleOutput, schedule_output_id)
        if not output:
            raise HTTPException(status_code=404, detail="Bloco planeado não encontrado.")
            
        if is_teacher and output.lesson.teacher_id != current_user.teacher_id:
            raise HTTPException(status_code=403, detail="Não pode alterar registos de outros professores.")
            
        # 2. Executar o upsert e a contabilidade do progresso
        return lesson_log_service.upsert_lesson_log_sync(
            sync_db,
            organization_id=current_user.organization_id,
            user_id=current_user.id,
            schedule_output_id=schedule_output_id,
            payload=payload
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
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_user)],
):
    is_admin = bool(current_user.is_superuser or current_user.role == models.UserRole.admin)
    is_teacher = current_user.role == models.UserRole.teacher

    if not is_admin and not is_teacher:
        raise HTTPException(status_code=403, detail="Acesso negado.")

    def _run(sync_db):
        from app.services import lesson_log_service

        block = sync_db.get(models.OperationalScheduleBlock, operational_block_id)
        if not block or block.organization_id != current_user.organization_id:
            raise HTTPException(status_code=404, detail="Bloco operacional nao encontrado.")
        if is_teacher and block.teacher_id != current_user.teacher_id:
            raise HTTPException(status_code=403, detail="Nao pode alterar registos de outros professores.")

        return lesson_log_service.upsert_operational_lesson_log_sync(
            sync_db,
            organization_id=current_user.organization_id,
            user_id=current_user.id,
            operational_block_id=operational_block_id,
            payload=payload,
        )

    return await db.run_sync(_run)
