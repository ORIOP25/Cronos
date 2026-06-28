from datetime import date, datetime, timezone

import pytest

from app import models
from app.services.scheduler_status_service import (
    NO_TRIGGER_MESSAGE,
    SchedulerStatusService,
)


pytestmark = pytest.mark.integration


async def _status_context(db_session):
    organization = models.Organization(name="Status School", plan_status="active")
    db_session.add(organization)
    await db_session.flush()
    user = models.User(
        organization_id=organization.id,
        email="status-admin@example.com",
        role=models.UserRole.admin,
        is_active=True,
        is_superuser=False,
    )
    school_year = models.SchedulerSchoolYear(
        organization_id=organization.id,
        label="2025/2026",
        start_date=date(2025, 9, 1),
        hard_end_date=date(2026, 7, 15),
        timezone="Europe/Lisbon",
    )
    db_session.add_all([user, school_year])
    await db_session.flush()
    state = models.SchedulerSchoolYearState(
        organization_id=organization.id,
        school_year_id=school_year.id,
    )
    db_session.add(state)
    await db_session.commit()
    return organization, user, school_year, state


@pytest.mark.asyncio
async def test_status_exposes_first_generation_as_primary_action(db_session):
    organization, _user, school_year, _state = await _status_context(db_session)

    status = await SchedulerStatusService(db_session).get_status(organization.id)

    assert status.school_year_id == school_year.id
    assert status.school_year_publication_state == "UNPUBLISHED"
    assert status.primary_action == "GENERATE_SCHEDULE"
    assert status.can_generate_new_draft is True
    assert status.can_regenerate_with_confirmation is False
    assert status.trigger_type == "FIRST_GENERATION"


@pytest.mark.asyncio
async def test_pending_draft_review_outranks_regeneration(db_session):
    organization, user, school_year, state = await _status_context(db_session)
    now = datetime.now(timezone.utc)
    job = models.ScheduleGenerationJob(
        organization_id=organization.id,
        school_year_id=school_year.id,
        requested_by_user_id=user.id,
        strategy=models.ScheduleGenerationStrategy.COMPLETE_GENERATION,
        trigger_type=models.ScheduleGenerationTrigger.FIRST_GENERATION,
        job_status=models.ScheduleGenerationJobStatus.SUCCEEDED,
        result_category=models.ScheduleGenerationResultCategory.COMPLETE_SUCCESS,
        queued_at=now,
        started_at=now,
        finished_at=now,
    )
    db_session.add(job)
    await db_session.flush()
    draft = models.ScheduleDraft(
        organization_id=organization.id,
        school_year_id=school_year.id,
        generation_job_id=job.id,
        strategy=models.ScheduleGenerationStrategy.COMPLETE_GENERATION,
        result_category=models.ScheduleGenerationResultCategory.COMPLETE_SUCCESS,
        trigger_type=models.ScheduleGenerationTrigger.FIRST_GENERATION,
        generation_input_fingerprint="a" * 64,
        scheduler_state_version_used=0,
        projected_completion_date=date(2026, 6, 30),
        hard_end_date=school_year.hard_end_date,
        summary_json={},
        created_by_user_id=user.id,
    )
    db_session.add(draft)
    await db_session.flush()
    state.pending_draft_id = draft.id
    await db_session.commit()

    status = await SchedulerStatusService(db_session).get_status(organization.id)

    assert status.pending_draft_id == draft.id
    assert status.primary_action == "REVIEW_PENDING_DRAFT"
    assert status.can_generate_new_draft is False
    assert status.can_regenerate_with_confirmation is True


@pytest.mark.asyncio
async def test_published_status_distinguishes_no_trigger_and_scheduler_change(db_session):
    organization, _user, _school_year, state = await _status_context(db_session)
    state.school_year_publication_state = models.SchoolYearPublicationState.PUBLISHED
    state.active_schedule_version_id = "v1"
    state.scheduler_state_version = 4
    state.approved_scheduler_state_version = 4
    await db_session.commit()

    blocked = await SchedulerStatusService(db_session).get_status(organization.id)
    assert blocked.primary_action == "GENERATION_UNAVAILABLE"
    assert blocked.blocked_reason == NO_TRIGGER_MESSAGE
    assert blocked.can_generate_new_draft is False

    state.scheduler_state_version = 5
    await db_session.commit()
    changed = await SchedulerStatusService(db_session).get_status(organization.id)
    assert changed.primary_action == "GENERATE_SCHEDULE"
    assert changed.trigger_type == "SCHEDULER_CHANGE"
    assert changed.can_generate_new_draft is True


@pytest.mark.asyncio
async def test_status_endpoint_returns_unconfigured_state(
    async_client,
    clerk_admin_headers,
):
    response = await async_client.get(
        "/api/v1/scheduler/status",
        headers=clerk_admin_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["primary_action"] == "GENERATION_UNAVAILABLE"
    assert payload["can_generate_new_draft"] is False
    assert payload["blocked_reason"] == "The scheduler school year is not configured."

    draft_response = await async_client.get(
        "/api/v1/scheduler/drafts/current",
        headers=clerk_admin_headers,
    )
    assert draft_response.status_code == 404
