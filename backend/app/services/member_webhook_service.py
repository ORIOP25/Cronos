from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import models
from app.config import settings
from app.db.tenant import set_async_tenant_context
from app.services import clerk_sync

RETRYABLE_CATEGORIES = {"temporary_failure", "provider_rate_limited"}


def _now() -> datetime:
    return datetime.now(UTC)


def _normalize_email(email: str | None) -> str | None:
    return email.strip().lower() if email else None


def _normalize_role(role: str | None) -> str | None:
    if role in {"admin", "org:admin"}:
        return models.ClerkOrganizationRole.admin.value
    if role in {"member", "teacher", "org:member"}:
        return models.ClerkOrganizationRole.member.value
    return role


def _event_object_id(event_type: str, data: dict[str, Any]) -> str | None:
    if event_type.startswith("organizationMembership."):
        return data.get("id") or data.get("membership_id")
    if event_type.startswith("organizationInvitation."):
        return data.get("id")
    return data.get("id")


def sanitize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data") or {}
    user_data = data.get("public_user_data") or {}
    email_addresses = data.get("email_addresses") or []
    primary_email = None
    primary_email_id = data.get("primary_email_address_id")
    for email in email_addresses:
        if primary_email_id and email.get("id") == primary_email_id:
            primary_email = email.get("email_address")
            break
    if primary_email is None and email_addresses:
        primary_email = email_addresses[0].get("email_address")

    return {
        "type": payload.get("type"),
        "object": payload.get("object"),
        "timestamp": payload.get("timestamp"),
        "data": {
            "id": data.get("id"),
            "email_address": data.get("email_address")
            or user_data.get("identifier")
            or primary_email,
            "first_name": data.get("first_name"),
            "last_name": data.get("last_name"),
            "organization": {
                "id": (data.get("organization") or {}).get("id") or data.get("organization_id"),
                "name": (data.get("organization") or {}).get("name"),
            },
            "name": data.get("name"),
            "public_user_data": {
                "user_id": user_data.get("user_id"),
                "identifier": user_data.get("identifier"),
            },
            "public_metadata": data.get("public_metadata") or {},
            "role": data.get("role"),
            "status": data.get("status"),
            "expires_at": data.get("expires_at"),
        },
    }


async def enqueue_and_process_clerk_event(
    db: AsyncSession,
    *,
    svix_id: str,
    payload: dict[str, Any],
) -> models.ClerkWebhookEvent:
    event_type = payload.get("type") or "unknown"
    data = payload.get("data") or {}
    clerk_org_id = (data.get("organization") or {}).get("id") or data.get("organization_id")
    clerk_user_id = (
        data.get("id")
        if event_type.startswith("user.")
        else (data.get("public_user_data") or {}).get("user_id")
    )
    event = models.ClerkWebhookEvent(
        svix_id=svix_id,
        event_type=event_type,
        clerk_object_id=_event_object_id(event_type, data),
        clerk_org_id=clerk_org_id,
        clerk_user_id=clerk_user_id,
        payload_json=sanitize_payload(payload),
        processing_status=models.ClerkWebhookProcessingStatus.received,
    )
    try:
        async with db.begin_nested():
            db.add(event)
            await db.flush()
    except IntegrityError:
        existing = await db.scalar(
            select(models.ClerkWebhookEvent).where(models.ClerkWebhookEvent.svix_id == svix_id)
        )
        if existing is not None:
            if _should_reprocess(existing):
                await process_clerk_event(db, existing)
            return existing
        raise
    await process_clerk_event(db, event)
    return event


def _should_reprocess(event: models.ClerkWebhookEvent) -> bool:
    if event.processing_status in {
        models.ClerkWebhookProcessingStatus.received,
        models.ClerkWebhookProcessingStatus.retryable_failed,
    }:
        return event.next_retry_at is None or event.next_retry_at <= _now()
    if (
        event.processing_status == models.ClerkWebhookProcessingStatus.processing
        and event.last_attempt_at is not None
        and event.last_attempt_at < _now() - timedelta(minutes=10)
    ):
        event.processing_status = models.ClerkWebhookProcessingStatus.retryable_failed
        event.next_retry_at = _now()
        return True
    return False


async def _set_webhook_tenant_context(db: AsyncSession, clerk_org_id: str | None) -> bool:
    if not clerk_org_id:
        return False
    result = await db.execute(
        text("SELECT app_security.resolve_webhook_organization(:clerk_org_id)"),
        {"clerk_org_id": clerk_org_id},
    )
    organization_id = result.scalar_one_or_none()
    if organization_id is None:
        return False
    await set_async_tenant_context(db, int(organization_id))
    return True


async def process_clerk_event(db: AsyncSession, event: models.ClerkWebhookEvent) -> None:
    if event.processing_status == models.ClerkWebhookProcessingStatus.processed:
        return
    event.processing_status = models.ClerkWebhookProcessingStatus.processing
    event.attempt_count += 1
    event.last_attempt_at = _now()
    await db.flush()
    try:
        event_type = event.event_type
        data = (event.payload_json or {}).get("data") or {}
        clerk_org_id = (data.get("organization") or {}).get("id") or data.get("organization_id")
        if event_type in {"organization.created", "organization.updated"}:
            clerk_org_id = clerk_org_id or data.get("id")
            if clerk_org_id:
                await clerk_sync.ensure_organization_exists(
                    db, clerk_org_id, data.get("name") or "Organization"
                )
            event.processing_status = models.ClerkWebhookProcessingStatus.processed
        elif event_type == "organization.deleted":
            changed = (
                await clerk_sync.deactivate_organization_by_clerk_id(db, data.get("id"))
                if data.get("id")
                else False
            )
            event.processing_status = (
                models.ClerkWebhookProcessingStatus.processed
                if changed
                else models.ClerkWebhookProcessingStatus.ignored
            )
        elif event_type == "user.deleted":
            changed = (
                await clerk_sync.deactivate_user_by_clerk_id(db, data.get("id"))
                if data.get("id")
                else False
            )
            event.processing_status = (
                models.ClerkWebhookProcessingStatus.processed
                if changed
                else models.ClerkWebhookProcessingStatus.ignored
            )
        elif event_type in {"user.created", "user.updated"}:
            event.processing_status = models.ClerkWebhookProcessingStatus.ignored
        elif event_type.startswith(("organizationMembership.", "organizationInvitation.")):
            if not await _set_webhook_tenant_context(db, clerk_org_id):
                event.processing_status = models.ClerkWebhookProcessingStatus.ignored
            elif event_type in {"organizationMembership.created", "organizationMembership.updated"}:
                matched = await _sync_membership(db, event, data)
                if event.processing_status != models.ClerkWebhookProcessingStatus.sync_error:
                    event.processing_status = (
                        models.ClerkWebhookProcessingStatus.processed
                        if matched
                        else models.ClerkWebhookProcessingStatus.ignored
                    )
            elif event_type == "organizationMembership.deleted":
                matched = await _delete_membership(db, data)
                event.processing_status = (
                    models.ClerkWebhookProcessingStatus.processed
                    if matched
                    else models.ClerkWebhookProcessingStatus.ignored
                )
            else:
                matched = await _sync_invitation(db, event_type, data)
                event.processing_status = (
                    models.ClerkWebhookProcessingStatus.processed
                    if matched
                    else models.ClerkWebhookProcessingStatus.ignored
                )
        else:
            event.processing_status = models.ClerkWebhookProcessingStatus.ignored
        event.error_category = None
        event.processed_at = _now()
        if event.processing_status in {
            models.ClerkWebhookProcessingStatus.processed,
            models.ClerkWebhookProcessingStatus.ignored,
        }:
            event.payload_json = {}
    except Exception:
        event.processing_status = (
            models.ClerkWebhookProcessingStatus.dead_letter
            if event.attempt_count >= settings.CLERK_WEBHOOK_MAX_ATTEMPTS
            else models.ClerkWebhookProcessingStatus.retryable_failed
        )
        if event.processing_status == models.ClerkWebhookProcessingStatus.retryable_failed:
            event.next_retry_at = _now() + timedelta(
                seconds=settings.CLERK_WEBHOOK_RETRY_BASE_SECONDS
                * 2 ** max(event.attempt_count - 1, 0)
            )
        event.error_category = "temporary_failure"


async def _sync_organization(db: AsyncSession, data: dict[str, Any]) -> None:
    clerk_org_id = (data.get("organization") or {}).get("id") or data.get("id")
    if not clerk_org_id:
        return
    org = await db.scalar(
        select(models.Organization).where(models.Organization.clerk_org_id == clerk_org_id)
    )
    if org is None:
        org = models.Organization(
            name=data.get("name") or (data.get("organization") or {}).get("name") or "Organization",
            clerk_org_id=clerk_org_id,
            plan_status="active",
        )
        db.add(org)
    elif data.get("name"):
        org.name = data["name"]


async def _archive_organization(db: AsyncSession, data: dict[str, Any]) -> None:
    clerk_org_id = data.get("id")
    org = await db.scalar(
        select(models.Organization).where(models.Organization.clerk_org_id == clerk_org_id)
    )
    if org is not None:
        org.plan_status = models.OrganizationPlanStatus.inactive


async def _load_matching_membership(
    db: AsyncSession,
    *,
    clerk_org_id: str | None,
    email: str | None,
    membership_id: int | None = None,
) -> models.OrganizationMembership | None:
    stmt = (
        select(models.OrganizationMembership)
        .join(models.Organization)
        .join(models.User, models.User.id == models.OrganizationMembership.account_id)
        .options(
            selectinload(models.OrganizationMembership.account),
            selectinload(models.OrganizationMembership.teacher_profile),
        )
        .where(models.Organization.clerk_org_id == clerk_org_id)
    )
    if membership_id:
        stmt = stmt.where(models.OrganizationMembership.id == membership_id)
    elif email:
        stmt = stmt.where(func.lower(models.User.email) == email)
    else:
        return None
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return rows[0] if len(rows) == 1 else None


def _mark_identity_conflict(
    member: models.OrganizationMembership,
    *,
    event: models.ClerkWebhookEvent | None = None,
) -> None:
    member.access_status = models.MembershipAccessStatus.sync_error
    member.access_error_category = "identity_conflict"
    member.access_error_safe_message = "Os dados de acesso precisam de ser confirmados."
    if event is not None:
        event.processing_status = models.ClerkWebhookProcessingStatus.sync_error
        event.error_category = "identity_conflict"


async def _sync_membership(
    db: AsyncSession, event: models.ClerkWebhookEvent, data: dict[str, Any]
) -> bool:
    org_data = data.get("organization") or {}
    clerk_org_id = org_data.get("id")
    user_data = data.get("public_user_data") or {}
    email = _normalize_email(user_data.get("identifier"))
    public_metadata = data.get("public_metadata") or {}
    metadata_member_id = public_metadata.get("membership_id")
    metadata_id = int(metadata_member_id) if str(metadata_member_id or "").isdigit() else None
    member = None
    if metadata_id:
        member = await _load_matching_membership(
            db,
            clerk_org_id=clerk_org_id,
            email=None,
            membership_id=metadata_id,
        )
    if member is None:
        member = await _load_matching_membership(
            db,
            clerk_org_id=clerk_org_id,
            email=email,
            membership_id=None,
        )
    if member is None:
        return False
    webhook_user_id = user_data.get("user_id")
    if not webhook_user_id:
        return False
    if member.account.clerk_user_id and member.account.clerk_user_id != webhook_user_id:
        _mark_identity_conflict(member, event=event)
        return True
    conflicting_account = await db.scalar(
        select(models.User).where(
            models.User.clerk_user_id == webhook_user_id,
            models.User.id != member.account_id,
        )
    )
    if conflicting_account is not None:
        _mark_identity_conflict(member, event=event)
        return True
    expected_role = member.expected_clerk_role.value if member.expected_clerk_role else None
    provider_role = _normalize_role(data.get("role"))
    if expected_role and provider_role != expected_role:
        member.access_status = models.MembershipAccessStatus.sync_error
        member.access_error_category = "provider_role_mismatch"
        member.access_error_safe_message = "Os dados de acesso precisam de ser confirmados."
        event.processing_status = models.ClerkWebhookProcessingStatus.sync_error
        return True
    linked_account = await clerk_sync.ensure_user_exists(
        db,
        clerk_user_id=webhook_user_id,
        email=email,
        name=member.organization_display_name,
        role=provider_role,
        organization_id=member.organization_id,
        teacher_id=member.teacher_profile.id if member.teacher_profile else None,
    )
    if linked_account is None or linked_account.id != member.account_id:
        _mark_identity_conflict(member, event=event)
        return True
    await db.refresh(member.account)
    member.clerk_membership_id = data.get("id") or member.clerk_membership_id
    member.access_status = (
        models.MembershipAccessStatus.active
        if expected_role
        else models.MembershipAccessStatus.none
    )
    member.clerk_invitation_status = (
        models.ClerkInvitationStatus.accepted
        if member.clerk_invitation_id
        else member.clerk_invitation_status
    )
    member.access_error_category = None
    member.access_error_safe_message = None
    return True


async def _delete_membership(db: AsyncSession, data: dict[str, Any]) -> bool:
    clerk_membership_id = data.get("id") or data.get("membership_id")
    clerk_user_id = (data.get("public_user_data") or {}).get("user_id")
    stmt = select(models.OrganizationMembership).options(
        selectinload(models.OrganizationMembership.account)
    )
    if clerk_membership_id:
        stmt = stmt.where(models.OrganizationMembership.clerk_membership_id == clerk_membership_id)
    elif clerk_user_id:
        stmt = stmt.join(models.User).where(models.User.clerk_user_id == clerk_user_id)
    else:
        return False
    member = await db.scalar(stmt)
    if member is None:
        return False
    member.access_status = models.MembershipAccessStatus.blocked
    member.clerk_membership_id = None
    member.access_block_reason = "provider_membership_deleted"
    return True


async def _sync_invitation(db: AsyncSession, event_type: str, data: dict[str, Any]) -> bool:
    invitation_id = data.get("id")
    if not invitation_id:
        return False
    member = await db.scalar(
        select(models.OrganizationMembership).where(
            models.OrganizationMembership.clerk_invitation_id == invitation_id
        )
    )
    if member is None:
        return False
    status_map = {
        "organizationInvitation.created": models.ClerkInvitationStatus.pending,
        "organizationInvitation.accepted": models.ClerkInvitationStatus.accepted,
        "organizationInvitation.revoked": models.ClerkInvitationStatus.revoked,
    }
    member.clerk_invitation_status = status_map[event_type]
    if (
        event_type == "organizationInvitation.revoked"
        and member.access_status == models.MembershipAccessStatus.pending_invite
    ):
        member.access_status = models.MembershipAccessStatus.invite_expired
    return True


async def _sync_user_identity(db: AsyncSession, data: dict[str, Any]) -> bool:
    clerk_user_id = data.get("id")
    email = _normalize_email(data.get("email_address"))
    if not clerk_user_id or not email:
        return False
    result = await db.execute(select(models.User).where(func.lower(models.User.email) == email))
    accounts = result.scalars().all()
    if len(accounts) != 1:
        return False
    account = accounts[0]
    if account.clerk_user_id and account.clerk_user_id != clerk_user_id:
        members = await db.execute(
            select(models.OrganizationMembership).where(
                models.OrganizationMembership.account_id == account.id,
                models.OrganizationMembership.access_status.in_(
                    [
                        models.MembershipAccessStatus.pending_invite,
                        models.MembershipAccessStatus.invite_expired,
                        models.MembershipAccessStatus.active,
                    ]
                ),
            )
        )
        matched_members = members.scalars().all()
        for member in matched_members:
            _mark_identity_conflict(member)
        return bool(matched_members)
    conflicting_account = await db.scalar(
        select(models.User).where(
            models.User.clerk_user_id == clerk_user_id, models.User.id != account.id
        )
    )
    if conflicting_account is not None:
        members = await db.execute(
            select(models.OrganizationMembership).where(
                models.OrganizationMembership.account_id == account.id,
                models.OrganizationMembership.access_status.in_(
                    [
                        models.MembershipAccessStatus.pending_invite,
                        models.MembershipAccessStatus.invite_expired,
                        models.MembershipAccessStatus.active,
                    ]
                ),
            )
        )
        matched_members = members.scalars().all()
        for member in matched_members:
            _mark_identity_conflict(member)
        return bool(matched_members)
    profile_name = " ".join(filter(None, [data.get("first_name"), data.get("last_name")])) or None
    linked_account = await clerk_sync.ensure_user_exists(
        db,
        clerk_user_id=clerk_user_id,
        email=email,
        name=profile_name,
    )
    if linked_account is None or linked_account.id != account.id:
        return False
    await db.refresh(account)
    return True


async def _block_deleted_user(db: AsyncSession, data: dict[str, Any]) -> bool:
    clerk_user_id = data.get("id")
    if not clerk_user_id:
        return False
    result = await db.execute(
        select(models.OrganizationMembership)
        .join(models.User)
        .where(models.User.clerk_user_id == clerk_user_id)
        .options(selectinload(models.OrganizationMembership.account))
    )
    members = result.scalars().all()
    for member in members:
        member.access_status = models.MembershipAccessStatus.blocked
        member.access_block_reason = "provider_user_deleted"
        member.clerk_membership_id = None
    return bool(members)
