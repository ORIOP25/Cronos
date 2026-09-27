"""The browser fixture prepares the v1 records used by live generation tests."""

from datetime import date

from sqlalchemy import select

from app import models
from app.scheduler.infrastructure.models import CurricularAssignment, CurricularRequirement
from tests._support.scheduler_v1 import seed_v1_assignment


async def test_e2e_seed_materializes_current_class_subject_and_preferred_end(db_session):
    seed = await seed_v1_assignment(db_session)
    requirement = await db_session.scalar(select(CurricularRequirement))
    await db_session.delete(requirement)
    await db_session.flush()
    await db_session.delete(seed.assignment)
    await db_session.flush()
    db_session.add(
        models.ClassSubjectLink(
            organization_id=seed.organization.id,
            class_id=seed.class_.id,
            subject_id=seed.subject.id,
            grade_level=seed.class_.grade_level,
            teacher_id=seed.assignment.teacher_id,
        )
    )
    await db_session.flush()

    from scripts.seed_scheduler_e2e import seed_scheduler_e2e

    await seed_scheduler_e2e(
        db_session,
        organization_id=seed.organization.id,
        class_id=seed.class_.id,
        subject_id=seed.subject.id,
        preferred_end_date=date(2026, 10, 30),
    )

    assignment = await db_session.scalar(
        select(CurricularAssignment).where(
            CurricularAssignment.organization_id == seed.organization.id,
            CurricularAssignment.class_id == seed.class_.id,
            CurricularAssignment.subject_id == seed.subject.id,
        )
    )
    requirement = await db_session.scalar(
        select(CurricularRequirement).where(CurricularRequirement.assignment_id == assignment.id)
    )
    assert seed.year.preferred_end_date == date(2026, 10, 30)
    assert assignment.teacher_id == seed.assignment.teacher_id
    assert requirement.module_id == seed.module.id
    assert requirement.required_minutes == seed.module.required_minutes
    assert (seed.state.input_revision, seed.state.planning_revision) == (1, 1)
