"""Testes para diff de rascunhos e estatísticas de comparação."""

import pytest
from datetime import date, time, timedelta

from app import models
from app.services import schedule_service

pytestmark = pytest.mark.integration


class TestDiffSummary:
    def test_diff_empty_when_no_data(self, sync_db):
        org = models.Organization(name="Test", plan_status="active")
        sync_db.add(org)
        sync_db.commit()
        diff = schedule_service.get_diff_sync(sync_db, org.id, "nonexistent")
        assert diff["added"] == 0
        assert diff["removed"] == 0

    def test_diff_counts_added_blocks(self, sync_db):
        org = models.Organization(name="Test", plan_status="active")
        sync_db.add(org)
        sync_db.commit()

        teacher = models.Teacher(name="Prof", organization_id=org.id)
        sync_db.add(teacher)
        sync_db.commit()

        subject = models.Subject(name="Mat", organization_id=org.id)
        sync_db.add(subject)
        sync_db.commit()

        course = models.Course(name="Curso", abbreviation="C1", organization_id=org.id)
        sync_db.add(course)
        sync_db.commit()

        class_ = models.Class(
            name="10A", size=25, grade_level=10,
            start_year=2025, end_year=2028,
            course_id=course.id, organization_id=org.id,
        )
        sync_db.add(class_)
        sync_db.commit()

        ts = models.Timeslot(
            day_of_week=0, start_time=time(8, 0), end_time=time(8, 50),
            organization_id=org.id,
        )
        sync_db.add(ts)
        sync_db.commit()

        room = models.Room(name="Sala 1", type=models.RoomType.normal, organization_id=org.id)
        sync_db.add(room)
        sync_db.commit()

        lesson = models.Lesson(
            organization_id=org.id, class_id=class_.id,
            subject_id=subject.id, teacher_id=teacher.id,
        )
        sync_db.add(lesson)
        sync_db.commit()

        today = date.today()
        future = today + timedelta(days=30)
        gen_id = "gen-diff-test"

        schedule_service.create_schedule_output_with_date_sync(
            sync_db, lesson.id, ts.id, room.id,
            future, org.id, gen_id, is_draft=True,
        )
        sync_db.commit()

        diff = schedule_service.get_diff_sync(sync_db, org.id, gen_id)
        assert diff["total_draft"] == 1

    def test_diff_tenant_isolation(self, sync_db):
        org_a = models.Organization(name="A", plan_status="active")
        org_b = models.Organization(name="B", plan_status="active")
        sync_db.add_all([org_a, org_b])
        sync_db.commit()

        diff = schedule_service.get_diff_sync(sync_db, org_a.id, "gen-other-org")
        assert diff["total_draft"] == 0
