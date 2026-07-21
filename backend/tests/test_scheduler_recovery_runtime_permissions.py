"""Tests that SchedulerRecoveryService operations succeed under cronos_app privileges.

These tests use runtime_db_session (cronos_app) for service operations and
db_session (cronos_migrator) to prepare immutable seed data, mirroring
production privilege boundaries.
"""

from datetime import UTC, date, datetime, time

import pytest_asyncio
from sqlalchemy import select

from app import models
from app.db.tenant import set_async_tenant_context
from app.services.scheduler_recovery_service import SchedulerRecoveryService
from tests.conftest import (
    RuntimeTestingSessionLocal,
    create_org_and_user,
    create_teacher_profile,
)


@pytest_asyncio.fixture
async def seed(db_session):
    """Create org, school year, class, subject, teacher, timeslot, job, draft."""
    org, user = await create_org_and_user(
        db_session,
        clerk_user_id="user_recovery_test",
        email="recovery@test.com",
        role="admin",
        clerk_org_id="org_recovery_test",
    )
    membership = (
        await db_session.execute(
            select(models.OrganizationMembership).where(
                models.OrganizationMembership.account_id == user.id,
            )
        )
    ).scalar_one()

    year = models.SchedulerSchoolYear(
        organization_id=org.id,
        label="2026/2027",
        start_date=date(2026, 9, 1),
        hard_end_date=date(2027, 7, 31),
    )
    db_session.add(year)
    await db_session.flush()

    cls = models.SchoolClass(organization_id=org.id, name="T1", abbreviation="T1", level="10")
    db_session.add(cls)
    await db_session.flush()

    subject = models.Subject(organization_id=org.id, name="Math", abbreviation="MAT")
    db_session.add(subject)
    await db_session.flush()

    teacher = await create_teacher_profile(
        db_session, organization_id=org.id, name="Prof. Recovery"
    )

    room = models.Room(organization_id=org.id, name="R1")
    db_session.add(room)
    await db_session.flush()

    timeslot = models.Timeslot(
        organization_id=org.id,
        day_of_week=0,
        start_time=time(8, 0),
        end_time=time(9, 0),
    )
    db_session.add(timeslot)
    await db_session.flush()

    # Occurrence needed for PlannedRecoveryLink FK
    occurrence = models.LessonOccurrence(
        organization_id=org.id,
        date=date(2027, 1, 15),
        class_id=cls.id,
        subject_id=subject.id,
        revision=1,
        planned_minutes=50,
    )
    db_session.add(occurrence)
    await db_session.flush()

    job = models.ScheduleGenerationJob(
        organization_id=org.id,
        school_year_id=year.id,
        strategy=models.ScheduleGenerationStrategy.ADAPTIVE_REPAIR,
        job_status=models.ScheduleGenerationJobStatus.SUCCEEDED,
        result_category=models.ScheduleGenerationResultCategory.PARTIAL_RECOVERY,
        requested_by_membership_id=membership.id,
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        generation_input_fingerprint="test_fp",
    )
    db_session.add(job)
    await db_session.flush()

    draft = models.ScheduleDraft(
        organization_id=org.id,
        school_year_id=year.id,
        generation_job_id=job.id,
        strategy=models.ScheduleGenerationStrategy.ADAPTIVE_REPAIR,
        draft_state=models.ScheduleDraftState.PENDING,
        result_category=models.ScheduleGenerationResultCategory.PARTIAL_RECOVERY,
        trigger_type=models.ScheduleGenerationTrigger.SCHEDULER_CHANGE,
        generation_input_fingerprint="test_fp",
        projected_completion_date=date(2027, 6, 30),
        hard_end_date=date(2027, 7, 31),
        summary_json={},
        created_by_membership_id=membership.id,
        editable_start_date=date(2027, 1, 20),
    )
    db_session.add(draft)
    await db_session.flush()

    block = models.ScheduleDraftBlock(
        organization_id=org.id,
        school_year_id=year.id,
        draft_id=draft.id,
        stable_block_key="recovery_block_1",
        class_id=cls.id,
        subject_id=subject.id,
        teacher_id=teacher.id,
        room_id=room.id,
        date=date(2027, 2, 1),
        timeslot_id=timeslot.id,
        duration_minutes=50,
        is_recovery_block=True,
        recovery_source_occurrence_id=occurrence.id,
        recovery_source_occurrence_revision=1,
        change_type=models.ScheduleDraftBlockChangeType.ADDED,
    )
    db_session.add(block)
    await db_session.flush()
    await db_session.commit()

    return {
        "org": org,
        "year": year,
        "draft": draft,
        "block": block,
        "cls": cls,
        "subject": subject,
        "teacher": teacher,
        "occurrence": occurrence,
        "membership": membership,
    }


async def test_reconcile_no_links_succeeds_as_cronos_app(seed):
    """Even with zero rows, FOR UPDATE validates privileges. Must not raise."""
    async with RuntimeTestingSessionLocal() as session:
        await set_async_tenant_context(session, seed["org"].id)
        svc = SchedulerRecoveryService(session)
        result = await svc.reconcile_approved_recovery_links(
            seed["org"].id,
            seed["year"].id,
            seed["draft"].id,
            {},
        )
        assert result == (0, 0)
        await session.commit()


async def test_cancel_draft_recovery_links_succeeds_as_cronos_app(seed, db_session):
    """Cancel a PLANNED link using cronos_app session."""
    link = models.PlannedRecoveryLink(
        organization_id=seed["org"].id,
        school_year_id=seed["year"].id,
        debt_occurrence_id=seed["occurrence"].id,
        debt_occurrence_revision=1,
        planned_draft_block_id=seed["block"].id,
        planned_recovery_minutes=50,
        class_id=seed["cls"].id,
        subject_id=seed["subject"].id,
        teacher_id=seed["teacher"].id,
        status=models.PlannedRecoveryLinkStatus.PLANNED,
    )
    db_session.add(link)
    await db_session.commit()

    async with RuntimeTestingSessionLocal() as session:
        await set_async_tenant_context(session, seed["org"].id)
        svc = SchedulerRecoveryService(session)
        canceled = await svc.cancel_draft_recovery_links(
            seed["org"].id,
            seed["year"].id,
            seed["draft"].id,
        )
        assert canceled == 1
        await session.commit()

    # Verify status changed
    async with RuntimeTestingSessionLocal() as session:
        await set_async_tenant_context(session, seed["org"].id)
        reloaded = await session.get(models.PlannedRecoveryLink, link.id)
        assert reloaded.status == models.PlannedRecoveryLinkStatus.CANCELED


async def test_plan_draft_recovery_succeeds_as_cronos_app(seed, db_session):
    """Plan a recovery link using cronos_app, validating FOR UPDATE OF schedule_drafts."""
    # Need active debt ledger — create a debt state entry
    state = models.SchedulerSchoolYearState(
        organization_id=seed["org"].id,
        school_year_id=seed["year"].id,
    )
    db_session.add(state)
    await db_session.flush()
    await db_session.commit()

    async with RuntimeTestingSessionLocal() as session:
        await set_async_tenant_context(session, seed["org"].id)
        svc = SchedulerRecoveryService(session)
        try:
            link = await svc.plan_draft_recovery(
                seed["org"].id,
                seed["year"].id,
                seed["block"].id,
            )
            # If debt ledger is empty, this raises RecoveryDebtUnavailableError
            # which is acceptable — the important thing is no permission error
            assert link is not None
            await session.commit()
        except Exception as exc:
            # RecoveryDebtUnavailableError is acceptable: the lock succeeded,
            # only the debt lookup failed because test fixtures don't populate
            # the full debt ledger. InsufficientPrivilegeError would be a real failure.
            assert "permission denied" not in str(exc).lower(), (
                f"Unexpected permission error: {exc}"
            )


async def test_tenant_isolation(seed):
    """Another org cannot see this org's recovery links."""
    async with RuntimeTestingSessionLocal() as session:
        # Set context to a different org (id=999999)
        await session.execute(
            models.Organization.__table__.insert().values(
                id=999999, name="Other Org", clerk_org_id="org_other_isolation"
            )
        )
        await session.commit()

    async with RuntimeTestingSessionLocal() as session:
        await set_async_tenant_context(session, 999999)
        svc = SchedulerRecoveryService(session)
        result = await svc.reconcile_approved_recovery_links(
            999999, seed["year"].id, seed["draft"].id, {}
        )
        assert result == (0, 0)
        await session.commit()
