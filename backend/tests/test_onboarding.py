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
            "subject_ids": [],
        })

    assert resp.status_code == 200
    mock_invite.assert_called_once()
    call_kwargs = mock_invite.call_args.kwargs
    assert call_kwargs["clerk_org_id"] == "org_inv_001"
    assert call_kwargs["teacher_email"] == "prof@invite.pt"
    assert call_kwargs["teacher_id"] is not None


# ── FASE 1.5: Onboarding fluxos de borda ──────────────────────

@pytest.mark.asyncio
async def test_onboarding_post_idempotent(async_client, db_session):
    """POST 2x → segunda vez é no-op, retorna 200 em ambas."""
    from app import models
    from sqlalchemy.future import select as sa_select

    org = models.Organization(name="Escola Idemp", clerk_org_id="org_onb_idem", plan_status="active")
    db_session.add(org)
    await db_session.flush()

    user = models.User(
        clerk_user_id="user_onb_idem", email="idem@onb.pt",
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
        mock_payload.return_value = {"sub": "user_onb_idem", "o": {"id": "org_onb_idem", "rol": "admin"}}
        resp1 = await async_client.post("/api/v1/onboarding", json=data)
        assert resp1.status_code == 200

        resp2 = await async_client.post("/api/v1/onboarding", json=data)
        assert resp2.status_code == 200

    # Apenas 1 OrganizationSettings
    result = await db_session.execute(
        sa_select(models.OrganizationSettings).where(
            models.OrganizationSettings.organization_id == org.id
        )
    )
    assert len(result.all()) == 1


@pytest.mark.asyncio
async def test_onboarding_status_incomplete(async_client, db_session):
    """GET /onboarding/status sem settings → onboarding_complete: false."""
    from app import models

    org = models.Organization(name="Escola Incomp", clerk_org_id="org_onb_inc", plan_status="active")
    db_session.add(org)
    await db_session.flush()

    user = models.User(
        clerk_user_id="user_onb_inc", email="inc@onb.pt",
        role="admin", organization_id=org.id, is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    with patch("app.api.deps.get_clerk_payload") as mock_payload:
        mock_payload.return_value = {"sub": "user_onb_inc", "o": {"id": "org_onb_inc", "rol": "admin"}}
        resp = await async_client.get("/api/v1/onboarding/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["onboarding_complete"] is False
        assert data["organization_name"] == "Escola Incomp"


@pytest.mark.asyncio
async def test_onboarding_status_complete_after_post(async_client, db_session):
    """POST onboarding → GET status → onboarding_complete: true."""
    from app import models

    org = models.Organization(name="Escola Comp", clerk_org_id="org_onb_comp", plan_status="active")
    db_session.add(org)
    await db_session.flush()

    user = models.User(
        clerk_user_id="user_onb_comp", email="comp@onb.pt",
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
        mock_payload.return_value = {"sub": "user_onb_comp", "o": {"id": "org_onb_comp", "rol": "admin"}}
        await async_client.post("/api/v1/onboarding", json=data)
        resp = await async_client.get("/api/v1/onboarding/status")
        assert resp.status_code == 200
        assert resp.json()["onboarding_complete"] is True


@pytest.mark.asyncio
async def test_onboarding_requires_organization_association(async_client, db_session):
    """User sem organization_id → 400."""
    from app import models

    user = models.User(
        clerk_user_id="user_no_org_assoc", email="noorg@onb.pt",
        role="admin", organization_id=None, is_active=True,
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
        mock_payload.return_value = {"sub": "user_no_org_assoc", "o": {"id": "org_x", "rol": "admin"}}
        resp = await async_client.post("/api/v1/onboarding", json=data)
        assert resp.status_code == 400
