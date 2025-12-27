import pytest
from httpx import AsyncClient
from app.config import settings

@pytest.mark.asyncio
async def test_create_and_list_teachers(authorized_client: AsyncClient):
    # 1. Criar um Professor
    payload = {"name": "Professor Snape"}
    response = await authorized_client.post(f"{settings.API_V1_STR}/teachers/", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Professor Snape"
    assert "id" in data
    
    # 2. Listar Professores
    response = await authorized_client.get(f"{settings.API_V1_STR}/teachers/")
    assert response.status_code == 200
    lista = response.json()
    
    assert len(lista) == 1
    assert lista[0]["name"] == "Professor Snape"