from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from app import models
from app.api import deps
from app.main import app
from app.services import clerk_sync
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
    # The bootstrapping admin is the founder: created_by_membership_id points at itself.
    mem.created_by_membership_id = mem.id
    await db_session.flush()
    await accept_current_legal_documents(
        db_session,
        organization_id=org.id,
        membership_id=mem.id,
    )
    return org, user, mem


@pytest.fixture
def override_auth_actor(db_session, monkeypatch):
    provider_creator = [None]

    async def fetch_organization_profile(_clerk_org_id, _gateway=None):
        return clerk_sync.ClerkOrganizationProfile(
            name="Foundation gate test organization",
            created_by=provider_creator[0],
        )

    monkeypatch.setattr(
        clerk_sync,
        "fetch_clerk_organization_profile",
        fetch_organization_profile,
    )
    app.dependency_overrides[deps.get_clerk_gateway] = lambda: None

    async def _get_db():
        yield db_session

    app.dependency_overrides[deps.get_db] = _get_db

    def _override(actor: deps.Actor):
        provider_creator[0] = actor.clerk_user_id

        async def _get_current_user_override():
            return actor

        app.dependency_overrides[deps.get_current_user] = _get_current_user_override

    yield _override
    app.dependency_overrides.pop(deps.get_current_user, None)
    app.dependency_overrides.pop(deps.get_clerk_gateway, None)
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


async def _add_second_admin(
    db_session, org, founder_membership, *, clerk_suffix: str
) -> tuple[models.User, models.OrganizationMembership]:
    user = models.User(
        name="Second Admin",
        email=f"second_admin_{clerk_suffix}@test.com",
        clerk_user_id=f"user_second_admin_{clerk_suffix}",
    )
    db_session.add(user)
    await db_session.flush()
    membership = models.OrganizationMembership(
        organization_id=org.id,
        account_id=user.id,
        organization_display_name="Second Admin",
        lifecycle_status=models.MembershipLifecycleStatus.active,
        access_status=models.MembershipAccessStatus.active,
        clerk_membership_id=f"mem_second_admin_{clerk_suffix}",
        can_admin=True,
        can_teach=False,
        created_by_membership_id=founder_membership.id,
    )
    db_session.add(membership)
    await db_session.flush()
    return user, membership


async def test_completed_org_second_admin_gets_completed_member_and_config(
    db_session, override_auth_actor
):
    org, _founder, founder_membership = await _create_org_and_admin(
        db_session,
        "Completed Switch Org",
        "org_completed_switch",
        models.OrganizationFoundationStatus.COMPLETED,
    )
    second_user, second_membership = await _add_second_admin(
        db_session, org, founder_membership, clerk_suffix="switch"
    )
    actor = deps.Actor(
        account_id=second_user.id,
        clerk_user_id=second_user.clerk_user_id,
        organization_id=org.id,
        membership_id=second_membership.id,
        can_admin=True,
        can_teach=False,
        teacher_id=None,
    )
    override_auth_actor(actor)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        me_resp = await ac.get("/api/v1/members/me")
        assert me_resp.status_code == 200
        body = me_resp.json()
        assert body["foundation_status"] == "COMPLETED"
        assert body["can_manage_foundation"] is False

        # The school configuration API is the later-admin destination and stays
        # available once the foundation is complete.
        config_resp = await ac.post(
            "/api/v1/school/settings/",
            json={
                "school_start_date": "2025-09-15",
                "school_hard_end_date": "2026-07-31",
                "repair_stability_window_days": 14,
            },
        )
        assert config_resp.status_code == 200


async def test_completed_foundation_cannot_be_reset_by_foundation_mutations(
    db_session, override_auth_actor
):
    org, user, mem = await _create_org_and_admin(
        db_session,
        "Monotonic Org",
        "org_monotonic_gate",
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

    completed_at = org.foundation_completed_at

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Completing twice is idempotent and never reopens the wizard.
        complete_resp = await ac.post(
            "/api/v1/foundation/complete",
            json={"expected_version": 1, "confirmed": True},
        )
        assert complete_resp.status_code == 200
        assert complete_resp.json()["foundation_status"] == "COMPLETED"

        # The draft endpoint refuses to reopen a completed foundation.
        draft_resp = await ac.put(
            "/api/v1/foundation/draft",
            json={"expected_version": 1, "current_step": 1, "data": {}},
        )
        assert draft_resp.status_code == 409
        assert draft_resp.json()["detail"]["code"] == "FOUNDATION_ALREADY_COMPLETED"

        status_resp = await ac.get("/api/v1/foundation/status")
        assert status_resp.status_code == 200
        assert status_resp.json()["foundation_status"] == "COMPLETED"

    await db_session.refresh(org)
    assert org.foundation_status == models.OrganizationFoundationStatus.COMPLETED
    assert org.foundation_completed_at == completed_at
