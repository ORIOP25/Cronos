# Ficheiro: backend/tests/test_occurrences.py
#
# Testes para Sprint 2: LessonOccurrence, auto-confirmação e dívidas de horas.
import os
os.environ["RATELIMIT_ENABLED"] = "false"

from concurrent.futures import ThreadPoolExecutor

import pytest
import pytest_asyncio
from datetime import date, datetime, time, timedelta, timezone
from typing import AsyncGenerator

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker

from app.db.database import ASYNC_DB_URL
from app import models, schemas
from app.models import LessonOccurrenceStatus
from app.services import occurrence_service, schedule_service
from app.core.security import create_access_token, hash_password

# sync_db fixture is provided by conftest.py (shared across all test files)
# SyncTestSession kept locally for concurrent thread tests that need separate sessions
from sqlalchemy import create_engine as _ce
from sqlalchemy.orm import sessionmaker as _sm
from app.db.database import SYNC_DB_URL
SyncTestSession = _sm(bind=_ce(SYNC_DB_URL, echo=False), autocommit=False, autoflush=False)

# ---------------------------------------------------------------------------
# Fixture para construir a cadeia completa de entidades necessárias
# ---------------------------------------------------------------------------
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
        hashed_password=hash_password("pass123"),
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
        day_of_week=0,  # Segunda
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
    org_id = full_setup["org_id"]
    class_id = full_setup["class_id"]
    course_id = full_setup["course_id"]
    room_id = full_setup["room_id"]
    timeslot_id = full_setup["timeslot_id"]
    target_date = date.today()

    class_row = sync_db.get(models.Class, class_id)
    assert class_row is not None

    # Segundo candidato elegível (para ranking/tie-break)
    candidate_b_teacher = models.Teacher(name="Prof. Candidato B", organization_id=org_id)
    sync_db.add(candidate_b_teacher)
    sync_db.flush()

    candidate_b_subject = models.Subject(
        name="Área Integradora B",
        organization_id=org_id,
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
        organization_id=org_id,
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
        organization_id=org_id,
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
    conflict_teacher = models.Teacher(name="Prof. Conflito", organization_id=org_id)
    sync_db.add(conflict_teacher)
    sync_db.flush()

    conflict_subject = models.Subject(
        name="Área Conflito",
        organization_id=org_id,
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
        organization_id=org_id,
        class_id=class_other.id,
        subject_id=conflict_subject.id,
        teacher_id=conflict_teacher.id,
    )
    sync_db.add(lesson_conflict)
    sync_db.flush()

    schedule_output_conflict = models.ScheduleOutput(
        organization_id=org_id,
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
        hashed_password=hash_password("pass123"),
        is_active=True,
        role=models.UserRole.teacher,
        organization_id=org_id,
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


# ===========================================================================
# 1. Testes de Schema (sem BD)
# ===========================================================================

class TestLessonOccurrenceSchemas:
    """Validação das regras Pydantic dos schemas de Sprint 2."""

    def test_create_occurrence_command_default_action_valid(self):
        payload = schemas.LessonOccurrenceCreate(schedule_output_id=10)
        assert payload.action == "CREATE_OCCURRENCE"

    def test_create_occurrence_command_rejects_unknown_action(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            schemas.LessonOccurrenceCreate(
                action="OPEN_OCCURRENCE",
                schedule_output_id=10,
            )


class TestWeekSchedulePerformance:
    """Valida leitura semanal com custo estável (sem padrão N+1)."""

    def test_get_week_schedule_sync_avoids_n_plus_one_for_active_modules(self, sync_db, full_setup):
        org_id = full_setup["org_id"]
        class_id = full_setup["class_id"]
        room_id = full_setup["room_id"]
        timeslot_id = full_setup["timeslot_id"]
        week_start = date.today() - timedelta(days=date.today().weekday())

        # Amplia pares (class_id, subject_id) para stressar resolução de módulo ativo.
        for idx in range(12):
            teacher = models.Teacher(
                name=f"Perf Prof {idx}",
                organization_id=org_id,
            )
            sync_db.add(teacher)
            sync_db.flush()

            subject = models.Subject(
                name=f"Perf Subject {idx}",
                organization_id=org_id,
                required_room_type=models.RoomType.normal,
            )
            sync_db.add(subject)
            sync_db.flush()

            sync_db.add(models.Module(
                name=f"Perf Module {idx}",
                hours_total=20,
                order=1,
                subject_id=subject.id,
            ))
            sync_db.flush()

            lesson = models.Lesson(
                organization_id=org_id,
                class_id=class_id,
                subject_id=subject.id,
                teacher_id=teacher.id,
            )
            sync_db.add(lesson)
            sync_db.flush()

            sync_db.add(models.ScheduleOutput(
                organization_id=org_id,
                lesson_id=lesson.id,
                timeslot_id=timeslot_id,
                room_id=room_id,
                generation_id=f"perf-gen-{idx}",
                date=week_start + timedelta(days=idx % 5),
                is_draft=False,
            ))

        sync_db.commit()

        bind = sync_db.get_bind()
        counter = {"count": 0}

        def _before_cursor_execute(*_args, **_kwargs):
            counter["count"] += 1

        event.listen(bind, "before_cursor_execute", _before_cursor_execute)
        try:
            slots = schedule_service.get_week_schedule_sync(
                sync_db,
                organization_id=org_id,
                week_start=week_start,
                class_id=class_id,
            )
        finally:
            event.remove(bind, "before_cursor_execute", _before_cursor_execute)

        assert len(slots) >= 10
        # Custo esperado estável: 1 query outputs + 1 occurrences + 1 modules + 1 progress.
        assert counter["count"] <= 8

    def test_update_status_gap_valid(self):
        """GAP não requer professor substituto."""
        payload = schemas.LessonOccurrenceUpdate(status=LessonOccurrenceStatus.GAP)
        assert payload.status == LessonOccurrenceStatus.GAP
        assert payload.substitute_teacher_id is None

    def test_update_status_given_valid(self):
        """GIVEN não requer professor substituto."""
        payload = schemas.LessonOccurrenceUpdate(status=LessonOccurrenceStatus.GIVEN)
        assert payload.status == LessonOccurrenceStatus.GIVEN

    def test_update_status_substituted_requires_teacher(self):
        """SUBSTITUTED sem professor → ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            schemas.LessonOccurrenceUpdate(
                status=LessonOccurrenceStatus.SUBSTITUTED,
                substitute_teacher_id=None,
                substitute_subject_id=7,
            )
        errors = exc_info.value.errors()
        assert any("substitute_teacher_id" in str(e) for e in errors)

    def test_update_status_substituted_requires_subject(self):
        """SUBSTITUTED sem disciplina executada → ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            schemas.LessonOccurrenceUpdate(
                status=LessonOccurrenceStatus.SUBSTITUTED,
                substitute_teacher_id=42,
                substitute_subject_id=None,
            )
        errors = exc_info.value.errors()
        assert any("substitute_subject_id" in str(e) for e in errors)

    def test_update_status_substituted_with_teacher_valid(self):
        """SUBSTITUTED com professor → válido."""
        payload = schemas.LessonOccurrenceUpdate(
            status=LessonOccurrenceStatus.SUBSTITUTED,
            substitute_teacher_id=42,
            substitute_subject_id=7,
        )
        assert payload.substitute_teacher_id == 42

    def test_update_status_gap_rejects_substitute_fields(self):
        """GAP com dados de substituição deve falhar (payload inconsistente)."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            schemas.LessonOccurrenceUpdate(
                status=LessonOccurrenceStatus.GAP,
                substitute_teacher_id=1,
                substitute_subject_id=2,
            )

    def test_debt_item_schema(self):
        """DebtItem é construível com os campos corretos."""
        item = schemas.DebtItem(
            class_id=1,
            class_name="TINF 24/27",
            subject_id=2,
            subject_name="Programação",
            teacher_id=3,
            teacher_name="Prof. Silva",
            gap_occurrences=3,
            hours_owed=6.0,
        )
        assert item.hours_owed == pytest.approx(6.0)
        assert item.gap_occurrences_overdue == 0
        assert item.hours_owed_overdue == pytest.approx(0.0)

    def test_debt_list_read_schema(self):
        """DebtListRead agrega corretamente."""
        debt_list = schemas.DebtListRead(
            total_gaps=2,
            total_hours_owed=4.0,
            as_of_date=date.today(),
            items=[],
        )
        assert debt_list.total_gaps == 2

    def test_available_substitute_schema(self):
        """AvailableSubstituteRead tem todos os campos necessários."""
        sub = schemas.AvailableSubstituteRead(
            teacher_id=1,
            teacher_name="Prof. Maria",
            subject_id=2,
            subject_name="Matemática",
            class_id=3,
            class_name="10A",
        )
        assert sub.teacher_id == 1


# ===========================================================================
# 2. Testes de Serviço (com BD síncrona)
# ===========================================================================

class TestAutoConfirmService:
    """Testa o cron de confirmação automática diária."""

    def test_auto_confirm_creates_given_record(self, sync_db, full_setup):
        """Deve criar LessonOccurrence GIVEN para slots de hoje sem ocorrência."""
        org_id = full_setup["org_id"]
        today = date.today()

        count = occurrence_service.auto_confirm_daily_sync(sync_db, org_id, today)

        assert count == 1

        # Verificar que o registo existe na BD
        from sqlalchemy import select
        occurrence = sync_db.execute(
            select(models.LessonOccurrence).where(
                models.LessonOccurrence.schedule_output_id
                == full_setup["schedule_output_id"]
            )
        ).scalar_one_or_none()

        assert occurrence is not None
        assert occurrence.status == LessonOccurrenceStatus.GIVEN
        assert occurrence.hours_given == pytest.approx(2.0)  # 09:00 → 11:00 = 2h

    def test_auto_confirm_skips_existing_occurrence(self, sync_db, full_setup):
        """Se já existe uma ocorrência manual, o cron não cria outra."""
        org_id = full_setup["org_id"]
        today = date.today()
        output_id = full_setup["schedule_output_id"]

        # Criar ocorrência manual GAP antes do cron
        manual = models.LessonOccurrence(
            organization_id=org_id,
            schedule_output_id=output_id,
            date=today,
            status=LessonOccurrenceStatus.GAP,
            hours_given=0.0,
        )
        sync_db.add(manual)
        sync_db.commit()

        # Cron deve ignorar este slot
        count = occurrence_service.auto_confirm_daily_sync(sync_db, org_id, today)
        assert count == 0

        # Verificar que continua a existir apenas 1 ocorrência
        from sqlalchemy import select
        all_occurrences = list(
            sync_db.execute(
                select(models.LessonOccurrence).where(
                    models.LessonOccurrence.schedule_output_id == output_id
                )
            ).scalars()
        )
        assert len(all_occurrences) == 1
        assert all_occurrences[0].status == LessonOccurrenceStatus.GAP

    def test_get_debts_empty_when_no_gaps(self, sync_db, full_setup):
        """Sem ocorrências GAP, as dívidas devem estar vazias."""
        org_id = full_setup["org_id"]
        result = occurrence_service.get_debts_sync(sync_db, org_id)
        assert result.total_gaps == 0
        assert result.total_hours_owed == pytest.approx(0.0)
        assert result.total_gaps_overdue == 0
        assert result.total_hours_owed_overdue == pytest.approx(0.0)
        assert result.items == []

    def test_get_debts_counts_gap_occurrences(self, sync_db, full_setup):
        """Uma ocorrência GAP deve aparecer nas dívidas."""
        org_id = full_setup["org_id"]
        today = date.today()
        output_id = full_setup["schedule_output_id"]

        gap = models.LessonOccurrence(
            organization_id=org_id,
            schedule_output_id=output_id,
            date=today,
            status=LessonOccurrenceStatus.GAP,
            hours_given=2.0,
        )
        sync_db.add(gap)
        sync_db.commit()

        result = occurrence_service.get_debts_sync(sync_db, org_id)

        assert result.total_gaps == 1
        assert result.total_hours_owed == pytest.approx(2.0)
        assert result.total_gaps_overdue == 1
        assert result.total_hours_owed_overdue == pytest.approx(2.0)
        assert len(result.items) == 1

    def test_get_occurrence_returns_none_for_wrong_org(self, sync_db, full_setup):
        """Não deve retornar ocorrências de outra organização (tenant isolation)."""
        result = occurrence_service.get_occurrence_sync(sync_db, 9999, org_id=9999)
        assert result is None


class TestOccurrenceStateMachineAndAccounting:
    """Cobre WBS 1.1, 1.2 e 1.3 (transições, contabilização e auditoria)."""

    def _load_occurrence(self, sync_db, schedule_output_id: int):
        return sync_db.execute(
            select(models.LessonOccurrence).where(
                models.LessonOccurrence.schedule_output_id == schedule_output_id
            )
        ).scalar_one()

    def _prepare_open_occurrence(self, sync_db, full_setup):
        occurrence, _ = occurrence_service.create_occurrence_from_block_sync(
            sync_db,
            full_setup["org_id"],
            full_setup["schedule_output_id"],
        )
        return occurrence

    def test_concurrent_create_occurrence_command_keeps_single_row(self, full_setup):
        org_id = full_setup["org_id"]
        schedule_output_id = full_setup["schedule_output_id"]

        def _attempt_create():
            db_local = SyncTestSession()
            try:
                occurrence, created_now = occurrence_service.create_occurrence_from_block_sync(
                    db_local,
                    organization_id=org_id,
                    schedule_output_id=schedule_output_id,
                )
                return {"id": occurrence.id, "created_now": created_now}
            finally:
                db_local.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [pool.submit(_attempt_create).result() for _ in range(2)]

        created_count = sum(1 for item in results if item["created_now"])
        assert created_count == 1
        assert results[0]["id"] == results[1]["id"]

        verify_db = SyncTestSession()
        try:
            occurrences = verify_db.execute(
                select(models.LessonOccurrence).where(
                    models.LessonOccurrence.organization_id == org_id,
                    models.LessonOccurrence.schedule_output_id == schedule_output_id,
                )
            ).scalars().all()
            assert len(occurrences) == 1
        finally:
            verify_db.close()

    def test_given_to_gap_updates_accounting_and_audit(self, sync_db, full_setup):
        org_id = full_setup["org_id"]
        occurrence = self._prepare_open_occurrence(sync_db, full_setup)

        updated = occurrence_service.update_occurrence_sync(
            sync_db,
            occurrence.id,
            org_id,
            schemas.LessonOccurrenceUpdate(status=LessonOccurrenceStatus.GAP),
            decided_by_user_id=full_setup["admin_id"],
        )

        assert updated.status == LessonOccurrenceStatus.GAP
        assert updated.decided_by_user_id == full_setup["admin_id"]
        assert updated.decided_at is not None
        assert updated.planned_teacher_id == full_setup["teacher_id"]
        assert updated.executed_teacher_id is None
        assert updated.hours_given == pytest.approx(0.0)

        progress = sync_db.execute(
            select(models.ClassProgress).where(
                models.ClassProgress.class_id == full_setup["class_id"],
                models.ClassProgress.module_id == full_setup["module_id"],
            )
        ).scalar_one()

        assert progress.hours_completed == pytest.approx(0.0)
        assert progress.hours_debt == pytest.approx(2.0)

    def test_given_to_substituted_moves_progress_and_creates_debt(self, sync_db, full_setup):
        org_id = full_setup["org_id"]
        occurrence = self._prepare_open_occurrence(sync_db, full_setup)

        updated = occurrence_service.update_occurrence_sync(
            sync_db,
            occurrence.id,
            org_id,
            schemas.LessonOccurrenceUpdate(
                status=LessonOccurrenceStatus.SUBSTITUTED,
                substitute_teacher_id=full_setup["substitute_teacher_id"],
                substitute_subject_id=full_setup["substitute_subject_id"],
            ),
            decided_by_user_id=full_setup["admin_id"],
        )

        assert updated.status == LessonOccurrenceStatus.SUBSTITUTED
        assert updated.executed_teacher_id == full_setup["substitute_teacher_id"]
        assert updated.executed_module_id == full_setup["substitute_module_id"]

        planned_progress = sync_db.execute(
            select(models.ClassProgress).where(
                models.ClassProgress.class_id == full_setup["class_id"],
                models.ClassProgress.module_id == full_setup["module_id"],
            )
        ).scalar_one()
        substitute_progress = sync_db.execute(
            select(models.ClassProgress).where(
                models.ClassProgress.class_id == full_setup["class_id"],
                models.ClassProgress.module_id == full_setup["substitute_module_id"],
            )
        ).scalar_one()

        assert planned_progress.hours_completed == pytest.approx(0.0)
        assert planned_progress.hours_debt == pytest.approx(2.0)
        assert substitute_progress.hours_completed == pytest.approx(2.0)
        assert substitute_progress.hours_debt == pytest.approx(0.0)

        debts = occurrence_service.get_debts_sync(sync_db, org_id)
        assert debts.total_gaps == 1
        assert debts.total_hours_owed == pytest.approx(2.0)
        assert debts.total_gaps_overdue == 1
        assert debts.total_hours_owed_overdue == pytest.approx(2.0)

    def test_future_gap_is_counted_immediately_in_debts(self, sync_db, full_setup):
        """GAP futuro decidido deve aparecer de imediato na lista de dívida."""
        org_id = full_setup["org_id"]
        future_date = date.today() + timedelta(days=7)

        future_output = models.ScheduleOutput(
            organization_id=org_id,
            lesson_id=full_setup["lesson_id"],
            timeslot_id=full_setup["timeslot_id"],
            room_id=full_setup["room_id"],
            generation_id="future-gap-debt-001",
            date=future_date,
            is_draft=False,
        )
        sync_db.add(future_output)
        sync_db.commit()

        occurrence, _ = occurrence_service.create_occurrence_from_block_sync(
            sync_db,
            org_id,
            future_output.id,
        )

        updated = occurrence_service.update_occurrence_sync(
            sync_db,
            occurrence.id,
            org_id,
            schemas.LessonOccurrenceUpdate(status=LessonOccurrenceStatus.GAP),
            decided_by_user_id=full_setup["admin_id"],
        )

        assert updated.date == future_date
        assert updated.status == LessonOccurrenceStatus.GAP

        debts = occurrence_service.get_debts_sync(sync_db, org_id)
        assert debts.total_gaps == 1
        assert debts.total_hours_owed == pytest.approx(2.0)
        assert debts.total_gaps_overdue == 0
        assert debts.total_hours_owed_overdue == pytest.approx(0.0)

    def test_invalid_transition_gap_to_substituted_fails(self, sync_db, full_setup):
        org_id = full_setup["org_id"]
        occurrence = self._prepare_open_occurrence(sync_db, full_setup)

        occurrence_service.update_occurrence_sync(
            sync_db,
            occurrence.id,
            org_id,
            schemas.LessonOccurrenceUpdate(status=LessonOccurrenceStatus.GAP),
            decided_by_user_id=full_setup["admin_id"],
        )

        with pytest.raises(occurrence_service.OccurrenceServiceError) as exc_info:
            occurrence_service.update_occurrence_sync(
                sync_db,
                occurrence.id,
                org_id,
                schemas.LessonOccurrenceUpdate(
                    status=LessonOccurrenceStatus.SUBSTITUTED,
                    substitute_teacher_id=full_setup["substitute_teacher_id"],
                    substitute_subject_id=full_setup["substitute_subject_id"],
                ),
                decided_by_user_id=full_setup["admin_id"],
            )

        assert exc_info.value.status_code == 409

    def test_idempotent_duplicate_submission_does_not_duplicate_accounting(self, sync_db, full_setup):
        org_id = full_setup["org_id"]
        occurrence = self._prepare_open_occurrence(sync_db, full_setup)
        payload = schemas.LessonOccurrenceUpdate(status=LessonOccurrenceStatus.GAP)

        occurrence_service.update_occurrence_sync(
            sync_db,
            occurrence.id,
            org_id,
            payload,
            decided_by_user_id=full_setup["admin_id"],
        )
        occurrence_service.update_occurrence_sync(
            sync_db,
            occurrence.id,
            org_id,
            payload,
            decided_by_user_id=full_setup["admin_id"],
        )

        progress = sync_db.execute(
            select(models.ClassProgress).where(
                models.ClassProgress.class_id == full_setup["class_id"],
                models.ClassProgress.module_id == full_setup["module_id"],
            )
        ).scalar_one()

        assert progress.hours_completed == pytest.approx(0.0)
        assert progress.hours_debt == pytest.approx(2.0)

    def test_update_occurrence_blocks_cross_tenant_access(self, sync_db, full_setup):
        org_id = full_setup["org_id"]
        occurrence = self._prepare_open_occurrence(sync_db, full_setup)

        with pytest.raises(occurrence_service.OccurrenceServiceError) as exc_info:
            occurrence_service.update_occurrence_sync(
                sync_db,
                occurrence.id,
                org_id + 999,
                schemas.LessonOccurrenceUpdate(status=LessonOccurrenceStatus.GAP),
                decided_by_user_id=full_setup["admin_id"],
            )

        assert exc_info.value.status_code == 404

    def test_update_occurrence_rolls_back_on_mid_operation_error(self, sync_db, full_setup, monkeypatch):
        org_id = full_setup["org_id"]
        occurrence = self._prepare_open_occurrence(sync_db, full_setup)

        original = occurrence_service._apply_module_delta
        calls = {"count": 0}

        def _explode_on_second_module_delta(*args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 2:
                raise RuntimeError("forced-mid-operation-error")
            return original(*args, **kwargs)

        monkeypatch.setattr(occurrence_service, "_apply_module_delta", _explode_on_second_module_delta)

        with pytest.raises(RuntimeError):
            occurrence_service.update_occurrence_sync(
                sync_db,
                occurrence.id,
                org_id,
                schemas.LessonOccurrenceUpdate(
                    status=LessonOccurrenceStatus.SUBSTITUTED,
                    substitute_teacher_id=full_setup["substitute_teacher_id"],
                    substitute_subject_id=full_setup["substitute_subject_id"],
                ),
                decided_by_user_id=full_setup["admin_id"],
            )

        sync_db.expire_all()

        reloaded_occurrence = self._load_occurrence(sync_db, full_setup["schedule_output_id"])
        reloaded_planned_progress = sync_db.execute(
            select(models.ClassProgress).where(
                models.ClassProgress.class_id == full_setup["class_id"],
                models.ClassProgress.module_id == full_setup["module_id"],
            )
        ).scalar_one_or_none()
        reloaded_executed_progress = sync_db.execute(
            select(models.ClassProgress).where(
                models.ClassProgress.class_id == full_setup["class_id"],
                models.ClassProgress.module_id == full_setup["substitute_module_id"],
            )
        ).scalar_one_or_none()

        assert reloaded_occurrence.status == LessonOccurrenceStatus.GIVEN
        assert reloaded_occurrence.decided_at is None
        assert reloaded_planned_progress is None
        assert reloaded_executed_progress is None

    def test_cannot_delete_occurrence_history(self, sync_db, full_setup):
        occurrence = self._prepare_open_occurrence(sync_db, full_setup)

        sync_db.delete(occurrence)
        with pytest.raises(ValueError):
            sync_db.commit()

        sync_db.rollback()
        still_exists = self._load_occurrence(sync_db, full_setup["schedule_output_id"])
        assert still_exists is not None


class TestSubstitutionEligibilityAndRanking:
    """Cobre WBS 2.1 e 2.2: elegibilidade e ranking determinístico."""

    def _prepare_occurrence(self, sync_db, setup):
        occurrence, _ = occurrence_service.create_occurrence_from_block_sync(
            sync_db,
            setup["org_id"],
            setup["schedule_output_id"],
        )
        return occurrence

    def test_valid_substitution_same_class_different_subject(self, sync_db, substitution_setup):
        occurrence = self._prepare_occurrence(sync_db, substitution_setup)

        updated = occurrence_service.update_occurrence_sync(
            sync_db,
            occurrence.id,
            substitution_setup["org_id"],
            schemas.LessonOccurrenceUpdate(
                status=LessonOccurrenceStatus.SUBSTITUTED,
                substitute_teacher_id=substitution_setup["substitute_teacher_id"],
                substitute_subject_id=substitution_setup["substitute_subject_id"],
            ),
            decided_by_user_id=substitution_setup["admin_id"],
        )

        assert updated.status == LessonOccurrenceStatus.SUBSTITUTED
        assert updated.substitute_teacher_id == substitution_setup["substitute_teacher_id"]

    def test_invalid_same_subject_teacher_from_other_class(self, sync_db, substitution_setup):
        occurrence = self._prepare_occurrence(sync_db, substitution_setup)

        with pytest.raises(occurrence_service.OccurrenceServiceError) as exc_info:
            occurrence_service.update_occurrence_sync(
                sync_db,
                occurrence.id,
                substitution_setup["org_id"],
                schemas.LessonOccurrenceUpdate(
                    status=LessonOccurrenceStatus.SUBSTITUTED,
                    substitute_teacher_id=substitution_setup["teacher_same_subject_other_class_id"],
                    substitute_subject_id=substitution_setup["subject_id"],
                ),
                decided_by_user_id=substitution_setup["admin_id"],
            )

        assert exc_info.value.status_code == 409

    def test_invalid_substitution_slot_conflict(self, sync_db, substitution_setup):
        occurrence = self._prepare_occurrence(sync_db, substitution_setup)

        with pytest.raises(occurrence_service.OccurrenceServiceError) as exc_info:
            occurrence_service.update_occurrence_sync(
                sync_db,
                occurrence.id,
                substitution_setup["org_id"],
                schemas.LessonOccurrenceUpdate(
                    status=LessonOccurrenceStatus.SUBSTITUTED,
                    substitute_teacher_id=substitution_setup["conflict_teacher_id"],
                    substitute_subject_id=substitution_setup["conflict_subject_id"],
                ),
                decided_by_user_id=substitution_setup["admin_id"],
            )

        assert exc_info.value.status_code == 409
        assert "conflito" in exc_info.value.detail.lower()

    def test_invalid_substitution_when_teacher_already_substituting_same_slot(
        self,
        sync_db,
        substitution_setup,
    ):
        occurrence = self._prepare_occurrence(sync_db, substitution_setup)
        source_output = sync_db.get(models.ScheduleOutput, substitution_setup["schedule_output_id"])
        assert source_output is not None

        blocking_lesson = models.Lesson(
            organization_id=substitution_setup["org_id"],
            class_id=substitution_setup["class_id"],
            subject_id=substitution_setup["substitute_subject_id"],
            teacher_id=substitution_setup["substitute_teacher_id"],
        )
        sync_db.add(blocking_lesson)
        sync_db.flush()

        blocking_output = models.ScheduleOutput(
            organization_id=substitution_setup["org_id"],
            lesson_id=blocking_lesson.id,
            timeslot_id=source_output.timeslot_id,
            room_id=source_output.room_id,
            generation_id="gen-block-existing-substitution",
            date=source_output.date,
            is_draft=False,
        )
        sync_db.add(blocking_output)
        sync_db.flush()

        sync_db.add(models.LessonOccurrence(
            organization_id=substitution_setup["org_id"],
            schedule_output_id=blocking_output.id,
            date=source_output.date,
            status=LessonOccurrenceStatus.SUBSTITUTED,
            planned_hours=2.0,
            substitute_teacher_id=substitution_setup["substitute_teacher_id"],
            substitute_subject_id=substitution_setup["substitute_subject_id"],
            planned_teacher_id=substitution_setup["substitute_teacher_id"],
            executed_teacher_id=substitution_setup["substitute_teacher_id"],
            planned_module_id=substitution_setup["substitute_module_id"],
            executed_module_id=substitution_setup["substitute_module_id"],
            hours_given=2.0,
            decided_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
        ))
        sync_db.commit()

        with pytest.raises(occurrence_service.OccurrenceServiceError) as exc_info:
            occurrence_service.update_occurrence_sync(
                sync_db,
                occurrence.id,
                substitution_setup["org_id"],
                schemas.LessonOccurrenceUpdate(
                    status=LessonOccurrenceStatus.SUBSTITUTED,
                    substitute_teacher_id=substitution_setup["substitute_teacher_id"],
                    substitute_subject_id=substitution_setup["substitute_subject_id"],
                ),
                decided_by_user_id=substitution_setup["admin_id"],
            )

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail == occurrence_service.ERR_SUBSTITUTE_SLOT_CONFLICT

    def test_invalid_substitution_different_tenant(self, sync_db, substitution_setup):
        occurrence = self._prepare_occurrence(sync_db, substitution_setup)

        with pytest.raises(occurrence_service.OccurrenceServiceError) as exc_info:
            occurrence_service.update_occurrence_sync(
                sync_db,
                occurrence.id,
                substitution_setup["org_id"],
                schemas.LessonOccurrenceUpdate(
                    status=LessonOccurrenceStatus.SUBSTITUTED,
                    substitute_teacher_id=substitution_setup["other_tenant_teacher_id"],
                    substitute_subject_id=substitution_setup["other_tenant_subject_id"],
                ),
                decided_by_user_id=substitution_setup["admin_id"],
            )

        assert exc_info.value.status_code == 409

    def test_recommendation_ranking_reproducible(self, sync_db, substitution_setup):
        occurrence = self._prepare_occurrence(sync_db, substitution_setup)

        first = occurrence_service.get_substitute_recommendations_sync(
            sync_db,
            organization_id=substitution_setup["org_id"],
            occurrence_id=occurrence.id,
        )
        second = occurrence_service.get_substitute_recommendations_sync(
            sync_db,
            organization_id=substitution_setup["org_id"],
            occurrence_id=occurrence.id,
        )

        assert [(r.teacher_id, r.subject_id, r.rank) for r in first] == [
            (r.teacher_id, r.subject_id, r.rank) for r in second
        ]

    def test_recommendation_tie_break_by_teacher_id(self, sync_db, substitution_setup):
        occurrence = self._prepare_occurrence(sync_db, substitution_setup)
        recs = occurrence_service.get_substitute_recommendations_sync(
            sync_db,
            organization_id=substitution_setup["org_id"],
            occurrence_id=occurrence.id,
        )

        assert len(recs) >= 2
        expected_first = min(
            substitution_setup["substitute_teacher_id"],
            substitution_setup["candidate_b_teacher_id"],
        )
        assert recs[0].teacher_id == expected_first

    def test_recommendation_criteria3_applies_when_criteria1_2_tie(self, sync_db, substitution_setup):
        occurrence = self._prepare_occurrence(sync_db, substitution_setup)
        schedule_output = sync_db.get(models.ScheduleOutput, substitution_setup["schedule_output_id"])
        assert schedule_output is not None

        candidate_b_module_id = sync_db.execute(
            select(models.Module.id).where(
                models.Module.subject_id == substitution_setup["candidate_b_subject_id"]
            )
        ).scalar_one()

        older_date = occurrence.date - timedelta(days=10)
        newer_date = occurrence.date - timedelta(days=3)

        so_old = models.ScheduleOutput(
            organization_id=substitution_setup["org_id"],
            lesson_id=schedule_output.lesson_id,
            timeslot_id=schedule_output.timeslot_id,
            room_id=schedule_output.room_id,
            generation_id="gen-step2-old",
            date=older_date,
            is_draft=False,
        )
        so_new = models.ScheduleOutput(
            organization_id=substitution_setup["org_id"],
            lesson_id=schedule_output.lesson_id,
            timeslot_id=schedule_output.timeslot_id,
            room_id=schedule_output.room_id,
            generation_id="gen-step2-new",
            date=newer_date,
            is_draft=False,
        )
        sync_db.add_all([so_old, so_new])
        sync_db.flush()

        sync_db.add(models.LessonOccurrence(
            organization_id=substitution_setup["org_id"],
            schedule_output_id=so_old.id,
            date=older_date,
            status=LessonOccurrenceStatus.SUBSTITUTED,
            planned_hours=2.0,
            substitute_teacher_id=substitution_setup["candidate_b_teacher_id"],
            substitute_subject_id=substitution_setup["candidate_b_subject_id"],
            planned_teacher_id=substitution_setup["teacher_id"],
            executed_teacher_id=substitution_setup["candidate_b_teacher_id"],
            planned_module_id=substitution_setup["module_id"],
            executed_module_id=candidate_b_module_id,
            hours_given=2.0,
        ))
        sync_db.add(models.LessonOccurrence(
            organization_id=substitution_setup["org_id"],
            schedule_output_id=so_new.id,
            date=newer_date,
            status=LessonOccurrenceStatus.SUBSTITUTED,
            planned_hours=2.0,
            substitute_teacher_id=substitution_setup["substitute_teacher_id"],
            substitute_subject_id=substitution_setup["substitute_subject_id"],
            planned_teacher_id=substitution_setup["teacher_id"],
            executed_teacher_id=substitution_setup["substitute_teacher_id"],
            planned_module_id=substitution_setup["module_id"],
            executed_module_id=substitution_setup["substitute_module_id"],
            hours_given=2.0,
        ))
        sync_db.commit()

        recs = occurrence_service.get_substitute_recommendations_sync(
            sync_db,
            organization_id=substitution_setup["org_id"],
            occurrence_id=occurrence.id,
        )

        assert recs[0].teacher_id == substitution_setup["candidate_b_teacher_id"]

    def test_recommendation_empty_when_no_eligible(self, sync_db, substitution_setup):
        occurrence = self._prepare_occurrence(sync_db, substitution_setup)

        sync_db.query(models.Availability).filter(
            models.Availability.timeslot_id == substitution_setup["timeslot_id"]
        ).update({models.Availability.score: models.PreferenceLevel.IMPOSSIBLE.value})
        sync_db.commit()

        recs = occurrence_service.get_substitute_recommendations_sync(
            sync_db,
            organization_id=substitution_setup["org_id"],
            occurrence_id=occurrence.id,
        )

        assert recs == []

    def test_concurrent_substitution_confirmations_only_one_wins(self, substitution_setup):
        org_id = substitution_setup["org_id"]
        admin_id = substitution_setup["admin_id"]

        seed_db = SyncTestSession()
        try:
            occurrence, _ = occurrence_service.create_occurrence_from_block_sync(
                seed_db,
                org_id,
                substitution_setup["schedule_output_id"],
            )
            occurrence_id = occurrence.id
        finally:
            seed_db.close()

        candidate_pairs = [
            (
                substitution_setup["substitute_teacher_id"],
                substitution_setup["substitute_subject_id"],
            ),
            (
                substitution_setup["candidate_b_teacher_id"],
                substitution_setup["candidate_b_subject_id"],
            ),
        ]

        def _attempt_confirm(candidate):
            teacher_id, subject_id = candidate
            db_local = SyncTestSession()
            try:
                updated = occurrence_service.update_occurrence_sync(
                    db_local,
                    occurrence_id,
                    org_id,
                    schemas.LessonOccurrenceUpdate(
                        status=LessonOccurrenceStatus.SUBSTITUTED,
                        substitute_teacher_id=teacher_id,
                        substitute_subject_id=subject_id,
                    ),
                    decided_by_user_id=admin_id,
                )
                return {"ok": True, "teacher_id": updated.executed_teacher_id}
            except occurrence_service.OccurrenceServiceError as exc:
                return {
                    "ok": False,
                    "status_code": exc.status_code,
                    "detail": exc.detail,
                }
            finally:
                db_local.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(_attempt_confirm, pair) for pair in candidate_pairs]
            results = [future.result() for future in futures]

        success = [r for r in results if r["ok"]]
        failures = [r for r in results if not r["ok"]]

        assert len(success) == 1
        assert len(failures) == 1
        assert failures[0]["status_code"] == 409

        verify_db = SyncTestSession()
        try:
            final_occurrence = verify_db.get(models.LessonOccurrence, occurrence_id)
            assert final_occurrence is not None
            assert final_occurrence.status == LessonOccurrenceStatus.SUBSTITUTED
            assert final_occurrence.executed_teacher_id == success[0]["teacher_id"]

            planned_progress = verify_db.execute(
                select(models.ClassProgress).where(
                    models.ClassProgress.class_id == substitution_setup["class_id"],
                    models.ClassProgress.module_id == substitution_setup["module_id"],
                )
            ).scalar_one()
            assert planned_progress.hours_debt == pytest.approx(2.0)

            candidate_b_module_id = verify_db.execute(
                select(models.Module.id).where(
                    models.Module.subject_id == substitution_setup["candidate_b_subject_id"]
                )
            ).scalar_one()

            executed_progress_rows = verify_db.execute(
                select(models.ClassProgress).where(
                    models.ClassProgress.class_id == substitution_setup["class_id"],
                    models.ClassProgress.module_id.in_(
                        [substitution_setup["substitute_module_id"], candidate_b_module_id]
                    ),
                )
            ).scalars().all()

            assert sum(float(row.hours_completed) for row in executed_progress_rows) == pytest.approx(2.0)
        finally:
            verify_db.close()


# ===========================================================================
# 3. Testes de Endpoint HTTP
# ===========================================================================

class TestOccurrenceEndpoints:
    """Testes de integração para os endpoints HTTP de ocorrências."""

    @pytest_asyncio.fixture
    async def auth_headers(self, full_setup) -> dict:
        token = create_access_token(data={"sub": full_setup["admin_email"]})
        return {"Authorization": f"Bearer {token}"}

    @pytest_asyncio.fixture
    async def teacher_auth_headers(self, substitution_setup) -> dict:
        token = create_access_token(data={"sub": substitution_setup["teacher_user_email"]})
        return {"Authorization": f"Bearer {token}"}

    async def _create_open_occurrence(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        schedule_output_id: int,
    ) -> int:
        response = await async_client.post(
            "/api/v1/occurrences/",
            headers=auth_headers,
            json={"schedule_output_id": schedule_output_id},
        )
        assert response.status_code in (200, 201)
        return int(response.json()["id"])

    @pytest.mark.asyncio
    async def test_list_occurrences_empty(
        self, async_client: AsyncClient, full_setup, auth_headers
    ):
        """GET /occurrences/ sem dados → lista vazia."""
        response = await async_client.get(
            "/api/v1/occurrences/", headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_get_debts_empty(
        self, async_client: AsyncClient, full_setup, auth_headers
    ):
        """GET /occurrences/debts sem GAPs → zeros."""
        response = await async_client.get(
            "/api/v1/occurrences/debts", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_gaps"] == 0
        assert data["total_gaps_overdue"] == 0
        assert data["total_hours_owed_overdue"] == pytest.approx(0.0)
        assert isinstance(data["as_of_date"], str)
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_get_debts_includes_future_decided_gap(
        self,
        async_client: AsyncClient,
        sync_db,
        full_setup,
        auth_headers,
    ):
        future_date = date.today() + timedelta(days=5)
        future_output = models.ScheduleOutput(
            organization_id=full_setup["org_id"],
            lesson_id=full_setup["lesson_id"],
            timeslot_id=full_setup["timeslot_id"],
            room_id=full_setup["room_id"],
            generation_id="future-gap-api-001",
            date=future_date,
            is_draft=False,
        )
        sync_db.add(future_output)
        sync_db.commit()

        create_response = await async_client.post(
            "/api/v1/occurrences/",
            headers=auth_headers,
            json={"schedule_output_id": future_output.id},
        )
        assert create_response.status_code == 201
        occurrence_id = int(create_response.json()["id"])

        patch_response = await async_client.patch(
            f"/api/v1/occurrences/{occurrence_id}",
            headers=auth_headers,
            json={"status": "GAP"},
        )
        assert patch_response.status_code == 200

        debts_response = await async_client.get(
            "/api/v1/occurrences/debts",
            headers=auth_headers,
        )
        assert debts_response.status_code == 200
        debt_data = debts_response.json()
        assert debt_data["total_gaps"] == 1
        assert debt_data["total_hours_owed"] == pytest.approx(2.0)
        assert debt_data["total_gaps_overdue"] == 0
        assert debt_data["total_hours_owed_overdue"] == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_get_occurrence_not_found(
        self, async_client: AsyncClient, full_setup, auth_headers
    ):
        """GET /occurrences/9999 → 404."""
        response = await async_client.get(
            "/api/v1/occurrences/9999", headers=auth_headers
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_patch_occurrence_not_found(
        self, async_client: AsyncClient, full_setup, auth_headers
    ):
        """PATCH /occurrences/9999 → 404."""
        response = await async_client.patch(
            "/api/v1/occurrences/9999",
            headers=auth_headers,
            json={"status": "GAP"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_occurrence_from_block_returns_201_then_200(
        self,
        async_client: AsyncClient,
        full_setup,
        auth_headers,
    ):
        create_response = await async_client.post(
            "/api/v1/occurrences/",
            headers=auth_headers,
            json={"schedule_output_id": full_setup["schedule_output_id"]},
        )
        assert create_response.status_code == 201
        created = create_response.json()
        assert created["schedule_output_id"] == full_setup["schedule_output_id"]
        assert created["decided_at"] is None

        second_response = await async_client.post(
            "/api/v1/occurrences/",
            headers=auth_headers,
            json={"schedule_output_id": full_setup["schedule_output_id"]},
        )
        assert second_response.status_code == 200
        reused = second_response.json()
        assert reused["id"] == created["id"]

    @pytest.mark.asyncio
    async def test_create_occurrence_then_first_decision_applies_accounting_once(
        self,
        async_client: AsyncClient,
        sync_db,
        full_setup,
        auth_headers,
    ):
        create_response = await async_client.post(
            "/api/v1/occurrences/",
            headers=auth_headers,
            json={"schedule_output_id": full_setup["schedule_output_id"]},
        )
        assert create_response.status_code == 201
        occurrence_id = create_response.json()["id"]

        patch_response = await async_client.patch(
            f"/api/v1/occurrences/{occurrence_id}",
            headers=auth_headers,
            json={"status": "GAP"},
        )
        assert patch_response.status_code == 200
        body = patch_response.json()
        assert body["status"] == "GAP"
        assert body["decided_at"] is not None

        progress = sync_db.execute(
            select(models.ClassProgress).where(
                models.ClassProgress.class_id == full_setup["class_id"],
                models.ClassProgress.module_id == full_setup["module_id"],
            )
        ).scalar_one()
        assert float(progress.hours_debt) == pytest.approx(2.0)
        assert float(progress.hours_completed) == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_occurrence_payload_includes_context_and_decider_name(
        self,
        async_client: AsyncClient,
        full_setup,
        auth_headers,
    ):
        create_response = await async_client.post(
            "/api/v1/occurrences/",
            headers=auth_headers,
            json={"schedule_output_id": full_setup["schedule_output_id"]},
        )
        assert create_response.status_code == 201
        created = create_response.json()
        assert created["class_id"] == full_setup["class_id"]
        assert created["class_name"] == "TINF 24/27"
        assert created["subject_id"] == full_setup["subject_id"]
        assert created["subject_name"] == "Programação"
        assert created["planned_teacher_name"] == "Prof. Teste"
        assert created["decided_by_user_name"] is None

        occurrence_id = int(created["id"])
        patch_response = await async_client.patch(
            f"/api/v1/occurrences/{occurrence_id}",
            headers=auth_headers,
            json={"status": "GAP"},
        )
        assert patch_response.status_code == 200
        patched = patch_response.json()
        assert patched["decided_by_user_id"] is not None
        assert patched["decided_by_user_name"] == full_setup["admin_email"]
        assert patched["class_id"] == full_setup["class_id"]
        assert patched["subject_id"] == full_setup["subject_id"]

        list_response = await async_client.get(
            "/api/v1/occurrences/",
            headers=auth_headers,
        )
        assert list_response.status_code == 200
        rows = list_response.json()
        target = next(row for row in rows if row["id"] == occurrence_id)
        assert target["class_name"] == "TINF 24/27"
        assert target["subject_name"] == "Programação"
        assert target["decided_by_user_name"] == full_setup["admin_email"]

    @pytest.mark.asyncio
    async def test_create_occurrence_teacher_forbidden(
        self,
        async_client: AsyncClient,
        substitution_setup,
        teacher_auth_headers,
    ):
        response = await async_client.post(
            "/api/v1/occurrences/",
            headers=teacher_auth_headers,
            json={"schedule_output_id": substitution_setup["schedule_output_id"]},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_list_occurrences_teacher_forbidden(
        self,
        async_client: AsyncClient,
        substitution_setup,
        teacher_auth_headers,
    ):
        response = await async_client.get(
            "/api/v1/occurrences/",
            headers=teacher_auth_headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_get_debts_teacher_forbidden(
        self,
        async_client: AsyncClient,
        substitution_setup,
        teacher_auth_headers,
    ):
        response = await async_client.get(
            "/api/v1/occurrences/debts",
            headers=teacher_auth_headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_get_occurrence_teacher_forbidden(
        self,
        async_client: AsyncClient,
        substitution_setup,
        auth_headers,
        teacher_auth_headers,
    ):
        occurrence_id = await self._create_open_occurrence(
            async_client,
            auth_headers,
            substitution_setup["schedule_output_id"],
        )

        response = await async_client.get(
            f"/api/v1/occurrences/{occurrence_id}",
            headers=teacher_auth_headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_create_occurrence_emits_success_event_with_correlation(
        self,
        async_client: AsyncClient,
        sync_db,
        full_setup,
        auth_headers,
    ):
        response = await async_client.post(
            "/api/v1/occurrences/",
            headers=auth_headers,
            json={"schedule_output_id": full_setup["schedule_output_id"]},
        )
        assert response.status_code == 201
        occurrence_id = response.json()["id"]

        event = sync_db.execute(
            select(models.OccurrenceOperationalEvent)
            .where(
                models.OccurrenceOperationalEvent.organization_id == full_setup["org_id"],
                models.OccurrenceOperationalEvent.event_type == occurrence_service.OBS_EVENT_CREATE,
                models.OccurrenceOperationalEvent.result == occurrence_service.OBS_RESULT_SUCCESS,
            )
            .order_by(models.OccurrenceOperationalEvent.id.desc())
        ).scalars().first()

        assert event is not None
        assert event.occurrence_id == occurrence_id
        assert event.schedule_output_id == full_setup["schedule_output_id"]

    @pytest.mark.asyncio
    async def test_create_occurrence_not_found_emits_validation_failure_event(
        self,
        async_client: AsyncClient,
        sync_db,
        full_setup,
        auth_headers,
    ):
        response = await async_client.post(
            "/api/v1/occurrences/",
            headers=auth_headers,
            json={"schedule_output_id": 999999},
        )
        assert response.status_code == 404

        event = sync_db.execute(
            select(models.OccurrenceOperationalEvent)
            .where(
                models.OccurrenceOperationalEvent.organization_id == full_setup["org_id"],
                models.OccurrenceOperationalEvent.event_type == occurrence_service.OBS_EVENT_CREATE,
                models.OccurrenceOperationalEvent.result == occurrence_service.OBS_RESULT_VALIDATION_FAILURE,
            )
            .order_by(models.OccurrenceOperationalEvent.id.desc())
        ).scalars().first()

        assert event is not None
        assert event.occurrence_id is None
        assert event.schedule_output_id is None
        assert "schedule_output_id=999999" in (event.detail or "")

    @pytest.mark.asyncio
    async def test_patch_occurrence_conflict_emits_conflict_event(
        self,
        async_client: AsyncClient,
        sync_db,
        full_setup,
        auth_headers,
    ):
        occurrence_id = await self._create_open_occurrence(
            async_client,
            auth_headers,
            full_setup["schedule_output_id"],
        )

        first = await async_client.patch(
            f"/api/v1/occurrences/{occurrence_id}",
            headers=auth_headers,
            json={"status": "GAP"},
        )
        assert first.status_code == 200

        second = await async_client.patch(
            f"/api/v1/occurrences/{occurrence_id}",
            headers=auth_headers,
            json={
                "status": "SUBSTITUTED",
                "substitute_teacher_id": full_setup["substitute_teacher_id"],
                "substitute_subject_id": full_setup["substitute_subject_id"],
            },
        )
        assert second.status_code == 409

        event = sync_db.execute(
            select(models.OccurrenceOperationalEvent)
            .where(
                models.OccurrenceOperationalEvent.organization_id == full_setup["org_id"],
                models.OccurrenceOperationalEvent.event_type == occurrence_service.OBS_EVENT_DECIDE,
                models.OccurrenceOperationalEvent.result == occurrence_service.OBS_RESULT_CONFLICT,
                models.OccurrenceOperationalEvent.occurrence_id == occurrence_id,
            )
            .order_by(models.OccurrenceOperationalEvent.id.desc())
        ).scalars().first()

        assert event is not None

    @pytest.mark.asyncio
    async def test_observability_summary_counts_operational_outcomes(
        self,
        async_client: AsyncClient,
        full_setup,
        auth_headers,
    ):
        create_response = await async_client.post(
            "/api/v1/occurrences/",
            headers=auth_headers,
            json={"schedule_output_id": full_setup["schedule_output_id"]},
        )
        assert create_response.status_code == 201
        occurrence_id = create_response.json()["id"]

        gap_response = await async_client.patch(
            f"/api/v1/occurrences/{occurrence_id}",
            headers=auth_headers,
            json={"status": "GAP"},
        )
        assert gap_response.status_code == 200

        conflict_response = await async_client.patch(
            f"/api/v1/occurrences/{occurrence_id}",
            headers=auth_headers,
            json={
                "status": "SUBSTITUTED",
                "substitute_teacher_id": full_setup["substitute_teacher_id"],
                "substitute_subject_id": full_setup["substitute_subject_id"],
            },
        )
        assert conflict_response.status_code == 409

        invalid_create = await async_client.post(
            "/api/v1/occurrences/",
            headers=auth_headers,
            json={"schedule_output_id": 999999},
        )
        assert invalid_create.status_code == 404

        summary_response = await async_client.get(
            "/api/v1/occurrences/observability/summary",
            headers=auth_headers,
            params={"window_days": 30},
        )
        assert summary_response.status_code == 200

        summary = summary_response.json()
        assert summary["decisions_success"] == 1
        assert summary["conflicts"] == 1
        assert summary["validation_failures"] == 1
        assert summary["total_events"] == 4

    @pytest.mark.asyncio
    async def test_observability_summary_is_tenant_scoped(
        self,
        async_client: AsyncClient,
        sync_db,
        full_setup,
        auth_headers,
    ):
        create_response = await async_client.post(
            "/api/v1/occurrences/",
            headers=auth_headers,
            json={"schedule_output_id": full_setup["schedule_output_id"]},
        )
        assert create_response.status_code == 201

        other_org = models.Organization(name="Escola Isolada", plan_status="active")
        sync_db.add(other_org)
        sync_db.flush()

        sync_db.add(models.OccurrenceOperationalEvent(
            organization_id=other_org.id,
            event_type=occurrence_service.OBS_EVENT_DECIDE,
            result=occurrence_service.OBS_RESULT_SUCCESS,
            created_at=datetime.now(timezone.utc),
        ))
        sync_db.commit()

        expected_org_events = sync_db.execute(
            select(func.count(models.OccurrenceOperationalEvent.id)).where(
                models.OccurrenceOperationalEvent.organization_id == full_setup["org_id"]
            )
        ).scalar_one()

        response = await async_client.get(
            "/api/v1/occurrences/observability/summary",
            headers=auth_headers,
            params={"window_days": 30},
        )
        assert response.status_code == 200
        assert response.json()["total_events"] == int(expected_org_events)

    @pytest.mark.asyncio
    async def test_create_occurrence_command_invalid_action_returns_422(
        self,
        async_client: AsyncClient,
        full_setup,
        auth_headers,
    ):
        response = await async_client.post(
            "/api/v1/occurrences/",
            headers=auth_headers,
            json={
                "action": "OPEN_OCCURRENCE",
                "schedule_output_id": full_setup["schedule_output_id"],
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_occurrence_then_recommendation_and_patch_flow_works(
        self,
        async_client: AsyncClient,
        sync_db,
        substitution_setup,
        auth_headers,
    ):
        create_resp = await async_client.post(
            "/api/v1/occurrences/",
            headers=auth_headers,
            json={"schedule_output_id": substitution_setup["schedule_output_id"]},
        )
        assert create_resp.status_code == 201
        occurrence_id = create_resp.json()["id"]

        recs_resp = await async_client.get(
            f"/api/v1/occurrences/{occurrence_id}/substitutes/recommendations",
            headers=auth_headers,
        )
        assert recs_resp.status_code == 200
        recommendation = recs_resp.json()[0]

        patch_resp = await async_client.patch(
            f"/api/v1/occurrences/{occurrence_id}",
            headers=auth_headers,
            json={
                "status": "SUBSTITUTED",
                "substitute_teacher_id": recommendation["teacher_id"],
                "substitute_subject_id": recommendation["subject_id"],
            },
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["status"] == "SUBSTITUTED"

        persisted = sync_db.get(models.LessonOccurrence, occurrence_id)
        assert persisted is not None
        assert persisted.executed_teacher_id == recommendation["teacher_id"]

    @pytest.mark.asyncio
    async def test_legacy_substitution_post_uses_occurrence_source_of_truth_and_is_idempotent(
        self,
        async_client: AsyncClient,
        sync_db,
        full_setup,
        auth_headers,
    ):
        payload = {
            "lesson_id": full_setup["lesson_id"],
            "timeslot_id": full_setup["timeslot_id"],
            "original_teacher_id": full_setup["teacher_id"],
            "substitute_teacher_id": full_setup["substitute_teacher_id"],
            "date": date.today().isoformat(),
            "reason": "Falta imprevista",
        }

        first = await async_client.post(
            "/api/v1/substitutions/",
            headers=auth_headers,
            json=payload,
        )
        assert first.status_code == 200

        second = await async_client.post(
            "/api/v1/substitutions/",
            headers=auth_headers,
            json=payload,
        )
        assert second.status_code == 200

        occurrences = sync_db.execute(
            select(models.LessonOccurrence).where(
                models.LessonOccurrence.organization_id == full_setup["org_id"],
                models.LessonOccurrence.schedule_output_id == full_setup["schedule_output_id"],
            )
        ).scalars().all()
        assert len(occurrences) == 1

        occurrence = occurrences[0]
        assert occurrence.status == models.LessonOccurrenceStatus.SUBSTITUTED
        assert occurrence.substitute_teacher_id == full_setup["substitute_teacher_id"]
        assert occurrence.substitute_subject_id == full_setup["substitute_subject_id"]

        substitutions = sync_db.execute(
            select(models.Substitution).where(
                models.Substitution.lesson_id == full_setup["lesson_id"],
                models.Substitution.timeslot_id == full_setup["timeslot_id"],
                models.Substitution.date == date.today(),
                models.Substitution.original_teacher_id == full_setup["teacher_id"],
            )
        ).scalars().all()
        assert len(substitutions) == 1
        assert substitutions[0].substitute_teacher_id == full_setup["substitute_teacher_id"]

        planned_progress = sync_db.execute(
            select(models.ClassProgress).where(
                models.ClassProgress.class_id == full_setup["class_id"],
                models.ClassProgress.module_id == full_setup["module_id"],
            )
        ).scalar_one()
        executed_progress = sync_db.execute(
            select(models.ClassProgress).where(
                models.ClassProgress.class_id == full_setup["class_id"],
                models.ClassProgress.module_id == full_setup["substitute_module_id"],
            )
        ).scalar_one()
        assert float(planned_progress.hours_debt) == pytest.approx(2.0)
        assert float(executed_progress.hours_completed) == pytest.approx(2.0)

    @pytest.mark.asyncio
    async def test_legacy_and_new_occurrence_calls_keep_consistent_final_state(
        self,
        async_client: AsyncClient,
        sync_db,
        substitution_setup,
        auth_headers,
    ):
        create_resp = await async_client.post(
            "/api/v1/occurrences/",
            headers=auth_headers,
            json={"schedule_output_id": substitution_setup["schedule_output_id"]},
        )
        assert create_resp.status_code == 201
        occurrence_id = create_resp.json()["id"]

        recs_resp = await async_client.get(
            f"/api/v1/occurrences/{occurrence_id}/substitutes/recommendations",
            headers=auth_headers,
        )
        assert recs_resp.status_code == 200
        top = recs_resp.json()[0]

        patch_resp = await async_client.patch(
            f"/api/v1/occurrences/{occurrence_id}",
            headers=auth_headers,
            json={
                "status": "SUBSTITUTED",
                "substitute_teacher_id": top["teacher_id"],
                "substitute_subject_id": top["subject_id"],
            },
        )
        assert patch_resp.status_code == 200

        legacy_resp = await async_client.post(
            "/api/v1/substitutions/",
            headers=auth_headers,
            json={
                "lesson_id": substitution_setup["lesson_id"],
                "timeslot_id": substitution_setup["timeslot_id"],
                "original_teacher_id": substitution_setup["teacher_id"],
                "substitute_teacher_id": top["teacher_id"],
                "date": date.today().isoformat(),
                "reason": "Reforço compatibilidade",
            },
        )
        assert legacy_resp.status_code == 200

        persisted = sync_db.get(models.LessonOccurrence, occurrence_id)
        assert persisted is not None
        assert persisted.status == models.LessonOccurrenceStatus.SUBSTITUTED
        assert persisted.substitute_teacher_id == top["teacher_id"]
        assert persisted.substitute_subject_id == top["subject_id"]

    @pytest.mark.asyncio
    async def test_legacy_substitution_teacher_forbidden(
        self,
        async_client: AsyncClient,
        substitution_setup,
        teacher_auth_headers,
    ):
        response = await async_client.post(
            "/api/v1/substitutions/",
            headers=teacher_auth_headers,
            json={
                "lesson_id": substitution_setup["lesson_id"],
                "timeslot_id": substitution_setup["timeslot_id"],
                "original_teacher_id": substitution_setup["teacher_id"],
                "substitute_teacher_id": substitution_setup["substitute_teacher_id"],
                "date": date.today().isoformat(),
                "reason": "Sem permissao",
            },
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_legacy_substitution_cross_tenant_rejected(
        self,
        async_client: AsyncClient,
        sync_db,
        full_setup,
    ):
        other_org = models.Organization(name="Escola B", plan_status="active")
        sync_db.add(other_org)
        sync_db.flush()

        other_admin_email = "admin_cross_tenant@escola.com"
        other_admin = models.User(
            email=other_admin_email,
            hashed_password=hash_password("pass123"),
            is_active=True,
            role=models.UserRole.admin,
            organization_id=other_org.id,
        )
        sync_db.add(other_admin)
        sync_db.commit()

        token = create_access_token(data={"sub": other_admin_email})
        headers = {"Authorization": f"Bearer {token}"}

        response = await async_client.post(
            "/api/v1/substitutions/",
            headers=headers,
            json={
                "lesson_id": full_setup["lesson_id"],
                "timeslot_id": full_setup["timeslot_id"],
                "original_teacher_id": full_setup["teacher_id"],
                "substitute_teacher_id": full_setup["substitute_teacher_id"],
                "date": date.today().isoformat(),
                "reason": "Tentativa cross-tenant",
            },
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_create_occurrence_past_block_compatible_with_update_flow(
        self,
        async_client: AsyncClient,
        sync_db,
        full_setup,
        auth_headers,
    ):
        output = sync_db.get(models.ScheduleOutput, full_setup["schedule_output_id"])
        assert output is not None
        output.date = date.today() - timedelta(days=1)
        sync_db.commit()

        create_resp = await async_client.post(
            "/api/v1/occurrences/",
            headers=auth_headers,
            json={"schedule_output_id": full_setup["schedule_output_id"]},
        )
        assert create_resp.status_code == 201
        occurrence_id = create_resp.json()["id"]

        patch_resp = await async_client.patch(
            f"/api/v1/occurrences/{occurrence_id}",
            headers=auth_headers,
            json={"status": "GAP"},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["status"] == "GAP"

    @pytest.mark.asyncio
    async def test_week_schedule_payload_exposes_additive_occurrence_fields_without_occurrence(
        self,
        async_client: AsyncClient,
        full_setup,
        auth_headers,
    ):
        week_start = date.today() - timedelta(days=date.today().weekday())
        response = await async_client.get(
            "/api/v1/schedule/week",
            headers=auth_headers,
            params={"week_start": week_start.isoformat(), "class_id": full_setup["class_id"]},
        )
        assert response.status_code == 200
        payload = response.json()
        assert len(payload) >= 1

        target = next(
            slot for slot in payload
            if slot["schedule_output_id"] == full_setup["schedule_output_id"]
        )
        assert "occurrence_id" in target
        assert "occurrence_decided_at" in target
        assert "can_create_occurrence" in target
        assert "can_decide_occurrence" in target

        assert target["occurrence_id"] is None
        assert target["occurrence_decided_at"] is None
        assert target["can_create_occurrence"] is True
        assert target["can_decide_occurrence"] is False

    @pytest.mark.asyncio
    async def test_week_schedule_payload_sets_flags_and_occurrence_context_when_occurrence_exists(
        self,
        async_client: AsyncClient,
        full_setup,
        auth_headers,
    ):
        create_resp = await async_client.post(
            "/api/v1/occurrences/",
            headers=auth_headers,
            json={"schedule_output_id": full_setup["schedule_output_id"]},
        )
        assert create_resp.status_code == 201
        occurrence_id = create_resp.json()["id"]

        patch_resp = await async_client.patch(
            f"/api/v1/occurrences/{occurrence_id}",
            headers=auth_headers,
            json={"status": "GAP"},
        )
        assert patch_resp.status_code == 200

        week_start = date.today() - timedelta(days=date.today().weekday())
        response = await async_client.get(
            "/api/v1/schedule/week",
            headers=auth_headers,
            params={"week_start": week_start.isoformat(), "class_id": full_setup["class_id"]},
        )
        assert response.status_code == 200
        payload = response.json()

        target = next(
            slot for slot in payload
            if slot["schedule_output_id"] == full_setup["schedule_output_id"]
        )
        assert target["occurrence_id"] == occurrence_id
        assert target["occurrence_status"] == "GAP"
        assert target["occurrence_decided_at"] is not None
        assert target["can_create_occurrence"] is False
        assert target["can_decide_occurrence"] is True

    @pytest.mark.asyncio
    async def test_week_schedule_teacher_can_only_query_own_scope(
        self,
        async_client: AsyncClient,
        substitution_setup,
        teacher_auth_headers,
    ):
        week_start = date.today() - timedelta(days=date.today().weekday())

        own_response = await async_client.get(
            "/api/v1/schedule/week",
            headers=teacher_auth_headers,
            params={"week_start": week_start.isoformat()},
        )
        assert own_response.status_code == 200

        class_scope = await async_client.get(
            "/api/v1/schedule/week",
            headers=teacher_auth_headers,
            params={
                "week_start": week_start.isoformat(),
                "class_id": substitution_setup["class_id"],
            },
        )
        assert class_scope.status_code == 403

        other_teacher_scope = await async_client.get(
            "/api/v1/schedule/week",
            headers=teacher_auth_headers,
            params={
                "week_start": week_start.isoformat(),
                "teacher_id": substitution_setup["teacher_id"],
            },
        )
        assert other_teacher_scope.status_code == 403

    @pytest.mark.asyncio
    async def test_patch_substituted_without_teacher_returns_422(
        self, async_client: AsyncClient, full_setup, auth_headers
    ):
        """PATCH com status=SUBSTITUTED sem teacher_id → 422 (validação Pydantic)."""
        response = await async_client.patch(
            "/api/v1/occurrences/1",
            headers=auth_headers,
            json={"status": "SUBSTITUTED", "substitute_teacher_id": None},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_patch_occurrence_partial_payload_returns_422(
        self,
        async_client: AsyncClient,
        sync_db,
        full_setup,
        auth_headers,
    ):
        occurrence_service.auto_confirm_daily_sync(sync_db, full_setup["org_id"], date.today())
        occurrence = sync_db.execute(
            select(models.LessonOccurrence).where(
                models.LessonOccurrence.schedule_output_id == full_setup["schedule_output_id"]
            )
        ).scalar_one()

        response = await async_client.patch(
            f"/api/v1/occurrences/{occurrence.id}",
            headers=auth_headers,
            json={},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_patch_occurrence_rejects_unknown_fields_returns_422(
        self,
        async_client: AsyncClient,
        sync_db,
        full_setup,
        auth_headers,
    ):
        occurrence_service.auto_confirm_daily_sync(sync_db, full_setup["org_id"], date.today())
        occurrence = sync_db.execute(
            select(models.LessonOccurrence).where(
                models.LessonOccurrence.schedule_output_id == full_setup["schedule_output_id"]
            )
        ).scalar_one()

        response = await async_client.patch(
            f"/api/v1/occurrences/{occurrence.id}",
            headers=auth_headers,
            json={"status": "GAP", "unexpected": "x"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_patch_invalid_state_transition_returns_409(
        self,
        async_client: AsyncClient,
        full_setup,
        auth_headers,
    ):
        """GAP -> SUBSTITUTED deve falhar por sobrescrita destrutiva do histórico."""
        occurrence_id = await self._create_open_occurrence(
            async_client,
            auth_headers,
            full_setup["schedule_output_id"],
        )

        first = await async_client.patch(
            f"/api/v1/occurrences/{occurrence_id}",
            headers=auth_headers,
            json={"status": "GAP"},
        )
        assert first.status_code == 200

        second = await async_client.patch(
            f"/api/v1/occurrences/{occurrence_id}",
            headers=auth_headers,
            json={
                "status": "SUBSTITUTED",
                "substitute_teacher_id": full_setup["substitute_teacher_id"],
                "substitute_subject_id": full_setup["substitute_subject_id"],
            },
        )
        assert second.status_code == 409

    @pytest.mark.asyncio
    async def test_list_substitutes_with_invalid_timeslot(
        self, async_client: AsyncClient, full_setup, auth_headers
    ):
        """GET /occurrences/substitutes com timeslot inexistente → lista vazia."""
        response = await async_client.get(
            "/api/v1/occurrences/substitutes",
            headers=auth_headers,
            params={"timeslot_id": 9999, "target_date": str(date.today())},
        )
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_get_substitute_recommendations_returns_ranked_list(
        self,
        async_client: AsyncClient,
        sync_db,
        substitution_setup,
        auth_headers,
    ):
        occurrence_service.auto_confirm_daily_sync(sync_db, substitution_setup["org_id"], date.today())
        occurrence = sync_db.execute(
            select(models.LessonOccurrence).where(
                models.LessonOccurrence.schedule_output_id == substitution_setup["schedule_output_id"]
            )
        ).scalar_one()

        response = await async_client.get(
            f"/api/v1/occurrences/{occurrence.id}/substitutes/recommendations",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert data[0]["rank"] == 1
        assert "justification" in data[0]

    @pytest.mark.asyncio
    async def test_get_substitute_recommendations_not_found_returns_404(
        self,
        async_client: AsyncClient,
        substitution_setup,
        auth_headers,
    ):
        response = await async_client.get(
            "/api/v1/occurrences/999999/substitutes/recommendations",
            headers=auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_substitute_recommendations_missing_context_returns_422(
        self,
        async_client: AsyncClient,
        sync_db,
        full_setup,
        auth_headers,
    ):
        broken_occurrence = models.LessonOccurrence(
            organization_id=full_setup["org_id"],
            schedule_output_id=None,
            date=date.today(),
            status=LessonOccurrenceStatus.GIVEN,
            planned_hours=2.0,
            hours_given=2.0,
        )
        sync_db.add(broken_occurrence)
        sync_db.commit()

        response = await async_client.get(
            f"/api/v1/occurrences/{broken_occurrence.id}/substitutes/recommendations",
            headers=auth_headers,
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_substitute_recommendations_teacher_forbidden(
        self,
        async_client: AsyncClient,
        sync_db,
        substitution_setup,
        teacher_auth_headers,
    ):
        occurrence_service.auto_confirm_daily_sync(sync_db, substitution_setup["org_id"], date.today())
        occurrence = sync_db.execute(
            select(models.LessonOccurrence).where(
                models.LessonOccurrence.schedule_output_id == substitution_setup["schedule_output_id"]
            )
        ).scalar_one()

        response = await async_client.get(
            f"/api/v1/occurrences/{occurrence.id}/substitutes/recommendations",
            headers=teacher_auth_headers,
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_patch_substitution_confirm_success_with_revalidation(
        self,
        async_client: AsyncClient,
        substitution_setup,
        auth_headers,
    ):
        occurrence_id = await self._create_open_occurrence(
            async_client,
            auth_headers,
            substitution_setup["schedule_output_id"],
        )

        recs_resp = await async_client.get(
            f"/api/v1/occurrences/{occurrence_id}/substitutes/recommendations",
            headers=auth_headers,
        )
        assert recs_resp.status_code == 200
        rec = recs_resp.json()[0]

        patch_resp = await async_client.patch(
            f"/api/v1/occurrences/{occurrence_id}",
            headers=auth_headers,
            json={
                "status": "SUBSTITUTED",
                "substitute_teacher_id": rec["teacher_id"],
                "substitute_subject_id": rec["subject_id"],
            },
        )

        assert patch_resp.status_code == 200
        body = patch_resp.json()
        assert body["status"] == "SUBSTITUTED"
        assert body["decided_by_user_id"] is not None
        assert body["executed_teacher_id"] == rec["teacher_id"]

    @pytest.mark.asyncio
    async def test_patch_substitution_fails_if_candidate_becomes_ineligible(
        self,
        async_client: AsyncClient,
        sync_db,
        substitution_setup,
        auth_headers,
    ):
        occurrence_id = await self._create_open_occurrence(
            async_client,
            auth_headers,
            substitution_setup["schedule_output_id"],
        )
        occurrence = sync_db.get(models.LessonOccurrence, occurrence_id)
        assert occurrence is not None

        recs_resp = await async_client.get(
            f"/api/v1/occurrences/{occurrence_id}/substitutes/recommendations",
            headers=auth_headers,
        )
        assert recs_resp.status_code == 200
        rec = recs_resp.json()[0]

        # Simula perda de elegibilidade entre sugestão e confirmação (slot fica ocupado)
        source_output = sync_db.get(models.ScheduleOutput, substitution_setup["schedule_output_id"])
        assert source_output is not None
        lesson = models.Lesson(
            organization_id=substitution_setup["org_id"],
            class_id=substitution_setup["class_id"],
            subject_id=rec["subject_id"],
            teacher_id=rec["teacher_id"],
        )
        sync_db.add(lesson)
        sync_db.flush()

        sync_db.add(models.ScheduleOutput(
            organization_id=substitution_setup["org_id"],
            lesson_id=lesson.id,
            timeslot_id=source_output.timeslot_id,
            room_id=source_output.room_id,
            generation_id="gen-lock-candidate",
            date=occurrence.date,
            is_draft=False,
        ))
        sync_db.commit()

        patch_resp = await async_client.patch(
            f"/api/v1/occurrences/{occurrence_id}",
            headers=auth_headers,
            json={
                "status": "SUBSTITUTED",
                "substitute_teacher_id": rec["teacher_id"],
                "substitute_subject_id": rec["subject_id"],
            },
        )

        assert patch_resp.status_code == 409

    @pytest.mark.asyncio
    async def test_patch_occurrence_teacher_forbidden(
        self,
        async_client: AsyncClient,
        sync_db,
        substitution_setup,
        teacher_auth_headers,
    ):
        occurrence_service.auto_confirm_daily_sync(sync_db, substitution_setup["org_id"], date.today())
        occurrence = sync_db.execute(
            select(models.LessonOccurrence).where(
                models.LessonOccurrence.schedule_output_id == substitution_setup["schedule_output_id"]
            )
        ).scalar_one()

        response = await async_client.patch(
            f"/api/v1/occurrences/{occurrence.id}",
            headers=teacher_auth_headers,
            json={"status": "GAP"},
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_patch_closed_auto_confirmed_occurrence_returns_409(
        self,
        async_client: AsyncClient,
        sync_db,
        full_setup,
        auth_headers,
    ):
        occurrence_service.auto_confirm_daily_sync(sync_db, full_setup["org_id"], date.today())
        occurrence = sync_db.execute(
            select(models.LessonOccurrence).where(
                models.LessonOccurrence.schedule_output_id == full_setup["schedule_output_id"]
            )
        ).scalar_one()

        response = await async_client.patch(
            f"/api/v1/occurrences/{occurrence.id}",
            headers=auth_headers,
            json={"status": "GAP"},
        )

        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_legacy_substitution_suggestions_returns_410(
        self,
        async_client: AsyncClient,
        full_setup,
        auth_headers,
    ):
        response = await async_client.get(
            "/api/v1/substitutions/suggestions",
            headers=auth_headers,
            params={
                "timeslot_id": full_setup["timeslot_id"],
                "date_str": date.today().isoformat(),
                "original_teacher_id": full_setup["teacher_id"],
            },
        )

        assert response.status_code == 410

    @pytest.mark.asyncio
    async def test_list_occurrences_requires_auth(
        self, async_client: AsyncClient
    ):
        """GET /occurrences/ sem token → 401."""
        response = await async_client.get("/api/v1/occurrences/")
        assert response.status_code == 401
