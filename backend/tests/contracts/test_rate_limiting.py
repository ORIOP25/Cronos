import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from limits.errors import StorageError
from limits.storage import RedisStorage
from limits.strategies import FixedWindowRateLimiter
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.core.ratelimit import FailClosedSlowAPIMiddleware, limiter

pytestmark = pytest.mark.redis


async def test_enabled_redis_limit_returns_exact_429():
    test_app = FastAPI()
    test_app.state.limiter = limiter
    test_app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    test_app.add_middleware(SlowAPIMiddleware)

    @test_app.get("/limited")
    @limiter.limit("2/minute")
    async def limited(request: Request):
        return {"ok": True}

    previous_enabled = limiter.enabled
    limiter.enabled = True
    limiter.reset()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://ratelimit.test"
        ) as client:
            assert (await client.get("/limited")).status_code == 200
            assert (await client.get("/limited")).status_code == 200
            assert (await client.get("/limited")).status_code == 429
    finally:
        limiter.enabled = previous_enabled


async def test_redis_failure_returns_stable_503_without_memory_fallback(monkeypatch):
    test_app = FastAPI()
    test_app.state.limiter = limiter
    test_app.add_middleware(FailClosedSlowAPIMiddleware)

    @limiter.limit("2/minute")
    async def limited(request: Request):
        return {"ok": True}

    test_app.add_api_route("/limited", limited, methods=["GET"])
    previous_storage, previous_limiter, previous_enabled = (
        limiter._storage,
        limiter._limiter,
        limiter.enabled,
    )

    class BrokenStorage(RedisStorage):
        def incr(self, *_args, **_kwargs):
            raise StorageError(ConnectionError("redis://secret@redis:6379/0"))

    events = []
    monkeypatch.setattr(
        "app.core.ratelimit.logger.error",
        lambda *args, **kwargs: events.append((args, kwargs)),
    )
    limiter._storage = BrokenStorage("redis://127.0.0.1:9/0")
    limiter._limiter = FixedWindowRateLimiter(limiter._storage)
    limiter.enabled = True
    try:
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://ratelimit.test"
        ) as client:
            response = await client.get("/limited")
    finally:
        limiter._storage, limiter._limiter, limiter.enabled = (
            previous_storage,
            previous_limiter,
            previous_enabled,
        )

    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "code": "RATE_LIMIT_UNAVAILABLE",
            "message": "Request protection is temporarily unavailable.",
        }
    }
    assert "redis://" not in response.text
    assert "redis://" not in repr(events)
