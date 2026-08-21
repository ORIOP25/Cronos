from datetime import UTC, date, datetime, time

import pytest
from httpx import ASGITransport, AsyncClient

from app import models
from app.api import deps
from app.main import app
from app.services.preflight_service import PreflightService

pytestmark = pytest.mark.postgresql


async def _create_org_and_admin(db_session, org_name: str, clerk_org: str):
    org = models.Organization(
        name=org_name,
        clerk_org_id=clerk_org,
        plan_status=models.OrganizationPlanStatus.active,
        foundation_status=models.OrganizationFoundationStatus.COMPLETED,
        foundation_completed_at=datetime.now(UTC),
    )
    db_session.add(org)
    await db_session.flush()

    user = models.User(
        name="Preflight Admin",
        email=f"preflight_{clerk_org}@test.com",
        clerk_user_id=f"user_{clerk_org}",
    )
    db_session.add(user)
    await db_session.flush()

    mem = models.OrganizationMembership(
        organization_id=org.id,
        account_id=user.id,
        organization_display_name="Preflight Admin",
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


async def test_preflight_service_returns_canonical_report(db_session):
    org, user, mem = await _create_org_and_admin(
        db_session, "Preflight Service School", "org_preflight_svc"
    )

    # Add academic year settings
    settings = models.OrganizationSettings(
        organization_id=org.id,
        school_start_date=date(2025, 9, 15),
        school_hard_end_date=date(2026, 7, 31),
    )
    db_session.add(settings)

    # Add timeslot
    ts = models.Timeslot(
        organization_id=org.id,
        day_of_week=0,
        start_time=time(8, 30),
        end_time=time(9, 20),
    )
    db_session.add(ts)
    await db_session.flush()

    service = PreflightService(db_session)
    report = await service.evaluate(organization_id=org.id)

    assert report.status == "BLOCKED"
    issue_codes = {issue.code for issue in report.issues}
    assert "ACTIVE_SCHOOL_YEAR_REQUIRED" in issue_codes
    assert "MISSING_ROOMS" in issue_codes
    assert "MISSING_TEACHERS" in issue_codes


async def test_preflight_endpoint_returns_report(db_session, override_auth_actor):
    org, user, mem = await _create_org_and_admin(
        db_session, "Preflight API School", "org_preflight_api"
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
        resp = await ac.get("/api/v1/readiness/prevalidation")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "BLOCKED"
        assert "issues" in data
        assert any(issue["code"] == "ACTIVE_SCHOOL_YEAR_REQUIRED" for issue in data["issues"])
