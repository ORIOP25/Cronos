"""
Testes de Endpoints HTTP de Ocorrências
Parte de test_occurrences.py (split).
"""
import pytest
import pytest_asyncio
from unittest.mock import patch
from datetime import date, datetime, timedelta, timezone

from httpx import AsyncClient
from sqlalchemy import select, func

from app import models
from app.models import LessonOccurrenceStatus
from app.services import occurrence_service
from test_occurrence_shared import full_setup, SyncTestSession, substitution_setup
from tests.conftest import mock_clerk_payload


class TestOccurrenceEndpoints:
    """Testes de integração para os endpoints HTTP de ocorrências."""

    @pytest_asyncio.fixture
    async def auth_headers(self, full_setup) -> dict:
        return {"Authorization": "Bearer test_occ_admin_001"}

    @pytest_asyncio.fixture
    async def teacher_auth_headers(self, substitution_setup) -> dict:
        return {"Authorization": "Bearer test_occ_teacher_001"}

    @pytest_asyncio.fixture
    async def _patch_admin(self, full_setup):
        payload = mock_clerk_payload("occ_admin_001", None, "admin")
        with patch("app.api.deps.get_clerk_payload", return_value=payload):
            yield

    @pytest_asyncio.fixture
    async def _patch_teacher(self, substitution_setup):
        payload = mock_clerk_payload("occ_teacher_001", None, "member")
        with patch("app.api.deps.get_clerk_payload", return_value=payload):
            yield

    async def _create_open_occurrence(self, async_client: AsyncClient, auth_headers: dict, schedule_output_id: int) -> int:
        response = await async_client.post(
            "/api/v1/occurrences/", headers=auth_headers,
            json={"schedule_output_id": schedule_output_id},
        )
        assert response.status_code in (200, 201)
        return int(response.json()["id"])

    @pytest.mark.asyncio
    async def test_list_occurrences_empty(        self, async_client: AsyncClient, full_setup, auth_headers, _patch_admin):
        response = await async_client.get("/api/v1/occurrences/", headers=auth_headers)
        assert response.status_code == 200
        assert response.json() == {"items": [], "total": 0, "limit": 100, "offset": 0}

    @pytest.mark.asyncio
    async def test_get_debts_empty(        self, async_client: AsyncClient, full_setup, auth_headers, _patch_admin):
        response = await async_client.get("/api/v1/occurrences/debts", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total_gaps"] == 0
        assert data["total_gaps_overdue"] == 0
        assert data["total_hours_owed_overdue"] == pytest.approx(0.0)
        assert isinstance(data["as_of_date"], str)
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_get_debts_includes_future_decided_gap(self, async_client, sync_db, full_setup, auth_headers, _patch_admin):
        future_date = date.today() + timedelta(days=5)
        future_output = models.ScheduleOutput(
            organization_id=full_setup["organization_id"],
            lesson_id=full_setup["lesson_id"],
            timeslot_id=full_setup["timeslot_id"],
            room_id=full_setup["room_id"],
            generation_id="future-gap-api-001",
            date=future_date,
            is_draft=False,
        )
        sync_db.add(future_output)
        sync_db.commit()

        create_response = await async_client.post(
            "/api/v1/occurrences/", headers=auth_headers,
            json={"schedule_output_id": future_output.id},
        )
        assert create_response.status_code == 201
        created_occurrence = create_response.json()
        occurrence_id = int(created_occurrence["id"])

        patch_response = await async_client.patch(
            f"/api/v1/occurrences/{occurrence_id}", headers=auth_headers,
            json={"status": "GAP", "version": created_occurrence["version"]},
        )
        assert patch_response.status_code == 200

        debts_response = await async_client.get("/api/v1/occurrences/debts", headers=auth_headers)
        assert debts_response.status_code == 200
        debt_data = debts_response.json()
        assert debt_data["total_gaps"] == 1
        assert debt_data["total_hours_owed"] == pytest.approx(2.0)
        assert debt_data["total_gaps_overdue"] == 0
        assert debt_data["total_hours_owed_overdue"] == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_get_occurrence_not_found(self, async_client, full_setup, auth_headers, _patch_admin):
        response = await async_client.get("/api/v1/occurrences/9999", headers=auth_headers)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_patch_occurrence_not_found(self, async_client, full_setup, auth_headers, _patch_admin):
        response = await async_client.patch(
            "/api/v1/occurrences/9999", headers=auth_headers, json={"status": "GAP", "version": 1},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_patch_occurrence_requires_version(self, async_client, full_setup, auth_headers, _patch_admin):
        occurrence_id = await self._create_open_occurrence(
            async_client, auth_headers, full_setup["schedule_output_id"],
        )
        response = await async_client.patch(
            f"/api/v1/occurrences/{occurrence_id}", headers=auth_headers, json={"status": "GAP"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_occurrence_from_block_returns_201_then_200(self, async_client, full_setup, auth_headers, _patch_admin):
        create_response = await async_client.post(
            "/api/v1/occurrences/", headers=auth_headers,
            json={"schedule_output_id": full_setup["schedule_output_id"]},
        )
        assert create_response.status_code == 201
        created = create_response.json()
        assert created["schedule_output_id"] == full_setup["schedule_output_id"]
        assert created["status"] is None
        assert created["operational_state"] == "OPEN_PENDING"
        assert created["decided_at"] is None

        second_response = await async_client.post(
            "/api/v1/occurrences/", headers=auth_headers,
            json={"schedule_output_id": full_setup["schedule_output_id"]},
        )
        assert second_response.status_code == 200
        reused = second_response.json()
        assert reused["id"] == created["id"]

    @pytest.mark.asyncio
    async def test_create_occurrence_then_first_decision_applies_accounting_once(
        self, async_client, sync_db, full_setup, auth_headers, _patch_admin,
    ):
        create_response = await async_client.post(
            "/api/v1/occurrences/", headers=auth_headers,
            json={"schedule_output_id": full_setup["schedule_output_id"]},
        )
        assert create_response.status_code == 201
        created_occurrence = create_response.json()
        occurrence_id = created_occurrence["id"]

        patch_response = await async_client.patch(
            f"/api/v1/occurrences/{occurrence_id}",
            headers=auth_headers,
            json={"status": "GAP", "version": created_occurrence["version"]},
        )
        assert patch_response.status_code == 200
        body = patch_response.json()
        assert body["status"] == "GAP"
        assert body["decided_at"] is not None

        progress = sync_db.execute(
            select(models.ClassProgress).where(
                models.ClassProgress.class_id == full_setup["class_id"],
                models.ClassProgress.module_id == full_setup["module_id"],
            )
        ).scalar_one()
        assert float(progress.hours_debt) == pytest.approx(2.0)
        assert float(progress.hours_completed) == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_create_occurrence_teacher_forbidden(
        self, async_client, substitution_setup, teacher_auth_headers, _patch_teacher,
    ):
        response = await async_client.post(
            "/api/v1/occurrences/", headers=teacher_auth_headers,
            json={"schedule_output_id": substitution_setup["schedule_output_id"]},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_list_occurrences_teacher_forbidden(
        self, async_client, substitution_setup, teacher_auth_headers, _patch_teacher,
    ):
        response = await async_client.get("/api/v1/occurrences/", headers=teacher_auth_headers)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_get_debts_teacher_forbidden(
        self, async_client, substitution_setup, teacher_auth_headers, _patch_teacher,
    ):
        response = await async_client.get("/api/v1/occurrences/debts", headers=teacher_auth_headers)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_get_occurrence_teacher_forbidden(
        self, async_client, substitution_setup, auth_headers, teacher_auth_headers, _patch_admin,
    ):
        occurrence_id = await self._create_open_occurrence(
            async_client, auth_headers, substitution_setup["schedule_output_id"],
        )
        payload_t = mock_clerk_payload("occ_teacher_001", None, "member")
        with patch("app.api.deps.get_clerk_payload", return_value=payload_t):
            response = await async_client.get(
                f"/api/v1/occurrences/{occurrence_id}", headers=teacher_auth_headers,
            )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_list_occurrences_requires_auth(self, async_client):
        response = await async_client.get("/api/v1/occurrences/")
        assert response.status_code == 401
