"""Endpoints para gestão de ocorrências de aulas (Sprint 2).

Rotas:
    POST /occurrences/        — criar/reutilizar ocorrência por bloco planeado
  GET  /occurrences/         — listar ocorrências (com filtros)
  GET  /occurrences/debts    — dívidas de horas agrupadas
    GET  /occurrences/observability/summary — contadores operacionais por organização
    GET  /occurrences/{id}/substitutes/recommendations — ranking de elegíveis
  GET  /occurrences/{id}     — detalhe de uma ocorrência
  PATCH /occurrences/{id}    — registar falta (GAP) ou substituição
  GET  /occurrences/substitutes — professores disponíveis num slot/data
"""
from __future__ import annotations

from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app import models, schemas
from app.services import occurrence_service

# Constante reutilizada (SonarQube S1192)
OCCURRENCE_NOT_FOUND_MSG = "Ocorrência não encontrada"

router = APIRouter()


# ---------------------------------------------------------------------------
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
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
    class_id: Optional[int] = Query(None, description="Filtrar por turma"),
    date_from: Optional[date] = Query(None, description="Data de início (YYYY-MM-DD)"),
    date_to: Optional[date] = Query(None, description="Data de fim (YYYY-MM-DD)"),
    status: Optional[str] = Query(None, description="Filtrar por estado: OPEN, GIVEN, GAP, SUBSTITUTED"),
    skip: int = Query(0, ge=0, description="Registos a saltar"),
    limit: int = Query(100, ge=1, le=500, description="Máximo de registos a devolver"),
):
    """Devolve ocorrências de aulas com filtros opcionais."""
    organization_id = current_user.organization_id

    def _run(sync_db):
        return occurrence_service.list_occurrences_sync(
            sync_db, organization_id, class_id=class_id, date_from=date_from, date_to=date_to,
            skip=skip, limit=limit, status_filter=status,
        )

    return await db.run_sync(_run)


@router.post(
    "/",
    response_model=schemas.LessonOccurrenceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Criar ocorrência operacional por bloco planeado",
    responses={
        404: {"description": "Bloco planeado não encontrado"},
        409: {"description": "Bloco inválido para criação operacional"},
        422: {"description": "Contexto de bloco inválido"},
    },
)
async def create_occurrence(
    payload: schemas.LessonOccurrenceCreate,
    response: Response,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
):
    """Executa comando CREATE_OCCURRENCE (cria/reutiliza) para um bloco do horário."""
    organization_id = current_user.organization_id

    def _run(sync_db):
        return occurrence_service.create_occurrence_from_block_sync(
            sync_db,
            organization_id=organization_id,
            schedule_output_id=payload.schedule_output_id,
        )

    try:
        occurrence, created_now = await db.run_sync(_run)
    except occurrence_service.OccurrenceServiceError as exc:
        def _emit_failure(sync_db):
            occurrence_service.log_occurrence_event_safe_sync(
                sync_db,
                organization_id=organization_id,
                event_type=occurrence_service.OBS_EVENT_CREATE,
                result=occurrence_service.classify_occurrence_error_result(exc.status_code),
                actor_user_id=current_user.id,
                occurrence_id=None,
                schedule_output_id=None,
                detail=f"{exc.detail} (schedule_output_id={payload.schedule_output_id})",
            )

        await db.run_sync(_emit_failure)
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    if not created_now:
        response.status_code = status.HTTP_200_OK

    def _emit_success(sync_db):
        occurrence_service.log_occurrence_event_safe_sync(
            sync_db,
            organization_id=organization_id,
            event_type=occurrence_service.OBS_EVENT_CREATE,
            result=occurrence_service.OBS_RESULT_SUCCESS,
            actor_user_id=current_user.id,
            occurrence_id=occurrence.id,
            schedule_output_id=occurrence.schedule_output_id,
            detail=None,
        )

    await db.run_sync(_emit_success)
    return occurrence


@router.get(
    "/debts",
    response_model=schemas.DebtListRead,
    summary="Dívidas de horas de aulas",
)
async def list_debts(
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
    class_id: Optional[int] = Query(None, description="Filtrar por turma"),
):
    """Devolve as horas em dívida (faltas não recuperadas) agrupadas por turma/disciplina."""
    organization_id = current_user.organization_id

    def _run(sync_db):
        return occurrence_service.get_debts_sync(sync_db, organization_id, class_id=class_id)

    return await db.run_sync(_run)


@router.get(
    "/observability/summary",
    response_model=schemas.OccurrenceObservabilitySummaryRead,
    summary="Resumo de observabilidade operacional de ocorrências",
)
async def get_occurrence_observability_summary(
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
    window_days: int = Query(7, ge=1, le=90, description="Janela de agregação em dias"),
):
    organization_id = current_user.organization_id

    def _run(sync_db):
        return occurrence_service.get_occurrence_observability_summary_sync(
            sync_db,
            organization_id=organization_id,
            window_days=window_days,
        )

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
    organization_id = current_user.organization_id

    def _run(sync_db):
        return occurrence_service.get_available_substitutes_sync(
            sync_db, organization_id, timeslot_id, target_date
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
    organization_id = current_user.organization_id

    def _run(sync_db):
        return occurrence_service.get_substitute_recommendations_sync(
            sync_db,
            organization_id=organization_id,
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
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
):
    """Devolve uma ocorrência pelo ID."""
    organization_id = current_user.organization_id

    def _run(sync_db):
        return occurrence_service.get_occurrence_sync(sync_db, occurrence_id, organization_id)

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
    organization_id = current_user.organization_id

    def _run(sync_db):
        return occurrence_service.update_occurrence_sync(
            sync_db,
            occurrence_id,
            organization_id,
            payload,
            decided_by_user_id=current_user.id,
        )

    try:
        updated = await db.run_sync(_run)
    except occurrence_service.OccurrenceServiceError as exc:
        def _emit_failure(sync_db):
            occurrence_service.log_occurrence_event_safe_sync(
                sync_db,
                organization_id=organization_id,
                event_type=occurrence_service.OBS_EVENT_DECIDE,
                result=occurrence_service.classify_occurrence_error_result(exc.status_code),
                actor_user_id=current_user.id,
                occurrence_id=occurrence_id,
                schedule_output_id=None,
                detail=exc.detail,
            )

        await db.run_sync(_emit_failure)
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    def _emit_success(sync_db):
        occurrence_service.log_occurrence_event_safe_sync(
            sync_db,
            organization_id=organization_id,
            event_type=occurrence_service.OBS_EVENT_DECIDE,
            result=occurrence_service.OBS_RESULT_SUCCESS,
            actor_user_id=current_user.id,
            occurrence_id=updated.id,
            schedule_output_id=updated.schedule_output_id,
            decision_status=updated.status,
            detail=None,
        )

    await db.run_sync(_emit_success)

    return updated


@router.post(
    "/{occurrence_id}/cancel",
    summary="Cancelar uma ocorrência",
    responses={404: {"description": "Ocorrência não encontrada."}},
)
async def cancel_occurrence(
    occurrence_id: int,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
):
    """Cancela uma ocorrência (OPEN ou decidida), revertendo o LessonLog para PENDING."""
    organization_id = current_user.organization_id

    def _run(sync_db):
        return occurrence_service.cancel_occurrence_sync(
            sync_db,
            organization_id=organization_id,
            occurrence_id=occurrence_id,
            cancelled_by_user_id=current_user.id,
        )

    try:
        return await db.run_sync(_run)
    except occurrence_service.OccurrenceServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
