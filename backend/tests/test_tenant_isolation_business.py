"""
Testes de Tenant Isolation — Lógica de Negócio
Parte de test_business_logic.py (split).
"""
import pytest
from httpx import AsyncClient
from app import models
from app.core.security import hash_password, create_access_token
from app.models import UserRole
from test_business_logic_shared import API


@pytest.mark.asyncio
class TestTenantIsolation:
    """
    Garante que dados de uma Organização NÃO são visíveis por outra.
    Cria duas orgs com admins separados e verifica isolamento.
    """

    async def _create_org_admin(self, db_session, email: str, org_name: str) -> dict:
        org = models.Organization(name=org_name, plan_status="active")
        db_session.add(org)
        await db_session.flush()
        user = models.User(
            email=email, hashed_password=hash_password("pass123"),
            is_active=True, role=UserRole.admin, organization_id=org.id,
        )
        db_session.add(user)
        await db_session.commit()
        token = create_access_token(data={"sub": email})
        return {"headers": {"Authorization": f"Bearer {token}"}, "organization_id": org.id}

    async def test_org_a_cannot_see_org_b_rooms(
        self, async_client: AsyncClient, db_session,
    ):
        org_a = await self._create_org_admin(db_session, "admin_a@escola.pt", "Escola A")
        org_b = await self._create_org_admin(db_session, "admin_b@escola.pt", "Escola B")
        await async_client.post(
            f"{API}/rooms/", json={"name": "Lab A", "room_type": "lab"}, headers=org_a["headers"],
        )
        resp = await async_client.get(f"{API}/rooms/", headers=org_b["headers"])
        assert resp.status_code == 200
        assert len(resp.json()) == 0

    async def test_org_a_cannot_see_org_b_teachers(
        self, async_client: AsyncClient, db_session,
    ):
        org_a = await self._create_org_admin(db_session, "admin_a@escola.pt", "Escola A")
        org_b = await self._create_org_admin(db_session, "admin_b@escola.pt", "Escola B")
        await async_client.post(
            f"{API}/teachers/", json={"name": "Prof. A", "email": "profa@escola.pt"}, headers=org_a["headers"],
        )
        resp = await async_client.get(f"{API}/teachers/", headers=org_b["headers"])
        assert resp.status_code == 200
        assert len(resp.json()) == 0

    async def test_org_a_cannot_update_org_b_subject(
        self, async_client: AsyncClient, db_session,
    ):
        org_a = await self._create_org_admin(db_session, "admin_a@escola.pt", "Escola A")
        org_b = await self._create_org_admin(db_session, "admin_b@escola.pt", "Escola B")
        sub_resp = await async_client.post(
            f"{API}/subjects/", json={"name": "Física B", "required_room_type": "lab"}, headers=org_b["headers"],
        )
        sub_id = sub_resp.json()["id"]
        resp = await async_client.patch(
            f"{API}/subjects/{sub_id}", json={"name": "Hackeado"}, headers=org_a["headers"],
        )
        assert resp.status_code == 404

    async def test_org_a_cannot_delete_org_b_course(
        self, async_client: AsyncClient, db_session,
    ):
        org_a = await self._create_org_admin(db_session, "admin_a@escola.pt", "Escola A")
        org_b = await self._create_org_admin(db_session, "admin_b@escola.pt", "Escola B")
        course_resp = await async_client.post(
            f"{API}/courses/", json={"name": "Curso B", "abbreviation": "CB"}, headers=org_b["headers"],
        )
        course_id = course_resp.json()["id"]
        resp = await async_client.delete(f"{API}/courses/{course_id}", headers=org_a["headers"])
        assert resp.status_code == 404
