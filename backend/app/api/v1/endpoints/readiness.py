"""Readiness endpoints for school bases and pure prevalidation."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app import models, schemas
from app.api import deps
from app.core.exceptions import AppError
from app.services.preflight_service import PreflightService
from app.services.scheduler_state_service import SchedulerStateService
from app.services.school_readiness_service import SchoolReadinessService

router = APIRouter()


@router.get("/bases", response_model=schemas.BasesReadinessResponse)
async def get_bases_readiness(
    db: deps.DbSession,
    current_user: deps.AdminActor,
):
    """Calcula a prontidão das Bases Escolares em cadeia cumulativa de 7 níveis."""
    service = SchoolReadinessService(db)
    return await service.evaluate_bases(current_user.organization_id)


@router.get("/prevalidation", response_model=schemas.PreflightReport)
async def get_prevalidation(
    db: deps.DbSession,
    current_user: deps.AdminActor,
    fingerprint: Annotated[
        str | None,
        Query(description="Token de concorrência opcional para deteção de estado obsoleto."),
    ] = None,
):
    """Executa a pré-validação pura antes da geração de horários (zero writes)."""
    state_service = SchedulerStateService(db)
    active_school_year = await state_service.get_active_school_year(current_user.organization_id)
    if active_school_year is None:
        return schemas.PreflightReport(
            status="BLOCKED",
            fingerprint=None,
            issues=[
                schemas.PreflightIssue(
                    code="ACTIVE_SCHOOL_YEAR_REQUIRED",
                    severity="BLOCKER",
                    message="Defina o ano letivo ativo antes de gerar.",
                    route="/config",
                )
            ],
        )

    preflight_service = PreflightService(db)
    initial_report = await preflight_service.evaluate(
        organization_id=current_user.organization_id,
        school_year_id=active_school_year.id,
        strategy=models.ScheduleGenerationStrategy.COMPLETE_GENERATION,
    )

    if fingerprint is not None and fingerprint != initial_report.fingerprint:
        raise AppError(
            kind="conflict",
            code="PREFLIGHT_STALE",
            detail="O estado da escola foi alterado. Recalcule a prontidão das bases.",
        )

    return initial_report
