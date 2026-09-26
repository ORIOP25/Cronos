from datetime import date

import pytest

from app import models
from app.scheduler.infrastructure.progress import configure_school_year
from tests._support.db_fixtures import TestingSessionLocal, create_completed_organization

pytestmark = pytest.mark.postgresql


async def _seed_year(db_session, clerk_user_id: str, clerk_org_id: str):
    organization, _ = await create_completed_organization(
        db_session, clerk_user_id=clerk_user_id, clerk_org_id=clerk_org_id
    )
    year = models.SchedulerSchoolYear(
        organization_id=organization.id,
        label="2026/27",
        start_date=date(2026, 9, 1),
        hard_end_date=date(2027, 7, 31),
    )
    db_session.add(year)
    await db_session.flush()
    state = models.SchedulerSchoolYearState(
        organization_id=organization.id,
        school_year_id=year.id,
        school_year_publication_state=models.SchoolYearPublicationState.UNPUBLISHED,
        scheduler_state_version=0,
        lock_version=0,
    )
    db_session.add(state)
    await db_session.flush()
    return organization, year, state


@pytest.mark.asyncio
async def test_configuration_change_updates_preference_and_consumes_revisions(db_session):
    organization, year, state = await _seed_year(db_session, "w02_config_a", "w02_config_org_a")

    changed = await configure_school_year(
        db_session, organization.id, year.id, preferred_end_date=date(2027, 6, 11)
    )

    assert changed is True
    assert year.preferred_end_date == date(2027, 6, 11)
    assert (state.input_revision, state.planning_revision) == (1, 1)


@pytest.mark.asyncio
async def test_repeated_configuration_is_a_no_op_without_revisions(db_session):
    organization, year, state = await _seed_year(db_session, "w02_config_b", "w02_config_org_b")
    await configure_school_year(
        db_session, organization.id, year.id, preferred_end_date=date(2027, 6, 11)
    )

    changed = await configure_school_year(
        db_session, organization.id, year.id, preferred_end_date=date(2027, 6, 11)
    )

    assert changed is False
    assert (state.input_revision, state.planning_revision) == (1, 1)


@pytest.mark.asyncio
async def test_invalid_date_order_is_rejected_without_revisions(db_session):
    organization, year, state = await _seed_year(db_session, "w02_config_c", "w02_config_org_c")

    with pytest.raises(ValueError, match="start <= preferred"):
        await configure_school_year(
            db_session, organization.id, year.id, preferred_end_date=date(2027, 8, 15)
        )

    assert year.preferred_end_date is None
    assert (state.input_revision, state.planning_revision) == (0, 0)


@pytest.mark.asyncio
async def test_rollback_preserves_the_previous_configuration(db_session):
    organization, year, state = await _seed_year(db_session, "w02_config_d", "w02_config_org_d")
    await configure_school_year(
        db_session, organization.id, year.id, preferred_end_date=date(2027, 6, 11)
    )
    await db_session.commit()

    async with TestingSessionLocal() as session:
        await configure_school_year(
            session, organization.id, year.id, preferred_end_date=date(2027, 6, 20)
        )
        await session.rollback()

    async with TestingSessionLocal() as session:
        refreshed_year = await session.get(models.SchedulerSchoolYear, year.id)
        refreshed_state = await session.get(models.SchedulerSchoolYearState, state.id)
    assert refreshed_year.preferred_end_date == date(2027, 6, 11)
    assert (refreshed_state.input_revision, refreshed_state.planning_revision) == (1, 1)


@pytest.mark.asyncio
async def test_configuration_rejects_another_school_year(db_session):
    organization, year, _ = await _seed_year(db_session, "w02_config_e", "w02_config_org_e")
    other, other_year, _ = await _seed_year(db_session, "w02_config_f", "w02_config_org_f")

    with pytest.raises(ValueError, match="does not (exist|belong)"):
        await configure_school_year(
            db_session, organization.id, other_year.id, preferred_end_date=date(2027, 6, 11)
        )
    assert other_year.preferred_end_date is None
