# Ficheiro: app/api/endpoints/health.py


import structlog
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api import deps
from app.config import settings
from app.core.ratelimit import limiter

logger = structlog.get_logger(__name__)
router = APIRouter()


async def readiness(
    request: Request,
    db: deps.DbSession,
):
    health_status = {
        "status": "ok",
        "revision": settings.RAILWAY_GIT_COMMIT_SHA or settings.DEPLOYED_REVISION or "unknown",
        "postgres": "unknown",
        "redis": "unknown",
    }

    try:
        await db.execute(text("SELECT 1"))
        health_status["postgres"] = "connected"
    except Exception as e:
        health_status["postgres"] = "disconnected"
        health_status["status"] = "error"
        logger.warning("Health check: Postgres disconnected", error_type=type(e).__name__)

    try:
        if await request.app.state.redis.ping():
            health_status["redis"] = "connected"
        else:
            raise ValueError("Ping failed")
    except Exception as e:
        health_status["redis"] = "disconnected"
        health_status["status"] = "error"
        logger.warning("Health check: Redis disconnected", error_type=type(e).__name__)

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
