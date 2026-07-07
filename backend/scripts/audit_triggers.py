"""Audit tenant-ref trigger contracts before they become noisy CI failures."""

from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import text

from app.db.database import engine_sync


def _load_baseline_migration():
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260705_beta_baseline.py"
    )
    spec = importlib.util.spec_from_file_location("beta_baseline_migration", migration_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load migration from {migration_path}")
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def main() -> int:
    migration = _load_baseline_migration()
    errors = migration._tenant_ref_contract_errors()
    if errors:
        print("Invalid SAME_TENANT_REFS contract:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("SAME_TENANT_REFS metadata contract: ok")

    sql = """
    SELECT c.relname AS table_name, p.proname, p.prosrc
    FROM pg_trigger t
    JOIN pg_class c ON c.oid = t.tgrelid
    JOIN pg_proc p ON p.oid = t.tgfoid
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'app_security'
      AND p.proname LIKE 'validate_%_tenant_refs'
      AND NOT t.tgisinternal
    ORDER BY c.relname
    """
    column_refs = re.compile(r'NEW\."?([A-Za-z_][A-Za-z0-9_]*)"?')

    with engine_sync.connect() as conn:
        rows = conn.execute(text(sql)).mappings().all()
        if not rows:
            print("No installed tenant-ref triggers found.", file=sys.stderr)
            return 1

        failed = False
        for row in rows:
            actual_columns = set(
                conn.execute(
                    text(
                        """
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = :table_name
                        """
                    ),
                    {"table_name": row["table_name"]},
                ).scalars()
            )
            refs = set(column_refs.findall(row["prosrc"])) - {"organization_id"}
            missing = sorted(refs - actual_columns)
            if missing:
                failed = True
                print(
                    f"{row['proname']} references missing columns: {missing}",
                    file=sys.stderr,
                )
        if failed:
            return 1

    print("Installed tenant-ref trigger functions: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
