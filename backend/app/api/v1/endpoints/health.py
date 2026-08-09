# Ficheiro: app/api/endpoints/health.py

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.ratelimit import limiter

logger = structlog.get_logger(__name__)
router = APIRouter()


async def readiness(
    request: Request,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
):
    health_status = {"status": "ok", "postgres": "unknown", "redis": "unknown"}

    try:
        await db.execute(text("SELECT 1"))
        health_status["postgres"] = "connected"
    except Exception as e:
        health_status["postgres"] = "disconnected"
        health_status["status"] = "error"
        logger.warning("Health check: Postgres disconnected", error=str(e))

    try:
        if await request.app.state.redis.ping():
            health_status["redis"] = "connected"
        else:
            raise ValueError("Ping failed")
    except Exception as e:
        health_status["redis"] = "disconnected"
        health_status["status"] = "error"
        logger.warning("Health check: Redis disconnected", error=str(e))

    if health_status["status"] == "error":
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=health_status,
        )

    return health_status


@router.get("/health", status_code=status.HTTP_200_OK)
@limiter.exempt
async def health_check():
    return {"status": "ok"}
