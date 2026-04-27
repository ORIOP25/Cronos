import pytest


@pytest.mark.asyncio
async def test_upsert_settings_accepts_lunch_window(async_client, admin_token_headers):
    payload = {
        "school_start_date": "2025-09-15",
        "school_target_end_date": "2026-06-15",
        "school_hard_end_date": "2026-07-31",
        "repair_stability_window_days": 14,
    }

    response = await async_client.post(
        "/api/v1/school/settings/",
        json=payload,
        headers=admin_token_headers,
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
        headers=admin_token_headers,
    )

    assert grid_response.status_code == 200
    grid_data = grid_response.json()
    assert grid_data["lunch_window_start"].startswith("12:00")
    assert grid_data["lunch_window_end"].startswith("14:00")
    assert grid_data["lunch_min_duration_minutes"] == 60


@pytest.mark.asyncio
async def test_upsert_settings_rejects_invalid_lunch_window(async_client, admin_token_headers):
    payload = {
        "lunch_window_start": "14:00",
        "lunch_window_end": "12:00",
        "lunch_min_duration_minutes": 30,
    }

    response = await async_client.post(
        "/api/v1/school/grid-settings/",
        json=payload,
        headers=admin_token_headers,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_upsert_settings_rejects_hard_end_before_target(async_client, admin_token_headers):
    payload = {
        "school_start_date": "2025-09-15",
        "school_target_end_date": "2026-06-15",
        "school_hard_end_date": "2026-06-01",
    }

    response = await async_client.post(
        "/api/v1/school/settings/",
        json=payload,
        headers=admin_token_headers,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_upsert_settings_rejects_invalid_repair_window(async_client, admin_token_headers):
    payload = {
        "school_start_date": "2025-09-15",
        "school_target_end_date": "2026-06-15",
        "repair_stability_window_days": 0,
    }

    response = await async_client.post(
        "/api/v1/school/settings/",
        json=payload,
        headers=admin_token_headers,
    )

    assert response.status_code == 422
