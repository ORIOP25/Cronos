import pytest
from datetime import time
from uuid import uuid4
from unittest.mock import patch

from httpx import AsyncClient

from app import models
from app.config import settings
from app.models import UserRole
from tests.conftest import mock_clerk_payload


API = settings.API_V1_STR


async def _create_teacher_auth_headers(
    db_session,
    *,
    organization_id: int,
    teacher_id: int | None,
    is_active: bool = True,
    role: UserRole = UserRole.teacher,
) -> tuple[dict, str]:
    cid = f"role_reg_{uuid4().hex[:8]}"
    user = models.User(
        email=f"teacher.role.regression.{uuid4().hex[:8]}@escola.pt",
        clerk_user_id=cid,
        is_active=is_active,
        role=role,
        organization_id=organization_id,
        teacher_id=teacher_id,
    )
    db_session.add(user)
    await db_session.commit()
    return {"Authorization": f"Bearer test_{cid}"}, cid


async def _patch_and_call(cid, headers, endpoint, async_client, method="GET", **kwargs):
    role = "member"
    payload = mock_clerk_payload(cid, None, role)
    with patch("app.api.deps.get_clerk_payload", return_value=payload):
        if method == "GET":
            return await async_client.get(endpoint, headers=headers, **kwargs)
        elif method == "POST":
            return await async_client.post(endpoint, headers=headers, **kwargs)


async def _patch_loop(cid, headers, endpoint, async_client, count, **kwargs):
    payload = mock_clerk_payload(cid, None, "member")
    with patch("app.api.deps.get_clerk_payload", return_value=payload):
        for _ in range(count):
            response = await async_client.get(endpoint, headers=headers, **kwargs)
            assert response.status_code == 200


@pytest.mark.asyncio
class TestTeacherRoleRegressionContracts:
    async def test_teacher_self_availability_contract_200(self, async_client: AsyncClient, admin_token_headers: dict, db_session):
        timeslots_resp = await async_client.post(
            f"{API}/timeslots/generate",
            json={"start_time": "08:00", "end_time": "10:00", "slot_duration_minutes": 50, "break_duration_minutes": 10, "days_of_week": [0]},
            headers=admin_token_headers,
        )
        assert timeslots_resp.status_code in (200, 201)
        slot_rows = (await async_client.get(f"{API}/timeslots/", headers=admin_token_headers)).json()
        teacher_resp = await async_client.post(
            f"{API}/teachers/", json={"name": "Prof. Contract 200", "email": f"contract200.{uuid4().hex[:8]}@escola.pt"}, headers=admin_token_headers,
        )
        assert teacher_resp.status_code == 200
        teacher_id = teacher_resp.json()["id"]
        write_resp = await async_client.post(
            f"{API}/teachers/{teacher_id}/availability", json=[{"timeslot_id": slot_rows[0]["id"], "score": 2}], headers=admin_token_headers,
        )
        assert write_resp.status_code == 200
        teacher_headers, cid = await _create_teacher_auth_headers(db_session, organization_id=1, teacher_id=teacher_id)
        read_resp = await _patch_and_call(cid, teacher_headers, f"{API}/teachers/me/availability", async_client)
        assert read_resp.status_code == 200
        payload_data = read_resp.json()
        assert isinstance(payload_data, list)
        assert len(payload_data) == 1
        assert payload_data[0]["timeslot_id"] == slot_rows[0]["id"]
        assert payload_data[0]["score"] == 2

    async def test_teacher_self_availability_contract_403(self, async_client: AsyncClient, admin_token_headers: dict, db_session):
        admin_resp = await async_client.get(f"{API}/teachers/me/availability", headers=admin_token_headers)
        assert admin_resp.status_code == 403
        teacher_without_profile_headers, cid_np = await _create_teacher_auth_headers(db_session, organization_id=1, teacher_id=None)
        no_profile_resp = await _patch_and_call(cid_np, teacher_without_profile_headers, f"{API}/teachers/me/availability", async_client)
        assert no_profile_resp.status_code == 403

    async def test_teacher_self_availability_contract_404_cross_tenant_profile(self, async_client: AsyncClient, db_session):
        org_a = models.Organization(name=f"Org A Role {uuid4().hex[:6]}", plan_status="active")
        org_b = models.Organization(name=f"Org B Role {uuid4().hex[:6]}", plan_status="active")
        db_session.add_all([org_a, org_b])
        await db_session.flush()
        teacher_a = models.Teacher(name="Prof. Org A Role", organization_id=org_a.id)
        db_session.add(teacher_a)
        await db_session.flush()
        db_session.add(models.Timeslot(day_of_week=0, start_time=time(8, 0), end_time=time(9, 0), organization_id=org_a.id))
        await db_session.flush()
        db_session.add(models.Availability(teacher_id=teacher_a.id, timeslot_id=1, score=2))
        await db_session.commit()
        mismatched_headers, cid = await _create_teacher_auth_headers(db_session, organization_id=org_b.id, teacher_id=teacher_a.id)
        resp = await _patch_and_call(cid, mismatched_headers, f"{API}/teachers/me/availability", async_client)
        assert resp.status_code == 404

    async def test_teacher_horizon_contract_200_403_404(self, async_client: AsyncClient, admin_token_headers: dict, db_session):
        settings_resp = await async_client.post(
            f"{API}/school/settings/", json={"academic_year": "2025/2026", "school_start_date": "2025-09-01", "school_target_end_date": "2026-06-30", "school_hard_end_date": "2026-07-31"}, headers=admin_token_headers,
        )
        assert settings_resp.status_code == 200
        teacher_resp = await async_client.post(
            f"{API}/teachers/", json={"name": "Prof. Horizon 200", "email": f"horizon200.{uuid4().hex[:8]}@escola.pt"}, headers=admin_token_headers,
        )
        assert teacher_resp.status_code == 200
        teacher_headers, cid = await _create_teacher_auth_headers(db_session, organization_id=1, teacher_id=teacher_resp.json()["id"])
        ok_resp = await _patch_and_call(cid, teacher_headers, f"{API}/schedule/me/horizon", async_client)
        assert ok_resp.status_code == 200
        assert "active_generation_id" in ok_resp.json()
        admin_resp = await async_client.get(f"{API}/schedule/me/horizon", headers=admin_token_headers)
        assert admin_resp.status_code == 403
        org_without_settings = models.Organization(name=f"Org Sem Horizon {uuid4().hex[:6]}", plan_status="active")
        db_session.add(org_without_settings)
        await db_session.flush()
        teacher_without_settings = models.Teacher(name="Prof. Sem Horizon", organization_id=org_without_settings.id)
        db_session.add(teacher_without_settings)
        await db_session.flush()
        no_settings_headers, cid2 = await _create_teacher_auth_headers(db_session, organization_id=org_without_settings.id, teacher_id=teacher_without_settings.id)
        not_found_resp = await _patch_and_call(cid2, no_settings_headers, f"{API}/schedule/me/horizon", async_client)
        assert not_found_resp.status_code == 404

    async def test_teacher_horizon_polling_volume_does_not_trip_old_global_limit(self, async_client: AsyncClient, admin_token_headers: dict, db_session):
        settings_resp = await async_client.post(
            f"{API}/school/settings/", json={"academic_year": "2025/2026", "school_start_date": "2025-09-01", "school_target_end_date": "2026-06-30", "school_hard_end_date": "2026-07-31"}, headers=admin_token_headers,
        )
        assert settings_resp.status_code == 200
        teacher_resp = await async_client.post(
            f"{API}/teachers/", json={"name": "Prof. Horizon Polling", "email": f"horizonpoll.{uuid4().hex[:8]}@escola.pt"}, headers=admin_token_headers,
        )
        assert teacher_resp.status_code == 200
        teacher_headers, cid = await _create_teacher_auth_headers(db_session, organization_id=1, teacher_id=teacher_resp.json()["id"])
        await _patch_loop(cid, teacher_headers, f"{API}/schedule/me/horizon", async_client, 55)

    async def test_teacher_week_navigation_volume_does_not_trip_old_global_limit(self, async_client: AsyncClient, admin_token_headers: dict, db_session):
        teacher_resp = await async_client.post(
            f"{API}/teachers/", json={"name": "Prof. Week Navigation", "email": f"weeknav.{uuid4().hex[:8]}@escola.pt"}, headers=admin_token_headers,
        )
        assert teacher_resp.status_code == 200
        teacher_headers, cid = await _create_teacher_auth_headers(db_session, organization_id=1, teacher_id=teacher_resp.json()["id"])
        await _patch_loop(cid, teacher_headers, f"{API}/schedule/week", async_client, 70, params={"week_start": "2026-04-20"})

    async def test_teacher_week_schedule_contract_403_and_422(self, async_client: AsyncClient, admin_token_headers: dict, db_session):
        teacher_resp = await async_client.post(
            f"{API}/teachers/", json={"name": "Prof. Week Scope", "email": f"weekscope.{uuid4().hex[:8]}@escola.pt"}, headers=admin_token_headers,
        )
        assert teacher_resp.status_code == 200
        teacher_id = teacher_resp.json()["id"]
        teacher_headers, cid = await _create_teacher_auth_headers(db_session, organization_id=1, teacher_id=teacher_id)
        missing_week_resp = await _patch_and_call(cid, teacher_headers, f"{API}/schedule/week", async_client)
        assert missing_week_resp.status_code == 422
        invalid_week_resp = await _patch_and_call(cid, teacher_headers, f"{API}/schedule/week", async_client, params={"week_start": "not-a-date"})
        assert invalid_week_resp.status_code == 422
        class_scope_resp = await _patch_and_call(cid, teacher_headers, f"{API}/schedule/week", async_client, params={"week_start": "2026-04-20", "class_id": 1})
        assert class_scope_resp.status_code == 403
        other_teacher_resp = await _patch_and_call(cid, teacher_headers, f"{API}/schedule/week", async_client, params={"week_start": "2026-04-20", "teacher_id": teacher_id + 999})
        assert other_teacher_resp.status_code == 403

    async def test_student_is_denied_on_teacher_self_service_and_week_schedule(self, async_client: AsyncClient, admin_token_headers: dict, db_session):
        teacher_resp = await async_client.post(
            f"{API}/teachers/", json={"name": "Prof. Student Deny", "email": f"deny.student.{uuid4().hex[:8]}@escola.pt"}, headers=admin_token_headers,
        )
        assert teacher_resp.status_code == 200
        teacher_id = teacher_resp.json()["id"]
        student_headers, cid = await _create_teacher_auth_headers(db_session, organization_id=1, teacher_id=None, role=UserRole.student)
        availability_resp = await _patch_and_call(cid, student_headers, f"{API}/teachers/{teacher_id}/availability", async_client, "POST", json=[])
        assert availability_resp.status_code == 403
        week_resp = await _patch_and_call(cid, student_headers, f"{API}/schedule/week", async_client, params={"week_start": "2026-04-20", "teacher_id": teacher_id})
        assert week_resp.status_code == 403

    async def test_availability_rejects_duplicate_timeslot_without_data_loss(self, async_client: AsyncClient, admin_token_headers: dict, db_session):
        timeslots_resp = await async_client.post(
            f"{API}/timeslots/generate", json={"start_time": "08:00", "end_time": "10:00", "slot_duration_minutes": 50, "break_duration_minutes": 10, "days_of_week": [0]}, headers=admin_token_headers,
        )
        assert timeslots_resp.status_code in (200, 201)
        slot_rows = (await async_client.get(f"{API}/timeslots/", headers=admin_token_headers)).json()
        teacher_resp = await async_client.post(
            f"{API}/teachers/", json={"name": "Prof. Duplicate", "email": f"duplicate.{uuid4().hex[:8]}@escola.pt"}, headers=admin_token_headers,
        )
        assert teacher_resp.status_code == 200
        teacher_id = teacher_resp.json()["id"]
        baseline_resp = await async_client.post(
            f"{API}/teachers/{teacher_id}/availability", json=[{"timeslot_id": slot_rows[0]["id"], "score": 2}], headers=admin_token_headers,
        )
        assert baseline_resp.status_code == 200
        duplicate_resp = await async_client.post(
            f"{API}/teachers/{teacher_id}/availability", json=[{"timeslot_id": slot_rows[0]["id"], "score": 1}, {"timeslot_id": slot_rows[0]["id"], "score": 0}], headers=admin_token_headers,
        )
        assert duplicate_resp.status_code == 400
        assert "duplicado" in duplicate_resp.json()["detail"].lower()
        teacher_headers, cid = await _create_teacher_auth_headers(db_session, organization_id=1, teacher_id=teacher_id)
        persisted_resp = await _patch_and_call(cid, teacher_headers, f"{API}/teachers/me/availability", async_client)
        assert persisted_resp.status_code == 200
        persisted_rows = persisted_resp.json()
        assert len(persisted_rows) == 1
        assert persisted_rows[0]["timeslot_id"] == slot_rows[0]["id"]
        assert persisted_rows[0]["score"] == 2
