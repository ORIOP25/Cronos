import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.requests import Request as StarletteRequest

from app.config import settings
from app.core.ratelimit import limiter, proxy_aware_remote_address

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


def test_proxy_aware_key_uses_header_from_trusted_proxy(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_IPS", "127.0.0.1")
    request = StarletteRequest(
        {
            "type": "http",
            "headers": [(b"x-real-ip", b"2001:0db8::1")],
            "client": ("127.0.0.1", 1234),
        }
    )
    assert proxy_aware_remote_address(request) == "2001:db8::1"


def test_proxy_aware_key_ignores_direct_spoofed_header(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_IPS", "127.0.0.1")
    request = StarletteRequest(
        {
            "type": "http",
            "headers": [(b"x-real-ip", b"198.51.100.1")],
            "client": ("192.0.2.10", 1234),
        }
    )
    assert proxy_aware_remote_address(request) == "192.0.2.10"


def test_proxy_aware_key_rejects_invalid_real_ip(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_IPS", "192.0.2.0/24")
    request = StarletteRequest(
        {"type": "http", "headers": [(b"x-real-ip", b"not-an-ip")], "client": ("192.0.2.10", 1234)}
    )
    assert proxy_aware_remote_address(request) == "192.0.2.10"
