"""HTTP regression for the v1 lesson log route under the runtime role.

``async_client`` runs every request through ``RuntimeTestingSessionLocal`` (the
``cronos_app`` role), while direct ``db_session`` tests run as the migration
role. ``cronos_app`` only has ``SELECT, INSERT`` on ``scheduler_lesson_v1``, so
a ``SELECT ... FOR UPDATE`` on that immutable table is a privilege violation
that surfaced as HTTP 500. These tests exercise the real HTTP path and keep the
runtime role honest.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from joint_lesson_support import add_joint_lesson, seed_joint_pair
from sqlalchemy import select

from app import models
from app.scheduler.infrastructure.models import SchedulerLessonLogV1, SchedulerLessonSliceV1
from app.scheduler.infrastructure.progress import load_executed_minutes
from tests._support.scheduler_v1 import add_lesson, add_version, seed_v1_assignment

pytestmark = pytest.mark.postgresql

PAST_START = datetime(2026, 9, 22, 10, 0, tzinfo=UTC)
FUTURE_START = datetime(2027, 6, 1, 9, 0, tzinfo=UTC)


async def _seed_http_school(db_session, *, clerk_user_id: str, clerk_org_id: str):
    seed = await seed_v1_assignment(
        db_session, clerk_user_id=clerk_user_id, clerk_org_id=clerk_org_id
    )
    version = await add_version(db_session, seed, status="ACTIVE")
    await db_session.commit()
    return seed, version


async def _add_lesson(db_session, seed, version, *, key: str, start: datetime, minutes: int = 50):
    end = start + timedelta(minutes=minutes)
    lesson = await add_lesson(
        db_session,
        seed,
        version,
        stable_key=key,
        school_date=start.date(),
        start=start,
        end=end,
        credit_minutes=minutes,
    )
    db_session.add(
        SchedulerLessonSliceV1(
            organization_id=seed.organization.id,
            school_year_id=seed.year.id,
            lesson_id=lesson.id,
            module_id=seed.module.id,
            offset_minutes=0,
            minutes=minutes,
        )
    )
    await db_session.commit()
    return lesson


def _headers(clerk_user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer test_{clerk_user_id}"}


async def test_ordinary_occurrence_log_returns_200(db_session, async_client):
    seed, version = await _seed_http_school(
        db_session, clerk_user_id="http_occ_admin", clerk_org_id="http_occ_org"
    )
    lesson = await _add_lesson(db_session, seed, version, key="http-occ", start=PAST_START)

    response = await async_client.put(
        f"/api/v1/schedule/lessons/{lesson.id}/log",
        json={"status": "OCCURRENCE", "summary": "Falta registada.", "notes": None},
        headers=_headers("http_occ_admin"),
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "OCCURRENCE"


async def test_future_completed_log_returns_422_lesson_not_finished(db_session, async_client):
    seed, version = await _seed_http_school(
        db_session, clerk_user_id="http_future_admin", clerk_org_id="http_future_org"
    )
    lesson = await _add_lesson(db_session, seed, version, key="http-future", start=FUTURE_START)

    response = await async_client.put(
        f"/api/v1/schedule/lessons/{lesson.id}/log",
        json={"status": "COMPLETED", "summary": "Cedo.", "notes": None},
        headers=_headers("http_future_admin"),
    )

    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "lesson_not_finished"


async def test_past_completed_log_returns_200_and_credits_once(db_session, async_client):
    seed, version = await _seed_http_school(
        db_session, clerk_user_id="http_past_admin", clerk_org_id="http_past_org"
    )
    lesson = await _add_lesson(db_session, seed, version, key="http-past", start=PAST_START)

    response = await async_client.put(
        f"/api/v1/schedule/lessons/{lesson.id}/log",
        json={"status": "COMPLETED", "summary": "Aula dada.", "notes": None},
        headers=_headers("http_past_admin"),
    )

    assert response.status_code == 200, response.text
    assert response.json()["credited_minutes"] == lesson.credit_minutes
    await db_session.commit()
    executed = await load_executed_minutes(db_session, seed.organization.id, [seed.assignment.id])
    assert sum(executed[seed.assignment.id].values()) == lesson.credit_minutes


async def test_frozen_week_returns_409_without_effects(db_session, async_client):
    seed, version = await _seed_http_school(
        db_session, clerk_user_id="http_frozen_admin", clerk_org_id="http_frozen_org"
    )
    lesson = await _add_lesson(db_session, seed, version, key="http-frozen", start=PAST_START)
    week_start = lesson.school_date - timedelta(days=lesson.school_date.weekday())
    db_session.add(
        models.TeacherWeeklyTimesheet(
            organization_id=seed.organization.id,
            teacher_id=seed.assignment.teacher_id,
            week_start_date=week_start,
            status=models.TimesheetStatus.SUBMITTED,
        )
    )
    await db_session.commit()

    response = await async_client.put(
        f"/api/v1/schedule/lessons/{lesson.id}/log",
        json={"status": "COMPLETED", "summary": "Fora de prazo.", "notes": None},
        headers=_headers("http_frozen_admin"),
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "week_locked"
    await db_session.commit()
    log = await db_session.scalar(
        select(SchedulerLessonLogV1).where(SchedulerLessonLogV1.lesson_id == lesson.id)
    )
    assert log is None


async def test_joint_absent_completed_is_atomic_over_http(db_session, async_client):
    seed, class_b, assignment_b, _group = await seed_joint_pair(
        db_session, clerk_user_id="http_joint_admin", clerk_org_id="http_joint_org"
    )
    version = await add_version(db_session, seed, status="ACTIVE")
    lesson_a, _lesson_b = await add_joint_lesson(
        db_session, seed, assignment_b, version, stable_key="http-joint", start=PAST_START
    )
    await db_session.commit()

    response = await async_client.put(
        f"/api/v1/schedule/lessons/{lesson_a.id}/log",
        json={
            "status": "COMPLETED",
            "summary": "Aula conjunta.",
            "notes": None,
            "absent_class_ids": [class_b.id],
        },
        headers=_headers("http_joint_admin"),
    )

    assert response.status_code == 200, response.text
    classes = {row["class_id"]: row for row in response.json()["classes"]}
    assert classes[seed.class_.id]["credited_minutes"] == lesson_a.credit_minutes
    assert classes[class_b.id]["status"] == "OCCURRENCE"
    await db_session.commit()
    executed_b = await load_executed_minutes(db_session, seed.organization.id, [assignment_b.id])
    assert sum(executed_b.get(assignment_b.id, {}).values()) == 0
