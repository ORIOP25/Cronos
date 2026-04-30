from datetime import date, timedelta
from statistics import mean, pstdev
from time import perf_counter
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi_cache.decorator import cache
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import desc, func, select as sa_select
from celery.result import AsyncResult
from typing import List, Annotated
import json
import redis
import structlog
from app import schemas, models
from app.api import deps
from app.services import schedule_service, settings_service, teacher_observability_service
from app.solver_tasks import (
    generate_schedule_task,
    _build_blocked_dates,
    _build_primary_rolling_window,
    _compute_remaining_minutes,
    _estimate_capacity_minutes_in_range,
    _resolve_expansion_start_date,
    _resolve_solver_v2_rolling_weeks,
)
from app.config import settings
from app.core.ratelimit import limiter

router = APIRouter()
logger = structlog.get_logger(__name__)
ERR_DRAFT_NOT_FOUND = "Rascunho não encontrado"
DEFAULT_REPAIR_WINDOW_DAYS = 14
DEFAULT_HARD_END_MONTH = 7
DEFAULT_HARD_END_DAY = 31
ERR_TEACHER_PROFILE_REQUIRED = "Professor sem perfil associado"
ERR_TEACHER_OWN_SCHEDULE_ONLY = "Professor só pode consultar o próprio horário"
ERR_TEACHER_HORIZON_NOT_FOUND = "Não existe horizonte semanal configurado para a organização"
ERR_SCHEDULE_RESET_FORBIDDEN = "Sem permissões para apagar os dados de horário"
TASK_KEY_TTL_SECONDS = 60 * 60 * 24
TASK_ORG_KEY_PREFIX = "schedule_task_org:"
TASK_CANCEL_KEY_PREFIX = "schedule_task_cancel:"
ACTIVE_TASK_BY_ORG_KEY_PREFIX = "schedule_active_task_org:"


def _resolve_solver_engine_version() -> str:
    version = str(getattr(settings, "SOLVER_ENGINE_VERSION", "v1")).lower()
    return version if version in {"v1", "v2"} else "v1"


def _task_org_key(task_id: str) -> str:
    return f"{TASK_ORG_KEY_PREFIX}{task_id}"


def _task_cancel_key(task_id: str) -> str:
    return f"{TASK_CANCEL_KEY_PREFIX}{task_id}"


def _active_task_by_org_key(org_id: int) -> str:
    return f"{ACTIVE_TASK_BY_ORG_KEY_PREFIX}{org_id}"


def _get_redis_client() -> redis.Redis:
    return redis.Redis.from_url(str(settings.REDIS_URL))


def _extract_request_id(request: Request) -> str | None:
    return (
        request.headers.get("x-request-id")
        or request.headers.get("x-correlation-id")
    )


def _log_schedule_reset_audit(
    request: Request,
    *,
    org_id: int | None,
    user_id: int | None,
    role: str | None,
    status_code: int,
    detail: str,
) -> None:
    logger.info(
        "schedule_reset_audit",
        org_id=org_id,
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
    current_user: Annotated[models.User, Depends(deps.get_current_user)],
) -> models.User:
    """Aplica gate admin-only com trilho de auditoria para tentativas negadas."""
    try:
        active_user = deps.get_current_active_user(current_user)
        return deps.get_current_active_admin(active_user)
    except HTTPException as exc:
        detail = str(exc.detail)
        if exc.status_code == 403:
            detail = ERR_SCHEDULE_RESET_FORBIDDEN
        _log_schedule_reset_audit(
            request,
            org_id=getattr(current_user, "organization_id", None),
            user_id=getattr(current_user, "id", None),
            role=getattr(getattr(current_user, "role", None), "value", getattr(current_user, "role", None)),
            status_code=exc.status_code,
            detail=detail,
        )
        raise HTTPException(status_code=exc.status_code, detail=detail)


def _validate_task_ownership(task_id: str, org_id: int) -> redis.Redis:
    try:
        r = _get_redis_client()
        org_value = r.get(_task_org_key(task_id))
        if not org_value:
            raise HTTPException(status_code=404, detail="Task não encontrada")
        if org_value.decode("utf-8") != str(org_id):
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
    # Garante que usamos o org_id do utilizador logado
    return await schedule_service.create_constraint(db, item, current_user.organization_id)

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
    success = await schedule_service.delete_constraint(db, constraint_id, current_user.organization_id)
    if not success:
        raise HTTPException(status_code=404, detail="Regra não encontrada")
    return {"ok": True}

# --- GERAÇÃO (Celery) ---

async def _get_latest_settings_with_dates(
    db: AsyncSession,
    org_id: int,
) -> models.OrganizationSettings | None:
    settings_result = await db.execute(
        sa_select(models.OrganizationSettings).where(
            models.OrganizationSettings.org_id == org_id,
            models.OrganizationSettings.school_start_date.isnot(None),
            models.OrganizationSettings.school_target_end_date.isnot(None),
        )
    )
    return settings_result.scalars().first()


def _resolve_repair_window_days(org_settings: models.OrganizationSettings) -> int:
    value = org_settings.repair_stability_window_days
    if value is None:
        return DEFAULT_REPAIR_WINDOW_DAYS
    return max(1, int(value))


def _resolve_preflight_hard_end_date(org_settings: models.OrganizationSettings) -> date | None:
    if org_settings.school_hard_end_date is not None:
        return org_settings.school_hard_end_date
    if org_settings.school_target_end_date is None:
        return None
    return date(org_settings.school_target_end_date.year, DEFAULT_HARD_END_MONTH, DEFAULT_HARD_END_DAY)


def _validate_repair_generation_window(org_settings: models.OrganizationSettings) -> str | None:
    repair_window_days = _resolve_repair_window_days(org_settings)
    frozen_until = date.today() + timedelta(days=repair_window_days)
    hard_end_date = _resolve_preflight_hard_end_date(org_settings)
    if hard_end_date is None:
        return None
    if hard_end_date <= frozen_until:
        return (
            "Regeneração em modo repair bloqueada: não existe horizonte fora da janela "
            f"de estabilidade (até {frozen_until.isoformat()}) antes do hard end date "
            f"({hard_end_date.isoformat()})."
        )
    return None


async def _ensure_auto_holidays(
    db: AsyncSession,
    org_id: int,
    org_settings: models.OrganizationSettings,
) -> str | None:
    holiday_count = await db.scalar(
        sa_select(func.count(models.SchoolCalendarEvent.id)).where(
            models.SchoolCalendarEvent.org_id == org_id,
            models.SchoolCalendarEvent.source == models.CalendarEventSource.auto,
        )
    )
    if holiday_count:
        return None

    try:
        imported = await settings_service.sync_holidays(
            db,
            org_id=org_id,
        )
    except Exception:
        return (
            "Falha ao sincronizar feriados automáticos. "
            "Aceda a Configurações > Calendário Escolar e clique em 'Sincronizar Feriados'."
        )

    if imported <= 0:
        return (
            "Não foi possível carregar feriados automáticos. "
            "Aceda a Configurações > Calendário Escolar e clique em 'Sincronizar Feriados'."
        )
    return None


async def _get_generation_workload_counts(db: AsyncSession, org_id: int) -> tuple[int, int]:
    class_subject_count = await db.scalar(
        sa_select(func.count(models.ClassSubjectLink.id))
        .join(models.Class, models.ClassSubjectLink.class_id == models.Class.id)
        .where(
            models.Class.organization_id == org_id,
            models.Class.is_archived == False,  # noqa: E712
            models.ClassSubjectLink.teacher_id.isnot(None),
            models.ClassSubjectLink.grade_level == models.Class.grade_level,
        )
    )
    lesson_count = await db.scalar(
        sa_select(func.count(models.Lesson.id))
        .join(models.Class, models.Lesson.class_id == models.Class.id)
        .where(
            models.Lesson.organization_id == org_id,
            models.Class.is_archived == False,  # noqa: E712
        )
    )
    return class_subject_count or 0, lesson_count or 0


async def _collect_generation_teacher_ids(db: AsyncSession, org_id: int) -> set[int]:
    class_subject_teacher_rows = await db.execute(
        sa_select(models.ClassSubjectLink.teacher_id)
        .join(models.Class, models.ClassSubjectLink.class_id == models.Class.id)
        .where(
            models.Class.organization_id == org_id,
            models.Class.is_archived == False,  # noqa: E712
            models.ClassSubjectLink.teacher_id.isnot(None),
            models.ClassSubjectLink.grade_level == models.Class.grade_level,
        )
        .distinct()
    )
    class_subject_teacher_ids = {row[0] for row in class_subject_teacher_rows.all()}

    lesson_teacher_rows = await db.execute(
        sa_select(models.Lesson.teacher_id)
        .join(models.Class, models.Lesson.class_id == models.Class.id)
        .where(
            models.Lesson.organization_id == org_id,
            models.Class.is_archived == False,  # noqa: E712
        )
        .distinct()
    )
    lesson_teacher_ids = {row[0] for row in lesson_teacher_rows.all()}
    return class_subject_teacher_ids | lesson_teacher_ids


async def _collect_generation_subject_ids(db: AsyncSession, org_id: int) -> set[int]:
    class_subject_subject_rows = await db.execute(
        sa_select(models.ClassSubjectLink.subject_id)
        .join(models.Class, models.ClassSubjectLink.class_id == models.Class.id)
        .where(
            models.Class.organization_id == org_id,
            models.Class.is_archived == False,  # noqa: E712
            models.ClassSubjectLink.teacher_id.isnot(None),
            models.ClassSubjectLink.grade_level == models.Class.grade_level,
        )
        .distinct()
    )
    class_subject_ids = {row[0] for row in class_subject_subject_rows.all()}

    lesson_subject_rows = await db.execute(
        sa_select(models.Lesson.subject_id)
        .join(models.Class, models.Lesson.class_id == models.Class.id)
        .where(
            models.Lesson.organization_id == org_id,
            models.Class.is_archived == False,  # noqa: E712
        )
        .distinct()
    )
    lesson_subject_ids = {row[0] for row in lesson_subject_rows.all()}
    return class_subject_ids | lesson_subject_ids


async def _validate_teacher_availabilities(
    db: AsyncSession,
    teacher_ids: set[int],
) -> str | None:
    if not teacher_ids:
        return None

    available_teacher_rows = await db.execute(
        sa_select(models.Availability.teacher_id)
        .where(models.Availability.teacher_id.in_(teacher_ids))
        .distinct()
    )
    available_teacher_ids = {row[0] for row in available_teacher_rows.all()}
    missing_availability_ids = teacher_ids - available_teacher_ids
    if not missing_availability_ids:
        return None

    teacher_name_rows = await db.execute(
        sa_select(models.Teacher.name)
        .where(models.Teacher.id.in_(missing_availability_ids))
        .order_by(models.Teacher.name)
    )
    missing_names = [row[0] for row in teacher_name_rows.all()]
    return (
        "Professores sem disponibilidade configurada: "
        f"{', '.join(missing_names)}. "
        "Configure em Professores > Disponibilidade."
    )


async def _validate_subject_requirements(
    db: AsyncSession,
    org_id: int,
    subject_ids: set[int],
) -> list[str]:
    if not subject_ids:
        return []

    errors: list[str] = []
    module_rows = await db.execute(
        sa_select(models.Module.subject_id, models.Module.hours_total)
        .where(models.Module.subject_id.in_(subject_ids))
    )
    modules_by_subject: dict[int, list[int]] = {}
    for subject_id, hours_total in module_rows.all():
        modules_by_subject.setdefault(subject_id, []).append(hours_total)

    missing_module_subject_ids = {
        subject_id
        for subject_id in subject_ids
        if subject_id not in modules_by_subject
    }
    invalid_module_subject_ids = {
        subject_id
        for subject_id, hours_list in modules_by_subject.items()
        if any(hours <= 0 for hours in hours_list)
    }
    impacted_subject_ids = missing_module_subject_ids | invalid_module_subject_ids

    if impacted_subject_ids:
        subject_rows = await db.execute(
            sa_select(models.Subject.id, models.Subject.name)
            .where(models.Subject.id.in_(impacted_subject_ids))
        )
        subject_name_map = {row[0]: row[1] for row in subject_rows.all()}

        if missing_module_subject_ids:
            missing_names = sorted(
                subject_name_map.get(sid, f"ID {sid}")
                for sid in missing_module_subject_ids
            )
            errors.append(
                "Disciplinas sem módulos definidos: "
                f"{', '.join(missing_names)}. "
                "Adicione módulos com horas > 0 em Disciplinas."
            )

        if invalid_module_subject_ids:
            invalid_names = sorted(
                subject_name_map.get(sid, f"ID {sid}")
                for sid in invalid_module_subject_ids
            )
            errors.append(
                "Disciplinas com módulos inválidos (hours_total <= 0): "
                f"{', '.join(invalid_names)}. "
                "Corrija a carga horária dos módulos."
            )

    required_type_rows = await db.execute(
        sa_select(models.Subject.required_room_type)
        .where(models.Subject.id.in_(subject_ids))
        .distinct()
    )
    required_room_types = {row[0] for row in required_type_rows.all()}
    available_type_rows = await db.execute(
        sa_select(models.Room.type)
        .where(models.Room.organization_id == org_id)
        .distinct()
    )
    available_room_types = {row[0] for row in available_type_rows.all()}

    missing_room_types = required_room_types - available_room_types
    if missing_room_types:
        missing_labels = sorted(rt.value for rt in missing_room_types)
        errors.append(
            "Não existem salas para os tipos exigidos: "
            f"{', '.join(missing_labels)}. "
            "Adicione salas desses tipos em Salas."
        )

    return errors


async def _validate_repair_capacity_feasibility(
    db: AsyncSession,
    org_id: int,
    org_settings: models.OrganizationSettings,
    room_count: int,
) -> str | None:
    """Mantido por compatibilidade: usar preflight hibrido em _build_hard_end_feasibility."""
    _ = (db, org_id, org_settings, room_count)
    return None


def _build_preflight_primary_window(
    *,
    org_settings: models.OrganizationSettings,
    mode: str,
    blocked_dates: set[date],
) -> dict | None:
    hard_end_date = _resolve_preflight_hard_end_date(org_settings)
    if hard_end_date is None:
        return None

    repair_window_days = _resolve_repair_window_days(org_settings) if mode == "repair" else 0
    window_start = _resolve_expansion_start_date(
        org_settings.school_start_date,
        mode=mode,
        repair_window_days=repair_window_days,
    )

    primary_window = _build_primary_rolling_window(
        window_start_date=window_start,
        hard_end_date=hard_end_date,
        blocked_dates=blocked_dates,
        rolling_weeks=_resolve_solver_v2_rolling_weeks(),
    )
    return {
        "rolling_weeks": int(primary_window["rolling_weeks"]),
        "start_date": primary_window["window_start_date"],
        "end_date": primary_window["window_end_date"],
        "total_days": int(primary_window["window_total_days"]),
        "blocked_days": int(primary_window["window_blocked_days"]),
        "usable_days": int(primary_window["window_usable_days"]),
    }


async def _build_hard_end_feasibility(
    db: AsyncSession,
    org_id: int,
    org_settings: models.OrganizationSettings,
    mode: str,
    room_count: int,
    blocked_dates: set[date],
) -> dict | None:
    hard_end_date = _resolve_preflight_hard_end_date(org_settings)
    if hard_end_date is None:
        return None

    repair_window_days = _resolve_repair_window_days(org_settings) if mode == "repair" else 0
    horizon_start = _resolve_expansion_start_date(
        org_settings.school_start_date,
        mode=mode,
        repair_window_days=repair_window_days,
    )

    def _run(sync_db) -> tuple[int, int]:
        lessons = schedule_service.get_active_lessons_with_subject_sync(sync_db, org_id)
        modules_by_subject = schedule_service.get_modules_by_subject_sync(sync_db, org_id)
        progress_map = schedule_service.get_class_progress_map_sync(sync_db, org_id)

        committed_minutes_by_lesson: dict[int, int] = {}
        if mode == "repair":
            frozen_until = horizon_start - timedelta(days=1)
            committed_minutes_by_lesson = schedule_service.get_repair_committed_minutes_by_lesson_sync(
                sync_db,
                org_id,
                frozen_until,
            )

        remaining_minutes = 0
        if lessons:
            for lesson in lessons:
                remaining = _compute_remaining_minutes(lesson, modules_by_subject, progress_map)
                if mode == "repair":
                    remaining -= max(0, int(committed_minutes_by_lesson.get(lesson.id, 0)))
                remaining_minutes += max(0, int(remaining))
        else:
            link_rows = (
                sync_db.query(
                    models.ClassSubjectLink.class_id,
                    models.ClassSubjectLink.subject_id,
                )
                .join(models.Class, models.ClassSubjectLink.class_id == models.Class.id)
                .filter(
                    models.Class.organization_id == org_id,
                    models.Class.is_archived == False,  # noqa: E712
                    models.ClassSubjectLink.teacher_id.isnot(None),
                    models.ClassSubjectLink.grade_level == models.Class.grade_level,
                )
                .distinct()
                .all()
            )

            for class_id, subject_id in link_rows:
                for module in modules_by_subject.get(subject_id, []):
                    hours_done = float(progress_map.get((class_id, module.id), 0) or 0)
                    remaining_hours = max(0.0, float(module.hours_total) - hours_done)
                    remaining_minutes += int(round(remaining_hours * 60))

        if remaining_minutes <= 0:
            return (0, 0)

        timeslots = schedule_service.get_timeslots_by_org_sync(sync_db, org_id)
        capacity_minutes = _estimate_capacity_minutes_in_range(
            timeslots=timeslots,
            room_count=max(0, int(room_count)),
            blocked_dates=blocked_dates,
            start_date=horizon_start,
            end_date=hard_end_date,
        )
        return (remaining_minutes, capacity_minutes)

    backlog_minutes, capacity_minutes = await db.run_sync(_run)
    expected_residual_minutes = max(0, backlog_minutes - max(0, capacity_minutes))

    return {
        "start_date": horizon_start,
        "hard_end_date": hard_end_date,
        "backlog_hours": round(max(0, backlog_minutes) / 60, 1),
        "capacity_hours": round(max(0, capacity_minutes) / 60, 1),
        "expected_residual_hours": round(expected_residual_minutes / 60, 1),
        "feasible_until_hard_end": expected_residual_minutes == 0,
    }


def _build_repair_infeasible_error(feasibility: dict) -> str:
    return (
        "Regeneracao em modo repair bloqueada: carga reconciliada estimada "
        f"({feasibility['backlog_hours']}h) excede a capacidade teorica maxima "
        f"({feasibility['capacity_hours']}h) no horizonte "
        f"{feasibility['start_date'].isoformat()} a {feasibility['hard_end_date'].isoformat()}. "
        f"Residual esperado ate hard end: {feasibility['expected_residual_hours']}h."
    )


async def _preflight_check(db: AsyncSession, org_id: int, mode: str = "full") -> tuple[list[str], dict]:
    """Valida pré-condições e devolve erros + resumo de preflight híbrido."""
    errors: list[str] = []
    preflight_summary: dict = {
        "mode": mode,
        "primary_window": None,
        "hard_end_feasibility": None,
    }

    from app.services import schedule_service
    drafts = await db.run_sync(lambda sync_db: schedule_service.list_draft_gen_ids_sync(sync_db, org_id))
    if drafts:
        return (
            [
                "Existe um rascunho pendente de aprovação. "
                "Por favor, aprove ou rejeite o rascunho atual antes de iniciar uma nova geração."
            ],
            preflight_summary,
        )

    org_settings = await _get_latest_settings_with_dates(db, org_id)
    if not org_settings:
        return (
            [
                "Nenhum ano letivo com 'data de início' e 'data de fim-alvo'. "
                "Configure em Configurações > Anos Letivos."
            ],
            preflight_summary,
        )

    if mode == "repair":
        window_error = _validate_repair_generation_window(org_settings)
        if window_error:
            errors.append(window_error)

    holiday_error = await _ensure_auto_holidays(db, org_id, org_settings)
    if holiday_error:
        errors.append(holiday_error)

    class_subject_count, lesson_count = await _get_generation_workload_counts(db, org_id)
    if not class_subject_count and not lesson_count:
        errors.append(
            "Nenhuma carga letiva ativa encontrada. "
            "Atribua professores em Turmas > Disciplinas (modelo novo) "
            "ou configure lições no fluxo legado."
        )

    ts_count = await db.scalar(
        sa_select(func.count(models.Timeslot.id)).where(models.Timeslot.organization_id == org_id)
    )
    if not ts_count:
        errors.append(
            "Nenhum período horário configurado. Configure em Configurações > Grelha Horária."
        )

    room_count = await db.scalar(
        sa_select(func.count(models.Room.id)).where(models.Room.organization_id == org_id)
    )
    if not room_count:
        errors.append("Nenhuma sala configurada.")

    calendar_events = await db.execute(
        sa_select(models.SchoolCalendarEvent).where(models.SchoolCalendarEvent.org_id == org_id)
    )
    blocked_dates = _build_blocked_dates(calendar_events.scalars().all())
    preflight_summary["primary_window"] = _build_preflight_primary_window(
        org_settings=org_settings,
        mode=mode,
        blocked_dates=blocked_dates,
    )

    teacher_ids = await _collect_generation_teacher_ids(db, org_id)
    teacher_error = await _validate_teacher_availabilities(db, teacher_ids)
    if teacher_error:
        errors.append(teacher_error)

    subject_ids = await _collect_generation_subject_ids(db, org_id)
    errors.extend(await _validate_subject_requirements(db, org_id, subject_ids))

    if not errors:
        feasibility = await _build_hard_end_feasibility(
            db,
            org_id,
            org_settings,
            mode,
            int(room_count or 0),
            blocked_dates,
        )
        preflight_summary["hard_end_feasibility"] = feasibility

        if (
            mode == "repair"
            and feasibility is not None
            and not feasibility["feasible_until_hard_end"]
        ):
            errors.append(_build_repair_infeasible_error(feasibility))

    return errors, preflight_summary


@router.post(
    "/generate",
    response_model=schemas.ScheduleGenerateResponse,
    responses={
        400: {"description": "Preflight falhou — dados insuficientes para gerar horário"},
    },
)
@limiter.limit("5/minute")
async def trigger_generation(
    request: Request,
    payload: schemas.ScheduleGenerateRequest,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
):
    """Valida pré-condições e inicia a geração de horário em background."""
    org_id = current_user.organization_id

    preflight_errors, preflight_summary = await _preflight_check(db, org_id, payload.mode)
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

    solver_version = _resolve_solver_engine_version()

    task = generate_schedule_task.delay(org_id, payload.mode)
    try:
        r = _get_redis_client()
        r.setex(_task_org_key(task.id), TASK_KEY_TTL_SECONDS, str(org_id))
        r.setex(_active_task_by_org_key(org_id), TASK_KEY_TTL_SECONDS, task.id)
    except Exception:
        pass
    return {
        "task_id": task.id,
        "status": "Processing started",
        "solver_version": solver_version,
        "preflight": encoded_preflight,
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
        if active_task_value and active_task_value.decode("utf-8") == task_id:
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
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
):
    """Cancela uma geração em curso sem deixar resultados parciais persistidos."""
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
    
    # 1. Tentar ligar ao Redis
    try:
        r = redis.Redis.from_url(str(settings.REDIS_URL))
        cached_data = r.get(CACHE_KEY)
        
        if cached_data:
            # [CACHE HIT] - Encontrámos dados!
            print(f"⚡ Cache HIT para {CACHE_KEY}. A servir do Redis.")
            return json.loads(cached_data)
    except Exception as e:
        print(f"⚠️ Erro ao ler cache Redis: {e}. A seguir para a BD.")

    # 2. [CACHE MISS] - Não estava no Redis (ou foi apagado pelo Worker)
    print(f"🐢 Cache MISS para {CACHE_KEY}. A ler da Base de Dados...")
    
    # Vamos buscar à base de dados (Lento)
    latest_schedule = await schedule_service.get_latest_schedule_by_org(db, current_user.organization_id)
    
    # 3. Guardar no Redis para a próxima vez
    if latest_schedule:
        try:
            # Convertemos os objetos da BD para JSON puro
            json_data = jsonable_encoder(latest_schedule)
            
            # Guardamos no Redis com validade de 60 segundos (TTL)
            # Se ninguém apagar, expira sozinho.
            # Se o Worker gerar novo horário, ele apaga esta chave explicitamente.
            r.set(CACHE_KEY, json.dumps(json_data), ex=60)
        except Exception as e:
            print(f"⚠️ Erro ao gravar cache Redis: {e}")

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
            org_id=current_user.organization_id,
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
    """Retorna todos os rascunhos (mode=repair) pendentes de aprovação."""

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
            or org_settings.school_target_end_date
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
                .filter(models.OrganizationSettings.org_id == current_user.organization_id)
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
                org_id=current_user.organization_id,
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
                org_id=current_user.organization_id,
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
                    org_id=current_user.organization_id,
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
    org_id = current_user.organization_id

    if generation_id is None:
        latest_row = await db.execute(
            sa_select(models.ScheduleOutput.generation_id)
            .where(
                models.ScheduleOutput.organization_id == org_id,
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
            models.ScheduleOutput.organization_id == org_id,
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
            models.ScheduleOutput.organization_id == org_id,
            models.ScheduleOutput.is_draft.is_(False),
            models.ScheduleOutput.generation_id == generation_id,
        )
    )
    overview = overview_row.one()

    week_start = date.today() - timedelta(days=date.today().weekday())
    week_end = week_start + timedelta(days=6)

    class_ids_result = await db.execute(
        sa_select(models.Class.id).where(
            models.Class.organization_id == org_id,
            models.Class.is_archived == False,  # noqa: E712
        )
    )
    class_ids = [row[0] for row in class_ids_result.all()]
    classes_total = len(class_ids)

    class_week_rows = await db.execute(
        sa_select(models.Lesson.class_id, func.count(models.ScheduleOutput.id).label("slots_count"))
        .join(models.ScheduleOutput, models.ScheduleOutput.lesson_id == models.Lesson.id)
        .where(
            models.ScheduleOutput.organization_id == org_id,
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
            models.ScheduleOutput.organization_id == org_id,
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
            models.ScheduleOutput.organization_id == org_id,
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
            models.ScheduleOutput.organization_id == org_id,
            models.ScheduleOutput.is_draft.is_(False),
            models.ScheduleOutput.generation_id == generation_id,
            models.ScheduleOutput.date.between(week_start, week_end),
        )
        .group_by(models.Lesson.teacher_id)
    )
    teacher_week_values = [row.slots_count for row in teacher_week_rows.all()]
    teacher_week_slots_min, teacher_week_slots_max, teacher_week_slots_avg, _ = _build_distribution_stats(teacher_week_values)
    teachers_with_week_slots = len(teacher_week_values)

    room_usage_rows = await db.execute(
        sa_select(models.Room.type, func.count(models.ScheduleOutput.id).label("blocks_count"))
        .join(models.ScheduleOutput, models.ScheduleOutput.room_id == models.Room.id)
        .where(
            models.ScheduleOutput.organization_id == org_id,
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
            org_id=current_user.organization_id,
            user_id=current_user.id,
            schedule_output_id=schedule_output_id,
            payload=payload
        )

    return await db.run_sync(_run)