"""Testes para endpoints de analytics, importação, lessons e substitutions."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_analytics_heatmap_empty_no_teachers(async_client, admin_token_headers):
    r = await async_client.get("/api/v1/analytics/availability-heatmap", headers=admin_token_headers)
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_analytics_heatmap_requires_auth(async_client):
    r = await async_client.get("/api/v1/analytics/availability-heatmap")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_import_timeslots_empty(async_client, admin_token_headers):
    r = await async_client.get("/api/v1/import/timeslots", headers=admin_token_headers)
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_import_teachers_requires_admin(async_client, admin_token_headers):
    r = await async_client.get("/api/v1/import/teachers", headers=admin_token_headers)
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_import_teachers_no_auth(async_client):
    r = await async_client.get("/api/v1/import/teachers")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_import_rooms_requires_admin(async_client, admin_token_headers):
    r = await async_client.get("/api/v1/import/rooms", headers=admin_token_headers)
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_import_rooms_no_auth(async_client):
    r = await async_client.get("/api/v1/import/rooms")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_lessons_list_empty(async_client, admin_token_headers):
    r = await async_client.get("/api/v1/lessons/", headers=admin_token_headers)
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_lessons_list_no_auth(async_client):
    r = await async_client.get("/api/v1/lessons/")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_substitutions_legacy_suggestions_returns_410(async_client, admin_token_headers):
    url = "/api/v1/substitutions/suggestions?timeslot_id=1&date_str=2026-01-01&original_teacher_id=1"
    r = await async_client.get(url, headers=admin_token_headers)
    assert r.status_code == 410


@pytest.mark.asyncio
async def test_substitutions_create_no_auth(async_client):
    r = await async_client.post(
        "/api/v1/substitutions/",
        json={"lesson_id": 1, "timeslot_id": 1, "original_teacher_id": 1, "substitute_teacher_id": 2, "date": "2026-01-01"},
    )
    assert r.status_code == 401
