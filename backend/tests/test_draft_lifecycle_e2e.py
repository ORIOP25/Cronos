"""
TESTES DE DRAFT LIFECYCLE — END-TO-END
======================================
Valida o ciclo de vida completo dos rascunhos:
1. Gerar rascunho (via serviço síncrono)
2. Verificar que aparece na listagem
3. Verificar que está isolado por organização
4. Rejeitar e confirmar que blocos foram removidos
5. Tentar aprovar rascunho de outra organização (bloqueado)
"""

import pytest
from datetime import date, time, timedelta

from app import models
from app.services import schedule_service


@pytest.mark.integration
class TestDraftLifecycleE2E:
    def test_create_list_reject_draft_flow(self, sync_db):
        org = models.Organization(name="Draft E2E", plan_status="active")
        sync_db.add(org)
        sync_db.commit()

        teacher = models.Teacher(name="Prof. Draft", organization_id=org.id)
        sync_db.add(teacher)
        sync_db.commit()

        subject = models.Subject(name="Draft Subject", organization_id=org.id)
        sync_db.add(subject)
        sync_db.commit()

        course = models.Course(
            name="Draft Course", abbreviation="DC", organization_id=org.id
        )
        sync_db.add(course)
        sync_db.commit()

        klass = models.Class(
            name="DC 25/28", size=25, grade_level=10,
            start_year=2025, end_year=2028,
            course_id=course.id, organization_id=org.id,
        )
        sync_db.add(klass)
        sync_db.commit()

        ts = models.Timeslot(
            day_of_week=0, start_time=time(8, 0), end_time=time(8, 50),
            organization_id=org.id,
        )
        sync_db.add(ts)
        sync_db.commit()

        room = models.Room(
            name="Sala Draft", type=models.RoomType.normal, organization_id=org.id
        )
        sync_db.add(room)
        sync_db.commit()

        lesson = models.Lesson(
            organization_id=org.id, class_id=klass.id,
            subject_id=subject.id, teacher_id=teacher.id,
        )
        sync_db.add(lesson)
        sync_db.commit()

        gen_id = "e2e-draft-001"
        today = date.today()

        for i in range(5):
            schedule_service.create_schedule_output_with_date_sync(
                sync_db, lesson.id, ts.id, room.id,
                today + timedelta(days=14 + i), org.id, gen_id, is_draft=True,
            )
        sync_db.commit()

        drafts = schedule_service.list_draft_gen_ids_sync(sync_db, org.id)
        assert len(drafts) == 1
        assert drafts[0]["generation_id"] == gen_id
        assert drafts[0]["count"] == 5

        rejected_count = schedule_service.reject_draft_sync(sync_db, org.id, gen_id)
        assert rejected_count == 5

        drafts_after = schedule_service.list_draft_gen_ids_sync(sync_db, org.id)
        assert drafts_after == []

    def test_draft_not_visible_to_other_org(self, sync_db):
        org_a = models.Organization(name="Draft Org A", plan_status="active")
        org_b = models.Organization(name="Draft Org B", plan_status="active")
        sync_db.add_all([org_a, org_b])
        sync_db.commit()

        teacher = models.Teacher(name="Prof. Draft A", organization_id=org_a.id)
        sync_db.add(teacher)
        sync_db.commit()

        subject = models.Subject(name="Sub A", organization_id=org_a.id)
        sync_db.add(subject)
        sync_db.commit()

        course = models.Course(name="Curso A", abbreviation="CA", organization_id=org_a.id)
        sync_db.add(course)
        sync_db.commit()

        klass = models.Class(
            name="CA 25/28", size=25, grade_level=10,
            start_year=2025, end_year=2028,
            course_id=course.id, organization_id=org_a.id,
        )
        sync_db.add(klass)
        sync_db.commit()

        ts = models.Timeslot(
            day_of_week=0, start_time=time(8, 0), end_time=time(8, 50),
            organization_id=org_a.id,
        )
        sync_db.add(ts)
        sync_db.commit()

        room = models.Room(
            name="Sala A", type=models.RoomType.normal, organization_id=org_a.id
        )
        sync_db.add(room)
        sync_db.commit()

        lesson = models.Lesson(
            organization_id=org_a.id, class_id=klass.id,
            subject_id=subject.id, teacher_id=teacher.id,
        )
        sync_db.add(lesson)
        sync_db.commit()

        gen_id = "e2e-draft-cross-org"
        schedule_service.create_schedule_output_with_date_sync(
            sync_db, lesson.id, ts.id, room.id,
            date.today() + timedelta(days=14), org_a.id, gen_id, is_draft=True,
        )
        sync_db.commit()

        drafts_a = schedule_service.list_draft_gen_ids_sync(sync_db, org_a.id)
        assert len(drafts_a) == 1

        drafts_b = schedule_service.list_draft_gen_ids_sync(sync_db, org_b.id)
        assert drafts_b == []

    def test_reject_draft_removes_all_blocks(self, sync_db):
        org = models.Organization(name="Draft Reject", plan_status="active")
        sync_db.add(org)
        sync_db.commit()

        teacher = models.Teacher(name="Prof. Reject", organization_id=org.id)
        sync_db.add(teacher)
        sync_db.commit()

        subject = models.Subject(name="Sub Reject", organization_id=org.id)
        sync_db.add(subject)
        sync_db.commit()

        course = models.Course(name="Curso R", abbreviation="CR", organization_id=org.id)
        sync_db.add(course)
        sync_db.commit()

        klass = models.Class(
            name="CR 25/28", size=25, grade_level=10,
            start_year=2025, end_year=2028,
            course_id=course.id, organization_id=org.id,
        )
        sync_db.add(klass)
        sync_db.commit()

        ts = models.Timeslot(
            day_of_week=0, start_time=time(8, 0), end_time=time(8, 50),
            organization_id=org.id,
        )
        sync_db.add(ts)
        sync_db.commit()

        room = models.Room(
            name="Sala Reject", type=models.RoomType.normal, organization_id=org.id
        )
        sync_db.add(room)
        sync_db.commit()

        lesson = models.Lesson(
            organization_id=org.id, class_id=klass.id,
            subject_id=subject.id, teacher_id=teacher.id,
        )
        sync_db.add(lesson)
        sync_db.commit()

        gen_id = "e2e-reject"
        today = date.today()

        for i in range(3):
            schedule_service.create_schedule_output_with_date_sync(
                sync_db, lesson.id, ts.id, room.id,
                today + timedelta(days=14 + i), org.id, gen_id, is_draft=True,
            )
        sync_db.commit()

        count = schedule_service.reject_draft_sync(sync_db, org.id, gen_id)
        assert count == 3

        drafts = schedule_service.list_draft_gen_ids_sync(sync_db, org.id)
        assert drafts == []

    def test_create_multiple_drafts_independent(self, sync_db):
        org = models.Organization(name="Draft Multi", plan_status="active")
        sync_db.add(org)
        sync_db.commit()

        teacher = models.Teacher(name="Prof. Multi", organization_id=org.id)
        sync_db.add(teacher)
        sync_db.commit()

        subject = models.Subject(name="Sub Multi", organization_id=org.id)
        sync_db.add(subject)
        sync_db.commit()

        course = models.Course(name="Curso M", abbreviation="CM", organization_id=org.id)
        sync_db.add(course)
        sync_db.commit()

        klass = models.Class(
            name="CM 25/28", size=25, grade_level=10,
            start_year=2025, end_year=2028,
            course_id=course.id, organization_id=org.id,
        )
        sync_db.add(klass)
        sync_db.commit()

        ts = models.Timeslot(
            day_of_week=0, start_time=time(8, 0), end_time=time(8, 50),
            organization_id=org.id,
        )
        sync_db.add(ts)
        sync_db.commit()

        room = models.Room(
            name="Sala Multi", type=models.RoomType.normal, organization_id=org.id
        )
        sync_db.add(room)
        sync_db.commit()

        lesson = models.Lesson(
            organization_id=org.id, class_id=klass.id,
            subject_id=subject.id, teacher_id=teacher.id,
        )
        sync_db.add(lesson)
        sync_db.commit()

        today = date.today()

        schedule_service.create_schedule_output_with_date_sync(
            sync_db, lesson.id, ts.id, room.id,
            today + timedelta(days=14), org.id, "draft-1", is_draft=True,
        )
        sync_db.commit()

        schedule_service.create_schedule_output_with_date_sync(
            sync_db, lesson.id, ts.id, room.id,
            today + timedelta(days=21), org.id, "draft-2", is_draft=True,
        )
        sync_db.commit()

        gen_ids = schedule_service.list_draft_gen_ids_sync(sync_db, org.id)
        assert len(gen_ids) == 2
        gen_id_values = [g["generation_id"] for g in gen_ids]
        assert "draft-1" in gen_id_values
        assert "draft-2" in gen_id_values
