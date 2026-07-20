from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import models
from app.config import settings
from app.services import member_webhook_service
from app.services.member_service import ClerkAccessService


def _now() -> datetime:
    return datetime.now(UTC)


def _normalize_token_role(token_role: str | None) -> str | None:
    if token_role in {"admin", "org:admin"}:
        return models.ClerkOrganizationRole.admin.value
    if token_role in {"member", "teacher", "org:member"}:
        return models.ClerkOrganizationRole.member.value
    return token_role


async def reconcile_first_login(
    db: AsyncSession,
    *,
    user: models.User,
    organization: models.Organization | None,
    token_role: str | None,
    clerk_access: ClerkAccessService | None = None,
) -> bool:
    """Accept delayed Clerk webhooks only when a local pending membership already exists."""
    if organization is None or user.clerk_user_id is None:
        return False
    member = await db.scalar(
        select(models.OrganizationMembership)
        .where(
            models.OrganizationMembership.organization_id == organization.id,
            models.OrganizationMembership.account_id == user.id,
            models.OrganizationMembership.lifecycle_status
            == models.MembershipLifecycleStatus.active,
            models.OrganizationMembership.access_status.in_(
                [
                    models.MembershipAccessStatus.pending_invite,
                    models.MembershipAccessStatus.invite_expired,
                    models.MembershipAccessStatus.sync_error,
                ]
            ),
        )
        .options(selectinload(models.OrganizationMembership.teacher_profile))
    )
    if member is None or member.expected_clerk_role is None:
        return False
    if _normalize_token_role(token_role) != member.expected_clerk_role.value:
        return False
    clerk_access = clerk_access or ClerkAccessService()
    provider = await clerk_access.get_membership(
        clerk_org_id=organization.clerk_org_id,
        clerk_user_id=user.clerk_user_id,
    )
    if not provider.ok or _normalize_token_role(provider.role) != member.expected_clerk_role.value:
        member.access_error_category = provider.error_category or "provider_unconfirmed"
        member.access_error_safe_message = (
            provider.safe_message or "Clerk membership could not be confirmed."
        )
        await db.flush()
        return False
    member.access_status = models.MembershipAccessStatus.active
    member.clerk_membership_id = provider.membership_id or member.clerk_membership_id
    member.clerk_invitation_status = (
        models.ClerkInvitationStatus.accepted
        if member.clerk_invitation_id
        else member.clerk_invitation_status
    )
    member.access_error_category = None
    member.access_error_safe_message = None
    member.updated_by_membership_id = user.id
    member.lock_version += 1
    await db.flush()
    return True


async def confirm_provider_membership(
    db: AsyncSession,
    member: models.OrganizationMembership,
    *,
    clerk_access: ClerkAccessService | None = None,
) -> Any | None:
    if member.organization is None:
        member = await db.scalar(
            select(models.OrganizationMembership)
            .where(models.OrganizationMembership.id == member.id)
            .options(
                selectinload(models.OrganizationMembership.organization),
                selectinload(models.OrganizationMembership.account),
            )
        )
    if member is None or member.organization is None or not member.organization.clerk_org_id:
        return None
    if member.account is None or not member.account.clerk_user_id:
        return None
    clerk_access = clerk_access or ClerkAccessService()
    provider = await clerk_access.get_membership(
        clerk_org_id=member.organization.clerk_org_id,
        clerk_user_id=member.account.clerk_user_id,
    )
    if provider.ok:
        member.clerk_membership_id = provider.membership_id or member.clerk_membership_id
    return provider


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
            models.OrganizationMembership.access_status.in_(
                [
                    models.MembershipAccessStatus.pending_invite,
                    models.MembershipAccessStatus.invite_expired,
                    models.MembershipAccessStatus.sync_error,
                ]
            ),
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
            provider.safe_message or "Clerk membership could not be confirmed."
        )
        await db.flush()
        return None
    if _normalize_token_role(provider.role) != member.expected_clerk_role.value:
        member.access_status = models.MembershipAccessStatus.sync_error
        member.access_error_category = "provider_role_mismatch"
        member.access_error_safe_message = "Clerk role does not match the expected local access."
        await db.flush()
        return None

    account = member.account
    account.clerk_user_id = clerk_user_id
    account.clerk_profile_name = name or account.clerk_profile_name
    account.last_clerk_sync_at = _now()
    member.access_status = models.MembershipAccessStatus.active
    member.clerk_membership_id = provider.membership_id or member.clerk_membership_id
    member.clerk_invitation_status = (
        models.ClerkInvitationStatus.accepted
        if member.clerk_invitation_id
        else member.clerk_invitation_status
    )
    member.access_error_category = None
    member.access_error_safe_message = None
    member.updated_by_membership_id = account.id
    member.lock_version += 1
    await db.flush()
    return account


async def run_scheduled_reconciliation(
    db: AsyncSession,
    *,
    limit: int = 100,
    clerk_access: ClerkAccessService | None = None,
) -> dict[str, Any]:
    now = _now()
    expired_result = await db.execute(
        select(models.OrganizationMembership).where(
            models.OrganizationMembership.access_status
            == models.MembershipAccessStatus.pending_invite,
            models.OrganizationMembership.invitation_expires_at.is_not(None),
            models.OrganizationMembership.invitation_expires_at < now,
        )
    )
    expired = expired_result.scalars().all()
    for member in expired:
        member.access_status = models.MembershipAccessStatus.invite_expired
        member.clerk_invitation_status = models.ClerkInvitationStatus.expired

    pending_invite_result = await db.execute(
        select(models.OrganizationMembership)
        .join(models.Organization)
        .where(
            models.OrganizationMembership.access_status
            == models.MembershipAccessStatus.pending_invite,
            models.OrganizationMembership.clerk_invitation_id.is_not(None),
        )
        .options(selectinload(models.OrganizationMembership.organization))
        .limit(limit)
    )
    checked_invites = 0
    clerk_access = clerk_access or ClerkAccessService()
    for member in pending_invite_result.scalars().all():
        if not member.organization.clerk_org_id:
            continue
        checked_invites += 1
        result = await clerk_access.get_invitation(
            clerk_org_id=member.organization.clerk_org_id,
            invitation_id=member.clerk_invitation_id,
        )
        if not result.ok:
            member.access_error_category = result.error_category or "provider_unconfirmed"
            member.access_error_safe_message = (
                result.safe_message or "Clerk invitation state could not be confirmed."
            )
            continue
        if result.invitation_status in {"expired", "revoked"}:
            member.access_status = models.MembershipAccessStatus.invite_expired
            member.clerk_invitation_status = (
                models.ClerkInvitationStatus.revoked
                if result.invitation_status == "revoked"
                else models.ClerkInvitationStatus.expired
            )
        elif result.invitation_status == "accepted":
            member.clerk_invitation_status = models.ClerkInvitationStatus.accepted
        member.invitation_expires_at = result.expires_at or member.invitation_expires_at
        member.access_error_category = None
        member.access_error_safe_message = None

    stale_processing_result = await db.execute(
        select(models.ClerkWebhookEvent).where(
            models.ClerkWebhookEvent.processing_status
            == models.ClerkWebhookProcessingStatus.processing,
            models.ClerkWebhookEvent.last_attempt_at < now - timedelta(minutes=10),
        )
    )
    stale_events = stale_processing_result.scalars().all()
    for event in stale_events:
        event.processing_status = models.ClerkWebhookProcessingStatus.retryable_failed
        event.next_retry_at = now
        event.error_category = "stale_processing"

    retry_result = await db.execute(
        select(models.ClerkWebhookEvent)
        .where(
            models.ClerkWebhookEvent.processing_status
            == models.ClerkWebhookProcessingStatus.retryable_failed,
            models.ClerkWebhookEvent.next_retry_at <= now,
        )
        .order_by(models.ClerkWebhookEvent.created_at)
        .limit(limit)
    )
    retry_events = retry_result.scalars().all()
    for event in retry_events:
        if event.attempt_count >= settings.CLERK_WEBHOOK_MAX_ATTEMPTS:
            event.processing_status = models.ClerkWebhookProcessingStatus.dead_letter
            continue
        await member_webhook_service.process_clerk_event(db, event)

    await db.flush()
    return {
        "expired_invitations": len(expired),
        "provider_invitations_checked": checked_invites,
        "stale_processing_requeued": len(stale_events),
        "retry_events_processed": len(retry_events),
    }
