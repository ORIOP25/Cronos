from datetime import date, time

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app import models, schemas
from app.config import settings
from app.core.exceptions import AppError
from app.services import grid_version_service, teacher_service

API = settings.API_V1_STR


async def _seed_versions(db_session, organization_id: int):
    older = models.GridVersion(
        organization_id=organization_id,
        effective_date=date(2000, 1, 1),
        state=models.GridVersionState.ACTIVE,
    )
    newer = models.GridVersion(
        organization_id=organization_id,
        effective_date=date(2030, 1, 1),
        state=models.GridVersionState.ACTIVE,
    )
    pending = models.GridVersion(
        organization_id=organization_id,
        effective_date=date(2040, 1, 1),
        state=models.GridVersionState.PENDING,
    )
    db_session.add_all([older, newer, pending])
    await db_session.flush()
    for version, start in ((older, time(9, 0)), (newer, time(10, 0)), (pending, time(11, 0))):
        db_session.add(
            models.Timeslot(
                organization_id=organization_id,
                grid_version_id=version.id,
                day_of_week=0,
                start_time=start,
                end_time=time(start.hour, start.minute + 50),
            )
        )
    await db_session.flush()
    return older, newer, pending


class TestTimeslotVersionReads:
    async def test_timeslots_endpoint_uses_the_requested_school_date(
        self, async_client: AsyncClient, clerk_admin_headers: dict, db_session
    ):
        organization_id = await db_session.scalar(
            select(models.Organization.id).where(models.Organization.clerk_org_id == "org_test_001")
        )
        older, newer, _pending = await _seed_versions(db_session, organization_id)
        await db_session.commit()

        default = await async_client.get(f"{API}/timeslots/", headers=clerk_admin_headers)
        assert default.status_code == 200
        assert [row["start_time"][:5] for row in default.json()] == ["09:00"]

        future = await async_client.get(
            f"{API}/timeslots/",
            params={"on_date": "2031-01-01"},
            headers=clerk_admin_headers,
        )
        assert future.status_code == 200
        assert [row["start_time"][:5] for row in future.json()] == ["10:00"]

        far_future = await async_client.get(
            f"{API}/timeslots/",
            params={"on_date": "2050-01-01"},
            headers=clerk_admin_headers,
        )
        assert [row["start_time"][:5] for row in far_future.json()] == ["10:00"]
        assert older.id != newer.id


async def test_teacher_availability_follows_the_visible_version(db_session):
    organization = models.Organization(name="Reader School", plan_status="active")
    db_session.add(organization)
    await db_session.flush()
    older, newer, _pending = await _seed_versions(db_session, organization.id)
    teacher = models.Teacher(
        organization_id=organization.id,
        organization_membership_id=None,
    )
    account = models.User(name="Reader Teacher", email="reader-teacher@test.invalid")
    db_session.add(account)
    await db_session.flush()
    membership = models.OrganizationMembership(
        organization_id=organization.id,
        account_id=account.id,
        organization_display_name="Reader Teacher",
        lifecycle_status=models.MembershipLifecycleStatus.active,
        access_status=models.MembershipAccessStatus.none,
        can_admin=False,
        can_teach=True,
        teacher_access_mode=models.TeacherAccessMode.scheduler_only,
    )
    db_session.add(membership)
    await db_session.flush()
    teacher.organization_membership_id = membership.id
    db_session.add(teacher)
    await db_session.flush()

    visible = await grid_version_service.resolve_grid(
        db_session,
        organization.id,
        await grid_version_service.school_today(db_session, organization.id),
    )
    visible_ids = [block.id for block in visible.blocks]
    assert visible.version.id == older.id

    await teacher_service.set_teacher_availability(
        db_session,
        teacher.id,
        [
            schemas.AvailabilitySelfCreate(
                timeslot_id=block_id, score=models.PreferenceLevel.NEUTRAL
            )
            for block_id in visible_ids
        ],
        organization.id,
    )
    read_back = await teacher_service.get_teacher_availability(
        db_session, teacher.id, organization.id
    )
    assert [row["timeslot_id"] for row in read_back] == visible_ids

    newer_blocks = await grid_version_service.get_version_blocks(
        db_session, organization.id, newer.id
    )
    with pytest.raises(AppError):
        await teacher_service.set_teacher_availability(
            db_session,
            teacher.id,
            [
                schemas.AvailabilitySelfCreate(
                    timeslot_id=block.id, score=models.PreferenceLevel.NEUTRAL
                )
                for block in newer_blocks
            ],
            organization.id,
        )


async def _seed_midweek_versions(db_session, organization_id: int):
    older = models.GridVersion(
        organization_id=organization_id,
        effective_date=date(2000, 1, 1),
        state=models.GridVersionState.ACTIVE,
    )
    newer = models.GridVersion(
        organization_id=organization_id,
        effective_date=date(2026, 9, 23),
        state=models.GridVersionState.ACTIVE,
    )
    pending = models.GridVersion(
        organization_id=organization_id,
        effective_date=date(2040, 1, 1),
        state=models.GridVersionState.PENDING,
    )
    db_session.add_all([older, newer, pending])
    await db_session.flush()
    for version, start in ((older, time(9, 0)), (newer, time(10, 0))):
        for day in (0, 2):
            db_session.add(
                models.Timeslot(
                    organization_id=organization_id,
                    grid_version_id=version.id,
                    day_of_week=day,
                    start_time=start,
                    end_time=time(start.hour, start.minute + 50),
                )
            )
    db_session.add(
        models.Timeslot(
            organization_id=organization_id,
            grid_version_id=pending.id,
            day_of_week=0,
            start_time=time(11, 0),
            end_time=time(11, 50),
        )
    )
    await db_session.flush()
    return older, newer, pending


async def test_week_range_resolves_each_date_and_reports_the_transition(db_session):
    organization = models.Organization(name="Week Range School", plan_status="active")
    db_session.add(organization)
    await db_session.flush()
    older, newer, pending = await _seed_midweek_versions(db_session, organization.id)

    payload = await grid_version_service.week_grid_versions(
        db_session, organization.id, date(2026, 9, 21), date(2026, 9, 27)
    )

    days = payload["days"]
    assert len(days) == 7
    assert days[0]["version_id"] == older.id
    assert [row["start_time"] for row in days[0]["blocks"]] == [time(9, 0)]
    assert days[2]["version_id"] == newer.id
    assert [row["start_time"] for row in days[2]["blocks"]] == [time(10, 0)]
    assert days[3]["version_id"] == newer.id
    assert payload["transition_date"] == date(2026, 9, 23)
    assert all(day["version_id"] != pending.id for day in days)


async def test_week_range_without_transition_inside_the_week(db_session):
    organization = models.Organization(name="Week Stable School", plan_status="active")
    db_session.add(organization)
    await db_session.flush()
    older, newer, _pending = await _seed_midweek_versions(db_session, organization.id)

    payload = await grid_version_service.week_grid_versions(
        db_session, organization.id, date(2026, 10, 5), date(2026, 10, 11)
    )
    assert payload["transition_date"] is None
    assert {day["version_id"] for day in payload["days"]} == {newer.id}


class TestWeekGridRangeEndpoint:
    async def test_range_endpoint_returns_per_date_blocks(
        self, async_client: AsyncClient, clerk_admin_headers: dict, db_session
    ):
        organization_id = await db_session.scalar(
            select(models.Organization.id).where(models.Organization.clerk_org_id == "org_test_001")
        )
        older, newer, _pending = await _seed_midweek_versions(db_session, organization_id)
        await db_session.commit()

        response = await async_client.get(
            f"{API}/timeslots/range",
            params={"from_date": "2026-09-21", "to_date": "2026-09-27"},
            headers=clerk_admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["transition_date"] == "2026-09-23"
        assert data["days"][0]["version_id"] == older.id
        assert data["days"][2]["version_id"] == newer.id
        assert data["days"][2]["blocks"][0]["start_time"].startswith("10:00")

    async def test_range_endpoint_rejects_invalid_ranges(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        response = await async_client.get(
            f"{API}/timeslots/range",
            params={"from_date": "2026-09-27", "to_date": "2026-09-21"},
            headers=clerk_admin_headers,
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "grid_range_invalid"
