from datetime import date, time
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app import models, schemas
from app.core.exceptions import AppError
from app.services import lesson_log_service, occurrence_service
from tests._support.db_fixtures import create_teacher_profile


async def _occurrence_context(db_session, *, suffix: str) -> SimpleNamespace:
    """Build one published block with both a planned and eligible substitute teacher."""
    organization = models.Organization(
        name=f"Occurrence accounting {suffix}",
        plan_status=models.OrganizationPlanStatus.active,
    )
    db_session.add(organization)
    await db_session.flush()

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
        abbreviation=f"C{suffix[-6:]}",
    )
    planned_subject = models.Subject(
        organization_id=organization.id,
        name=f"Planned subject {suffix}",
        required_room_type=models.RoomType.normal,
    )
    substitute_subject = models.Subject(
        organization_id=organization.id,
        name=f"Substitute subject {suffix}",
        required_room_type=models.RoomType.normal,
    )
    room = models.Room(
        organization_id=organization.id,
        name=f"Room {suffix}",
        type=models.RoomType.normal,
        capacity=30,
    )
    timeslot = models.Timeslot(
        organization_id=organization.id,
        day_of_week=0,
        start_time=time(9, 0),
        end_time=time(10, 0),
    )
    db_session.add_all([school_year, course, planned_subject, substitute_subject, room, timeslot])
    await db_session.flush()

    class_ = models.Class(
        organization_id=organization.id,
        name=f"10A {suffix}",
        size=20,
        start_year=2025,
        end_year=2028,
        grade_level=10,
        course_id=course.id,
    )
    planned_module = models.Module(
        organization_id=organization.id,
        name=f"Planned module {suffix}",
        code=f"P{suffix[-6:]}",
        required_minutes=120,
        order=1,
        subject_id=planned_subject.id,
    )
    substitute_module = models.Module(
        organization_id=organization.id,
        name=f"Substitute module {suffix}",
        code=f"S{suffix[-6:]}",
        required_minutes=120,
        order=1,
        subject_id=substitute_subject.id,
    )
    db_session.add_all([class_, planned_module, substitute_module])
    await db_session.flush()

    admin_user = models.User(email=f"occurrence-admin-{suffix}@test.invalid")
    db_session.add(admin_user)
    await db_session.flush()
    membership = models.OrganizationMembership(
        organization_id=organization.id,
        account_id=admin_user.id,
        organization_display_name=f"Occurrence admin {suffix}",
        lifecycle_status=models.MembershipLifecycleStatus.active,
        access_status=models.MembershipAccessStatus.active,
        can_admin=True,
        can_teach=False,
    )
    db_session.add(membership)
    await db_session.flush()

    planned_teacher = await create_teacher_profile(
        db_session,
        organization_id=organization.id,
        name=f"Planned teacher {suffix}",
        subject_ids=[planned_subject.id],
    )
    substitute_teacher = await create_teacher_profile(
        db_session,
        organization_id=organization.id,
        name=f"Substitute teacher {suffix}",
        subject_ids=[substitute_subject.id],
    )
    db_session.add_all(
        [
            models.ClassSubjectLink(
                organization_id=organization.id,
                class_id=class_.id,
                subject_id=planned_subject.id,
                grade_level=class_.grade_level,
                teacher_id=planned_teacher.id,
            ),
            models.ClassSubjectLink(
                organization_id=organization.id,
                class_id=class_.id,
                subject_id=substitute_subject.id,
                grade_level=class_.grade_level,
                teacher_id=substitute_teacher.id,
            ),
            models.Availability(
                organization_id=organization.id,
                teacher_id=substitute_teacher.id,
                timeslot_id=timeslot.id,
                score=1,
            ),
        ]
    )
    await db_session.flush()

    job = models.ScheduleGenerationJob(
        organization_id=organization.id,
        school_year_id=school_year.id,
        requested_by_membership_id=membership.id,
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
        projected_completion_date=date(2026, 6, 30),
        hard_end_date=school_year.hard_end_date,
        summary_json={},
        created_by_membership_id=membership.id,
    )
    db_session.add(draft)
    await db_session.flush()
    target_date = date(2026, 1, 12)
    draft_block = models.ScheduleDraftBlock(
        organization_id=organization.id,
        school_year_id=school_year.id,
        draft_id=draft.id,
        stable_block_key=f"occurrence-{suffix}",
        class_id=class_.id,
        subject_id=planned_subject.id,
        teacher_id=planned_teacher.id,
        room_id=room.id,
        room_type_id=models.RoomType.normal,
        date=target_date,
        timeslot_id=timeslot.id,
        duration_minutes=60,
        change_type=models.ScheduleDraftBlockChangeType.ADDED,
    )
    db_session.add(draft_block)
    await db_session.flush()
    active_block = models.ActiveScheduleBlock(
        organization_id=organization.id,
        school_year_id=school_year.id,
        schedule_version_id=f"version-{suffix}",
        stable_block_key=draft_block.stable_block_key,
        class_id=class_.id,
        subject_id=planned_subject.id,
        teacher_id=planned_teacher.id,
        room_id=room.id,
        date=target_date,
        timeslot_id=timeslot.id,
        duration_minutes=60,
        source_draft_block_id=draft_block.id,
    )
    db_session.add(active_block)
    await db_session.commit()

    occurrence, created = await occurrence_service.create_occurrence_from_active_block(
        db_session,
        organization.id,
        active_block.id,
        created_by_membership_id=membership.id,
    )
    assert created is True
    await db_session.commit()
    return SimpleNamespace(
        organization_id=organization.id,
        class_id=class_.id,
        membership_id=membership.id,
        occurrence_id=occurrence.id,
        active_block_id=active_block.id,
        substitute_teacher_id=substitute_teacher.id,
        substitute_subject_id=substitute_subject.id,
        planned_module_id=planned_module.id,
        substitute_module_id=substitute_module.id,
        organization=organization,
        school_year=school_year,
        class_=class_,
        planned_subject=planned_subject,
        substitute_subject=substitute_subject,
        planned_teacher=planned_teacher,
        substitute_teacher=substitute_teacher,
        planned_module=planned_module,
        substitute_module=substitute_module,
        room=room,
        timeslot=timeslot,
        membership=membership,
        active_block=active_block,
        occurrence=occurrence,
    )


def _decision(status, version, *, substitute_teacher_id=None, substitute_subject_id=None):
    return schemas.LessonOccurrenceUpdate(
        status=status,
        version=version,
        substitute_teacher_id=substitute_teacher_id,
        substitute_subject_id=substitute_subject_id,
    )


async def _ledger(db_session, context):
    return list(
        (
            await db_session.execute(
                select(models.ProgressLedgerEntry)
                .where(
                    models.ProgressLedgerEntry.organization_id == context.organization_id,
                    models.ProgressLedgerEntry.class_id == context.class_id,
                )
                .order_by(models.ProgressLedgerEntry.id)
            )
        )
        .scalars()
        .all()
    )


@pytest.mark.parametrize(
    ("status", "completed_delta", "debt_delta"),
    [
        (models.LessonOccurrenceStatus.GIVEN, 60, 0),
        (models.LessonOccurrenceStatus.GAP, 0, 60),
    ],
)
async def test_occurrence_decisions_apply_exact_forward_ledger_deltas(
    db_session, status, completed_delta, debt_delta
):
    context = await _occurrence_context(db_session, suffix=f"basic-{status.value.lower()}")

    await occurrence_service.update_occurrence(
        db_session,
        context.occurrence_id,
        context.organization_id,
        _decision(status, 1),
        decided_by_membership_id=context.membership_id,
    )
    await db_session.commit()

    entries = await _ledger(db_session, context)
    assert len(entries) == 1
    assert entries[0].source_type == "OCCURRENCE_DECISION"
    assert entries[0].source_revision == context.occurrence.revision == 1
    assert entries[0].completed_minutes_delta == completed_delta
    assert entries[0].debt_minutes_delta == debt_delta
    await db_session.refresh(context.occurrence)
    assert context.occurrence.status == status
    assert context.occurrence.version == 2


async def test_occurrence_redecision_reverses_then_reapplies_exact_accounting(db_session):
    context = await _occurrence_context(db_session, suffix="redecision")

    await occurrence_service.update_occurrence(
        db_session,
        context.occurrence_id,
        context.organization_id,
        _decision(models.LessonOccurrenceStatus.GAP, 1),
        decided_by_membership_id=context.membership_id,
    )
    await db_session.commit()
    await occurrence_service.update_occurrence(
        db_session,
        context.occurrence_id,
        context.organization_id,
        _decision(
            models.LessonOccurrenceStatus.SUBSTITUTED,
            2,
            substitute_teacher_id=context.substitute_teacher_id,
            substitute_subject_id=context.substitute_subject_id,
        ),
        decided_by_membership_id=context.membership_id,
    )
    await db_session.commit()
    await occurrence_service.update_occurrence(
        db_session,
        context.occurrence_id,
        context.organization_id,
        _decision(models.LessonOccurrenceStatus.GAP, 3),
        decided_by_membership_id=context.membership_id,
    )
    await db_session.commit()

    entries = await _ledger(db_session, context)
    assert [(entry.source_type, entry.debt_minutes_delta) for entry in entries] == [
        ("OCCURRENCE_DECISION", 60),
        ("OCCURRENCE_REVERSAL", -60),
        ("OCCURRENCE_DECISION", 60),
        ("OCCURRENCE_REVERSAL", -60),
        ("OCCURRENCE_DECISION", 60),
    ]
    assert sum(entry.debt_minutes_delta for entry in entries) == 60
    operational = (
        await db_session.execute(
            select(models.OperationalScheduleBlock).where(
                models.OperationalScheduleBlock.source_occurrence_id == context.occurrence_id
            )
        )
    ).scalar_one()
    assert operational.status == models.OperationalBlockStatus.CANCELLED
    await db_session.refresh(context.occurrence)
    assert context.occurrence.status == models.LessonOccurrenceStatus.GAP
    assert context.occurrence.version == 4
    assert context.occurrence.revision == 1


async def test_occurrence_retry_is_idempotent_and_stale_version_is_rejected(db_session):
    context = await _occurrence_context(db_session, suffix="retry")
    given = _decision(models.LessonOccurrenceStatus.GIVEN, 1)
    await occurrence_service.update_occurrence(
        db_session,
        context.occurrence_id,
        context.organization_id,
        given,
        decided_by_membership_id=context.membership_id,
    )
    await db_session.commit()

    retried = await occurrence_service.update_occurrence(
        db_session,
        context.occurrence_id,
        context.organization_id,
        given,
        decided_by_membership_id=context.membership_id,
    )
    await db_session.commit()
    assert retried.version == 2
    assert len(await _ledger(db_session, context)) == 1

    with pytest.raises(AppError) as error:
        await occurrence_service.update_occurrence(
            db_session,
            context.occurrence_id,
            context.organization_id,
            _decision(models.LessonOccurrenceStatus.GAP, 1),
            decided_by_membership_id=context.membership_id,
        )
    assert error.value.detail == occurrence_service.ERR_STALE_VERSION
    await db_session.rollback()
    await db_session.refresh(context.occurrence)
    assert context.occurrence.status == models.LessonOccurrenceStatus.GIVEN
    assert context.occurrence.version == 2
    assert len(await _ledger(db_session, context)) == 1


async def test_occurrence_cancellation_reverses_ledger_and_preserves_audit_revision(db_session):
    context = await _occurrence_context(db_session, suffix="cancel")
    await occurrence_service.update_occurrence(
        db_session,
        context.occurrence_id,
        context.organization_id,
        _decision(models.LessonOccurrenceStatus.GAP, 1),
        decided_by_membership_id=context.membership_id,
    )
    await db_session.commit()
    await occurrence_service.log_occurrence_event_safe(
        db_session,
        organization_id=context.organization_id,
        event_type=occurrence_service.OBS_EVENT_DECIDE,
        result=occurrence_service.OBS_RESULT_SUCCESS,
        actor_membership_id=context.membership_id,
        occurrence_id=context.occurrence_id,
        active_schedule_block_id=context.active_block_id,
        decision_status=models.LessonOccurrenceStatus.GAP,
        detail="decision committed",
    )
    await db_session.commit()

    await occurrence_service.cancel_occurrence(
        db_session,
        organization_id=context.organization_id,
        occurrence_id=context.occurrence_id,
        cancelled_by_membership_id=context.membership_id,
        version=2,
        reason="test cancellation",
    )
    await db_session.commit()

    entries = await _ledger(db_session, context)
    assert [(entry.source_type, entry.debt_minutes_delta) for entry in entries] == [
        ("OCCURRENCE_DECISION", 60),
        ("OCCURRENCE_REVERSAL", -60),
    ]
    events = list(
        (
            await db_session.execute(
                select(models.OccurrenceOperationalEvent).where(
                    models.OccurrenceOperationalEvent.organization_id == context.organization_id,
                    models.OccurrenceOperationalEvent.occurrence_id == context.occurrence_id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
    assert events[0].event_type == occurrence_service.OBS_EVENT_DECIDE
    await db_session.refresh(context.occurrence)
    assert context.occurrence.status == models.LessonOccurrenceStatus.REVOKED
    assert context.occurrence.is_active is False
    assert context.occurrence.version == 3
    assert context.occurrence.revision == 1
    assert context.occurrence.revoked_reason == "test cancellation"


async def test_completed_substitute_log_is_protected_then_can_be_reversed(db_session):
    context = await _occurrence_context(db_session, suffix="completed-log")
    await occurrence_service.update_occurrence(
        db_session,
        context.occurrence_id,
        context.organization_id,
        _decision(
            models.LessonOccurrenceStatus.SUBSTITUTED,
            1,
            substitute_teacher_id=context.substitute_teacher_id,
            substitute_subject_id=context.substitute_subject_id,
        ),
        decided_by_membership_id=context.membership_id,
    )
    await db_session.commit()
    operational = (
        await db_session.execute(
            select(models.OperationalScheduleBlock).where(
                models.OperationalScheduleBlock.source_occurrence_id == context.occurrence_id,
                models.OperationalScheduleBlock.status == models.OperationalBlockStatus.ACTIVE,
            )
        )
    ).scalar_one()
    completed_log = await db_session.run_sync(
        lambda sync_db: lesson_log_service.upsert_operational_lesson_log_sync(
            sync_db,
            context.organization_id,
            context.membership_id,
            operational.id,
            schemas.LessonLogCreate(
                status=models.LessonLogStatus.COMPLETED,
                summary="Substitute delivered",
            ),
        )
    )
    await db_session.commit()
    assert completed_log.status == models.LessonLogStatus.COMPLETED

    with pytest.raises(AppError) as error:
        await occurrence_service.cancel_occurrence(
            db_session,
            organization_id=context.organization_id,
            occurrence_id=context.occurrence_id,
            cancelled_by_membership_id=context.membership_id,
            version=2,
        )
    assert error.value.detail == occurrence_service.ERR_SUBSTITUTE_LOG_LOCKED
    await db_session.rollback()
    await db_session.refresh(context.occurrence)
    assert context.occurrence.status == models.LessonOccurrenceStatus.SUBSTITUTED

    await occurrence_service.cancel_occurrence(
        db_session,
        organization_id=context.organization_id,
        occurrence_id=context.occurrence_id,
        cancelled_by_membership_id=context.membership_id,
        version=2,
        cancel_completed_substitute_log=True,
    )
    await db_session.commit()
    await db_session.refresh(completed_log)
    await db_session.refresh(operational)
    assert completed_log.status == models.LessonLogStatus.PENDING
    assert completed_log.version == 2
    assert operational.status == models.OperationalBlockStatus.CANCELLED
    assert operational.execution_status == models.OperationalBlockExecutionStatus.CANCELLED

    entries = await _ledger(db_session, context)
    assert [
        (
            entry.source_type,
            entry.module_id,
            entry.completed_minutes_delta,
            entry.debt_minutes_delta,
        )
        for entry in entries
    ] == [
        ("OCCURRENCE_DECISION", context.planned_module_id, 0, 60),
        ("LESSON_LOG", context.substitute_module_id, 60, 0),
        ("OCCURRENCE_REVERSAL", context.planned_module_id, 0, -60),
        ("LESSON_LOG", context.substitute_module_id, -60, 0),
    ]


async def test_occurrence_reads_and_mutations_are_tenant_scoped(db_session):
    first = await _occurrence_context(db_session, suffix="tenant-a")
    await db_session.commit()
    second = await _occurrence_context(db_session, suffix="tenant-b")
    await db_session.commit()

    with pytest.raises(AppError) as error:
        await occurrence_service.update_occurrence(
            db_session,
            first.occurrence_id,
            second.organization_id,
            _decision(models.LessonOccurrenceStatus.GAP, 1),
            decided_by_membership_id=second.membership.id,
        )
    assert error.value.detail == occurrence_service.OCCURRENCE_NOT_FOUND
    await db_session.rollback()
    await db_session.refresh(first.occurrence)
    assert first.occurrence.status is None
    assert first.occurrence.version == 1
    assert (
        await db_session.execute(
            select(models.ProgressLedgerEntry).where(
                models.ProgressLedgerEntry.organization_id == first.organization_id
            )
        )
    ).scalars().all() == []
