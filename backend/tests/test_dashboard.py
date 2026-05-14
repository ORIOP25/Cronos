"""Testes para o endpoint Dashboard V1 — Command Center."""
import pytest
from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app import models
from app.services import occurrence_service


class TestDashboardEndpoint:
    """Testes de integração para GET /api/v1/dashboard."""

    async def _seed_minimal_org(self, db_session: AsyncSession) -> dict:
        """Cria org + admin + dados mínimos."""
        org = models.Organization(name="Escola Teste Dashboard", plan_status="active")
        db_session.add(org)
        await db_session.flush()

        admin = models.User(
            email="dashadmin@escola.com",
            is_active=True,
            role=models.UserRole.admin,
            organization_id=org.id,
        )
        db_session.add(admin)
        await db_session.flush()

        from app.core.security import create_access_token
        token = create_access_token(data={"sub": "dashadmin@escola.com"})

        return {
            "org_id": org.id,
            "org_name": org.name,
            "admin_id": admin.id,
            "admin_email": admin.email,
            "auth_headers": {"Authorization": f"Bearer {token}"},
        }

    async def _seed_teacher(self, db_session: AsyncSession, org_id: int, name: str) -> models.Teacher:
        teacher = models.Teacher(name=name, organization_id=org_id)
        db_session.add(teacher)
        await db_session.flush()
        return teacher

    async def _seed_course(self, db_session: AsyncSession, org_id: int, name: str, abbr: str) -> models.Course:
        course = models.Course(name=name, abbreviation=abbr, organization_id=org_id)
        db_session.add(course)
        await db_session.flush()
        return course

    async def _seed_class(
        self, db_session: AsyncSession, org_id: int, course_id: int,
        name: str, grade_level: int, start_year: int, end_year: int, size: int = 25,
    ) -> models.Class:
        klass = models.Class(
            name=name, size=size, course_id=course_id,
            grade_level=grade_level, start_year=start_year, end_year=end_year,
            organization_id=org_id,
        )
        db_session.add(klass)
        await db_session.flush()
        return klass

    async def _seed_subject(self, db_session: AsyncSession, org_id: int, name: str) -> models.Subject:
        subject = models.Subject(name=name, required_room_type=models.RoomType.normal, organization_id=org_id)
        db_session.add(subject)
        await db_session.flush()
        return subject

    async def _seed_room(self, db_session: AsyncSession, org_id: int, name: str, room_type=None, capacity: int = 30) -> models.Room:
        if room_type is None:
            room_type = models.RoomType.normal
        room = models.Room(name=name, type=room_type, capacity=capacity, organization_id=org_id)
        db_session.add(room)
        await db_session.flush()
        return room

    async def _seed_timeslot(
        self, db_session: AsyncSession, org_id: int, day: int, start: str, end: str,
    ) -> models.Timeslot:
        from datetime import time as dt_time
        h_start, m_start = map(int, start.split(":"))
        h_end, m_end = map(int, end.split(":"))
        ts = models.Timeslot(
            organization_id=org_id,
            day_of_week=day,
            start_time=dt_time(h_start, m_start),
            end_time=dt_time(h_end, m_end),
        )
        db_session.add(ts)
        await db_session.flush()
        return ts

    async def _seed_lesson(
        self, db_session: AsyncSession, org_id: int,
        teacher_id: int, subject_id: int, class_id: int,
    ) -> models.Lesson:
        lesson = models.Lesson(
            organization_id=org_id,
            teacher_id=teacher_id,
            subject_id=subject_id,
            class_id=class_id,
        )
        db_session.add(lesson)
        await db_session.flush()
        return lesson

    async def _seed_schedule_output(
        self, db_session: AsyncSession, org_id: int,
        lesson_id: int, timeslot_id: int, room_id: int,
        generation_id: str, schedule_date: date, is_draft: bool = False,
    ) -> models.ScheduleOutput:
        so = models.ScheduleOutput(
            organization_id=org_id,
            lesson_id=lesson_id,
            timeslot_id=timeslot_id,
            room_id=room_id,
            generation_id=generation_id,
            date=schedule_date,
            is_draft=is_draft,
        )
        db_session.add(so)
        await db_session.flush()
        return so

    async def _seed_class_progress(
        self, db_session: AsyncSession,
        class_id: int, module_id: int,
        hours_completed: float = 0.0, hours_debt: float = 0.0,
    ) -> models.ClassProgress:
        cp = models.ClassProgress(
            class_id=class_id,
            module_id=module_id,
            hours_completed=hours_completed,
            hours_debt=hours_debt,
        )
        db_session.add(cp)
        await db_session.flush()
        return cp

    async def _seed_module(
        self, db_session: AsyncSession,
        name: str, code: str, hours_total: int, order: int, subject_id: int,
    ) -> models.Module:
        mod = models.Module(
            name=name, code=code, hours_total=hours_total,
            order=order, subject_id=subject_id,
        )
        db_session.add(mod)
        await db_session.flush()
        return mod

    # ------------------------------------------------------------------
    # Cenário 1: Admin acede ao dashboard com dados completos
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_dashboard_with_data(self, async_client: AsyncClient, db_session: AsyncSession):
        ctx = await self._seed_minimal_org(db_session)
        org_id = ctx["org_id"]
        today = date.today()

        t = await self._seed_teacher(db_session, org_id, "Prof. Silva")
        c = await self._seed_course(db_session, org_id, "TGPSI", "TGPSI")
        klass = await self._seed_class(db_session, org_id, c.id, "1ºA TGPSI", 10, 2025, 2028)
        subj = await self._seed_subject(db_session, org_id, "Matemática")
        room = await self._seed_room(db_session, org_id, "Sala 1.1")
        ts = await self._seed_timeslot(db_session, org_id, 0, "09:00", "09:45")
        lesson = await self._seed_lesson(db_session, org_id, t.id, subj.id, klass.id)
        gen_id = "gen-dash-test-001"
        await self._seed_schedule_output(db_session, org_id, lesson.id, ts.id, room.id, gen_id, today, is_draft=False)

        mod = await self._seed_module(db_session, name="Mod 1", code="M1", hours_total=50, order=1, subject_id=subj.id)
        await self._seed_class_progress(db_session, class_id=klass.id, module_id=mod.id, hours_completed=25.0)

        occ = models.LessonOccurrence(
            organization_id=org_id,
            schedule_output_id=None,
            date=today,
            status=models.LessonOccurrenceStatus.GIVEN,
            planned_hours=0.75,
        )
        db_session.add(occ)
        await db_session.commit()

        response = await async_client.get("/api/v1/dashboard", headers=ctx["auth_headers"])
        assert response.status_code == 200
        data = response.json()

        assert data["organization_name"] == "Escola Teste Dashboard"

        alerts = data["alerts"]
        assert alerts["pending_occurrences_today"] == 1
        assert alerts["pending_timesheets"] == 0
        assert alerts["pending_drafts"] == 0
        assert alerts["active_substitutions_today"] == 0

        resources = data["resources"]
        assert resources["teachers_count"] == 1
        assert resources["classes_count"] == 1
        assert resources["courses_count"] >= 1
        assert resources["subjects_count"] >= 1
        assert resources["rooms_count"] >= 1
        assert "normal" in resources["rooms_by_type"]

        health = data["schedule_health"]
        assert health is not None
        assert health["generation_id"] == gen_id
        assert health["blocks_count"] == 1
        assert health["classes_total"] >= 1
        assert health["duplicate_teacher_slots"] == 0
        assert health["duplicate_class_slots"] == 0

        progress = data["class_progress"]
        assert len(progress) >= 1
        cp_entry = next(p for p in progress if p["class_id"] == klass.id)
        assert cp_entry["class_name"] == "1ºA TGPSI"
        assert cp_entry["overall_percentage"] == 50.0

        debts = data["debts"]
        assert isinstance(debts["total_gaps"], int)
        assert isinstance(debts["total_hours_owed"], (int, float))
        assert isinstance(debts["as_of_date"], str)

    # ------------------------------------------------------------------
    # Cenário 2: Admin acede ao dashboard com org vazia (sem dados)
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_dashboard_empty_org(self, async_client: AsyncClient, db_session: AsyncSession):
        ctx = await self._seed_minimal_org(db_session)
        await db_session.commit()

        response = await async_client.get("/api/v1/dashboard", headers=ctx["auth_headers"])
        assert response.status_code == 200
        data = response.json()

        alerts = data["alerts"]
        assert alerts["pending_occurrences_today"] == 0
        assert alerts["pending_timesheets"] == 0
        assert alerts["pending_drafts"] == 0
        assert alerts["active_substitutions_today"] == 0

        resources = data["resources"]
        assert resources["teachers_count"] == 0
        assert resources["classes_count"] == 0
        assert resources["courses_count"] == 0
        assert resources["subjects_count"] == 0
        assert resources["rooms_count"] == 0

        assert data["schedule_health"] is None
        assert data["class_progress"] == []

        debts = data["debts"]
        assert debts["total_gaps"] == 0
        assert debts["total_hours_owed"] == 0.0

    # ------------------------------------------------------------------
    # Cenário 3: Teacher acede ao dashboard → 403 Forbidden
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_dashboard_teacher_forbidden(self, async_client: AsyncClient, db_session: AsyncSession):
        org = models.Organization(name="Escola Teacher", plan_status="active")
        db_session.add(org)
        await db_session.flush()

        from app.core.security import create_access_token
teacher_user = models.User(
            email="teacher@escola.com",
            is_active=True,
            role=models.UserRole.teacher,
            organization_id=org.id,
        )
        db_session.add(teacher_user)
        await db_session.commit()

        token = create_access_token(data={"sub": "teacher@escola.com"})
        headers = {"Authorization": f"Bearer {token}"}

        response = await async_client.get("/api/v1/dashboard", headers=headers)
        assert response.status_code == 403

    # ------------------------------------------------------------------
    # Cenário 4: Utilizador não autenticado → 401 Unauthorized
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_dashboard_unauthenticated(self, async_client: AsyncClient):
        response = await async_client.get("/api/v1/dashboard")
        assert response.status_code == 401

    # ------------------------------------------------------------------
    # Cenário 5: Organização sem geração de horário → schedule_health = None
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_dashboard_no_generation(self, async_client: AsyncClient, db_session: AsyncSession):
        ctx = await self._seed_minimal_org(db_session)
        await self._seed_teacher(db_session, ctx["org_id"], "Prof. Teste")
        await db_session.commit()

        response = await async_client.get("/api/v1/dashboard", headers=ctx["auth_headers"])
        assert response.status_code == 200
        data = response.json()

        assert data["schedule_health"] is None
        assert data["resources"]["teachers_count"] == 1

    # ------------------------------------------------------------------
    # Cenário 6: Organização sem progresso de turmas → class_progress = []
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_dashboard_no_progress(self, async_client: AsyncClient, db_session: AsyncSession):
        ctx = await self._seed_minimal_org(db_session)
        org_id = ctx["org_id"]

        course = await self._seed_course(db_session, org_id, "INFO", "INF")
        klass = await self._seed_class(db_session, org_id, course.id, "1ºA INFO", 10, 2025, 2028)
        await db_session.commit()

        response = await async_client.get("/api/v1/dashboard", headers=ctx["auth_headers"])
        assert response.status_code == 200
        data = response.json()

        progress = data["class_progress"]
        assert len(progress) == 1
        cp = progress[0]
        assert cp["class_id"] == klass.id
        assert cp["overall_percentage"] == 0.0
        assert cp["completed_hours"] == 0.0

    # ------------------------------------------------------------------
    # Cenário 7: Organização sem dívidas → debts com valores a 0
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_dashboard_no_debts(self, async_client: AsyncClient, db_session: AsyncSession):
        ctx = await self._seed_minimal_org(db_session)
        await db_session.commit()

        response = await async_client.get("/api/v1/dashboard", headers=ctx["auth_headers"])
        assert response.status_code == 200
        data = response.json()

        debts = data["debts"]
        assert debts["total_gaps"] == 0
        assert debts["total_hours_owed"] == 0.0
        assert debts["total_gaps_overdue"] == 0
        assert debts["total_hours_owed_overdue"] == 0.0
        assert debts["affected_classes_count"] == 0

    # ------------------------------------------------------------------
    # Cenário 8: Estrutura da resposta válida (Pydantic validation via endpoint)
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_dashboard_response_structure(self, async_client: AsyncClient, db_session: AsyncSession):
        ctx = await self._seed_minimal_org(db_session)
        await db_session.commit()

        response = await async_client.get("/api/v1/dashboard", headers=ctx["auth_headers"])
        assert response.status_code == 200
        data = response.json()

        expected_keys = {"alerts", "resources", "schedule_health", "class_progress", "debts", "organization_name"}
        assert set(data.keys()) == expected_keys

        alert_keys = {"pending_occurrences_today", "pending_occurrences_total", "pending_timesheets", "pending_drafts", "active_substitutions_today"}
        assert set(data["alerts"].keys()) == alert_keys

        resource_keys = {"teachers_count", "classes_count", "courses_count", "subjects_count", "rooms_count", "rooms_by_type"}
        assert set(data["resources"].keys()) == resource_keys

        assert isinstance(data["class_progress"], list)

        debt_keys = {"total_gaps", "total_hours_owed", "total_gaps_overdue", "total_hours_owed_overdue", "affected_classes_count", "as_of_date"}
        assert set(data["debts"].keys()) == debt_keys
