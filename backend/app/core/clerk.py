from functools import lru_cache
from clerk_backend_api import Clerk
from clerk_backend_api.security.types import AuthenticateRequestOptions, RequestState, AuthStatus
from app.config import settings


@lru_cache()
def get_clerk_sdk() -> Clerk:
    return Clerk(bearer_auth=settings.CLERK_SECRET_KEY)


def verify_clerk_request(request) -> RequestState:
    sdk = get_clerk_sdk()
    return sdk.authenticate_request(
        request,
        AuthenticateRequestOptions(
            authorized_parties=[settings.FRONTEND_URL],
        ),
    )
