import json
import datetime
import pytest
from httpx import AsyncClient, ASGITransport
from svix.webhooks import Webhook


_WEBHOOK_SECRET = "whsec_dGVzdF9zZWNyZXRfa2V5MTIz"

_TS = 1713158400000


def _svix_headers(payload: dict) -> dict:
    wh = Webhook(_WEBHOOK_SECRET)
    body = json.dumps(payload)
    wh_id = "msg_1713158400000"
    wh_timestamp = datetime.datetime.now(datetime.timezone.utc)
    wh_sign = wh.sign(msg_id=wh_id, timestamp=wh_timestamp, data=body)
    return {
        "svix-id": wh_id,
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


@pytest.fixture
def async_client():
    from app.main import app
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# ── T9: user.created ────────────────────────────────────────────
@pytest.mark.asyncio
async def test_webhook_user_created_creates_local_user(async_client, db_session):
    payload = _mk_payload("user.created", {
        "id": "user_wb_001",
        "first_name": "Test",
        "last_name": "User",
        "email_addresses": [{"email_address": "test@example.com", "id": "idn_123"}],
    })

    headers = _svix_headers(payload)
    resp = await async_client.post(
        "/api/v1/webhooks/clerk",
        content=json.dumps(payload),
        headers=headers,
    )
    assert resp.status_code == 200

    from app import models
    from sqlalchemy.future import select
    result = await db_session.execute(
        select(models.User).where(models.User.clerk_user_id == "user_wb_001")
    )
    user = result.scalar_one_or_none()
    assert user is not None
    assert user.email == "test@example.com"
    assert user.name == "Test User"


# ── T10: Idempotency ────────────────────────────────────────────
@pytest.mark.asyncio
async def test_webhook_user_created_idempotent(async_client, db_session):
    payload = _mk_payload("user.created", {
        "id": "user_wb_002",
        "first_name": "First",
        "last_name": "Call",
        "email_addresses": [{"email_address": "first@example.com", "id": "idn_1"}],
    })

    headers = _svix_headers(payload)
    raw = json.dumps(payload)
    resp1 = await async_client.post("/api/v1/webhooks/clerk", content=raw, headers=headers)

    payload["data"]["first_name"] = "Second"
    payload["data"]["email_addresses"] = [{"email_address": "second@example.com", "id": "idn_1"}]
    headers2 = _svix_headers(payload)
    raw2 = json.dumps(payload)
    resp2 = await async_client.post("/api/v1/webhooks/clerk", content=raw2, headers=headers2)

    assert resp1.status_code == 200
    assert resp2.status_code == 200

    from app import models
    from sqlalchemy.future import select
    from sqlalchemy import func
    result = await db_session.execute(
        select(func.count()).select_from(models.User).where(
            models.User.clerk_user_id == "user_wb_002"
        )
    )
    count = result.scalar()
    assert count == 1


# ── T11: organization.created ───────────────────────────────────
@pytest.mark.asyncio
async def test_webhook_organization_created(async_client, db_session):
    payload = _mk_payload("organization.created", {
        "id": "org_wb_001", "name": "Escola Teste", "slug": "escola-teste",
    })

    headers = _svix_headers(payload)
    resp = await async_client.post(
        "/api/v1/webhooks/clerk", content=json.dumps(payload), headers=headers,
    )
    assert resp.status_code == 200

    from app import models
    from sqlalchemy.future import select
    result = await db_session.execute(
        select(models.Organization).where(models.Organization.clerk_org_id == "org_wb_001")
    )
    org = result.scalar_one_or_none()
    assert org is not None
    assert org.name == "Escola Teste"


# ── T12: membership.created admin ───────────────────────────────
@pytest.mark.asyncio
async def test_webhook_membership_created_admin(async_client, db_session):
    from app import models
    org = models.Organization(name="OrgA", clerk_org_id="org_wb_admin", plan_status="active")
    db_session.add(org)
    await db_session.commit()

    payload = _mk_payload("organizationMembership.created", {
        "role": "admin",
        "organization": {"id": "org_wb_admin", "name": "OrgA", "slug": "orga"},
        "public_user_data": {"user_id": "user_wb_admin", "identifier": "admin@ex.com"},
        "public_metadata": {},
    })

    headers = _svix_headers(payload)
    resp = await async_client.post(
        "/api/v1/webhooks/clerk", content=json.dumps(payload), headers=headers,
    )
    assert resp.status_code == 200

    from sqlalchemy.future import select
    result = await db_session.execute(
        select(models.User).where(models.User.clerk_user_id == "user_wb_admin")
    )
    user = result.scalar_one_or_none()
    assert user is not None
    assert user.role == "admin"


# ── T13: membership.created teacher ─────────────────────────────
@pytest.mark.asyncio
async def test_webhook_membership_created_teacher(async_client, db_session):
    from app import models
    org = models.Organization(name="OrgB", clerk_org_id="org_wb_teacher", plan_status="active")
    db_session.add(org)
    await db_session.commit()

    payload = _mk_payload("organizationMembership.created", {
        "role": "member",
        "organization": {"id": "org_wb_teacher", "name": "OrgB", "slug": "orgb"},
        "public_user_data": {"user_id": "user_wb_teacher", "identifier": "prof@ex.com"},
        "public_metadata": {},
    })

    headers = _svix_headers(payload)
    resp = await async_client.post(
        "/api/v1/webhooks/clerk", content=json.dumps(payload), headers=headers,
    )
    assert resp.status_code == 200

    from sqlalchemy.future import select
    result = await db_session.execute(
        select(models.User).where(models.User.clerk_user_id == "user_wb_teacher")
    )
    user = result.scalar_one_or_none()
    assert user.role == "teacher"


# ── T14: membership.created with teacher_id ─────────────────────
@pytest.mark.asyncio
async def test_webhook_membership_created_with_teacher_id(async_client, db_session):
    from app import models
    org = models.Organization(name="OrgC", clerk_org_id="org_wb_link", plan_status="active")
    db_session.add(org)
    await db_session.flush()

    teacher = models.Teacher(name="Prof Link", organization_id=org.id)
    db_session.add(teacher)
    await db_session.flush()
    await db_session.commit()

    payload = _mk_payload("organizationMembership.created", {
        "role": "member",
        "organization": {"id": "org_wb_link", "name": "OrgC", "slug": "orgc"},
        "public_user_data": {"user_id": "user_wb_link", "identifier": "link@ex.com"},
        "public_metadata": {"teacher_id": teacher.id},
    })

    headers = _svix_headers(payload)
    resp = await async_client.post(
        "/api/v1/webhooks/clerk", content=json.dumps(payload), headers=headers,
    )
    assert resp.status_code == 200

    from sqlalchemy.future import select
    result = await db_session.execute(
        select(models.User).where(models.User.clerk_user_id == "user_wb_link")
    )
    user = result.scalar_one_or_none()
    assert user.teacher_id == teacher.id


# ── T15: membership.updated → role change ───────────────────────
@pytest.mark.asyncio
async def test_webhook_membership_updated_role_change(async_client, db_session):
    from app import models
    org = models.Organization(name="OrgD", clerk_org_id="org_wb_update", plan_status="active")
    db_session.add(org)
    await db_session.commit()

    user = models.User(
        clerk_user_id="user_wb_update", email="change@ex.com",
        role="teacher", organization_id=org.id
    )
    db_session.add(user)
    await db_session.commit()

    payload = _mk_payload("organizationMembership.updated", {
        "role": "admin",
        "organization": {"id": "org_wb_update", "name": "OrgD", "slug": "orgd"},
        "public_user_data": {"user_id": "user_wb_update", "identifier": "change@ex.com"},
        "public_metadata": {},
    })

    headers = _svix_headers(payload)
    resp = await async_client.post(
        "/api/v1/webhooks/clerk", content=json.dumps(payload), headers=headers,
    )
    assert resp.status_code == 200

    await db_session.refresh(user)
    assert user.role == "admin"


# ── T16: membership.deleted → org_id cleared ────────────────────
@pytest.mark.asyncio
async def test_webhook_membership_deleted(async_client, db_session):
    from app import models
    org = models.Organization(name="OrgE", clerk_org_id="org_wb_del", plan_status="active")
    db_session.add(org)
    await db_session.commit()

    user = models.User(
        clerk_user_id="user_wb_del", email="leave@ex.com",
        role="teacher", organization_id=org.id
    )
    db_session.add(user)
    await db_session.commit()

    payload = _mk_payload("organizationMembership.deleted", {
        "organization": {"id": "org_wb_del"},
        "public_user_data": {"user_id": "user_wb_del"},
    })

    headers = _svix_headers(payload)
    resp = await async_client.post(
        "/api/v1/webhooks/clerk", content=json.dumps(payload), headers=headers,
    )
    assert resp.status_code == 200

    await db_session.refresh(user)
    assert user.organization_id is None


# ── T17: Invalid signature → 401 ────────────────────────────────
@pytest.mark.asyncio
async def test_webhook_invalid_signature_rejected(async_client):
    payload = {"type": "user.created", "object": "event", "timestamp": _TS, "data": {"id": "x"}}
    headers = {
        "svix-id": "bad", "svix-timestamp": "0",
        "svix-signature": "v1,bad_signature",
        "Content-Type": "application/json",
    }
    resp = await async_client.post(
        "/api/v1/webhooks/clerk", content=json.dumps(payload), headers=headers,
    )
    assert resp.status_code == 401


# ── T18: Missing Svix headers → 400 ─────────────────────────────
@pytest.mark.asyncio
async def test_webhook_missing_svix_headers(async_client):
    payload = {"type": "user.created", "object": "event", "timestamp": _TS, "data": {"id": "x"}}
    resp = await async_client.post(
        "/api/v1/webhooks/clerk", content=json.dumps(payload),
    )
    assert resp.status_code == 400
