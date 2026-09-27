import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, text

from app.config import settings
from app.scheduler.domain.debt import DebtOrigin
from app.scheduler.domain.demand import ExecutionEntry, ModuleCredit
from app.scheduler.infrastructure.progress import record_debt, record_execution
from scripts.reset_test_data import reset_test_data
from tests._support.scheduler_v1 import add_version, seed_v1_assignment

pytestmark = pytest.mark.postgresql


def _migration_sync_url() -> str:
    return os.environ.get("MIGRATION_DATABASE_URL") or str(settings.MIGRATION_DATABASE_URL or "")


def _count_sync(table: str) -> int:
    engine = create_engine(_migration_sync_url())
    try:
        with engine.connect() as connection:
            connection.execute(text("SET LOCAL row_security = off"))
            return int(connection.scalar(text(f'SELECT count(*) FROM public."{table}"')))
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_reset_is_repeatable_and_empties_the_named_targets(db_session):
    seed = await seed_v1_assignment(
        db_session, clerk_user_id="w02_reset_a", clerk_org_id="w02_reset_org_a"
    )
    await add_version(db_session, seed, status="CANDIDATE")
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

    first = reset_test_data(_migration_sync_url(), ("scheduler-v1",))
    second = reset_test_data(_migration_sync_url(), ("scheduler-v1",))

    assert first["rows_before"]["curricular_execution"] == 1
    assert _count_sync("curricular_execution") == 0
    assert _count_sync("curricular_assignment") == 0
    assert _count_sync("scheduler_lesson_v1") == 0
    assert second["tables"] == first["tables"]


def test_reset_rejects_unknown_targets_and_wrong_databases():
    with pytest.raises(ValueError, match="Unknown reset targets"):
        reset_test_data(_migration_sync_url(), ("not-a-target",))
    with pytest.raises(ValueError, match="Refusing to reset"):
        reset_test_data("postgresql://user:test@127.0.0.1:5432/production", ("scheduler-v1",))


@pytest.mark.asyncio
async def test_evidence_reset_keeps_curriculum_intact(db_session):
    seed = await seed_v1_assignment(
        db_session, clerk_user_id="w02_reset_b", clerk_org_id="w02_reset_org_b"
    )
    await record_debt(
        db_session,
        seed.organization.id,
        seed.year.id,
        seed.assignment.id,
        DebtOrigin(
            "occurrence:1",
            1,
            seed.year.start_date,
            20,
            seed.membership.id,
            "Missed lesson",
            datetime(2026, 9, 23, 12, tzinfo=UTC),
        ),
    )
    await db_session.commit()

    reset_test_data(_migration_sync_url(), ("evidence",))

    assert _count_sync("curricular_debt") == 0
    assert _count_sync("curricular_assignment") == 1
    assert _count_sync("curricular_requirement") == 1
