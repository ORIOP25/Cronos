import datetime
import json
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from svix.webhooks import Webhook

_WEBHOOK_SECRET = "whsec_dGVzdF9zZWNyZXRfa2V5MTIz"
_TS = 1713158400000


def _svix_headers(payload: dict, *, svix_id: str = "msg_1713158400000") -> dict:
    wh = Webhook(_WEBHOOK_SECRET)
    body = json.dumps(payload)
    wh_timestamp = datetime.datetime.now(datetime.UTC)
    wh_sign = wh.sign(msg_id=svix_id, timestamp=wh_timestamp, data=body)
    return {
        "svix-id": svix_id,
        "svix-timestamp": str(int(wh_timestamp.timestamp())),
        "svix-signature": wh_sign,
        "Content-Type": "application/json",
    }


def _mk_payload(evt_type: str, data: dict) -> dict:
    return {"type": evt_type, "object": "event", "timestamp": _TS, "data": data}


@pytest.fixture(autouse=True)
def _set_webhook_secret(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "CLERK_WEBHOOK_SECRET", _WEBHOOK_SECRET)


@pytest_asyncio.fixture
async def async_client():
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
        yield client


async def test_webhook_user_created_without_membership_does_not_create_orphan_user(
    async_client, db_session
):
    payload = _mk_payload(
        "user.created",
        {
            "id": "user_wb_001",
            "first_name": "Test",
            "last_name": "User",
            "email_addresses": [{"email_address": "test@example.com", "id": "idn_123"}],
        },
    )

    response = await async_client.post(
        "/api/v1/webhooks/clerk", content=json.dumps(payload), headers=_svix_headers(payload)
    )

    assert response.status_code == 200

    from sqlalchemy import select

    from app import models

    user = await db_session.scalar(
        select(models.User).where(models.User.clerk_user_id == "user_wb_001")
    )
    event = await db_session.scalar(
        select(models.ClerkWebhookEvent).where(
            models.ClerkWebhookEvent.svix_id == "msg_1713158400000"
        )
    )
    assert user is None
    assert event.processing_status == models.ClerkWebhookProcessingStatus.ignored
    assert "email_addresses" not in event.payload_json["data"]


async def test_webhook_idempotency_uses_svix_event_id(async_client, db_session):
    payload = _mk_payload(
        "user.created",
        {"id": "user_wb_002", "email_addresses": [{"email_address": "first@example.com"}]},
    )
    response_1 = await async_client.post(
        "/api/v1/webhooks/clerk",
        content=json.dumps(payload),
        headers=_svix_headers(payload, svix_id="msg_idem"),
    )
    payload["data"]["email_addresses"] = [{"email_address": "second@example.com"}]
    response_2 = await async_client.post(
        "/api/v1/webhooks/clerk",
        content=json.dumps(payload),
        headers=_svix_headers(payload, svix_id="msg_idem"),
    )

    assert response_1.status_code == 200
    assert response_2.status_code == 200

    from sqlalchemy import func, select

    from app import models

    count = await db_session.scalar(
        select(func.count())
        .select_from(models.ClerkWebhookEvent)
        .where(models.ClerkWebhookEvent.svix_id == "msg_idem")
    )
    assert count == 1


async def test_webhook_membership_created_unmatched_does_not_grant_access(async_client, db_session):
    from sqlalchemy import select

    from app import models

    org = models.Organization(name="OrgA", clerk_org_id="org_wb_unmatched", plan_status="active")
    db_session.add(org)
    await db_session.commit()

    payload = _mk_payload(
        "organizationMembership.created",
        {
            "id": "mem_unmatched",
            "role": "org:admin",
            "organization": {"id": "org_wb_unmatched", "name": "OrgA"},
            "public_user_data": {"user_id": "user_wb_admin", "identifier": "admin@ex.com"},
            "public_metadata": {},
        },
    )

    response = await async_client.post(
        "/api/v1/webhooks/clerk",
        content=json.dumps(payload),
        headers=_svix_headers(payload, svix_id="msg_unmatched"),
    )

    assert response.status_code == 200
    user = await db_session.scalar(
        select(models.User).where(models.User.clerk_user_id == "user_wb_admin")
    )
    assert user is None


async def test_webhook_membership_created_matches_pending_local_member(async_client, db_session):
    from app import models

    org = models.Organization(name="OrgB", clerk_org_id="org_wb_match", plan_status="active")
    user = models.User(email="match@example.com", name="Match User")
    db_session.add_all([org, user])
    await db_session.flush()
    member = models.OrganizationMembership(
        organization_id=org.id,
        account_id=user.id,
        organization_display_name="Match User",
        lifecycle_status=models.MembershipLifecycleStatus.active,
        access_status=models.MembershipAccessStatus.pending_invite,
        can_admin=True,
        can_teach=False,
        expected_clerk_role=models.ClerkOrganizationRole.admin,
        clerk_invitation_id="inv_match",
        clerk_invitation_status=models.ClerkInvitationStatus.pending,
    )
    db_session.add(member)
    await db_session.flush()
    member_id = member.id
    await db_session.commit()

    payload = _mk_payload(
        "organizationMembership.created",
        {
            "id": "mem_match",
            "role": "org:admin",
            "organization": {"id": "org_wb_match", "name": "OrgB"},
            "public_user_data": {"user_id": "user_wb_match", "identifier": "match@example.com"},
            "public_metadata": {"membership_id": member_id},
        },
    )

    from app.services import member_webhook_service

    await member_webhook_service.enqueue_and_process_clerk_event(
        db_session,
        svix_id=f"msg_match_{uuid4().hex}",
        payload=payload,
    )
    await db_session.flush()
    await db_session.refresh(member)
    await db_session.refresh(user)

    assert member.access_status == models.MembershipAccessStatus.active
    assert member.clerk_membership_id == "mem_match"
    assert user.clerk_user_id == "user_wb_match"


async def test_webhook_membership_role_mismatch_sets_sync_error(async_client, db_session):
    from app import models

    org = models.Organization(name="OrgC", clerk_org_id="org_wb_role", plan_status="active")
    user = models.User(email="role@example.com", name="Role User")
    db_session.add_all([org, user])
    await db_session.flush()
    member = models.OrganizationMembership(
        organization_id=org.id,
        account_id=user.id,
        organization_display_name="Role User",
        lifecycle_status=models.MembershipLifecycleStatus.active,
        access_status=models.MembershipAccessStatus.pending_invite,
        can_admin=True,
        can_teach=False,
        expected_clerk_role=models.ClerkOrganizationRole.admin,
    )
    db_session.add(member)
    await db_session.flush()
    member_id = member.id
    await db_session.commit()

    payload = _mk_payload(
        "organizationMembership.created",
        {
            "id": "mem_role",
            "role": "org:member",
            "organization": {"id": "org_wb_role", "name": "OrgC"},
            "public_user_data": {"user_id": "user_wb_role", "identifier": "role@example.com"},
            "public_metadata": {"membership_id": member_id},
        },
    )

    from app.services import member_webhook_service

    await member_webhook_service.enqueue_and_process_clerk_event(
        db_session,
        svix_id=f"msg_role_{uuid4().hex}",
        payload=payload,
    )
    await db_session.flush()
    await db_session.refresh(member)

    assert member.access_status == models.MembershipAccessStatus.sync_error
    assert member.access_error_category == "provider_role_mismatch"


async def test_webhook_membership_identity_conflict_sets_sync_error(db_session):
    from app import models
    from app.services import member_webhook_service

    org = models.Organization(
        name="OrgIdentity", clerk_org_id="org_wb_identity", plan_status="active"
    )
    user = models.User(
        email="identity@example.com", name="Identity User", clerk_user_id="user_existing_identity"
    )
    db_session.add_all([org, user])
    await db_session.flush()
    member = models.OrganizationMembership(
        organization_id=org.id,
        account_id=user.id,
        organization_display_name="Identity User",
        lifecycle_status=models.MembershipLifecycleStatus.active,
        access_status=models.MembershipAccessStatus.pending_invite,
        can_admin=True,
        can_teach=False,
        expected_clerk_role=models.ClerkOrganizationRole.admin,
    )
    db_session.add(member)
    await db_session.flush()
    member_id = member.id
    await db_session.commit()

    payload = _mk_payload(
        "organizationMembership.created",
        {
            "id": "mem_identity",
            "role": "org:admin",
            "organization": {"id": "org_wb_identity", "name": "OrgIdentity"},
            "public_user_data": {
                "user_id": "user_other_identity",
                "identifier": "identity@example.com",
            },
            "public_metadata": {"membership_id": member_id},
        },
    )

    await member_webhook_service.enqueue_and_process_clerk_event(
        db_session,
        svix_id=f"msg_identity_{uuid4().hex}",
        payload=payload,
    )
    await db_session.flush()
    await db_session.refresh(member)
    await db_session.refresh(user)

    assert user.clerk_user_id == "user_existing_identity"
    assert member.access_status == models.MembershipAccessStatus.sync_error
    assert member.access_error_category == "identity_conflict"


async def test_webhook_user_identity_conflict_marks_memberships_sync_error(db_session):
    from app import models
    from app.services import member_webhook_service

    org = models.Organization(
        name="OrgUserIdentity", clerk_org_id="org_wb_user_identity", plan_status="active"
    )
    user = models.User(
        email="user.identity@example.com",
        name="User Identity",
        clerk_user_id="user_existing_profile",
    )
    db_session.add_all([org, user])
    await db_session.flush()
    member = models.OrganizationMembership(
        organization_id=org.id,
        account_id=user.id,
        organization_display_name="User Identity",
        lifecycle_status=models.MembershipLifecycleStatus.active,
        access_status=models.MembershipAccessStatus.active,
        can_admin=True,
        can_teach=False,
        expected_clerk_role=models.ClerkOrganizationRole.admin,
        clerk_membership_id="mem_user_identity",
    )
    db_session.add(member)
    await db_session.flush()
    await db_session.commit()

    payload = _mk_payload(
        "user.updated",
        {
            "id": "user_conflicting_profile",
            "first_name": "User",
            "last_name": "Identity",
            "email_addresses": [
                {"email_address": "user.identity@example.com", "id": "idn_user_identity"}
            ],
        },
    )

    await member_webhook_service.enqueue_and_process_clerk_event(
        db_session,
        svix_id=f"msg_user_identity_{uuid4().hex}",
        payload=payload,
    )
    await db_session.flush()
    await db_session.refresh(member)
    await db_session.refresh(user)

    assert user.clerk_user_id == "user_existing_profile"
    assert member.access_status == models.MembershipAccessStatus.sync_error
    assert member.access_error_category == "identity_conflict"


async def test_webhook_missing_secret_fails_closed(async_client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "CLERK_WEBHOOK_SECRET", "")
    payload = _mk_payload("user.created", {"id": "user_no_secret"})

    response = await async_client.post(
        "/api/v1/webhooks/clerk",
        content=json.dumps(payload),
        headers=_svix_headers(payload, svix_id="msg_no_secret"),
    )

    assert response.status_code == 503


async def test_webhook_invalid_signature_rejected(async_client):
    payload = _mk_payload("user.created", {"id": "user_bad_sig"})
    headers = _svix_headers(payload, svix_id="msg_bad_sig")
    headers["svix-signature"] = "bad"

    response = await async_client.post(
        "/api/v1/webhooks/clerk", content=json.dumps(payload), headers=headers
    )

    assert response.status_code == 401
