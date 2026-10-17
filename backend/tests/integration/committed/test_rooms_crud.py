# Ficheiro: backend/tests/test_rooms_crud.py
"""
TESTES CRUD DE SALAS (Rooms)
============================
Valida endpoints da API:
- POST /rooms/ (criar com tipo da escola, por defeito Normal)
- GET /rooms/ (listar com o tipo da escola)
- PATCH /rooms/{id} (atualizar nome, tipo e capacidade)
- DELETE /rooms/{id} (apagar, proteção de dependências)
- 404 para IDs inexistentes ou tipos inválidos
"""

from httpx import AsyncClient
from sqlalchemy import select

from app import models
from app.config import settings
from tests.factories import room_type_ids

API = settings.API_V1_STR


class TestRoomsCRUD:
    # ---------- CREATE ----------

    async def test_create_room_normal(self, async_client: AsyncClient, clerk_admin_headers: dict):
        """✅ Criar sala com o tipo Normal da escola"""
        types = await room_type_ids(async_client, clerk_admin_headers)
        payload = {"name": "Sala 101", "room_type_id": types["normal"], "capacity": 30}
        resp = await async_client.post(f"{API}/rooms/", json=payload, headers=clerk_admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Sala 101"
        assert data["room_type"] == {
            "id": types["normal"],
            "name": "Normal",
            "is_normal": True,
        }
        assert data["capacity"] == 30

    async def test_create_room_lab(self, async_client: AsyncClient, clerk_admin_headers: dict):
        """✅ Criar sala do tipo Laboratório"""
        types = await room_type_ids(async_client, clerk_admin_headers)
        payload = {"name": "Laboratório 1", "room_type_id": types["laboratorio"], "capacity": 20}
        resp = await async_client.post(f"{API}/rooms/", json=payload, headers=clerk_admin_headers)
        assert resp.status_code == 200
        assert resp.json()["room_type"]["name"] == "Laboratório"

    async def test_create_room_gym(self, async_client: AsyncClient, clerk_admin_headers: dict):
        """✅ Criar sala do tipo Ginásio"""
        types = await room_type_ids(async_client, clerk_admin_headers)
        payload = {"name": "Ginásio", "room_type_id": types["ginasio"], "capacity": 50}
        resp = await async_client.post(f"{API}/rooms/", json=payload, headers=clerk_admin_headers)
        assert resp.status_code == 200
        assert resp.json()["room_type"]["name"] == "Ginásio"

    async def test_create_room_without_type_defaults_to_normal(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        """✅ Sala sem tipo usa o tipo Normal da escola"""
        resp = await async_client.post(
            f"{API}/rooms/",
            json={"name": "Sala Sem Tipo", "capacity": 30},
            headers=clerk_admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["room_type"]["name"] == "Normal"
        assert resp.json()["room_type"]["is_normal"] is True

    async def test_create_room_invalid_type_422(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        """❌ Tipo de sala que não é um identificador devolve 422"""
        payload = {"name": "Sala Inválida", "room_type_id": "piscina_olímpica"}
        resp = await async_client.post(f"{API}/rooms/", json=payload, headers=clerk_admin_headers)
        assert resp.status_code == 422

    async def test_create_room_missing_name_422(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        """❌ Sala sem nome devolve 422"""
        payload = {"capacity": 30}
        resp = await async_client.post(f"{API}/rooms/", json=payload, headers=clerk_admin_headers)
        assert resp.status_code == 422

    async def test_create_room_invalid_capacity_422(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        """❌ Capacidade zero ou negativa é rejeitada antes de gravar."""
        payload = {"name": "Sala Sem Lugares", "capacity": 0}
        resp = await async_client.post(f"{API}/rooms/", json=payload, headers=clerk_admin_headers)
        assert resp.status_code == 422

    async def test_create_room_rejects_removed_type_key_422(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        """❌ A chave removida `type` devolve 422 e não grava a sala"""
        payload = {"name": "Lab Removida", "type": "lab", "capacity": 20}
        resp = await async_client.post(f"{API}/rooms/", json=payload, headers=clerk_admin_headers)
        assert resp.status_code == 422
        rooms = await async_client.get(f"{API}/rooms/", headers=clerk_admin_headers)
        assert all(room["name"] != "Lab Removida" for room in rooms.json())

    # ---------- READ ----------

    async def test_list_rooms(self, async_client: AsyncClient, clerk_admin_headers: dict):
        """✅ Listar salas da organização"""
        await async_client.post(
            f"{API}/rooms/",
            json={"name": "Sala Listável"},
            headers=clerk_admin_headers,
        )
        resp = await async_client.get(f"{API}/rooms/", headers=clerk_admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert any(r["name"] == "Sala Listável" for r in data)

    # ---------- UPDATE ----------

    async def test_update_room_name(self, async_client: AsyncClient, clerk_admin_headers: dict):
        """✅ Atualizar o nome de uma sala"""
        create = await async_client.post(
            f"{API}/rooms/",
            json={"name": "Velha"},
            headers=clerk_admin_headers,
        )
        rid = create.json()["id"]

        resp = await async_client.patch(
            f"{API}/rooms/{rid}",
            json={"name": "Renovada"},
            headers=clerk_admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Renovada"

    async def test_update_room_type(self, async_client: AsyncClient, clerk_admin_headers: dict):
        """✅ Mudar o tipo de uma sala"""
        types = await room_type_ids(async_client, clerk_admin_headers)
        create = await async_client.post(
            f"{API}/rooms/",
            json={"name": "Mutável"},
            headers=clerk_admin_headers,
        )
        rid = create.json()["id"]

        resp = await async_client.patch(
            f"{API}/rooms/{rid}",
            json={"room_type_id": types["laboratorio"]},
            headers=clerk_admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["room_type"]["name"] == "Laboratório"

    async def test_update_room_invalid_capacity_422(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        """❌ PATCH não permite transformar uma sala válida numa sala inválida."""
        create = await async_client.post(
            f"{API}/rooms/",
            json={"name": "Capacidade", "capacity": 25},
            headers=clerk_admin_headers,
        )
        rid = create.json()["id"]

        resp = await async_client.patch(
            f"{API}/rooms/{rid}",
            json={"capacity": -1},
            headers=clerk_admin_headers,
        )
        assert resp.status_code == 422

    async def test_update_room_not_found_404(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        """❌ PATCH em sala inexistente devolve 404"""
        resp = await async_client.patch(
            f"{API}/rooms/99999",
            json={"name": "Fantasma"},
            headers=clerk_admin_headers,
        )
        assert resp.status_code == 404

    # ---------- DELETE ----------

    async def test_delete_room(self, async_client: AsyncClient, clerk_admin_headers: dict):
        """✅ Apagar sala sem dependências"""
        create = await async_client.post(
            f"{API}/rooms/",
            json={"name": "Descartável"},
            headers=clerk_admin_headers,
        )
        rid = create.json()["id"]

        resp = await async_client.delete(f"{API}/rooms/{rid}", headers=clerk_admin_headers)
        assert resp.status_code == 200

    async def test_delete_room_not_found_404(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        """❌ Apagar sala inexistente devolve 404"""
        resp = await async_client.delete(f"{API}/rooms/99999", headers=clerk_admin_headers)
        assert resp.status_code == 404


async def _create_type(client: AsyncClient, headers: dict, name: str = "Oficina") -> int:
    resp = await client.post(f"{API}/room-types/", json={"name": name}, headers=headers)
    assert resp.status_code == 201
    return resp.json()["id"]


class TestSchoolRoomTypes:
    """S2/R02: a sala usa o tipo da escola, por identificador."""

    async def test_custom_type_room_is_created_and_listed(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        oficina = await _create_type(async_client, clerk_admin_headers)

        resp = await async_client.post(
            f"{API}/rooms/",
            json={"name": "Oficina 1", "room_type_id": oficina, "capacity": 20},
            headers=clerk_admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["room_type"] == {
            "id": oficina,
            "name": "Oficina",
            "is_normal": False,
        }

        listed = await async_client.get(f"{API}/rooms/", headers=clerk_admin_headers)
        room = next(item for item in listed.json() if item["name"] == "Oficina 1")
        assert room["room_type"] == {"id": oficina, "name": "Oficina", "is_normal": False}

    async def test_update_room_type_keeps_the_other_fields(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        types = await room_type_ids(async_client, clerk_admin_headers)
        create = await async_client.post(
            f"{API}/rooms/",
            json={"name": "Polivalente", "capacity": 22},
            headers=clerk_admin_headers,
        )
        rid = create.json()["id"]

        changed = await async_client.patch(
            f"{API}/rooms/{rid}",
            json={"room_type_id": types["ginasio"]},
            headers=clerk_admin_headers,
        )
        assert changed.status_code == 200
        assert changed.json()["name"] == "Polivalente"
        assert changed.json()["capacity"] == 22
        assert changed.json()["room_type"]["name"] == "Ginásio"

        renamed = await async_client.patch(
            f"{API}/rooms/{rid}",
            json={"name": "Polivalente 2"},
            headers=clerk_admin_headers,
        )
        assert renamed.status_code == 200
        assert renamed.json()["room_type"]["name"] == "Ginásio"

    async def test_explicit_null_room_type_falls_back_to_normal(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        types = await room_type_ids(async_client, clerk_admin_headers)
        create = await async_client.post(
            f"{API}/rooms/",
            json={"name": "Sala Móvel", "room_type_id": types["ginasio"]},
            headers=clerk_admin_headers,
        )
        rid = create.json()["id"]

        reset = await async_client.patch(
            f"{API}/rooms/{rid}",
            json={"room_type_id": None},
            headers=clerk_admin_headers,
        )
        assert reset.status_code == 200
        assert reset.json()["room_type"]["name"] == "Normal"

    async def test_unknown_room_type_is_rejected(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        resp = await async_client.post(
            f"{API}/rooms/",
            json={"name": "Sem Dono", "room_type_id": 999999},
            headers=clerk_admin_headers,
        )
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "resource_not_found"

    async def test_archived_room_type_is_rejected(
        self, async_client: AsyncClient, db_session, clerk_admin_headers: dict
    ):
        oficina = await _create_type(async_client, clerk_admin_headers)
        room_type = await db_session.get(models.SchoolRoomType, oficina)
        room_type.is_archived = True
        await db_session.commit()

        resp = await async_client.post(
            f"{API}/rooms/",
            json={"name": "Oficina Arquivada", "room_type_id": oficina},
            headers=clerk_admin_headers,
        )
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "resource_not_found"

    async def test_room_type_of_another_school_is_rejected(
        self, async_client: AsyncClient, db_session, clerk_admin_headers: dict
    ):
        from tests._support.db_fixtures import create_org_and_user

        await create_org_and_user(
            db_session,
            clerk_user_id="rooms_admin_b",
            clerk_org_id="org_rooms_b",
            org_name="Escola Secundária",
        )
        await db_session.commit()
        headers_b = {"Authorization": "Bearer test_rooms_admin_b"}
        foreign_type = await _create_type(async_client, headers_b)

        created = await async_client.post(
            f"{API}/rooms/",
            json={"name": "Sala Isolada", "capacity": 30},
            headers=clerk_admin_headers,
        )
        rid = created.json()["id"]

        resp = await async_client.patch(
            f"{API}/rooms/{rid}",
            json={"room_type_id": foreign_type},
            headers=clerk_admin_headers,
        )
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "resource_not_found"

        current = await db_session.scalar(
            select(models.Room.room_type_id).where(models.Room.id == rid)
        )
        assert current != foreign_type


class TestRoomHomeClasses:
    """S8/T14: a sala lista as turmas ativas que a têm como sala da turma."""

    async def test_room_lists_its_active_home_classes(
        self, async_client: AsyncClient, db_session, clerk_admin_headers: dict
    ):
        course = await async_client.post(
            f"{API}/courses/",
            json={"name": "Curso Salas", "abbreviation": "CSA"},
            headers=clerk_admin_headers,
        )
        course_id = course.json()["id"]
        room = await async_client.post(
            f"{API}/rooms/",
            json={"name": "Sala de Turma", "capacity": 30},
            headers=clerk_admin_headers,
        )
        room_id = room.json()["id"]
        class_ids = []
        for name in ("Turma Ativa", "Turma Arquivada"):
            created = await async_client.post(
                f"{API}/courses/{course_id}/classes",
                json={"name": name, "grade_level": 10, "start_year": 2025, "end_year": 2028},
                headers=clerk_admin_headers,
            )
            class_ids.append(created.json()["id"])
            await async_client.patch(
                f"{API}/courses/{course_id}/classes/{created.json()['id']}",
                json={"home_room_id": room_id},
                headers=clerk_admin_headers,
            )
        archived = await db_session.get(models.Class, class_ids[1])
        archived.is_archived = True
        await db_session.commit()

        listed = await async_client.get(f"{API}/rooms/", headers=clerk_admin_headers)

        assert listed.status_code == 200
        row = next(item for item in listed.json() if item["id"] == room_id)
        assert row["home_classes"] == [{"id": class_ids[0], "name": "Turma Ativa"}]
