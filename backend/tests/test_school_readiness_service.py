import pytest

from app import models
from app.services.school_readiness_service import SchoolReadinessService
from tests.conftest import create_org_and_user, create_teacher_profile

pytestmark = pytest.mark.postgresql


@pytest.mark.asyncio
async def test_readiness_evaluates_modules_before_class_subject_links(db_session):
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
    assert report.percentage == 28
    assert [step.code for step in report.steps] == [
        "ACTIVE_CLASSES",
        "MODULES",
        "CLASS_SUBJECTS",
        "TEACHER_ASSIGNMENT",
        "COMPATIBLE_ROOM",
        "TIMESLOTS",
        "TEACHER_AVAILABILITY",
    ]
    assert [step.status for step in report.steps[:3]] == ["COMPLETE", "COMPLETE", "PENDING"]

    db_session.add(
        models.ClassSubjectLink(
            organization_id=organization.id,
            class_id=school_class.id,
            subject_id=subject.id,
            grade_level=10,
        )
    )
    await db_session.flush()

    linked_report = await service.evaluate_bases(organization.id)

    assert linked_report.depth == 3
    assert linked_report.percentage == 42


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
    assert scheduler_only_report.percentage == 57

    membership = await db_session.get(
        models.OrganizationMembership,
        teacher.organization_membership_id,
    )
    membership.access_status = models.MembershipAccessStatus.active
    await db_session.flush()

    platform_report = await service.evaluate_bases(organization.id)

    assert platform_report.depth == 4
    assert platform_report.percentage == 57
