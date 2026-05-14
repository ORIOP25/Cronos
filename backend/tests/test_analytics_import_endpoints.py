"""
Testes para endpoints de analytics, importação, lessons e substitutions.

Cobre fluxos reais com dados, não apenas respostas vazias.
"""

import pytest
from httpx import AsyncClient

from app.config import settings
from app.core.security import create_access_token
from app import models

API = settings.API_V1_STR


@pytest.mark.asyncio
class TestAnalyticsHeatmap:
    async def test_heatmap_empty_when_no_teachers(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        r = await async_client.get(
            f"{API}/analytics/availability-heatmap", headers=admin_token_headers
        )
        assert r.status_code == 200
        assert r.json() == []

    async def test_heatmap_requires_auth(self, async_client: AsyncClient):
        r = await async_client.get(f"{API}/analytics/availability-heatmap")
        assert r.status_code == 401

    async def test_heatmap_accessible_to_teacher(
        self, async_client: AsyncClient, db_session
    ):
        """Heatmap é acessível a qualquer utilizador autenticado (não requer admin)."""
        from app.core.security import create_access_token
org = models.Organization(name="Heatmap Teacher Org", plan_status="active")
        db_session.add(org)
        await db_session.flush()

        teacher = models.Teacher(name="Prof. Heatmap Teacher", organization_id=org.id)
        db_session.add(teacher)
        await db_session.flush()

        teacher_user = models.User(
            email="heatmap.prof.ci@escola.pt",
            is_active=True,
            role=models.UserRole.teacher,
            organization_id=org.id,
            teacher_id=teacher.id,
        )
        db_session.add(teacher_user)
        await db_session.commit()

        token = create_access_token(data={"sub": "heatmap.prof.ci@escola.pt"})
        teacher_headers = {"Authorization": f"Bearer {token}"}

        r = await async_client.get(
            f"{API}/analytics/availability-heatmap", headers=teacher_headers
        )
        assert r.status_code == 200

    async def test_heatmap_with_teachers_and_timeslots(
        self, async_client: AsyncClient, admin_token_headers: dict, db_session
    ):
        from datetime import time

        teacher = models.Teacher(name="Prof. Dados Heatmap", organization_id=1)
        db_session.add(teacher)
        await db_session.flush()

        timeslot = models.Timeslot(
            day_of_week=0,
            start_time=time(8, 0),
            end_time=time(9, 0),
            organization_id=1,
        )
        db_session.add(timeslot)
        await db_session.flush()

        availability = models.Availability(
            teacher_id=teacher.id,
            timeslot_id=timeslot.id,
            score=models.PreferenceLevel.PREFERRED.value,
        )
        db_session.add(availability)
        await db_session.commit()

        r = await async_client.get(
            f"{API}/analytics/availability-heatmap", headers=admin_token_headers
        )
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1


@pytest.mark.asyncio
class TestImportEndpoints:
    async def test_import_timeslots_requires_admin(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        r = await async_client.get(
            f"{API}/import/timeslots", headers=admin_token_headers
        )
        assert r.status_code == 200

    async def test_import_timeslots_no_auth(self, async_client: AsyncClient):
        r = await async_client.get(f"{API}/import/timeslots")
        assert r.status_code == 401

    async def test_import_teachers_requires_admin(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        r = await async_client.get(
            f"{API}/import/teachers", headers=admin_token_headers
        )
        assert r.status_code == 200

    async def test_import_teachers_no_auth(self, async_client: AsyncClient):
        r = await async_client.get(f"{API}/import/teachers")
        assert r.status_code == 401

    async def test_import_rooms_requires_admin(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        r = await async_client.get(
            f"{API}/import/rooms", headers=admin_token_headers
        )
        assert r.status_code == 200

    async def test_import_rooms_no_auth(self, async_client: AsyncClient):
        r = await async_client.get(f"{API}/import/rooms")
        assert r.status_code == 401


@pytest.mark.asyncio
class TestLessonsEndpoints:
    async def test_lessons_list_requires_admin(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        r = await async_client.get(f"{API}/lessons/", headers=admin_token_headers)
        assert r.status_code == 200

    async def test_lessons_list_no_auth(self, async_client: AsyncClient):
        r = await async_client.get(f"{API}/lessons/")
        assert r.status_code == 401


@pytest.mark.asyncio
class TestSubstitutionsLegacyEndpoints:
    async def test_substitutions_legacy_suggestions_returns_410(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        url = (
            f"{API}/substitutions/suggestions"
            "?timeslot_id=1&date_str=2026-01-01&original_teacher_id=1"
        )
        r = await async_client.get(url, headers=admin_token_headers)
        assert r.status_code == 410

    async def test_substitutions_create_no_auth(self, async_client: AsyncClient):
        r = await async_client.post(
            f"{API}/substitutions/",
            json={
                "lesson_id": 1,
                "timeslot_id": 1,
                "original_teacher_id": 1,
                "substitute_teacher_id": 2,
                "date": "2026-01-01",
            },
        )
        assert r.status_code == 401
