import pytest
from httpx import ASGITransport, AsyncByteStream, AsyncClient
from limits.storage import MemoryStorage
from limits.strategies import FixedWindowRateLimiter

from app.contact.dependencies import get_contact_service
from app.core.exceptions import AppError
from app.core.ratelimit import limiter
from app.main import app

PAYLOAD = {
    "subject": "Criar horários do zero",
    "courses": "Entre 1 e 5",
    "teachers": "Entre 1 e 15",
    "name": "Ana Coordenadora",
    "email": "ana@escola.pt",
    "phone": "+351 912 345 678",
    "message": "Demonstração",
    "website": "",
    "turnstile_token": "token",
}


class FakeService:
    def __init__(self, failure=None):
        self.failure = failure
        self.calls = []

    async def submit(self, submission, *, remote_ip):
        self.calls.append((submission, remote_ip))
        if self.failure:
            raise self.failure


class ChunkedBody(AsyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk


@pytest.fixture
def fake_service():
    service = FakeService()
    app.dependency_overrides[get_contact_service] = lambda: service
    yield service
    app.dependency_overrides.pop(get_contact_service, None)


@pytest.mark.asyncio
async def test_contact_is_public_and_calls_service(fake_service):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert "/api/v1/contact" in (await client.get("/openapi.json")).json()["paths"]
        response = await client.post("/api/v1/contact", json=PAYLOAD)
    assert response.status_code == 204
    assert len(fake_service.calls) == 1


@pytest.mark.asyncio
async def test_honeypot_is_accepted_with_no_public_signal(fake_service):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/contact", json=PAYLOAD | {"website": "bot"})
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_unexpected_field_returns_422_without_calling_service(fake_service):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/contact", json=PAYLOAD | {"unexpected": True})
    assert response.status_code == 422
    assert fake_service.calls == []


@pytest.mark.asyncio
async def test_legacy_camel_case_turnstile_token_is_rejected(fake_service):
    payload = {key: value for key, value in PAYLOAD.items() if key != "turnstile_token"}
    payload["turnstileToken"] = "legacy-token"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/contact", json=payload)
    assert response.status_code == 422
    assert fake_service.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "code", "status"),
    [
        ("bad_request", "turnstile_rejected", 400),
        ("unavailable", "contact_delivery_unavailable", 503),
    ],
)
async def test_application_errors_are_mapped(kind, code, status):
    failure = AppError(kind=kind, code=code, detail="safe")
    app.dependency_overrides[get_contact_service] = lambda: FakeService(failure)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/contact", json=PAYLOAD)
    finally:
        app.dependency_overrides.pop(get_contact_service, None)
    assert response.status_code == status
    assert response.json() == {"detail": "safe"}


@pytest.mark.asyncio
async def test_content_length_body_limit_rejects_16385_bytes(fake_service):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/contact",
            content=b"x" * 16_385,
            headers={"Content-Type": "application/json"},
        )
    assert response.status_code == 413
    assert fake_service.calls == []


@pytest.mark.asyncio
async def test_exact_limit_is_passed_to_json_parsing(fake_service):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/contact",
            content=b"x" * 16_384,
            headers={"Content-Type": "application/json"},
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chunked_body_without_content_length_is_limited(fake_service):
    stream = ChunkedBody([b"x" * 8_192, b"y" * 8_193])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        request = client.build_request(
            "POST",
            "/api/v1/contact",
            content=stream,
            headers={"Content-Type": "application/json"},
        )
        request.headers.pop("content-length", None)
        response = await client.send(request)
    assert response.status_code == 413


@pytest.mark.asyncio
async def test_body_limit_does_not_apply_to_other_endpoint(fake_service):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/not-contact", content=b"x" * 16_385)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_contact_limit_rejects_sixth_request(fake_service):
    original_storage, original_limiter, original_enabled = (
        limiter._storage,
        limiter._limiter,
        limiter.enabled,
    )
    memory_storage = MemoryStorage()
    limiter._storage = memory_storage
    limiter._limiter = FixedWindowRateLimiter(memory_storage)
    limiter.enabled = True
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app, client=("127.0.0.1", 1234)),
            base_url="http://test",
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
    assert len(fake_service.calls) == 5
