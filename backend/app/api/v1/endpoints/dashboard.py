"""Endpoint do Dashboard V1 â€” Command Center para administradores."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.api import deps
from app.services import dashboard_service
from app.services.school_readiness_service import SchoolReadinessService

router = APIRouter()


@router.get("/dashboard", response_model=schemas.DashboardResponse)
async def get_dashboard(
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: deps.AdminActor,
):
    """Dashboard V1 â€” Command Center.

    Agrega alertas operacionais, saÃºde do horÃ¡rio, progresso curricular,
    contagens de recursos e resumo de dÃ­vidas numa Ãºnica resposta.
    """

    bases = None
    organization = await db.get(models.Organization, current_user.organization_id)
    if organization is not None and organization.first_real_schedule_approved_at is None:
        bases = await SchoolReadinessService(db).evaluate_bases(current_user.organization_id)

    def _run(sync_db):
        return dashboard_service.get_dashboard_summary_sync(
            sync_db,
            current_user.organization_id,
            bases=bases,
        )

    return await db.run_sync(_run)
