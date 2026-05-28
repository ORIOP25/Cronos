# Ficheiro: backend/tests/test_subjects_crud.py
"""
TESTES CRUD DE DISCIPLINAS (Subjects)
=====================================
Valida endpoints da API:
- POST /subjects/ (criar com e sem módulos)
- GET /subjects/ (listar)
- PATCH /subjects/{id} (atualizar nome, tipo de sala, módulos)
- DELETE /subjects/{id} (apagar, proteção de dependências)
- 404 para IDs inexistentes
- 422 para payloads inválidos
"""

import pytest
from httpx import AsyncClient
from app.config import settings


API = settings.API_V1_STR


@pytest.mark.asyncio
class TestSubjectsCRUD:

    # ---------- CREATE ----------

    async def test_create_subject_without_modules(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """✅ Criar disciplina sem módulos"""
        payload = {"name": "Matemática", "required_room_type": "normal"}
        resp = await async_client.post(
            f"{API}/subjects/", json=payload, headers=admin_token_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Matemática"
        assert data["required_room_type"] == "normal"
        assert data["modules"] == []

    async def test_create_subject_with_modules(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """✅ Criar disciplina com módulos sequenciais"""
        payload = {
            "name": "Programação",
            "required_room_type": "lab",
            "modules": [
                {"name": "Python Básico", "code": "P001", "hours_total": 40, "order": 0},
                {"name": "Python Avançado", "code": "P002", "hours_total": 30, "order": 1},
            ],
        }
        resp = await async_client.post(
            f"{API}/subjects/", json=payload, headers=admin_token_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["modules"]) == 2
        assert data["modules"][0]["name"] == "Python Básico"
        assert data["modules"][1]["order"] == 1
        assert data["required_room_type"] == "lab"

    async def test_create_subject_invalid_room_type_422(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """❌ Tipo de sala inválido devolve 422"""
        payload = {"name": "X", "required_room_type": "piscina"}
        resp = await async_client.post(
            f"{API}/subjects/", json=payload, headers=admin_token_headers
        )
        assert resp.status_code == 422

    async def test_create_subject_modules_gap_order_422(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """❌ Módulos com ordem não sequencial (0, 2) devolvem 422"""
        payload = {
            "name": "Teste",
            "required_room_type": "normal",
            "modules": [
                {"name": "M1", "code": "T01", "hours_total": 10, "order": 0},
                {"name": "M2", "code": "T02", "hours_total": 10, "order": 2},
            ],
        }
        resp = await async_client.post(
            f"{API}/subjects/", json=payload, headers=admin_token_headers
        )
        assert resp.status_code == 422

    # ---------- READ ----------

    async def test_list_subjects(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """✅ Listar disciplinas da organização"""
        # Criar uma disciplina primeiro
        await async_client.post(
            f"{API}/subjects/",
            json={"name": "Física", "required_room_type": "lab"},
            headers=admin_token_headers,
        )
        resp = await async_client.get(
            f"{API}/subjects/", headers=admin_token_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert any(s["name"] == "Física" for s in data)

    # ---------- UPDATE ----------

    async def test_update_subject_name(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """✅ PATCH do nome da disciplina"""
        create_resp = await async_client.post(
            f"{API}/subjects/",
            json={"name": "Velha", "required_room_type": "normal"},
            headers=admin_token_headers,
        )
        sid = create_resp.json()["id"]

        resp = await async_client.patch(
            f"{API}/subjects/{sid}",
            json={"name": "Nova"},
            headers=admin_token_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Nova"

    async def test_update_subject_modules_gap_order_422(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        create_resp = await async_client.post(
            f"{API}/subjects/",
            json={"name": "Modular", "required_room_type": "normal"},
            headers=admin_token_headers,
        )
        sid = create_resp.json()["id"]

        resp = await async_client.patch(
            f"{API}/subjects/{sid}",
            json={
                "modules": [
                    {"name": "M1", "code": "T01", "hours_total": 10, "order": 0},
                    {"name": "M2", "code": "T02", "hours_total": 10, "order": 2},
                ]
            },
            headers=admin_token_headers,
        )

        assert resp.status_code == 422

    async def test_update_subject_not_found_404(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """❌ PATCH de disciplina inexistente devolve 404"""
        resp = await async_client.patch(
            f"{API}/subjects/99999",
            json={"name": "Fantasma"},
            headers=admin_token_headers,
        )
        assert resp.status_code == 404

    # ---------- DELETE ----------

    async def test_delete_subject(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """✅ Apagar disciplina sem dependências"""
        create_resp = await async_client.post(
            f"{API}/subjects/",
            json={"name": "Descartável", "required_room_type": "normal"},
            headers=admin_token_headers,
        )
        sid = create_resp.json()["id"]

        resp = await async_client.delete(
            f"{API}/subjects/{sid}", headers=admin_token_headers
        )
        assert resp.status_code == 200

        # Confirmar que foi removida
        get_resp = await async_client.get(
            f"{API}/subjects/", headers=admin_token_headers
        )
        ids = [s["id"] for s in get_resp.json()]
        assert sid not in ids

    async def test_delete_subject_not_found_404(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """❌ Apagar disciplina inexistente devolve 404"""
        resp = await async_client.delete(
            f"{API}/subjects/99999", headers=admin_token_headers
        )
        assert resp.status_code == 404
