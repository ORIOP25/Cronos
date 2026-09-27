from datetime import date, time

from httpx import AsyncClient
from sqlalchemy import select

from app import models, schemas
from app.config import settings
from app.services import grid_change_service, grid_version_service
from tests._support.db_fixtures import create_teacher_profile
from tests._support.scheduler_v1 import (
    add_lesson,
    add_version,
    lesson_interval,
    seed_generatable_school,
)

API = settings.API_V1_STR


async def _regenerate(client: AsyncClient, headers: dict, timeslots: dict):
    return await client.post(
        f"{API}/school/grid-settings/regenerate",
        json={"grid_settings": {}, "timeslots": timeslots},
        headers=headers,
    )


def _proposal(**changes) -> dict:
    payload = {
        "start_time": "09:00",
        "end_time": "12:00",
        "slot_duration_minutes": 50,
        "break_duration_minutes": 10,
        "break_overrides": [],
        "days_of_week": [0],
    }
    payload.update(changes)
    return payload


class TestGridChangePreviewEndpoint:
    async def test_grid_configuration_endpoint_returns_the_stored_version(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        response = await _regenerate(
            async_client,
            clerk_admin_headers,
            _proposal(end_time="10:50"),
        )
        assert response.status_code == 200

        config = await async_client.get(
            f"{API}/school/grid-configuration/", headers=clerk_admin_headers
        )
        assert config.status_code == 200
        data = config.json()
        assert data["source"] == "VERSION"
        assert data["configuration"]["closing_time"] == "10:50"
        assert data["configuration"]["break_duration_minutes"] == 10
        assert data["version_id"] is not None

    async def test_preview_reports_the_impact_without_writing(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        base = await _regenerate(
            async_client,
            clerk_admin_headers,
            _proposal(end_time="10:50"),
        )
        assert base.status_code == 200

        response = await async_client.post(
            f"{API}/school/grid-changes/preview",
            json={"timeslots": _proposal()},
            headers=clerk_admin_headers,
        )
        assert response.status_code == 200
        data = response.json()

        assert data["first_editable_date"]
        assert data["proposed_configuration"]["opening_time"] == "09:00"
        assert data["proposed_configuration"]["break_duration_minutes"] == 10
        monday = next(day for day in data["daily"] if day["day_of_week"] == 0)
        assert monday["current_lessons"] == 2
        assert monday["proposed_lessons"] == 3
        assert monday["delta"] == 1
        assert data["can_propose"] is True
        assert data["blockers"] == []
        assert len(data["fingerprint"]) == 64

        after = await async_client.get(f"{API}/timeslots/", headers=clerk_admin_headers)
        assert len(after.json()) == 2

    async def test_preview_blocks_when_a_pending_grid_version_exists(
        self, async_client: AsyncClient, clerk_admin_headers: dict, db_session
    ):
        base = await _regenerate(
            async_client,
            clerk_admin_headers,
            _proposal(end_time="10:50"),
        )
        assert base.status_code == 200

        slot_rows = (
            await async_client.get(f"{API}/timeslots/", headers=clerk_admin_headers)
        ).json()
        organization_id = slot_rows[0]["organization_id"]
        pending = models.GridVersion(
            organization_id=organization_id,
            effective_date=date(2026, 1, 5),
            state=models.GridVersionState.PENDING,
        )
        db_session.add(pending)
        await db_session.commit()

        response = await async_client.post(
            f"{API}/school/grid-changes/preview",
            json={"timeslots": _proposal()},
            headers=clerk_admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["can_propose"] is False
        assert data["pending_grid_version_id"] == pending.id
        assert any("proposta de grelha pendente" in blocker for blocker in data["blockers"])


async def test_analysis_reports_moved_availability_and_pending_lessons(db_session):
    seed = await seed_generatable_school(
        db_session,
        clerk_user_id="preview-admin",
        clerk_org_id="preview-org",
    )
    organization = seed.organization
    version = await grid_version_service.ensure_active_grid_version(
        db_session, organization.id, effective_date=date(2026, 1, 1)
    )
    slot = models.Timeslot(
        organization_id=organization.id,
        grid_version_id=version.id,
        day_of_week=0,
        start_time=time(9, 0),
        end_time=time(9, 50),
    )
    db_session.add(slot)
    await db_session.flush()
    teacher = await create_teacher_profile(
        db_session, organization_id=organization.id, name="Preview Teacher"
    )
    db_session.add(
        models.Availability(
            organization_id=organization.id,
            teacher_id=teacher.id,
            timeslot_id=slot.id,
            score=models.PreferenceLevel.IMPOSSIBLE.value,
        )
    )
    active_schedule = await add_version(db_session, seed, status="ACTIVE")
    past = date(2020, 1, 1)
    future = date(2030, 1, 1)
    start, end = lesson_interval(past, 9)
    await add_lesson(
        db_session,
        seed,
        active_schedule,
        stable_key="1",
        school_date=past,
        start=start,
        end=end,
    )
    start, end = lesson_interval(future, 9)
    await add_lesson(
        db_session,
        seed,
        active_schedule,
        stable_key="2",
        school_date=future,
        start=start,
        end=end,
    )
    await db_session.flush()

    proposal = schemas.TimeslotBulkCreate(
        **_proposal(slot_duration_minutes=55, break_duration_minutes=5)
    )
    analysis = await grid_change_service.analyze_grid_change(db_session, organization.id, proposal)

    assert analysis.can_propose is False
    assert [row["date"] for row in analysis.lessons_without_closure] == [past]
    moved = [
        entry
        for entry in analysis.affected_availabilities
        if entry["current_timeslot_id"] == slot.id
    ]
    assert moved
    assert moved[0]["requires_decision"] is True
    assert moved[0]["match"] == "MOVED"
    assert moved[0]["ambiguous"] is False
    assert moved[0]["proposed"]["start_time"] == time(9, 0)
    assert moved[0]["proposed"]["end_time"] == time(9, 55)
    assert moved[0]["teachers"][0]["score"] == models.PreferenceLevel.IMPOSSIBLE.value

    exact = await grid_change_service.analyze_grid_change(
        db_session,
        organization.id,
        schemas.TimeslotBulkCreate(**_proposal(end_time="09:50")),
    )
    exact_entry = next(
        entry for entry in exact.affected_availabilities if entry["current_timeslot_id"] == slot.id
    )
    assert exact_entry["match"] == "EXACT"
    assert exact_entry["requires_decision"] is False
    assert exact_entry["proposed"]["end_time"] == time(9, 50)

    repeated = await grid_change_service.analyze_grid_change(
        db_session,
        organization.id,
        schemas.TimeslotBulkCreate(**_proposal(slot_duration_minutes=55, break_duration_minutes=5)),
    )
    assert repeated.fingerprint == analysis.fingerprint

    availability_id = await db_session.scalar(
        select(models.Availability.id).where(
            models.Availability.teacher_id == teacher.id,
            models.Availability.timeslot_id == slot.id,
        )
    )
    changed_availability = await db_session.get(models.Availability, availability_id)
    changed_availability.score = models.PreferenceLevel.NEUTRAL.value
    await db_session.flush()
    after_score_change = await grid_change_service.analyze_grid_change(
        db_session, organization.id, proposal
    )
    assert after_score_change.fingerprint != analysis.fingerprint
