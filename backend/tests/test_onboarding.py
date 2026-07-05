import pytest
from unittest.mock import patch
from datetime import date, time


@pytest.fixture(autouse=True)
def _stub_clerk_onboarding_metadata(monkeypatch):
    async def _noop(_clerk_user_id: str) -> None:
        return None

    monkeypatch.setattr(
        "app.api.v1.endpoints.onboarding.mark_onboarding_complete_in_clerk",
        _noop,
    )


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
    from tests.conftest import create_org_and_user

    org, _ = await create_org_and_user(
        db_session,
        clerk_user_id="user_onb_001",
        email="admin@onboard.pt",
        role="admin",
        org_name="Escola Onboard",
        clerk_org_id="org_onb_001",
    )

    data = {
        "school_start_date": "2025-09-15",
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
    from tests.conftest import create_org_and_user

    await create_org_and_user(
        db_session,
        clerk_user_id="user_t_001",
        email="teacher@t.pt",
        role="teacher",
        org_name="Escola T",
        clerk_org_id="org_t_001",
    )

    data = {
        "school_start_date": "2025-09-15",
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
async def test_create_teacher_write_is_quarantined(async_client, db_session):
    from tests.conftest import create_org_and_user

    await create_org_and_user(
        db_session,
        clerk_user_id="user_admin_inv",
        email="admin@invite.pt",
        role="admin",
        org_name="Escola Invite",
        clerk_org_id="org_inv_001",
    )

    with patch("app.api.deps.get_clerk_payload") as mock_payload:
        mock_payload.return_value = {"sub": "user_admin_inv", "o": {"id": "org_inv_001", "rol": "admin"}}

        resp = await async_client.post("/api/v1/teachers/", json={
            "name": "Prof Teste",
            "email": "prof@invite.pt",
            "subject_ids": [],
        })

    assert resp.status_code == 410
    assert "/api/v1/members" in resp.json()["detail"]


# ── FASE 1.5: Onboarding fluxos de borda ──────────────────────

@pytest.mark.asyncio
async def test_onboarding_post_idempotent(async_client, db_session):
    """POST 2x → segunda vez é no-op, retorna 200 em ambas."""
    from app import models
    from sqlalchemy.future import select as sa_select
    from tests.conftest import create_org_and_user

    org, _ = await create_org_and_user(
        db_session,
        clerk_user_id="user_onb_idem",
        email="idem@onb.pt",
        role="admin",
        org_name="Escola Idemp",
        clerk_org_id="org_onb_idem",
    )

    data = {
        "school_start_date": "2025-09-15",
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
    from tests.conftest import create_org_and_user

    await create_org_and_user(
        db_session,
        clerk_user_id="user_onb_inc",
        email="inc@onb.pt",
        role="admin",
        org_name="Escola Incomp",
        clerk_org_id="org_onb_inc",
    )

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
    from tests.conftest import create_org_and_user

    await create_org_and_user(
        db_session,
        clerk_user_id="user_onb_comp",
        email="comp@onb.pt",
        role="admin",
        org_name="Escola Comp",
        clerk_org_id="org_onb_comp",
    )

    data = {
        "school_start_date": "2025-09-15",
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
async def test_global_account_can_exist_without_organization_membership(async_client, db_session):
    """User sem organization_id é rejeitado pela invariant final do schema."""
    from app import models

    user = models.User(
        clerk_user_id="user_no_org_assoc", email="noorg@onb.pt",
        role=None, organization_id=None, is_active=None,
    )
    db_session.add(user)
    await db_session.commit()
    assert user.id is not None
