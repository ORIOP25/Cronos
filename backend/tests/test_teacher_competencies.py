"""
Testes de Competências de Professores
Parte de test_business_logic.py (split).
"""
import pytest
from httpx import AsyncClient
from test_business_logic_shared import API, _setup_course_class_subject


@pytest.mark.asyncio
class TestCompetencies:

    async def test_assign_teacher_with_competency(self, async_client: AsyncClient, admin_token_headers: dict):
        ctx = await _setup_course_class_subject(async_client, admin_token_headers)
        teacher_resp = await async_client.post(
            f"{API}/teachers/",
            json={"name": "Prof. Competente", "email": "comp@escola.pt", "subject_ids": [ctx["subject_id"]]},
            headers=admin_token_headers,
        )
        teacher_id = teacher_resp.json()["id"]
        resp = await async_client.patch(
            f"{API}/classes/{ctx['class_id']}/subjects/{ctx['subject_id']}",
            json={"teacher_id": teacher_id},
            headers=admin_token_headers,
        )
        assert resp.status_code == 200

    async def test_assign_teacher_without_competency_400(self, async_client: AsyncClient, admin_token_headers: dict):
        ctx = await _setup_course_class_subject(async_client, admin_token_headers)
        teacher_resp = await async_client.post(
            f"{API}/teachers/",
            json={"name": "Prof. Sem Comp", "email": "semcomp@escola.pt", "subject_ids": []},
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

    async def test_assign_teacher_wrong_subject_400(self, async_client: AsyncClient, admin_token_headers: dict):
        ctx = await _setup_course_class_subject(async_client, admin_token_headers)
        other_sub = await async_client.post(
            f"{API}/subjects/",
            json={"name": "Educação Física", "required_room_type": "gym"},
            headers=admin_token_headers,
        )
        other_sub_id = other_sub.json()["id"]
        teacher_resp = await async_client.post(
            f"{API}/teachers/",
            json={"name": "Prof. EF", "email": "ef@escola.pt", "subject_ids": [other_sub_id]},
            headers=admin_token_headers,
        )
        teacher_id = teacher_resp.json()["id"]
        resp = await async_client.patch(
            f"{API}/classes/{ctx['class_id']}/subjects/{ctx['subject_id']}",
            json={"teacher_id": teacher_id},
            headers=admin_token_headers,
        )
        assert resp.status_code == 400

    async def test_remove_teacher_assignment(self, async_client: AsyncClient, admin_token_headers: dict):
        ctx = await _setup_course_class_subject(async_client, admin_token_headers)
        teacher_resp = await async_client.post(
            f"{API}/teachers/",
            json={"name": "Prof. Temp", "email": "temp@escola.pt", "subject_ids": [ctx["subject_id"]]},
            headers=admin_token_headers,
        )
        teacher_id = teacher_resp.json()["id"]
        await async_client.patch(
            f"{API}/classes/{ctx['class_id']}/subjects/{ctx['subject_id']}",
            json={"teacher_id": teacher_id},
            headers=admin_token_headers,
        )
        resp = await async_client.patch(
            f"{API}/classes/{ctx['class_id']}/subjects/{ctx['subject_id']}",
            json={"teacher_id": None},
            headers=admin_token_headers,
        )
        assert resp.status_code == 200
