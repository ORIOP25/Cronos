"""Testes para endpoints de analytics, importação de dados e lessons."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


class TestAnalyticsEndpoints:
    async def test_heatmap_empty_no_teachers(self, async_client, admin_token_headers):
        response = await async_client.get(
            "/api/v1/analytics/availability-heatmap",
            headers=admin_token_headers,
        )
        assert response.status_code == 200
        assert response.json() == []

    async def test_heatmap_requires_auth(self, async_client):
        response = await async_client.get("/api/v1/analytics/availability-heatmap")
        assert response.status_code == 401


class TestImportEndpoints:
    async def test_get_timeslots_empty(self, async_client, admin_token_headers):
        response = await async_client.get(
            "/api/v1/import/timeslots",
            headers=admin_token_headers,
        )
        assert response.status_code == 200
        assert response.json() == []

    async def test_get_teachers_requires_admin(self, async_client, admin_token_headers):
        response = await async_client.get(
            "/api/v1/import/teachers",
            headers=admin_token_headers,
        )
        assert response.status_code == 200

    async def test_get_teachers_no_auth(self, async_client):
        response = await async_client.get("/api/v1/import/teachers")
        assert response.status_code == 401

    async def test_get_rooms_requires_admin(self, async_client, admin_token_headers):
        response = await async_client.get(
            "/api/v1/import/rooms",
            headers=admin_token_headers,
        )
        assert response.status_code == 200

    async def test_get_rooms_no_auth(self, async_client):
        response = await async_client.get("/api/v1/import/rooms")
        assert response.status_code == 401


class TestLessonsEndpoint:
    async def test_list_lessons_empty(self, async_client, admin_token_headers):
        response = await async_client.get(
            "/api/v1/lessons/",
            headers=admin_token_headers,
        )
        assert response.status_code == 200

    async def test_list_lessons_no_auth(self, async_client):
        response = await async_client.get("/api/v1/lessons/")
        assert response.status_code == 401


class TestSubstitutionsEndpoint:
    async def test_legacy_suggestions_returns_410(self, async_client, admin_token_headers):
        url = "/api/v1/substitutions/suggestions?timeslot_id=1&date_str=2026-01-01&original_teacher_id=1"
        response = await async_client.get(url, headers=admin_token_headers)
        assert response.status_code == 410

    async def test_create_substitution_no_auth(self, async_client):
        response = await async_client.post(
            "/api/v1/substitutions/",
            json={
                "lesson_id": 1, "timeslot_id": 1,
                "original_teacher_id": 1, "substitute_teacher_id": 2,
                "date": "2026-01-01",
            },
        )
        assert response.status_code == 401
