"""Deterministic lock-order regression for occurrence mutators.

Every schedule mutator must take the school-year state row lock before any
mutable lesson-log row. The SQLAlchemy ``before_cursor_execute`` event records
the real ``SELECT ... FOR UPDATE`` order, so an inversion fails without sleeps
or timing assumptions.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from joint_lesson_support import add_joint_lesson, seed_joint_pair
from sqlalchemy import event

from app import models, schemas
from app.scheduler.infrastructure import occurrences as occurrences_v1
from app.scheduler.infrastructure.models import SchedulerLessonSliceV1
from app.scheduler.infrastructure.operations import record_lesson_log
from tests._support.db_fixtures import test_engine
from tests._support.scheduler_v1 import add_lesson, add_version, seed_v1_assignment

pytestmark = pytest.mark.postgresql

PAST = datetime(2026, 9, 22, 10, 0, tzinfo=UTC)


@pytest.fixture
def lock_order():
    """Record the ordered ``FOR UPDATE`` targets during the test body."""
    order: list[str] = []

    def _record(connection, cursor, statement, parameters, context, executemany):
        lowered = statement.lower()
        if "for update" not in lowered:
            return
        if "scheduler_school_year_state" in lowered:
            order.append("state")
        elif "scheduler_lesson_log_v1" in lowered:
            order.append("log")
        elif "operational_schedule_block" in lowered:
            order.append("block")
        elif "lesson_log" in lowered:
            order.append("block_log")

    event.listen(test_engine.sync_engine, "before_cursor_execute", _record)
    try:
        yield order
    finally:
        event.remove(test_engine.sync_engine, "before_cursor_execute", _record)


def _assert_state_first(order: list[str]) -> None:
    assert order, "A operação tem de bloquear a linha de estado do ano."
    assert order[0] == "state", f"O estado do ano tem de ser bloqueado primeiro: {order}"
    assert "log" in order, order


async def _seed_single(db_session, *, suffix: str):
    seed = await seed_v1_assignment(
        db_session, clerk_user_id=f"lock_{suffix}", clerk_org_id=f"lock_{suffix}_org"
    )
    version = await add_version(db_session, seed, status="ACTIVE")
    lesson = await add_lesson(
        db_session,
        seed,
        version,
        stable_key=f"lock-{suffix}",
        school_date=PAST.date(),
        start=PAST,
        end=PAST + timedelta(minutes=50),
    )
    db_session.add(
        SchedulerLessonSliceV1(
            organization_id=seed.organization.id,
            school_year_id=seed.year.id,
            lesson_id=lesson.id,
            module_id=seed.module.id,
            offset_minutes=0,
            minutes=50,
        )
    )
    await db_session.commit()
    return seed, version, lesson


async def _occurrence(db_session, seed, lesson) -> dict:
    await record_lesson_log(
        db_session,
        seed.organization.id,
        membership_id=seed.membership.id,
        lesson_id=lesson.id,
        status="OCCURRENCE",
        summary="Falta.",
        notes=None,
        now_utc=PAST,
    )
    await db_session.commit()
    return (await occurrences_v1.list_occurrences(db_session, seed.organization.id))["items"][0]


async def test_given_decision_locks_state_before_log(db_session, lock_order):
    seed, _version, lesson = await _seed_single(db_session, suffix="given")
    item = await _occurrence(db_session, seed, lesson)

    lock_order.clear()
    await occurrences_v1.update_occurrence(
        db_session,
        seed.organization.id,
        item["id"],
        schemas.LessonOccurrenceUpdate(
            status=models.LessonOccurrenceStatus.GIVEN, version=item["version"]
        ),
        decided_by_membership_id=seed.membership.id,
        now_utc=lesson.ends_at,
    )

    _assert_state_first(lock_order)


async def test_gap_decision_locks_state_before_log(db_session, lock_order):
    seed, _version, lesson = await _seed_single(db_session, suffix="gap")
    item = await _occurrence(db_session, seed, lesson)

    lock_order.clear()
    await occurrences_v1.update_occurrence(
        db_session,
        seed.organization.id,
        item["id"],
        schemas.LessonOccurrenceUpdate(
            status=models.LessonOccurrenceStatus.GAP, version=item["version"]
        ),
        decided_by_membership_id=seed.membership.id,
        now_utc=PAST,
    )

    _assert_state_first(lock_order)


async def test_joint_decision_locks_state_before_logs(db_session, lock_order):
    seed, class_b, assignment_b, _group = await seed_joint_pair(
        db_session, clerk_user_id="lock_joint", clerk_org_id="lock_joint_org"
    )
    version = await add_version(db_session, seed, status="ACTIVE")
    lesson_a, _lesson_b = await add_joint_lesson(
        db_session, seed, assignment_b, version, stable_key="lock-joint", start=PAST
    )
    await db_session.commit()
    item = await _occurrence(db_session, seed, lesson_a)

    lock_order.clear()
    await occurrences_v1.update_occurrence(
        db_session,
        seed.organization.id,
        item["id"],
        schemas.LessonOccurrenceUpdate(
            status=models.LessonOccurrenceStatus.GAP,
            version=item["version"],
            class_ids=[seed.class_.id, class_b.id],
        ),
        decided_by_membership_id=seed.membership.id,
        now_utc=PAST,
    )

    _assert_state_first(lock_order)
    assert lock_order.count("log") >= 2, lock_order


async def test_cancel_locks_state_before_log(db_session, lock_order):
    seed, _version, lesson = await _seed_single(db_session, suffix="cancel")
    item = await _occurrence(db_session, seed, lesson)
    decided = await occurrences_v1.update_occurrence(
        db_session,
        seed.organization.id,
        item["id"],
        schemas.LessonOccurrenceUpdate(
            status=models.LessonOccurrenceStatus.GAP, version=item["version"]
        ),
        decided_by_membership_id=seed.membership.id,
        now_utc=PAST,
    )
    await db_session.commit()

    lock_order.clear()
    await occurrences_v1.cancel_occurrence(
        db_session,
        seed.organization.id,
        item["id"],
        version=decided["version"],
        reason="Reversão de ordem de bloqueio",
        cancelled_by_membership_id=seed.membership.id,
        now_utc=PAST,
    )

    _assert_state_first(lock_order)
