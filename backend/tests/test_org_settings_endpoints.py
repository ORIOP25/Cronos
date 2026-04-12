import pytest


@pytest.mark.asyncio
async def test_upsert_settings_accepts_lunch_window(async_client, admin_token_headers):
    payload = {
        "academic_year": "2025/2026",
        "school_start_date": "2025-09-15",
        "school_target_end_date": "2026-06-15",
        "school_hard_end_date": "2026-07-31",
        "region_code": "Lisboa",
        "lunch_window_start": "12:00",
        "lunch_window_end": "14:00",
        "lunch_min_duration_minutes": 60,
        "repair_stability_window_days": 14,
    }

    response = await async_client.post(
        "/api/v1/school/settings/",
        json=payload,
        headers=admin_token_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["academic_year"] == "2025/2026"
    assert data["school_hard_end_date"] == "2026-07-31"
    assert data["lunch_window_start"].startswith("12:00")
    assert data["lunch_window_end"].startswith("14:00")
    assert data["lunch_min_duration_minutes"] == 60
    assert data["repair_stability_window_days"] == 14


@pytest.mark.asyncio
async def test_upsert_settings_rejects_invalid_lunch_window(async_client, admin_token_headers):
    payload = {
        "academic_year": "2025/2026",
        "school_start_date": "2025-09-15",
        "school_target_end_date": "2026-06-15",
        "lunch_window_start": "14:00",
        "lunch_window_end": "12:00",
        "lunch_min_duration_minutes": 30,
    }

    response = await async_client.post(
        "/api/v1/school/settings/",
        json=payload,
        headers=admin_token_headers,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_upsert_settings_rejects_hard_end_before_target(async_client, admin_token_headers):
    payload = {
        "academic_year": "2025/2026",
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
        "academic_year": "2025/2026",
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
