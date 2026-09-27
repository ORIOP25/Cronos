from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text

from app.scheduler.domain.demand import ExecutionEntry, ModuleCredit
from app.scheduler.infrastructure.models import CurricularExecution
from app.scheduler.infrastructure.progress import record_execution
from scripts import privacy
from tests._support.db_fixtures import TestingSessionLocal, runtime_sync_test_engine
from tests._support.scheduler_v1 import seed_v1_assignment

pytestmark = pytest.mark.postgresql


@pytest.mark.asyncio
async def test_administrative_erasure_removes_append_only_evidence(db_session):
    seed = await seed_v1_assignment(
        db_session, clerk_user_id="w02_rgpd_a", clerk_org_id="w02_rgpd_org_a"
    )
    await record_execution(
        db_session,
        seed.organization.id,
        seed.year.id,
        seed.assignment.id,
        ExecutionEntry(
            "lesson:1",
            1,
            seed.membership.id,
            "Confirmed",
            (ModuleCredit(seed.module.id, 50),),
            recorded_at=datetime(2026, 9, 23, 12, tzinfo=UTC),
        ),
        planning_relevant=False,
    )
    await db_session.commit()

    with runtime_sync_test_engine.connect() as connection:
        can_delete = connection.scalar(
            text(
                "SELECT has_table_privilege('cronos_app', 'public.curricular_execution', 'DELETE')"
            )
        )
    assert can_delete is False

    result = await privacy._erase(
        seed.organization.id,
        seed.organization.clerk_org_id,
        execute=True,
        provider_deleted=True,
    )

    assert result["dry_run"] is False
    async with TestingSessionLocal() as session:
        remaining = (
            await session.scalars(
                select(CurricularExecution).where(
                    CurricularExecution.organization_id == seed.organization.id
                )
            )
        ).all()
    assert remaining == []


@pytest.mark.asyncio
async def test_dry_run_reports_counts_without_deleting(db_session):
    seed = await seed_v1_assignment(
        db_session, clerk_user_id="w02_rgpd_b", clerk_org_id="w02_rgpd_org_b"
    )
    await record_execution(
        db_session,
        seed.organization.id,
        seed.year.id,
        seed.assignment.id,
        ExecutionEntry(
            "lesson:1",
            1,
            seed.membership.id,
            "Confirmed",
            (ModuleCredit(seed.module.id, 50),),
            recorded_at=datetime(2026, 9, 23, 12, tzinfo=UTC),
        ),
        planning_relevant=False,
    )
    await db_session.commit()

    result = await privacy._erase(
        seed.organization.id,
        seed.organization.clerk_org_id,
        execute=False,
        provider_deleted=False,
    )

    assert result["dry_run"] is True
    assert result["counts"]["curricular_execution"] == 1
