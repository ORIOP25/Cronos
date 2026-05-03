from datetime import datetime, timezone
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app import models
from app.config import settings
from app.core.security import create_access_token, hash_password
from app.models import UserRole
from app.services import teacher_observability_service

API = settings.API_V1_STR


async def _create_user_headers(
    db_session,
    *,
    organization_id: int,
    teacher_id: int | None,
    role: UserRole,
    is_active: bool = True,
) -> dict:
    email = f"obs.{role.value}.{uuid4().hex[:8]}@escola.pt"
    user = models.User(
        email=email,
        hashed_password=hash_password("pass123"),
        is_active=is_active,
        role=role,
        organization_id=organization_id,
        teacher_id=teacher_id,
    )
    db_session.add(user)
    await db_session.commit()

    token = create_access_token(data={"sub": email})
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_teacher_self_availability_logs_observability_event(
    async_client: AsyncClient,
    admin_token_headers: dict,
    db_session,
):
    teacher_resp = await async_client.post(
        f"{API}/teachers/",
        json={"name": "Prof. Obs", "email": f"obs.{uuid4().hex[:8]}@escola.pt"},
        headers=admin_token_headers,
    )
    assert teacher_resp.status_code == 200
    teacher_id = teacher_resp.json()["id"]

    teacher_headers = await _create_user_headers(
        db_session,
        organization_id=1,
        teacher_id=teacher_id,
        role=UserRole.teacher,
    )

    response = await async_client.get(
        f"{API}/teachers/me/availability",
        headers=teacher_headers,
    )
    assert response.status_code == 200

    rows = (
        await db_session.execute(
            select(models.TeacherEndpointOperationalEvent).where(
                models.TeacherEndpointOperationalEvent.endpoint_key
                == teacher_observability_service.ENDPOINT_TEACHERS_ME_AVAILABILITY_READ
            )
        )
    ).scalars().all()

    assert len(rows) >= 1
    assert rows[-1].http_status == 200
    assert rows[-1].latency_ms > 0


@pytest.mark.asyncio
async def test_teacher_observability_summary_is_admin_only(
    async_client: AsyncClient,
    admin_token_headers: dict,
    db_session,
):
    teacher_resp = await async_client.post(
        f"{API}/teachers/",
        json={"name": "Prof. Restrito", "email": f"restricted.{uuid4().hex[:8]}@escola.pt"},
        headers=admin_token_headers,
    )
    assert teacher_resp.status_code == 200

    teacher_headers = await _create_user_headers(
        db_session,
        organization_id=1,
        teacher_id=teacher_resp.json()["id"],
        role=UserRole.teacher,
    )

    response = await async_client.get(
        f"{API}/teachers/observability/summary",
        headers=teacher_headers,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_teacher_observability_summary_detects_403_alert_and_recovery(
    async_client: AsyncClient,
    admin_token_headers: dict,
    db_session,
):
    now = datetime.now(timezone.utc)

    failure_events = [
        models.TeacherEndpointOperationalEvent(
            organization_id=1,
            actor_user_id=None,
            actor_role=UserRole.admin.value,
            endpoint_key=teacher_observability_service.ENDPOINT_TEACHERS_ME_AVAILABILITY_READ,
            http_status=403,
            latency_ms=20,
            active_generation_id=None,
            created_at=now,
        )
        for _ in range(12)
    ]
    db_session.add_all(failure_events)
    await db_session.commit()

    summary_failure = await async_client.get(
        f"{API}/teachers/observability/summary",
        headers=admin_token_headers,
        params={"window_minutes": 15},
    )
    assert summary_failure.status_code == 200

    alerts_failure = summary_failure.json()["alerts"]
    assert any(
        alert["endpoint_key"] == teacher_observability_service.ENDPOINT_TEACHERS_ME_AVAILABILITY_READ
        and alert["alert_code"] == "ABNORMAL_403_RATE"
        for alert in alerts_failure
    )

    recovery_events = [
        models.TeacherEndpointOperationalEvent(
            organization_id=1,
            actor_user_id=None,
            actor_role=UserRole.teacher.value,
            endpoint_key=teacher_observability_service.ENDPOINT_TEACHERS_ME_AVAILABILITY_READ,
            http_status=200,
            latency_ms=18,
            active_generation_id=None,
            created_at=now,
        )
        for _ in range(60)
    ]
    db_session.add_all(recovery_events)
    await db_session.commit()

    summary_recovered = await async_client.get(
        f"{API}/teachers/observability/summary",
        headers=admin_token_headers,
        params={"window_minutes": 15},
    )
    assert summary_recovered.status_code == 200

    alerts_recovered = summary_recovered.json()["alerts"]
    assert not any(
        alert["endpoint_key"] == teacher_observability_service.ENDPOINT_TEACHERS_ME_AVAILABILITY_READ
        and alert["alert_code"] == "ABNORMAL_403_RATE"
        for alert in alerts_recovered
    )


@pytest.mark.asyncio
async def test_teacher_observability_summary_detects_high_5xx_rate(
    async_client: AsyncClient,
    admin_token_headers: dict,
    db_session,
):
    now = datetime.now(timezone.utc)

    db_session.add(
        models.TeacherEndpointOperationalEvent(
            organization_id=1,
            actor_user_id=None,
            actor_role=UserRole.teacher.value,
            endpoint_key=teacher_observability_service.ENDPOINT_SCHEDULE_ME_HORIZON_READ,
            http_status=500,
            latency_ms=250,
            active_generation_id="gen-5xx",
            created_at=now,
        )
    )

    success_events = [
        models.TeacherEndpointOperationalEvent(
            organization_id=1,
            actor_user_id=None,
            actor_role=UserRole.teacher.value,
            endpoint_key=teacher_observability_service.ENDPOINT_SCHEDULE_ME_HORIZON_READ,
            http_status=200,
            latency_ms=35,
            active_generation_id="gen-5xx",
            created_at=now,
        )
        for _ in range(29)
    ]
    db_session.add_all(success_events)
    await db_session.commit()

    response = await async_client.get(
        f"{API}/teachers/observability/summary",
        headers=admin_token_headers,
        params={"window_minutes": 15},
    )
    assert response.status_code == 200

    payload = response.json()
    assert any(
        alert["endpoint_key"] == teacher_observability_service.ENDPOINT_SCHEDULE_ME_HORIZON_READ
        and alert["alert_code"] == "HIGH_5XX_RATE"
        for alert in payload["alerts"]
    )

    endpoint_rows = [
        row
        for row in payload["endpoints"]
        if row["endpoint_key"] == teacher_observability_service.ENDPOINT_SCHEDULE_ME_HORIZON_READ
    ]
    assert len(endpoint_rows) == 1
    assert endpoint_rows[0]["p95_latency_ms"] >= 35
