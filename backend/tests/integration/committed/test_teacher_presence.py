"""S2 teacher presence API, scheduler revision and fingerprint contract.

Scenarios R01, R02, R09, R11, R12, R19, R20 and R25 of the teacher presence
tech spec, plus the 0005 migration round trip and its check constraints (R17).
"""

from datetime import date, time

import pytest
from httpx import AsyncClient
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError

from alembic import command
from app import models
from app.config import settings
from app.services.scheduler_fingerprint_service import SchedulerFingerprintService
from tests._support.db_fixtures import (
    _alembic_config,
    create_teacher_profile,
    create_teacher_user,
    get_school_room_type_id,
    sync_test_engine,
)

API = settings.API_V1_STR
PREVIOUS_REVISION = "0004_joint_lesson_groups"
PRESENCE_COLUMNS = {"lunch_required", "minimum_presence_hours", "maximum_presence_gap_hours"}
DEFAULT_PRESENCE = {"lunch_required": True, "minimum_hours": None, "max_gap_hours": None}


def _presence(lunch_required: bool = True, minimum_hours=None, max_gap_hours=None) -> dict:
    return {
        "lunch_required": lunch_required,
        "minimum_hours": minimum_hours,
        "max_gap_hours": max_gap_hours,
    }


async def _org_id(db_session) -> int:
    return await db_session.scalar(
        select(models.Organization.id).where(models.Organization.clerk_org_id == "org_test_001")
    )


async def _scheduler_year(db_session, organization_id: int) -> models.SchedulerSchoolYear:
    year = models.SchedulerSchoolYear(
        organization_id=organization_id,
        label="2025/2026",
        start_date=date(2025, 9, 1),
        hard_end_date=date(2026, 7, 15),
        timezone="Europe/Lisbon",
    )
    db_session.add_all(
        [
            year,
            models.Timeslot(
                organization_id=organization_id,
                day_of_week=1,
                start_time=time(9, 0),
                end_time=time(10, 0),
            ),
        ]
    )
    await db_session.flush()
    db_session.add(
        models.SchedulerSchoolYearState(
            organization_id=organization_id,
            school_year_id=year.id,
        )
    )
    await db_session.flush()
    return year


async def _assign_teacher(db_session, organization_id: int, teacher: models.Teacher) -> None:
    course = models.Course(
        organization_id=organization_id, name="Presence Course", abbreviation="PRC"
    )
    subject = models.Subject(
        organization_id=organization_id,
        name="Presence Subject",
        room_type_id=await get_school_room_type_id(db_session, organization_id, "Normal"),
    )
    db_session.add_all([course, subject])
    await db_session.flush()
    class_ = models.Class(
        organization_id=organization_id,
        name="Presence Class",
        size=20,
        start_year=2025,
        end_year=2026,
        grade_level=10,
        course_id=course.id,
    )
    db_session.add(class_)
    await db_session.flush()
    db_session.add(
        models.ClassSubjectLink(
            organization_id=organization_id,
            class_id=class_.id,
            subject_id=subject.id,
            grade_level=class_.grade_level,
            teacher_id=teacher.id,
        )
    )
    await db_session.flush()


async def _fingerprint(db_session, organization_id: int, school_year_id: int):
    return await SchedulerFingerprintService(db_session).generation_input_fingerprint(
        organization_id,
        school_year_id,
        models.ScheduleGenerationStrategy.COMPLETE_GENERATION,
    )


async def _input_revision(db_session, organization_id: int, school_year_id: int) -> int:
    return await db_session.scalar(
        select(models.SchedulerSchoolYearState.input_revision).where(
            models.SchedulerSchoolYearState.organization_id == organization_id,
            models.SchedulerSchoolYearState.school_year_id == school_year_id,
        )
    )


# --- R01: identifiers ---------------------------------------------------------


async def test_r01_put_uses_the_teacher_id_and_not_the_membership_id(
    async_client: AsyncClient, clerk_admin_headers: dict, db_session
):
    organization_id = await _org_id(db_session)
    teacher = await create_teacher_profile(db_session, organization_id=organization_id, name="R01")
    membership_id = teacher.organization_membership_id
    await db_session.commit()
    assert membership_id != teacher.id

    response = await async_client.put(
        f"{API}/teachers/{membership_id}/presence",
        json=_presence(lunch_required=False, minimum_hours=3, max_gap_hours=1),
        headers=clerk_admin_headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "resource_not_found"
    current = await async_client.get(
        f"{API}/teachers/{teacher.id}/presence", headers=clerk_admin_headers
    )
    assert current.json() == DEFAULT_PRESENCE


# --- R02: tenant isolation ----------------------------------------------------


async def test_r02_presence_rejects_a_teacher_from_another_organization(
    async_client: AsyncClient, clerk_admin_headers: dict, db_session
):
    other_org = models.Organization(name="Other Presence School", plan_status="active")
    db_session.add(other_org)
    await db_session.flush()
    foreign_teacher = await create_teacher_profile(
        db_session, organization_id=other_org.id, name="Foreign"
    )
    await db_session.commit()

    response = await async_client.put(
        f"{API}/teachers/{foreign_teacher.id}/presence",
        json=_presence(minimum_hours=3, max_gap_hours=1),
        headers=clerk_admin_headers,
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "resource_not_found"


# --- R09: scheduler revision and fingerprint ---------------------------------


async def test_r09_presence_change_bumps_revision_and_fingerprint(
    async_client: AsyncClient, clerk_admin_headers: dict, db_session
):
    organization_id = await _org_id(db_session)
    teacher = await create_teacher_profile(db_session, organization_id=organization_id, name="R09")
    year = await _scheduler_year(db_session, organization_id)
    await _assign_teacher(db_session, organization_id, teacher)
    await db_session.commit()

    before = await _fingerprint(db_session, organization_id, year.id)
    assert before.snapshot["teachers"] == [{"id": teacher.id}]
    assert await _input_revision(db_session, organization_id, year.id) == 0

    response = await async_client.put(
        f"{API}/teachers/{teacher.id}/presence",
        json=_presence(lunch_required=False, minimum_hours=3, max_gap_hours=1),
        headers=clerk_admin_headers,
    )
    assert response.status_code == 200

    after = await _fingerprint(db_session, organization_id, year.id)
    assert after.value != before.value
    assert after.snapshot["teachers"] == [
        {
            "id": teacher.id,
            "lunch_required": False,
            "minimum_presence_hours": 3,
            "maximum_presence_gap_hours": 1,
        }
    ]
    assert await _input_revision(db_session, organization_id, year.id) == 1
    scope = await db_session.scalar(
        select(models.SchedulerStateVersionEvent.change_scope).where(
            models.SchedulerStateVersionEvent.organization_id == organization_id,
            models.SchedulerStateVersionEvent.entity_type == "TEACHER_PRESENCE",
        )
    )
    assert scope == models.SchedulerStateChangeScope.FUTURE_IMPACTING


# --- R11: reverting the rule --------------------------------------------------


async def test_r11_clearing_the_minimum_clears_the_gap(
    async_client: AsyncClient, clerk_admin_headers: dict, db_session
):
    organization_id = await _org_id(db_session)
    teacher = await create_teacher_profile(db_session, organization_id=organization_id, name="R11")
    await db_session.commit()

    set_gap = await async_client.put(
        f"{API}/teachers/{teacher.id}/presence",
        json=_presence(minimum_hours=3, max_gap_hours=1),
        headers=clerk_admin_headers,
    )
    assert set_gap.status_code == 200

    cleared = await async_client.put(
        f"{API}/teachers/{teacher.id}/presence",
        json=_presence(),
        headers=clerk_admin_headers,
    )
    assert cleared.status_code == 200
    assert cleared.json() == DEFAULT_PRESENCE

    again = await async_client.put(
        f"{API}/teachers/{teacher.id}/presence",
        json=_presence(minimum_hours=3, max_gap_hours=1),
        headers=clerk_admin_headers,
    )
    assert again.status_code == 200
    assert again.json() == {"lunch_required": True, "minimum_hours": 3, "max_gap_hours": 1}


# --- R12: limits and paired values -------------------------------------------


async def test_r12_rejects_out_of_range_and_unpaired_values(
    async_client: AsyncClient, clerk_admin_headers: dict, db_session
):
    organization_id = await _org_id(db_session)
    teacher = await create_teacher_profile(db_session, organization_id=organization_id, name="R12")
    await db_session.commit()
    url = f"{API}/teachers/{teacher.id}/presence"

    minimum_out = await async_client.put(
        url, json=_presence(minimum_hours=13, max_gap_hours=1), headers=clerk_admin_headers
    )
    assert minimum_out.status_code == 422
    assert minimum_out.json()["detail"]["code"] == "validation_error"

    gap_out = await async_client.put(
        url, json=_presence(minimum_hours=3, max_gap_hours=13), headers=clerk_admin_headers
    )
    assert gap_out.status_code == 422
    assert gap_out.json()["detail"]["code"] == "validation_error"

    minimum_only = await async_client.put(
        url, json=_presence(minimum_hours=3, max_gap_hours=None), headers=clerk_admin_headers
    )
    assert minimum_only.status_code == 422

    gap_only = await async_client.put(
        url, json=_presence(minimum_hours=None, max_gap_hours=1), headers=clerk_admin_headers
    )
    assert gap_only.status_code == 422

    boundary = await async_client.put(
        url, json=_presence(minimum_hours=12, max_gap_hours=0), headers=clerk_admin_headers
    )
    assert boundary.status_code == 200
    assert boundary.json() == {"lunch_required": True, "minimum_hours": 12, "max_gap_hours": 0}


# --- R19: presence is independent of the availability grid -------------------


async def test_r19_availability_write_does_not_change_presence(
    async_client: AsyncClient, clerk_admin_headers: dict, db_session
):
    organization_id = await _org_id(db_session)
    teacher = await create_teacher_profile(db_session, organization_id=organization_id, name="R19")
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
    db_session.add_all([older, newer])
    await db_session.flush()
    db_session.add(
        models.Timeslot(
            organization_id=organization_id,
            grid_version_id=newer.id,
            day_of_week=0,
            start_time=time(10, 0),
            end_time=time(10, 50),
        )
    )
    await db_session.flush()
    newer_slot_id = await db_session.scalar(
        select(models.Timeslot.id).where(models.Timeslot.grid_version_id == newer.id)
    )
    await db_session.commit()

    saved = await async_client.put(
        f"{API}/teachers/{teacher.id}/presence",
        json=_presence(minimum_hours=3, max_gap_hours=1),
        headers=clerk_admin_headers,
    )
    assert saved.status_code == 200

    availability = await async_client.put(
        f"{API}/teachers/{teacher.id}/availability",
        params={"on_date": "2031-01-01"},
        json=[{"timeslot_id": newer_slot_id, "score": 2}],
        headers=clerk_admin_headers,
    )
    assert availability.status_code == 200

    current = await async_client.get(
        f"{API}/teachers/{teacher.id}/presence", headers=clerk_admin_headers
    )
    assert current.json() == {"lunch_required": True, "minimum_hours": 3, "max_gap_hours": 1}


# --- R20: teacher self view and admin-only write -----------------------------


async def test_r20_teacher_reads_me_presence_and_only_admins_write(
    async_client: AsyncClient, clerk_admin_headers: dict, db_session
):
    organization_id = await _org_id(db_session)
    teacher = await create_teacher_profile(db_session, organization_id=organization_id, name="R20")
    other = await create_teacher_profile(
        db_session, organization_id=organization_id, name="R20 Other"
    )
    await create_teacher_user(
        db_session,
        clerk_user_id="user_teacher_presence",
        org_id=organization_id,
        teacher_id=teacher.id,
    )
    await db_session.commit()
    teacher_headers = {"Authorization": "Bearer test_user_teacher_presence"}

    saved = await async_client.put(
        f"{API}/teachers/{teacher.id}/presence",
        json=_presence(minimum_hours=4, max_gap_hours=1),
        headers=clerk_admin_headers,
    )
    assert saved.status_code == 200

    self_read = await async_client.get(f"{API}/teachers/me/presence", headers=teacher_headers)
    assert self_read.status_code == 200
    assert self_read.json() == {"lunch_required": True, "minimum_hours": 4, "max_gap_hours": 1}

    admin_read = await async_client.get(
        f"{API}/teachers/{other.id}/presence", headers=clerk_admin_headers
    )
    assert admin_read.status_code == 200

    other_read = await async_client.get(
        f"{API}/teachers/{other.id}/presence", headers=teacher_headers
    )
    assert other_read.status_code == 403

    teacher_write = await async_client.put(
        f"{API}/teachers/{other.id}/presence",
        json=_presence(minimum_hours=3, max_gap_hours=1),
        headers=teacher_headers,
    )
    assert teacher_write.status_code == 403

    admin_without_profile = await async_client.get(
        f"{API}/teachers/me/presence", headers=clerk_admin_headers
    )
    assert admin_without_profile.status_code == 403


# --- R25: an unassigned teacher does not stale the fingerprint ---------------


async def test_r25_unassigned_teacher_rule_keeps_the_fingerprint(
    async_client: AsyncClient, clerk_admin_headers: dict, db_session
):
    organization_id = await _org_id(db_session)
    teacher = await create_teacher_profile(db_session, organization_id=organization_id, name="R25")
    year = await _scheduler_year(db_session, organization_id)
    await db_session.commit()

    before = await _fingerprint(db_session, organization_id, year.id)

    response = await async_client.put(
        f"{API}/teachers/{teacher.id}/presence",
        json=_presence(lunch_required=False, minimum_hours=3, max_gap_hours=1),
        headers=clerk_admin_headers,
    )
    assert response.status_code == 200

    after = await _fingerprint(db_session, organization_id, year.id)
    assert after.value == before.value
    assert after.snapshot["teachers"] == []


# --- Defaults, no-op writes, member read -------------------------------------


async def test_default_presence_and_noop_write_records_no_event(
    async_client: AsyncClient, clerk_admin_headers: dict, db_session
):
    organization_id = await _org_id(db_session)
    teacher = await create_teacher_profile(db_session, organization_id=organization_id, name="Noop")
    year = await _scheduler_year(db_session, organization_id)
    await db_session.commit()
    url = f"{API}/teachers/{teacher.id}/presence"

    read_default = await async_client.get(url, headers=clerk_admin_headers)
    assert read_default.status_code == 200
    assert read_default.json() == DEFAULT_PRESENCE

    unchanged = await async_client.put(url, json=_presence(), headers=clerk_admin_headers)
    assert unchanged.status_code == 200
    assert await _presence_event_count(db_session, organization_id) == 0

    changed = await async_client.put(
        url, json=_presence(minimum_hours=3, max_gap_hours=1), headers=clerk_admin_headers
    )
    assert changed.status_code == 200
    assert await _presence_event_count(db_session, organization_id) == 1
    assert await _input_revision(db_session, organization_id, year.id) == 0

    repeated = await async_client.put(
        url, json=_presence(minimum_hours=3, max_gap_hours=1), headers=clerk_admin_headers
    )
    assert repeated.status_code == 200
    assert await _presence_event_count(db_session, organization_id) == 1


async def _presence_event_count(db_session, organization_id: int) -> int:
    return await db_session.scalar(
        select(func.count())
        .select_from(models.SchedulerStateVersionEvent)
        .where(
            models.SchedulerStateVersionEvent.organization_id == organization_id,
            models.SchedulerStateVersionEvent.entity_type == "TEACHER_PRESENCE",
        )
    )


async def test_member_read_carries_teacher_presence(
    async_client: AsyncClient, clerk_admin_headers: dict, db_session
):
    organization_id = await _org_id(db_session)
    teacher = await create_teacher_profile(
        db_session, organization_id=organization_id, name="Presence Member"
    )
    membership = await db_session.get(
        models.OrganizationMembership, teacher.organization_membership_id
    )
    account = await db_session.get(models.User, membership.account_id)
    account.email = "presence.member@example.com"
    await db_session.commit()

    saved = await async_client.put(
        f"{API}/teachers/{teacher.id}/presence",
        json=_presence(minimum_hours=2, max_gap_hours=1),
        headers=clerk_admin_headers,
    )
    assert saved.status_code == 200

    member = await async_client.get(
        f"{API}/members/{teacher.organization_membership_id}", headers=clerk_admin_headers
    )
    assert member.status_code == 200
    assert member.json()["teacher_id"] == teacher.id
    assert member.json()["teacher_presence"] == {
        "lunch_required": True,
        "minimum_hours": 2,
        "max_gap_hours": 1,
    }

    admin_membership_id = await db_session.scalar(
        select(models.OrganizationMembership.id)
        .join(models.User, models.User.id == models.OrganizationMembership.account_id)
        .where(models.User.clerk_user_id == "user_admin_001")
    )
    admin_member = await async_client.get(
        f"{API}/members/{admin_membership_id}", headers=clerk_admin_headers
    )
    assert admin_member.status_code == 200
    assert admin_member.json()["teacher_presence"] is None


# --- R09 digest and pending proposal staleness (S3) --------------------------


async def test_r09_presence_rule_changes_the_snapshot_digest_and_stales_the_proposal(
    db_session, monkeypatch
):
    from app import scheduler_v1_worker as worker
    from app import schemas
    from app.scheduler.domain.candidate import SchedulingStrategy
    from app.scheduler.infrastructure.jobs import enqueue_generation
    from app.scheduler.infrastructure.queries import scheduler_status
    from app.scheduler.infrastructure.snapshot import load_snapshot
    from app.services import teacher_service
    from tests._support.db_fixtures import TestingSessionLocal, test_engine
    from tests._support.scheduler_v1 import MOMENT, seed_generatable_school

    seed = await seed_generatable_school(db_session, clerk_org_id="presence_stale_org")
    await db_session.commit()
    before = await load_snapshot(
        db_session,
        seed.organization.id,
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        now_utc=MOMENT,
        school_year_id=seed.year.id,
    )

    await enqueue_generation(
        db_session,
        seed.organization.id,
        idempotency_key="presence-stale",
        requested_by_membership_id=seed.membership.id,
        now_utc=MOMENT,
    )
    await db_session.commit()
    monkeypatch.setattr(worker, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(worker, "engine_async", test_engine)
    monkeypatch.setattr(worker, "_now", lambda: MOMENT)
    monkeypatch.setattr(worker, "RECOVERY_ASSESSMENT_SECONDS", 0.0)
    await worker.process_next_jobs()
    await db_session.refresh(seed.state)

    pending = (await scheduler_status(db_session, seed.organization.id, now_utc=MOMENT))[
        "pending_proposal"
    ]
    assert pending is not None
    assert pending["is_stale"] is False

    await teacher_service.set_teacher_presence(
        db_session,
        seed.assignment.teacher_id,
        schemas.TeacherPresence(lunch_required=False, minimum_hours=3, max_gap_hours=1),
        organization_id=seed.organization.id,
    )
    await db_session.commit()

    after = await load_snapshot(
        db_session,
        seed.organization.id,
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        now_utc=MOMENT,
        school_year_id=seed.year.id,
    )
    assert after.digest != before.digest

    stale = (await scheduler_status(db_session, seed.organization.id, now_utc=MOMENT))[
        "pending_proposal"
    ]
    assert stale["is_stale"] is True
    assert stale["stale_reason"] == "REVISIONS_CHANGED"


async def test_r25_unassigned_teacher_rule_does_not_change_the_snapshot_digest(db_session):
    from app import schemas
    from app.scheduler.domain.candidate import SchedulingStrategy
    from app.scheduler.infrastructure.snapshot import load_snapshot
    from app.services import teacher_service
    from tests._support.scheduler_v1 import MOMENT, seed_generatable_school

    seed = await seed_generatable_school(db_session, clerk_org_id="presence_unassigned_org")
    extra = await create_teacher_profile(
        db_session, organization_id=seed.organization.id, name="Unassigned"
    )
    await db_session.commit()
    before = await load_snapshot(
        db_session,
        seed.organization.id,
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        now_utc=MOMENT,
        school_year_id=seed.year.id,
    )

    await teacher_service.set_teacher_presence(
        db_session,
        extra.id,
        schemas.TeacherPresence(lunch_required=False, minimum_hours=3, max_gap_hours=1),
        organization_id=seed.organization.id,
    )
    await db_session.commit()

    after = await load_snapshot(
        db_session,
        seed.organization.id,
        strategy=SchedulingStrategy.COMPLETE_GENERATION,
        now_utc=MOMENT,
        school_year_id=seed.year.id,
    )
    assert after.digest == before.digest


# --- R17: migration round trip and check constraints -------------------------


def test_r17_teacher_presence_migration_round_trip(clean_database):
    config = _alembic_config()
    try:
        with sync_test_engine.connect() as connection:
            inspector = inspect(connection)
            columns = {column["name"]: column for column in inspector.get_columns("teacher")}
            assert PRESENCE_COLUMNS <= set(columns)
            assert columns["lunch_required"]["nullable"] is False

        command.downgrade(config, PREVIOUS_REVISION)

        with sync_test_engine.connect() as connection:
            columns = {column["name"] for column in inspect(connection).get_columns("teacher")}
            assert not (PRESENCE_COLUMNS & columns)

        command.upgrade(config, "head")
        command.check(config)

        with sync_test_engine.connect() as connection:
            columns = {column["name"] for column in inspect(connection).get_columns("teacher")}
            assert PRESENCE_COLUMNS <= columns
    finally:
        command.upgrade(config, "head")


def _seed_teacher(connection, marker: str) -> int:
    organization_id = connection.execute(
        text(
            "INSERT INTO public.organization(name, clerk_org_id, plan_status) "
            "VALUES (:name, :clerk_org_id, 'active') RETURNING id"
        ),
        {"name": f"Org {marker}", "clerk_org_id": f"org-{marker}"},
    ).scalar_one()
    account_id = connection.execute(
        text(
            'INSERT INTO public."user"(email, name, created_at, updated_at) '
            "VALUES (:email, 'Teacher', now(), now()) RETURNING id"
        ),
        {"email": f"{marker}@example.test"},
    ).scalar_one()
    membership_id = connection.execute(
        text(
            "INSERT INTO public.organization_membership("
            "organization_id, account_id, organization_display_name, lifecycle_status, "
            "access_status, teacher_access_mode, can_admin, can_teach, lock_version, "
            "created_at, updated_at"
            ") VALUES (:organization_id, :account_id, 'Teacher', 'active', 'active', "
            "'scheduler_only', false, true, 0, now(), now()) RETURNING id"
        ),
        {"organization_id": organization_id, "account_id": account_id},
    ).scalar_one()
    return connection.execute(
        text(
            "INSERT INTO public.teacher(organization_id, organization_membership_id) "
            "VALUES (:organization_id, :membership_id) RETURNING id"
        ),
        {"organization_id": organization_id, "membership_id": membership_id},
    ).scalar_one()


def test_r17_teacher_presence_check_constraints(clean_database):
    with sync_test_engine.begin() as connection:
        teacher_id = _seed_teacher(connection, "presence-checks")

    with sync_test_engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT lunch_required, minimum_presence_hours, maximum_presence_gap_hours "
                "FROM public.teacher WHERE id = :teacher_id"
            ),
            {"teacher_id": teacher_id},
        ).one()
    assert row == (True, None, None)

    with pytest.raises(IntegrityError):
        with sync_test_engine.begin() as connection:
            connection.execute(
                text("UPDATE public.teacher SET minimum_presence_hours = 3 WHERE id = :teacher_id"),
                {"teacher_id": teacher_id},
            )

    with pytest.raises(IntegrityError):
        with sync_test_engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE public.teacher SET minimum_presence_hours = 13, "
                    "maximum_presence_gap_hours = 1 WHERE id = :teacher_id"
                ),
                {"teacher_id": teacher_id},
            )

    with pytest.raises(IntegrityError):
        with sync_test_engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE public.teacher SET minimum_presence_hours = 0, "
                    "maximum_presence_gap_hours = 1 WHERE id = :teacher_id"
                ),
                {"teacher_id": teacher_id},
            )

    with sync_test_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE public.teacher SET minimum_presence_hours = 3, "
                "maximum_presence_gap_hours = 1 WHERE id = :teacher_id"
            ),
            {"teacher_id": teacher_id},
        )

    with sync_test_engine.connect() as connection:
        stored = connection.execute(
            text(
                "SELECT minimum_presence_hours, maximum_presence_gap_hours "
                "FROM public.teacher WHERE id = :teacher_id"
            ),
            {"teacher_id": teacher_id},
        ).one()
    assert stored == (3, 1)
