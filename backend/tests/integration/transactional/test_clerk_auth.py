from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from clerk_backend_api.security.types import AuthStatus, RequestState
from fastapi import HTTPException

from app import models
from app.api.deps import (
    get_clerk_payload,
    get_current_active_admin,
    get_current_user,
)
from app.core.auth import Actor
from app.core.clerk import ClerkGateway, verify_clerk_request
from app.services import clerk_sync
from tests._support.db_fixtures import ensure_membership_capabilities


class FakeClerkGateway:
    def __init__(self, state: RequestState) -> None:
        self.state = state
        self.calls = 0

    async def authenticate_request(self, _request):
        self.calls += 1
        return self.state


async def test_clerk_gateway_uses_injected_sdk_without_a_secret(monkeypatch):
    monkeypatch.setattr("app.core.clerk.settings.CLERK_SECRET_KEY", "   ")
    calls = []
    signed_out = RequestState(status=AuthStatus.SIGNED_OUT)

    class FakeSdk:
        options = None

        async def __aenter__(self):
            calls.append("enter")
            return self

        async def __aexit__(self, *_args):
            calls.append("exit")

        async def authenticate_request_async(self, _request, _options):
            calls.append("authenticate")
            self.options = _options
            return signed_out

    sdk = FakeSdk()
    async with ClerkGateway(sdk) as gateway:
        assert await gateway.authenticate_request(MagicMock()) is signed_out

    assert calls == ["enter", "authenticate", "exit"]
    assert sdk.options.clock_skew_in_ms == 60_000


def test_clerk_gateway_requires_a_secret_for_real_sdk(monkeypatch):
    monkeypatch.setattr("app.core.clerk.settings.CLERK_SECRET_KEY", "   ")

    with pytest.raises(RuntimeError, match="CLERK_SECRET_KEY"):
        ClerkGateway()


@pytest.mark.parametrize(
    ("state", "signed_in"),
    [
        (
            RequestState(
                status=AuthStatus.SIGNED_IN,
                payload={"sub": "user_123", "o": {"id": "org_456", "rol": "admin"}},
            ),
            True,
        ),
        (RequestState(status=AuthStatus.SIGNED_OUT), False),
    ],
)
async def test_verify_clerk_request_uses_gateway(state, signed_in):
    gateway = FakeClerkGateway(state)

    result = await verify_clerk_request(MagicMock(), gateway)

    assert result.is_signed_in is signed_in
    assert gateway.calls == 1


async def test_verify_clerk_request_creates_and_closes_gateway_when_not_injected(monkeypatch):
    calls = []
    signed_out = RequestState(status=AuthStatus.SIGNED_OUT)

    class ManagedGateway:
        async def __aenter__(self):
            calls.append("enter")
            return self

        async def __aexit__(self, *_args):
            calls.append("exit")

        async def authenticate_request(self, _request):
            calls.append("authenticate")
            return signed_out

    monkeypatch.setattr("app.core.clerk.ClerkGateway", ManagedGateway)

    assert await verify_clerk_request(MagicMock()) is signed_out
    assert calls == ["enter", "authenticate", "exit"]


async def test_get_current_user_resolves_immutable_actor(db_session):
    organization = models.Organization(
        name="Actor School",
        clerk_org_id="org_actor",
        plan_status=models.OrganizationPlanStatus.active,
    )
    account = models.User(
        clerk_user_id="user_actor",
        email="actor@example.com",
    )
    db_session.add_all([organization, account])
    await db_session.flush()
    membership = await ensure_membership_capabilities(
        db_session,
        organization_id=organization.id,
        user=account,
        capabilities=[models.MembershipCapability.admin],
    )

    request = MagicMock()
    actor = await get_current_user(
        request,
        db_session,
        {"sub": "user_actor", "o": {"id": "org_actor", "rol": "admin"}},
    )

    assert actor == Actor(
        account_id=account.id,
        clerk_user_id="user_actor",
        organization_id=organization.id,
        membership_id=membership.id,
        can_admin=True,
        can_teach=False,
        teacher_id=None,
    )
    assert request.state.current_organization_id == organization.id
    assert not hasattr(actor, "email")


@pytest.mark.parametrize(
    ("lifecycle_status", "access_status"),
    [
        (models.MembershipLifecycleStatus.active, models.MembershipAccessStatus.blocked),
        (models.MembershipLifecycleStatus.archived, models.MembershipAccessStatus.none),
        (models.MembershipLifecycleStatus.active, models.MembershipAccessStatus.sync_error),
    ],
)
async def test_denied_membership_is_not_repaired_during_authentication(
    db_session,
    monkeypatch,
    lifecycle_status,
    access_status,
):
    organization = models.Organization(
        name="Denied School",
        clerk_org_id=f"org-denied-{access_status.value}",
        plan_status=models.OrganizationPlanStatus.active,
    )
    account = models.User(
        clerk_user_id=f"user-denied-{access_status.value}",
        email=f"denied-{access_status.value}@example.com",
    )
    db_session.add_all([organization, account])
    await db_session.flush()
    member = models.OrganizationMembership(
        organization_id=organization.id,
        account_id=account.id,
        organization_display_name=organization.name,
        lifecycle_status=lifecycle_status,
        access_status=access_status,
        can_admin=True,
        can_teach=True,
        teacher_access_mode=models.TeacherAccessMode.platform,
    )
    db_session.add(member)
    await db_session.flush()

    monkeypatch.setattr(
        clerk_sync,
        "fetch_clerk_user_profile",
        AsyncMock(
            return_value=clerk_sync.ClerkUserProfile(
                email=account.email,
                name="Denied User",
            )
        ),
    )
    ensure_user = AsyncMock(side_effect=AssertionError("generic identity repair was called"))
    monkeypatch.setattr(clerk_sync, "ensure_user_exists", ensure_user)

    with pytest.raises(HTTPException) as exc:
        await get_current_user(
            MagicMock(),
            db_session,
            {
                "sub": account.clerk_user_id,
                "o": {"id": organization.clerk_org_id, "rol": "admin"},
            },
        )

    assert exc.value.status_code == 403
    assert ensure_user.await_count == 0
    await db_session.refresh(member)
    assert member.lifecycle_status == lifecycle_status
    assert member.access_status == access_status
    assert member.can_admin is True


@pytest.mark.parametrize(
    ("payload", "status_code"),
    [
        ({"o": {"id": "org_1"}}, 401),
        ({"sub": "user_1"}, 403),
    ],
)
async def test_get_current_user_requires_subject_and_organization(
    db_session,
    payload,
    status_code,
):
    with pytest.raises(HTTPException) as exc:
        await get_current_user(MagicMock(), db_session, payload)

    assert exc.value.status_code == status_code


def test_get_current_active_admin_accepts_admin_actor():
    actor = Actor(1, "user_1", 2, 3, True, False, None)
    assert get_current_active_admin(actor) is actor


def test_get_current_active_admin_rejects_non_admin_actor():
    actor = Actor(1, "user_1", 2, 3, False, True, 4)

    with pytest.raises(HTTPException) as exc:
        get_current_active_admin(actor)

    assert exc.value.status_code == 403


async def test_get_clerk_payload_rejects_signed_out_request():
    gateway = FakeClerkGateway(RequestState(status=AuthStatus.SIGNED_OUT))

    with pytest.raises(HTTPException) as exc:
        await get_clerk_payload(MagicMock(), gateway)

    assert exc.value.status_code == 401
    assert exc.value.detail["error"] == "NOT_AUTHENTICATED"


async def test_get_clerk_payload_logs_the_specific_clerk_failure(monkeypatch):
    from app.api import deps

    calls = []
    monkeypatch.setattr(
        deps.logger,
        "warning",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    state = SimpleNamespace(
        is_signed_in=False,
        reason=SimpleNamespace(value="token-invalid-signature"),
    )

    with pytest.raises(HTTPException):
        await get_clerk_payload(MagicMock(), FakeClerkGateway(state))

    assert calls == [
        (("clerk_auth_rejected",), {"auth_failure_category": "token-invalid-signature"})
    ]
