from datetime import UTC, date, datetime, time

import pytest

from app import models
from app.scheduler.domain.serialization import canonical_json, payload_digest
from app.services.scheduler_fingerprint_service import (
    SchedulerFingerprintError,
    SchedulerFingerprintService,
)
from tests._support.db_fixtures import create_teacher_profile


def test_canonical_hash_is_stable_across_mapping_and_set_order():
    first = {"b": {3, 1, 2}, "a": {"date": date(2026, 1, 2), "value": 4}}
    second = {"a": {"value": 4, "date": date(2026, 1, 2)}, "b": {2, 3, 1}}

    assert canonical_json(first) == canonical_json(second)
    assert payload_digest(first) == payload_digest(second)
    assert len(payload_digest(first)) == 64


async def test_generation_input_fingerprint_changes_only_for_canonical_inputs(db_session):
    organization = models.Organization(name="Fingerprint School", plan_status="active")
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
    room = models.Room(
        organization_id=organization.id,
        name="Original name",
        type=models.RoomType.normal,
        capacity=20,
    )
    slot = models.Timeslot(
        organization_id=organization.id,
        day_of_week=1,
        start_time=time(9, 0),
        end_time=time(10, 0),
    )
    db_session.add_all([state, room, slot])
    await db_session.commit()

    service = SchedulerFingerprintService(db_session)
    first = await service.generation_input_fingerprint(
        organization.id,
        school_year.id,
        models.ScheduleGenerationStrategy.COMPLETE_GENERATION,
    )
    room.name = "Display name changed"
    await db_session.flush()
    renamed = await service.generation_input_fingerprint(
        organization.id,
        school_year.id,
        models.ScheduleGenerationStrategy.COMPLETE_GENERATION,
    )
    assert renamed.value == first.value

    room.capacity = 25
    await db_session.flush()
    resized = await service.generation_input_fingerprint(
        organization.id,
        school_year.id,
        models.ScheduleGenerationStrategy.COMPLETE_GENERATION,
    )
    assert resized.value != first.value


async def test_strategy_changes_snapshot_without_retired_active_schedule(db_session):
    organization = models.Organization(name="Strategy Fingerprint", plan_status="active")
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
    await db_session.commit()

    service = SchedulerFingerprintService(db_session)
    complete = await service.generation_input_fingerprint(
        organization.id,
        school_year.id,
        models.ScheduleGenerationStrategy.COMPLETE_GENERATION,
    )
    adaptive = await service.generation_input_fingerprint(
        organization.id,
        school_year.id,
        models.ScheduleGenerationStrategy.ADAPTIVE_REPAIR,
    )

    assert "active_schedule" not in complete.snapshot
    assert "active_schedule" not in adaptive.snapshot
    assert adaptive.value != complete.value


async def test_recreated_semantically_identical_calendar_event_keeps_fingerprint(db_session):
    organization = models.Organization(name="Calendar Fingerprint", plan_status="active")
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
    first_event = models.SchoolCalendarEvent(
        organization_id=organization.id,
        name="Display label one",
        start_date=date(2025, 12, 25),
        end_date=date(2025, 12, 25),
        event_type=models.CalendarEventType.national_holiday,
        source=models.CalendarEventSource.auto,
    )
    db_session.add(first_event)
    await db_session.commit()
    service = SchedulerFingerprintService(db_session)
    first = await service.generation_input_fingerprint(
        organization.id,
        school_year.id,
        models.ScheduleGenerationStrategy.COMPLETE_GENERATION,
    )

    await db_session.delete(first_event)
    await db_session.flush()
    db_session.add(
        models.SchoolCalendarEvent(
            organization_id=organization.id,
            name="Different display label",
            start_date=date(2025, 12, 25),
            end_date=date(2025, 12, 25),
            event_type=models.CalendarEventType.national_holiday,
            source=models.CalendarEventSource.auto,
        )
    )
    await db_session.flush()
    recreated = await service.generation_input_fingerprint(
        organization.id,
        school_year.id,
        models.ScheduleGenerationStrategy.COMPLETE_GENERATION,
    )

    assert recreated.value == first.value


async def test_repair_policy_snapshot_uses_school_local_date_and_allows_zero(db_session):
    organization = models.Organization(name="Policy Snapshot", plan_status="active")
    db_session.add(organization)
    await db_session.flush()
    school_year = models.SchedulerSchoolYear(
        organization_id=organization.id,
        label="2025/2026",
        start_date=date(2025, 9, 1),
        hard_end_date=date(2026, 7, 15),
        timezone="Europe/Lisbon",
    )
    settings = models.OrganizationSettings(
        organization_id=organization.id,
        school_start_date=school_year.start_date,
        school_hard_end_date=school_year.hard_end_date,
        repair_stability_window_days=0,
    )
    db_session.add_all([school_year, settings])
    await db_session.commit()

    result = await SchedulerFingerprintService(db_session).repair_policy_snapshot(
        organization.id,
        school_year.id,
        now=datetime(2026, 6, 1, 23, 30, tzinfo=UTC),
    )

    assert result.editable_start_date == date(2026, 6, 2)
    assert result.snapshot == {
        "editable_start_date": "2026-06-02",
        "grid_days": [],
        "repair_stability_window_days": 0,
        "school_timezone": "Europe/Lisbon",
        "school_today": "2026-06-02",
    }
    assert result.value == payload_digest(result.snapshot)

    settings.repair_stability_window_days = -1
    await db_session.flush()
    with pytest.raises(SchedulerFingerprintError, match="cannot be negative"):
        await SchedulerFingerprintService(db_session).repair_policy_snapshot(
            organization.id,
            school_year.id,
            now=datetime(2026, 6, 1, 23, 30, tzinfo=UTC),
        )


async def test_repair_policy_change_has_separate_hash_from_generation_inputs(db_session):
    organization = models.Organization(name="Policy Separation", plan_status="active")
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
    settings = models.OrganizationSettings(
        organization_id=organization.id,
        school_start_date=school_year.start_date,
        school_hard_end_date=school_year.hard_end_date,
        repair_stability_window_days=7,
    )
    db_session.add_all(
        [
            state,
            settings,
            models.Timeslot(
                organization_id=organization.id,
                day_of_week=0,
                start_time=time(9, 0),
                end_time=time(10, 0),
            ),
        ]
    )
    await db_session.commit()
    service = SchedulerFingerprintService(db_session)
    instant = datetime(2026, 1, 5, 12, tzinfo=UTC)

    generation_before = await service.generation_input_fingerprint(
        organization.id,
        school_year.id,
        models.ScheduleGenerationStrategy.ADAPTIVE_REPAIR,
    )
    policy_before = await service.repair_policy_snapshot(
        organization.id, school_year.id, now=instant
    )
    settings.repair_stability_window_days = 14
    await db_session.flush()
    generation_after = await service.generation_input_fingerprint(
        organization.id,
        school_year.id,
        models.ScheduleGenerationStrategy.ADAPTIVE_REPAIR,
    )
    policy_after = await service.repair_policy_snapshot(
        organization.id, school_year.id, now=instant
    )

    assert generation_after.value == generation_before.value
    assert policy_after.value != policy_before.value
    assert policy_before.editable_start_date == date(2026, 2, 23)
    assert policy_after.editable_start_date == date(2026, 4, 13)
    assert state.scheduler_state_version == 0


async def test_repair_policy_counts_grid_days_and_ignores_calendar_events(db_session):
    organization = models.Organization(name="Grid Policy", plan_status="active")
    db_session.add(organization)
    await db_session.flush()
    school_year = models.SchedulerSchoolYear(
        organization_id=organization.id,
        label="2025/2026",
        start_date=date(2025, 9, 1),
        hard_end_date=date(2026, 7, 15),
        timezone="Europe/Lisbon",
    )
    settings = models.OrganizationSettings(
        organization_id=organization.id,
        school_start_date=school_year.start_date,
        school_hard_end_date=school_year.hard_end_date,
        repair_stability_window_days=2,
    )
    db_session.add_all(
        [
            school_year,
            settings,
            models.Timeslot(
                organization_id=organization.id,
                day_of_week=0,
                start_time=time(9, 0),
                end_time=time(10, 0),
            ),
            models.SchoolCalendarEvent(
                organization_id=organization.id,
                name="Feriado na segunda",
                start_date=date(2026, 1, 12),
                end_date=date(2026, 1, 12),
                event_type=models.CalendarEventType.national_holiday,
                source=models.CalendarEventSource.auto,
            ),
        ]
    )
    await db_session.commit()
    service = SchedulerFingerprintService(db_session)
    instant = datetime(2026, 1, 5, 12, tzinfo=UTC)

    policy = await service.repair_policy_snapshot(organization.id, school_year.id, now=instant)

    assert policy.snapshot["grid_days"] == [0]
    assert policy.editable_start_date == date(2026, 1, 19)

    db_session.add(
        models.Timeslot(
            organization_id=organization.id,
            day_of_week=1,
            start_time=time(9, 0),
            end_time=time(10, 0),
        )
    )
    await db_session.commit()
    changed = await service.repair_policy_snapshot(organization.id, school_year.id, now=instant)

    assert changed.snapshot["grid_days"] == [0, 1]
    assert changed.value != policy.value
    assert changed.editable_start_date == date(2026, 1, 12)


async def test_class_subject_requirements_include_scheduler_inputs_and_ignore_other_year_events(
    db_session,
):
    organization = models.Organization(name="Canonical Inputs", plan_status="active")
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
        name="Canonical Course",
        abbreviation="LEG",
    )
    subject = models.Subject(
        organization_id=organization.id,
        name="Canonical Subject",
        required_room_type=models.RoomType.normal,
    )
    teacher = await create_teacher_profile(
        db_session,
        organization_id=organization.id,
        name="Canonical Teacher",
    )
    slot = models.Timeslot(
        organization_id=organization.id,
        day_of_week=1,
        start_time=time(9, 0),
        end_time=time(10, 0),
    )
    db_session.add_all([school_year, course, subject, slot])
    await db_session.flush()
    state = models.SchedulerSchoolYearState(
        organization_id=organization.id,
        school_year_id=school_year.id,
    )
    class_ = models.Class(
        organization_id=organization.id,
        name="Canonical Class",
        size=20,
        start_year=2025,
        end_year=2026,
        grade_level=10,
        course_id=course.id,
    )
    module = models.Module(
        organization_id=organization.id,
        subject_id=subject.id,
        name="Canonical Module",
        code="LM1",
        hours_total=10,
        order=1,
    )
    db_session.add_all([state, class_, module])
    await db_session.flush()
    assignment = models.ClassSubjectLink(
        organization_id=organization.id,
        class_id=class_.id,
        subject_id=subject.id,
        grade_level=class_.grade_level,
        teacher_id=teacher.id,
    )
    availability = models.Availability(
        organization_id=organization.id,
        teacher_id=teacher.id,
        timeslot_id=slot.id,
        score=1,
    )
    old_event = models.SchoolCalendarEvent(
        organization_id=organization.id,
        name="Old holiday",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 1),
        event_type=models.CalendarEventType.national_holiday,
        source=models.CalendarEventSource.auto,
    )
    db_session.add_all([assignment, availability, old_event])
    await db_session.commit()

    service = SchedulerFingerprintService(db_session)
    first = await service.generation_input_fingerprint(
        organization.id,
        school_year.id,
        models.ScheduleGenerationStrategy.COMPLETE_GENERATION,
    )
    assert first.snapshot["subjects"] == [{"id": subject.id, "required_room_type": "normal"}]
    assert first.snapshot["class_subject_requirements"] == [
        {
            "class_id": class_.id,
            "subject_id": subject.id,
            "grade_level": class_.grade_level,
            "teacher_id": teacher.id,
        }
    ]
    assert first.snapshot["module_accounting"][0]["id"] == module.id
    assert first.snapshot["teacher_availability"] == [
        {"teacher_id": teacher.id, "timeslot_id": slot.id, "score": 1}
    ]
    assert first.snapshot["calendar_events"] == []

    old_event.start_date = date(2024, 2, 1)
    old_event.end_date = date(2024, 2, 1)
    await db_session.flush()
    after_irrelevant_event = await service.generation_input_fingerprint(
        organization.id,
        school_year.id,
        models.ScheduleGenerationStrategy.COMPLETE_GENERATION,
    )
    assert after_irrelevant_event.value == first.value


async def test_fingerprint_tracks_class_availability_and_ignores_archived_classes(db_session):
    organization = models.Organization(name="Class Availability Fingerprint", plan_status="active")
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
    course = models.Course(
        organization_id=organization.id, name="Fingerprint Course", abbreviation="FPC"
    )
    slot = models.Timeslot(
        organization_id=organization.id,
        day_of_week=1,
        start_time=time(9, 0),
        end_time=time(10, 0),
    )
    db_session.add_all([course, slot])
    await db_session.flush()
    class_ = models.Class(
        organization_id=organization.id,
        name="Fingerprint Class",
        size=20,
        start_year=2025,
        end_year=2026,
        grade_level=10,
        course_id=course.id,
    )
    db_session.add(class_)
    await db_session.flush()
    row = models.ClassAvailability(
        organization_id=organization.id,
        class_id=class_.id,
        timeslot_id=slot.id,
        score=models.PreferenceLevel.IMPOSSIBLE.value,
    )
    db_session.add(row)
    await db_session.flush()

    service = SchedulerFingerprintService(db_session)

    async def fingerprint():
        return await service.generation_input_fingerprint(
            organization.id,
            school_year.id,
            models.ScheduleGenerationStrategy.COMPLETE_GENERATION,
        )

    first = await fingerprint()
    assert first.snapshot["class_availability"] == [
        {
            "class_id": class_.id,
            "timeslot_id": slot.id,
            "score": models.PreferenceLevel.IMPOSSIBLE.value,
        }
    ]

    row.score = models.PreferenceLevel.AVOID.value
    await db_session.flush()
    changed = await fingerprint()
    assert changed.value != first.value
    assert changed.snapshot["class_availability"][0]["score"] == models.PreferenceLevel.AVOID.value

    class_.is_archived = True
    await db_session.flush()
    archived = await fingerprint()
    assert archived.snapshot["class_availability"] == []
    assert archived.value != changed.value


async def test_generation_input_snapshot_tracks_the_class_subject_module_selection(db_session):
    organization = models.Organization(name="Selection Fingerprint", plan_status="active")
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
        name="Selection Course",
        abbreviation="SEL",
    )
    subject = models.Subject(
        organization_id=organization.id,
        name="Selection Subject",
        required_room_type=models.RoomType.normal,
    )
    db_session.add_all([school_year, course, subject])
    await db_session.flush()
    state = models.SchedulerSchoolYearState(
        organization_id=organization.id,
        school_year_id=school_year.id,
    )
    class_ = models.Class(
        organization_id=organization.id,
        name="Selection Class",
        size=20,
        start_year=2025,
        end_year=2026,
        grade_level=10,
        course_id=course.id,
    )
    module_one = models.Module(
        organization_id=organization.id,
        subject_id=subject.id,
        name="Selection Module One",
        required_minutes=60,
        order=1,
    )
    module_two = models.Module(
        organization_id=organization.id,
        subject_id=subject.id,
        name="Selection Module Two",
        required_minutes=60,
        order=2,
    )
    db_session.add_all([state, class_, module_one, module_two])
    await db_session.flush()
    link = models.ClassSubjectLink(
        organization_id=organization.id,
        class_id=class_.id,
        subject_id=subject.id,
        grade_level=class_.grade_level,
        teacher_id=None,
    )
    db_session.add(link)
    await db_session.flush()
    await db_session.execute(
        models.class_subject_module.insert().values(
            organization_id=organization.id,
            class_subject_link_id=link.id,
            module_id=module_one.id,
        )
    )
    await db_session.commit()

    service = SchedulerFingerprintService(db_session)
    first = await service.generation_input_fingerprint(
        organization.id,
        school_year.id,
        models.ScheduleGenerationStrategy.COMPLETE_GENERATION,
    )
    assert first.snapshot["class_subject_modules"] == [
        {
            "class_id": class_.id,
            "subject_id": subject.id,
            "grade_level": class_.grade_level,
            "module_id": module_one.id,
        }
    ]

    await db_session.execute(
        models.class_subject_module.insert().values(
            organization_id=organization.id,
            class_subject_link_id=link.id,
            module_id=module_two.id,
        )
    )
    await db_session.commit()
    second = await service.generation_input_fingerprint(
        organization.id,
        school_year.id,
        models.ScheduleGenerationStrategy.COMPLETE_GENERATION,
    )

    assert second.value != first.value
    assert second.snapshot["class_subject_modules"] == [
        {
            "class_id": class_.id,
            "subject_id": subject.id,
            "grade_level": class_.grade_level,
            "module_id": module_one.id,
        },
        {
            "class_id": class_.id,
            "subject_id": subject.id,
            "grade_level": class_.grade_level,
            "module_id": module_two.id,
        },
    ]
