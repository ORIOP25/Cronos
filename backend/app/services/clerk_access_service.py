from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import structlog

from app.core.clerk import get_clerk_sdk


SAFE_PROVIDER_ERROR = "Access could not be synchronized with Clerk. Try again or contact support."
PROVIDER_CONTRACT_ERROR = "provider_contract_error"

logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class ClerkAccessResult:
    invitation_id: str | None = None
    invitation_status: str | None = None
    expires_at: datetime | None = None
    membership_id: str | None = None
    user_id: str | None = None
    role: str | None = None
    retryable: bool = False
    error_category: str | None = None
    safe_message: str | None = None
    raw: Any = None

    @property
    def ok(self) -> bool:
        return self.error_category is None


def normalize_clerk_datetime(value: object) -> datetime | None:
    """Translate Clerk's millisecond epoch timestamps into the domain time type."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"Unsupported Clerk timestamp type: {type(value).__name__}")
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc)


class ClerkAccessService:
    """Infrastructure adapter for Clerk Backend API access operations."""

    async def _call(self, fn, *args, **kwargs) -> ClerkAccessResult:
        try:
            result = await asyncio.to_thread(fn, *args, **kwargs)
        except Exception as exc:
            text = str(exc).lower()
            retryable = any(
                marker in text
                for marker in ["429", "rate", "timeout", "temporar", "connection"]
            )
            return ClerkAccessResult(
                retryable=retryable,
                error_category="provider_rate_limited" if retryable else "provider_error",
                safe_message=SAFE_PROVIDER_ERROR,
            )
        return ClerkAccessResult(raw=result)

    @staticmethod
    def _invitation_result(raw: Any, *, fallback_id: str | None = None) -> ClerkAccessResult:
        invitation_id = getattr(raw, "id", fallback_id) if raw is not None else fallback_id
        invitation_status = getattr(raw, "status", None) if raw is not None else None
        raw_expires_at = getattr(raw, "expires_at", None) if raw is not None else None
        if not invitation_id:
            logger.error(
                "clerk_provider_contract_error",
                field="id",
                value_type=type(invitation_id).__name__,
            )
            return ClerkAccessResult(
                error_category=PROVIDER_CONTRACT_ERROR,
                safe_message=SAFE_PROVIDER_ERROR,
                raw=raw,
            )
        try:
            expires_at = normalize_clerk_datetime(raw_expires_at)
        except (OverflowError, OSError, TypeError, ValueError):
            logger.error(
                "clerk_provider_contract_error",
                invitation_id=invitation_id,
                field="expires_at",
                value_type=type(raw_expires_at).__name__,
            )
            return ClerkAccessResult(
                invitation_id=invitation_id,
                invitation_status=invitation_status,
                error_category=PROVIDER_CONTRACT_ERROR,
                safe_message=SAFE_PROVIDER_ERROR,
                raw=raw,
            )
        return ClerkAccessResult(
            invitation_id=invitation_id,
            invitation_status=invitation_status,
            expires_at=expires_at,
            raw=raw,
        )

    async def create_organization_invitation(
        self,
        *,
        clerk_org_id: str,
        email: str,
        role: str,
        inviter_user_id: str,
        membership_id: int | None,
    ) -> ClerkAccessResult:
        sdk = get_clerk_sdk()

        def _send():
            return sdk.organization_invitations.create(
                organization_id=clerk_org_id,
                email_address=email,
                role=role,
                inviter_user_id=inviter_user_id,
                public_metadata={"membership_id": membership_id} if membership_id else {},
            )

        result = await self._call(_send)
        if not result.ok:
            return result
        parsed = self._invitation_result(result.raw)
        if parsed.invitation_status is None:
            parsed.invitation_status = "pending"
        return parsed

    async def revoke_organization_invitation(
        self,
        *,
        clerk_org_id: str,
        invitation_id: str,
        requesting_user_id: str,
    ) -> ClerkAccessResult:
        sdk = get_clerk_sdk()

        def _revoke():
            return sdk.organization_invitations.revoke(
                organization_id=clerk_org_id,
                invitation_id=invitation_id,
                requesting_user_id=requesting_user_id,
            )

        return await self._call(_revoke)

    async def revoke_organization_membership(
        self,
        *,
        clerk_org_id: str,
        clerk_user_id: str | None = None,
        clerk_membership_id: str | None = None,
    ) -> ClerkAccessResult:
        sdk = get_clerk_sdk()

        def _delete():
            if clerk_membership_id:
                return sdk.organization_memberships.delete(
                    organization_id=clerk_org_id,
                    membership_id=clerk_membership_id,
                )
            return sdk.organization_memberships.delete(
                organization_id=clerk_org_id,
                user_id=clerk_user_id,
            )

        return await self._call(_delete)

    async def change_membership_role(
        self,
        *,
        clerk_org_id: str,
        clerk_user_id: str,
        role: str,
    ) -> ClerkAccessResult:
        sdk = get_clerk_sdk()

        def _update():
            return sdk.organization_memberships.update(
                organization_id=clerk_org_id,
                user_id=clerk_user_id,
                role=role,
            )

        result = await self._call(_update)
        if not result.ok:
            return result
        raw = result.raw
        return ClerkAccessResult(
            membership_id=getattr(raw, "id", None),
            user_id=clerk_user_id,
            role=getattr(raw, "role", role),
            raw=raw,
        )

    async def get_membership(
        self,
        *,
        clerk_org_id: str,
        clerk_user_id: str,
    ) -> ClerkAccessResult:
        sdk = get_clerk_sdk()

        def _get():
            if hasattr(sdk.organization_memberships, "get"):
                return sdk.organization_memberships.get(
                    organization_id=clerk_org_id,
                    user_id=clerk_user_id,
                )
            return sdk.organization_memberships.list(
                organization_id=clerk_org_id,
                user_id=clerk_user_id,
            )

        result = await self._call(_get)
        if not result.ok:
            return result
        raw = result.raw
        item = raw.data[0] if hasattr(raw, "data") and raw.data else raw
        return ClerkAccessResult(
            membership_id=getattr(item, "id", None),
            user_id=clerk_user_id,
            role=getattr(item, "role", None),
            raw=item,
        )

    async def get_invitation(
        self,
        *,
        clerk_org_id: str,
        invitation_id: str,
    ) -> ClerkAccessResult:
        sdk = get_clerk_sdk()

        def _get():
            if hasattr(sdk.organization_invitations, "get"):
                return sdk.organization_invitations.get(
                    organization_id=clerk_org_id,
                    invitation_id=invitation_id,
                )
            return sdk.organization_invitations.list(organization_id=clerk_org_id)

        result = await self._call(_get)
        if not result.ok:
            return result
        raw = result.raw
        item = raw
        if hasattr(raw, "data"):
            item = next(
                (
                    candidate
                    for candidate in raw.data
                    if getattr(candidate, "id", None) == invitation_id
                ),
                None,
            )
        return self._invitation_result(item, fallback_id=invitation_id)
