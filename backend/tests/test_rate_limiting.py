"""
TESTES DE RATE LIMITING
=======================
Valida que os endpoints com rate limits documentados respeitam
os limites configurados e devolvem 429 quando excedidos.

Documentação de referência: ENDPOINT_STANDARDS.md
"""

import pytest
from httpx import AsyncClient
from unittest.mock import patch
from uuid import uuid4

from app.config import settings
from app import models
from tests.conftest import create_teacher_profile, create_teacher_user, mock_clerk_payload

API = settings.API_V1_STR


@pytest.mark.asyncio
class TestHealthNotRateLimited:
    """Health endpoint NUNCA deve ser rate limited."""

    async def test_health_never_429(self, async_client: AsyncClient):
        for _ in range(20):
            response = await async_client.get(f"{API}/health")
            assert response.status_code in (200, 503)


@pytest.mark.asyncio
class TestGlobalRateLimit:
    """Rate limit global de 50/hour. Requer Redis funcional."""

    async def test_global_limit_returns_429(
        self, async_client: AsyncClient, admin_token_headers: dict
    ):
        r = await async_client.get(f"{API}/health")
        if r.status_code == 503:
            pytest.skip("Redis não disponível — rate limit test skipado")

        import os
        if os.environ.get("RATELIMIT_ENABLED", "").lower() == "false":
            pytest.skip("RATELIMIT_ENABLED=false — rate limit desligado nos testes")

        responses_ok = 0
        responses_429 = 0

        for _ in range(60):
            response = await async_client.get(
                f"{API}/teachers/", headers=admin_token_headers
            )
            if response.status_code == 429:
                responses_429 += 1
            elif response.status_code == 200:
                responses_ok += 1

        assert responses_429 > 0, (
            f"Esperado pelo menos um 429, mas nenhum ocorreu em 60 pedidos. "
            f"Respostas OK: {responses_ok}"
        )


@pytest.mark.asyncio
class TestTeacherHorizonRateLimit:
    """GET /schedule/me/horizon tem limite dedicado de 300/hour."""

    async def test_horizon_volume_within_dedicated_limit(
        self, async_client: AsyncClient, admin_token_headers: dict, db_session
    ):
        from app import models
        from uuid import uuid4

        settings_resp = await async_client.post(
            f"{API}/school/settings/",
            json={
                "school_start_date": "2025-09-01",
                "school_hard_end_date": "2026-07-31",
            },
            headers=admin_token_headers,
        )
        assert settings_resp.status_code == 200

        teacher = await create_teacher_profile(db_session, organization_id=1, name="Prof. RateLimit")
        await db_session.commit()
        teacher_id = teacher.id

        teacher_cid = f"ratelimit_horizon_{uuid4().hex[:8]}"
        await create_teacher_user(
            db_session,
            clerk_user_id=teacher_cid,
            email=f"ratelimit.t.{uuid4().hex[:8]}@escola.pt",
            org_id=1,
            teacher_id=teacher_id,
        )
        await db_session.commit()

        teacher_headers = {"Authorization": f"Bearer test_{teacher_cid}"}

        with patch("app.api.deps.get_clerk_payload", return_value=mock_clerk_payload(teacher_cid, None, "teacher")):
            for _ in range(55):
                response = await async_client.get(
                    f"{API}/schedule/me/horizon",
                    headers=teacher_headers,
                )
                assert response.status_code == 200, (
                    f"Rate limit do horizon não devia ter disparado com 55 pedidos. "
                    f"Status: {response.status_code}"
                )


@pytest.mark.asyncio
class TestWeekScheduleRateLimit:
    """GET /schedule/week tem limite dedicado 30/min;360/hour."""

    async def test_week_schedule_volume_within_limit(
        self, async_client: AsyncClient, admin_token_headers: dict, db_session
    ):
        from app import models
        from uuid import uuid4

        teacher = await create_teacher_profile(db_session, organization_id=1, name="Prof. Week RL")
        await db_session.commit()
        teacher_id = teacher.id

        teacher_cid = f"ratelimit_week_{uuid4().hex[:8]}"
        await create_teacher_user(
            db_session,
            clerk_user_id=teacher_cid,
            email=f"ratelimit.wk.{uuid4().hex[:8]}@escola.pt",
            org_id=1,
            teacher_id=teacher_id,
        )
        await db_session.commit()

        teacher_headers = {"Authorization": f"Bearer test_{teacher_cid}"}

        with patch("app.api.deps.get_clerk_payload", return_value=mock_clerk_payload(teacher_cid, None, "teacher")):
            for _ in range(25):
                response = await async_client.get(
                    f"{API}/schedule/week",
                    params={"week_start": "2026-04-20"},
                    headers=teacher_headers,
                )
                assert response.status_code == 200, (
                    f"Rate limit semanal não devia ter disparado com 25 pedidos. "
                    f"Status: {response.status_code}"
                )
