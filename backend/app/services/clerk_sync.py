import asyncio
from datetime import datetime, timezone
import structlog
from sqlalchemy import func, select
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app import models
from app.core.clerk import get_clerk_sdk
from app.db.tenant import set_async_tenant_context
from app.models import UserRole
from app.services import member_reconciliation_service

logger = structlog.get_logger(__name__)


def parse_role(clerk_role: str | None) -> str:
    if not clerk_role:
        return UserRole.teacher.value
    role_map = {
        "admin": UserRole.admin.value,
        "member": UserRole.teacher.value,
    }
    return role_map.get(clerk_role, UserRole.teacher.value)


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
    sdk = get_clerk_sdk()
    try:
        clerk_user = await asyncio.to_thread(lambda: sdk.users.get(user_id=clerk_user_id))
    except Exception as e:
        logger.error("BAPI users.get falhou para %s: %s", clerk_user_id, e)
        return None

    email = None
    if clerk_user.email_addresses:
        email = clerk_user.email_addresses[0].email_address

    name = f"{clerk_user.first_name or ''} {clerk_user.last_name or ''}".strip() or None

    if organization_id is not None:
        organization = await db.get(models.Organization, organization_id)
        if organization is None:
            return None
        user = await member_reconciliation_service.reconcile_first_login_by_email(
            db,
            clerk_user_id=clerk_user_id,
            email=email,
            name=name,
            organization=organization,
            token_role=role,
        )
        if user is not None:
            return user

        # Bootstrap: org creator on a fresh DB (no pre-existing membership).
        # Only bootstrap when the organization has zero members yet.
        existing_count = await db.scalar(
            select(func.count(models.OrganizationMembership.id)).where(
                models.OrganizationMembership.organization_id == organization_id
            )
        )
        if existing_count and existing_count > 0:
            logger.warning(
                "Fallback: org ja tem membros, nao vou criar bootstrap",
                clerk_user_id=clerk_user_id,
                organization_id=organization_id,
            )
            return None

        logger.info(
            "Bootstrap: a criar utilizador fundador da organizacao",
            clerk_user_id=clerk_user_id,
            organization_id=organization_id,
        )

        await set_async_tenant_context(db, organization_id)

        user = models.User(
            email=email.strip().lower() if email else clerk_user_id,
            name=name,
            clerk_user_id=clerk_user_id,
            clerk_profile_name=name,
            organization_id=organization_id,
            role=models.UserRole.admin,
            is_active=True,
            last_clerk_sync_at=datetime.now(timezone.utc),
        )
        db.add(user)
        await db.flush()

        membership = models.OrganizationMembership(
            organization_id=organization_id,
            account_id=user.id,
            organization_display_name=organization.name or "Organization",
            lifecycle_status=models.MembershipLifecycleStatus.active,
            access_status=models.MembershipAccessStatus.active,
            expected_clerk_role=models.ClerkOrganizationRole.admin,
        )
        db.add(membership)
        await db.flush()

        admin_cap = models.OrganizationMembershipCapability(
            organization_membership_id=membership.id,
            capability=models.MembershipCapability.admin,
        )
        db.add(admin_cap)
        await db.flush()

        logger.info(
            "Bootstrap concluido: user + membership + admin capability criados",
            user_id=user.id,
            membership_id=membership.id,
        )
        return user

    return await ensure_user_exists(
        db=db,
        clerk_user_id=clerk_user_id,
        email=email,
        name=name,
        role=role,
        organization_id=organization_id,
        teacher_id=teacher_id,
    )


async def sync_organization_from_clerk_api(
    db: AsyncSession, clerk_org_id: str
) -> models.Organization | None:
    sdk = get_clerk_sdk()
    try:
        clerk_org = await asyncio.to_thread(lambda: sdk.organizations.get(organization_id=clerk_org_id))
    except Exception as e:
        logger.error("BAPI organizations.get falhou para %s: %s", clerk_org_id, e)
        return None

    return await ensure_organization_exists(db, clerk_org_id, clerk_org.name)
