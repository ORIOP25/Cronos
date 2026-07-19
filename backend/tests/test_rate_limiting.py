import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.core.ratelimit import limiter

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
