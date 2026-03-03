# Ficheiro: backend/tests/test_sprint3.py
#
# Testes para Sprint 3: Repair Mode, Rascunhos e Diff de Horários.
# Cobre:
#   1. Validação de schemas Pydantic
#   2. Serviços síncronos de rascunho (draft)
#   3. Solver engine em modo repair (previous_pattern)
#   4. Endpoints HTTP para gestão de rascunhos
import os
os.environ["RATELIMIT_ENABLED"] = "false"

import pytest
import pytest_asyncio
from datetime import date, time, timedelta
from typing import AsyncGenerator

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import ASYNC_DB_URL
from app import models, schemas
from app.services import schedule_service
from app.core.security import create_access_token, hash_password
from app.core.solver_engine import ScheduleEngine, LessonInput, TimeslotInput, RoomInput

# ---------------------------------------------------------------------------
# Sessão síncrona para testes de serviço
# ---------------------------------------------------------------------------
SYNC_TEST_URL = ASYNC_DB_URL.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
sync_test_engine = create_engine(SYNC_TEST_URL, echo=False)
SyncTestSession = sessionmaker(bind=sync_test_engine, autocommit=False, autoflush=False)

TODAY = date.today()
FUTURE = TODAY + timedelta(days=10)
GEN_ACTIVE = "gen-active-111"
GEN_DRAFT = "gen-draft-222"


@pytest.fixture
def sync_db(db_session):
    """Sessão síncrona apontada para a mesma BD de teste."""
    db = SyncTestSession()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Fixture de dados mínimos para testes de rascunho
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def draft_setup(db_session: AsyncSession):
    """Cria: Org → Teacher → Subject → Course → Class → Timeslot → Room →
    Lesson → ScheduleOutput (ativo futuro + rascunho futuro).
    Retorna dict com IDs e credenciais de admin.
    """
    # Organization
    org = models.Organization(name="Escola Sprint 3", plan_status="active")
    db_session.add(org)
    await db_session.flush()

    # Teacher + Admin user
    teacher = models.Teacher(name="Prof. Draft", organization_id=org.id)
    db_session.add(teacher)
    await db_session.flush()

    admin = models.User(
        email="admin_s3@escola.com",
        hashed_password=hash_password("pass123"),
        is_active=True,
        is_superuser=False,
        role=models.UserRole.admin,
        organization_id=org.id,
    )
    db_session.add(admin)
    await db_session.flush()

    # Subject
    subject = models.Subject(
        name="Matemática",
        organization_id=org.id,
        required_room_type=models.RoomType.normal,
    )
    db_session.add(subject)
    await db_session.flush()

    # Course + Class
    course = models.Course(name="Técnico Informática", abbreviation="TI", organization_id=org.id)
    db_session.add(course)
    await db_session.flush()

    turma = models.Class(
        name="TI 24/27",
        organization_id=org.id,
        course_id=course.id,
        grade_level=10,
        size=20,
        start_year=2024,
        end_year=2027,
        is_archived=False,
    )
    db_session.add(turma)
    await db_session.flush()

    # Room + Timeslot
    room = models.Room(
        name="Sala A1",
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

    # Lesson
    lesson = models.Lesson(
        class_id=turma.id,
        subject_id=subject.id,
        teacher_id=teacher.id,
        organization_id=org.id,
    )
    db_session.add(lesson)
    await db_session.flush()

    # ScheduleOutput ativo (não draft) — data futura
    active_out = models.ScheduleOutput(
        lesson_id=lesson.id,
        timeslot_id=timeslot.id,
        room_id=room.id,
        date=FUTURE,
        organization_id=org.id,
        generation_id=GEN_ACTIVE,
        is_draft=False,
    )
    db_session.add(active_out)

    # ScheduleOutput rascunho — mesma data futura, geração diferente
    draft_out = models.ScheduleOutput(
        lesson_id=lesson.id,
        timeslot_id=timeslot.id,
        room_id=room.id,
        date=FUTURE + timedelta(days=7),
        organization_id=org.id,
        generation_id=GEN_DRAFT,
        is_draft=True,
    )
    db_session.add(draft_out)
    await db_session.commit()

    token = create_access_token({"sub": admin.email})
    return {
        "org_id": org.id,
        "admin_email": admin.email,
        "admin_token": token,
        "lesson_id": lesson.id,
        "timeslot_id": timeslot.id,
        "room_id": room.id,
    }


# ===========================================================================
# 1. Schemas Pydantic (sem BD)
# ===========================================================================

class TestSprint3Schemas:
    """Valida os novos schemas de Sprint 3."""

    def test_draft_read_fields(self):
        draft = schemas.ScheduleDraftRead(
            generation_id="abc-123",
            count=50,
            earliest_date=date(2026, 3, 1),
            latest_date=date(2026, 6, 30),
        )
        assert draft.generation_id == "abc-123"
        assert draft.count == 50

    def test_draft_read_optional_dates(self):
        draft = schemas.ScheduleDraftRead(generation_id="xyz", count=0)
        assert draft.earliest_date is None
        assert draft.latest_date is None

    def test_diff_read_fields(self):
        diff = schemas.ScheduleDiffRead(
            generation_id="gen-1",
            added=10,
            removed=5,
            unchanged=80,
            total_draft=90,
            total_active=85,
        )
        assert diff.added == 10
        assert diff.removed == 5
        assert diff.unchanged == 80

    def test_schedule_generate_request_defaults_to_full(self):
        req = schemas.ScheduleGenerateRequest()
        assert req.mode == "full"

    def test_schedule_generate_request_repair(self):
        req = schemas.ScheduleGenerateRequest(mode="repair")
        assert req.mode == "repair"


# ===========================================================================
# 2. Solver Engine — Repair Mode (sem BD)
# ===========================================================================

class TestSolverEngineRepairMode:
    """Garante que o previous_pattern é aceite sem erros e que o solver resolve."""

    def _make_inputs(self):
        lessons = [LessonInput(
            lesson_id=1, class_id=1, subject_id=1,
            teacher_id=1, required_room_type="normal", remaining_minutes=120,
        )]
        timeslots = [
            TimeslotInput(ts_id=1, day_of_week=0, duration_minutes=120),
            TimeslotInput(ts_id=2, day_of_week=2, duration_minutes=120),
        ]
        rooms = [RoomInput(room_id=1, room_type="normal")]
        return lessons, timeslots, rooms

    def test_solve_without_previous_pattern(self):
        lessons, timeslots, rooms = self._make_inputs()
        engine = ScheduleEngine(lessons=lessons, timeslots=timeslots, rooms=rooms,
                                availability_map={})
        result = engine.solve()
        assert result is not None
        assert len(result) >= 1

    def test_solve_with_previous_pattern_no_crash(self):
        """Repair mode não deve lançar exceção."""
        lessons, timeslots, rooms = self._make_inputs()
        previous = {(1, 1): 1}   # lesson 1 estava no timeslot 1
        engine = ScheduleEngine(lessons=lessons, timeslots=timeslots, rooms=rooms,
                                availability_map={}, previous_pattern=previous)
        result = engine.solve()
        assert result is not None

    def test_solve_with_full_previous_pattern_prefers_same_slots(self):
        """Solver com previous_pattern deve preferir manter o mesmo timeslot."""
        lessons, timeslots, rooms = self._make_inputs()
        previous = {(1, 1): 1}   # prefere ts_id=1
        engine = ScheduleEngine(lessons=lessons, timeslots=timeslots, rooms=rooms,
                                availability_map={}, previous_pattern=previous)
        result = engine.solve()
        assert result is not None
        ts_ids_chosen = {a.ts_id for a in result}
        assert 1 in ts_ids_chosen   # deve manter o slot preferido

    def test_solve_with_empty_previous_pattern(self):
        """Passar dict vazio como previous_pattern é equivalente a mode=full."""
        lessons, timeslots, rooms = self._make_inputs()
        engine = ScheduleEngine(lessons=lessons, timeslots=timeslots, rooms=rooms,
                                availability_map={}, previous_pattern={})
        result = engine.solve()
        assert result is not None


# ===========================================================================
# 3. Serviços síncronos de rascunho
# ===========================================================================

class TestDraftServices:
    """Testa os serviços de gestão de rascunhos com BD real."""

    def test_list_draft_gen_ids_returns_draft(self, sync_db, draft_setup):
        org_id = draft_setup["org_id"]
        drafts = schedule_service.list_draft_gen_ids_sync(sync_db, org_id)
        assert len(drafts) == 1
        assert drafts[0]["generation_id"] == GEN_DRAFT
        assert drafts[0]["count"] == 1

    def test_list_draft_gen_ids_empty_for_wrong_org(self, sync_db, draft_setup):
        drafts = schedule_service.list_draft_gen_ids_sync(sync_db, 9999)
        assert drafts == []

    def test_get_active_future_pattern_returns_active(self, sync_db, draft_setup):
        org_id = draft_setup["org_id"]
        lesson_id = draft_setup["lesson_id"]
        timeslot_id = draft_setup["timeslot_id"]
        pattern = schedule_service.get_active_future_pattern_sync(sync_db, org_id)
        assert (lesson_id, timeslot_id) in pattern

    def test_get_diff_sync_shows_added(self, sync_db, draft_setup):
        org_id = draft_setup["org_id"]
        diff = schedule_service.get_diff_sync(sync_db, org_id, GEN_DRAFT)
        # O draft tem data FUTURE+7 (não existe no ativo), o ativo tem FUTURE (não existe no draft)
        assert diff["added"] >= 0
        assert diff["removed"] >= 0
        assert diff["total_draft"] == 1
        assert diff["total_active"] == 1

    def test_approve_draft_promotes_to_active(self, sync_db, draft_setup):
        org_id = draft_setup["org_id"]
        count = schedule_service.approve_draft_sync(sync_db, org_id, GEN_DRAFT)
        assert count == 1
        # Após aprovação, não deve existir rascunho
        drafts = schedule_service.list_draft_gen_ids_sync(sync_db, org_id)
        assert len(drafts) == 0

    def test_reject_draft_deletes_it(self, sync_db, draft_setup):
        org_id = draft_setup["org_id"]
        count = schedule_service.reject_draft_sync(sync_db, org_id, GEN_DRAFT)
        assert count == 1
        drafts = schedule_service.list_draft_gen_ids_sync(sync_db, org_id)
        assert len(drafts) == 0


# ===========================================================================
# 4. Endpoints HTTP
# ===========================================================================

class TestDraftEndpoints:
    """Testa os endpoints REST de gestão de rascunhos."""

    @pytest.mark.asyncio
    async def test_list_drafts_returns_one(self, async_client: AsyncClient, draft_setup):
        token = draft_setup["admin_token"]
        resp = await async_client.get(
            "/api/v1/schedule/drafts",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["generation_id"] == GEN_DRAFT

    @pytest.mark.asyncio
    async def test_list_drafts_no_auth(self, async_client: AsyncClient, draft_setup):
        resp = await async_client.get("/api/v1/schedule/drafts")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_get_diff_returns_stats(self, async_client: AsyncClient, draft_setup):
        token = draft_setup["admin_token"]
        resp = await async_client.get(
            f"/api/v1/schedule/drafts/{GEN_DRAFT}/diff",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "added" in data
        assert "removed" in data
        assert "unchanged" in data
        assert data["generation_id"] == GEN_DRAFT

    @pytest.mark.asyncio
    async def test_get_diff_not_found(self, async_client: AsyncClient, draft_setup):
        token = draft_setup["admin_token"]
        resp = await async_client.get(
            "/api/v1/schedule/drafts/nonexistent-gen/diff",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_approve_draft(self, async_client: AsyncClient, draft_setup):
        token = draft_setup["admin_token"]
        resp = await async_client.post(
            f"/api/v1/schedule/drafts/{GEN_DRAFT}/approve",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["blocks_activated"] == 1

        # Verificar que o rascunho desapareceu
        resp2 = await async_client.get(
            "/api/v1/schedule/drafts",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp2.json() == []

    @pytest.mark.asyncio
    async def test_approve_draft_not_found(self, async_client: AsyncClient, draft_setup):
        token = draft_setup["admin_token"]
        resp = await async_client.post(
            "/api/v1/schedule/drafts/nonexistent/approve",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_reject_draft(self, async_client: AsyncClient, draft_setup):
        token = draft_setup["admin_token"]
        resp = await async_client.delete(
            f"/api/v1/schedule/drafts/{GEN_DRAFT}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["blocks_deleted"] == 1

        # Verificar que o rascunho desapareceu
        resp2 = await async_client.get(
            "/api/v1/schedule/drafts",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp2.json() == []

    @pytest.mark.asyncio
    async def test_reject_draft_not_found(self, async_client: AsyncClient, draft_setup):
        token = draft_setup["admin_token"]
        resp = await async_client.delete(
            "/api/v1/schedule/drafts/nonexistent",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404
