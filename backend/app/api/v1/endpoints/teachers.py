from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Request

from app import schemas
from app.api import deps
from app.core.exceptions import AppError
from app.core.ratelimit import limiter
from app.services import teacher_service

TEACHER_NOT_FOUND_MSG = "Professor não encontrado"

router = APIRouter()


def _require_teacher_profile(current_user: deps.Actor) -> int:
    if current_user.teacher_id is None:
        raise AppError(
            kind="forbidden", code="access_forbidden", detail="Professor sem perfil associado"
        )
    return current_user.teacher_id


@router.get(
    "/me/availability",
    response_model=list[schemas.AvailabilitySelfRead],
    responses={403: {"description": "Sem permissões"}, 404: {"description": TEACHER_NOT_FOUND_MSG}},
)
async def read_my_availability(
    db: deps.DbSession,
    current_user: deps.ActiveActor,
):
    """Lê disponibilidade do professor autenticado (self-service)."""
    return await teacher_service.get_teacher_availability(
        db,
        teacher_id=_require_teacher_profile(current_user),
        organization_id=current_user.organization_id,
    )


@router.get(
    "/me/presence",
    response_model=schemas.TeacherPresence,
    responses={403: {"description": "Sem permissões"}},
)
async def read_my_presence(
    db: deps.DbSession,
    current_user: deps.ActiveActor,
):
    """Lê a regra de presença do professor autenticado (self-service)."""
    return await teacher_service.get_teacher_presence(
        db,
        teacher_id=_require_teacher_profile(current_user),
        organization_id=current_user.organization_id,
    )


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
    availability_data: schemas.WeeklyAvailabilityPayload,
    db: deps.DbSession,
    current_user: deps.ActiveActor,
):
    """Atualiza disponibilidade do professor autenticado (self-service)."""
    return await teacher_service.set_teacher_availability(
        db,
        _require_teacher_profile(current_user),
        availability_data,
        organization_id=current_user.organization_id,
        changed_by_membership_id=current_user.membership_id,
    )


@router.put(
    "/{teacher_id}/availability",
    responses={
        403: {"description": "Sem permissões"},
        404: {"description": TEACHER_NOT_FOUND_MSG},
        400: {"description": "Timeslot inválido"},
    },
)
async def update_teacher_availability(
    teacher_id: int,
    availability_data: schemas.WeeklyAvailabilityPayload,
    db: deps.DbSession,
    current_user: deps.AdminActor,
    on_date: Annotated[date | None, Query(description="Data da grelha de disponibilidade")] = None,
):
    """Direção atualiza a disponibilidade de um professor, sem convite."""
    return await teacher_service.set_teacher_availability(
        db,
        teacher_id,
        availability_data,
        organization_id=current_user.organization_id,
        changed_by_membership_id=current_user.membership_id,
        on_date=on_date,
    )


@router.get(
    "/{teacher_id}/availability",
    response_model=list[schemas.AvailabilitySelfRead],
    responses={403: {"description": "Sem permissões"}, 404: {"description": TEACHER_NOT_FOUND_MSG}},
)
async def read_teacher_availability(
    teacher_id: int,
    db: deps.DbSession,
    current_user: deps.ActiveActor,
    on_date: Annotated[date | None, Query(description="Data da grelha de disponibilidade")] = None,
):
    """Inspetor read-only de disponibilidade para Administrador ou o próprio Professor."""
    is_admin = deps.user_has_admin_capability(current_user)
    if not is_admin and current_user.teacher_id != teacher_id:
        raise AppError(
            kind="forbidden",
            code="access_forbidden",
            detail="Sem permissões para visualizar outro professor",
        )

    return await teacher_service.get_teacher_availability(
        db,
        teacher_id=teacher_id,
        organization_id=current_user.organization_id,
        on_date=on_date,
    )


@router.put(
    "/{teacher_id}/presence",
    response_model=schemas.TeacherPresence,
    responses={403: {"description": "Sem permissões"}, 404: {"description": TEACHER_NOT_FOUND_MSG}},
)
async def update_teacher_presence(
    teacher_id: int,
    presence: schemas.TeacherPresence,
    db: deps.DbSession,
    current_user: deps.AdminActor,
):
    """A direção define a regra de presença de um professor."""
    return await teacher_service.set_teacher_presence(
        db,
        teacher_id,
        presence,
        organization_id=current_user.organization_id,
        changed_by_membership_id=current_user.membership_id,
    )


@router.get(
    "/{teacher_id}/presence",
    response_model=schemas.TeacherPresence,
    responses={403: {"description": "Sem permissões"}, 404: {"description": TEACHER_NOT_FOUND_MSG}},
)
async def read_teacher_presence(
    teacher_id: int,
    db: deps.DbSession,
    current_user: deps.ActiveActor,
):
    """Inspetor read-only da regra de presença para Administrador ou o próprio Professor."""
    is_admin = deps.user_has_admin_capability(current_user)
    if not is_admin and current_user.teacher_id != teacher_id:
        raise AppError(
            kind="forbidden",
            code="access_forbidden",
            detail="Sem permissões para visualizar outro professor",
        )
    return await teacher_service.get_teacher_presence(
        db,
        teacher_id=teacher_id,
        organization_id=current_user.organization_id,
    )


@router.get(
    "/me/progress",
    response_model=list[schemas.TeacherClassProgressRead],
    summary="Progresso curricular do professor autenticado",
    responses={403: {"description": "Sem permissões"}},
)
async def read_my_progress(
    db: deps.DbSession,
    current_user: deps.ActiveActor,
):
    """Retorna o progresso das disciplinas do professor nas turmas assignadas."""
    return await teacher_service.get_teacher_progress(
        db,
        teacher_id=_require_teacher_profile(current_user),
        organization_id=current_user.organization_id,
    )


# --- 1. Ler Professores ---
@router.get("/", response_model=list[schemas.TeacherRead])
async def read_teachers(
    current_user: deps.AdminActor,
    db: deps.DbSession,
    skip: int = 0,
    limit: int = 100,
):
    return await teacher_service.get_teachers_by_org(
        db, organization_id=current_user.organization_id, skip=skip, limit=limit
    )
