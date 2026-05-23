from __future__ import annotations

import pytest
import pytest_asyncio
from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import patch
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from tests.conftest import mock_clerk_payload

from app import models, schemas
from app.services import (
    lesson_log_service,
    timesheet_service,
    occurrence_service,
    settings_service,
)

# sync_db fixture is provided by conftest.py (shared across all test files)

@pytest.fixture
def base_setup(sync_db):
    import uuid
    uid = uuid.uuid4().hex[:6]
    # Create Organization
    org = models.Organization(name=f"Test Org Soft Reset {uid}", plan_status="active")
    sync_db.add(org)
    sync_db.flush()

    # Create Teacher
    teacher = models.Teacher(name=f"Prof. Teste {uid}", organization_id=org.id)
    sync_db.add(teacher)
    sync_db.flush()

    # Create User (Admin)
    admin = models.User(
        email=f"admin_{uid}@escola.com",
        is_active=True,
        role=models.UserRole.admin,
        organization_id=org.id,
    )
    sync_db.add(admin)
    sync_db.flush()

    # Create Subject & Module
    subject = models.Subject(
        name="Programação",
        organization_id=org.id,
        required_room_type=models.RoomType.normal,
    )
    sync_db.add(subject)
    sync_db.flush()

    module = models.Module(
        name="M1 - Introdução",
        hours_total=25,
        order=1,
        subject_id=subject.id,
    )
    sync_db.add(module)
    sync_db.flush()

    # Create Course & Class
    course = models.Course(
        name=f"TINF {uid}",
        abbreviation=f"T_{uid[:4]}",
        organization_id=org.id,
    )
    sync_db.add(course)
    sync_db.flush()

    class_ = models.Class(
        name="10A",
        size=20,
        start_year=2024,
        end_year=2027,
        grade_level=10,
        course_id=course.id,
        organization_id=org.id,
    )
    sync_db.add(class_)
    sync_db.flush()

    # Room & Timeslot
    room = models.Room(
        name="Sala 1",
        capacity=30,
        type=models.RoomType.normal,
        organization_id=org.id,
    )
    sync_db.add(room)
    sync_db.flush()

    timeslot = models.Timeslot(
        day_of_week=0,
        start_time=time(9, 0),
        end_time=time(11, 0),
        organization_id=org.id,
    )
    sync_db.add(timeslot)
    sync_db.flush()

    # Lesson & ScheduleOutput (Yesterday)
    lesson = models.Lesson(
        organization_id=org.id,
        class_id=class_.id,
        subject_id=subject.id,
        teacher_id=teacher.id,
    )
    sync_db.add(lesson)
    sync_db.flush()

    yesterday = date.today() - timedelta(days=1)
    
    schedule_output = models.ScheduleOutput(
        organization_id=org.id,
        lesson_id=lesson.id,
        timeslot_id=timeslot.id,
        room_id=room.id,
        generation_id="test-gen",
        date=yesterday,
        is_draft=False,
    )
    sync_db.add(schedule_output)
    
    # Pre-add ClassProgress
    progress = models.ClassProgress(
        class_id=class_.id,
        module_id=module.id,
        hours_completed=5.0
    )
    sync_db.add(progress)

    sync_db.commit()

    return {
        "organization_id": org.id,
        "teacher_id": teacher.id,
        "user_id": admin.id,
        "class_id": class_.id,
        "module_id": module.id,
        "schedule_output_id": schedule_output.id,
        "date": yesterday,
        "timeslot_start": timeslot.start_time,
        "timeslot_end": timeslot.end_time,
    }


class TestLessonRegistration:
    def test_upsert_lesson_log(self, sync_db, base_setup):
        organization_id = base_setup["organization_id"]
        output_id = base_setup["schedule_output_id"]
        
        # Act
        payload = schemas.LessonLogCreate(
            status=models.LessonLogStatus.COMPLETED,
            summary="Introdução a Python",
            notes=""
        )
        llog = lesson_log_service.upsert_lesson_log_sync(
            sync_db, organization_id, base_setup["user_id"], output_id, payload
        )
        
        # Assert
        assert llog.status == models.LessonLogStatus.COMPLETED
        assert llog.summary == "Introdução a Python"
        
        # Check ClassProgress increment
        progress = sync_db.execute(
            select(models.ClassProgress).where(
                models.ClassProgress.class_id == base_setup["class_id"],
                models.ClassProgress.module_id == base_setup["module_id"]
            )
        ).scalar_one()
        # 5.0 base + 2.0 (9:00 to 11:00)
        assert progress.hours_completed == 7.0

    def test_timesheet_submission_workflow(self, sync_db, base_setup):
        organization_id = base_setup["organization_id"]
        output_id = base_setup["schedule_output_id"]
        teacher_id = base_setup["teacher_id"]
        week_start = base_setup["date"] - timedelta(days=base_setup["date"].weekday())

        # Submeter aula
        payload = schemas.LessonLogCreate(
            status=models.LessonLogStatus.COMPLETED,
            summary="Aula teste",
            notes=""
        )
        lesson_log_service.upsert_lesson_log_sync(
            sync_db, organization_id, base_setup["user_id"], output_id, payload
        )
        
        # Submeter semana
        _ = timesheet_service.submit_timesheet_sync(
            sync_db, organization_id, teacher_id, week_start
        )
        assert timesheet.status == models.TimesheetStatus.SUBMITTED
        
        # Alterar aula deve falhar
        from app.core.exceptions import DomainError
        with pytest.raises(DomainError) as exc:
            lesson_log_service.upsert_lesson_log_sync(
                sync_db, organization_id, base_setup["user_id"], output_id, payload
            )
        assert exc.value.status_code == 400
        assert "Esta semana já foi submetida" in exc.value.message
        
        # Aprovar semana
        timesheet_service.update_timesheet_status_sync(
            sync_db, organization_id, timesheet.id, models.TimesheetStatus.APPROVED, base_setup["user_id"]
        )
        timesheet_updated = timesheet_service.get_or_create_timesheet_sync(sync_db, organization_id, teacher_id, week_start)
        assert timesheet_updated.status == models.TimesheetStatus.APPROVED


@pytest.mark.asyncio
class TestSoftReset:
    async def test_soft_reset_clears_data_and_resets_progress(self, sync_db, base_setup):
        organization_id = base_setup["organization_id"]
        
        # Using a new async session to test async function soft_reset_year
        from sqlalchemy.ext.asyncio import AsyncSession
        from app.db.database import SessionLocal
        async with SessionLocal() as async_session:
            await settings_service.soft_reset_year(async_session, organization_id)
            
            # Assert ClassProgress is 0.0
            result = await async_session.execute(
                select(models.ClassProgress).where(
                    models.ClassProgress.class_id == base_setup["class_id"],
                    models.ClassProgress.module_id == base_setup["module_id"]
                )
            )
            progress = result.scalar_one()
            assert progress.hours_completed == 0.0
            
            # Assert ScheduleOutput is deleted
            out_result = await async_session.execute(
                select(models.ScheduleOutput).where(
                    models.ScheduleOutput.organization_id == organization_id
                )
            )
            assert len(out_result.scalars().all()) == 0
            
            # Assert Timesheet deleted
            ts_result = await async_session.execute(
                select(models.TeacherWeeklyTimesheet).where(
                    models.TeacherWeeklyTimesheet.organization_id == organization_id
                )
            )
            assert len(ts_result.scalars().all()) == 0


@pytest.fixture
def substitution_setup(sync_db, base_setup):
    """Extende base_setup com um segundo professor elegível para substituição."""
    organization_id = base_setup["organization_id"]
    class_id = base_setup["class_id"]

    # Create second subject & module
    subject2 = models.Subject(
        name="Bases de Dados",
        organization_id=organization_id,
        required_room_type=models.RoomType.normal,
    )
    sync_db.add(subject2)
    sync_db.flush()

    module2 = models.Module(
        name="M1 - SQL",
        hours_total=30,
        order=1,
        subject_id=subject2.id,
    )
    sync_db.add(module2)
    sync_db.flush()

    # Link subject to course
    course = sync_db.execute(
        select(models.Course).where(models.Course.id == sync_db.execute(
            select(models.Class.course_id).where(models.Class.id == class_id)
        ).scalar_one())
    ).scalar_one()
    course.subjects.append(subject2)

    # Create substitute teacher
    sub_teacher = models.Teacher(name="Prof. Substituto", organization_id=organization_id)
    sub_teacher.subjects.append(subject2)
    sync_db.add(sub_teacher)
    sync_db.flush()

    # ClassSubjectLink for substitute
    link = models.ClassSubjectLink(
        class_id=class_id,
        subject_id=subject2.id,
        grade_level=10,
        teacher_id=sub_teacher.id,
    )
    sync_db.add(link)

    # Availability for substitute in same timeslot
    timeslot = sync_db.execute(
        select(models.Timeslot).where(
            models.Timeslot.organization_id == organization_id
        ).order_by(models.Timeslot.id)
    ).scalar_one()

    avail = models.Availability(
        teacher_id=sub_teacher.id,
        timeslot_id=timeslot.id,
        score=models.PreferenceLevel.NEUTRAL,
    )
    sync_db.add(avail)

    sync_db.commit()

    base_setup["substitute_teacher_id"] = sub_teacher.id
    base_setup["substitute_subject_id"] = subject2.id
    base_setup["substitute_module_id"] = module2.id
    return base_setup


class TestSubstitutionFromModal:
    def test_substitution_step_recommends_teachers(self, sync_db, substitution_setup):
        """T 5.1.1: Verificar que o endpoint de recomendações devolve professores elegíveis para o slot."""
        organization_id = substitution_setup["organization_id"]
        output_id = substitution_setup["schedule_output_id"]

        # Create occurrence
        occurrence, _ = occurrence_service.create_occurrence_from_block_sync(
            sync_db, organization_id, output_id
        )

        # Get recommendations
        recommendations = occurrence_service.get_substitute_recommendations_sync(
            sync_db, organization_id, occurrence.id
        )

        assert len(recommendations) >= 1
        rec = recommendations[0]
        assert rec.teacher_id == substitution_setup["substitute_teacher_id"]
        assert rec.subject_id == substitution_setup["substitute_subject_id"]

    def test_substitution_creation_from_modal(self, sync_db, substitution_setup):
        """T 5.1.2: Criar uma substituição via endpoint e verificar que a LessonOccurrence é criada corretamente com status=SUBSTITUTED."""
        organization_id = substitution_setup["organization_id"]
        output_id = substitution_setup["schedule_output_id"]
        user_id = substitution_setup["user_id"]

        # Step 1: Create occurrence
        occurrence, created = occurrence_service.create_occurrence_from_block_sync(
            sync_db, organization_id, output_id
        )
        assert created is True
        assert occurrence.status == models.LessonOccurrenceStatus.GIVEN

        # Step 2: Update to SUBSTITUTED
        payload = schemas.LessonOccurrenceUpdate(
            status=models.LessonOccurrenceStatus.SUBSTITUTED,
            substitute_teacher_id=substitution_setup["substitute_teacher_id"],
            substitute_subject_id=substitution_setup["substitute_subject_id"],
        )
        updated = occurrence_service.update_occurrence_sync(
            sync_db, occurrence.id, organization_id, payload, decided_by_user_id=user_id
        )

        assert updated.status == models.LessonOccurrenceStatus.SUBSTITUTED
        assert updated.substitute_teacher_id == substitution_setup["substitute_teacher_id"]
        assert updated.substitute_subject_id == substitution_setup["substitute_subject_id"]

    def test_cannot_create_substitution_if_existing_occurrence(self, sync_db, substitution_setup):
        """T 5.1.3: Tentar criar substituição num bloco que já tem ocorrência decidida.

        O backend reutiliza a ocorrência existente (idempotente), garantindo
        que não há duplicados e que o estado decidido é preservado.
        """
        organization_id = substitution_setup["organization_id"]
        output_id = substitution_setup["schedule_output_id"]
        user_id = substitution_setup["user_id"]

        # Create and decide occurrence as SUBSTITUTED
        occurrence, _ = occurrence_service.create_occurrence_from_block_sync(
            sync_db, organization_id, output_id
        )
        payload = schemas.LessonOccurrenceUpdate(
            status=models.LessonOccurrenceStatus.SUBSTITUTED,
            substitute_teacher_id=substitution_setup["substitute_teacher_id"],
            substitute_subject_id=substitution_setup["substitute_subject_id"],
        )
        occurrence_service.update_occurrence_sync(
            sync_db, occurrence.id, organization_id, payload, decided_by_user_id=user_id
        )

        # Try to create again — should reuse existing, not create duplicate
        existing, created_now = occurrence_service.create_occurrence_from_block_sync(
            sync_db, organization_id, output_id
        )
        assert created_now is False
        assert existing.id == occurrence.id
        assert existing.status == models.LessonOccurrenceStatus.SUBSTITUTED


class TestSummarySynchronization:
    def test_admin_can_update_teacher_summary(self, sync_db, base_setup):
        """T 5.2.1: Professor cria log com sumário → Admin atualiza o sumário → Verificar que o valor foi alterado."""
        organization_id = base_setup["organization_id"]
        output_id = base_setup["schedule_output_id"]
        teacher_user_id = base_setup["user_id"]

        # Teacher creates log
        payload = schemas.LessonLogCreate(
            status=models.LessonLogStatus.COMPLETED,
            summary="Sumário do professor",
            notes="Notas do professor",
        )
        llog = lesson_log_service.upsert_lesson_log_sync(
            sync_db, organization_id, teacher_user_id, output_id, payload
        )
        assert llog.summary == "Sumário do professor"

        # Admin updates log
        admin_payload = schemas.LessonLogCreate(
            status=models.LessonLogStatus.COMPLETED,
            summary="Sumário atualizado pelo admin",
            notes="Notas atualizadas pelo admin",
        )
        updated = lesson_log_service.upsert_lesson_log_sync(
            sync_db, organization_id, teacher_user_id, output_id, admin_payload
        )
        assert updated.summary == "Sumário atualizado pelo admin"
        assert updated.notes == "Notas atualizadas pelo admin"

    def test_summary_persists_after_status_change(self, sync_db, base_setup):
        """T 5.2.2: Alterar o estado de COMPLETED para OCCURRENCE e verificar que o sumário não é apagado."""
        organization_id = base_setup["organization_id"]
        output_id = base_setup["schedule_output_id"]
        user_id = base_setup["user_id"]

        # Create log as COMPLETED with summary
        payload = schemas.LessonLogCreate(
            status=models.LessonLogStatus.COMPLETED,
            summary="Sumário importante",
            notes="Notas importantes",
        )
        lesson_log_service.upsert_lesson_log_sync(
            sync_db, organization_id, user_id, output_id, payload
        )

        # Change to OCCURRENCE keeping same summary
        payload2 = schemas.LessonLogCreate(
            status=models.LessonLogStatus.OCCURRENCE,
            summary="Sumário importante",
            notes="Notas importantes",
        )
        updated = lesson_log_service.upsert_lesson_log_sync(
            sync_db, organization_id, user_id, output_id, payload2
        )
        assert updated.status == models.LessonLogStatus.OCCURRENCE
        assert updated.summary == "Sumário importante"
        assert updated.notes == "Notas importantes"


class TestAdminOpensLessonLogModal:
    def test_admin_opens_lesson_log_modal_for_past_slot(self, sync_db, base_setup):
        """T 5.3.1: Verificar que o endpoint devolve os campos lesson_log_* corretos para o admin."""
        from app.services import schedule_service
        organization_id = base_setup["organization_id"]
        class_id = base_setup["class_id"]
        week_start = base_setup["date"] - timedelta(days=base_setup["date"].weekday())

        # Create a lesson log
        payload = schemas.LessonLogCreate(
            status=models.LessonLogStatus.COMPLETED,
            summary="Teste de integração",
            notes="Notas de teste",
        )
        lesson_log_service.upsert_lesson_log_sync(
            sync_db, organization_id, base_setup["user_id"], base_setup["schedule_output_id"], payload
        )

        # Fetch week schedule
        slots = schedule_service.get_week_schedule_sync(
            sync_db, organization_id, week_start, class_id=class_id
        )
        assert len(slots) == 1
        slot = slots[0]
        assert slot["lesson_log_status"] == "COMPLETED"
        assert slot["lesson_log_summary"] == "Teste de integração"
        assert slot["lesson_log_notes"] == "Notas de teste"
        assert slot["is_past"] is True


class TestWeekScheduleTimesheetStatus:
    def test_week_schedule_includes_timesheet_status(self, sync_db, base_setup):
        """T 6.1.1: Submeter timesheet → endpoint deve devolver week_timesheet_status=SUBMITTED."""
        from app.services import schedule_service
        organization_id = base_setup["organization_id"]
        teacher_id = base_setup["teacher_id"]
        class_id = base_setup["class_id"]
        week_start = base_setup["date"] - timedelta(days=base_setup["date"].weekday())

        # Pre-register the lesson log so submission is allowed
        lesson_log_service.upsert_lesson_log_sync(
            sync_db, organization_id, base_setup["user_id"], base_setup["schedule_output_id"],
            schemas.LessonLogCreate(status=models.LessonLogStatus.COMPLETED, summary="Aula", notes="")
        )

        # Submit timesheet via service
        _ = timesheet_service.submit_timesheet_sync(
            sync_db, organization_id, teacher_id, week_start
        )
        assert timesheet.status == models.TimesheetStatus.SUBMITTED

        # Fetch week schedule
        slots = schedule_service.get_week_schedule_sync(
            sync_db, organization_id, week_start, class_id=class_id
        )
        assert len(slots) == 1
        slot = slots[0]
        assert slot["week_timesheet_status"] == "SUBMITTED"
        assert slot["timesheet_id"] == timesheet.id

    def test_week_schedule_different_teachers_different_statuses(self, sync_db, base_setup):
        """T 6.1.2: Dois professores na mesma semana com estados diferentes.
        Cada slot deve refletir o estado correto do seu professor."""
        from app.services import schedule_service
        organization_id = base_setup["organization_id"]
        teacher1_id = base_setup["teacher_id"]
        class_id = base_setup["class_id"]
        week_start = base_setup["date"] - timedelta(days=base_setup["date"].weekday())

        # Pre-register lesson log for teacher1 so submission is allowed
        lesson_log_service.upsert_lesson_log_sync(
            sync_db, organization_id, base_setup["user_id"], base_setup["schedule_output_id"],
            schemas.LessonLogCreate(status=models.LessonLogStatus.COMPLETED, summary="Aula T1", notes="")
        )

        # Create second teacher with lesson in same class/week
        teacher2 = models.Teacher(name="Prof. Segundo", organization_id=organization_id)
        sync_db.add(teacher2)
        sync_db.flush()

        # Get existing timeslot and subject
        timeslot = sync_db.execute(
            select(models.Timeslot).where(models.Timeslot.organization_id == organization_id)
        ).scalar_one()
        subject = sync_db.execute(
            select(models.Subject).where(models.Subject.organization_id == organization_id)
        ).scalar_one()
        room = sync_db.execute(
            select(models.Room).where(models.Room.organization_id == organization_id)
        ).scalar_one()

        lesson2 = models.Lesson(
            organization_id=organization_id,
            class_id=class_id,
            subject_id=subject.id,
            teacher_id=teacher2.id,
        )
        sync_db.add(lesson2)
        sync_db.flush()

        output2 = models.ScheduleOutput(
            organization_id=organization_id,
            lesson_id=lesson2.id,
            timeslot_id=timeslot.id,
            room_id=room.id,
            generation_id="test-gen-2",
            date=base_setup["date"],
            is_draft=False,
        )
        sync_db.add(output2)
        sync_db.commit()

        # Submit timesheet for teacher1 only
        timesheet1 = timesheet_service.submit_timesheet_sync(
            sync_db, organization_id, teacher1_id, week_start
        )
        assert timesheet1.status == models.TimesheetStatus.SUBMITTED

        # Fetch week schedule by class (gets both teachers)
        slots = schedule_service.get_week_schedule_sync(
            sync_db, organization_id, week_start, class_id=class_id
        )
        assert len(slots) == 2

        statuses_by_teacher = {
            s["teacher"]["id"]: (s["week_timesheet_status"], s["timesheet_id"])
            for s in slots
        }
        assert statuses_by_teacher[teacher1_id] == ("SUBMITTED", timesheet1.id)
        assert statuses_by_teacher[teacher2.id] == ("OPEN", None)

    def test_week_grid_returns_timesheet_summary(self, sync_db, base_setup):
        """T 6.3.1: Todos os slots do mesmo professor na mesma semana partilham o mesmo week_timesheet_status."""
        from app.services import schedule_service
        organization_id = base_setup["organization_id"]
        teacher_id = base_setup["teacher_id"]
        week_start = base_setup["date"] - timedelta(days=base_setup["date"].weekday())

        # Pre-register lesson log for existing slot
        lesson_log_service.upsert_lesson_log_sync(
            sync_db, organization_id, base_setup["user_id"], base_setup["schedule_output_id"],
            schemas.LessonLogCreate(status=models.LessonLogStatus.COMPLETED, summary="Aula 1", notes="")
        )

        # Create a second timeslot and schedule output for the same teacher+lesson
        room = sync_db.execute(
            select(models.Room).where(models.Room.organization_id == organization_id)
        ).scalar_one()
        timeslot2 = models.Timeslot(
            day_of_week=1,
            start_time=time(11, 0),
            end_time=time(13, 0),
            organization_id=organization_id,
        )
        sync_db.add(timeslot2)
        sync_db.flush()

        lesson = sync_db.execute(
            select(models.Lesson).where(
                models.Lesson.organization_id == organization_id,
                models.Lesson.teacher_id == teacher_id,
            )
        ).scalar_one()

        output2 = models.ScheduleOutput(
            organization_id=organization_id,
            lesson_id=lesson.id,
            timeslot_id=timeslot2.id,
            room_id=room.id,
            generation_id="test-gen-3",
            date=base_setup["date"],
            is_draft=False,
        )
        sync_db.add(output2)
        sync_db.flush()

        # Pre-register lesson log for second slot too
        lesson_log_service.upsert_lesson_log_sync(
            sync_db, organization_id, base_setup["user_id"], output2.id,
            schemas.LessonLogCreate(status=models.LessonLogStatus.COMPLETED, summary="Aula 2", notes="")
        )

        # Submit timesheet
        _ = timesheet_service.submit_timesheet_sync(
            sync_db, organization_id, teacher_id, week_start
        )

        # Fetch by teacher (gets both slots)
        slots = schedule_service.get_week_schedule_sync(
            sync_db, organization_id, week_start, teacher_id=teacher_id
        )
        assert len(slots) == 2
        for slot in slots:
            assert slot["week_timesheet_status"] == "SUBMITTED"
            assert slot["timesheet_id"] == timesheet.id


class TestTimesheetReopen:
    def test_admin_reopens_submitted_week_from_modal(self, sync_db, base_setup):
        """T 6.2.1: Submeter semana → Admin reabre via API → Verificar que o estado é OPEN."""
        organization_id = base_setup["organization_id"]
        teacher_id = base_setup["teacher_id"]
        week_start = base_setup["date"] - timedelta(days=base_setup["date"].weekday())

        # Pre-register lesson log so submission is allowed
        lesson_log_service.upsert_lesson_log_sync(
            sync_db, organization_id, base_setup["user_id"], base_setup["schedule_output_id"],
            schemas.LessonLogCreate(status=models.LessonLogStatus.COMPLETED, summary="Aula", notes="")
        )

        # Submit
        _ = timesheet_service.submit_timesheet_sync(
            sync_db, organization_id, teacher_id, week_start
        )
        assert timesheet.status == models.TimesheetStatus.SUBMITTED

        # Reopen by admin
        reopened = timesheet_service.update_timesheet_status_sync(
            sync_db, organization_id, timesheet.id, models.TimesheetStatus.OPEN, base_setup["user_id"]
        )
        assert reopened["status"] == models.TimesheetStatus.OPEN

    def test_reopen_preserves_lesson_logs(self, sync_db, base_setup):
        """T 6.2.3: Reabrir a semana e verificar que os LessonLogs existentes não são apagados."""
        organization_id = base_setup["organization_id"]
        teacher_id = base_setup["teacher_id"]
        output_id = base_setup["schedule_output_id"]
        week_start = base_setup["date"] - timedelta(days=base_setup["date"].weekday())

        # Create lesson log
        payload = schemas.LessonLogCreate(
            status=models.LessonLogStatus.COMPLETED,
            summary="Aula antes do fecho",
            notes="",
        )
        lesson_log_service.upsert_lesson_log_sync(
            sync_db, organization_id, base_setup["user_id"], output_id, payload
        )

        # Submit and approve
        _ = timesheet_service.submit_timesheet_sync(
            sync_db, organization_id, teacher_id, week_start
        )
        timesheet_service.update_timesheet_status_sync(
            sync_db, organization_id, timesheet.id, models.TimesheetStatus.APPROVED, base_setup["user_id"]
        )

        # Reopen
        timesheet_service.update_timesheet_status_sync(
            sync_db, organization_id, timesheet.id, models.TimesheetStatus.OPEN, base_setup["user_id"]
        )

        # Verify lesson log still exists
        llog = sync_db.execute(
            select(models.LessonLog).where(models.LessonLog.schedule_output_id == output_id)
        ).scalar_one()
        assert llog.status == models.LessonLogStatus.COMPLETED
        assert llog.summary == "Aula antes do fecho"


# ---------------------------------------------------------------------------
# Endpoint-level permission test (async)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestTimesheetReopenPermissions:
    async def test_teacher_cannot_reopen_week(self, async_client, db_session):
        """T 6.2.2: Professor tenta chamar o endpoint de reabertura → HTTP 403."""
        # Create org
        org = models.Organization(name="Test Org Reopen", plan_status="active")
        db_session.add(org)
        await db_session.flush()

        # Create teacher
        teacher = models.Teacher(name="Prof. Reopen", organization_id=org.id)
        db_session.add(teacher)
        await db_session.flush()

        # Create teacher user
        teacher_cid = "teacher_reopen_001"
        teacher_user = models.User(
            email="teacher_reopen@test.com",
            clerk_user_id=teacher_cid,
            is_active=True,
            role=models.UserRole.teacher,
            organization_id=org.id,
            teacher_id=teacher.id,
        )
        db_session.add(teacher_user)
        await db_session.flush()

        # Create timesheet
        week_start = date.today() - timedelta(days=date.today().weekday())
        _ = models.TeacherWeeklyTimesheet(
            organization_id=org.id,
            teacher_id=teacher.id,
            week_start_date=week_start,
            status=models.TimesheetStatus.SUBMITTED,
        )
        db_session.add(timesheet)
        await db_session.commit()

        headers = {"Authorization": f"Bearer test_{teacher_cid}"}

        with patch("app.api.deps.get_clerk_payload", return_value=mock_clerk_payload(teacher_cid, None, "teacher")):
            response = await async_client.patch(
                f"/api/v1/timesheets/{timesheet.id}/status",
                json={"status": "OPEN"},
                headers=headers,
            )
        assert response.status_code == 403
        assert "Apenas admins" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Fase 7.3 — Slot counts in timesheet list
# ---------------------------------------------------------------------------
@pytest.fixture
def slot_counts_setup(sync_db, base_setup):
    """Extende base_setup com múltiplos slots na mesma semana para testar contagens."""
    organization_id = base_setup["organization_id"]
    teacher_id = base_setup["teacher_id"]
    user_id = base_setup["user_id"]
    week_start = base_setup["date"] - timedelta(days=base_setup["date"].weekday())

    # Get existing room
    room = sync_db.execute(
        select(models.Room).where(models.Room.organization_id == organization_id)
    ).scalar_one()

    # Create 2 more timeslots
    ts2 = models.Timeslot(day_of_week=1, start_time=time(11, 0), end_time=time(13, 0), organization_id=organization_id)
    ts3 = models.Timeslot(day_of_week=2, start_time=time(14, 0), end_time=time(16, 0), organization_id=organization_id)
    sync_db.add(ts2)
    sync_db.add(ts3)
    sync_db.flush()

    # Get existing lesson
    lesson = sync_db.execute(
        select(models.Lesson).where(models.Lesson.organization_id == organization_id, models.Lesson.teacher_id == teacher_id)
    ).scalar_one()

    # Slot 2 — COMPLETED
    out2 = models.ScheduleOutput(
        organization_id=organization_id, lesson_id=lesson.id, timeslot_id=ts2.id,
        room_id=room.id, generation_id="test-gen-2", date=base_setup["date"], is_draft=False,
    )
    sync_db.add(out2)
    sync_db.flush()
    lesson_log_service.upsert_lesson_log_sync(
        sync_db, organization_id, user_id, out2.id,
        schemas.LessonLogCreate(status=models.LessonLogStatus.COMPLETED, summary="Aula 2", notes="")
    )

    # Slot 3 — OCCURRENCE
    out3 = models.ScheduleOutput(
        organization_id=organization_id, lesson_id=lesson.id, timeslot_id=ts3.id,
        room_id=room.id, generation_id="test-gen-3", date=base_setup["date"], is_draft=False,
    )
    sync_db.add(out3)
    sync_db.flush()
    lesson_log_service.upsert_lesson_log_sync(
        sync_db, organization_id, user_id, out3.id,
        schemas.LessonLogCreate(status=models.LessonLogStatus.OCCURRENCE, summary="Falta", notes="")
    )

    # Slot 4 — DRAFT (should NOT be counted)
    out4 = models.ScheduleOutput(
        organization_id=organization_id, lesson_id=lesson.id, timeslot_id=ts2.id,
        room_id=room.id, generation_id="test-gen-4", date=base_setup["date"], is_draft=True,
    )
    sync_db.add(out4)
    sync_db.commit()

    base_setup["output_2_id"] = out2.id
    base_setup["output_3_id"] = out3.id
    base_setup["output_4_id"] = out4.id
    base_setup["week_start"] = week_start
    return base_setup


class TestTimesheetListSlotCounts:
    def test_timesheets_list_with_slot_counts(self, sync_db, slot_counts_setup):
        """T 7.3.1: Criar aulas, registar algumas, chamar list_timesheets_sync e verificar as contagens."""
        organization_id = slot_counts_setup["organization_id"]
        teacher_id = slot_counts_setup["teacher_id"]
        week_start = slot_counts_setup["week_start"]

        # Create timesheet so it appears in the list
        _ = timesheet_service.get_or_create_timesheet_sync(
            sync_db, organization_id, teacher_id, week_start
        )

        results = timesheet_service.list_timesheets_sync(
            sync_db, organization_id, week_start_date=week_start
        )
        assert len(results) == 1
        result = results[0]
        assert result["teacher_id"] == teacher_id
        # 3 non-draft slots (base + out2 + out3), out4 is draft and excluded
        assert result["total_slots"] == 3
        # 2 registered (COMPLETED + OCCURRENCE); base_setup slot has no log
        assert result["registered_slots"] == 2
        # 1 completed (out2); base_setup has no log, out3 is OCCURRENCE
        assert result["completed_slots"] == 1
        assert result["occurrence_slots"] == 1

    def test_timesheets_excludes_draft_slots(self, sync_db, slot_counts_setup):
        """T 7.3.2: Verificar que blocos draft não são contabilizados nas contagens."""
        organization_id = slot_counts_setup["organization_id"]
        teacher_id = slot_counts_setup["teacher_id"]
        week_start = slot_counts_setup["week_start"]

        timesheet_service.get_or_create_timesheet_sync(
            sync_db, organization_id, teacher_id, week_start
        )

        results = timesheet_service.list_timesheets_sync(
            sync_db, organization_id, week_start_date=week_start
        )
        result = results[0]
        # The draft output (out4) uses the same timeslot as out2 but should not count
        assert result["total_slots"] == 3


# ---------------------------------------------------------------------------
# Fase 7.2 — Approval / Reopen via endpoint
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestTimesheetApprovalEndpoints:
    async def test_approve_from_timesheets_detail(self, async_client, db_session):
        """T 7.2.1: Admin aprova uma timesheet SUBMITTED via endpoint → estado APPROVED."""
        org = models.Organization(name="Test Org Approve", plan_status="active")
        db_session.add(org)
        await db_session.flush()

        teacher = models.Teacher(name="Prof. Approve", organization_id=org.id)
        db_session.add(teacher)
        await db_session.flush()

        admin_cid = "admin_approve_001"
        admin_user = models.User(
            email="admin_approve@test.com",
            clerk_user_id=admin_cid,
            is_active=True,
            role=models.UserRole.admin,
            organization_id=org.id,
        )
        db_session.add(admin_user)
        await db_session.flush()

        week_start = date.today() - timedelta(days=date.today().weekday())
        _ = models.TeacherWeeklyTimesheet(
            organization_id=org.id,
            teacher_id=teacher.id,
            week_start_date=week_start,
            status=models.TimesheetStatus.SUBMITTED,
            submitted_at=datetime.now(timezone.utc),
        )
        db_session.add(timesheet)
        await db_session.commit()

        headers = {"Authorization": f"Bearer test_{admin_cid}"}

        with patch("app.api.deps.get_clerk_payload", return_value=mock_clerk_payload(admin_cid, None, "admin")):
            response = await async_client.patch(
                f"/api/v1/timesheets/{timesheet.id}/status",
                json={"status": "APPROVED"},
                headers=headers,
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "APPROVED"
        assert data["approved_at"] is not None

    async def test_reopen_from_timesheets_detail(self, async_client, db_session):
        """T 7.2.2: Admin reabre uma timesheet APPROVED via endpoint → estado OPEN."""
        org = models.Organization(name="Test Org Reopen2", plan_status="active")
        db_session.add(org)
        await db_session.flush()

        teacher = models.Teacher(name="Prof. Reopen2", organization_id=org.id)
        db_session.add(teacher)
        await db_session.flush()

        admin_cid = "admin_reopen2_001"
        admin_user = models.User(
            email="admin_reopen2@test.com",
            clerk_user_id=admin_cid,
            is_active=True,
            role=models.UserRole.admin,
            organization_id=org.id,
        )
        db_session.add(admin_user)
        await db_session.flush()

        week_start = date.today() - timedelta(days=date.today().weekday())
        _ = models.TeacherWeeklyTimesheet(
            organization_id=org.id,
            teacher_id=teacher.id,
            week_start_date=week_start,
            status=models.TimesheetStatus.APPROVED,
            approved_at=datetime.now(timezone.utc),
        )
        db_session.add(timesheet)
        await db_session.commit()

        headers = {"Authorization": f"Bearer test_{admin_cid}"}

        with patch("app.api.deps.get_clerk_payload", return_value=mock_clerk_payload(admin_cid, None, "admin")):
            response = await async_client.patch(
                f"/api/v1/timesheets/{timesheet.id}/status",
                json={"status": "OPEN"},
                headers=headers,
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "OPEN"
        assert data["approved_at"] is None
        assert data["submitted_at"] is None


# ---------------------------------------------------------------------------
# Fase 7.1 — Endpoint enriched list
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestTimesheetsListEndpoint:
    async def test_timesheets_list_endpoint_returns_teacher_summary(self, async_client, db_session):
        """T 7.1.1: Verificar que o endpoint devolve a lista de professores com contagens."""
        org = models.Organization(name="Test Org List", plan_status="active")
        db_session.add(org)
        await db_session.flush()

        teacher = models.Teacher(name="Prof. List", organization_id=org.id)
        db_session.add(teacher)
        await db_session.flush()

        admin_cid = "admin_list_001"
        admin_user = models.User(
            email="admin_list@test.com",
            clerk_user_id=admin_cid,
            is_active=True,
            role=models.UserRole.admin,
            organization_id=org.id,
        )
        db_session.add(admin_user)
        await db_session.flush()

        week_start = date.today() - timedelta(days=date.today().weekday())
        _ = models.TeacherWeeklyTimesheet(
            organization_id=org.id,
            teacher_id=teacher.id,
            week_start_date=week_start,
            status=models.TimesheetStatus.SUBMITTED,
        )
        db_session.add(timesheet)
        await db_session.commit()

        headers = {"Authorization": f"Bearer test_{admin_cid}"}

        with patch("app.api.deps.get_clerk_payload", return_value=mock_clerk_payload(admin_cid, None, "admin")):
            response = await async_client.get(
                f"/api/v1/timesheets/?week_start_date={week_start.isoformat()}",
                headers=headers,
            )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["teacher_name"] == "Prof. List"
        assert data[0]["status"] == "SUBMITTED"
        assert "total_slots" in data[0]
        assert "registered_slots" in data[0]

    async def test_timesheets_detail_endpoint_returns_week_slots(self, async_client, db_session):
        """T 7.1.2: Verificar que o endpoint devolve os slots do professor para a semana."""
        org = models.Organization(name="Test Org Detail", plan_status="active")
        db_session.add(org)
        await db_session.flush()

        teacher = models.Teacher(name="Prof. Detail", organization_id=org.id)
        db_session.add(teacher)
        await db_session.flush()

        # Create timeslot, room, class, subject
        room = models.Room(name="Sala D", capacity=30, type=models.RoomType.normal, organization_id=org.id)
        db_session.add(room)
        subject = models.Subject(name="Disc D", organization_id=org.id, required_room_type=models.RoomType.normal)
        db_session.add(subject)
        course = models.Course(name="Curso D", abbreviation="CD", organization_id=org.id)
        db_session.add(course)
        await db_session.flush()
        class_ = models.Class(name="10D", size=20, start_year=2024, end_year=2027, grade_level=10, course_id=course.id, organization_id=org.id)
        db_session.add(class_)
        await db_session.flush()
        ts = models.Timeslot(day_of_week=0, start_time=time(9, 0), end_time=time(11, 0), organization_id=org.id)
        db_session.add(ts)
        await db_session.flush()

        lesson = models.Lesson(organization_id=org.id, class_id=class_.id, subject_id=subject.id, teacher_id=teacher.id)
        db_session.add(lesson)
        await db_session.flush()

        yesterday = date.today() - timedelta(days=1)
        output = models.ScheduleOutput(
            organization_id=org.id, lesson_id=lesson.id, timeslot_id=ts.id,
            room_id=room.id, generation_id="test-gen-d", date=yesterday, is_draft=False,
        )
        db_session.add(output)
        await db_session.flush()

        # Create log
        llog = models.LessonLog(
            organization_id=org.id, schedule_output_id=output.id,
            status=models.LessonLogStatus.COMPLETED, summary="Aula D",
        )
        db_session.add(llog)
        await db_session.commit()

        admin_cid = "admin_detail_001"
        admin_user = models.User(
            email="admin_detail@test.com",
            clerk_user_id=admin_cid,
            is_active=True,
            role=models.UserRole.admin,
            organization_id=org.id,
        )
        db_session.add(admin_user)
        await db_session.commit()

        headers = {"Authorization": f"Bearer test_{admin_cid}"}

        week_start = yesterday - timedelta(days=yesterday.weekday())
        with patch("app.api.deps.get_clerk_payload", return_value=mock_clerk_payload(admin_cid, None, "admin")):
            response = await async_client.get(
                f"/api/v1/schedule/week?week_start={week_start.isoformat()}&teacher_id={teacher.id}",
                headers=headers,
            )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["lesson_log_status"] == "COMPLETED"
        assert data[0]["lesson_log_summary"] == "Aula D"


# ---------------------------------------------------------------------------
# Testes em falta — Fase 5 (Correções de Bugs)
# ---------------------------------------------------------------------------
class TestSoftResetCompleteness:
    @pytest.mark.asyncio
    async def test_soft_reset_resets_hours_debt_and_is_completed(self, sync_db, base_setup):
        """T-1: Soft-reset deve limpar hours_debt e is_completed além de hours_completed."""
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
        from sqlalchemy.pool import NullPool
        from app.db.database import ASYNC_DB_URL
        organization_id = base_setup["organization_id"]

        # Pre-populate ClassProgress with debt and completed flag
        progress = sync_db.execute(
            select(models.ClassProgress).where(
                models.ClassProgress.class_id == base_setup["class_id"],
                models.ClassProgress.module_id == base_setup["module_id"]
            )
        ).scalar_one()
        progress.hours_debt = 3.5
        progress.is_completed = True
        sync_db.commit()

        # Create a fresh async engine/session bound to the current event loop
        engine = create_async_engine(ASYNC_DB_URL, poolclass=NullPool)
        session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
        async with session_factory() as async_session:
            await settings_service.soft_reset_year(async_session, organization_id)

            result = await async_session.execute(
                select(models.ClassProgress).where(
                    models.ClassProgress.class_id == base_setup["class_id"],
                    models.ClassProgress.module_id == base_setup["module_id"]
                )
            )
            progress_after = result.scalar_one()

        await engine.dispose()
        assert progress_after.hours_completed == 0.0
        assert progress_after.hours_debt == 0.0
        assert progress_after.is_completed is False


class TestClassProgressReversal:
    def test_completed_to_pending_reverses_class_progress(self, sync_db, base_setup):
        """T-2: Mudar de COMPLETED para PENDING deve reverter as horas contabilizadas."""
        organization_id = base_setup["organization_id"]
        output_id = base_setup["schedule_output_id"]
        user_id = base_setup["user_id"]

        # Step 1: COMPLETED increments hours
        payload = schemas.LessonLogCreate(
            status=models.LessonLogStatus.COMPLETED,
            summary="Aula dada",
            notes="",
        )
        lesson_log_service.upsert_lesson_log_sync(
            sync_db, organization_id, user_id, output_id, payload
        )

        progress = sync_db.execute(
            select(models.ClassProgress).where(
                models.ClassProgress.class_id == base_setup["class_id"],
                models.ClassProgress.module_id == base_setup["module_id"]
            )
        ).scalar_one()
        assert progress.hours_completed == 7.0  # 5.0 base + 2.0

        # Step 2: PENDING reverts hours
        payload2 = schemas.LessonLogCreate(
            status=models.LessonLogStatus.PENDING,
            summary="Aula dada",
            notes="",
        )
        lesson_log_service.upsert_lesson_log_sync(
            sync_db, organization_id, user_id, output_id, payload2
        )

        progress_after = sync_db.execute(
            select(models.ClassProgress).where(
                models.ClassProgress.class_id == base_setup["class_id"],
                models.ClassProgress.module_id == base_setup["module_id"]
            )
        ).scalar_one()
        assert progress_after.hours_completed == 5.0  # back to base


class TestTimesheetStateTransitions:
    def test_timesheet_invalid_state_transition_rejected(self, sync_db, base_setup):
        """T-3: OPEN → APPROVED direto deve ser rejeitado (HTTP 400)."""
        organization_id = base_setup["organization_id"]
        teacher_id = base_setup["teacher_id"]
        week_start = base_setup["date"] - timedelta(days=base_setup["date"].weekday())

        # Create timesheet in OPEN state (default)
        _ = timesheet_service.get_or_create_timesheet_sync(
            sync_db, organization_id, teacher_id, week_start
        )
        assert timesheet.status == models.TimesheetStatus.OPEN

        # Attempt illegal transition OPEN → APPROVED
        from app.core.exceptions import DomainError
        with pytest.raises(DomainError) as exc:
            timesheet_service.update_timesheet_status_sync(
                sync_db, organization_id, timesheet.id,
                models.TimesheetStatus.APPROVED, base_setup["user_id"]
            )
        assert exc.value.status_code == 400
        assert "Transição de estado inválida" in exc.value.message


class TestAutoConfirmDaily:
    def test_auto_confirm_daily_sync(self, sync_db, base_setup):
        """T-4: Cron de auto-confirm deve criar ocorrências GIVEN e contabilizar horas."""
        organization_id = base_setup["organization_id"]
        output_id = base_setup["schedule_output_id"]
        target_date = base_setup["date"]

        # Ensure no manual occurrence exists
        existing = sync_db.execute(
            select(models.LessonOccurrence).where(
                models.LessonOccurrence.schedule_output_id == output_id
            )
        ).scalar_one_or_none()
        assert existing is None

        # Run auto-confirm
        created = occurrence_service.auto_confirm_daily_sync(sync_db, organization_id, target_date)
        assert created == 1

        # Verify occurrence was created as GIVEN
        occurrence = sync_db.execute(
            select(models.LessonOccurrence).where(
                models.LessonOccurrence.schedule_output_id == output_id
            )
        ).scalar_one()
        assert occurrence.status == models.LessonOccurrenceStatus.GIVEN
        assert occurrence.decided_at is not None

        # Verify ClassProgress was incremented
        progress = sync_db.execute(
            select(models.ClassProgress).where(
                models.ClassProgress.class_id == base_setup["class_id"],
                models.ClassProgress.module_id == base_setup["module_id"]
            )
        ).scalar_one()
        assert progress.hours_completed == 7.0  # 5.0 base + 2.0

    def test_manual_occurrence_then_auto_confirm_skips(self, sync_db, base_setup):
        """T-6: Ocorrência manual (decided_at=None) + auto-confirm não deve duplicar."""
        organization_id = base_setup["organization_id"]
        output_id = base_setup["schedule_output_id"]
        target_date = base_setup["date"]
        user_id = base_setup["user_id"]

        # Create manual occurrence (undecided — decided_at=None)
        occurrence, _ = occurrence_service.create_occurrence_from_block_sync(
            sync_db, organization_id, output_id
        )
        assert occurrence.decided_at is None

        # Run auto-confirm — should skip because occurrence already exists
        created = occurrence_service.auto_confirm_daily_sync(sync_db, organization_id, target_date)
        assert created == 0  # skipped

        # Verify original occurrence is untouched
        occurrence_after = sync_db.execute(
            select(models.LessonOccurrence).where(
                models.LessonOccurrence.schedule_output_id == output_id
            )
        ).scalar_one()
        assert occurrence_after.id == occurrence.id
        assert occurrence_after.decided_at is None  # still undecided


class TestAvailableSubstitutes:
    def test_get_available_substitutes_sync(self, sync_db, substitution_setup):
        """T-5: Lista de substitutos disponíveis deve excluir professor planejado."""
        organization_id = substitution_setup["organization_id"]
        output_id = substitution_setup["schedule_output_id"]
        target_date = substitution_setup["date"]

        # Get timeslot_id from the schedule output
        output = sync_db.execute(
            select(models.ScheduleOutput).where(models.ScheduleOutput.id == output_id)
        ).scalar_one()

        substitutes = occurrence_service.get_available_substitutes_sync(
            sync_db, organization_id, output.timeslot_id, target_date
        )
        # Should return at least the substitute teacher from substitution_setup
        teacher_ids = [s.teacher_id for s in substitutes]
        assert substitution_setup["substitute_teacher_id"] in teacher_ids


class TestOccurrenceFilters:
    def test_list_occurrences_with_filters(self, sync_db, base_setup):
        """T-8: Filtros class_id, date_from, date_to devem funcionar."""
        organization_id = base_setup["organization_id"]
        output_id = base_setup["schedule_output_id"]
        target_date = base_setup["date"]
        user_id = base_setup["user_id"]

        # Create occurrence
        occurrence, _ = occurrence_service.create_occurrence_from_block_sync(
            sync_db, organization_id, output_id
        )
        # Decide it
        payload = schemas.LessonOccurrenceUpdate(
            status=models.LessonOccurrenceStatus.GIVEN,
        )
        occurrence_service.update_occurrence_sync(
            sync_db, occurrence.id, organization_id, payload, decided_by_user_id=user_id
        )

        # No filters — should find it
        all_occurrences = occurrence_service.list_occurrences_sync(sync_db, organization_id)
        assert len(all_occurrences) == 1

        # Filter by date_from/date_to that include the occurrence
        filtered = occurrence_service.list_occurrences_sync(
            sync_db, organization_id, date_from=target_date, date_to=target_date
        )
        assert len(filtered) == 1

        # Filter by date_from/date_to that exclude the occurrence
        empty = occurrence_service.list_occurrences_sync(
            sync_db, organization_id, date_from=target_date + timedelta(days=1),
            date_to=target_date + timedelta(days=2)
        )
        assert len(empty) == 0


class TestWeekStartValidation:
    def test_week_start_not_monday_accepted(self, sync_db, base_setup):
        """T-9: week_start que não é Segunda-feira é aceite (comportamento atual documentado)."""
        from app.services import schedule_service
        organization_id = base_setup["organization_id"]
        teacher_id = base_setup["teacher_id"]

        # Update the schedule_output's date to be inside the query window
        wednesday = base_setup["date"] - timedelta(days=base_setup["date"].weekday()) + timedelta(days=2)
        output = sync_db.get(models.ScheduleOutput, base_setup["schedule_output_id"])
        output.date = wednesday
        sync_db.flush()

        slots = schedule_service.get_week_schedule_sync(
            sync_db, organization_id, wednesday, teacher_id=teacher_id
        )
        # Should still return the slot (query window is Wed-Tue)
        assert len(slots) == 1


class TestTimezoneBoundary:
    def test_timezone_boundary_blocking(self, sync_db, base_setup):
        """T-10: Blocos no limite de timezone devem ser tratados corretamente com UTC."""
        organization_id = base_setup["organization_id"]
        output_id = base_setup["schedule_output_id"]
        user_id = base_setup["user_id"]

        # The existing slot is from yesterday (base_setup date), so it's already in the past.
        # Attempting to register should succeed because it's past.
        payload = schemas.LessonLogCreate(
            status=models.LessonLogStatus.COMPLETED,
            summary="Teste timezone",
            notes="",
        )
        llog = lesson_log_service.upsert_lesson_log_sync(
            sync_db, organization_id, user_id, output_id, payload
        )
        assert llog.status == models.LessonLogStatus.COMPLETED

        # Create a future slot for tomorrow to verify blocking
        from datetime import timezone
        tomorrow = date.today() + timedelta(days=1)
        room = sync_db.execute(
            select(models.Room).where(models.Room.organization_id == organization_id)
        ).scalar_one()
        timeslot = sync_db.execute(
            select(models.Timeslot).where(models.Timeslot.organization_id == organization_id)
        ).scalar_one()
        lesson = sync_db.execute(
            select(models.Lesson).where(models.Lesson.organization_id == organization_id)
        ).scalar_one()

        future_output = models.ScheduleOutput(
            organization_id=organization_id,
            lesson_id=lesson.id,
            timeslot_id=timeslot.id,
            room_id=room.id,
            generation_id="test-future",
            date=tomorrow,
            is_draft=False,
        )
        sync_db.add(future_output)
        sync_db.commit()

        from app.core.exceptions import DomainError
        with pytest.raises(DomainError) as exc:
            lesson_log_service.upsert_lesson_log_sync(
                sync_db, organization_id, user_id, future_output.id, payload
            )
        assert exc.value.status_code == 400
        assert "ainda não terminou" in exc.value.message

