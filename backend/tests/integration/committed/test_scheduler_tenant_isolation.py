from datetime import UTC, date, datetime, time

from app import models
from app.services.scheduler_lifecycle_service import SchedulerLifecycleService
from app.services.scheduler_recovery_service import SchedulerRecoveryService
from tests._support.db_fixtures import (
    create_org_and_user,
    create_teacher_profile,
    ensure_membership_capabilities,
)


async def _tenant_bundle(db_session, suffix: str) -> dict[str, object]:
    organization, user = await create_org_and_user(
        db_session,
        clerk_user_id=f"scheduler_tenant_{suffix}",
        email=f"scheduler-tenant-{suffix}@example.com",
        role="admin",
        org_name=f"Scheduler Tenant {suffix}",
        clerk_org_id=f"org_scheduler_tenant_{suffix}",
    )
    membership = await ensure_membership_capabilities(
        db_session,
        organization_id=organization.id,
        user=user,
        capabilities=[models.MembershipCapability.admin],
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
        name=f"Course {suffix}",
        abbreviation=f"C{suffix}",
    )
    subject = models.Subject(
        organization_id=organization.id,
        name=f"Subject {suffix}",
        required_room_type=models.RoomType.normal,
    )
    teacher = await create_teacher_profile(
        db_session,
        organization_id=organization.id,
        name=f"Teacher {suffix}",
    )
    room = models.Room(
        organization_id=organization.id,
        name=f"Room {suffix}",
        type=models.RoomType.normal,
        capacity=30,
    )
    slot = models.Timeslot(
        organization_id=organization.id,
        day_of_week=1,
        start_time=time(9),
        end_time=time(10),
    )
    db_session.add_all([school_year, course, subject, teacher, room, slot])
    await db_session.flush()
    class_ = models.Class(
        organization_id=organization.id,
        name=f"Class {suffix}",
        size=20,
        start_year=2025,
        end_year=2026,
        grade_level=10,
        course_id=course.id,
    )
    state = models.SchedulerSchoolYearState(
        organization_id=organization.id,
        school_year_id=school_year.id,
    )
    db_session.add_all([class_, state])
    await db_session.flush()

    now = datetime.now(UTC)
    completed_job = models.ScheduleGenerationJob(
        organization_id=organization.id,
        school_year_id=school_year.id,
        requested_by_membership_id=membership.id,
        strategy=models.ScheduleGenerationStrategy.ADAPTIVE_REPAIR,
        trigger_type=models.ScheduleGenerationTrigger.EXPLICIT_DEBT,
        job_status=models.ScheduleGenerationJobStatus.SUCCEEDED,
        result_category=models.ScheduleGenerationResultCategory.PARTIAL_RECOVERY,
        queued_at=now,
        started_at=now,
        finished_at=now,
    )
    queued_job = models.ScheduleGenerationJob(
        organization_id=organization.id,
        school_year_id=school_year.id,
        requested_by_membership_id=membership.id,
        strategy=models.ScheduleGenerationStrategy.COMPLETE_GENERATION,
        trigger_type=models.ScheduleGenerationTrigger.FIRST_GENERATION,
        job_status=models.ScheduleGenerationJobStatus.QUEUED,
        queued_at=now,
    )
    db_session.add_all([completed_job, queued_job])
    await db_session.flush()
    draft = models.ScheduleDraft(
        organization_id=organization.id,
        school_year_id=school_year.id,
        generation_job_id=completed_job.id,
        strategy=models.ScheduleGenerationStrategy.ADAPTIVE_REPAIR,
        result_category=models.ScheduleGenerationResultCategory.PARTIAL_RECOVERY,
        trigger_type=models.ScheduleGenerationTrigger.EXPLICIT_DEBT,
        generation_input_fingerprint="a" * 64,
        scheduler_state_version_used=0,
        debt_basis_fingerprint="b" * 64,
        repair_policy_snapshot_json={
            "repair_stability_window_days": 0,
            "editable_start_date": "2025-09-01",
        },
        repair_policy_snapshot_hash="c" * 64,
        editable_start_date=date(2025, 9, 1),
        projected_completion_date=date(2026, 6, 30),
        hard_end_date=school_year.hard_end_date,
        summary_json={"recovered_minutes": 60, "remaining_unscheduled_minutes": 60},
        created_by_membership_id=membership.id,
    )
    db_session.add(draft)
    await db_session.flush()
    occurrence = models.LessonOccurrence(
        organization_id=organization.id,
        date=date(2025, 9, 1),
        class_id=class_.id,
        subject_id=subject.id,
        status=models.LessonOccurrenceStatus.GAP,
        revision=1,
        planned_hours=1,
        hours_given=0,
    )
    db_session.add(occurrence)
    await db_session.flush()
    draft_block = models.ScheduleDraftBlock(
        organization_id=organization.id,
        school_year_id=school_year.id,
        draft_id=draft.id,
        stable_block_key=f"recovery-{suffix}",
        class_id=class_.id,
        subject_id=subject.id,
        teacher_id=teacher.id,
        room_id=room.id,
        room_type_id=models.RoomType.normal,
        date=date(2025, 9, 2),
        timeslot_id=slot.id,
        duration_minutes=60,
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
        schedule_version_id=f"version-{suffix}",
        stable_block_key=f"recovery-{suffix}",
        class_id=class_.id,
        subject_id=subject.id,
        teacher_id=teacher.id,
        room_id=room.id,
        date=draft_block.date,
        timeslot_id=slot.id,
        duration_minutes=60,
        source_draft_block_id=draft_block.id,
        is_recovery_block=True,
    )
    db_session.add(active_block)
    await db_session.flush()
    recovery_link = models.PlannedRecoveryLink(
        organization_id=organization.id,
        school_year_id=school_year.id,
        debt_occurrence_id=occurrence.id,
        debt_occurrence_revision=occurrence.revision,
        planned_active_block_id=active_block.id,
        planned_recovery_minutes=60,
        class_id=class_.id,
        subject_id=subject.id,
        teacher_id=teacher.id,
    )
    db_session.add(recovery_link)
    state.pending_draft_id = draft.id
    await db_session.commit()
    return {
        "organization": organization,
        "user": user,
        "membership": membership,
        "school_year": school_year,
        "state": state,
        "queued_job": queued_job,
        "draft": draft,
        "active_block": active_block,
        "recovery_link": recovery_link,
    }


def _headers(suffix: str) -> dict[str, str]:
    return {"Authorization": f"Bearer scheduler_tenant_{suffix}"}


async def test_scheduler_api_rejects_cross_tenant_jobs_and_drafts(
    async_client,
    db_session,
):
    await _tenant_bundle(db_session, "a")
    tenant_b = await _tenant_bundle(db_session, "b")
    job_id = tenant_b["queued_job"].id
    draft_id = tenant_b["draft"].id
    responses = [
        await async_client.get(f"/api/v1/scheduler/jobs/{job_id}", headers=_headers("a")),
        await async_client.post(f"/api/v1/scheduler/jobs/{job_id}/cancel", headers=_headers("a")),
        await async_client.get(f"/api/v1/scheduler/drafts/{draft_id}", headers=_headers("a")),
        await async_client.get(f"/api/v1/scheduler/drafts/{draft_id}/diff", headers=_headers("a")),
        await async_client.post(
            f"/api/v1/scheduler/drafts/{draft_id}/approve", headers=_headers("a")
        ),
        await async_client.post(
            f"/api/v1/scheduler/drafts/{draft_id}/reject", headers=_headers("a")
        ),
    ]

    assert [response.status_code for response in responses] == [404] * len(responses)
    await db_session.refresh(tenant_b["queued_job"])
    await db_session.refresh(tenant_b["draft"])
    assert tenant_b["queued_job"].job_status == models.ScheduleGenerationJobStatus.QUEUED
    assert tenant_b["draft"].draft_state == models.ScheduleDraftState.PENDING


async def test_reset_and_recovery_mutations_preserve_other_tenant_state(db_session):
    tenant_a = await _tenant_bundle(db_session, "a")
    tenant_b = await _tenant_bundle(db_session, "b")

    canceled = await SchedulerRecoveryService(db_session).cancel_active_recovery_links(
        tenant_a["organization"].id,
        tenant_a["school_year"].id,
        {tenant_b["active_block"].id},
    )
    assert canceled == 0

    await SchedulerLifecycleService(db_session).reset_year(
        tenant_a["organization"].id,
        reset_by_membership_id=tenant_a["membership"].id,
        confirmed=True,
    )
    await db_session.commit()
    await db_session.refresh(tenant_b["active_block"])
    await db_session.refresh(tenant_b["recovery_link"])
    await db_session.refresh(tenant_b["state"])

    assert tenant_b["active_block"].status == models.ActiveScheduleBlockStatus.ACTIVE
    assert tenant_b["recovery_link"].status == models.PlannedRecoveryLinkStatus.PLANNED
    assert tenant_b["state"].pending_draft_id == tenant_b["draft"].id
