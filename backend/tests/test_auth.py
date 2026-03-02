# Ficheiro: tests/test_auth.py
import pytest
from httpx import AsyncClient
from app.config import settings

API = settings.API_V1_STR


@pytest.mark.asyncio
async def test_register_and_login(async_client: AsyncClient):
    # 1. Registar nova escola (RegisterRequest)
    register_payload = {
        "school_name": "Escola de Testes",
        "admin_name": "Admin Teste",
        "email": "admin@teste.pt",
        "password": "senha_segura_123",
    }
    response = await async_client.post(f"{API}/auth/register", json=register_payload)
    assert response.status_code == 200
    token_data = response.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"
    assert token_data["role"] == "admin"
    assert token_data["organization_name"] == "Escola de Testes"
    assert token_data["teacher_id"] is not None

    # 2. Fazer Login com as mesmas credenciais (OAuth2 form data)
    login_payload = {
        "username": "admin@teste.pt",
        "password": "senha_segura_123",
    }
    response = await async_client.post(f"{API}/auth/token", data=login_payload)
    assert response.status_code == 200
    login_data = response.json()
    assert "access_token" in login_data
    assert login_data["token_type"] == "bearer"
    assert login_data["organization_name"] == "Escola de Testes"
