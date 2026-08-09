import pytest
from httpx import ASGITransport, AsyncClient
from limits.storage import MemoryStorage
from limits.strategies import FixedWindowRateLimiter

from app.core.exceptions import AppError
from app.core.ratelimit import limiter
from app.main import app
from app.services import contact_email_service

PAYLOAD = {
    "subject": "Criar hor?rios do zero",
    "courses": "Entre 1 e 5",
    "teachers": "Entre 1 e 15",
    "name": "Ana Coordenadora",
    "email": "ana@escola.pt",
    "phone": "+351 912 345 678",
    "message": "Demonstra??o",
    "website": "",
}


@pytest.mark.asyncio
async def test_contact_is_public_and_calls_service(monkeypatch):
    calls = []

    async def sent(submission):
        calls.append(submission)

    monkeypatch.setattr(contact_email_service, "send_contact_email", sent)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert "/api/v1/contact" in (await client.get("/openapi.json")).json()["paths"]
        response = await client.post("/api/v1/contact", json=PAYLOAD)
    assert response.status_code == 204 and len(calls) == 1


@pytest.mark.asyncio
async def test_invalid_payload_does_not_send(monkeypatch):
    async def sent(_):
        raise AssertionError("must not send")

    monkeypatch.setattr(contact_email_service, "send_contact_email", sent)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = PAYLOAD | {"website": "bot"}
        assert (await client.post("/api/v1/contact", json=payload)).status_code == 422


@pytest.mark.asyncio
async def test_service_error_has_safe_503_envelope(monkeypatch):
    async def fail(_):
        raise AppError(
            kind="unavailable",
            code="contact_delivery_unavailable",
            detail="safe",
            metadata={"code": "contact_delivery_unavailable", "message": "safe", "retryable": True},
        )

    monkeypatch.setattr(contact_email_service, "send_contact_email", fail)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/contact", json=PAYLOAD)
    assert response.status_code == 503
    assert response.json() == {
        "detail": {"code": "contact_delivery_unavailable", "message": "safe", "retryable": True}
    }


@pytest.mark.asyncio
async def test_contact_limit_is_per_client_and_rejects_sixth_request(monkeypatch):
    original_storage, original_limiter, original_enabled = (
        limiter._storage,
        limiter._limiter,
        limiter.enabled,
    )
    memory_storage = MemoryStorage()
    limiter._storage = memory_storage
    limiter._limiter = FixedWindowRateLimiter(memory_storage)
    limiter.enabled = True
    deliveries = []

    async def sent(submission):
        deliveries.append(submission)

    monkeypatch.setattr(contact_email_service, "send_contact_email", sent)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app, client=("127.0.0.1", 1234)), base_url="http://test"
        ) as client:
            for _ in range(5):
                assert (await client.post("/api/v1/contact", json=PAYLOAD)).status_code == 204
            assert (await client.post("/api/v1/contact", json=PAYLOAD)).status_code == 429
    finally:
        limiter._storage, limiter._limiter, limiter.enabled = (
            original_storage,
            original_limiter,
            original_enabled,
        )

    assert len(deliveries) == 5
