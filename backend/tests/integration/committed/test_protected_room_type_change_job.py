"""A room type change does not block the update of a published schedule.

Owner decision 2026-10-18: a school may change a room's type after lessons were
published in it. Protected lessons keep that room; the editable future moves to
rooms that still fit the subject.
"""

from __future__ import annotations

from sqlalchemy import select

from app import models
from app.scheduler.infrastructure.models import SchedulerJobV1, SchedulerLessonV1
from tests._support.scheduler_v1 import run_generation, seed_generatable_school
from tests.integration.committed.test_joint_lesson_diagnostic_job import _enqueue, _run_worker


async def test_an_update_succeeds_after_a_protected_lesson_room_changes_type(
    db_session, monkeypatch
):
    seed = await seed_generatable_school(db_session, module_minutes=200)
    organization_id = seed.organization.id
    settings = await db_session.scalar(
        select(models.OrganizationSettings).where(
            models.OrganizationSettings.organization_id == organization_id
        )
    )
    if settings is None:
        settings = models.OrganizationSettings(organization_id=organization_id)
        db_session.add(settings)
    settings.repair_stability_window_days = 10
    await run_generation(db_session, monkeypatch, seed, key="room-type-publish")
    version_id = int(seed.state.active_schedule_version_id)
    protected_room_ids = set(
        (
            await db_session.scalars(
                select(SchedulerLessonV1.room_id).where(
                    SchedulerLessonV1.organization_id == organization_id,
                    SchedulerLessonV1.version_id == version_id,
                )
            )
        ).all()
    )
    assert protected_room_ids == {seed.room.id}
    laboratory = await db_session.scalar(
        select(models.SchoolRoomType).where(
            models.SchoolRoomType.organization_id == organization_id,
            models.SchoolRoomType.is_normal.is_(False),
        )
    )
    db_session.add(
        models.Room(
            name="Sala nova",
            capacity=seed.room.capacity,
            organization_id=organization_id,
            room_type_id=seed.room.room_type_id,
        )
    )
    seed.room.room_type_id = laboratory.id
    seed.state.input_revision += 1
    seed.state.planning_revision += 1
    queued = await _enqueue(db_session, seed, key="room-type-repair")

    await _run_worker(monkeypatch)

    job = await db_session.get(SchedulerJobV1, queued.job.id)
    await db_session.refresh(job)
    assert (job.status, job.result_code) == ("SUCCEEDED", "COMPLETE")
