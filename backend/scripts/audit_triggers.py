"""Confirm that tenant isolation uses the baseline's composite foreign keys."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from app.db.database import engine_async

UNEXPECTED_TENANT_TRIGGER_FUNCTIONS_SQL = """
SELECT p.proname
FROM pg_trigger t
JOIN pg_proc p ON p.oid = t.tgfoid
JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname = 'app_security'
  AND p.proname LIKE 'validate_%_tenant_refs'
  AND NOT t.tgisinternal
ORDER BY p.proname
"""


async def _unexpected_trigger_functions() -> list[str]:
    async with engine_async.connect() as connection:
        result = await connection.execute(text(UNEXPECTED_TENANT_TRIGGER_FUNCTIONS_SQL))
        return list(result.scalars())


def main() -> None:
    unexpected_functions = asyncio.run(_unexpected_trigger_functions())
    if unexpected_functions:
        details = "\n- ".join(unexpected_functions)
        raise SystemExit(f"Unexpected tenant-reference trigger functions found:\n- {details}")

    print("Tenant trigger audit passed: the current baseline uses composite foreign keys.")


if __name__ == "__main__":
    main()
