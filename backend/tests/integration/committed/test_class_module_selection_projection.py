"""WBS 2.5: the curricular projection follows the per-class module selection."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, select

from app import models
from app.scheduler.infrastructure.curriculum import sync_curricular_projection
from app.scheduler.infrastructure.models import (
    CurricularAssignment,
    CurricularExecution,
    CurricularExecutionCredit,
    CurricularRequirement,
)
from app.scheduler.infrastructure.snapshot import SnapshotConfigurationError
from tests._support.scheduler_v1 import seed_generatable_school

pytestmark = pytest.mark.postgresql

NOW = datetime(2026, 9, 2, 9, 0, tzinfo=UTC)


async def _drop_direct_projection(db_session, seed) -> None:
    await db_session.execute(
        delete(CurricularRequirement).where(
            CurricularRequirement.organization_id == seed.organization.id
        )
    )
    await db_session.execute(
        delete(CurricularAssignment).where(
            CurricularAssignment.organization_id == seed.organization.id
        )
    )
    await db_session.commit()


async def _link_id(db_session, seed) -> int:
    return await db_session.scalar(
        select(models.ClassSubjectLink.id).where(
            models.ClassSubjectLink.organization_id == seed.organization.id,
            models.ClassSubjectLink.class_id == seed.class_.id,
            models.ClassSubjectLink.subject_id == seed.subject.id,
        )
    )


async def _add_second_selected_module(db_session, seed) -> models.Module:
    module = models.Module(
        organization_id=seed.organization.id,
        subject_id=seed.subject.id,
        name="Módulo 2",
        required_minutes=40,
        order=2,
    )
    db_session.add(module)
    await db_session.flush()
    await db_session.execute(
        models.class_subject_module.insert().values(
            organization_id=seed.organization.id,
            class_subject_link_id=await _link_id(db_session, seed),
            module_id=module.id,
        )
    )
    await db_session.commit()
    return module


async def _requirements(db_session, seed) -> dict[int, CurricularRequirement]:
    rows = (
        await db_session.scalars(
            select(CurricularRequirement).where(
                CurricularRequirement.organization_id == seed.organization.id
            )
        )
    ).all()
    return {row.module_id: row for row in rows}


async def test_deselecting_a_module_without_credits_deletes_its_requirement(db_session):
    seed = await seed_generatable_school(
        db_session, clerk_user_id="selection_p1", clerk_org_id="selection_p1_org"
    )
    await db_session.commit()
    await _drop_direct_projection(db_session, seed)
    other = await _add_second_selected_module(db_session, seed)

    await sync_curricular_projection(db_session, seed.organization.id, seed.year)
    await db_session.commit()
    assert set(await _requirements(db_session, seed)) == {seed.module.id, other.id}

    await db_session.execute(
        delete(models.class_subject_module).where(
            models.class_subject_module.c.organization_id == seed.organization.id,
            models.class_subject_module.c.module_id == other.id,
        )
    )
    await db_session.commit()
    await sync_curricular_projection(db_session, seed.organization.id, seed.year)
    await db_session.commit()

    assert set(await _requirements(db_session, seed)) == {seed.module.id}


async def test_deselecting_a_module_with_credits_marks_it_not_planned(db_session):
    seed = await seed_generatable_school(
        db_session, clerk_user_id="selection_p2", clerk_org_id="selection_p2_org"
    )
    await db_session.commit()
    await _drop_direct_projection(db_session, seed)
    await _add_second_selected_module(db_session, seed)

    await sync_curricular_projection(db_session, seed.organization.id, seed.year)
    await db_session.commit()
    assignment = await db_session.scalar(
        select(CurricularAssignment).where(
            CurricularAssignment.organization_id == seed.organization.id
        )
    )
    execution = CurricularExecution(
        organization_id=seed.organization.id,
        assignment_id=assignment.id,
        origin="manual-test",
        revision=1,
        author_membership_id=seed.membership.id,
        reason="Test credit",
        recorded_at=NOW,
        planning_relevant=True,
    )
    db_session.add(execution)
    await db_session.flush()
    db_session.add(
        CurricularExecutionCredit(
            organization_id=seed.organization.id,
            execution_id=execution.id,
            module_id=seed.module.id,
            offset_minutes=0,
            delta_minutes=30,
        )
    )
    await db_session.commit()

    await db_session.execute(
        delete(models.class_subject_module).where(
            models.class_subject_module.c.organization_id == seed.organization.id,
            models.class_subject_module.c.module_id == seed.module.id,
        )
    )
    await db_session.commit()
    await sync_curricular_projection(db_session, seed.organization.id, seed.year)
    await db_session.commit()

    requirements = await _requirements(db_session, seed)
    assert requirements[seed.module.id].planned is False

    # Re-selecting the module restores it as planned with the catalogue minutes.
    await db_session.execute(
        models.class_subject_module.insert().values(
            organization_id=seed.organization.id,
            class_subject_link_id=await _link_id(db_session, seed),
            module_id=seed.module.id,
        )
    )
    await db_session.commit()
    await sync_curricular_projection(db_session, seed.organization.id, seed.year)
    await db_session.commit()
    requirements = await _requirements(db_session, seed)
    assert requirements[seed.module.id].planned is True
    assert requirements[seed.module.id].required_minutes == seed.module.required_minutes


async def test_active_link_without_selected_modules_blocks_the_projection(db_session):
    seed = await seed_generatable_school(
        db_session, clerk_user_id="selection_p3", clerk_org_id="selection_p3_org"
    )
    await db_session.commit()
    await _drop_direct_projection(db_session, seed)
    await db_session.execute(
        delete(models.class_subject_module).where(
            models.class_subject_module.c.organization_id == seed.organization.id
        )
    )
    await db_session.commit()

    with pytest.raises(SnapshotConfigurationError) as raised:
        await sync_curricular_projection(db_session, seed.organization.id, seed.year)

    assert raised.value.code == "CLASS_SUBJECT_WITHOUT_MODULES"
    assert raised.value.public_context == {
        "class_id": seed.class_.id,
        "subject_id": seed.subject.id,
    }
