"""
Testes de Competências de Professores
Parte de test_business_logic.py (split).
"""

from factories import API, _setup_course_class_subject
from httpx import AsyncClient

from tests.conftest import create_teacher_profile


class TestCompetencies:
    async def test_assign_teacher_with_competency(
        self, async_client: AsyncClient, clerk_admin_headers: dict, db_session
    ):
        ctx = await _setup_course_class_subject(async_client, clerk_admin_headers)
        teacher = await create_teacher_profile(
            db_session,
            organization_id=1,
            name="Prof. Competente",
            subject_ids=[ctx["subject_id"]],
        )
        await db_session.commit()
        teacher_id = teacher.id
        resp = await async_client.patch(
            f"{API}/classes/{ctx['class_id']}/subjects/{ctx['subject_id']}",
            json={"teacher_id": teacher_id},
            headers=clerk_admin_headers,
        )
        assert resp.status_code == 200

    async def test_assign_teacher_without_competency_400(
        self, async_client: AsyncClient, clerk_admin_headers: dict, db_session
    ):
        ctx = await _setup_course_class_subject(async_client, clerk_admin_headers)
        teacher = await create_teacher_profile(db_session, organization_id=1, name="Prof. Sem Comp")
        await db_session.commit()
        teacher_id = teacher.id
        resp = await async_client.patch(
            f"{API}/classes/{ctx['class_id']}/subjects/{ctx['subject_id']}",
            json={"teacher_id": teacher_id},
            headers=clerk_admin_headers,
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"].lower()
        assert "professor" in detail
        assert "disciplina" in detail

    async def test_assign_teacher_wrong_subject_400(
        self, async_client: AsyncClient, clerk_admin_headers: dict, db_session
    ):
        ctx = await _setup_course_class_subject(async_client, clerk_admin_headers)
        other_sub = await async_client.post(
            f"{API}/subjects/",
            json={"name": "Educação Física", "required_room_type": "gym"},
            headers=clerk_admin_headers,
        )
        other_sub_id = other_sub.json()["id"]
        teacher = await create_teacher_profile(
            db_session,
            organization_id=1,
            name="Prof. EF",
            subject_ids=[other_sub_id],
        )
        await db_session.commit()
        teacher_id = teacher.id
        resp = await async_client.patch(
            f"{API}/classes/{ctx['class_id']}/subjects/{ctx['subject_id']}",
            json={"teacher_id": teacher_id},
            headers=clerk_admin_headers,
        )
        assert resp.status_code == 400

    async def test_remove_teacher_assignment(
        self, async_client: AsyncClient, clerk_admin_headers: dict, db_session
    ):
        ctx = await _setup_course_class_subject(async_client, clerk_admin_headers)
        teacher = await create_teacher_profile(
            db_session,
            organization_id=1,
            name="Prof. Temp",
            subject_ids=[ctx["subject_id"]],
        )
        await db_session.commit()
        teacher_id = teacher.id
        await async_client.patch(
            f"{API}/classes/{ctx['class_id']}/subjects/{ctx['subject_id']}",
            json={"teacher_id": teacher_id},
            headers=clerk_admin_headers,
        )
        resp = await async_client.patch(
            f"{API}/classes/{ctx['class_id']}/subjects/{ctx['subject_id']}",
            json={"teacher_id": None},
            headers=clerk_admin_headers,
        )
        assert resp.status_code == 200
