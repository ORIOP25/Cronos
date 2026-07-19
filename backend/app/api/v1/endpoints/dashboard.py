"""Endpoint do Dashboard V1 â€” Command Center para administradores."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.api import deps
from app.services import dashboard_service

router = APIRouter()


@router.get("/dashboard", response_model=schemas.DashboardV1Response)
async def get_dashboard(
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: deps.AdminActor,
):
    """Dashboard V1 â€” Command Center.

    Agrega alertas operacionais, saÃºde do horÃ¡rio, progresso curricular,
    contagens de recursos e resumo de dÃ­vidas numa Ãºnica resposta.
    """

    def _run(sync_db):
        return dashboard_service.get_dashboard_summary_sync(
            sync_db,
            current_user.organization_id,
        )

    return await db.run_sync(_run)
