from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.celery_worker import celery_app
from app.db.database import SessionLocal
from app.db.tenant import set_async_tenant_context
from app.services.privacy_maintenance_service import PrivacyMaintenanceService


async def _run_once() -> dict[str, int]:
    async with SessionLocal() as discovery_db:
        result = await discovery_db.execute(
            text("SELECT app_security.list_reconciliation_organization_ids()")
        )
        organization_ids = [int(value) for value in result.scalars()]

    totals: dict[str, int] = {}
    async with SessionLocal.begin() as db:
        global_result = await PrivacyMaintenanceService(db).run_webhook_maintenance()
        for key, value in global_result.items():
            totals[key] = totals.get(key, 0) + value
    for organization_id in organization_ids:
        async with SessionLocal.begin() as db:
            await set_async_tenant_context(db, organization_id)
            result = await PrivacyMaintenanceService(db).run(
                organization_id=organization_id,
                include_global_webhooks=False,
            )
        for key, value in result.items():
            totals[key] = totals.get(key, 0) + value
    totals["organizations_processed"] = len(organization_ids)
    return totals


@celery_app.task(name="privacy.run_maintenance")
def run_privacy_maintenance_task() -> dict[str, int]:
    return asyncio.run(_run_once())
