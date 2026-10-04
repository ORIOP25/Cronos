from datetime import date

import pytest
from sqlalchemy import select

from app import models, schemas
from app.scheduler.infrastructure.progress import configure_school_year
from app.services import settings_service
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


async def _active_year_state(db_session, organization_id: int):
    year = await db_session.scalar(
        select(models.SchedulerSchoolYear).where(
            models.SchedulerSchoolYear.organization_id == organization_id,
            models.SchedulerSchoolYear.is_active.is_(True),
        )
    )
    state = await db_session.scalar(
        select(models.SchedulerSchoolYearState).where(
            models.SchedulerSchoolYearState.organization_id == organization_id,
            models.SchedulerSchoolYearState.school_year_id == year.id,
        )
    )
    return year, state


@pytest.mark.asyncio
async def test_settings_configure_the_preferred_end_date(db_session):
    organization, _ = await create_completed_organization(
        db_session, clerk_user_id="w02_pref_a", clerk_org_id="w02_pref_org_a"
    )
    payload = schemas.OrganizationSettingsUpsert(
        school_start_date=date(2026, 9, 1),
        school_hard_end_date=date(2027, 7, 31),
        preferred_end_date=date(2027, 6, 11),
    )

    await settings_service.upsert_settings(db_session, organization.id, payload)

    year, state = await _active_year_state(db_session, organization.id)
    assert year.preferred_end_date == date(2027, 6, 11)
    assert state.input_revision == 2
    assert state.planning_revision == 2

    await settings_service.upsert_settings(db_session, organization.id, payload)
    await db_session.refresh(state)
    assert state.input_revision == 2
    assert state.planning_revision == 2


@pytest.mark.parametrize("start_year", [2025, 2028])
async def test_calendar_dates_and_preference_change_atomically(db_session, start_year):
    organization, _ = await create_completed_organization(
        db_session,
        clerk_user_id=f"calendar_atomic_{start_year}",
        clerk_org_id=f"calendar_atomic_org_{start_year}",
    )
    await settings_service.upsert_settings(
        db_session,
        organization.id,
        schemas.OrganizationSettingsUpsert(
            school_start_date=date(2026, 9, 1),
            school_hard_end_date=date(2027, 7, 31),
            preferred_end_date=date(2027, 6, 11),
        ),
    )
    await db_session.commit()
    year, state = await _active_year_state(db_session, organization.id)
    previous_revisions = (state.input_revision, state.planning_revision)
    payload = schemas.OrganizationSettingsUpsert(
        school_start_date=date(start_year, 9, 1),
        school_hard_end_date=date(start_year + 1, 7, 31),
        preferred_end_date=date(start_year + 1, 6, 11),
    )

    saved = await settings_service.upsert_settings(db_session, organization.id, payload)
    await db_session.commit()
    await db_session.refresh(year)
    await db_session.refresh(state)
    assert saved.school_start_date == year.start_date == payload.school_start_date
    assert saved.school_hard_end_date == year.hard_end_date == payload.school_hard_end_date
    assert year.preferred_end_date == payload.preferred_end_date
    assert (state.input_revision, state.planning_revision) == tuple(
        revision + 2 for revision in previous_revisions
    )
    await settings_service.upsert_settings(db_session, organization.id, payload)
    await db_session.commit()
    await db_session.refresh(state)
    assert (state.input_revision, state.planning_revision) == tuple(
        revision + 2 for revision in previous_revisions
    )


@pytest.mark.asyncio
async def test_settings_accept_a_partial_preferred_update_inside_the_year(db_session):
    organization, _ = await create_completed_organization(
        db_session, clerk_user_id="w02_pref_b", clerk_org_id="w02_pref_org_b"
    )
    await settings_service.upsert_settings(
        db_session,
        organization.id,
        schemas.OrganizationSettingsUpsert(
            school_start_date=date(2026, 9, 1),
            school_hard_end_date=date(2027, 7, 31),
            preferred_end_date=date(2027, 6, 11),
        ),
    )

    await settings_service.upsert_settings(
        db_session,
        organization.id,
        schemas.OrganizationSettingsUpsert(preferred_end_date=date(2027, 5, 31)),
    )

    year, _ = await _active_year_state(db_session, organization.id)
    assert year.preferred_end_date == date(2027, 5, 31)


@pytest.mark.asyncio
async def test_settings_reject_a_preferred_date_outside_the_school_year(db_session):
    organization, _ = await create_completed_organization(
        db_session, clerk_user_id="w02_pref_c", clerk_org_id="w02_pref_org_c"
    )
    organization_id = organization.id
    await settings_service.upsert_settings(
        db_session,
        organization_id,
        schemas.OrganizationSettingsUpsert(
            school_start_date=date(2026, 9, 1),
            school_hard_end_date=date(2027, 7, 31),
            preferred_end_date=date(2027, 6, 11),
        ),
    )
    await db_session.commit()

    with pytest.raises(ValueError, match="data-alvo"):
        await settings_service.upsert_settings(
            db_session,
            organization_id,
            schemas.OrganizationSettingsUpsert(preferred_end_date=date(2027, 8, 15)),
        )

    await db_session.rollback()
    year, _ = await _active_year_state(db_session, organization_id)
    assert year.preferred_end_date == date(2027, 6, 11)
