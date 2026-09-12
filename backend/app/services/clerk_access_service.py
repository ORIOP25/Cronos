from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog

from app.config import settings
from app.core.clerk import ClerkGateway, get_clerk_sdk

SAFE_PROVIDER_ERROR = "Não foi possível sincronizar o acesso. Tente novamente ou contacte o apoio."
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
    provider_status_code: int | None = None
    provider_error_code: str | None = None
    provider_request_id: str | None = None
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
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"Unsupported Clerk timestamp type: {type(value).__name__}")
    return datetime.fromtimestamp(value / 1000, tz=UTC)


class ClerkAccessService:
    """Infrastructure adapter for Clerk Backend API access operations."""

    def __init__(
        self,
        gateway: ClerkGateway | None = None,
        *,
        timeout_seconds: float | None = None,
    ) -> None:
        self._gateway = gateway
        self._timeout_seconds = (
            float(settings.CLERK_ACCESS_TIMEOUT_SECONDS)
            if timeout_seconds is None
            else timeout_seconds
        )
        if self._timeout_seconds <= 0:
            raise ValueError("Clerk access timeout must be positive.")

    @property
    def _sdk(self):
        return self._gateway.sdk if self._gateway is not None else get_clerk_sdk()

    async def _call(self, fn, *args, **kwargs) -> ClerkAccessResult:
        try:
            provider_call = (
                fn(*args, **kwargs)
                if self._gateway is not None
                else asyncio.to_thread(fn, *args, **kwargs)
            )
            result = await asyncio.wait_for(provider_call, timeout=self._timeout_seconds)
        except TimeoutError:
            logger.warning(
                "clerk_provider_request_timed_out",
                operation=getattr(fn, "__name__", type(fn).__name__),
                timeout_seconds=self._timeout_seconds,
            )
            return ClerkAccessResult(
                retryable=True,
                error_category="provider_timeout",
                safe_message=SAFE_PROVIDER_ERROR,
            )
        except Exception as exc:
            text = str(exc).lower()
            status_code = getattr(exc, "status_code", None)
            headers = getattr(exc, "headers", None) or {}
            request_id = headers.get("x-request-id") or headers.get("x-clerk-request-id")
            errors = getattr(getattr(exc, "data", None), "errors", None) or []
            provider_code = getattr(errors[0], "code", None) if errors else None
            retryable = (
                any(
                    marker in text
                    for marker in ["429", "rate", "timeout", "temporar", "connection"]
                )
                or status_code == 429
            )
            logger.warning(
                "clerk_provider_request_failed",
                operation=getattr(fn, "__name__", type(fn).__name__),
                error_type=type(exc).__name__,
                provider_status_code=status_code,
                provider_error_code=provider_code,
                provider_request_id=request_id,
                retryable=retryable,
            )
            return ClerkAccessResult(
                retryable=retryable,
                error_category="provider_rate_limited" if retryable else "provider_error",
                safe_message=SAFE_PROVIDER_ERROR,
                provider_status_code=status_code,
                provider_error_code=provider_code,
                provider_request_id=request_id,
            )
        return ClerkAccessResult(raw=result)

    async def find_user_by_email(self, *, email: str) -> ClerkAccessResult:
        sdk = self._sdk
        normalized = email.strip().lower()
        list_users = sdk.users.list_async if self._gateway is not None else sdk.users.list
        result = await self._call(
            list_users,
            request={"email_address": [normalized], "limit": 10},
        )
        if not result.ok:
            return result
        users = list(result.raw or [])
        exact = []
        for user in users:
            addresses = {
                getattr(address, "email_address", "").strip().lower()
                for address in (getattr(user, "email_addresses", None) or [])
            }
            if normalized in addresses:
                exact.append(user)
        if not exact:
            return ClerkAccessResult()
        if len(exact) > 1:
            logger.error(
                "clerk_provider_contract_error",
                field="users.email_address",
                match_count=len(exact),
            )
            return ClerkAccessResult(
                error_category=PROVIDER_CONTRACT_ERROR,
                safe_message=SAFE_PROVIDER_ERROR,
            )
        return ClerkAccessResult(user_id=getattr(exact[0], "id", None), raw=exact[0])

    async def find_pending_invitation(
        self,
        *,
        clerk_org_id: str,
        email: str,
    ) -> ClerkAccessResult:
        sdk = self._sdk
        normalized = email.strip().lower()
        list_invitations = (
            sdk.organization_invitations.list_async
            if self._gateway is not None
            else sdk.organization_invitations.list
        )
        result = await self._call(
            list_invitations,
            organization_id=clerk_org_id,
            email_address=normalized,
            status="pending",
            limit=100,
        )
        if not result.ok:
            return result
        invitations = [
            item
            for item in (getattr(result.raw, "data", None) or [])
            if getattr(item, "email_address", "").strip().lower() == normalized
            and getattr(item, "status", None) == "pending"
        ]
        if not invitations:
            return ClerkAccessResult()
        if len(invitations) > 1:
            logger.error(
                "clerk_duplicate_pending_invitations",
                clerk_org_id=clerk_org_id,
                invitation_count=len(invitations),
            )
            return ClerkAccessResult(
                error_category="provider_duplicate_pending_invitations",
                safe_message="Existem vários convites pendentes. Contacte o apoio para concluir a sincronização.",
            )
        return self._invitation_result(invitations[0])

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
        sdk = self._sdk
        create_invitation = (
            sdk.organization_invitations.create_async
            if self._gateway is not None
            else sdk.organization_invitations.create
        )
        result = await self._call(
            create_invitation,
            organization_id=clerk_org_id,
            email_address=email,
            role=role,
            inviter_user_id=inviter_user_id,
            public_metadata={"membership_id": membership_id} if membership_id else {},
            redirect_url=settings.CLERK_INVITATION_REDIRECT_URL,
            notify=True,
        )
        if not result.ok:
            return result
        parsed = self._invitation_result(result.raw)
        if parsed.invitation_status is None:
            parsed.invitation_status = "pending"
        return parsed

    async def create_organization_membership(
        self,
        *,
        clerk_org_id: str,
        clerk_user_id: str,
        role: str,
    ) -> ClerkAccessResult:
        sdk = self._sdk
        create_membership = (
            sdk.organization_memberships.create_async
            if self._gateway is not None
            else sdk.organization_memberships.create
        )
        result = await self._call(
            create_membership,
            organization_id=clerk_org_id,
            user_id=clerk_user_id,
            role=role,
        )
        if not result.ok:
            return result
        raw = result.raw
        membership_id = getattr(raw, "id", None)
        if not membership_id:
            logger.error(
                "clerk_provider_contract_error",
                field="organization_membership.id",
            )
            return ClerkAccessResult(
                user_id=clerk_user_id,
                error_category=PROVIDER_CONTRACT_ERROR,
                safe_message=SAFE_PROVIDER_ERROR,
                raw=raw,
            )
        return ClerkAccessResult(
            membership_id=membership_id,
            user_id=clerk_user_id,
            role=getattr(raw, "role", role),
            raw=raw,
        )

    async def revoke_organization_invitation(
        self,
        *,
        clerk_org_id: str,
        invitation_id: str,
        requesting_user_id: str,
    ) -> ClerkAccessResult:
        sdk = self._sdk
        revoke_invitation = (
            sdk.organization_invitations.revoke_async
            if self._gateway is not None
            else sdk.organization_invitations.revoke
        )
        return await self._call(
            revoke_invitation,
            organization_id=clerk_org_id,
            invitation_id=invitation_id,
            requesting_user_id=requesting_user_id,
        )

    async def revoke_organization_membership(
        self,
        *,
        clerk_org_id: str,
        clerk_user_id: str,
    ) -> ClerkAccessResult:
        sdk = self._sdk
        delete_membership = (
            sdk.organization_memberships.delete_async
            if self._gateway is not None
            else sdk.organization_memberships.delete
        )
        return await self._call(
            delete_membership,
            organization_id=clerk_org_id,
            user_id=clerk_user_id,
        )

    async def change_membership_role(
        self,
        *,
        clerk_org_id: str,
        clerk_user_id: str,
        role: str,
    ) -> ClerkAccessResult:
        sdk = self._sdk
        update_membership = (
            sdk.organization_memberships.update_async
            if self._gateway is not None
            else sdk.organization_memberships.update
        )
        result = await self._call(
            update_membership,
            organization_id=clerk_org_id,
            user_id=clerk_user_id,
            role=role,
        )
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
        sdk = self._sdk
        list_memberships = (
            sdk.organization_memberships.list_async
            if self._gateway is not None
            else sdk.organization_memberships.list
        )
        result = await self._call(
            list_memberships,
            organization_id=clerk_org_id,
            user_id=[clerk_user_id],
            limit=10,
        )
        if not result.ok:
            return result
        raw = result.raw
        item = (
            raw.data[0]
            if hasattr(raw, "data") and raw.data
            else (None if hasattr(raw, "data") else raw)
        )
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
        sdk = self._sdk
        get_invitation = (
            sdk.organization_invitations.get_async
            if self._gateway is not None
            else sdk.organization_invitations.get
        )
        result = await self._call(
            get_invitation,
            organization_id=clerk_org_id,
            invitation_id=invitation_id,
        )
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
