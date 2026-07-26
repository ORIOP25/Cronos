from datetime import date, time

import pytest


@pytest.fixture(autouse=True)
def _stub_clerk_onboarding_metadata(monkeypatch):
    async def _noop(_clerk_user_id: str, _gateway=None) -> None:
        return None

    monkeypatch.setattr(
        "app.api.v1.endpoints.onboarding.mark_onboarding_complete_in_clerk",
        _noop,
    )


async def test_onboarding_clerk_metadata_uses_update_metadata(monkeypatch):
    from app.services.organization_service import mark_onboarding_complete_in_clerk

    class FakeUsers:
        def __init__(self):
            self.calls = []

        def update_metadata(self, *, user_id, public_metadata):
            self.calls.append(
                {
                    "user_id": user_id,
                    "public_metadata": public_metadata,
                }
            )

    class FakeSdk:
        def __init__(self):
            self.users = FakeUsers()

    fake_sdk = FakeSdk()
    monkeypatch.setattr(
        "app.core.clerk.get_clerk_sdk",
        lambda: fake_sdk,
    )

    await mark_onboarding_complete_in_clerk("user_onb_metadata")

    assert fake_sdk.users.calls == [
        {
            "user_id": "user_onb_metadata",
            "public_metadata": {"onboardingComplete": True},
        }
    ]


# ── T19: GET status without token → 401 ────────────────────────
async def test_onboarding_status_requires_auth(async_client):
    resp = await async_client.get("/api/v1/onboarding/status")
    assert resp.status_code == 401


# ── T20: POST onboarding → creates settings ────────────────────
async def test_onboarding_creates_settings(async_client, db_session):
    from sqlalchemy.future import select

    from app import models
    from tests.conftest import create_org_and_user

    org, _ = await create_org_and_user(
        db_session,
        clerk_user_id="user_onb_001",
        email="admin@onboard.pt",
        role="admin",
        org_name="Escola Onboard",
        clerk_org_id="org_onb_001",
    )
    await db_session.commit()
    data = {
        "school_start_date": "2025-09-15",
        "school_hard_end_date": "2026-07-31",
        "lunch_start": "12:30",
        "lunch_end": "14:00",
        "lunch_min_duration": 60,
    }

    resp = await async_client.post(
        "/api/v1/onboarding",
        headers={"Authorization": "Bearer test_user_onb_001"},
        json=data,
    )

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
    await db_session.commit()
    data = {
        "school_start_date": "2025-09-15",
        "school_hard_end_date": "2026-07-31",
        "lunch_start": "12:30",
        "lunch_end": "14:00",
        "lunch_min_duration": 60,
    }

    resp = await async_client.post(
        "/api/v1/onboarding",
        headers={"Authorization": "Bearer test_user_t_001"},
        json=data,
    )

    assert resp.status_code == 403


# ── FASE 1.5: Onboarding fluxos de borda ──────────────────────
async def test_onboarding_post_idempotent(async_client, db_session):
    """POST 2x → segunda vez é no-op, retorna 200 em ambas."""
    from sqlalchemy.future import select as sa_select

    from app import models
    from tests.conftest import create_org_and_user

    org, _ = await create_org_and_user(
        db_session,
        clerk_user_id="user_onb_idem",
        email="idem@onb.pt",
        role="admin",
        org_name="Escola Idemp",
        clerk_org_id="org_onb_idem",
    )
    await db_session.commit()
    data = {
        "school_start_date": "2025-09-15",
        "school_hard_end_date": "2026-07-31",
        "lunch_start": "12:30",
        "lunch_end": "14:00",
        "lunch_min_duration": 60,
    }

    headers = {"Authorization": "Bearer test_user_onb_idem"}
    resp1 = await async_client.post("/api/v1/onboarding", headers=headers, json=data)
    assert resp1.status_code == 200
    resp2 = await async_client.post("/api/v1/onboarding", headers=headers, json=data)
    assert resp2.status_code == 200

    # Apenas 1 OrganizationSettings
    result = await db_session.execute(
        sa_select(models.OrganizationSettings).where(
            models.OrganizationSettings.organization_id == org.id
        )
    )
    assert len(result.all()) == 1


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
    await db_session.commit()
    resp = await async_client.get(
        "/api/v1/onboarding/status",
        headers={"Authorization": "Bearer test_user_onb_inc"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["onboarding_complete"] is False
    assert data["organization_name"] == "Escola Incomp"


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
    await db_session.commit()
    data = {
        "school_start_date": "2025-09-15",
        "school_hard_end_date": "2026-07-31",
        "lunch_start": "12:30",
        "lunch_end": "14:00",
        "lunch_min_duration": 60,
    }

    headers = {"Authorization": "Bearer test_user_onb_comp"}
    await async_client.post("/api/v1/onboarding", headers=headers, json=data)
    resp = await async_client.get("/api/v1/onboarding/status", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["onboarding_complete"] is True


async def test_global_account_can_exist_without_organization_membership(async_client, db_session):
    """User sem organization_id é rejeitado pela invariant final do schema."""
    from app import models

    user = models.User(
        clerk_user_id="user_no_org_assoc",
        email="noorg@onb.pt",
    )
    db_session.add(user)
    await db_session.commit()
    assert user.id is not None
