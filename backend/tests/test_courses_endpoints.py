import pytest
from httpx import AsyncClient
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession
from app import models

@pytest.mark.asyncio
class TestCoursesEndpoints:
    """
    Testes de Integração para os Endpoints de Cursos (CRUD Completo).
    """

    async def test_get_courses_pagination(self, async_client: AsyncClient, db_session: AsyncSession, admin_token_headers):
        """
        📈 Scalability: Testa se a paginação (limit/skip) funciona corretamente.
        """
        # 1. Criar 15 cursos dummy com Zero Padding para garantir ordem alfabética correta
        # Curso 00, Curso 01, ... Curso 14
        for i in range(15):
            c = models.Course(name=f"Curso {i:02d}", abbreviation=f"C{i}", organization_id=1)
            db_session.add(c)
        await db_session.commit()

        # 2. Pedir página 1 (Limit 10) -> Deve vir Curso 00 até Curso 09
        response = await async_client.get("/api/v1/courses/?skip=0&limit=10", headers=admin_token_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 10
        assert data[0]["name"] == "Curso 00"

        # 3. Pedir página 2 (Skip 10) -> Deve vir Curso 10 até Curso 14
        response_p2 = await async_client.get("/api/v1/courses/?skip=10&limit=10", headers=admin_token_headers)
        assert response_p2.status_code == 200
        data_p2 = response_p2.json()
        assert len(data_p2) == 5  # Sobraram 5
        assert data_p2[0]["name"] == "Curso 10" 

    async def test_get_course_details_structure(self, async_client: AsyncClient, db_session: AsyncSession, admin_token_headers):
        """
        ⚡ Optimization: Verifica se o endpoint devolve a estrutura 'CourseDetailRead'
        """
        subject = models.Subject(name="Matemática", organization_id=1)
        db_session.add(subject)
        await db_session.commit()
        
        course = models.Course(name="Ciências", abbreviation="CT-CIE", organization_id=1)
        db_session.add(course)
        await db_session.flush()
        await db_session.execute(
            insert(models.course_subject_link).values(
                organization_id=1,
                course_id=course.id,
                subject_id=subject.id,
            )
        )
        await db_session.commit()

        cls = models.Class(name="CT-CIE 10A", course_id=course.id, organization_id=1, grade_level=10, start_year=2025, end_year=2026, size=25)
        db_session.add(cls)
        await db_session.commit()

        response = await async_client.get(f"/api/v1/courses/{course.id}", headers=admin_token_headers)
        assert response.status_code == 200
        data = response.json()

        assert data["name"] == "Ciências"
        assert len(data["subjects"]) == 1
        assert data["subjects"][0]["name"] == "Matemática"
        assert len(data["classes"]) == 1

    async def test_patch_course_abbreviation_conflict(self, async_client: AsyncClient, db_session: AsyncSession, admin_token_headers):
        """
        🔐 Security/Stability: Não permite atualizar para uma sigla que já existe.
        """
        c1 = models.Course(name="Curso A", abbreviation="AAA", organization_id=1)
        c2 = models.Course(name="Curso B", abbreviation="BBB", organization_id=1)
        db_session.add_all([c1, c2])
        await db_session.commit()

        payload = {"abbreviation": "AAA"}
        response = await async_client.patch(f"/api/v1/courses/{c2.id}", json=payload, headers=admin_token_headers)
        
        assert response.status_code == 400
        assert "já existe" in response.json()["detail"]

    async def test_patch_course_abbreviation_invalid_length_422(self, async_client: AsyncClient, db_session: AsyncSession, admin_token_headers):
        """
        Stability: PATCH deve manter a mesma validação de sigla usada na criação.
        """
        course = models.Course(name="Curso A", abbreviation="AAA", organization_id=1)
        db_session.add(course)
        await db_session.commit()

        response = await async_client.patch(
            f"/api/v1/courses/{course.id}",
            json={"abbreviation": "A"},
            headers=admin_token_headers,
        )

        assert response.status_code == 422

    async def test_patch_course_subjects_replace(self, async_client: AsyncClient, db_session: AsyncSession, admin_token_headers):
        """
        ⚙️ Stability: Verifica se o PATCH substitui a lista de disciplinas.
        """
        s1 = models.Subject(name="Mat", organization_id=1)
        s2 = models.Subject(name="Port", organization_id=1)
        db_session.add_all([s1, s2])
        await db_session.commit() # IDs: 1, 2

        course = models.Course(name="Curso Misto", abbreviation="CM", organization_id=1)
        # Nota: Inserir via SQL no setup para evitar poluição da sessão do teste
        db_session.add(course)
        await db_session.commit()
        
        # Associar S1 inicialmente
        await db_session.execute(
            insert(models.course_subject_link).values(
                organization_id=1,
                course_id=course.id,
                subject_id=s1.id,
            )
        )
        await db_session.commit()

        # PATCH: Enviar apenas [s2]
        payload = {"subject_ids": [s2.id]}
        response = await async_client.patch(f"/api/v1/courses/{course.id}", json=payload, headers=admin_token_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["subjects"]) == 1
        assert data["subjects"][0]["id"] == s2.id 

    async def test_delete_course_dependency_protection(self, async_client: AsyncClient, db_session: AsyncSession, admin_token_headers):
        """
        ⚙️ Stability: Impede apagar curso se tiver turmas associadas.
        """
        course = models.Course(name="Curso Perigoso", abbreviation="DANGER", organization_id=1)
        db_session.add(course)
        await db_session.commit()
        
        cls = models.Class(name="Turma 1", course_id=course.id, organization_id=1, grade_level=10, start_year=2025, end_year=2026, size=20)
        db_session.add(cls)
        await db_session.commit()

        response = await async_client.delete(f"/api/v1/courses/{course.id}", headers=admin_token_headers)
        assert response.status_code == 400
        
        await db_session.delete(cls)
        await db_session.commit()

        response_retry = await async_client.delete(f"/api/v1/courses/{course.id}", headers=admin_token_headers)
        assert response_retry.status_code == 200
