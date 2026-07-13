from datetime import datetime, timezone
from types import SimpleNamespace

import pytest


pytestmark = pytest.mark.asyncio


@pytest.mark.unit
async def test_clerk_access_service_normalizes_invitation_expiry_milliseconds(monkeypatch):
    from app.services.member_service import ClerkAccessService

    expires_at_ms = 1_786_526_551_827
    invitation = SimpleNamespace(
        id="orginv_contract",
        status="pending",
        expires_at=expires_at_ms,
    )
    sdk = SimpleNamespace(
        organization_invitations=SimpleNamespace(
            create=lambda **_kwargs: invitation,
        )
    )
    monkeypatch.setattr("app.services.clerk_access_service.get_clerk_sdk", lambda: sdk)

    result = await ClerkAccessService().create_organization_invitation(
        clerk_org_id="org_contract",
        email="teacher+clerk_test@example.com",
        role="org:member",
        inviter_user_id="user_admin",
        membership_id=42,
    )

    assert result.ok is True
    assert result.expires_at == datetime.fromtimestamp(expires_at_ms / 1000, tz=timezone.utc)
    assert result.expires_at.tzinfo is timezone.utc


@pytest.mark.unit
async def test_clerk_access_service_rejects_invitation_without_provider_id():
    from app.services.clerk_access_service import ClerkAccessService

    result = ClerkAccessService._invitation_result(
        SimpleNamespace(status="pending", expires_at=1_786_526_901_149)
    )

    assert result.ok is False
    assert result.error_category == "provider_contract_error"


async def test_create_scheduler_only_teacher_member(async_client, clerk_admin_headers):
    response = await async_client.post(
        "/api/v1/members",
        headers=clerk_admin_headers,
        json={
            "organization_display_name": "Ana Silva",
            "email": "ana.silva@example.com",
            "capabilities": ["teacher"],
            "teacher_access_mode": "scheduler_only",
            "subject_ids": [],
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["organization_display_name"] == "Ana Silva"
    assert body["capabilities"] == ["teacher"]
    assert body["access_status"] == "none"
    assert body["teacher_access_mode"] == "scheduler_only"
    assert body["teacher_id"] is not None
    assert body["clerk_user_id"] is None


async def test_members_list_has_top_level_total(async_client, clerk_admin_headers):
    response = await async_client.get("/api/v1/members", headers=clerk_admin_headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert "items" in body
    assert "total" in body
    assert all("total" not in item for item in body["items"])


@pytest.mark.parametrize("forbidden_field", ["password", "create_user_account"])
async def test_create_member_rejects_legacy_credential_fields(async_client, clerk_admin_headers, forbidden_field):
    payload = {
        "organization_display_name": "Bruno Costa",
        "email": "bruno.costa@example.com",
        "capabilities": ["teacher"],
        "teacher_access_mode": "scheduler_only",
        "subject_ids": [],
        forbidden_field: "legacy",
    }

    response = await async_client.post("/api/v1/members", headers=clerk_admin_headers, json=payload)

    assert response.status_code == 422


async def test_legacy_admin_teacher_write_routes_are_removed(async_client, clerk_admin_headers):
    create_response = await async_client.post(
        "/api/v1/teachers/",
        headers=clerk_admin_headers,
        json={"name": "Legacy Teacher", "email": "legacy@example.com"},
    )
    update_response = await async_client.patch(
        "/api/v1/teachers/123",
        headers=clerk_admin_headers,
        json={"name": "Legacy Teacher 2"},
    )
    delete_response = await async_client.delete("/api/v1/teachers/123", headers=clerk_admin_headers)

    assert create_response.status_code == 405
    assert update_response.status_code == 404
    assert delete_response.status_code == 404


async def test_platform_teacher_invite_and_resend(
    async_client,
    clerk_admin_headers,
    db_session,
    monkeypatch,
):
    from sqlalchemy import select

    from app import models
    from app.services.member_service import ClerkAccessResult

    invitation_ids = iter(["inv_initial", "inv_resend"])
    revoked = []

    expires_at_ms = 1_786_526_551_827

    async def fake_create_invitation(self, **kwargs):
        return ClerkAccessResult(
            invitation_id=next(invitation_ids),
            invitation_status="pending",
            expires_at=expires_at_ms,
        )

    async def fake_revoke_invitation(self, **kwargs):
        revoked.append(kwargs["invitation_id"])
        return ClerkAccessResult()

    monkeypatch.setattr("app.services.member_service.ClerkAccessService.create_organization_invitation", fake_create_invitation)
    monkeypatch.setattr("app.services.member_service.ClerkAccessService.revoke_organization_invitation", fake_revoke_invitation)

    create_response = await async_client.post(
        "/api/v1/members",
        headers=clerk_admin_headers,
        json={
            "organization_display_name": "Platform Teacher",
            "email": "platform.teacher@example.com",
            "capabilities": ["teacher"],
            "teacher_access_mode": "platform",
            "subject_ids": [],
        },
    )

    assert create_response.status_code == 201, create_response.text
    created = create_response.json()
    assert created["access_status"] == "pending_invite"
    assert created["clerk_invitation_id"] == "inv_initial"
    assert datetime.fromisoformat(created["invitation_expires_at"].replace("Z", "+00:00")) == datetime.fromtimestamp(
        expires_at_ms / 1000,
        tz=timezone.utc,
    )

    resend_response = await async_client.post(
        f"/api/v1/members/{created['id']}/resend-invitation",
        headers=clerk_admin_headers,
    )

    assert resend_response.status_code == 200, resend_response.text
    resent = resend_response.json()
    assert revoked == ["inv_initial"]
    assert resent["clerk_invitation_id"] == "inv_resend"
    assert resent["actions"]["can_resend_invite"] is True
    assert resent["provider_state"] == "confirmed"
    assert resent["remove_effect"] in {"archive", "hard_delete"}
    operations = list(
        (
            await db_session.scalars(
                select(models.MemberAccessOperation).where(
                    models.MemberAccessOperation.target_email
                    == "platform.teacher@example.com"
                )
            )
        ).all()
    )
    assert len(operations) == 3
    assert all(
        operation.operation_status
        == models.MemberAccessOperationStatus.local_committed
        for operation in operations
    )


async def test_scheduler_only_teacher_can_be_converted_to_platform_access(
    async_client,
    clerk_admin_headers,
    db_session,
    monkeypatch,
):
    from app.services.member_service import ClerkAccessResult

    expires_at_ms = 1_786_526_901_149

    async def fake_create_invitation(self, **_kwargs):
        return ClerkAccessResult(
            invitation_id="inv_conversion",
            invitation_status="pending",
            expires_at=expires_at_ms,
        )

    monkeypatch.setattr(
        "app.services.member_service.ClerkAccessService.create_organization_invitation",
        fake_create_invitation,
    )

    created_response = await async_client.post(
        "/api/v1/members",
        headers=clerk_admin_headers,
        json={
            "organization_display_name": "Scheduler Teacher",
            "email": "scheduler.convert@example.com",
            "capabilities": ["teacher"],
            "teacher_access_mode": "scheduler_only",
            "subject_ids": [],
        },
    )
    assert created_response.status_code == 201, created_response.text
    created = created_response.json()
    # The production request dependency commits after every successful request.
    # The shared test transaction deliberately does not, so expose this member to
    # the independent access-operation ledger before issuing the next request.
    await db_session.commit()

    converted_response = await async_client.patch(
        f"/api/v1/members/{created['id']}",
        headers=clerk_admin_headers,
        json={
            "capabilities": ["teacher"],
            "teacher_access_mode": "platform",
            "subject_ids": [],
            "lock_version": created["lock_version"],
        },
    )

    assert converted_response.status_code == 200, converted_response.text
    converted = converted_response.json()
    assert converted["teacher_access_mode"] == "platform"
    assert converted["access_status"] == "pending_invite"
    assert converted["clerk_invitation_id"] == "inv_conversion"
    assert datetime.fromisoformat(converted["invitation_expires_at"].replace("Z", "+00:00")) == datetime.fromtimestamp(
        expires_at_ms / 1000,
        tz=timezone.utc,
    )


async def test_retry_sync_relinks_active_member(async_client, clerk_admin_headers, db_session, monkeypatch):
    from sqlalchemy import select
    from app import models
    from app.services.member_service import ClerkAccessResult

    async def fake_change_role(self, **kwargs):
        return ClerkAccessResult(membership_id="mem_retry", role=kwargs["role"])

    monkeypatch.setattr("app.services.member_service.ClerkAccessService.change_membership_role", fake_change_role)

    user = models.User(email="retry.direct@example.com", name="Retry Direct", clerk_user_id="user_retry_direct")
    db_session.add(user)
    await db_session.flush()
    org = await db_session.scalar(select(models.Organization).where(models.Organization.clerk_org_id == "org_test_001"))
    member = models.OrganizationMembership(
        organization_id=org.id,
        account_id=user.id,
        organization_display_name="Retry Direct",
        lifecycle_status=models.MembershipLifecycleStatus.active,
        access_status=models.MembershipAccessStatus.sync_error,
        expected_clerk_role=models.ClerkOrganizationRole.admin,
    )
    db_session.add(member)
    await db_session.flush()
    db_session.add(models.OrganizationMembershipCapability(organization_membership_id=member.id, capability=models.MembershipCapability.admin))
    await db_session.commit()

    response = await async_client.post(f"/api/v1/members/{member.id}/retry-sync", headers=clerk_admin_headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["access_status"] == "active"
    assert body["clerk_membership_id"] == "mem_retry"


@pytest.mark.unit
async def test_legacy_teacher_admin_writes_are_absent_from_openapi():
    from app.main import app

    paths = app.openapi()["paths"]

    assert "post" not in paths["/api/v1/teachers/"]
    assert "/api/v1/teachers/{teacher_id}" not in paths


async def test_legacy_active_user_without_membership_is_denied(async_client, db_session, monkeypatch):
    from app import models
    from tests.conftest import mock_clerk_payload

    org = models.Organization(name="Legacy Auth Org", clerk_org_id="org_legacy_denied", plan_status="active")
    user = models.User(
        email="legacy.active@example.com",
        name="Legacy Active",
        clerk_user_id="user_legacy_active",
        organization_id=None,
        role=models.UserRole.admin,
        is_active=True,
    )
    db_session.add_all([org, user])
    await db_session.commit()

    async def _payload(_request):
        return mock_clerk_payload("user_legacy_active", "org_legacy_denied", "admin")

    monkeypatch.setattr("app.api.deps.get_clerk_payload", _payload)

    response = await async_client.get("/api/v1/members", headers={"Authorization": "Bearer test_user_legacy_active"})

    assert response.status_code == 403


async def test_mixed_member_can_use_teacher_self_service(async_client, db_session, monkeypatch):
    from app import models
    from tests.conftest import mock_clerk_payload

    org = models.Organization(name="Mixed Org", clerk_org_id="org_mixed_member", plan_status="active")
    db_session.add(org)
    await db_session.flush()
    teacher = models.Teacher(name="Mixed Teacher", organization_id=org.id)
    user = models.User(
        email="mixed@example.com",
        name="Mixed Member",
        clerk_user_id="user_mixed_member",
        organization_id=None,
        role=None,
        is_active=None,
    )
    db_session.add_all([teacher, user])
    await db_session.flush()
    member = models.OrganizationMembership(
        organization_id=org.id,
        account_id=user.id,
        organization_display_name="Mixed Member",
        lifecycle_status=models.MembershipLifecycleStatus.active,
        access_status=models.MembershipAccessStatus.active,
        teacher_access_mode=models.TeacherAccessMode.platform,
        expected_clerk_role=models.ClerkOrganizationRole.admin,
    )
    db_session.add(member)
    await db_session.flush()
    teacher.organization_membership_id = member.id
    db_session.add_all([
        models.OrganizationMembershipCapability(organization_membership_id=member.id, capability=models.MembershipCapability.admin),
        models.OrganizationMembershipCapability(organization_membership_id=member.id, capability=models.MembershipCapability.teacher),
    ])
    await db_session.commit()

    async def _payload(_request):
        return mock_clerk_payload("user_mixed_member", "org_mixed_member", "admin")

    monkeypatch.setattr("app.api.deps.get_clerk_payload", _payload)

    response = await async_client.get("/api/v1/teachers/me/availability", headers={"Authorization": "Bearer test_user_mixed_member"})

    assert response.status_code == 200, response.text


async def test_remove_scheduler_only_teacher_with_history_archives(async_client, clerk_admin_headers, db_session):
    from datetime import time
    from sqlalchemy import select
    from app import models

    create_response = await async_client.post(
        "/api/v1/members",
        headers=clerk_admin_headers,
        json={
            "organization_display_name": "History Teacher",
            "email": "history.teacher@example.com",
            "capabilities": ["teacher"],
            "teacher_access_mode": "scheduler_only",
            "subject_ids": [],
        },
    )
    assert create_response.status_code == 201, create_response.text
    created = create_response.json()
    teacher_id = created["teacher_id"]
    org = await db_session.scalar(select(models.Organization).where(models.Organization.clerk_org_id == "org_test_001"))
    db_session.add(
        models.Timeslot(
            organization_id=org.id,
            day_of_week=1,
            start_time=time(9, 0),
            end_time=time(10, 0),
        )
    )
    await db_session.flush()
    timeslot = await db_session.scalar(select(models.Timeslot).where(models.Timeslot.organization_id == org.id))
    db_session.add(models.Availability(organization_id=org.id, teacher_id=teacher_id, timeslot_id=timeslot.id))
    await db_session.commit()

    remove_response = await async_client.post(f"/api/v1/members/{created['id']}/remove", headers=clerk_admin_headers)

    assert remove_response.status_code == 200, remove_response.text
    assert remove_response.json()["remove_effect"] == "archive"
    member = await db_session.get(models.OrganizationMembership, created["id"])
    assert member is not None
    assert member.lifecycle_status == models.MembershipLifecycleStatus.archived


async def test_update_validates_subjects_before_clerk_role_change(async_client, clerk_admin_headers, db_session, monkeypatch):
    from sqlalchemy import select
    from app import models
    from app.services.member_service import ClerkAccessResult

    called = False

    async def fake_change_role(self, **kwargs):
        nonlocal called
        called = True
        return ClerkAccessResult(membership_id="mem_changed", role=kwargs["role"])

    monkeypatch.setattr("app.services.member_service.ClerkAccessService.change_membership_role", fake_change_role)
    org = await db_session.scalar(select(models.Organization).where(models.Organization.clerk_org_id == "org_test_001"))
    account = models.User(email="validate-before-clerk@example.com", name="Validate First", clerk_user_id="user_validate_first")
    db_session.add(account)
    await db_session.flush()
    member = models.OrganizationMembership(
        organization_id=org.id,
        account_id=account.id,
        organization_display_name="Validate First",
        lifecycle_status=models.MembershipLifecycleStatus.active,
        access_status=models.MembershipAccessStatus.active,
        teacher_access_mode=models.TeacherAccessMode.platform,
        expected_clerk_role=models.ClerkOrganizationRole.member,
        clerk_membership_id="mem_existing",
    )
    db_session.add(member)
    await db_session.flush()
    teacher = models.Teacher(name="Validate First", organization_id=org.id, organization_membership_id=member.id)
    db_session.add(teacher)
    db_session.add(models.OrganizationMembershipCapability(organization_membership_id=member.id, capability=models.MembershipCapability.teacher))
    await db_session.commit()

    response = await async_client.patch(
        f"/api/v1/members/{member.id}",
        headers=clerk_admin_headers,
        json={
            "capabilities": ["teacher", "admin"],
            "teacher_access_mode": "platform",
            "subject_ids": [999999],
            "lock_version": member.lock_version,
        },
    )

    assert response.status_code == 422
    assert called is False
