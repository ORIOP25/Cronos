"""Endpoint do Dashboard V1 — Command Center para administradores."""

from fastapi import APIRouter

from app import schemas
from app.api import deps
from app.services import dashboard_service

router = APIRouter()


@router.get("/dashboard", response_model=schemas.DashboardResponse)
async def get_dashboard(
    db: deps.DbSession,
    current_user: deps.AdminActor,
):
    """Dashboard V1 — Command Center.

    Agrega alertas operacionais, saúde do horário, progresso curricular,
    contagens de recursos e resumo de dívidas numa única resposta.
    """

    return await dashboard_service.get_dashboard_summary(db, current_user.organization_id)
