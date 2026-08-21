from __future__ import annotations

import asyncio
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.core.clerk import ClerkGateway, get_clerk_sdk
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
    foundation_status: str


class SessionBootstrapService:
    def __init__(self, db: AsyncSession, clerk: ClerkGateway | None = None):
        self.db = db
        self.clerk = clerk

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

        provider_membership_id, profile, organization_name = await asyncio.gather(
            self._verify_provider_membership(clerk_org_id, clerk_user_id),
            clerk_sync.fetch_clerk_user_profile(clerk_user_id, self.clerk),
            clerk_sync.fetch_clerk_organization_name(clerk_org_id, self.clerk),
        )
        if profile is None or organization_name is None:
            raise ClerkDirectoryUnavailableError(
                "The provider directory is temporarily unavailable."
            )
        principal = (
            (
                await self.db.execute(
                    text(
                        """
                SELECT account_id, organization_id, membership_id
                FROM app_security.bootstrap_organization_admin(
                    :clerk_user_id, :clerk_org_id, :organization_name,
                    :email, :profile_name, :provider_membership_id
                )
                """
                    ),
                    {
                        "clerk_user_id": clerk_user_id,
                        "clerk_org_id": clerk_org_id,
                        "organization_name": organization_name,
                        "email": profile.email,
                        "profile_name": profile.name,
                        "provider_membership_id": provider_membership_id,
                    },
                )
            )
            .mappings()
            .one_or_none()
        )
        if principal is None:
            raise ActiveOrganizationAccessDeniedError(
                "The established organization has no local membership for this account."
            )
        await set_async_tenant_context(self.db, principal["organization_id"])
        organization = await self.db.get(models.Organization, principal["organization_id"])
        membership = await self._load_membership(principal["membership_id"])
        if organization is None:
            raise RuntimeError("Founder organization could not be loaded.")
        capabilities = sorted(row.capability.value for row in membership.capabilities)
        if models.MembershipCapability.admin.value not in capabilities:
            raise ActiveOrganizationAccessDeniedError(
                "Active organization administrator access is required."
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
            foundation_status=organization.foundation_status.value,
        )

    async def _load_membership(
        self,
        membership_id: int,
    ) -> models.OrganizationMembership:
        membership = await self.db.scalar(
            select(models.OrganizationMembership).where(
                models.OrganizationMembership.id == membership_id
            )
        )
        if membership is None:
            raise RuntimeError("Founder membership could not be loaded.")
        return membership

    async def _verify_provider_membership(
        self,
        clerk_org_id: str,
        clerk_user_id: str,
    ) -> str | None:
        try:
            if self.clerk is not None:
                response = await self.clerk.sdk.organization_memberships.list_async(
                    organization_id=clerk_org_id,
                    user_id=[clerk_user_id],
                    limit=10,
                )
            else:
                sdk = get_clerk_sdk()
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
