from __future__ import annotations

import asyncio
import json
import sys
from datetime import date, time

from sqlalchemy.ext.asyncio import AsyncSession

from app import models, schemas
from app.db.database import SessionLocal
from app.services.e2e_clerk_state import (
    E2EClerkPreflightError,
    E2EClerkPrepResult,
    SdkClerkDirectory,
    config_from_env,
    prepare_e2e_clerk_state,
)
from app.services.foundation_service import FoundationService


def _default_foundation_data() -> schemas.FoundationDraftData:
    return schemas.FoundationDraftData(
        school_start_date=date(2025, 9, 15),
        school_hard_end_date=date(2026, 7, 31),
        repair_stability_window_days=14,
        days_of_week=[0, 1, 2, 3, 4],
        opening_time=time(8, 0),
        closing_time=time(18, 0),
        slot_duration_minutes=50,
        break_duration_minutes=0,
        lunch_window_start=time(12, 0),
        lunch_window_end=time(14, 0),
        lunch_min_duration_minutes=60,
        automatic_holidays_enabled=False,
    )


async def _ensure_default_foundation(db: AsyncSession, result: E2EClerkPrepResult) -> None:
    organization = await db.get(models.Organization, result.organization_id)
    if organization is None:
        raise RuntimeError(
            f"Organization {result.organization_id} not found after Clerk preparation"
        )
    if organization.foundation_status == models.OrganizationFoundationStatus.COMPLETED:
        return

    service = FoundationService(db)
    draft = await service.get_draft(organization.id)
    saved_draft = await service.save_draft(
        organization.id,
        schemas.FoundationDraftWrite(
            expected_version=draft.version,
            current_step=9,
            data=_default_foundation_data(),
        ),
        result.admin_membership_id,
    )
    await service.complete_foundation(
        organization.id,
        schemas.FoundationCompleteCommand(
            expected_version=saved_draft.version,
            confirmed=True,
        ),
        result.admin_membership_id,
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
            await _ensure_default_foundation(db, result)
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
