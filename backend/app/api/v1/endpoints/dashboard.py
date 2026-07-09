"""Endpoint do Dashboard V1 — Command Center para administradores."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.api import deps
from app.services import dashboard_service

router = APIRouter()


@router.get("/dashboard", response_model=schemas.DashboardV1Response)
async def get_dashboard(
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_admin)],
):
    """Dashboard V1 — Command Center.

    Agrega alertas operacionais, saúde do horário, progresso curricular,
    contagens de recursos e resumo de dívidas numa única resposta.
    """

    def _run(sync_db):
        return dashboard_service.get_dashboard_summary_sync(
            sync_db,
            current_user.organization_id,
        )

    return await db.run_sync(_run)
