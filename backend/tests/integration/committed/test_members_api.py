import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest


async def test_clerk_access_service_normalizes_invitation_expiry_milliseconds(monkeypatch):
    from app.services.member_service import ClerkAccessService

    expires_at_ms = 1_786_526_551_827
    create_kwargs = {}
    invitation = SimpleNamespace(
        id="orginv_contract",
        status="pending",
        expires_at=expires_at_ms,
    )

    def create_invitation(**kwargs):
        create_kwargs.update(kwargs)
        return invitation

    sdk = SimpleNamespace(
        organization_invitations=SimpleNamespace(
            create=create_invitation,
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
    assert result.expires_at == datetime.fromtimestamp(expires_at_ms / 1000, tz=UTC)
    assert result.expires_at.tzinfo is UTC
    assert create_kwargs["redirect_url"] == "http://localhost:5173/login"
    assert create_kwargs["notify"] is True


async def test_clerk_access_service_rejects_invitation_without_provider_id():
    from app.services.clerk_access_service import ClerkAccessService

    result = ClerkAccessService._invitation_result(
        SimpleNamespace(status="pending", expires_at=1_786_526_901_149)
    )

    assert result.ok is False
    assert result.error_category == "provider_contract_error"


async def test_clerk_access_service_preserves_safe_provider_diagnostics():
    from app.services.clerk_access_service import ClerkAccessService

    class ProviderError(RuntimeError):
        status_code = 409
        headers = {"x-request-id": "req_contract"}
        data = SimpleNamespace(errors=[SimpleNamespace(code="organization_membership_exists")])

    def fail():
        raise ProviderError("sensitive provider response")

    result = await ClerkAccessService()._call(fail)

    assert result.ok is False
    assert result.safe_message == (
        "Access could not be synchronized with Clerk. Try again or contact support."
    )
    assert result.provider_status_code == 409
    assert result.provider_error_code == "organization_membership_exists"
    assert result.provider_request_id == "req_contract"


async def test_clerk_access_service_bounds_provider_wait_time():
    from app.services.clerk_access_service import ClerkAccessService

    async def never_returns():
        await asyncio.sleep(60)

    access = ClerkAccessService(
        gateway=SimpleNamespace(sdk=None),
        timeout_seconds=0.01,
    )

    result = await access._call(never_returns)

    assert result.ok is False
    assert result.retryable is True
    assert result.error_category == "provider_timeout"
    assert result.safe_message == (
        "Access could not be synchronized with Clerk. Try again or contact support."
    )


async def test_clerk_access_service_finds_exact_user_and_membership(monkeypatch):
    from app.services.clerk_access_service import ClerkAccessService

    user = SimpleNamespace(
        id="user_existing",
        email_addresses=[SimpleNamespace(email_address="existing@example.com")],
    )
    membership = SimpleNamespace(
        id="orgmem_existing",
        role="org:member",
    )
    sdk = SimpleNamespace(
        users=SimpleNamespace(list=lambda **_kwargs: [user]),
        organization_memberships=SimpleNamespace(
            list=lambda **_kwargs: SimpleNamespace(data=[membership])
        ),
    )
    monkeypatch.setattr("app.services.clerk_access_service.get_clerk_sdk", lambda: sdk)
    access = ClerkAccessService()

    found_user = await access.find_user_by_email(email="EXISTING@example.com")
    found_membership = await access.get_membership(
        clerk_org_id="org_existing",
        clerk_user_id=found_user.user_id,
    )

    assert found_user.user_id == "user_existing"
    assert found_membership.membership_id == "orgmem_existing"
    assert found_membership.role == "org:member"


async def test_clerk_access_service_creates_membership_for_existing_user(monkeypatch):
    from app.services.member_service import ClerkAccessService

    create_kwargs = {}

    def create_membership(**kwargs):
        create_kwargs.update(kwargs)
        return SimpleNamespace(id="orgmem_created", role="org:member")

    sdk = SimpleNamespace(
        organization_memberships=SimpleNamespace(create=create_membership),
    )
    monkeypatch.setattr("app.services.clerk_access_service.get_clerk_sdk", lambda: sdk)

    result = await ClerkAccessService().create_organization_membership(
        clerk_org_id="org_existing",
        clerk_user_id="user_existing",
        role="org:member",
    )

    assert result.ok is True
    assert result.membership_id == "orgmem_created"
    assert result.user_id == "user_existing"
    assert create_kwargs == {
        "organization_id": "org_existing",
        "user_id": "user_existing",
        "role": "org:member",
    }


async def test_clerk_access_service_revokes_membership_by_user_id(monkeypatch):
    from app.services.member_service import ClerkAccessService

    delete_kwargs = {}

    def delete_membership(*, organization_id, user_id):
        delete_kwargs.update(organization_id=organization_id, user_id=user_id)
        return SimpleNamespace(id="orgmem_revoked", role="org:member")

    sdk = SimpleNamespace(
        organization_memberships=SimpleNamespace(delete=delete_membership),
    )
    monkeypatch.setattr("app.services.clerk_access_service.get_clerk_sdk", lambda: sdk)

    result = await ClerkAccessService().revoke_organization_membership(
        clerk_org_id="org_existing",
        clerk_user_id="user_existing",
    )

    assert result.ok is True
    assert delete_kwargs == {
        "organization_id": "org_existing",
        "user_id": "user_existing",
    }


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
async def test_create_member_rejects_legacy_credential_fields(
    async_client, clerk_admin_headers, forbidden_field
):
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

    async def fake_find_user(self, **_kwargs):
        return ClerkAccessResult()

    async def fake_find_pending_invitation(self, **_kwargs):
        return ClerkAccessResult()

    async def fake_revoke_invitation(self, **kwargs):
        revoked.append(kwargs["invitation_id"])
        return ClerkAccessResult()

    monkeypatch.setattr(
        "app.services.member_service.ClerkAccessService.create_organization_invitation",
        fake_create_invitation,
    )
    monkeypatch.setattr(
        "app.services.member_service.ClerkAccessService.revoke_organization_invitation",
        fake_revoke_invitation,
    )
    monkeypatch.setattr(
        "app.services.member_service.ClerkAccessService.find_user_by_email", fake_find_user
    )
    monkeypatch.setattr(
        "app.services.member_service.ClerkAccessService.find_pending_invitation",
        fake_find_pending_invitation,
    )

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
    assert datetime.fromisoformat(
        created["invitation_expires_at"].replace("Z", "+00:00")
    ) == datetime.fromtimestamp(
        expires_at_ms / 1000,
        tz=UTC,
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

    cooldown_response = await async_client.post(
        f"/api/v1/members/{created['id']}/resend-invitation",
        headers=clerk_admin_headers,
    )
    assert cooldown_response.status_code == 409
    assert cooldown_response.json()["detail"]["code"] == "resend_cooldown"
    operations = list(
        (
            await db_session.scalars(
                select(models.MemberAccessOperation).where(
                    models.MemberAccessOperation.target_email == "platform.teacher@example.com"
                )
            )
        ).all()
    )
    assert len(operations) == 3
    assert all(
        operation.operation_status == models.MemberAccessOperationStatus.local_committed
        for operation in operations
    )


async def test_platform_resend_is_atomic_under_concurrency(
    async_client,
    clerk_admin_headers,
    db_session,
    monkeypatch,
):
    from sqlalchemy import select

    from app import models
    from app.services.member_service import ClerkAccessResult

    create_calls = []
    provider_started = asyncio.Event()
    release_provider = asyncio.Event()
    expires_at_ms = 1_786_526_551_827

    async def fake_create_invitation(self, **kwargs):
        create_calls.append(kwargs)
        if len(create_calls) == 2:
            provider_started.set()
            await release_provider.wait()
        return ClerkAccessResult(
            invitation_id="inv_initial" if len(create_calls) == 1 else "inv_resend",
            invitation_status="pending",
            expires_at=expires_at_ms,
        )

    async def fake_find_user(self, **_kwargs):
        return ClerkAccessResult()

    async def fake_find_pending_invitation(self, **_kwargs):
        return ClerkAccessResult()

    monkeypatch.setattr(
        "app.services.member_service.ClerkAccessService.create_organization_invitation",
        fake_create_invitation,
    )
    monkeypatch.setattr(
        "app.services.member_service.ClerkAccessService.find_user_by_email", fake_find_user
    )
    monkeypatch.setattr(
        "app.services.member_service.ClerkAccessService.find_pending_invitation",
        fake_find_pending_invitation,
    )

    create_response = await async_client.post(
        "/api/v1/members",
        headers=clerk_admin_headers,
        json={
            "organization_display_name": "Concurrent Teacher",
            "email": "concurrent.teacher@example.com",
            "capabilities": ["teacher"],
            "teacher_access_mode": "platform",
            "subject_ids": [],
        },
    )
    assert create_response.status_code == 201, create_response.text
    created = create_response.json()

    await db_session.rollback()
    member = await db_session.get(models.OrganizationMembership, created["id"])
    assert member is not None
    member.access_status = models.MembershipAccessStatus.invite_expired
    member.clerk_invitation_id = None
    member.clerk_invitation_status = models.ClerkInvitationStatus.expired
    member.invitation_expires_at = None
    await db_session.commit()

    endpoint = f"/api/v1/members/{created['id']}/resend-invitation"
    concurrent_headers = {
        **clerk_admin_headers,
        "Authorization": "Bearer test_user_admin_001|org_test_001",
    }
    requests = [
        asyncio.create_task(async_client.post(endpoint, headers=concurrent_headers)),
        asyncio.create_task(async_client.post(endpoint, headers=concurrent_headers)),
    ]
    await asyncio.wait_for(provider_started.wait(), timeout=5)
    release_provider.set()
    responses = await asyncio.gather(*requests)

    assert sorted(response.status_code for response in responses) == [200, 409]
    assert len(create_calls) == 2  # initial invitation plus exactly one resend

    await db_session.rollback()
    operations = list(
        (
            await db_session.scalars(
                select(models.MemberAccessOperation).where(
                    models.MemberAccessOperation.organization_id == member.organization_id,
                    models.MemberAccessOperation.membership_id == member.id,
                    models.MemberAccessOperation.operation_type
                    == models.MemberAccessOperationType.resend_invitation,
                )
            )
        ).all()
    )
    assert len(operations) == 1
    assert operations[0].operation_status == models.MemberAccessOperationStatus.local_committed


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

    async def fake_find_user(self, **_kwargs):
        return ClerkAccessResult()

    async def fake_find_pending_invitation(self, **_kwargs):
        return ClerkAccessResult()

    monkeypatch.setattr(
        "app.services.member_service.ClerkAccessService.create_organization_invitation",
        fake_create_invitation,
    )
    monkeypatch.setattr(
        "app.services.member_service.ClerkAccessService.find_user_by_email",
        fake_find_user,
    )
    monkeypatch.setattr(
        "app.services.member_service.ClerkAccessService.find_pending_invitation",
        fake_find_pending_invitation,
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
    assert datetime.fromisoformat(
        converted["invitation_expires_at"].replace("Z", "+00:00")
    ) == datetime.fromtimestamp(
        expires_at_ms / 1000,
        tz=UTC,
    )


async def test_create_platform_teacher_reconciles_existing_clerk_membership(
    async_client,
    clerk_admin_headers,
    monkeypatch,
):
    from app.services.member_service import ClerkAccessResult

    invitation_attempted = False

    async def fake_find_user(self, **_kwargs):
        return ClerkAccessResult(user_id="user_existing")

    async def fake_get_membership(self, **_kwargs):
        return ClerkAccessResult(
            user_id="user_existing",
            membership_id="orgmem_existing",
            role="org:member",
        )

    async def fake_find_pending_invitation(self, **_kwargs):
        return ClerkAccessResult()

    async def fake_create_invitation(self, **_kwargs):
        nonlocal invitation_attempted
        invitation_attempted = True
        return ClerkAccessResult(error_category="unexpected_invitation")

    monkeypatch.setattr(
        "app.services.member_service.ClerkAccessService.find_user_by_email",
        fake_find_user,
    )
    monkeypatch.setattr(
        "app.services.member_service.ClerkAccessService.get_membership",
        fake_get_membership,
    )
    monkeypatch.setattr(
        "app.services.member_service.ClerkAccessService.find_pending_invitation",
        fake_find_pending_invitation,
    )
    monkeypatch.setattr(
        "app.services.member_service.ClerkAccessService.create_organization_invitation",
        fake_create_invitation,
    )

    response = await async_client.post(
        "/api/v1/members",
        headers=clerk_admin_headers,
        json={
            "organization_display_name": "Existing Clerk Teacher",
            "email": "existing.clerk@example.com",
            "capabilities": ["teacher"],
            "teacher_access_mode": "platform",
            "subject_ids": [],
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert invitation_attempted is False
    assert body["access_status"] == "active"
    assert body["clerk_membership_id"] == "orgmem_existing"
    assert body["clerk_invitation_id"] is None


async def test_create_platform_teacher_adopts_existing_pending_invitation(
    async_client,
    clerk_admin_headers,
    monkeypatch,
):
    from app.services.member_service import ClerkAccessResult

    expires_at_ms = 1_786_526_901_149
    invitation_attempted = False

    async def fake_find_user(self, **_kwargs):
        return ClerkAccessResult()

    async def fake_find_pending_invitation(self, **_kwargs):
        return ClerkAccessResult(
            invitation_id="orginv_existing",
            invitation_status="pending",
            expires_at=expires_at_ms,
        )

    async def fake_create_invitation(self, **_kwargs):
        nonlocal invitation_attempted
        invitation_attempted = True
        return ClerkAccessResult(error_category="unexpected_invitation")

    monkeypatch.setattr(
        "app.services.member_service.ClerkAccessService.find_user_by_email",
        fake_find_user,
    )
    monkeypatch.setattr(
        "app.services.member_service.ClerkAccessService.find_pending_invitation",
        fake_find_pending_invitation,
    )
    monkeypatch.setattr(
        "app.services.member_service.ClerkAccessService.create_organization_invitation",
        fake_create_invitation,
    )

    response = await async_client.post(
        "/api/v1/members",
        headers=clerk_admin_headers,
        json={
            "organization_display_name": "Already Invited Teacher",
            "email": "already.invited@example.com",
            "capabilities": ["teacher"],
            "teacher_access_mode": "platform",
            "subject_ids": [],
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert invitation_attempted is False
    assert body["access_status"] == "pending_invite"
    assert body["clerk_invitation_id"] == "orginv_existing"


async def test_create_platform_teacher_directly_adds_existing_clerk_user(
    async_client,
    clerk_admin_headers,
    monkeypatch,
):
    from app.services.member_service import ClerkAccessResult

    invitation_attempted = False
    membership_created = False

    async def fake_find_user(self, **_kwargs):
        return ClerkAccessResult(user_id="user_existing_without_membership")

    async def fake_get_membership(self, **_kwargs):
        return ClerkAccessResult(user_id="user_existing_without_membership")

    async def fake_create_membership(self, **_kwargs):
        nonlocal membership_created
        membership_created = True
        return ClerkAccessResult(
            user_id="user_existing_without_membership",
            membership_id="orgmem_created_directly",
            role="org:member",
        )

    async def fake_create_invitation(self, **_kwargs):
        nonlocal invitation_attempted
        invitation_attempted = True
        return ClerkAccessResult(error_category="unexpected_invitation")

    monkeypatch.setattr(
        "app.services.member_service.ClerkAccessService.find_user_by_email",
        fake_find_user,
    )
    monkeypatch.setattr(
        "app.services.member_service.ClerkAccessService.get_membership",
        fake_get_membership,
    )
    monkeypatch.setattr(
        "app.services.member_service.ClerkAccessService.create_organization_membership",
        fake_create_membership,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.member_service.ClerkAccessService.create_organization_invitation",
        fake_create_invitation,
    )

    response = await async_client.post(
        "/api/v1/members",
        headers=clerk_admin_headers,
        json={
            "organization_display_name": "Existing Direct Teacher",
            "email": "existing.direct@example.com",
            "capabilities": ["teacher"],
            "teacher_access_mode": "platform",
            "subject_ids": [],
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert membership_created is True
    assert invitation_attempted is False
    assert body["access_status"] == "active"
    assert body["clerk_membership_id"] == "orgmem_created_directly"
    assert body["clerk_invitation_id"] is None


async def test_scheduler_only_conversion_reconciles_existing_clerk_membership(
    async_client,
    clerk_admin_headers,
    db_session,
    monkeypatch,
):
    from app.services.member_service import ClerkAccessResult

    invitation_attempted = False

    async def fake_find_user(self, **_kwargs):
        return ClerkAccessResult(user_id="user_scheduler_existing")

    async def fake_get_membership(self, **_kwargs):
        return ClerkAccessResult(
            user_id="user_scheduler_existing",
            membership_id="orgmem_scheduler_existing",
            role="org:member",
        )

    async def fake_find_pending_invitation(self, **_kwargs):
        return ClerkAccessResult()

    async def fake_create_invitation(self, **_kwargs):
        nonlocal invitation_attempted
        invitation_attempted = True
        return ClerkAccessResult(error_category="unexpected_invitation")

    monkeypatch.setattr(
        "app.services.member_service.ClerkAccessService.find_user_by_email",
        fake_find_user,
    )
    monkeypatch.setattr(
        "app.services.member_service.ClerkAccessService.get_membership",
        fake_get_membership,
    )
    monkeypatch.setattr(
        "app.services.member_service.ClerkAccessService.find_pending_invitation",
        fake_find_pending_invitation,
    )
    monkeypatch.setattr(
        "app.services.member_service.ClerkAccessService.create_organization_invitation",
        fake_create_invitation,
    )

    created_response = await async_client.post(
        "/api/v1/members",
        headers=clerk_admin_headers,
        json={
            "organization_display_name": "Existing Scheduler Teacher",
            "email": "existing.scheduler@example.com",
            "capabilities": ["teacher"],
            "teacher_access_mode": "scheduler_only",
            "subject_ids": [],
        },
    )
    assert created_response.status_code == 201, created_response.text
    created = created_response.json()
    await db_session.commit()

    response = await async_client.patch(
        f"/api/v1/members/{created['id']}",
        headers=clerk_admin_headers,
        json={
            "capabilities": ["teacher"],
            "teacher_access_mode": "platform",
            "subject_ids": [],
            "lock_version": created["lock_version"],
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert invitation_attempted is False
    assert body["access_status"] == "active"
    assert body["clerk_membership_id"] == "orgmem_scheduler_existing"


async def test_scheduler_only_conversion_adds_existing_clerk_user_to_organization(
    async_client,
    clerk_admin_headers,
    db_session,
    monkeypatch,
):
    from app.services.member_service import ClerkAccessResult

    invitation_attempted = False
    membership_created = False

    async def fake_find_user(self, **_kwargs):
        return ClerkAccessResult(user_id="user_scheduler_without_membership")

    async def fake_get_membership(self, **_kwargs):
        return ClerkAccessResult(user_id="user_scheduler_without_membership")

    async def fake_create_membership(self, **_kwargs):
        nonlocal membership_created
        membership_created = True
        return ClerkAccessResult(
            user_id="user_scheduler_without_membership",
            membership_id="orgmem_scheduler_created",
            role="org:member",
        )

    async def fake_create_invitation(self, **_kwargs):
        nonlocal invitation_attempted
        invitation_attempted = True
        return ClerkAccessResult(error_category="unexpected_invitation")

    monkeypatch.setattr(
        "app.services.member_service.ClerkAccessService.find_user_by_email",
        fake_find_user,
    )
    monkeypatch.setattr(
        "app.services.member_service.ClerkAccessService.get_membership",
        fake_get_membership,
    )
    monkeypatch.setattr(
        "app.services.member_service.ClerkAccessService.create_organization_membership",
        fake_create_membership,
    )
    monkeypatch.setattr(
        "app.services.member_service.ClerkAccessService.create_organization_invitation",
        fake_create_invitation,
    )

    created_response = await async_client.post(
        "/api/v1/members",
        headers=clerk_admin_headers,
        json={
            "organization_display_name": "Direct Scheduler Teacher",
            "email": "direct.scheduler@example.com",
            "capabilities": ["teacher"],
            "teacher_access_mode": "scheduler_only",
            "subject_ids": [],
        },
    )
    assert created_response.status_code == 201, created_response.text
    created = created_response.json()
    await db_session.commit()

    response = await async_client.patch(
        f"/api/v1/members/{created['id']}",
        headers=clerk_admin_headers,
        json={
            "capabilities": ["teacher"],
            "teacher_access_mode": "platform",
            "subject_ids": [],
            "lock_version": created["lock_version"],
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert membership_created is True
    assert invitation_attempted is False
    assert body["access_status"] == "active"
    assert body["clerk_membership_id"] == "orgmem_scheduler_created"
    assert body["clerk_invitation_id"] is None


async def test_retry_sync_relinks_active_member(
    async_client, clerk_admin_headers, db_session, monkeypatch
):
    from sqlalchemy import select

    from app import models
    from app.services.member_service import ClerkAccessResult

    async def fake_change_role(self, **kwargs):
        return ClerkAccessResult(membership_id="mem_retry", role=kwargs["role"])

    monkeypatch.setattr(
        "app.services.member_service.ClerkAccessService.change_membership_role", fake_change_role
    )

    user = models.User(
        email="retry.direct@example.com", name="Retry Direct", clerk_user_id="user_retry_direct"
    )
    db_session.add(user)
    await db_session.flush()
    org = await db_session.scalar(
        select(models.Organization).where(models.Organization.clerk_org_id == "org_test_001")
    )
    member = models.OrganizationMembership(
        organization_id=org.id,
        account_id=user.id,
        organization_display_name="Retry Direct",
        lifecycle_status=models.MembershipLifecycleStatus.active,
        access_status=models.MembershipAccessStatus.sync_error,
        can_admin=True,
        can_teach=False,
        expected_clerk_role=models.ClerkOrganizationRole.admin,
    )
    db_session.add(member)
    await db_session.flush()
    await db_session.commit()

    response = await async_client.post(
        f"/api/v1/members/{member.id}/retry-sync", headers=clerk_admin_headers
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["access_status"] == "active"
    assert body["clerk_membership_id"] == "mem_retry"


async def test_legacy_teacher_admin_writes_are_absent_from_openapi():
    from app.main import app

    paths = app.openapi()["paths"]

    assert "post" not in paths["/api/v1/teachers/"]
    assert "/api/v1/teachers/{teacher_id}" not in paths


async def test_legacy_active_user_without_membership_is_denied(async_client, db_session):
    from app import models

    org = models.Organization(
        name="Legacy Auth Org", clerk_org_id="org_legacy_denied", plan_status="active"
    )
    user = models.User(
        email="legacy.active@example.com",
        name="Legacy Active",
        clerk_user_id="user_legacy_active",
    )
    db_session.add_all([org, user])
    await db_session.commit()
    response = await async_client.get(
        "/api/v1/members",
        headers={"Authorization": "Bearer test_user_legacy_active|org_legacy_denied"},
    )

    assert response.status_code == 403


async def test_mixed_member_can_use_teacher_self_service(async_client, db_session):
    from datetime import UTC, datetime

    from app import models

    org = models.Organization(
        name="Mixed Org",
        clerk_org_id="org_mixed_member",
        plan_status="active",
        foundation_status=models.OrganizationFoundationStatus.COMPLETED,
        foundation_completed_at=datetime.now(UTC),
    )
    db_session.add(org)
    await db_session.flush()
    user = models.User(
        email="mixed@example.com",
        name="Mixed Member",
        clerk_user_id="user_mixed_member",
    )
    db_session.add(user)
    await db_session.flush()
    member = models.OrganizationMembership(
        organization_id=org.id,
        account_id=user.id,
        organization_display_name="Mixed Member",
        lifecycle_status=models.MembershipLifecycleStatus.active,
        access_status=models.MembershipAccessStatus.active,
        teacher_access_mode=models.TeacherAccessMode.platform,
        can_admin=True,
        can_teach=True,
    )
    db_session.add(member)
    await db_session.flush()
    teacher = models.Teacher(
        organization_id=org.id,
        organization_membership_id=member.id,
    )
    db_session.add(teacher)
    await db_session.commit()

    response = await async_client.get(
        "/api/v1/teachers/me/availability",
        headers={"Authorization": "Bearer test_user_mixed_member"},
    )

    assert response.status_code == 200, response.text


async def test_remove_scheduler_only_teacher_with_history_archives(
    async_client, clerk_admin_headers, db_session
):
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
    org = await db_session.scalar(
        select(models.Organization).where(models.Organization.clerk_org_id == "org_test_001")
    )
    db_session.add(
        models.Timeslot(
            organization_id=org.id,
            day_of_week=1,
            start_time=time(9, 0),
            end_time=time(10, 0),
        )
    )
    await db_session.flush()
    timeslot = await db_session.scalar(
        select(models.Timeslot).where(models.Timeslot.organization_id == org.id)
    )
    db_session.add(
        models.Availability(organization_id=org.id, teacher_id=teacher_id, timeslot_id=timeslot.id)
    )
    await db_session.commit()

    remove_response = await async_client.post(
        f"/api/v1/members/{created['id']}/remove", headers=clerk_admin_headers
    )

    assert remove_response.status_code == 200, remove_response.text
    assert remove_response.json()["remove_effect"] == "archive"
    member = await db_session.get(models.OrganizationMembership, created["id"])
    assert member is not None
    assert member.lifecycle_status == models.MembershipLifecycleStatus.archived


async def test_active_platform_teacher_can_be_archived_and_restored(
    async_client,
    clerk_admin_headers,
    db_session,
    monkeypatch,
):
    from datetime import time

    from sqlalchemy import select

    from app import models
    from app.services.member_service import ClerkAccessResult

    revoked = []
    restored_memberships = []

    async def fake_revoke_membership(self, *, clerk_org_id, clerk_user_id):
        revoked.append((clerk_org_id, clerk_user_id))
        return ClerkAccessResult()

    async def fake_find_user(self, **_kwargs):
        return ClerkAccessResult(user_id="user_archive_active")

    async def fake_get_membership(self, **_kwargs):
        return ClerkAccessResult(user_id="user_archive_active")

    async def fake_create_membership(self, *, clerk_org_id, clerk_user_id, role):
        restored_memberships.append((clerk_org_id, clerk_user_id, role))
        return ClerkAccessResult(
            user_id=clerk_user_id,
            membership_id="orgmem_archive_restored",
            role=role,
        )

    monkeypatch.setattr(
        "app.services.member_service.ClerkAccessService.revoke_organization_membership",
        fake_revoke_membership,
    )
    monkeypatch.setattr(
        "app.services.member_service.ClerkAccessService.find_user_by_email",
        fake_find_user,
    )
    monkeypatch.setattr(
        "app.services.member_service.ClerkAccessService.get_membership",
        fake_get_membership,
    )
    monkeypatch.setattr(
        "app.services.member_service.ClerkAccessService.create_organization_membership",
        fake_create_membership,
    )

    org = await db_session.scalar(
        select(models.Organization).where(models.Organization.clerk_org_id == "org_test_001")
    )
    account = models.User(
        email="archive.active@example.com",
        name="Archive Active",
        clerk_user_id="user_archive_active",
    )
    db_session.add(account)
    await db_session.flush()
    member = models.OrganizationMembership(
        organization_id=org.id,
        account_id=account.id,
        organization_display_name="Archive Active",
        lifecycle_status=models.MembershipLifecycleStatus.active,
        access_status=models.MembershipAccessStatus.active,
        teacher_access_mode=models.TeacherAccessMode.platform,
        can_admin=False,
        can_teach=True,
        expected_clerk_role=models.ClerkOrganizationRole.member,
        clerk_membership_id="orgmem_archive_active",
    )
    db_session.add(member)
    await db_session.flush()
    teacher = models.Teacher(
        organization_id=org.id,
        organization_membership_id=member.id,
    )
    timeslot = models.Timeslot(
        organization_id=org.id,
        day_of_week=2,
        start_time=time(9, 0),
        end_time=time(10, 0),
    )
    db_session.add_all([teacher, timeslot])
    await db_session.flush()
    db_session.add(
        models.Availability(
            organization_id=org.id,
            teacher_id=teacher.id,
            timeslot_id=timeslot.id,
        )
    )
    await db_session.commit()

    response = await async_client.post(
        f"/api/v1/members/{member.id}/remove",
        headers=clerk_admin_headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["remove_effect"] == "archive"
    assert revoked == [("org_test_001", "user_archive_active")]
    await db_session.refresh(member)
    assert member.lifecycle_status == models.MembershipLifecycleStatus.archived
    assert member.access_status == models.MembershipAccessStatus.blocked
    assert member.clerk_membership_id is None

    restore_response = await async_client.post(
        f"/api/v1/members/{member.id}/restore",
        headers=clerk_admin_headers,
        json={},
    )

    assert restore_response.status_code == 200, restore_response.text
    restored = restore_response.json()
    assert restored["lifecycle_status"] == "active"
    assert restored["access_status"] == "active"
    assert restored["clerk_membership_id"] == "orgmem_archive_restored"
    assert restored_memberships == [("org_test_001", "user_archive_active", "org:member")]
    await db_session.refresh(member)
    assert member.lifecycle_status == models.MembershipLifecycleStatus.active
    assert member.access_status == models.MembershipAccessStatus.active
    assert member.clerk_membership_id == "orgmem_archive_restored"


async def test_update_validates_subjects_before_clerk_role_change(
    async_client, clerk_admin_headers, db_session, monkeypatch
):
    from sqlalchemy import select

    from app import models
    from app.services.member_service import ClerkAccessResult

    called = False

    async def fake_change_role(self, **kwargs):
        nonlocal called
        called = True
        return ClerkAccessResult(membership_id="mem_changed", role=kwargs["role"])

    monkeypatch.setattr(
        "app.services.member_service.ClerkAccessService.change_membership_role", fake_change_role
    )
    org = await db_session.scalar(
        select(models.Organization).where(models.Organization.clerk_org_id == "org_test_001")
    )
    account = models.User(
        email="validate-before-clerk@example.com",
        name="Validate First",
        clerk_user_id="user_validate_first",
    )
    db_session.add(account)
    await db_session.flush()
    member = models.OrganizationMembership(
        organization_id=org.id,
        account_id=account.id,
        organization_display_name="Validate First",
        lifecycle_status=models.MembershipLifecycleStatus.active,
        access_status=models.MembershipAccessStatus.active,
        teacher_access_mode=models.TeacherAccessMode.platform,
        can_admin=False,
        can_teach=True,
        expected_clerk_role=models.ClerkOrganizationRole.member,
        clerk_membership_id="mem_existing",
    )
    db_session.add(member)
    await db_session.flush()
    teacher = models.Teacher(organization_id=org.id, organization_membership_id=member.id)
    db_session.add(teacher)
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
