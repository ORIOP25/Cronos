from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app import models
from app.api import deps
from app.main import app
from app.services import settings_service
from tests._support.db_fixtures import accept_current_legal_documents

pytestmark = pytest.mark.postgresql


async def _create_org_and_admin(
    db_session, org_name: str, clerk_org: str, status: models.OrganizationFoundationStatus
):
    org = models.Organization(
        name=org_name,
        clerk_org_id=clerk_org,
        plan_status=models.OrganizationPlanStatus.active,
        foundation_status=status,
    )
    db_session.add(org)
    await db_session.flush()

    user = models.User(
        name="Foundation API Admin",
        email=f"admin_{clerk_org}@test.com",
        clerk_user_id=f"user_{clerk_org}",
    )
    db_session.add(user)
    await db_session.flush()

    mem = models.OrganizationMembership(
        organization_id=org.id,
        account_id=user.id,
        organization_display_name="Foundation API Admin",
        lifecycle_status=models.MembershipLifecycleStatus.active,
        access_status=models.MembershipAccessStatus.active,
        clerk_membership_id=f"mem_{clerk_org}",
        can_admin=True,
        can_teach=False,
    )
    db_session.add(mem)
    await db_session.flush()
    await accept_current_legal_documents(
        db_session,
        organization_id=org.id,
        membership_id=mem.id,
    )
    return org, user, mem


@pytest.fixture
def override_auth_actor(db_session):
    async def _get_db():
        try:
            yield db_session
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise

    app.dependency_overrides[deps.get_db] = _get_db

    def _override(actor: deps.Actor):
        async def _get_current_user_override():
            return actor

        app.dependency_overrides[deps.get_current_user] = _get_current_user_override

    yield _override
    app.dependency_overrides.pop(deps.get_current_user, None)
    app.dependency_overrides.pop(deps.get_db, None)


async def test_foundation_endpoints_full_lifecycle(db_session, override_auth_actor):
    org, user, mem = await _create_org_and_admin(
        db_session,
        "Lifecycle Org",
        "org_lifecycle_test",
        models.OrganizationFoundationStatus.NOT_STARTED,
    )
    actor = deps.Actor(
        account_id=user.id,
        clerk_user_id=user.clerk_user_id,
        organization_id=org.id,
        membership_id=mem.id,
        can_admin=True,
        can_teach=False,
        teacher_id=None,
    )
    override_auth_actor(actor)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:

        async def request(method: str, path: str, **kwargs):
            return await ac.request(method, path, **kwargs)

        # 1. Initial status is NOT_STARTED
        resp = await request("GET", "/api/v1/foundation/status")
        assert resp.status_code == 200
        assert resp.json()["foundation_status"] == "NOT_STARTED"

        # 2. /members/me is accessible in NOT_STARTED and returns foundation_status
        me_resp = await request("GET", "/api/v1/members/me")
        assert me_resp.status_code == 200
        assert me_resp.json()["foundation_status"] == "NOT_STARTED"

        # 3. Operational endpoints return 409 FOUNDATION_REQUIRED
        classes_resp = await request("GET", "/api/v1/classes/")
        assert classes_resp.status_code == 409
        assert classes_resp.json()["detail"]["code"] == "FOUNDATION_REQUIRED"

        # 4. Get initial draft -> version 0
        resp = await request("GET", "/api/v1/foundation/draft")
        assert resp.status_code == 200
        assert resp.json()["version"] == 0

        # 5. Save draft version 0 -> advances to 1
        put_payload = {
            "expected_version": 0,
            "current_step": 2,
            "data": {
                "school_start_date": "2025-09-15",
                "school_hard_end_date": "2026-07-31",
                "repair_stability_window_days": 14,
                "days_of_week": [0, 1, 2, 3, 4],
                "opening_time": "08:30:00",
                "closing_time": "17:30:00",
                "slot_duration_minutes": 50,
                "break_duration_minutes": 10,
                "lunch_window_start": "12:30:00",
                "lunch_window_end": "14:00:00",
                "lunch_min_duration_minutes": 60,
            },
        }
        resp = await request("PUT", "/api/v1/foundation/draft", json=put_payload)
        assert resp.status_code == 200
        assert resp.json()["version"] == 1

        # 6. Status is now IN_PROGRESS
        resp = await request("GET", "/api/v1/foundation/status")
        assert resp.status_code == 200
        assert resp.json()["foundation_status"] == "IN_PROGRESS"

        # 7. Stale save with expected_version 0 yields 409
        resp = await request("PUT", "/api/v1/foundation/draft", json=put_payload)
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "FOUNDATION_DRAFT_VERSION_CONFLICT"
        assert resp.json()["detail"]["current_version"] == 1

        # 8. Complete foundation with version 1 -> succeeds
        resp = await request(
            "POST", "/api/v1/foundation/complete", json={"expected_version": 1, "confirmed": True}
        )
        assert resp.status_code == 200
        assert resp.json()["foundation_status"] == "COMPLETED"
        assert resp.json()["generated_timeslot_count"] > 0

        # 9. Status is now COMPLETED
        resp = await request("GET", "/api/v1/foundation/status")
        assert resp.status_code == 200
        assert resp.json()["foundation_status"] == "COMPLETED"

        # 10. Attempting to save draft when COMPLETED yields 409
        resp = await request(
            "PUT",
            "/api/v1/foundation/draft",
            json={"expected_version": 1, "current_step": 1, "data": {}},
        )
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "FOUNDATION_ALREADY_COMPLETED"

        # 11. Operational endpoints are now accessible
        classes_resp = await request("GET", "/api/v1/classes/")
        assert classes_resp.status_code == 200


async def test_foundation_draft_automatic_holidays_failure_rolls_back_and_recovers(
    db_session, override_auth_actor, monkeypatch
):
    monkeypatch.setattr(
        settings_service,
        "_get_pt_holidays",
        lambda _years: {
            date(2025, 9, 15): "Início original",
            date(2026, 7, 31): "Fim original",
        },
    )
    org, user, mem = await _create_org_and_admin(
        db_session,
        "Draft Recovery Org",
        "org_draft_recovery_test",
        models.OrganizationFoundationStatus.NOT_STARTED,
    )
    org_id = org.id
    actor = deps.Actor(
        account_id=user.id,
        clerk_user_id=user.clerk_user_id,
        organization_id=org_id,
        membership_id=mem.id,
        can_admin=True,
        can_teach=False,
        teacher_id=None,
    )
    override_auth_actor(actor)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. Save initial draft with automatic holidays enabled -> version 1
        resp = await ac.put(
            "/api/v1/foundation/draft",
            json={
                "expected_version": 0,
                "current_step": 1,
                "data": {
                    "school_start_date": "2025-09-15",
                    "school_hard_end_date": "2026-07-31",
                    "automatic_holidays_enabled": True,
                },
            },
        )
        assert resp.status_code == 200
        assert resp.json()["version"] == 1

        events = (
            await db_session.scalars(
                select(models.SchoolCalendarEvent)
                .where(models.SchoolCalendarEvent.organization_id == org_id)
                .order_by(models.SchoolCalendarEvent.start_date)
            )
        ).all()
        assert [(e.start_date, e.name) for e in events] == [
            (date(2025, 9, 15), "Início original"),
            (date(2026, 7, 31), "Fim original"),
        ]

        # 2. Provoke failure during next draft save
        def fail_sync(_years):
            raise RuntimeError("provider unavailable")

        monkeypatch.setattr(settings_service, "_get_pt_holidays", fail_sync)

        failed_resp = await ac.put(
            "/api/v1/foundation/draft",
            json={
                "expected_version": 1,
                "current_step": 1,
                "data": {
                    "school_start_date": "2025-09-15",
                    "school_hard_end_date": "2026-08-31",
                    "automatic_holidays_enabled": True,
                },
            },
        )
        assert failed_resp.status_code == 503
        assert failed_resp.json()["detail"]["code"] == "HOLIDAY_SYNC_FAILED"

        # 3. Verify in draft that version did NOT advance and previous data is preserved
        draft_resp = await ac.get("/api/v1/foundation/draft")
        assert draft_resp.status_code == 200
        assert draft_resp.json()["version"] == 1
        assert draft_resp.json()["data"]["school_hard_end_date"] == "2026-07-31"

        events_after_fail = (
            await db_session.scalars(
                select(models.SchoolCalendarEvent)
                .where(models.SchoolCalendarEvent.organization_id == org_id)
                .order_by(models.SchoolCalendarEvent.start_date)
            )
        ).all()
        assert [(e.start_date, e.name) for e in events_after_fail] == [
            (date(2025, 9, 15), "Início original"),
            (date(2026, 7, 31), "Fim original"),
        ]

        # 4. Recover with automatic_holidays_enabled: False and new dates
        recover_resp = await ac.put(
            "/api/v1/foundation/draft",
            json={
                "expected_version": 1,
                "current_step": 1,
                "data": {
                    "school_start_date": "2025-09-15",
                    "school_hard_end_date": "2026-08-31",
                    "automatic_holidays_enabled": False,
                },
            },
        )
        assert recover_resp.status_code == 200
        assert recover_resp.json()["version"] == 2
        assert recover_resp.json()["data"]["school_hard_end_date"] == "2026-08-31"
        assert recover_resp.json()["data"]["automatic_holidays_enabled"] is False

        # Previous events still preserved
        events_after_recovery = (
            await db_session.scalars(
                select(models.SchoolCalendarEvent)
                .where(models.SchoolCalendarEvent.organization_id == org_id)
                .order_by(models.SchoolCalendarEvent.start_date)
            )
        ).all()
        assert [(e.start_date, e.name) for e in events_after_recovery] == [
            (date(2025, 9, 15), "Início original"),
            (date(2026, 7, 31), "Fim original"),
        ]

        # 5. Repeat operation with success when provider is restored -> no duplicates
        monkeypatch.setattr(
            settings_service,
            "_get_pt_holidays",
            lambda _years: {
                date(2025, 9, 15): "Início original",
                date(2026, 7, 31): "Fim original",
                date(2026, 8, 15): "Assunção",
            },
        )
        repeat_resp = await ac.put(
            "/api/v1/foundation/draft",
            json={
                "expected_version": 2,
                "current_step": 1,
                "data": {
                    "school_start_date": "2025-09-15",
                    "school_hard_end_date": "2026-08-31",
                    "automatic_holidays_enabled": True,
                },
            },
        )
        assert repeat_resp.status_code == 200
        assert repeat_resp.json()["version"] == 3

        events_after_success = (
            await db_session.scalars(
                select(models.SchoolCalendarEvent)
                .where(models.SchoolCalendarEvent.organization_id == org_id)
                .order_by(models.SchoolCalendarEvent.start_date)
            )
        ).all()
        assert [(e.start_date, e.name) for e in events_after_success] == [
            (date(2025, 9, 15), "Início original"),
            (date(2026, 7, 31), "Fim original"),
            (date(2026, 8, 15), "Assunção"),
        ]

        # Repeat again with identical configuration: version increments, no duplicates
        repeat_again_resp = await ac.put(
            "/api/v1/foundation/draft",
            json={
                "expected_version": 3,
                "current_step": 1,
                "data": {
                    "school_start_date": "2025-09-15",
                    "school_hard_end_date": "2026-08-31",
                    "automatic_holidays_enabled": True,
                },
            },
        )
        assert repeat_again_resp.status_code == 200
        assert repeat_again_resp.json()["version"] == 4

        events_after_repeat = (
            await db_session.scalars(
                select(models.SchoolCalendarEvent)
                .where(models.SchoolCalendarEvent.organization_id == org_id)
                .order_by(models.SchoolCalendarEvent.start_date)
            )
        ).all()
        assert [(e.start_date, e.name) for e in events_after_repeat] == [
            (date(2025, 9, 15), "Início original"),
            (date(2026, 7, 31), "Fim original"),
            (date(2026, 8, 15), "Assunção"),
        ]
