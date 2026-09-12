from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.celery_worker import celery_app
from app.db.database import SessionLocal
from app.db.tenant import set_async_tenant_context
from app.services.scheduler_job_service import SchedulerJobService


async def _run_once() -> dict[str, int]:
    async with SessionLocal() as discovery_db:
        result = await discovery_db.execute(
            text("SELECT app_security.list_reconciliation_organization_ids()")
        )
        organization_ids = [int(value) for value in result.scalars()]

    totals: dict[str, int] = {"organizations_processed": 0}
    for organization_id in organization_ids:
        async with SessionLocal.begin() as db:
            await set_async_tenant_context(db, organization_id)
            recovered = await SchedulerJobService(db).recover_stale_jobs(organization_id)
        totals["organizations_processed"] += 1
        for key, value in recovered.items():
            totals[key] = totals.get(key, 0) + value
    return totals


@celery_app.task(name="scheduler.run_stale_job_recovery")
def run_stale_job_recovery_task() -> dict[str, int]:
    return asyncio.run(_run_once())
