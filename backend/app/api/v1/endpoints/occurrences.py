"""Endpoints para gestão de ocorrências de aulas (Sprint 2).

Rotas:
  GET  /occurrences/         — listar ocorrências (com filtros)
  GET  /occurrences/debts    — dívidas de horas agrupadas
  GET  /occurrences/{id}/substitutes/recommendations — ranking de elegíveis
  GET  /occurrences/{id}     — detalhe de uma ocorrência
  PATCH /occurrences/{id}    — registar falta (GAP) ou substituição
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app import schemas
from app.api import deps
from app.scheduler.infrastructure import occurrences as occurrences_v1

# Constante reutilizada (SonarQube S1192)
OCCURRENCE_NOT_FOUND_MSG = "Ocorrência não encontrada"

router = APIRouter()


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Rotas
# ---------------------------------------------------------------------------


@router.get(
    "/",
    response_model=schemas.LessonOccurrenceListRead,
    summary="Listar ocorrências de aulas",
)
async def list_occurrences(
    db: deps.DbSession,
    current_user: deps.AdminActor,
    class_id: Annotated[int | None, Query(gt=0, description="Filtrar por turma")] = None,
    date_from: Annotated[date | None, Query(description="Data de início (YYYY-MM-DD)")] = None,
    date_to: Annotated[date | None, Query(description="Data de fim (YYYY-MM-DD)")] = None,
    status: Annotated[
        str | None,
        Query(description="Filtrar por estado: OPEN_PENDING, GIVEN, GAP, SUBSTITUTED, REVOKED"),
    ] = None,
    skip: Annotated[int, Query(ge=0, description="Registos a saltar")] = 0,
    limit: Annotated[int, Query(ge=1, le=500, description="Máximo de registos a devolver")] = 100,
):
    """Devolve ocorrências de aulas com filtros opcionais."""
    organization_id = current_user.organization_id

    return await occurrences_v1.list_occurrences(
        db,
        organization_id,
        class_id=class_id,
        date_from=date_from,
        date_to=date_to,
        status_filter=status,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/debts",
    response_model=schemas.DebtListRead,
    summary="Dívidas de horas de aulas",
)
async def list_debts(
    db: deps.DbSession,
    current_user: deps.AdminActor,
    class_id: Annotated[int | None, Query(description="Filtrar por turma")] = None,
):
    """Devolve as horas em dívida (faltas não recuperadas) agrupadas por turma/disciplina."""
    organization_id = current_user.organization_id

    return await occurrences_v1.get_debts(db, organization_id, class_id=class_id)


@router.get(
    "/{occurrence_id}/substitutes/recommendations",
    response_model=list[schemas.SubstituteRecommendationRead],
    summary="Ranking de elegíveis para substituição",
    responses={
        404: {"description": OCCURRENCE_NOT_FOUND_MSG},
        422: {"description": "Ocorrência sem contexto válido para recomendação"},
    },
)
async def get_substitute_recommendations(
    occurrence_id: int,
    db: deps.DbSession,
    current_user: deps.AdminActor,
):
    organization_id = current_user.organization_id

    return await occurrences_v1.get_substitute_recommendations(db, organization_id, occurrence_id)


@router.get(
    "/{occurrence_id}/substitutes/diagnostics",
    response_model=schemas.SubstituteDiagnosticsRead,
    summary="Diagnóstico de elegibilidade de substitutos",
    responses={404: {"description": OCCURRENCE_NOT_FOUND_MSG}},
)
async def get_substitute_diagnostics(
    occurrence_id: int,
    db: deps.DbSession,
    current_user: deps.AdminActor,
):
    """Devolve candidatos e os motivos estruturados que os excluem."""
    organization_id = current_user.organization_id

    return await occurrences_v1.get_substitute_diagnostics(db, organization_id, occurrence_id)


@router.get(
    "/{occurrence_id}",
    response_model=schemas.LessonOccurrenceRead,
    summary="Detalhe de uma ocorrência",
    responses={404: {"description": OCCURRENCE_NOT_FOUND_MSG}},
)
async def get_occurrence(
    occurrence_id: int,
    db: deps.DbSession,
    current_user: deps.AdminActor,
):
    """Devolve uma ocorrência pelo ID."""
    organization_id = current_user.organization_id

    return await occurrences_v1.get_occurrence(db, organization_id, occurrence_id)


@router.patch(
    "/{occurrence_id}",
    response_model=schemas.LessonOccurrenceRead,
    summary="Registar falta ou substituição",
    responses={
        404: {"description": OCCURRENCE_NOT_FOUND_MSG},
        422: {"description": "Dados inválidos (ex: substituto obrigatório em SUBSTITUTED)"},
        409: {"description": "Transição inválida ou tentativa de sobrescrever histórico"},
    },
)
async def update_occurrence(
    occurrence_id: int,
    payload: schemas.LessonOccurrenceUpdate,
    db: deps.DbSession,
    current_user: deps.AdminActor,
):
    """Permite ao diretor marcar uma ocorrência como GAP ou SUBSTITUTED."""
    organization_id = current_user.organization_id

    return await occurrences_v1.update_occurrence(
        db,
        organization_id,
        occurrence_id,
        payload,
        decided_by_membership_id=current_user.membership_id,
    )


@router.post(
    "/{occurrence_id}/cancel",
    summary="Cancelar uma ocorrência",
    responses={404: {"description": "Ocorrência não encontrada."}},
)
async def cancel_occurrence(
    occurrence_id: int,
    payload: schemas.LessonOccurrenceCancel,
    db: deps.DbSession,
    current_user: deps.AdminActor,
):
    """Cancela uma ocorrência (OPEN ou decidida), revertendo o LessonLog para PENDING."""
    organization_id = current_user.organization_id

    return await occurrences_v1.cancel_occurrence(
        db,
        organization_id,
        occurrence_id,
        version=payload.version,
        reason="ADMINISTRATIVE_REVERSAL",
        cancelled_by_membership_id=current_user.membership_id,
        cancel_completed_substitute_log=payload.cancel_completed_substitute_log,
    )
