# Ficheiro: app/core/ratelimit.py

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings

# ==========================================
# RATE LIMITER DISTRIBUÍDO
# ==========================================
# key_func: Identifica o utilizador (neste caso, por IP)
# storage_uri: ONDE guardamos a contagem.
#    - Antes: "memory://" (RAM)
#    - Agora: str(settings.REDIS_URL) (Redis)


limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=str(settings.REDIS_URL),
    enabled=settings.RATELIMIT_ENABLED,
    default_limits=["200 per day", "50 per hour"],  # Limites padrão de segurança
)
# SlowAPI reloads this key through Starlette Config without a boolean cast.
limiter.enabled = settings.RATELIMIT_ENABLED
