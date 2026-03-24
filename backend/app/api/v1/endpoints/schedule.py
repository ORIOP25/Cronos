from datetime import date, timedelta
from statistics import mean, pstdev
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi_cache.decorator import cache
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import desc, func, select as sa_select
from celery.result import AsyncResult
from typing import List, Annotated
import json
import redis
from app import schemas, models
from app.api import deps
from app.services import schedule_service, settings_service
from app.solver_tasks import generate_schedule_task
from app.config import settings
from app.core.ratelimit import limiter

router = APIRouter()
ERR_DRAFT_NOT_FOUND = "Rascunho não encontrado"

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
        ).order_by(
            desc(models.OrganizationSettings.academic_year),
            desc(models.OrganizationSettings.id),
        )
    )
    return settings_result.scalars().first()


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
            academic_year=org_settings.academic_year,
            region_code=org_settings.region_code,
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


async def _preflight_check(db: AsyncSession, org_id: int) -> list[str]:
    """Valida pré-condições antes de iniciar o solver. Retorna lista de erros."""
    errors: list[str] = []

    org_settings = await _get_latest_settings_with_dates(db, org_id)
    if not org_settings:
        return [
            "Nenhum ano letivo com 'data de início' e 'data de fim-alvo'. "
            "Configure em Configurações > Anos Letivos."
        ]

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

    teacher_ids = await _collect_generation_teacher_ids(db, org_id)
    teacher_error = await _validate_teacher_availabilities(db, teacher_ids)
    if teacher_error:
        errors.append(teacher_error)

    subject_ids = await _collect_generation_subject_ids(db, org_id)
    errors.extend(await _validate_subject_requirements(db, org_id, subject_ids))

    return errors


@router.post(
    "/generate",
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

    preflight_errors = await _preflight_check(db, org_id)
    if preflight_errors:
        raise HTTPException(
            status_code=400,
            detail={"error": "preflight_failed", "problems": preflight_errors},
        )

    task = generate_schedule_task.delay(org_id, payload.mode)
    try:
        r = redis.Redis.from_url(str(settings.REDIS_URL))
        r.setex(f"schedule_task_org:{task.id}", 60 * 60 * 24, str(org_id))
    except Exception:
        pass
    return {"task_id": task.id, "status": "Processing started"}

@router.get("/status/{task_id}", responses={404: {"description": "Task não encontrada"}, 403: {"description": "Sem permissões para esta task"}, 503: {"description": "Validação de task indisponível"}})
@limiter.limit("60/minute")
async def get_status(
    request: Request,
    task_id: str,
    current_user: Annotated[models.User, Depends(deps.get_current_user)]
):
    """Verifica o progresso da geração."""
    # Validar se o task_id pertence à organização
    try:
        r = redis.Redis.from_url(str(settings.REDIS_URL))
        org_value = r.get(f"schedule_task_org:{task_id}")
        if not org_value:
            raise HTTPException(status_code=404, detail="Task não encontrada")
        if org_value.decode("utf-8") != str(current_user.organization_id):
            raise HTTPException(status_code=403, detail="Sem permissões para esta task")
    except HTTPException:
        raise
    except Exception:
        # Se Redis falhar, negar por segurança
        raise HTTPException(status_code=503, detail="Validação de task indisponível")

    task_result = AsyncResult(task_id)
    task_payload = task_result.result if isinstance(task_result.result, dict) else {}
    progress = task_payload.get("progress") if isinstance(task_payload, dict) else None
    response = {
        "task_id": task_id,
        "status": task_result.status,
        "result": task_result.result,
        "detail": task_payload.get("detail") if isinstance(task_payload, dict) else None,
        "phase": task_payload.get("phase") if isinstance(task_payload, dict) else None,
        "progress": progress,
    }
    return response

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

@router.delete("/reset")
async def reset_all_data(
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_user)]
):
    await schedule_service.delete_all_schedule_data(db, current_user.organization_id)
    
    # [EXTRA] Se apagamos os dados, também devemos limpar a cache!
    try:
        r = redis.Redis.from_url(str(settings.REDIS_URL))
        CACHE_KEY = f"schedule_latest_data_{current_user.organization_id}"
        r.delete(CACHE_KEY)
    except Exception:
        pass

    return {"msg": "Dados de horário apagados com sucesso."}


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
        drafts = svc.list_draft_gen_ids_sync(sync_db, current_user.organization_id)
        if not any(d["generation_id"] == gen_id for d in drafts):
            return None
        return svc.get_diff_sync(sync_db, current_user.organization_id, gen_id)

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


@router.get(
    "/week",
    response_model=list[schemas.WeekSlotRead],
    responses={
        400: {"description": WEEK_FILTER_REQUIRED_MSG},
    },
    summary="Horário de uma semana (turma ou professor)",
)
async def get_week_schedule(
    week_start: Annotated[date, Query(description="Data de início da semana (segunda-feira, YYYY-MM-DD)")],
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_user)],
    class_id: Annotated[int | None, Query(description="ID da turma")] = None,
    teacher_id: Annotated[int | None, Query(description="ID do professor")] = None,
):
    """Retorna os slots da semana indicada, enriquecidos com o estado de ocorrência para dias passados."""
    if class_id is None and teacher_id is None:
        raise HTTPException(status_code=400, detail=WEEK_FILTER_REQUIRED_MSG)

    def _run(sync_db):
        from app.services import schedule_service as svc
        return svc.get_week_schedule_sync(
            sync_db,
            org_id=current_user.organization_id,
            week_start=week_start,
            class_id=class_id,
            teacher_id=teacher_id,
        )

    return await db.run_sync(_run)


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
        teacher_week_slots_avg=teacher_week_slots_avg,
        room_type_usage=room_type_usage,
    )