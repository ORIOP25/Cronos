"""An internship flow keeps its classes out of the flow period through every later generation.

Owner requirement: classes linked to an internship flow have no lessons during the
flow's active period, on the schedule published after the flow is applied and on
every later update (ADAPTIVE_RECOVERY) or new generation (COMPLETE_GENERATION).
The flow's start and end dates are inclusive. Each test runs the real preview,
flow service and worker path on PostgreSQL.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app import models, schemas
from app.scheduler.infrastructure.models import SchedulerLessonLogV1, SchedulerLessonV1
from app.scheduler.infrastructure.occurrences import get_debts
from app.services import internship_flow_service
from tests._support.scheduler_v1 import (
    add_class_sharing_subject,
    run_generation,
    seed_generatable_school,
    seed_joint_school,
)

pytestmark = pytest.mark.postgresql

# Three 50-minute lessons per class on the Monday and Tuesday grid slots.
MODULE_MINUTES = 150
REQUIRED_MINUTES = MODULE_MINUTES
# Tuesday 1 September 2026 and Monday 7 September 2026 are the first two grid days.
FIRST_GRID_DAY = date(2026, 9, 1)
SECOND_GRID_DAY = date(2026, 9, 7)


async def _seed_school(db_session, name: str):
    """Two classes with the same subject and teacher, and an open school calendar."""
    seed = await seed_generatable_school(
        db_session,
        clerk_org_id=f"{name}_org",
        clerk_user_id=f"{name}_admin",
        module_minutes=MODULE_MINUTES,
    )
    _, assignment_b, _ = await add_class_sharing_subject(
        db_session, seed, name="B", module_minutes=MODULE_MINUTES
    )
    db_session.add(_calendar_settings(seed))
    await db_session.commit()
    return seed, assignment_b.id


async def _seed_joint_school(db_session):
    joint = await seed_joint_school(db_session, module_minutes=MODULE_MINUTES)
    db_session.add(_calendar_settings(joint.base))
    await db_session.commit()
    return joint


def _calendar_settings(seed) -> models.OrganizationSettings:
    return models.OrganizationSettings(
        organization_id=seed.organization.id,
        school_start_date=seed.year.start_date,
        school_hard_end_date=seed.year.hard_end_date,
        repair_stability_window_days=0,
    )


async def _apply_flow(db_session, seed, class_ids: list[int], start: date, end: date):
    """Preview, then confirm the flow exactly as the owner-facing endpoint does."""
    organization_id = seed.organization.id
    preview = await internship_flow_service.preview_change(
        db_session,
        organization_id,
        schemas.CalendarEventChangePreviewRequest(
            operation="create",
            event_id=None,
            name="Estágio",
            start_date=start,
            end_date=end,
            class_ids=class_ids,
        ),
    )
    await internship_flow_service.create_flow(
        db_session,
        organization_id,
        schemas.SchoolCalendarEventCreate(
            name="Estágio",
            start_date=start,
            end_date=end,
            event_type=models.CalendarEventType.internship_flow,
            class_ids=class_ids,
            confirmation_fingerprint=preview.confirmation_fingerprint,
        ),
        changed_by_membership_id=seed.membership.id,
    )
    await db_session.commit()
    return preview


async def _lessons(
    db_session, seed, version_id: int, assignment_id: int, *, include_withdrawn: bool
):
    """Lessons of one assignment in one version; withdrawn ones only when asked for."""
    statement = (
        select(SchedulerLessonV1)
        .where(
            SchedulerLessonV1.organization_id == seed.organization.id,
            SchedulerLessonV1.version_id == version_id,
            SchedulerLessonV1.assignment_id == assignment_id,
        )
        .order_by(SchedulerLessonV1.school_date, SchedulerLessonV1.starts_at)
    )
    if not include_withdrawn:
        statement = statement.where(
            SchedulerLessonV1.id.not_in(
                select(SchedulerLessonLogV1.lesson_id).where(
                    SchedulerLessonLogV1.organization_id == seed.organization.id,
                    SchedulerLessonLogV1.withdrawn_at.is_not(None),
                )
            )
        )
    return list((await db_session.scalars(statement)).all())


def _dates(rows) -> list[date]:
    return [row.school_date for row in rows]


def _inside(day: date, start: date, end: date) -> bool:
    return start <= day <= end


def _credit(rows) -> int:
    return sum(row.credit_minutes for row in rows)


async def test_update_keeps_the_flow_class_out_of_the_flow_and_replaces_its_hours(
    db_session, monkeypatch
):
    seed, assignment_b_id = await _seed_school(db_session, "flow_update")
    await run_generation(db_session, monkeypatch, seed, key="flow-update:first")
    first_version = int(seed.state.active_schedule_version_id)
    first_a = await _lessons(
        db_session, seed, first_version, seed.assignment.id, include_withdrawn=False
    )
    first_b = await _lessons(
        db_session, seed, first_version, assignment_b_id, include_withdrawn=False
    )
    assert len(first_a) == 3
    assert _credit(first_a) == REQUIRED_MINUTES
    # The flow starts and ends on lessons of class A, so both edges are removed.
    start, end = first_a[0].school_date, first_a[1].school_date

    preview = await _apply_flow(db_session, seed, [seed.class_.id], start, end)

    assert {row.lesson_id for row in preview.affected_lessons} == {first_a[0].id, first_a[1].id}
    after_flow_a = await _lessons(
        db_session, seed, first_version, seed.assignment.id, include_withdrawn=False
    )
    assert [row.id for row in after_flow_a] == [first_a[2].id]
    after_flow_b = await _lessons(
        db_session, seed, first_version, assignment_b_id, include_withdrawn=False
    )
    assert [row.id for row in after_flow_b] == [row.id for row in first_b]
    withdrawn_logs = (
        await db_session.scalars(
            select(SchedulerLessonLogV1).where(
                SchedulerLessonLogV1.lesson_id.in_([first_a[0].id, first_a[1].id])
            )
        )
    ).all()
    assert len(withdrawn_logs) == 2
    assert all(log.decision == "GAP" and log.withdrawn_at is not None for log in withdrawn_logs)
    assert (await get_debts(db_session, seed.organization.id))["total_gaps"] == 2

    await run_generation(db_session, monkeypatch, seed, key="flow-update:after-flow")

    second_version = int(seed.state.active_schedule_version_id)
    assert second_version != first_version
    second_a = await _lessons(
        db_session, seed, second_version, seed.assignment.id, include_withdrawn=False
    )
    second_b = await _lessons(
        db_session, seed, second_version, assignment_b_id, include_withdrawn=False
    )
    assert len(second_a) == 3
    assert not any(_inside(day, start, end) for day in _dates(second_a))
    assert _credit(second_a) == REQUIRED_MINUTES
    assert _credit(second_b) == REQUIRED_MINUTES
    # The withdrawal stays on the lessons that were withdrawn, never on the re-placed ones.
    withdrawn_ids = {
        row.lesson_id
        for row in await db_session.scalars(
            select(SchedulerLessonLogV1).where(SchedulerLessonLogV1.withdrawn_at.is_not(None))
        )
    }
    assert withdrawn_ids == {first_a[0].id, first_a[1].id}


async def test_first_generation_places_no_flow_class_lessons_on_the_flow_edges_or_inside(
    db_session, monkeypatch
):
    seed, assignment_b_id = await _seed_school(db_session, "flow_first")
    # The flow covers the first two grid days, so both of its edges must stay empty.
    await _apply_flow(db_session, seed, [seed.class_.id], FIRST_GRID_DAY, SECOND_GRID_DAY)

    await run_generation(db_session, monkeypatch, seed, key="flow-first:generation")

    version = int(seed.state.active_schedule_version_id)
    lessons_a = await _lessons(
        db_session, seed, version, seed.assignment.id, include_withdrawn=False
    )
    lessons_b = await _lessons(db_session, seed, version, assignment_b_id, include_withdrawn=False)
    assert _credit(lessons_a) == REQUIRED_MINUTES
    assert not any(_inside(day, FIRST_GRID_DAY, SECOND_GRID_DAY) for day in _dates(lessons_a))
    assert FIRST_GRID_DAY not in _dates(lessons_a)
    assert SECOND_GRID_DAY not in _dates(lessons_a)
    assert _credit(lessons_b) == REQUIRED_MINUTES


async def test_joint_lesson_leaves_for_both_classes_and_is_replaced_outside_the_flow(
    db_session, monkeypatch
):
    joint = await _seed_joint_school(db_session)
    seed = joint.base
    assignment_a_id, assignment_b_id = joint.assignment_ids
    await run_generation(db_session, monkeypatch, seed, key="joint-flow:first")
    first_version = int(seed.state.active_schedule_version_id)
    first_a = await _lessons(
        db_session, seed, first_version, assignment_a_id, include_withdrawn=False
    )
    assert len(first_a) == 3
    assert _dates(first_a) == _dates(
        await _lessons(db_session, seed, first_version, assignment_b_id, include_withdrawn=False)
    )
    start, end = first_a[0].school_date, first_a[1].school_date

    preview = await _apply_flow(db_session, seed, [seed.class_.id], start, end)

    assert {row.lesson_id for row in preview.affected_lessons} == {first_a[0].id, first_a[1].id}
    # Every member loses the joint lesson, so the partner class loses it too (J18).
    after_flow_b = await _lessons(
        db_session, seed, first_version, assignment_b_id, include_withdrawn=False
    )
    assert _dates(after_flow_b) == [day for day in _dates(first_a) if not _inside(day, start, end)]

    await run_generation(db_session, monkeypatch, seed, key="joint-flow:after-flow")

    second_version = int(seed.state.active_schedule_version_id)
    second_a = await _lessons(
        db_session, seed, second_version, assignment_a_id, include_withdrawn=False
    )
    second_b = await _lessons(
        db_session, seed, second_version, assignment_b_id, include_withdrawn=False
    )
    assert not any(_inside(day, start, end) for day in _dates(second_a))
    assert not any(_inside(day, start, end) for day in _dates(second_b))
    assert _credit(second_a) == REQUIRED_MINUTES
    assert _credit(second_b) == REQUIRED_MINUTES
    assert _dates(second_a) == _dates(second_b)
