from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.core.exceptions import new_error_reference
from app.db.tenant import set_async_tenant_context
from app.services.clerk_access_service import ClerkAccessResult, ClerkAccessService

logger = structlog.get_logger(__name__)

UNRESOLVED_STATUSES = {
    models.MemberAccessOperationStatus.pending,
    models.MemberAccessOperationStatus.clerk_succeeded,
    models.MemberAccessOperationStatus.compensation_failed,
    models.MemberAccessOperationStatus.support_required,
}
REUSABLE_STATUSES = {
    models.MemberAccessOperationStatus.failed,
    models.MemberAccessOperationStatus.compensated,
}


class UnresolvedAccessOperationError(RuntimeError):
    def __init__(self, operation_id: int):
        super().__init__(f"Access operation {operation_id} requires resolution.")
        self.operation_id = operation_id


@dataclass(frozen=True, slots=True)
class AccessOperationContext:
    id: int
    idempotency_key: str
    organization_id: int
    membership_id: int | None
    target_email: str
    operation_type: models.MemberAccessOperationType


def _canonical_intent_hash(intent: dict[str, Any]) -> str:
    payload = json.dumps(intent, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def _idempotency_key(
    *,
    operation_type: models.MemberAccessOperationType,
    organization_id: int,
    membership_id: int | None,
    target_email: str,
    lock_version: int | None,
    intent: dict[str, Any],
) -> str:
    subject = str(membership_id) if membership_id is not None else target_email.lower()
    version = lock_version if lock_version is not None else "create"
    digest = _canonical_intent_hash(intent)
    return f"{operation_type.value}:{organization_id}:{subject}:{version}:{digest}"


class MemberAccessOperationService:
    """Durable access-operation ledger, committed independently of domain writes."""

    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        clerk_access: ClerkAccessService,
    ) -> None:
        self._session_factory = session_factory
        self.clerk_access = clerk_access
        self._organization_id: int | None = None

    def _bind_organization(self, organization_id: int) -> None:
        if self._organization_id not in (None, organization_id):
            raise RuntimeError("A member access operation service cannot cross tenants.")
        self._organization_id = organization_id

    def _bound_organization_id(self) -> int:
        if self._organization_id is None:
            raise RuntimeError("The member access operation service is not tenant-bound.")
        return self._organization_id

    async def create_pending(
        self,
        *,
        organization_id: int,
        target_email: str,
        operation_type: models.MemberAccessOperationType,
        created_by_membership_id: int,
        intended_capabilities: set[models.MembershipCapability],
        intended_role: models.ClerkOrganizationRole | None,
        intent: dict[str, Any],
        membership_id: int | None = None,
        account_id: int | None = None,
        lock_version: int | None = None,
        previous_snapshot: dict[str, Any] | None = None,
        draft_payload: dict[str, Any] | None = None,
        clerk_org_id: str | None = None,
        clerk_user_id: str | None = None,
        clerk_membership_id: str | None = None,
        clerk_invitation_id: str | None = None,
    ) -> AccessOperationContext:
        self._bind_organization(organization_id)
        key = _idempotency_key(
            operation_type=operation_type,
            organization_id=organization_id,
            membership_id=membership_id,
            target_email=target_email,
            lock_version=lock_version,
            intent=intent,
        )
        async with self._session_factory() as db:
            await set_async_tenant_context(db, organization_id)
            unresolved_conditions = [
                models.MemberAccessOperation.organization_id == organization_id,
                models.MemberAccessOperation.operation_status.in_(UNRESOLVED_STATUSES),
            ]
            if membership_id is None:
                unresolved_conditions.append(
                    models.MemberAccessOperation.target_email == target_email.lower()
                )
            else:
                unresolved_conditions.append(
                    or_(
                        models.MemberAccessOperation.membership_id == membership_id,
                        models.MemberAccessOperation.target_email == target_email.lower(),
                    )
                )
            unresolved = await db.scalar(
                select(models.MemberAccessOperation).where(*unresolved_conditions).with_for_update()
            )
            if unresolved is not None and unresolved.idempotency_key != key:
                raise UnresolvedAccessOperationError(unresolved.id)

            operation = await db.scalar(
                select(models.MemberAccessOperation)
                .where(models.MemberAccessOperation.idempotency_key == key)
                .with_for_update()
            )
            if operation is not None and operation.operation_status in UNRESOLVED_STATUSES:
                raise UnresolvedAccessOperationError(operation.id)
            if operation is None:
                # Access operations may be started while the domain session is
                # editing the target membership/account. Persisting those foreign
                # keys here would make this independent ledger transaction wait on
                # the domain transaction, while the domain transaction waits for
                # this commit: a cross-session self-deadlock. The target email is
                # the durable correlation key until the local commit succeeds; the
                # final transition attaches the local identifiers afterwards.
                operation = models.MemberAccessOperation(
                    organization_id=organization_id,
                    membership_id=None,
                    account_id=None,
                    target_email=target_email.lower(),
                    operation_type=operation_type,
                    idempotency_key=key,
                    created_by_membership_id=created_by_membership_id,
                )
                db.add(operation)
            elif operation.operation_status not in REUSABLE_STATUSES:
                raise UnresolvedAccessOperationError(operation.id)

            operation.operation_status = models.MemberAccessOperationStatus.pending
            operation.intended_capabilities_json = {
                "capabilities": sorted(capability.value for capability in intended_capabilities)
            }
            operation.intended_clerk_role = intended_role.value if intended_role else None
            operation.previous_access_snapshot_json = previous_snapshot
            operation.draft_payload_json = draft_payload
            operation.clerk_org_id = clerk_org_id
            operation.clerk_user_id = clerk_user_id
            operation.clerk_membership_id = clerk_membership_id
            operation.clerk_invitation_id = clerk_invitation_id
            operation.provider_error_category = None
            operation.provider_error_safe_message = None
            operation.compensation_attempted_at = None
            operation.support_required_at = None
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()
                await set_async_tenant_context(db, organization_id)
                conflict_conditions = [
                    models.MemberAccessOperation.organization_id == organization_id,
                    models.MemberAccessOperation.operation_status.in_(UNRESOLVED_STATUSES),
                ]
                conflict_conditions.append(
                    models.MemberAccessOperation.target_email == target_email.lower()
                    if membership_id is None
                    else or_(
                        models.MemberAccessOperation.membership_id == membership_id,
                        models.MemberAccessOperation.target_email == target_email.lower(),
                    )
                )
                conflict_id = await db.scalar(
                    select(models.MemberAccessOperation.id).where(*conflict_conditions)
                )
                if conflict_id is not None:
                    raise UnresolvedAccessOperationError(conflict_id) from None
                raise
            logger.info(
                "member_access_operation_created",
                operation_id=operation.id,
                organization_id=organization_id,
                membership_id=membership_id,
                operation_type=operation_type.value,
            )
            return AccessOperationContext(
                id=operation.id,
                idempotency_key=key,
                organization_id=organization_id,
                membership_id=membership_id,
                target_email=target_email.lower(),
                operation_type=operation_type,
            )

    async def transition(
        self,
        operation_id: int,
        status: models.MemberAccessOperationStatus,
        *,
        membership_id: int | None = None,
        account_id: int | None = None,
        clerk_invitation_id: str | None = None,
        clerk_membership_id: str | None = None,
        provider_error_reference: str | None = None,
        error_category: str | None = None,
        safe_message: str | None = None,
        compensation_attempted: bool = False,
        support_required: bool = False,
    ) -> None:
        organization_id = self._bound_organization_id()
        async with self._session_factory() as db:
            await set_async_tenant_context(db, organization_id)
            operation = await db.get(models.MemberAccessOperation, operation_id)
            if operation is None:
                raise RuntimeError(f"Access operation {operation_id} was not found.")
            operation.operation_status = status
            if membership_id is not None:
                operation.membership_id = membership_id
            if account_id is not None:
                operation.account_id = account_id
            if clerk_invitation_id is not None:
                operation.clerk_invitation_id = clerk_invitation_id
            if clerk_membership_id is not None:
                operation.clerk_membership_id = clerk_membership_id
            if provider_error_reference is not None:
                operation.provider_error_reference = provider_error_reference[:120]
            elif error_category is not None or support_required:
                operation.provider_error_reference = (
                    operation.provider_error_reference or new_error_reference()
                )
            operation.provider_error_category = error_category
            operation.provider_error_safe_message = safe_message
            if compensation_attempted:
                operation.compensation_attempted_at = datetime.now(UTC)
            if support_required:
                operation.support_required_at = datetime.now(UTC)
            await db.commit()
            logger.info(
                "member_access_operation_transitioned",
                operation_id=operation_id,
                operation_status=status.value,
                support_required=support_required,
            )


@dataclass(frozen=True, slots=True)
class SagaCompensationOutcome:
    support_required: bool


class MemberAccessSagaCoordinator:
    """Concrete Clerk compensations with one durable completion path."""

    def __init__(self, operations: MemberAccessOperationService) -> None:
        self._operations = operations
        self._clerk_access = operations.clerk_access

    async def _finish(
        self,
        *,
        operation_id: int,
        compensation: ClerkAccessResult,
        attempted: bool,
        error_category: str,
        safe_message: str,
        clerk_invitation_id: str | None = None,
        clerk_membership_id: str | None = None,
    ) -> SagaCompensationOutcome:
        support_required = not compensation.ok
        provider_references = {}
        if clerk_invitation_id is not None:
            provider_references["clerk_invitation_id"] = clerk_invitation_id
        if clerk_membership_id is not None:
            provider_references["clerk_membership_id"] = clerk_membership_id
        if compensation.provider_request_id is not None:
            provider_references["provider_error_reference"] = compensation.provider_request_id
        await self._operations.transition(
            operation_id,
            (
                models.MemberAccessOperationStatus.support_required
                if support_required
                else models.MemberAccessOperationStatus.compensated
            ),
            **provider_references,
            error_category=(compensation.error_category if support_required else error_category),
            safe_message=compensation.safe_message if support_required else safe_message,
            compensation_attempted=attempted,
            support_required=support_required,
        )
        return SagaCompensationOutcome(support_required=support_required)

    async def compensate_created_invitation(
        self,
        *,
        operation_id: int,
        clerk_org_id: str,
        invitation_id: str,
        requesting_user_id: str,
        error_category: str,
        safe_message: str,
    ) -> SagaCompensationOutcome:
        compensation = await self._clerk_access.revoke_organization_invitation(
            clerk_org_id=clerk_org_id,
            invitation_id=invitation_id,
            requesting_user_id=requesting_user_id,
        )
        return await self._finish(
            operation_id=operation_id,
            compensation=compensation,
            attempted=True,
            error_category=error_category,
            safe_message=safe_message,
            clerk_invitation_id=invitation_id,
        )

    async def compensate_created_membership(
        self,
        *,
        operation_id: int,
        clerk_org_id: str,
        clerk_user_id: str,
        clerk_membership_id: str | None,
        error_category: str,
        safe_message: str,
    ) -> SagaCompensationOutcome:
        compensation = await self._clerk_access.revoke_organization_membership(
            clerk_org_id=clerk_org_id,
            clerk_user_id=clerk_user_id,
        )
        return await self._finish(
            operation_id=operation_id,
            compensation=compensation,
            attempted=True,
            error_category=error_category,
            safe_message=safe_message,
            clerk_membership_id=clerk_membership_id,
        )

    async def compensate_role_change(
        self,
        *,
        operation_id: int,
        clerk_org_id: str,
        clerk_user_id: str,
        previous_role: models.ClerkOrganizationRole | None,
        clerk_membership_id: str | None,
        error_category: str,
        safe_message: str,
    ) -> SagaCompensationOutcome:
        attempted = previous_role is not None
        compensation = (
            await self._clerk_access.change_membership_role(
                clerk_org_id=clerk_org_id,
                clerk_user_id=clerk_user_id,
                role=previous_role.value,
            )
            if previous_role is not None
            else ClerkAccessResult(error_category="compensation_unavailable")
        )
        return await self._finish(
            operation_id=operation_id,
            compensation=compensation,
            attempted=attempted,
            error_category=error_category,
            safe_message=safe_message,
            clerk_membership_id=clerk_membership_id,
        )
