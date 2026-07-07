from __future__ import annotations

import asyncio
import json
import sys

from app.db.database import SessionLocal
from app.services.e2e_clerk_state import (
    E2EClerkPreflightError,
    SdkClerkDirectory,
    config_from_env,
    prepare_e2e_clerk_state,
)


async def _main() -> int:
    try:
        config = config_from_env()
    except E2EClerkPreflightError as exc:
        print(f"E2E Clerk preflight failed: {exc}", file=sys.stderr)
        return 1

    async with SessionLocal() as db:
        try:
            result = await prepare_e2e_clerk_state(
                db,
                directory=SdkClerkDirectory(),
                config=config,
            )
            await db.commit()
        except E2EClerkPreflightError as exc:
            await db.rollback()
            print(f"E2E Clerk preflight failed: {exc}", file=sys.stderr)
            return 1
        except Exception as exc:
            await db.rollback()
            print(f"E2E Clerk state preparation failed: {exc}", file=sys.stderr)
            return 1

    print(json.dumps(result.asdict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
