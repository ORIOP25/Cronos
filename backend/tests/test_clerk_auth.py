from unittest.mock import MagicMock

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
from tests.conftest import ensure_membership_capabilities


class FakeClerkGateway:
    def __init__(self, state: RequestState) -> None:
        self.state = state
        self.calls = 0

    async def authenticate_request(self, _request):
        self.calls += 1
        return self.state


async def test_clerk_gateway_owns_async_sdk_lifecycle():
    calls = []
    signed_out = RequestState(status=AuthStatus.SIGNED_OUT)

    class FakeSdk:
        async def __aenter__(self):
            calls.append("enter")
            return self

        async def __aexit__(self, *_args):
            calls.append("exit")

        async def authenticate_request_async(self, _request, _options):
            calls.append("authenticate")
            return signed_out

    async with ClerkGateway(FakeSdk()) as gateway:
        assert await gateway.authenticate_request(MagicMock()) is signed_out

    assert calls == ["enter", "authenticate", "exit"]


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
