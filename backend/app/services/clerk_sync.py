import asyncio
import structlog
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app import models
from app.core.clerk import get_clerk_sdk
from app.models import UserRole

logger = structlog.get_logger(__name__)


def parse_role(clerk_role: str | None) -> str:
    if not clerk_role:
        return UserRole.admin.value
    role_map = {
        "admin": UserRole.admin.value,
        "member": UserRole.teacher.value,
    }
    return role_map.get(clerk_role, UserRole.teacher.value)


async def ensure_organization_exists(
    db: AsyncSession, clerk_org_id: str, org_name: str
) -> models.Organization:
    result = await db.execute(
        select(models.Organization).where(models.Organization.clerk_org_id == clerk_org_id)
    )
    org = result.scalar_one_or_none()

    if not org:
        stmt = (
            pg_insert(models.Organization)
            .values(
                name=org_name,
                clerk_org_id=clerk_org_id,
                plan_status="active",
            )
            .on_conflict_do_nothing()
        )
        await db.execute(stmt)
        await db.flush()

        result = await db.execute(
            select(models.Organization).where(models.Organization.clerk_org_id == clerk_org_id)
        )
        org = result.scalar_one_or_none()
        if not org:
            raise RuntimeError(f"Failed to ensure org: {clerk_org_id}")

        logger.debug("Organization criada localmente", clerk_org_id=clerk_org_id)
    elif org.name != org_name:
        org.name = org_name
        await db.flush()
        logger.debug("Organization actualizada", clerk_org_id=clerk_org_id)

    return org


async def ensure_user_exists(
    db: AsyncSession,
    clerk_user_id: str,
    email: str | None = None,
    name: str | None = None,
    role: str | None = None,
    organization_id: int | None = None,
    teacher_id: int | None = None,
) -> models.User:
    result = await db.execute(
        select(models.User).where(models.User.clerk_user_id == clerk_user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        stmt = (
            pg_insert(models.User)
            .values(
                clerk_user_id=clerk_user_id,
                email=email or "",
                name=name,
                role=parse_role(role),
                organization_id=organization_id,
                teacher_id=teacher_id,
            )
            .on_conflict_do_nothing()
        )
        await db.execute(stmt)
        await db.flush()

        result = await db.execute(
            select(models.User).where(models.User.clerk_user_id == clerk_user_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise RuntimeError(f"Failed to ensure user: {clerk_user_id}")

        logger.debug("User criado localmente", clerk_user_id=clerk_user_id)
        return user

    updated = False
    if email and user.email != email:
        user.email = email
        updated = True
    if name and user.name != name:
        user.name = name
        updated = True
    if role and user.role != parse_role(role):
        user.role = parse_role(role)
        updated = True
    if organization_id is not None and user.organization_id != organization_id:
        user.organization_id = organization_id
        updated = True
    if teacher_id is not None and user.teacher_id != teacher_id:
        user.teacher_id = teacher_id
        updated = True

    if updated:
        logger.debug("User actualizado", clerk_user_id=clerk_user_id)

    return user


async def sync_user_from_clerk_api(
    db: AsyncSession, clerk_user_id: str
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

    return await ensure_user_exists(
        db=db,
        clerk_user_id=clerk_user_id,
        email=email,
        name=name,
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
