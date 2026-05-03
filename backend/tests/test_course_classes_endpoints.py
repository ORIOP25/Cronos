import pytest
from datetime import time, date
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models


@pytest.mark.asyncio
class TestCourseClassesEndpoints:
    async def test_create_course_class_success(self, async_client: AsyncClient, db_session: AsyncSession, admin_token_headers):
        course = models.Course(name="Curso Redes", abbreviation="CRD", organization_id=1)
        db_session.add(course)
        await db_session.commit()

        payload = {
            "name": "CRD 10A",
            "size": 26,
            "grade_level": 10,
            "start_year": 2026,
            "end_year": 2029,
        }

        response = await async_client.post(
            f"/api/v1/courses/{course.id}/classes",
            json=payload,
            headers=admin_token_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "CRD 10A"
        assert data["course_id"] == course.id
        assert data["grade_level"] == 10

    async def test_create_course_class_rejects_foreign_course(self, async_client: AsyncClient, db_session: AsyncSession, admin_token_headers):
        other_org = models.Organization(name="Outra Escola", plan_status="active")
        db_session.add(other_org)
        await db_session.flush()

        foreign_course = models.Course(name="Curso Externo", abbreviation="CEXT", organization_id=other_org.id)
        db_session.add(foreign_course)
        await db_session.commit()

        payload = {
            "name": "EXT 10A",
            "size": 22,
            "grade_level": 10,
            "start_year": 2026,
            "end_year": 2029,
        }

        response = await async_client.post(
            f"/api/v1/courses/{foreign_course.id}/classes",
            json=payload,
            headers=admin_token_headers,
        )

        assert response.status_code == 404
        assert "Curso não encontrado" in response.json()["detail"]

    async def test_update_course_class_allows_cycle_fields(self, async_client: AsyncClient, db_session: AsyncSession, admin_token_headers):
        course = models.Course(name="Curso Programação", abbreviation="CPRG", organization_id=1)
        db_session.add(course)
        await db_session.flush()

        db_class = models.Class(
            name="CPRG 10A",
            size=24,
            grade_level=10,
            start_year=2025,
            end_year=2028,
            course_id=course.id,
            organization_id=1,
        )
        db_session.add(db_class)
        await db_session.commit()

        payload = {
            "name": "CPRG 11A",
            "size": 27,
            "grade_level": 11,
            "start_year": 2026,
            "end_year": 2029,
        }

        response = await async_client.patch(
            f"/api/v1/courses/{course.id}/classes/{db_class.id}",
            json=payload,
            headers=admin_token_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "CPRG 11A"
        assert data["size"] == 27
        assert data["grade_level"] == 11
        assert data["start_year"] == 2026
        assert data["end_year"] == 2029

    async def test_delete_course_class_cascades_lessons_outputs_and_substitutions(self, async_client: AsyncClient, db_session: AsyncSession, admin_token_headers):
        course = models.Course(name="Curso Gestão", abbreviation="CGES", organization_id=1)
        subject = models.Subject(name="Gestão", organization_id=1)
        teacher_a = models.Teacher(name="Prof A", organization_id=1)
        teacher_b = models.Teacher(name="Prof B", organization_id=1)
        room = models.Room(name="Sala 1", capacity=30, type=models.RoomType.normal, organization_id=1)
        timeslot = models.Timeslot(day_of_week=1, start_time=time(9, 0), end_time=time(10, 0), organization_id=1)
        db_session.add_all([course, subject, teacher_a, teacher_b, room, timeslot])
        await db_session.flush()

        db_class = models.Class(
            name="CGES 10A",
            size=23,
            grade_level=10,
            start_year=2025,
            end_year=2028,
            course_id=course.id,
            organization_id=1,
        )
        db_session.add(db_class)
        await db_session.flush()

        lesson = models.Lesson(
            organization_id=1,
            class_id=db_class.id,
            subject_id=subject.id,
            teacher_id=teacher_a.id,
        )
        db_session.add(lesson)
        await db_session.flush()

        schedule_output = models.ScheduleOutput(
            organization_id=1,
            lesson_id=lesson.id,
            timeslot_id=timeslot.id,
            room_id=room.id,
            generation_id="gen-1",
        )
        substitution = models.Substitution(
            organization_id=1,
            lesson_id=lesson.id,
            timeslot_id=timeslot.id,
            date=date(2026, 2, 10),
            original_teacher_id=teacher_a.id,
            substitute_teacher_id=teacher_b.id,
            status="CONFIRMED",
            reason="Baixa",
        )
        db_session.add_all([schedule_output, substitution])
        await db_session.commit()

        response = await async_client.delete(
            f"/api/v1/courses/{course.id}/classes/{db_class.id}",
            headers=admin_token_headers,
        )

        assert response.status_code == 200

        class_exists = await db_session.execute(select(models.Class).where(models.Class.id == db_class.id))
        lesson_exists = await db_session.execute(select(models.Lesson).where(models.Lesson.id == lesson.id))
        schedule_exists = await db_session.execute(select(models.ScheduleOutput).where(models.ScheduleOutput.lesson_id == lesson.id))
        substitution_exists = await db_session.execute(select(models.Substitution).where(models.Substitution.lesson_id == lesson.id))

        assert class_exists.scalars().first() is None
        assert lesson_exists.scalars().first() is None
        assert schedule_exists.scalars().first() is None
        assert substitution_exists.scalars().first() is None
