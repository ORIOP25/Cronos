"""
Testes de Disponibilidade e Self-Service (Paintbrush)
Parte de test_business_logic.py (split).
"""
import pytest
from unittest.mock import patch
from httpx import AsyncClient
from datetime import date, time, timedelta
from uuid import uuid4
from app import models
from app.models import UserRole
from test_business_logic_shared import API, _create_teacher_auth_headers
from tests.conftest import create_teacher_profile, create_teacher_user, ensure_membership_capabilities, mock_clerk_payload


async def _make_teacher_call(async_client, db_session, teacher_id, org_id, clerk_id, endpoint, method="GET", json_data=None):
    """Helper: aplica patch e faz chamada autenticada como teacher."""
    headers = {"Authorization": f"Bearer test_{clerk_id}"}
    payload = mock_clerk_payload(clerk_id, None, "member")
    with patch("app.api.deps.get_clerk_payload", return_value=payload):
        if method == "GET":
            return await async_client.get(endpoint, headers=headers)
        elif method == "PATCH":
            return await async_client.patch(endpoint, json=json_data, headers=headers)
        elif method == "POST":
            return await async_client.post(endpoint, json=json_data, headers=headers)


@pytest.mark.asyncio
class TestTeacherAvailability:

    async def test_set_availability(self, async_client: AsyncClient, admin_token_headers: dict, db_session):
        await async_client.post(
            f"{API}/timeslots/generate",
            json={
                "start_time": "08:00", "end_time": "10:00",
                "slot_duration_minutes": 50, "break_duration_minutes": 10,
                "days_of_week": [0],
            },
            headers=admin_token_headers,
        )
        slots_resp = await async_client.get(f"{API}/timeslots/", headers=admin_token_headers)
        slot_ids = [s["id"] for s in slots_resp.json()]
        assert len(slot_ids) >= 2

        teacher = await create_teacher_profile(db_session, organization_id=1, name="Prof. Disp")
        await db_session.commit()
        teacher_id = teacher.id

        payload = [
            {"timeslot_id": slot_ids[0], "score": 2},
            {"timeslot_id": slot_ids[1], "score": -1},
        ]
        resp = await async_client.post(
            f"{API}/teachers/{teacher_id}/availability",
            json=payload,
            headers=admin_token_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["count"] == 2

    async def test_availability_invalid_timeslot_400(self, async_client: AsyncClient, admin_token_headers: dict, db_session):
        teacher = await create_teacher_profile(db_session, organization_id=1, name="Prof. Bad")
        await db_session.commit()
        teacher_id = teacher.id
        resp = await async_client.post(
            f"{API}/teachers/{teacher_id}/availability",
            json=[{"timeslot_id": 99999, "score": 1}],
            headers=admin_token_headers,
        )
        assert resp.status_code == 400

    async def test_availability_teacher_not_found_404(self, async_client: AsyncClient, admin_token_headers: dict):
        resp = await async_client.post(
            f"{API}/teachers/99999/availability", json=[], headers=admin_token_headers,
        )
        assert resp.status_code == 404

    async def test_availability_overwrite(self, async_client: AsyncClient, admin_token_headers: dict, db_session):
        await async_client.post(
            f"{API}/timeslots/generate",
            json={
                "start_time": "08:00", "end_time": "10:00",
                "slot_duration_minutes": 50, "break_duration_minutes": 10,
                "days_of_week": [0],
            },
            headers=admin_token_headers,
        )
        slots = (await async_client.get(f"{API}/timeslots/", headers=admin_token_headers)).json()
        slot_id = slots[0]["id"]

        teacher = await create_teacher_profile(db_session, organization_id=1, name="Prof. Over")
        await db_session.commit()
        teacher_id = teacher.id

        await async_client.post(
            f"{API}/teachers/{teacher_id}/availability",
            json=[{"timeslot_id": slot_id, "score": 2}],
            headers=admin_token_headers,
        )
        resp = await async_client.post(
            f"{API}/teachers/{teacher_id}/availability",
            json=[{"timeslot_id": slot_id, "score": -1}],
            headers=admin_token_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    async def test_teacher_can_read_own_availability_self_endpoint(
        self, async_client: AsyncClient, admin_token_headers: dict, db_session,
    ):
        await async_client.post(
            f"{API}/timeslots/generate",
            json={
                "start_time": "08:00", "end_time": "10:00",
                "slot_duration_minutes": 50, "break_duration_minutes": 10,
                "days_of_week": [0],
            },
            headers=admin_token_headers,
        )
        slots = (await async_client.get(f"{API}/timeslots/", headers=admin_token_headers)).json()
        slot_ids = [s["id"] for s in slots]

        teacher = await create_teacher_profile(db_session, organization_id=1, name="Prof. Self")
        await db_session.commit()
        teacher_id = teacher.id

        set_resp = await async_client.post(
            f"{API}/teachers/{teacher_id}/availability",
            json=[
                {"timeslot_id": slot_ids[0], "score": 2},
                {"timeslot_id": slot_ids[1], "score": -1},
            ],
            headers=admin_token_headers,
        )
        assert set_resp.status_code == 200

        teacher_headers, cid = await _create_teacher_auth_headers(
            db_session, teacher_id=teacher_id, organization_id=1,
        )
        payload = mock_clerk_payload(cid, None, "member")
        with patch("app.api.deps.get_clerk_payload", return_value=payload):
            read_resp = await async_client.get(
                f"{API}/teachers/me/availability", headers=teacher_headers,
            )
        assert read_resp.status_code == 200
        data = read_resp.json()
        assert len(data) == 2
        scores_by_slot = {item["timeslot_id"]: item["score"] for item in data}
        assert scores_by_slot[slot_ids[0]] == 2
        assert scores_by_slot[slot_ids[1]] == -1

    async def test_admin_cannot_read_teacher_self_availability(
        self, async_client: AsyncClient, admin_token_headers: dict,
    ):
        resp = await async_client.get(
            f"{API}/teachers/me/availability", headers=admin_token_headers,
        )
        assert resp.status_code == 403

    async def test_teacher_without_profile_cannot_read_self_availability(
        self, async_client: AsyncClient, db_session,
    ):
        org = models.Organization(name=f"Org Sem Perfil {uuid4().hex[:6]}", plan_status="active")
        db_session.add(org)
        await db_session.flush()

        cid = f"noprofile_{uuid4().hex[:8]}"
        no_profile_user = models.User(
            email=f"teacher.noprofile.{uuid4().hex[:8]}@escola.pt",
            clerk_user_id=cid,
            is_active=True, role=UserRole.teacher,
            organization_id=org.id, teacher_id=None,
        )
        db_session.add(no_profile_user)
        await db_session.flush()
        await ensure_membership_capabilities(
            db_session,
            organization_id=org.id,
            user=no_profile_user,
            capabilities=[models.MembershipCapability.teacher],
            expected_clerk_role=models.ClerkOrganizationRole.member,
            teacher_access_mode=models.TeacherAccessMode.platform,
        )
        await db_session.commit()

        payload = mock_clerk_payload(cid, None, "member")
        with patch("app.api.deps.get_clerk_payload", return_value=payload):
            resp = await async_client.get(
                f"{API}/teachers/me/availability",
                headers={"Authorization": f"Bearer test_{cid}"},
            )
        assert resp.status_code == 403

    async def test_inactive_teacher_cannot_read_self_availability(
        self, async_client: AsyncClient, admin_token_headers: dict, db_session,
    ):
        teacher = await create_teacher_profile(db_session, organization_id=1, name="Prof. Inativo")
        await db_session.commit()
        teacher_id = teacher.id

        cid = f"inactive_{uuid4().hex[:8]}"
        inactive_user = models.User(
            email=f"teacher.inactive.{uuid4().hex[:8]}@escola.pt",
            clerk_user_id=cid,
            is_active=False, role=UserRole.teacher,
            organization_id=1, teacher_id=teacher_id,
        )
        db_session.add(inactive_user)
        await db_session.flush()
        membership = await ensure_membership_capabilities(
            db_session,
            organization_id=1,
            user=inactive_user,
            capabilities=[models.MembershipCapability.teacher],
            expected_clerk_role=models.ClerkOrganizationRole.member,
            teacher_access_mode=models.TeacherAccessMode.platform,
        )
        membership.access_status = models.MembershipAccessStatus.none
        await db_session.commit()

        payload = mock_clerk_payload(cid, None, "member")
        with patch("app.api.deps.get_clerk_payload", return_value=payload):
            resp = await async_client.get(
                f"{API}/teachers/me/availability",
                headers={"Authorization": f"Bearer test_{cid}"},
            )
        assert resp.status_code == 403

    async def test_teacher_cannot_read_admin_teacher_listing(
        self, async_client: AsyncClient, admin_token_headers: dict, db_session,
    ):
        teacher = await create_teacher_profile(db_session, organization_id=1, name="Prof. Scoped")
        await db_session.commit()
        teacher_id = teacher.id

        teacher_headers, cid = await _create_teacher_auth_headers(
            db_session, teacher_id=teacher_id, organization_id=1,
        )
        payload = mock_clerk_payload(cid, None, "member")
        with patch("app.api.deps.get_clerk_payload", return_value=payload):
            resp = await async_client.get(f"{API}/teachers/", headers=teacher_headers)
        assert resp.status_code == 403

    async def test_teacher_can_read_schedule_horizon_self_endpoint(
        self, async_client: AsyncClient, admin_token_headers: dict, db_session,
    ):
        settings_resp = await async_client.post(
            f"{API}/school/settings/",
            json={
                "school_start_date": "2025-09-01",
                "school_hard_end_date": "2026-07-31",
            },
            headers=admin_token_headers,
        )
        assert settings_resp.status_code == 200

        teacher = await create_teacher_profile(db_session, organization_id=1, name="Prof. Horizon")
        await db_session.commit()
        teacher_id = teacher.id

        teacher_headers, cid = await _create_teacher_auth_headers(
            db_session, teacher_id=teacher_id, organization_id=1,
        )
        payload = mock_clerk_payload(cid, None, "member")
        with patch("app.api.deps.get_clerk_payload", return_value=payload):
            horizon_resp = await async_client.get(f"{API}/schedule/me/horizon", headers=teacher_headers)
        assert horizon_resp.status_code == 200
        data = horizon_resp.json()
        assert data["hard_end_date"] == "2026-07-31"
        assert "active_generation_id" in data
        assert data["active_generation_id"] is None
        assert date.fromisoformat(data["week_start_recommended"]) <= date.fromisoformat(data["hard_end_date"])

    async def test_admin_cannot_read_teacher_schedule_horizon(
        self, async_client: AsyncClient, admin_token_headers: dict,
    ):
        resp = await async_client.get(f"{API}/schedule/me/horizon", headers=admin_token_headers)
        assert resp.status_code == 403

    async def test_teacher_without_profile_cannot_read_schedule_horizon(
        self, async_client: AsyncClient, db_session,
    ):
        org = models.Organization(name=f"Org Horizon Sem Perfil {uuid4().hex[:6]}", plan_status="active")
        db_session.add(org)
        await db_session.flush()
        cid = f"horizon_noprofile_{uuid4().hex[:8]}"
        no_profile_user = models.User(
            email=f"teacher.horizon.noprofile.{uuid4().hex[:8]}@escola.pt",
            clerk_user_id=cid,
            is_active=True, role=UserRole.teacher,
            organization_id=org.id, teacher_id=None,
        )
        db_session.add(no_profile_user)
        await db_session.flush()
        await ensure_membership_capabilities(
            db_session,
            organization_id=org.id,
            user=no_profile_user,
            capabilities=[models.MembershipCapability.teacher],
            expected_clerk_role=models.ClerkOrganizationRole.member,
            teacher_access_mode=models.TeacherAccessMode.platform,
        )
        await db_session.commit()
        payload = mock_clerk_payload(cid, None, "member")
        with patch("app.api.deps.get_clerk_payload", return_value=payload):
            resp = await async_client.get(
                f"{API}/schedule/me/horizon",
                headers={"Authorization": f"Bearer test_{cid}"},
            )
        assert resp.status_code == 403

    async def test_teacher_schedule_horizon_is_tenant_scoped(
        self, async_client: AsyncClient, admin_token_headers: dict, db_session,
    ):
        settings_org1 = await async_client.post(
            f"{API}/school/settings/",
            json={
                "school_start_date": "2025-09-01",
                "school_hard_end_date": "2026-07-31",
            },
            headers=admin_token_headers,
        )
        assert settings_org1.status_code == 200

        teacher_org1 = await create_teacher_profile(db_session, organization_id=1, name="Prof. Org1")
        await db_session.commit()
        teacher_org1_id = teacher_org1.id
        teacher_org1_headers, cid1 = await _create_teacher_auth_headers(
            db_session, teacher_id=teacher_org1_id, organization_id=1,
        )

        org2 = models.Organization(name=f"Escola B {uuid4().hex[:6]}", plan_status="active")
        db_session.add(org2)
        await db_session.flush()
        teacher_org2 = models.Teacher(name="Prof. Org2", organization_id=org2.id)
        db_session.add(teacher_org2)
        await db_session.flush()
        settings_org2 = models.OrganizationSettings(
            organization_id=org2.id,
            school_start_date=date(2027, 9, 1),
            school_hard_end_date=date(2028, 7, 31),
        )
        db_session.add(settings_org2)

        cid2 = f"org2_{uuid4().hex[:8]}"
        await create_teacher_user(
            db_session,
            clerk_user_id=cid2,
            email=f"teacher.org2.{uuid4().hex[:8]}@escola.pt",
            org_id=org2.id,
            teacher_id=teacher_org2.id,
        )
        await db_session.commit()

        payload1 = mock_clerk_payload(cid1, None, "member")
        with patch("app.api.deps.get_clerk_payload", return_value=payload1):
            resp_org1 = await async_client.get(
                f"{API}/schedule/me/horizon", headers=teacher_org1_headers,
            )
        assert resp_org1.status_code == 200
        assert resp_org1.json()["hard_end_date"] == "2026-07-31"

        payload2 = mock_clerk_payload(cid2, None, "member")
        with patch("app.api.deps.get_clerk_payload", return_value=payload2):
            resp_org2 = await async_client.get(
                f"{API}/schedule/me/horizon",
                headers={"Authorization": f"Bearer test_{cid2}"},
            )
        assert resp_org2.status_code == 200
        assert resp_org2.json()["hard_end_date"] == "2028-07-31"

    async def test_teacher_schedule_horizon_returns_404_without_settings(
        self, async_client: AsyncClient, db_session,
    ):
        org = models.Organization(name=f"Org Sem Settings {uuid4().hex[:6]}", plan_status="active")
        db_session.add(org)
        await db_session.flush()
        teacher = models.Teacher(name="Prof. Sem Settings", organization_id=org.id)
        db_session.add(teacher)
        await db_session.flush()
        teacher_headers, cid = await _create_teacher_auth_headers(
            db_session, teacher_id=teacher.id, organization_id=org.id,
        )
        payload = mock_clerk_payload(cid, None, "member")
        with patch("app.api.deps.get_clerk_payload", return_value=payload):
            resp = await async_client.get(f"{API}/schedule/me/horizon", headers=teacher_headers)
        assert resp.status_code == 404

    async def test_teacher_self_availability_is_tenant_scoped_when_profile_id_belongs_to_other_org(
        self, async_client: AsyncClient, db_session,
    ):
        org_a = models.Organization(name=f"Org A Avail {uuid4().hex[:6]}", plan_status="active")
        org_b = models.Organization(name=f"Org B Avail {uuid4().hex[:6]}", plan_status="active")
        db_session.add_all([org_a, org_b])
        await db_session.flush()
        teacher_a = models.Teacher(name="Prof. Org A", organization_id=org_a.id)
        db_session.add(teacher_a)
        await db_session.flush()
        timeslot_a = models.Timeslot(
            day_of_week=0, start_time=time(8, 0), end_time=time(9, 0),
            organization_id=org_a.id,
        )
        db_session.add(timeslot_a)
        await db_session.flush()
        db_session.add(models.Availability(teacher_id=teacher_a.id, timeslot_id=timeslot_a.id, score=2))
        await db_session.commit()

        mismatched_headers, cid = await _create_teacher_auth_headers(
            db_session, teacher_id=teacher_a.id, organization_id=org_b.id,
        )
        payload = mock_clerk_payload(cid, None, "member")
        with patch("app.api.deps.get_clerk_payload", return_value=payload):
            resp = await async_client.get(f"{API}/teachers/me/availability", headers=mismatched_headers)
        assert resp.status_code == 404

    async def test_teacher_week_schedule_is_tenant_scoped_when_profile_id_belongs_to_other_org(
        self, async_client: AsyncClient, db_session,
    ):
        org_a = models.Organization(name=f"Org A Week {uuid4().hex[:6]}", plan_status="active")
        org_b = models.Organization(name=f"Org B Week {uuid4().hex[:6]}", plan_status="active")
        db_session.add_all([org_a, org_b])
        await db_session.flush()
        teacher_a = models.Teacher(name="Prof. Week Org A", organization_id=org_a.id)
        db_session.add(teacher_a)
        await db_session.flush()
        subject_a = models.Subject(
            name="Disciplina Week Org A", organization_id=org_a.id,
            required_room_type=models.RoomType.normal,
        )
        db_session.add(subject_a)
        await db_session.flush()
        db_session.add(models.Module(name="Modulo Week Org A", hours_total=20, order=1, subject_id=subject_a.id))
        course_a = models.Course(
            name="Curso Week Org A", abbreviation=f"WA{uuid4().hex[:2].upper()}", organization_id=org_a.id,
        )
        db_session.add(course_a)
        await db_session.flush()
        class_a = models.Class(
            name="Turma Week Org A", size=20, start_year=2025, end_year=2028,
            grade_level=10, course_id=course_a.id, organization_id=org_a.id,
        )
        db_session.add(class_a)
        await db_session.flush()
        room_a = models.Room(name="Sala Week Org A", capacity=30, type=models.RoomType.normal, organization_id=org_a.id)
        db_session.add(room_a)
        await db_session.flush()
        timeslot_a = models.Timeslot(
            day_of_week=0, start_time=time(9, 0), end_time=time(11, 0), organization_id=org_a.id,
        )
        db_session.add(timeslot_a)
        await db_session.flush()
        lesson_a = models.Lesson(
            organization_id=org_a.id, class_id=class_a.id, subject_id=subject_a.id, teacher_id=teacher_a.id,
        )
        db_session.add(lesson_a)
        await db_session.flush()
        week_start = date.today() - timedelta(days=date.today().weekday())
        db_session.add(models.ScheduleOutput(
            organization_id=org_a.id, lesson_id=lesson_a.id,
            timeslot_id=timeslot_a.id, room_id=room_a.id,
            generation_id="tenant-week-a", date=week_start, is_draft=False,
        ))
        await db_session.commit()

        mismatched_headers, cid = await _create_teacher_auth_headers(
            db_session, teacher_id=teacher_a.id, organization_id=org_b.id,
        )
        payload = mock_clerk_payload(cid, None, "member")
        with patch("app.api.deps.get_clerk_payload", return_value=payload):
            resp = await async_client.get(
                f"{API}/schedule/week", headers=mismatched_headers,
                params={"week_start": week_start.isoformat()},
            )
        assert resp.status_code == 200
        assert resp.json() == []
