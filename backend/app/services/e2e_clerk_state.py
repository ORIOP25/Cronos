from __future__ import annotations

import asyncio
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.core.clerk import get_clerk_sdk
from app.db.tenant import set_async_tenant_context


class E2EClerkPreflightError(RuntimeError):
    """Raised when real Clerk test state is not safe to mirror locally."""


@dataclass(frozen=True, slots=True)
class ClerkUser:
    id: str
    email: str
    name: str | None = None


@dataclass(frozen=True, slots=True)
class ClerkOrganization:
    id: str
    name: str


@dataclass(frozen=True, slots=True)
class ClerkOrganizationMembership:
    id: str | None
    organization_id: str
    user_id: str
    role: str | None


class ClerkDirectory(Protocol):
    async def get_user_by_email(self, email: str) -> ClerkUser | None: ...

    async def get_organization(self, organization_id: str) -> ClerkOrganization | None: ...

    async def list_user_organization_memberships(
        self,
        user_id: str,
    ) -> list[ClerkOrganizationMembership]: ...

    async def get_organization_membership(
        self,
        organization_id: str,
        user_id: str,
    ) -> ClerkOrganizationMembership | None: ...


@dataclass(frozen=True, slots=True)
class E2EClerkPrepConfig:
    admin_email: str
    teacher_email: str
    clerk_org_id: str | None = None


@dataclass(frozen=True, slots=True)
class E2EClerkPrepResult:
    clerk_org_id: str
    organization_id: int
    admin_user_id: int
    admin_membership_id: int
    teacher_user_id: int
    teacher_membership_id: int
    teacher_id: int

    def asdict(self) -> dict[str, int | str]:
        return asdict(self)


def config_from_env(env: os._Environ[str] | dict[str, str] = os.environ) -> E2EClerkPrepConfig:
    missing = [
        name
        for name in [
            "CLERK_SECRET_KEY",
            "E2E_CLERK_ADMIN_EMAIL",
            "E2E_CLERK_TEACHER_EMAIL",
            "E2E_CLERK_ORG_ID",
        ]
        if not env.get(name)
    ]
    if missing:
        raise E2EClerkPreflightError(
            "Missing required Clerk E2E configuration: "
            + ", ".join(missing)
            + ". Set these as GitHub secrets before running real E2E."
        )
    unsafe_emails = [
        name
        for name in ["E2E_CLERK_ADMIN_EMAIL", "E2E_CLERK_TEACHER_EMAIL"]
        if not env[name].strip().lower().endswith("+clerk_test@example.com")
    ]
    if unsafe_emails:
        raise E2EClerkPreflightError(
            "Real-person emails are forbidden in Clerk E2E configuration: "
            + ", ".join(unsafe_emails)
            + ". Use dedicated Clerk reserved test users."
        )
    return E2EClerkPrepConfig(
        admin_email=env["E2E_CLERK_ADMIN_EMAIL"],
        teacher_email=env["E2E_CLERK_TEACHER_EMAIL"],
        clerk_org_id=env["E2E_CLERK_ORG_ID"],
    )


def _items(raw) -> list:
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    data = getattr(raw, "data", None)
    if data is not None:
        return list(data)
    return [raw]


def _email_address(raw) -> str | None:
    return getattr(raw, "email_address", None)


def _primary_email(raw_user) -> str | None:
    addresses = list(getattr(raw_user, "email_addresses", None) or [])
    if not addresses:
        return None
    primary_id = getattr(raw_user, "primary_email_address_id", None)
    primary = next((item for item in addresses if getattr(item, "id", None) == primary_id), None)
    return _email_address(primary or addresses[0])


def _user_name(raw_user) -> str | None:
    full_name = getattr(raw_user, "full_name", None)
    if full_name:
        return full_name
    parts = [getattr(raw_user, "first_name", None), getattr(raw_user, "last_name", None)]
    return " ".join(part for part in parts if part) or None


def _organization_id(raw_membership) -> str | None:
    organization_id = getattr(raw_membership, "organization_id", None)
    if organization_id:
        return organization_id
    organization = getattr(raw_membership, "organization", None)
    return getattr(organization, "id", None)


def _membership_user_id(raw_membership) -> str | None:
    user_id = getattr(raw_membership, "user_id", None)
    if user_id:
        return user_id
    public_user_data = getattr(raw_membership, "public_user_data", None)
    return getattr(public_user_data, "user_id", None)


def _to_clerk_membership(raw_membership, *, fallback_user_id: str | None = None) -> ClerkOrganizationMembership | None:
    organization_id = _organization_id(raw_membership)
    user_id = _membership_user_id(raw_membership) or fallback_user_id
    if not organization_id or not user_id:
        return None
    return ClerkOrganizationMembership(
        id=getattr(raw_membership, "id", None),
        organization_id=organization_id,
        user_id=user_id,
        role=getattr(raw_membership, "role", None),
    )


class SdkClerkDirectory:
    """Adapter around clerk-backend-api with only the reads CI prep needs."""

    def __init__(self, sdk=None) -> None:
        self._sdk = sdk or get_clerk_sdk()

    async def get_user_by_email(self, email: str) -> ClerkUser | None:
        normalized = email.strip().lower()

        def _list_users():
            try:
                return self._sdk.users.list(
                    request={"email_address": [normalized], "limit": 10}
                )
            except TypeError:
                return self._sdk.users.list(email_address=[normalized], limit=10)

        try:
            raw_users = _items(await asyncio.to_thread(_list_users))
        except Exception as exc:
            raise E2EClerkPreflightError(
                f"Could not read Clerk user {email!r}. Check CLERK_SECRET_KEY and Clerk API availability."
            ) from exc
        matches = []
        for raw_user in raw_users:
            addresses = list(getattr(raw_user, "email_addresses", None) or [])
            user_emails = {_email_address(item).strip().lower() for item in addresses if _email_address(item)}
            primary = _primary_email(raw_user)
            if primary:
                user_emails.add(primary.strip().lower())
            if normalized in user_emails:
                matches.append(raw_user)

        if not matches:
            return None
        if len(matches) > 1:
            raise E2EClerkPreflightError(
                f"Clerk returned multiple users for {email!r}; E2E user emails must be unique."
            )

        raw_user = matches[0]
        primary_email = _primary_email(raw_user) or normalized
        return ClerkUser(
            id=getattr(raw_user, "id"),
            email=primary_email.strip().lower(),
            name=_user_name(raw_user),
        )

    async def get_organization(self, organization_id: str) -> ClerkOrganization | None:
        try:
            raw_org = await asyncio.to_thread(
                lambda: self._sdk.organizations.get(organization_id=organization_id)
            )
        except Exception:
            return None
        return ClerkOrganization(
            id=getattr(raw_org, "id", organization_id),
            name=getattr(raw_org, "name", None) or "E2E Organization",
        )

    async def list_user_organization_memberships(
        self,
        user_id: str,
    ) -> list[ClerkOrganizationMembership]:
        try:
            raw = await asyncio.to_thread(
                lambda: self._sdk.users.get_organization_memberships(user_id=user_id, limit=100)
            )
        except Exception as exc:
            raise E2EClerkPreflightError(
                f"Could not list Clerk organization memberships for user {user_id!r}."
            ) from exc
        memberships = [
            _to_clerk_membership(item, fallback_user_id=user_id)
            for item in _items(raw)
        ]
        return [membership for membership in memberships if membership is not None]

    async def get_organization_membership(
        self,
        organization_id: str,
        user_id: str,
    ) -> ClerkOrganizationMembership | None:
        try:
            raw = await asyncio.to_thread(
                lambda: self._sdk.organization_memberships.list(
                    organization_id=organization_id,
                    user_id=[user_id],
                    limit=10,
                )
            )
        except Exception as exc:
            raise E2EClerkPreflightError(
                f"Could not read Clerk organization membership for user {user_id!r} in org {organization_id!r}."
            ) from exc
        memberships = [
            _to_clerk_membership(item, fallback_user_id=user_id)
            for item in _items(raw)
        ]
        return next((membership for membership in memberships if membership is not None), None)


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _normalize_clerk_role(role: str | None) -> str | None:
    if role in {"admin", "org:admin"}:
        return models.ClerkOrganizationRole.admin.value
    if role in {"member", "teacher", "org:member"}:
        return models.ClerkOrganizationRole.member.value
    return role


async def _required_clerk_user(directory: ClerkDirectory, email: str, label: str) -> ClerkUser:
    user = await directory.get_user_by_email(email)
    if user is None:
        raise E2EClerkPreflightError(
            f"Clerk {label} user {email!r} was not found. Check E2E_CLERK_{label.upper()}_EMAIL."
        )
    return user


async def _resolve_clerk_org_id(
    directory: ClerkDirectory,
    admin: ClerkUser,
    configured_org_id: str | None,
) -> str:
    if configured_org_id:
        return configured_org_id

    memberships = await directory.list_user_organization_memberships(admin.id)
    org_ids = sorted({membership.organization_id for membership in memberships})
    if len(org_ids) != 1:
        raise E2EClerkPreflightError(
            "E2E_CLERK_ORG_ID is required unless the admin test account belongs to exactly one "
            f"Clerk organization; found {len(org_ids)} for {admin.email!r}: {', '.join(org_ids) or 'none'}."
        )
    return org_ids[0]


async def _required_membership(
    directory: ClerkDirectory,
    *,
    organization_id: str,
    user: ClerkUser,
    expected_role: models.ClerkOrganizationRole,
    label: str,
) -> ClerkOrganizationMembership:
    membership = await directory.get_organization_membership(organization_id, user.id)
    if membership is None:
        raise E2EClerkPreflightError(
            f"Clerk {label} user {user.email!r} is not a member of organization {organization_id!r}."
        )
    actual = _normalize_clerk_role(membership.role)
    if actual != expected_role.value:
        raise E2EClerkPreflightError(
            f"Clerk {label} user {user.email!r} must have role {expected_role.value}; found {membership.role!r}."
        )
    return membership


async def _upsert_organization(db: AsyncSession, clerk_org: ClerkOrganization) -> models.Organization:
    organization = await db.scalar(
        select(models.Organization).where(models.Organization.clerk_org_id == clerk_org.id)
    )
    if organization is None:
        organization = models.Organization(
            name=clerk_org.name,
            clerk_org_id=clerk_org.id,
            plan_status=models.OrganizationPlanStatus.active,
        )
        db.add(organization)
        await db.flush()
    else:
        organization.name = clerk_org.name
        organization.plan_status = models.OrganizationPlanStatus.active
    return organization


async def _upsert_user(
    db: AsyncSession,
    *,
    clerk_user: ClerkUser,
    organization_id: int,
    role: models.UserRole,
) -> models.User:
    normalized_email = _normalize_email(clerk_user.email)
    user = await db.scalar(
        select(models.User).where(models.User.clerk_user_id == clerk_user.id)
    )
    if user is None:
        user = await db.scalar(select(models.User).where(models.User.email == normalized_email))
    if user is None:
        user = models.User(email=normalized_email)
        db.add(user)
        await db.flush()

    user.clerk_user_id = clerk_user.id
    user.email = normalized_email
    user.name = clerk_user.name or user.name or normalized_email
    user.clerk_profile_name = clerk_user.name
    user.organization_id = organization_id
    user.role = role
    user.is_active = True
    user.last_clerk_sync_at = datetime.now(timezone.utc)
    return user


async def _sync_capabilities(
    db: AsyncSession,
    membership: models.OrganizationMembership,
    desired: set[models.MembershipCapability],
) -> None:
    existing_rows = (
        await db.scalars(
            select(models.OrganizationMembershipCapability).where(
                models.OrganizationMembershipCapability.organization_membership_id == membership.id
            )
        )
    ).all()
    existing = {row.capability for row in existing_rows}
    for row in existing_rows:
        if row.capability not in desired:
            await db.delete(row)
    for capability in desired - existing:
        db.add(
            models.OrganizationMembershipCapability(
                organization_membership_id=membership.id,
                capability=capability,
            )
        )
    await db.flush()


async def _upsert_membership(
    db: AsyncSession,
    *,
    organization: models.Organization,
    user: models.User,
    display_name: str,
    expected_role: models.ClerkOrganizationRole,
    clerk_membership: ClerkOrganizationMembership,
    capability: models.MembershipCapability,
) -> models.OrganizationMembership:
    membership = await db.scalar(
        select(models.OrganizationMembership).where(
            models.OrganizationMembership.organization_id == organization.id,
            models.OrganizationMembership.account_id == user.id,
        )
    )
    if membership is None:
        membership = models.OrganizationMembership(
            organization_id=organization.id,
            account_id=user.id,
            organization_display_name=display_name,
        )
        db.add(membership)
        await db.flush()

    membership.organization_display_name = display_name
    membership.lifecycle_status = models.MembershipLifecycleStatus.active
    membership.access_status = models.MembershipAccessStatus.active
    membership.expected_clerk_role = expected_role
    membership.clerk_membership_id = clerk_membership.id
    membership.teacher_access_mode = (
        models.TeacherAccessMode.platform
        if capability == models.MembershipCapability.teacher
        else None
    )
    membership.access_error_category = None
    membership.access_error_safe_message = None
    await _sync_capabilities(db, membership, {capability})
    return membership


async def _ensure_teacher_profile(
    db: AsyncSession,
    *,
    organization_id: int,
    user: models.User,
    membership: models.OrganizationMembership,
) -> models.Teacher:
    teacher = await db.scalar(
        select(models.Teacher).where(models.Teacher.organization_membership_id == membership.id)
    )
    if teacher is None and user.teacher_id:
        existing = await db.get(models.Teacher, user.teacher_id)
        if existing is not None and existing.organization_id == organization_id:
            teacher = existing
            teacher.organization_membership_id = membership.id
    if teacher is None:
        teacher = models.Teacher(
            name=user.name or user.email,
            organization_id=organization_id,
            organization_membership_id=membership.id,
        )
        db.add(teacher)
        await db.flush()

    teacher.name = user.name or user.email
    user.teacher_id = teacher.id
    return teacher


async def prepare_e2e_clerk_state(
    db: AsyncSession,
    *,
    directory: ClerkDirectory,
    config: E2EClerkPrepConfig,
) -> E2EClerkPrepResult:
    admin = await _required_clerk_user(directory, config.admin_email, "admin")
    teacher = await _required_clerk_user(directory, config.teacher_email, "teacher")
    if admin.id == teacher.id:
        raise E2EClerkPreflightError("Admin and teacher E2E users must be different Clerk users.")

    clerk_org_id = await _resolve_clerk_org_id(directory, admin, config.clerk_org_id)
    clerk_org = await directory.get_organization(clerk_org_id)
    if clerk_org is None:
        raise E2EClerkPreflightError(
            f"Clerk organization {clerk_org_id!r} was not found. Check E2E_CLERK_ORG_ID."
        )

    admin_provider_membership = await _required_membership(
        directory,
        organization_id=clerk_org_id,
        user=admin,
        expected_role=models.ClerkOrganizationRole.admin,
        label="admin",
    )
    teacher_provider_membership = await _required_membership(
        directory,
        organization_id=clerk_org_id,
        user=teacher,
        expected_role=models.ClerkOrganizationRole.member,
        label="teacher",
    )

    organization = await _upsert_organization(db, clerk_org)
    await set_async_tenant_context(db, organization.id)

    admin_user = await _upsert_user(
        db,
        clerk_user=admin,
        organization_id=organization.id,
        role=models.UserRole.admin,
    )
    teacher_user = await _upsert_user(
        db,
        clerk_user=teacher,
        organization_id=organization.id,
        role=models.UserRole.teacher,
    )
    await db.flush()

    admin_membership = await _upsert_membership(
        db,
        organization=organization,
        user=admin_user,
        display_name=admin.name or admin.email,
        expected_role=models.ClerkOrganizationRole.admin,
        clerk_membership=admin_provider_membership,
        capability=models.MembershipCapability.admin,
    )
    teacher_membership = await _upsert_membership(
        db,
        organization=organization,
        user=teacher_user,
        display_name=teacher.name or teacher.email,
        expected_role=models.ClerkOrganizationRole.member,
        clerk_membership=teacher_provider_membership,
        capability=models.MembershipCapability.teacher,
    )
    teacher_profile = await _ensure_teacher_profile(
        db,
        organization_id=organization.id,
        user=teacher_user,
        membership=teacher_membership,
    )
    admin_user.teacher_id = None
    await db.flush()

    return E2EClerkPrepResult(
        clerk_org_id=clerk_org_id,
        organization_id=organization.id,
        admin_user_id=admin_user.id,
        admin_membership_id=admin_membership.id,
        teacher_user_id=teacher_user.id,
        teacher_membership_id=teacher_membership.id,
        teacher_id=teacher_profile.id,
    )
