from datetime import time

import pytest

from app import models
from app.scheduler.domain.candidate import LunchRule, SchedulingStrategy
from app.scheduler.infrastructure.snapshot import SnapshotConfigurationError, load_snapshot
from tests._support.scheduler_v1 import MOMENT, add_version, seed_generatable_school


async def _with_stability_window(db_session, seed, days: int) -> None:
    db_session.add(
        models.OrganizationSettings(
            organization_id=seed.organization.id,
            repair_stability_window_days=days,
        )
    )
    await db_session.flush()


async def test_first_generation_ignores_the_stability_window(db_session):
    seed = await seed_generatable_school(db_session, clerk_org_id="stability_first")
    await _with_stability_window(db_session, seed, 5)
    await db_session.commit()

    bundle = await load_snapshot(
        db_session,
        seed.organization.id,
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        now_utc=MOMENT,
        school_year_id=seed.year.id,
    )

    assert bundle.snapshot.protected_dates == frozenset()
    assert bundle.snapshot.active_version_id is None


async def test_adaptive_recovery_keeps_the_stability_window(db_session):
    seed = await seed_generatable_school(db_session, clerk_org_id="stability_repair")
    await _with_stability_window(db_session, seed, 5)
    await add_version(db_session, seed, status="ACTIVE")
    await db_session.commit()

    bundle = await load_snapshot(
        db_session,
        seed.organization.id,
        strategy=SchedulingStrategy.ADAPTIVE_RECOVERY,
        now_utc=MOMENT,
        school_year_id=seed.year.id,
    )

    assert len(bundle.snapshot.protected_dates) == 5


async def test_complete_generation_with_a_published_version_is_rejected(db_session):
    seed = await seed_generatable_school(db_session, clerk_org_id="incoherent_first")
    await add_version(db_session, seed, status="ACTIVE")
    await db_session.commit()

    with pytest.raises(SnapshotConfigurationError) as error:
        await load_snapshot(
            db_session,
            seed.organization.id,
            strategy=SchedulingStrategy.COMPLETE_GENERATION,
            now_utc=MOMENT,
            school_year_id=seed.year.id,
        )

    assert error.value.code == "ACTIVE_VERSION_PUBLISHED"


async def test_incomplete_lunch_configuration_is_reported(db_session):
    seed = await seed_generatable_school(db_session, clerk_org_id="lunch_incomplete")
    db_session.add(
        models.OrganizationGridSettings(
            organization_id=seed.organization.id,
            lunch_window_start=time(12, 0),
        )
    )
    await db_session.commit()

    with pytest.raises(SnapshotConfigurationError) as error:
        await load_snapshot(
            db_session,
            seed.organization.id,
            strategy=SchedulingStrategy.COMPLETE_GENERATION,
            now_utc=MOMENT,
            school_year_id=seed.year.id,
        )

    assert error.value.code == "LUNCH_CONFIGURATION_INCOMPLETE"


async def test_a_complete_lunch_configuration_becomes_a_rule(db_session):
    seed = await seed_generatable_school(db_session, clerk_org_id="lunch_complete")
    db_session.add(
        models.OrganizationGridSettings(
            organization_id=seed.organization.id,
            lunch_window_start=time(12, 0),
            lunch_window_end=time(14, 0),
            lunch_min_duration_minutes=60,
        )
    )
    await db_session.commit()

    bundle = await load_snapshot(
        db_session,
        seed.organization.id,
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        now_utc=MOMENT,
        school_year_id=seed.year.id,
    )

    assert bundle.snapshot.lunch_rule == LunchRule(
        window_start=time(12, 0), window_end=time(14, 0), minimum_minutes=60
    )
