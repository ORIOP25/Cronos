from datetime import UTC, date, datetime, time

import pytest
from sqlalchemy import select

from app import models
from app.services.scheduler_debt_service import SchedulerDebtService
from app.services.scheduler_fingerprint_service import SchedulerFingerprintService
from app.services.scheduler_generation_service import (
    NoOperationalTriggerError,
    SchedulerGenerationService,
)
from app.services.scheduler_recovery_service import (
    RecoveryDebtUnavailableError,
    SchedulerRecoveryService,
)
from tests._support.db_fixtures import create_teacher_profile


async def _debt_context(db_session):
    organization = models.Organization(name="Debt Fingerprint", plan_status="active")
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
    db_session.add(
        models.SchedulerSchoolYearState(
            organization_id=organization.id,
            school_year_id=school_year.id,
        )
    )
    subject = models.Subject(
        organization_id=organization.id,
        name="Math",
        required_room_type=models.RoomType.normal,
    )
    course = models.Course(
        organization_id=organization.id,
        name="Course",
        abbreviation="CRS",
    )
    teacher = await create_teacher_profile(
        db_session,
        organization_id=organization.id,
        name="Teacher",
    )
    room = models.Room(
        organization_id=organization.id,
        name="Room",
        type=models.RoomType.normal,
        capacity=30,
    )
    timeslot = models.Timeslot(
        organization_id=organization.id,
        day_of_week=1,
        start_time=time(9, 0),
        end_time=time(10, 30),
    )
    db_session.add_all([subject, course, room, timeslot])
    await db_session.flush()
    class_ = models.Class(
        organization_id=organization.id,
        name="10A",
        size=20,
        start_year=2025,
        end_year=2026,
        grade_level=10,
        course_id=course.id,
    )
    db_session.add(class_)
    await db_session.flush()
    db_session.add(
        models.ClassSubjectLink(
            organization_id=organization.id,
            class_id=class_.id,
            subject_id=subject.id,
            grade_level=class_.grade_level,
            teacher_id=teacher.id,
        )
    )
    await db_session.execute(
        models.teacher_subject_link.insert().values(
            organization_id=organization.id,
            teacher_id=teacher.id,
            subject_id=subject.id,
        )
    )
    occurrence = models.LessonOccurrence(
        organization_id=organization.id,
        date=date(2026, 1, 12),
        class_id=class_.id,
        subject_id=subject.id,
        status=models.LessonOccurrenceStatus.GAP,
        revision=1,
        is_active=True,
        planned_timeslot_id=timeslot.id,
        planned_teacher_id=teacher.id,
        planned_hours=1.5,
        hours_given=0,
    )
    db_session.add(occurrence)
    await db_session.commit()
    return organization, school_year, class_, subject, teacher, room, timeslot, occurrence


async def test_debt_fingerprint_tracks_status_revision_and_minutes(db_session):
    organization, school_year, *_, occurrence = await _debt_context(db_session)
    service = SchedulerFingerprintService(db_session)

    first = await service.debt_basis_fingerprint(organization.id, school_year.id)
    assert first is not None
    assert first.unresolved_debt_minutes == 90
    assert first.snapshot["items"][0]["debt_status"] == "GAP"

    occurrence.revision = 2
    await db_session.flush()
    revised = await service.debt_basis_fingerprint(organization.id, school_year.id)
    assert revised is not None
    assert revised.value != first.value

    occurrence.status = models.LessonOccurrenceStatus.GIVEN
    await db_session.flush()
    assert await service.debt_basis_fingerprint(organization.id, school_year.id) is None


async def test_debt_exists_only_after_human_controlled_status_decision(db_session):
    organization, school_year, *_, occurrence = await _debt_context(db_session)
    service = SchedulerFingerprintService(db_session)

    occurrence.status = None
    await db_session.flush()
    assert await service.debt_basis_fingerprint(organization.id, school_year.id) is None

    occurrence.status = models.LessonOccurrenceStatus.GAP
    await db_session.flush()
    assert (
        await service.debt_basis_fingerprint(organization.id, school_year.id)
    ).unresolved_debt_minutes == 90


async def test_active_planned_recovery_suppresses_covered_debt(db_session):
    (
        organization,
        school_year,
        class_,
        subject,
        teacher,
        room,
        timeslot,
        occurrence,
    ) = await _debt_context(db_session)
    user = models.User(
        email="debt-fingerprint@example.com",
    )
    db_session.add(user)
    await db_session.flush()
    membership = models.OrganizationMembership(
        organization_id=organization.id,
        account_id=user.id,
        organization_display_name="Debt Admin",
        lifecycle_status=models.MembershipLifecycleStatus.active,
        access_status=models.MembershipAccessStatus.active,
        can_admin=True,
        can_teach=False,
    )
    db_session.add(membership)
    await db_session.flush()
    job = models.ScheduleGenerationJob(
        organization_id=organization.id,
        school_year_id=school_year.id,
        requested_by_membership_id=membership.id,
        strategy=models.ScheduleGenerationStrategy.ADAPTIVE_REPAIR,
    )
    db_session.add(job)
    await db_session.flush()
    draft = models.ScheduleDraft(
        organization_id=organization.id,
        school_year_id=school_year.id,
        generation_job_id=job.id,
        strategy=models.ScheduleGenerationStrategy.ADAPTIVE_REPAIR,
        result_category=models.ScheduleGenerationResultCategory.PARTIAL_RECOVERY,
        trigger_type=models.ScheduleGenerationTrigger.EXPLICIT_DEBT,
        generation_input_fingerprint="a" * 64,
        debt_basis_fingerprint="b" * 64,
        editable_start_date=date(2026, 1, 13),
        projected_completion_date=date(2026, 6, 30),
        hard_end_date=school_year.hard_end_date,
        summary_json={},
        created_by_membership_id=membership.id,
    )
    db_session.add(draft)
    await db_session.flush()
    draft_block = models.ScheduleDraftBlock(
        organization_id=organization.id,
        school_year_id=school_year.id,
        draft_id=draft.id,
        stable_block_key="recovery-1",
        class_id=class_.id,
        subject_id=subject.id,
        teacher_id=teacher.id,
        room_id=room.id,
        room_type_id=models.RoomType.normal,
        date=date(2026, 1, 19),
        timeslot_id=timeslot.id,
        duration_minutes=90,
        is_recovery_block=True,
        recovery_source_occurrence_id=occurrence.id,
        recovery_source_occurrence_revision=occurrence.revision,
        change_type=models.ScheduleDraftBlockChangeType.ADDED,
    )
    db_session.add(draft_block)
    await db_session.flush()
    active_block = models.ActiveScheduleBlock(
        organization_id=organization.id,
        school_year_id=school_year.id,
        schedule_version_id="version-1",
        stable_block_key=draft_block.stable_block_key,
        class_id=class_.id,
        subject_id=subject.id,
        teacher_id=teacher.id,
        room_id=room.id,
        date=draft_block.date,
        timeslot_id=timeslot.id,
        duration_minutes=90,
        source_draft_block_id=draft_block.id,
        is_recovery_block=True,
    )
    db_session.add(active_block)
    await db_session.flush()
    state = await db_session.scalar(
        select(models.SchedulerSchoolYearState).where(
            models.SchedulerSchoolYearState.organization_id == organization.id,
            models.SchedulerSchoolYearState.school_year_id == school_year.id,
        )
    )
    state.school_year_publication_state = models.SchoolYearPublicationState.PUBLISHED
    state.active_schedule_version_id = "version-1"
    state.approved_scheduler_state_version = state.scheduler_state_version
    recovery_service = SchedulerRecoveryService(db_session)
    link = await recovery_service.plan_draft_recovery(
        organization.id,
        school_year.id,
        draft_block.id,
        recovery_minutes=30,
    )
    activated, canceled_count = await recovery_service.reconcile_approved_recovery_links(
        organization.id,
        school_year.id,
        draft.id,
        {draft_block.id: active_block.id},
    )
    assert (activated, canceled_count) == (1, 0)
    assert link.planned_active_block_id == active_block.id
    await db_session.commit()

    service = SchedulerFingerprintService(db_session)
    planned = await service.debt_basis_fingerprint(organization.id, school_year.id)
    assert planned is not None
    assert planned.unresolved_debt_minutes == 60
    assert planned.snapshot["items"][0]["active_planned_recovery_minutes"] == 30
    ledger = await SchedulerDebtService(db_session).active_debt_ledger(
        organization.id,
        school_year.id,
    )
    assert ledger.total_remaining_minutes == 60
    assert ledger.remaining_minutes_by_class_subject == {(class_.id, subject.id): 60}
    assert ledger.entries[0].occurrence_id == occurrence.id
    assert ledger.entries[0].source_planned_block_id is None
    duplicate_block = models.ScheduleDraftBlock(
        organization_id=organization.id,
        school_year_id=school_year.id,
        draft_id=draft.id,
        stable_block_key="recovery-2",
        class_id=class_.id,
        subject_id=subject.id,
        teacher_id=teacher.id,
        room_id=room.id,
        room_type_id=models.RoomType.normal,
        date=date(2026, 1, 20),
        timeslot_id=timeslot.id,
        duration_minutes=90,
        is_recovery_block=True,
        recovery_source_occurrence_id=occurrence.id,
        recovery_source_occurrence_revision=occurrence.revision,
        change_type=models.ScheduleDraftBlockChangeType.ADDED,
    )
    db_session.add(duplicate_block)
    await db_session.flush()
    with pytest.raises(RecoveryDebtUnavailableError, match="Only 60"):
        await recovery_service.plan_draft_recovery(
            organization.id,
            school_year.id,
            duplicate_block.id,
            recovery_minutes=61,
        )

    draft.draft_state = models.ScheduleDraftState.APPROVED
    draft.decided_by_membership_id = membership.id
    draft.decided_at = datetime.now(UTC)
    await db_session.flush()
    selection = await SchedulerGenerationService(db_session).select_strategy(organization.id)
    assert selection.trigger_type == models.ScheduleGenerationTrigger.EXPLICIT_DEBT
    assert selection.debt_basis.unresolved_debt_minutes == 60

    link.planned_recovery_minutes = 90
    await db_session.flush()
    assert await service.debt_basis_fingerprint(organization.id, school_year.id) is None
    fully_covered = await SchedulerDebtService(db_session).active_debt_ledger(
        organization.id,
        school_year.id,
    )
    assert fully_covered.is_empty
    assert fully_covered.total_remaining_minutes == 0
    with pytest.raises(NoOperationalTriggerError):
        await SchedulerGenerationService(db_session).select_strategy(organization.id)

    link.status = models.PlannedRecoveryLinkStatus.CANCELED
    await db_session.flush()
    canceled = await service.debt_basis_fingerprint(organization.id, school_year.id)
    assert canceled is not None
    assert canceled.unresolved_debt_minutes == 90
    assert canceled.value != planned.value

    link.status = models.PlannedRecoveryLinkStatus.PLANNED
    link.planned_recovery_minutes = 30
    lesson_log = models.LessonLog(
        organization_id=organization.id,
        active_schedule_block_id=active_block.id,
        status=models.LessonLogStatus.COMPLETED,
        logged_by_membership_id=membership.id,
    )
    db_session.add(lesson_log)
    await db_session.flush()
    delivered = await recovery_service.record_delivery(
        organization.id,
        school_year.id,
        active_block.id,
        lesson_log.id,
        delivered_minutes=30,
    )
    assert delivered.status == models.PlannedRecoveryLinkStatus.DELIVERED
    assert delivered.delivered_lesson_log_id == lesson_log.id
    assert delivered.delivered_recovery_minutes == 30
    delivered_again = await recovery_service.record_delivery(
        organization.id,
        school_year.id,
        active_block.id,
        lesson_log.id,
    )
    assert delivered_again.id == delivered.id
    after_delivery = await service.debt_basis_fingerprint(
        organization.id,
        school_year.id,
    )
    assert after_delivery is not None
    assert after_delivery.unresolved_debt_minutes == 60
