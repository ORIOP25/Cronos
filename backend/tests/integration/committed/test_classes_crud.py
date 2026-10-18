# Ficheiro: backend/tests/test_classes_crud.py
"""
TESTES CRUD DE TURMAS (Classes)
===============================
Valida endpoints da API:
- POST /courses/{course_id}/classes (criar turma)
- GET /classes/ (listar)
- GET /classes/{id} (detalhe completo com progresso)
- PATCH /courses/{course_id}/classes/{id} (atualizar)
- DELETE /courses/{course_id}/classes/{id} (apagar)
- Validação de year range, curso inexistente, 404, 422
"""

from datetime import date

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.config import settings
from app.services import room_type_service
from tests._support.db_fixtures import get_school_room_type_id
from tests.factories import room_type_ids

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
            "grade_level": 10,
            "start_year": 2025,
            "end_year": 2028,
        }
        resp = await async_client.post(
            f"{API}/courses/{course_id}/classes", json=payload, headers=clerk_admin_headers
        )
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
            "grade_level": 11,
            "start_year": 2025,
            "end_year": 2028,
            "size": 30,
        }
        resp = await async_client.post(
            f"{API}/courses/{course_id}/classes", json=payload, headers=clerk_admin_headers
        )
        assert resp.status_code == 200
        assert resp.json()["size"] == 30

    async def test_create_class_invalid_year_range_422(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        """❌ end_year <= start_year devolve 422 (validação Pydantic)"""
        course_id = await _create_course(async_client, clerk_admin_headers)
        payload = {
            "name": "Turma Inválida",
            "grade_level": 10,
            "start_year": 2025,
            "end_year": 2025,
        }
        resp = await async_client.post(
            f"{API}/courses/{course_id}/classes", json=payload, headers=clerk_admin_headers
        )
        assert resp.status_code == 422

    async def test_create_class_course_not_found_404(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        """❌ Curso inexistente devolve 404"""
        payload = {
            "name": "Turma Orfã",
            "grade_level": 10,
            "start_year": 2025,
            "end_year": 2028,
        }
        resp = await async_client.post(
            f"{API}/courses/99999/classes", json=payload, headers=clerk_admin_headers
        )
        assert resp.status_code == 404

    async def test_create_class_invalid_grade_422(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        """❌ grade_level fora de [10, 12] devolve 422"""
        course_id = await _create_course(async_client, clerk_admin_headers)
        payload = {
            "name": "Turma Grade",
            "grade_level": 9,  # Inválido: mínimo é 10
            "start_year": 2025,
            "end_year": 2028,
        }
        resp = await async_client.post(
            f"{API}/courses/{course_id}/classes", json=payload, headers=clerk_admin_headers
        )
        assert resp.status_code == 422

    # ---------- READ ----------

    async def test_list_classes(
        self,
        async_client: AsyncClient,
        clerk_admin_headers: dict,
        db_session: AsyncSession,
    ):
        """✅ Listar turmas da organização esconde as arquivadas."""
        course_id = await _create_course(async_client, clerk_admin_headers)
        archived = await async_client.post(
            f"{API}/courses/{course_id}/classes",
            json={
                "name": "Turma Arquivada",
                "grade_level": 10,
                "start_year": 2025,
                "end_year": 2028,
            },
            headers=clerk_admin_headers,
        )
        await async_client.post(
            f"{API}/courses/{course_id}/classes",
            json={
                "name": "Turma Ativa",
                "grade_level": 11,
                "start_year": 2025,
                "end_year": 2028,
            },
            headers=clerk_admin_headers,
        )
        school_class = await db_session.get(models.Class, archived.json()["id"])
        school_class.is_archived = True
        await db_session.commit()

        resp = await async_client.get(f"{API}/classes/", headers=clerk_admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        names = [c["name"] for c in data]
        assert "Turma Arquivada" not in names
        assert "Turma Ativa" in names

    async def test_get_class_full_detail(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        """✅ Obter detalhe completo da turma (ClassFullDetailRead)"""
        course_id = await _create_course(async_client, clerk_admin_headers)
        create_resp = await async_client.post(
            f"{API}/courses/{course_id}/classes",
            json={
                "name": "Turma Detalhe",
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

    async def test_get_class_full_detail_fractional_hours(
        self,
        async_client: AsyncClient,
        clerk_admin_headers: dict,
        db_session: AsyncSession,
    ):
        """✅ Valida cálculo de horas fracionárias e percentagem (50 min em módulo de 25h = 3.3%)"""
        course_id = await _create_course(async_client, clerk_admin_headers)
        create_resp = await async_client.post(
            f"{API}/courses/{course_id}/classes",
            json={
                "name": "Turma Progresso Fracionário",
                "grade_level": 10,
                "start_year": 2025,
                "end_year": 2028,
            },
            headers=clerk_admin_headers,
        )
        assert create_resp.status_code == 200
        class_id = create_resp.json()["id"]

        db_class = await db_session.get(models.Class, class_id)
        assert db_class is not None
        org_id = db_class.organization_id

        subject = models.Subject(
            name="Tecnologias Web",
            organization_id=org_id,
            room_type_id=await get_school_room_type_id(db_session, org_id, "Normal"),
        )
        db_session.add(subject)
        await db_session.flush()

        module = models.Module(
            subject_id=subject.id,
            name="Introdução ao HTML/CSS",
            code="MOD-01",
            hours_total=25,
            required_minutes=1500,
            order=1,
            organization_id=org_id,
        )
        db_session.add(module)
        await db_session.flush()

        link = models.ClassSubjectLink(
            class_id=class_id,
            subject_id=subject.id,
            grade_level=10,
            organization_id=org_id,
        )
        db_session.add(link)
        await db_session.flush()
        # WBS 2.2.2: the dashboard progress counts only selected modules.
        await db_session.execute(
            models.class_subject_module.insert().values(
                organization_id=org_id,
                class_subject_link_id=link.id,
                module_id=module.id,
            )
        )

        entry = models.ProgressLedgerEntry(
            organization_id=org_id,
            source_type="lesson_log",
            source_id=1,
            class_id=class_id,
            module_id=module.id,
            completed_minutes_delta=50,
            debt_minutes_delta=0,
            idempotency_key="test-ledger-50min",
        )
        db_session.add(entry)
        await db_session.commit()

        resp = await async_client.get(f"{API}/classes/{class_id}", headers=clerk_admin_headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert len(data["subjects"]) == 1
        subj_data = data["subjects"][0]
        assert subj_data["name"] == "Tecnologias Web"
        assert subj_data["total_hours"] == 25.0
        assert subj_data["completed_hours"] == 0.8
        assert subj_data["overall_percentage"] == 3.3

        assert len(subj_data["modules"]) == 1
        mod_data = subj_data["modules"][0]
        assert mod_data["hours_total"] == 25.0
        assert mod_data["hours_completed"] == 0.8
        assert mod_data["percentage"] == 3.3

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
            f"{API}/courses/{course_id}/classes",
            json={
                "name": "Antigo",
                "grade_level": 10,
                "start_year": 2025,
                "end_year": 2028,
            },
            headers=clerk_admin_headers,
        )
        class_id = create.json()["id"]

        resp = await async_client.patch(
            f"{API}/courses/{course_id}/classes/{class_id}",
            json={"name": "Renomeada"},
            headers=clerk_admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Renomeada"

    async def test_update_class_invalid_year_range_422(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        """❌ Atualizar com end_year <= start_year devolve 422"""
        course_id = await _create_course(async_client, clerk_admin_headers)
        create = await async_client.post(
            f"{API}/courses/{course_id}/classes",
            json={
                "name": "Turma",
                "grade_level": 10,
                "start_year": 2025,
                "end_year": 2028,
            },
            headers=clerk_admin_headers,
        )
        class_id = create.json()["id"]

        resp = await async_client.patch(
            f"{API}/courses/{course_id}/classes/{class_id}",
            json={"start_year": 2026, "end_year": 2026},
            headers=clerk_admin_headers,
        )
        assert resp.status_code == 422

    async def test_update_class_partial_year_range_invalid_400(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        """PATCH parcial não pode deixar end_year <= start_year."""
        course_id = await _create_course(async_client, clerk_admin_headers)
        create = await async_client.post(
            f"{API}/courses/{course_id}/classes",
            json={
                "name": "Turma Parcial",
                "grade_level": 10,
                "start_year": 2025,
                "end_year": 2028,
            },
            headers=clerk_admin_headers,
        )
        class_id = create.json()["id"]

        resp = await async_client.patch(
            f"{API}/courses/{course_id}/classes/{class_id}",
            json={"end_year": 2025},
            headers=clerk_admin_headers,
        )

        assert resp.status_code == 400

    async def test_update_class_not_found_404(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        """❌ Turma inexistente devolve 404"""
        resp = await async_client.patch(
            f"{API}/courses/99999/classes/99999",
            json={"name": "Fantasma"},
            headers=clerk_admin_headers,
        )
        assert resp.status_code == 404

    # ---------- DELETE ----------

    async def test_delete_class(self, async_client: AsyncClient, clerk_admin_headers: dict):
        """✅ Apagar turma com sucesso"""
        course_id = await _create_course(async_client, clerk_admin_headers)
        create = await async_client.post(
            f"{API}/courses/{course_id}/classes",
            json={
                "name": "Descartável",
                "grade_level": 10,
                "start_year": 2025,
                "end_year": 2028,
            },
            headers=clerk_admin_headers,
        )
        class_id = create.json()["id"]

        resp = await async_client.delete(
            f"{API}/courses/{course_id}/classes/{class_id}", headers=clerk_admin_headers
        )
        assert resp.status_code == 200

    async def test_delete_class_not_found_404(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        """❌ Apagar turma inexistente devolve 404"""
        resp = await async_client.delete(
            f"{API}/courses/99999/classes/99999", headers=clerk_admin_headers
        )
        assert resp.status_code == 404


async def _create_room(client: AsyncClient, headers: dict, name: str, capacity: int) -> int:
    types = await room_type_ids(client, headers)
    resp = await client.post(
        f"{API}/rooms/",
        json={"name": name, "room_type_id": types["normal"], "capacity": capacity},
        headers=headers,
    )
    assert resp.status_code == 200
    return resp.json()["id"]


async def _create_class_in_course(client: AsyncClient, headers: dict, course_id: int) -> int:
    resp = await client.post(
        f"{API}/courses/{course_id}/classes",
        json={"name": "Turma Sala", "grade_level": 10, "start_year": 2025, "end_year": 2028},
        headers=headers,
    )
    assert resp.status_code == 200
    return resp.json()["id"]


async def _set_home_room(client: AsyncClient, headers: dict, course_id: int, class_id: int, room):
    return await client.patch(
        f"{API}/courses/{course_id}/classes/{class_id}",
        json={"home_room_id": room},
        headers=headers,
    )


class TestClassHomeRoom:
    """S8, R01, R09 e R10: a sala da turma pela API."""

    async def test_home_room_must_be_a_room_id_not_a_room_type_id(
        self, async_client: AsyncClient, clerk_admin_headers: dict, db_session: AsyncSession
    ):
        """❌ R01: o id de um tipo de sala não é uma sala: 404 e nada é gravado."""
        course_id = await _create_course(async_client, clerk_admin_headers)
        class_id = await _create_class_in_course(async_client, clerk_admin_headers, course_id)
        types = await room_type_ids(async_client, clerk_admin_headers)

        resp = await _set_home_room(
            async_client, clerk_admin_headers, course_id, class_id, types["normal"]
        )

        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "resource_not_found"
        saved = await db_session.scalar(
            select(models.Class.home_room_id).where(models.Class.id == class_id)
        )
        assert saved is None

    async def test_home_room_not_found_names_the_room_in_context(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        """❌ A sala inexistente dá 404 com o contexto 'room' para a UI a identificar."""
        course_id = await _create_course(async_client, clerk_admin_headers)
        class_id = await _create_class_in_course(async_client, clerk_admin_headers, course_id)
        types = await room_type_ids(async_client, clerk_admin_headers)

        resp = await _set_home_room(
            async_client, clerk_admin_headers, course_id, class_id, types["normal"]
        )

        assert resp.status_code == 404
        assert resp.json()["detail"]["context"] == {"resource": "room"}

    async def test_missing_class_is_not_reported_as_a_missing_room(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        """❌ A turma inexistente dá 404 sem contexto de sala."""
        course_id = await _create_course(async_client, clerk_admin_headers)
        room_id = await _create_room(async_client, clerk_admin_headers, "Sala Existente", 30)

        resp = await _set_home_room(async_client, clerk_admin_headers, course_id, 99999, room_id)

        assert resp.status_code == 404
        assert resp.json()["detail"]["context"] == {}

    async def test_home_room_of_another_school_is_not_found(
        self, async_client: AsyncClient, clerk_admin_headers: dict, db_session: AsyncSession
    ):
        """❌ R01: a sala de outra escola devolve 404 e nada é gravado."""
        course_id = await _create_course(async_client, clerk_admin_headers)
        class_id = await _create_class_in_course(async_client, clerk_admin_headers, course_id)
        other = models.Organization(name="Outra Escola Sala", plan_status="active")
        db_session.add(other)
        await db_session.flush()
        await room_type_service.ensure_initial_room_types(db_session, other.id)
        other_room = models.Room(
            organization_id=other.id,
            name="Sala alheia",
            capacity=30,
            room_type_id=await get_school_room_type_id(db_session, other.id, "Normal"),
        )
        db_session.add(other_room)
        await db_session.commit()

        resp = await _set_home_room(
            async_client, clerk_admin_headers, course_id, class_id, other_room.id
        )

        assert resp.status_code == 404
        saved = await db_session.scalar(
            select(models.Class.home_room_id).where(models.Class.id == class_id)
        )
        assert saved is None

    async def test_home_room_is_saved_shown_and_kept_when_absent(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        """✅ A sala aparece no detalhe; PATCH sem o campo mantém-na; null volta a Automática."""
        course_id = await _create_course(async_client, clerk_admin_headers)
        class_id = await _create_class_in_course(async_client, clerk_admin_headers, course_id)
        room_id = await _create_room(async_client, clerk_admin_headers, "Sala Turma", 30)
        types = await room_type_ids(async_client, clerk_admin_headers)

        resp = await _set_home_room(async_client, clerk_admin_headers, course_id, class_id, room_id)
        assert resp.status_code == 200
        assert resp.json()["home_room_id"] == room_id

        renamed = await async_client.patch(
            f"{API}/courses/{course_id}/classes/{class_id}",
            json={"name": "Turma Renomeada"},
            headers=clerk_admin_headers,
        )
        assert renamed.status_code == 200
        detail = await async_client.get(f"{API}/classes/{class_id}", headers=clerk_admin_headers)
        assert detail.json()["home_room"] == {
            "id": room_id,
            "name": "Sala Turma",
            "capacity": 30,
            "room_type": {"id": types["normal"], "name": "Normal", "is_normal": True},
        }

        automatic = await _set_home_room(
            async_client, clerk_admin_headers, course_id, class_id, None
        )
        assert automatic.status_code == 200
        assert automatic.json()["home_room_id"] is None
        detail = await async_client.get(f"{API}/classes/{class_id}", headers=clerk_admin_headers)
        assert detail.json()["home_room"] is None

    async def test_home_room_smaller_than_the_class_is_rejected(
        self, async_client: AsyncClient, clerk_admin_headers: dict, db_session: AsyncSession
    ):
        """❌ R09: sala com menos lugares que a turma dá 422 com o código e o contexto."""
        course_id = await _create_course(async_client, clerk_admin_headers)
        class_id = await _create_class_in_course(async_client, clerk_admin_headers, course_id)
        room_id = await _create_room(async_client, clerk_admin_headers, "Sala Pequena", 10)

        resp = await _set_home_room(async_client, clerk_admin_headers, course_id, class_id, room_id)

        assert resp.status_code == 422
        error = resp.json()["detail"]
        assert error["code"] == "home_room_capacity"
        assert error["context"] == {
            "room_name": "Sala Pequena",
            "room_capacity": 10,
            "class_size": 25,
        }
        saved = await db_session.scalar(
            select(models.Class.home_room_id).where(models.Class.id == class_id)
        )
        assert saved is None

    async def test_growing_the_class_above_its_home_room_is_accepted(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        """✅ R09: a turma que cresce acima da lotação mantém a sala, e o detalhe mostra-a."""
        course_id = await _create_course(async_client, clerk_admin_headers)
        class_id = await _create_class_in_course(async_client, clerk_admin_headers, course_id)
        room_id = await _create_room(async_client, clerk_admin_headers, "Sala Cheia", 30)
        await _set_home_room(async_client, clerk_admin_headers, course_id, class_id, room_id)

        grown = await async_client.patch(
            f"{API}/courses/{course_id}/classes/{class_id}",
            json={"size": 40},
            headers=clerk_admin_headers,
        )

        assert grown.status_code == 200
        detail = await async_client.get(f"{API}/classes/{class_id}", headers=clerk_admin_headers)
        assert detail.json()["home_room"]["id"] == room_id
        assert detail.json()["home_room"]["capacity"] == 30

    async def test_home_room_round_trip_records_three_class_demand_changes(
        self, async_client: AsyncClient, clerk_admin_headers: dict, db_session: AsyncSession
    ):
        """❌ R10: definir, voltar a Automática e definir outra regista três CLASS_DEMAND."""
        course_id = await _create_course(async_client, clerk_admin_headers)
        class_id = await _create_class_in_course(async_client, clerk_admin_headers, course_id)
        org_id = await db_session.scalar(
            select(models.Class.organization_id).where(models.Class.id == class_id)
        )
        db_session.add(
            models.SchedulerSchoolYear(
                organization_id=org_id,
                label="2026/2027",
                start_date=date(2026, 9, 1),
                hard_end_date=date(2027, 7, 15),
                timezone="Europe/Lisbon",
            )
        )
        await db_session.commit()
        first_room = await _create_room(async_client, clerk_admin_headers, "Sala A", 30)
        second_room = await _create_room(async_client, clerk_admin_headers, "Sala B", 30)

        await _set_home_room(async_client, clerk_admin_headers, course_id, class_id, first_room)
        await _set_home_room(async_client, clerk_admin_headers, course_id, class_id, None)
        await _set_home_room(async_client, clerk_admin_headers, course_id, class_id, second_room)

        updates = (
            await db_session.scalars(
                select(models.SchedulerStateVersionEvent)
                .where(
                    models.SchedulerStateVersionEvent.entity_type == "CLASS_DEMAND",
                    models.SchedulerStateVersionEvent.entity_id == str(class_id),
                    models.SchedulerStateVersionEvent.operation
                    == models.SchedulerStateChangeOperation.UPDATE,
                )
                .order_by(models.SchedulerStateVersionEvent.id)
            )
        ).all()
        assert [event.before_metadata_json["home_room_id"] for event in updates] == [
            None,
            first_room,
            None,
        ]
        assert [event.after_metadata_json["home_room_id"] for event in updates] == [
            first_room,
            None,
            second_room,
        ]
