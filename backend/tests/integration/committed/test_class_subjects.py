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

from datetime import date

import pytest
from factories import API, _setup_course_class_subject
from httpx import AsyncClient
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.scheduler.infrastructure.models import (
    CurricularAssignment,
    CurricularExecution,
    CurricularExecutionCredit,
    CurricularRequirement,
)
from app.services import class_service
from app.services.room_type_service import ensure_initial_room_types
from tests._support.db_fixtures import (
    TestingSessionLocal,
    create_teacher_profile,
    get_school_room_type_id,
)


class TestClassSubjectLink:
    """Testes do ClassSubjectLink (associação turma-disciplina)"""

    async def _create_base_data(self, db_session: AsyncSession):
        """Cria dados base: org, curso, turma, disciplina, professor"""
        org = models.Organization(name="Escola Teste", plan_status="active")
        db_session.add(org)
        await db_session.flush()
        await ensure_initial_room_types(db_session, org.id)

        course = models.Course(
            name="Técnico em Informática", abbreviation="TI", organization_id=org.id
        )
        db_session.add(course)
        await db_session.flush()

        cls = models.Class(
            name="TI 25/28",
            size=25,
            course_id=course.id,
            grade_level=10,
            start_year=2025,
            end_year=2028,
            organization_id=org.id,
        )
        db_session.add(cls)
        await db_session.flush()

        subject = models.Subject(
            name="Matemática",
            organization_id=org.id,
            room_type_id=await get_school_room_type_id(db_session, org.id, "Normal"),
        )
        db_session.add(subject)
        await db_session.flush()

        teacher = await create_teacher_profile(
            db_session,
            organization_id=org.id,
            name="Prof. Silva",
        )

        # Adicionar competência ao professor
        from sqlalchemy import insert

        await db_session.execute(
            insert(models.teacher_subject_link).values(
                organization_id=org.id, teacher_id=teacher.id, subject_id=subject.id
            )
        )
        await db_session.commit()

        return org, course, cls, subject, teacher

    async def test_class_subject_link_default_values(self, db_session: AsyncSession):
        """✅ ClassSubjectLink criado com teacher_id=None por padrão"""
        _, _, cls, subject, _ = await self._create_base_data(db_session)

        link = models.ClassSubjectLink(
            organization_id=cls.organization_id,
            class_id=cls.id,
            subject_id=subject.id,
            grade_level=cls.grade_level,
        )
        db_session.add(link)
        await db_session.commit()
        await db_session.refresh(link)

        assert link.teacher_id is None

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

    async def test_class_subject_link_unique_constraint(self, db_session: AsyncSession):
        """🔐 Não pode haver 2 links para mesma turma+disciplina+grade_level"""
        from sqlalchemy import exc

        _, _, cls, subject, _ = await self._create_base_data(db_session)

        link1 = models.ClassSubjectLink(
            organization_id=cls.organization_id,
            class_id=cls.id,
            subject_id=subject.id,
            grade_level=cls.grade_level,
        )
        db_session.add(link1)
        await db_session.commit()

        link2 = models.ClassSubjectLink(
            organization_id=cls.organization_id,
            class_id=cls.id,
            subject_id=subject.id,
            grade_level=cls.grade_level,
        )
        db_session.add(link2)

        with pytest.raises(exc.IntegrityError):
            await db_session.commit()

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
            select(models.ClassSubjectLink)
            .where(
                models.ClassSubjectLink.class_id == cls.id,
                models.ClassSubjectLink.subject_id == subject.id,
            )
            .order_by(models.ClassSubjectLink.grade_level)
        )
        links = result.scalars().all()

        assert len(links) == 2
        assert links[0].grade_level == 10
        assert links[1].grade_level == 11


class TestClassSubjectModuleSelection:
    """WBS 2.3: read and write the per-class module selection."""

    async def test_post_marks_every_subject_module(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        ctx = await _setup_course_class_subject(async_client, clerk_admin_headers)

        resp = await async_client.get(
            f"{API}/classes/{ctx['class_id']}/subjects", headers=clerk_admin_headers
        )

        assert resp.status_code == 200, resp.text
        subject = resp.json()["subjects"][0]
        assert [module["id"] for module in subject["modules"]] == ctx["module_ids"]
        assert [module["order"] for module in subject["modules"]] == sorted(
            module["order"] for module in subject["modules"]
        )
        assert all(module["selected"] is True for module in subject["modules"])

    async def test_patch_selects_only_the_given_modules(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        ctx = await _setup_course_class_subject(async_client, clerk_admin_headers)
        chosen = ctx["module_ids"][:1]

        resp = await async_client.patch(
            f"{API}/classes/{ctx['class_id']}/subjects/{ctx['subject_id']}",
            json={"module_ids": chosen},
            headers=clerk_admin_headers,
        )

        assert resp.status_code == 200, resp.text
        modules = resp.json()["subjects"][0]["modules"]
        assert [module["id"] for module in modules if module["selected"]] == chosen

    async def test_patch_accepts_an_empty_list(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        ctx = await _setup_course_class_subject(async_client, clerk_admin_headers)

        resp = await async_client.patch(
            f"{API}/classes/{ctx['class_id']}/subjects/{ctx['subject_id']}",
            json={"module_ids": []},
            headers=clerk_admin_headers,
        )

        assert resp.status_code == 200, resp.text
        modules = resp.json()["subjects"][0]["modules"]
        assert modules
        assert all(module["selected"] is False for module in modules)

    async def test_patch_rejects_duplicate_module_ids(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        ctx = await _setup_course_class_subject(async_client, clerk_admin_headers)
        duplicated = [ctx["module_ids"][0], ctx["module_ids"][0]]

        resp = await async_client.patch(
            f"{API}/classes/{ctx['class_id']}/subjects/{ctx['subject_id']}",
            json={"module_ids": duplicated},
            headers=clerk_admin_headers,
        )

        assert resp.status_code == 400

    async def test_patch_rejects_a_module_from_another_subject(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        ctx = await _setup_course_class_subject(async_client, clerk_admin_headers)
        other_subject = await async_client.post(
            f"{API}/subjects/",
            json={
                "name": "Educação Física",
                "modules": [{"name": "M1", "code": "EF1", "hours_total": 10, "order": 0}],
            },
            headers=clerk_admin_headers,
        )
        other_module_id = other_subject.json()["modules"][0]["id"]

        resp = await async_client.patch(
            f"{API}/classes/{ctx['class_id']}/subjects/{ctx['subject_id']}",
            json={"module_ids": [other_module_id]},
            headers=clerk_admin_headers,
        )

        assert resp.status_code == 400

    async def test_teacher_only_patch_keeps_the_selection(
        self,
        async_client: AsyncClient,
        clerk_admin_headers: dict,
        db_session: AsyncSession,
    ):
        ctx = await _setup_course_class_subject(async_client, clerk_admin_headers)
        teacher = await create_teacher_profile(
            db_session,
            organization_id=1,
            name="Prof. Módulos",
            subject_ids=[ctx["subject_id"]],
        )
        await db_session.commit()

        resp = await async_client.patch(
            f"{API}/classes/{ctx['class_id']}/subjects/{ctx['subject_id']}",
            json={"teacher_id": teacher.id},
            headers=clerk_admin_headers,
        )

        assert resp.status_code == 200, resp.text
        subject = resp.json()["subjects"][0]
        assert subject["teacher_id"] == teacher.id
        assert all(module["selected"] for module in subject["modules"])

    async def test_patch_null_module_ids_keeps_the_selection(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        ctx = await _setup_course_class_subject(async_client, clerk_admin_headers)

        resp = await async_client.patch(
            f"{API}/classes/{ctx['class_id']}/subjects/{ctx['subject_id']}",
            json={"module_ids": None},
            headers=clerk_admin_headers,
        )

        assert resp.status_code == 200, resp.text
        modules = resp.json()["subjects"][0]["modules"]
        assert all(module["selected"] for module in modules)

    async def test_validates_modules_before_applying_the_teacher(
        self,
        async_client: AsyncClient,
        clerk_admin_headers: dict,
        db_session: AsyncSession,
    ):
        ctx = await _setup_course_class_subject(async_client, clerk_admin_headers)
        teacher = await create_teacher_profile(
            db_session,
            organization_id=1,
            name="Prof. Validação",
            subject_ids=[ctx["subject_id"]],
        )
        await db_session.commit()

        resp = await async_client.patch(
            f"{API}/classes/{ctx['class_id']}/subjects/{ctx['subject_id']}",
            json={"teacher_id": teacher.id, "module_ids": [999_999]},
            headers=clerk_admin_headers,
        )

        assert resp.status_code == 404
        after = await async_client.get(
            f"{API}/classes/{ctx['class_id']}/subjects", headers=clerk_admin_headers
        )
        subject = after.json()["subjects"][0]
        assert subject["teacher_id"] is None
        assert all(module["selected"] for module in subject["modules"])

    async def test_patch_archived_class_is_rejected(
        self,
        async_client: AsyncClient,
        clerk_admin_headers: dict,
        db_session: AsyncSession,
    ):
        ctx = await _setup_course_class_subject(async_client, clerk_admin_headers)
        db_class = await db_session.get(models.Class, ctx["class_id"])
        db_class.is_archived = True
        await db_session.commit()

        resp = await async_client.patch(
            f"{API}/classes/{ctx['class_id']}/subjects/{ctx['subject_id']}",
            json={"module_ids": []},
            headers=clerk_admin_headers,
        )

        assert resp.status_code == 400

    async def test_new_catalog_module_is_not_auto_selected(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        ctx = await _setup_course_class_subject(async_client, clerk_admin_headers)
        updated = await async_client.patch(
            f"{API}/subjects/{ctx['subject_id']}",
            json={
                "modules": [
                    {
                        "id": ctx["module_ids"][0],
                        "name": "M1",
                        "code": "P01",
                        "hours_total": 25,
                        "order": 0,
                    },
                    {
                        "id": ctx["module_ids"][1],
                        "name": "M2",
                        "code": "P02",
                        "hours_total": 50,
                        "order": 1,
                    },
                    {"name": "M3", "code": "P03", "hours_total": 10, "order": 2},
                ]
            },
            headers=clerk_admin_headers,
        )
        assert updated.status_code == 200, updated.text

        resp = await async_client.get(
            f"{API}/classes/{ctx['class_id']}/subjects", headers=clerk_admin_headers
        )
        modules = resp.json()["subjects"][0]["modules"]
        selected = [module["id"] for module in modules if module["selected"]]
        assert selected == ctx["module_ids"]
        new_module = next(module for module in modules if module["code"] == "P03")
        assert new_module["selected"] is False


class TestClassProgressV1SelectionGuard:
    """D1: progress validates the live selection before the v1/legacy dispatch."""

    async def test_v1_progress_rejects_an_unselected_module(
        self,
        async_client: AsyncClient,
        clerk_admin_headers: dict,
        db_session: AsyncSession,
    ):
        ctx = await _setup_course_class_subject(async_client, clerk_admin_headers)
        organization_id = 1
        teacher = await create_teacher_profile(
            db_session, organization_id=organization_id, name="Prof. V1"
        )
        year = models.SchedulerSchoolYear(
            organization_id=organization_id,
            label="2026/2027",
            start_date=date(2026, 9, 1),
            hard_end_date=date(2027, 7, 31),
            is_active=True,
        )
        db_session.add(year)
        await db_session.flush()
        db_session.add(
            models.SchedulerSchoolYearState(
                organization_id=organization_id,
                school_year_id=year.id,
                school_year_publication_state=models.SchoolYearPublicationState.UNPUBLISHED,
                scheduler_state_version=0,
                lock_version=0,
            )
        )
        assignment = CurricularAssignment(
            organization_id=organization_id,
            school_year_id=year.id,
            class_id=ctx["class_id"],
            subject_id=ctx["subject_id"],
            teacher_id=teacher.id,
        )
        db_session.add(assignment)
        await db_session.flush()
        modules = {
            module.id: module
            for module in (
                await db_session.scalars(
                    select(models.Module).where(models.Module.id.in_(ctx["module_ids"]))
                )
            ).all()
        }
        for sequence, module_id in enumerate(ctx["module_ids"], start=1):
            db_session.add(
                CurricularRequirement(
                    organization_id=organization_id,
                    assignment_id=assignment.id,
                    module_id=module_id,
                    sequence=sequence,
                    required_minutes=modules[module_id].required_minutes,
                )
            )
        await db_session.commit()

        selected_module, deselected_module = ctx["module_ids"]
        deselect = await async_client.patch(
            f"{API}/classes/{ctx['class_id']}/subjects/{ctx['subject_id']}",
            json={"module_ids": [selected_module]},
            headers=clerk_admin_headers,
        )
        assert deselect.status_code == 200, deselect.text

        rejected = await async_client.patch(
            f"{API}/classes/{ctx['class_id']}/progress",
            json={"progress": [{"module_id": deselected_module, "hours_completed": 10}]},
            headers=clerk_admin_headers,
        )
        assert rejected.status_code == 400
        assert "processar" in rejected.json()["detail"]["message"]

        accepted = await async_client.patch(
            f"{API}/classes/{ctx['class_id']}/progress",
            json={"progress": [{"module_id": selected_module, "hours_completed": 10}]},
            headers=clerk_admin_headers,
        )
        assert accepted.status_code == 200, accepted.text

        ledger = {
            module_id: int(minutes)
            for module_id, minutes in (
                await db_session.execute(
                    select(
                        CurricularExecutionCredit.module_id,
                        func.sum(CurricularExecutionCredit.delta_minutes),
                    )
                    .join(
                        CurricularExecution,
                        CurricularExecution.id == CurricularExecutionCredit.execution_id,
                    )
                    .where(CurricularExecution.assignment_id == assignment.id)
                    .group_by(CurricularExecutionCredit.module_id)
                )
            ).all()
        }
        assert ledger == {selected_module: 600}


class TestClassSubjectModuleSelectionQueryBudget:
    """D8/WBS 2.3.2: catalogue modules and selection in one extra statement."""

    async def _statement_count(self, class_id: int, organization_id: int) -> int:
        statements: list[str] = []

        def record(_conn, _cursor, statement, _params, _context, _many):
            statements.append(statement)

        async with TestingSessionLocal() as session:
            engine = session.get_bind()
            event.listen(engine, "before_cursor_execute", record)
            try:
                await class_service.get_class_subjects(session, class_id, organization_id)
            finally:
                event.remove(engine, "before_cursor_execute", record)
        return len(statements)

    async def test_query_count_is_constant_with_one_or_many_subjects(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        ctx = await _setup_course_class_subject(async_client, clerk_admin_headers)

        second_class = await async_client.post(
            f"{API}/courses/{ctx['course_id']}/classes",
            json={
                "name": "Turma Multi",
                "grade_level": 10,
                "start_year": 2025,
                "end_year": 2028,
            },
            headers=clerk_admin_headers,
        )
        multi_class_id = second_class.json()["id"]
        subject_ids = [ctx["subject_id"]]
        for index in range(2):
            created = await async_client.post(
                f"{API}/subjects/",
                json={
                    "name": f"Extra {index}",
                    "modules": [
                        {"name": f"E{index}", "code": f"E{index}", "hours_total": 10, "order": 0}
                    ],
                },
                headers=clerk_admin_headers,
            )
            subject_ids.append(created.json()["id"])
        for subject_id in subject_ids:
            assigned = await async_client.post(
                f"{API}/classes/{multi_class_id}/subjects",
                json={"subject_id": subject_id},
                headers=clerk_admin_headers,
            )
            assert assigned.status_code == 200, assigned.text

        single = await self._statement_count(ctx["class_id"], 1)
        many = await self._statement_count(multi_class_id, 1)

        assert single == many
        # Five batched reads plus one constant joint-group read for the badge.
        assert many <= 6
