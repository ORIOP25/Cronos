from datetime import time

import pytest
from sqlalchemy import select

from app import models, schemas
from app.services import settings_service, timeslot_service
from tests.test_school_year_reset_service import _seed_reset_regression_graph


pytestmark = pytest.mark.integration


def _payload(**timeslot_changes):
    return {
        "grid_settings": {
            "lunch_window_start": "08:00:00",
            "lunch_window_end": "08:30:00",
            "lunch_min_duration_minutes": 30,
        },
        "timeslots": {
            "start_time": "08:00:00",
            "end_time": "10:00:00",
            "slot_duration_minutes": 50,
            "break_duration_minutes": 10,
            "days_of_week": [0],
            **timeslot_changes,
        },
    }


async def _admin(db_session):
    return await db_session.scalar(
        select(models.User).where(models.User.clerk_user_id == "user_admin_001")
    )


@pytest.mark.asyncio
async def test_clean_tenant_commits_settings_grid_and_preserves_availability(
    async_client,
    db_session,
    admin_token_headers,
):
    admin = await _admin(db_session)
    teacher = models.Teacher(organization_id=admin.organization_id, name="Grid Teacher")
    old_slot = models.Timeslot(
        organization_id=admin.organization_id,
        day_of_week=0,
        start_time=time(8),
        end_time=time(8, 50),
    )
    db_session.add_all([teacher, old_slot])
    await db_session.flush()
    db_session.add(models.Availability(
        organization_id=admin.organization_id,
        teacher_id=teacher.id,
        timeslot_id=old_slot.id,
        score=models.PreferenceLevel.PREFERRED.value,
    ))
    await db_session.commit()

    response = await async_client.post(
        "/api/v1/school/grid-settings/regenerate",
        json=_payload(),
        headers=admin_token_headers,
    )

    assert response.status_code == 200
    assert response.json() == {
        "message": "Grelha configurada e regenerada com sucesso.",
        "generated_count": 2,
        "changed": True,
        "grid_regenerated": True,
    }
    rows = (
        await db_session.execute(
            select(models.Timeslot, models.Availability.score)
            .join(models.Availability)
            .where(models.Timeslot.organization_id == admin.organization_id)
            .order_by(models.Timeslot.start_time)
        )
    ).all()
    assert [(slot.start_time, score) for slot, score in rows] == [
        (time(8), models.PreferenceLevel.PREFERRED.value),
        (time(9), models.PreferenceLevel.NEUTRAL.value),
    ]


@pytest.mark.asyncio
async def test_noop_keeps_timeslot_ids_and_lunch_only_does_not_regenerate(
    async_client,
    db_session,
    admin_token_headers,
):
    admin = await _admin(db_session)
    slot = models.Timeslot(
        organization_id=admin.organization_id,
        day_of_week=0,
        start_time=time(8),
        end_time=time(8, 50),
    )
    settings = models.OrganizationGridSettings(
        organization_id=admin.organization_id,
        lunch_window_start=time(8),
        lunch_window_end=time(8, 30),
        lunch_min_duration_minutes=30,
    )
    db_session.add_all([slot, settings])
    await db_session.commit()
    slot_id = slot.id
    same_grid = _payload(end_time="08:50:00")

    noop = await async_client.post(
        "/api/v1/school/grid-settings/regenerate",
        json=same_grid,
        headers=admin_token_headers,
    )
    assert noop.status_code == 200
    assert noop.json()["changed"] is False
    assert noop.json()["grid_regenerated"] is False

    same_grid["grid_settings"]["lunch_min_duration_minutes"] = 20
    lunch_only = await async_client.post(
        "/api/v1/school/grid-settings/regenerate",
        json=same_grid,
        headers=admin_token_headers,
    )
    assert lunch_only.status_code == 200
    assert lunch_only.json()["changed"] is True
    assert lunch_only.json()["grid_regenerated"] is False
    assert await db_session.scalar(select(models.Timeslot.id)) == slot_id


@pytest.mark.asyncio
async def test_failure_after_preparing_settings_rolls_back_everything(
    db_session,
    admin_token_headers,
    monkeypatch,
):
    del admin_token_headers
    admin = await _admin(db_session)
    slot = models.Timeslot(
        organization_id=admin.organization_id,
        day_of_week=0,
        start_time=time(8),
        end_time=time(8, 50),
    )
    settings = models.OrganizationGridSettings(
        organization_id=admin.organization_id,
        lunch_window_start=time(11),
        lunch_window_end=time(13),
        lunch_min_duration_minutes=45,
    )
    db_session.add_all([slot, settings])
    await db_session.commit()
    slot_id = slot.id
    settings_id = settings.id

    async def fail_after_settings(*_args, **_kwargs):
        raise RuntimeError("injected failure")

    monkeypatch.setattr(timeslot_service, "apply_grid_regeneration", fail_after_settings)
    with pytest.raises(RuntimeError, match="injected failure"):
        await settings_service.save_and_regenerate_grid(
            db_session,
            admin.organization_id,
            schemas.GridConfigurationCommand.model_validate(_payload()),
            admin.id,
        )

    db_session.expire_all()
    persisted_settings = await db_session.get(models.OrganizationGridSettings, settings_id)
    assert (
        persisted_settings.lunch_window_start,
        persisted_settings.lunch_window_end,
        persisted_settings.lunch_min_duration_minutes,
    ) == (time(11), time(13), 45)
    assert await db_session.scalar(select(models.Timeslot.id)) == slot_id


@pytest.mark.asyncio
async def test_json_slot_rule_blocks_structural_change(
    async_client,
    db_session,
    admin_token_headers,
):
    admin = await _admin(db_session)
    slot = models.Timeslot(
        organization_id=admin.organization_id,
        day_of_week=0,
        start_time=time(8),
        end_time=time(8, 50),
    )
    db_session.add(slot)
    await db_session.flush()
    db_session.add(models.Constraint(
        organization_id=admin.organization_id,
        rule_type=models.ConstraintType.lock_time,
        rule_payload={"timeslot_id": slot.id},
    ))
    await db_session.commit()

    response = await async_client.post(
        "/api/v1/school/grid-settings/regenerate",
        json=_payload(),
        headers=admin_token_headers,
    )

    assert response.status_code == 409
    assert "regras associadas" in response.json()["detail"]


@pytest.mark.asyncio
async def test_active_schedule_block_returns_409_without_partial_changes(
    async_client,
    db_session,
    admin_token_headers,
):
    admin = await db_session.scalar(
        select(models.User).where(models.User.clerk_user_id == "user_admin_001")
    )
    organization_id = admin.organization_id
    await _seed_reset_regression_graph(db_session, organization_id, admin.id)
    settings = models.OrganizationGridSettings(
        organization_id=organization_id,
        lunch_window_start=time(11),
        lunch_window_end=time(13),
        lunch_min_duration_minutes=45,
    )
    db_session.add(settings)
    await db_session.commit()

    slots_before = [
        (slot.id, slot.day_of_week, slot.start_time, slot.end_time)
        for slot in await timeslot_service.get_timeslots_by_org(db_session, organization_id)
    ]
    response = await async_client.post(
        "/api/v1/school/grid-settings/regenerate",
        json=_payload(),
        headers=admin_token_headers,
    )

    assert response.status_code == 409
    assert "Recomeçar Ano Letivo" in response.json()["detail"]
    db_session.expire_all()
    persisted_settings = await db_session.scalar(
        select(models.OrganizationGridSettings).where(
            models.OrganizationGridSettings.organization_id == organization_id
        )
    )
    slots_after = [
        (slot.id, slot.day_of_week, slot.start_time, slot.end_time)
        for slot in await timeslot_service.get_timeslots_by_org(db_session, organization_id)
    ]
    assert (
        persisted_settings.lunch_window_start,
        persisted_settings.lunch_window_end,
        persisted_settings.lunch_min_duration_minutes,
    ) == (time(11), time(13), 45)
    assert slots_after == slots_before
    assert await db_session.scalar(select(models.ActiveScheduleBlock.id)) is not None

    legacy_response = await async_client.post(
        "/api/v1/timeslots/generate",
        json=_payload()["timeslots"],
        headers=admin_token_headers,
    )
    assert legacy_response.status_code == 409

    published_noop = await async_client.post(
        "/api/v1/school/grid-settings/regenerate",
        json={
            "grid_settings": {
                "lunch_window_start": "09:00:00",
                "lunch_window_end": "10:00:00",
                "lunch_min_duration_minutes": 30,
            },
            "timeslots": {
                "start_time": "09:00:00",
                "end_time": "10:00:00",
                "slot_duration_minutes": 60,
                "break_duration_minutes": 0,
                "days_of_week": [1],
            },
        },
        headers=admin_token_headers,
    )
    assert published_noop.status_code == 200
    assert published_noop.json()["grid_regenerated"] is False
    assert [
        slot.id
        for slot in await timeslot_service.get_timeslots_by_org(db_session, organization_id)
    ] == [slot[0] for slot in slots_before]


@pytest.mark.asyncio
async def test_teacher_cannot_regenerate_grid(async_client, clerk_teacher_headers):
    response = await async_client.post(
        "/api/v1/school/grid-settings/regenerate",
        json=_payload(),
        headers=clerk_teacher_headers,
    )

    assert response.status_code == 403


@pytest.mark.unit
def test_timeslot_foreign_keys_have_an_explicit_regeneration_policy():
    expected = {
        ("availability", "timeslot_id"): "recreate",
        ("schedule_draft_blocks", "timeslot_id"): "protect",
        ("active_schedule_blocks", "timeslot_id"): "protect",
        ("operational_schedule_block", "timeslot_id"): "protect",
        ("schedule_output", "timeslot_id"): "protect",
        ("substitutions", "timeslot_id"): "protect",
        ("lesson_occurrence", "planned_timeslot_id"): "protect",
        ("schedule_diff_entries", "before_timeslot_id"): "protect",
        ("schedule_diff_entries", "after_timeslot_id"): "protect",
    }
    actual = {
        (foreign_key.parent.table.name, foreign_key.parent.name)
        for table in models.Base.metadata.tables.values()
        for foreign_key in table.foreign_keys
        if foreign_key.column.table is models.Timeslot.__table__
    }

    assert actual == set(expected)
    assert timeslot_service.TIMESLOT_DEPENDENCY_POLICIES == expected


@pytest.mark.unit
def test_timeslot_signature_generation_is_deterministic():
    signatures = timeslot_service.build_timeslot_signatures(
        schemas.TimeslotBulkCreate(
            start_time="08:00",
            end_time="10:00",
            slot_duration_minutes=50,
            break_duration_minutes=10,
            days_of_week=[1, 0],
        )
    )

    assert signatures == [
        (0, time(8), time(8, 50)),
        (0, time(9), time(9, 50)),
        (1, time(8), time(8, 50)),
        (1, time(9), time(9, 50)),
    ]
