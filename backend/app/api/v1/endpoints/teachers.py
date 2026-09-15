# Ficheiro: backend/app/api/endpoints/teachers.py

from time import perf_counter
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.api import deps
from app.core.exceptions import AppError, status_code_for_kind
from app.core.ratelimit import limiter
from app.services import teacher_observability_service, teacher_service

TEACHER_NOT_FOUND_MSG = "Professor não encontrado"

router = APIRouter()


@router.get(
    "/me/availability",
    response_model=list[schemas.AvailabilitySelfRead],
    responses={403: {"description": "Sem permissões"}, 404: {"description": TEACHER_NOT_FOUND_MSG}},
)
async def read_my_availability(
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.ActiveActor,
):
    """Lê disponibilidade do professor autenticado (self-service)."""
    start_ts = perf_counter()
    status_code = 200

    try:
        if current_user.teacher_id is None:
            status_code = 403
            raise HTTPException(status_code=403, detail="Professor sem perfil associado")

        result = await teacher_service.get_teacher_availability(
            db,
            teacher_id=current_user.teacher_id,
            organization_id=current_user.organization_id,
        )
        return result
    except AppError as exc:
        status_code = status_code_for_kind(exc.kind, exc.code)
        raise
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
                actor_membership_id=current_user.membership_id,
                actor_role=deps.actor_role(current_user),
                endpoint_key=teacher_observability_service.ENDPOINT_TEACHERS_ME_AVAILABILITY_READ,
                http_status=status_code,
                latency_ms=elapsed_ms,
            )

        await db.run_sync(_emit)


@router.put(
    "/me/availability",
    responses={
        403: {"description": "Sem permissões"},
        404: {"description": TEACHER_NOT_FOUND_MSG},
        400: {"description": "Timeslot inválido"},
    },
)
@limiter.limit("30/minute")
async def update_my_availability(
    request: Request,
    availability_data: schemas.TeacherAvailabilityPayload,
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.ActiveActor,
):
    """Atualiza disponibilidade do professor autenticado (self-service)."""
    if current_user.teacher_id is None:
        raise HTTPException(status_code=403, detail="Professor sem perfil associado")

    result = await teacher_service.set_teacher_availability(
        db,
        current_user.teacher_id,
        availability_data,
        organization_id=current_user.organization_id,
        changed_by_membership_id=current_user.membership_id,
    )
    return result


@router.get(
    "/{teacher_id}/availability",
    response_model=list[schemas.AvailabilitySelfRead],
    responses={403: {"description": "Sem permissões"}, 404: {"description": TEACHER_NOT_FOUND_MSG}},
)
async def read_teacher_availability(
    teacher_id: int,
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.ActiveActor,
):
    """Inspetor read-only de disponibilidade para Administrador ou o próprio Professor."""
    is_admin = deps.user_has_admin_capability(current_user)
    if not is_admin and current_user.teacher_id != teacher_id:
        raise HTTPException(
            status_code=403, detail="Sem permissões para visualizar outro professor"
        )

    result = await teacher_service.get_teacher_availability(
        db,
        teacher_id=teacher_id,
        organization_id=current_user.organization_id,
    )
    return result


@router.get(
    "/observability/summary",
    response_model=schemas.TeacherEndpointObservabilitySummaryRead,
    summary="Resumo operacional dos endpoints críticos do professor",
)
async def get_teacher_endpoints_observability_summary(
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.AdminActor,
    window_minutes: Annotated[
        int, Query(ge=5, le=1440, description="Janela de agregação em minutos")
    ] = 15,
):
    def _run(sync_db):
        return teacher_observability_service.get_teacher_endpoint_observability_summary_sync(
            sync_db,
            organization_id=current_user.organization_id,
            window_minutes=window_minutes,
        )

    return await db.run_sync(_run)


@router.get(
    "/me/progress",
    response_model=list[schemas.TeacherClassProgressRead],
    summary="Progresso curricular do professor autenticado",
    responses={403: {"description": "Sem permissões"}},
)
async def read_my_progress(
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.ActiveActor,
):
    """Retorna o progresso das disciplinas do professor nas turmas assignadas."""
    start_ts = perf_counter()
    status_code = 200

    try:
        if current_user.teacher_id is None:
            status_code = 403
            raise HTTPException(status_code=403, detail="Professor sem perfil associado")

        result = await teacher_service.get_teacher_progress(
            db,
            teacher_id=current_user.teacher_id,
            organization_id=current_user.organization_id,
        )
        return result
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
                actor_membership_id=current_user.membership_id,
                actor_role=deps.actor_role(current_user),
                endpoint_key=teacher_observability_service.ENDPOINT_TEACHERS_ME_PROGRESS_READ,
                http_status=status_code,
                latency_ms=elapsed_ms,
            )

        await db.run_sync(_emit)


# --- 1. Ler Professores ---
@router.get("/", response_model=list[schemas.TeacherRead])
async def read_teachers(
    current_user: deps.AdminActor,
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    skip: int = 0,
    limit: int = 100,
):
    return await teacher_service.get_teachers_by_org(
        db, organization_id=current_user.organization_id, skip=skip, limit=limit
    )
