"""
TESTES DE TENANT ISOLATION — COBERTURA COMPLETA (CLERK)
======================================================
Valida isolamento entre organizacoes para TODAS as entidades:
Rooms, Courses, Timeslots, Occurrences, Settings, IDOR.
Reescrito para usar Clerk mock fixtures apos migracao.
"""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.config import settings
from tests._support.db_fixtures import create_org_and_user

API = settings.API_V1_STR


async def _setup_pair(
    db_session: AsyncSession,
    suffix: str,
) -> tuple[tuple[models.Organization, models.User], tuple[models.Organization, models.User]]:
    """Create two organizations with separate persisted administrators."""
    org_a, user_a = await create_org_and_user(
        db_session,
        clerk_user_id=f"user_{suffix}_a",
        email=f"{suffix}_a@test.pt",
        role="admin",
        org_name=f"Org {suffix} A",
        clerk_org_id=f"org_{suffix}_a",
    )
    org_b, user_b = await create_org_and_user(
        db_session,
        clerk_user_id=f"user_{suffix}_b",
        email=f"{suffix}_b@test.pt",
        role="admin",
        org_name=f"Org {suffix} B",
        clerk_org_id=f"org_{suffix}_b",
    )
    await db_session.commit()
    return (org_a, user_a), (org_b, user_b)


def _hdr(user_id: str) -> dict:
    return {"Authorization": f"Bearer test_{user_id}"}


# ============================================================
# ROOMS
# ============================================================
async def test_rooms_isolated_between_orgs(async_client: AsyncClient, db_session: AsyncSession):
    (_org_a, _), (_org_b, _) = await _setup_pair(db_session, "rooms")

    r = await async_client.post(
        f"{API}/rooms/",
        json={
            "name": "Sala Exclusiva A",
            "type": "normal",
            "capacity": 30,
        },
        headers=_hdr("user_rooms_a"),
    )
    assert r.status_code == 200

    r = await async_client.post(
        f"{API}/rooms/",
        json={
            "name": "Sala Exclusiva B",
            "type": "lab",
            "capacity": 20,
        },
        headers=_hdr("user_rooms_b"),
    )
    assert r.status_code == 200

    resp_a = await async_client.get(f"{API}/rooms/", headers=_hdr("user_rooms_a"))
    names_a = [item["name"] for item in resp_a.json()]
    assert "Sala Exclusiva A" in names_a
    assert "Sala Exclusiva B" not in names_a

    resp_b = await async_client.get(f"{API}/rooms/", headers=_hdr("user_rooms_b"))
    names_b = [item["name"] for item in resp_b.json()]
    assert "Sala Exclusiva B" in names_b
    assert "Sala Exclusiva A" not in names_b


# ============================================================
# COURSES
# ============================================================
async def test_courses_isolated_between_orgs(async_client: AsyncClient, db_session: AsyncSession):
    (_org_a, _), (_org_b, _) = await _setup_pair(db_session, "courses")

    r = await async_client.post(
        f"{API}/courses/",
        json={
            "name": "Curso Exclusivo A",
            "abbreviation": "CEA",
        },
        headers=_hdr("user_courses_a"),
    )
    assert r.status_code == 200

    r = await async_client.post(
        f"{API}/courses/",
        json={
            "name": "Curso Exclusivo B",
            "abbreviation": "CEB",
        },
        headers=_hdr("user_courses_b"),
    )
    assert r.status_code == 200

    resp_a = await async_client.get(f"{API}/courses/", headers=_hdr("user_courses_a"))
    names_a = [c["name"] for c in resp_a.json()]
    assert "Curso Exclusivo A" in names_a
    assert "Curso Exclusivo B" not in names_a

    resp_b = await async_client.get(f"{API}/courses/", headers=_hdr("user_courses_b"))
    names_b = [c["name"] for c in resp_b.json()]
    assert "Curso Exclusivo B" in names_b
    assert "Curso Exclusivo A" not in names_b


# ============================================================
# TIMESLOTS
# ============================================================
async def test_timeslots_isolated_between_orgs(async_client: AsyncClient, db_session: AsyncSession):
    (_org_a, _), (_org_b, _) = await _setup_pair(db_session, "slots")

    r = await async_client.post(
        f"{API}/timeslots/generate",
        json={
            "start_time": "08:00",
            "end_time": "10:00",
            "slot_duration_minutes": 50,
            "break_duration_minutes": 10,
            "days_of_week": [0],
        },
        headers=_hdr("user_slots_a"),
    )
    assert r.status_code == 200

    r = await async_client.post(
        f"{API}/timeslots/generate",
        json={
            "start_time": "14:00",
            "end_time": "16:00",
            "slot_duration_minutes": 50,
            "break_duration_minutes": 10,
            "days_of_week": [1],
        },
        headers=_hdr("user_slots_b"),
    )
    assert r.status_code == 200

    resp_a = await async_client.get(f"{API}/timeslots/", headers=_hdr("user_slots_a"))
    day_a = {ts["day_of_week"] for ts in resp_a.json()}
    assert day_a == {0}

    resp_b = await async_client.get(f"{API}/timeslots/", headers=_hdr("user_slots_b"))
    day_b = {ts["day_of_week"] for ts in resp_b.json()}
    assert day_b == {1}


# ============================================================
# OCCURRENCES
# ============================================================
async def test_occurrences_not_visible_across_orgs(
    async_client: AsyncClient, db_session: AsyncSession
):
    (_org_a, _), (_org_b, _) = await _setup_pair(db_session, "occ")

    r = await async_client.get(f"{API}/occurrences/", headers=_hdr("user_occ_b"))
    assert r.status_code == 200
    assert r.json()["items"] == []

    resp_cross = await async_client.get(
        f"{API}/occurrences/99999/substitutes/recommendations",
        headers=_hdr("user_occ_a"),
    )
    assert resp_cross.status_code == 404


# ============================================================
# SETTINGS
# ============================================================
async def test_settings_isolated_between_orgs(async_client: AsyncClient, db_session: AsyncSession):
    (_org_a, _), (_org_b, _) = await _setup_pair(db_session, "set")

    r = await async_client.post(
        f"{API}/school/settings/",
        json={
            "school_start_date": "2025-09-01",
            "school_hard_end_date": "2026-07-31",
        },
        headers=_hdr("user_set_a"),
    )
    assert r.status_code == 200

    resp_a = await async_client.get(f"{API}/school/settings/", headers=_hdr("user_set_a"))
    assert resp_a.status_code == 200
    data_a = resp_a.json()
    assert "school_start_date" in data_a

    resp_b = await async_client.get(f"{API}/school/settings/", headers=_hdr("user_set_b"))
    assert resp_b.status_code == 404


# ============================================================
# IDOR — Insecure Direct Object Reference
# ============================================================
async def test_cannot_access_room_from_other_org(
    async_client: AsyncClient, db_session: AsyncSession
):
    (_org_a, _), (_org_b, _) = await _setup_pair(db_session, "idor_room")

    r = await async_client.post(
        f"{API}/rooms/",
        json={
            "name": "Sala IDOR",
            "type": "normal",
            "capacity": 30,
        },
        headers=_hdr("user_idor_room_a"),
    )
    room_id = r.json()["id"]

    r = await async_client.get(f"{API}/rooms/{room_id}", headers=_hdr("user_idor_room_b"))
    assert r.status_code == 405


async def test_cannot_access_course_from_other_org(
    async_client: AsyncClient, db_session: AsyncSession
):
    (_org_a, _), (_org_b, _) = await _setup_pair(db_session, "idor_course")

    r = await async_client.post(
        f"{API}/courses/",
        json={
            "name": "Curso IDOR",
            "abbreviation": "CID",
        },
        headers=_hdr("user_idor_course_a"),
    )
    course_id = r.json()["id"]

    r = await async_client.get(f"{API}/courses/{course_id}", headers=_hdr("user_idor_course_b"))
    assert r.status_code == 404
