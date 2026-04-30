import pytest
import pytest_asyncio
from datetime import date, datetime, time, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.database import ASYNC_DB_URL
from app import models, schemas
from app.services import lesson_log_service, timesheet_service, settings_service
from app.core.security import hash_password

SYNC_TEST_URL = ASYNC_DB_URL.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
sync_test_engine = create_engine(SYNC_TEST_URL, echo=False)
SyncTestSession = sessionmaker(bind=sync_test_engine, autocommit=False, autoflush=False)

@pytest.fixture
def sync_db():
    db = SyncTestSession()
    try:
        yield db
    finally:
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

