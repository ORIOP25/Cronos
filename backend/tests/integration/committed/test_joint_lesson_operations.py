"""Joint lesson operations (WBS 5.1): one summary, presences and per-class credit.

The joint lessons are seeded directly (one ``scheduler_lesson_v1`` row per
member class sharing ``(version_id, stable_key)``) so these tests exercise the
operation layer without depending on the generation engine.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app import models
from app.scheduler.infrastructure.models import (
    CurricularAssignment,
    CurricularRequirement,
    SchedulerLessonLogV1,
    SchedulerLessonSliceV1,
)
from app.scheduler.infrastructure.operations import (
    OperationsError,
    record_lesson_log,
    week_schedule,
)
from app.scheduler.infrastructure.progress import load_executed_minutes
from tests._support.scheduler_v1 import V1Seed, add_lesson, add_version, seed_v1_assignment

pytestmark = pytest.mark.postgresql

MOMENT = datetime(2026, 9, 22, 10, 0, tzinfo=UTC)
SCHOOL_DATE = date(2026, 9, 22)


async def _link_id(db_session, seed: V1Seed, class_id: int) -> int:
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
    clerk_user_id: str = "joint_op_admin",
    clerk_org_id: str = "joint_op_org",
    module_minutes: int = 100,
):
    """One subject with two member classes in the same joint lesson group."""
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
    link_a_id = await _link_id(db_session, seed, seed.class_.id)
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
    """Two sibling rows with identical identity and one slice each."""
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


async def _log(db_session, lesson_id: int) -> SchedulerLessonLogV1 | None:
    return await db_session.scalar(
        select(SchedulerLessonLogV1).where(SchedulerLessonLogV1.lesson_id == lesson_id)
    )


async def test_completed_joint_lesson_credits_present_and_occurs_absent(db_session):
    seed, class_b, assignment_b, _group = await seed_joint_pair(db_session)
    version = await add_version(db_session, seed, status="ACTIVE")
    lesson_a, lesson_b = await add_joint_lesson(
        db_session, seed, assignment_b, version, stable_key="j1"
    )

    result = await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=lesson_a.id,
        status="COMPLETED",
        summary="Aula conjunta dada.",
        notes=None,
        now_utc=lesson_a.ends_at,
        absent_class_ids=[class_b.id],
    )
    await db_session.commit()

    classes = {row["class_id"]: row for row in result["classes"]}
    assert classes[seed.class_.id]["status"] == "COMPLETED"
    assert classes[seed.class_.id]["credited_minutes"] == lesson_a.credit_minutes
    assert classes[class_b.id]["status"] == "OCCURRENCE"
    assert classes[class_b.id]["credited_minutes"] == 0

    executed_a = await load_executed_minutes(db_session, seed.organization.id, [seed.assignment.id])
    assert sum(executed_a[seed.assignment.id].values()) == lesson_a.credit_minutes
    executed_b = await load_executed_minutes(db_session, seed.organization.id, [assignment_b.id])
    assert sum(executed_b.get(assignment_b.id, {}).values()) == 0

    log_a = await _log(db_session, lesson_a.id)
    log_b = await _log(db_session, lesson_b.id)
    assert log_a.status == "COMPLETED" and log_a.summary == "Aula conjunta dada."
    assert log_b.status == "OCCURRENCE"
    assert log_b.summary is None
    assert log_b.notes == "Turma ausente"


async def test_completed_joint_lesson_without_absences_credits_every_class(db_session):
    seed, class_b, assignment_b, _group = await seed_joint_pair(
        db_session, clerk_user_id="joint_all", clerk_org_id="joint_all_org"
    )
    version = await add_version(db_session, seed, status="ACTIVE")
    lesson_a, lesson_b = await add_joint_lesson(
        db_session, seed, assignment_b, version, stable_key="j2"
    )

    result = await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=lesson_b.id,
        status="COMPLETED",
        summary="Todos presentes.",
        notes=None,
        now_utc=lesson_a.ends_at,
    )
    await db_session.commit()

    assert {row["status"] for row in result["classes"]} == {"COMPLETED"}
    assert result["credited_minutes"] == lesson_a.credit_minutes, (
        "O total da resposta conta a aula física uma só vez."
    )
    assert {row["credited_minutes"] for row in result["classes"]} == {lesson_a.credit_minutes}
    log_a = await _log(db_session, lesson_a.id)
    log_b = await _log(db_session, lesson_b.id)
    assert log_a.summary == log_b.summary == "Todos presentes."
    executed_b = await load_executed_minutes(db_session, seed.organization.id, [assignment_b.id])
    assert sum(executed_b[assignment_b.id].values()) == lesson_b.credit_minutes


async def test_all_absent_and_unknown_are_rejected_without_effects(db_session):
    seed, class_b, assignment_b, _group = await seed_joint_pair(
        db_session, clerk_user_id="joint_invalid", clerk_org_id="joint_invalid_org"
    )
    version = await add_version(db_session, seed, status="ACTIVE")
    lesson_a, _lesson_b = await add_joint_lesson(
        db_session, seed, assignment_b, version, stable_key="j3"
    )

    with pytest.raises(OperationsError) as all_absent:
        await record_lesson_log(
            db_session,
            seed.organization.id,
            membership_id=seed.membership.id,
            lesson_id=lesson_a.id,
            status="COMPLETED",
            summary="Ninguém veio.",
            notes=None,
            now_utc=lesson_a.ends_at,
            absent_class_ids=[seed.class_.id, class_b.id],
        )
    assert all_absent.value.code == "absent_classes_all"

    with pytest.raises(OperationsError) as unknown:
        await record_lesson_log(
            db_session,
            seed.organization.id,
            membership_id=seed.membership.id,
            lesson_id=lesson_a.id,
            status="COMPLETED",
            summary="Turma estranha.",
            notes=None,
            now_utc=lesson_a.ends_at,
            absent_class_ids=[999_999],
        )
    assert unknown.value.code == "absent_class_unknown"

    assert await _log(db_session, lesson_a.id) is None
    executed = await load_executed_minutes(db_session, seed.organization.id, [seed.assignment.id])
    assert sum(executed.get(seed.assignment.id, {}).values()) == 0


async def test_single_class_rejects_absent_classes(db_session):
    seed = await seed_v1_assignment(
        db_session, clerk_user_id="joint_single", clerk_org_id="joint_single_org"
    )
    version = await add_version(db_session, seed, status="ACTIVE")
    lesson = await add_lesson(
        db_session,
        seed,
        version,
        stable_key="s1",
        school_date=SCHOOL_DATE,
        start=MOMENT,
        end=MOMENT + timedelta(minutes=50),
    )
    db_session.add(
        SchedulerLessonSliceV1(
            organization_id=seed.organization.id,
            school_year_id=seed.year.id,
            lesson_id=lesson.id,
            module_id=seed.module.id,
            offset_minutes=0,
            minutes=50,
        )
    )
    await db_session.flush()

    with pytest.raises(OperationsError) as excinfo:
        await record_lesson_log(
            db_session,
            seed.organization.id,
            membership_id=seed.membership.id,
            lesson_id=lesson.id,
            status="COMPLETED",
            summary="Aula.",
            notes=None,
            now_utc=lesson.ends_at,
            absent_class_ids=[seed.class_.id],
        )
    assert excinfo.value.code == "absent_classes_not_joint"


async def test_a_correction_reverses_only_the_changed_class(db_session):
    seed, class_b, assignment_b, _group = await seed_joint_pair(
        db_session, clerk_user_id="joint_correct", clerk_org_id="joint_correct_org"
    )
    version = await add_version(db_session, seed, status="ACTIVE")
    lesson_a, lesson_b = await add_joint_lesson(
        db_session, seed, assignment_b, version, stable_key="j4"
    )
    await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=lesson_a.id,
        status="COMPLETED",
        summary="Aula conjunta.",
        notes=None,
        now_utc=lesson_a.ends_at,
    )
    await db_session.commit()

    # Correct only class B to an occurrence: class A keeps its credit.
    await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=lesson_b.id,
        status="COMPLETED",
        summary="Aula conjunta.",
        notes=None,
        now_utc=lesson_a.ends_at,
        absent_class_ids=[class_b.id],
    )
    await db_session.commit()

    executed_a = await load_executed_minutes(db_session, seed.organization.id, [seed.assignment.id])
    assert sum(executed_a[seed.assignment.id].values()) == lesson_a.credit_minutes
    executed_b = await load_executed_minutes(db_session, seed.organization.id, [assignment_b.id])
    assert sum(executed_b.get(assignment_b.id, {}).values()) == 0
    assert (await _log(db_session, lesson_a.id)).status == "COMPLETED"
    assert (await _log(db_session, lesson_b.id)).status == "OCCURRENCE"


async def test_a_closed_week_blocks_every_sibling(db_session):
    seed, class_b, assignment_b, _group = await seed_joint_pair(
        db_session, clerk_user_id="joint_locked", clerk_org_id="joint_locked_org"
    )
    version = await add_version(db_session, seed, status="ACTIVE")
    lesson_a, lesson_b = await add_joint_lesson(
        db_session, seed, assignment_b, version, stable_key="j5"
    )
    week_start = SCHOOL_DATE - timedelta(days=SCHOOL_DATE.weekday())
    db_session.add(
        models.TeacherWeeklyTimesheet(
            organization_id=seed.organization.id,
            teacher_id=seed.assignment.teacher_id,
            week_start_date=week_start,
            status=models.TimesheetStatus.SUBMITTED,
        )
    )
    await db_session.commit()

    with pytest.raises(OperationsError) as locked:
        await record_lesson_log(
            db_session,
            seed.organization.id,
            membership_id=seed.membership.id,
            lesson_id=lesson_a.id,
            status="COMPLETED",
            summary="Fora de prazo.",
            notes=None,
            now_utc=lesson_a.ends_at,
            absent_class_ids=[class_b.id],
        )
    assert locked.value.code == "week_locked"
    assert await _log(db_session, lesson_a.id) is None
    assert await _log(db_session, lesson_b.id) is None


async def test_week_view_exposes_joint_classes_for_a_member_class(db_session):
    seed, class_b, assignment_b, _group = await seed_joint_pair(
        db_session, clerk_user_id="joint_view", clerk_org_id="joint_view_org"
    )
    version = await add_version(db_session, seed, status="ACTIVE")
    lesson_a, _lesson_b = await add_joint_lesson(
        db_session, seed, assignment_b, version, stable_key="j6"
    )

    slots = await week_schedule(
        db_session,
        seed.organization.id,
        week_start=SCHOOL_DATE - timedelta(days=SCHOOL_DATE.weekday()),
        class_id=seed.class_.id,
        teacher_id=None,
        today=SCHOOL_DATE,
    )
    slot = next(row for row in slots if row["scheduler_lesson_id"] == lesson_a.id)
    assert {row["id"] for row in slot["joint_classes"]} == {class_b.id}
    assert slot["joint_classes"][0]["name"] == class_b.name
    assert slot["class_info"] == {"id": seed.class_.id, "name": seed.class_.name}


async def test_teacher_week_view_collapses_the_joint_lesson(db_session):
    seed, class_b, assignment_b, _group = await seed_joint_pair(
        db_session, clerk_user_id="joint_tview", clerk_org_id="joint_tview_org"
    )
    version = await add_version(db_session, seed, status="ACTIVE")
    lesson_a, lesson_b = await add_joint_lesson(
        db_session, seed, assignment_b, version, stable_key="j7"
    )

    slots = await week_schedule(
        db_session,
        seed.organization.id,
        week_start=SCHOOL_DATE - timedelta(days=SCHOOL_DATE.weekday()),
        class_id=None,
        teacher_id=seed.assignment.teacher_id,
        today=SCHOOL_DATE,
    )
    joint = [row for row in slots if row["scheduler_lesson_id"] in {lesson_a.id, lesson_b.id}]
    assert len(joint) == 1, "A vista do professor mostra um só bloco para a aula conjunta."
    assert {info["id"] for info in joint[0]["class_infos"]} == {seed.class_.id, class_b.id}
    assert {info["lesson_db_id"] for info in joint[0]["class_infos"]} == {lesson_a.id, lesson_b.id}
