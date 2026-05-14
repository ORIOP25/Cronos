import pytest
from datetime import time
from uuid import uuid4

from httpx import AsyncClient

from app import models
from app.config import settings
from app.core.security import create_access_token
from app.models import UserRole


API = settings.API_V1_STR


async def _create_teacher_auth_headers(
    db_session,
    *,
    organization_id: int,
    teacher_id: int | None,
    is_active: bool = True,
    role: UserRole = UserRole.teacher,
) -> dict:
    email = f"teacher.role.regression.{uuid4().hex[:8]}@escola.pt"
    user = models.User(
        email=email,
        is_active=is_active,
        role=role,
        organization_id=organization_id,
        teacher_id=teacher_id,
    )
    db_session.add(user)
    await db_session.commit()

    token = create_access_token(data={"sub": email})
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
class TestTeacherRoleRegressionContracts:
    async def test_teacher_self_availability_contract_200(self, async_client: AsyncClient, admin_token_headers: dict, db_session):
        timeslots_resp = await async_client.post(
            f"{API}/timeslots/generate",
            json={
                "start_time": "08:00",
                "end_time": "10:00",
                "slot_duration_minutes": 50,
                "break_duration_minutes": 10,
                "days_of_week": [0],
            },
            headers=admin_token_headers,
        )
        assert timeslots_resp.status_code in (200, 201)

        slot_rows = (await async_client.get(f"{API}/timeslots/", headers=admin_token_headers)).json()
        teacher_resp = await async_client.post(
            f"{API}/teachers/",
            json={"name": "Prof. Contract 200", "email": f"contract200.{uuid4().hex[:8]}@escola.pt"},
            headers=admin_token_headers,
        )
        assert teacher_resp.status_code == 200
        teacher_id = teacher_resp.json()["id"]

        write_resp = await async_client.post(
            f"{API}/teachers/{teacher_id}/availability",
            json=[{"timeslot_id": slot_rows[0]["id"], "score": 2}],
            headers=admin_token_headers,
        )
        assert write_resp.status_code == 200

        teacher_headers = await _create_teacher_auth_headers(
            db_session,
            organization_id=1,
            teacher_id=teacher_id,
        )
        read_resp = await async_client.get(
            f"{API}/teachers/me/availability",
            headers=teacher_headers,
        )

        assert read_resp.status_code == 200
        payload = read_resp.json()
        assert isinstance(payload, list)
        assert len(payload) == 1
        assert payload[0]["timeslot_id"] == slot_rows[0]["id"]
        assert payload[0]["score"] == 2

    async def test_teacher_self_availability_contract_403(self, async_client: AsyncClient, admin_token_headers: dict, db_session):
        admin_resp = await async_client.get(
            f"{API}/teachers/me/availability",
            headers=admin_token_headers,
        )
        assert admin_resp.status_code == 403

        teacher_without_profile_headers = await _create_teacher_auth_headers(
            db_session,
            organization_id=1,
            teacher_id=None,
        )
        no_profile_resp = await async_client.get(
            f"{API}/teachers/me/availability",
            headers=teacher_without_profile_headers,
        )
        assert no_profile_resp.status_code == 403

    async def test_teacher_self_availability_contract_404_cross_tenant_profile(self, async_client: AsyncClient, db_session):
        org_a = models.Organization(name=f"Org A Role {uuid4().hex[:6]}", plan_status="active")
        org_b = models.Organization(name=f"Org B Role {uuid4().hex[:6]}", plan_status="active")
        db_session.add_all([org_a, org_b])
        await db_session.flush()

        teacher_a = models.Teacher(name="Prof. Org A Role", organization_id=org_a.id)
        db_session.add(teacher_a)
        await db_session.flush()

        timeslot_a = models.Timeslot(
            day_of_week=0,
            start_time=time(8, 0),
            end_time=time(9, 0),
            organization_id=org_a.id,
        )
        db_session.add(timeslot_a)
        await db_session.flush()

        db_session.add(models.Availability(
            teacher_id=teacher_a.id,
            timeslot_id=timeslot_a.id,
            score=2,
        ))
        await db_session.commit()

        mismatched_headers = await _create_teacher_auth_headers(
            db_session,
            organization_id=org_b.id,
            teacher_id=teacher_a.id,
        )

        resp = await async_client.get(
            f"{API}/teachers/me/availability",
            headers=mismatched_headers,
        )
        assert resp.status_code == 404

    async def test_teacher_horizon_contract_200_403_404(self, async_client: AsyncClient, admin_token_headers: dict, db_session):
        settings_resp = await async_client.post(
            f"{API}/school/settings/",
            json={
                "academic_year": "2025/2026",
                "school_start_date": "2025-09-01",
                "school_target_end_date": "2026-06-30",
                "school_hard_end_date": "2026-07-31",
            },
            headers=admin_token_headers,
        )
        assert settings_resp.status_code == 200

        teacher_resp = await async_client.post(
            f"{API}/teachers/",
            json={"name": "Prof. Horizon 200", "email": f"horizon200.{uuid4().hex[:8]}@escola.pt"},
            headers=admin_token_headers,
        )
        assert teacher_resp.status_code == 200
        teacher_headers = await _create_teacher_auth_headers(
            db_session,
            organization_id=1,
            teacher_id=teacher_resp.json()["id"],
        )

        ok_resp = await async_client.get(f"{API}/schedule/me/horizon", headers=teacher_headers)
        assert ok_resp.status_code == 200
        assert "active_generation_id" in ok_resp.json()
        assert "min_week_start" in ok_resp.json()

        admin_resp = await async_client.get(f"{API}/schedule/me/horizon", headers=admin_token_headers)
        assert admin_resp.status_code == 403

        org_without_settings = models.Organization(name=f"Org Sem Horizon {uuid4().hex[:6]}", plan_status="active")
        db_session.add(org_without_settings)
        await db_session.flush()

        teacher_without_settings = models.Teacher(
            name="Prof. Sem Horizon",
            organization_id=org_without_settings.id,
        )
        db_session.add(teacher_without_settings)
        await db_session.flush()

        no_settings_headers = await _create_teacher_auth_headers(
            db_session,
            organization_id=org_without_settings.id,
            teacher_id=teacher_without_settings.id,
        )

        not_found_resp = await async_client.get(f"{API}/schedule/me/horizon", headers=no_settings_headers)
        assert not_found_resp.status_code == 404

    async def test_teacher_horizon_polling_volume_does_not_trip_old_global_limit(
        self,
        async_client: AsyncClient,
        admin_token_headers: dict,
        db_session,
    ):
        settings_resp = await async_client.post(
            f"{API}/school/settings/",
            json={
                "academic_year": "2025/2026",
                "school_start_date": "2025-09-01",
                "school_target_end_date": "2026-06-30",
                "school_hard_end_date": "2026-07-31",
            },
            headers=admin_token_headers,
        )
        assert settings_resp.status_code == 200

        teacher_resp = await async_client.post(
            f"{API}/teachers/",
            json={"name": "Prof. Horizon Polling", "email": f"horizonpoll.{uuid4().hex[:8]}@escola.pt"},
            headers=admin_token_headers,
        )
        assert teacher_resp.status_code == 200

        teacher_headers = await _create_teacher_auth_headers(
            db_session,
            organization_id=1,
            teacher_id=teacher_resp.json()["id"],
        )

        # 55 pedidos simulam polling sustentado acima do limite global antigo (50/hour).
        for _ in range(55):
            response = await async_client.get(
                f"{API}/schedule/me/horizon",
                headers=teacher_headers,
            )
            assert response.status_code == 200

    async def test_teacher_week_navigation_volume_does_not_trip_old_global_limit(
        self,
        async_client: AsyncClient,
        admin_token_headers: dict,
        db_session,
    ):
        teacher_resp = await async_client.post(
            f"{API}/teachers/",
            json={"name": "Prof. Week Navigation", "email": f"weeknav.{uuid4().hex[:8]}@escola.pt"},
            headers=admin_token_headers,
        )
        assert teacher_resp.status_code == 200

        teacher_headers = await _create_teacher_auth_headers(
            db_session,
            organization_id=1,
            teacher_id=teacher_resp.json()["id"],
        )

        # 70 pedidos simulam navegação semanal ativa acima do limite global antigo (50/hour).
        for _ in range(70):
            response = await async_client.get(
                f"{API}/schedule/week",
                params={"week_start": "2026-04-20"},
                headers=teacher_headers,
            )
            assert response.status_code == 200

    async def test_teacher_week_schedule_contract_403_and_422(self, async_client: AsyncClient, admin_token_headers: dict, db_session):
        teacher_resp = await async_client.post(
            f"{API}/teachers/",
            json={"name": "Prof. Week Scope", "email": f"weekscope.{uuid4().hex[:8]}@escola.pt"},
            headers=admin_token_headers,
        )
        assert teacher_resp.status_code == 200
        teacher_id = teacher_resp.json()["id"]

        teacher_headers = await _create_teacher_auth_headers(
            db_session,
            organization_id=1,
            teacher_id=teacher_id,
        )

        missing_week_resp = await async_client.get(
            f"{API}/schedule/week",
            headers=teacher_headers,
        )
        assert missing_week_resp.status_code == 422

        invalid_week_resp = await async_client.get(
            f"{API}/schedule/week",
            headers=teacher_headers,
            params={"week_start": "not-a-date"},
        )
        assert invalid_week_resp.status_code == 422

        class_scope_resp = await async_client.get(
            f"{API}/schedule/week",
            headers=teacher_headers,
            params={"week_start": "2026-04-20", "class_id": 1},
        )
        assert class_scope_resp.status_code == 403

        other_teacher_resp = await async_client.get(
            f"{API}/schedule/week",
            headers=teacher_headers,
            params={"week_start": "2026-04-20", "teacher_id": teacher_id + 999},
        )
        assert other_teacher_resp.status_code == 403

    async def test_student_is_denied_on_teacher_self_service_and_week_schedule(
        self,
        async_client: AsyncClient,
        admin_token_headers: dict,
        db_session,
    ):
        teacher_resp = await async_client.post(
            f"{API}/teachers/",
            json={"name": "Prof. Student Deny", "email": f"deny.student.{uuid4().hex[:8]}@escola.pt"},
            headers=admin_token_headers,
        )
        assert teacher_resp.status_code == 200
        teacher_id = teacher_resp.json()["id"]

        student_headers = await _create_teacher_auth_headers(
            db_session,
            organization_id=1,
            teacher_id=None,
            role=UserRole.student,
        )

        availability_resp = await async_client.post(
            f"{API}/teachers/{teacher_id}/availability",
            json=[],
            headers=student_headers,
        )
        assert availability_resp.status_code == 403

        week_resp = await async_client.get(
            f"{API}/schedule/week",
            params={"week_start": "2026-04-20", "teacher_id": teacher_id},
            headers=student_headers,
        )
        assert week_resp.status_code == 403

    async def test_availability_rejects_duplicate_timeslot_without_data_loss(
        self,
        async_client: AsyncClient,
        admin_token_headers: dict,
        db_session,
    ):
        timeslots_resp = await async_client.post(
            f"{API}/timeslots/generate",
            json={
                "start_time": "08:00",
                "end_time": "10:00",
                "slot_duration_minutes": 50,
                "break_duration_minutes": 10,
                "days_of_week": [0],
            },
            headers=admin_token_headers,
        )
        assert timeslots_resp.status_code in (200, 201)

        slot_rows = (await async_client.get(f"{API}/timeslots/", headers=admin_token_headers)).json()
        teacher_resp = await async_client.post(
            f"{API}/teachers/",
            json={"name": "Prof. Duplicate", "email": f"duplicate.{uuid4().hex[:8]}@escola.pt"},
            headers=admin_token_headers,
        )
        assert teacher_resp.status_code == 200
        teacher_id = teacher_resp.json()["id"]

        baseline_resp = await async_client.post(
            f"{API}/teachers/{teacher_id}/availability",
            json=[{"timeslot_id": slot_rows[0]["id"], "score": 2}],
            headers=admin_token_headers,
        )
        assert baseline_resp.status_code == 200

        duplicate_resp = await async_client.post(
            f"{API}/teachers/{teacher_id}/availability",
            json=[
                {"timeslot_id": slot_rows[0]["id"], "score": 1},
                {"timeslot_id": slot_rows[0]["id"], "score": 0},
            ],
            headers=admin_token_headers,
        )
        assert duplicate_resp.status_code == 400
        assert "duplicado" in duplicate_resp.json()["detail"].lower()

        teacher_headers = await _create_teacher_auth_headers(
            db_session,
            organization_id=1,
            teacher_id=teacher_id,
        )
        persisted_resp = await async_client.get(
            f"{API}/teachers/me/availability",
            headers=teacher_headers,
        )
        assert persisted_resp.status_code == 200
        persisted_rows = persisted_resp.json()
        assert len(persisted_rows) == 1
        assert persisted_rows[0]["timeslot_id"] == slot_rows[0]["id"]
        assert persisted_rows[0]["score"] == 2
