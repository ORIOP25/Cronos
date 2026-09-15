from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.api import deps
from app.core.exceptions import AppError
from app.services.session_bootstrap_service import (
    SessionBootstrapError,
    SessionBootstrapService,
)

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.post("/bootstrap", response_model=schemas.SessionBootstrapResponse)
async def bootstrap_session(
    request: Request,
    db: Annotated[AsyncSession, Depends(deps.get_db, scope="function")],
    clerk: deps.ClerkGatewayDep,
    payload: Annotated[dict, Depends(deps.get_clerk_payload)],
):
    try:
        result = await SessionBootstrapService(db, clerk).bootstrap(payload)
        logger.info("session_bootstrap_outcome", outcome="success")
        return result
    except SessionBootstrapError as exc:
        logger.warning(
            "session_bootstrap_outcome",
            outcome=exc.code.lower(),
        )
        kind = {401: "unauthorized", 403: "forbidden"}.get(exc.status_code, "bad_request")
        raise AppError(kind=kind, code=exc.code, detail=str(exc)) from exc
