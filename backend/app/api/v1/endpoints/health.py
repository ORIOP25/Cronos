# Ficheiro: app/api/endpoints/health.py

import redis
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.api import deps
from app.config import settings

router = APIRouter()

@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check(
    db: AsyncSession = Depends(deps.get_db)
):
    """
    Verifica a saúde vital do sistema:
    1. Base de Dados (Postgres)
    2. Cache/Queue (Redis)
    
    Se algum falhar, retorna 503 (Service Unavailable).
    O Render/Kubernetes usa isto para reiniciar containers estragados.
    """
    health_status = {
        "status": "ok",
        "postgres": "unknown",
        "redis": "unknown"
    }
    
    # 1. Testar Postgres (SELECT 1)
    try:
        # Executa uma query simples e rápida
        await db.execute(text("SELECT 1"))
        health_status["postgres"] = "connected"
    except Exception as e:
        health_status["postgres"] = "disconnected"
        health_status["status"] = "error"
        # Log do erro (futuramente usaremos structlog aqui)
        print(f"❌ Health Check falhou no Postgres: {e}")

    # 2. Testar Redis (PING)
    try:
        r = redis.Redis.from_url(str(settings.REDIS_URL), socket_connect_timeout=1)
        if r.ping():
            health_status["redis"] = "connected"
        else:
            raise ValueError("Ping falhou")
    except Exception as e:
        health_status["redis"] = "disconnected"
        health_status["status"] = "error"
        print(f"❌ Health Check falhou no Redis: {e}")

    # Decisão Final
    if health_status["status"] == "error":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=health_status
        )
    
    return health_status