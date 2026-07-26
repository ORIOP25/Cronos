from datetime import time

import pytest
from httpx import AsyncClient

from app import models
from app.config import settings
from tests.conftest import create_teacher_profile

API = settings.API_V1_STR


async def test_heatmap_empty_for_authenticated_tenant(
    async_client: AsyncClient,
    clerk_admin_headers: dict,
):
    response = await async_client.get(
        f"{API}/analytics/availability-heatmap",
        headers=clerk_admin_headers,
    )
    assert response.status_code == 200
    assert response.json() == []


async def test_heatmap_requires_authentication(async_client: AsyncClient):
    response = await async_client.get(f"{API}/analytics/availability-heatmap")
    assert response.status_code == 401


async def test_heatmap_returns_canonical_availability(
    async_client: AsyncClient,
    clerk_admin_headers: dict,
    db_session,
):
    teacher = await create_teacher_profile(
        db_session,
        organization_id=1,
        name="Prof. Heatmap",
    )
    timeslot = models.Timeslot(
        day_of_week=0,
        start_time=time(8),
        end_time=time(9),
        organization_id=1,
    )
    db_session.add(timeslot)
    await db_session.flush()
    db_session.add(
        models.Availability(
            organization_id=1,
            teacher_id=teacher.id,
            timeslot_id=timeslot.id,
            score=models.PreferenceLevel.PREFERRED.value,
        )
    )
    await db_session.commit()

    response = await async_client.get(
        f"{API}/analytics/availability-heatmap",
        headers=clerk_admin_headers,
    )
    assert response.status_code == 200
    assert len(response.json()) == 1


@pytest.mark.parametrize(
    "path",
    [
        "/import/timeslots",
        "/import/teachers",
        "/import/rooms",
        "/lessons/",
    ],
)
async def test_legacy_read_aliases_are_removed(async_client: AsyncClient, path: str):
    response = await async_client.get(f"{API}{path}")
    assert response.status_code == 404
