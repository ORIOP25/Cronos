from __future__ import annotations

import argparse
import asyncio
import json

from sqlalchemy import text

from app.db.database import SessionLocal
from app.services import member_reconciliation_service


async def _main() -> None:
    parser = argparse.ArgumentParser(description="Run Clerk-backed member reconciliation once")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--organization-id", type=int)
    args = parser.parse_args()

    if args.organization_id is not None:
        organization_ids = [args.organization_id]
    else:
        async with SessionLocal() as db:
            result = await db.execute(
                text("SELECT app_security.list_reconciliation_organization_ids()")
            )
            organization_ids = [int(value) for value in result.scalars()]

    totals: dict[str, int] = {}
    for organization_id in organization_ids:
        async with SessionLocal.begin() as db:
            result = await member_reconciliation_service.run_scheduled_reconciliation(
                db,
                organization_id=organization_id,
                limit=args.limit,
            )
        for key, value in result.items():
            if isinstance(value, int):
                totals[key] = totals.get(key, 0) + value
    totals["organizations_processed"] = len(organization_ids)
    print(json.dumps(totals, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(_main())
