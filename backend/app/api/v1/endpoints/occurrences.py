"""Endpoints para gestão de ocorrências de aulas (Sprint 2).

Rotas:
  GET  /occurrences/         — listar ocorrências (com filtros)
  GET  /occurrences/debts    — dívidas de horas agrupadas
    GET  /occurrences/{id}/substitutes/recommendations — ranking de elegíveis
  GET  /occurrences/{id}     — detalhe de uma ocorrência
  PATCH /occurrences/{id}    — registar falta (GAP) ou substituição
  GET  /occurrences/substitutes — professores disponíveis num slot/data
"""
from __future__ import annotations

from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app import models, schemas
from app.services import occurrence_service
from app.db.database import SessionLocalSync

# Constante reutilizada (SonarQube S1192)
OCCURRENCE_NOT_FOUND_MSG = "Ocorrência não encontrada"

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers síncronos executados via run_sync
# ---------------------------------------------------------------------------

def _get_sync_db():
    """Cria uma sessão síncrona para as operações do serviço."""
    db = SessionLocalSync()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Rotas
# ---------------------------------------------------------------------------

@router.get(
    "/",
    response_model=list[schemas.LessonOccurrenceRead],
    summary="Listar ocorrências de aulas",
)
async def list_occurrences(
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_user)],
    class_id: Optional[int] = Query(None, description="Filtrar por turma"),
    date_from: Optional[date] = Query(None, description="Data de início (YYYY-MM-DD)"),
    date_to: Optional[date] = Query(None, description="Data de fim (YYYY-MM-DD)"),
):
    """Devolve ocorrências de aulas com filtros opcionais."""
    org_id = current_user.organization_id

    def _run(sync_db):
        return occurrence_service.list_occurrences_sync(
            sync_db, org_id, class_id=class_id, date_from=date_from, date_to=date_to
        )

    return await db.run_sync(_run)


@router.get(
    "/debts",
    response_model=schemas.DebtListRead,
    summary="Dívidas de horas de aulas",
)
async def list_debts(
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_user)],
    class_id: Optional[int] = Query(None, description="Filtrar por turma"),
):
    """Devolve as horas em dívida (faltas não recuperadas) agrupadas por turma/disciplina."""
    org_id = current_user.organization_id

    def _run(sync_db):
        return occurrence_service.get_debts_sync(sync_db, org_id, class_id=class_id)

    return await db.run_sync(_run)


@router.get(
    "/substitutes",
    response_model=list[schemas.AvailableSubstituteRead],
    summary="Professores disponíveis para substituição",
    responses={404: {"description": "Timeslot não encontrado"}},
)
async def list_available_substitutes(
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
    timeslot_id: int = Query(..., description="ID do timeslot afetado"),
    target_date: date = Query(..., description="Data da aula (YYYY-MM-DD)"),
):
    """Devolve professores da organização que estão disponíveis num dado timeslot/data."""
    org_id = current_user.organization_id

    def _run(sync_db):
        return occurrence_service.get_available_substitutes_sync(
            sync_db, org_id, timeslot_id, target_date
        )

    results = await db.run_sync(_run)
    return results


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
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
):
    org_id = current_user.organization_id

    def _run(sync_db):
        return occurrence_service.get_substitute_recommendations_sync(
            sync_db,
            org_id=org_id,
            occurrence_id=occurrence_id,
        )

    try:
        return await db.run_sync(_run)
    except occurrence_service.OccurrenceServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get(
    "/{occurrence_id}",
    response_model=schemas.LessonOccurrenceRead,
    summary="Detalhe de uma ocorrência",
    responses={404: {"description": OCCURRENCE_NOT_FOUND_MSG}},
)
async def get_occurrence(
    occurrence_id: int,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_user)],
):
    """Devolve uma ocorrência pelo ID."""
    org_id = current_user.organization_id

    def _run(sync_db):
        return occurrence_service.get_occurrence_sync(sync_db, occurrence_id, org_id)

    occurrence = await db.run_sync(_run)
    if occurrence is None:
        raise HTTPException(status_code=404, detail=OCCURRENCE_NOT_FOUND_MSG)
    return occurrence


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
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
):
    """Permite ao diretor marcar uma ocorrência como GAP ou SUBSTITUTED."""
    org_id = current_user.organization_id

    def _run(sync_db):
        return occurrence_service.update_occurrence_sync(
            sync_db,
            occurrence_id,
            org_id,
            payload,
            decided_by_user_id=current_user.id,
        )

    try:
        updated = await db.run_sync(_run)
    except occurrence_service.OccurrenceServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    return updated
