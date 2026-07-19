from __future__ import annotations

from clerk_backend_api import Clerk
from clerk_backend_api.security.types import AuthenticateRequestOptions, RequestState

from app.config import settings


class ClerkGateway:
    """One lifecycle-owned async Clerk SDK context."""

    def __init__(self, sdk: Clerk | None = None) -> None:
        self.sdk = sdk or Clerk(bearer_auth=settings.CLERK_SECRET_KEY)

    async def __aenter__(self) -> ClerkGateway:
        await self.sdk.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        await self.sdk.__aexit__(exc_type, exc, traceback)

    async def authenticate_request(self, request) -> RequestState:
        return await self.sdk.authenticate_request_async(
            request,
            AuthenticateRequestOptions(
                authorized_parties=settings.CLERK_AUTHORIZED_PARTIES_LIST,
            ),
        )


def get_clerk_sdk() -> Clerk:
    """Compatibility seam for isolated scripts and tests.

    API and worker code must pass a lifecycle-owned ``ClerkGateway`` instead.
    """
    return Clerk(bearer_auth=settings.CLERK_SECRET_KEY)


async def verify_clerk_request(
    request,
    gateway: ClerkGateway | None = None,
) -> RequestState:
    if gateway is not None:
        return await gateway.authenticate_request(request)
    # Compatibility for direct unit calls which do not start FastAPI lifespan.
    sdk = get_clerk_sdk()
    return await sdk.authenticate_request_async(
        request,
        AuthenticateRequestOptions(
            authorized_parties=settings.CLERK_AUTHORIZED_PARTIES_LIST,
        ),
    )
