from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

TENANT_CONTEXT_SETTING = "app.current_organization_id"
POSTGRES_INT_MAX = 2147483647


def _validate_organization_id(organization_id: int) -> int:
    if (
        not isinstance(organization_id, int)
        or organization_id < 1
        or organization_id > POSTGRES_INT_MAX
    ):
        raise ValueError("organization_id is required for tenant-scoped database access")
    return organization_id


async def set_async_tenant_context(db: AsyncSession, organization_id: int) -> None:
    organization_id = _validate_organization_id(organization_id)
    await db.execute(
        text("SELECT set_config(:setting_name, :organization_id, true)"),
        {
            "setting_name": TENANT_CONTEXT_SETTING,
            "organization_id": str(organization_id),
        },
    )


def set_sync_tenant_context(db: Session, organization_id: int) -> None:
    organization_id = _validate_organization_id(organization_id)
    db.execute(
        text("SELECT set_config(:setting_name, :organization_id, true)"),
        {
            "setting_name": TENANT_CONTEXT_SETTING,
            "organization_id": str(organization_id),
        },
    )
