"""Integration tests for the class weekly availability API and table (WBS 2.1.2, 2.2)."""

from datetime import date, time
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, insert, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app import models
from app.config import settings

pytestmark = pytest.mark.postgresql

API = settings.API_V1_STR
ADMIN_CLERK_ORG_ID = "org_test_001"


async def _admin_org_id(db_session) -> int:
    return await db_session.scalar(
        select(models.Organization.id).where(models.Organization.clerk_org_id == ADMIN_CLERK_ORG_ID)
    )


async def _prepare_grid(client: AsyncClient, headers: dict) -> list[dict]:
    settings_resp = await client.post(
        f"{API}/school/settings/",
        json={"school_start_date": "2025-09-01", "school_hard_end_date": "2026-07-31"},
        headers=headers,
    )
    assert settings_resp.status_code == 200
    grid_resp = await client.post(
        f"{API}/school/grid-settings/regenerate",
        json={
            "grid_settings": {},
            "timeslots": {
                "start_time": "08:00",
                "end_time": "10:00",
                "slot_duration_minutes": 50,
                "break_duration_minutes": 10,
                "days_of_week": [0, 1],
            },
        },
        headers=headers,
    )
    assert grid_resp.status_code == 200
    blocks = (await client.get(f"{API}/timeslots/", headers=headers)).json()
    assert blocks
    return blocks


async def _seed_grid_versions(db_session, organization_id: int, *, slots_per_version: int = 1):
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
    older_slots = [
        models.Timeslot(
            organization_id=organization_id,
            grid_version_id=older.id,
            day_of_week=0,
            start_time=time(8 + index, 0),
            end_time=time(8 + index, 50),
        )
        for index in range(slots_per_version)
    ]
    newer_slots = [
        models.Timeslot(
            organization_id=organization_id,
            grid_version_id=newer.id,
            day_of_week=0,
            start_time=time(10 + index, 0),
            end_time=time(10 + index, 50),
        )
        for index in range(slots_per_version)
    ]
    db_session.add_all([*older_slots, *newer_slots])
    await db_session.flush()
    return older_slots, newer_slots


async def _seed_class(
    db_session,
    organization_id: int,
    *,
    name: str,
    is_archived: bool = False,
    with_link: bool = False,
) -> models.Class:
    course = models.Course(
        name=f"Curso {name}",
        abbreviation=f"C{uuid4().hex[:5].upper()}",
        organization_id=organization_id,
    )
    db_session.add(course)
    await db_session.flush()
    klass = models.Class(
        name=name,
        size=20,
        start_year=2025,
        end_year=2028,
        grade_level=10,
        course_id=course.id,
        organization_id=organization_id,
        is_archived=is_archived,
    )
    db_session.add(klass)
    await db_session.flush()
    if with_link:
        subject = models.Subject(
            name=f"Disciplina {name}",
            required_room_type=models.RoomType.normal,
            organization_id=organization_id,
        )
        db_session.add(subject)
        await db_session.flush()
        db_session.add(
            models.ClassSubjectLink(
                organization_id=organization_id,
                class_id=klass.id,
                subject_id=subject.id,
                grade_level=10,
            )
        )
        await db_session.flush()
    await db_session.commit()
    return klass


async def _saved_scores(db_session, organization_id: int, class_id: int) -> dict[int, int]:
    rows = (
        await db_session.execute(
            select(models.ClassAvailability.timeslot_id, models.ClassAvailability.score).where(
                models.ClassAvailability.organization_id == organization_id,
                models.ClassAvailability.class_id == class_id,
            )
        )
    ).all()
    return {int(timeslot_id): int(score) for timeslot_id, score in rows}


async def _class_events(db_session, organization_id: int) -> list:
    return list(
        (
            await db_session.scalars(
                select(models.SchedulerStateVersionEvent)
                .where(
                    models.SchedulerStateVersionEvent.organization_id == organization_id,
                    models.SchedulerStateVersionEvent.entity_type == "CLASS_AVAILABILITY",
                )
                .order_by(models.SchedulerStateVersionEvent.id)
            )
        ).all()
    )


async def _seed_plain_class(db_session, *, name: str, slot_count: int = 1):
    organization = models.Organization(name=f"{name} Org {uuid4().hex[:6]}", plan_status="active")
    db_session.add(organization)
    await db_session.flush()
    course = models.Course(
        name=f"{name} Course",
        abbreviation=f"C{uuid4().hex[:5].upper()}",
        organization_id=organization.id,
    )
    version = models.GridVersion(
        organization_id=organization.id,
        effective_date=date(2000, 1, 1),
        state=models.GridVersionState.ACTIVE,
    )
    db_session.add_all([course, version])
    await db_session.flush()
    klass = models.Class(
        name=f"{name} Class",
        size=20,
        start_year=2025,
        end_year=2028,
        grade_level=10,
        course_id=course.id,
        organization_id=organization.id,
    )
    db_session.add(klass)
    await db_session.flush()
    slots = [
        models.Timeslot(
            organization_id=organization.id,
            grid_version_id=version.id,
            day_of_week=0,
            start_time=time(8 + index, 0),
            end_time=time(8 + index, 50),
        )
        for index in range(slot_count)
    ]
    db_session.add_all(slots)
    await db_session.flush()
    return organization, klass, slots


async def _add_class_scores(db_session, organization_id: int, class_id: int, scores) -> None:
    for slot, score in scores:
        db_session.add(
            models.ClassAvailability(
                organization_id=organization_id,
                class_id=class_id,
                timeslot_id=slot.id,
                score=score,
            )
        )
    await db_session.flush()


class TestClassAvailabilityTableContract:
    async def test_check_constraint_rejects_a_neutral_row(self, db_session):
        organization, klass, slots = await _seed_plain_class(db_session, name="Check", slot_count=2)
        await _add_class_scores(db_session, organization.id, klass.id, [(slots[0], -1)])

        with pytest.raises(IntegrityError):
            await _add_class_scores(db_session, organization.id, klass.id, [(slots[1], 1)])
        await db_session.rollback()

    async def test_impossible_avoid_and_preferred_scores_are_accepted(self, db_session):
        organization, klass, slots = await _seed_plain_class(
            db_session, name="Scores", slot_count=3
        )
        await _add_class_scores(
            db_session, organization.id, klass.id, list(zip(slots, (-1, 0, 2), strict=True))
        )

        assert await _saved_scores(db_session, organization.id, klass.id) == {
            slots[0].id: -1,
            slots[1].id: 0,
            slots[2].id: 2,
        }

    async def test_rows_cascade_when_the_class_or_block_is_deleted(self, db_session):
        organization, klass, slots = await _seed_plain_class(
            db_session, name="Cascade", slot_count=2
        )
        await _add_class_scores(
            db_session, organization.id, klass.id, [(slots[0], -1), (slots[1], 2)]
        )

        await db_session.execute(delete(models.Timeslot).where(models.Timeslot.id == slots[0].id))
        await db_session.flush()
        assert await _saved_scores(db_session, organization.id, klass.id) == {slots[1].id: 2}

        await db_session.execute(delete(models.Class).where(models.Class.id == klass.id))
        await db_session.flush()
        assert await _saved_scores(db_session, organization.id, klass.id) == {}

    async def test_runtime_role_with_check_rejects_a_foreign_organization_row(
        self, db_session, runtime_db_session
    ):
        own_org, _, _ = await _seed_plain_class(db_session, name="Rls Own")
        foreign_org, foreign_klass, foreign_slots = await _seed_plain_class(
            db_session, name="Rls Foreign"
        )
        await db_session.commit()

        await runtime_db_session.execute(
            text("SELECT set_config('app.current_organization_id', :org, true)"),
            {"org": str(own_org.id)},
        )
        with pytest.raises(DBAPIError):
            await runtime_db_session.execute(
                insert(models.ClassAvailability).values(
                    organization_id=foreign_org.id,
                    class_id=foreign_klass.id,
                    timeslot_id=foreign_slots[0].id,
                    score=-1,
                )
            )
            await runtime_db_session.flush()


class TestClassAvailabilityRead:
    async def test_missing_rows_read_as_neutral(
        self, async_client: AsyncClient, clerk_admin_headers: dict, db_session
    ):
        blocks = await _prepare_grid(async_client, clerk_admin_headers)
        org_id = await _admin_org_id(db_session)
        klass = await _seed_class(db_session, org_id, name="Turma Neutra")

        response = await async_client.get(
            f"{API}/classes/{klass.id}/availability", headers=clerk_admin_headers
        )

        assert response.status_code == 200
        payload = response.json()
        expected_ids = [block["id"] for block in blocks]
        assert [row["timeslot_id"] for row in payload] == expected_ids
        assert set(row["timeslot_id"] for row in payload) == set(expected_ids)
        assert {row["score"] for row in payload} == {1}


class TestClassAvailabilityWrite:
    async def test_put_keeps_only_non_neutral_rows_and_records_the_change(
        self, async_client: AsyncClient, clerk_admin_headers: dict, db_session
    ):
        blocks = await _prepare_grid(async_client, clerk_admin_headers)
        org_id = await _admin_org_id(db_session)
        klass = await _seed_class(db_session, org_id, name="Turma Escrita", with_link=True)
        ordered = sorted(block["id"] for block in blocks)
        payload = [
            {"timeslot_id": ordered[0], "score": 2},
            {"timeslot_id": ordered[1], "score": 1},
            {"timeslot_id": ordered[2], "score": 0},
            {"timeslot_id": ordered[3], "score": -1},
        ]

        response = await async_client.put(
            f"{API}/classes/{klass.id}/availability",
            json=payload,
            headers=clerk_admin_headers,
        )

        assert response.status_code == 200
        assert response.json() == {"status": "success", "count": 3}
        assert await _saved_scores(db_session, org_id, klass.id) == {
            ordered[0]: 2,
            ordered[2]: 0,
            ordered[3]: -1,
        }
        events = await _class_events(db_session, org_id)
        assert len(events) == 1
        assert events[0].operation == models.SchedulerStateChangeOperation.BULK_IMPORT
        assert events[0].entity_id == str(klass.id)
        assert events[0].change_scope == models.SchedulerStateChangeScope.FUTURE_IMPACTING

    async def test_put_without_class_subject_link_is_an_inactive_resource(
        self, async_client: AsyncClient, clerk_admin_headers: dict, db_session
    ):
        blocks = await _prepare_grid(async_client, clerk_admin_headers)
        org_id = await _admin_org_id(db_session)
        klass = await _seed_class(db_session, org_id, name="Turma Sem Disciplinas")
        ordered = sorted(block["id"] for block in blocks)

        response = await async_client.put(
            f"{API}/classes/{klass.id}/availability",
            json=[{"timeslot_id": block_id, "score": 0} for block_id in ordered],
            headers=clerk_admin_headers,
        )

        assert response.status_code == 200
        events = await _class_events(db_session, org_id)
        assert events[-1].change_scope == models.SchedulerStateChangeScope.INACTIVE_RESOURCE

    async def test_put_rejects_duplicate_timeslots(
        self, async_client: AsyncClient, clerk_admin_headers: dict, db_session
    ):
        blocks = await _prepare_grid(async_client, clerk_admin_headers)
        org_id = await _admin_org_id(db_session)
        klass = await _seed_class(db_session, org_id, name="Turma Duplicada")
        first = blocks[0]["id"]

        response = await async_client.put(
            f"{API}/classes/{klass.id}/availability",
            json=[{"timeslot_id": first, "score": 0}, {"timeslot_id": first, "score": 2}],
            headers=clerk_admin_headers,
        )

        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "duplicate_timeslot"

    async def test_put_rejects_an_incomplete_timeslot_set(
        self, async_client: AsyncClient, clerk_admin_headers: dict, db_session
    ):
        blocks = await _prepare_grid(async_client, clerk_admin_headers)
        org_id = await _admin_org_id(db_session)
        klass = await _seed_class(db_session, org_id, name="Turma Incompleta")

        response = await async_client.put(
            f"{API}/classes/{klass.id}/availability",
            json=[{"timeslot_id": blocks[0]["id"], "score": 0}],
            headers=clerk_admin_headers,
        )

        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "bad_request"

    async def test_put_rejects_an_archived_class(
        self, async_client: AsyncClient, clerk_admin_headers: dict, db_session
    ):
        blocks = await _prepare_grid(async_client, clerk_admin_headers)
        org_id = await _admin_org_id(db_session)
        klass = await _seed_class(db_session, org_id, name="Turma Arquivada", is_archived=True)

        response = await async_client.put(
            f"{API}/classes/{klass.id}/availability",
            json=[{"timeslot_id": block["id"], "score": 0} for block in blocks],
            headers=clerk_admin_headers,
        )

        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "bad_request"

    async def test_put_leaves_rows_of_other_versions_untouched(
        self, async_client: AsyncClient, clerk_admin_headers: dict, db_session
    ):
        org_id = await _admin_org_id(db_session)
        older = models.GridVersion(
            organization_id=org_id,
            effective_date=date(2000, 1, 1),
            state=models.GridVersionState.ACTIVE,
        )
        newer = models.GridVersion(
            organization_id=org_id,
            effective_date=date(2030, 1, 1),
            state=models.GridVersionState.ACTIVE,
        )
        db_session.add_all([older, newer])
        await db_session.flush()
        old_slot = models.Timeslot(
            organization_id=org_id,
            grid_version_id=older.id,
            day_of_week=0,
            start_time=time(8, 0),
            end_time=time(8, 50),
        )
        new_slot = models.Timeslot(
            organization_id=org_id,
            grid_version_id=newer.id,
            day_of_week=0,
            start_time=time(10, 0),
            end_time=time(10, 50),
        )
        db_session.add_all([old_slot, new_slot])
        klass = await _seed_class(db_session, org_id, name="Turma Versões")
        db_session.add(
            models.ClassAvailability(
                organization_id=org_id, class_id=klass.id, timeslot_id=old_slot.id, score=-1
            )
        )
        await db_session.commit()

        response = await async_client.put(
            f"{API}/classes/{klass.id}/availability",
            params={"on_date": "2031-01-01"},
            json=[{"timeslot_id": new_slot.id, "score": 2}],
            headers=clerk_admin_headers,
        )

        assert response.status_code == 200
        assert await _saved_scores(db_session, org_id, klass.id) == {
            old_slot.id: -1,
            new_slot.id: 2,
        }


class TestClassAvailabilityVersionScope:
    async def test_get_on_date_selects_the_visible_version(
        self, async_client: AsyncClient, clerk_admin_headers: dict, db_session
    ):
        org_id = await _admin_org_id(db_session)
        older_slots, newer_slots = await _seed_grid_versions(db_session, org_id)
        klass = await _seed_class(db_session, org_id, name="Turma OnDate")
        db_session.add_all(
            [
                models.ClassAvailability(
                    organization_id=org_id,
                    class_id=klass.id,
                    timeslot_id=older_slots[0].id,
                    score=-1,
                ),
                models.ClassAvailability(
                    organization_id=org_id,
                    class_id=klass.id,
                    timeslot_id=newer_slots[0].id,
                    score=2,
                ),
            ]
        )
        await db_session.commit()

        older = await async_client.get(
            f"{API}/classes/{klass.id}/availability",
            params={"on_date": "2001-01-01"},
            headers=clerk_admin_headers,
        )
        assert older.status_code == 200
        assert older.json() == [{"timeslot_id": older_slots[0].id, "score": -1}]

        newer = await async_client.get(
            f"{API}/classes/{klass.id}/availability",
            params={"on_date": "2031-01-01"},
            headers=clerk_admin_headers,
        )
        assert newer.status_code == 200
        assert newer.json() == [{"timeslot_id": newer_slots[0].id, "score": 2}]

    async def test_put_rejects_a_timeslot_outside_the_visible_version(
        self, async_client: AsyncClient, clerk_admin_headers: dict, db_session
    ):
        org_id = await _admin_org_id(db_session)
        _older_slots, newer_slots = await _seed_grid_versions(db_session, org_id)
        klass = await _seed_class(db_session, org_id, name="Turma Fora Versão")

        response = await async_client.put(
            f"{API}/classes/{klass.id}/availability",
            params={"on_date": "2001-01-01"},
            json=[{"timeslot_id": newer_slots[0].id, "score": 0}],
            headers=clerk_admin_headers,
        )

        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "bad_request"
        assert await _saved_scores(db_session, org_id, klass.id) == {}

    async def test_copy_keeps_rows_of_other_versions(
        self, async_client: AsyncClient, clerk_admin_headers: dict, db_session
    ):
        org_id = await _admin_org_id(db_session)
        older_slots, newer_slots = await _seed_grid_versions(db_session, org_id)
        origin = await _seed_class(db_session, org_id, name="Origem Versões")
        target = await _seed_class(db_session, org_id, name="Destino Versões")
        db_session.add_all(
            [
                models.ClassAvailability(
                    organization_id=org_id,
                    class_id=origin.id,
                    timeslot_id=older_slots[0].id,
                    score=-1,
                ),
                models.ClassAvailability(
                    organization_id=org_id,
                    class_id=origin.id,
                    timeslot_id=newer_slots[0].id,
                    score=2,
                ),
                models.ClassAvailability(
                    organization_id=org_id,
                    class_id=target.id,
                    timeslot_id=older_slots[0].id,
                    score=0,
                ),
            ]
        )
        await db_session.commit()

        response = await async_client.post(
            f"{API}/classes/{origin.id}/availability/copy",
            params={"on_date": "2031-01-01"},
            json={"target_class_ids": [target.id]},
            headers=clerk_admin_headers,
        )

        assert response.status_code == 200
        assert await _saved_scores(db_session, org_id, target.id) == {
            older_slots[0].id: 0,
            newer_slots[0].id: 2,
        }


class TestClassAvailabilityCopy:
    async def test_copy_replaces_every_target_grid_and_records_each_target(
        self, async_client: AsyncClient, clerk_admin_headers: dict, db_session
    ):
        blocks = await _prepare_grid(async_client, clerk_admin_headers)
        org_id = await _admin_org_id(db_session)
        origin = await _seed_class(db_session, org_id, name="Turma Origem", with_link=True)
        targets = [
            await _seed_class(db_session, org_id, name=f"Turma Destino {index}", with_link=True)
            for index in range(2)
        ]
        ordered = sorted(block["id"] for block in blocks)
        origin_response = await async_client.put(
            f"{API}/classes/{origin.id}/availability",
            json=[
                {"timeslot_id": ordered[0], "score": -1},
                {"timeslot_id": ordered[1], "score": 0},
                {"timeslot_id": ordered[2], "score": 1},
                {"timeslot_id": ordered[3], "score": 2},
            ],
            headers=clerk_admin_headers,
        )
        assert origin_response.status_code == 200

        response = await async_client.post(
            f"{API}/classes/{origin.id}/availability/copy",
            json={"target_class_ids": [target.id for target in targets]},
            headers=clerk_admin_headers,
        )

        assert response.status_code == 200
        assert response.json() == {"updated_class_ids": [target.id for target in targets]}
        expected = {ordered[0]: -1, ordered[1]: 0, ordered[3]: 2}
        for target in targets:
            assert await _saved_scores(db_session, org_id, target.id) == expected
        events = await _class_events(db_session, org_id)
        copied = [event for event in events if event.entity_id in {str(t.id) for t in targets}]
        assert len(copied) == 2

    async def test_copy_rejects_duplicate_targets_origin_and_archived_target(
        self, async_client: AsyncClient, clerk_admin_headers: dict, db_session
    ):
        await _prepare_grid(async_client, clerk_admin_headers)
        org_id = await _admin_org_id(db_session)
        origin = await _seed_class(db_session, org_id, name="Turma Origem Inválida")
        archived = await _seed_class(
            db_session, org_id, name="Turma Alvo Arquivada", is_archived=True
        )

        duplicate = await async_client.post(
            f"{API}/classes/{origin.id}/availability/copy",
            json={"target_class_ids": [origin.id + 1000, origin.id + 1000]},
            headers=clerk_admin_headers,
        )
        assert duplicate.status_code == 400
        assert duplicate.json()["detail"]["code"] == "bad_request"

        same_as_origin = await async_client.post(
            f"{API}/classes/{origin.id}/availability/copy",
            json={"target_class_ids": [origin.id]},
            headers=clerk_admin_headers,
        )
        assert same_as_origin.status_code == 400

        archived_target = await async_client.post(
            f"{API}/classes/{origin.id}/availability/copy",
            json={"target_class_ids": [archived.id]},
            headers=clerk_admin_headers,
        )
        assert archived_target.status_code == 400

    async def test_copy_validates_all_targets_before_changing_any(
        self, async_client: AsyncClient, clerk_admin_headers: dict, db_session
    ):
        blocks = await _prepare_grid(async_client, clerk_admin_headers)
        org_id = await _admin_org_id(db_session)
        origin = await _seed_class(db_session, org_id, name="Turma Origem Atómica", with_link=True)
        valid_target = await _seed_class(db_session, org_id, name="Turma Alvo Válida")
        ordered = sorted(block["id"] for block in blocks)
        await async_client.put(
            f"{API}/classes/{origin.id}/availability",
            json=[{"timeslot_id": block_id, "score": -1} for block_id in ordered],
            headers=clerk_admin_headers,
        )

        response = await async_client.post(
            f"{API}/classes/{origin.id}/availability/copy",
            json={"target_class_ids": [valid_target.id, 999999]},
            headers=clerk_admin_headers,
        )

        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "resource_not_found"
        assert await _saved_scores(db_session, org_id, valid_target.id) == {}

    async def test_copy_rejects_a_foreign_target_and_changes_nothing(
        self, async_client: AsyncClient, clerk_admin_headers: dict, db_session
    ):
        blocks = await _prepare_grid(async_client, clerk_admin_headers)
        org_id = await _admin_org_id(db_session)
        origin = await _seed_class(db_session, org_id, name="Origem Foreign", with_link=True)
        valid_target = await _seed_class(db_session, org_id, name="Destino Válido")
        foreign_org = models.Organization(name=f"Foreign {uuid4().hex[:6]}", plan_status="active")
        db_session.add(foreign_org)
        await db_session.flush()
        foreign_course = models.Course(
            name="Foreign Course", abbreviation="FRG", organization_id=foreign_org.id
        )
        db_session.add(foreign_course)
        await db_session.flush()
        foreign_class = models.Class(
            name="Foreign Class",
            size=20,
            start_year=2025,
            end_year=2028,
            grade_level=10,
            course_id=foreign_course.id,
            organization_id=foreign_org.id,
        )
        db_session.add(foreign_class)
        await db_session.commit()
        ordered = sorted(block["id"] for block in blocks)
        await async_client.put(
            f"{API}/classes/{origin.id}/availability",
            json=[{"timeslot_id": block_id, "score": -1} for block_id in ordered],
            headers=clerk_admin_headers,
        )

        response = await async_client.post(
            f"{API}/classes/{origin.id}/availability/copy",
            json={"target_class_ids": [valid_target.id, foreign_class.id]},
            headers=clerk_admin_headers,
        )

        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "resource_not_found"
        assert await _saved_scores(db_session, org_id, valid_target.id) == {}
