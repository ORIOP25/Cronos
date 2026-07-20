from __future__ import annotations

import asyncio
import json
import os

from sqlalchemy import select

from app import models
from app.core.clerk import get_clerk_sdk
from app.db.database import SessionLocal
from app.services.clerk_access_service import ClerkAccessService

EMAIL_ENV_NAMES = (
    "E2E_CLERK_INVITE_CREATE_EMAIL",
    "E2E_CLERK_INVITE_CONVERT_EMAIL",
)
RESERVED_SUFFIX = "+clerk_test@example.com"


def _required_test_emails() -> list[str]:
    emails = [os.getenv(name, "").strip().lower() for name in EMAIL_ENV_NAMES]
    invalid = [email for email in emails if not email.endswith(RESERVED_SUFFIX)]
    if invalid:
        raise RuntimeError("Cleanup is restricted to exact Clerk reserved test emails.")
    return emails


async def _main() -> None:
    emails = _required_test_emails()
    admin_email = os.getenv("E2E_CLERK_ADMIN_EMAIL", "").strip().lower()
    if not admin_email:
        raise RuntimeError("E2E_CLERK_ADMIN_EMAIL is required.")

    async with SessionLocal() as db:
        admin = await db.scalar(select(models.User).where(models.User.email == admin_email))
        if admin is None or not admin.clerk_user_id:
            raise RuntimeError("The prepared E2E admin was not found locally.")
        membership = await db.scalar(
            select(models.OrganizationMembership).where(
                models.OrganizationMembership.account_id == admin.id
            )
        )
        organization = await db.get(
            models.Organization, membership.organization_id if membership else None
        )
        if organization is None or not organization.clerk_org_id:
            raise RuntimeError("The prepared E2E Clerk organization was not found locally.")
        org_id = organization.clerk_org_id
        requesting_user_id = admin.clerk_user_id

    access = ClerkAccessService()
    sdk = get_clerk_sdk()
    revoked: list[str] = []
    for email in emails:
        invitations = await asyncio.to_thread(
            sdk.organization_invitations.list,
            organization_id=org_id,
            email_address=email,
            status="pending",
            limit=100,
        )
        for invitation in invitations.data:
            result = await access.revoke_organization_invitation(
                clerk_org_id=org_id,
                invitation_id=invitation.id,
                requesting_user_id=requesting_user_id,
            )
            if not result.ok:
                raise RuntimeError(f"Could not revoke E2E invitation {invitation.id}.")
            revoked.append(invitation.id)
    print(json.dumps({"revoked_invitation_ids": revoked}, indent=2))


if __name__ == "__main__":
    asyncio.run(_main())
