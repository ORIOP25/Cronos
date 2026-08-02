# Ficheiro: app/core/ratelimit.py

import ipaddress

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

def _is_trusted_proxy(peer: str | None) -> bool:
    if not peer:
        return False
    try:
        peer_address = ipaddress.ip_address(peer)
    except ValueError:
        return False
    return any(
        peer_address in ipaddress.ip_network(candidate.strip(), strict=False)
        for candidate in settings.TRUSTED_PROXY_IPS.split(",")
        if candidate.strip()
    )


def proxy_aware_remote_address(request) -> str:
    peer = request.client.host if request.client else None
    real_ip = request.headers.get("X-Real-IP")
    if real_ip and _is_trusted_proxy(peer):
        try:
            return str(ipaddress.ip_address(real_ip))
        except ValueError:
            pass
    return peer or get_remote_address(request)


limiter = Limiter(
    key_func=proxy_aware_remote_address,
    storage_uri=str(settings.REDIS_URL),
    enabled=settings.RATELIMIT_ENABLED,
    default_limits=["200 per day", "50 per hour"],  # Limites padrão de segurança
)
# SlowAPI reloads this key through Starlette Config without a boolean cast.
limiter.enabled = settings.RATELIMIT_ENABLED
