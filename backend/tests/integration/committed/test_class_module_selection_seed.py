"""WBS 2.2.1: the scheduler v1 seed records the module selection."""

import pytest
from sqlalchemy import select

from app import models
from tests._support.scheduler_v1 import seed_v1_assignment

pytestmark = pytest.mark.postgresql


@pytest.mark.asyncio
async def test_seed_v1_assignment_records_its_module_selection(db_session):
    seed = await seed_v1_assignment(db_session, clerk_org_id="selection_seed")

    link_id = await db_session.scalar(
        select(models.ClassSubjectLink.id).where(
            models.ClassSubjectLink.organization_id == seed.organization.id,
            models.ClassSubjectLink.class_id == seed.class_.id,
            models.ClassSubjectLink.subject_id == seed.subject.id,
        )
    )
    selected = (
        (
            await db_session.execute(
                select(models.class_subject_module.c.module_id).where(
                    models.class_subject_module.c.organization_id == seed.organization.id,
                    models.class_subject_module.c.class_subject_link_id == link_id,
                )
            )
        )
        .scalars()
        .all()
    )

    assert selected == [seed.module.id]
