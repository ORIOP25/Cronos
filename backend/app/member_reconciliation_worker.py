from __future__ import annotations

import asyncio

from app.celery_worker import celery_app
from app.core.clerk import ClerkGateway
from app.db.database import SessionLocal
from app.services.clerk_access_service import ClerkAccessService
from app.services.member_reconciliation_service import run_scheduled_reconciliation


async def _run_once() -> dict[str, object]:
    async with ClerkGateway() as clerk:
        async with SessionLocal.begin() as db:
            return await run_scheduled_reconciliation(
                db,
                clerk_access=ClerkAccessService(clerk),
            )


@celery_app.task(name="members.run_scheduled_reconciliation")
def run_member_reconciliation_task() -> dict[str, object]:
    return asyncio.run(_run_once())
