"""
Testes de Tenant Isolation — Lógica de Negócio
Parte de test_business_logic.py (split).
"""

from factories import API
from httpx import AsyncClient

from tests._support.db_fixtures import create_org_and_user, create_teacher_profile


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
            json={"name": "Física B", "required_room_type": "lab"},
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
