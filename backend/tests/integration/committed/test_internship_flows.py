from datetime import UTC, date, datetime, time

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import models, schemas
from app.core.exceptions import AppError
from app.services import internship_flow_service, occurrence_service, settings_service
from app.services.scheduler_fingerprint_service import SchedulerFingerprintService

pytestmark = pytest.mark.postgresql

FLOW_DATE = date(2025, 10, 6)
FLOW_END = date(2025, 10, 7)


async def _flow_context(db_session):
    organization = models.Organization(
        name="Internship School",
        plan_status=models.OrganizationPlanStatus.active,
        foundation_status=models.OrganizationFoundationStatus.COMPLETED,
        foundation_completed_at=datetime.now(UTC),
    )
    db_session.add(organization)
    await db_session.flush()
    user = models.User(name="Flow Admin", email="flow-admin@example.com")
    school_year = models.SchedulerSchoolYear(
        organization_id=organization.id,
        label="2025/2026",
        start_date=date(2025, 9, 15),
        hard_end_date=date(2026, 7, 31),
        timezone="Europe/Lisbon",
    )
    course = models.Course(
        organization_id=organization.id,
        name="Course",
        abbreviation="FLW",
    )
    subject = models.Subject(
        organization_id=organization.id,
        name="Subject",
        required_room_type=models.RoomType.normal,
    )
    room = models.Room(
        organization_id=organization.id,
        name="Room",
        type=models.RoomType.normal,
        capacity=30,
    )
    slot = models.Timeslot(
        organization_id=organization.id,
        day_of_week=FLOW_DATE.weekday(),
        start_time=time(9),
        end_time=time(10),
    )
    slot_b = models.Timeslot(
        organization_id=organization.id,
        day_of_week=FLOW_DATE.weekday(),
        start_time=time(10),
        end_time=time(11),
    )
    db_session.add_all([user, school_year, course, subject, room, slot, slot_b])
    await db_session.flush()
    membership = models.OrganizationMembership(
        organization_id=organization.id,
        account_id=user.id,
        organization_display_name="Flow Admin",
        lifecycle_status=models.MembershipLifecycleStatus.active,
        access_status=models.MembershipAccessStatus.active,
        can_admin=True,
        can_teach=False,
    )
    db_session.add(membership)
    await db_session.flush()
    teacher = models.Teacher(
        organization_id=organization.id,
        organization_membership_id=membership.id,
    )
    db_session.add(teacher)
    await db_session.flush()
    state = models.SchedulerSchoolYearState(
        organization_id=organization.id,
        school_year_id=school_year.id,
    )
    settings = models.OrganizationSettings(
        organization_id=organization.id,
        school_start_date=school_year.start_date,
        school_hard_end_date=school_year.hard_end_date,
        repair_stability_window_days=0,
    )
    class_a = models.Class(
        organization_id=organization.id,
        name="10A",
        size=20,
        start_year=2025,
        end_year=2026,
        grade_level=10,
        course_id=course.id,
    )
    class_b = models.Class(
        organization_id=organization.id,
        name="10B",
        size=20,
        start_year=2025,
        end_year=2026,
        grade_level=10,
        course_id=course.id,
    )
    db_session.add_all([state, settings, class_a, class_b])
    await db_session.flush()
    db_session.add_all(
        [
            models.Module(
                organization_id=organization.id,
                name="Module",
                code="FLW-1",
                hours_total=1,
                order=1,
                subject_id=subject.id,
            ),
            models.ClassSubjectLink(
                organization_id=organization.id,
                class_id=class_a.id,
                subject_id=subject.id,
                grade_level=10,
                teacher_id=teacher.id,
            ),
            models.ClassSubjectLink(
                organization_id=organization.id,
                class_id=class_b.id,
                subject_id=subject.id,
                grade_level=10,
                teacher_id=teacher.id,
            ),
        ]
    )
    await db_session.execute(
        models.teacher_subject_link.insert().values(
            organization_id=organization.id,
            teacher_id=teacher.id,
            subject_id=subject.id,
        )
    )
    job = models.ScheduleGenerationJob(
        organization_id=organization.id,
        school_year_id=school_year.id,
        strategy=models.ScheduleGenerationStrategy.COMPLETE_GENERATION,
        trigger_type=models.ScheduleGenerationTrigger.FIRST_GENERATION,
        idempotency_key="flow-context-job",
    )
    db_session.add(job)
    await db_session.flush()
    draft = models.ScheduleDraft(
        organization_id=organization.id,
        school_year_id=school_year.id,
        generation_job_id=job.id,
        strategy=models.ScheduleGenerationStrategy.COMPLETE_GENERATION,
        draft_state=models.ScheduleDraftState.PENDING,
        result_category=models.ScheduleGenerationResultCategory.COMPLETE_SUCCESS,
        trigger_type=models.ScheduleGenerationTrigger.FIRST_GENERATION,
        generation_input_fingerprint="0" * 64,
        projected_completion_date=FLOW_END,
        hard_end_date=school_year.hard_end_date,
        summary_json={},
        created_by_membership_id=membership.id,
    )
    db_session.add(draft)
    await db_session.flush()
    ctx = {
        "organization": organization,
        "membership": membership,
        "school_year": school_year,
        "state": state,
        "class_a": class_a,
        "class_b": class_b,
        "subject": subject,
        "teacher": teacher,
        "room": room,
        "slot": slot,
        "slot_b": slot_b,
        "draft": draft,
    }
    await db_session.commit()
    return ctx


async def _publish_block(db_session, ctx, class_, block_date, key, timeslot=None):
    draft_block = models.ScheduleDraftBlock(
        organization_id=ctx["organization"].id,
        school_year_id=ctx["school_year"].id,
        draft_id=ctx["draft"].id,
        stable_block_key=key,
        class_id=class_.id,
        subject_id=ctx["subject"].id,
        teacher_id=ctx["teacher"].id,
        room_id=ctx["room"].id,
        date=block_date,
        timeslot_id=(timeslot or ctx["slot"]).id,
        duration_minutes=60,
        module_sequence_index=1,
        change_type=models.ScheduleDraftBlockChangeType.ADDED,
    )
    db_session.add(draft_block)
    await db_session.flush()
    active = models.ActiveScheduleBlock(
        organization_id=ctx["organization"].id,
        school_year_id=ctx["school_year"].id,
        schedule_version_id="flow-v1",
        stable_block_key=key,
        class_id=class_.id,
        subject_id=ctx["subject"].id,
        teacher_id=ctx["teacher"].id,
        room_id=ctx["room"].id,
        date=block_date,
        timeslot_id=draft_block.timeslot_id,
        duration_minutes=60,
        source_draft_block_id=draft_block.id,
        status=models.ActiveScheduleBlockStatus.ACTIVE,
    )
    db_session.add(active)
    await db_session.flush()
    await db_session.commit()
    return active


def _create_payload(**overrides):
    data = {
        "name": "Estágio 10A",
        "start_date": FLOW_DATE,
        "end_date": FLOW_END,
        "event_type": models.CalendarEventType.internship_flow,
        "class_ids": [],
    }
    data.update(overrides)
    return schemas.SchoolCalendarEventCreate(**data)


async def _preview(db_session, ctx, payload, operation="create", event_id=None):
    return await internship_flow_service.preview_change(
        db_session,
        ctx["organization"].id,
        schemas.CalendarEventChangePreviewRequest(
            operation=operation,
            event_id=event_id,
            name=payload.name,
            start_date=payload.start_date,
            end_date=payload.end_date,
            class_ids=payload.class_ids,
        ),
    )


async def _create_confirmed(db_session, ctx, **overrides):
    payload = _create_payload(**overrides)
    preview = await _preview(db_session, ctx, payload)
    confirmed = payload.model_copy(
        update={"confirmation_fingerprint": preview.confirmation_fingerprint}
    )
    return await internship_flow_service.create_flow(
        db_session,
        ctx["organization"].id,
        confirmed,
        changed_by_membership_id=ctx["membership"].id,
    )


async def test_flow_removes_only_lessons_of_associated_classes(db_session):
    ctx = await _flow_context(db_session)
    block_a = await _publish_block(db_session, ctx, ctx["class_a"], FLOW_DATE, "flow-a")
    block_b = await _publish_block(
        db_session, ctx, ctx["class_b"], FLOW_DATE, "flow-b", timeslot=ctx["slot_b"]
    )

    payload = _create_payload(class_ids=[ctx["class_a"].id])
    preview = await _preview(db_session, ctx, payload)
    assert preview.requires_confirmation is True
    assert [row.active_schedule_block_id for row in preview.affected_lessons] == [block_a.id]

    event = await _create_confirmed(db_session, ctx, class_ids=[ctx["class_a"].id])
    await db_session.commit()

    await db_session.refresh(block_a)
    await db_session.refresh(block_b)
    assert block_a.status is models.ActiveScheduleBlockStatus.REMOVED
    assert block_b.status is models.ActiveScheduleBlockStatus.ACTIVE
    assert event.class_ids == [ctx["class_a"].id]
    assert event.school_year_start_year == 2025

    state = await db_session.get(models.SchedulerSchoolYearState, ctx["state"].id)
    assert state.scheduler_state_version == 1
    change = await db_session.scalar(
        select(models.SchedulerStateVersionEvent).where(
            models.SchedulerStateVersionEvent.entity_type == "INTERNSHIP_FLOW"
        )
    )
    assert change is not None
    assert change.change_scope is models.SchedulerStateChangeScope.FUTURE_IMPACTING

    absence = await db_session.scalar(
        select(models.LessonOccurrence).where(
            models.LessonOccurrence.active_schedule_block_id == block_a.id,
            models.LessonOccurrence.is_active.is_(True),
        )
    )
    assert absence is not None
    assert absence.status is models.LessonOccurrenceStatus.GAP
    assert absence.reason == internship_flow_service.INTERNSHIP_FLOW_OCCURRENCE_REASON
    assert absence.creation_source == "internship_flow"
    assert (
        await db_session.scalar(
            select(models.LessonOccurrence.id).where(
                models.LessonOccurrence.active_schedule_block_id == block_b.id
            )
        )
        is None
    )


async def test_empty_flow_does_not_block_or_require_confirmation(db_session):
    ctx = await _flow_context(db_session)
    block_a = await _publish_block(db_session, ctx, ctx["class_a"], FLOW_DATE, "flow-a")
    block_b = await _publish_block(
        db_session, ctx, ctx["class_b"], FLOW_DATE, "flow-b", timeslot=ctx["slot_b"]
    )

    payload = _create_payload(class_ids=[])
    preview = await _preview(db_session, ctx, payload)
    assert preview.requires_confirmation is False
    assert preview.affected_lessons == []

    event = await internship_flow_service.create_flow(
        db_session,
        ctx["organization"].id,
        payload,
        changed_by_membership_id=ctx["membership"].id,
    )
    await db_session.commit()

    await db_session.refresh(block_a)
    await db_session.refresh(block_b)
    assert block_a.status is models.ActiveScheduleBlockStatus.ACTIVE
    assert block_b.status is models.ActiveScheduleBlockStatus.ACTIVE
    assert event.class_ids == []

    state = await db_session.get(models.SchedulerSchoolYearState, ctx["state"].id)
    assert state.scheduler_state_version == 0


async def test_confirmation_is_required_and_stale_fingerprints_are_rejected(db_session):
    ctx = await _flow_context(db_session)
    block_a = await _publish_block(db_session, ctx, ctx["class_a"], FLOW_DATE, "flow-a")
    payload = _create_payload(class_ids=[ctx["class_a"].id])

    with pytest.raises(internship_flow_service.InternshipFlowConfirmationRequired):
        await internship_flow_service.create_flow(db_session, ctx["organization"].id, payload)
    assert block_a.status is models.ActiveScheduleBlockStatus.ACTIVE

    preview = await _preview(db_session, ctx, payload)
    db_session.add(
        models.LessonLog(
            organization_id=ctx["organization"].id,
            active_schedule_block_id=block_a.id,
            status=models.LessonLogStatus.COMPLETED,
            logged_by_membership_id=ctx["membership"].id,
        )
    )
    await db_session.flush()

    with pytest.raises(internship_flow_service.InternshipFlowStale):
        await internship_flow_service.create_flow(
            db_session,
            ctx["organization"].id,
            payload.model_copy(
                update={"confirmation_fingerprint": preview.confirmation_fingerprint}
            ),
        )


async def test_given_lessons_are_preserved_and_absences_keep_their_history(db_session):
    ctx = await _flow_context(db_session)
    given = await _publish_block(db_session, ctx, ctx["class_a"], FLOW_DATE, "flow-given")
    missing = await _publish_block(db_session, ctx, ctx["class_a"], FLOW_END, "flow-gap")
    db_session.add(
        models.LessonLog(
            organization_id=ctx["organization"].id,
            active_schedule_block_id=given.id,
            status=models.LessonLogStatus.COMPLETED,
            logged_by_membership_id=ctx["membership"].id,
        )
    )
    occurrence = models.LessonOccurrence(
        organization_id=ctx["organization"].id,
        date=FLOW_END,
        class_id=ctx["class_a"].id,
        subject_id=ctx["subject"].id,
        active_schedule_block_id=missing.id,
        status=models.LessonOccurrenceStatus.GAP,
        revision=1,
        planned_hours=1,
        hours_given=0,
        planned_minutes=60,
    )
    db_session.add(occurrence)
    await db_session.commit()

    await _create_confirmed(db_session, ctx, class_ids=[ctx["class_a"].id])
    await db_session.commit()

    await db_session.refresh(given)
    await db_session.refresh(missing)
    await db_session.refresh(occurrence)
    assert given.status is models.ActiveScheduleBlockStatus.ACTIVE
    assert missing.status is models.ActiveScheduleBlockStatus.REMOVED
    assert occurrence.status is models.LessonOccurrenceStatus.GAP
    assert occurrence.is_active is True

    occurrences = (
        await db_session.scalars(
            select(models.LessonOccurrence).where(
                models.LessonOccurrence.active_schedule_block_id.in_([given.id, missing.id]),
                models.LessonOccurrence.is_active.is_(True),
            )
        )
    ).all()
    assert len(occurrences) == 1
    assert occurrences[0].active_schedule_block_id == missing.id

    debt = await SchedulerFingerprintService(db_session).debt_basis_fingerprint(
        ctx["organization"].id, ctx["school_year"].id
    )
    assert debt is not None
    assert debt.unresolved_debt_minutes == 60


async def test_update_and_delete_do_not_restore_removed_lessons(db_session):
    ctx = await _flow_context(db_session)
    first = await _publish_block(db_session, ctx, ctx["class_a"], FLOW_DATE, "flow-first")
    second = await _publish_block(db_session, ctx, ctx["class_a"], FLOW_END, "flow-second")

    event = await _create_confirmed(db_session, ctx, class_ids=[ctx["class_a"].id])
    await db_session.commit()
    preview = await internship_flow_service.preview_change(
        db_session,
        ctx["organization"].id,
        schemas.CalendarEventChangePreviewRequest(
            operation="update",
            event_id=event.id,
            name="Estágio 10A alargado",
            start_date=FLOW_DATE,
            end_date=FLOW_END,
            class_ids=[ctx["class_a"].id],
        ),
    )
    updated = await internship_flow_service.update_flow(
        db_session,
        ctx["organization"].id,
        event.id,
        schemas.SchoolCalendarEventUpdate(
            name="Estágio 10A alargado",
            start_date=FLOW_DATE,
            end_date=FLOW_END,
            class_ids=[ctx["class_a"].id],
            confirmation_fingerprint=preview.confirmation_fingerprint,
        ),
        changed_by_membership_id=ctx["membership"].id,
    )
    await db_session.commit()
    assert updated.class_ids == [ctx["class_a"].id]

    await internship_flow_service.delete_flow(
        db_session,
        ctx["organization"].id,
        event.id,
        changed_by_membership_id=ctx["membership"].id,
    )
    await db_session.commit()

    await db_session.refresh(first)
    await db_session.refresh(second)
    assert first.status is models.ActiveScheduleBlockStatus.REMOVED
    assert second.status is models.ActiveScheduleBlockStatus.REMOVED
    assert (
        await db_session.scalar(
            select(models.SchoolCalendarEvent).where(models.SchoolCalendarEvent.id == event.id)
        )
        is None
    )


async def test_removed_lesson_is_recorded_as_absence(db_session):
    ctx = await _flow_context(db_session)
    block_a = await _publish_block(db_session, ctx, ctx["class_a"], FLOW_DATE, "flow-a")
    await _create_confirmed(db_session, ctx, class_ids=[ctx["class_a"].id])
    await db_session.commit()

    history = await settings_service.list_calendar_events(db_session, ctx["organization"].id)
    assert [event.name for event in history] == ["Estágio 10A"]

    occurrences = await occurrence_service.list_occurrences(
        db_session,
        ctx["organization"].id,
        class_id=ctx["class_a"].id,
        date_from=FLOW_DATE,
        date_to=FLOW_END,
    )
    removed = [item for item in occurrences if item.active_schedule_block_id == block_a.id]
    assert len(removed) == 1
    assert removed[0].status is models.LessonOccurrenceStatus.GAP
    assert removed[0].reason == internship_flow_service.INTERNSHIP_FLOW_OCCURRENCE_REASON
    assert removed[0].creation_source == "internship_flow"


async def test_flow_validation_rejects_foreign_classes_and_out_of_range_dates(db_session):
    ctx = await _flow_context(db_session)
    other_org = models.Organization(name="Other", plan_status=models.OrganizationPlanStatus.active)
    db_session.add(other_org)
    await db_session.flush()
    foreign_course = models.Course(
        organization_id=other_org.id, name="Other Course", abbreviation="OTH"
    )
    db_session.add(foreign_course)
    await db_session.flush()
    foreign_class = models.Class(
        organization_id=other_org.id,
        name="99Z",
        size=10,
        start_year=2025,
        end_year=2026,
        grade_level=10,
        course_id=foreign_course.id,
    )
    db_session.add(foreign_class)
    await db_session.commit()

    with pytest.raises(internship_flow_service.InternshipFlowError):
        await internship_flow_service.create_flow(
            db_session,
            ctx["organization"].id,
            _create_payload(class_ids=[foreign_class.id]),
        )

    with pytest.raises(internship_flow_service.InternshipFlowError):
        await internship_flow_service.create_flow(
            db_session,
            ctx["organization"].id,
            _create_payload(start_date=date(2025, 1, 1), end_date=date(2025, 1, 2)),
        )


async def test_association_table_rejects_cross_tenant_rows(db_session):
    ctx = await _flow_context(db_session)
    other_org = models.Organization(
        name="Foreign", plan_status=models.OrganizationPlanStatus.active
    )
    db_session.add(other_org)
    await db_session.flush()
    other_event = models.SchoolCalendarEvent(
        organization_id=other_org.id,
        name="Foreign flow",
        start_date=FLOW_DATE,
        end_date=FLOW_END,
        event_type=models.CalendarEventType.internship_flow,
        source=models.CalendarEventSource.manual,
    )
    db_session.add(other_event)
    await db_session.flush()

    db_session.add(
        models.SchoolCalendarEventClass(
            organization_id=other_org.id,
            calendar_event_id=other_event.id,
            class_id=ctx["class_a"].id,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_school_year_change_disables_previous_flows(db_session):
    ctx = await _flow_context(db_session)
    event = await _create_confirmed(db_session, ctx, class_ids=[ctx["class_a"].id])
    await db_session.commit()
    assert event.school_year_start_year == 2025

    await settings_service.upsert_settings(
        db_session,
        ctx["organization"].id,
        schemas.OrganizationSettingsUpsert(
            school_start_date=date(2026, 9, 15),
            school_hard_end_date=date(2027, 7, 31),
        ),
    )
    await db_session.commit()

    events = await settings_service.list_calendar_events(db_session, ctx["organization"].id)
    assert events[0].applies_to_current_school_year is False

    fingerprint = await SchedulerFingerprintService(db_session).generation_input_fingerprint(
        ctx["organization"].id,
        ctx["school_year"].id,
        models.ScheduleGenerationStrategy.COMPLETE_GENERATION,
    )
    assert fingerprint.snapshot["calendar_events"] == []

    with pytest.raises(internship_flow_service.InternshipFlowError):
        await internship_flow_service.update_flow(
            db_session,
            ctx["organization"].id,
            event.id,
            schemas.SchoolCalendarEventUpdate(
                name="Renomear ano anterior",
                start_date=FLOW_DATE,
                end_date=FLOW_END,
                class_ids=[],
            ),
        )


async def test_school_year_date_shift_keeps_flows_applying(db_session):
    ctx = await _flow_context(db_session)
    await _create_confirmed(db_session, ctx, class_ids=[ctx["class_a"].id])
    await db_session.commit()

    await settings_service.upsert_settings(
        db_session,
        ctx["organization"].id,
        schemas.OrganizationSettingsUpsert(
            school_start_date=date(2025, 9, 16),
            school_hard_end_date=date(2026, 7, 30),
        ),
    )
    await db_session.commit()

    events = await settings_service.list_calendar_events(db_session, ctx["organization"].id)
    assert events[0].applies_to_current_school_year is True

    fingerprint = await SchedulerFingerprintService(db_session).generation_input_fingerprint(
        ctx["organization"].id,
        ctx["school_year"].id,
        models.ScheduleGenerationStrategy.COMPLETE_GENERATION,
    )
    assert [row["event_type"] for row in fingerprint.snapshot["calendar_events"]] == [
        "internship_flow"
    ]


async def test_previous_year_flows_stay_visible_but_do_not_apply(db_session):
    ctx = await _flow_context(db_session)
    db_session.add(
        models.SchoolCalendarEvent(
            organization_id=ctx["organization"].id,
            school_year_start_year=2024,
            name="Estágio do ano anterior",
            start_date=FLOW_DATE,
            end_date=FLOW_END,
            event_type=models.CalendarEventType.internship_flow,
            source=models.CalendarEventSource.manual,
        )
    )
    await db_session.commit()

    events = await settings_service.list_calendar_events(db_session, ctx["organization"].id)
    assert [event.name for event in events] == ["Estágio do ano anterior"]
    assert events[0].applies_to_current_school_year is False

    fingerprint = await SchedulerFingerprintService(db_session).generation_input_fingerprint(
        ctx["organization"].id,
        ctx["school_year"].id,
        models.ScheduleGenerationStrategy.COMPLETE_GENERATION,
    )
    assert fingerprint.snapshot["calendar_events"] == []


async def test_flow_fingerprint_includes_class_associations(db_session):
    ctx = await _flow_context(db_session)
    first = await SchedulerFingerprintService(db_session).generation_input_fingerprint(
        ctx["organization"].id,
        ctx["school_year"].id,
        models.ScheduleGenerationStrategy.COMPLETE_GENERATION,
    )
    await _create_confirmed(db_session, ctx, class_ids=[ctx["class_a"].id])
    await db_session.commit()
    second = await SchedulerFingerprintService(db_session).generation_input_fingerprint(
        ctx["organization"].id,
        ctx["school_year"].id,
        models.ScheduleGenerationStrategy.COMPLETE_GENERATION,
    )

    assert first.snapshot["calendar_events"] == []
    entry = second.snapshot["calendar_events"][0]
    assert entry["event_type"] == "internship_flow"
    assert entry["class_ids"] == [ctx["class_a"].id]
    assert entry["school_year_start_year"] == 2025
    assert second.value != first.value


async def _gap_occurrence(db_session, ctx, block, *, status=models.LessonOccurrenceStatus.GAP):
    occurrence = models.LessonOccurrence(
        organization_id=ctx["organization"].id,
        date=block.date,
        class_id=block.class_id,
        subject_id=block.subject_id,
        active_schedule_block_id=block.id,
        status=status,
        revision=1,
        planned_hours=1,
        hours_given=0,
        planned_minutes=block.duration_minutes,
    )
    db_session.add(occurrence)
    await db_session.flush()
    return occurrence


async def _pending_operational_block(db_session, ctx, occurrence):
    operational = models.OperationalScheduleBlock(
        organization_id=ctx["organization"].id,
        source_occurrence_id=occurrence.id,
        source_occurrence_revision=occurrence.revision,
        planned_active_schedule_block_id=occurrence.active_schedule_block_id,
        date=occurrence.date,
        timeslot_id=ctx["slot"].id,
        room_id=ctx["room"].id,
        class_id=occurrence.class_id,
        teacher_id=ctx["teacher"].id,
        subject_id=ctx["subject"].id,
        status=models.OperationalBlockStatus.ACTIVE,
        execution_status=models.OperationalBlockExecutionStatus.PENDING_LOG,
    )
    db_session.add(operational)
    await db_session.flush()
    return operational


async def test_flow_cancels_pending_substitutions_and_keeps_taught_ones(db_session):
    ctx = await _flow_context(db_session)
    pending_block = await _publish_block(
        db_session, ctx, ctx["class_a"], FLOW_DATE, "flow-pending-sub"
    )
    taught_block = await _publish_block(
        db_session, ctx, ctx["class_a"], FLOW_END, "flow-taught-sub"
    )
    pending_occurrence = await _gap_occurrence(
        db_session, ctx, pending_block, status=models.LessonOccurrenceStatus.SUBSTITUTED
    )
    taught_occurrence = await _gap_occurrence(
        db_session, ctx, taught_block, status=models.LessonOccurrenceStatus.SUBSTITUTED
    )
    pending_operational = await _pending_operational_block(db_session, ctx, pending_occurrence)
    taught_operational = await _pending_operational_block(db_session, ctx, taught_occurrence)
    db_session.add(
        models.LessonLog(
            organization_id=ctx["organization"].id,
            operational_block_id=taught_operational.id,
            status=models.LessonLogStatus.COMPLETED,
        )
    )
    await db_session.commit()

    await _create_confirmed(db_session, ctx, class_ids=[ctx["class_a"].id])
    await db_session.commit()

    await db_session.refresh(pending_operational)
    await db_session.refresh(taught_operational)
    assert pending_operational.status is models.OperationalBlockStatus.CANCELLED
    assert pending_operational.execution_status is models.OperationalBlockExecutionStatus.CANCELLED
    assert pending_operational.cancelled_at is not None
    assert taught_operational.status is models.OperationalBlockStatus.ACTIVE
    assert taught_operational.execution_status is models.OperationalBlockExecutionStatus.PENDING_LOG


async def test_flow_blocks_substitution_decisions_on_removed_blocks(db_session):
    ctx = await _flow_context(db_session)
    removed_block = await _publish_block(db_session, ctx, ctx["class_a"], FLOW_DATE, "flow-decide")
    occurrence = await _gap_occurrence(db_session, ctx, removed_block)
    await db_session.commit()

    await _create_confirmed(db_session, ctx, class_ids=[ctx["class_a"].id])
    await db_session.commit()

    with pytest.raises(AppError) as excinfo:
        await occurrence_service.update_occurrence(
            db_session,
            occurrence.id,
            ctx["organization"].id,
            schemas.LessonOccurrenceUpdate(
                status=models.LessonOccurrenceStatus.SUBSTITUTED,
                version=occurrence.version,
                substitute_teacher_id=ctx["teacher"].id,
                substitute_subject_id=ctx["subject"].id,
            ),
            decided_by_membership_id=ctx["membership"].id,
        )
    assert excinfo.value.code == "INTERNSHIP_FLOW_BLOCKS_LESSON"


async def test_flow_blocks_substitution_decisions_inside_flow_dates(db_session):
    ctx = await _flow_context(db_session)
    await _create_confirmed(
        db_session,
        ctx,
        class_ids=[ctx["class_a"].id],
        start_date=FLOW_END,
        end_date=FLOW_END,
    )
    await db_session.commit()

    late_block = await _publish_block(db_session, ctx, ctx["class_a"], FLOW_END, "flow-late")
    occurrence = await _gap_occurrence(db_session, ctx, late_block)
    await db_session.commit()

    with pytest.raises(AppError) as excinfo:
        await occurrence_service.update_occurrence(
            db_session,
            occurrence.id,
            ctx["organization"].id,
            schemas.LessonOccurrenceUpdate(
                status=models.LessonOccurrenceStatus.SUBSTITUTED,
                version=occurrence.version,
                substitute_teacher_id=ctx["teacher"].id,
                substitute_subject_id=ctx["subject"].id,
            ),
            decided_by_membership_id=ctx["membership"].id,
        )
    assert excinfo.value.code == "INTERNSHIP_FLOW_BLOCKS_LESSON"


async def test_confirmation_is_recomputed_under_lock(db_session, monkeypatch):
    ctx = await _flow_context(db_session)
    block = await _publish_block(db_session, ctx, ctx["class_a"], FLOW_DATE, "flow-race")
    payload = _create_payload(class_ids=[ctx["class_a"].id])
    preview = await _preview(db_session, ctx, payload)
    assert preview.requires_confirmation is True

    original_compute = internship_flow_service.compute_impact
    calls = {"count": 0}

    async def racing_compute(db, organization_id, class_ids, start_date, end_date):
        calls["count"] += 1
        result = await original_compute(db, organization_id, class_ids, start_date, end_date)
        if calls["count"] == 1:
            db.add(
                models.LessonLog(
                    organization_id=organization_id,
                    active_schedule_block_id=block.id,
                    status=models.LessonLogStatus.COMPLETED,
                )
            )
            await db.flush()
        return result

    organization_id = ctx["organization"].id
    monkeypatch.setattr(internship_flow_service, "compute_impact", racing_compute)

    with pytest.raises(internship_flow_service.InternshipFlowStale):
        await internship_flow_service.create_flow(
            db_session,
            organization_id,
            payload.model_copy(
                update={"confirmation_fingerprint": preview.confirmation_fingerprint}
            ),
        )
    await db_session.rollback()

    assert (
        await db_session.scalar(
            select(models.SchoolCalendarEvent.id).where(
                models.SchoolCalendarEvent.organization_id == organization_id
            )
        )
        is None
    )


async def test_rename_only_does_not_bump_scheduler_state_version(db_session):
    ctx = await _flow_context(db_session)
    await _publish_block(db_session, ctx, ctx["class_a"], FLOW_DATE, "flow-rename")
    event = await _create_confirmed(db_session, ctx, class_ids=[ctx["class_a"].id])
    await db_session.commit()
    state = await db_session.get(models.SchedulerSchoolYearState, ctx["state"].id)
    version_before = state.scheduler_state_version

    await internship_flow_service.update_flow(
        db_session,
        ctx["organization"].id,
        event.id,
        schemas.SchoolCalendarEventUpdate(
            name="Estágio renomeado",
            start_date=FLOW_DATE,
            end_date=FLOW_END,
            class_ids=[ctx["class_a"].id],
        ),
    )
    await db_session.commit()

    await db_session.refresh(state)
    assert state.scheduler_state_version == version_before
    updated = await db_session.get(models.SchoolCalendarEvent, event.id)
    assert updated.name == "Estágio renomeado"


async def test_each_removed_lesson_gets_one_absence_record(db_session):
    ctx = await _flow_context(db_session)
    first_block = await _publish_block(db_session, ctx, ctx["class_a"], FLOW_DATE, "flow-one")
    second_block = await _publish_block(db_session, ctx, ctx["class_a"], FLOW_END, "flow-two")
    existing = await _gap_occurrence(db_session, ctx, first_block)
    await db_session.commit()

    await _create_confirmed(db_session, ctx, class_ids=[ctx["class_a"].id])
    await db_session.commit()

    occurrences = (
        await db_session.scalars(
            select(models.LessonOccurrence)
            .where(
                models.LessonOccurrence.active_schedule_block_id.in_(
                    [first_block.id, second_block.id]
                )
            )
            .order_by(models.LessonOccurrence.active_schedule_block_id)
        )
    ).all()
    assert [item.active_schedule_block_id for item in occurrences] == [
        first_block.id,
        second_block.id,
    ]
    assert all(item.status is models.LessonOccurrenceStatus.GAP for item in occurrences)
    assert occurrences[0].id == existing.id
    assert occurrences[0].reason == existing.reason
    assert occurrences[1].creation_source == "internship_flow"
    assert occurrences[1].reason == internship_flow_service.INTERNSHIP_FLOW_OCCURRENCE_REASON
