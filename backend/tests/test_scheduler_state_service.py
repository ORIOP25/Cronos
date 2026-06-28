from datetime import date

import pytest

from app import models
from sqlalchemy import select
from app.services.scheduler_state_service import (
    InvalidSchedulerStateTransitionError,
    PendingDraftConflictError,
    SchedulerStateIntegrityError,
    SchedulerStateService,
)


pytestmark = pytest.mark.integration


async def _create_org_and_user(db_session):
    organization = models.Organization(name="State Service School", plan_status="active")
    db_session.add(organization)
    await db_session.flush()
    user = models.User(
        organization_id=organization.id,
        email=f"state-service-{organization.id}@example.com",
        role=models.UserRole.admin,
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.flush()
    return organization, user


async def _create_pending_draft(db_session, organization, school_year, user, state):
    job = models.ScheduleGenerationJob(
        organization_id=organization.id,
        school_year_id=school_year.id,
        requested_by_user_id=user.id,
        strategy=models.ScheduleGenerationStrategy.COMPLETE_GENERATION,
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
        scheduler_state_version_used=state.scheduler_state_version,
        projected_completion_date=date(2026, 6, 30),
        hard_end_date=school_year.hard_end_date,
        summary_json={},
        created_by_user_id=user.id,
    )
    db_session.add(draft)
    await db_session.flush()
    return draft


@pytest.mark.asyncio
async def test_get_or_create_active_state_is_idempotent(db_session):
    organization, _ = await _create_org_and_user(db_session)
    service = SchedulerStateService(db_session)

    first_year, first_state = await service.get_or_create_active_state(
        organization.id,
        start_date=date(2025, 9, 1),
        hard_end_date=date(2026, 7, 15),
    )
    second_year, second_state = await service.get_or_create_active_state(
        organization.id,
        start_date=date(2025, 9, 1),
        hard_end_date=date(2026, 7, 15),
    )

    assert second_year.id == first_year.id
    assert second_state.id == first_state.id
    assert first_state.school_year_publication_state == (
        models.SchoolYearPublicationState.UNPUBLISHED
    )


@pytest.mark.asyncio
async def test_pending_lookup_requires_pointer_consistency(db_session):
    organization, user = await _create_org_and_user(db_session)
    service = SchedulerStateService(db_session)
    school_year, state = await service.get_or_create_active_state(
        organization.id,
        start_date=date(2025, 9, 1),
        hard_end_date=date(2026, 7, 15),
    )
    draft = await _create_pending_draft(
        db_session, organization, school_year, user, state
    )

    with pytest.raises(SchedulerStateIntegrityError):
        await service.get_pending_draft(organization.id, school_year.id)

    await service.set_pending_draft(organization.id, school_year.id, draft.id)
    pending = await service.get_pending_draft(organization.id, school_year.id)
    assert pending is not None
    assert pending.id == draft.id


@pytest.mark.asyncio
async def test_publish_and_reset_transitions_are_centralized(db_session):
    organization, user = await _create_org_and_user(db_session)
    service = SchedulerStateService(db_session)
    school_year, state = await service.get_or_create_active_state(
        organization.id,
        start_date=date(2025, 9, 1),
        hard_end_date=date(2026, 7, 15),
    )
    draft = await _create_pending_draft(
        db_session, organization, school_year, user, state
    )
    await service.set_pending_draft(organization.id, school_year.id, draft.id)

    published = await service.mark_published(
        organization.id,
        school_year.id,
        active_schedule_version_id="version-1",
        approved_scheduler_state_version=state.scheduler_state_version,
        approved_draft_id=draft.id,
    )
    assert published.school_year_publication_state == (
        models.SchoolYearPublicationState.PUBLISHED
    )
    assert published.pending_draft_id is None

    reset = await service.reset_year(
        organization.id,
        school_year.id,
        reset_by_user_id=user.id,
    )
    assert reset.school_year_publication_state == (
        models.SchoolYearPublicationState.UNPUBLISHED
    )
    assert reset.active_schedule_version_id is None
    assert reset.approved_scheduler_state_version is None
    assert reset.reset_at is not None


@pytest.mark.asyncio
async def test_clear_pending_draft_uses_expected_identity(db_session):
    organization, user = await _create_org_and_user(db_session)
    service = SchedulerStateService(db_session)
    school_year, state = await service.get_or_create_active_state(
        organization.id,
        start_date=date(2025, 9, 1),
        hard_end_date=date(2026, 7, 15),
    )
    draft = await _create_pending_draft(
        db_session, organization, school_year, user, state
    )
    await service.set_pending_draft(organization.id, school_year.id, draft.id)

    with pytest.raises(PendingDraftConflictError):
        await service.clear_pending_draft(
            organization.id,
            school_year.id,
            expected_draft_id=draft.id + 1,
        )


@pytest.mark.asyncio
async def test_publish_rejects_a_stale_scheduler_state_version(db_session):
    organization, user = await _create_org_and_user(db_session)
    service = SchedulerStateService(db_session)
    school_year, state = await service.get_or_create_active_state(
        organization.id,
        start_date=date(2025, 9, 1),
        hard_end_date=date(2026, 7, 15),
    )
    draft = await _create_pending_draft(
        db_session, organization, school_year, user, state
    )
    await service.set_pending_draft(organization.id, school_year.id, draft.id)

    with pytest.raises(InvalidSchedulerStateTransitionError):
        await service.mark_published(
            organization.id,
            school_year.id,
            active_schedule_version_id="version-1",
            approved_scheduler_state_version=state.scheduler_state_version + 1,
            approved_draft_id=draft.id,
        )


@pytest.mark.asyncio
async def test_active_school_year_rejects_invalid_timezone(db_session):
    organization, _ = await _create_org_and_user(db_session)
    service = SchedulerStateService(db_session)

    with pytest.raises(SchedulerStateIntegrityError):
        await service.get_or_create_active_school_year(
            organization.id,
            start_date=date(2025, 9, 1),
            hard_end_date=date(2026, 7, 15),
            timezone_name="not/a-timezone",
        )


@pytest.mark.asyncio
async def test_relevant_change_increments_once_and_records_event(db_session):
    organization, user = await _create_org_and_user(db_session)
    service = SchedulerStateService(db_session)
    school_year, state = await service.get_or_create_active_state(
        organization.id,
        start_date=date(2025, 9, 1),
        hard_end_date=date(2026, 7, 15),
    )

    event = await service.record_change(
        organization.id,
        entity_type="ROOM",
        entity_id=12,
        operation=models.SchedulerStateChangeOperation.UPDATE,
        before={"capacity": 20, "type": models.RoomType.normal},
        after={"type": models.RoomType.lab, "capacity": 20},
        changed_by_user_id=user.id,
    )

    assert event is not None
    assert event.change_scope == models.SchedulerStateChangeScope.FUTURE_IMPACTING
    assert event.version_before == 0
    assert event.version_after == 1
    assert state.scheduler_state_version == 1
    stored = await db_session.scalar(
        select(models.SchedulerStateVersionEvent).where(
            models.SchedulerStateVersionEvent.id == event.id
        )
    )
    assert stored is not None
    assert stored.before_metadata_json == {"capacity": 20, "type": "normal"}


@pytest.mark.asyncio
async def test_noop_and_repair_policy_changes_do_not_increment(db_session):
    organization, _ = await _create_org_and_user(db_session)
    service = SchedulerStateService(db_session)
    _, state = await service.get_or_create_active_state(
        organization.id,
        start_date=date(2025, 9, 1),
        hard_end_date=date(2026, 7, 15),
    )

    no_op = await service.record_change(
        organization.id,
        entity_type="ROOM",
        entity_id=4,
        operation=models.SchedulerStateChangeOperation.UPDATE,
        before={"capacity": 20},
        after={"capacity": 20},
    )
    policy = await service.record_change(
        organization.id,
        entity_type="REPAIR_POLICY",
        entity_id=None,
        operation=models.SchedulerStateChangeOperation.UPDATE,
        before={"stability_window_days": 14},
        after={"stability_window_days": 7},
        repair_policy_change=True,
    )

    assert no_op is not None
    assert no_op.change_scope == models.SchedulerStateChangeScope.NO_OP
    assert policy is not None
    assert policy.change_scope == models.SchedulerStateChangeScope.NO_OP
    assert policy.metadata_json == {"repair_policy_change": True}
    assert state.scheduler_state_version == 0


@pytest.mark.asyncio
async def test_inactive_resource_change_is_audited_without_increment(db_session):
    organization, _ = await _create_org_and_user(db_session)
    service = SchedulerStateService(db_session)
    _, state = await service.get_or_create_active_state(
        organization.id,
        start_date=date(2025, 9, 1),
        hard_end_date=date(2026, 7, 15),
    )

    event = await service.record_change(
        organization.id,
        entity_type="CLASS_DEMAND",
        entity_id=99,
        operation=models.SchedulerStateChangeOperation.DELETE,
        before={"minutes": 600},
        after=None,
        active_resource=False,
    )

    assert event is not None
    assert event.change_scope == models.SchedulerStateChangeScope.INACTIVE_RESOURCE
    assert state.scheduler_state_version == 0
