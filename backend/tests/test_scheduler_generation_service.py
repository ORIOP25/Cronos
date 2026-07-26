import asyncio
from dataclasses import replace
from datetime import date

import pytest

from app import models
from app.services.scheduler_generation_service import (
    NoOperationalTriggerError,
    PendingDraftReplacementRequiredError,
    SchedulerGenerationService,
)
from app.services.scheduler_job_service import (
    SchedulerJobIdempotencyConflictError,
    SchedulerJobService,
)
from tests.conftest import TestingSessionLocal


async def _base_state(db_session):
    organization = models.Organization(name="Strategy School", plan_status="active")
    db_session.add(organization)
    await db_session.flush()
    school_year = models.SchedulerSchoolYear(
        organization_id=organization.id,
        label="2025/2026",
        start_date=date(2025, 9, 1),
        hard_end_date=date(2026, 7, 15),
        timezone="Europe/Lisbon",
    )
    db_session.add(school_year)
    await db_session.flush()
    state = models.SchedulerSchoolYearState(
        organization_id=organization.id,
        school_year_id=school_year.id,
    )
    db_session.add(state)
    await db_session.commit()
    return organization, school_year, state


async def _admin_membership(db_session, organization, email):
    user = models.User(email=email)
    db_session.add(user)
    await db_session.flush()
    membership = models.OrganizationMembership(
        organization_id=organization.id,
        account_id=user.id,
        organization_display_name="Scheduler Admin",
        lifecycle_status=models.MembershipLifecycleStatus.active,
        access_status=models.MembershipAccessStatus.active,
        can_admin=True,
        can_teach=False,
    )
    db_session.add(membership)
    await db_session.flush()
    return membership


async def test_strategy_selection_covers_first_debt_change_mixed_and_no_trigger(db_session):
    organization, school_year, state = await _base_state(db_session)
    service = SchedulerGenerationService(db_session)

    first = await service.select_strategy(organization.id)
    assert first.strategy == models.ScheduleGenerationStrategy.COMPLETE_GENERATION
    assert first.trigger_type == models.ScheduleGenerationTrigger.FIRST_GENERATION
    assert first.debt_basis is None

    state.school_year_publication_state = models.SchoolYearPublicationState.PUBLISHED
    state.active_schedule_version_id = "active-v1"
    state.approved_scheduler_state_version = 0
    await db_session.flush()
    with pytest.raises(NoOperationalTriggerError) as blocked:
        await service.select_strategy(organization.id)
    assert blocked.value.code == "no_operational_trigger"

    state.scheduler_state_version = 1
    await db_session.flush()
    changed = await service.select_strategy(organization.id)
    assert changed.strategy == models.ScheduleGenerationStrategy.ADAPTIVE_REPAIR
    assert changed.trigger_type == models.ScheduleGenerationTrigger.SCHEDULER_CHANGE

    occurrence = models.LessonOccurrence(
        organization_id=organization.id,
        date=date(2026, 1, 12),
        status=models.LessonOccurrenceStatus.GAP,
        revision=1,
        is_active=True,
        planned_hours=1.0,
        hours_given=0,
    )
    db_session.add(occurrence)
    await db_session.flush()
    mixed = await service.select_strategy(organization.id)
    assert mixed.trigger_type == models.ScheduleGenerationTrigger.MIXED
    assert mixed.debt_basis is not None
    assert mixed.debt_basis.unresolved_debt_minutes == 60

    state.approved_scheduler_state_version = 1
    await db_session.flush()
    debt = await service.select_strategy(organization.id)
    assert debt.trigger_type == models.ScheduleGenerationTrigger.EXPLICIT_DEBT

    occurrence.status = models.LessonOccurrenceStatus.GIVEN
    await db_session.flush()
    with pytest.raises(NoOperationalTriggerError):
        await service.select_strategy(organization.id)


async def test_pending_draft_requires_confirmation_and_is_not_replaced_early(db_session):
    organization, school_year, state = await _base_state(db_session)
    membership = await _admin_membership(db_session, organization, "strategy-selector@example.com")
    job = models.ScheduleGenerationJob(
        organization_id=organization.id,
        school_year_id=school_year.id,
        requested_by_membership_id=membership.id,
        strategy=models.ScheduleGenerationStrategy.COMPLETE_GENERATION,
        trigger_type=models.ScheduleGenerationTrigger.FIRST_GENERATION,
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
        projected_completion_date=date(2026, 6, 30),
        hard_end_date=school_year.hard_end_date,
        summary_json={},
        created_by_membership_id=membership.id,
    )
    db_session.add(draft)
    await db_session.flush()
    state.pending_draft_id = draft.id
    await db_session.commit()
    service = SchedulerGenerationService(db_session)

    with pytest.raises(PendingDraftReplacementRequiredError) as blocked:
        await service.select_strategy(organization.id)
    assert blocked.value.pending_draft_id == draft.id

    selected = await service.select_strategy(
        organization.id,
        replace_pending_draft=True,
    )
    assert selected.replaces_pending_draft is True
    assert selected.pending_draft_id == draft.id
    assert draft.draft_state == models.ScheduleDraftState.PENDING
    assert state.pending_draft_id == draft.id


async def test_job_creation_is_locked_idempotent_and_reuses_active_job(db_session):
    organization, _, _ = await _base_state(db_session)
    membership = await _admin_membership(db_session, organization, "job-requester@example.com")
    selection = await SchedulerGenerationService(db_session).select_strategy(organization.id)
    jobs = SchedulerJobService(db_session)

    first = await jobs.create_or_get_job(
        selection,
        requested_by_membership_id=membership.id,
        idempotency_key=" request-1 ",
    )
    await db_session.commit()
    assert first.created is True
    assert first.job.idempotency_key == "request-1"
    assert first.job.job_status == models.ScheduleGenerationJobStatus.QUEUED
    assert jobs.worker_task_id(first.job.id) == f"scheduler-job-{first.job.id}"

    retry = await jobs.create_or_get_job(
        selection,
        requested_by_membership_id=membership.id,
        idempotency_key="request-1",
    )
    assert retry.created is False
    assert retry.job.id == first.job.id

    concurrent = await jobs.create_or_get_job(
        selection,
        requested_by_membership_id=membership.id,
    )
    assert concurrent.created is False
    assert concurrent.job.id == first.job.id

    conflicting = replace(
        selection,
        trigger_type=models.ScheduleGenerationTrigger.SCHEDULER_CHANGE,
    )
    with pytest.raises(SchedulerJobIdempotencyConflictError):
        await jobs.create_or_get_job(
            conflicting,
            requested_by_membership_id=membership.id,
            idempotency_key="request-1",
        )


async def test_job_cancellation_is_tenant_scoped_and_idempotent(db_session):
    organization, _, _ = await _base_state(db_session)
    membership = await _admin_membership(db_session, organization, "job-cancel@example.com")
    selection = await SchedulerGenerationService(db_session).select_strategy(organization.id)
    jobs = SchedulerJobService(db_session)
    handle = await jobs.create_or_get_job(
        selection,
        requested_by_membership_id=membership.id,
    )

    requested = await jobs.request_cancellation(organization.id, handle.job.id)
    first_requested_at = requested.cancellation_requested_at
    assert requested.job_status == models.ScheduleGenerationJobStatus.CANCEL_REQUESTED
    assert first_requested_at is not None

    repeated = await jobs.request_cancellation(organization.id, handle.job.id)
    assert repeated.job_status == models.ScheduleGenerationJobStatus.CANCEL_REQUESTED
    assert repeated.cancellation_requested_at == first_requested_at


async def test_simultaneous_job_admission_reuses_one_active_job(db_session):
    organization, _, _ = await _base_state(db_session)
    membership = await _admin_membership(db_session, organization, "job-race@example.com")
    await db_session.commit()
    organization_id = organization.id
    membership_id = membership.id
    selection = await SchedulerGenerationService(db_session).select_strategy(organization_id)

    async def admit() -> tuple[int, bool]:
        async with TestingSessionLocal() as session:
            handle = await SchedulerJobService(session).create_or_get_job(
                selection,
                requested_by_membership_id=membership_id,
            )
            await session.commit()
            return handle.job.id, handle.created

    results = await asyncio.gather(admit(), admit())

    assert len({job_id for job_id, _created in results}) == 1
    assert sum(created for _job_id, created in results) == 1
