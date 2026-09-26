from __future__ import annotations

import asyncio

from app.celery_worker import celery_app
from app.config import settings
from app.db.database import SessionLocal
from app.scheduler.infrastructure.jobs import (
    has_queued_jobs,
    has_running_job,
    reconcile_abandoned,
    scheduler_now,
)


async def _supervise_scheduler_v1() -> dict[str, int | bool]:
    """Recover abandoned attempts and wake the executor when work is waiting."""
    async with SessionLocal() as db:
        reconciled = await reconcile_abandoned(
            db,
            stale_after_seconds=settings.SCHEDULER_V1_ABANDONED_SECONDS,
            now_utc=scheduler_now(),
        )
        queued = await has_queued_jobs(db)
        running = await has_running_job(db)
    if queued and not running:
        celery_app.send_task("scheduler.v1.run_next_job")
    return {"reconciled": reconciled, "queued": queued, "running": running}


@celery_app.task(name="scheduler.v1.supervise")
def supervise_scheduler_v1_task() -> dict[str, int | bool]:
    return asyncio.run(_supervise_scheduler_v1())
