"""Joint lesson weekly timesheet counts (WBS 5.5)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from joint_lesson_support import add_joint_lesson, seed_joint_pair

from app import models
from app.core.exceptions import AppError
from app.scheduler.infrastructure.models import SchedulerLessonLogV1
from app.services import timesheet_service
from tests._support.scheduler_v1 import add_version

pytestmark = pytest.mark.postgresql

WEEK_START = date(2026, 9, 21)
LOGGED_AT = datetime(2026, 9, 22, 18, tzinfo=UTC)


def _log(db_session, seed, lesson, status: str) -> None:
    db_session.add(
        SchedulerLessonLogV1(
            organization_id=seed.organization.id,
            school_year_id=seed.year.id,
            lesson_id=lesson.id,
            status=status,
            logged_by_membership_id=seed.membership.id,
            logged_at=LOGGED_AT,
            created_at=LOGGED_AT,
            updated_at=LOGGED_AT,
        )
    )


async def _counts(db_session, seed):
    return await db_session.run_sync(
        lambda sync_db: timesheet_service.week_slot_counts_sync(
            sync_db, seed.organization.id, seed.assignment.teacher_id, WEEK_START
        )
    )


async def _submit(db_session, seed):
    return await db_session.run_sync(
        lambda sync_db: timesheet_service.submit_timesheet_sync(
            sync_db,
            organization_id=seed.organization.id,
            teacher_id=seed.assignment.teacher_id,
            week_start_date=WEEK_START,
        )
    )


async def test_a_joint_lesson_counts_once_and_needs_every_record(db_session):
    seed, _class_b, assignment_b, _group = await seed_joint_pair(
        db_session, clerk_user_id="joint_ts", clerk_org_id="joint_ts_org"
    )
    version = await add_version(db_session, seed, status="ACTIVE")
    lesson_a, lesson_b = await add_joint_lesson(
        db_session, seed, assignment_b, version, stable_key="ts1"
    )
    await db_session.commit()

    counts = await _counts(db_session, seed)
    assert counts["total_slots"] == 1

    _log(db_session, seed, lesson_a, "COMPLETED")
    await db_session.commit()
    counts = await _counts(db_session, seed)
    assert counts["total_slots"] == 1
    assert counts["registered_slots"] == 0, "Falta o registo de uma turma irmã."
    with pytest.raises(AppError):
        await _submit(db_session, seed)

    _log(db_session, seed, lesson_b, "COMPLETED")
    await db_session.commit()
    counts = await _counts(db_session, seed)
    assert counts["total_slots"] == 1
    assert counts["registered_slots"] == 1
    assert counts["completed_slots"] == 1
    timesheet = await _submit(db_session, seed)
    assert timesheet.status == models.TimesheetStatus.SUBMITTED


async def test_a_joint_lesson_with_an_occurrence_counts_once(db_session):
    seed, _class_b, assignment_b, _group = await seed_joint_pair(
        db_session, clerk_user_id="joint_ts_occ", clerk_org_id="joint_ts_occ_org"
    )
    version = await add_version(db_session, seed, status="ACTIVE")
    lesson_a, lesson_b = await add_joint_lesson(
        db_session, seed, assignment_b, version, stable_key="ts2"
    )
    _log(db_session, seed, lesson_a, "COMPLETED")
    _log(db_session, seed, lesson_b, "OCCURRENCE")
    await db_session.commit()

    counts = await _counts(db_session, seed)
    assert counts["total_slots"] == 1
    assert counts["registered_slots"] == 1
    assert counts["completed_slots"] == 0
    assert counts["occurrence_slots"] == 1
