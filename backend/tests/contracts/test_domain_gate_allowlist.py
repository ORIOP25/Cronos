from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from app import models
from app.api import deps
from app.main import app
from tests._support.db_fixtures import accept_current_legal_documents

pytestmark = pytest.mark.postgresql


async def _create_org_and_admin(
    db_session, org_name: str, clerk_org: str, status: models.OrganizationFoundationStatus
):
    completed_at = (
        datetime.now(UTC) if status == models.OrganizationFoundationStatus.COMPLETED else None
    )
    org = models.Organization(
        name=org_name,
        clerk_org_id=clerk_org,
        plan_status=models.OrganizationPlanStatus.active,
        foundation_status=status,
        foundation_completed_at=completed_at,
    )
    db_session.add(org)
    await db_session.flush()

    user = models.User(
        name="Gate Admin",
        email=f"admin_{clerk_org}@test.com",
        clerk_user_id=f"user_{clerk_org}",
    )
    db_session.add(user)
    await db_session.flush()

    mem = models.OrganizationMembership(
        organization_id=org.id,
        account_id=user.id,
        organization_display_name="Gate Admin",
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
        yield db_session

    app.dependency_overrides[deps.get_db] = _get_db

    def _override(actor: deps.Actor):
        async def _get_current_user_override():
            return actor

        app.dependency_overrides[deps.get_current_user] = _get_current_user_override

    yield _override
    app.dependency_overrides.pop(deps.get_current_user, None)
    app.dependency_overrides.pop(deps.get_db, None)


async def test_uncompleted_foundation_blocks_operational_endpoints_with_409(
    db_session, override_auth_actor
):
    org, user, mem = await _create_org_and_admin(
        db_session,
        "Incomplete Org",
        "org_incomplete_gate",
        models.OrganizationFoundationStatus.IN_PROGRESS,
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
        # 1. Operational endpoints are BLOCKED with 409 FOUNDATION_REQUIRED
        for endpoint in [
            "/api/v1/classes/",
            "/api/v1/teachers/",
            "/api/v1/rooms/",
            "/api/v1/subjects/",
        ]:
            resp = await ac.get(endpoint)
            assert resp.status_code == 409, f"{endpoint} should be blocked with 409"
            body = resp.json()
            assert body["detail"]["code"] == "FOUNDATION_REQUIRED"

        # 2. Foundation and session endpoints remain available during onboarding
        status_resp = await ac.get("/api/v1/foundation/status")
        assert status_resp.status_code == 200
        assert status_resp.json()["foundation_status"] == "IN_PROGRESS"

        draft_resp = await ac.get("/api/v1/foundation/draft")
        assert draft_resp.status_code == 200

        me_resp = await ac.get("/api/v1/members/me")
        assert me_resp.status_code == 200
        assert me_resp.json()["foundation_status"] == "IN_PROGRESS"

        legal_resp = await ac.get("/api/v1/legal/status")
        assert legal_resp.status_code == 200
        assert legal_resp.json()["accepted"] is True


async def test_completed_foundation_allows_operational_endpoints(db_session, override_auth_actor):
    org, user, mem = await _create_org_and_admin(
        db_session,
        "Complete Org",
        "org_complete_gate",
        models.OrganizationFoundationStatus.COMPLETED,
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
        resp = await ac.get("/api/v1/classes/")
        assert resp.status_code == 200
