import asyncio
from dataclasses import dataclass

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.core.clerk import ClerkGateway, get_clerk_sdk
from app.core.logging import safe_exception_frames
from app.db.tenant import set_async_tenant_context
from app.services import member_reconciliation_service

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ClerkUserProfile:
    email: str | None
    name: str | None


@dataclass(frozen=True)
class ClerkOrganizationProfile:
    name: str | None
    created_by: str | None


async def fetch_clerk_organization_profile(
    clerk_org_id: str,
    gateway: ClerkGateway | None = None,
) -> ClerkOrganizationProfile | None:
    """Read the organization name and its trusted creator from one provider call.

    ``created_by`` is the Clerk user id that created the organization. It is the
    only trusted evidence of who owns the one-time Foundation setup.
    """
    sdk = gateway.sdk if gateway is not None else get_clerk_sdk()
    try:
        organization = (
            await sdk.organizations.get_async(organization_id=clerk_org_id)
            if gateway is not None
            else await asyncio.to_thread(
                lambda: sdk.organizations.get(organization_id=clerk_org_id)
            )
        )
    except Exception as exc:
        logger.error(
            "clerk_provider_organization_fetch_failed",
            clerk_org_id=clerk_org_id,
            error_type=type(exc).__name__,
            exception_frames=safe_exception_frames(exc),
        )
        return None
    return ClerkOrganizationProfile(
        name=getattr(organization, "name", None),
        created_by=getattr(organization, "created_by", None),
    )


async def fetch_clerk_user_profile(
    clerk_user_id: str,
    gateway: ClerkGateway | None = None,
) -> ClerkUserProfile | None:
    sdk = gateway.sdk if gateway is not None else get_clerk_sdk()
    try:
        clerk_user = (
            await sdk.users.get_async(user_id=clerk_user_id)
            if gateway is not None
            else await asyncio.to_thread(lambda: sdk.users.get(user_id=clerk_user_id))
        )
    except Exception as exc:
        logger.error(
            "clerk_provider_user_fetch_failed",
            clerk_user_id=clerk_user_id,
            error_type=type(exc).__name__,
            exception_frames=safe_exception_frames(exc),
        )
        return None
    email = clerk_user.email_addresses[0].email_address if clerk_user.email_addresses else None
    name = f"{clerk_user.first_name or ''} {clerk_user.last_name or ''}".strip() or None
    return ClerkUserProfile(email=email, name=name)


def _provider_status_code(error: Exception) -> int | None:
    """Read the status code exposed by the different Clerk SDK error types."""
    for source in (error, getattr(error, "response", None)):
        if source is None:
            continue
        for attribute in ("status_code", "status"):
            value = getattr(source, attribute, None)
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
    return None


async def clerk_user_exists(
    clerk_user_id: str,
    gateway: ClerkGateway | None = None,
) -> bool | None:
    """Return whether Clerk still has an identity, or ``None`` on directory outage."""
    sdk = gateway.sdk if gateway is not None else get_clerk_sdk()
    try:
        if gateway is not None:
            await sdk.users.get_async(user_id=clerk_user_id)
        else:
            await asyncio.to_thread(lambda: sdk.users.get(user_id=clerk_user_id))
    except Exception as exc:
        if _provider_status_code(exc) == 404:
            return False
        logger.error(
            "clerk_provider_identity_reconciliation_failed",
            error_type=type(exc).__name__,
            exception_frames=safe_exception_frames(exc),
        )
        return None
    return True


async def ensure_organization_exists(
    db: AsyncSession, clerk_org_id: str, org_name: str
) -> models.Organization:
    helper = await db.execute(
        text(
            """
            SELECT id
            FROM app_security.ensure_organization(:clerk_org_id, :org_name)
            """
        ),
        {"clerk_org_id": clerk_org_id, "org_name": org_name},
    )
    ensured = helper.mappings().first()
    if ensured is not None:
        await set_async_tenant_context(db, ensured["id"])
        org = await db.get(models.Organization, ensured["id"])
        if org is None:
            raise RuntimeError(f"Failed to load ensured org: {clerk_org_id}")
        return org

    raise RuntimeError(f"Failed to ensure org: {clerk_org_id}")


async def ensure_user_exists(
    db: AsyncSession,
    clerk_user_id: str,
    email: str | None = None,
    name: str | None = None,
    role: str | None = None,
    organization_id: int | None = None,
    teacher_id: int | None = None,
) -> models.User | None:
    if organization_id is None:
        helper = await db.execute(
            text(
                """
                SELECT id, organization_id
                FROM app_security.update_user_profile(
                    :clerk_user_id,
                    :email,
                    :name,
                    :role,
                    :teacher_id
                )
                """
            ),
            {
                "clerk_user_id": clerk_user_id,
                "email": email,
                "name": name,
                "role": role,
                "teacher_id": teacher_id,
            },
        )
        updated = helper.mappings().first()
        if updated is None:
            logger.info(
                "Clerk user profile ignored until membership exists",
                clerk_user_id=clerk_user_id,
            )
            return None
        await set_async_tenant_context(db, updated["organization_id"])
        user = await db.get(models.User, updated["id"])
        if user is None:
            raise RuntimeError(f"Failed to load updated user: {clerk_user_id}")
        return user

    helper = await db.execute(
        text(
            """
            SELECT id, organization_id
            FROM app_security.ensure_user(
                :clerk_user_id,
                :email,
                :name,
                :role,
                :organization_id,
                :teacher_id
            )
            """
        ),
        {
            "clerk_user_id": clerk_user_id,
            "email": email,
            "name": name,
            "role": role,
            "organization_id": organization_id,
            "teacher_id": teacher_id,
        },
    )
    ensured = helper.mappings().first()
    if ensured is None:
        logger.info(
            "Clerk user ignored until a pending membership can be reconciled",
            clerk_user_id=clerk_user_id,
            organization_id=organization_id,
        )
        return None

    await set_async_tenant_context(db, ensured["organization_id"])
    user = await db.get(models.User, ensured["id"])
    if user is None:
        raise RuntimeError(f"Failed to load ensured user: {clerk_user_id}")
    return user


async def deactivate_user_by_clerk_id(db: AsyncSession, clerk_user_id: str) -> bool:
    result = await db.execute(
        text("SELECT app_security.deactivate_user(:clerk_user_id) AS deactivated"),
        {"clerk_user_id": clerk_user_id},
    )
    return bool(result.scalar_one())


async def deactivate_organization_by_clerk_id(db: AsyncSession, clerk_org_id: str) -> bool:
    result = await db.execute(
        text("SELECT app_security.deactivate_organization(:clerk_org_id) AS deactivated"),
        {"clerk_org_id": clerk_org_id},
    )
    return bool(result.scalar_one())


async def sync_user_from_clerk_api(
    db: AsyncSession,
    clerk_user_id: str,
    organization_id: int | None = None,
    role: str | None = None,
    teacher_id: int | None = None,
) -> models.User | None:
    profile = await fetch_clerk_user_profile(clerk_user_id)
    if profile is None:
        return None

    if organization_id is not None:
        organization = await db.get(models.Organization, organization_id)
        if organization is None:
            return None
        return await member_reconciliation_service.reconcile_first_login_by_email(
            db,
            clerk_user_id=clerk_user_id,
            email=profile.email,
            name=profile.name,
            organization=organization,
            token_role=role,
        )

    return await ensure_user_exists(
        db=db,
        clerk_user_id=clerk_user_id,
        email=profile.email,
        name=profile.name,
        role=role,
        organization_id=organization_id,
        teacher_id=teacher_id,
    )
