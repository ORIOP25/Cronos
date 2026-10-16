"""Prevalidation uses the same strategy as the requested schedule operation."""

from unittest.mock import AsyncMock

import pytest

from app import models, schemas
from app.services.preflight_service import PreflightService
from tests._support.scheduler_v1 import seed_generatable_school

pytestmark = pytest.mark.postgresql


@pytest.mark.parametrize("strategy", ["COMPLETE_GENERATION", "ADAPTIVE_REPAIR"])
async def test_prevalidation_uses_requested_strategy(async_client, db_session, monkeypatch, strategy):
    seed = await seed_generatable_school(
        db_session, clerk_user_id="readiness-strategy-admin", clerk_org_id="readiness-strategy-org"
    )
    await db_session.commit()
    evaluate = AsyncMock(return_value=schemas.PreflightReport(status="READY", fingerprint=None, issues=[]))
    monkeypatch.setattr(PreflightService, "evaluate", evaluate)

    response = await async_client.get(
        "/api/v1/readiness/prevalidation",
        params={"strategy": strategy},
        headers={"Authorization": "Bearer readiness-strategy-admin"},
    )

    assert response.status_code == 200
    evaluate.assert_awaited_once_with(
        organization_id=seed.organization.id,
        school_year_id=seed.year.id,
        strategy=models.ScheduleGenerationStrategy(strategy),
    )
