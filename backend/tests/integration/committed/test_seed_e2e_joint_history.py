"""Integration proof that the joint-history seed only reads the canonical version.

The pure unit tests cannot prove the query filter. These tests seed a superseded
and an active published version in the isolated test database and assert the
script selects the active version's block and stays idempotent on a repeat call.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from joint_lesson_support import add_joint_lesson, seed_joint_pair
from sqlalchemy import select

from app import models
from app.scheduler.infrastructure.models import SchedulerLessonV1
from scripts import seed_e2e_joint_history as seed_script
from tests._support.scheduler_v1 import add_version

NOW = datetime(2026, 9, 14, 8, 0, tzinfo=UTC)
SUPERSEDED_DATE = date(2026, 9, 15)
ACTIVE_DATE = date(2026, 9, 22)


async def _two_versions(db_session):
    """One older superseded block and the canonical active block for both classes."""
    base, class_b, assignment_b, _group = await seed_joint_pair(
        db_session, clerk_user_id="seed_history", clerk_org_id="seed_history_org"
    )
    base.class_.name = "E2E Joint A"
    class_b.name = "E2E Joint B"
    superseded = await add_version(db_session, base, status="SUPERSEDED", digest="b" * 64)
    active = await add_version(db_session, base, status="ACTIVE", digest="c" * 64)
    await add_joint_lesson(
        db_session,
        base,
        assignment_b,
        superseded,
        stable_key="superseded",
        school_date=SUPERSEDED_DATE,
        start=datetime(2026, 9, 15, 9, 0, tzinfo=UTC),
    )
    active_a, active_b = await add_joint_lesson(
        db_session,
        base,
        assignment_b,
        active,
        stable_key="active",
        school_date=ACTIVE_DATE,
        start=datetime(2026, 9, 22, 10, 0, tzinfo=UTC),
    )
    base.state.active_schedule_version_id = str(active.id)
    base.state.school_year_publication_state = models.SchoolYearPublicationState.PUBLISHED
    await db_session.flush()
    return base, superseded, active_a, active_b


async def test_seed_reads_only_the_canonical_active_version(db_session):
    base, superseded, active_a, active_b = await _two_versions(db_session)

    result = await seed_script.move_first_joint_lesson(
        db_session,
        base.organization.id,
        base.organization.clerk_org_id,
        now_utc=NOW,
    )

    assert result["lesson_ids"] == sorted([active_a.id, active_b.id])
    assert result["school_date"] == (ACTIVE_DATE - timedelta(days=14)).isoformat()
    superseded_rows = list(
        await db_session.scalars(
            select(SchedulerLessonV1).where(SchedulerLessonV1.version_id == superseded.id)
        )
    )
    assert [row.school_date for row in superseded_rows] == [
        SUPERSEDED_DATE,
        SUPERSEDED_DATE,
    ]


async def test_seed_repeated_call_keeps_the_ended_metadata_unchanged(db_session):
    base, _superseded, _active_a, _active_b = await _two_versions(db_session)

    first = await seed_script.move_first_joint_lesson(
        db_session,
        base.organization.id,
        base.organization.clerk_org_id,
        now_utc=NOW,
    )
    await db_session.flush()
    second = await seed_script.move_first_joint_lesson(
        db_session,
        base.organization.id,
        base.organization.clerk_org_id,
        now_utc=NOW,
    )

    assert second == first
    moved = list(
        await db_session.scalars(
            select(SchedulerLessonV1).where(SchedulerLessonV1.id.in_(first["lesson_ids"]))
        )
    )
    assert [row.school_date.isoformat() for row in moved] == [first["school_date"]] * 2
