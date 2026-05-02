"""Testes para endpoints de analytics e importação de dados."""

import pytest
from httpx import AsyncClient
from app.config import settings

pytestmark = pytest.mark.integration


class TestAnalyticsEndpoints:
    async def test_heatmap_empty_no_teachers(self, async_client, admin_token_headers):
        response = await async_client.get(
            f"{settings.API_V1_STR}/analytics/availability-heatmap",
            headers=admin_token_headers,
        )
        assert response.status_code == 200
        assert response.json() == []

    async def test_heatmap_requires_auth(self, async_client):
        response = await async_client.get(
            f"{settings.API_V1_STR}/analytics/availability-heatmap",
        )
        assert response.status_code == 401


class TestImportEndpoints:
    async def test_get_timeslots_empty(self, async_client, admin_token_headers):
        response = await async_client.get(
            f"{settings.API_V1_STR}/import/timeslots",
            headers=admin_token_headers,
        )
        assert response.status_code == 200
        assert response.json() == []

    async def test_get_teachers_requires_admin(self, async_client, admin_token_headers):
        response = await async_client.get(
            f"{settings.API_V1_STR}/import/teachers",
            headers=admin_token_headers,
        )
        assert response.status_code == 200

    async def test_get_teachers_no_auth(self, async_client):
        response = await async_client.get(
            f"{settings.API_V1_STR}/import/teachers",
        )
        assert response.status_code == 401

    async def test_get_rooms_requires_admin(self, async_client, admin_token_headers):
        response = await async_client.get(
            f"{settings.API_V1_STR}/import/rooms",
            headers=admin_token_headers,
        )
        assert response.status_code == 200

    async def test_get_rooms_no_auth(self, async_client):
        response = await async_client.get(
            f"{settings.API_V1_STR}/import/rooms",
        )
        assert response.status_code == 401


class TestLessonsEndpoint:
    async def test_list_lessons_empty(self, async_client, admin_token_headers):
        response = await async_client.get(
            f"{settings.API_V1_STR}/lessons/",
            headers=admin_token_headers,
        )
        assert response.status_code == 200

    async def test_list_lessons_no_auth(self, async_client):
        response = await async_client.get(
            f"{settings.API_V1_STR}/lessons/",
        )
        assert response.status_code == 401


class TestSubstitutionsEndpoint:
    async def test_legacy_suggestions_returns_410(self, async_client, admin_token_headers):
        response = await async_client.get(
            f"{settings.API_V1_STR}/substitutions/suggestions"
            "?timeslot_id=1&date_str=2026-01-01&original_teacher_id=1",
            headers=admin_token_headers,
        )
        assert response.status_code == 410

    async def test_create_substitution_no_auth(self, async_client):
        response = await async_client.post(
            f"{settings.API_V1_STR}/substitutions/",
            json={
                "lesson_id": 1, "timeslot_id": 1,
                "original_teacher_id": 1, "substitute_teacher_id": 2,
                "date": "2026-01-01",
            },
        )
        assert response.status_code == 401
