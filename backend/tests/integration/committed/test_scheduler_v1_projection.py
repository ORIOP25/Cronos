"""W12.R1: the generation command projects product links into v1 planning data."""

from __future__ import annotations

import pytest
from sqlalchemy import delete, select

from app import models
from app.scheduler.infrastructure.curriculum import sync_curricular_projection
from app.scheduler.infrastructure.models import (
    CurricularAssignment,
    CurricularRequirement,
)
from app.scheduler.infrastructure.queries import current_proposal
from tests._support.db_fixtures import create_teacher_profile
from tests._support.scheduler_v1 import MOMENT, seed_generatable_school

pytestmark = pytest.mark.postgresql


async def _drop_direct_projection(db_session, seed):
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
    return await db_session.scalar(
        select(models.ClassSubjectLink).where(
            models.ClassSubjectLink.organization_id == seed.organization.id,
            models.ClassSubjectLink.class_id == seed.class_.id,
            models.ClassSubjectLink.subject_id == seed.subject.id,
        )
    )


async def _queue_generation(db_session, monkeypatch, seed, *, key: str) -> None:
    from app import scheduler_v1_worker as worker
    from app.scheduler.infrastructure.jobs import enqueue_generation
    from tests._support.db_fixtures import TestingSessionLocal, test_engine

    await enqueue_generation(
        db_session,
        seed.organization.id,
        idempotency_key=key,
        requested_by_membership_id=seed.membership.id,
        now_utc=MOMENT,
    )
    await db_session.commit()
    monkeypatch.setattr(worker, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(worker, "engine_async", test_engine)
    monkeypatch.setattr(worker, "_now", lambda: MOMENT)
    monkeypatch.setattr(worker, "RECOVERY_ASSESSMENT_SECONDS", 0.0)
    await worker.process_next_jobs()
    await db_session.refresh(seed.state)


async def test_generation_projects_the_class_subject_link(db_session, monkeypatch):
    seed = await seed_generatable_school(
        db_session, clerk_user_id="projection_a", clerk_org_id="projection_org_a"
    )
    await db_session.commit()
    link = await _drop_direct_projection(db_session, seed)
    assert link is not None

    await _queue_generation(db_session, monkeypatch, seed, key="projection-a")

    proposal = await current_proposal(db_session, seed.organization.id, now_utc=MOMENT)
    assert proposal is not None
    assert proposal["can_approve"] is True
    assignments = (
        await db_session.scalars(
            select(CurricularAssignment).where(
                CurricularAssignment.organization_id == seed.organization.id
            )
        )
    ).all()
    assert [(row.class_id, row.subject_id, row.teacher_id) for row in assignments] == [
        (seed.class_.id, seed.subject.id, link.teacher_id)
    ]
    requirements = (
        await db_session.scalars(
            select(CurricularRequirement).where(
                CurricularRequirement.organization_id == seed.organization.id
            )
        )
    ).all()
    assert [(row.module_id, row.sequence, row.required_minutes) for row in requirements] == [
        (seed.module.id, 1, seed.module.required_minutes)
    ]


async def test_the_projection_stays_inside_the_organization(db_session, monkeypatch):
    first = await seed_generatable_school(
        db_session, clerk_user_id="projection_b1", clerk_org_id="projection_org_b1"
    )
    second = await seed_generatable_school(
        db_session,
        clerk_user_id="projection_b2",
        clerk_org_id="projection_org_b2",
        module_minutes=50,
    )
    await db_session.commit()
    await _drop_direct_projection(db_session, first)
    second_link = await _drop_direct_projection(db_session, second)
    await db_session.delete(second_link)
    await db_session.commit()

    await _queue_generation(db_session, monkeypatch, first, key="projection-b")

    assert (
        await db_session.scalars(
            select(CurricularAssignment).where(
                CurricularAssignment.organization_id == first.organization.id
            )
        )
    ).all()
    assert (
        await db_session.scalars(
            select(CurricularAssignment).where(
                CurricularAssignment.organization_id == second.organization.id
            )
        )
    ).all() == []
    assert (
        await db_session.scalars(
            select(CurricularRequirement).where(
                CurricularRequirement.organization_id == second.organization.id
            )
        )
    ).all() == []


async def test_the_projection_follows_link_and_module_changes(db_session):
    seed = await seed_generatable_school(
        db_session, clerk_user_id="projection_c", clerk_org_id="projection_org_c"
    )
    await db_session.commit()
    link = await _drop_direct_projection(db_session, seed)

    created = await sync_curricular_projection(db_session, seed.organization.id, seed.year)
    await db_session.commit()
    assert created == 1
    assignment = await db_session.scalar(
        select(CurricularAssignment).where(
            CurricularAssignment.organization_id == seed.organization.id
        )
    )
    assignment_id = assignment.id

    await sync_curricular_projection(db_session, seed.organization.id, seed.year)
    await db_session.commit()
    assignments = (
        await db_session.scalars(
            select(CurricularAssignment).where(
                CurricularAssignment.organization_id == seed.organization.id
            )
        )
    ).all()
    assert [row.id for row in assignments] == [assignment_id]

    other = await create_teacher_profile(
        db_session, organization_id=seed.organization.id, name="Outro Docente"
    )
    await db_session.refresh(link)
    link.teacher_id = other.id
    await db_session.commit()
    await sync_curricular_projection(db_session, seed.organization.id, seed.year)
    await db_session.commit()
    await db_session.refresh(assignments[0])
    assert assignments[0].teacher_id == other.id

    await db_session.refresh(link)
    await db_session.delete(link)
    await db_session.commit()
    await sync_curricular_projection(db_session, seed.organization.id, seed.year)
    await db_session.commit()
    assert (
        await db_session.scalars(
            select(CurricularAssignment).where(
                CurricularAssignment.organization_id == seed.organization.id
            )
        )
    ).all() == []
    assert (
        await db_session.scalars(
            select(CurricularRequirement).where(
                CurricularRequirement.organization_id == seed.organization.id
            )
        )
    ).all() == []
