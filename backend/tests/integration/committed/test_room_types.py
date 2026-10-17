"""S1 school room types: tenant isolation, names, Normal fix and removal.

Covers R02 (API), R04, R05 and R06 of the class home room spec, including the
serialization of the catalogue writes that keeps the folded-name uniqueness.
"""

import asyncio
from contextlib import asynccontextmanager

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app import models, schemas
from app.config import settings
from app.core.exceptions import AppError
from app.services import room_type_service
from app.services.bulk_import_policy import fold_text
from tests._support.db_fixtures import MOCK_ORG_ID, TestingSessionLocal, create_org_and_user

API = settings.API_V1_STR
INITIAL_TYPES = {"Normal", "Laboratório", "Ginásio", "Artes"}


async def _list_types(client: AsyncClient, headers: dict) -> list[dict]:
    resp = await client.get(f"{API}/room-types/", headers=headers)
    assert resp.status_code == 200
    return resp.json()


async def _type_by_name(client: AsyncClient, headers: dict, name: str) -> dict:
    for item in await _list_types(client, headers):
        if item["name"] == name:
            return item
    raise AssertionError(f"room type {name!r} not found")


async def _organization_id(db_session, clerk_org_id: str) -> int:
    return await db_session.scalar(
        select(models.Organization.id).where(models.Organization.clerk_org_id == clerk_org_id)
    )


async def _type_id(db_session, organization_id: int, name: str) -> int:
    return await db_session.scalar(
        select(models.SchoolRoomType.id).where(
            models.SchoolRoomType.organization_id == organization_id,
            models.SchoolRoomType.name == name,
        )
    )


async def _assert_still_blocked(task: asyncio.Task) -> None:
    """A write waiting on the school lock cannot finish; an unserialized one does."""
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(asyncio.shield(task), timeout=1.0)


@asynccontextmanager
async def _two_sessions():
    """Two independent connections of the test database."""
    first = TestingSessionLocal()
    second = TestingSessionLocal()
    try:
        yield first, second
    finally:
        for session in (first, second):
            await session.rollback()
            await session.close()


class TestFixtureAndIsolation:
    async def test_fixture_school_has_the_four_initial_types_with_one_normal(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        data = await _list_types(async_client, clerk_admin_headers)
        assert {item["name"] for item in data} == INITIAL_TYPES
        assert [item["name"] for item in data if item["is_normal"]] == ["Normal"]
        assert all(item["room_count"] == 0 and item["subject_count"] == 0 for item in data)

    async def test_two_schools_only_list_their_own_types(
        self, async_client: AsyncClient, db_session, clerk_admin_headers: dict
    ):
        await create_org_and_user(
            db_session,
            clerk_user_id="rt_admin_b",
            clerk_org_id="org_rt_b",
            org_name="Escola Secundária",
        )
        await db_session.commit()
        headers_b = {"Authorization": "Bearer test_rt_admin_b"}

        resp = await async_client.post(
            f"{API}/room-types/", json={"name": "Oficina"}, headers=clerk_admin_headers
        )
        assert resp.status_code == 201

        names_a = {item["name"] for item in await _list_types(async_client, clerk_admin_headers)}
        names_b = {item["name"] for item in await _list_types(async_client, headers_b)}
        assert names_a == INITIAL_TYPES | {"Oficina"}
        assert names_b == INITIAL_TYPES

        type_a = await _type_by_name(async_client, clerk_admin_headers, "Oficina")
        rename = await async_client.patch(
            f"{API}/room-types/{type_a['id']}", json={"name": "Oficina B"}, headers=headers_b
        )
        assert rename.status_code == 404
        delete = await async_client.delete(f"{API}/room-types/{type_a['id']}", headers=headers_b)
        assert delete.status_code == 404

    async def test_teacher_cannot_manage_room_types(
        self, async_client: AsyncClient, clerk_teacher_headers: dict
    ):
        resp = await async_client.get(f"{API}/room-types/", headers=clerk_teacher_headers)
        assert resp.status_code == 403


class TestNormalIsFixed:
    async def test_rename_normal_is_rejected(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        normal = await _type_by_name(async_client, clerk_admin_headers, "Normal")
        resp = await async_client.patch(
            f"{API}/room-types/{normal['id']}",
            json={"name": "Comum"},
            headers=clerk_admin_headers,
        )
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "room_type_fixed"

    async def test_remove_normal_is_rejected(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        normal = await _type_by_name(async_client, clerk_admin_headers, "Normal")
        resp = await async_client.delete(
            f"{API}/room-types/{normal['id']}", headers=clerk_admin_headers
        )
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "room_type_fixed"


class TestNames:
    async def test_name_collides_ignoring_case_and_accents(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        resp = await async_client.post(
            f"{API}/room-types/", json={"name": "laboratorio"}, headers=clerk_admin_headers
        )
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "room_type_name_taken"

    async def test_rename_to_an_existing_name_is_rejected(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        created = await async_client.post(
            f"{API}/room-types/", json={"name": "Oficina"}, headers=clerk_admin_headers
        )
        resp = await async_client.patch(
            f"{API}/room-types/{created.json()['id']}",
            json={"name": "Ginásio"},
            headers=clerk_admin_headers,
        )
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "room_type_name_taken"

    async def test_renaming_to_its_own_folded_name_is_allowed(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        created = await async_client.post(
            f"{API}/room-types/", json={"name": "Oficina"}, headers=clerk_admin_headers
        )
        resp = await async_client.patch(
            f"{API}/room-types/{created.json()['id']}",
            json={"name": "OFICINA"},
            headers=clerk_admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "OFICINA"

    async def test_blank_and_too_long_names_are_rejected(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        for name in ("", "   ", "x" * 61):
            resp = await async_client.post(
                f"{API}/room-types/", json={"name": name}, headers=clerk_admin_headers
            )
            assert resp.status_code == 422, name


class TestRemoval:
    async def test_unused_type_is_deleted(
        self, async_client: AsyncClient, clerk_admin_headers: dict
    ):
        created = await async_client.post(
            f"{API}/room-types/", json={"name": "Oficina"}, headers=clerk_admin_headers
        )
        resp = await async_client.delete(
            f"{API}/room-types/{created.json()['id']}", headers=clerk_admin_headers
        )
        assert resp.status_code == 200
        assert resp.json()["remove_effect"] == "hard_delete"
        assert "Oficina" not in {
            item["name"] for item in await _list_types(async_client, clerk_admin_headers)
        }

    async def test_type_used_by_an_active_room_is_blocked_with_names(
        self, async_client: AsyncClient, db_session, clerk_admin_headers: dict
    ):
        created = await async_client.post(
            f"{API}/room-types/", json={"name": "Oficina"}, headers=clerk_admin_headers
        )
        organization_id = await _organization_id(db_session, MOCK_ORG_ID)
        db_session.add(
            models.Room(
                name="Sala Oficina",
                organization_id=organization_id,
                room_type_id=created.json()["id"],
            )
        )
        db_session.add(
            models.Subject(
                name="Práticas Oficina",
                organization_id=organization_id,
                room_type_id=created.json()["id"],
            )
        )
        await db_session.commit()

        resp = await async_client.delete(
            f"{API}/room-types/{created.json()['id']}", headers=clerk_admin_headers
        )
        assert resp.status_code == 409
        detail = resp.json()["detail"]
        assert detail["code"] == "resource_in_use"
        assert detail["context"]["rooms"] == ["Sala Oficina"]
        assert detail["context"]["subjects"] == ["Práticas Oficina"]

    async def test_type_used_only_by_an_archived_room_is_archived_and_restored(
        self, async_client: AsyncClient, db_session, clerk_admin_headers: dict
    ):
        created = await async_client.post(
            f"{API}/room-types/", json={"name": "Oficina"}, headers=clerk_admin_headers
        )
        organization_id = await _organization_id(db_session, MOCK_ORG_ID)
        db_session.add(
            models.Room(
                name="Sala Antiga",
                organization_id=organization_id,
                room_type_id=created.json()["id"],
                is_archived=True,
            )
        )
        await db_session.commit()

        removed = await async_client.delete(
            f"{API}/room-types/{created.json()['id']}", headers=clerk_admin_headers
        )
        assert removed.status_code == 200
        assert removed.json()["remove_effect"] == "archive"
        assert "Oficina" not in {
            item["name"] for item in await _list_types(async_client, clerk_admin_headers)
        }

        restored = await async_client.post(
            f"{API}/room-types/", json={"name": "oficina"}, headers=clerk_admin_headers
        )
        assert restored.status_code == 201
        assert restored.json()["id"] == created.json()["id"]
        assert restored.json()["name"] == "Oficina"
        assert "Oficina" in {
            item["name"] for item in await _list_types(async_client, clerk_admin_headers)
        }

    async def test_type_used_only_by_an_archived_subject_is_archived(
        self, async_client: AsyncClient, db_session, clerk_admin_headers: dict
    ):
        created = await async_client.post(
            f"{API}/room-types/", json={"name": "Oficina"}, headers=clerk_admin_headers
        )
        organization_id = await _organization_id(db_session, MOCK_ORG_ID)
        db_session.add(
            models.Subject(
                name="Práticas Antigas",
                organization_id=organization_id,
                room_type_id=created.json()["id"],
                is_archived=True,
            )
        )
        await db_session.commit()

        removed = await async_client.delete(
            f"{API}/room-types/{created.json()['id']}", headers=clerk_admin_headers
        )
        assert removed.status_code == 200
        assert removed.json()["remove_effect"] == "archive"


class TestCounts:
    async def test_counts_include_only_active_rooms_and_subjects(
        self, async_client: AsyncClient, db_session, clerk_admin_headers: dict
    ):
        created = await async_client.post(
            f"{API}/room-types/", json={"name": "Oficina"}, headers=clerk_admin_headers
        )
        room_type_id = created.json()["id"]
        organization_id = await _organization_id(db_session, MOCK_ORG_ID)
        db_session.add_all(
            [
                models.Room(
                    name="Sala Ativa",
                    organization_id=organization_id,
                    room_type_id=room_type_id,
                ),
                models.Room(
                    name="Sala Antiga",
                    organization_id=organization_id,
                    room_type_id=room_type_id,
                    is_archived=True,
                ),
                models.Subject(
                    name="Práticas Ativas",
                    organization_id=organization_id,
                    room_type_id=room_type_id,
                ),
                models.Subject(
                    name="Práticas Antigas",
                    organization_id=organization_id,
                    room_type_id=room_type_id,
                    is_archived=True,
                ),
            ]
        )
        await db_session.commit()

        room_type = await _type_by_name(async_client, clerk_admin_headers, "Oficina")
        assert room_type["room_count"] == 1
        assert room_type["subject_count"] == 1

        normal = await _type_by_name(async_client, clerk_admin_headers, "Normal")
        assert normal["room_count"] == 0
        assert normal["subject_count"] == 0


class TestConcurrentWrites:
    async def test_concurrent_create_with_accent_only_difference_keeps_one_type(
        self, db_session, clerk_admin_headers: dict, async_client: AsyncClient
    ):
        organization_id = await _organization_id(db_session, MOCK_ORG_ID)

        async with _two_sessions() as (first, second):
            await room_type_service.create_room_type(
                first, schemas.RoomTypeCreate(name="Oficina"), organization_id
            )
            racing = asyncio.create_task(
                room_type_service.create_room_type(
                    second, schemas.RoomTypeCreate(name="Ofícina"), organization_id
                )
            )
            await _assert_still_blocked(racing)
            await first.commit()

            with pytest.raises(AppError) as error:
                await racing
            assert error.value.code == "room_type_name_taken"

        names = [item["name"] for item in await _list_types(async_client, clerk_admin_headers)]
        assert names.count("Oficina") == 1
        assert "Ofícina" not in names

    async def test_concurrent_create_with_case_only_difference_returns_name_taken(
        self, db_session, clerk_admin_headers: dict, async_client: AsyncClient
    ):
        organization_id = await _organization_id(db_session, MOCK_ORG_ID)

        async with _two_sessions() as (first, second):
            await room_type_service.create_room_type(
                first, schemas.RoomTypeCreate(name="Oficina"), organization_id
            )
            racing = asyncio.create_task(
                room_type_service.create_room_type(
                    second, schemas.RoomTypeCreate(name="OFICINA"), organization_id
                )
            )
            await _assert_still_blocked(racing)
            await first.commit()

            with pytest.raises(AppError) as error:
                await racing
            assert error.value.code == "room_type_name_taken"

        names = [item["name"] for item in await _list_types(async_client, clerk_admin_headers)]
        assert names.count("Oficina") == 1

    async def test_concurrent_rename_cannot_introduce_a_folded_duplicate(
        self, db_session, clerk_admin_headers: dict, async_client: AsyncClient
    ):
        organization_id = await _organization_id(db_session, MOCK_ORG_ID)
        artes_id = await _type_id(db_session, organization_id, "Artes")
        ginasio_id = await _type_id(db_session, organization_id, "Ginásio")

        async with _two_sessions() as (first, second):
            await room_type_service.rename_room_type(
                first, artes_id, schemas.RoomTypeUpdate(name="Oficina"), organization_id
            )
            racing = asyncio.create_task(
                room_type_service.rename_room_type(
                    second, ginasio_id, schemas.RoomTypeUpdate(name="OFICINA"), organization_id
                )
            )
            await _assert_still_blocked(racing)
            await first.commit()

            with pytest.raises(AppError) as error:
                await racing
            assert error.value.code == "room_type_name_taken"

        names = [item["name"] for item in await _list_types(async_client, clerk_admin_headers)]
        assert [name for name in names if fold_text(name) == fold_text("Oficina")] == ["Oficina"]
