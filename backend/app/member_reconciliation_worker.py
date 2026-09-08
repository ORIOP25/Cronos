from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.celery_worker import celery_app
from app.core.clerk import ClerkGateway
from app.db.database import SessionLocal
from app.services.clerk_access_service import ClerkAccessService
from app.services.member_reconciliation_service import run_scheduled_reconciliation


async def _run_once() -> dict[str, object]:
    async with SessionLocal() as discovery_db:
        result = await discovery_db.execute(
            text("SELECT app_security.list_reconciliation_organization_ids()")
        )
        organization_ids = [int(value) for value in result.scalars()]

    totals: dict[str, int] = {}
    async with ClerkGateway() as clerk:
        for organization_id in organization_ids:
            async with SessionLocal.begin() as db:
                result = await run_scheduled_reconciliation(
                    db,
                    organization_id=organization_id,
                    clerk_access=ClerkAccessService(clerk),
                )
            for key, value in result.items():
                if isinstance(value, int):
                    totals[key] = totals.get(key, 0) + value
    totals["organizations_processed"] = len(organization_ids)
    return totals


@celery_app.task(name="members.run_scheduled_reconciliation")
def run_member_reconciliation_task() -> dict[str, object]:
    return asyncio.run(_run_once())
