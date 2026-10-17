"""Shared direct seeds for the joint lesson operation tests.

The helpers create member classes, curricular assignments, joint groups and
sibling lesson rows without the generation engine, so the operation layer can
be tested in isolation (WBS 5).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from app import models
from app.scheduler.infrastructure.models import (
    CurricularAssignment,
    CurricularRequirement,
    SchedulerLessonSliceV1,
)
from tests._support.db_fixtures import create_teacher_profile
from tests._support.scheduler_v1 import V1Seed, add_lesson, seed_v1_assignment

MOMENT = datetime(2026, 9, 22, 10, 0, tzinfo=UTC)
SCHOOL_DATE = date(2026, 9, 22)


async def link_id(db_session, seed: V1Seed, class_id: int) -> int:
    return await db_session.scalar(
        select(models.ClassSubjectLink.id).where(
            models.ClassSubjectLink.organization_id == seed.organization.id,
            models.ClassSubjectLink.class_id == class_id,
            models.ClassSubjectLink.subject_id == seed.subject.id,
        )
    )


async def seed_joint_pair(
    db_session,
    *,
    clerk_user_id: str = "joint_support_admin",
    clerk_org_id: str = "joint_support_org",
    module_minutes: int = 100,
):
    """A subject with two member classes A and B in the same joint group."""
    seed = await seed_v1_assignment(
        db_session,
        clerk_user_id=clerk_user_id,
        clerk_org_id=clerk_org_id,
        module_minutes=module_minutes,
    )
    class_b = models.Class(
        name="B",
        size=18,
        start_year=2026,
        end_year=2029,
        grade_level=10,
        course_id=seed.course.id,
        organization_id=seed.organization.id,
    )
    db_session.add(class_b)
    await db_session.flush()
    assignment_b = CurricularAssignment(
        organization_id=seed.organization.id,
        school_year_id=seed.year.id,
        class_id=class_b.id,
        subject_id=seed.subject.id,
        teacher_id=seed.assignment.teacher_id,
    )
    db_session.add(assignment_b)
    await db_session.flush()
    db_session.add(
        CurricularRequirement(
            organization_id=seed.organization.id,
            assignment_id=assignment_b.id,
            module_id=seed.module.id,
            sequence=1,
            required_minutes=module_minutes,
        )
    )
    link_b = models.ClassSubjectLink(
        organization_id=seed.organization.id,
        class_id=class_b.id,
        subject_id=seed.subject.id,
        grade_level=class_b.grade_level,
        teacher_id=seed.assignment.teacher_id,
    )
    db_session.add(link_b)
    await db_session.flush()
    await db_session.execute(
        models.class_subject_module.insert().values(
            organization_id=seed.organization.id,
            class_subject_link_id=link_b.id,
            module_id=seed.module.id,
        )
    )
    link_a_id = await link_id(db_session, seed, seed.class_.id)
    group = models.JointLessonGroup(
        organization_id=seed.organization.id, subject_id=seed.subject.id
    )
    db_session.add(group)
    await db_session.flush()
    await db_session.execute(
        models.joint_lesson_group_member.insert().values(
            [
                {
                    "organization_id": seed.organization.id,
                    "group_id": group.id,
                    "class_subject_link_id": link_a_id,
                },
                {
                    "organization_id": seed.organization.id,
                    "group_id": group.id,
                    "class_subject_link_id": link_b.id,
                },
            ]
        )
    )
    await db_session.execute(
        models.joint_lesson_group_module.insert().values(
            organization_id=seed.organization.id,
            group_id=group.id,
            module_id=seed.module.id,
        )
    )
    await db_session.commit()
    return seed, class_b, assignment_b, group


async def add_joint_lesson(
    db_session,
    seed: V1Seed,
    assignment_b: CurricularAssignment,
    version,
    *,
    stable_key: str,
    school_date: date = SCHOOL_DATE,
    start: datetime = MOMENT,
    minutes: int = 50,
):
    """Two sibling lesson rows with identical identity and one slice each."""
    end = start + timedelta(minutes=minutes)
    lesson_a = await add_lesson(
        db_session,
        seed,
        version,
        stable_key=stable_key,
        school_date=school_date,
        start=start,
        end=end,
        credit_minutes=minutes,
    )
    lesson_b = await add_lesson(
        db_session,
        seed,
        version,
        stable_key=stable_key,
        school_date=school_date,
        start=start,
        end=end,
        credit_minutes=minutes,
        assignment_id=assignment_b.id,
    )
    for lesson in (lesson_a, lesson_b):
        db_session.add(
            SchedulerLessonSliceV1(
                organization_id=seed.organization.id,
                school_year_id=seed.year.id,
                lesson_id=lesson.id,
                module_id=seed.module.id,
                offset_minutes=0,
                minutes=minutes,
            )
        )
    await db_session.flush()
    return lesson_a, lesson_b


async def add_joint_subject(
    db_session,
    seed: V1Seed,
    class_b: models.Class,
    *,
    name: str,
    joint: bool = True,
    module_minutes: int = 100,
):
    """A second subject with an assignment per class and an optional joint group."""
    subject = models.Subject(
        name=name,
        organization_id=seed.organization.id,
        room_type_id=seed.room.room_type_id,
    )
    teacher = await create_teacher_profile(
        db_session, organization_id=seed.organization.id, name=f"Prof. {name}"
    )
    db_session.add(subject)
    await db_session.flush()
    module = models.Module(
        organization_id=seed.organization.id,
        subject_id=subject.id,
        name=f"Modulo {name}",
        required_minutes=module_minutes,
        order=1,
    )
    db_session.add(module)
    await db_session.flush()
    assignments: dict[int, CurricularAssignment] = {}
    links: dict[int, int] = {}
    for class_id in (seed.class_.id, class_b.id):
        link = models.ClassSubjectLink(
            organization_id=seed.organization.id,
            class_id=class_id,
            subject_id=subject.id,
            grade_level=10,
            teacher_id=teacher.id,
        )
        db_session.add(link)
        await db_session.flush()
        await db_session.execute(
            models.class_subject_module.insert().values(
                organization_id=seed.organization.id,
                class_subject_link_id=link.id,
                module_id=module.id,
            )
        )
        assignment = CurricularAssignment(
            organization_id=seed.organization.id,
            school_year_id=seed.year.id,
            class_id=class_id,
            subject_id=subject.id,
            teacher_id=teacher.id,
        )
        db_session.add(assignment)
        await db_session.flush()
        db_session.add(
            CurricularRequirement(
                organization_id=seed.organization.id,
                assignment_id=assignment.id,
                module_id=module.id,
                sequence=1,
                required_minutes=module_minutes,
            )
        )
        assignments[class_id] = assignment
        links[class_id] = link.id
    if joint:
        group = models.JointLessonGroup(organization_id=seed.organization.id, subject_id=subject.id)
        db_session.add(group)
        await db_session.flush()
        await db_session.execute(
            models.joint_lesson_group_member.insert().values(
                [
                    {
                        "organization_id": seed.organization.id,
                        "group_id": group.id,
                        "class_subject_link_id": links[seed.class_.id],
                    },
                    {
                        "organization_id": seed.organization.id,
                        "group_id": group.id,
                        "class_subject_link_id": links[class_b.id],
                    },
                ]
            )
        )
        await db_session.execute(
            models.joint_lesson_group_module.insert().values(
                organization_id=seed.organization.id,
                group_id=group.id,
                module_id=module.id,
            )
        )
    await db_session.commit()
    return subject, teacher, module, assignments
