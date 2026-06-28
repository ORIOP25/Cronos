from datetime import date, datetime, time, timezone

import pytest

from app import models
from app.services.scheduler_fingerprint_service import (
    SchedulerFingerprintError,
    SchedulerFingerprintService,
)
from app.services.scheduler_serialization import canonical_json_bytes, sha256_json


pytestmark = pytest.mark.integration


def test_canonical_hash_is_stable_across_mapping_and_set_order():
    first = {"b": {3, 1, 2}, "a": {"date": date(2026, 1, 2), "value": 4}}
    second = {"a": {"value": 4, "date": date(2026, 1, 2)}, "b": {2, 3, 1}}

    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert sha256_json(first) == sha256_json(second)
    assert len(sha256_json(first)) == 64


@pytest.mark.asyncio
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


@pytest.mark.asyncio
async def test_strategy_changes_snapshot_and_adaptive_includes_active_schedule(db_session):
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
    assert adaptive.snapshot["active_schedule"] == []
    assert adaptive.value != complete.value


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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
        now=datetime(2026, 6, 1, 23, 30, tzinfo=timezone.utc),
    )

    assert result.editable_start_date == date(2026, 6, 2)
    assert result.snapshot == {
        "editable_start_date": "2026-06-02",
        "repair_stability_window_days": 0,
        "school_timezone": "Europe/Lisbon",
        "school_today": "2026-06-02",
    }
    assert result.value == sha256_json(result.snapshot)

    settings.repair_stability_window_days = -1
    await db_session.flush()
    with pytest.raises(SchedulerFingerprintError, match="cannot be negative"):
        await SchedulerFingerprintService(db_session).repair_policy_snapshot(
            organization.id,
            school_year.id,
            now=datetime(2026, 6, 1, 23, 30, tzinfo=timezone.utc),
        )


@pytest.mark.asyncio
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
    db_session.add_all([state, settings])
    await db_session.commit()
    service = SchedulerFingerprintService(db_session)
    instant = datetime(2026, 1, 5, 12, tzinfo=timezone.utc)

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
    assert policy_before.editable_start_date == date(2026, 1, 12)
    assert policy_after.editable_start_date == date(2026, 1, 19)
    assert state.scheduler_state_version == 0


@pytest.mark.asyncio
async def test_legacy_lessons_include_scheduler_inputs_and_ignore_other_year_events(db_session):
    organization = models.Organization(name="Legacy Inputs", plan_status="active")
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
        name="Legacy Course",
        abbreviation="LEG",
    )
    subject = models.Subject(
        organization_id=organization.id,
        name="Legacy Subject",
        required_room_type=models.RoomType.normal,
    )
    teacher = models.Teacher(organization_id=organization.id, name="Legacy Teacher")
    slot = models.Timeslot(
        organization_id=organization.id,
        day_of_week=1,
        start_time=time(9, 0),
        end_time=time(10, 0),
    )
    db_session.add_all([school_year, course, subject, teacher, slot])
    await db_session.flush()
    state = models.SchedulerSchoolYearState(
        organization_id=organization.id,
        school_year_id=school_year.id,
    )
    class_ = models.Class(
        organization_id=organization.id,
        name="Legacy Class",
        size=20,
        start_year=2025,
        end_year=2026,
        grade_level=10,
        course_id=course.id,
    )
    module = models.Module(
        organization_id=organization.id,
        subject_id=subject.id,
        name="Legacy Module",
        code="LM1",
        hours_total=10,
        order=1,
    )
    db_session.add_all([state, class_, module])
    await db_session.flush()
    lesson = models.Lesson(
        organization_id=organization.id,
        class_id=class_.id,
        subject_id=subject.id,
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
    db_session.add_all([lesson, availability, old_event])
    await db_session.commit()

    service = SchedulerFingerprintService(db_session)
    first = await service.generation_input_fingerprint(
        organization.id,
        school_year.id,
        models.ScheduleGenerationStrategy.COMPLETE_GENERATION,
    )
    assert first.snapshot["subjects"] == [
        {"id": subject.id, "required_room_type": "normal"}
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
