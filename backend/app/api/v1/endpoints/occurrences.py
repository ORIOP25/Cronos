"""Endpoints para gestÃ£o de ocorrÃªncias de aulas (Sprint 2).

Rotas:
    POST /occurrences/        â€” criar/reutilizar ocorrÃªncia por bloco planeado
  GET  /occurrences/         â€” listar ocorrÃªncias (com filtros)
  GET  /occurrences/debts    â€” dÃ­vidas de horas agrupadas
    GET  /occurrences/observability/summary â€” contadores operacionais por organizaÃ§Ã£o
    GET  /occurrences/{id}/substitutes/recommendations â€” ranking de elegÃ­veis
  GET  /occurrences/{id}     â€” detalhe de uma ocorrÃªncia
  PATCH /occurrences/{id}    â€” registar falta (GAP) ou substituiÃ§Ã£o
  GET  /occurrences/substitutes â€” professores disponÃ­veis num slot/data
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.api import deps
from app.core.exceptions import AppError, status_code_for_kind
from app.services import occurrence_service

# Constante reutilizada (SonarQube S1192)
OCCURRENCE_NOT_FOUND_MSG = "OcorrÃªncia nÃ£o encontrada"

router = APIRouter()


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Rotas
# ---------------------------------------------------------------------------


@router.get(
    "/",
    response_model=schemas.LessonOccurrenceListRead,
    summary="Listar ocorrÃªncias de aulas",
)
async def list_occurrences(
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.AdminActor,
    class_id: Annotated[int | None, Query(gt=0, description="Filtrar por turma")] = None,
    date_from: Annotated[date | None, Query(description="Data de inÃ­cio (YYYY-MM-DD)")] = None,
    date_to: Annotated[date | None, Query(description="Data de fim (YYYY-MM-DD)")] = None,
    status: Annotated[
        str | None,
        Query(description="Filtrar por estado: OPEN_PENDING, GIVEN, GAP, SUBSTITUTED, REVOKED"),
    ] = None,
    skip: Annotated[int, Query(ge=0, description="Registos a saltar")] = 0,
    limit: Annotated[int, Query(ge=1, le=500, description="MÃ¡ximo de registos a devolver")] = 100,
):
    """Devolve ocorrÃªncias de aulas com filtros opcionais."""
    organization_id = current_user.organization_id

    def _run(sync_db):
        return occurrence_service.list_occurrences_sync(
            sync_db,
            organization_id,
            class_id=class_id,
            date_from=date_from,
            date_to=date_to,
            skip=skip,
            limit=limit,
            status_filter=status,
            as_page=True,
        )

    try:
        return await db.run_sync(_run)
    except AppError:
        raise


@router.post(
    "/",
    response_model=schemas.LessonOccurrenceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Criar ocorrÃªncia operacional por bloco planeado",
    responses={
        404: {"description": "Bloco planeado nÃ£o encontrado"},
        409: {"description": "Bloco invÃ¡lido para criaÃ§Ã£o operacional"},
        422: {"description": "Contexto de bloco invÃ¡lido"},
    },
)
async def create_occurrence(
    payload: schemas.LessonOccurrenceCreate,
    response: Response,
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.AdminActor,
):
    """Executa comando CREATE_OCCURRENCE (cria/reutiliza) para um bloco do horÃ¡rio."""
    organization_id = current_user.organization_id

    def _run(sync_db):
        return occurrence_service.create_occurrence_from_active_block_sync(
            sync_db,
            organization_id=organization_id,
            active_schedule_block_id=payload.active_schedule_block_id,
            created_by_membership_id=current_user.membership_id,
            creation_source=payload.mode,
            reason=occurrence_service.OCCURRENCE_REPORTED,
        )

    try:
        occurrence, created_now = await db.run_sync(_run)
    except AppError as exc:
        error_status = status_code_for_kind(exc.kind, exc.code)
        error_detail = exc.detail

        def _emit_failure(sync_db):
            occurrence_service.log_occurrence_event_safe_sync(
                sync_db,
                organization_id=organization_id,
                event_type=occurrence_service.OBS_EVENT_CREATE,
                result=occurrence_service.classify_occurrence_error_result(error_status),
                actor_membership_id=current_user.membership_id,
                occurrence_id=None,
                active_schedule_block_id=payload.active_schedule_block_id,
                detail=f"{error_detail} (active_schedule_block_id={payload.active_schedule_block_id})",
            )

        await db.run_sync(_emit_failure)
        raise

    if not created_now:
        response.status_code = status.HTTP_200_OK

    def _emit_success(sync_db):
        occurrence_service.log_occurrence_event_safe_sync(
            sync_db,
            organization_id=organization_id,
            event_type=occurrence_service.OBS_EVENT_CREATE,
            result=occurrence_service.OBS_RESULT_SUCCESS,
            actor_membership_id=current_user.membership_id,
            occurrence_id=occurrence.id,
            active_schedule_block_id=occurrence.active_schedule_block_id,
            detail=None,
        )

    await db.run_sync(_emit_success)
    return occurrence


@router.get(
    "/debts",
    response_model=schemas.DebtListRead,
    summary="DÃ­vidas de horas de aulas",
)
async def list_debts(
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.AdminActor,
    class_id: Annotated[int | None, Query(description="Filtrar por turma")] = None,
):
    """Devolve as horas em dÃ­vida (faltas nÃ£o recuperadas) agrupadas por turma/disciplina."""
    organization_id = current_user.organization_id

    def _run(sync_db):
        return occurrence_service.get_debts_sync(sync_db, organization_id, class_id=class_id)

    return await db.run_sync(_run)


@router.get(
    "/observability/summary",
    response_model=schemas.OccurrenceObservabilitySummaryRead,
    summary="Resumo de observabilidade operacional de ocorrÃªncias",
)
async def get_occurrence_observability_summary(
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.AdminActor,
    window_days: Annotated[
        int, Query(ge=1, le=90, description="Janela de agregaÃ§Ã£o em dias")
    ] = 7,
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
    summary="Professores disponÃ­veis para substituiÃ§Ã£o",
    responses={404: {"description": "Timeslot nÃ£o encontrado"}},
)
async def list_available_substitutes(
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.AdminActor,
    timeslot_id: Annotated[int, Query(description="ID do timeslot afetado")],
    target_date: Annotated[date, Query(description="Data da aula (YYYY-MM-DD)")],
):
    """Devolve professores da organizaÃ§Ã£o que estÃ£o disponÃ­veis num dado timeslot/data."""
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
    summary="Ranking de elegÃ­veis para substituiÃ§Ã£o",
    responses={
        404: {"description": OCCURRENCE_NOT_FOUND_MSG},
        422: {"description": "OcorrÃªncia sem contexto vÃ¡lido para recomendaÃ§Ã£o"},
    },
)
async def get_substitute_recommendations(
    occurrence_id: int,
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.AdminActor,
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
    except AppError:
        raise


@router.get(
    "/{occurrence_id}",
    response_model=schemas.LessonOccurrenceRead,
    summary="Detalhe de uma ocorrÃªncia",
    responses={404: {"description": OCCURRENCE_NOT_FOUND_MSG}},
)
async def get_occurrence(
    occurrence_id: int,
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.AdminActor,
):
    """Devolve uma ocorrÃªncia pelo ID."""
    organization_id = current_user.organization_id

    def _run(sync_db):
        return occurrence_service.get_occurrence_sync(sync_db, occurrence_id, organization_id)

    return await db.run_sync(_run)


@router.patch(
    "/{occurrence_id}",
    response_model=schemas.LessonOccurrenceRead,
    summary="Registar falta ou substituiÃ§Ã£o",
    responses={
        404: {"description": OCCURRENCE_NOT_FOUND_MSG},
        422: {"description": "Dados invÃ¡lidos (ex: substituto obrigatÃ³rio em SUBSTITUTED)"},
        409: {"description": "TransiÃ§Ã£o invÃ¡lida ou tentativa de sobrescrever histÃ³rico"},
    },
)
async def update_occurrence(
    occurrence_id: int,
    payload: schemas.LessonOccurrenceUpdate,
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.AdminActor,
):
    """Permite ao diretor marcar uma ocorrÃªncia como GAP ou SUBSTITUTED."""
    organization_id = current_user.organization_id

    def _run(sync_db):
        return occurrence_service.update_occurrence_sync(
            sync_db,
            occurrence_id,
            organization_id,
            payload,
            decided_by_membership_id=current_user.membership_id,
        )

    try:
        updated = await db.run_sync(_run)
    except AppError as exc:
        error_status = status_code_for_kind(exc.kind, exc.code)
        error_detail = exc.detail

        def _emit_failure(sync_db):
            occurrence_service.log_occurrence_event_safe_sync(
                sync_db,
                organization_id=organization_id,
                event_type=occurrence_service.OBS_EVENT_DECIDE,
                result=occurrence_service.classify_occurrence_error_result(error_status),
                actor_membership_id=current_user.membership_id,
                occurrence_id=occurrence_id,
                active_schedule_block_id=None,
                detail=error_detail,
            )

        await db.run_sync(_emit_failure)
        raise

    def _emit_success(sync_db):
        occurrence_service.log_occurrence_event_safe_sync(
            sync_db,
            organization_id=organization_id,
            event_type=occurrence_service.OBS_EVENT_DECIDE,
            result=occurrence_service.OBS_RESULT_SUCCESS,
            actor_membership_id=current_user.membership_id,
            occurrence_id=updated.id,
            active_schedule_block_id=updated.active_schedule_block_id,
            decision_status=updated.status,
            detail=None,
        )

    await db.run_sync(_emit_success)

    return updated


@router.post(
    "/{occurrence_id}/cancel",
    summary="Cancelar uma ocorrÃªncia",
    responses={404: {"description": "OcorrÃªncia nÃ£o encontrada."}},
)
async def cancel_occurrence(
    occurrence_id: int,
    payload: schemas.LessonOccurrenceCancel,
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    current_user: deps.AdminActor,
):
    """Cancela uma ocorrÃªncia (OPEN ou decidida), revertendo o LessonLog para PENDING."""
    organization_id = current_user.organization_id

    def _run(sync_db):
        return occurrence_service.cancel_occurrence_sync(
            sync_db,
            organization_id=organization_id,
            occurrence_id=occurrence_id,
            cancelled_by_membership_id=current_user.membership_id,
            version=payload.version,
            reason=occurrence_service.ADMINISTRATIVE_REVERSAL,
            cancel_completed_substitute_log=payload.cancel_completed_substitute_log,
        )

    try:
        return await db.run_sync(_run)
    except AppError:
        raise
