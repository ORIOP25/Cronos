"""Joint lesson internship withdrawal (WBS 5.6, decision J18)."""

from __future__ import annotations

from datetime import time

import pytest
from joint_lesson_support import SCHOOL_DATE, add_joint_lesson, seed_joint_pair
from sqlalchemy import select

from app import models
from app.scheduler.infrastructure.models import SchedulerLessonLogV1
from app.scheduler.infrastructure.occurrences import get_debts
from app.services import internship_flow_service
from tests._support.scheduler_v1 import add_version

pytestmark = pytest.mark.postgresql


async def test_an_internship_withdraws_every_joint_sibling_with_gap(db_session):
    seed, class_b, assignment_b, _group = await seed_joint_pair(
        db_session, clerk_user_id="joint_int", clerk_org_id="joint_int_org"
    )
    seed.year.timezone = "UTC"
    version = await add_version(db_session, seed, status="ACTIVE")
    lesson_a, lesson_b = await add_joint_lesson(
        db_session, seed, assignment_b, version, stable_key="int1"
    )
    db_session.add(
        models.Timeslot(
            organization_id=seed.organization.id,
            day_of_week=SCHOOL_DATE.weekday(),
            start_time=time(10, 0),
            end_time=time(10, 50),
        )
    )
    await db_session.commit()

    impact = await internship_flow_service.compute_impact(
        db_session, seed.organization.id, [seed.class_.id], SCHOOL_DATE, SCHOOL_DATE
    )
    assert {lesson.lesson_id for lesson in impact.lessons} == {lesson_a.id}
    await internship_flow_service._record_internship_occurrences(
        db_session, seed.organization.id, impact.lessons, seed.membership.id
    )
    await internship_flow_service.remove_affected_blocks(
        db_session, seed.organization.id, impact.lessons
    )
    await db_session.commit()

    logs = {
        row.lesson_id: row
        for row in (
            await db_session.scalars(
                select(SchedulerLessonLogV1).where(
                    SchedulerLessonLogV1.lesson_id.in_([lesson_a.id, lesson_b.id])
                )
            )
        ).all()
    }
    assert set(logs) == {lesson_a.id, lesson_b.id}
    assert all(row.withdrawn_at is not None for row in logs.values())
    assert all(row.decision == "GAP" for row in logs.values())
    assert logs[lesson_a.id].notes == internship_flow_service.INTERNSHIP_BLOCKED_NOTE
    assert logs[lesson_b.id].notes == (f"Aula conjunta retirada por estágio de {seed.class_.name}")

    debts = await get_debts(db_session, seed.organization.id)
    assert debts["total_gaps"] == 2
