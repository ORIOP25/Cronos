# Ficheiro: backend/tests/test_course_centric_model.py
"""
TESTES DO MODELO CURSO-CÊNTRICO
================================
Valida:
1. ✅ Campos obrigatórios (abbreviation, start_year, end_year, grade_level, order, updated_at)
2. ✅ Relações hierárquicas (Organization → Course → Class → Module → ClassProgress)
3. ✅ Constraints únicos (abbreviation único, order único por subject)
4. ✅ Regra de negócio: Módulos sequenciais

4 Pilares:
🔐 Security: Validação de dados, constraints na BD
⚙️ Stability: Transações atómicas, rollback em erro
⚡ Optimization: Índices nas FKs, lazy load relationships
📈 Scalability: Modelo hierárquico multi-organização
"""

import pytest
from datetime import datetime
from sqlalchemy import exc, select
from sqlalchemy.ext.asyncio import AsyncSession
from app import models


class TestCourseCentricModel:
    """Testes do modelo Organization → Course → Class → Module → ClassProgress"""
    
    @pytest.mark.asyncio
    async def test_organization_creation(self, db_session: AsyncSession):
        """🏢 Criar uma organização"""
        org = models.Organization(name="Escola Teste", plan_status="active")
        db_session.add(org)
        await db_session.commit()
        await db_session.refresh(org)
        
        assert org.id is not None
        assert org.name == "Escola Teste"
        assert org.plan_status == "active"
    
    @pytest.mark.asyncio
    async def test_course_abbreviation_required(self, db_session: AsyncSession):
        """🔐 Course.abbreviation é obrigatório"""
        org = models.Organization(name="Escola Teste", plan_status="active")
        db_session.add(org)
        await db_session.commit()
        await db_session.refresh(org)
        
        # Tentar criar sem abbreviation deve falhar
        course = models.Course(
            name="Curso Sem Abreviação",
            abbreviation=None,
            organization_id=org.id
        )
        db_session.add(course)
        
        with pytest.raises(exc.IntegrityError):
            await db_session.commit()
    
    @pytest.mark.asyncio
    async def test_course_abbreviation_unique(self, db_session: AsyncSession):
        """🔐 Course.abbreviation é único"""
        org = models.Organization(name="Escola Teste", plan_status="active")
        db_session.add(org)
        await db_session.commit()
        await db_session.refresh(org)
        
        course1 = models.Course(name="Técnico em Informática", abbreviation="TI", organization_id=org.id)
        db_session.add(course1)
        await db_session.commit()
        
        # Segunda com mesma abbreviation
        course2 = models.Course(name="Outro Técnico", abbreviation="TI", organization_id=org.id)
        db_session.add(course2)
        
        with pytest.raises(exc.IntegrityError):
            await db_session.commit()
    
    @pytest.mark.asyncio
    async def test_class_cycle_fields_required(self, db_session: AsyncSession):
        """🔐 Class requer start_year, end_year, grade_level"""
        org = models.Organization(name="Escola Teste", plan_status="active")
        db_session.add(org)
        await db_session.commit()
        await db_session.refresh(org)
        
        course = models.Course(name="Técnico em Informática", abbreviation="TI", organization_id=org.id)
        db_session.add(course)
        await db_session.commit()
        await db_session.refresh(course)
        
        # Sem grade_level
        cls = models.Class(
            name="TI 25/28", size=25, course_id=course.id,
            start_year=2025, end_year=2028, grade_level=None,
            organization_id=org.id
        )
        db_session.add(cls)
        
        with pytest.raises(exc.IntegrityError):
            await db_session.commit()
    
    @pytest.mark.asyncio
    async def test_class_hierarchy_with_cycles(self, db_session: AsyncSession):
        """📈 Classes têm ciclos de 3 anos (10º-12º)"""
        org = models.Organization(name="Escola Teste", plan_status="active")
        db_session.add(org)
        await db_session.commit()
        await db_session.refresh(org)
        
        course = models.Course(name="Técnico em Informática", abbreviation="TI", organization_id=org.id)
        db_session.add(course)
        await db_session.commit()
        await db_session.refresh(course)
        
        # Criar 3 turmas com ciclos
        classes_data = [
            {"name": "TI 25/28", "grade": 10, "start": 2025, "end": 2028, "size": 25},
            {"name": "TI 24/27", "grade": 11, "start": 2024, "end": 2027, "size": 24},
            {"name": "TI 23/26", "grade": 12, "start": 2023, "end": 2026, "size": 23},
        ]
        
        for cls_data in classes_data:
            cls = models.Class(
                name=cls_data["name"], size=cls_data["size"],
                course_id=course.id,
                grade_level=cls_data["grade"],
                start_year=cls_data["start"], end_year=cls_data["end"],
                organization_id=org.id
            )
            db_session.add(cls)
        
        await db_session.commit()
        
        result = await db_session.execute(select(models.Class).where(models.Class.course_id == course.id).order_by(models.Class.grade_level))
        classes = result.scalars().all()
        
        assert len(classes) == 3
        assert classes[0].grade_level == 10
        assert classes[1].grade_level == 11
        assert classes[2].grade_level == 12
        assert classes[0].start_year == 2025 and classes[0].end_year == 2028
    
    @pytest.mark.asyncio
    async def test_module_order_unique_per_subject(self, db_session: AsyncSession):
        """⚙️ Módulos têm ordem única por disciplina"""
        org = models.Organization(name="Escola Teste", plan_status="active")
        db_session.add(org)
        await db_session.commit()
        await db_session.refresh(org)
        
        subject = models.Subject(name="Matemática", organization_id=org.id)
        db_session.add(subject)
        await db_session.commit()
        await db_session.refresh(subject)
        
        module1 = models.Module(name="Álgebra", code="M001", hours_total=30, order=1, subject_id=subject.id)
        db_session.add(module1)
        await db_session.commit()
        
        # Outro com order=1 na mesma disciplina
        module2 = models.Module(name="Geometria", code="M002", hours_total=30, order=1, subject_id=subject.id)
        db_session.add(module2)
        
        with pytest.raises(exc.IntegrityError):
            await db_session.commit()
    
    @pytest.mark.asyncio
    async def test_module_sequential_order_per_subject(self, db_session: AsyncSession):
        """⚙️ Módulos têm ordem sequencial (1, 2, 3...)"""
        org = models.Organization(name="Escola Teste", plan_status="active")
        db_session.add(org)
        await db_session.commit()
        await db_session.refresh(org)
        
        subject = models.Subject(name="Matemática", organization_id=org.id)
        db_session.add(subject)
        await db_session.commit()
        await db_session.refresh(subject)
        
        modules_data = [
            {"name": "Álgebra", "code": "M001", "hours": 30, "order": 1},
            {"name": "Geometria", "code": "M002", "hours": 30, "order": 2},
            {"name": "Cálculo", "code": "M003", "hours": 20, "order": 3},
        ]
        
        for mod_data in modules_data:
            module = models.Module(
                name=mod_data["name"], code=mod_data["code"],
                hours_total=mod_data["hours"], order=mod_data["order"],
                subject_id=subject.id
            )
            db_session.add(module)
        
        await db_session.commit()
        
        result = await db_session.execute(select(models.Module).where(models.Module.subject_id == subject.id).order_by(models.Module.order))
        modules = result.scalars().all()
        
        assert len(modules) == 3
        assert [m.order for m in modules] == [1, 2, 3]
        assert [m.hours_total for m in modules] == [30, 30, 20]
    
    @pytest.mark.asyncio
    async def test_class_progress_creation_and_timestamp(self, db_session: AsyncSession):
        """📊 ClassProgress rastreia horas e atualiza timestamp automaticamente"""
        org = models.Organization(name="Escola Teste", plan_status="active")
        db_session.add(org)
        await db_session.commit()
        await db_session.refresh(org)
        
        # Hierarquia completa
        course = models.Course(name="Técnico em Informática", abbreviation="TI", organization_id=org.id)
        db_session.add(course)
        await db_session.commit()
        await db_session.refresh(course)
        
        cls = models.Class(
            name="TI 25/28", size=25, course_id=course.id,
            grade_level=10, start_year=2025, end_year=2028,
            organization_id=org.id
        )
        db_session.add(cls)
        await db_session.commit()
        await db_session.refresh(cls)
        
        subject = models.Subject(name="Matemática", organization_id=org.id)
        db_session.add(subject)
        await db_session.commit()
        await db_session.refresh(subject)
        
        module = models.Module(name="Álgebra", code="M001", hours_total=30, order=1, subject_id=subject.id)
        db_session.add(module)
        await db_session.commit()
        await db_session.refresh(module)
        
        # Criar progresso
        progress = models.ClassProgress(
            class_id=cls.id, module_id=module.id,
            hours_completed=15, is_completed=False
        )
        db_session.add(progress)
        await db_session.commit()
        await db_session.refresh(progress)
        
        assert progress.id is not None
        assert progress.hours_completed == 15
        assert progress.is_completed is False
        assert isinstance(progress.updated_at, datetime)  # ✅ Timestamp automático
    
    @pytest.mark.asyncio
    async def test_class_progress_unique_per_class_module(self, db_session: AsyncSession):
        """🔐 Não pode haver 2 ClassProgress para mesma turma+módulo"""
        org = models.Organization(name="Escola Teste", plan_status="active")
        db_session.add(org)
        await db_session.commit()
        await db_session.refresh(org)
        
        course = models.Course(name="Técnico em Informática", abbreviation="TI", organization_id=org.id)
        db_session.add(course)
        await db_session.commit()
        await db_session.refresh(course)
        
        cls = models.Class(
            name="TI 25/28", size=25, course_id=course.id,
            grade_level=10, start_year=2025, end_year=2028,
            organization_id=org.id
        )
        db_session.add(cls)
        await db_session.commit()
        await db_session.refresh(cls)
        
        subject = models.Subject(name="Matemática", organization_id=org.id)
        db_session.add(subject)
        await db_session.commit()
        await db_session.refresh(subject)
        
        module = models.Module(name="Álgebra", code="M001", hours_total=30, order=1, subject_id=subject.id)
        db_session.add(module)
        await db_session.commit()
        await db_session.refresh(module)
        
        # Primeiro progresso
        progress1 = models.ClassProgress(class_id=cls.id, module_id=module.id, hours_completed=10, is_completed=False)
        db_session.add(progress1)
        await db_session.commit()
        
        # Segundo com mesma combinação
        progress2 = models.ClassProgress(class_id=cls.id, module_id=module.id, hours_completed=20, is_completed=False)
        db_session.add(progress2)
        
        with pytest.raises(exc.IntegrityError):
            await db_session.commit()
    
    @pytest.mark.asyncio
    async def test_full_hierarchy_cascade(self, db_session: AsyncSession):
        """🔄 Verificar cascata completa: Organization → Course → Class → ClassProgress"""
        org = models.Organization(name="Escola Teste", plan_status="active")
        db_session.add(org)
        await db_session.commit()
        await db_session.refresh(org)
        
        # Nível 2: Course
        course = models.Course(name="Técnico em Informática", abbreviation="TI", organization_id=org.id)
        db_session.add(course)
        await db_session.commit()
        await db_session.refresh(course)
        
        # Nível 3: Class
        cls = models.Class(
            name="TI 25/28", size=25, course_id=course.id,
            grade_level=10, start_year=2025, end_year=2028,
            organization_id=org.id
        )
        db_session.add(cls)
        await db_session.commit()
        await db_session.refresh(cls)
        
        # Nível 3.5: Subject + Module
        subject = models.Subject(name="Matemática", organization_id=org.id)
        db_session.add(subject)
        await db_session.commit()
        await db_session.refresh(subject)
        
        module = models.Module(name="Álgebra", code="M001", hours_total=30, order=1, subject_id=subject.id)
        db_session.add(module)
        await db_session.commit()
        await db_session.refresh(module)
        
        # Nível 4: ClassProgress
        progress = models.ClassProgress(class_id=cls.id, module_id=module.id, hours_completed=0, is_completed=False)
        db_session.add(progress)
        await db_session.commit()
        await db_session.refresh(progress)
        
        # Verificar a hierarquia completa (com eager loading para evitar MissingGreenlet)
        from sqlalchemy.orm import selectinload
        result = await db_session.execute(
            select(models.ClassProgress)
            .where(models.ClassProgress.id == progress.id)
            .options(
                selectinload(models.ClassProgress.class_).selectinload(models.Class.course).selectinload(models.Course.organization),
                selectinload(models.ClassProgress.module).selectinload(models.Module.subject).selectinload(models.Subject.organization),
            )
        )
        fetched_progress = result.scalar()
        
        assert fetched_progress.class_.course.organization.id == org.id
        assert fetched_progress.module.subject.organization.id == org.id