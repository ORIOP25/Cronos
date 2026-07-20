from datetime import date, time
from types import SimpleNamespace

import pytest

from app import schemas
from app.services import settings_service


class _NoopDb:
    async def commit(self):
        return None

    async def refresh(self, _obj):
        return None


async def test_upsert_settings_accepts_lunch_window(async_client, clerk_admin_headers):
    payload = {
        "school_start_date": "2025-09-15",
        "school_hard_end_date": "2026-07-31",
        "repair_stability_window_days": 14,
    }

    response = await async_client.post(
        "/api/v1/school/settings/",
        json=payload,
        headers=clerk_admin_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["school_hard_end_date"] == "2026-07-31"
    assert data["repair_stability_window_days"] == 14

    grid_payload = {
        "lunch_window_start": "12:00",
        "lunch_window_end": "14:00",
        "lunch_min_duration_minutes": 60,
    }

    grid_response = await async_client.post(
        "/api/v1/school/grid-settings/",
        json=grid_payload,
        headers=clerk_admin_headers,
    )

    assert grid_response.status_code == 200
    grid_data = grid_response.json()
    assert grid_data["lunch_window_start"].startswith("12:00")
    assert grid_data["lunch_window_end"].startswith("14:00")
    assert grid_data["lunch_min_duration_minutes"] == 60


async def test_upsert_settings_rejects_invalid_lunch_window(async_client, clerk_admin_headers):
    payload = {
        "lunch_window_start": "14:00",
        "lunch_window_end": "12:00",
        "lunch_min_duration_minutes": 30,
    }

    response = await async_client.post(
        "/api/v1/school/grid-settings/",
        json=payload,
        headers=clerk_admin_headers,
    )

    assert response.status_code == 422


async def test_upsert_settings_rejects_hard_end_before_start(async_client, clerk_admin_headers):
    payload = {
        "school_start_date": "2025-09-15",
        "school_hard_end_date": "2025-09-01",
    }

    response = await async_client.post(
        "/api/v1/school/settings/",
        json=payload,
        headers=clerk_admin_headers,
    )

    assert response.status_code == 422


async def test_upsert_settings_accepts_zero_repair_window(async_client, clerk_admin_headers):
    payload = {
        "school_start_date": "2025-09-15",
        "school_hard_end_date": "2026-07-31",
        "repair_stability_window_days": 0,
    }

    response = await async_client.post(
        "/api/v1/school/settings/",
        json=payload,
        headers=clerk_admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["repair_stability_window_days"] == 0


async def test_upsert_settings_rejects_partial_update_that_breaks_existing_dates(
    async_client,
    clerk_admin_headers,
):
    valid_payload = {
        "school_start_date": "2025-09-15",
        "school_hard_end_date": "2026-07-31",
    }
    create_response = await async_client.post(
        "/api/v1/school/settings/",
        json=valid_payload,
        headers=clerk_admin_headers,
    )
    assert create_response.status_code == 200

    response = await async_client.post(
        "/api/v1/school/settings/",
        json={"school_hard_end_date": "2025-09-01"},
        headers=clerk_admin_headers,
    )

    assert response.status_code == 422


async def test_upsert_grid_settings_rejects_partial_update_that_breaks_existing_window(
    async_client,
    clerk_admin_headers,
):
    valid_payload = {
        "lunch_window_start": "12:00",
        "lunch_window_end": "14:00",
        "lunch_min_duration_minutes": 60,
    }
    create_response = await async_client.post(
        "/api/v1/school/grid-settings/",
        json=valid_payload,
        headers=clerk_admin_headers,
    )
    assert create_response.status_code == 200

    response = await async_client.post(
        "/api/v1/school/grid-settings/",
        json={"lunch_window_end": "11:30"},
        headers=clerk_admin_headers,
    )

    assert response.status_code == 422


async def test_settings_service_validates_combined_partial_date_update(monkeypatch):
    existing = SimpleNamespace(
        school_start_date=date(2025, 9, 15),
        school_hard_end_date=date(2026, 7, 31),
        repair_stability_window_days=14,
    )

    async def fake_get_settings(*_args):
        return existing

    monkeypatch.setattr(settings_service, "get_settings", fake_get_settings)

    with pytest.raises(ValueError):
        await settings_service.upsert_settings(
            _NoopDb(),
            1,
            schemas.OrganizationSettingsUpsert(school_hard_end_date=date(2025, 9, 1)),
        )

    assert existing.school_hard_end_date == date(2026, 7, 31)


async def test_grid_settings_service_validates_combined_partial_lunch_update(monkeypatch):
    existing = SimpleNamespace(
        lunch_window_start=time(12, 0),
        lunch_window_end=time(14, 0),
        lunch_min_duration_minutes=60,
    )

    async def fake_get_grid_settings(*_args):
        return existing

    monkeypatch.setattr(settings_service, "get_grid_settings", fake_get_grid_settings)

    with pytest.raises(ValueError):
        await settings_service.upsert_grid_settings(
            _NoopDb(),
            1,
            schemas.OrganizationGridSettingsUpsert(lunch_window_end=time(11, 30)),
        )

    assert existing.lunch_window_end == time(14, 0)
