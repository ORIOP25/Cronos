from datetime import date

import pytest
from sqlalchemy import select

from app import models
from app.services.scheduler_state_service import (
    SchedulerStateIntegrityError,
    SchedulerStateService,
)


async def _create_org_and_user(db_session):
    organization = models.Organization(name="State Service School", plan_status="active")
    db_session.add(organization)
    await db_session.flush()
    user = models.User(
        email=f"state-service-{organization.id}@example.com",
    )
    db_session.add(user)
    await db_session.flush()
    membership = models.OrganizationMembership(
        organization_id=organization.id,
        account_id=user.id,
        organization_display_name="State Service Admin",
        lifecycle_status=models.MembershipLifecycleStatus.active,
        access_status=models.MembershipAccessStatus.active,
        can_admin=True,
        can_teach=False,
    )
    db_session.add(membership)
    await db_session.flush()
    return organization, membership


async def test_get_or_create_active_state_is_idempotent(db_session):
    organization, _ = await _create_org_and_user(db_session)
    service = SchedulerStateService(db_session)

    first_year, first_state = await service.get_or_create_active_state(
        organization.id,
        start_date=date(2025, 9, 1),
        hard_end_date=date(2026, 7, 15),
    )
    second_year, second_state = await service.get_or_create_active_state(
        organization.id,
        start_date=date(2025, 9, 1),
        hard_end_date=date(2026, 7, 15),
    )

    assert second_year.id == first_year.id
    assert second_state.id == first_state.id
    assert first_state.school_year_publication_state == (
        models.SchoolYearPublicationState.UNPUBLISHED
    )


async def test_active_school_year_rejects_invalid_timezone(db_session):
    organization, _ = await _create_org_and_user(db_session)
    service = SchedulerStateService(db_session)

    with pytest.raises(SchedulerStateIntegrityError):
        await service.get_or_create_active_school_year(
            organization.id,
            start_date=date(2025, 9, 1),
            hard_end_date=date(2026, 7, 15),
            timezone_name="not/a-timezone",
        )


async def test_relevant_change_increments_once_and_records_event(db_session):
    organization, membership = await _create_org_and_user(db_session)
    service = SchedulerStateService(db_session)
    school_year, state = await service.get_or_create_active_state(
        organization.id,
        start_date=date(2025, 9, 1),
        hard_end_date=date(2026, 7, 15),
    )

    event = await service.record_change(
        organization.id,
        entity_type="ROOM",
        entity_id=12,
        operation=models.SchedulerStateChangeOperation.UPDATE,
        before={"capacity": 20, "room_type_id": 1},
        after={"room_type_id": 2, "capacity": 20},
        changed_by_membership_id=membership.id,
    )

    assert event is not None
    assert event.change_scope == models.SchedulerStateChangeScope.FUTURE_IMPACTING
    assert event.version_before == 0
    assert event.version_after == 1
    assert state.scheduler_state_version == 1
    stored = await db_session.scalar(
        select(models.SchedulerStateVersionEvent).where(
            models.SchedulerStateVersionEvent.id == event.id
        )
    )
    assert stored is not None
    assert stored.before_metadata_json == {"capacity": 20, "type": "normal"}


async def test_noop_and_repair_policy_changes_do_not_increment(db_session):
    organization, _ = await _create_org_and_user(db_session)
    service = SchedulerStateService(db_session)
    _, state = await service.get_or_create_active_state(
        organization.id,
        start_date=date(2025, 9, 1),
        hard_end_date=date(2026, 7, 15),
    )

    no_op = await service.record_change(
        organization.id,
        entity_type="ROOM",
        entity_id=4,
        operation=models.SchedulerStateChangeOperation.UPDATE,
        before={"capacity": 20},
        after={"capacity": 20},
    )
    policy = await service.record_change(
        organization.id,
        entity_type="REPAIR_POLICY",
        entity_id=None,
        operation=models.SchedulerStateChangeOperation.UPDATE,
        before={"stability_window_days": 14},
        after={"stability_window_days": 7},
        repair_policy_change=True,
    )

    assert no_op is not None
    assert no_op.change_scope == models.SchedulerStateChangeScope.NO_OP
    assert policy is not None
    assert policy.change_scope == models.SchedulerStateChangeScope.NO_OP
    assert policy.metadata_json == {"repair_policy_change": True}
    assert state.scheduler_state_version == 0


async def test_inactive_resource_change_is_audited_without_increment(db_session):
    organization, _ = await _create_org_and_user(db_session)
    service = SchedulerStateService(db_session)
    _, state = await service.get_or_create_active_state(
        organization.id,
        start_date=date(2025, 9, 1),
        hard_end_date=date(2026, 7, 15),
    )

    event = await service.record_change(
        organization.id,
        entity_type="CLASS_DEMAND",
        entity_id=99,
        operation=models.SchedulerStateChangeOperation.DELETE,
        before={"minutes": 600},
        after=None,
        active_resource=False,
    )

    assert event is not None
    assert event.change_scope == models.SchedulerStateChangeScope.INACTIVE_RESOURCE
    assert state.scheduler_state_version == 0
