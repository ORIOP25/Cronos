import asyncio
import faulthandler
import sys

import pytest
from httpx import ASGITransport, AsyncClient

from app import models
from app.api import deps
from app.main import app

pytestmark = pytest.mark.postgresql


async def _await_with_diagnostics(coro, *, timeout: float, operation: str):
    task = asyncio.create_task(coro, name=operation)
    done, _ = await asyncio.wait({task}, timeout=timeout)
    if task in done:
        return task.result()

    print(f"Timed out while {operation}; pending task stack:", file=sys.stderr, flush=True)
    task.print_stack(file=sys.stderr)
    task.cancel()
    raise AssertionError(f"Timed out while {operation}")


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
    return org, user, mem


@pytest.fixture
def override_auth_actor(db_session):
    async def _get_db():
        yield db_session

    app.dependency_overrides[deps.get_db] = _get_db

    def _override(actor: deps.Actor):
        async def _get_current_user_override():
            return actor

        app.dependency_overrides[deps.get_current_user] = _get_current_user_override

    yield _override
    app.dependency_overrides.pop(deps.get_current_user, None)
    app.dependency_overrides.pop(deps.get_db, None)


async def test_foundation_endpoints_full_lifecycle(db_session, override_auth_actor):
    faulthandler.dump_traceback_later(10, repeat=True)
    org, user, mem = await _await_with_diagnostics(
        _create_org_and_admin(
            db_session,
            "Lifecycle Org",
            "org_lifecycle_test",
            models.OrganizationFoundationStatus.NOT_STARTED,
        ),
        timeout=10,
        operation="creating the Foundation lifecycle test organization",
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
            return await _await_with_diagnostics(
                ac.request(method, path, **kwargs),
                timeout=10,
                operation=f"requesting {method} {path}",
            )

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
