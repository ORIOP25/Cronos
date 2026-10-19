from datetime import UTC, date, datetime

from sqlalchemy import select

from app import models
from app.scheduler.domain.priorities import DEFAULT_LEVELS
from app.scheduler.infrastructure.models import SchedulerJobV1, SchedulerProposalV1
from tests._support.db_fixtures import create_org_and_user

ENDPOINT = "/api/v1/school/settings/schedule-priorities"


def _changed_levels() -> dict[str, int]:
    levels = dict(DEFAULT_LEVELS)
    levels["class_gaps"] = 3
    return levels


async def test_schedule_priorities_are_admin_only_tenant_scoped_and_strict(
    async_client, db_session, clerk_admin_headers, clerk_teacher_headers
):
    org_a = await db_session.scalar(
        select(models.Organization).where(models.Organization.clerk_org_id == "org_test_001")
    )
    settings = models.OrganizationSettings(organization_id=org_a.id)
    db_session.add(settings)
    await db_session.commit()

    defaults = {"levels": dict(DEFAULT_LEVELS), "defaults": dict(DEFAULT_LEVELS)}
    response = await async_client.get(ENDPOINT, headers=clerk_admin_headers)
    assert response.status_code == 200
    assert response.json() == defaults

    levels = _changed_levels()
    saved = await async_client.put(ENDPOINT, json={"levels": levels}, headers=clerk_admin_headers)
    assert saved.status_code == 200
    assert saved.json() == {"levels": levels, "defaults": dict(DEFAULT_LEVELS)}

    malformed = [
        {"levels": {**levels, "class_gaps": 5}},
        {"levels": {key: value for key, value in levels.items() if key != "class_gaps"}},
        {"levels": {**levels, "unexpected": 1}},
        {"levels": {**levels, "class_gaps": True}},
        {"levels": {**levels, "class_gaps": 2.5}},
    ]
    for payload in malformed:
        invalid = await async_client.put(ENDPOINT, json=payload, headers=clerk_admin_headers)
        assert invalid.status_code == 422
        assert invalid.json()["detail"]["code"] == "schedule_priorities_invalid"
        assert invalid.json()["detail"]["message"] == "Escolha um nível de 0 a 4 em cada critério."

    teacher = await async_client.get(ENDPOINT, headers=clerk_teacher_headers)
    assert teacher.status_code == 403
    teacher_write = await async_client.put(
        ENDPOINT, json={"levels": levels}, headers=clerk_teacher_headers
    )
    assert teacher_write.status_code == 403

    org_b, _ = await create_org_and_user(
        db_session,
        clerk_user_id="priority_org_b_admin",
        email="priority-org-b@test.com",
        clerk_org_id="org_priority_b",
    )
    db_session.add(models.OrganizationSettings(organization_id=org_b.id))
    await db_session.commit()
    org_b_response = await async_client.get(
        ENDPOINT,
        headers={"Authorization": "Bearer test_priority_org_b_admin"},
    )
    assert org_b_response.status_code == 200
    assert org_b_response.json() == defaults


async def test_schedule_priorities_missing_settings_returns_not_found(
    async_client, clerk_admin_headers
):
    response = await async_client.get(ENDPOINT, headers=clerk_admin_headers)

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "settings_not_found"
    assert response.json()["detail"]["message"] == "Configurações da escola não encontradas"


async def test_schedule_priorities_change_stales_pending_proposal_and_identical_save_is_noop(
    async_client, db_session, clerk_admin_headers
):
    organization = await db_session.scalar(
        select(models.Organization).where(models.Organization.clerk_org_id == "org_test_001")
    )
    settings = models.OrganizationSettings(organization_id=organization.id)
    year = models.SchedulerSchoolYear(
        organization_id=organization.id,
        label="2025/2026",
        start_date=date(2025, 9, 1),
        hard_end_date=date(2026, 7, 15),
        timezone="Europe/Lisbon",
        is_active=True,
    )
    db_session.add_all([settings, year])
    await db_session.flush()
    state = models.SchedulerSchoolYearState(organization_id=organization.id, school_year_id=year.id)
    db_session.add(state)
    await db_session.flush()
    job = SchedulerJobV1(
        organization_id=organization.id,
        school_year_id=year.id,
        strategy="COMPLETE_GENERATION",
        status="SUCCEEDED",
        origin="schedule-priority-test",
        revision=1,
        queued_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        input_revision_used=0,
        planning_revision_used=0,
        snapshot_digest="a" * 64,
    )
    db_session.add(job)
    await db_session.flush()
    db_session.add(
        SchedulerProposalV1(
            organization_id=organization.id,
            school_year_id=year.id,
            job_id=job.id,
            status="PENDING",
            snapshot_digest="a" * 64,
            policy_version="baseline-v1",
            input_revision_used=0,
            planning_revision_used=0,
            created_at=datetime.now(UTC),
        )
    )
    await db_session.commit()

    levels = _changed_levels()
    changed = await async_client.put(ENDPOINT, json={"levels": levels}, headers=clerk_admin_headers)
    assert changed.status_code == 200
    await db_session.refresh(state)
    assert state.input_revision == 1
    status = await async_client.get("/api/v1/scheduler/status", headers=clerk_admin_headers)
    assert status.status_code == 200
    assert status.json()["pending_proposal"]["is_stale"] is True

    unchanged = await async_client.put(
        ENDPOINT, json={"levels": levels}, headers=clerk_admin_headers
    )
    assert unchanged.status_code == 200
    await db_session.refresh(state)
    assert state.input_revision == 1
    event = await db_session.scalar(
        select(models.SchedulerStateVersionEvent)
        .where(
            models.SchedulerStateVersionEvent.organization_id == organization.id,
            models.SchedulerStateVersionEvent.entity_type == "SCHEDULE_PRIORITIES",
        )
        .order_by(models.SchedulerStateVersionEvent.id.desc())
    )
    assert event.change_scope == models.SchedulerStateChangeScope.NO_OP


async def test_schedule_priorities_survive_school_year_soft_reset(
    async_client, db_session, clerk_admin_headers
):
    organization = await db_session.scalar(
        select(models.Organization).where(models.Organization.clerk_org_id == "org_test_001")
    )
    db_session.add(models.OrganizationSettings(organization_id=organization.id))
    await db_session.commit()
    levels = _changed_levels()
    saved = await async_client.put(ENDPOINT, json={"levels": levels}, headers=clerk_admin_headers)
    assert saved.status_code == 200

    reset = await async_client.post(
        "/api/v1/school/settings/soft-reset",
        json={"confirm_phrase": "Confirmo"},
        headers=clerk_admin_headers,
    )
    assert reset.status_code == 200
    after_reset = await async_client.get(ENDPOINT, headers=clerk_admin_headers)
    assert after_reset.status_code == 200
    assert after_reset.json()["levels"] == levels
