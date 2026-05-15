# Ficheiro: backend/tests/test_schedule_draft_lifecycle.py
#
# Testes para Sprint 3: Repair Mode, Rascunhos e Diff de Horários.
import os
os.environ["RATELIMIT_ENABLED"] = "false"

import pytest
import pytest_asyncio
from unittest.mock import patch
from datetime import date, time, timedelta
from typing import AsyncGenerator

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import ASYNC_DB_URL
from app import models
from app import schemas
from tests.conftest import mock_clerk_payload
from app.services import schedule_service
from app.core.solver_engine import ScheduleEngine, LessonInput, TimeslotInput, RoomInput

# sync_db fixture is provided by conftest.py (shared across all test files)

TODAY = date.today()
FUTURE = TODAY + timedelta(days=10)
GEN_ACTIVE = "gen-active-111"
GEN_DRAFT = "gen-draft-222"
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
        clerk_user_id="draft_admin_001",
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

    return {
        "organization_id": org.id,
        "admin_email": admin.email,
        "admin_clerk_id": "draft_admin_001",
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
        organization_id = draft_setup["organization_id"]
        drafts = schedule_service.list_draft_gen_ids_sync(sync_db, organization_id)
        assert len(drafts) == 1
        assert drafts[0]["generation_id"] == GEN_DRAFT
        assert drafts[0]["count"] == 1

    def test_list_draft_gen_ids_empty_for_wrong_org(self, sync_db, draft_setup):
        drafts = schedule_service.list_draft_gen_ids_sync(sync_db, 9999)
        assert drafts == []

    def test_get_active_future_pattern_returns_active(self, sync_db, draft_setup):
        organization_id = draft_setup["organization_id"]
        lesson_id = draft_setup["lesson_id"]
        timeslot_id = draft_setup["timeslot_id"]
        pattern = schedule_service.get_active_future_pattern_sync(sync_db, organization_id)
        assert (lesson_id, timeslot_id) in pattern

    def test_get_diff_sync_shows_added(self, sync_db, draft_setup):
        organization_id = draft_setup["organization_id"]
        diff = schedule_service.get_diff_sync(sync_db, organization_id, GEN_DRAFT)
        assert diff["added"] >= 0
        assert diff["removed"] >= 0
        assert diff["total_draft"] == 1

    def test_approve_draft_promotes_to_active(self, sync_db, draft_setup):
        organization_id = draft_setup["organization_id"]
        count = schedule_service.approve_draft_sync(sync_db, organization_id, GEN_DRAFT)
        assert count == 1
        # Após aprovação, não deve existir rascunho
        drafts = schedule_service.list_draft_gen_ids_sync(sync_db, organization_id)
        assert len(drafts) == 0

    def test_approve_draft_preserves_published_inside_stability_window(self, sync_db, draft_setup):
        organization_id = draft_setup["organization_id"]

        sync_db.add(models.OrganizationSettings(
            organization_id=organization_id,
            school_start_date=TODAY - timedelta(days=60),
            school_target_end_date=TODAY + timedelta(days=120),
            school_hard_end_date=TODAY + timedelta(days=120),
            repair_stability_window_days=14,
        ))

        lesson_id = draft_setup["lesson_id"]
        timeslot_id = draft_setup["timeslot_id"]
        room_id = draft_setup["room_id"]

        # Draft adicional dentro da janela congelada: não pode ser ativado
        in_window_draft = models.ScheduleOutput(
            lesson_id=lesson_id,
            timeslot_id=timeslot_id,
            room_id=room_id,
            date=TODAY + timedelta(days=3),
            organization_id=organization_id,
            generation_id=GEN_DRAFT,
            is_draft=True,
        )
        sync_db.add(in_window_draft)
        sync_db.commit()

        count = schedule_service.approve_draft_sync(sync_db, organization_id, GEN_DRAFT)
        assert count == 1

        active_dates = {
            row.date
            for row in sync_db.query(models.ScheduleOutput)
            .filter(
                models.ScheduleOutput.organization_id == organization_id,
                models.ScheduleOutput.is_draft.is_(False),
            )
            .all()
        }

        assert FUTURE in active_dates  # mantido (dentro da janela)
        assert FUTURE + timedelta(days=7) in active_dates  # promovido (fora da janela)
        assert TODAY + timedelta(days=3) not in active_dates  # bloqueado por janela

        drafts = schedule_service.list_draft_gen_ids_sync(sync_db, organization_id)
        assert drafts == []

    def test_reject_draft_deletes_it(self, sync_db, draft_setup):
        organization_id = draft_setup["organization_id"]
        count = schedule_service.reject_draft_sync(sync_db, organization_id, GEN_DRAFT)
        assert count == 1
        drafts = schedule_service.list_draft_gen_ids_sync(sync_db, organization_id)
        assert len(drafts) == 0

    def test_clear_schedule_window_sync_deletes_only_unconfirmed_outputs(self, sync_db, draft_setup):
        organization_id = draft_setup["organization_id"]

        active = (
            sync_db.query(models.ScheduleOutput)
            .filter(
                models.ScheduleOutput.organization_id == organization_id,
                models.ScheduleOutput.is_draft.is_(False),
            )
            .first()
        )
        assert active is not None

        # Mantem este output protegido por ocorrencia
        protected_occurrence = models.LessonOccurrence(
            organization_id=organization_id,
            schedule_output_id=active.id,
            date=active.date,
            status=models.LessonOccurrenceStatus.GIVEN,
            hours_given=2.0,
        )
        sync_db.add(protected_occurrence)

        # Novo output sem ocorrencia dentro da mesma janela
        removable_output = models.ScheduleOutput(
            lesson_id=active.lesson_id,
            timeslot_id=active.timeslot_id,
            room_id=active.room_id,
            date=active.date + timedelta(days=1),
            organization_id=organization_id,
            generation_id="gen-window-delete",
            is_draft=False,
        )
        sync_db.add(removable_output)
        sync_db.commit()
        removable_output_id = removable_output.id

        deleted = schedule_service.clear_schedule_window_sync(
            sync_db,
            organization_id,
            active.date,
            active.date + timedelta(days=1),
        )
        sync_db.commit()

        assert deleted == 1

        remaining_ids = {
            row.id
            for row in sync_db.query(models.ScheduleOutput)
            .filter(
                models.ScheduleOutput.organization_id == organization_id,
                models.ScheduleOutput.is_draft.is_(False),
            )
            .all()
        }
        assert active.id in remaining_ids
        assert removable_output_id not in remaining_ids

    def test_clear_schedule_window_sync_scoped_by_org(self, sync_db, draft_setup):
        organization_id = draft_setup["organization_id"]

        other_org = models.Organization(name="Outra Org", plan_status="active")
        sync_db.add(other_org)
        sync_db.flush()

        teacher = models.Teacher(name="Prof Outra", organization_id=other_org.id)
        subject = models.Subject(
            name="Outra Disciplina",
            organization_id=other_org.id,
            required_room_type=models.RoomType.normal,
        )
        course = models.Course(name="Curso O", abbreviation="CO", organization_id=other_org.id)
        sync_db.add_all([teacher, subject, course])
        sync_db.flush()

        klass = models.Class(
            name="Outra Turma",
            organization_id=other_org.id,
            course_id=course.id,
            grade_level=10,
            size=20,
            start_year=2024,
            end_year=2027,
            is_archived=False,
        )
        room = models.Room(
            name="Sala O1",
            capacity=20,
            type=models.RoomType.normal,
            organization_id=other_org.id,
        )
        ts = models.Timeslot(
            day_of_week=0,
            start_time=time(8, 0),
            end_time=time(10, 0),
            organization_id=other_org.id,
        )

        sync_db.add_all([klass, room, ts])
        sync_db.flush()

        lesson = models.Lesson(
            class_id=klass.id,
            subject_id=subject.id,
            teacher_id=teacher.id,
            organization_id=other_org.id,
        )
        sync_db.add(lesson)
        sync_db.flush()

        other_output = models.ScheduleOutput(
            lesson_id=lesson.id,
            timeslot_id=ts.id,
            room_id=room.id,
            date=FUTURE,
            organization_id=other_org.id,
            generation_id="gen-other-org",
            is_draft=False,
        )
        sync_db.add(other_output)
        sync_db.commit()

        deleted = schedule_service.clear_schedule_window_sync(
            sync_db,
            organization_id,
            FUTURE,
            FUTURE + timedelta(days=1),
        )
        sync_db.commit()

        assert deleted >= 0
        assert (
            sync_db.query(models.ScheduleOutput)
            .filter(models.ScheduleOutput.id == other_output.id)
            .first()
            is not None
        )

    def test_create_schedule_output_with_date_sync_replaces_unconfirmed_conflict(self, sync_db, draft_setup):
        organization_id = draft_setup["organization_id"]

        active = (
            sync_db.query(models.ScheduleOutput)
            .filter(
                models.ScheduleOutput.organization_id == organization_id,
                models.ScheduleOutput.is_draft.is_(False),
            )
            .first()
        )
        assert active is not None

        source_lesson = sync_db.query(models.Lesson).filter(models.Lesson.id == active.lesson_id).first()
        assert source_lesson is not None

        replacement_subject = models.Subject(
            name="Disciplina Substituta",
            organization_id=organization_id,
            required_room_type=models.RoomType.normal,
        )
        sync_db.add(replacement_subject)
        sync_db.flush()

        replacement_lesson = models.Lesson(
            class_id=source_lesson.class_id,
            subject_id=replacement_subject.id,
            teacher_id=source_lesson.teacher_id,
            organization_id=organization_id,
        )
        sync_db.add(replacement_lesson)
        sync_db.commit()

        schedule_service.create_schedule_output_with_date_sync(
            db=sync_db,
            lesson_id=replacement_lesson.id,
            timeslot_id=active.timeslot_id,
            room_id=active.room_id,
            output_date=active.date,
            organization_id=organization_id,
            gen_id="gen-replace-conflict",
            is_draft=False,
        )
        sync_db.commit()

        same_slot_outputs = (
            sync_db.query(models.ScheduleOutput)
            .join(models.Lesson, models.ScheduleOutput.lesson_id == models.Lesson.id)
            .filter(
                models.ScheduleOutput.organization_id == organization_id,
                models.ScheduleOutput.is_draft.is_(False),
                models.ScheduleOutput.date == active.date,
                models.ScheduleOutput.timeslot_id == active.timeslot_id,
                models.Lesson.class_id == source_lesson.class_id,
            )
            .all()
        )

        assert len(same_slot_outputs) == 1
        assert same_slot_outputs[0].lesson_id == replacement_lesson.id

    def test_create_schedule_output_with_date_sync_does_not_override_confirmed_conflict(self, sync_db, draft_setup):
        organization_id = draft_setup["organization_id"]

        active = (
            sync_db.query(models.ScheduleOutput)
            .filter(
                models.ScheduleOutput.organization_id == organization_id,
                models.ScheduleOutput.is_draft.is_(False),
            )
            .first()
        )
        assert active is not None

        source_lesson = sync_db.query(models.Lesson).filter(models.Lesson.id == active.lesson_id).first()
        assert source_lesson is not None

        sync_db.add(models.LessonOccurrence(
            organization_id=organization_id,
            schedule_output_id=active.id,
            date=active.date,
            status=models.LessonOccurrenceStatus.GIVEN,
            hours_given=2.0,
        ))

        replacement_subject = models.Subject(
            name="Disciplina Bloqueada",
            organization_id=organization_id,
            required_room_type=models.RoomType.normal,
        )
        sync_db.add(replacement_subject)
        sync_db.flush()

        replacement_lesson = models.Lesson(
            class_id=source_lesson.class_id,
            subject_id=replacement_subject.id,
            teacher_id=source_lesson.teacher_id,
            organization_id=organization_id,
        )
        sync_db.add(replacement_lesson)
        sync_db.commit()

        schedule_service.create_schedule_output_with_date_sync(
            db=sync_db,
            lesson_id=replacement_lesson.id,
            timeslot_id=active.timeslot_id,
            room_id=active.room_id,
            output_date=active.date,
            organization_id=organization_id,
            gen_id="gen-blocked-conflict",
            is_draft=False,
        )
        sync_db.commit()

        same_slot_outputs = (
            sync_db.query(models.ScheduleOutput)
            .join(models.Lesson, models.ScheduleOutput.lesson_id == models.Lesson.id)
            .filter(
                models.ScheduleOutput.organization_id == organization_id,
                models.ScheduleOutput.is_draft.is_(False),
                models.ScheduleOutput.date == active.date,
                models.ScheduleOutput.timeslot_id == active.timeslot_id,
                models.Lesson.class_id == source_lesson.class_id,
            )
            .all()
        )

        assert len(same_slot_outputs) == 1
        assert same_slot_outputs[0].id == active.id


# ===========================================================================
# 4. Endpoints HTTP
# ===========================================================================

class TestDraftEndpoints:
    """Testa os endpoints REST de gestão de rascunhos."""

    async def _draft_call(self, async_client, endpoint, method="GET", json_data=None):
        payload = mock_clerk_payload("draft_admin_001", "org_001", "admin")
        headers = {"Authorization": "Bearer test_draft_admin_001"}
        with patch("app.api.deps.get_clerk_payload", return_value=payload):
            if method == "GET":
                return await async_client.get(endpoint, headers=headers)
            elif method == "POST":
                return await async_client.post(endpoint, headers=headers, json=json_data)
            elif method == "DELETE":
                return await async_client.delete(endpoint, headers=headers)

    @pytest.mark.asyncio
    async def test_list_drafts_returns_one(self, async_client: AsyncClient, draft_setup):
        resp = await self._draft_call(async_client, "/api/v1/schedule/drafts")
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
        resp = await self._draft_call(async_client, f"/api/v1/schedule/drafts/{GEN_DRAFT}/diff")
        assert resp.status_code == 200
        data = resp.json()
        assert "added" in data
        assert "removed" in data
        assert "unchanged" in data
        assert data["generation_id"] == GEN_DRAFT

    @pytest.mark.asyncio
    async def test_get_diff_not_found(self, async_client: AsyncClient, draft_setup):
        resp = await self._draft_call(async_client, "/api/v1/schedule/drafts/nonexistent-gen/diff")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_approve_draft(self, async_client: AsyncClient, draft_setup):
        resp = await self._draft_call(async_client, f"/api/v1/schedule/drafts/{GEN_DRAFT}/approve", "POST")
        assert resp.status_code == 200
        data = resp.json()
        assert data["blocks_activated"] == 1
        resp2 = await self._draft_call(async_client, "/api/v1/schedule/drafts")
        assert resp2.json() == []

    @pytest.mark.asyncio
    async def test_approve_draft_not_found(self, async_client: AsyncClient, draft_setup):
        resp = await self._draft_call(async_client, "/api/v1/schedule/drafts/nonexistent/approve", "POST")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_reject_draft(self, async_client: AsyncClient, draft_setup):
        resp = await self._draft_call(async_client, f"/api/v1/schedule/drafts/{GEN_DRAFT}", "DELETE")
        assert resp.status_code == 200
        data = resp.json()
        assert data["blocks_deleted"] == 1
        resp2 = await self._draft_call(async_client, "/api/v1/schedule/drafts")
        assert resp2.json() == []

    @pytest.mark.asyncio
    async def test_reject_draft_not_found(self, async_client: AsyncClient, draft_setup):
        resp = await self._draft_call(async_client, "/api/v1/schedule/drafts/nonexistent", "DELETE")
        assert resp.status_code == 404
