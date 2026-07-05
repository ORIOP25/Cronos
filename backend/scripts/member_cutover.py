from __future__ import annotations

import argparse
import asyncio
import json

from app.config import settings
from app.db.database import SessionLocal
from app.services import member_cutover_service


async def _main() -> None:
    parser = argparse.ArgumentParser(description="Clerk-backed Equipa member cutover checks")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("dry-run", help="Print cutover report and blockers")
    bootstrap = subparsers.add_parser("bootstrap", help="Bootstrap legacy memberships")
    bootstrap.add_argument("--apply", action="store_true", help="Persist bootstrap changes")
    args = parser.parse_args()

    async with SessionLocal() as db:
        if args.command == "dry-run":
            report = await member_cutover_service.generate_cutover_report(
                db,
                webhook_secret_configured=bool(settings.CLERK_WEBHOOK_SECRET),
            )
            print(json.dumps({"report": report.to_dict(), "blockers": report.blockers}, indent=2, default=str))
        elif args.command == "bootstrap":
            result = await member_cutover_service.bootstrap_legacy_memberships(db, apply=args.apply)
            if args.apply:
                await db.commit()
            else:
                await db.rollback()
            print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(_main())
