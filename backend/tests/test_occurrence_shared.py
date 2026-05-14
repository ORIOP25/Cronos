"""
Fixtures e imports partilhados pelos testes de ocorrências.
Importado pelos ficheiros split: schemas, auto_confirm, state_machine, substitution, endpoints.
"""
import pytest
import pytest_asyncio
from datetime import date, time, timedelta
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app import models, schemas
from app.models import LessonOccurrenceStatus
from app.services import occurrence_service
from app.core.security import create_access_token
# SyncTestSession para testes de concorrência
from sqlalchemy import create_engine as _ce
from sqlalchemy.orm import sessionmaker as _sm
from app.db.database import SYNC_DB_URL
SyncTestSession = _sm(bind=_ce(SYNC_DB_URL, echo=False), autocommit=False, autoflush=False)


@pytest_asyncio.fixture
async def full_setup(db_session: AsyncSession):
    """Cria: Org → Teacher → Subject → Module → Course → Class →
    ClassSubjectLink → Timeslot → Room → Lesson → ScheduleOutput
    para hoje. Retorna um dict com todos os IDs criados.
    """
    # 1. Organization
    org = models.Organization(name="Escola Sprint 2", plan_status="active")
    db_session.add(org)
    await db_session.flush()

    # 2. Teacher & User (admin)
    teacher = models.Teacher(name="Prof. Teste", organization_id=org.id)
    db_session.add(teacher)
    await db_session.flush()

    substitute_teacher = models.Teacher(name="Prof. Substituto", organization_id=org.id)
    db_session.add(substitute_teacher)
    await db_session.flush()

    admin = models.User(
        email="admin_s2@escola.com",
        is_active=True,
        role=models.UserRole.admin,
        organization_id=org.id,
    )
    db_session.add(admin)
    await db_session.flush()

    # 3. Subject & Module
    subject = models.Subject(
        name="Programação",
        organization_id=org.id,
        required_room_type=models.RoomType.normal,
    )
    db_session.add(subject)
    await db_session.flush()

    substitute_subject = models.Subject(
        name="Inglês Técnico",
        organization_id=org.id,
        required_room_type=models.RoomType.normal,
    )
    db_session.add(substitute_subject)
    await db_session.flush()

    module = models.Module(
        name="M1 - Introdução",
        hours_total=25,
        order=1,
        subject_id=subject.id,
    )
    db_session.add(module)
    await db_session.flush()

    substitute_module = models.Module(
        name="M1 - Conversação",
        hours_total=30,
        order=1,
        subject_id=substitute_subject.id,
    )
    db_session.add(substitute_module)
    await db_session.flush()

    # 4. Course
    course = models.Course(
        name="Técnico de Informática",
        abbreviation="TINF",
        organization_id=org.id,
    )
    db_session.add(course)
    await db_session.flush()

    # 5. Class (Turma)
    class_ = models.Class(
        name="TINF 24/27",
        size=20,
        start_year=2024,
        end_year=2027,
        grade_level=10,
        course_id=course.id,
        organization_id=org.id,
    )
    db_session.add(class_)
    await db_session.flush()

    # 6. Room & Timeslot
    room = models.Room(
        name="Sala 101",
        capacity=30,
        type=models.RoomType.normal,
        organization_id=org.id,
    )
    db_session.add(room)
    await db_session.flush()

    timeslot = models.Timeslot(
        day_of_week=0,
        start_time=time(9, 0),
        end_time=time(11, 0),
        organization_id=org.id,
    )
    db_session.add(timeslot)
    await db_session.flush()

    # 7. Ligações curriculares e disponibilidade base para substituição elegível
    db_session.add(models.ClassSubjectLink(
        class_id=class_.id,
        subject_id=subject.id,
        grade_level=class_.grade_level,
        teacher_id=teacher.id,
    ))
    db_session.add(models.ClassSubjectLink(
        class_id=class_.id,
        subject_id=substitute_subject.id,
        grade_level=class_.grade_level,
        teacher_id=substitute_teacher.id,
    ))
    db_session.add(models.Availability(
        teacher_id=teacher.id,
        timeslot_id=timeslot.id,
        score=models.PreferenceLevel.NEUTRAL.value,
    ))
    db_session.add(models.Availability(
        teacher_id=substitute_teacher.id,
        timeslot_id=timeslot.id,
        score=models.PreferenceLevel.PREFERRED.value,
    ))
    await db_session.flush()

    # 8. Lesson (definição abstrata)
    lesson = models.Lesson(
        organization_id=org.id,
        class_id=class_.id,
        subject_id=subject.id,
        teacher_id=teacher.id,
    )
    db_session.add(lesson)
    await db_session.flush()

    # 9. ScheduleOutput para hoje
    today = date.today()
    schedule_output = models.ScheduleOutput(
        organization_id=org.id,
        lesson_id=lesson.id,
        timeslot_id=timeslot.id,
        room_id=room.id,
        generation_id="test-gen-001",
        date=today,
        is_draft=False,
    )
    db_session.add(schedule_output)
    await db_session.commit()

    return {
        "organization_id": org.id,
        "admin_id": admin.id,
        "teacher_id": teacher.id,
        "substitute_teacher_id": substitute_teacher.id,
        "subject_id": subject.id,
        "substitute_subject_id": substitute_subject.id,
        "module_id": module.id,
        "substitute_module_id": substitute_module.id,
        "class_id": class_.id,
        "course_id": course.id,
        "room_id": room.id,
        "timeslot_id": timeslot.id,
        "lesson_id": lesson.id,
        "schedule_output_id": schedule_output.id,
        "admin_email": admin.email,
    }


@pytest.fixture
def substitution_setup(sync_db, full_setup):
    """Contexto rico para passo 2: elegíveis, não elegíveis e conflito de slot."""
    organization_id = full_setup["organization_id"]
    class_id = full_setup["class_id"]
    course_id = full_setup["course_id"]
    room_id = full_setup["room_id"]
    timeslot_id = full_setup["timeslot_id"]
    target_date = date.today()

    class_row = sync_db.get(models.Class, class_id)
    assert class_row is not None

    # Segundo candidato elegível (para ranking/tie-break)
    candidate_b_teacher = models.Teacher(name="Prof. Candidato B", organization_id=organization_id)
    sync_db.add(candidate_b_teacher)
    sync_db.flush()

    candidate_b_subject = models.Subject(
        name="Área Integradora B",
        organization_id=organization_id,
        required_room_type=models.RoomType.normal,
    )
    sync_db.add(candidate_b_subject)
    sync_db.flush()

    sync_db.add(models.Module(
        name="M1 - B",
        hours_total=20,
        order=1,
        subject_id=candidate_b_subject.id,
    ))

    sync_db.add(models.ClassSubjectLink(
        class_id=class_id,
        subject_id=candidate_b_subject.id,
        grade_level=class_row.grade_level,
        teacher_id=candidate_b_teacher.id,
    ))
    sync_db.add(models.Availability(
        teacher_id=candidate_b_teacher.id,
        timeslot_id=timeslot_id,
        score=models.PreferenceLevel.PREFERRED.value,
    ))

    # Docente da mesma disciplina, mas noutra turma (não elegível)
    teacher_same_subject_other_class = models.Teacher(
        name="Prof. Mesmo Assunto Outra Turma",
        organization_id=organization_id,
    )
    sync_db.add(teacher_same_subject_other_class)
    sync_db.flush()

    class_other = models.Class(
        name="TINF 24/27 B",
        size=18,
        start_year=2024,
        end_year=2027,
        grade_level=10,
        course_id=course_id,
        organization_id=organization_id,
    )
    sync_db.add(class_other)
    sync_db.flush()

    sync_db.add(models.ClassSubjectLink(
        class_id=class_other.id,
        subject_id=full_setup["subject_id"],
        grade_level=class_other.grade_level,
        teacher_id=teacher_same_subject_other_class.id,
    ))
    sync_db.add(models.Availability(
        teacher_id=teacher_same_subject_other_class.id,
        timeslot_id=timeslot_id,
        score=models.PreferenceLevel.PREFERRED.value,
    ))

    # Candidato com conflito de slot
    conflict_teacher = models.Teacher(name="Prof. Conflito", organization_id=organization_id)
    sync_db.add(conflict_teacher)
    sync_db.flush()

    conflict_subject = models.Subject(
        name="Área Conflito",
        organization_id=organization_id,
        required_room_type=models.RoomType.normal,
    )
    sync_db.add(conflict_subject)
    sync_db.flush()

    sync_db.add(models.Module(
        name="M1 - Conflito",
        hours_total=20,
        order=1,
        subject_id=conflict_subject.id,
    ))

    sync_db.add(models.ClassSubjectLink(
        class_id=class_id,
        subject_id=conflict_subject.id,
        grade_level=class_row.grade_level,
        teacher_id=conflict_teacher.id,
    ))
    sync_db.add(models.Availability(
        teacher_id=conflict_teacher.id,
        timeslot_id=timeslot_id,
        score=models.PreferenceLevel.PREFERRED.value,
    ))

    lesson_conflict = models.Lesson(
        organization_id=organization_id,
        class_id=class_other.id,
        subject_id=conflict_subject.id,
        teacher_id=conflict_teacher.id,
    )
    sync_db.add(lesson_conflict)
    sync_db.flush()

    schedule_output_conflict = models.ScheduleOutput(
        organization_id=organization_id,
        lesson_id=lesson_conflict.id,
        timeslot_id=timeslot_id,
        room_id=room_id,
        generation_id="gen-conflict-step2",
        date=target_date,
        is_draft=False,
    )
    sync_db.add(schedule_output_conflict)

    # Docente de outro tenant (não elegível)
    other_org = models.Organization(name="Escola Outro Tenant", plan_status="active")
    sync_db.add(other_org)
    sync_db.flush()

    other_course = models.Course(
        name="Curso Outro Tenant",
        abbreviation="TOT",
        organization_id=other_org.id,
    )
    sync_db.add(other_course)
    sync_db.flush()

    other_class = models.Class(
        name="OUT 10A",
        size=15,
        start_year=2024,
        end_year=2027,
        grade_level=10,
        course_id=other_course.id,
        organization_id=other_org.id,
    )
    sync_db.add(other_class)
    sync_db.flush()

    other_teacher = models.Teacher(name="Prof. Outro Tenant", organization_id=other_org.id)
    sync_db.add(other_teacher)
    sync_db.flush()

    other_subject = models.Subject(
        name="Disciplina Outro Tenant",
        organization_id=other_org.id,
        required_room_type=models.RoomType.normal,
    )
    sync_db.add(other_subject)
    sync_db.flush()

    sync_db.add(models.Module(
        name="M1 - Outro Tenant",
        hours_total=20,
        order=1,
        subject_id=other_subject.id,
    ))
    sync_db.add(models.ClassSubjectLink(
        class_id=other_class.id,
        subject_id=other_subject.id,
        grade_level=other_class.grade_level,
        teacher_id=other_teacher.id,
    ))

    # User professor para testar bloqueio de confirmação
    teacher_user = models.User(
        email="teacher_s2@escola.com",
        is_active=True,
        role=models.UserRole.teacher,
        organization_id=organization_id,
        teacher_id=full_setup["substitute_teacher_id"],
    )
    sync_db.add(teacher_user)

    sync_db.commit()

    return {
        **full_setup,
        "candidate_b_teacher_id": candidate_b_teacher.id,
        "candidate_b_subject_id": candidate_b_subject.id,
        "teacher_same_subject_other_class_id": teacher_same_subject_other_class.id,
        "conflict_teacher_id": conflict_teacher.id,
        "conflict_subject_id": conflict_subject.id,
        "other_tenant_teacher_id": other_teacher.id,
        "other_tenant_subject_id": other_subject.id,
        "teacher_user_email": teacher_user.email,
    }
