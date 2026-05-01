import pytest
import pytest_asyncio
from datetime import date, datetime, time, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.database import ASYNC_DB_URL
from app import models, schemas
from app.services import lesson_log_service, timesheet_service, settings_service, occurrence_service
from app.core.security import hash_password

SYNC_TEST_URL = ASYNC_DB_URL.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
sync_test_engine = create_engine(SYNC_TEST_URL, echo=False)
SyncTestSession = sessionmaker(bind=sync_test_engine, autocommit=False, autoflush=False)

def _ensure_sync_tables():
    from app.db.database import Base
    from sqlalchemy import inspect
    inspector = inspect(sync_test_engine)
    if inspector.has_table("organization"):
        return
    # Async tests dropped tables; recreate only tables (not enums) to avoid conflicts
    for table in Base.metadata.sorted_tables:
        try:
            table.create(sync_test_engine, checkfirst=True)
        except Exception:
            pass


@pytest.fixture
def sync_db():
    _ensure_sync_tables()
    db = SyncTestSession()
    db.begin_nested()  # Create a savepoint so commits inside tests are isolated
    try:
        yield db
    finally:
        db.rollback()  # Rollback the outer transaction to clean up
        db.close()

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
        hashed_password=hash_password("pass123"),
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
        "org_id": org.id,
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
        org_id = base_setup["org_id"]
        output_id = base_setup["schedule_output_id"]
        
        # Act
        payload = schemas.LessonLogCreate(
            status=models.LessonLogStatus.COMPLETED,
            summary="Introdução a Python",
            notes=""
        )
        llog = lesson_log_service.upsert_lesson_log_sync(
            sync_db, org_id, base_setup["user_id"], output_id, payload
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
        org_id = base_setup["org_id"]
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
            sync_db, org_id, base_setup["user_id"], output_id, payload
        )
        
        # Submeter semana
        timesheet = timesheet_service.submit_timesheet_sync(
            sync_db, org_id, teacher_id, week_start
        )
        assert timesheet.status == models.TimesheetStatus.SUBMITTED
        
        # Alterar aula deve falhar
        import fastapi
        with pytest.raises(fastapi.HTTPException) as exc:
            lesson_log_service.upsert_lesson_log_sync(
                sync_db, org_id, base_setup["user_id"], output_id, payload
            )
        assert exc.value.status_code == 400
        assert "Esta semana já foi submetida" in str(exc.value.detail)
        
        # Aprovar semana
        timesheet_service.update_timesheet_status_sync(
            sync_db, org_id, timesheet.id, models.TimesheetStatus.APPROVED, base_setup["user_id"]
        )
        timesheet_updated = timesheet_service.get_or_create_timesheet_sync(sync_db, org_id, teacher_id, week_start)
        assert timesheet_updated.status == models.TimesheetStatus.APPROVED


@pytest.mark.asyncio
class TestSoftReset:
    async def test_soft_reset_clears_data_and_resets_progress(self, sync_db, base_setup):
        org_id = base_setup["org_id"]
        
        # Using a new async session to test async function soft_reset_year
        from sqlalchemy.ext.asyncio import AsyncSession
        from app.db.database import SessionLocal
        async with SessionLocal() as async_session:
            await settings_service.soft_reset_year(async_session, org_id)
            
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
                    models.ScheduleOutput.organization_id == org_id
                )
            )
            assert len(out_result.scalars().all()) == 0
            
            # Assert Timesheet deleted
            ts_result = await async_session.execute(
                select(models.TeacherWeeklyTimesheet).where(
                    models.TeacherWeeklyTimesheet.org_id == org_id
                )
            )
            assert len(ts_result.scalars().all()) == 0


@pytest.fixture
def substitution_setup(sync_db, base_setup):
    """Extende base_setup com um segundo professor elegível para substituição."""
    org_id = base_setup["org_id"]
    class_id = base_setup["class_id"]

    # Create second subject & module
    subject2 = models.Subject(
        name="Bases de Dados",
        organization_id=org_id,
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
    sub_teacher = models.Teacher(name="Prof. Substituto", organization_id=org_id)
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
            models.Timeslot.organization_id == org_id
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
        org_id = substitution_setup["org_id"]
        output_id = substitution_setup["schedule_output_id"]

        # Create occurrence
        occurrence, _ = occurrence_service.create_occurrence_from_block_sync(
            sync_db, org_id, output_id
        )

        # Get recommendations
        recommendations = occurrence_service.get_substitute_recommendations_sync(
            sync_db, org_id, occurrence.id
        )

        assert len(recommendations) >= 1
        rec = recommendations[0]
        assert rec.teacher_id == substitution_setup["substitute_teacher_id"]
        assert rec.subject_id == substitution_setup["substitute_subject_id"]

    def test_substitution_creation_from_modal(self, sync_db, substitution_setup):
        """T 5.1.2: Criar uma substituição via endpoint e verificar que a LessonOccurrence é criada corretamente com status=SUBSTITUTED."""
        org_id = substitution_setup["org_id"]
        output_id = substitution_setup["schedule_output_id"]
        user_id = substitution_setup["user_id"]

        # Step 1: Create occurrence
        occurrence, created = occurrence_service.create_occurrence_from_block_sync(
            sync_db, org_id, output_id
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
            sync_db, occurrence.id, org_id, payload, decided_by_user_id=user_id
        )

        assert updated.status == models.LessonOccurrenceStatus.SUBSTITUTED
        assert updated.substitute_teacher_id == substitution_setup["substitute_teacher_id"]
        assert updated.substitute_subject_id == substitution_setup["substitute_subject_id"]

    def test_cannot_create_substitution_if_existing_occurrence(self, sync_db, substitution_setup):
        """T 5.1.3: Tentar criar substituição num bloco que já tem ocorrência decidida.

        O backend reutiliza a ocorrência existente (idempotente), garantindo
        que não há duplicados e que o estado decidido é preservado.
        """
        org_id = substitution_setup["org_id"]
        output_id = substitution_setup["schedule_output_id"]
        user_id = substitution_setup["user_id"]

        # Create and decide occurrence as SUBSTITUTED
        occurrence, _ = occurrence_service.create_occurrence_from_block_sync(
            sync_db, org_id, output_id
        )
        payload = schemas.LessonOccurrenceUpdate(
            status=models.LessonOccurrenceStatus.SUBSTITUTED,
            substitute_teacher_id=substitution_setup["substitute_teacher_id"],
            substitute_subject_id=substitution_setup["substitute_subject_id"],
        )
        occurrence_service.update_occurrence_sync(
            sync_db, occurrence.id, org_id, payload, decided_by_user_id=user_id
        )

        # Try to create again — should reuse existing, not create duplicate
        existing, created_now = occurrence_service.create_occurrence_from_block_sync(
            sync_db, org_id, output_id
        )
        assert created_now is False
        assert existing.id == occurrence.id
        assert existing.status == models.LessonOccurrenceStatus.SUBSTITUTED


class TestSummarySynchronization:
    def test_admin_can_update_teacher_summary(self, sync_db, base_setup):
        """T 5.2.1: Professor cria log com sumário → Admin atualiza o sumário → Verificar que o valor foi alterado."""
        org_id = base_setup["org_id"]
        output_id = base_setup["schedule_output_id"]
        teacher_user_id = base_setup["user_id"]

        # Teacher creates log
        payload = schemas.LessonLogCreate(
            status=models.LessonLogStatus.COMPLETED,
            summary="Sumário do professor",
            notes="Notas do professor",
        )
        llog = lesson_log_service.upsert_lesson_log_sync(
            sync_db, org_id, teacher_user_id, output_id, payload
        )
        assert llog.summary == "Sumário do professor"

        # Admin updates log
        admin_payload = schemas.LessonLogCreate(
            status=models.LessonLogStatus.COMPLETED,
            summary="Sumário atualizado pelo admin",
            notes="Notas atualizadas pelo admin",
        )
        updated = lesson_log_service.upsert_lesson_log_sync(
            sync_db, org_id, teacher_user_id, output_id, admin_payload
        )
        assert updated.summary == "Sumário atualizado pelo admin"
        assert updated.notes == "Notas atualizadas pelo admin"

    def test_summary_persists_after_status_change(self, sync_db, base_setup):
        """T 5.2.2: Alterar o estado de COMPLETED para OCCURRENCE e verificar que o sumário não é apagado."""
        org_id = base_setup["org_id"]
        output_id = base_setup["schedule_output_id"]
        user_id = base_setup["user_id"]

        # Create log as COMPLETED with summary
        payload = schemas.LessonLogCreate(
            status=models.LessonLogStatus.COMPLETED,
            summary="Sumário importante",
            notes="Notas importantes",
        )
        lesson_log_service.upsert_lesson_log_sync(
            sync_db, org_id, user_id, output_id, payload
        )

        # Change to OCCURRENCE keeping same summary
        payload2 = schemas.LessonLogCreate(
            status=models.LessonLogStatus.OCCURRENCE,
            summary="Sumário importante",
            notes="Notas importantes",
        )
        updated = lesson_log_service.upsert_lesson_log_sync(
            sync_db, org_id, user_id, output_id, payload2
        )
        assert updated.status == models.LessonLogStatus.OCCURRENCE
        assert updated.summary == "Sumário importante"
        assert updated.notes == "Notas importantes"


class TestAdminOpensLessonLogModal:
    def test_admin_opens_lesson_log_modal_for_past_slot(self, sync_db, base_setup):
        """T 5.3.1: Verificar que o endpoint devolve os campos lesson_log_* corretos para o admin."""
        from app.services import schedule_service
        org_id = base_setup["org_id"]
        class_id = base_setup["class_id"]
        week_start = base_setup["date"] - timedelta(days=base_setup["date"].weekday())

        # Create a lesson log
        payload = schemas.LessonLogCreate(
            status=models.LessonLogStatus.COMPLETED,
            summary="Teste de integração",
            notes="Notas de teste",
        )
        lesson_log_service.upsert_lesson_log_sync(
            sync_db, org_id, base_setup["user_id"], base_setup["schedule_output_id"], payload
        )

        # Fetch week schedule
        slots = schedule_service.get_week_schedule_sync(
            sync_db, org_id, week_start, class_id=class_id
        )
        assert len(slots) == 1
        slot = slots[0]
        assert slot["lesson_log_status"] == "COMPLETED"
        assert slot["lesson_log_summary"] == "Teste de integração"
        assert slot["lesson_log_notes"] == "Notas de teste"
        assert slot["is_past"] is True

