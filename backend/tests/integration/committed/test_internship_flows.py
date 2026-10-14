from datetime import UTC, date, datetime, time, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import models, schemas
from app.core.exceptions import AppError
from app.scheduler.infrastructure import occurrences as occurrences_v1
from app.scheduler.infrastructure.models import (
    CurricularAssignment,
    CurricularRequirement,
    SchedulerLessonLogV1,
    SchedulerLessonSliceV1,
)
from app.scheduler.infrastructure.operations import record_lesson_log, week_schedule
from app.services import internship_flow_service, settings_service
from app.services.scheduler_fingerprint_service import SchedulerFingerprintService
from tests._support.scheduler_v1 import add_lesson, add_version

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
    slot_end = models.Timeslot(
        organization_id=organization.id,
        day_of_week=FLOW_END.weekday(),
        start_time=time(9),
        end_time=time(10),
    )
    db_session.add_all([user, school_year, course, subject, room, slot, slot_b, slot_end])
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
    module = models.Module(
        organization_id=organization.id,
        name="Module",
        code="FLW-1",
        hours_total=10,
        order=1,
        subject_id=subject.id,
    )
    link_a = models.ClassSubjectLink(
        organization_id=organization.id,
        class_id=class_a.id,
        subject_id=subject.id,
        grade_level=10,
        teacher_id=teacher.id,
    )
    link_b = models.ClassSubjectLink(
        organization_id=organization.id,
        class_id=class_b.id,
        subject_id=subject.id,
        grade_level=10,
        teacher_id=teacher.id,
    )
    db_session.add_all([module, link_a, link_b])
    await db_session.flush()
    # WBS 2.2.2: the planning loader reads the per-class module selection.
    await db_session.execute(
        models.class_subject_module.insert(),
        [
            {
                "organization_id": organization.id,
                "class_subject_link_id": link_a.id,
                "module_id": module.id,
            },
            {
                "organization_id": organization.id,
                "class_subject_link_id": link_b.id,
                "module_id": module.id,
            },
        ],
    )
    await db_session.execute(
        models.teacher_subject_link.insert().values(
            organization_id=organization.id,
            teacher_id=teacher.id,
            subject_id=subject.id,
        )
    )
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
        "slot_end": slot_end,
    }
    await db_session.commit()
    return ctx


async def _publish_block(db_session, ctx, class_, block_date, key, timeslot=None):
    assignment = await db_session.scalar(
        select(CurricularAssignment).where(
            CurricularAssignment.organization_id == ctx["organization"].id,
            CurricularAssignment.school_year_id == ctx["school_year"].id,
            CurricularAssignment.class_id == class_.id,
        )
    )
    if assignment is None:
        assignment = CurricularAssignment(
            organization_id=ctx["organization"].id,
            school_year_id=ctx["school_year"].id,
            class_id=class_.id,
            subject_id=ctx["subject"].id,
            teacher_id=ctx["teacher"].id,
        )
        db_session.add(assignment)
        await db_session.flush()
        module = await db_session.scalar(
            select(models.Module).where(
                models.Module.organization_id == ctx["organization"].id,
                models.Module.subject_id == ctx["subject"].id,
            )
        )
        db_session.add(
            CurricularRequirement(
                organization_id=ctx["organization"].id,
                assignment_id=assignment.id,
                module_id=module.id,
                sequence=module.order + 1,
                required_minutes=600,
            )
        )
    seed = SimpleNamespace(
        organization=ctx["organization"],
        year=ctx["school_year"],
        assignment=assignment,
        room=ctx["room"],
    )
    if "version" not in ctx:
        ctx["version"] = await add_version(db_session, seed)
        ctx["state"].active_schedule_version_id = str(ctx["version"].id)
        ctx["state"].school_year_publication_state = models.SchoolYearPublicationState.PUBLISHED
    slot = timeslot or (
        ctx["slot"] if block_date.weekday() == FLOW_DATE.weekday() else ctx["slot_end"]
    )
    start = datetime.combine(
        block_date, slot.start_time, tzinfo=ZoneInfo("Europe/Lisbon")
    ).astimezone(UTC)
    end = start + timedelta(hours=1)
    lesson = await add_lesson(
        db_session,
        seed,
        ctx["version"],
        stable_key=key,
        school_date=block_date,
        start=start,
        end=end,
    )
    module_id = await db_session.scalar(
        select(CurricularRequirement.module_id).where(
            CurricularRequirement.assignment_id == assignment.id
        )
    )
    db_session.add(
        SchedulerLessonSliceV1(
            organization_id=ctx["organization"].id,
            school_year_id=ctx["school_year"].id,
            lesson_id=lesson.id,
            module_id=module_id,
            offset_minutes=0,
            minutes=60,
        )
    )
    await db_session.commit()
    return lesson


async def _log(db_session, ctx, lesson, status="OCCURRENCE"):
    await record_lesson_log(
        db_session,
        ctx["organization"].id,
        membership_id=ctx["membership"].id,
        lesson_id=lesson.id,
        status=status,
        summary="Historical lesson",
        notes=None,
        now_utc=lesson.ends_at,
    )
    await db_session.flush()
    return await db_session.scalar(
        select(SchedulerLessonLogV1).where(SchedulerLessonLogV1.lesson_id == lesson.id)
    )


async def _logs(db_session, ctx):
    return (
        await db_session.scalars(
            select(SchedulerLessonLogV1)
            .where(SchedulerLessonLogV1.organization_id == ctx["organization"].id)
            .order_by(SchedulerLessonLogV1.lesson_id)
        )
    ).all()


async def _week(db_session, ctx):
    return await week_schedule(
        db_session,
        ctx["organization"].id,
        week_start=FLOW_DATE,
        class_id=None,
        teacher_id=ctx["teacher"].id,
    )


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
    first = await _publish_block(db_session, ctx, ctx["class_a"], FLOW_DATE, "a")
    second = await _publish_block(db_session, ctx, ctx["class_b"], FLOW_DATE, "b", ctx["slot_b"])
    preview = await _preview(db_session, ctx, _create_payload(class_ids=[ctx["class_a"].id]))
    assert preview.requires_confirmation is True
    assert [row.lesson_id for row in preview.affected_lessons] == [first.id]
    event = await _create_confirmed(db_session, ctx, class_ids=[ctx["class_a"].id])
    await db_session.commit()
    logs = await _logs(db_session, ctx)
    assert [(log.lesson_id, log.status, log.decision) for log in logs] == [
        (first.id, "OCCURRENCE", "GAP")
    ]
    assert event.class_ids == [ctx["class_a"].id]
    assert ctx["state"].scheduler_state_version > 0
    assert [item["scheduler_lesson_id"] for item in await _week(db_session, ctx)] == [second.id]
    debts = await occurrences_v1.get_debts(db_session, ctx["organization"].id)
    assert debts["total_gaps"] == 1


async def test_empty_flow_does_not_block_or_require_confirmation(db_session):
    ctx = await _flow_context(db_session)
    lesson = await _publish_block(db_session, ctx, ctx["class_a"], FLOW_DATE, "a")
    preview = await _preview(db_session, ctx, _create_payload())
    assert preview.requires_confirmation is False
    assert preview.affected_lessons == []
    await _create_confirmed(db_session, ctx)
    await db_session.commit()
    assert await _logs(db_session, ctx) == []
    assert [item["scheduler_lesson_id"] for item in await _week(db_session, ctx)] == [lesson.id]
    assert ctx["state"].scheduler_state_version == 0


async def test_confirmation_is_required_and_stale_fingerprints_are_rejected(db_session):
    ctx = await _flow_context(db_session)
    lesson = await _publish_block(db_session, ctx, ctx["class_a"], FLOW_DATE, "a")
    payload = _create_payload(class_ids=[ctx["class_a"].id])
    with pytest.raises(internship_flow_service.InternshipFlowConfirmationRequired):
        await internship_flow_service.create_flow(db_session, ctx["organization"].id, payload)
    preview = await _preview(db_session, ctx, payload)
    await _log(db_session, ctx, lesson, "COMPLETED")
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
    given = await _publish_block(db_session, ctx, ctx["class_a"], FLOW_DATE, "given")
    missing = await _publish_block(db_session, ctx, ctx["class_a"], FLOW_END, "gap")
    await _log(db_session, ctx, given, "COMPLETED")
    existing = await _log(db_session, ctx, missing)
    existing_id = existing.id
    await _create_confirmed(db_session, ctx, class_ids=[ctx["class_a"].id])
    await db_session.commit()
    logs = await _logs(db_session, ctx)
    assert [(log.lesson_id, log.status) for log in logs] == [
        (given.id, "COMPLETED"),
        (missing.id, "OCCURRENCE"),
    ]
    assert logs[1].id == existing_id
    assert logs[1].decision == "GAP"
    assert logs[1].withdrawn_at is not None
    assert [item["scheduler_lesson_id"] for item in await _week(db_session, ctx)] == [given.id]


async def test_update_and_delete_do_not_restore_removed_lessons(db_session):
    ctx = await _flow_context(db_session)
    await _publish_block(db_session, ctx, ctx["class_a"], FLOW_DATE, "a")
    event = await _create_confirmed(db_session, ctx, class_ids=[ctx["class_a"].id])
    await db_session.commit()
    await internship_flow_service.update_flow(
        db_session,
        ctx["organization"].id,
        event.id,
        schemas.SchoolCalendarEventUpdate(
            name="Renamed", start_date=FLOW_DATE, end_date=FLOW_END, class_ids=[]
        ),
    )
    await internship_flow_service.delete_flow(db_session, ctx["organization"].id, event.id)
    await db_session.commit()
    assert [(log.status, log.decision) for log in await _logs(db_session, ctx)] == [
        ("OCCURRENCE", "GAP")
    ]
    assert all(log.withdrawn_at is not None for log in await _logs(db_session, ctx))
    assert await _week(db_session, ctx) == []
    assert await db_session.get(models.SchoolCalendarEvent, event.id) is None


async def test_removed_lesson_is_recorded_as_absence(db_session):
    ctx = await _flow_context(db_session)
    lesson = await _publish_block(db_session, ctx, ctx["class_a"], FLOW_DATE, "a")
    await _create_confirmed(db_session, ctx, class_ids=[ctx["class_a"].id])
    await db_session.commit()
    history = await settings_service.list_calendar_events(db_session, ctx["organization"].id)
    assert [event.name for event in history] == ["Estágio 10A"]
    page = await occurrences_v1.list_occurrences(db_session, ctx["organization"].id)
    assert page["total"] == 1
    assert page["items"][0]["status"] == "GAP"
    assert page["items"][0]["class_id"] == ctx["class_a"].id
    assert (await _logs(db_session, ctx))[0].lesson_id == lesson.id


async def test_removed_lesson_absence_survives_a_new_active_version(db_session):
    ctx = await _flow_context(db_session)
    await _publish_block(db_session, ctx, ctx["class_a"], FLOW_DATE, "a")
    await _create_confirmed(db_session, ctx, class_ids=[ctx["class_a"].id])
    ctx["version"].status = "SUPERSEDED"
    await db_session.flush()
    seed = SimpleNamespace(organization=ctx["organization"], year=ctx["school_year"])
    republished = await add_version(db_session, seed, digest="b" * 64)
    ctx["state"].active_schedule_version_id = str(republished.id)
    await db_session.commit()
    page = await occurrences_v1.list_occurrences(db_session, ctx["organization"].id)
    assert page["total"] == 1
    assert page["items"][0]["status"] == "GAP"


async def test_confirmation_is_recomputed_under_lock(db_session, monkeypatch):
    ctx = await _flow_context(db_session)
    lesson = await _publish_block(db_session, ctx, ctx["class_a"], FLOW_DATE, "a")
    payload = _create_payload(class_ids=[ctx["class_a"].id])
    preview = await _preview(db_session, ctx, payload)
    original = internship_flow_service.compute_impact
    calls = 0

    async def racing_compute(db, organization_id, class_ids, start_date, end_date):
        nonlocal calls
        calls += 1
        impact = await original(db, organization_id, class_ids, start_date, end_date)
        if calls == 1:
            await _log(db, ctx, lesson, "COMPLETED")
        return impact

    monkeypatch.setattr(internship_flow_service, "compute_impact", racing_compute)
    with pytest.raises(internship_flow_service.InternshipFlowStale):
        await internship_flow_service.create_flow(
            db_session,
            ctx["organization"].id,
            payload.model_copy(
                update={"confirmation_fingerprint": preview.confirmation_fingerprint}
            ),
        )


async def test_each_removed_lesson_gets_one_absence_record(db_session):
    ctx = await _flow_context(db_session)
    first = await _publish_block(db_session, ctx, ctx["class_a"], FLOW_DATE, "a")
    second = await _publish_block(db_session, ctx, ctx["class_a"], FLOW_END, "b")
    existing = await _log(db_session, ctx, first)
    existing_id = existing.id
    await _create_confirmed(db_session, ctx, class_ids=[ctx["class_a"].id])
    await db_session.commit()
    logs = await _logs(db_session, ctx)
    assert [log.lesson_id for log in logs] == [first.id, second.id]
    assert logs[0].id == existing_id
    assert all(log.decision == "GAP" for log in logs)


async def test_flow_blocks_substitution_decisions_inside_flow_dates(db_session):
    ctx = await _flow_context(db_session)
    lesson = await _publish_block(db_session, ctx, ctx["class_a"], FLOW_DATE, "a")
    await _create_confirmed(db_session, ctx, class_ids=[ctx["class_a"].id])
    await db_session.commit()
    log = (await _logs(db_session, ctx))[0]
    with pytest.raises(AppError) as error:
        await occurrences_v1.update_occurrence(
            db_session,
            ctx["organization"].id,
            log.id,
            schemas.LessonOccurrenceUpdate(
                status=models.LessonOccurrenceStatus.SUBSTITUTED,
                version=log.revision,
                substitute_teacher_id=ctx["teacher"].id,
                substitute_subject_id=ctx["subject"].id,
            ),
            decided_by_membership_id=ctx["membership"].id,
            now_utc=lesson.ends_at,
        )
    assert error.value.kind == "conflict"
    assert error.value.detail == "A aula foi retirada por fluxo de estágio."


async def test_flow_cancels_pending_substitutions_and_keeps_taught_ones(db_session):
    ctx = await _flow_context(db_session)
    lessons = [
        await _publish_block(db_session, ctx, ctx["class_a"], day, key)
        for day, key in ((FLOW_DATE, "pending-substitution"), (FLOW_END, "taught-substitution"))
    ]
    blocks = []
    for lesson in lessons:
        log = await _log(db_session, ctx, lesson)
        log.decision = "SUBSTITUTED"
        log.decided_at = lesson.ends_at
        log.decided_by_membership_id = ctx["membership"].id
        block = models.OperationalScheduleBlock(
            organization_id=ctx["organization"].id,
            origin_kind=models.OperationalBlockOrigin.V1,
            source_v1_lesson_log_id=log.id,
            substitute_curricular_assignment_id=lesson.assignment_id,
            date=lesson.school_date,
            timeslot_id=ctx["slot"].id,
            room_id=ctx["room"].id,
            class_id=ctx["class_a"].id,
            teacher_id=ctx["teacher"].id,
            subject_id=ctx["subject"].id,
            status=models.OperationalBlockStatus.ACTIVE,
            execution_status=models.OperationalBlockExecutionStatus.PENDING_LOG,
        )
        db_session.add(block)
        await db_session.flush()
        blocks.append(block)
    taught = blocks[1]
    taught.execution_status = models.OperationalBlockExecutionStatus.COMPLETED
    db_session.add(
        models.LessonLog(
            organization_id=ctx["organization"].id,
            operational_block_id=taught.id,
            logged_by_membership_id=ctx["membership"].id,
            status=models.LessonLogStatus.COMPLETED,
        )
    )
    await db_session.commit()

    await _create_confirmed(db_session, ctx, class_ids=[ctx["class_a"].id])
    await db_session.commit()

    for block in blocks:
        await db_session.refresh(block)
    assert blocks[0].status is models.OperationalBlockStatus.CANCELLED
    assert blocks[0].execution_status is models.OperationalBlockExecutionStatus.CANCELLED
    assert blocks[0].cancelled_at is not None
    assert taught.status is models.OperationalBlockStatus.ACTIVE
    assert taught.execution_status is models.OperationalBlockExecutionStatus.COMPLETED


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
