# Ficheiro: backend/tests/test_rooms_crud.py
"""
TESTES CRUD DE SALAS (Rooms)
============================
Valida endpoints da API:
- POST /rooms/ (criar com tipos válidos/inválidos)
- GET /rooms/ (listar)
- PATCH /rooms/{id} (atualizar)
- DELETE /rooms/{id} (apagar, proteção de dependências)
- 404 para IDs inexistentes
"""

import pytest
from httpx import AsyncClient
from app.config import settings


API = settings.API_V1_STR


@pytest.mark.asyncio
class TestRoomsCRUD:

    # ---------- CREATE ----------

    async def test_create_room_normal(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """✅ Criar sala do tipo 'normal'"""
        payload = {"name": "Sala 101", "type": "normal", "capacity": 30}
        resp = await async_client.post(
            f"{API}/rooms/", json=payload, headers=admin_token_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Sala 101"
        assert data["type"] == "normal"
        assert data["capacity"] == 30

    async def test_create_room_lab(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """✅ Criar sala do tipo 'lab'"""
        payload = {"name": "Laboratório 1", "type": "lab", "capacity": 20}
        resp = await async_client.post(
            f"{API}/rooms/", json=payload, headers=admin_token_headers
        )
        assert resp.status_code == 200
        assert resp.json()["type"] == "lab"

    async def test_create_room_gym(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """✅ Criar sala do tipo 'gym'"""
        payload = {"name": "Ginásio", "type": "gym", "capacity": 50}
        resp = await async_client.post(
            f"{API}/rooms/", json=payload, headers=admin_token_headers
        )
        assert resp.status_code == 200
        assert resp.json()["type"] == "gym"

    async def test_create_room_invalid_type_422(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """❌ Tipo de sala inválido devolve 422"""
        payload = {"name": "Sala Inválida", "type": "piscina_olímpica"}
        resp = await async_client.post(
            f"{API}/rooms/", json=payload, headers=admin_token_headers
        )
        assert resp.status_code == 422

    async def test_create_room_missing_name_422(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """❌ Sala sem nome devolve 422"""
        payload = {"type": "normal"}
        resp = await async_client.post(
            f"{API}/rooms/", json=payload, headers=admin_token_headers
        )
        assert resp.status_code == 422

    # ---------- READ ----------

    async def test_list_rooms(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """✅ Listar salas da organização"""
        await async_client.post(
            f"{API}/rooms/",
            json={"name": "Sala Listável", "type": "normal"},
            headers=admin_token_headers,
        )
        resp = await async_client.get(
            f"{API}/rooms/", headers=admin_token_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert any(r["name"] == "Sala Listável" for r in data)

    # ---------- UPDATE ----------

    async def test_update_room_name(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """✅ Atualizar o nome de uma sala"""
        create = await async_client.post(
            f"{API}/rooms/",
            json={"name": "Velha", "type": "normal"},
            headers=admin_token_headers,
        )
        rid = create.json()["id"]

        resp = await async_client.patch(
            f"{API}/rooms/{rid}",
            json={"name": "Renovada"},
            headers=admin_token_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Renovada"

    async def test_update_room_type(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """✅ Mudar o tipo de uma sala"""
        create = await async_client.post(
            f"{API}/rooms/",
            json={"name": "Mutável", "type": "normal"},
            headers=admin_token_headers,
        )
        rid = create.json()["id"]

        resp = await async_client.patch(
            f"{API}/rooms/{rid}",
            json={"type": "lab"},
            headers=admin_token_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["type"] == "lab"

    async def test_update_room_not_found_404(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """❌ PATCH em sala inexistente devolve 404"""
        resp = await async_client.patch(
            f"{API}/rooms/99999",
            json={"name": "Fantasma"},
            headers=admin_token_headers,
        )
        assert resp.status_code == 404

    # ---------- DELETE ----------

    async def test_delete_room(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """✅ Apagar sala sem dependências"""
        create = await async_client.post(
            f"{API}/rooms/",
            json={"name": "Descartável", "type": "art"},
            headers=admin_token_headers,
        )
        rid = create.json()["id"]

        resp = await async_client.delete(
            f"{API}/rooms/{rid}", headers=admin_token_headers
        )
        assert resp.status_code == 200

    async def test_delete_room_not_found_404(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """❌ Apagar sala inexistente devolve 404"""
        resp = await async_client.delete(
            f"{API}/rooms/99999", headers=admin_token_headers
        )
        assert resp.status_code == 404
