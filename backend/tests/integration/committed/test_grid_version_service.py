from datetime import date, time

from app import models, schemas
from app.services import grid_version_service, settings_service, timeslot_service


async def _create_org(db_session) -> models.Organization:
    organization = models.Organization(name="Grid Version School", plan_status="active")
    db_session.add(organization)
    await db_session.flush()
    return organization


def _bulk(**changes) -> schemas.TimeslotBulkCreate:
    payload = {
        "start_time": "09:00",
        "end_time": "11:45",
        "slot_duration_minutes": 50,
        "break_duration_minutes": 10,
        "break_overrides": [{"after_slot": 2, "duration_minutes": 5}],
        "days_of_week": [0, 4],
    }
    payload.update(changes)
    return schemas.TimeslotBulkCreate(**payload)


async def _regenerate(db_session, organization, settings) -> int:
    plan = await timeslot_service.preflight_grid_regeneration(db_session, settings, organization.id)
    return await timeslot_service.apply_grid_regeneration(db_session, plan)


async def test_regeneration_stores_overrides_in_the_active_version(db_session):
    organization = await _create_org(db_session)
    settings = _bulk()

    count = await _regenerate(db_session, organization, settings)
    assert count == 6

    version = await grid_version_service.get_active_grid_version(db_session, organization.id)
    assert version is not None
    assert version.state == models.GridVersionState.ACTIVE
    assert version.configuration_json == {
        "opening_time": "09:00",
        "closing_time": "11:45",
        "slot_duration_minutes": 50,
        "break_duration_minutes": 10,
        "break_overrides": [{"after_slot": 2, "duration_minutes": 5}],
        "days_of_week": [0, 4],
    }

    resolved = await grid_version_service.resolve_grid(
        db_session, organization.id, date(2025, 9, 15)
    )
    assert resolved.version is not None
    assert resolved.version.id == version.id
    assert len(resolved.blocks) == 6
    assert {
        (block.start_time, block.end_time) for block in resolved.blocks if block.day_of_week == 0
    } == {
        (time(9, 0), time(9, 50)),
        (time(10, 0), time(10, 50)),
        (time(10, 55), time(11, 45)),
    }

    await _regenerate(db_session, organization, _bulk(break_overrides=[]))
    version_after = await grid_version_service.get_active_grid_version(db_session, organization.id)
    assert version_after is not None
    assert version_after.id == version.id
    assert version_after.configuration_json is not None
    assert version_after.configuration_json["break_overrides"] == []
    resolved_after = await grid_version_service.resolve_grid(
        db_session, organization.id, date(2025, 9, 15)
    )
    assert len(resolved_after.blocks) == 4
    assert all(block.grid_version_id == version.id for block in resolved_after.blocks)


async def test_resolution_uses_effective_dates_and_hides_pending_versions(db_session):
    organization = await _create_org(db_session)
    older = models.GridVersion(
        organization_id=organization.id,
        effective_date=date(2025, 9, 15),
        state=models.GridVersionState.ACTIVE,
    )
    newer = models.GridVersion(
        organization_id=organization.id,
        effective_date=date(2026, 1, 5),
        state=models.GridVersionState.ACTIVE,
    )
    pending = models.GridVersion(
        organization_id=organization.id,
        effective_date=date(2026, 3, 2),
        state=models.GridVersionState.PENDING,
    )
    db_session.add_all([older, newer, pending])
    await db_session.flush()
    for version, start in ((older, 9), (newer, 10), (pending, 11)):
        db_session.add(
            models.Timeslot(
                organization_id=organization.id,
                grid_version_id=version.id,
                day_of_week=0,
                start_time=time(start, 0),
                end_time=time(start, 50),
            )
        )
    await db_session.flush()

    assert (
        await grid_version_service.resolve_grid_version(
            db_session, organization.id, date(2025, 10, 1)
        )
    ).id == older.id
    assert (
        await grid_version_service.resolve_grid_version(
            db_session, organization.id, date(2026, 2, 1)
        )
    ).id == newer.id
    assert (
        await grid_version_service.resolve_grid_version(
            db_session, organization.id, date(2025, 10, 1), pending_version_id=pending.id
        )
    ).id == pending.id
    assert (
        await grid_version_service.resolve_grid_version(
            db_session, organization.id, date(2025, 10, 1), pending_version_id=999
        )
        is None
    )


async def test_legacy_unversioned_blocks_fallback_to_the_active_version(db_session):
    organization = await _create_org(db_session)
    version = await grid_version_service.ensure_active_grid_version(db_session, organization.id)
    db_session.add(
        models.Timeslot(
            organization_id=organization.id,
            day_of_week=1,
            start_time=time(8, 0),
            end_time=time(8, 50),
        )
    )
    await db_session.flush()

    resolved = await grid_version_service.resolve_grid(
        db_session, organization.id, date(2026, 1, 1)
    )
    assert resolved.version is not None
    assert resolved.version.id == version.id
    assert [block.start_time for block in resolved.blocks] == [time(8, 0)]


async def test_ensure_active_version_reuses_the_existing_version(db_session):
    organization = await _create_org(db_session)
    first = await grid_version_service.ensure_active_grid_version(db_session, organization.id)
    second = await grid_version_service.ensure_active_grid_version(db_session, organization.id)
    assert first.id == second.id


async def test_foundation_completion_generates_the_variable_break_sequence(db_session):
    from app.services.foundation_service import FoundationService

    organization = await _create_org(db_session)
    account = models.User(name="Foundation Admin", email="foundation-admin@test.invalid")
    db_session.add(account)
    await db_session.flush()
    membership = models.OrganizationMembership(
        organization_id=organization.id,
        account_id=account.id,
        organization_display_name="Foundation Admin",
        lifecycle_status=models.MembershipLifecycleStatus.active,
        access_status=models.MembershipAccessStatus.active,
        can_admin=True,
        can_teach=False,
    )
    db_session.add(membership)
    await db_session.flush()

    service = FoundationService(db_session)
    await service.save_draft(
        organization.id,
        schemas.FoundationDraftWrite(
            expected_version=0,
            current_step=5,
            data=schemas.FoundationDraftData(
                school_start_date=date(2025, 9, 15),
                school_hard_end_date=date(2026, 7, 31),
                days_of_week=[0],
                opening_time=time(9, 0),
                closing_time=time(11, 45),
                slot_duration_minutes=50,
                break_duration_minutes=10,
                break_overrides=[schemas.BreakOverridePayload(after_slot=2, duration_minutes=5)],
                lunch_window_start=time(11, 0),
                lunch_window_end=time(11, 40),
                lunch_min_duration_minutes=30,
            ),
        ),
        membership.id,
    )
    await service.complete_foundation(
        organization.id,
        schemas.FoundationCompleteCommand(expected_version=1, confirmed=True),
        membership.id,
    )

    resolved = await grid_version_service.resolve_grid(
        db_session, organization.id, date(2025, 9, 15)
    )
    assert [
        (block.start_time.strftime("%H:%M"), block.end_time.strftime("%H:%M"))
        for block in resolved.blocks
    ] == [("09:00", "09:50"), ("10:00", "10:50"), ("10:55", "11:45")]
    assert resolved.version is not None
    assert resolved.version.configuration_json is not None
    assert resolved.version.configuration_json["break_overrides"] == [
        {"after_slot": 2, "duration_minutes": 5}
    ]


async def test_configuration_only_change_is_persisted_without_touching_blocks(db_session):
    organization = await _create_org(db_session)
    first = await settings_service.save_and_regenerate_grid(
        db_session,
        organization.id,
        schemas.GridConfigurationCommand(
            grid_settings=schemas.OrganizationGridSettingsUpsert(),
            timeslots=_bulk(end_time="10:50", break_overrides=[]),
        ),
    )
    assert first.changed is True
    assert first.grid_regenerated is True
    before = await grid_version_service.resolve_grid(db_session, organization.id, date(2025, 9, 15))
    before_ids = sorted(block.id for block in before.blocks)
    assert len(before_ids) == 4

    second = await settings_service.save_and_regenerate_grid(
        db_session,
        organization.id,
        schemas.GridConfigurationCommand(
            grid_settings=schemas.OrganizationGridSettingsUpsert(),
            timeslots=_bulk(end_time="11:00", break_overrides=[]),
        ),
    )
    assert second.changed is True
    assert second.grid_regenerated is False

    version = await grid_version_service.get_active_grid_version(db_session, organization.id)
    assert version is not None
    assert version.configuration_json is not None
    assert version.configuration_json["closing_time"] == "11:00"

    after = await grid_version_service.resolve_grid(db_session, organization.id, date(2025, 9, 15))
    assert sorted(block.id for block in after.blocks) == before_ids


async def test_active_grid_configuration_prefers_the_stored_version(db_session):
    organization = await _create_org(db_session)
    await _regenerate(db_session, organization, _bulk())

    payload = await grid_version_service.active_grid_configuration(db_session, organization.id)
    assert payload["source"] == "VERSION"
    assert payload["configuration"]["closing_time"] == "11:45"
    assert payload["version_id"] is not None


async def test_active_grid_configuration_rebuilds_legacy_blocks(db_session):
    organization = await _create_org(db_session)
    db_session.add_all(
        [
            models.Timeslot(
                organization_id=organization.id,
                day_of_week=0,
                start_time=time(9, 0),
                end_time=time(9, 50),
            ),
            models.Timeslot(
                organization_id=organization.id,
                day_of_week=0,
                start_time=time(10, 0),
                end_time=time(10, 50),
            ),
        ]
    )
    await db_session.flush()

    payload = await grid_version_service.active_grid_configuration(db_session, organization.id)
    assert payload["source"] == "BLOCKS"
    assert payload["configuration"]["closing_time"] == "10:50"
    assert payload["configuration"]["break_duration_minutes"] == 10
