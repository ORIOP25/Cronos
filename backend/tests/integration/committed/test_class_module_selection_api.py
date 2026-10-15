"""WBS 2.3: read and write the per-class module selection."""

from __future__ import annotations

import pytest

from app import models, schemas
from app.core.exceptions import AppError
from app.services import class_service
from tests._support.db_fixtures import create_org_and_user

pytestmark = pytest.mark.postgresql


async def _scenario(db_session, *, suffix: str, module_count: int = 2):
    org, _ = await create_org_and_user(
        db_session,
        clerk_user_id=f"selection-{suffix}-user",
        clerk_org_id=f"selection-{suffix}-org",
    )
    course = models.Course(organization_id=org.id, name="Curso", abbreviation=suffix[:9].upper())
    subject = models.Subject(organization_id=org.id, name="Disciplina")
    db_session.add_all([course, subject])
    await db_session.flush()
    school_class = models.Class(
        organization_id=org.id,
        course_id=course.id,
        name="Turma",
        size=20,
        grade_level=10,
        start_year=2026,
        end_year=2029,
    )
    db_session.add(school_class)
    await db_session.flush()
    modules = []
    for order in range(module_count):
        module = models.Module(
            organization_id=org.id,
            subject_id=subject.id,
            name=f"Módulo {order}",
            required_minutes=50,
            order=order,
        )
        db_session.add(module)
        modules.append(module)
    await db_session.flush()
    await class_service.add_class_subject(db_session, school_class.id, subject.id, org.id)
    await db_session.commit()
    return org, school_class, subject, modules


async def test_add_class_subject_selects_all_modules(db_session):
    _, school_class, subject, modules = await _scenario(db_session, suffix="api-all")

    result = await class_service.get_class_subjects(
        db_session, school_class.id, subject.organization_id
    )
    listed = result["subjects"][0]["modules"]

    assert [row["id"] for row in listed] == [module.id for module in modules]
    assert all(row["selected"] for row in listed)


async def test_update_class_subject_replaces_the_selection_including_empty(db_session):
    org, school_class, subject, modules = await _scenario(db_session, suffix="api-write")

    await class_service.update_class_subject(
        db_session,
        school_class.id,
        subject.id,
        schemas.ClassSubjectUpdate(module_ids=[modules[1].id]),
        org.id,
    )
    result = await class_service.get_class_subjects(db_session, school_class.id, org.id)
    selected = {row["id"]: row["selected"] for row in result["subjects"][0]["modules"]}
    assert selected == {modules[0].id: False, modules[1].id: True}

    await class_service.update_class_subject(
        db_session,
        school_class.id,
        subject.id,
        schemas.ClassSubjectUpdate(module_ids=[]),
        org.id,
    )
    result = await class_service.get_class_subjects(db_session, school_class.id, org.id)
    assert all(not row["selected"] for row in result["subjects"][0]["modules"])


async def test_update_class_subject_rejects_duplicates_and_foreign_modules(db_session):
    org, school_class, subject, modules = await _scenario(db_session, suffix="api-bad")

    with pytest.raises(AppError) as duplicate:
        await class_service.update_class_subject(
            db_session,
            school_class.id,
            subject.id,
            schemas.ClassSubjectUpdate(module_ids=[modules[0].id, modules[0].id]),
            org.id,
        )
    assert duplicate.value.code == "bad_request"

    other_subject = models.Subject(organization_id=org.id, name="Outra")
    db_session.add(other_subject)
    await db_session.flush()
    foreign_module = models.Module(
        organization_id=org.id,
        subject_id=other_subject.id,
        name="Fora",
        required_minutes=50,
        order=0,
    )
    db_session.add(foreign_module)
    await db_session.flush()

    with pytest.raises(AppError) as wrong_subject:
        await class_service.update_class_subject(
            db_session,
            school_class.id,
            subject.id,
            schemas.ClassSubjectUpdate(module_ids=[foreign_module.id]),
            org.id,
        )
    assert wrong_subject.value.code == "bad_request"

    other_org, _ = await create_org_and_user(
        db_session,
        clerk_user_id="selection-foreign-user",
        clerk_org_id="selection-foreign-org",
    )
    foreign_org_subject = models.Subject(organization_id=other_org.id, name="Externa")
    db_session.add(foreign_org_subject)
    await db_session.flush()
    foreign_org_module = models.Module(
        organization_id=other_org.id,
        subject_id=foreign_org_subject.id,
        name="Externo",
        required_minutes=50,
        order=0,
    )
    db_session.add(foreign_org_module)
    await db_session.flush()

    with pytest.raises(AppError) as foreign_org_error:
        await class_service.update_class_subject(
            db_session,
            school_class.id,
            subject.id,
            schemas.ClassSubjectUpdate(module_ids=[foreign_org_module.id]),
            org.id,
        )
    assert foreign_org_error.value.code == "resource_not_found"
