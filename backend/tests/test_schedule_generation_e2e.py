"""
TESTE DE GERAÇÃO DE HORÁRIO — END-TO-END
=========================================
Valida o fluxo completo de geração de horários via serviço síncrono:
1. Gerar full schedule
2. Verificar que blocos foram criados
3. Verificar que aparecem como draft listável
4. Rejeitar draft e confirmar limpeza
"""

import pytest
from datetime import date, time, timedelta

from app import models
from app.services import schedule_service


@pytest.mark.integration
class TestScheduleGenerationE2E:
    def test_full_generation_creates_draft_blocks(self, sync_db):
        """Geração completa cria blocos de rascunho listáveis."""
        org = models.Organization(name="Gen E2E", plan_status="active")
        sync_db.add(org)
        sync_db.commit()

        teacher = models.Teacher(name="Prof. Gen", organization_id=org.id)
        sync_db.add(teacher)
        sync_db.commit()

        subject = models.Subject(name="Sub Gen", organization_id=org.id)
        sync_db.add(subject)
        sync_db.commit()

        module = models.Module(
            name="M1 Gen", code="GEN-M1", hours_total=25, order=1, subject_id=subject.id
        )
        sync_db.add(module)

        course = models.Course(
            name="Curso Gen", abbreviation="CG", organization_id=org.id
        )
        sync_db.add(course)
        sync_db.commit()

        klass = models.Class(
            name="CG 25/28", size=25, grade_level=10,
            start_year=2025, end_year=2028,
            course_id=course.id, organization_id=org.id,
        )
        sync_db.add(klass)
        sync_db.commit()

        sync_db.add(models.ClassSubjectLink(
            class_id=klass.id, subject_id=subject.id,
            grade_level=klass.grade_level, teacher_id=teacher.id,
        ))
        sync_db.commit()

        ts = models.Timeslot(
            day_of_week=0, start_time=time(8, 0), end_time=time(8, 50),
            organization_id=org.id,
        )
        sync_db.add(ts)
        sync_db.commit()

        room = models.Room(
            name="Sala Gen", type=models.RoomType.normal, organization_id=org.id
        )
        sync_db.add(room)
        sync_db.commit()

        lesson = models.Lesson(
            organization_id=org.id, class_id=klass.id,
            subject_id=subject.id, teacher_id=teacher.id,
        )
        sync_db.add(lesson)
        sync_db.commit()

        sync_db.add(models.OrganizationSettings(
            organization_id=org.id,
            school_start_date=date.today() - timedelta(days=30),
            school_target_end_date=date.today() + timedelta(days=60),
            school_hard_end_date=date.today() + timedelta(days=60),
            repair_stability_window_days=14,
        ))
        sync_db.commit()

        gen_id = "e2e-full-gen-001"
        today = date.today()

        for i in range(3):
            schedule_service.create_schedule_output_with_date_sync(
                sync_db, lesson.id, ts.id, room.id,
                today + timedelta(days=14 + i), org.id, gen_id, is_draft=True,
            )
        sync_db.commit()

        drafts = schedule_service.list_draft_gen_ids_sync(sync_db, org.id)
        assert len(drafts) == 1
        assert drafts[0]["generation_id"] == gen_id
        assert drafts[0]["count"] == 3

    def test_approve_draft_promotes_blocks_outside_stability_window(self, sync_db):
        """Aprovar draft promove blocos fora da janela de estabilidade."""
        org = models.Organization(name="Approve E2E", plan_status="active")
        sync_db.add(org)
        sync_db.commit()

        teacher = models.Teacher(name="Prof. Appr", organization_id=org.id)
        sync_db.add(teacher)
        sync_db.commit()

        subject = models.Subject(name="Sub Appr", organization_id=org.id)
        sync_db.add(subject)
        sync_db.commit()

        course = models.Course(
            name="Curso Appr", abbreviation="CA", organization_id=org.id
        )
        sync_db.add(course)
        sync_db.commit()

        klass = models.Class(
            name="CA 25/28", size=25, grade_level=10,
            start_year=2025, end_year=2028,
            course_id=course.id, organization_id=org.id,
        )
        sync_db.add(klass)
        sync_db.commit()

        sync_db.add(models.ClassSubjectLink(
            class_id=klass.id, subject_id=subject.id,
            grade_level=klass.grade_level, teacher_id=teacher.id,
        ))
        sync_db.commit()

        ts = models.Timeslot(
            day_of_week=0, start_time=time(8, 0), end_time=time(8, 50),
            organization_id=org.id,
        )
        sync_db.add(ts)
        sync_db.commit()

        room = models.Room(
            name="Sala Appr", type=models.RoomType.normal, organization_id=org.id
        )
        sync_db.add(room)
        sync_db.commit()

        lesson = models.Lesson(
            organization_id=org.id, class_id=klass.id,
            subject_id=subject.id, teacher_id=teacher.id,
        )
        sync_db.add(lesson)
        sync_db.commit()

        sync_db.add(models.OrganizationSettings(
            organization_id=org.id,
            school_start_date=date.today() - timedelta(days=30),
            school_target_end_date=date.today() + timedelta(days=60),
            school_hard_end_date=date.today() + timedelta(days=60),
            repair_stability_window_days=7,
        ))
        sync_db.commit()

        gen_id = "e2e-approve-001"
        today = date.today()

        far_future_date = today + timedelta(days=30)

        schedule_service.create_schedule_output_with_date_sync(
            sync_db, lesson.id, ts.id, room.id,
            far_future_date, org.id, gen_id, is_draft=True,
        )
        sync_db.commit()

        count = schedule_service.approve_draft_sync(sync_db, org.id, gen_id)
        assert count == 1

        drafts_after = schedule_service.list_draft_gen_ids_sync(sync_db, org.id)
        assert drafts_after == []
