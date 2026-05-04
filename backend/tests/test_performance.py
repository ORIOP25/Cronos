"""
TESTE DE PERFORMANCE — CARGA MODERADA
=====================================
Simula cenário realista com seed de dados representativo de uma escola
típica de ensino profissional e mede tempos de operações críticas.
"""

import time as perf_time
from datetime import date, time, timedelta

import pytest

from app import models
from app.models import LessonOccurrenceStatus
from app.services import (
    occurrence_service,
    schedule_service,
    lesson_log_service,
    timesheet_service,
)

pytestmark = pytest.mark.slow


def _seed_realistic_school(sync_db):
    """Cria uma escola com 3 cursos, 7 turmas, 15 profs, 12 disciplinas."""
    org = models.Organization(name="Escola Perf", plan_status="active")
    sync_db.add(org)
    sync_db.flush()

    sync_db.add(models.OrganizationSettings(
        organization_id=org.id,
        school_start_date=date.today() - timedelta(days=120),
        school_target_end_date=date.today() + timedelta(days=180),
        school_hard_end_date=date.today() + timedelta(days=180),
        repair_stability_window_days=14,
    ))
    sync_db.flush()

    courses = []
    for i in range(3):
        c = models.Course(
            name=f"Curso Perf {i+1}",
            abbreviation=f"CP{i+1}",
            organization_id=org.id,
        )
        sync_db.add(c)
        sync_db.flush()
        courses.append(c)

    classes = []
    for i, course in enumerate(courses):
        for grade in [10, 11]:
            if i == 2 and grade == 11:
                continue
            klass = models.Class(
                name=f"{course.abbreviation} {grade}º",
                size=22 + i * 2,
                grade_level=grade,
                start_year=2025 if grade == 10 else 2024,
                end_year=2028 if grade == 10 else 2027,
                course_id=course.id,
                organization_id=org.id,
            )
            sync_db.add(klass)
            sync_db.flush()
            classes.append(klass)

    teachers = []
    for i in range(15):
        t = models.Teacher(
            name=f"Prof. Perf {i+1}",
            organization_id=org.id,
        )
        sync_db.add(t)
        sync_db.flush()
        teachers.append(t)

    subjects = []
    for i in range(12):
        room_type = models.RoomType.lab if i % 4 == 0 else models.RoomType.normal
        s = models.Subject(
            name=f"Disciplina Perf {i+1}",
            organization_id=org.id,
            required_room_type=room_type,
        )
        sync_db.add(s)
        sync_db.flush()
        subjects.append(s)

        for m_order in range(1, 4):
            sync_db.add(models.Module(
                name=f"M{m_order} - {s.name}",
                code=f"P{i+1:02d}{m_order}",
                hours_total=25 + m_order * 5,
                order=m_order,
                subject_id=s.id,
            ))

    sync_db.flush()

    timeslots = []
    for day in range(5):
        for slot_idx, (start_h, start_m) in enumerate([
            (8, 30), (9, 20), (10, 20), (11, 10),
            (12, 0), (13, 30), (14, 20), (15, 10),
        ]):
            ts = models.Timeslot(
                day_of_week=day,
                start_time=time(start_h, start_m),
                end_time=time(start_h, start_m + 50),
                organization_id=org.id,
            )
            sync_db.add(ts)
            sync_db.flush()
            timeslots.append(ts)

    rooms = []
    for i in range(12):
        rtype = models.RoomType.lab if i >= 8 else models.RoomType.normal
        r = models.Room(
            name=f"Sala {i+1}",
            capacity=25 + i,
            type=rtype,
            organization_id=org.id,
        )
        sync_db.add(r)
        sync_db.flush()
        rooms.append(r)

    teacher_idx = 0
    for klass in classes:
        for subj in subjects[:4]:
            teacher = teachers[teacher_idx % len(teachers)]
            sync_db.add(models.ClassSubjectLink(
                class_id=klass.id,
                subject_id=subj.id,
                grade_level=klass.grade_level,
                teacher_id=teacher.id,
            ))
            sync_db.flush()

            lesson = models.Lesson(
                organization_id=org.id,
                class_id=klass.id,
                subject_id=subj.id,
                teacher_id=teacher.id,
            )
            sync_db.add(lesson)
            sync_db.flush()

            today = date.today()
            for week_offset in range(4):
                for ts in timeslots:
                    if ts.day_of_week == (week_offset + 1) % 5:
                        schedule_service.create_schedule_output_with_date_sync(
                            sync_db, lesson.id, ts.id, rooms[teacher_idx % len(rooms)].id,
                            today + timedelta(weeks=week_offset + 1, days=-((today.weekday() - ts.day_of_week) % 7)),
                            org.id, "gen-perf", is_draft=False,
                        )
            teacher_idx += 1

    sync_db.commit()

    return {
        "org_id": org.id,
        "class_count": len(classes),
        "teacher_count": len(teachers),
        "subject_count": len(subjects),
        "timeslot_count": len(timeslots),
        "room_count": len(rooms),
    }


class TestPerformanceRealisticLoad:
    def test_seed_and_auto_confirm_performance(self, sync_db):
        """Seed realista + auto-confirm deve completar em tempo aceitável."""
        start_seed = perf_time.monotonic()
        ctx = _seed_realistic_school(sync_db)
        seed_time = perf_time.monotonic() - start_seed

        assert seed_time < 30, f"Seed demorou {seed_time:.1f}s"

        today = date.today()
        target_date = today + timedelta(days=7)

        start_confirm = perf_time.monotonic()
        created = occurrence_service.auto_confirm_daily_sync(
            sync_db, ctx["org_id"], target_date
        )
        confirm_time = perf_time.monotonic() - start_confirm

        assert confirm_time < 30, f"Auto-confirm demorou {confirm_time:.1f}s"
        assert created >= 0

    def test_debt_calculation_performance(self, sync_db):
        """Cálculo de dívidas deve ser rápido mesmo com muitos dados."""
        ctx = _seed_realistic_school(sync_db)

        today = date.today()
        for week_offset in range(8):
            target_date = today + timedelta(weeks=week_offset + 1)
            occurrence_service.auto_confirm_daily_sync(
                sync_db, ctx["org_id"], target_date
            )
        sync_db.commit()

        start = perf_time.monotonic()
        debts = occurrence_service.get_debts_sync(
            sync_db, ctx["org_id"]
        )
        elapsed = perf_time.monotonic() - start

        assert elapsed < 5, f"Cálculo de dívidas demorou {elapsed:.1f}s"
        assert isinstance(debts, dict)
