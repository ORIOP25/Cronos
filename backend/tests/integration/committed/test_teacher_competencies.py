"""
Testes de Competências de Professores
Parte de test_business_logic.py (split).
"""

from factories import API, _setup_course_class_subject
from httpx import AsyncClient

from app import models
from tests._support.db_fixtures import create_teacher_profile


class TestCompetencies:
    async def test_eligible_teachers_excludes_archived_membership(
        self, async_client: AsyncClient, clerk_admin_headers: dict, db_session
    ):
        ctx = await _setup_course_class_subject(async_client, clerk_admin_headers)
        active_teacher = await create_teacher_profile(
            db_session,
            organization_id=1,
            name="Prof. Ativo",
            subject_ids=[ctx["subject_id"]],
        )
        archived_teacher = await create_teacher_profile(
            db_session,
            organization_id=1,
            name="Prof. Arquivado",
            subject_ids=[ctx["subject_id"]],
        )
        archived_membership = await db_session.get(
            models.OrganizationMembership,
            archived_teacher.organization_membership_id,
        )
        archived_membership.lifecycle_status = models.MembershipLifecycleStatus.archived
        await db_session.commit()

        response = await async_client.get(
            f"{API}/classes/subjects/{ctx['subject_id']}/eligible-teachers",
            headers=clerk_admin_headers,
        )

        assert response.status_code == 200
        teacher_ids = {teacher["id"] for teacher in response.json()}
        assert active_teacher.id in teacher_ids
        assert archived_teacher.id not in teacher_ids

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
        detail = resp.json()["detail"]["message"].lower()
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
