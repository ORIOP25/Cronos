"""W09: /scheduler/status reports state and eligibility without writing."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app import models
from app.scheduler.infrastructure.queries import scheduler_status
from tests._support.scheduler_v1 import seed_generatable_school

MOMENT = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)


async def test_status_reports_first_generation_for_a_configured_year(db_session):
    seed = await seed_generatable_school(
        db_session, clerk_user_id="status_admin", clerk_org_id="status_org"
    )
    await db_session.commit()

    status = await scheduler_status(db_session, seed.organization.id, now_utc=MOMENT)

    assert status["configured"] is True
    assert status["school_year"]["id"] == seed.year.id
    assert status["publication_state"] == "UNPUBLISHED"
    assert status["active_version_id"] is None
    assert status["default_strategy"] == "COMPLETE_GENERATION"
    assert status["eligibility"]["can_generate"] is True
    assert status["eligibility"]["reasons"] == ["FIRST_GENERATION"]
    assert status["eligibility"]["blocker"] is None
    assert status["active_job"] is None
    assert status["pending_proposal"] is None


async def test_status_does_not_write(db_session):
    seed = await seed_generatable_school(
        db_session, clerk_user_id="status_nowrite", clerk_org_id="status_nowrite_org"
    )
    await db_session.commit()
    before = await db_session.scalar(
        select(models.SchedulerSchoolYearState.input_revision).where(
            models.SchedulerSchoolYearState.organization_id == seed.organization.id
        )
    )

    await scheduler_status(db_session, seed.organization.id, now_utc=MOMENT)
    await scheduler_status(db_session, seed.organization.id, now_utc=MOMENT)

    after = await db_session.scalar(
        select(models.SchedulerSchoolYearState.input_revision).where(
            models.SchedulerSchoolYearState.organization_id == seed.organization.id
        )
    )
    assert before == after


async def test_status_endpoint_returns_unconfigured_state(
    async_client,
    clerk_admin_headers,
):
    response = await async_client.get(
        "/api/v1/scheduler/status",
        headers=clerk_admin_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["configured"] is False
    assert payload["eligibility"]["can_generate"] is False
    assert payload["school_year"] is None

    draft_response = await async_client.get(
        "/api/v1/scheduler/drafts/current",
        headers=clerk_admin_headers,
    )
    assert draft_response.status_code == 404
