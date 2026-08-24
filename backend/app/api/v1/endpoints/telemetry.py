"""Telemetry endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.api import deps
from app.core.ratelimit import limiter
from app.services.tutorial_telemetry_service import TutorialTelemetryService

router = APIRouter(tags=["telemetry"])


@router.post(
    "/tutorial/telemetry",
    status_code=status.HTTP_204_NO_CONTENT,
)
@limiter.limit("60/minute")
async def record_tutorial_telemetry(
    request: Request,
    event: schemas.TutorialTelemetryEventCreate,
    current_user: deps.FoundationAdminActor,
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
) -> Response:
    """Registo de evento de telemetria do tutorial (append-only)."""
    await TutorialTelemetryService.record(
        db,
        organization_id=current_user.organization_id,
        event=event,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
