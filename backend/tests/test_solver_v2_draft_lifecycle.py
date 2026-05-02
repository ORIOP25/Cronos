"""Testes para o ciclo de vida de rascunhos (draft) — serviços síncronos.

Estes testes complementam test_schedule_draft_lifecycle.py com cenários
adicionais de edge cases na gestão de rascunhos.
"""

import pytest
from datetime import date, datetime, time, timedelta

from app import models
from app.services import schedule_service
from app.core.security import hash_password

pytestmark = pytest.mark.integration


class TestDraftLifecycleEdgeCases:
    def test_empty_draft_list_for_new_org(self, sync_db):
        org = models.Organization(name="Test", plan_status="active")
        sync_db.add(org)
        sync_db.commit()
        drafts = schedule_service.list_draft_gen_ids_sync(sync_db, org.id)
        assert drafts == []

    def test_draft_not_visible_to_other_org(self, sync_db):
        org_a = models.Organization(name="Org A", plan_status="active")
        org_b = models.Organization(name="Org B", plan_status="active")
        sync_db.add_all([org_a, org_b])
        sync_db.commit()

        teacher = models.Teacher(name="Prof", organization_id=org_a.id)
        sync_db.add(teacher)
        sync_db.commit()

        subject = models.Subject(name="Mat", organization_id=org_a.id)
        sync_db.add(subject)
        sync_db.commit()

        course = models.Course(name="Curso", abbreviation="C1", organization_id=org_a.id)
        sync_db.add(course)
        sync_db.commit()

        class_ = models.Class(
            name="10A", size=25, grade_level=10,
            start_year=2025, end_year=2028,
            course_id=course.id, organization_id=org_a.id,
        )
        sync_db.add(class_)
        sync_db.commit()

        ts = models.Timeslot(
            day_of_week=0, start_time=time(8, 0), end_time=time(8, 50),
            organization_id=org_a.id,
        )
        sync_db.add(ts)
        sync_db.commit()

        room = models.Room(name="Sala 1", type=models.RoomType.normal, organization_id=org_a.id)
        sync_db.add(room)
        sync_db.commit()

        lesson = models.Lesson(
            organization_id=org_a.id, class_id=class_.id,
            subject_id=subject.id, teacher_id=teacher.id,
        )
        sync_db.add(lesson)
        sync_db.commit()

        today = date.today()
        schedule_service.create_schedule_output_with_date_sync(
            sync_db, lesson.id, ts.id, room.id,
            today + timedelta(days=14), org_a.id, "gen-draft-test", is_draft=True,
        )
        sync_db.commit()

        drafts_a = schedule_service.list_draft_gen_ids_sync(sync_db, org_a.id)
        assert len(drafts_a) == 1

        drafts_b = schedule_service.list_draft_gen_ids_sync(sync_db, org_b.id)
        assert drafts_b == []

    def test_reject_draft_removes_all_blocks(self, sync_db):
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
        for i in range(3):
            schedule_service.create_schedule_output_with_date_sync(
                sync_db, lesson.id, ts.id, room.id,
                today + timedelta(days=14 + i), org.id, "gen-to-reject", is_draft=True,
            )
        sync_db.commit()

        count = schedule_service.reject_draft_sync(sync_db, org.id, "gen-to-reject")
        assert count == 3

        drafts = schedule_service.list_draft_gen_ids_sync(sync_db, org.id)
        assert drafts == []
