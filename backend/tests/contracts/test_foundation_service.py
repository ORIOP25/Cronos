from datetime import date, time

import pytest
from sqlalchemy import select

from app import models, schemas
from app.services import settings_service
from app.services.foundation_service import (
    FoundationDraftVersionConflictError,
    FoundationIncompleteDraftError,
    FoundationService,
)

pytestmark = pytest.mark.postgresql


async def _create_test_org(
    db_session, clerk_id: str = "org_found_test"
) -> tuple[models.Organization, models.OrganizationMembership]:
    org = models.Organization(
        name="Foundation Test School",
        clerk_org_id=clerk_id,
        plan_status=models.OrganizationPlanStatus.active,
        foundation_status=models.OrganizationFoundationStatus.NOT_STARTED,
    )
    db_session.add(org)
    await db_session.flush()

    user = models.User(
        name="Foundation Service Admin",
        email=f"admin_{clerk_id}@test.com",
        clerk_user_id=f"user_{clerk_id}",
    )
    db_session.add(user)
    await db_session.flush()

    mem = models.OrganizationMembership(
        organization_id=org.id,
        account_id=user.id,
        organization_display_name="Foundation Service Admin",
        lifecycle_status=models.MembershipLifecycleStatus.active,
        access_status=models.MembershipAccessStatus.active,
        clerk_membership_id=f"mem_{clerk_id}",
        can_admin=True,
        can_teach=False,
    )
    db_session.add(mem)
    await db_session.flush()
    return org, mem


async def test_foundation_get_status_pure_read(db_session):
    org, mem = await _create_test_org(db_session, "org_found_status")
    service = FoundationService(db_session)

    status = await service.get_status(org.id)
    assert status.foundation_status == "NOT_STARTED"
    assert status.organization_name == "Foundation Test School"
    assert status.first_real_schedule_approved_at is None


async def test_foundation_get_draft_returns_zero_when_empty(db_session):
    org, mem = await _create_test_org(db_session, "org_found_draft_empty")
    service = FoundationService(db_session)

    draft = await service.get_draft(org.id)
    assert draft.version == 0
    assert draft.current_step == 1
    assert draft.data.school_start_date is None


async def test_foundation_save_draft_advances_version_and_sets_in_progress(db_session):
    org, mem = await _create_test_org(db_session, "org_found_save")
    service = FoundationService(db_session)

    write_data = schemas.FoundationDraftWrite(
        expected_version=0,
        current_step=2,
        data=schemas.FoundationDraftData(
            school_start_date=date(2025, 9, 15),
            school_hard_end_date=date(2026, 7, 31),
        ),
    )

    saved = await service.save_draft(org.id, write_data, membership_id=mem.id)
    assert saved.version == 1
    assert saved.current_step == 2
    assert saved.data.school_start_date == date(2025, 9, 15)

    # Check org status transitioned to IN_PROGRESS
    refreshed_org = await db_session.get(models.Organization, org.id)
    assert refreshed_org.foundation_status == models.OrganizationFoundationStatus.IN_PROGRESS

    # Second save with expected_version=1 succeeds and increments to 2
    write_data_2 = schemas.FoundationDraftWrite(
        expected_version=1,
        current_step=3,
        data=schemas.FoundationDraftData(
            school_start_date=date(2025, 9, 15),
            school_hard_end_date=date(2026, 7, 31),
            days_of_week=[0, 1, 2, 3, 4],
        ),
    )
    saved_2 = await service.save_draft(org.id, write_data_2, membership_id=mem.id)
    assert saved_2.version == 2
    assert saved_2.current_step == 3


async def test_foundation_save_draft_detects_version_conflict(db_session):
    org, mem = await _create_test_org(db_session, "org_found_conflict")
    service = FoundationService(db_session)

    # First save
    write_data = schemas.FoundationDraftWrite(
        expected_version=0,
        current_step=2,
        data=schemas.FoundationDraftData(school_start_date=date(2025, 9, 15)),
    )
    await service.save_draft(org.id, write_data, membership_id=mem.id)

    # Stale save with expected_version=0 when current is 1
    stale_write = schemas.FoundationDraftWrite(
        expected_version=0,
        current_step=2,
        data=schemas.FoundationDraftData(school_start_date=date(2025, 9, 20)),
    )
    with pytest.raises(FoundationDraftVersionConflictError) as exc_info:
        await service.save_draft(org.id, stale_write, membership_id=mem.id)
    assert exc_info.value.current_version == 1


async def test_foundation_draft_automatic_holidays_uses_draft_period(db_session, monkeypatch):
    org, mem = await _create_test_org(db_session, "org_found_auto_holidays")
    monkeypatch.setattr(
        settings_service,
        "_get_pt_holidays",
        lambda _years: {
            date(2025, 9, 15): "Dentro",
            date(2025, 9, 14): "Antes",
            date(2026, 7, 31): "Limite",
            date(2026, 8, 1): "Depois",
        },
    )

    service = FoundationService(db_session)
    first = await service.save_draft(
        org.id,
        schemas.FoundationDraftWrite(
            expected_version=0,
            current_step=1,
            data=schemas.FoundationDraftData(
                school_start_date=date(2025, 9, 15),
                school_hard_end_date=date(2026, 7, 31),
            ),
        ),
        membership_id=mem.id,
    )
    assert (await db_session.scalars(select(models.SchoolCalendarEvent))).all() == []

    await service.save_draft(
        org.id,
        schemas.FoundationDraftWrite(
            expected_version=first.version,
            current_step=8,
            data=schemas.FoundationDraftData(
                school_start_date=date(2025, 9, 15),
                school_hard_end_date=date(2026, 7, 31),
                automatic_holidays_enabled=True,
            ),
        ),
        membership_id=mem.id,
    )
    events = (
        await db_session.scalars(
            select(models.SchoolCalendarEvent).order_by(models.SchoolCalendarEvent.start_date)
        )
    ).all()
    assert [(event.start_date, event.name) for event in events] == [
        (date(2025, 9, 15), "Dentro"),
        (date(2026, 7, 31), "Limite"),
    ]

    second = await service.save_draft(
        org.id,
        schemas.FoundationDraftWrite(
            expected_version=2,
            current_step=8,
            data=schemas.FoundationDraftData(
                school_start_date=date(2025, 9, 15),
                school_hard_end_date=date(2026, 8, 1),
                automatic_holidays_enabled=True,
            ),
        ),
        membership_id=mem.id,
    )
    assert second.version == 3
    events = (
        await db_session.scalars(
            select(models.SchoolCalendarEvent).order_by(models.SchoolCalendarEvent.start_date)
        )
    ).all()
    assert [(event.start_date, event.name) for event in events] == [
        (date(2025, 9, 15), "Dentro"),
        (date(2026, 7, 31), "Limite"),
        (date(2026, 8, 1), "Depois"),
    ]


async def test_foundation_complete_transactional_generates_grid(db_session):
    org, mem = await _create_test_org(db_session, "org_found_complete")
    service = FoundationService(db_session)

    # Save full draft
    full_data = schemas.FoundationDraftData(
        school_start_date=date(2025, 9, 15),
        school_hard_end_date=date(2026, 7, 31),
        repair_stability_window_days=14,
        days_of_week=[0, 1, 2, 3, 4],
        opening_time=time(8, 30),
        closing_time=time(17, 30),
        slot_duration_minutes=50,
        break_duration_minutes=10,
        lunch_window_start=time(12, 30),
        lunch_window_end=time(14, 0),
        lunch_min_duration_minutes=60,
    )
    saved = await service.save_draft(
        org.id,
        schemas.FoundationDraftWrite(expected_version=0, current_step=9, data=full_data),
        membership_id=mem.id,
    )

    command = schemas.FoundationCompleteCommand(expected_version=saved.version, confirmed=True)
    res = await service.complete_foundation(org.id, command, membership_id=mem.id)

    assert res.foundation_status == "COMPLETED"
    assert res.foundation_completed_at is not None
    assert res.generated_timeslot_count > 0

    # Org is now COMPLETED
    refreshed_org = await db_session.get(models.Organization, org.id)
    assert refreshed_org.foundation_status == models.OrganizationFoundationStatus.COMPLETED
    assert refreshed_org.foundation_completed_at is not None

    # Idempotent completion call returns same result
    repeat = await service.complete_foundation(org.id, command, membership_id=mem.id)
    assert repeat.foundation_status == "COMPLETED"


async def test_foundation_complete_creates_internship_flows_once(db_session):
    org, mem = await _create_test_org(db_session, "org_found_flows")
    service = FoundationService(db_session)
    full_data = schemas.FoundationDraftData(
        school_start_date=date(2025, 9, 15),
        school_hard_end_date=date(2026, 7, 31),
        repair_stability_window_days=14,
        days_of_week=[0, 1, 2, 3, 4],
        opening_time=time(8, 30),
        closing_time=time(17, 30),
        slot_duration_minutes=50,
        break_duration_minutes=10,
        lunch_window_start=time(12, 30),
        lunch_window_end=time(14, 0),
        lunch_min_duration_minutes=60,
        internship_flows=[
            schemas.FoundationInternshipFlow(
                name="Estágio 10A",
                start_date=date(2026, 2, 2),
                end_date=date(2026, 2, 13),
            )
        ],
    )
    saved = await service.save_draft(
        org.id,
        schemas.FoundationDraftWrite(expected_version=0, current_step=10, data=full_data),
        membership_id=mem.id,
    )
    command = schemas.FoundationCompleteCommand(expected_version=saved.version, confirmed=True)
    await service.complete_foundation(org.id, command, membership_id=mem.id)
    await db_session.commit()

    events = (
        await db_session.scalars(
            select(models.SchoolCalendarEvent).where(
                models.SchoolCalendarEvent.event_type == models.CalendarEventType.internship_flow
            )
        )
    ).all()
    assert [event.name for event in events] == ["Estágio 10A"]
    assert events[0].class_ids == []
    assert events[0].school_year_start_year == 2025

    await service.complete_foundation(org.id, command, membership_id=mem.id)
    await db_session.commit()
    assert (
        await db_session.scalar(
            select(models.SchoolCalendarEvent.id).where(
                models.SchoolCalendarEvent.event_type == models.CalendarEventType.internship_flow
            )
        )
        is not None
    )
    assert (
        len(
            (
                await db_session.scalars(
                    select(models.SchoolCalendarEvent).where(
                        models.SchoolCalendarEvent.event_type
                        == models.CalendarEventType.internship_flow
                    )
                )
            ).all()
        )
        == 1
    )


async def test_foundation_partial_flow_survives_and_blocks_completion(db_session):
    org, mem = await _create_test_org(db_session, "org_found_partial_flow")
    service = FoundationService(db_session)
    full_data = schemas.FoundationDraftData(
        school_start_date=date(2025, 9, 15),
        school_hard_end_date=date(2026, 7, 31),
        repair_stability_window_days=14,
        days_of_week=[0, 1, 2, 3, 4],
        opening_time=time(8, 30),
        closing_time=time(17, 30),
        slot_duration_minutes=50,
        break_duration_minutes=10,
        lunch_window_start=time(12, 30),
        lunch_window_end=time(14, 0),
        lunch_min_duration_minutes=60,
        internship_flows=[
            schemas.FoundationInternshipFlow(name="Estágio 10A"),
        ],
    )
    saved = await service.save_draft(
        org.id,
        schemas.FoundationDraftWrite(expected_version=0, current_step=9, data=full_data),
        membership_id=mem.id,
    )

    draft = await service.get_draft(org.id)
    assert draft.data.internship_flows[0].name == "Estágio 10A"
    assert draft.data.internship_flows[0].start_date is None

    with pytest.raises(FoundationIncompleteDraftError):
        await service.complete_foundation(
            org.id,
            schemas.FoundationCompleteCommand(expected_version=saved.version, confirmed=True),
            membership_id=mem.id,
        )


async def test_foundation_draft_accepts_old_payload_without_flows(db_session):
    org, mem = await _create_test_org(db_session, "org_found_old_draft")
    service = FoundationService(db_session)

    saved = await service.save_draft(
        org.id,
        schemas.FoundationDraftWrite(
            expected_version=0,
            current_step=9,
            data=schemas.FoundationDraftData(
                school_start_date=date(2025, 9, 15),
                school_hard_end_date=date(2026, 7, 31),
            ),
        ),
        membership_id=mem.id,
    )

    assert saved.data.internship_flows == []
    draft = await service.get_draft(org.id)
    assert draft.current_step == 9
    assert draft.data.internship_flows == []
