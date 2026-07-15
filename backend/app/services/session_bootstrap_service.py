from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import models
from app.core.clerk import get_clerk_sdk
from app.db.tenant import set_async_tenant_context
from app.services import clerk_sync


class SessionBootstrapError(RuntimeError):
    status_code = 500
    code = "SESSION_BOOTSTRAP_FAILED"


class ActiveOrganizationRequiredError(SessionBootstrapError):
    status_code = 409
    code = "ACTIVE_ORGANIZATION_REQUIRED"


class ActiveOrganizationAccessDeniedError(SessionBootstrapError):
    status_code = 403
    code = "ACTIVE_ORGANIZATION_ACCESS_DENIED"


class ClerkDirectoryUnavailableError(SessionBootstrapError):
    status_code = 503
    code = "CLERK_DIRECTORY_UNAVAILABLE"


@dataclass(frozen=True)
class SessionBootstrapResult:
    organization: dict
    member: dict
    onboarding_complete: bool


class SessionBootstrapService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def bootstrap(self, payload: dict) -> SessionBootstrapResult:
        clerk_user_id = payload.get("sub")
        organization_claim = payload.get("o") or {}
        clerk_org_id = organization_claim.get("id")
        token_role = organization_claim.get("rol")
        if not clerk_user_id:
            raise ActiveOrganizationAccessDeniedError("Authenticated user is missing.")
        if not clerk_org_id:
            raise ActiveOrganizationRequiredError(
                "Select an active organization before bootstrapping the session."
            )
        if token_role not in {"admin", "org:admin"}:
            raise ActiveOrganizationAccessDeniedError(
                "Active organization administrator access is required."
            )

        await self.db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:clerk_org_id))"),
            {"clerk_org_id": clerk_org_id},
        )
        provider_membership_id = await self._verify_provider_membership(
            clerk_org_id,
            clerk_user_id,
        )
        organization = await clerk_sync.sync_organization_from_clerk_api(
            self.db,
            clerk_org_id,
        )
        if organization is None:
            raise ClerkDirectoryUnavailableError(
                "The organization directory is temporarily unavailable."
            )
        profile = await clerk_sync.fetch_clerk_user_profile(clerk_user_id)
        if profile is None:
            raise ClerkDirectoryUnavailableError(
                "The user directory is temporarily unavailable."
            )
        membership = await self._ensure_founder_membership(
            organization,
            clerk_user_id,
            profile,
            provider_membership_id,
        )
        capabilities = sorted(row.capability.value for row in membership.capabilities)
        if models.MembershipCapability.admin.value not in capabilities:
            raise ActiveOrganizationAccessDeniedError(
                "Active organization administrator access is required."
            )
        onboarding_complete = bool(
            await self.db.scalar(
                select(models.OrganizationSettings.id).where(
                    models.OrganizationSettings.organization_id == organization.id
                )
            )
        )
        return SessionBootstrapResult(
            organization={
                "id": organization.id,
                "clerk_org_id": organization.clerk_org_id,
                "name": organization.name,
            },
            member={
                "id": membership.id,
                "access_status": membership.access_status.value,
                "lifecycle_status": membership.lifecycle_status.value,
                "capabilities": capabilities,
                "default_mode": "admin",
                "teacher_id": None,
            },
            onboarding_complete=onboarding_complete,
        )

    async def _ensure_founder_membership(
        self,
        organization: models.Organization,
        clerk_user_id: str,
        profile: clerk_sync.ClerkUserProfile,
        provider_membership_id: str | None,
    ) -> models.OrganizationMembership:
        await set_async_tenant_context(self.db, organization.id)
        normalized_email = (
            profile.email.strip().lower() if profile.email else clerk_user_id
        )
        membership = await self.db.scalar(
            select(models.OrganizationMembership)
            .join(models.User, models.User.id == models.OrganizationMembership.account_id)
            .where(
                models.OrganizationMembership.organization_id == organization.id,
                or_(
                    models.User.clerk_user_id == clerk_user_id,
                    and_(
                        models.User.clerk_user_id.is_(None),
                        models.User.email == normalized_email,
                    ),
                ),
            )
            .options(
                selectinload(models.OrganizationMembership.account),
                selectinload(models.OrganizationMembership.capabilities),
            )
        )
        now = datetime.now(timezone.utc)
        if membership is not None:
            user = membership.account
            user.clerk_user_id = clerk_user_id
            user.clerk_profile_name = profile.name
            user.name = profile.name or user.name
            user.last_clerk_sync_at = now
            user.is_active = True
            user.organization_id = organization.id
            user.role = models.UserRole.admin
            membership.lifecycle_status = models.MembershipLifecycleStatus.active
            membership.access_status = models.MembershipAccessStatus.active
            membership.expected_clerk_role = models.ClerkOrganizationRole.admin
            membership.clerk_membership_id = (
                provider_membership_id or membership.clerk_membership_id
            )
            membership.access_error_category = None
            membership.access_error_safe_message = None
            if not any(
                row.capability is models.MembershipCapability.admin
                for row in membership.capabilities
            ):
                self.db.add(models.OrganizationMembershipCapability(
                    organization_membership_id=membership.id,
                    capability=models.MembershipCapability.admin,
                ))
                await self.db.flush()
            return await self._load_membership(membership.id)

        existing_count = int(
            await self.db.scalar(
                select(func.count(models.OrganizationMembership.id)).where(
                    models.OrganizationMembership.organization_id == organization.id
                )
            )
            or 0
        )
        if existing_count:
            raise ActiveOrganizationAccessDeniedError(
                "The established organization has no local membership for this account."
            )

        user = await self.db.scalar(
            select(models.User).where(models.User.clerk_user_id == clerk_user_id)
        )
        if user is None:
            user = await self.db.scalar(
                select(models.User).where(
                    models.User.clerk_user_id.is_(None),
                    models.User.email == normalized_email,
                )
            )
        if user is None:
            user = models.User(
                email=normalized_email,
                name=profile.name,
                clerk_user_id=clerk_user_id,
                clerk_profile_name=profile.name,
                organization_id=organization.id,
                role=models.UserRole.admin,
                is_active=True,
                last_clerk_sync_at=now,
            )
            self.db.add(user)
            await self.db.flush()
        else:
            user.clerk_user_id = clerk_user_id
            user.clerk_profile_name = profile.name
            user.name = profile.name or user.name
            user.last_clerk_sync_at = now
            user.is_active = True
            user.organization_id = organization.id
            user.role = models.UserRole.admin

        membership = models.OrganizationMembership(
            organization_id=organization.id,
            account_id=user.id,
            organization_display_name=organization.name or "Organization",
            lifecycle_status=models.MembershipLifecycleStatus.active,
            access_status=models.MembershipAccessStatus.active,
            expected_clerk_role=models.ClerkOrganizationRole.admin,
            clerk_membership_id=provider_membership_id,
            created_by_user_id=user.id,
            updated_by_user_id=user.id,
        )
        self.db.add(membership)
        await self.db.flush()
        self.db.add(models.OrganizationMembershipCapability(
            organization_membership_id=membership.id,
            capability=models.MembershipCapability.admin,
        ))
        await self.db.flush()
        return await self._load_membership(membership.id)

    async def _load_membership(
        self,
        membership_id: int,
    ) -> models.OrganizationMembership:
        membership = await self.db.scalar(
            select(models.OrganizationMembership)
            .where(models.OrganizationMembership.id == membership_id)
            .options(selectinload(models.OrganizationMembership.capabilities))
        )
        if membership is None:
            raise RuntimeError("Founder membership could not be loaded.")
        return membership

    @staticmethod
    async def _verify_provider_membership(
        clerk_org_id: str,
        clerk_user_id: str,
    ) -> str | None:
        sdk = get_clerk_sdk()
        try:
            response = await asyncio.to_thread(
                lambda: sdk.organization_memberships.list(
                    organization_id=clerk_org_id,
                    user_id=[clerk_user_id],
                    limit=10,
                )
            )
        except Exception as exc:
            raise ClerkDirectoryUnavailableError(
                "The organization directory is temporarily unavailable."
            ) from exc
        memberships = tuple(getattr(response, "data", ()) or ())
        matching = next(
            (
                row
                for row in memberships
                if str(getattr(getattr(row, "role", None), "value", getattr(row, "role", None)))
                in {"admin", "org:admin"}
            ),
            None,
        )
        if matching is None:
            raise ActiveOrganizationAccessDeniedError(
                "The provider membership does not grant administrator access."
            )
        return getattr(matching, "id", None)
