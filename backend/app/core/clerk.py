import asyncio
from functools import lru_cache
from clerk_backend_api import Clerk
from clerk_backend_api.security.types import AuthenticateRequestOptions, RequestState
from app.config import settings


@lru_cache()
def get_clerk_sdk() -> Clerk:
    return Clerk(bearer_auth=settings.CLERK_SECRET_KEY)


def _verify_clerk_request_sync(request) -> RequestState:
    """Validação síncrona interna — NÃO usar diretamente em endpoints async."""
    sdk = get_clerk_sdk()
    return sdk.authenticate_request(
        request,
        AuthenticateRequestOptions(
            authorized_parties=[settings.FRONTEND_URL],
        ),
    )


async def verify_clerk_request(request) -> RequestState:
    """Valida o token Clerk de um request HTTP de forma não-bloqueante."""
    return await asyncio.to_thread(_verify_clerk_request_sync, request)
