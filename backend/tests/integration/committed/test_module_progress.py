"""
Testes de Progresso de Módulos
Parte de test_business_logic.py (split).
"""

from factories import API, _setup_course_class_subject
from httpx import AsyncClient
from pytest import approx

from app.services import teacher_service
from tests._support.db_fixtures import create_teacher_profile


class TestModuleProgress:
    async def test_update_progress_basic(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        ctx = await _setup_course_class_subject(async_client, clerk_admin_headers)
        resp = await async_client.patch(
            f"{API}/classes/{ctx['class_id']}/progress",
            json={"progress": [{"module_id": ctx["module_ids"][0], "hours_completed": 10}]},
            headers=clerk_admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        m1 = None
        for subj in data["subjects"]:
            for mod in subj["modules"]:
                if mod["id"] == ctx["module_ids"][0]:
                    m1 = mod
                    break
        assert m1 is not None
        assert m1["hours_completed"] == 10
        assert m1["is_completed"] is False
        assert m1["percentage"] == approx(40.0)

    async def test_progress_auto_complete(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        ctx = await _setup_course_class_subject(async_client, clerk_admin_headers)
        resp = await async_client.patch(
            f"{API}/classes/{ctx['class_id']}/progress",
            json={"progress": [{"module_id": ctx["module_ids"][0], "hours_completed": 25}]},
            headers=clerk_admin_headers,
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
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        ctx = await _setup_course_class_subject(async_client, clerk_admin_headers)
        resp = await async_client.patch(
            f"{API}/classes/{ctx['class_id']}/progress",
            json={"progress": [{"module_id": ctx["module_ids"][0], "hours_completed": 999}]},
            headers=clerk_admin_headers,
        )
        assert resp.status_code == 200
        m1 = None
        for subj in resp.json()["subjects"]:
            for mod in subj["modules"]:
                if mod["id"] == ctx["module_ids"][0]:
                    m1 = mod
                    break
        assert m1["hours_completed"] == 25
        assert m1["is_completed"] is True

    async def test_progress_invalid_module_400(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        ctx = await _setup_course_class_subject(async_client, clerk_admin_headers)
        resp = await async_client.patch(
            f"{API}/classes/{ctx['class_id']}/progress",
            json={"progress": [{"module_id": 99999, "hours_completed": 10}]},
            headers=clerk_admin_headers,
        )
        assert resp.status_code == 400
        assert "processar" in resp.json()["detail"]["message"]

    async def test_progress_class_not_found_404(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        resp = await async_client.patch(
            f"{API}/classes/99999/progress",
            json={"progress": [{"module_id": 1, "hours_completed": 10}]},
            headers=clerk_admin_headers,
        )
        assert resp.status_code == 404

    async def test_progress_bulk_update(self, async_client: AsyncClient, clerk_admin_headers: dict):
        ctx = await _setup_course_class_subject(async_client, clerk_admin_headers)
        resp = await async_client.patch(
            f"{API}/classes/{ctx['class_id']}/progress",
            json={
                "progress": [
                    {"module_id": ctx["module_ids"][0], "hours_completed": 25},
                    {"module_id": ctx["module_ids"][1], "hours_completed": 30},
                ]
            },
            headers=clerk_admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        subj = data["subjects"][0]
        assert subj["completed_hours"] == 55
        assert subj["total_hours"] == 75
        overall_pct = round((55 / 75) * 100, 1)
        assert subj["overall_percentage"] == overall_pct


class TestClassModuleSelectionProgress:
    """WBS 2.8: class progress counts only the selected modules."""

    async def _select(self, async_client, headers, ctx, module_ids):
        resp = await async_client.patch(
            f"{API}/classes/{ctx['class_id']}/subjects/{ctx['subject_id']}",
            json={"module_ids": module_ids},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text

    async def test_class_progress_lists_only_selected_modules(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        ctx = await _setup_course_class_subject(async_client, clerk_admin_headers)
        await self._select(async_client, clerk_admin_headers, ctx, ctx["module_ids"][:1])

        resp = await async_client.get(
            f"{API}/classes/{ctx['class_id']}", headers=clerk_admin_headers
        )

        assert resp.status_code == 200, resp.text
        subject = resp.json()["subjects"][0]
        assert [module["id"] for module in subject["modules"]] == ctx["module_ids"][:1]
        assert subject["total_hours"] == 25.0

    async def test_class_progress_rejects_an_unselected_module(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        ctx = await _setup_course_class_subject(async_client, clerk_admin_headers)
        await self._select(async_client, clerk_admin_headers, ctx, ctx["module_ids"][:1])

        resp = await async_client.patch(
            f"{API}/classes/{ctx['class_id']}/progress",
            json={"progress": [{"module_id": ctx["module_ids"][1], "hours_completed": 10}]},
            headers=clerk_admin_headers,
        )

        assert resp.status_code == 400
        assert "processar" in resp.json()["detail"]["message"]

    async def test_class_progress_without_selected_modules_is_zero(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        ctx = await _setup_course_class_subject(async_client, clerk_admin_headers)
        await self._select(async_client, clerk_admin_headers, ctx, [])

        resp = await async_client.get(
            f"{API}/classes/{ctx['class_id']}", headers=clerk_admin_headers
        )

        assert resp.status_code == 200, resp.text
        subject = resp.json()["subjects"][0]
        assert subject["modules"] == []
        assert subject["total_hours"] == 0
        assert subject["completed_hours"] == 0
        assert subject["overall_percentage"] == 0


class TestTeacherModuleSelectionProgress:
    """WBS 2.8.1: teacher progress lists only the selected modules."""

    async def test_teacher_progress_lists_only_selected_modules(
        self, async_client: AsyncClient, clerk_admin_headers: dict, db_session
    ):
        ctx = await _setup_course_class_subject(async_client, clerk_admin_headers)
        teacher = await create_teacher_profile(
            db_session,
            organization_id=1,
            name="Prof. Seleção",
            subject_ids=[ctx["subject_id"]],
        )
        await db_session.commit()
        resp = await async_client.patch(
            f"{API}/classes/{ctx['class_id']}/subjects/{ctx['subject_id']}",
            json={"teacher_id": teacher.id, "module_ids": ctx["module_ids"][:1]},
            headers=clerk_admin_headers,
        )
        assert resp.status_code == 200, resp.text

        progress = await teacher_service.get_teacher_progress(db_session, teacher.id, 1)

        subject = progress[0]["subjects"][0]
        assert [module["id"] for module in subject["modules"]] == ctx["module_ids"][:1]
        assert subject["total_hours"] == 25.0
