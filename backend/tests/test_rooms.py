import pytest
from httpx import AsyncClient
from app.config import settings

@pytest.mark.asyncio
async def test_create_room(authorized_client: AsyncClient):
    # 1. Criar Sala (TIPO VÁLIDO)
    payload = {"name": "Sala 101", "type": "normal"} # Usa string, o Pydantic valida
    response = await authorized_client.post(f"{settings.API_V1_STR}/rooms/", json=payload)

    # --- DETETIVE ---
    if response.status_code != 200:
        print("\n⚠️ ERRO NO SERVIDOR:", response.json())  # <--- Isto vai mostrar o erro no terminal
    
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Sala 101"
    assert data["type"] == "normal"

@pytest.mark.asyncio
async def test_create_room_invalid_type(authorized_client: AsyncClient):
    # 2. Criar Sala (TIPO INVÁLIDO) - Deve falhar!
    payload = {"name": "Sala Errada", "type": "sala_de_jogos"} 
    response = await authorized_client.post(f"{settings.API_V1_STR}/rooms/", json=payload)
    
    # O Pydantic deve rejeitar e devolver 422 (Unprocessable Entity)
    assert response.status_code == 422