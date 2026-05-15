# Ficheiro: app/api/endpoints/health.py

import redis
import structlog
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.api import deps
from app.config import settings
from app.core.ratelimit import limiter
from typing import Annotated

logger = structlog.get_logger(__name__)
router = APIRouter()

@router.get("/health", status_code=status.HTTP_200_OK)
@limiter.exempt
async def health_check(
    db: Annotated[AsyncSession, Depends(deps.get_db)]
):
    health_status = {
        "status": "ok",
        "postgres": "unknown",
        "redis": "unknown"
    }

    try:
        await db.execute(text("SELECT 1"))
        health_status["postgres"] = "connected"
    except Exception as e:
        health_status["postgres"] = "disconnected"
        health_status["status"] = "error"
        logger.warning("Health check: Postgres disconnected", error=str(e))

    try:
        r = redis.Redis.from_url(str(settings.REDIS_URL), socket_connect_timeout=1)
        if r.ping():
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