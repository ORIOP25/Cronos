"""Seed runner for Alpha V1 operational scenarios (Step 6).

Usage:
    python seed_data_operational.py
"""

from __future__ import annotations

import sys

from app.db.database import Base, SessionLocalSync, engine_sync
from app.services.operational_seed_service import seed_operational_scenarios_sync


def recreate_schema() -> None:
    """Recreate full schema before applying deterministic operational seed."""
    print("\n1/2 Recreating schema...")
    Base.metadata.drop_all(bind=engine_sync)
    Base.metadata.create_all(bind=engine_sync)
    print("[OK] Schema recreated")


def run_seed() -> None:
    """Populate operational scenarios and print deterministic summary."""
    print("\n2/2 Seeding operational scenarios...")
    db = SessionLocalSync()
    try:
        payload = seed_operational_scenarios_sync(db)
        signature = payload["signature"]

        print("[OK] Operational seed completed")
        print("\nSummary:")
        print(f"  profile: {signature['profile']}")
        print(f"  reference_date: {signature['reference_date']}")
        print(f"  organization_count: {signature['organization_count']}")
        print(f"  scenario_codes: {', '.join(signature['scenario_codes'])}")
        for key, value in signature["totals"].items():
            print(f"  {key}: {value}")
    except Exception as exc:
        db.rollback()
        print(f"[ERROR] Operational seed failed: {exc}")
        raise
    finally:
        db.close()


def main() -> None:
    print("=" * 64)
    print("  Alpha V1 - Step 6 Operational Seed")
    print("=" * 64)

    try:
        recreate_schema()
        run_seed()
    except Exception:
        sys.exit(1)


if __name__ == "__main__":
    main()
