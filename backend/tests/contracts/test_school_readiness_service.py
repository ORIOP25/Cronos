from datetime import date, time

import pytest
from sqlalchemy import select

from app import models
from app.services.availability_matrix_service import (
    AvailabilityMatrixInspector,
    AvailabilityMatrixRepairService,
)
from app.services.school_readiness_service import SchoolReadinessService
from tests._support.db_fixtures import (
    create_org_and_user,
    create_teacher_profile,
    get_school_room_type_id,
    select_all_subject_modules,
)

pytestmark = pytest.mark.postgresql


@pytest.mark.asyncio
async def test_availability_matrix_repairs_set_and_preserves_impossible_cells(db_session):
    organization, _ = await create_org_and_user(
        db_session,
        clerk_user_id="availability-matrix-user",
        clerk_org_id="availability-matrix-org",
    )
    teacher = await create_teacher_profile(db_session, organization_id=organization.id)
    timeslots = [
        models.Timeslot(
            organization_id=organization.id,
            day_of_week=day,
            start_time=time(8),
            end_time=time(9),
        )
        for day in (0, 1)
    ]
    db_session.add_all(timeslots)
    await db_session.flush()
    db_session.add(
        models.Availability(
            organization_id=organization.id,
            teacher_id=teacher.id,
            timeslot_id=timeslots[0].id,
            score=models.PreferenceLevel.IMPOSSIBLE.value,
        )
    )
    await db_session.flush()

    repaired = await AvailabilityMatrixRepairService.repair(
        db_session,
        organization_id=organization.id,
    )
    assert repaired == 1

    inspection = await AvailabilityMatrixInspector.inspect(
        db_session,
        organization_id=organization.id,
        teacher_ids=[teacher.id],
        timeslot_ids=[slot.id for slot in timeslots],
    )
    assert inspection.get_score(teacher.id, timeslots[0].id) == models.PreferenceLevel.IMPOSSIBLE
    assert inspection.get_score(teacher.id, timeslots[1].id) == models.PreferenceLevel.NEUTRAL
    assert inspection.anomalies == []
    assert (
        await AvailabilityMatrixInspector.fully_impossible_teacher_ids(
            db_session,
            organization_id=organization.id,
            teacher_ids=[teacher.id],
            timeslot_ids=[slot.id for slot in timeslots],
        )
        == set()
    )


@pytest.mark.asyncio
async def test_readiness_evaluates_teachers_before_class_subject_links(db_session):
    organization, _ = await create_org_and_user(
        db_session,
        clerk_user_id="readiness-order-user",
        clerk_org_id="readiness-order-org",
    )
    course = models.Course(
        organization_id=organization.id,
        name="Curso de Teste",
        abbreviation="CT",
    )
    subject = models.Subject(
        organization_id=organization.id,
        name="Disciplina de Teste",
        room_type_id=await get_school_room_type_id(db_session, organization.id, "Normal"),
    )
    db_session.add_all([course, subject])
    await db_session.flush()

    school_class = models.Class(
        organization_id=organization.id,
        course_id=course.id,
        name="Turma de Teste",
        size=20,
        grade_level=10,
        start_year=2025,
        end_year=2028,
    )
    module = models.Module(
        organization_id=organization.id,
        subject_id=subject.id,
        name="Módulo de Teste",
        required_minutes=60,
        order=0,
    )
    db_session.add_all([school_class, module])
    await db_session.flush()

    service = SchoolReadinessService(db_session)
    report = await service.evaluate_bases(organization.id)

    assert report.depth == 2
    assert report.percentage == 33
    assert [step.code for step in report.steps] == [
        "ACTIVE_CLASSES",
        "MODULES",
        "TEACHERS",
        "TEACHER_ASSIGNMENT",
        "COMPATIBLE_ROOM",
        "TEACHER_AVAILABILITY",
    ]
    assert [step.status for step in report.steps[:3]] == ["COMPLETE", "COMPLETE", "PENDING"]
    assert report.issues[0].code == "TEACHERS_REQUIRED"
    assert report.issues[0].route == "/members"

    await create_teacher_profile(
        db_session,
        organization_id=organization.id,
        name="Professor sem competências",
    )
    teacher_report = await service.evaluate_bases(organization.id)

    assert teacher_report.depth == 3
    assert teacher_report.percentage == 50
    assert teacher_report.steps[2].status == "COMPLETE"
    assert teacher_report.issues[0].code == "TEACHER_ASSIGNMENT_REQUIRED"
    assert teacher_report.issues[0].route == "/courses"

    db_session.add(
        models.ClassSubjectLink(
            organization_id=organization.id,
            class_id=school_class.id,
            subject_id=subject.id,
            grade_level=10,
            teacher_id=None,
        )
    )
    await db_session.flush()

    linked_report = await service.evaluate_bases(organization.id)

    assert linked_report.depth == 3
    assert linked_report.percentage == 50
    assert (
        linked_report.issues[0].route == f"/courses/{course.id}/classes/{school_class.id}/subjects"
    )


@pytest.mark.asyncio
async def test_readiness_teacher_step_uses_active_membership_capability_only(db_session):
    organization, _ = await create_org_and_user(
        db_session,
        clerk_user_id="readiness-teacher-fact-user",
        clerk_org_id="readiness-teacher-fact-org",
    )
    course = models.Course(
        organization_id=organization.id,
        name="Curso de Professores",
        abbreviation="CP",
    )
    subject = models.Subject(
        organization_id=organization.id,
        name="Disciplina de Professores",
        room_type_id=await get_school_room_type_id(db_session, organization.id, "Normal"),
    )
    db_session.add_all([course, subject])
    await db_session.flush()
    db_session.add_all(
        [
            models.Class(
                organization_id=organization.id,
                course_id=course.id,
                name="Turma de Professores",
                size=20,
                grade_level=10,
                start_year=2025,
                end_year=2028,
            ),
            models.Module(
                organization_id=organization.id,
                subject_id=subject.id,
                name="Módulo de Professores",
                required_minutes=60,
                order=0,
            ),
        ]
    )
    await db_session.flush()

    teacher = await create_teacher_profile(db_session, organization_id=organization.id)
    service = SchoolReadinessService(db_session)
    membership = await db_session.get(
        models.OrganizationMembership,
        teacher.organization_membership_id,
    )

    assert (await service.evaluate_bases(organization.id)).depth == 3

    membership.lifecycle_status = models.MembershipLifecycleStatus.archived
    await db_session.flush()
    assert (await service.evaluate_bases(organization.id)).depth == 2

    membership.lifecycle_status = models.MembershipLifecycleStatus.active
    membership.can_admin = True
    membership.can_teach = False
    membership.teacher_access_mode = None
    await db_session.flush()
    assert (await service.evaluate_bases(organization.id)).depth == 2

    membership.can_admin = False
    membership.can_teach = True
    membership.teacher_access_mode = models.TeacherAccessMode.scheduler_only
    membership.access_status = models.MembershipAccessStatus.none
    await db_session.flush()
    assert (await service.evaluate_bases(organization.id)).depth == 3

    other_organization, _ = await create_org_and_user(
        db_session,
        clerk_user_id="readiness-teacher-fact-other-user",
        clerk_org_id="readiness-teacher-fact-other-org",
    )
    other_course = models.Course(
        organization_id=other_organization.id,
        name="Curso de Outra Organização",
        abbreviation="CO",
    )
    other_subject = models.Subject(
        organization_id=other_organization.id,
        name="Disciplina de Outra Organização",
        room_type_id=await get_school_room_type_id(db_session, other_organization.id, "Normal"),
    )
    db_session.add_all([other_course, other_subject])
    await db_session.flush()
    db_session.add_all(
        [
            models.Class(
                organization_id=other_organization.id,
                course_id=other_course.id,
                name="Turma de Outra Organização",
                size=20,
                grade_level=10,
                start_year=2025,
                end_year=2028,
            ),
            models.Module(
                organization_id=other_organization.id,
                subject_id=other_subject.id,
                name="Módulo de Outra Organização",
                required_minutes=60,
                order=0,
            ),
        ]
    )
    await db_session.flush()

    assert (await service.evaluate_bases(organization.id)).depth == 3
    assert (await service.evaluate_bases(other_organization.id)).depth == 2


@pytest.mark.asyncio
async def test_readiness_counts_scheduler_only_teacher_assignment(db_session):
    organization, _ = await create_org_and_user(
        db_session,
        clerk_user_id="readiness-scheduler-teacher-user",
        clerk_org_id="readiness-scheduler-teacher-org",
    )
    course = models.Course(
        organization_id=organization.id,
        name="Curso de Docência",
        abbreviation="CD",
    )
    subject = models.Subject(
        organization_id=organization.id,
        name="Disciplina de Docência",
        room_type_id=await get_school_room_type_id(db_session, organization.id, "Normal"),
    )
    db_session.add_all([course, subject])
    await db_session.flush()

    school_class = models.Class(
        organization_id=organization.id,
        course_id=course.id,
        name="Turma de Docência",
        size=20,
        grade_level=10,
        start_year=2025,
        end_year=2028,
    )
    module = models.Module(
        organization_id=organization.id,
        subject_id=subject.id,
        name="Módulo de Docência",
        required_minutes=60,
        order=0,
    )
    db_session.add_all([school_class, module])
    await db_session.flush()

    teacher = await create_teacher_profile(
        db_session,
        organization_id=organization.id,
        name="Professor sem acesso",
        subject_ids=[subject.id],
    )

    link = models.ClassSubjectLink(
        organization_id=organization.id,
        class_id=school_class.id,
        subject_id=subject.id,
        grade_level=school_class.grade_level,
        teacher_id=None,
    )
    db_session.add(link)
    await db_session.flush()
    await db_session.execute(
        models.class_subject_module.insert().values(
            organization_id=organization.id,
            class_subject_link_id=link.id,
            module_id=module.id,
        )
    )
    await db_session.flush()

    service = SchoolReadinessService(db_session)
    competency_only_report = await service.evaluate_bases(organization.id)

    assert competency_only_report.depth == 3
    expected_subject_route = f"/courses/{course.id}/classes/{school_class.id}/subjects"
    assert competency_only_report.issues[0].route == expected_subject_route
    assert competency_only_report.steps[3].route == expected_subject_route
    assert competency_only_report.issues[0].message == (
        "Atribua um professor ativo e competente à disciplina da turma."
    )

    link.teacher_id = teacher.id
    await db_session.flush()

    scheduler_only_report = await service.evaluate_bases(organization.id)

    assert scheduler_only_report.depth == 4
    assert scheduler_only_report.percentage == 67

    membership = await db_session.get(
        models.OrganizationMembership,
        teacher.organization_membership_id,
    )
    membership.access_status = models.MembershipAccessStatus.active
    await db_session.flush()

    platform_report = await service.evaluate_bases(organization.id)

    assert platform_report.depth == 4
    assert platform_report.percentage == 67


@pytest.mark.asyncio
async def test_readiness_mixed_and_fully_impossible_availability(db_session):
    organization, _ = await create_org_and_user(
        db_session,
        clerk_user_id="readiness-avail-user",
        clerk_org_id="readiness-avail-org",
    )
    course = models.Course(
        organization_id=organization.id,
        name="Curso Misto",
        abbreviation="CM",
    )
    subject = models.Subject(
        organization_id=organization.id,
        name="Disciplina Mista",
        room_type_id=await get_school_room_type_id(db_session, organization.id, "Normal"),
    )
    room = models.Room(
        organization_id=organization.id,
        name="Sala 1",
        capacity=30,
        room_type_id=await get_school_room_type_id(db_session, organization.id, "Normal"),
    )
    school_year = models.SchedulerSchoolYear(
        organization_id=organization.id,
        label="2025/2026",
        start_date=date(2025, 9, 1),
        hard_end_date=date(2026, 6, 30),
        is_active=True,
    )
    db_session.add_all([course, subject, room, school_year])
    await db_session.flush()

    school_year_state = models.SchedulerSchoolYearState(
        organization_id=organization.id,
        school_year_id=school_year.id,
        school_year_publication_state=models.SchoolYearPublicationState.UNPUBLISHED,
        scheduler_state_version=1,
    )
    db_session.add(school_year_state)
    await db_session.flush()

    school_class = models.Class(
        organization_id=organization.id,
        course_id=course.id,
        name="Turma Mista",
        size=20,
        grade_level=10,
        start_year=2025,
        end_year=2028,
    )
    module = models.Module(
        organization_id=organization.id,
        subject_id=subject.id,
        name="Módulo Misto",
        required_minutes=60,
        order=0,
    )
    db_session.add_all([school_class, module])
    await db_session.flush()

    teacher = await create_teacher_profile(
        db_session,
        organization_id=organization.id,
        name="Professor Misto",
        subject_ids=[subject.id],
    )
    link = models.ClassSubjectLink(
        organization_id=organization.id,
        class_id=school_class.id,
        subject_id=subject.id,
        grade_level=school_class.grade_level,
        teacher_id=teacher.id,
    )
    db_session.add(link)

    # 2 timeslots
    slot1 = models.Timeslot(
        organization_id=organization.id,
        day_of_week=0,
        start_time=time(8, 30),
        end_time=time(9, 20),
    )
    slot2 = models.Timeslot(
        organization_id=organization.id,
        day_of_week=0,
        start_time=time(9, 30),
        end_time=time(10, 20),
    )
    db_session.add_all([slot1, slot2])
    await db_session.flush()
    await db_session.execute(
        models.class_subject_module.insert().values(
            organization_id=organization.id,
            class_subject_link_id=link.id,
            module_id=module.id,
        )
    )
    await db_session.flush()

    # Availability from another tenant must never participate in this report.
    other_organization, _ = await create_org_and_user(
        db_session,
        clerk_user_id="readiness-avail-other-user",
        clerk_org_id="readiness-avail-other-org",
    )
    other_teacher = await create_teacher_profile(
        db_session,
        organization_id=other_organization.id,
        name="Professor de Outra Escola",
    )
    other_slot = models.Timeslot(
        organization_id=other_organization.id,
        day_of_week=0,
        start_time=time(8, 30),
        end_time=time(9, 20),
    )
    db_session.add(other_slot)
    await db_session.flush()
    db_session.add(
        models.Availability(
            organization_id=other_organization.id,
            teacher_id=other_teacher.id,
            timeslot_id=other_slot.id,
            score=models.PreferenceLevel.IMPOSSIBLE.value,
        )
    )
    await db_session.flush()

    service = SchoolReadinessService(db_session)

    # Case 1: Neutral availability (no explicit availability records) -> 100%
    neutral_report = await service.evaluate_bases(organization.id)
    assert neutral_report.depth == 6
    assert neutral_report.complete is True
    assert neutral_report.percentage == 100

    preferred = models.Availability(
        organization_id=organization.id,
        teacher_id=teacher.id,
        timeslot_id=slot2.id,
        score=models.PreferenceLevel.PREFERRED.value,
    )
    db_session.add(preferred)
    await db_session.flush()
    preferred_report = await service.evaluate_bases(organization.id)
    assert preferred_report.depth == 6
    assert preferred_report.complete is True
    assert preferred_report.percentage == 100

    # Case 3: Mixed availability (1 impossible slot, 1 preferred slot) -> MUST reach 100%
    avail_impossible = models.Availability(
        organization_id=organization.id,
        teacher_id=teacher.id,
        timeslot_id=slot1.id,
        score=models.PreferenceLevel.IMPOSSIBLE.value,
    )
    db_session.add(avail_impossible)
    await db_session.flush()

    mixed_report = await service.evaluate_bases(organization.id)
    assert mixed_report.depth == 6
    assert mixed_report.complete is True
    assert mixed_report.percentage == 100

    # Case 4: Fully impossible availability (both slots impossible) -> blocks level 6 (depth 5)
    preferred.score = models.PreferenceLevel.IMPOSSIBLE.value
    await db_session.flush()

    blocked_report = await service.evaluate_bases(organization.id)
    assert blocked_report.depth == 5
    assert blocked_report.complete is False
    assert blocked_report.percentage == 83
    assert blocked_report.issues[0].code == "TEACHER_AVAILABILITY_REQUIRED"
    assert blocked_report.issues[0].message == (
        "Marque pelo menos um bloco como Neutro, Evitar ou Preferencial "
        "na disponibilidade dos professores atribuídos."
    )


@pytest.mark.asyncio
async def test_readiness_ignores_archived_class_and_subject(db_session):
    organization, _ = await create_org_and_user(
        db_session,
        clerk_user_id="readiness-archived-user",
        clerk_org_id="readiness-archived-org",
    )
    course = models.Course(
        organization_id=organization.id,
        name="Curso Arquivado",
        abbreviation="CA",
    )
    subject = models.Subject(
        organization_id=organization.id,
        name="Disciplina Arquivada",
        room_type_id=await get_school_room_type_id(db_session, organization.id, "Normal"),
    )
    db_session.add_all([course, subject])
    await db_session.flush()

    school_class = models.Class(
        organization_id=organization.id,
        course_id=course.id,
        name="Turma Arquivada",
        size=20,
        grade_level=10,
        start_year=2025,
        end_year=2028,
    )
    module = models.Module(
        organization_id=organization.id,
        subject_id=subject.id,
        name="Módulo Arquivado",
        required_minutes=60,
        order=0,
    )
    db_session.add_all([school_class, module])
    await db_session.flush()

    subject.is_archived = True
    school_class.is_archived = True
    await db_session.flush()

    report = await SchoolReadinessService(db_session).evaluate_bases(organization.id)

    assert report.depth == 0
    assert report.percentage == 0
    assert report.issues[0].code == "ACTIVE_CLASSES_REQUIRED"


@pytest.mark.asyncio
async def test_readiness_requires_an_active_compatible_room(db_session):
    organization, _ = await create_org_and_user(
        db_session,
        clerk_user_id="readiness-room-archive-user",
        clerk_org_id="readiness-room-archive-org",
    )
    laboratory_type = await db_session.scalar(
        select(models.SchoolRoomType).where(
            models.SchoolRoomType.organization_id == organization.id,
            models.SchoolRoomType.name == "Laboratório",
        )
    )
    other_type = models.SchoolRoomType(
        organization_id=organization.id,
        name="Oficina",
        is_normal=False,
    )
    db_session.add(other_type)
    await db_session.flush()
    course = models.Course(organization_id=organization.id, name="Curso Sala", abbreviation="CS")
    subject = models.Subject(
        organization_id=organization.id,
        name="Disciplina Sala",
        room_type_id=laboratory_type.id,
    )
    room = models.Room(
        organization_id=organization.id,
        name="Sala Compatível",
        capacity=30,
        room_type_id=other_type.id,
    )
    db_session.add_all([course, subject, room])
    await db_session.flush()

    school_class = models.Class(
        organization_id=organization.id,
        course_id=course.id,
        name="Turma Sala",
        size=20,
        grade_level=10,
        start_year=2025,
        end_year=2028,
    )
    module = models.Module(
        organization_id=organization.id,
        subject_id=subject.id,
        name="Módulo Sala",
        required_minutes=60,
        order=0,
    )
    db_session.add_all([school_class, module])
    await db_session.flush()

    teacher = await create_teacher_profile(
        db_session,
        organization_id=organization.id,
        name="Professor Sala",
        subject_ids=[subject.id],
    )
    link = models.ClassSubjectLink(
        organization_id=organization.id,
        class_id=school_class.id,
        subject_id=subject.id,
        grade_level=school_class.grade_level,
        teacher_id=teacher.id,
    )
    db_session.add(link)
    db_session.add(
        models.Timeslot(
            organization_id=organization.id,
            day_of_week=0,
            start_time=time(8, 30),
            end_time=time(9, 20),
        )
    )
    await db_session.flush()
    await db_session.execute(
        models.class_subject_module.insert().values(
            organization_id=organization.id,
            class_subject_link_id=link.id,
            module_id=module.id,
        )
    )
    await db_session.flush()

    service = SchoolReadinessService(db_session)

    room.is_archived = True
    await db_session.flush()
    archived_report = await service.evaluate_bases(organization.id)

    assert archived_report.depth == 4
    assert archived_report.issues[0].code == "COMPATIBLE_ROOM_REQUIRED"

    room.is_archived = False
    await db_session.flush()
    mismatched_report = await service.evaluate_bases(organization.id)

    assert mismatched_report.depth == 4
    assert mismatched_report.issues[0].code == "COMPATIBLE_ROOM_REQUIRED"

    room.room_type_id = laboratory_type.id
    await db_session.flush()
    active_report = await service.evaluate_bases(organization.id)
    assert active_report.depth == 6
    assert "COMPATIBLE_ROOM_REQUIRED" not in {issue.code for issue in active_report.issues}


@pytest.mark.asyncio
async def test_readiness_requires_a_selected_module(db_session):
    organization, _ = await create_org_and_user(
        db_session,
        clerk_user_id="readiness-selection-user",
        clerk_org_id="readiness-selection-org",
    )
    course = models.Course(
        organization_id=organization.id,
        name="Curso Seleção",
        abbreviation="CS",
    )
    subject = models.Subject(
        organization_id=organization.id,
        name="Disciplina Seleção",
        room_type_id=await get_school_room_type_id(db_session, organization.id, "Normal"),
    )
    db_session.add_all([course, subject])
    await db_session.flush()

    school_class = models.Class(
        organization_id=organization.id,
        course_id=course.id,
        name="Turma Seleção",
        size=20,
        grade_level=10,
        start_year=2025,
        end_year=2028,
    )
    module = models.Module(
        organization_id=organization.id,
        subject_id=subject.id,
        name="Módulo Seleção",
        required_minutes=60,
        order=0,
    )
    db_session.add_all([school_class, module])
    await db_session.flush()

    teacher = await create_teacher_profile(
        db_session,
        organization_id=organization.id,
        name="Professor Seleção",
        subject_ids=[subject.id],
    )
    link = models.ClassSubjectLink(
        organization_id=organization.id,
        class_id=school_class.id,
        subject_id=subject.id,
        grade_level=school_class.grade_level,
        teacher_id=teacher.id,
    )
    db_session.add(link)
    await db_session.flush()

    service = SchoolReadinessService(db_session)
    without_selection = await service.evaluate_bases(organization.id)

    # A link with no selected module does not satisfy the assignment step.
    assert without_selection.depth == 3
    assert without_selection.issues[0].code == "TEACHER_ASSIGNMENT_REQUIRED"

    await db_session.execute(
        models.class_subject_module.insert().values(
            organization_id=organization.id,
            class_subject_link_id=link.id,
            module_id=module.id,
        )
    )
    await db_session.flush()
    with_selection = await service.evaluate_bases(organization.id)

    assert with_selection.depth == 4
    assert with_selection.issues[0].code == "COMPATIBLE_ROOM_REQUIRED"


@pytest.mark.asyncio
async def test_readiness_invalid_joint_member_blocks_the_group(db_session):
    organization, _ = await create_org_and_user(
        db_session,
        clerk_user_id="readiness-joint-user",
        clerk_org_id="readiness-joint-org",
    )
    course = models.Course(organization_id=organization.id, name="Curso J", abbreviation="CJ")
    subject = models.Subject(
        organization_id=organization.id,
        name="Português",
        room_type_id=await get_school_room_type_id(db_session, organization.id, "Normal"),
    )
    room = models.Room(
        organization_id=organization.id,
        name="Sala J",
        capacity=40,
        room_type_id=await get_school_room_type_id(db_session, organization.id, "Normal"),
    )
    db_session.add_all([course, subject, room])
    await db_session.flush()
    school_year = models.SchedulerSchoolYear(
        organization_id=organization.id,
        label="2025/2026",
        start_date=date(2025, 9, 1),
        hard_end_date=date(2026, 6, 30),
        is_active=True,
    )
    db_session.add(school_year)
    await db_session.flush()
    db_session.add(
        models.SchedulerSchoolYearState(
            organization_id=organization.id,
            school_year_id=school_year.id,
            school_year_publication_state=models.SchoolYearPublicationState.UNPUBLISHED,
            scheduler_state_version=1,
        )
    )
    module = models.Module(
        organization_id=organization.id,
        subject_id=subject.id,
        name="M1",
        required_minutes=60,
        order=0,
    )
    db_session.add(module)
    db_session.add(
        models.Timeslot(
            organization_id=organization.id,
            day_of_week=0,
            start_time=time(8, 30),
            end_time=time(9, 20),
        )
    )
    await db_session.flush()
    teacher = await create_teacher_profile(
        db_session, organization_id=organization.id, subject_ids=[subject.id]
    )
    links = []
    for index in range(2):
        school_class = models.Class(
            organization_id=organization.id,
            course_id=course.id,
            name=f"Turma {index}",
            size=18,
            grade_level=10,
            start_year=2025,
            end_year=2028,
        )
        db_session.add(school_class)
        await db_session.flush()
        link = models.ClassSubjectLink(
            organization_id=organization.id,
            class_id=school_class.id,
            subject_id=subject.id,
            grade_level=10,
            teacher_id=teacher.id,
        )
        db_session.add(link)
        await db_session.flush()
        await select_all_subject_modules(
            db_session,
            organization_id=organization.id,
            class_subject_link_id=link.id,
            subject_id=subject.id,
        )
        links.append(link)
    group = models.JointLessonGroup(organization_id=organization.id, subject_id=subject.id)
    db_session.add(group)
    await db_session.flush()
    await db_session.execute(
        models.joint_lesson_group_member.insert().values(
            [
                {
                    "organization_id": organization.id,
                    "group_id": group.id,
                    "class_subject_link_id": link.id,
                }
                for link in links
            ]
        )
    )
    await db_session.execute(
        models.joint_lesson_group_module.insert().values(
            organization_id=organization.id, group_id=group.id, module_id=module.id
        )
    )
    await db_session.flush()

    service = SchoolReadinessService(db_session)
    ready = await service.evaluate_bases(organization.id)
    assert ready.depth == 6
    assert ready.complete is True

    links[1].teacher_id = None
    await db_session.flush()

    invalid = await service.evaluate_bases(organization.id)
    assert invalid.depth == 6
    assert invalid.complete is False
    assert "JOINT_GROUP_INCOMPLETE" in {issue.code for issue in invalid.issues}
