from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import AsyncClient
from limits import parse

from app import models
from app.config import settings
from app.core.ratelimit import limiter
from tests._support.db_fixtures import (
    accept_current_legal_documents,
    create_teacher_profile,
    create_teacher_user,
    ensure_membership_capabilities,
)
from tests.roles import UserRole

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
    if role == UserRole.teacher and teacher_id is not None:
        user = await create_teacher_user(
            db_session,
            clerk_user_id=cid,
            email=f"teacher.role.regression.{uuid4().hex[:8]}@escola.pt",
            name="Teacher Role Regression",
            org_id=organization_id,
            teacher_id=teacher_id,
        )
    else:
        user = models.User(
            email=f"teacher.role.regression.{uuid4().hex[:8]}@escola.pt",
            clerk_user_id=cid,
        )
        db_session.add(user)
        await db_session.flush()
        capabilities = [models.MembershipCapability.teacher] if role == UserRole.teacher else []
        await ensure_membership_capabilities(
            db_session,
            organization_id=organization_id,
            user=user,
            capabilities=capabilities,
            expected_clerk_role=models.ClerkOrganizationRole.member,
            teacher_access_mode=(models.TeacherAccessMode.platform if capabilities else None),
        )
    from sqlalchemy import select

    membership = await db_session.scalar(
        select(models.OrganizationMembership).where(
            models.OrganizationMembership.organization_id == organization_id,
            models.OrganizationMembership.account_id == user.id,
        )
    )
    assert membership is not None
    await accept_current_legal_documents(
        db_session,
        organization_id=organization_id,
        membership_id=membership.id,
    )
    if not is_active:
        membership = (
            await db_session.execute(
                select(models.OrganizationMembership).where(
                    models.OrganizationMembership.organization_id == organization_id,
                    models.OrganizationMembership.account_id == user.id,
                )
            )
        ).scalar_one()
        membership.access_status = models.MembershipAccessStatus.none
    await db_session.commit()
    return {"Authorization": f"Bearer test_{cid}"}, cid


async def _patch_and_call(cid, headers, endpoint, async_client, method="GET", **kwargs):
    if method == "GET":
        return await async_client.get(endpoint, headers=headers, **kwargs)
    return await async_client.post(endpoint, headers=headers, **kwargs)


def _seed_rate_limit(limit: str, *, ip: str, path: str, count: int) -> None:
    """Consume real Redis counters so the next request sits at the threshold.

    The seed uses the production limiter strategy and the exact ``(ip, path)``
    identifiers the endpoint decorator uses, so the seeded bucket is the one the
    real HTTP request observes.
    """
    item = parse(limit)
    for _ in range(count):
        assert limiter._limiter.hit(item, ip, path)


@pytest.fixture
def enabled_rate_limiter(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_IPS", "127.0.0.1/32")
    previous_enabled = limiter.enabled
    limiter.enabled = True
    limiter.reset()
    try:
        yield
    finally:
        limiter.reset()
        limiter.enabled = previous_enabled


class TestTeacherRoleRegressionContracts:
    async def test_teacher_self_availability_contract_200(
        self, async_client: AsyncClient, clerk_admin_headers: dict, db_session
    ):
        timeslots_resp = await async_client.post(
            f"{API}/school/grid-settings/regenerate",
            json={
                "grid_settings": {},
                "timeslots": {
                    "start_time": "08:00",
                    "end_time": "10:00",
                    "slot_duration_minutes": 50,
                    "break_duration_minutes": 10,
                    "days_of_week": [0],
                },
            },
            headers=clerk_admin_headers,
        )
        assert timeslots_resp.status_code == 200
        slot_rows = (
            await async_client.get(f"{API}/timeslots/", headers=clerk_admin_headers)
        ).json()
        teacher = await create_teacher_profile(
            db_session, organization_id=1, name="Prof. Contract 200"
        )
        await db_session.commit()
        teacher_id = teacher.id
        teacher_headers, cid = await _create_teacher_auth_headers(
            db_session, organization_id=1, teacher_id=teacher_id
        )
        write_resp = await async_client.put(
            f"{API}/teachers/me/availability",
            json=[{"timeslot_id": slot["id"], "score": 2} for slot in slot_rows],
            headers=teacher_headers,
        )
        assert write_resp.status_code == 200
        read_resp = await _patch_and_call(
            cid, teacher_headers, f"{API}/teachers/me/availability", async_client
        )
        assert read_resp.status_code == 200
        payload_data = read_resp.json()
        assert isinstance(payload_data, list)
        assert len(payload_data) == len(slot_rows)
        assert payload_data[0]["timeslot_id"] == slot_rows[0]["id"]
        assert payload_data[0]["score"] == 2

    async def test_teacher_self_availability_contract_403(
        self, async_client: AsyncClient, clerk_admin_headers: dict, db_session
    ):
        admin_resp = await async_client.get(
            f"{API}/teachers/me/availability", headers=clerk_admin_headers
        )
        assert admin_resp.status_code == 403
        teacher_without_profile_headers, cid_np = await _create_teacher_auth_headers(
            db_session, organization_id=1, teacher_id=None
        )
        no_profile_resp = await _patch_and_call(
            cid_np, teacher_without_profile_headers, f"{API}/teachers/me/availability", async_client
        )
        assert no_profile_resp.status_code == 403

    async def test_teacher_identity_rejects_cross_tenant_profile(self, db_session):
        org_a = models.Organization(name=f"Org A Role {uuid4().hex[:6]}", plan_status="active")
        org_b = models.Organization(name=f"Org B Role {uuid4().hex[:6]}", plan_status="active")
        db_session.add_all([org_a, org_b])
        await db_session.flush()
        teacher_a = await create_teacher_profile(
            db_session,
            name="Prof. Org A Role",
            organization_id=org_a.id,
        )
        await db_session.commit()
        with pytest.raises(ValueError, match="does not belong"):
            await _create_teacher_auth_headers(
                db_session,
                organization_id=org_b.id,
                teacher_id=teacher_a.id,
            )

    async def test_teacher_horizon_contract_200_403_404(
        self, async_client: AsyncClient, clerk_admin_headers: dict, db_session
    ):
        settings_resp = await async_client.post(
            f"{API}/school/settings/",
            json={"school_start_date": "2025-09-01", "school_hard_end_date": "2026-07-31"},
            headers=clerk_admin_headers,
        )
        assert settings_resp.status_code == 200
        teacher = await create_teacher_profile(
            db_session, organization_id=1, name="Prof. Horizon 200"
        )
        await db_session.commit()
        teacher_headers, cid = await _create_teacher_auth_headers(
            db_session, organization_id=1, teacher_id=teacher.id
        )
        ok_resp = await _patch_and_call(
            cid, teacher_headers, f"{API}/schedule/me/horizon", async_client
        )
        assert ok_resp.status_code == 200
        assert "active_generation_id" in ok_resp.json()
        admin_resp = await async_client.get(
            f"{API}/schedule/me/horizon", headers=clerk_admin_headers
        )
        assert admin_resp.status_code == 403
        org_without_settings = models.Organization(
            name=f"Org Sem Horizon {uuid4().hex[:6]}",
            plan_status="active",
            foundation_status=models.OrganizationFoundationStatus.COMPLETED,
            foundation_completed_at=datetime.now(UTC),
        )
        db_session.add(org_without_settings)
        await db_session.flush()
        teacher_without_settings = await create_teacher_profile(
            db_session,
            name="Prof. Sem Horizon",
            organization_id=org_without_settings.id,
        )
        no_settings_headers, cid2 = await _create_teacher_auth_headers(
            db_session,
            organization_id=org_without_settings.id,
            teacher_id=teacher_without_settings.id,
        )
        not_found_resp = await _patch_and_call(
            cid2, no_settings_headers, f"{API}/schedule/me/horizon", async_client
        )
        assert not_found_resp.status_code == 404

    @pytest.mark.xdist_group("rate-limit-volume")
    async def test_teacher_horizon_volume_proves_override_above_old_global_limit(
        self,
        async_client: AsyncClient,
        clerk_admin_headers: dict,
        db_session,
        enabled_rate_limiter,
    ):
        settings_resp = await async_client.post(
            f"{API}/school/settings/",
            json={"school_start_date": "2025-09-01", "school_hard_end_date": "2026-07-31"},
            headers=clerk_admin_headers,
        )
        assert settings_resp.status_code == 200
        teacher = await create_teacher_profile(
            db_session, organization_id=1, name="Prof. Horizon Polling"
        )
        await db_session.commit()
        teacher_headers, _ = await _create_teacher_auth_headers(
            db_session, organization_id=1, teacher_id=teacher.id
        )
        ip = "198.51.100.51"
        path = f"{API}/schedule/me/horizon"
        # Seed both the registered 300/hour route bucket and the retired default
        # 50/hour bucket on the exact same ``(ip, path)`` identifiers. A correctly
        # registered override ignores the default, so the 51st request still passes.
        _seed_rate_limit("300/hour", ip=ip, path=path, count=50)
        _seed_rate_limit("50/hour", ip=ip, path=path, count=50)

        response = await async_client.get(path, headers={**teacher_headers, "x-real-ip": ip})

        assert response.status_code == 200
        route = limiter._limiter.get_window_stats(parse("300/hour"), ip, path)
        assert route.remaining == 249
        # The default bucket is untouched by the request. If the override broke and
        # the default 50/hour also applied, this request would have returned 429.
        default = limiter._limiter.get_window_stats(parse("50/hour"), ip, path)
        assert default.remaining == 0

    @pytest.mark.xdist_group("rate-limit-volume")
    async def test_teacher_week_volume_enforces_the_real_minute_limit(
        self,
        async_client: AsyncClient,
        clerk_admin_headers: dict,
        db_session,
        enabled_rate_limiter,
    ):
        teacher = await create_teacher_profile(
            db_session, organization_id=1, name="Prof. Week Navigation"
        )
        await db_session.commit()
        teacher_headers, _ = await _create_teacher_auth_headers(
            db_session, organization_id=1, teacher_id=teacher.id
        )
        ip = "198.51.100.60"
        path = f"{API}/schedule/week"
        params = {"week_start": "2026-04-20"}
        _seed_rate_limit("60/minute", ip=ip, path=path, count=59)

        allowed = await async_client.get(
            path, headers={**teacher_headers, "x-real-ip": ip}, params=params
        )
        assert allowed.status_code == 200
        exceeded = await async_client.get(
            path, headers={**teacher_headers, "x-real-ip": ip}, params=params
        )
        # The 61st request in the same minute hits the real configured 60/minute limit.
        assert exceeded.status_code == 429
        assert exceeded.headers.get("Retry-After") == "60"
        minute = parse("60/minute")
        assert limiter._storage.get(minute.key_for(ip, path)) == 61
        assert limiter._limiter.get_window_stats(minute, ip, path).remaining == 0

    async def test_teacher_week_schedule_contract_403_and_422(
        self, async_client: AsyncClient, clerk_admin_headers: dict, db_session
    ):
        teacher = await create_teacher_profile(
            db_session, organization_id=1, name="Prof. Week Scope"
        )
        await db_session.commit()
        teacher_id = teacher.id
        teacher_headers, cid = await _create_teacher_auth_headers(
            db_session, organization_id=1, teacher_id=teacher_id
        )
        missing_week_resp = await _patch_and_call(
            cid, teacher_headers, f"{API}/schedule/week", async_client
        )
        assert missing_week_resp.status_code == 422
        invalid_week_resp = await _patch_and_call(
            cid,
            teacher_headers,
            f"{API}/schedule/week",
            async_client,
            params={"week_start": "not-a-date"},
        )
        assert invalid_week_resp.status_code == 422
        class_scope_resp = await _patch_and_call(
            cid,
            teacher_headers,
            f"{API}/schedule/week",
            async_client,
            params={"week_start": "2026-04-20", "class_id": 1},
        )
        assert class_scope_resp.status_code == 403
        other_teacher_resp = await _patch_and_call(
            cid,
            teacher_headers,
            f"{API}/schedule/week",
            async_client,
            params={"week_start": "2026-04-20", "teacher_id": teacher_id + 999},
        )
        assert other_teacher_resp.status_code == 403

    async def test_availability_rejects_duplicate_timeslot_without_data_loss(
        self, async_client: AsyncClient, clerk_admin_headers: dict, db_session
    ):
        timeslots_resp = await async_client.post(
            f"{API}/school/grid-settings/regenerate",
            json={
                "grid_settings": {},
                "timeslots": {
                    "start_time": "08:00",
                    "end_time": "10:00",
                    "slot_duration_minutes": 50,
                    "break_duration_minutes": 10,
                    "days_of_week": [0],
                },
            },
            headers=clerk_admin_headers,
        )
        assert timeslots_resp.status_code == 200
        slot_rows = (
            await async_client.get(f"{API}/timeslots/", headers=clerk_admin_headers)
        ).json()
        teacher = await create_teacher_profile(
            db_session, organization_id=1, name="Prof. Duplicate"
        )
        await db_session.commit()
        teacher_id = teacher.id
        teacher_headers, cid = await _create_teacher_auth_headers(
            db_session, organization_id=1, teacher_id=teacher_id
        )
        baseline_resp = await async_client.put(
            f"{API}/teachers/me/availability",
            json=[{"timeslot_id": slot["id"], "score": 2} for slot in slot_rows],
            headers=teacher_headers,
        )
        assert baseline_resp.status_code == 200
        duplicate_resp = await async_client.put(
            f"{API}/teachers/me/availability",
            json=[
                {"timeslot_id": slot_rows[0]["id"], "score": 1},
                {"timeslot_id": slot_rows[0]["id"], "score": 0},
            ],
            headers=teacher_headers,
        )
        assert duplicate_resp.status_code == 400
        assert "duplicado" in duplicate_resp.json()["detail"]["message"].lower()
        persisted_resp = await _patch_and_call(
            cid, teacher_headers, f"{API}/teachers/me/availability", async_client
        )
        assert persisted_resp.status_code == 200
        persisted_rows = persisted_resp.json()
        assert len(persisted_rows) == len(slot_rows)
        assert persisted_rows[0]["timeslot_id"] == slot_rows[0]["id"]
        assert persisted_rows[0]["score"] == 2

    async def test_teacher_cannot_read_write_or_copy_class_availability(
        self, async_client: AsyncClient, clerk_admin_headers: dict, db_session
    ):
        course = models.Course(name="Curso Class Avail", abbreviation="CCA", organization_id=1)
        db_session.add(course)
        await db_session.flush()
        class_row = models.Class(
            name="Turma Class Avail",
            size=20,
            start_year=2025,
            end_year=2028,
            grade_level=10,
            course_id=course.id,
            organization_id=1,
        )
        db_session.add(class_row)
        await db_session.flush()
        teacher = await create_teacher_profile(
            db_session, organization_id=1, name="Prof. Class Avail"
        )
        await db_session.commit()
        teacher_headers, _ = await _create_teacher_auth_headers(
            db_session, organization_id=1, teacher_id=teacher.id
        )

        read_resp = await async_client.get(
            f"{API}/classes/{class_row.id}/availability", headers=teacher_headers
        )
        assert read_resp.status_code == 403

        write_resp = await async_client.put(
            f"{API}/classes/{class_row.id}/availability",
            json=[{"timeslot_id": 1, "score": 1}],
            headers=teacher_headers,
        )
        assert write_resp.status_code == 403

        copy_resp = await async_client.post(
            f"{API}/classes/{class_row.id}/availability/copy",
            json={"target_class_ids": [class_row.id + 1]},
            headers=teacher_headers,
        )
        assert copy_resp.status_code == 403
