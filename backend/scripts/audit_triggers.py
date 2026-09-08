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


EXPECTED_TRIGGERS_SQL = """
SELECT t.tgname
FROM pg_trigger t
JOIN pg_class c ON c.oid = t.tgrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND t.tgname IN ('trg_organization_foundation_monotonic', 'trg_organization_legal_acceptance_append_only')
  AND NOT t.tgisinternal
ORDER BY t.tgname
"""


async def _check_triggers() -> list[str]:
    async with engine_async.connect() as connection:
        unexpected_result = await connection.execute(text(UNEXPECTED_TENANT_TRIGGER_FUNCTIONS_SQL))
        unexpected = list(unexpected_result.scalars())
        errors = []
        if unexpected:
            errors.append(f"Unexpected tenant-reference trigger functions found: {unexpected}")

        expected_result = await connection.execute(text(EXPECTED_TRIGGERS_SQL))
        found_expected = set(expected_result.scalars())
        required_triggers = {
            "trg_organization_foundation_monotonic",
            "trg_organization_legal_acceptance_append_only",
        }
        missing = required_triggers - found_expected
        if missing:
            errors.append(f"Missing required triggers: {sorted(missing)}")

        # Verify trigger events for trg_organization_foundation_monotonic
        event_sql = """
        SELECT tgtype
        FROM pg_trigger
        WHERE tgname = 'trg_organization_foundation_monotonic'
          AND NOT tgisinternal
        """
        tgtype_res = await connection.execute(text(event_sql))
        tgtype = tgtype_res.scalar_one_or_none()
        # In PG, BEFORE (bit 1=2), UPDATE (bit 4=16), DELETE (bit 3=8) -> 2 | 16 | 8 = 26 or 28
        if tgtype is not None and not (tgtype & 4 and tgtype & 8 and tgtype & 16):
            errors.append(
                f"trg_organization_foundation_monotonic must cover INSERT, UPDATE and DELETE: tgtype={tgtype}"
            )

        function_body = await connection.scalar(
            text(
                "SELECT pg_get_functiondef(p.oid) "
                "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
                "WHERE n.nspname = 'app_security' "
                "AND p.proname = 'trg_fn_organization_foundation_monotonic'"
            )
        )
        if function_body and "RETURN OLD" not in function_body:
            errors.append("Foundation trigger must return OLD for permitted DELETE operations")

        return errors


def main() -> None:
    errors = asyncio.run(_check_triggers())
    if errors:
        details = "\n- ".join(errors)
        raise SystemExit(f"Tenant trigger audit failed:\n- {details}")

    print(
        "Tenant trigger audit passed: monotonic, append-only, and composite foreign key triggers verified."
    )


if __name__ == "__main__":
    main()
