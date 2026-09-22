from httpx import AsyncClient
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import models


class TestCoursesEndpoints:
    async def test_get_courses_pagination(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        clerk_admin_headers,
    ):
        db_session.add_all(
            models.Course(
                name=f"Curso {index:02d}",
                abbreviation=f"C{index}",
                organization_id=1,
            )
            for index in range(15)
        )
        await db_session.commit()

        first = await async_client.get(
            "/api/v1/courses/?skip=0&limit=10",
            headers=clerk_admin_headers,
        )
        second = await async_client.get(
            "/api/v1/courses/?skip=10&limit=10",
            headers=clerk_admin_headers,
        )

        assert first.status_code == second.status_code == 200
        assert len(first.json()) == 10
        assert first.json()[0]["name"] == "Curso 00"
        assert len(second.json()) == 5
        assert second.json()[0]["name"] == "Curso 10"

    async def test_get_course_details_structure(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        clerk_admin_headers,
    ):
        subject = models.Subject(name="Matematica", organization_id=1)
        course = models.Course(name="Ciencias", abbreviation="CT-CIE", organization_id=1)
        db_session.add_all([subject, course])
        await db_session.flush()
        await db_session.execute(
            insert(models.course_subject_link).values(
                organization_id=1,
                course_id=course.id,
                subject_id=subject.id,
            )
        )
        db_session.add(
            models.Class(
                name="CT-CIE 10A",
                course_id=course.id,
                organization_id=1,
                grade_level=10,
                start_year=2025,
                end_year=2026,
                size=25,
            )
        )
        await db_session.commit()

        response = await async_client.get(
            f"/api/v1/courses/{course.id}",
            headers=clerk_admin_headers,
        )

        assert response.status_code == 200
        assert response.json()["name"] == "Ciencias"
        assert response.json()["subjects"][0]["name"] == "Matematica"
        assert len(response.json()["classes"]) == 1

    async def test_patch_course_abbreviation_conflict(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        clerk_admin_headers,
    ):
        first = models.Course(name="Curso A", abbreviation="AAA", organization_id=1)
        second = models.Course(name="Curso B", abbreviation="BBB", organization_id=1)
        db_session.add_all([first, second])
        await db_session.commit()

        response = await async_client.patch(
            f"/api/v1/courses/{second.id}",
            json={"abbreviation": "AAA"},
            headers=clerk_admin_headers,
        )

        assert response.status_code == 400
        assert "processar" in response.json()["detail"]["message"]

    async def test_patch_course_abbreviation_invalid_length_422(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        clerk_admin_headers,
    ):
        course = models.Course(name="Curso A", abbreviation="AAA", organization_id=1)
        db_session.add(course)
        await db_session.commit()

        response = await async_client.patch(
            f"/api/v1/courses/{course.id}",
            json={"abbreviation": "A"},
            headers=clerk_admin_headers,
        )

        assert response.status_code == 422

    async def test_patch_course_subjects_replace(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        clerk_admin_headers,
    ):
        first = models.Subject(name="Mat", organization_id=1)
        second = models.Subject(name="Port", organization_id=1)
        course = models.Course(name="Curso Misto", abbreviation="CM", organization_id=1)
        db_session.add_all([first, second, course])
        await db_session.flush()
        await db_session.execute(
            insert(models.course_subject_link).values(
                organization_id=1,
                course_id=course.id,
                subject_id=first.id,
            )
        )
        await db_session.commit()

        response = await async_client.patch(
            f"/api/v1/courses/{course.id}",
            json={"subject_ids": [second.id]},
            headers=clerk_admin_headers,
        )

        assert response.status_code == 200
        assert [row["id"] for row in response.json()["subjects"]] == [second.id]

    async def test_delete_course_dependency_protection(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        clerk_admin_headers,
    ):
        course = models.Course(name="Curso Perigoso", abbreviation="DANGER", organization_id=1)
        db_session.add(course)
        await db_session.flush()
        linked_class = models.Class(
            name="Turma 1",
            course_id=course.id,
            organization_id=1,
            grade_level=10,
            start_year=2025,
            end_year=2026,
            size=20,
        )
        db_session.add(linked_class)
        await db_session.commit()

        blocked = await async_client.delete(
            f"/api/v1/courses/{course.id}",
            headers=clerk_admin_headers,
        )
        assert blocked.status_code == 400
        assert blocked.json()["detail"]["code"] == "course_has_classes"
        assert blocked.json()["detail"]["message"] == "Apague primeiro as turmas deste curso."

        await db_session.delete(linked_class)
        await db_session.commit()
        deleted = await async_client.delete(
            f"/api/v1/courses/{course.id}",
            headers=clerk_admin_headers,
        )
        assert deleted.status_code == 200

    async def test_delete_course_with_subjects(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        clerk_admin_headers,
    ):
        subject = models.Subject(name="Matematica", organization_id=1)
        course = models.Course(name="Curso Misto", abbreviation="CM", organization_id=1)
        db_session.add_all([subject, course])
        await db_session.flush()
        await db_session.execute(
            insert(models.course_subject_link).values(
                organization_id=1,
                course_id=course.id,
                subject_id=subject.id,
            )
        )
        await db_session.commit()

        response = await async_client.delete(
            f"/api/v1/courses/{course.id}",
            headers=clerk_admin_headers,
        )

        assert response.status_code == 200
