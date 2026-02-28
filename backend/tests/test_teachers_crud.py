# Ficheiro: backend/tests/test_teachers_crud.py
"""
TESTES CRUD DE PROFESSORES (Teachers)
=====================================
Valida endpoints da API:
- POST /teachers/ (criar com/sem competências, com/sem conta de acesso)
- GET /teachers/ (listar)
- PATCH /teachers/{id} (atualizar nome, competências)
- DELETE /teachers/{id} (apagar, proteção de dependências)
- 404 para IDs inexistentes
"""

import pytest
from httpx import AsyncClient
from app.config import settings


API = settings.API_V1_STR


@pytest.mark.asyncio
class TestTeachersCRUD:

    # ---------- CREATE ----------

    async def test_create_teacher_minimal(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """✅ Criar professor apenas com nome e email"""
        payload = {
            "name": "Prof. Silva",
            "email": "silva@escola.pt",
        }
        resp = await async_client.post(
            f"{API}/teachers/", json=payload, headers=admin_token_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Prof. Silva"
        assert "id" in data

    async def test_create_teacher_with_competencies(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """✅ Criar professor com competências (disciplinas)"""
        # 1. Criar disciplina primeiro
        sub_resp = await async_client.post(
            f"{API}/subjects/",
            json={"name": "Matemática", "required_room_type": "normal"},
            headers=admin_token_headers,
        )
        sub_id = sub_resp.json()["id"]

        # 2. Criar professor com competência
        payload = {
            "name": "Prof. Costa",
            "email": "costa@escola.pt",
            "subject_ids": [sub_id],
        }
        resp = await async_client.post(
            f"{API}/teachers/", json=payload, headers=admin_token_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert sub_id in data["subject_ids"]

    async def test_create_teacher_with_user_account(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """✅ Criar professor com conta de acesso ativa"""
        payload = {
            "name": "Prof. Ativo",
            "email": "ativo@escola.pt",
            "create_user_account": True,
        }
        resp = await async_client.post(
            f"{API}/teachers/", json=payload, headers=admin_token_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_active"] is True

    async def test_create_teacher_missing_name_422(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """❌ Professor sem nome devolve 422"""
        payload = {"email": "sem_nome@escola.pt"}
        resp = await async_client.post(
            f"{API}/teachers/", json=payload, headers=admin_token_headers
        )
        assert resp.status_code == 422

    # ---------- READ ----------

    async def test_list_teachers(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """✅ Listar professores da organização"""
        await async_client.post(
            f"{API}/teachers/",
            json={"name": "Prof. Lista", "email": "lista@escola.pt"},
            headers=admin_token_headers,
        )
        resp = await async_client.get(
            f"{API}/teachers/", headers=admin_token_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert any(t["name"] == "Prof. Lista" for t in data)

    # ---------- UPDATE ----------

    async def test_update_teacher_name(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """✅ Atualizar nome do professor"""
        create = await async_client.post(
            f"{API}/teachers/",
            json={"name": "Antigo", "email": "antigo@escola.pt"},
            headers=admin_token_headers,
        )
        tid = create.json()["id"]

        resp = await async_client.patch(
            f"{API}/teachers/{tid}",
            json={"name": "Renomeado"},
            headers=admin_token_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Renomeado"

    async def test_update_teacher_competencies(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """✅ Atualizar competências (disciplinas) de um professor"""
        sub1 = await async_client.post(
            f"{API}/subjects/",
            json={"name": "Física", "required_room_type": "lab"},
            headers=admin_token_headers,
        )
        sub2 = await async_client.post(
            f"{API}/subjects/",
            json={"name": "Química", "required_room_type": "lab"},
            headers=admin_token_headers,
        )
        s1_id = sub1.json()["id"]
        s2_id = sub2.json()["id"]

        create = await async_client.post(
            f"{API}/teachers/",
            json={"name": "Prof. Comp", "email": "comp@escola.pt", "subject_ids": [s1_id]},
            headers=admin_token_headers,
        )
        tid = create.json()["id"]

        # Mudar para [s2]
        resp = await async_client.patch(
            f"{API}/teachers/{tid}",
            json={"subject_ids": [s2_id]},
            headers=admin_token_headers,
        )
        assert resp.status_code == 200
        assert s2_id in resp.json()["subject_ids"]
        assert s1_id not in resp.json()["subject_ids"]

    async def test_update_teacher_not_found_404(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """❌ Atualizar professor inexistente devolve 404"""
        resp = await async_client.patch(
            f"{API}/teachers/99999",
            json={"name": "Fantasma"},
            headers=admin_token_headers,
        )
        assert resp.status_code == 404

    # ---------- DELETE ----------

    async def test_delete_teacher(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """✅ Apagar professor sem dependências"""
        create = await async_client.post(
            f"{API}/teachers/",
            json={"name": "Descartável", "email": "desc@escola.pt"},
            headers=admin_token_headers,
        )
        tid = create.json()["id"]

        resp = await async_client.delete(
            f"{API}/teachers/{tid}", headers=admin_token_headers
        )
        assert resp.status_code == 200

    async def test_delete_teacher_not_found_404(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """❌ Apagar professor inexistente devolve 404"""
        resp = await async_client.delete(
            f"{API}/teachers/99999", headers=admin_token_headers
        )
        assert resp.status_code == 404
