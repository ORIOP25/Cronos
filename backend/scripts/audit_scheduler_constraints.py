"""Fail the release gate when persisted scheduler constraints are unusable."""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app import models
from app.db.database import SessionLocal
from app.scheduler.domain.constraints import SchedulerConstraintPolicy


async def audit_scheduler_constraints() -> int:
    async with SessionLocal() as db:
        rows = tuple(
            await db.scalars(
                select(models.Constraint).order_by(
                    models.Constraint.organization_id,
                    models.Constraint.id,
                )
            )
        )
    violations = SchedulerConstraintPolicy.parse(rows).configuration_violations
    if violations:
        for violation in violations:
            print(
                "INVALID scheduler constraint: "
                f"id={violation.constraint_id} type={violation.rule_type} "
                f"error={violation.message}"
            )
        return 1
    print(f"OK: {len(rows)} persisted scheduler constraints are generation-compatible.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(audit_scheduler_constraints()))
