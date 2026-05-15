"""
TESTES PARAMETRIZADOS — CONTRATOS DE ERRO
=========================================
Demonstra o padrão de parametrização para contratos de erro repetitivos,
reduzindo duplicação e documentando cobertura de forma explícita.

Padrão a adotar para novos testes.
"""

import pytest
from httpx import AsyncClient
from unittest.mock import patch
from uuid import uuid4

from app import models
from app.config import settings
from tests.conftest import mock_clerk_payload
API = settings.API_V1_STR


async def _make_teacher_headers(db_session, org_id, teacher_id, role=models.UserRole.teacher):
    cid = f"param_{uuid4().hex[:8]}"
    email = f"param.{uuid4().hex[:8]}@test.pt"
    user = models.User(
        email=email,
        clerk_user_id=cid,
        is_active=True, role=role,
        organization_id=org_id, teacher_id=teacher_id,
    )
    db_session.add(user)
    await db_session.commit()
    return {"Authorization": f"Bearer test_{cid}"}, cid


@pytest.mark.asyncio
class TestTeacherAvailabilityErrorContracts:
    """GET /teachers/me/availability — contratos de erro parametrizados."""

    @pytest.mark.parametrize("scenario,expected_status,expected_message", [
        pytest.param(
            "admin_access",
            403,
            None,
            id="admin bloqueado do self-service",
        ),
        pytest.param(
            "teacher_without_profile",
            403,
            None,
            id="professor sem perfil associado",
        ),
        pytest.param(
            "cross_tenant_profile",
            404,
            None,
            id="perfil de org diferente bloqueado",
        ),
    ])
    async def test_me_availability_error_contracts(
        self,
        scenario: str,
        expected_status: int,
        expected_message: str | None,
        async_client: AsyncClient,
        admin_token_headers: dict,
        db_session,
    ):
        if scenario == "admin_access":
            resp = await async_client.get(
                f"{API}/teachers/me/availability", headers=admin_token_headers
            )
            assert resp.status_code == expected_status

        elif scenario == "teacher_without_profile":
            headers, cid = await _make_teacher_headers(db_session, 1, None)
            with patch("app.api.deps.get_clerk_payload", return_value=mock_clerk_payload(cid, None, "teacher")):
                resp = await async_client.get(
                    f"{API}/teachers/me/availability", headers=headers
                )
            assert resp.status_code == expected_status

        elif scenario == "cross_tenant_profile":
            org_a = models.Organization(name=f"Param Org A {uuid4().hex[:6]}", plan_status="active")
            org_b = models.Organization(name=f"Param Org B {uuid4().hex[:6]}", plan_status="active")
            db_session.add_all([org_a, org_b])
            await db_session.flush()
            teacher_a = models.Teacher(name="Prof. Param A", organization_id=org_a.id)
            db_session.add(teacher_a)
            await db_session.commit()

            headers, cid = await _make_teacher_headers(db_session, org_b.id, teacher_a.id)
            with patch("app.api.deps.get_clerk_payload", return_value=mock_clerk_payload(cid, None, "teacher")):
                resp = await async_client.get(
                    f"{API}/teachers/me/availability", headers=headers
                )
            assert resp.status_code == expected_status


@pytest.mark.asyncio
class TestTeacherHorizonErrorContracts:
    """GET /schedule/me/horizon — contratos de erro parametrizados."""

    @pytest.mark.parametrize("scenario,expected_status", [
        pytest.param("admin_access", 403, id="admin bloqueado"),
        pytest.param("teacher_without_profile", 403, id="sem perfil"),
        pytest.param("teacher_without_settings", 404, id="sem settings na org"),
    ])
    async def test_me_horizon_error_contracts(
        self,
        scenario: str,
        expected_status: int,
        async_client: AsyncClient,
        admin_token_headers: dict,
        db_session,
    ):
        if scenario == "admin_access":
            resp = await async_client.get(
                f"{API}/schedule/me/horizon", headers=admin_token_headers
            )
            assert resp.status_code == expected_status

        elif scenario == "teacher_without_profile":
            headers, cid = await _make_teacher_headers(db_session, 1, None)
            with patch("app.api.deps.get_clerk_payload", return_value=mock_clerk_payload(cid, None, "teacher")):
                resp = await async_client.get(
                    f"{API}/schedule/me/horizon", headers=headers
                )
            assert resp.status_code == expected_status

        elif scenario == "teacher_without_settings":
            org = models.Organization(
                name=f"No Settings Param {uuid4().hex[:6]}", plan_status="active"
            )
            db_session.add(org)
            await db_session.flush()
            teacher = models.Teacher(
                name="Prof. No Settings", organization_id=org.id
            )
            db_session.add(teacher)
            await db_session.commit()

            headers, cid = await _make_teacher_headers(db_session, org.id, teacher.id)
            with patch("app.api.deps.get_clerk_payload", return_value=mock_clerk_payload(cid, None, "teacher")):
                resp = await async_client.get(
                    f"{API}/schedule/me/horizon", headers=headers
                )
            assert resp.status_code == expected_status


@pytest.mark.asyncio
class TestWeekScheduleErrorContracts:
    """GET /schedule/week — contratos de erro parametrizados."""

    @pytest.mark.parametrize("scenario,query_params,expected_status", [
        pytest.param(
            "missing_week_start", {}, 422,
            id="sem week_start",
        ),
        pytest.param(
            "invalid_week_start", {"week_start": "not-a-date"}, 422,
            id="week_start inválido",
        ),
        pytest.param(
            "teacher_uses_class_id",
            {"week_start": "2026-04-20", "class_id": 1},
            403,
            id="professor não pode usar class_id",
        ),
        pytest.param(
            "teacher_uses_other_teacher_id",
            {"week_start": "2026-04-20", "teacher_id": 999},
            403,
            id="professor não pode ver outro teacher",
        ),
    ])
    async def test_week_schedule_error_contracts(
        self,
        scenario: str,
        query_params: dict,
        expected_status: int,
        async_client: AsyncClient,
        admin_token_headers: dict,
        db_session,
    ):
        teacher_resp = await async_client.post(
            f"{API}/teachers/",
            json={"name": f"Prof. Week Param {scenario}", "email": f"week.param.{uuid4().hex[:8]}@test.pt"},
            headers=admin_token_headers,
        )
        assert teacher_resp.status_code == 200
        teacher_id = teacher_resp.json()["id"]

        headers, cid = await _make_teacher_headers(db_session, 1, teacher_id)
        with patch("app.api.deps.get_clerk_payload", return_value=mock_clerk_payload(cid, None, "teacher")):
            resp = await async_client.get(
                f"{API}/schedule/week", params=query_params, headers=headers
            )
        assert resp.status_code == expected_status
