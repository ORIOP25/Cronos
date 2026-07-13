from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

import structlog
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.db.database import SessionLocal


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
        session_factory: Callable[[], AsyncSession] = SessionLocal,
    ) -> None:
        self._session_factory = session_factory

    async def create_pending(
        self,
        *,
        organization_id: int,
        target_email: str,
        operation_type: models.MemberAccessOperationType,
        created_by_user_id: int,
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
        key = _idempotency_key(
            operation_type=operation_type,
            organization_id=organization_id,
            membership_id=membership_id,
            target_email=target_email,
            lock_version=lock_version,
            intent=intent,
        )
        async with self._session_factory() as db:
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
                select(models.MemberAccessOperation)
                .where(*unresolved_conditions)
                .with_for_update()
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
                operation = models.MemberAccessOperation(
                    organization_id=organization_id,
                    membership_id=membership_id,
                    account_id=account_id,
                    target_email=target_email.lower(),
                    operation_type=operation_type,
                    idempotency_key=key,
                    created_by_user_id=created_by_user_id,
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
            await db.commit()
            await db.refresh(operation)
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
        error_category: str | None = None,
        safe_message: str | None = None,
        compensation_attempted: bool = False,
        support_required: bool = False,
    ) -> None:
        async with self._session_factory() as db:
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
            operation.provider_error_category = error_category
            operation.provider_error_safe_message = safe_message
            if compensation_attempted:
                operation.compensation_attempted_at = datetime.now(timezone.utc)
            if support_required:
                operation.support_required_at = datetime.now(timezone.utc)
            await db.commit()
            logger.info(
                "member_access_operation_transitioned",
                operation_id=operation_id,
                operation_status=status.value,
                support_required=support_required,
            )
