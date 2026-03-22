# Ficheiro: backend/tests/test_occurrences.py
#
# Testes para Sprint 2: LessonOccurrence, auto-confirmação e dívidas de horas.
# Cobre:
#   1. Validação de schemas Pydantic (sem BD)
#   2. Serviço de auto-confirmação diária (com BD síncrona)
#   3. Endpoints HTTP (via async_client)
import os
os.environ["RATELIMIT_ENABLED"] = "false"

import pytest
import pytest_asyncio
from datetime import date, time
from typing import AsyncGenerator

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import ASYNC_DB_URL
from app import models, schemas
from app.models import LessonOccurrenceStatus
from app.services import occurrence_service
from app.core.security import create_access_token, hash_password

# ---------------------------------------------------------------------------
# Sessão síncrona para testes do serviço
# ---------------------------------------------------------------------------
SYNC_TEST_URL = ASYNC_DB_URL.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
sync_test_engine = create_engine(SYNC_TEST_URL, echo=False)
SyncTestSession = sessionmaker(bind=sync_test_engine, autocommit=False, autoflush=False)


@pytest.fixture
def sync_db(db_session):
    """Fornece uma sessão síncrona apontada para a mesma BD de teste."""
    db = SyncTestSession()
    try:
        yield db
    finally:
        db.close()


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

    module = models.Module(
        name="M1 - Introdução",
        hours_total=25,
        order=1,
        subject_id=subject.id,
    )
    db_session.add(module)
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

    # 7. Lesson (definição abstrata)
    lesson = models.Lesson(
        organization_id=org.id,
        class_id=class_.id,
        subject_id=subject.id,
        teacher_id=teacher.id,
    )
    db_session.add(lesson)
    await db_session.flush()

    # 8. ScheduleOutput para hoje
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
        "org_id": org.id,
        "teacher_id": teacher.id,
        "subject_id": subject.id,
        "module_id": module.id,
        "class_id": class_.id,
        "room_id": room.id,
        "timeslot_id": timeslot.id,
        "lesson_id": lesson.id,
        "schedule_output_id": schedule_output.id,
        "admin_email": admin.email,
    }


# ===========================================================================
# 1. Testes de Schema (sem BD)
# ===========================================================================

class TestLessonOccurrenceSchemas:
    """Validação das regras Pydantic dos schemas de Sprint 2."""

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
            )
        errors = exc_info.value.errors()
        assert any("substitute_teacher_id" in str(e) for e in errors)

    def test_update_status_substituted_with_teacher_valid(self):
        """SUBSTITUTED com professor → válido."""
        payload = schemas.LessonOccurrenceUpdate(
            status=LessonOccurrenceStatus.SUBSTITUTED,
            substitute_teacher_id=42,
            substitute_subject_id=7,
        )
        assert payload.substitute_teacher_id == 42

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

    def test_debt_list_read_schema(self):
        """DebtListRead agrega corretamente."""
        debt_list = schemas.DebtListRead(
            total_gaps=2,
            total_hours_owed=4.0,
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
            org_id=org_id,
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
        assert result.items == []

    def test_get_debts_counts_gap_occurrences(self, sync_db, full_setup):
        """Uma ocorrência GAP deve aparecer nas dívidas."""
        org_id = full_setup["org_id"]
        today = date.today()
        output_id = full_setup["schedule_output_id"]

        gap = models.LessonOccurrence(
            org_id=org_id,
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
        assert len(result.items) == 1

    def test_get_occurrence_returns_none_for_wrong_org(self, sync_db, full_setup):
        """Não deve retornar ocorrências de outra organização (tenant isolation)."""
        result = occurrence_service.get_occurrence_sync(sync_db, 9999, org_id=9999)
        assert result is None


# ===========================================================================
# 3. Testes de Endpoint HTTP
# ===========================================================================

class TestOccurrenceEndpoints:
    """Testes de integração para os endpoints HTTP de ocorrências."""

    @pytest_asyncio.fixture
    async def auth_headers(self, full_setup) -> dict:
        token = create_access_token(data={"sub": full_setup["admin_email"]})
        return {"Authorization": f"Bearer {token}"}

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
        assert data["items"] == []

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
    async def test_list_occurrences_requires_auth(
        self, async_client: AsyncClient
    ):
        """GET /occurrences/ sem token → 401."""
        response = await async_client.get("/api/v1/occurrences/")
        assert response.status_code == 401
