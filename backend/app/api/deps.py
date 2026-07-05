# Ficheiro: backend/app/api/deps.py
from typing import Annotated, AsyncGenerator

import structlog
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value
from sqlalchemy.orm import selectinload
from sqlalchemy.future import select

from app import models
from app.core.clerk import verify_clerk_request
from app.db.database import SessionLocal
from app.db.tenant import set_async_tenant_context
from app.services import clerk_sync, member_reconciliation_service

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
    # Compatibility columns are populated on the ORM object for existing service
    # signatures only. set_committed_value keeps them out of UPDATE statements.
    if token_org is not None:
        set_committed_value(user, "organization_id", token_org.id)
    set_committed_value(user, "role", None)
    set_committed_value(user, "teacher_id", None)


def _normalize_token_role(token_role: str | None) -> str | None:
    if token_role in {"admin", "org:admin"}:
        return models.ClerkOrganizationRole.admin.value
    if token_role in {"member", "teacher", "org:member"}:
        return models.ClerkOrganizationRole.member.value
    return token_role


async def _confirm_current_clerk_role(
    db: AsyncSession,
    membership: models.OrganizationMembership,
    *,
    token_role: str | None,
) -> None:
    if membership.expected_clerk_role is None:
        return
    if _normalize_token_role(token_role) == membership.expected_clerk_role.value:
        return

    provider = await member_reconciliation_service.confirm_provider_membership(db, membership)
    if provider and _normalize_token_role(provider.role) == membership.expected_clerk_role.value:
        return

    if provider and not provider.ok:
        membership.access_error_category = provider.error_category or "provider_unconfirmed"
        membership.access_error_safe_message = provider.safe_message or "Clerk membership could not be confirmed."
    else:
        membership.access_status = models.MembershipAccessStatus.sync_error
        membership.access_error_category = "provider_role_mismatch"
        membership.access_error_safe_message = "Clerk role does not match the expected local access."
    await db.flush()
    raise HTTPException(status_code=403, detail="Active organization membership required")


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
    token_org = await _get_token_organization(db, clerk_org_id)
    request.state.current_organization_id = token_org.id if token_org is not None else None
    request.state.current_clerk_org_role = token_role

    result = await db.execute(
        select(models.User).where(models.User.clerk_user_id == clerk_user_id)
    )
    user = result.scalar_one_or_none()

    if user:
        if clerk_org_id and token_org is None:
            raise HTTPException(status_code=403, detail="Organization mismatch")
        await member_reconciliation_service.reconcile_first_login(
            db,
            user=user,
            organization=token_org,
            token_role=token_role,
        )
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
    await member_reconciliation_service.reconcile_first_login(
        db,
        user=user,
        organization=token_org,
        token_role=token_role,
    )

    logger.info(
        "Fallback sincrono concluido",
        clerk_user_id=clerk_user_id,
        org_id=token_org.id,
    )
    return user


async def get_current_active_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[models.User, Depends(get_current_user)],
) -> models.User:
    organization_id = getattr(request.state, "current_organization_id", None)
    token_role = getattr(request.state, "current_clerk_org_role", None)
    if organization_id is None:
        logger.warning(
            "Missing tenant context for authenticated user",
            actor_user_id=current_user.id,
        )
        raise HTTPException(status_code=403, detail="Organization required")
    result = await db.execute(
        select(models.OrganizationMembership)
        .where(
            models.OrganizationMembership.organization_id == organization_id,
            models.OrganizationMembership.account_id == current_user.id,
            models.OrganizationMembership.lifecycle_status == models.MembershipLifecycleStatus.active,
            models.OrganizationMembership.access_status == models.MembershipAccessStatus.active,
        )
        .options(
            selectinload(models.OrganizationMembership.capabilities),
            selectinload(models.OrganizationMembership.teacher_profile),
        )
    )
    membership = result.scalar_one_or_none()
    if membership is not None:
        await _confirm_current_clerk_role(db, membership, token_role=token_role)
        capabilities = {cap.capability for cap in membership.capabilities}
        setattr(current_user, "_membership_id", membership.id)
        setattr(current_user, "_membership_capabilities", capabilities)
        if models.MembershipCapability.admin in capabilities:
            set_committed_value(current_user, "role", models.UserRole.admin)
        elif models.MembershipCapability.teacher in capabilities:
            set_committed_value(current_user, "role", models.UserRole.teacher)
        if models.MembershipCapability.teacher in capabilities and membership.teacher_profile is not None:
            set_committed_value(current_user, "teacher_id", membership.teacher_profile.id)
    else:
        raise HTTPException(status_code=403, detail="Active organization membership required")
    set_committed_value(current_user, "organization_id", organization_id)
    await set_async_tenant_context(db, organization_id)
    return current_user


def user_has_capability(
    current_user: models.User,
    capability: models.MembershipCapability,
) -> bool:
    capabilities = getattr(current_user, "_membership_capabilities", set())
    return capability in capabilities


def user_has_admin_capability(current_user: models.User) -> bool:
    return bool(
        current_user.is_superuser
        or user_has_capability(current_user, models.MembershipCapability.admin)
    )


def user_has_teacher_capability(current_user: models.User) -> bool:
    return bool(
        user_has_capability(current_user, models.MembershipCapability.teacher)
        and current_user.teacher_id is not None
    )


def get_current_active_admin(
    current_user: Annotated[models.User, Depends(get_current_active_user)],
) -> models.User:
    if not user_has_admin_capability(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user
