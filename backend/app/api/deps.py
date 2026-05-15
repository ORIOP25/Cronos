# Ficheiro: backend/app/api/deps.py
from typing import AsyncGenerator, Annotated
from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
import structlog

from app.db.database import SessionLocal
from app.core.clerk import verify_clerk_request
from app.services import clerk_sync
from app import models

logger = structlog.get_logger(__name__)

# --- DATABASE ---
async def get_db() -> AsyncGenerator:
    async with SessionLocal() as db:
        try:
            yield db
            await db.commit()
        except Exception:
            await db.rollback()
            raise


# --- CLERK AUTH ---

async def get_clerk_payload(request: Request) -> dict:
    state = await verify_clerk_request(request)
    if not state.is_signed_in:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return state.payload


async def get_current_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> models.User:
    payload = await get_clerk_payload(request)
    clerk_user_id = payload.get("sub")
    if not clerk_user_id:
        raise HTTPException(status_code=401, detail="No user ID in token")

    result = await db.execute(
        select(models.User).where(models.User.clerk_user_id == clerk_user_id)
    )
    user = result.scalar_one_or_none()

    if user:
        return user

    # Fallback: criar via BAPI (race condition com webhooks)
    org_id = payload.get("o", {}).get("id") if "o" in payload else None
    role = payload.get("o", {}).get("rol") if "o" in payload else None

    logger.info("Fallback síncrono ativado", clerk_user_id=clerk_user_id, clerk_org_id=org_id)

    if org_id:
        org = await clerk_sync.sync_organization_from_clerk_api(db, org_id)
        if org is None:
            logger.warning("BAPI sync_organization_from_clerk_api falhou", clerk_org_id=org_id)

    user = await clerk_sync.sync_user_from_clerk_api(db, clerk_user_id)

    if not user:
        logger.error("Fallback síncrono falhou — user não criado", clerk_user_id=clerk_user_id)
        raise HTTPException(status_code=401, detail="User not found")

    if org_id and user.organization_id is None:
        org_local_result = await db.execute(
            select(models.Organization).where(models.Organization.clerk_org_id == org_id)
        )
        org_local = org_local_result.scalar_one_or_none()
        if org_local:
            user.organization_id = org_local.id
        await db.flush()

    if role:
        user.role = clerk_sync.parse_role(role)
        await db.flush()

    logger.info("Fallback síncrono concluído", clerk_user_id=clerk_user_id, role=user.role, org_id=user.organization_id)

    if org_id and user.organization_id is None:
        org_local_result = await db.execute(
            select(models.Organization).where(models.Organization.clerk_org_id == org_id)
        )
        org_local = org_local_result.scalar_one_or_none()
        if org_local:
            user.organization_id = org_local.id
        await db.flush()

    if role:
        user.role = clerk_sync.parse_role(role)
        await db.flush()

    return user


def get_current_active_user(
    current_user: Annotated[models.User, Depends(get_current_user)],
) -> models.User:
    if not current_user.is_active:
        raise HTTPException(status_code=403, detail="Inactive user")
    return current_user


def get_current_active_admin(
    current_user: Annotated[models.User, Depends(get_current_active_user)],
) -> models.User:
    if not (current_user.is_superuser or current_user.role == models.UserRole.admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user