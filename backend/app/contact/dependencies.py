"""FastAPI dependency construction for the contact use case."""

from typing import Annotated

import httpx
from fastapi import Depends, Request

from app.config import settings
from app.contact.resend_gateway import ResendContactEmailGateway
from app.contact.service import ContactApplicationService
from app.contact.turnstile_verifier import CloudflareTurnstileVerifier


def get_http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client


def get_contact_service(
    request: Request,
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
) -> ContactApplicationService:
    resend_key = settings.RESEND_API_KEY.get_secret_value() if settings.RESEND_API_KEY else ""
    turnstile_key = (
        settings.TURNSTILE_SECRET_KEY.get_secret_value() if settings.TURNSTILE_SECRET_KEY else ""
    )
    raw_request_id = request.headers.get("x-request-id", "").strip()
    request_id = raw_request_id[:128] or None
    return ContactApplicationService(
        verifier=CloudflareTurnstileVerifier(
            client,
            secret_key=turnstile_key,
            allowed_hostnames=set(settings.TURNSTILE_ALLOWED_HOSTNAMES_LIST),
            timeout_seconds=settings.TURNSTILE_TIMEOUT_SECONDS,
            request_id=request_id,
        ),
        email_gateway=ResendContactEmailGateway(
            client,
            api_key=resend_key,
            email_from=str(settings.CONTACT_EMAIL_FROM),
            email_to=str(settings.CONTACT_EMAIL_TO),
            timeout_seconds=settings.CONTACT_EMAIL_TIMEOUT_SECONDS,
            request_id=request_id,
        ),
    )


ContactServiceDep = Annotated[ContactApplicationService, Depends(get_contact_service)]
