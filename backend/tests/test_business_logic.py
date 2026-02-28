# Ficheiro: backend/tests/test_business_logic.py
"""
TESTES DE LÓGICA DE NEGÓCIO — Ensino Profissional
==================================================
Valida regras específicas do domínio:

1. COMPETÊNCIAS: Professor sem competência não pode ser atribuído a disciplina
2. PROGRESSO DE MÓDULOS: Horas, auto-complete, clamping, módulo inválido
3. DISPONIBILIDADES: Gravar/atualizar preferências de horário (Paintbrush)
4. ISOLAMENTO DE TENANT: Admin de Org A NÃO vê dados de Org B

NÃO inclui testes de Solver/Schedule (excluídos por indicação).
"""

import pytest
from pytest import approx
from httpx import AsyncClient
from app.config import settings
from app import models
from app.core.security import hash_password, create_access_token
from app.models import UserRole


API = settings.API_V1_STR


# ==========================================
#  HELPERS para cenários complexos
# ==========================================


async def _setup_course_class_subject(client: AsyncClient, headers: dict):
    """Cria Curso + Turma + Disciplina com módulos, devolve IDs."""
    # Disciplina com módulos
    sub_resp = await client.post(
        f"{API}/subjects/",
        json={
            "name": "Programação",
            "required_room_type": "lab",
            "modules": [
                {"name": "M1", "code": "P01", "hours_total": 25, "order": 0},
                {"name": "M2", "code": "P02", "hours_total": 50, "order": 1},
            ],
        },
        headers=headers,
    )
    subject_id = sub_resp.json()["id"]
    modules = sub_resp.json()["modules"]

    # Curso
    course_resp = await client.post(
        f"{API}/courses/",
        json={
            "name": "Técnico Informática",
            "abbreviation": "TI",
            "subject_ids": [subject_id],
        },
        headers=headers,
    )
    course_id = course_resp.json()["id"]

    # Turma
    class_resp = await client.post(
        f"{API}/classes/",
        json={
            "name": "Turma TI-A",
            "course_id": course_id,
            "grade_level": 10,
            "start_year": 2025,
            "end_year": 2028,
        },
        headers=headers,
    )
    class_id = class_resp.json()["id"]

    # Associar disciplina à turma
    await client.post(
        f"{API}/classes/{class_id}/subjects",
        json={"subject_id": subject_id},
        headers=headers,
    )

    return {
        "course_id": course_id,
        "class_id": class_id,
        "subject_id": subject_id,
        "module_ids": [m["id"] for m in modules],
        "module_hours": [m["hours_total"] for m in modules],
    }


# ==========================================
#  1. COMPETÊNCIAS
# ==========================================


@pytest.mark.asyncio
class TestCompetencies:

    async def test_assign_teacher_with_competency(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """✅ Professor COM competência pode ser atribuído"""
        ctx = await _setup_course_class_subject(async_client, admin_token_headers)

        # Criar professor com competência na disciplina
        teacher_resp = await async_client.post(
            f"{API}/teachers/",
            json={
                "name": "Prof. Competente",
                "email": "comp@escola.pt",
                "subject_ids": [ctx["subject_id"]],
            },
            headers=admin_token_headers,
        )
        teacher_id = teacher_resp.json()["id"]

        # Atribuir professor à disciplina da turma
        resp = await async_client.patch(
            f"{API}/classes/{ctx['class_id']}/subjects/{ctx['subject_id']}",
            json={"teacher_id": teacher_id},
            headers=admin_token_headers,
        )
        assert resp.status_code == 200

    async def test_assign_teacher_without_competency_400(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """❌ Professor SEM competência é rejeitado com 400"""
        ctx = await _setup_course_class_subject(async_client, admin_token_headers)

        # Criar professor SEM competência (subject_ids vazio)
        teacher_resp = await async_client.post(
            f"{API}/teachers/",
            json={
                "name": "Prof. Sem Comp",
                "email": "semcomp@escola.pt",
                "subject_ids": [],
            },
            headers=admin_token_headers,
        )
        teacher_id = teacher_resp.json()["id"]

        resp = await async_client.patch(
            f"{API}/classes/{ctx['class_id']}/subjects/{ctx['subject_id']}",
            json={"teacher_id": teacher_id},
            headers=admin_token_headers,
        )
        assert resp.status_code == 400
        assert "competência" in resp.json()["detail"].lower()

    async def test_assign_teacher_wrong_subject_400(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """❌ Professor com competência NOUTRA disciplina é rejeitado"""
        ctx = await _setup_course_class_subject(async_client, admin_token_headers)

        # Criar outra disciplina
        other_sub = await async_client.post(
            f"{API}/subjects/",
            json={"name": "Educação Física", "required_room_type": "gym"},
            headers=admin_token_headers,
        )
        other_sub_id = other_sub.json()["id"]

        # Professor competente apenas em Educação Física
        teacher_resp = await async_client.post(
            f"{API}/teachers/",
            json={
                "name": "Prof. EF",
                "email": "ef@escola.pt",
                "subject_ids": [other_sub_id],
            },
            headers=admin_token_headers,
        )
        teacher_id = teacher_resp.json()["id"]

        resp = await async_client.patch(
            f"{API}/classes/{ctx['class_id']}/subjects/{ctx['subject_id']}",
            json={"teacher_id": teacher_id},
            headers=admin_token_headers,
        )
        assert resp.status_code == 400

    async def test_remove_teacher_assignment(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """✅ Remover atribuição de professor (teacher_id=null)"""
        ctx = await _setup_course_class_subject(async_client, admin_token_headers)

        # Criar e atribuir professor
        teacher_resp = await async_client.post(
            f"{API}/teachers/",
            json={
                "name": "Prof. Temp",
                "email": "temp@escola.pt",
                "subject_ids": [ctx["subject_id"]],
            },
            headers=admin_token_headers,
        )
        teacher_id = teacher_resp.json()["id"]
        await async_client.patch(
            f"{API}/classes/{ctx['class_id']}/subjects/{ctx['subject_id']}",
            json={"teacher_id": teacher_id},
            headers=admin_token_headers,
        )

        # Remover atribuição
        resp = await async_client.patch(
            f"{API}/classes/{ctx['class_id']}/subjects/{ctx['subject_id']}",
            json={"teacher_id": None},
            headers=admin_token_headers,
        )
        assert resp.status_code == 200


# ==========================================
#  2. PROGRESSO DE MÓDULOS
# ==========================================


@pytest.mark.asyncio
class TestModuleProgress:

    async def test_update_progress_basic(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """✅ Registar progresso parcial de um módulo"""
        ctx = await _setup_course_class_subject(async_client, admin_token_headers)

        resp = await async_client.patch(
            f"{API}/classes/{ctx['class_id']}/progress",
            json={
                "progress": [
                    {"module_id": ctx["module_ids"][0], "hours_completed": 10}
                ]
            },
            headers=admin_token_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        # Encontrar o módulo M1 no response
        m1 = None
        for subj in data["subjects"]:
            for mod in subj["modules"]:
                if mod["id"] == ctx["module_ids"][0]:
                    m1 = mod
                    break
        assert m1 is not None
        assert m1["hours_completed"] == 10
        assert m1["is_completed"] is False
        assert m1["percentage"] == approx(40.0)  # 10/25 * 100

    async def test_progress_auto_complete(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """✅ Módulo completo automaticamente quando horas >= total"""
        ctx = await _setup_course_class_subject(async_client, admin_token_headers)

        resp = await async_client.patch(
            f"{API}/classes/{ctx['class_id']}/progress",
            json={
                "progress": [
                    {"module_id": ctx["module_ids"][0], "hours_completed": 25}
                ]
            },
            headers=admin_token_headers,
        )
        assert resp.status_code == 200
        m1 = None
        for subj in resp.json()["subjects"]:
            for mod in subj["modules"]:
                if mod["id"] == ctx["module_ids"][0]:
                    m1 = mod
                    break
        assert m1["is_completed"] is True
        assert m1["percentage"] == approx(100.0)

    async def test_progress_clamp_to_max(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """✅ Horas excedentes são limitadas ao total do módulo"""
        ctx = await _setup_course_class_subject(async_client, admin_token_headers)

        resp = await async_client.patch(
            f"{API}/classes/{ctx['class_id']}/progress",
            json={
                "progress": [
                    {"module_id": ctx["module_ids"][0], "hours_completed": 999}
                ]
            },
            headers=admin_token_headers,
        )
        assert resp.status_code == 200
        m1 = None
        for subj in resp.json()["subjects"]:
            for mod in subj["modules"]:
                if mod["id"] == ctx["module_ids"][0]:
                    m1 = mod
                    break
        # Clamped to 25 (hours_total)
        assert m1["hours_completed"] == 25
        assert m1["is_completed"] is True

    async def test_progress_invalid_module_400(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """❌ Módulo que não pertence à turma devolve 400"""
        ctx = await _setup_course_class_subject(async_client, admin_token_headers)

        resp = await async_client.patch(
            f"{API}/classes/{ctx['class_id']}/progress",
            json={
                "progress": [
                    {"module_id": 99999, "hours_completed": 10}
                ]
            },
            headers=admin_token_headers,
        )
        assert resp.status_code == 400
        assert "módulo" in resp.json()["detail"].lower()

    async def test_progress_class_not_found_404(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """❌ Turma inexistente devolve 404"""
        resp = await async_client.patch(
            f"{API}/classes/99999/progress",
            json={
                "progress": [{"module_id": 1, "hours_completed": 10}]
            },
            headers=admin_token_headers,
        )
        assert resp.status_code == 404

    async def test_progress_bulk_update(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """✅ Atualizar progresso de múltiplos módulos em batch"""
        ctx = await _setup_course_class_subject(async_client, admin_token_headers)

        resp = await async_client.patch(
            f"{API}/classes/{ctx['class_id']}/progress",
            json={
                "progress": [
                    {"module_id": ctx["module_ids"][0], "hours_completed": 25},
                    {"module_id": ctx["module_ids"][1], "hours_completed": 30},
                ]
            },
            headers=admin_token_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        subj = data["subjects"][0]
        # M1: 25/25 (100%), M2: 30/50 (60%)
        assert subj["completed_hours"] == 55
        assert subj["total_hours"] == 75
        overall_pct = round((55 / 75) * 100, 1)
        assert subj["overall_percentage"] == overall_pct


# ==========================================
#  3. DISPONIBILIDADES (Paintbrush)
# ==========================================


@pytest.mark.asyncio
class TestTeacherAvailability:

    async def test_set_availability(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """✅ Gravar disponibilidades de um professor"""
        # Gerar timeslots
        await async_client.post(
            f"{API}/timeslots/generate",
            json={
                "start_time": "08:00",
                "end_time": "10:00",
                "slot_duration_minutes": 50,
                "break_duration_minutes": 10,
                "days_of_week": [0],
            },
            headers=admin_token_headers,
        )
        slots_resp = await async_client.get(
            f"{API}/timeslots/", headers=admin_token_headers
        )
        slot_ids = [s["id"] for s in slots_resp.json()]
        assert len(slot_ids) >= 2

        # Criar professor
        teacher_resp = await async_client.post(
            f"{API}/teachers/",
            json={"name": "Prof. Disp", "email": "disp@escola.pt"},
            headers=admin_token_headers,
        )
        teacher_id = teacher_resp.json()["id"]

        # Gravar disponibilidades (2=Preferencial, -1=Impossível)
        payload = [
            {"timeslot_id": slot_ids[0], "score": 2},
            {"timeslot_id": slot_ids[1], "score": -1},
        ]
        resp = await async_client.post(
            f"{API}/teachers/{teacher_id}/availability",
            json=payload,
            headers=admin_token_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["count"] == 2

    async def test_availability_invalid_timeslot_400(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """❌ Timeslot inexistente devolve 400"""
        teacher_resp = await async_client.post(
            f"{API}/teachers/",
            json={"name": "Prof. Bad", "email": "bad@escola.pt"},
            headers=admin_token_headers,
        )
        teacher_id = teacher_resp.json()["id"]

        resp = await async_client.post(
            f"{API}/teachers/{teacher_id}/availability",
            json=[{"timeslot_id": 99999, "score": 1}],
            headers=admin_token_headers,
        )
        assert resp.status_code == 400

    async def test_availability_teacher_not_found_404(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """❌ Professor inexistente devolve 404"""
        resp = await async_client.post(
            f"{API}/teachers/99999/availability",
            json=[],
            headers=admin_token_headers,
        )
        assert resp.status_code == 404

    async def test_availability_overwrite(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        """✅ Gravar novamente SOBRESCREVE disponibilidades anteriores"""
        # Gerar timeslots
        await async_client.post(
            f"{API}/timeslots/generate",
            json={
                "start_time": "08:00",
                "end_time": "10:00",
                "slot_duration_minutes": 50,
                "break_duration_minutes": 10,
                "days_of_week": [0],
            },
            headers=admin_token_headers,
        )
        slots = (
            await async_client.get(f"{API}/timeslots/", headers=admin_token_headers)
        ).json()
        slot_id = slots[0]["id"]

        teacher_resp = await async_client.post(
            f"{API}/teachers/",
            json={"name": "Prof. Over", "email": "over@escola.pt"},
            headers=admin_token_headers,
        )
        teacher_id = teacher_resp.json()["id"]

        # 1ª gravação: 2 entradas
        await async_client.post(
            f"{API}/teachers/{teacher_id}/availability",
            json=[
                {"timeslot_id": slot_id, "score": 2},
            ],
            headers=admin_token_headers,
        )

        # 2ª gravação: apenas 1 entrada (deve substituir)
        resp = await async_client.post(
            f"{API}/teachers/{teacher_id}/availability",
            json=[
                {"timeslot_id": slot_id, "score": -1},
            ],
            headers=admin_token_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["count"] == 1


# ==========================================
#  4. ISOLAMENTO DE TENANT
# ==========================================


@pytest.mark.asyncio
class TestTenantIsolation:
    """
    Garante que dados de uma Organização NÃO são visíveis por outra.
    Cria duas orgs com admins separados e verifica isolamento.
    """

    async def _create_org_admin(self, db_session, email: str, org_name: str) -> dict:
        """Helper: cria uma organização + admin e devolve headers."""
        org = models.Organization(name=org_name, plan_status="active")
        db_session.add(org)
        await db_session.flush()

        user = models.User(
            email=email,
            hashed_password=hash_password("pass123"),
            is_active=True,
            role=UserRole.admin,
            organization_id=org.id,
        )
        db_session.add(user)
        await db_session.commit()

        token = create_access_token(data={"sub": email})
        return {"headers": {"Authorization": f"Bearer {token}"}, "org_id": org.id}

    async def test_org_a_cannot_see_org_b_rooms(
        self, async_client: AsyncClient, db_session
    ):
        """🔐 Salas criadas pela Org A não aparecem para Org B"""
        org_a = await self._create_org_admin(db_session, "admin_a@escola.pt", "Escola A")
        org_b = await self._create_org_admin(db_session, "admin_b@escola.pt", "Escola B")

        # Org A cria sala
        await async_client.post(
            f"{API}/rooms/",
            json={"name": "Lab A", "room_type": "lab"},
            headers=org_a["headers"],
        )

        # Org B lista salas → deve estar vazia
        resp = await async_client.get(
            f"{API}/rooms/", headers=org_b["headers"]
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 0

    async def test_org_a_cannot_see_org_b_teachers(
        self, async_client: AsyncClient, db_session
    ):
        """🔐 Professores da Org A não aparecem para Org B"""
        org_a = await self._create_org_admin(db_session, "admin_a@escola.pt", "Escola A")
        org_b = await self._create_org_admin(db_session, "admin_b@escola.pt", "Escola B")

        await async_client.post(
            f"{API}/teachers/",
            json={"name": "Prof. A", "email": "profa@escola.pt"},
            headers=org_a["headers"],
        )

        resp = await async_client.get(
            f"{API}/teachers/", headers=org_b["headers"]
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 0

    async def test_org_a_cannot_update_org_b_subject(
        self, async_client: AsyncClient, db_session
    ):
        """🔐 Org A não consegue atualizar disciplina da Org B (404)"""
        org_a = await self._create_org_admin(db_session, "admin_a@escola.pt", "Escola A")
        org_b = await self._create_org_admin(db_session, "admin_b@escola.pt", "Escola B")

        # Org B cria disciplina
        sub_resp = await async_client.post(
            f"{API}/subjects/",
            json={"name": "Física B", "required_room_type": "lab"},
            headers=org_b["headers"],
        )
        sub_id = sub_resp.json()["id"]

        # Org A tenta atualizar → 404 (não encontra na sua org)
        resp = await async_client.patch(
            f"{API}/subjects/{sub_id}",
            json={"name": "Hackeado"},
            headers=org_a["headers"],
        )
        assert resp.status_code == 404

    async def test_org_a_cannot_delete_org_b_course(
        self, async_client: AsyncClient, db_session
    ):
        """🔐 Org A não consegue apagar curso da Org B (404)"""
        org_a = await self._create_org_admin(db_session, "admin_a@escola.pt", "Escola A")
        org_b = await self._create_org_admin(db_session, "admin_b@escola.pt", "Escola B")

        # Org B cria curso
        course_resp = await async_client.post(
            f"{API}/courses/",
            json={"name": "Curso B", "abbreviation": "CB"},
            headers=org_b["headers"],
        )
        course_id = course_resp.json()["id"]

        # Org A tenta apagar → 404
        resp = await async_client.delete(
            f"{API}/courses/{course_id}",
            headers=org_a["headers"],
        )
        assert resp.status_code == 404
