from datetime import date, datetime, time, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app import models
from app.main import app
from app.services.school_year_reset_service import SchoolYearResetService


pytestmark = pytest.mark.integration


async def _seed_reset_regression_graph(db, organization_id: int, admin_user_id: int):
    course = models.Course(
        organization_id=organization_id,
        name="Reset Course",
        abbreviation="RST",
    )
    subject = models.Subject(
        organization_id=organization_id,
        name="Reset Subject",
        required_room_type=models.RoomType.normal,
    )
    teacher = models.Teacher(organization_id=organization_id, name="Reset Teacher")
    room = models.Room(
        organization_id=organization_id,
        name="Reset Room",
        type=models.RoomType.normal,
        capacity=30,
    )
    timeslot = models.Timeslot(
        organization_id=organization_id,
        day_of_week=1,
        start_time=time(9),
        end_time=time(10),
    )
    settings = models.OrganizationSettings(
        organization_id=organization_id,
        school_start_date=date(2025, 9, 1),
        school_hard_end_date=date(2026, 7, 15),
        repair_stability_window_days=14,
    )
    school_year = models.SchedulerSchoolYear(
        organization_id=organization_id,
        label="2025/2026",
        start_date=settings.school_start_date,
        hard_end_date=settings.school_hard_end_date,
        timezone="Europe/Lisbon",
    )
    db.add_all([course, subject, teacher, room, timeslot, settings, school_year])
    await db.flush()

    class_ = models.Class(
        organization_id=organization_id,
        name="Reset Class",
        size=20,
        start_year=2025,
        end_year=2026,
        grade_level=10,
        course_id=course.id,
    )
    module = models.Module(
        organization_id=organization_id,
        name="Reset Module",
        code="RST-1",
        hours_total=25,
        order=1,
        subject_id=subject.id,
    )
    state = models.SchedulerSchoolYearState(
        organization_id=organization_id,
        school_year_id=school_year.id,
        school_year_publication_state=models.SchoolYearPublicationState.PUBLISHED,
        active_schedule_version_id="reset-v1",
        scheduler_state_version=1,
        approved_scheduler_state_version=1,
    )
    db.add_all([class_, module, state])
    await db.flush()

    lesson = models.Lesson(
        organization_id=organization_id,
        class_id=class_.id,
        subject_id=subject.id,
        teacher_id=teacher.id,
    )
    progress = models.ClassProgress(
        organization_id=organization_id,
        class_id=class_.id,
        module_id=module.id,
        hours_completed=10,
        hours_debt=2,
        is_completed=True,
    )
    now = datetime.now(timezone.utc)
    job = models.ScheduleGenerationJob(
        organization_id=organization_id,
        school_year_id=school_year.id,
        requested_by_user_id=admin_user_id,
        strategy=models.ScheduleGenerationStrategy.COMPLETE_GENERATION,
        trigger_type=models.ScheduleGenerationTrigger.FIRST_GENERATION,
        job_status=models.ScheduleGenerationJobStatus.SUCCEEDED,
        result_category=models.ScheduleGenerationResultCategory.COMPLETE_SUCCESS,
        queued_at=now,
        started_at=now,
        finished_at=now,
    )
    db.add_all([lesson, progress, job])
    await db.flush()

    draft = models.ScheduleDraft(
        organization_id=organization_id,
        school_year_id=school_year.id,
        generation_job_id=job.id,
        strategy=models.ScheduleGenerationStrategy.COMPLETE_GENERATION,
        draft_state=models.ScheduleDraftState.APPROVED,
        result_category=models.ScheduleGenerationResultCategory.COMPLETE_SUCCESS,
        trigger_type=models.ScheduleGenerationTrigger.FIRST_GENERATION,
        generation_input_fingerprint="a" * 64,
        scheduler_state_version_used=1,
        projected_completion_date=date(2026, 6, 30),
        hard_end_date=school_year.hard_end_date,
        summary_json={"block_count": 1},
        created_by_user_id=admin_user_id,
        decided_by_user_id=admin_user_id,
        decided_at=now,
    )
    db.add(draft)
    await db.flush()

    draft_block = models.ScheduleDraftBlock(
        organization_id=organization_id,
        school_year_id=school_year.id,
        draft_id=draft.id,
        stable_block_key="reset-block",
        class_id=class_.id,
        subject_id=subject.id,
        teacher_id=teacher.id,
        room_id=room.id,
        room_type_id=models.RoomType.normal,
        date=date(2025, 9, 2),
        timeslot_id=timeslot.id,
        duration_minutes=60,
        module_sequence_index=1,
        change_type=models.ScheduleDraftBlockChangeType.ADDED,
    )
    db.add(draft_block)
    await db.flush()

    active_block = models.ActiveScheduleBlock(
        organization_id=organization_id,
        school_year_id=school_year.id,
        schedule_version_id="reset-v1",
        stable_block_key=draft_block.stable_block_key,
        class_id=class_.id,
        subject_id=subject.id,
        teacher_id=teacher.id,
        room_id=room.id,
        date=draft_block.date,
        timeslot_id=timeslot.id,
        duration_minutes=60,
        source_draft_block_id=draft_block.id,
    )
    legacy_output = models.ScheduleOutput(
        organization_id=organization_id,
        lesson_id=lesson.id,
        timeslot_id=timeslot.id,
        room_id=room.id,
        generation_id="legacy-reset-v1",
        date=draft_block.date,
        is_draft=False,
    )
    db.add_all([active_block, legacy_output])
    await db.flush()

    occurrence = models.LessonOccurrence(
        organization_id=organization_id,
        schedule_output_id=legacy_output.id,
        active_schedule_block_id=active_block.id,
        date=draft_block.date,
        class_id=class_.id,
        subject_id=subject.id,
        status=models.LessonOccurrenceStatus.GAP,
        revision=1,
        planned_hours=1,
        hours_given=0,
    )
    lesson_log = models.LessonLog(
        organization_id=organization_id,
        active_schedule_block_id=active_block.id,
        status=models.LessonLogStatus.COMPLETED,
        summary="Reset regression",
        logged_by_user_id=admin_user_id,
    )
    db.add_all([occurrence, lesson_log])
    await db.flush()

    recovery_link = models.PlannedRecoveryLink(
        organization_id=organization_id,
        school_year_id=school_year.id,
        debt_occurrence_id=occurrence.id,
        debt_occurrence_revision=occurrence.revision,
        planned_active_block_id=active_block.id,
        planned_recovery_minutes=60,
        class_id=class_.id,
        subject_id=subject.id,
        teacher_id=teacher.id,
    )
    ledger = models.ProgressLedgerEntry(
        organization_id=organization_id,
        source_type="LESSON_OCCURRENCE",
        source_id=occurrence.id,
        source_revision=occurrence.revision,
        class_id=class_.id,
        module_id=module.id,
        debt_delta=1,
        idempotency_key=f"reset:{organization_id}:{occurrence.id}",
        created_by_user_id=admin_user_id,
    )
    timesheet = models.TeacherWeeklyTimesheet(
        organization_id=organization_id,
        teacher_id=teacher.id,
        week_start_date=date(2025, 9, 1),
    )
    db.add_all([recovery_link, ledger, timesheet])
    await db.commit()
    return {
        "course_id": course.id,
        "class_id": class_.id,
        "module_id": module.id,
        "settings_id": settings.id,
        "school_year_id": school_year.id,
        "progress_id": progress.id,
    }


async def _count_for_org(db, model, organization_id: int) -> int:
    return await db.scalar(
        select(func.count()).select_from(model).where(model.organization_id == organization_id)
    )


@pytest.mark.asyncio
async def test_soft_reset_clears_recovery_graph_and_recreates_clean_year(
    async_client,
    db_session,
    admin_token_headers,
):
    admin = await db_session.scalar(
        select(models.User).where(models.User.clerk_user_id == "user_admin_001")
    )
    seeded = await _seed_reset_regression_graph(
        db_session,
        admin.organization_id,
        admin.id,
    )
    other_organization = models.Organization(name="Other Reset School", plan_status="active")
    db_session.add(other_organization)
    await db_session.flush()
    other_admin = models.User(
        organization_id=other_organization.id,
        email="other-reset-admin@example.com",
        role=models.UserRole.admin,
        is_active=True,
    )
    db_session.add(other_admin)
    await db_session.flush()
    other_seeded = await _seed_reset_regression_graph(
        db_session,
        other_organization.id,
        other_admin.id,
    )
    other_counts_before = {
        model: await _count_for_org(db_session, model, other_organization.id)
        for model in (
            models.PlannedRecoveryLink,
            models.LessonOccurrence,
            models.ScheduleGenerationJob,
            models.ActiveScheduleBlock,
        )
    }

    # The shared fixture installs the test DB/auth dependency overrides. This
    # client turns an unhandled application exception into the HTTP 500 that a
    # browser observes, so a regression fails as an assertion instead of
    # leaking a background ASGI task.
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="https://test",
    ) as client:
        response = await client.post(
            "/api/v1/school/settings/soft-reset",
            json={"confirm_phrase": "Confirmo"},
            headers=admin_token_headers,
        )

    assert response.status_code == 200
    assert response.json() == {"message": "Soft-reset efetuado com sucesso."}
    for model in (
        models.PlannedRecoveryLink,
        models.LessonLog,
        models.LessonOccurrence,
        models.ProgressLedgerEntry,
        models.TeacherWeeklyTimesheet,
        models.ScheduleOutput,
        models.ScheduleGenerationJob,
        models.ScheduleDraft,
        models.ScheduleDraftBlock,
        models.ActiveScheduleBlock,
    ):
        assert await _count_for_org(db_session, model, admin.organization_id) == 0

    progress = await db_session.scalar(
        select(models.ClassProgress).where(models.ClassProgress.class_id == seeded["class_id"])
    )
    assert progress.hours_completed == 0
    assert progress.hours_debt == 0
    assert progress.is_completed is False
    assert await db_session.get(models.Course, seeded["course_id"]) is not None
    assert await db_session.get(models.Module, seeded["module_id"]) is not None
    assert await db_session.get(models.OrganizationSettings, seeded["settings_id"]) is not None

    new_year = await db_session.scalar(
        select(models.SchedulerSchoolYear).where(
            models.SchedulerSchoolYear.organization_id == admin.organization_id
        )
    )
    assert new_year is not None
    assert new_year.id != seeded["school_year_id"]
    state = await db_session.scalar(
        select(models.SchedulerSchoolYearState).where(
            models.SchedulerSchoolYearState.organization_id == admin.organization_id,
            models.SchedulerSchoolYearState.school_year_id == new_year.id,
        )
    )
    assert state.school_year_publication_state == models.SchoolYearPublicationState.UNPUBLISHED
    assert state.pending_draft_id is None
    assert state.active_schedule_version_id is None

    for model, expected_count in other_counts_before.items():
        assert await _count_for_org(db_session, model, other_organization.id) == expected_count
    other_progress = await db_session.get(models.ClassProgress, other_seeded["progress_id"])
    assert other_progress.hours_completed == 10
    assert other_progress.hours_debt == 2
    assert other_progress.is_completed is True


@pytest.mark.asyncio
async def test_soft_reset_rolls_back_every_change_when_a_late_step_fails(
    db_session,
    monkeypatch,
):
    organization = models.Organization(name="Rollback Reset School", plan_status="active")
    db_session.add(organization)
    await db_session.flush()
    admin = models.User(
        organization_id=organization.id,
        email="rollback-reset-admin@example.com",
        role=models.UserRole.admin,
        is_active=True,
    )
    db_session.add(admin)
    await db_session.flush()
    seeded = await _seed_reset_regression_graph(db_session, organization.id, admin.id)
    organization_id = organization.id
    admin_id = admin.id

    async def fail_recreation(*_args, **_kwargs):
        raise RuntimeError("forced late reset failure")

    monkeypatch.setattr(
        SchoolYearResetService,
        "_recreate_clean_school_year",
        fail_recreation,
    )

    with pytest.raises(RuntimeError, match="forced late reset failure"):
        await SchoolYearResetService(db_session).reset_year(
            organization_id,
            reset_by_user_id=admin_id,
        )
    await db_session.rollback()

    assert await _count_for_org(db_session, models.PlannedRecoveryLink, organization_id) == 1
    assert await _count_for_org(db_session, models.LessonOccurrence, organization_id) == 1
    assert await _count_for_org(db_session, models.ActiveScheduleBlock, organization_id) == 1
    assert await db_session.get(models.SchedulerSchoolYear, seeded["school_year_id"]) is not None
    progress = await db_session.get(models.ClassProgress, seeded["progress_id"])
    assert progress.hours_completed == 10
    assert progress.hours_debt == 2
    assert progress.is_completed is True


@pytest.mark.asyncio
async def test_soft_reset_requires_exact_confirmation(
    async_client,
    admin_token_headers,
):
    response = await async_client.post(
        "/api/v1/school/settings/soft-reset",
        json={"confirm_phrase": "confirmo"},
        headers=admin_token_headers,
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_soft_reset_rejects_teacher(
    async_client,
    clerk_teacher_headers,
):
    response = await async_client.post(
        "/api/v1/school/settings/soft-reset",
        json={"confirm_phrase": "Confirmo"},
        headers=clerk_teacher_headers,
    )

    assert response.status_code == 403
