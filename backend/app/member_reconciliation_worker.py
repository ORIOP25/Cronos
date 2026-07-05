from __future__ import annotations

import asyncio

from app.celery_worker import celery_app
from app.db.database import SessionLocal, engine_async
from app.services.member_reconciliation_service import run_scheduled_reconciliation


async def _run_once() -> dict[str, object]:
    try:
        async with SessionLocal() as db:
            result = await run_scheduled_reconciliation(db)
            await db.commit()
            return result
    finally:
        await engine_async.dispose()


@celery_app.task(name="members.run_scheduled_reconciliation")
def run_member_reconciliation_task() -> dict[str, object]:
    return asyncio.run(_run_once())
