# Ficheiro: backend/tests/test_health.py
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_health_check(async_client: AsyncClient):
    """
    Verifica se a rota de saúde /health responde.
    Nota: Em testes, o Redis pode falhar se não estiver mockado ou presente,
    por isso aceitamos 200 (OK) ou 503 (Serviço Indisponível), 
    desde que a API responda JSON válido.
    """
    response = await async_client.get("/api/v1/health")
    
    # A API está viva, mesmo que o Redis de teste não esteja lá
    assert response.status_code in [200, 503]
    
    data = response.json()
    assert "status" in data


@pytest.mark.asyncio
async def test_health_check_not_rate_limited(async_client: AsyncClient):
    """Health endpoint deve permanecer elegivel para probes frequentes sem 429."""
    for _ in range(60):
        response = await async_client.get("/api/v1/health")
        assert response.status_code in [200, 503]