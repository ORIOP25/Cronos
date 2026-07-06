import asyncio
from datetime import date, datetime, time, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select

import app.services.scheduler_job_runtime as runtime_module
from app import models
from app.api.v1.endpoints.scheduler import approve_draft as approve_draft_endpoint
from app.services.scheduler_generation_service import SchedulerGenerationService
from app.services.scheduler_complete_engine import run_complete_generation
from app.services.scheduler_adaptive_engine import run_adaptive_repair
from app.services.scheduler_fingerprint_service import SchedulerFingerprintService
from app.services.scheduler_draft_service import SchedulerDraftService
from app.services.scheduler_diff_service import SchedulerDiffService
from app.services.scheduler_approval_service import (
    DraftApprovalConflictError,
    SchedulerApprovalService,
)
from app.services.scheduler_lifecycle_service import SchedulerLifecycleService
from app.services.scheduler_status_service import SchedulerStatusService
from app.services.scheduler_job_runtime import (
    DraftBlockSpec,
    NoValidGenerationOutput,
    SchedulerJobRuntime,
    ValidatedGenerationResult,
)
from app.services.scheduler_job_service import SchedulerJobService
from tests.conftest import TestingSessionLocal


pytestmark = pytest.mark.integration


async def _runtime_context(db_session):
    organization = models.Organization(name="Runtime School", plan_status="active")
    db_session.add(organization)
    await db_session.flush()
    user = models.User(
        organization_id=organization.id,
        email="runtime-admin@example.com",
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
    course = models.Course(
        organization_id=organization.id,
        name="Course",
        abbreviation="RUN",
    )
    subject = models.Subject(
        organization_id=organization.id,
        name="Subject",
        required_room_type=models.RoomType.normal,
    )
    teacher = models.Teacher(organization_id=organization.id, name="Teacher")
    room = models.Room(
        organization_id=organization.id,
        name="Room",
        type=models.RoomType.normal,
        capacity=30,
    )
    slot = models.Timeslot(
        organization_id=organization.id,
        day_of_week=1,
        start_time=time(9),
        end_time=time(10),
    )
    db_session.add_all([user, school_year, course, subject, teacher, room, slot])
    await db_session.flush()
    state = models.SchedulerSchoolYearState(
        organization_id=organization.id,
        school_year_id=school_year.id,
    )
    class_ = models.Class(
        organization_id=organization.id,
        name="10A",
        size=20,
        start_year=2025,
        end_year=2026,
        grade_level=10,
        course_id=course.id,
    )
    db_session.add_all([state, class_])
    await db_session.flush()
    db_session.add_all(
        [
            models.Module(
                organization_id=organization.id,
                name="Runtime Module",
                code="RUN-1",
                hours_total=1,
                order=1,
                subject_id=subject.id,
            ),
            models.ClassSubjectLink(
                organization_id=organization.id,
                class_id=class_.id,
                subject_id=subject.id,
                grade_level=class_.grade_level,
                teacher_id=teacher.id,
            ),
        ]
    )
    await db_session.commit()
    return {
        "organization": organization,
        "user": user,
        "school_year": school_year,
        "state": state,
        "class": class_,
        "subject": subject,
        "teacher": teacher,
        "room": room,
        "slot": slot,
    }


def _valid_result(ctx) -> ValidatedGenerationResult:
    return ValidatedGenerationResult(
        result_category=models.ScheduleGenerationResultCategory.COMPLETE_SUCCESS,
        projected_completion_date=date(2026, 6, 30),
        hard_end_date=ctx["school_year"].hard_end_date,
        blocks=(
            DraftBlockSpec(
                stable_block_key="block-1",
                class_id=ctx["class"].id,
                subject_id=ctx["subject"].id,
                teacher_id=ctx["teacher"].id,
                room_id=ctx["room"].id,
                room_type_id=models.RoomType.normal,
                date=date(2025, 9, 2),
                timeslot_id=ctx["slot"].id,
                duration_minutes=60,
                module_sequence_index=1,
                change_type=models.ScheduleDraftBlockChangeType.ADDED,
            ),
        ),
        summary={"block_count": 1},
    )


async def _queue_job(db_session, ctx, key: str, *, replace_pending=False):
    selection = await SchedulerGenerationService(db_session).select_strategy(
        ctx["organization"].id,
        replace_pending_draft=replace_pending,
    )
    handle = await SchedulerJobService(db_session).create_or_get_job(
        selection,
        requested_by_user_id=ctx["user"].id,
        idempotency_key=key,
    )
    await db_session.commit()
    return handle.job


@pytest.mark.asyncio
async def test_success_commits_validated_draft_only_at_end(db_session):
    ctx = await _runtime_context(db_session)
    job = await _queue_job(db_session, ctx, "success-1")

    async def engine(execution):
        assert execution.immutable_snapshot["generation_input_fingerprint"]
        assert execution.solve_deadline_at < execution.deadline_at
        assert not (
            await db_session.scalars(
                select(models.ScheduleDraft).where(
                    models.ScheduleDraft.generation_job_id == execution.job_id
                )
            )
        ).all()
        return _valid_result(ctx)

    finished = await SchedulerJobRuntime(db_session).execute(job.id, engine)

    assert finished.job_status == models.ScheduleGenerationJobStatus.SUCCEEDED, (
        finished.failure_message
    )
    assert finished.started_at is not None
    assert finished.deadline_at - finished.started_at == timedelta(minutes=5)
    drafts = (
        await db_session.scalars(
            select(models.ScheduleDraft).where(
                models.ScheduleDraft.generation_job_id == job.id
            )
        )
    ).all()
    assert len(drafts) == 1
    assert drafts[0].draft_state == models.ScheduleDraftState.PENDING
    await db_session.refresh(ctx["state"])
    assert ctx["state"].pending_draft_id == drafts[0].id
    assert not (
        await db_session.scalars(select(models.ActiveScheduleBlock))
    ).all()


@pytest.mark.asyncio
async def test_runtime_emits_started_and_success_lifecycle_events(
    db_session,
    monkeypatch,
):
    ctx = await _runtime_context(db_session)
    job = await _queue_job(db_session, ctx, "observability-success")
    events = []
    monkeypatch.setattr(
        runtime_module,
        "emit_scheduler_job_event",
        lambda event_name, _job, **fields: events.append((event_name, fields)),
    )

    async def engine(_execution):
        return _valid_result(ctx)

    await SchedulerJobRuntime(db_session).execute(job.id, engine)

    assert [event[0] for event in events] == [
        "generation_started",
        "generation_succeeded",
    ]
    assert events[-1][1]["draft_id"] is not None
    assert events[-1][1]["result"].result_category == (
        models.ScheduleGenerationResultCategory.COMPLETE_SUCCESS
    )


@pytest.mark.asyncio
async def test_runtime_emits_no_output_and_timeout_categories(db_session, monkeypatch):
    ctx = await _runtime_context(db_session)
    events = []
    monkeypatch.setattr(
        runtime_module,
        "emit_scheduler_job_event",
        lambda event_name, _job, **fields: events.append((event_name, fields)),
    )
    no_output_job = await _queue_job(db_session, ctx, "observability-no-output")

    async def no_output(_execution):
        return NoValidGenerationOutput(blockers=("No hard-valid candidate.",))

    await SchedulerJobRuntime(db_session).execute(no_output_job.id, no_output)
    timeout_job = await _queue_job(db_session, ctx, "observability-timeout")
    now = [datetime.now(timezone.utc)]

    async def timeout(_execution):
        now[0] += timedelta(minutes=5, seconds=1)
        return _valid_result(ctx)

    await SchedulerJobRuntime(db_session, clock=lambda: now[0]).execute(
        timeout_job.id,
        timeout,
    )

    assert [event[0] for event in events] == [
        "generation_started",
        "generation_no_valid_output",
        "generation_started",
        "generation_timed_out",
    ]
    assert events[1][1]["hard_constraint_failures"] == 1


@pytest.mark.asyncio
async def test_real_complete_engine_persists_full_pending_draft(db_session):
    ctx = await _runtime_context(db_session)
    job = await _queue_job(db_session, ctx, "real-complete-engine")

    finished = await SchedulerJobRuntime(db_session).execute(
        job.id,
        run_complete_generation,
    )

    assert finished.job_status == models.ScheduleGenerationJobStatus.SUCCEEDED, (
        finished.failure_message
    )
    draft = await db_session.scalar(
        select(models.ScheduleDraft).where(
            models.ScheduleDraft.generation_job_id == job.id
        )
    )
    assert draft is not None
    assert draft.result_category == models.ScheduleGenerationResultCategory.COMPLETE_SUCCESS
    blocks = (
        await db_session.scalars(
            select(models.ScheduleDraftBlock).where(
                models.ScheduleDraftBlock.draft_id == draft.id
            )
        )
    ).all()
    assert len(blocks) == 1
    assert blocks[0].duration_minutes == 60
    assert blocks[0].module_sequence_index == 1
    diff = await SchedulerDiffService(db_session).list_diff(
        ctx["organization"].id,
        draft.id,
    )
    assert diff is not None and len(diff) == 1
    assert diff[0].change_type == "ADDED"
    assert diff[0].before_snapshot is None
    assert diff[0].after_draft_block_id == blocks[0].id


@pytest.mark.asyncio
async def test_approval_preconditions_accept_current_complete_draft(db_session):
    ctx = await _runtime_context(db_session)
    job = await _queue_job(db_session, ctx, "approval-current-complete")
    await SchedulerJobRuntime(db_session).execute(job.id, run_complete_generation)
    draft = await db_session.scalar(
        select(models.ScheduleDraft).where(
            models.ScheduleDraft.generation_job_id == job.id
        )
    )

    validated = await SchedulerApprovalService(db_session).validate_preconditions(
        ctx["organization"].id,
        draft.id,
        decided_by_user_id=ctx["user"].id,
    )

    assert validated.id == draft.id
    assert validated.draft_state == models.ScheduleDraftState.PENDING


@pytest.mark.asyncio
async def test_approval_preconditions_mark_changed_complete_draft_stale(db_session):
    ctx = await _runtime_context(db_session)
    job = await _queue_job(db_session, ctx, "approval-stale-complete")
    await SchedulerJobRuntime(db_session).execute(job.id, run_complete_generation)
    draft = await db_session.scalar(
        select(models.ScheduleDraft).where(
            models.ScheduleDraft.generation_job_id == job.id
        )
    )
    db_session.add(
        models.Room(
            organization_id=ctx["organization"].id,
            name="New room after generation",
            type=models.RoomType.normal,
            capacity=30,
        )
    )
    await db_session.commit()

    with pytest.raises(DraftApprovalConflictError) as raised:
        await SchedulerApprovalService(db_session).validate_preconditions(
            ctx["organization"].id,
            draft.id,
            decided_by_user_id=ctx["user"].id,
        )
    await db_session.commit()

    assert raised.value.draft_state == models.ScheduleDraftState.STALE
    await db_session.refresh(draft)
    await db_session.refresh(ctx["state"])
    assert draft.draft_state == models.ScheduleDraftState.STALE
    assert "Schedule conditions changed" in draft.stale_reason
    assert ctx["state"].pending_draft_id is None
    assert not (await db_session.scalars(select(models.ActiveScheduleBlock))).all()


@pytest.mark.asyncio
async def test_complete_approval_atomically_publishes_exact_target(db_session):
    ctx = await _runtime_context(db_session)
    job = await _queue_job(db_session, ctx, "approve-complete")
    await SchedulerJobRuntime(db_session).execute(job.id, run_complete_generation)
    draft = await db_session.scalar(
        select(models.ScheduleDraft).where(
            models.ScheduleDraft.generation_job_id == job.id
        )
    )
    target = list(
        await db_session.scalars(
            select(models.ScheduleDraftBlock).where(
                models.ScheduleDraftBlock.draft_id == draft.id
            )
        )
    )
    assert not (await db_session.scalars(select(models.ActiveScheduleBlock))).all()

    result = await SchedulerApprovalService(db_session).approve(
        ctx["organization"].id,
        draft.id,
        decided_by_user_id=ctx["user"].id,
    )
    await db_session.commit()

    active = list(
        await db_session.scalars(
            select(models.ActiveScheduleBlock).where(
                models.ActiveScheduleBlock.organization_id == ctx["organization"].id,
                models.ActiveScheduleBlock.school_year_id == ctx["school_year"].id,
                models.ActiveScheduleBlock.status == models.ActiveScheduleBlockStatus.ACTIVE,
            )
        )
    )
    assert result.active_block_count == len(target) == len(active) == 1
    assert {
        (
            row.stable_block_key,
            row.class_id,
            row.subject_id,
            row.teacher_id,
            row.room_id,
            row.date,
            row.timeslot_id,
            row.duration_minutes,
        )
        for row in active
    } == {
        (
            row.stable_block_key,
            row.class_id,
            row.subject_id,
            row.teacher_id,
            row.room_id,
            row.date,
            row.timeslot_id,
            row.duration_minutes,
        )
        for row in target
    }
    assert active[0].source_draft_block_id == target[0].id
    await db_session.refresh(draft)
    await db_session.refresh(ctx["state"])
    assert draft.draft_state == models.ScheduleDraftState.APPROVED
    assert draft.decided_by_user_id == ctx["user"].id
    assert ctx["state"].school_year_publication_state == (
        models.SchoolYearPublicationState.PUBLISHED
    )
    assert ctx["state"].pending_draft_id is None
    assert ctx["state"].active_schedule_version_id == f"draft-{draft.id}"
    assert ctx["state"].approved_scheduler_state_version == (
        ctx["state"].scheduler_state_version
    )
    assert await SchedulerDiffService(db_session).list_diff(
        ctx["organization"].id,
        draft.id,
    )


@pytest.mark.asyncio
async def test_approval_rejects_demand_result_mismatch_without_publication(db_session):
    ctx = await _runtime_context(db_session)
    job = await _queue_job(db_session, ctx, "approval-demand-mismatch")
    await SchedulerJobRuntime(db_session).execute(job.id, run_complete_generation)
    draft = await db_session.scalar(
        select(models.ScheduleDraft).where(
            models.ScheduleDraft.generation_job_id == job.id
        )
    )
    state_id = ctx["state"].id
    draft_id = draft.id
    block = await db_session.scalar(
        select(models.ScheduleDraftBlock).where(
            models.ScheduleDraftBlock.draft_id == draft.id
        )
    )
    block.duration_minutes -= 1
    await db_session.commit()

    with pytest.raises(DraftApprovalConflictError, match="demand"):
        await SchedulerApprovalService(db_session).approve(
            ctx["organization"].id,
            draft.id,
            decided_by_user_id=ctx["user"].id,
        )
    await db_session.rollback()
    db_session.expire_all()

    state = await db_session.get(models.SchedulerSchoolYearState, state_id)
    assert state.pending_draft_id == draft_id
    assert not (await db_session.scalars(select(models.ActiveScheduleBlock))).all()


@pytest.mark.asyncio
async def test_approval_rejects_recovery_link_on_non_recovery_target(db_session):
    ctx = await _runtime_context(db_session)
    job = await _queue_job(db_session, ctx, "approval-recovery-integrity")
    await SchedulerJobRuntime(db_session).execute(job.id, run_complete_generation)
    draft = await db_session.scalar(
        select(models.ScheduleDraft).where(
            models.ScheduleDraft.generation_job_id == job.id
        )
    )
    state_id = ctx["state"].id
    draft_id = draft.id
    block = await db_session.scalar(
        select(models.ScheduleDraftBlock).where(
            models.ScheduleDraftBlock.draft_id == draft.id
        )
    )
    occurrence = models.LessonOccurrence(
        organization_id=ctx["organization"].id,
        date=block.date,
        class_id=block.class_id,
        subject_id=block.subject_id,
        status=models.LessonOccurrenceStatus.GAP,
        revision=1,
        planned_hours=1,
        hours_given=0,
    )
    db_session.add(occurrence)
    await db_session.flush()
    db_session.add(
        models.PlannedRecoveryLink(
            organization_id=ctx["organization"].id,
            school_year_id=ctx["school_year"].id,
            debt_occurrence_id=occurrence.id,
            debt_occurrence_revision=occurrence.revision,
            planned_draft_block_id=block.id,
            planned_recovery_minutes=block.duration_minutes,
            class_id=block.class_id,
            subject_id=block.subject_id,
            teacher_id=block.teacher_id,
        )
    )
    await db_session.commit()

    with pytest.raises(DraftApprovalConflictError, match="recovery blocks"):
        await SchedulerApprovalService(db_session).approve(
            ctx["organization"].id,
            draft.id,
            decided_by_user_id=ctx["user"].id,
        )
    await db_session.rollback()
    db_session.expire_all()

    state = await db_session.get(models.SchedulerSchoolYearState, state_id)
    assert state.pending_draft_id == draft_id
    assert not (await db_session.scalars(select(models.ActiveScheduleBlock))).all()


@pytest.mark.asyncio
async def test_repair_approval_reconciles_moved_added_and_removed_blocks(db_session, monkeypatch):
    ctx = await _runtime_context(db_session)
    source_job = await _queue_job(db_session, ctx, "repair-reconcile-source")
    await SchedulerJobRuntime(db_session).execute(source_job.id, run_complete_generation)
    source_draft = await db_session.scalar(
        select(models.ScheduleDraft).where(
            models.ScheduleDraft.generation_job_id == source_job.id
        )
    )
    source_block = await db_session.scalar(
        select(models.ScheduleDraftBlock).where(
            models.ScheduleDraftBlock.draft_id == source_draft.id
        )
    )
    source_block.date = date(2026, 6, 30)
    second_source = models.ScheduleDraftBlock(
        organization_id=ctx["organization"].id,
        school_year_id=ctx["school_year"].id,
        draft_id=source_draft.id,
        stable_block_key="published-second",
        class_id=ctx["class"].id,
        subject_id=ctx["subject"].id,
        teacher_id=ctx["teacher"].id,
        room_id=ctx["room"].id,
        room_type_id=models.RoomType.normal,
        date=date(2026, 7, 14),
        timeslot_id=ctx["slot"].id,
        duration_minutes=60,
        module_sequence_index=1,
        change_type=models.ScheduleDraftBlockChangeType.ADDED,
    )
    db_session.add(second_source)
    await db_session.flush()
    first_active = models.ActiveScheduleBlock(
        organization_id=ctx["organization"].id,
        school_year_id=ctx["school_year"].id,
        schedule_version_id="published-v1",
        stable_block_key=source_block.stable_block_key,
        class_id=source_block.class_id,
        subject_id=source_block.subject_id,
        teacher_id=source_block.teacher_id,
        room_id=source_block.room_id,
        date=source_block.date,
        timeslot_id=source_block.timeslot_id,
        duration_minutes=source_block.duration_minutes,
        source_draft_block_id=source_block.id,
    )
    second_active = models.ActiveScheduleBlock(
        organization_id=ctx["organization"].id,
        school_year_id=ctx["school_year"].id,
        schedule_version_id="published-v1",
        stable_block_key=second_source.stable_block_key,
        class_id=second_source.class_id,
        subject_id=second_source.subject_id,
        teacher_id=second_source.teacher_id,
        room_id=second_source.room_id,
        date=second_source.date,
        timeslot_id=second_source.timeslot_id,
        duration_minutes=second_source.duration_minutes,
        source_draft_block_id=second_source.id,
    )
    db_session.add_all(
        [
            first_active,
            second_active,
            models.OrganizationSettings(
                organization_id=ctx["organization"].id,
                repair_stability_window_days=0,
            ),
        ]
    )
    source_draft.draft_state = models.ScheduleDraftState.APPROVED
    source_draft.decided_by_user_id = ctx["user"].id
    source_draft.decided_at = datetime.now(timezone.utc)
    ctx["state"].pending_draft_id = None
    ctx["state"].school_year_publication_state = models.SchoolYearPublicationState.PUBLISHED
    ctx["state"].active_schedule_version_id = "published-v1"
    ctx["state"].scheduler_state_version = 1
    ctx["state"].approved_scheduler_state_version = 0
    await db_session.commit()

    repair_job = await _queue_job(db_session, ctx, "repair-reconcile-target")
    fixed_now = datetime(2026, 6, 23, 12, tzinfo=timezone.utc)
    original_policy_snapshot = SchedulerFingerprintService.repair_policy_snapshot

    async def fixed_policy_snapshot(service, organization_id, school_year_id, **_kwargs):
        return await original_policy_snapshot(
            service,
            organization_id,
            school_year_id,
            now=fixed_now,
        )

    monkeypatch.setattr(
        SchedulerFingerprintService,
        "repair_policy_snapshot",
        fixed_policy_snapshot,
    )

    async def changed_target(execution):
        return ValidatedGenerationResult(
            result_category=models.ScheduleGenerationResultCategory.COMPLETE_SUCCESS,
            projected_completion_date=date(2026, 7, 14),
            hard_end_date=ctx["school_year"].hard_end_date,
            blocks=(
                DraftBlockSpec(
                    stable_block_key=first_active.stable_block_key,
                    source_active_block_id=first_active.id,
                    class_id=ctx["class"].id,
                    subject_id=ctx["subject"].id,
                    teacher_id=ctx["teacher"].id,
                    room_id=ctx["room"].id,
                    room_type_id=models.RoomType.normal,
                    date=date(2026, 7, 7),
                    timeslot_id=ctx["slot"].id,
                    duration_minutes=60,
                    change_type=models.ScheduleDraftBlockChangeType.MOVED,
                    reason_code="CALENDAR_REFLOW",
                ),
                DraftBlockSpec(
                    stable_block_key="new-target-block",
                    class_id=ctx["class"].id,
                    subject_id=ctx["subject"].id,
                    teacher_id=ctx["teacher"].id,
                    room_id=ctx["room"].id,
                    room_type_id=models.RoomType.normal,
                    date=date(2026, 7, 14),
                    timeslot_id=ctx["slot"].id,
                    duration_minutes=60,
                    change_type=models.ScheduleDraftBlockChangeType.ADDED,
                    reason_code="SCHEDULER_CHANGE_REFIT",
                ),
            ),
            summary={
                "recovered_minutes": 0,
                "remaining_unscheduled_minutes": 0,
                "disruption_score": 20,
            },
            adaptation_level="CALENDAR_GRID_REFLOW",
            metrics={"recovered_minutes": 0, "residual_debt_minutes": 0},
        )

    finished = await SchedulerJobRuntime(db_session).execute(
        repair_job.id,
        changed_target,
    )
    assert finished.job_status == models.ScheduleGenerationJobStatus.SUCCEEDED, (
        finished.failure_message
    )
    repair_draft = await db_session.scalar(
        select(models.ScheduleDraft).where(
            models.ScheduleDraft.generation_job_id == repair_job.id
        )
    )
    diff = await SchedulerDiffService(db_session).list_diff(
        ctx["organization"].id,
        repair_draft.id,
    )
    assert {row.change_type for row in diff} == {"MOVED", "ADDED", "REMOVED"}

    await SchedulerApprovalService(db_session).approve(
        ctx["organization"].id,
        repair_draft.id,
        decided_by_user_id=ctx["user"].id,
    )
    await db_session.commit()

    active_target = list(
        await db_session.scalars(
            select(models.ActiveScheduleBlock).where(
                models.ActiveScheduleBlock.organization_id == ctx["organization"].id,
                models.ActiveScheduleBlock.school_year_id == ctx["school_year"].id,
                models.ActiveScheduleBlock.status == models.ActiveScheduleBlockStatus.ACTIVE,
            )
        )
    )
    assert {(row.stable_block_key, row.date) for row in active_target} == {
        (first_active.stable_block_key, date(2026, 7, 7)),
        ("new-target-block", date(2026, 7, 14)),
    }
    await db_session.refresh(first_active)
    await db_session.refresh(second_active)
    assert first_active.status == models.ActiveScheduleBlockStatus.REMOVED
    assert second_active.status == models.ActiveScheduleBlockStatus.REMOVED


@pytest.mark.asyncio
async def test_reject_retains_draft_blocks_and_diff_audit(db_session):
    ctx = await _runtime_context(db_session)
    job = await _queue_job(db_session, ctx, "reject-audit")
    await SchedulerJobRuntime(db_session).execute(job.id, run_complete_generation)
    draft = await db_session.scalar(
        select(models.ScheduleDraft).where(
            models.ScheduleDraft.generation_job_id == job.id
        )
    )
    block_ids = set(
        await db_session.scalars(
            select(models.ScheduleDraftBlock.id).where(
                models.ScheduleDraftBlock.draft_id == draft.id
            )
        )
    )
    diff_ids = {
        row.id
        for row in await SchedulerDiffService(db_session).list_diff(
            ctx["organization"].id,
            draft.id,
        )
    }

    result = await SchedulerLifecycleService(db_session).reject_draft(
        ctx["organization"].id,
        draft.id,
        decided_by_user_id=ctx["user"].id,
    )
    await db_session.commit()

    assert result.draft_state == "REJECTED"
    await db_session.refresh(draft)
    await db_session.refresh(ctx["state"])
    assert draft.draft_state == models.ScheduleDraftState.REJECTED
    assert draft.decided_by_user_id == ctx["user"].id
    assert ctx["state"].pending_draft_id is None
    assert set(
        await db_session.scalars(
            select(models.ScheduleDraftBlock.id).where(
                models.ScheduleDraftBlock.draft_id == draft.id
            )
        )
    ) == block_ids
    assert {
        row.id
        for row in await SchedulerDiffService(db_session).list_diff(
            ctx["organization"].id,
            draft.id,
        )
    } == diff_ids


@pytest.mark.asyncio
async def test_reset_year_cancels_active_schedule_and_restores_first_generation(db_session):
    ctx = await _runtime_context(db_session)
    job = await _queue_job(db_session, ctx, "reset-published-source")
    await SchedulerJobRuntime(db_session).execute(job.id, run_complete_generation)
    draft = await db_session.scalar(
        select(models.ScheduleDraft).where(
            models.ScheduleDraft.generation_job_id == job.id
        )
    )
    await SchedulerApprovalService(db_session).approve(
        ctx["organization"].id,
        draft.id,
        decided_by_user_id=ctx["user"].id,
    )
    await db_session.commit()
    active = list(
        await db_session.scalars(
            select(models.ActiveScheduleBlock).where(
                models.ActiveScheduleBlock.status == models.ActiveScheduleBlockStatus.ACTIVE
            )
        )
    )
    assert active

    reset = await SchedulerLifecycleService(db_session).reset_year(
        ctx["organization"].id,
        reset_by_user_id=ctx["user"].id,
        confirmed=True,
    )
    await db_session.commit()

    assert reset.school_year_publication_state == "UNPUBLISHED"
    assert reset.canceled_active_blocks == len(active)
    for row in active:
        await db_session.refresh(row)
        assert row.status == models.ActiveScheduleBlockStatus.CANCELED
    await db_session.refresh(ctx["state"])
    assert ctx["state"].active_schedule_version_id is None
    assert ctx["state"].approved_scheduler_state_version is None
    assert ctx["state"].reset_by_user_id == ctx["user"].id
    status = await SchedulerStatusService(db_session).get_status(
        ctx["organization"].id
    )
    assert status.primary_action == "GENERATE_SCHEDULE"
    assert status.trigger_type == "FIRST_GENERATION"


@pytest.mark.asyncio
async def test_real_adaptive_engine_persists_valid_partial_target_and_links(
    db_session,
    monkeypatch,
):
    ctx = await _runtime_context(db_session)
    complete_job = await _queue_job(db_session, ctx, "adaptive-source")
    await SchedulerJobRuntime(db_session).execute(complete_job.id, run_complete_generation)
    source_draft = await db_session.scalar(
        select(models.ScheduleDraft).where(
            models.ScheduleDraft.generation_job_id == complete_job.id
        )
    )
    source_block = await db_session.scalar(
        select(models.ScheduleDraftBlock).where(
            models.ScheduleDraftBlock.draft_id == source_draft.id
        )
    )
    now = datetime.now(timezone.utc)
    source_draft.draft_state = models.ScheduleDraftState.APPROVED
    source_draft.decided_by_user_id = ctx["user"].id
    source_draft.decided_at = now
    active = models.ActiveScheduleBlock(
        organization_id=ctx["organization"].id,
        school_year_id=ctx["school_year"].id,
        schedule_version_id="approved-v1",
        stable_block_key=source_block.stable_block_key,
        class_id=source_block.class_id,
        subject_id=source_block.subject_id,
        teacher_id=source_block.teacher_id,
        room_id=source_block.room_id,
        date=source_block.date,
        timeslot_id=source_block.timeslot_id,
        duration_minutes=source_block.duration_minutes,
        source_draft_block_id=source_block.id,
    )
    lesson = models.Lesson(
        organization_id=ctx["organization"].id,
        class_id=ctx["class"].id,
        subject_id=ctx["subject"].id,
        teacher_id=ctx["teacher"].id,
    )
    settings = models.OrganizationSettings(
        organization_id=ctx["organization"].id,
        repair_stability_window_days=0,
    )
    db_session.add_all([active, lesson, settings])
    await db_session.flush()
    legacy_output = models.ScheduleOutput(
        organization_id=ctx["organization"].id,
        lesson_id=lesson.id,
        timeslot_id=ctx["slot"].id,
        room_id=ctx["room"].id,
        generation_id="legacy-debt-source",
        date=date(2026, 6, 16),
        is_draft=False,
    )
    db_session.add(legacy_output)
    await db_session.flush()
    debt = models.LessonOccurrence(
        organization_id=ctx["organization"].id,
        schedule_output_id=legacy_output.id,
        date=date(2026, 6, 16),
        class_id=ctx["class"].id,
        subject_id=ctx["subject"].id,
        status=models.LessonOccurrenceStatus.GAP,
        revision=2,
        is_active=True,
        planned_timeslot_id=ctx["slot"].id,
        planned_room_id=ctx["room"].id,
        planned_hours=5.0,
        planned_teacher_id=ctx["teacher"].id,
        hours_given=0.0,
    )
    db_session.add(debt)
    ctx["state"].school_year_publication_state = models.SchoolYearPublicationState.PUBLISHED
    ctx["state"].active_schedule_version_id = "approved-v1"
    ctx["state"].pending_draft_id = None
    ctx["state"].approved_scheduler_state_version = ctx["state"].scheduler_state_version
    await db_session.commit()

    repair_job = await _queue_job(db_session, ctx, "real-adaptive-partial")
    fixed_now = datetime(2026, 6, 23, 12, tzinfo=timezone.utc)
    original_policy_snapshot = SchedulerFingerprintService.repair_policy_snapshot

    async def fixed_policy_snapshot(service, organization_id, school_year_id, **_kwargs):
        return await original_policy_snapshot(
            service,
            organization_id,
            school_year_id,
            now=fixed_now,
        )

    monkeypatch.setattr(
        SchedulerFingerprintService,
        "repair_policy_snapshot",
        fixed_policy_snapshot,
    )
    finished = await SchedulerJobRuntime(db_session).execute(
        repair_job.id,
        run_adaptive_repair,
    )

    assert finished.job_status == models.ScheduleGenerationJobStatus.SUCCEEDED
    draft = await db_session.scalar(
        select(models.ScheduleDraft).where(
            models.ScheduleDraft.generation_job_id == repair_job.id
        )
    )
    assert draft.result_category == models.ScheduleGenerationResultCategory.PARTIAL_RECOVERY
    assert draft.summary_json["recovered_minutes"] == 240
    assert draft.summary_json["remaining_unscheduled_minutes"] == 60
    assert draft.main_blocker_message == (
        "The remaining hours cannot fit with the current resources and hard end date."
    )
    target_blocks = (
        await db_session.scalars(
            select(models.ScheduleDraftBlock).where(
                models.ScheduleDraftBlock.draft_id == draft.id
            )
        )
    ).all()
    recovery_blocks = [row for row in target_blocks if row.is_recovery_block]
    assert len(target_blocks) == 5
    assert len(recovery_blocks) == 4
    assert {row.recovery_source_occurrence_id for row in recovery_blocks} == {debt.id}
    assert {row.recovery_source_occurrence_revision for row in recovery_blocks} == {2}
    links = (
        await db_session.scalars(
            select(models.PlannedRecoveryLink).where(
                models.PlannedRecoveryLink.planned_draft_block_id.in_(
                    [row.id for row in recovery_blocks]
                )
            )
        )
    ).all()
    assert len(links) == 4
    assert sum(row.planned_recovery_minutes for row in links) == 240
    summary = await SchedulerDraftService(db_session).current_summary(
        ctx["organization"].id
    )
    assert summary.draft_id == draft.id
    assert summary.result_category == "PARTIAL_RECOVERY"
    assert summary.debt_hours_before == 5
    assert summary.debt_hours_recovered == 4
    assert summary.debt_hours_remaining == 1
    assert summary.changed_blocks == 4
    assert summary.affected_classes == 1
    assert summary.affected_teachers == 1
    assert summary.affected_days == 4
    assert summary.main_blocker_message == draft.main_blocker_message
    assert summary.can_approve is True
    diff = await SchedulerDiffService(db_session).list_diff(
        ctx["organization"].id,
        draft.id,
    )
    assert diff is not None and len(diff) == 4
    assert {row.change_type for row in diff} == {"ADDED"}
    assert all(row.recovery_link_impact is not None for row in diff)
    assert active.id not in {row.before_active_block_id for row in diff}
    residual = await SchedulerFingerprintService(db_session).debt_basis_fingerprint(
        ctx["organization"].id,
        ctx["school_year"].id,
    )
    assert residual is not None
    assert residual.unresolved_debt_minutes == 300

    approval = await SchedulerApprovalService(db_session).approve(
        ctx["organization"].id,
        draft.id,
        decided_by_user_id=ctx["user"].id,
    )
    await db_session.commit()

    active_after = list(
        await db_session.scalars(
            select(models.ActiveScheduleBlock).where(
                models.ActiveScheduleBlock.organization_id == ctx["organization"].id,
                models.ActiveScheduleBlock.school_year_id == ctx["school_year"].id,
                models.ActiveScheduleBlock.status == models.ActiveScheduleBlockStatus.ACTIVE,
            )
        )
    )
    assert approval.active_block_count == len(active_after) == 5
    assert active.id in {row.id for row in active_after}
    assert sum(row.is_recovery_block for row in active_after) == 4
    await db_session.refresh(active)
    assert active.schedule_version_id == f"draft-{draft.id}"
    for link in links:
        await db_session.refresh(link)
        assert link.status == models.PlannedRecoveryLinkStatus.PLANNED
        assert link.planned_active_block_id is not None
        assert link.planned_draft_block_id is None
    residual_after_approval = (
        await SchedulerFingerprintService(db_session).debt_basis_fingerprint(
            ctx["organization"].id,
            ctx["school_year"].id,
        )
    )
    assert residual_after_approval is not None
    assert residual_after_approval.unresolved_debt_minutes == 60
    await db_session.refresh(draft)
    await db_session.refresh(ctx["state"])
    assert draft.draft_state == models.ScheduleDraftState.APPROVED
    assert ctx["state"].pending_draft_id is None
    assert ctx["state"].active_schedule_version_id == f"draft-{draft.id}"


@pytest.mark.asyncio
async def test_no_output_and_validation_failure_create_no_draft(db_session):
    ctx = await _runtime_context(db_session)
    first = await _queue_job(db_session, ctx, "no-output")

    async def no_output(_execution):
        return NoValidGenerationOutput(
            blockers=("No eligible room remains before the hard end date.",)
        )

    no_output_job = await SchedulerJobRuntime(db_session).execute(first.id, no_output)
    assert no_output_job.job_status == models.ScheduleGenerationJobStatus.NO_VALID_OUTPUT
    assert no_output_job.failure_code == "NO_VALID_OUTPUT"
    assert "No eligible room" in no_output_job.failure_message

    second = await _queue_job(db_session, ctx, "invalid")
    invalid = _valid_result(ctx)
    duplicate = invalid.blocks[0]

    async def invalid_engine(_execution):
        return ValidatedGenerationResult(
            result_category=invalid.result_category,
            projected_completion_date=invalid.projected_completion_date,
            hard_end_date=invalid.hard_end_date,
            blocks=(duplicate, duplicate),
            summary={},
        )

    invalid_job = await SchedulerJobRuntime(db_session).execute(
        second.id,
        invalid_engine,
    )
    assert invalid_job.job_status == models.ScheduleGenerationJobStatus.FAILED
    assert invalid_job.failure_code == "FAILED_VALIDATION"
    assert not (await db_session.scalars(select(models.ScheduleDraft))).all()
    await db_session.refresh(ctx["state"])
    assert ctx["state"].pending_draft_id is None


@pytest.mark.asyncio
async def test_replacement_is_atomic_across_failure_and_success(db_session):
    ctx = await _runtime_context(db_session)
    initial_job = await _queue_job(db_session, ctx, "initial")

    async def valid(_execution):
        return _valid_result(ctx)

    await SchedulerJobRuntime(db_session).execute(initial_job.id, valid)
    old_draft = await db_session.scalar(
        select(models.ScheduleDraft).where(
            models.ScheduleDraft.generation_job_id == initial_job.id
        )
    )
    assert old_draft is not None

    failed_job = await _queue_job(
        db_session,
        ctx,
        "replacement-fails",
        replace_pending=True,
    )

    async def broken(_execution):
        raise RuntimeError("solver failed")

    failed = await SchedulerJobRuntime(db_session).execute(failed_job.id, broken)
    assert failed.failure_code == "SYSTEM_ERROR"
    await db_session.refresh(old_draft)
    await db_session.refresh(ctx["state"])
    assert old_draft.draft_state == models.ScheduleDraftState.PENDING
    assert ctx["state"].pending_draft_id == old_draft.id
    for instance in ctx.values():
        await db_session.refresh(instance)

    replacement_job = await _queue_job(
        db_session,
        ctx,
        "replacement-succeeds",
        replace_pending=True,
    )
    await SchedulerJobRuntime(db_session).execute(replacement_job.id, valid)
    await db_session.refresh(old_draft)
    await db_session.refresh(ctx["state"])
    new_draft = await db_session.scalar(
        select(models.ScheduleDraft).where(
            models.ScheduleDraft.generation_job_id == replacement_job.id
        )
    )
    assert new_draft is not None
    assert old_draft.draft_state == models.ScheduleDraftState.REPLACED
    assert old_draft.decided_at is not None
    assert new_draft.draft_state == models.ScheduleDraftState.PENDING
    assert ctx["state"].pending_draft_id == new_draft.id


@pytest.mark.parametrize(
    ("outcome", "expected_status", "expected_code"),
    (
        ("failure", models.ScheduleGenerationJobStatus.FAILED, "SYSTEM_ERROR"),
        ("cancel", models.ScheduleGenerationJobStatus.CANCELED, "CANCELED"),
        ("timeout", models.ScheduleGenerationJobStatus.FAILED, "TIMED_OUT"),
        (
            "no_output",
            models.ScheduleGenerationJobStatus.NO_VALID_OUTPUT,
            "NO_VALID_OUTPUT",
        ),
    ),
)
@pytest.mark.asyncio
async def test_replacement_terminal_outcomes_preserve_previous_pending_draft(
    db_session,
    outcome,
    expected_status,
    expected_code,
):
    ctx = await _runtime_context(db_session)
    initial_job = await _queue_job(db_session, ctx, f"preserve-{outcome}-initial")

    async def valid(_execution):
        return _valid_result(ctx)

    await SchedulerJobRuntime(db_session).execute(initial_job.id, valid)
    old_draft = await db_session.scalar(
        select(models.ScheduleDraft).where(
            models.ScheduleDraft.generation_job_id == initial_job.id
        )
    )
    replacement = await _queue_job(
        db_session,
        ctx,
        f"preserve-{outcome}-replacement",
        replace_pending=True,
    )
    now = [datetime.now(timezone.utc)]

    async def terminal(execution):
        if outcome == "failure":
            raise RuntimeError("replacement failed")
        if outcome == "cancel":
            running = await db_session.get(
                models.ScheduleGenerationJob,
                execution.job_id,
            )
            running.job_status = models.ScheduleGenerationJobStatus.CANCEL_REQUESTED
            await db_session.commit()
            await execution.ensure_can_continue()
        if outcome == "timeout":
            now[0] += timedelta(minutes=5, seconds=1)
            return _valid_result(ctx)
        return NoValidGenerationOutput(blockers=("No valid replacement.",))

    runtime = SchedulerJobRuntime(
        db_session,
        clock=(lambda: now[0]) if outcome == "timeout" else None,
    )
    finished = await runtime.execute(replacement.id, terminal)

    await db_session.refresh(old_draft)
    await db_session.refresh(ctx["state"])
    assert finished.job_status == expected_status
    assert finished.failure_code == expected_code
    assert old_draft.draft_state == models.ScheduleDraftState.PENDING
    assert ctx["state"].pending_draft_id == old_draft.id
    assert not (
        await db_session.scalars(
            select(models.ScheduleDraft).where(
                models.ScheduleDraft.generation_job_id == replacement.id
            )
        )
    ).all()


@pytest.mark.asyncio
async def test_repair_draft_becomes_stale_after_policy_change(db_session):
    ctx = await _runtime_context(db_session)
    complete_job = await _queue_job(db_session, ctx, "repair-stale-complete")
    await SchedulerJobRuntime(db_session).execute(
        complete_job.id,
        run_complete_generation,
    )
    complete_draft = await db_session.scalar(
        select(models.ScheduleDraft).where(
            models.ScheduleDraft.generation_job_id == complete_job.id
        )
    )
    await SchedulerApprovalService(db_session).approve(
        ctx["organization"].id,
        complete_draft.id,
        decided_by_user_id=ctx["user"].id,
    )
    settings = models.OrganizationSettings(
        organization_id=ctx["organization"].id,
        repair_stability_window_days=0,
    )
    db_session.add(settings)
    ctx["state"].scheduler_state_version += 1
    await db_session.commit()

    repair_job = await _queue_job(db_session, ctx, "repair-stale-policy")
    finished = await SchedulerJobRuntime(db_session).execute(
        repair_job.id,
        run_adaptive_repair,
    )
    assert finished.job_status == models.ScheduleGenerationJobStatus.SUCCEEDED
    repair_draft = await db_session.scalar(
        select(models.ScheduleDraft).where(
            models.ScheduleDraft.generation_job_id == repair_job.id
        )
    )
    settings.repair_stability_window_days = 1
    await db_session.commit()

    with pytest.raises(DraftApprovalConflictError) as raised:
        await SchedulerApprovalService(db_session).approve(
            ctx["organization"].id,
            repair_draft.id,
            decided_by_user_id=ctx["user"].id,
        )
    await db_session.commit()

    assert raised.value.draft_state == models.ScheduleDraftState.STALE
    await db_session.refresh(repair_draft)
    await db_session.refresh(ctx["state"])
    assert repair_draft.draft_state == models.ScheduleDraftState.STALE
    assert "repair policy changed" in repair_draft.stale_reason.lower()
    assert ctx["state"].pending_draft_id is None


@pytest.mark.asyncio
async def test_cancellation_during_engine_creates_no_draft(db_session):
    ctx = await _runtime_context(db_session)
    job = await _queue_job(db_session, ctx, "cancel-runtime")

    continued_after_checkpoint = False

    async def cancel(execution):
        nonlocal continued_after_checkpoint
        running_job = await db_session.get(models.ScheduleGenerationJob, execution.job_id)
        running_job.job_status = models.ScheduleGenerationJobStatus.CANCEL_REQUESTED
        await db_session.commit()
        await execution.ensure_can_continue()
        continued_after_checkpoint = True
        return _valid_result(ctx)

    finished = await SchedulerJobRuntime(db_session).execute(job.id, cancel)

    assert finished.job_status == models.ScheduleGenerationJobStatus.CANCELED
    assert finished.failure_code == "CANCELED"
    assert continued_after_checkpoint is False
    assert not (await db_session.scalars(select(models.ScheduleDraft))).all()


@pytest.mark.asyncio
async def test_cancellation_before_worker_start_is_finalized(db_session):
    ctx = await _runtime_context(db_session)
    job = await _queue_job(db_session, ctx, "cancel-before-start")
    await SchedulerJobService(db_session).request_cancellation(
        ctx["organization"].id,
        job.id,
    )
    await db_session.commit()

    async def must_not_run(_execution):
        raise AssertionError("Canceled queued job reached the generation engine.")

    finished = await SchedulerJobRuntime(db_session).execute(job.id, must_not_run)

    assert finished.job_status == models.ScheduleGenerationJobStatus.CANCELED
    assert finished.started_at is not None
    assert finished.finished_at >= finished.started_at
    assert not (await db_session.scalars(select(models.ScheduleDraft))).all()


@pytest.mark.asyncio
async def test_deadline_expiry_creates_no_draft(db_session):
    ctx = await _runtime_context(db_session)
    job = await _queue_job(db_session, ctx, "timeout-runtime")
    now = [datetime.now(timezone.utc)]

    async def exceed_deadline(_execution):
        now[0] += timedelta(minutes=5, seconds=1)
        return _valid_result(ctx)

    finished = await SchedulerJobRuntime(
        db_session,
        clock=lambda: now[0],
    ).execute(job.id, exceed_deadline)

    assert finished.job_status == models.ScheduleGenerationJobStatus.FAILED
    assert finished.failure_code == "TIMED_OUT"
    assert not (await db_session.scalars(select(models.ScheduleDraft))).all()


@pytest.mark.asyncio
async def test_validation_is_bounded_by_final_deadline_without_persisting_draft(
    db_session,
    monkeypatch,
):
    monkeypatch.setattr(runtime_module, "GENERATION_CAP_SECONDS", 3)
    monkeypatch.setattr(runtime_module, "FINAL_COMMIT_RESERVE_SECONDS", 1)
    ctx = await _runtime_context(db_session)
    job = await _queue_job(db_session, ctx, "validation-timeout")
    runtime = SchedulerJobRuntime(db_session)

    async def engine(_execution):
        return _valid_result(ctx)

    async def slow_validation(_context, _result):
        await asyncio.sleep(4)

    monkeypatch.setattr(runtime, "_validate_result", slow_validation)
    finished = await runtime.execute(job.id, engine)

    assert finished.job_status == models.ScheduleGenerationJobStatus.FAILED
    assert finished.failure_code == "TIMED_OUT"
    assert not (await db_session.scalars(select(models.ScheduleDraft))).all()


@pytest.mark.asyncio
async def test_concurrent_duplicate_generation_requests_converge_to_one_job(db_session):
    ctx = await _runtime_context(db_session)
    selection = await SchedulerGenerationService(db_session).select_strategy(
        ctx["organization"].id
    )

    async def create_job():
        async with TestingSessionLocal() as session:
            handle = await SchedulerJobService(session).create_or_get_job(
                selection,
                requested_by_user_id=ctx["user"].id,
                idempotency_key="concurrent-click",
            )
            await session.commit()
            return handle.job.id, handle.created

    first, second = await asyncio.gather(create_job(), create_job())

    assert first[0] == second[0]
    assert sorted((first[1], second[1])) == [False, True]
    jobs = (
        await db_session.scalars(
            select(models.ScheduleGenerationJob).where(
                models.ScheduleGenerationJob.organization_id
                == ctx["organization"].id,
                models.ScheduleGenerationJob.school_year_id
                == ctx["school_year"].id,
            )
        )
    ).all()
    assert [job.id for job in jobs] == [first[0]]


@pytest.mark.asyncio
async def test_concurrent_approval_publishes_exactly_once(db_session):
    ctx = await _runtime_context(db_session)
    job = await _queue_job(db_session, ctx, "concurrent-approval")
    organization_id = ctx["organization"].id
    school_year_id = ctx["school_year"].id
    user_id = ctx["user"].id
    await SchedulerJobRuntime(db_session).execute(job.id, run_complete_generation)
    draft = await db_session.scalar(
        select(models.ScheduleDraft).where(
            models.ScheduleDraft.generation_job_id == job.id
        )
    )

    async def approve():
        async with TestingSessionLocal() as session:
            try:
                result = await SchedulerApprovalService(session).approve(
                    organization_id,
                    draft.id,
                    decided_by_user_id=user_id,
                )
                await session.commit()
                return "approved", result.active_schedule_version_id
            except DraftApprovalConflictError:
                await session.rollback()
                return "conflict", None

    outcomes = await asyncio.gather(approve(), approve())

    assert sorted(outcome[0] for outcome in outcomes) == ["approved", "conflict"]
    db_session.expire_all()
    state = await db_session.scalar(
            select(models.SchedulerSchoolYearState).where(
                models.SchedulerSchoolYearState.organization_id
                == organization_id,
                models.SchedulerSchoolYearState.school_year_id == school_year_id,
        )
    )
    active = (
        await db_session.scalars(
                select(models.ActiveScheduleBlock).where(
                    models.ActiveScheduleBlock.organization_id
                    == organization_id,
                    models.ActiveScheduleBlock.school_year_id == school_year_id,
                models.ActiveScheduleBlock.status
                == models.ActiveScheduleBlockStatus.ACTIVE,
            )
        )
    ).all()
    assert state.school_year_publication_state == models.SchoolYearPublicationState.PUBLISHED
    assert state.pending_draft_id is None
    assert len(active) == 1
    assert active[0].schedule_version_id == state.active_schedule_version_id


@pytest.mark.asyncio
async def test_approval_endpoint_rolls_back_ordinary_integrity_conflicts(
    db_session,
    monkeypatch,
):
    ctx = await _runtime_context(db_session)
    state_id = ctx["state"].id

    async def fail_after_mutation(service, *_args, **_kwargs):
        state = await service._db.get(models.SchedulerSchoolYearState, state_id)
        state.lock_version = 99
        await service._db.flush()
        raise DraftApprovalConflictError(
            "Late integrity conflict.",
            models.ScheduleDraftState.PENDING,
        )

    monkeypatch.setattr(SchedulerApprovalService, "approve", fail_after_mutation)
    with pytest.raises(HTTPException) as raised:
        await approve_draft_endpoint(
            draft_id=999,
            db=db_session,
            current_user=ctx["user"],
        )

    assert raised.value.status_code == 409
    state = await db_session.get(models.SchedulerSchoolYearState, state_id)
    await db_session.refresh(state)
    assert state.lock_version == 0
