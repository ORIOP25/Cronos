"""WBS 2.3.2/2.3.4: the engine reads the class grid as engine preferences."""

from sqlalchemy import select

from app import models
from app.scheduler.composition import generate_schedule
from app.scheduler.domain.candidate import SchedulingStrategy, UnavailableResource
from app.scheduler.infrastructure.snapshot import load_snapshot
from tests._support.scheduler_v1 import MOMENT, seed_generatable_school


async def _monday_timeslot(db, seed):
    return await db.scalar(
        select(models.Timeslot).where(
            models.Timeslot.organization_id == seed.organization.id,
            models.Timeslot.day_of_week == 0,
        )
    )


async def _class_snapshot(db, seed):
    return await load_snapshot(
        db,
        seed.organization.id,
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        now_utc=MOMENT,
        school_year_id=seed.year.id,
    )


async def _set_class_score(db, seed, timeslot_id, score):
    db.add(
        models.ClassAvailability(
            organization_id=seed.organization.id,
            class_id=seed.class_.id,
            timeslot_id=timeslot_id,
            score=score,
        )
    )
    await db.commit()


async def test_an_impossible_class_block_is_a_hard_class_unavailability(db_session):
    seed = await seed_generatable_school(db_session, clerk_org_id="class_avail_hard")
    await db_session.commit()
    monday = await _monday_timeslot(db_session, seed)
    await _set_class_score(db_session, seed, monday.id, models.PreferenceLevel.IMPOSSIBLE.value)

    bundle = await _class_snapshot(db_session, seed)

    blocked = [
        row
        for row in bundle.snapshot.unavailable
        if row.resource_type is UnavailableResource.CLASS and row.resource_id == seed.class_.id
    ]
    assert blocked
    assert all(row.period.school_date.weekday() == 0 for row in blocked)
    assert not any(
        row.resource_type is UnavailableResource.CLASS for row in bundle.snapshot.soft_unavailable
    )


async def test_an_avoid_class_block_is_a_soft_class_unavailability(db_session):
    seed = await seed_generatable_school(db_session, clerk_org_id="class_avail_avoid")
    await db_session.commit()
    monday = await _monday_timeslot(db_session, seed)
    await _set_class_score(db_session, seed, monday.id, models.PreferenceLevel.AVOID.value)

    bundle = await _class_snapshot(db_session, seed)

    soft = [
        row
        for row in bundle.snapshot.soft_unavailable
        if row.resource_type is UnavailableResource.CLASS and row.resource_id == seed.class_.id
    ]
    assert soft
    assert all(row.period.school_date.weekday() == 0 for row in soft)
    assert not any(
        row.resource_type is UnavailableResource.CLASS for row in bundle.snapshot.unavailable
    )


async def test_an_archived_class_keeps_its_grid_out_of_the_snapshot(db_session):
    seed = await seed_generatable_school(db_session, clerk_org_id="class_avail_archived")
    await db_session.commit()
    monday = await _monday_timeslot(db_session, seed)
    await _set_class_score(db_session, seed, monday.id, models.PreferenceLevel.IMPOSSIBLE.value)
    seed.class_.is_archived = True
    await db_session.commit()

    bundle = await _class_snapshot(db_session, seed)

    assert not any(
        row.resource_type is UnavailableResource.CLASS for row in bundle.snapshot.unavailable
    )


async def test_generation_never_places_a_class_lesson_in_its_impossible_block(db_session):
    seed = await seed_generatable_school(
        db_session, clerk_org_id="class_avail_generation", module_minutes=50
    )
    await db_session.commit()
    monday = await _monday_timeslot(db_session, seed)
    await _set_class_score(db_session, seed, monday.id, models.PreferenceLevel.IMPOSSIBLE.value)

    bundle = await _class_snapshot(db_session, seed)
    result = generate_schedule(bundle.snapshot, bundle.periods, time_limit_seconds=5)

    assert result.outcome == "COMPLETE"
    assert result.report is not None and result.report.valid
    assert result.candidate is not None
    assert all(lesson.period.school_date.weekday() != 0 for lesson in result.candidate.lessons)
