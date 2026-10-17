# Ficheiro: backend/tests/integration/committed/test_resource_removal.py
"""
REMOÇÃO SEGURA DE RECURSOS
==========================
Cobre o comportamento acordado para salas, disciplinas, turmas e cursos:

- eliminar fisicamente quando for seguro;
- arquivar quando existir histórico (horários, sumários, progresso);
- remover associações de configuração na mesma transação;
- bloquear apenas a utilização publicada / operacional em curso;
- devolver `remove_effect` no contrato HTTP.

Reproduz ainda a falha de produção: um erro inesperado devolvia 500 sem
cabeçalhos CORS, o que o navegador apresentava como falha de rede.
"""

from datetime import date, time
from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.config import settings
from app.scheduler.infrastructure.models import CurricularAssignment
from app.services import class_service, room_service, subject_service
from tests._support.db_fixtures import create_teacher_profile, get_school_room_type_id
from tests._support.scheduler_v1 import (
    add_lesson,
    add_version,
    lesson_interval,
    seed_v1_assignment,
)

pytestmark = pytest.mark.postgresql

API = settings.API_V1_STR


async def _seed_scheduler(db_session: AsyncSession) -> dict:
    """Cria um contexto mínimo de planeamento sob a organização 1."""
    org_id = 1
    normal_room_type_id = await get_school_room_type_id(db_session, org_id, "Normal")
    school_year = models.SchedulerSchoolYear(
        organization_id=org_id,
        label="2025/2026",
        start_date=date(2025, 9, 15),
        hard_end_date=date(2026, 7, 31),
        timezone="Europe/Lisbon",
    )
    room = models.Room(
        organization_id=org_id,
        name="Sala Histórica",
        room_type_id=normal_room_type_id,
        capacity=30,
    )
    subject = models.Subject(
        organization_id=org_id,
        name="Disciplina Histórica",
        room_type_id=normal_room_type_id,
    )
    course = models.Course(organization_id=org_id, name="Curso Histórico", abbreviation="HIS")
    slot = models.Timeslot(
        organization_id=org_id, day_of_week=0, start_time=time(9), end_time=time(10)
    )
    db_session.add_all([school_year, room, subject, course, slot])
    await db_session.flush()

    school_class = models.Class(
        organization_id=org_id,
        name="Turma Histórica",
        size=20,
        start_year=2025,
        end_year=2026,
        grade_level=10,
        course_id=course.id,
    )
    module = models.Module(
        organization_id=org_id,
        name="Módulo",
        code="HIS-1",
        required_minutes=60,
        order=1,
        subject_id=subject.id,
    )
    db_session.add_all([school_class, module])
    await db_session.flush()

    teacher = await create_teacher_profile(
        db_session, organization_id=org_id, name="Prof. Histórico", subject_ids=[subject.id]
    )
    await db_session.flush()
    await db_session.commit()

    return {
        "org_id": org_id,
        "school_year": school_year,
        "room": room,
        "subject": subject,
        "course": course,
        "class": school_class,
        "module": module,
        "slot": slot,
        "teacher": teacher,
    }


async def _publish_block(db_session, ctx, *, key, status="ACTIVE"):
    assignment = CurricularAssignment(
        organization_id=ctx["org_id"],
        school_year_id=ctx["school_year"].id,
        class_id=ctx["class"].id,
        subject_id=ctx["subject"].id,
        teacher_id=ctx["teacher"].id,
    )
    db_session.add(assignment)
    await db_session.flush()
    seed = SimpleNamespace(
        organization=SimpleNamespace(id=ctx["org_id"]),
        year=ctx["school_year"],
        assignment=assignment,
        room=ctx["room"],
    )
    version = await add_version(db_session, seed, status=status)
    start, end = lesson_interval(date(2025, 10, 6), 9)
    lesson = await add_lesson(
        db_session,
        seed,
        version,
        stable_key=key,
        school_date=start.date(),
        start=start,
        end=end,
    )
    await db_session.commit()
    return lesson


async def _add_progress_history(db_session: AsyncSession, ctx: dict) -> None:
    db_session.add(
        models.ProgressLedgerEntry(
            organization_id=ctx["org_id"],
            source_type="MANUAL_ADJUSTMENT",
            source_id=ctx["class"].id,
            class_id=ctx["class"].id,
            module_id=ctx["module"].id,
            completed_minutes_delta=60,
            debt_minutes_delta=0,
            idempotency_key=f"progress-{ctx['class'].id}-{ctx['module'].id}",
        )
    )
    await db_session.commit()


class TestRoomRemoval:
    async def test_room_referenced_only_by_constraint_is_hard_deleted(
        self, async_client: AsyncClient, db_session: AsyncSession, clerk_admin_headers: dict
    ):
        ctx = await _seed_scheduler(db_session)
        constraint = models.Constraint(
            organization_id=ctx["org_id"],
            rule_type=models.ConstraintType.specific_room,
            class_id=ctx["class"].id,
            subject_id=ctx["subject"].id,
            room_id=ctx["room"].id,
        )
        db_session.add(constraint)
        await db_session.commit()
        constraint_id = constraint.id

        response = await async_client.delete(
            f"{API}/rooms/{ctx['room'].id}", headers=clerk_admin_headers
        )

        assert response.status_code == 200
        assert response.json()["remove_effect"] == "hard_delete"
        assert (
            await db_session.scalar(select(models.Room.id).where(models.Room.id == ctx["room"].id))
        ) is None
        assert (
            await db_session.scalar(
                select(models.Constraint.id).where(models.Constraint.id == constraint_id)
            )
        ) is None

    async def test_room_in_active_schedule_is_blocked(
        self, async_client: AsyncClient, db_session: AsyncSession, clerk_admin_headers: dict
    ):
        ctx = await _seed_scheduler(db_session)
        await _publish_block(db_session, ctx, key="room-active")

        response = await async_client.delete(
            f"{API}/rooms/{ctx['room'].id}", headers=clerk_admin_headers
        )

        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "resource_in_use"
        room = await db_session.get(models.Room, ctx["room"].id)
        assert room is not None
        assert room.is_archived is False

    async def test_room_with_removed_schedule_is_archived_and_hidden(
        self, async_client: AsyncClient, db_session: AsyncSession, clerk_admin_headers: dict
    ):
        ctx = await _seed_scheduler(db_session)
        await _publish_block(db_session, ctx, key="room-removed", status="SUPERSEDED")

        response = await async_client.delete(
            f"{API}/rooms/{ctx['room'].id}", headers=clerk_admin_headers
        )

        assert response.status_code == 200
        assert response.json()["remove_effect"] == "archive"
        await db_session.refresh(ctx["room"])
        assert ctx["room"].is_archived is True

        listed = await async_client.get(f"{API}/rooms/", headers=clerk_admin_headers)
        assert ctx["room"].id not in [row["id"] for row in listed.json()]


class TestSubjectRemoval:
    async def test_subject_with_progress_history_is_archived(
        self, async_client: AsyncClient, db_session: AsyncSession, clerk_admin_headers: dict
    ):
        ctx = await _seed_scheduler(db_session)
        await _add_progress_history(db_session, ctx)

        response = await async_client.delete(
            f"{API}/subjects/{ctx['subject'].id}", headers=clerk_admin_headers
        )

        assert response.status_code == 200
        assert response.json()["remove_effect"] == "archive"
        await db_session.refresh(ctx["subject"])
        assert ctx["subject"].is_archived is True
        # O histórico de progresso permanece intacto.
        assert (
            await db_session.scalar(
                select(models.ProgressLedgerEntry.id).where(
                    models.ProgressLedgerEntry.module_id == ctx["module"].id
                )
            )
        ) is not None

    async def test_unused_subject_is_hard_deleted(
        self, async_client: AsyncClient, db_session: AsyncSession, clerk_admin_headers: dict
    ):
        ctx = await _seed_scheduler(db_session)

        response = await async_client.delete(
            f"{API}/subjects/{ctx['subject'].id}", headers=clerk_admin_headers
        )

        assert response.status_code == 200
        assert response.json()["remove_effect"] == "hard_delete"
        assert (
            await db_session.scalar(
                select(models.Subject.id).where(models.Subject.id == ctx["subject"].id)
            )
        ) is None


class TestClassRemoval:
    async def test_class_with_progress_history_is_archived(
        self, async_client: AsyncClient, db_session: AsyncSession, clerk_admin_headers: dict
    ):
        ctx = await _seed_scheduler(db_session)
        await _add_progress_history(db_session, ctx)

        response = await async_client.delete(
            f"{API}/courses/{ctx['course'].id}/classes/{ctx['class'].id}",
            headers=clerk_admin_headers,
        )

        assert response.status_code == 200
        assert response.json()["remove_effect"] == "archive"
        await db_session.refresh(ctx["class"])
        assert ctx["class"].is_archived is True

    async def test_class_in_active_schedule_is_blocked(
        self, async_client: AsyncClient, db_session: AsyncSession, clerk_admin_headers: dict
    ):
        ctx = await _seed_scheduler(db_session)
        await _publish_block(db_session, ctx, key="class-active")

        response = await async_client.delete(
            f"{API}/courses/{ctx['course'].id}/classes/{ctx['class'].id}",
            headers=clerk_admin_headers,
        )

        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "resource_in_use"


class TestCourseRemoval:
    async def test_course_with_active_class_is_blocked(
        self, async_client: AsyncClient, db_session: AsyncSession, clerk_admin_headers: dict
    ):
        ctx = await _seed_scheduler(db_session)

        response = await async_client.delete(
            f"{API}/courses/{ctx['course'].id}", headers=clerk_admin_headers
        )

        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "course_has_classes"

    async def test_course_with_only_archived_classes_is_archived(
        self, async_client: AsyncClient, db_session: AsyncSession, clerk_admin_headers: dict
    ):
        ctx = await _seed_scheduler(db_session)
        ctx["class"].is_archived = True
        await db_session.commit()

        response = await async_client.delete(
            f"{API}/courses/{ctx['course'].id}", headers=clerk_admin_headers
        )

        assert response.status_code == 200
        assert response.json()["remove_effect"] == "archive"
        await db_session.refresh(ctx["course"])
        assert ctx["course"].is_archived is True


class TestArchivedResourcesAreNotReusable:
    async def test_archived_subject_cannot_be_assigned_to_a_class(
        self, async_client: AsyncClient, db_session: AsyncSession, clerk_admin_headers: dict
    ):
        ctx = await _seed_scheduler(db_session)
        ctx["subject"].is_archived = True
        await db_session.commit()

        response = await async_client.post(
            f"{API}/classes/{ctx['class'].id}/subjects",
            json={"subject_id": ctx["subject"].id},
            headers=clerk_admin_headers,
        )

        assert response.status_code == 400

    async def test_available_subjects_exclude_archived(
        self, async_client: AsyncClient, db_session: AsyncSession, clerk_admin_headers: dict
    ):
        ctx = await _seed_scheduler(db_session)
        ctx["subject"].is_archived = True
        await db_session.commit()

        response = await async_client.get(
            f"{API}/classes/{ctx['class'].id}/available-subjects", headers=clerk_admin_headers
        )

        assert response.status_code == 200
        assert ctx["subject"].id not in [row["id"] for row in response.json()]


class TestErrorResponseCors:
    """Um 500 inesperado tem de chegar ao browser com os cabeçalhos CORS."""

    async def test_unexpected_error_keeps_cors_headers(self, monkeypatch):
        from fastapi import Request

        from app.main import global_exception_handler

        origin = settings.CORS_ORIGINS_LIST[0]
        request = Request(
            {
                "type": "http",
                "method": "DELETE",
                "path": "/api/v1/rooms/1",
                "query_string": b"",
                "headers": [(b"origin", origin.encode())],
                "server": ("test", 80),
                "client": ("127.0.0.1", 1),
                "scheme": "https",
            }
        )
        monkeypatch.setattr("app.main.logger.error", lambda *args, **kwargs: None)

        response = await global_exception_handler(request, RuntimeError("production failure"))

        assert response.status_code == 500
        assert response.headers["access-control-allow-origin"] == origin
        assert response.headers["X-Request-ID"]

    async def test_disallowed_origin_is_not_reflected(self, monkeypatch):
        from fastapi import Request

        from app.main import global_exception_handler

        request = Request(
            {
                "type": "http",
                "method": "DELETE",
                "path": "/api/v1/rooms/1",
                "query_string": b"",
                "headers": [(b"origin", b"https://evil.example")],
                "server": ("test", 80),
                "client": ("127.0.0.1", 1),
                "scheme": "https",
            }
        )
        monkeypatch.setattr("app.main.logger.error", lambda *args, **kwargs: None)

        response = await global_exception_handler(request, RuntimeError("production failure"))

        assert response.status_code == 500
        assert "access-control-allow-origin" not in response.headers


class TestSchedulerV1References:
    """Production keeps scheduler v1 records that must not be destroyed."""

    async def test_subject_with_curricular_assignment_is_archived(self, db_session: AsyncSession):
        seed = await seed_v1_assignment(db_session)
        await db_session.commit()

        effect = await subject_service.delete_subject(
            db_session, seed.subject.id, seed.organization.id
        )
        await db_session.commit()

        assert effect == "archive"
        await db_session.refresh(seed.subject)
        assert seed.subject.is_archived is True

    async def test_class_with_curricular_assignment_is_archived(self, db_session: AsyncSession):
        seed = await seed_v1_assignment(db_session)
        await db_session.commit()

        effect = await class_service.delete_class_in_course(
            db_session, seed.course.id, seed.class_.id, seed.organization.id
        )
        await db_session.commit()

        assert effect == "archive"
        await db_session.refresh(seed.class_)
        assert seed.class_.is_archived is True

    async def test_room_with_scheduler_lesson_is_archived(self, db_session: AsyncSession):
        seed = await seed_v1_assignment(db_session)
        version = await add_version(db_session, seed, status="SUPERSEDED")
        start, end = lesson_interval(date(2026, 9, 22), 9)
        await add_lesson(
            db_session,
            seed,
            version,
            stable_key="lesson-1",
            school_date=date(2026, 9, 22),
            start=start,
            end=end,
        )
        await db_session.commit()

        effect = await room_service.delete_room(db_session, seed.room.id, seed.organization.id)
        await db_session.commit()

        assert effect == "archive"
        await db_session.refresh(seed.room)
        assert seed.room.is_archived is True

    async def test_room_without_references_is_hard_deleted(self, db_session: AsyncSession):
        seed = await seed_v1_assignment(db_session)
        await db_session.commit()

        effect = await room_service.delete_room(db_session, seed.room.id, seed.organization.id)
        await db_session.commit()

        assert effect == "hard_delete"
        assert (
            await db_session.scalar(select(models.Room.id).where(models.Room.id == seed.room.id))
        ) is None
