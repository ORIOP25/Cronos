from datetime import date

import pytest
from sqlalchemy import select

from app import models, schemas
from app.services import (
    class_service,
    room_service,
    room_type_service,
    schedule_service,
    settings_service,
    subject_service,
    teacher_service,
    timeslot_service,
)
from app.services.scheduler_state_service import SchedulerStateService
from tests._support.db_fixtures import create_teacher_profile, get_school_room_type_id


async def test_scheduler_shaping_writes_increment_but_policy_and_text_do_not(db_session):
    organization = models.Organization(name="Versioned School", plan_status="active")
    db_session.add(organization)
    await db_session.commit()
    # Uma escola precisa dos tipos de sala iniciais antes de ter salas (S2).
    await room_type_service.ensure_initial_room_types(db_session, organization.id)

    await settings_service.upsert_settings(
        db_session,
        organization.id,
        schemas.OrganizationSettingsUpsert(
            school_start_date=date(2025, 9, 1),
            school_hard_end_date=date(2026, 7, 15),
            repair_stability_window_days=14,
        ),
    )
    service = SchedulerStateService(db_session)
    school_year = await service.get_active_school_year(organization.id)
    assert school_year is not None
    state = await service.get_state(organization.id, school_year.id)
    assert state is not None
    assert state.scheduler_state_version == 1

    await settings_service.upsert_settings(
        db_session,
        organization.id,
        schemas.OrganizationSettingsUpsert(repair_stability_window_days=7),
    )
    await db_session.refresh(state)
    assert state.scheduler_state_version == 1

    room = await room_service.create_room(
        db_session,
        schemas.RoomCreate(name="Room A", capacity=20),
        organization.id,
    )
    await db_session.refresh(state)
    assert state.scheduler_state_version == 2

    await room_service.update_room(
        db_session,
        room.id,
        schemas.RoomUpdate(name="Renamed Room"),
        organization.id,
    )
    await db_session.refresh(state)
    assert state.scheduler_state_version == 2

    await room_service.update_room(
        db_session,
        room.id,
        schemas.RoomUpdate(capacity=30),
        organization.id,
    )
    await db_session.refresh(state)
    assert state.scheduler_state_version == 3

    timeslot = await timeslot_service.create_timeslot(
        db_session,
        schemas.TimeslotCreate(
            day_of_week=1,
            start_time="09:00",
            end_time="10:00",
        ),
        organization.id,
    )
    await db_session.refresh(state)
    assert state.scheduler_state_version == 4

    teacher = await create_teacher_profile(
        db_session,
        name="Unassigned Teacher",
        organization_id=organization.id,
    )
    await db_session.refresh(state)
    assert state.scheduler_state_version == 4
    membership = await db_session.get(
        models.OrganizationMembership,
        teacher.organization_membership_id,
    )
    assert membership is not None
    membership.organization_display_name = "Renamed Unassigned Teacher"
    await db_session.flush()
    await db_session.refresh(state)
    assert state.scheduler_state_version == 4
    await teacher_service.set_teacher_availability(
        db_session,
        teacher.id,
        [schemas.AvailabilitySelfCreate(timeslot_id=timeslot.id, score=0)],
        organization.id,
    )
    await db_session.refresh(state)
    assert state.scheduler_state_version == 4

    subject = models.Subject(
        name="Math",
        organization_id=organization.id,
        room_type_id=await get_school_room_type_id(db_session, organization.id, "Normal"),
    )
    course = models.Course(
        name="Science",
        abbreviation="SCI",
        organization_id=organization.id,
    )
    db_session.add_all([subject, course])
    await db_session.flush()
    class_ = models.Class(
        name="10A",
        size=20,
        start_year=2025,
        end_year=2026,
        grade_level=10,
        course_id=course.id,
        organization_id=organization.id,
    )
    db_session.add(class_)
    await db_session.flush()
    db_session.add(
        models.ClassSubjectLink(
            organization_id=organization.id,
            class_id=class_.id,
            subject_id=subject.id,
            grade_level=10,
            teacher_id=teacher.id,
        )
    )
    await db_session.commit()
    await teacher_service.set_teacher_availability(
        db_session,
        teacher.id,
        [schemas.AvailabilitySelfCreate(timeslot_id=timeslot.id, score=2)],
        organization.id,
    )
    await db_session.refresh(state)
    assert state.scheduler_state_version == 5

    first_module = models.Module(
        organization_id=organization.id,
        subject_id=subject.id,
        name="Module A",
        code="A",
        hours_total=10,
        order=0,
    )
    second_module = models.Module(
        organization_id=organization.id,
        subject_id=subject.id,
        name="Module B",
        code="B",
        hours_total=10,
        order=1,
    )
    db_session.add_all([first_module, second_module])
    await db_session.commit()

    await subject_service.update_subject(
        db_session,
        subject.id,
        schemas.SubjectUpdate(
            modules=[
                schemas.ModuleUpsert(
                    id=second_module.id,
                    name="Module B renamed",
                    code="B2",
                    hours_total=10,
                    order=0,
                ),
                schemas.ModuleUpsert(
                    id=first_module.id,
                    name="Module A renamed",
                    code="A2",
                    hours_total=10,
                    order=1,
                ),
            ]
        ),
        organization.id,
    )
    await db_session.refresh(state)
    assert state.scheduler_state_version == 6

    events = (
        await db_session.scalars(
            select(models.SchedulerStateVersionEvent)
            .where(models.SchedulerStateVersionEvent.organization_id == organization.id)
            .order_by(models.SchedulerStateVersionEvent.id)
        )
    ).all()
    future_versions = [
        event.version_after
        for event in events
        if event.change_scope == models.SchedulerStateChangeScope.FUTURE_IMPACTING
    ]
    assert future_versions == [1, 2, 3, 4, 5, 6]
    assert any(
        event.entity_type == "REPAIR_POLICY"
        and event.change_scope == models.SchedulerStateChangeScope.NO_OP
        for event in events
    )
    assert any(
        event.entity_type == "ROOM" and event.change_scope == models.SchedulerStateChangeScope.NO_OP
        for event in events
    )


async def test_module_selection_records_a_class_subject_assignment_update(db_session):
    organization = models.Organization(name="Selection Change School", plan_status="active")
    db_session.add(organization)
    await db_session.commit()

    await settings_service.upsert_settings(
        db_session,
        organization.id,
        schemas.OrganizationSettingsUpsert(
            school_start_date=date(2025, 9, 1),
            school_hard_end_date=date(2026, 7, 15),
            repair_stability_window_days=14,
        ),
    )
    service = SchedulerStateService(db_session)
    school_year = await service.get_active_school_year(organization.id)
    state = await service.get_state(organization.id, school_year.id)
    version_before = state.scheduler_state_version

    course = models.Course(name="Curso", abbreviation="CUR", organization_id=organization.id)
    subject = models.Subject(
        name="Disciplina",
        organization_id=organization.id,
        room_type_id=await get_school_room_type_id(db_session, organization.id, "Normal"),
    )
    db_session.add_all([course, subject])
    await db_session.flush()
    class_ = models.Class(
        name="10A",
        size=20,
        start_year=2025,
        end_year=2026,
        grade_level=10,
        course_id=course.id,
        organization_id=organization.id,
    )
    first_module = models.Module(
        organization_id=organization.id,
        subject_id=subject.id,
        name="M1",
        required_minutes=60,
        order=0,
    )
    second_module = models.Module(
        organization_id=organization.id,
        subject_id=subject.id,
        name="M2",
        required_minutes=60,
        order=1,
    )
    db_session.add_all([class_, first_module, second_module])
    await db_session.flush()
    await class_service.add_class_subject(db_session, class_.id, subject.id, organization.id)
    await db_session.commit()

    await class_service.update_class_subject(
        db_session,
        class_.id,
        subject.id,
        schemas.ClassSubjectUpdate(module_ids=[first_module.id]),
        organization.id,
    )
    await class_service.update_class_subject(
        db_session,
        class_.id,
        subject.id,
        schemas.ClassSubjectUpdate(module_ids=[second_module.id, first_module.id]),
        organization.id,
    )
    await db_session.commit()

    event = (
        await db_session.scalars(
            select(models.SchedulerStateVersionEvent)
            .where(models.SchedulerStateVersionEvent.organization_id == organization.id)
            .order_by(models.SchedulerStateVersionEvent.id.desc())
        )
    ).first()
    assert event is not None
    assert event.entity_type == "CLASS_SUBJECT_ASSIGNMENT"
    assert event.operation == models.SchedulerStateChangeOperation.UPDATE
    assert event.after_metadata_json["module_ids"] == [first_module.id, second_module.id]

    await db_session.refresh(state)
    assert state.scheduler_state_version == version_before + 3


async def test_specific_room_requires_the_same_school_room_type_id(db_session):
    organization = models.Organization(name="Specific Room School", plan_status="active")
    db_session.add(organization)
    await db_session.flush()
    await room_type_service.ensure_initial_room_types(db_session, organization.id)
    first_type = models.SchoolRoomType(
        organization_id=organization.id,
        name="Laboratório de Química",
        is_normal=False,
    )
    second_type = models.SchoolRoomType(
        organization_id=organization.id,
        name="Laboratório de Informática",
        is_normal=False,
    )
    course = models.Course(name="Curso", abbreviation="CUR", organization_id=organization.id)
    subject = models.Subject(
        name="Química",
        organization_id=organization.id,
        room_type_id=await get_school_room_type_id(db_session, organization.id, "Normal"),
    )
    db_session.add_all((first_type, second_type, course, subject))
    await db_session.flush()
    subject.room_type_id = second_type.id
    room = models.Room(
        name="Química 1",
        room_type_id=first_type.id,
        capacity=30,
        organization_id=organization.id,
    )
    school_class = models.Class(
        name="10A",
        size=20,
        start_year=2025,
        end_year=2026,
        grade_level=10,
        course_id=course.id,
        organization_id=organization.id,
    )
    db_session.add_all((room, school_class))
    await db_session.flush()
    db_session.add(
        models.ClassSubjectLink(
            organization_id=organization.id,
            class_id=school_class.id,
            subject_id=subject.id,
            grade_level=10,
        )
    )
    await db_session.flush()

    with pytest.raises(schedule_service.ConstraintSemanticValidationError):
        await schedule_service.create_constraint(
            db_session,
            schemas.SpecificRoomConstraintCreate(
                rule_type=schemas.SupportedConstraintType.specific_room,
                rule_payload=schemas.SpecificRoomPayload(
                    class_id=school_class.id,
                    subject_id=subject.id,
                    room_id=room.id,
                ),
            ),
            organization.id,
        )
