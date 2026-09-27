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
    assert data["automatic_holidays_enabled"] is False

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


async def test_upsert_settings_rejects_repair_window_above_sixty(
    async_client,
    clerk_admin_headers,
):
    response = await async_client.post(
        "/api/v1/school/settings/",
        json={"repair_stability_window_days": 61},
        headers=clerk_admin_headers,
    )

    assert response.status_code == 422


async def test_automatic_holidays_sync_is_bounded_and_can_be_disabled(
    async_client,
    clerk_admin_headers,
    monkeypatch,
):
    monkeypatch.setattr(
        settings_service,
        "_get_pt_holidays",
        lambda _years: {
            date(2025, 9, 15): "Dentro",
            date(2025, 9, 14): "Antes",
            date(2026, 7, 31): "Limite",
            date(2026, 8, 1): "Depois",
        },
    )
    payload = {
        "school_start_date": "2025-09-15",
        "school_hard_end_date": "2026-07-31",
        "automatic_holidays_enabled": True,
    }

    response = await async_client.post(
        "/api/v1/school/settings/",
        json=payload,
        headers=clerk_admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["automatic_holidays_enabled"] is True

    events_response = await async_client.get(
        "/api/v1/school/calendar-events/",
        headers=clerk_admin_headers,
    )
    assert [(event["start_date"], event["name"]) for event in events_response.json()] == [
        ("2025-09-15", "Dentro"),
        ("2026-07-31", "Limite"),
    ]

    response = await async_client.post(
        "/api/v1/school/settings/",
        json={"automatic_holidays_enabled": False},
        headers=clerk_admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["automatic_holidays_enabled"] is False

    preserved_response = await async_client.get(
        "/api/v1/school/calendar-events/",
        headers=clerk_admin_headers,
    )
    assert len(preserved_response.json()) == 2

    # With automatic holidays disabled, altering dates does not sync
    response = await async_client.post(
        "/api/v1/school/settings/",
        json={"school_hard_end_date": "2026-08-31"},
        headers=clerk_admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["school_hard_end_date"] == "2026-08-31"
    assert response.json()["automatic_holidays_enabled"] is False

    events_after_date_change = await async_client.get(
        "/api/v1/school/calendar-events/",
        headers=clerk_admin_headers,
    )
    assert [(event["start_date"], event["name"]) for event in events_after_date_change.json()] == [
        ("2025-09-15", "Dentro"),
        ("2026-07-31", "Limite"),
    ]


async def test_automatic_holidays_resyncs_only_after_period_change(
    async_client,
    clerk_admin_headers,
    monkeypatch,
):
    sync_years = []

    def fake_holidays(years):
        sync_years.append(tuple(years))
        return {
            date(2025, 9, 15): "Início",
            date(2026, 7, 31): "Período original",
            date(2026, 8, 31): "Período alargado",
        }

    monkeypatch.setattr(settings_service, "_get_pt_holidays", fake_holidays)
    base_payload = {
        "school_start_date": "2025-09-15",
        "school_hard_end_date": "2026-07-31",
        "automatic_holidays_enabled": True,
    }

    response = await async_client.post(
        "/api/v1/school/settings/", json=base_payload, headers=clerk_admin_headers
    )
    assert response.status_code == 200
    assert len(sync_years) == 1

    response = await async_client.post(
        "/api/v1/school/settings/",
        json={"repair_stability_window_days": 0, "automatic_holidays_enabled": True},
        headers=clerk_admin_headers,
    )
    assert response.status_code == 200
    assert len(sync_years) == 1

    response = await async_client.post(
        "/api/v1/school/settings/",
        json={"school_hard_end_date": "2026-08-31", "automatic_holidays_enabled": True},
        headers=clerk_admin_headers,
    )
    assert response.status_code == 200
    assert len(sync_years) == 2

    events_response = await async_client.get(
        "/api/v1/school/calendar-events/", headers=clerk_admin_headers
    )
    assert [(event["start_date"], event["name"]) for event in events_response.json()] == [
        ("2025-09-15", "Início"),
        ("2026-07-31", "Período original"),
        ("2026-08-31", "Período alargado"),
    ]


async def test_automatic_holidays_failure_rolls_back_settings_and_events(
    async_client,
    clerk_admin_headers,
    monkeypatch,
):
    def fail_sync(_years):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(settings_service, "_get_pt_holidays", fail_sync)
    response = await async_client.post(
        "/api/v1/school/settings/",
        json={
            "school_start_date": "2025-09-15",
            "school_hard_end_date": "2026-07-31",
            "automatic_holidays_enabled": True,
        },
        headers=clerk_admin_headers,
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "HOLIDAY_SYNC_FAILED"
    settings_response = await async_client.get(
        "/api/v1/school/settings/",
        headers=clerk_admin_headers,
    )
    assert settings_response.status_code == 404


async def test_automatic_holidays_failure_preserves_existing_settings_and_events(
    async_client,
    clerk_admin_headers,
    monkeypatch,
):
    monkeypatch.setattr(
        settings_service,
        "_get_pt_holidays",
        lambda _years: {
            date(2025, 9, 15): "Início original",
            date(2026, 7, 31): "Fim original",
        },
    )
    initial_response = await async_client.post(
        "/api/v1/school/settings/",
        json={
            "school_start_date": "2025-09-15",
            "school_hard_end_date": "2026-07-31",
            "automatic_holidays_enabled": True,
        },
        headers=clerk_admin_headers,
    )
    assert initial_response.status_code == 200

    def fail_sync(_years):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(settings_service, "_get_pt_holidays", fail_sync)
    failed_response = await async_client.post(
        "/api/v1/school/settings/",
        json={
            "school_hard_end_date": "2026-08-31",
            "automatic_holidays_enabled": True,
        },
        headers=clerk_admin_headers,
    )
    assert failed_response.status_code == 503
    assert failed_response.json()["detail"]["code"] == "HOLIDAY_SYNC_FAILED"

    settings_response = await async_client.get(
        "/api/v1/school/settings/", headers=clerk_admin_headers
    )
    assert settings_response.json()["school_hard_end_date"] == "2026-07-31"
    assert settings_response.json()["automatic_holidays_enabled"] is True
    events_response = await async_client.get(
        "/api/v1/school/calendar-events/", headers=clerk_admin_headers
    )
    assert [(event["start_date"], event["name"]) for event in events_response.json()] == [
        ("2025-09-15", "Início original"),
        ("2026-07-31", "Fim original"),
    ]

    # Recover with automatic holidays disabled: new dates saved, preference False, existing events preserved
    recovery_response = await async_client.post(
        "/api/v1/school/settings/",
        json={
            "school_hard_end_date": "2026-08-31",
            "automatic_holidays_enabled": False,
        },
        headers=clerk_admin_headers,
    )
    assert recovery_response.status_code == 200
    assert recovery_response.json()["school_hard_end_date"] == "2026-08-31"
    assert recovery_response.json()["automatic_holidays_enabled"] is False

    recovered_events = await async_client.get(
        "/api/v1/school/calendar-events/", headers=clerk_admin_headers
    )
    assert [(event["start_date"], event["name"]) for event in recovered_events.json()] == [
        ("2025-09-15", "Início original"),
        ("2026-07-31", "Fim original"),
    ]


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

    async def fake_get_preferred_end_date(*_args):
        return None

    monkeypatch.setattr(settings_service, "get_settings", fake_get_settings)
    monkeypatch.setattr(settings_service, "get_preferred_end_date", fake_get_preferred_end_date)

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
