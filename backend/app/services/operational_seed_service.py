"""Operational seed profile for Alpha V1 Step 6.

This seed is deterministic and focused on daily operations:
- two isolated organizations;
- one occurrence with multiple eligible substitutes;
- one no-eligible case resolved as GAP fallback.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models

ACADEMIC_YEAR = "2025/2026"
REFERENCE_DATE = date(2026, 4, 20)
HISTORICAL_DATE = REFERENCE_DATE - timedelta(days=3)

ORG_A_NAME = "Escola Piloto Operacional A"
ORG_B_NAME = "Escola Piloto Operacional B"

SCENARIO_MULTI_ELIGIBLE = "multi_eligible_substitution"
SCENARIO_NO_ELIGIBLE = "no_eligible_fallback_gap"


def _create_organization(
    db: Session,
    *,
    org_name: str,
    admin_email: str,
) -> tuple[models.Organization, models.User]:
    org = models.Organization(name=org_name, plan_status="active")
    db.add(org)
    db.flush()

    admin = models.User(
        name=f"Admin {org_name}",
        email=admin_email,
        clerk_user_id=f"seed_{admin_email}",
        role=models.UserRole.admin,
        organization_id=org.id,
        is_active=True,
    )
    db.add(admin)

    settings = models.OrganizationSettings(
        organization_id=org.id,
        school_start_date=date(2025, 9, 15),
        school_target_end_date=date(2026, 6, 15),
        school_hard_end_date=date(2026, 7, 31),
        repair_stability_window_days=14,
    )
    db.add(settings)

    grid_settings = models.OrganizationGridSettings(
        organization_id=org.id,
        lunch_window_start=time(12, 0),
        lunch_window_end=time(14, 0),
        lunch_min_duration_minutes=60,
    )
    db.add(grid_settings)
    db.flush()

    return org, admin


def _create_course_and_class(db: Session, *, organization_id: int, suffix: str) -> tuple[models.Course, models.Class]:
    course = models.Course(
        name=f"Curso Operacional {suffix}",
        abbreviation=f"COP{suffix}",
        organization_id=organization_id,
    )
    db.add(course)
    db.flush()

    klass = models.Class(
        name=f"Turma Operacional {suffix}",
        size=24,
        start_year=2025,
        end_year=2028,
        grade_level=10,
        course_id=course.id,
        organization_id=organization_id,
    )
    db.add(klass)
    db.flush()

    return course, klass


def _create_room_and_timeslots(db: Session, *, organization_id: int, suffix: str) -> tuple[models.Room, models.Timeslot, models.Timeslot]:
    room = models.Room(
        name=f"Sala Operacional {suffix}",
        capacity=30,
        type=models.RoomType.normal,
        organization_id=organization_id,
    )
    db.add(room)
    db.flush()

    slot_multi = models.Timeslot(
        day_of_week=0,
        start_time=time(9, 0),
        end_time=time(11, 0),
        organization_id=organization_id,
    )
    db.add(slot_multi)

    slot_gap = models.Timeslot(
        day_of_week=1,
        start_time=time(9, 0),
        end_time=time(11, 0),
        organization_id=organization_id,
    )
    db.add(slot_gap)
    db.flush()

    return room, slot_multi, slot_gap


def _create_teacher(db: Session, *, organization_id: int, name: str) -> models.Teacher:
    teacher = models.Teacher(name=name, organization_id=organization_id)
    db.add(teacher)
    db.flush()
    return teacher


def _create_subject_and_module(
    db: Session,
    *,
    organization_id: int,
    name: str,
    code: str,
    hours_total: int = 30,
) -> tuple[models.Subject, models.Module]:
    subject = models.Subject(
        name=name,
        required_room_type=models.RoomType.normal,
        organization_id=organization_id,
    )
    db.add(subject)
    db.flush()

    module = models.Module(
        organization_id=organization_id,
        name=f"Modulo {name}",
        code=code,
        hours_total=hours_total,
        order=1,
        subject_id=subject.id,
    )
    db.add(module)
    db.flush()

    return subject, module


def _link_class_subject(
    db: Session,
    *,
    klass: models.Class,
    subject: models.Subject,
    teacher: models.Teacher,
) -> None:
    existing = db.query(models.ClassSubjectLink).filter_by(
        class_id=klass.id,
        subject_id=subject.id,
        grade_level=klass.grade_level,
    ).first()
    if existing:
        return
    db.add(models.ClassSubjectLink(
        organization_id=klass.organization_id,
        class_id=klass.id,
        subject_id=subject.id,
        grade_level=klass.grade_level,
        teacher_id=teacher.id,
    ))


def _set_availability(
    db: Session,
    *,
    teacher: models.Teacher,
    slot: models.Timeslot,
    score: models.PreferenceLevel,
) -> None:
    db.add(models.Availability(
        organization_id=teacher.organization_id,
        teacher_id=teacher.id,
        timeslot_id=slot.id,
        score=score.value,
    ))


def _create_lesson(
    db: Session,
    *,
    organization_id: int,
    klass: models.Class,
    subject: models.Subject,
    teacher: models.Teacher,
) -> models.Lesson:
    lesson = models.Lesson(
        organization_id=organization_id,
        class_id=klass.id,
        subject_id=subject.id,
        teacher_id=teacher.id,
    )
    db.add(lesson)
    db.flush()
    return lesson


def _create_schedule_output(
    db: Session,
    *,
    organization_id: int,
    lesson: models.Lesson,
    slot: models.Timeslot,
    room: models.Room,
    target_date: date,
    generation_id: str,
) -> models.ScheduleOutput:
    schedule_output = models.ScheduleOutput(
        organization_id=organization_id,
        lesson_id=lesson.id,
        timeslot_id=slot.id,
        room_id=room.id,
        generation_id=generation_id,
        date=target_date,
        is_draft=False,
    )
    db.add(schedule_output)
    db.flush()
    return schedule_output


def _create_occurrence(
    db: Session,
    *,
    organization_id: int,
    schedule_output: models.ScheduleOutput,
    target_date: date,
    status: models.LessonOccurrenceStatus,
    planned_module_id: int,
    planned_teacher_id: int,
    hours: float,
    substitute_teacher_id: int | None = None,
    substitute_subject_id: int | None = None,
    executed_module_id: int | None = None,
    executed_teacher_id: int | None = None,
    decided_by_user_id: int | None = None,
    decided_at: datetime | None = None,
) -> models.LessonOccurrence:
    occurrence = models.LessonOccurrence(
        organization_id=organization_id,
        schedule_output_id=schedule_output.id,
        date=target_date,
        status=status,
        planned_hours=hours,
        substitute_teacher_id=substitute_teacher_id,
        substitute_subject_id=substitute_subject_id,
        planned_teacher_id=planned_teacher_id,
        executed_teacher_id=executed_teacher_id,
        planned_module_id=planned_module_id,
        executed_module_id=executed_module_id,
        hours_given=hours if status != models.LessonOccurrenceStatus.GAP else 0.0,
        decided_by_user_id=decided_by_user_id,
        decided_at=decided_at,
    )
    db.add(occurrence)
    db.flush()
    return occurrence


def _collect_totals(db: Session) -> dict[str, int]:
    return {
        "organizations": int(db.execute(select(func.count(models.Organization.id))).scalar_one()),
        "teachers": int(db.execute(select(func.count(models.Teacher.id))).scalar_one()),
        "subjects": int(db.execute(select(func.count(models.Subject.id))).scalar_one()),
        "classes": int(db.execute(select(func.count(models.Class.id))).scalar_one()),
        "lessons": int(db.execute(select(func.count(models.Lesson.id))).scalar_one()),
        "schedule_outputs": int(db.execute(select(func.count(models.ScheduleOutput.id))).scalar_one()),
        "occurrences": int(db.execute(select(func.count(models.LessonOccurrence.id))).scalar_one()),
        "availabilities": int(db.execute(select(func.count(models.Availability.id))).scalar_one()),
    }


def seed_operational_scenarios_sync(db: Session) -> dict[str, Any]:
    """Populate a deterministic operational dataset for Alpha V1 Step 6."""
    org_a, admin_a = _create_organization(
        db,
        org_name=ORG_A_NAME,
        admin_email="admin.operacional.a@seed.pt",
    )
    org_b, admin_b = _create_organization(
        db,
        org_name=ORG_B_NAME,
        admin_email="admin.operacional.b@seed.pt",
    )

    _, class_a = _create_course_and_class(db, organization_id=org_a.id, suffix="A")
    _, class_b = _create_course_and_class(db, organization_id=org_b.id, suffix="B")

    room_a, slot_a_multi, slot_a_gap = _create_room_and_timeslots(db, organization_id=org_a.id, suffix="A")
    room_b, slot_b_multi, _ = _create_room_and_timeslots(db, organization_id=org_b.id, suffix="B")

    planned_teacher_a = _create_teacher(db, organization_id=org_a.id, name="Prof Planeado A")
    candidate_a1 = _create_teacher(db, organization_id=org_a.id, name="Prof Candidato A1")
    candidate_a2 = _create_teacher(db, organization_id=org_a.id, name="Prof Candidato A2")
    blocked_a = _create_teacher(db, organization_id=org_a.id, name="Prof Sem Elegibilidade A")

    planned_teacher_b = _create_teacher(db, organization_id=org_b.id, name="Prof Planeado B")
    candidate_b1 = _create_teacher(db, organization_id=org_b.id, name="Prof Candidato B1")

    planned_subject_a, planned_module_a = _create_subject_and_module(
        db,
        organization_id=org_a.id,
        name="Programacao A",
        code="OPA-PROG-01",
    )
    planned_gap_subject_a, planned_gap_module_a = _create_subject_and_module(
        db,
        organization_id=org_a.id,
        name="Arquitetura A",
        code="OPA-ARQ-01",
    )
    alt_subject_a1, alt_module_a1 = _create_subject_and_module(
        db,
        organization_id=org_a.id,
        name="Redes A",
        code="OPA-RED-01",
    )
    alt_subject_a2, _ = _create_subject_and_module(
        db,
        organization_id=org_a.id,
        name="Ingles Tecnico A",
        code="OPA-ING-01",
    )
    blocked_subject_a, _ = _create_subject_and_module(
        db,
        organization_id=org_a.id,
        name="Fisica A",
        code="OPA-FIS-01",
    )

    planned_subject_b, planned_module_b = _create_subject_and_module(
        db,
        organization_id=org_b.id,
        name="Programacao B",
        code="OPB-PROG-01",
    )
    alt_subject_b1, _ = _create_subject_and_module(
        db,
        organization_id=org_b.id,
        name="Redes B",
        code="OPB-RED-01",
    )

    _link_class_subject(db, klass=class_a, subject=planned_subject_a, teacher=planned_teacher_a)
    _link_class_subject(db, klass=class_a, subject=planned_gap_subject_a, teacher=planned_teacher_a)
    _link_class_subject(db, klass=class_a, subject=alt_subject_a1, teacher=candidate_a1)
    _link_class_subject(db, klass=class_a, subject=alt_subject_a2, teacher=candidate_a2)
    _link_class_subject(db, klass=class_a, subject=blocked_subject_a, teacher=blocked_a)

    _link_class_subject(db, klass=class_b, subject=planned_subject_b, teacher=planned_teacher_b)
    _link_class_subject(db, klass=class_b, subject=alt_subject_b1, teacher=candidate_b1)

    _set_availability(db, teacher=planned_teacher_a, slot=slot_a_multi, score=models.PreferenceLevel.NEUTRAL)
    _set_availability(db, teacher=planned_teacher_a, slot=slot_a_gap, score=models.PreferenceLevel.NEUTRAL)
    _set_availability(db, teacher=candidate_a1, slot=slot_a_multi, score=models.PreferenceLevel.PREFERRED)
    _set_availability(db, teacher=candidate_a2, slot=slot_a_multi, score=models.PreferenceLevel.PREFERRED)

    _set_availability(db, teacher=candidate_a1, slot=slot_a_gap, score=models.PreferenceLevel.IMPOSSIBLE)
    _set_availability(db, teacher=candidate_a2, slot=slot_a_gap, score=models.PreferenceLevel.IMPOSSIBLE)
    _set_availability(db, teacher=blocked_a, slot=slot_a_gap, score=models.PreferenceLevel.IMPOSSIBLE)

    _set_availability(db, teacher=planned_teacher_b, slot=slot_b_multi, score=models.PreferenceLevel.NEUTRAL)
    _set_availability(db, teacher=candidate_b1, slot=slot_b_multi, score=models.PreferenceLevel.PREFERRED)

    lesson_multi = _create_lesson(
        db,
        organization_id=org_a.id,
        klass=class_a,
        subject=planned_subject_a,
        teacher=planned_teacher_a,
    )
    lesson_gap = _create_lesson(
        db,
        organization_id=org_a.id,
        klass=class_a,
        subject=planned_gap_subject_a,
        teacher=planned_teacher_a,
    )

    lesson_b = _create_lesson(
        db,
        organization_id=org_b.id,
        klass=class_b,
        subject=planned_subject_b,
        teacher=planned_teacher_b,
    )

    schedule_multi = _create_schedule_output(
        db,
        organization_id=org_a.id,
        lesson=lesson_multi,
        slot=slot_a_multi,
        room=room_a,
        target_date=REFERENCE_DATE,
        generation_id="seed-operational-a-multi",
    )
    schedule_gap = _create_schedule_output(
        db,
        organization_id=org_a.id,
        lesson=lesson_gap,
        slot=slot_a_gap,
        room=room_a,
        target_date=REFERENCE_DATE,
        generation_id="seed-operational-a-gap",
    )
    schedule_historical = _create_schedule_output(
        db,
        organization_id=org_a.id,
        lesson=lesson_multi,
        slot=slot_a_multi,
        room=room_a,
        target_date=HISTORICAL_DATE,
        generation_id="seed-operational-a-history",
    )

    schedule_b = _create_schedule_output(
        db,
        organization_id=org_b.id,
        lesson=lesson_b,
        slot=slot_b_multi,
        room=room_b,
        target_date=REFERENCE_DATE,
        generation_id="seed-operational-b-base",
    )

    multi_occurrence = _create_occurrence(
        db,
        organization_id=org_a.id,
        schedule_output=schedule_multi,
        target_date=REFERENCE_DATE,
        status=models.LessonOccurrenceStatus.GIVEN,
        planned_module_id=planned_module_a.id,
        planned_teacher_id=planned_teacher_a.id,
        hours=2.0,
    )

    no_eligible_occurrence = _create_occurrence(
        db,
        organization_id=org_a.id,
        schedule_output=schedule_gap,
        target_date=REFERENCE_DATE,
        status=models.LessonOccurrenceStatus.GAP,
        planned_module_id=planned_gap_module_a.id,
        planned_teacher_id=planned_teacher_a.id,
        hours=2.0,
        decided_by_user_id=admin_a.id,
        decided_at=datetime(2026, 4, 20, 8, 30, tzinfo=timezone.utc),
    )

    _create_occurrence(
        db,
        organization_id=org_a.id,
        schedule_output=schedule_historical,
        target_date=HISTORICAL_DATE,
        status=models.LessonOccurrenceStatus.SUBSTITUTED,
        planned_module_id=planned_module_a.id,
        planned_teacher_id=planned_teacher_a.id,
        substitute_teacher_id=candidate_a1.id,
        substitute_subject_id=alt_subject_a1.id,
        executed_module_id=alt_module_a1.id,
        executed_teacher_id=candidate_a1.id,
        hours=2.0,
        decided_by_user_id=admin_a.id,
        decided_at=datetime(2026, 4, 17, 10, 0, tzinfo=timezone.utc),
    )

    org_b_occurrence = _create_occurrence(
        db,
        organization_id=org_b.id,
        schedule_output=schedule_b,
        target_date=REFERENCE_DATE,
        status=models.LessonOccurrenceStatus.GIVEN,
        planned_module_id=planned_module_b.id,
        planned_teacher_id=planned_teacher_b.id,
        hours=2.0,
    )

    db.commit()

    signature = {
        "profile": "alpha_v1_operational_step6",
        "reference_date": REFERENCE_DATE.isoformat(),
        "organization_count": 2,
        "scenario_codes": [
            SCENARIO_MULTI_ELIGIBLE,
            SCENARIO_NO_ELIGIBLE,
        ],
        "expected": {
            SCENARIO_MULTI_ELIGIBLE: {
                "minimum_recommendations": 2,
            },
            SCENARIO_NO_ELIGIBLE: {
                "expected_recommendations": 0,
                "fallback_status": models.LessonOccurrenceStatus.GAP.value,
            },
        },
        "totals": _collect_totals(db),
    }

    runtime = {
        "org_a_id": org_a.id,
        "org_b_id": org_b.id,
        "org_a_admin_user_id": admin_a.id,
        "org_b_admin_user_id": admin_b.id,
        "org_a_class_id": class_a.id,
        "org_b_class_id": class_b.id,
        "multi_eligible_occurrence_id": multi_occurrence.id,
        "no_eligible_occurrence_id": no_eligible_occurrence.id,
        "org_b_occurrence_id": org_b_occurrence.id,
        "expected_first_recommendation_teacher_id": candidate_a2.id,
    }

    return {
        "signature": signature,
        "runtime": runtime,
    }
