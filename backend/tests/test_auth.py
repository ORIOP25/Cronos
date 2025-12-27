# Ficheiro: tests/test_auth.py
import pytest
from httpx import AsyncClient
from app.config import settings

# Marca o teste como Async (obrigatório para FastAPI)
@pytest.mark.asyncio
async def test_create_user_and_login(async_client: AsyncClient):
    # 1. Criar Utilizador (Register)
    payload = {"email": "test@escola.com", "password": "teste"}
    response = await async_client.post(f"{settings.API_V1_STR}/auth/register", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "test@escola.com"
    assert "id" in data
    
    # 2. Fazer Login (Token)
    login_payload = {
        "username": "test@escola.com", # O OAuth2 espera 'username', não 'email'
        "password": "teste"
    }
    # Nota: O endpoint de token espera Form Data, não JSON
    response = await async_client.post(f"{settings.API_V1_STR}/auth/token", data=login_payload)
    
    assert response.status_code == 200
    token_data = response.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"