from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import models
from app.config import settings
from app.db.tenant import set_async_tenant_context
from app.services import member_webhook_service
from app.services.clerk_access_service import ClerkAccessService


def _now() -> datetime:
    return datetime.now(UTC)


def _normalize_token_role(token_role: str | None) -> str | None:
    if token_role in {"admin", "org:admin"}:
        return models.ClerkOrganizationRole.admin.value
    if token_role in {"member", "teacher", "org:member"}:
        return models.ClerkOrganizationRole.member.value
    return token_role


async def reconcile_first_login_by_email(
    db: AsyncSession,
    *,
    clerk_user_id: str,
    email: str | None,
    name: str | None,
    organization: models.Organization,
    token_role: str | None,
    clerk_access: ClerkAccessService | None = None,
) -> models.User | None:
    """Link a Clerk user to the unique pending local member when webhooks lag."""
    if not email:
        return None
    normalized_email = email.strip().lower()
    member = await db.scalar(
        select(models.OrganizationMembership)
        .join(models.User, models.User.id == models.OrganizationMembership.account_id)
        .where(
            models.OrganizationMembership.organization_id == organization.id,
            models.OrganizationMembership.lifecycle_status
            == models.MembershipLifecycleStatus.active,
            models.OrganizationMembership.access_status
            == models.MembershipAccessStatus.pending_invite,
            models.User.clerk_user_id.is_(None),
            models.User.email == normalized_email,
        )
        .options(
            selectinload(models.OrganizationMembership.account),
            selectinload(models.OrganizationMembership.organization),
        )
    )
    if member is None or member.expected_clerk_role is None:
        return None
    if _normalize_token_role(token_role) != member.expected_clerk_role.value:
        return None

    clerk_access = clerk_access or ClerkAccessService()
    provider = await clerk_access.get_membership(
        clerk_org_id=organization.clerk_org_id,
        clerk_user_id=clerk_user_id,
    )
    if not provider.ok:
        member.access_error_category = provider.error_category or "provider_unconfirmed"
        member.access_error_safe_message = (
            provider.safe_message or "Não foi possível confirmar o estado de acesso."
        )
        await db.flush()
        return None
    if _normalize_token_role(provider.role) != member.expected_clerk_role.value:
        member.access_status = models.MembershipAccessStatus.sync_error
        member.access_error_category = "provider_role_mismatch"
        member.access_error_safe_message = "Os dados de acesso precisam de ser confirmados."
        await db.flush()
        return None

    account = member.account
    linked_account_id = await db.scalar(
        text(
            """
            SELECT id
            FROM app_security.ensure_user(
                :clerk_user_id, :email, :display_name, :role,
                :organization_id, NULL
            )
            """
        ),
        {
            "clerk_user_id": clerk_user_id,
            "email": normalized_email,
            "display_name": name or member.organization_display_name,
            "role": member.expected_clerk_role.value,
            "organization_id": organization.id,
        },
    )
    if linked_account_id != account.id:
        member.access_status = models.MembershipAccessStatus.sync_error
        member.access_error_category = "identity_conflict"
        member.access_error_safe_message = "Os dados de acesso precisam de ser confirmados."
        await db.flush()
        return None
    await db.refresh(account)
    member.access_status = models.MembershipAccessStatus.active
    member.clerk_membership_id = provider.membership_id or member.clerk_membership_id
    member.clerk_invitation_status = (
        models.ClerkInvitationStatus.accepted
        if member.clerk_invitation_id
        else member.clerk_invitation_status
    )
    member.access_error_category = None
    member.access_error_safe_message = None
    member.updated_by_membership_id = member.id
    member.lock_version += 1
    await db.flush()
    return account


async def _expire_pending_invitations(
    db: AsyncSession,
    *,
    organization_id: int,
    now: datetime,
) -> int:
    result = await db.execute(
        select(models.OrganizationMembership).where(
            models.OrganizationMembership.organization_id == organization_id,
            models.OrganizationMembership.access_status
            == models.MembershipAccessStatus.pending_invite,
            models.OrganizationMembership.invitation_expires_at.is_not(None),
            models.OrganizationMembership.invitation_expires_at < now,
        )
    )
    members = result.scalars().all()
    for member in members:
        member.access_status = models.MembershipAccessStatus.invite_expired
        member.clerk_invitation_status = models.ClerkInvitationStatus.expired
    return len(members)


async def _check_pending_invitations(
    db: AsyncSession,
    *,
    organization_id: int,
    limit: int,
    clerk_access: ClerkAccessService,
) -> int:
    result = await db.execute(
        select(models.OrganizationMembership)
        .join(models.Organization)
        .where(
            models.OrganizationMembership.organization_id == organization_id,
            models.OrganizationMembership.access_status
            == models.MembershipAccessStatus.pending_invite,
            models.OrganizationMembership.clerk_invitation_id.is_not(None),
        )
        .options(selectinload(models.OrganizationMembership.organization))
        .limit(limit)
    )
    checked = 0
    for member in result.scalars().all():
        if not member.organization.clerk_org_id:
            continue
        checked += 1
        invitation = await clerk_access.get_invitation(
            clerk_org_id=member.organization.clerk_org_id,
            invitation_id=member.clerk_invitation_id,
        )
        if not invitation.ok:
            member.access_error_category = invitation.error_category or "provider_unconfirmed"
            member.access_error_safe_message = (
                invitation.safe_message or "Não foi possível confirmar o estado do convite."
            )
            continue
        if invitation.invitation_status in {"expired", "revoked"}:
            member.access_status = models.MembershipAccessStatus.invite_expired
            member.clerk_invitation_status = (
                models.ClerkInvitationStatus.revoked
                if invitation.invitation_status == "revoked"
                else models.ClerkInvitationStatus.expired
            )
        elif invitation.invitation_status == "accepted":
            member.clerk_invitation_status = models.ClerkInvitationStatus.accepted
        member.invitation_expires_at = invitation.expires_at or member.invitation_expires_at
        member.access_error_category = None
        member.access_error_safe_message = None
    return checked


async def _requeue_stale_webhooks(
    db: AsyncSession,
    *,
    organization_id: int,
    now: datetime,
) -> int:
    result = await db.execute(
        select(models.ClerkWebhookEvent)
        .join(
            models.Organization,
            models.Organization.clerk_org_id == models.ClerkWebhookEvent.clerk_org_id,
        )
        .where(
            models.Organization.id == organization_id,
            models.ClerkWebhookEvent.processing_status
            == models.ClerkWebhookProcessingStatus.processing,
            models.ClerkWebhookEvent.last_attempt_at < now - timedelta(minutes=10),
        )
    )
    events = result.scalars().all()
    for event in events:
        event.processing_status = models.ClerkWebhookProcessingStatus.retryable_failed
        event.next_retry_at = now
        event.error_category = "stale_processing"
    return len(events)


async def _process_retryable_webhooks(
    db: AsyncSession,
    *,
    organization_id: int,
    now: datetime,
    limit: int,
) -> int:
    result = await db.execute(
        select(models.ClerkWebhookEvent)
        .join(
            models.Organization,
            models.Organization.clerk_org_id == models.ClerkWebhookEvent.clerk_org_id,
        )
        .where(
            models.Organization.id == organization_id,
            models.ClerkWebhookEvent.processing_status
            == models.ClerkWebhookProcessingStatus.retryable_failed,
            models.ClerkWebhookEvent.next_retry_at <= now,
        )
        .order_by(models.ClerkWebhookEvent.created_at)
        .limit(limit)
    )
    events = result.scalars().all()
    for event in events:
        if event.attempt_count >= settings.CLERK_WEBHOOK_MAX_ATTEMPTS:
            event.processing_status = models.ClerkWebhookProcessingStatus.dead_letter
            continue
        await member_webhook_service.process_clerk_event(db, event)
    return len(events)


async def run_scheduled_reconciliation(
    db: AsyncSession,
    *,
    organization_id: int,
    limit: int = 100,
    clerk_access: ClerkAccessService | None = None,
) -> dict[str, Any]:
    await set_async_tenant_context(db, organization_id)
    now = _now()
    expired_count = await _expire_pending_invitations(db, organization_id=organization_id, now=now)
    checked_count = await _check_pending_invitations(
        db,
        organization_id=organization_id,
        limit=limit,
        clerk_access=clerk_access or ClerkAccessService(),
    )
    stale_count = await _requeue_stale_webhooks(db, organization_id=organization_id, now=now)
    retry_count = await _process_retryable_webhooks(
        db, organization_id=organization_id, now=now, limit=limit
    )
    await db.flush()
    return {
        "expired_invitations": expired_count,
        "provider_invitations_checked": checked_count,
        "stale_processing_requeued": stale_count,
        "retry_events_processed": retry_count,
    }
