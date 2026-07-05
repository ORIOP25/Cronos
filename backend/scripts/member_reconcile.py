from __future__ import annotations

import argparse
import asyncio
import json

from app.db.database import SessionLocal
from app.services import member_reconciliation_service


async def _main() -> None:
    parser = argparse.ArgumentParser(description="Run Clerk-backed member reconciliation once")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    async with SessionLocal() as db:
        result = await member_reconciliation_service.run_scheduled_reconciliation(db, limit=args.limit)
        await db.commit()
        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(_main())
