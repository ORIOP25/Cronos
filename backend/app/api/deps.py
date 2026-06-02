# Ficheiro: backend/app/api/deps.py
from typing import Annotated, AsyncGenerator

import structlog
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app import models
from app.core.clerk import verify_clerk_request
from app.db.database import SessionLocal
from app.db.tenant import set_async_tenant_context
from app.services import clerk_sync

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


async def _get_token_organization(
    db: AsyncSession,
    clerk_org_id: str | None,
) -> models.Organization | None:
    if not clerk_org_id:
        return None

    result = await db.execute(
        select(models.Organization).where(models.Organization.clerk_org_id == clerk_org_id)
    )
    org = result.scalar_one_or_none()
    if org is not None:
        return org

    org = await clerk_sync.sync_organization_from_clerk_api(db, clerk_org_id)
    if org is None:
        logger.warning("BAPI sync_organization_from_clerk_api falhou", clerk_org_id=clerk_org_id)
    return org


async def _apply_token_membership(
    db: AsyncSession,
    user: models.User,
    token_org: models.Organization | None,
    token_role: str | None,
    clerk_user_id: str,
) -> None:
    if token_org is not None:
        if user.organization_id is None:
            user.organization_id = token_org.id
            await db.flush()
        elif user.organization_id != token_org.id:
            logger.warning(
                "Token Clerk com organizacao diferente da organizacao local do user",
                clerk_user_id=clerk_user_id,
                user_organization_id=user.organization_id,
                token_organization_id=token_org.id,
                token_clerk_org_id=token_org.clerk_org_id,
            )
            raise HTTPException(status_code=403, detail="Organization mismatch")

    if token_role:
        parsed_role = clerk_sync.parse_role(token_role)
        if user.role != parsed_role:
            user.role = parsed_role
            await db.flush()


async def get_current_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> models.User:
    payload = await get_clerk_payload(request)
    clerk_user_id = payload.get("sub")
    if not clerk_user_id:
        raise HTTPException(status_code=401, detail="No user ID in token")

    clerk_org_id = payload.get("o", {}).get("id") if "o" in payload else None
    token_role = payload.get("o", {}).get("rol") if "o" in payload else None
    if clerk_org_id:
        try:
            async with db.begin_nested():
                auth_context = await db.execute(
                    text(
                        """
                        SELECT user_id, organization_id, role, is_active
                        FROM app_security.resolve_auth_context(:clerk_user_id, :clerk_org_id)
                        """
                    ),
                    {"clerk_user_id": clerk_user_id, "clerk_org_id": clerk_org_id},
                )
                resolved = auth_context.mappings().first()
        except SQLAlchemyError:
            logger.warning(
                "Auth context resolver unavailable; falling back to Clerk sync",
                clerk_user_id=clerk_user_id,
                clerk_org_id=clerk_org_id,
            )
            resolved = None
        if resolved is not None:
            try:
                async with db.begin_nested():
                    await set_async_tenant_context(db, resolved["organization_id"])
            except (SQLAlchemyError, ValueError):
                logger.warning(
                    "Failed to apply tenant context from resolver",
                    clerk_user_id=clerk_user_id,
                    organization_id=resolved["organization_id"],
                )
                resolved = None
        if resolved is not None:
            result = await db.execute(
                select(models.User).where(models.User.id == resolved["user_id"])
            )
            user = result.scalar_one_or_none()
            if user is None:
                raise HTTPException(status_code=403, detail="Organization mismatch")
            if token_role:
                parsed_role = clerk_sync.parse_role(token_role)
                if user.role != parsed_role:
                    user.role = parsed_role
                    await db.flush()
            return user

    token_org = await _get_token_organization(db, clerk_org_id)

    result = await db.execute(
        select(models.User).where(models.User.clerk_user_id == clerk_user_id)
    )
    user = result.scalar_one_or_none()

    if user:
        if clerk_org_id and token_org is None and user.organization_id is not None:
            raise HTTPException(status_code=403, detail="Organization mismatch")
        await _apply_token_membership(db, user, token_org, token_role, clerk_user_id)
        return user

    # Fallback: criar via BAPI (race condition com webhooks)
    logger.info("Fallback sincrono ativado", clerk_user_id=clerk_user_id, clerk_org_id=clerk_org_id)
    if token_org is None:
        if clerk_org_id:
            raise HTTPException(status_code=403, detail="Organization mismatch")
        raise HTTPException(status_code=403, detail="Organization required")

    user = await clerk_sync.sync_user_from_clerk_api(
        db,
        clerk_user_id,
        organization_id=token_org.id if token_org is not None else None,
        role=token_role,
    )

    if not user:
        logger.error("Fallback sincrono falhou - user nao criado", clerk_user_id=clerk_user_id)
        raise HTTPException(status_code=401, detail="User not found")

    if clerk_org_id and token_org is None:
        raise HTTPException(status_code=403, detail="Organization mismatch")

    await _apply_token_membership(db, user, token_org, token_role, clerk_user_id)

    logger.info(
        "Fallback sincrono concluido",
        clerk_user_id=clerk_user_id,
        role=user.role,
        org_id=user.organization_id,
    )
    return user


async def get_current_active_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[models.User, Depends(get_current_user)],
) -> models.User:
    if not current_user.is_active:
        raise HTTPException(status_code=403, detail="Inactive user")
    if current_user.organization_id is None:
        logger.warning(
            "Missing tenant context for authenticated user",
            actor_user_id=current_user.id,
        )
        raise HTTPException(status_code=403, detail="Organization required")
    await set_async_tenant_context(db, current_user.organization_id)
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
