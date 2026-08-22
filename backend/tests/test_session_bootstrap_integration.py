import asyncio
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from app import models
from app.api import deps
from app.services import clerk_sync
from app.services.session_bootstrap_service import (
    ActiveOrganizationAccessDeniedError,
    SessionBootstrapService,
)
from tests.conftest import TestingSessionLocal

pytestmark = pytest.mark.postgresql


async def _provider_stubs(monkeypatch, organization):
    monkeypatch.setattr(
        SessionBootstrapService,
        "_verify_provider_membership",
        AsyncMock(return_value="orgmem_1"),
    )
    monkeypatch.setattr(
        clerk_sync,
        "fetch_clerk_organization_name",
        AsyncMock(return_value=organization.name),
    )
    monkeypatch.setattr(
        clerk_sync,
        "fetch_clerk_user_profile",
        AsyncMock(
            return_value=clerk_sync.ClerkUserProfile(
                email="founder@example.com",
                name="Founder",
            )
        ),
    )


async def test_bootstrap_creates_founder_graph_from_empty_baseline(
    db_session,
    monkeypatch,
):
    monkeypatch.setattr(
        SessionBootstrapService,
        "_verify_provider_membership",
        AsyncMock(return_value="orgmem_empty"),
    )
    monkeypatch.setattr(
        clerk_sync,
        "fetch_clerk_organization_name",
        AsyncMock(return_value="Empty Baseline School"),
    )
    monkeypatch.setattr(
        clerk_sync,
        "fetch_clerk_user_profile",
        AsyncMock(
            return_value=clerk_sync.ClerkUserProfile(
                email="founder@example.com",
                name="Founder",
            )
        ),
    )

    result = await SessionBootstrapService(db_session).bootstrap(
        {
            "sub": "user_empty",
            "o": {"id": "org_empty", "rol": "org:admin"},
        }
    )

    assert result.organization["clerk_org_id"] == "org_empty"
    assert result.member["capabilities"] == ["admin"]
    assert result.foundation_status == "NOT_STARTED"
    assert await db_session.scalar(select(func.count(models.User.id))) == 1
    assert await db_session.scalar(select(func.count(models.Organization.id))) == 1
    assert await db_session.scalar(select(func.count(models.OrganizationMembership.id))) == 1


async def test_bootstrap_is_idempotent_and_creates_one_founder_graph(
    db_session,
    monkeypatch,
):
    organization = models.Organization(
        name="Fresh School",
        clerk_org_id="org_fresh",
        plan_status=models.OrganizationPlanStatus.active,
    )
    db_session.add(organization)
    await db_session.flush()
    await _provider_stubs(monkeypatch, organization)
    service = SessionBootstrapService(db_session)
    payload = {"sub": "user_founder", "o": {"id": "org_fresh", "rol": "org:admin"}}

    first = await service.bootstrap(payload)
    second = await service.bootstrap(payload)

    assert first.organization == second.organization
    assert first.member == second.member
    assert first.member["capabilities"] == ["admin"]
    assert await db_session.scalar(select(func.count(models.User.id))) == 1
    assert await db_session.scalar(select(func.count(models.OrganizationMembership.id))) == 1
    assert (
        await db_session.scalar(
            select(func.count(models.OrganizationMembership.id)).where(
                models.OrganizationMembership.can_admin.is_(True)
            )
        )
        == 1
    )


async def test_bootstrap_never_grants_founder_access_to_established_tenant(
    db_session,
    monkeypatch,
):
    organization = models.Organization(name="Established", clerk_org_id="org_established")
    existing = models.User(
        email="existing@example.com",
        clerk_user_id="user_existing",
    )
    db_session.add_all([organization, existing])
    await db_session.flush()
    db_session.add(
        models.OrganizationMembership(
            organization_id=organization.id,
            account_id=existing.id,
            organization_display_name="Existing",
            lifecycle_status=models.MembershipLifecycleStatus.active,
            access_status=models.MembershipAccessStatus.active,
            can_admin=True,
            can_teach=False,
        )
    )
    await db_session.flush()
    await _provider_stubs(monkeypatch, organization)

    with pytest.raises(ActiveOrganizationAccessDeniedError):
        await SessionBootstrapService(db_session).bootstrap(
            {
                "sub": "user_founder",
                "o": {"id": "org_established", "rol": "org:admin"},
            }
        )

    assert await db_session.scalar(select(func.count(models.User.id))) == 1
    assert await db_session.scalar(select(func.count(models.OrganizationMembership.id))) == 1
    assert (
        await db_session.scalar(
            select(models.User).where(models.User.clerk_user_id == "user_founder")
        )
        is None
    )


async def test_bootstrap_reclaims_identity_after_clerk_user_was_deleted(
    db_session,
    monkeypatch,
):
    old_organization = models.Organization(
        name="Deleted School",
        clerk_org_id="org_deleted",
        plan_status=models.OrganizationPlanStatus.active,
    )
    old_account = models.User(
        email="founder@example.com",
        clerk_user_id="user_deleted",
        name="Old Founder",
    )
    db_session.add_all([old_organization, old_account])
    await db_session.flush()
    db_session.add(
        models.OrganizationMembership(
            organization_id=old_organization.id,
            account_id=old_account.id,
            organization_display_name=old_organization.name,
            lifecycle_status=models.MembershipLifecycleStatus.active,
            access_status=models.MembershipAccessStatus.active,
            can_admin=True,
            can_teach=False,
            clerk_membership_id="orgmem_deleted",
        )
    )
    await db_session.flush()
    await _provider_stubs(monkeypatch, old_organization)
    monkeypatch.setattr(clerk_sync, "clerk_user_exists", AsyncMock(return_value=False))

    result = await SessionBootstrapService(db_session).bootstrap(
        {
            "sub": "user_recreated",
            "o": {"id": "org_recreated", "rol": "org:admin"},
        }
    )

    assert result.organization["clerk_org_id"] == "org_recreated"
    recreated = await db_session.scalar(
        select(models.User).where(models.User.clerk_user_id == "user_recreated")
    )
    assert recreated is not None
    assert recreated.email == "founder@example.com"
    archived = await db_session.scalar(
        select(models.OrganizationMembership).where(
            models.OrganizationMembership.account_id == old_account.id
        )
    )
    assert archived is not None
    assert archived.access_status == models.MembershipAccessStatus.none
    assert archived.lifecycle_status == models.MembershipLifecycleStatus.archived
    assert await db_session.scalar(select(func.count(models.User.id))) == 2


async def test_bootstrap_does_not_reclaim_an_existing_clerk_identity(
    db_session,
    monkeypatch,
):
    old_account = models.User(
        email="founder@example.com",
        clerk_user_id="user_existing",
        name="Existing Founder",
    )
    db_session.add(old_account)
    await db_session.flush()
    await _provider_stubs(
        monkeypatch,
        models.Organization(name="New School", clerk_org_id="org_new"),
    )
    monkeypatch.setattr(clerk_sync, "clerk_user_exists", AsyncMock(return_value=True))

    with pytest.raises(ActiveOrganizationAccessDeniedError):
        await SessionBootstrapService(db_session).bootstrap(
            {
                "sub": "user_recreated",
                "o": {"id": "org_new", "rol": "org:admin"},
            }
        )

    assert (
        await db_session.scalar(
            select(models.User).where(models.User.clerk_user_id == "user_existing")
        )
        is not None
    )


async def test_concurrent_bootstrap_calls_create_exactly_one_founder_graph(
    db_session,
    monkeypatch,
):
    organization = models.Organization(
        name="Concurrent",
        clerk_org_id="org_concurrent",
        plan_status=models.OrganizationPlanStatus.active,
    )
    db_session.add(organization)
    await db_session.commit()
    monkeypatch.setattr(
        SessionBootstrapService,
        "_verify_provider_membership",
        AsyncMock(return_value="orgmem_concurrent"),
    )

    monkeypatch.setattr(
        clerk_sync,
        "fetch_clerk_organization_name",
        AsyncMock(return_value=organization.name),
    )
    monkeypatch.setattr(
        clerk_sync,
        "fetch_clerk_user_profile",
        AsyncMock(
            return_value=clerk_sync.ClerkUserProfile(
                email="concurrent@example.com",
                name="Concurrent Founder",
            )
        ),
    )
    payload = {
        "sub": "user_concurrent",
        "o": {"id": "org_concurrent", "rol": "org:admin"},
    }

    async def bootstrap_once():
        async with TestingSessionLocal() as session:
            async with session.begin():
                result = await SessionBootstrapService(session).bootstrap(payload)
                return result.organization["id"], result.member["id"]

    first, second = await asyncio.gather(bootstrap_once(), bootstrap_once())

    assert first == second
    assert await db_session.scalar(select(func.count(models.User.id))) == 1
    assert await db_session.scalar(select(func.count(models.OrganizationMembership.id))) == 1
    assert (
        await db_session.scalar(
            select(func.count(models.OrganizationMembership.id)).where(
                models.OrganizationMembership.can_admin.is_(True)
            )
        )
        == 1
    )


async def test_directory_failure_endpoint_rolls_back_partial_bootstrap(
    async_client,
    db_session,
    monkeypatch,
):
    async def payload():
        return {
            "sub": "user_outage",
            "o": {"id": "org_outage", "rol": "org:admin"},
        }

    from app.main import app

    app.dependency_overrides[deps.get_clerk_payload] = payload
    monkeypatch.setattr(
        SessionBootstrapService,
        "_verify_provider_membership",
        AsyncMock(return_value="orgmem_outage"),
    )
    monkeypatch.setattr(
        clerk_sync,
        "fetch_clerk_user_profile",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        clerk_sync,
        "fetch_clerk_organization_name",
        AsyncMock(return_value="Partial"),
    )

    try:
        response = await async_client.post("/api/v1/session/bootstrap")
    finally:
        app.dependency_overrides.pop(deps.get_clerk_payload, None)

    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "CLERK_DIRECTORY_UNAVAILABLE"
    assert await db_session.scalar(select(func.count(models.Organization.id))) == 0
