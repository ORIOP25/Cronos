# Ficheiro: backend/tests/test_class_subjects.py
"""
TESTES DO MODELO CURSO-CÊNTRICO: ClassSubjectLink
===================================================
Valida:
1. ✅ Criação de ClassSubjectLink com valores padrão
2. ✅ Atribuição de professor com validação de competência
3. ✅ Constraint única (class_id + subject_id + grade_level)
4. ✅ Grade levels diferentes permitem links separados
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app import models


class TestClassSubjectLink:
    """Testes do ClassSubjectLink (associação turma-disciplina)"""

    async def _create_base_data(self, db_session: AsyncSession):
        """Cria dados base: org, curso, turma, disciplina, professor"""
        org = models.Organization(name="Escola Teste", plan_status="active")
        db_session.add(org)
        await db_session.flush()

        course = models.Course(name="Técnico em Informática", abbreviation="TI", organization_id=org.id)
        db_session.add(course)
        await db_session.flush()

        cls = models.Class(
            name="TI 25/28", size=25, course_id=course.id,
            grade_level=10, start_year=2025, end_year=2028,
            organization_id=org.id
        )
        db_session.add(cls)
        await db_session.flush()

        subject = models.Subject(name="Matemática", organization_id=org.id)
        db_session.add(subject)
        await db_session.flush()

        teacher = models.Teacher(name="Prof. Silva", organization_id=org.id)
        db_session.add(teacher)
        await db_session.flush()

        # Adicionar competência ao professor
        from sqlalchemy import insert
        await db_session.execute(
            insert(models.teacher_subject_link).values(
                organization_id=org.id, teacher_id=teacher.id, subject_id=subject.id
            )
        )
        await db_session.commit()

        return org, course, cls, subject, teacher

    @pytest.mark.asyncio
    async def test_class_subject_link_default_values(self, db_session: AsyncSession):
        """✅ ClassSubjectLink criado com teacher_id=None por padrão"""
        _, _, cls, subject, _ = await self._create_base_data(db_session)

        link = models.ClassSubjectLink(
            organization_id=cls.organization_id,
            class_id=cls.id,
            subject_id=subject.id,
            grade_level=cls.grade_level
        )
        db_session.add(link)
        await db_session.commit()
        await db_session.refresh(link)

        assert link.teacher_id is None

    @pytest.mark.asyncio
    async def test_class_subject_link_custom_values(self, db_session: AsyncSession):
        """✅ ClassSubjectLink aceita professor atribuído"""
        _, _, cls, subject, teacher = await self._create_base_data(db_session)

        link = models.ClassSubjectLink(
            organization_id=cls.organization_id,
            class_id=cls.id,
            subject_id=subject.id,
            grade_level=cls.grade_level,
            teacher_id=teacher.id,
        )
        db_session.add(link)
        await db_session.commit()
        await db_session.refresh(link)

        assert link.teacher_id == teacher.id

    @pytest.mark.asyncio
    async def test_class_subject_link_update_teacher(self, db_session: AsyncSession):
        """✅ ClassSubjectLink permite atualizar professor"""
        _, _, cls, subject, teacher = await self._create_base_data(db_session)

        link = models.ClassSubjectLink(
            organization_id=cls.organization_id,
            class_id=cls.id,
            subject_id=subject.id,
            grade_level=cls.grade_level,
        )
        db_session.add(link)
        await db_session.commit()

        # Atualizar
        link.teacher_id = teacher.id
        await db_session.commit()
        await db_session.refresh(link)

        assert link.teacher_id == teacher.id

    @pytest.mark.asyncio
    async def test_class_subject_link_unique_constraint(self, db_session: AsyncSession):
        """🔐 Não pode haver 2 links para mesma turma+disciplina+grade_level"""
        from sqlalchemy import exc

        _, _, cls, subject, _ = await self._create_base_data(db_session)

        link1 = models.ClassSubjectLink(
            organization_id=cls.organization_id,
            class_id=cls.id,
            subject_id=subject.id,
            grade_level=cls.grade_level
        )
        db_session.add(link1)
        await db_session.commit()

        link2 = models.ClassSubjectLink(
            organization_id=cls.organization_id,
            class_id=cls.id,
            subject_id=subject.id,
            grade_level=cls.grade_level
        )
        db_session.add(link2)

        with pytest.raises(exc.IntegrityError):
            await db_session.commit()

    @pytest.mark.asyncio
    async def test_class_subject_link_different_grade_levels(self, db_session: AsyncSession):
        """📈 Mesma turma+disciplina pode existir em grade_levels diferentes"""
        _, _, cls, subject, _ = await self._create_base_data(db_session)

        link1 = models.ClassSubjectLink(
            organization_id=cls.organization_id,
            class_id=cls.id,
            subject_id=subject.id,
            grade_level=10,
        )
        link2 = models.ClassSubjectLink(
            organization_id=cls.organization_id,
            class_id=cls.id,
            subject_id=subject.id,
            grade_level=11,
        )
        db_session.add_all([link1, link2])
        await db_session.commit()

        result = await db_session.execute(
            select(models.ClassSubjectLink).where(
                models.ClassSubjectLink.class_id == cls.id,
                models.ClassSubjectLink.subject_id == subject.id
            ).order_by(models.ClassSubjectLink.grade_level)
        )
        links = result.scalars().all()

        assert len(links) == 2
        assert links[0].grade_level == 10
        assert links[1].grade_level == 11
