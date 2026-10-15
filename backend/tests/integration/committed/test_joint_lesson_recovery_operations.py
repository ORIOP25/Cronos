"""Joint lesson deficit and debt operations (WBS 5.4).

The engine-generated end-to-end recovery (a ``D`` unit placed before the next
joint segment) depends on the generation engine PR and is verified there. This
file proves the operation-side deficit: an absent class keeps its own debt and
the present class is credited, so the repair has exact demand to restore.
"""

from __future__ import annotations

import pytest
from joint_lesson_support import add_joint_lesson, seed_joint_pair

from app import models, schemas
from app.scheduler.infrastructure import occurrences as occurrences_v1
from app.scheduler.infrastructure.operations import record_lesson_log
from app.scheduler.infrastructure.progress import load_executed_minutes, load_open_debt
from tests._support.scheduler_v1 import add_version

pytestmark = pytest.mark.postgresql


async def test_an_absent_class_keeps_debt_while_the_present_class_is_credited(db_session):
    seed, class_b, assignment_b, _group = await seed_joint_pair(
        db_session, clerk_user_id="joint_rec", clerk_org_id="joint_rec_org"
    )
    version = await add_version(db_session, seed, status="ACTIVE")
    lesson_a, _lesson_b = await add_joint_lesson(
        db_session, seed, assignment_b, version, stable_key="rec1"
    )
    await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=lesson_a.id,
        status="COMPLETED",
        summary="Aula conjunta.",
        notes=None,
        now_utc=lesson_a.ends_at,
        absent_class_ids=[class_b.id],
    )
    await db_session.commit()
    item = (await occurrences_v1.list_occurrences(db_session, seed.organization.id))["items"][0]

    await occurrences_v1.update_occurrence(
        db_session,
        seed.organization.id,
        item["id"],
        schemas.LessonOccurrenceUpdate(
            status=models.LessonOccurrenceStatus.GAP, version=item["version"]
        ),
        decided_by_membership_id=seed.membership.id,
        now_utc=lesson_a.ends_at,
    )
    await db_session.commit()

    # The present class keeps its executed minutes and no debt.
    executed_a = await load_executed_minutes(db_session, seed.organization.id, [seed.assignment.id])
    assert sum(executed_a[seed.assignment.id].values()) == lesson_a.credit_minutes
    debt_a, _ = await load_open_debt(db_session, seed.organization.id, [seed.assignment.id])
    assert sum(debt_a.values()) == 0

    # The absent class has no execution and an exact open deficit.
    executed_b = await load_executed_minutes(db_session, seed.organization.id, [assignment_b.id])
    assert sum(executed_b.get(assignment_b.id, {}).values()) == 0
    debt_b, _ = await load_open_debt(db_session, seed.organization.id, [assignment_b.id])
    assert sum(debt_b.values()) == lesson_a.credit_minutes

    debts = await occurrences_v1.get_debts(db_session, seed.organization.id)
    assert debts["total_gaps"] == 1
    assert debts["items"][0]["class_id"] == class_b.id
