"""
Testes de Progresso de Módulos
Parte de test_business_logic.py (split).
"""
import pytest
from pytest import approx
from httpx import AsyncClient
from test_business_logic_shared import API, _setup_course_class_subject


@pytest.mark.asyncio
class TestModuleProgress:

    async def test_update_progress_basic(self, async_client: AsyncClient, admin_token_headers: dict):
        ctx = await _setup_course_class_subject(async_client, admin_token_headers)
        resp = await async_client.patch(
            f"{API}/classes/{ctx['class_id']}/progress",
            json={"progress": [{"module_id": ctx["module_ids"][0], "hours_completed": 10}]},
            headers=admin_token_headers,
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

    async def test_progress_auto_complete(self, async_client: AsyncClient, admin_token_headers: dict):
        ctx = await _setup_course_class_subject(async_client, admin_token_headers)
        resp = await async_client.patch(
            f"{API}/classes/{ctx['class_id']}/progress",
            json={"progress": [{"module_id": ctx["module_ids"][0], "hours_completed": 25}]},
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

    async def test_progress_clamp_to_max(self, async_client: AsyncClient, admin_token_headers: dict):
        ctx = await _setup_course_class_subject(async_client, admin_token_headers)
        resp = await async_client.patch(
            f"{API}/classes/{ctx['class_id']}/progress",
            json={"progress": [{"module_id": ctx["module_ids"][0], "hours_completed": 999}]},
            headers=admin_token_headers,
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

    async def test_progress_invalid_module_400(self, async_client: AsyncClient, admin_token_headers: dict):
        ctx = await _setup_course_class_subject(async_client, admin_token_headers)
        resp = await async_client.patch(
            f"{API}/classes/{ctx['class_id']}/progress",
            json={"progress": [{"module_id": 99999, "hours_completed": 10}]},
            headers=admin_token_headers,
        )
        assert resp.status_code == 400
        assert "módulo" in resp.json()["detail"].lower()

    async def test_progress_class_not_found_404(self, async_client: AsyncClient, admin_token_headers: dict):
        resp = await async_client.patch(
            f"{API}/classes/99999/progress",
            json={"progress": [{"module_id": 1, "hours_completed": 10}]},
            headers=admin_token_headers,
        )
        assert resp.status_code == 404

    async def test_progress_bulk_update(self, async_client: AsyncClient, admin_token_headers: dict):
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
        assert subj["completed_hours"] == 55
        assert subj["total_hours"] == 75
        overall_pct = round((55 / 75) * 100, 1)
        assert subj["overall_percentage"] == overall_pct
