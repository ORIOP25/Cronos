# Ficheiro: backend/tests/test_health.py
import json
from types import SimpleNamespace

from httpx import AsyncClient

from app.api.v1.endpoints import health as health_module


class _FakeDb:
    def __init__(self, should_fail=False):
        self.should_fail = should_fail

    async def execute(self, _statement):
        if self.should_fail:
            raise RuntimeError("db down")
        return object()


class _FakeRedis:
    def __init__(self, should_ping=True):
        self.should_ping = should_ping

    async def ping(self):
        if isinstance(self.should_ping, Exception):
            raise self.should_ping
        return self.should_ping


def _request(redis):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(redis=redis)))


def _response_payload(response):
    return json.loads(response.body.decode("utf-8"))


async def test_health_check_reports_connected_dependencies():
    response = await health_module.health_check(_request(_FakeRedis()), _FakeDb())

    assert response == {
        "status": "ok",
        "postgres": "connected",
        "redis": "connected",
    }


async def test_health_check_returns_503_when_postgres_fails():
    response = await health_module.health_check(_request(_FakeRedis()), _FakeDb(should_fail=True))

    assert response.status_code == 503
    assert _response_payload(response) == {
        "status": "error",
        "postgres": "disconnected",
        "redis": "connected",
    }


async def test_health_check_returns_503_when_redis_fails():
    response = await health_module.health_check(_request(_FakeRedis(False)), _FakeDb())

    assert response.status_code == 503
    assert _response_payload(response) == {
        "status": "error",
        "postgres": "connected",
        "redis": "disconnected",
    }


async def test_health_check(async_client: AsyncClient):
    async_client._transport.app.state.redis = _FakeRedis()
    response = await async_client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_health_check_not_rate_limited(async_client: AsyncClient):
    """Health endpoint deve permanecer elegivel para probes frequentes sem 429."""
    for _ in range(20):
        response = await async_client.get("/api/v1/health")
        assert response.status_code == 200
