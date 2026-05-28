# Ficheiro: backend/tests/test_health.py
import json

import pytest
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

    def ping(self):
        if isinstance(self.should_ping, Exception):
            raise self.should_ping
        return self.should_ping


def _response_payload(response):
    return json.loads(response.body.decode("utf-8"))


@pytest.mark.asyncio
async def test_health_check_reports_connected_dependencies(monkeypatch):
    monkeypatch.setattr(
        health_module.redis.Redis,
        "from_url",
        lambda *_args, **_kwargs: _FakeRedis(should_ping=True),
    )

    response = await health_module.health_check(_FakeDb())

    assert response == {
        "status": "ok",
        "postgres": "connected",
        "redis": "connected",
    }


@pytest.mark.asyncio
async def test_health_check_returns_503_when_postgres_fails(monkeypatch):
    monkeypatch.setattr(
        health_module.redis.Redis,
        "from_url",
        lambda *_args, **_kwargs: _FakeRedis(should_ping=True),
    )

    response = await health_module.health_check(_FakeDb(should_fail=True))

    assert response.status_code == 503
    assert _response_payload(response) == {
        "status": "error",
        "postgres": "disconnected",
        "redis": "connected",
    }


@pytest.mark.asyncio
async def test_health_check_returns_503_when_redis_fails(monkeypatch):
    monkeypatch.setattr(
        health_module.redis.Redis,
        "from_url",
        lambda *_args, **_kwargs: _FakeRedis(should_ping=False),
    )

    response = await health_module.health_check(_FakeDb())

    assert response.status_code == 503
    assert _response_payload(response) == {
        "status": "error",
        "postgres": "connected",
        "redis": "disconnected",
    }


@pytest.mark.asyncio
async def test_health_check(async_client: AsyncClient):
    """
    Verifica se a rota de saúde /health responde.
    Nota: Em testes, o Redis pode falhar se não estiver mockado ou presente,
    por isso aceitamos 200 (OK) ou 503 (Serviço Indisponível), 
    desde que a API responda JSON válido.
    """
    response = await async_client.get("/api/v1/health")
    # Em ambiente local sem Redis, 503 é aceitável
    assert response.status_code in (200, 503), (
        f"Health check falhou com {response.status_code}: {response.text}"
    )
    data = response.json()
    assert "status" in data


@pytest.mark.asyncio
async def test_health_check_not_rate_limited(async_client: AsyncClient):
    """Health endpoint deve permanecer elegivel para probes frequentes sem 429."""
    for _ in range(20):
        response = await async_client.get("/api/v1/health")
        assert response.status_code in (200, 503)
