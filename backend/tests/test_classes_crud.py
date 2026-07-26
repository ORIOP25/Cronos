# Ficheiro: backend/tests/test_classes_crud.py
"""
TESTES CRUD DE TURMAS (Classes)
===============================
Valida endpoints da API:
- POST /classes/ (criar turma com curso obrigatório)
- GET /classes/ (listar)
- GET /classes/{id} (detalhe completo com progresso)
- PATCH /classes/{id} (atualizar)
- DELETE /classes/{id} (apagar)
- Validação de year range, curso inexistente, 404, 422
"""

from httpx import AsyncClient

from app.config import settings

API = settings.API_V1_STR


async def _create_course(client: AsyncClient, headers: dict, name: str = "TGPSI") -> int:
    """Helper: cria um curso e devolve o ID."""
    resp = await client.post(
        f"{API}/courses/",
        json={"name": f"Curso {name}", "abbreviation": name},
        headers=headers,
    )
    assert resp.status_code == 200
    return resp.json()["id"]


class TestClassesCRUD:
    # ---------- CREATE ----------

    async def test_create_class(self, async_client: AsyncClient, clerk_admin_headers: dict):
        """✅ Criar turma com curso válido"""
        course_id = await _create_course(async_client, clerk_admin_headers)
        payload = {
            "name": "Turma A",
            "course_id": course_id,
            "grade_level": 10,
            "start_year": 2025,
            "end_year": 2028,
        }
        resp = await async_client.post(f"{API}/classes/", json=payload, headers=clerk_admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Turma A"
        assert data["course_id"] == course_id
        assert data["grade_level"] == 10

    async def test_create_class_custom_size(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        """✅ Criar turma com tamanho personalizado"""
        course_id = await _create_course(async_client, clerk_admin_headers)
        payload = {
            "name": "Turma B",
            "course_id": course_id,
            "grade_level": 11,
            "start_year": 2025,
            "end_year": 2028,
            "size": 30,
        }
        resp = await async_client.post(f"{API}/classes/", json=payload, headers=clerk_admin_headers)
        assert resp.status_code == 200
        assert resp.json()["size"] == 30

    async def test_create_class_invalid_year_range_422(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        """❌ end_year <= start_year devolve 422 (validação Pydantic)"""
        course_id = await _create_course(async_client, clerk_admin_headers)
        payload = {
            "name": "Turma Inválida",
            "course_id": course_id,
            "grade_level": 10,
            "start_year": 2025,
            "end_year": 2025,
        }
        resp = await async_client.post(f"{API}/classes/", json=payload, headers=clerk_admin_headers)
        assert resp.status_code == 422

    async def test_create_class_course_not_found_404(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        """❌ Curso inexistente devolve 404"""
        payload = {
            "name": "Turma Orfã",
            "course_id": 99999,
            "grade_level": 10,
            "start_year": 2025,
            "end_year": 2028,
        }
        resp = await async_client.post(f"{API}/classes/", json=payload, headers=clerk_admin_headers)
        assert resp.status_code == 404

    async def test_create_class_invalid_grade_422(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        """❌ grade_level fora de [10, 12] devolve 422"""
        course_id = await _create_course(async_client, clerk_admin_headers)
        payload = {
            "name": "Turma Grade",
            "course_id": course_id,
            "grade_level": 9,  # Inválido: mínimo é 10
            "start_year": 2025,
            "end_year": 2028,
        }
        resp = await async_client.post(f"{API}/classes/", json=payload, headers=clerk_admin_headers)
        assert resp.status_code == 422

    # ---------- READ ----------

    async def test_list_classes(self, async_client: AsyncClient, clerk_admin_headers: dict):
        """✅ Listar turmas da organização"""
        course_id = await _create_course(async_client, clerk_admin_headers)
        await async_client.post(
            f"{API}/classes/",
            json={
                "name": "Turma Lista",
                "course_id": course_id,
                "grade_level": 10,
                "start_year": 2025,
                "end_year": 2028,
            },
            headers=clerk_admin_headers,
        )
        resp = await async_client.get(f"{API}/classes/", headers=clerk_admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert any(c["name"] == "Turma Lista" for c in data)

    async def test_get_class_full_detail(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        """✅ Obter detalhe completo da turma (ClassFullDetailRead)"""
        course_id = await _create_course(async_client, clerk_admin_headers)
        create_resp = await async_client.post(
            f"{API}/classes/",
            json={
                "name": "Turma Detalhe",
                "course_id": course_id,
                "grade_level": 10,
                "start_year": 2025,
                "end_year": 2028,
            },
            headers=clerk_admin_headers,
        )
        class_id = create_resp.json()["id"]

        resp = await async_client.get(f"{API}/classes/{class_id}", headers=clerk_admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Turma Detalhe"
        assert "subjects" in data
        assert "course" in data

    async def test_get_class_not_found_404(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        """❌ Turma inexistente devolve 404"""
        resp = await async_client.get(f"{API}/classes/99999", headers=clerk_admin_headers)
        assert resp.status_code == 404

    # ---------- UPDATE ----------

    async def test_update_class_name(self, async_client: AsyncClient, clerk_admin_headers: dict):
        """✅ Atualizar nome da turma"""
        course_id = await _create_course(async_client, clerk_admin_headers)
        create = await async_client.post(
            f"{API}/classes/",
            json={
                "name": "Antigo",
                "course_id": course_id,
                "grade_level": 10,
                "start_year": 2025,
                "end_year": 2028,
            },
            headers=clerk_admin_headers,
        )
        class_id = create.json()["id"]

        resp = await async_client.patch(
            f"{API}/classes/{class_id}",
            json={"name": "Renomeada"},
            headers=clerk_admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Renomeada"

    async def test_update_class_invalid_year_range_400(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        """❌ Atualizar com end_year <= start_year devolve 400"""
        course_id = await _create_course(async_client, clerk_admin_headers)
        create = await async_client.post(
            f"{API}/classes/",
            json={
                "name": "Turma",
                "course_id": course_id,
                "grade_level": 10,
                "start_year": 2025,
                "end_year": 2028,
            },
            headers=clerk_admin_headers,
        )
        class_id = create.json()["id"]

        resp = await async_client.patch(
            f"{API}/classes/{class_id}",
            json={"start_year": 2026, "end_year": 2026},
            headers=clerk_admin_headers,
        )
        # A service layer valida e devolve "INVALID_YEAR_RANGE" → 400
        assert resp.status_code == 400

    async def test_update_class_partial_year_range_invalid_400(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        """PATCH parcial não pode deixar end_year <= start_year."""
        course_id = await _create_course(async_client, clerk_admin_headers)
        create = await async_client.post(
            f"{API}/classes/",
            json={
                "name": "Turma Parcial",
                "course_id": course_id,
                "grade_level": 10,
                "start_year": 2025,
                "end_year": 2028,
            },
            headers=clerk_admin_headers,
        )
        class_id = create.json()["id"]

        resp = await async_client.patch(
            f"{API}/classes/{class_id}",
            json={"end_year": 2025},
            headers=clerk_admin_headers,
        )

        assert resp.status_code == 400

    async def test_update_class_not_found_404(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        """❌ Turma inexistente devolve 404"""
        resp = await async_client.patch(
            f"{API}/classes/99999",
            json={"name": "Fantasma"},
            headers=clerk_admin_headers,
        )
        assert resp.status_code == 404

    # ---------- DELETE ----------

    async def test_delete_class(self, async_client: AsyncClient, clerk_admin_headers: dict):
        """✅ Apagar turma com sucesso"""
        course_id = await _create_course(async_client, clerk_admin_headers)
        create = await async_client.post(
            f"{API}/classes/",
            json={
                "name": "Descartável",
                "course_id": course_id,
                "grade_level": 10,
                "start_year": 2025,
                "end_year": 2028,
            },
            headers=clerk_admin_headers,
        )
        class_id = create.json()["id"]

        resp = await async_client.delete(f"{API}/classes/{class_id}", headers=clerk_admin_headers)
        assert resp.status_code == 200

    async def test_delete_class_not_found_404(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        """❌ Apagar turma inexistente devolve 404"""
        resp = await async_client.delete(f"{API}/classes/99999", headers=clerk_admin_headers)
        assert resp.status_code == 404
