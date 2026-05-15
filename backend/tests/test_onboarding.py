import pytest
from unittest.mock import patch
from datetime import date, time


# ── T19: GET status without token → 401 ────────────────────────
@pytest.mark.asyncio
async def test_onboarding_status_requires_auth(async_client):
    resp = await async_client.get("/api/v1/onboarding/status")
    assert resp.status_code == 401


# ── T20: POST onboarding → creates settings ────────────────────
@pytest.mark.asyncio
async def test_onboarding_creates_settings(async_client, db_session):
    from app import models
    from sqlalchemy.future import select

    org = models.Organization(name="Escola Onboard", clerk_org_id="org_onb_001", plan_status="active")
    db_session.add(org)
    await db_session.flush()

    user = models.User(
        clerk_user_id="user_onb_001", email="admin@onboard.pt",
        role="admin", organization_id=org.id, is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    data = {
        "school_start_date": "2025-09-15",
        "school_target_end_date": "2026-06-30",
        "school_hard_end_date": "2026-07-31",
        "lunch_start": "12:30",
        "lunch_end": "14:00",
        "lunch_min_duration": 60,
    }

    with patch("app.api.deps.get_clerk_payload") as mock_payload:
        mock_payload.return_value = {"sub": "user_onb_001", "o": {"id": "org_onb_001", "rol": "admin"}}
        resp = await async_client.post("/api/v1/onboarding", json=data)

    assert resp.status_code == 200
    resp_data = resp.json()
    assert resp_data["status"] == "ok"

    result = await db_session.execute(
        select(models.OrganizationSettings).where(
            models.OrganizationSettings.organization_id == org.id
        )
    )
    settings = result.scalar_one_or_none()
    assert settings is not None
    assert settings.school_start_date == date(2025, 9, 15)

    grid_result = await db_session.execute(
        select(models.OrganizationGridSettings).where(
            models.OrganizationGridSettings.organization_id == org.id
        )
    )
    grid = grid_result.scalar_one_or_none()
    assert grid is not None
    assert grid.lunch_window_start == time(12, 30)


# ── T21: POST without token → 401 ─────────────────────────────
@pytest.mark.asyncio
async def test_onboarding_requires_auth(async_client):
    data = {
        "school_start_date": "2025-09-15",
        "school_target_end_date": "2026-06-30",
        "school_hard_end_date": "2026-07-31",
        "lunch_start": "12:30",
        "lunch_end": "14:00",
        "lunch_min_duration": 60,
    }
    resp = await async_client.post("/api/v1/onboarding", json=data)
    assert resp.status_code == 401


# ── T22: Teacher rejected → 403 ───────────────────────────────
@pytest.mark.asyncio
async def test_onboarding_requires_admin(async_client, db_session):
    from app import models

    org = models.Organization(name="Escola T", clerk_org_id="org_t_001", plan_status="active")
    db_session.add(org)
    await db_session.flush()

    user = models.User(
        clerk_user_id="user_t_001", email="teacher@t.pt",
        role="teacher", organization_id=org.id, is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    data = {
        "school_start_date": "2025-09-15",
        "school_target_end_date": "2026-06-30",
        "school_hard_end_date": "2026-07-31",
        "lunch_start": "12:30",
        "lunch_end": "14:00",
        "lunch_min_duration": 60,
    }

    with patch("app.api.deps.get_clerk_payload") as mock_payload:
        mock_payload.return_value = {"sub": "user_t_001", "o": {"id": "org_t_001", "rol": "member"}}
        resp = await async_client.post("/api/v1/onboarding", json=data)

    assert resp.status_code == 403


# ── T23: Create teacher → sends Clerk invitation ───────────────
@pytest.mark.asyncio
async def test_create_teacher_invites_to_clerk(async_client, db_session):
    from app import models

    org = models.Organization(
        name="Escola Invite", clerk_org_id="org_inv_001", plan_status="active"
    )
    db_session.add(org)
    await db_session.flush()
    await db_session.commit()

    user = models.User(
        clerk_user_id="user_admin_inv", email="admin@invite.pt",
        role="admin", organization_id=org.id, is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    with patch("app.services.teacher_service.invite_teacher_to_clerk") as mock_invite, \
         patch("app.api.deps.get_clerk_payload") as mock_payload:
        mock_invite.return_value = {"invitation_id": "inv_123", "status": "pending"}
        mock_payload.return_value = {"sub": "user_admin_inv", "o": {"id": "org_inv_001", "rol": "admin"}}

        resp = await async_client.post("/api/v1/teachers/", json={
            "name": "Prof Teste",
            "email": "prof@invite.pt",
            "create_user_account": True,
            "password": "123456",
            "subject_ids": [],
        })

    assert resp.status_code == 200
    mock_invite.assert_called_once()
    call_kwargs = mock_invite.call_args.kwargs
    assert call_kwargs["clerk_org_id"] == "org_inv_001"
    assert call_kwargs["teacher_email"] == "prof@invite.pt"
    assert call_kwargs["teacher_id"] is not None
