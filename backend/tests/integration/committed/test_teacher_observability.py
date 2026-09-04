from datetime import UTC, datetime
from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy import select

from app import models
from app.config import settings
from app.services import teacher_observability_service
from tests._support.db_fixtures import (
    create_org_and_user,
    create_teacher_profile,
    create_teacher_user,
    ensure_membership_capabilities,
)
from tests.roles import UserRole

API = settings.API_V1_STR


async def _create_user_headers(
    db_session,
    *,
    organization_id: int,
    teacher_id: int | None,
    role: UserRole,
    is_active: bool = True,
) -> dict:
    clerk_id = f"user_{role.value}_{uuid4().hex[:8]}"
    if role == UserRole.teacher and teacher_id is not None:
        user = await create_teacher_user(
            db_session,
            clerk_user_id=clerk_id,
            email=f"obs.{role.value}.{uuid4().hex[:8]}@escola.pt",
            org_id=organization_id,
            teacher_id=teacher_id,
        )
    else:
        user = models.User(
            clerk_user_id=clerk_id,
            email=f"obs.{role.value}.{uuid4().hex[:8]}@escola.pt",
        )
        db_session.add(user)
        await db_session.flush()
        capabilities = (
            [models.MembershipCapability.teacher]
            if role == UserRole.teacher
            else [models.MembershipCapability.admin]
        )
        await ensure_membership_capabilities(
            db_session,
            organization_id=organization_id,
            user=user,
            capabilities=capabilities,
            expected_clerk_role=models.ClerkOrganizationRole.member,
            teacher_access_mode=(
                models.TeacherAccessMode.platform if role == UserRole.teacher else None
            ),
        )
    if not is_active:
        membership = await db_session.scalar(
            select(models.OrganizationMembership).where(
                models.OrganizationMembership.organization_id == organization_id,
                models.OrganizationMembership.account_id == user.id,
            )
        )
        membership.access_status = models.MembershipAccessStatus.none
    await db_session.commit()
    return {"Authorization": f"Bearer test_{clerk_id}"}


async def test_teacher_self_availability_logs_observability_event(
    async_client: AsyncClient,
    db_session,
):
    org, _ = await create_org_and_user(db_session, clerk_user_id="user_admin_001", role="admin")
    teacher = await create_teacher_profile(db_session, organization_id=org.id, name="Prof. Obs")
    await db_session.commit()
    teacher_id = teacher.id

    teacher_headers = await _create_user_headers(
        db_session,
        organization_id=org.id,
        teacher_id=teacher_id,
        role=UserRole.teacher,
    )
    response = await async_client.get(
        f"{API}/teachers/me/availability",
        headers=teacher_headers,
    )
    assert response.status_code == 200

    rows = (
        (
            await db_session.execute(
                select(models.TeacherEndpointOperationalEvent).where(
                    models.TeacherEndpointOperationalEvent.endpoint_key
                    == teacher_observability_service.ENDPOINT_TEACHERS_ME_AVAILABILITY_READ
                )
            )
        )
        .scalars()
        .all()
    )

    assert len(rows) >= 1
    assert rows[-1].http_status == 200
    assert rows[-1].latency_ms > 0


async def test_teacher_observability_summary_is_admin_only(
    async_client: AsyncClient,
    db_session,
):
    org, _ = await create_org_and_user(db_session, clerk_user_id="user_admin_001", role="admin")
    teacher = await create_teacher_profile(
        db_session, organization_id=org.id, name="Prof. Restrito"
    )
    await db_session.commit()

    teacher_headers = await _create_user_headers(
        db_session,
        organization_id=org.id,
        teacher_id=teacher.id,
        role=UserRole.teacher,
    )
    response = await async_client.get(
        f"{API}/teachers/observability/summary",
        headers=teacher_headers,
    )
    assert response.status_code == 403


async def test_teacher_observability_summary_detects_403_alert_and_recovery(
    async_client: AsyncClient,
    db_session,
):
    org, _ = await create_org_and_user(db_session, clerk_user_id="user_admin_001", role="admin")
    now = datetime.now(UTC)

    failure_events = [
        models.TeacherEndpointOperationalEvent(
            organization_id=1,
            actor_membership_id=None,
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
        headers={"Authorization": "Bearer test_user_admin_001"},
        params={"window_minutes": 15},
    )
    assert summary_failure.status_code == 200

    alerts_failure = summary_failure.json()["alerts"]
    assert any(
        alert["endpoint_key"]
        == teacher_observability_service.ENDPOINT_TEACHERS_ME_AVAILABILITY_READ
        and alert["alert_code"] == "ABNORMAL_403_RATE"
        for alert in alerts_failure
    )

    recovery_events = [
        models.TeacherEndpointOperationalEvent(
            organization_id=1,
            actor_membership_id=None,
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
        headers={"Authorization": "Bearer test_user_admin_001"},
        params={"window_minutes": 15},
    )
    assert summary_recovered.status_code == 200

    alerts_recovered = summary_recovered.json()["alerts"]
    assert not any(
        alert["endpoint_key"]
        == teacher_observability_service.ENDPOINT_TEACHERS_ME_AVAILABILITY_READ
        and alert["alert_code"] == "ABNORMAL_403_RATE"
        for alert in alerts_recovered
    )


async def test_teacher_observability_summary_detects_high_5xx_rate(
    async_client: AsyncClient,
    db_session,
):
    org, _ = await create_org_and_user(db_session, clerk_user_id="user_admin_001", role="admin")
    now = datetime.now(UTC)

    db_session.add(
        models.TeacherEndpointOperationalEvent(
            organization_id=1,
            actor_membership_id=None,
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
            actor_membership_id=None,
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
        headers={"Authorization": "Bearer test_user_admin_001"},
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
