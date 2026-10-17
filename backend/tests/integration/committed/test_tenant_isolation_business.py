"""
Testes de Tenant Isolation — Lógica de Negócio
Parte de test_business_logic.py (split).
"""

import base64

from factories import API, _setup_course_class_subject
from httpx import AsyncClient
from sqlalchemy import func, select

from app import models
from tests._support.db_fixtures import (
    create_org_and_user,
    create_teacher_profile,
    get_school_room_type_id,
)


def _csv_payload(filename: str, content: str) -> dict[str, str]:
    return {
        "filename": filename,
        "content_base64": base64.b64encode(("\ufeff" + content).encode("utf-8")).decode("ascii"),
    }


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
                "days_of_week": [0, 4],
            },
        },
        headers=headers,
    )
    assert grid_resp.status_code == 200
    blocks = (await client.get(f"{API}/timeslots/", headers=headers)).json()
    assert blocks
    return blocks


def _grid_hours(blocks: list[dict]) -> list[str]:
    return sorted({block["start_time"][:5] for block in blocks})


class TestTenantIsolation:
    """
    Garante que dados de uma Organização NÃO são visíveis por outra.
    Cria duas orgs com admins separados e verifica isolamento.
    """

    async def _create_org_admin(self, db_session, email: str, org_name: str, cid: str) -> dict:
        """Cria org+admin e devolve headers + mock payload para autenticação via Clerk."""
        org, _ = await create_org_and_user(
            db_session,
            clerk_user_id=cid,
            email=email,
            role="admin",
            org_name=org_name,
        )
        await db_session.commit()
        return {
            "headers": {"Authorization": f"Bearer test_{cid}"},
            "organization_id": org.id,
            "clerk_user_id": cid,
        }

    async def test_org_a_cannot_see_org_b_rooms(
        self,
        async_client: AsyncClient,
        db_session,
    ):
        org_a = await self._create_org_admin(
            db_session, "admin_a@escola.pt", "Escola A", "tenant_iso_a"
        )
        org_b = await self._create_org_admin(
            db_session, "admin_b@escola.pt", "Escola B", "tenant_iso_b"
        )

        await async_client.post(
            f"{API}/rooms/",
            json={"name": "Lab A", "room_type": "lab"},
            headers=org_a["headers"],
        )
        resp = await async_client.get(f"{API}/rooms/", headers=org_b["headers"])
        assert resp.status_code == 200
        assert len(resp.json()) == 0

    async def test_org_a_cannot_see_org_b_teachers(
        self,
        async_client: AsyncClient,
        db_session,
    ):
        org_a = await self._create_org_admin(
            db_session, "admin_a@escola.pt", "Escola A", "tenant_iso_a"
        )
        org_b = await self._create_org_admin(
            db_session, "admin_b@escola.pt", "Escola B", "tenant_iso_b"
        )

        await create_teacher_profile(
            db_session, organization_id=org_a["organization_id"], name="Prof. A"
        )
        await db_session.commit()
        resp = await async_client.get(f"{API}/teachers/", headers=org_b["headers"])
        assert resp.status_code == 200
        assert len(resp.json()) == 0

    async def test_org_a_cannot_update_org_b_subject(
        self,
        async_client: AsyncClient,
        db_session,
    ):
        org_a = await self._create_org_admin(
            db_session, "admin_a@escola.pt", "Escola A", "tenant_iso_a"
        )
        org_b = await self._create_org_admin(
            db_session, "admin_b@escola.pt", "Escola B", "tenant_iso_b"
        )

        sub_resp = await async_client.post(
            f"{API}/subjects/",
            json={
                "name": "Física B",
                "room_type_id": await get_school_room_type_id(
                    db_session, org_b["organization_id"], "Laboratório"
                ),
            },
            headers=org_b["headers"],
        )
        sub_id = sub_resp.json()["id"]
        resp = await async_client.patch(
            f"{API}/subjects/{sub_id}",
            json={"name": "Hackeado"},
            headers=org_a["headers"],
        )
        assert resp.status_code == 404

    async def test_org_a_cannot_delete_org_b_course(
        self,
        async_client: AsyncClient,
        db_session,
    ):
        org_a = await self._create_org_admin(
            db_session, "admin_a@escola.pt", "Escola A", "tenant_iso_a"
        )
        org_b = await self._create_org_admin(
            db_session, "admin_b@escola.pt", "Escola B", "tenant_iso_b"
        )

        course_resp = await async_client.post(
            f"{API}/courses/",
            json={"name": "Curso B", "abbreviation": "CB"},
            headers=org_b["headers"],
        )
        course_id = course_resp.json()["id"]
        resp = await async_client.delete(f"{API}/courses/{course_id}", headers=org_a["headers"])
        assert resp.status_code == 404

    async def test_org_a_cannot_access_org_b_class_availability(
        self,
        async_client: AsyncClient,
        db_session,
    ):
        org_a = await self._create_org_admin(
            db_session, "admin_avail_a@escola.pt", "Escola A Avail", "tenant_iso_avail_a"
        )
        org_b = await self._create_org_admin(
            db_session, "admin_avail_b@escola.pt", "Escola B Avail", "tenant_iso_avail_b"
        )

        course = models.Course(
            name="Curso B Avail",
            abbreviation="CBA",
            organization_id=org_b["organization_id"],
        )
        db_session.add(course)
        await db_session.flush()
        class_b = models.Class(
            name="Turma B Avail",
            size=20,
            start_year=2025,
            end_year=2028,
            grade_level=10,
            course_id=course.id,
            organization_id=org_b["organization_id"],
        )
        db_session.add(class_b)
        await db_session.commit()

        headers = org_a["headers"]
        get_resp = await async_client.get(
            f"{API}/classes/{class_b.id}/availability", headers=headers
        )
        assert get_resp.status_code == 404

        put_resp = await async_client.put(
            f"{API}/classes/{class_b.id}/availability", json=[], headers=headers
        )
        assert put_resp.status_code == 404

        copy_resp = await async_client.post(
            f"{API}/classes/{class_b.id}/availability/copy",
            json={"target_class_ids": [class_b.id + 1]},
            headers=headers,
        )
        assert copy_resp.status_code == 404

    async def test_org_a_cannot_select_org_b_module(
        self,
        async_client: AsyncClient,
        db_session,
    ):
        org_a = await self._create_org_admin(
            db_session, "admin_mod_a@escola.pt", "Escola A", "tenant_iso_mod_a"
        )
        org_b = await self._create_org_admin(
            db_session, "admin_mod_b@escola.pt", "Escola B", "tenant_iso_mod_b"
        )
        ctx_a = await _setup_course_class_subject(async_client, org_a["headers"])
        ctx_b = await _setup_course_class_subject(async_client, org_b["headers"])

        resp = await async_client.patch(
            f"{API}/classes/{ctx_a['class_id']}/subjects/{ctx_a['subject_id']}",
            json={"module_ids": ctx_b["module_ids"]},
            headers=org_a["headers"],
        )

        assert resp.status_code == 404

    async def test_org_a_cannot_import_org_b_teacher_availability(
        self,
        async_client: AsyncClient,
        db_session,
    ):
        org_a = await self._create_org_admin(
            db_session, "admin_ta_a@escola.pt", "Escola A TA", "tenant_iso_ta_a"
        )
        org_b = await self._create_org_admin(
            db_session, "admin_ta_b@escola.pt", "Escola B TA", "tenant_iso_ta_b"
        )
        blocks_a = await _prepare_grid(async_client, org_a["headers"])
        blocks_b = await _prepare_grid(async_client, org_b["headers"])
        teacher_b = await create_teacher_profile(
            db_session, organization_id=org_b["organization_id"], name="Prof. B"
        )
        await db_session.commit()
        membership = await db_session.get(
            models.OrganizationMembership, teacher_b.organization_membership_id
        )
        account = await db_session.get(models.User, membership.account_id)
        monday_b = next(
            block
            for block in blocks_b
            if block["day_of_week"] == 0
            and block["start_time"].startswith(_grid_hours(blocks_b)[0])
        )
        db_session.add(
            models.Availability(
                organization_id=org_b["organization_id"],
                teacher_id=teacher_b.id,
                timeslot_id=monday_b["id"],
                score=-1,
            )
        )
        await db_session.commit()

        hours_a = _grid_hours(blocks_a)
        cells = ";".join(["Impossível"] + ["" for _ in hours_a[1:]])
        files = {
            "rooms": _csv_payload(
                "Cronos_Salas_Template.csv",
                "Nome da sala;Tipo de sala;Capacidade\r\nSala Cross Tenant;Normal;20\r\n",
            ),
            "teacher_availability": _csv_payload(
                "Cronos_DisponibilidadeProfessores_Template.csv",
                "Nome do professor;Email do professor;Dia;"
                + ";".join(hours_a)
                + "\r\n"
                + f"Prof. B;{account.email};Segunda;{cells}\r\n",
            ),
        }

        response = await async_client.post(
            f"{API}/imports/validate", json={"files": files}, headers=org_a["headers"]
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["can_commit"] is False
        missing = [
            issue for issue in payload["issues"] if issue["code"] == "teacher_reference_missing"
        ]
        assert len(missing) == 1
        assert missing[0]["field"] == "teacher_email"

        commit = await async_client.post(
            f"{API}/imports/commit", json={"files": files}, headers=org_a["headers"]
        )
        assert commit.status_code == 422

        foreign_rows = await db_session.scalar(
            select(func.count())
            .select_from(models.Availability)
            .where(models.Availability.teacher_id == teacher_b.id)
        )
        assert foreign_rows == 1
        foreign_unchanged = await db_session.scalar(
            select(func.count())
            .select_from(models.Availability)
            .where(
                models.Availability.teacher_id == teacher_b.id,
                models.Availability.timeslot_id == monday_b["id"],
                models.Availability.score == -1,
            )
        )
        assert foreign_unchanged == 1
        local_rooms = await db_session.scalar(
            select(func.count())
            .select_from(models.Room)
            .where(
                models.Room.organization_id == org_a["organization_id"],
                models.Room.name == "Sala Cross Tenant",
            )
        )
        assert local_rooms == 0
