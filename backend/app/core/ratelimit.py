"""Distributed request limiting with fail-closed storage handling."""

import structlog
from fastapi import Request
from fastapi.responses import JSONResponse
from limits.errors import StorageError
from slowapi import Limiter
from slowapi.middleware import SlowAPIMiddleware

from app.config import settings
from app.core.client_ip import trusted_remote_address

logger = structlog.get_logger(__name__)

# ==========================================
# RATE LIMITER DISTRIBUÍDO
# ==========================================
# key_func: Identifica o utilizador (neste caso, por IP)
# storage_uri: ONDE guardamos a contagem.
#    - Antes: "memory://" (RAM)
#    - Agora: str(settings.REDIS_URL) (Redis)


limiter = Limiter(
    key_func=trusted_remote_address,
    storage_uri=str(settings.REDIS_URL),
    storage_options={"wrap_exceptions": True},
    enabled=settings.RATELIMIT_ENABLED,
    default_limits=["200 per day", "50 per hour"],  # Limites padrão de segurança
)
# SlowAPI reloads this key through Starlette Config without a boolean cast.
limiter.enabled = settings.RATELIMIT_ENABLED


class FailClosedSlowAPIMiddleware(SlowAPIMiddleware):
    """Return a stable response when Redis cannot enforce a request limit."""

    async def dispatch(self, request: Request, call_next):
        try:
            return await super().dispatch(request, call_next)
        except StorageError as exc:
            logger.error(
                "rate_limit_storage_unavailable",
                error_type=type(exc.storage_error).__name__,
                path=request.url.path,
            )
            return JSONResponse(
                status_code=503,
                content={
                    "detail": {
                        "code": "RATE_LIMIT_UNAVAILABLE",
                        "message": "Request protection is temporarily unavailable.",
                    }
                },
                headers={"Cache-Control": "no-store"},
            )
