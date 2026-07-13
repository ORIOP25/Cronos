from __future__ import annotations

from datetime import datetime, timezone

import structlog
from fastapi import HTTPException, status
from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import models, schemas
from app.services.clerk_access_service import (
    SAFE_PROVIDER_ERROR,
    ClerkAccessResult,
    ClerkAccessService,
    normalize_clerk_datetime,
)
from app.services.member_access_operation_service import (
    MemberAccessOperationService,
    UnresolvedAccessOperationError,
)
from app.services.scheduler_state_service import record_scheduler_change


logger = structlog.get_logger(__name__)


def member_error(
    status_code: int,
    code: str,
    message: str,
    *,
    category: str | None = None,
    retryable: bool = False,
    support_required: bool = False,
    fields: dict[str, str] | None = None,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "code": code,
            "category": category or code,
            "message": message,
            "retryable": retryable,
            "support_required": support_required,
            "fields": fields or {},
        },
    )


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _capability_values(caps: list[str]) -> set[models.MembershipCapability]:
    return {models.MembershipCapability(capability) for capability in caps}


def _expected_role(
    capabilities: set[models.MembershipCapability],
    teacher_access_mode: models.TeacherAccessMode | None,
) -> models.ClerkOrganizationRole | None:
    if models.MembershipCapability.admin in capabilities:
        return models.ClerkOrganizationRole.admin
    if models.MembershipCapability.teacher in capabilities and teacher_access_mode == models.TeacherAccessMode.platform:
        return models.ClerkOrganizationRole.member
    return None


def _access_status_for_draft(
    capabilities: set[models.MembershipCapability],
    teacher_access_mode: models.TeacherAccessMode | None,
) -> models.MembershipAccessStatus:
    return (
        models.MembershipAccessStatus.pending_invite
        if _expected_role(capabilities, teacher_access_mode) is not None
        else models.MembershipAccessStatus.none
    )


def _has_provider_outage(member: models.OrganizationMembership) -> bool:
    return member.access_error_category in {"provider_rate_limited", "provider_unconfirmed"}


def _provider_state(member: models.OrganizationMembership) -> str:
    if member.expected_clerk_role is None:
        return "not_required"
    return "unconfirmed" if _has_provider_outage(member) else "confirmed"


def _member_actions(member: models.OrganizationMembership, teacher: models.Teacher | None, *, has_history: bool = False) -> schemas.MemberActionFlags:
    return schemas.MemberActionFlags(
        can_edit=member.lifecycle_status == models.MembershipLifecycleStatus.active
        and member.access_status != models.MembershipAccessStatus.sync_error,
        can_remove=member.lifecycle_status == models.MembershipLifecycleStatus.active,
        remove_effect="archive" if has_history or member.access_status != models.MembershipAccessStatus.none else "hard_delete",
        can_restore=member.lifecycle_status == models.MembershipLifecycleStatus.archived,
        can_resend_invite=member.lifecycle_status == models.MembershipLifecycleStatus.active
        and member.access_status in {models.MembershipAccessStatus.pending_invite, models.MembershipAccessStatus.invite_expired}
        and not _has_provider_outage(member),
        can_retry_sync=member.access_status == models.MembershipAccessStatus.sync_error,
        provider_state=_provider_state(member),
    )


def _to_read(member: models.OrganizationMembership, *, has_history: bool = False) -> schemas.MemberRead:
    account = member.account
    teacher = member.teacher_profile
    caps = sorted(cap.capability.value for cap in member.capabilities)
    actions = _member_actions(member, teacher, has_history=has_history)
    return schemas.MemberRead(
        id=member.id,
        account_id=member.account_id,
        organization_id=member.organization_id,
        organization_display_name=member.organization_display_name,
        email=account.email,
        capabilities=caps,
        lifecycle_status=member.lifecycle_status.value,
        access_status=member.access_status.value,
        teacher_access_mode=member.teacher_access_mode.value if member.teacher_access_mode else None,
        expected_clerk_role=member.expected_clerk_role.value if member.expected_clerk_role else None,
        clerk_user_id=account.clerk_user_id,
        clerk_membership_id=member.clerk_membership_id,
        clerk_invitation_id=member.clerk_invitation_id,
        clerk_invitation_status=member.clerk_invitation_status.value if member.clerk_invitation_status else None,
        invitation_expires_at=member.invitation_expires_at,
        teacher_id=teacher.id if teacher else None,
        subject_ids=teacher.subject_ids if teacher else [],
        access_error_category=member.access_error_category,
        access_error_safe_message=member.access_error_safe_message,
        provider_state=actions.provider_state,
        remove_effect=actions.remove_effect,
        actions=actions,
        lock_version=member.lock_version,
    )


async def _get_or_create_account(db: AsyncSession, email: str, display_name: str) -> models.User:
    normalized = _normalize_email(email)
    account = await db.scalar(select(models.User).where(func.lower(models.User.email) == normalized))
    if account is not None:
        return account
    account = models.User(
        email=normalized,
        name=display_name.strip(),
        organization_id=None,
        role=None,
        teacher_id=None,
        is_active=None,
    )
    db.add(account)
    await db.flush()
    return account


async def _load_member(db: AsyncSession, organization_id: int, member_id: int) -> models.OrganizationMembership | None:
    return await db.scalar(
        select(models.OrganizationMembership)
        .where(
            models.OrganizationMembership.id == member_id,
            models.OrganizationMembership.organization_id == organization_id,
        )
        .options(
            selectinload(models.OrganizationMembership.account),
            selectinload(models.OrganizationMembership.capabilities),
            selectinload(models.OrganizationMembership.teacher_profile).selectinload(models.Teacher.subjects),
        )
    )


async def _teacher_ids_with_history(db: AsyncSession, organization_id: int, teacher_ids: list[int]) -> set[int]:
    teacher_ids = [teacher_id for teacher_id in teacher_ids if teacher_id]
    if not teacher_ids:
        return set()
    simple_checks = [
        (models.Availability, models.Availability.teacher_id),
        (models.TeacherWeeklyTimesheet, models.TeacherWeeklyTimesheet.teacher_id),
        (models.ClassSubjectLink, models.ClassSubjectLink.teacher_id),
        (models.Lesson, models.Lesson.teacher_id),
        (models.ScheduleDraftBlock, models.ScheduleDraftBlock.teacher_id),
        (models.ScheduleDiffEntry, models.ScheduleDiffEntry.teacher_id),
        (models.ActiveScheduleBlock, models.ActiveScheduleBlock.teacher_id),
        (models.PlannedRecoveryLink, models.PlannedRecoveryLink.teacher_id),
        (models.OperationalScheduleBlock, models.OperationalScheduleBlock.teacher_id),
    ]
    historical: set[int] = set()
    for model, column in simple_checks:
        rows = await db.execute(
            select(column).where(model.organization_id == organization_id, column.in_(teacher_ids)).distinct()
        )
        historical.update(rows.scalars().all())
    multi_checks = [
        (models.Substitution, [models.Substitution.original_teacher_id, models.Substitution.substitute_teacher_id]),
        (
            models.LessonOccurrence,
            [
                models.LessonOccurrence.substitute_teacher_id,
                models.LessonOccurrence.planned_teacher_id,
                models.LessonOccurrence.executed_teacher_id,
            ],
        ),
    ]
    for model, columns in multi_checks:
        for column in columns:
            rows = await db.execute(
                select(column).where(model.organization_id == organization_id, column.in_(teacher_ids)).distinct()
            )
            historical.update(rows.scalars().all())
    return historical


async def _organization(db: AsyncSession, organization_id: int) -> models.Organization:
    org = await db.get(models.Organization, organization_id)
    if org is None:
        raise member_error(404, "organization_not_found", "Organization not found.")
    return org


def _require_clerk_org(org: models.Organization, current_admin: models.User) -> str:
    if not org.clerk_org_id or not current_admin.clerk_user_id:
        raise member_error(503, "clerk_configuration_required", SAFE_PROVIDER_ERROR)
    return org.clerk_org_id


async def _replace_capabilities(
    db: AsyncSession,
    member: models.OrganizationMembership,
    capabilities: set[models.MembershipCapability],
) -> None:
    await db.execute(
        delete(models.OrganizationMembershipCapability).where(
            models.OrganizationMembershipCapability.organization_membership_id == member.id
        )
    )
    db.add_all(
        models.OrganizationMembershipCapability(organization_membership_id=member.id, capability=capability)
        for capability in sorted(capabilities, key=lambda cap: cap.value)
    )
    await db.flush()


async def _validate_subject_ids(db: AsyncSession, organization_id: int, subject_ids: list[int]) -> list[int]:
    if not subject_ids:
        return []
    result = await db.execute(
        select(models.Subject.id).where(
            models.Subject.organization_id == organization_id,
            models.Subject.id.in_(subject_ids),
        )
    )
    valid_subject_ids = [row[0] for row in result.all()]
    if len(valid_subject_ids) != len(set(subject_ids)):
        raise member_error(
            422,
            "validation_error",
            "Invalid competencies.",
            fields={"subject_ids": "One or more subjects do not belong to the organization."},
        )
    return valid_subject_ids


async def _sync_teacher_profile(
    db: AsyncSession,
    member: models.OrganizationMembership,
    *,
    capabilities: set[models.MembershipCapability],
    subject_ids: list[int] | None,
    current_admin: models.User,
) -> None:
    wants_teacher = models.MembershipCapability.teacher in capabilities
    teacher = await db.scalar(
        select(models.Teacher)
        .where(
            models.Teacher.organization_id == member.organization_id,
            models.Teacher.organization_membership_id == member.id,
        )
        .options(selectinload(models.Teacher.availabilities), selectinload(models.Teacher.timesheets))
    )
    if wants_teacher and teacher is None:
        teacher = models.Teacher(
            name=member.organization_display_name,
            organization_id=member.organization_id,
            organization_membership_id=member.id,
        )
        db.add(teacher)
        await db.flush()
        member.teacher_profile = teacher
        await record_scheduler_change(
            db,
            member.organization_id,
            entity_type="TEACHER_RESOURCE",
            entity_id=teacher.id,
            operation=models.SchedulerStateChangeOperation.CREATE,
            before=None,
            after={"subject_ids": sorted(subject_ids or [])},
            changed_by_user_id=current_admin.id,
            active_resource=False,
        )
    elif not wants_teacher and teacher is not None:
        has_history = bool(teacher.availabilities or teacher.timesheets)
        if has_history:
            teacher.archived_at = datetime.now(timezone.utc)
            teacher.organization_membership_id = None
        else:
            await db.delete(teacher)
        return

    if wants_teacher and teacher is not None:
        teacher.name = member.organization_display_name
        if subject_ids is not None:
            valid_subject_ids = await _validate_subject_ids(db, member.organization_id, subject_ids)
            await db.execute(
                delete(models.teacher_subject_link).where(
                    models.teacher_subject_link.c.organization_id == member.organization_id,
                    models.teacher_subject_link.c.teacher_id == teacher.id,
                )
            )
            if valid_subject_ids:
                await db.execute(
                    insert(models.teacher_subject_link).values(
                        [
                            {
                                "organization_id": member.organization_id,
                                "teacher_id": teacher.id,
                                "subject_id": subject_id,
                            }
                            for subject_id in valid_subject_ids
                        ]
                    )
                )


async def _active_admin_count(db: AsyncSession, organization_id: int, *, exclude_member_id: int | None = None) -> int:
    stmt = (
        select(func.count())
        .select_from(models.OrganizationMembership)
        .join(models.OrganizationMembershipCapability)
        .join(models.User, models.User.id == models.OrganizationMembership.account_id)
        .where(
            models.OrganizationMembership.organization_id == organization_id,
            models.OrganizationMembership.lifecycle_status == models.MembershipLifecycleStatus.active,
            models.OrganizationMembership.access_status == models.MembershipAccessStatus.active,
            models.OrganizationMembershipCapability.capability == models.MembershipCapability.admin,
            models.User.clerk_user_id.is_not(None),
        )
    )
    if exclude_member_id is not None:
        stmt = stmt.where(models.OrganizationMembership.id != exclude_member_id)
    return await db.scalar(stmt) or 0


async def _assert_can_remove_admin_capability(
    db: AsyncSession,
    member: models.OrganizationMembership,
    current_admin: models.User,
    *,
    next_capabilities: set[models.MembershipCapability],
) -> None:
    current_caps = {cap.capability for cap in member.capabilities}
    removes_admin = models.MembershipCapability.admin in current_caps and models.MembershipCapability.admin not in next_capabilities
    if not removes_admin:
        return
    if member.account_id == current_admin.id:
        raise member_error(409, "self_admin_change_blocked", "You cannot remove your own admin access.")
    if await _active_admin_count(db, member.organization_id, exclude_member_id=member.id) == 0:
        raise member_error(409, "last_active_admin_blocked", "At least one active admin must remain.")


def _raise_provider_failure(result: ClerkAccessResult) -> None:
    raise member_error(
        status.HTTP_429_TOO_MANY_REQUESTS if result.retryable else status.HTTP_502_BAD_GATEWAY,
        result.error_category or "provider_error",
        result.safe_message or SAFE_PROVIDER_ERROR,
        retryable=result.retryable,
    )


def _raise_unresolved_operation(exc: UnresolvedAccessOperationError) -> None:
    raise member_error(
        status.HTTP_409_CONFLICT,
        "member_access_operation_unresolved",
        "A previous access change still requires reconciliation. Contact support.",
        support_required=True,
    ) from exc


def _raise_local_commit_failure(*, support_required: bool) -> None:
    raise member_error(
        status.HTTP_503_SERVICE_UNAVAILABLE if support_required else status.HTTP_500_INTERNAL_SERVER_ERROR,
        "member_access_support_required" if support_required else "member_access_commit_failed",
        (
            "Access synchronization requires support before another change can be attempted."
            if support_required
            else "The member could not be saved. The Clerk invitation was revoked; please try again."
        ),
        retryable=not support_required,
        support_required=support_required,
    )


def _access_snapshot(member: models.OrganizationMembership) -> dict:
    return {
        "lifecycle_status": member.lifecycle_status.value,
        "access_status": member.access_status.value,
        "teacher_access_mode": (
            member.teacher_access_mode.value if member.teacher_access_mode else None
        ),
        "expected_clerk_role": (
            member.expected_clerk_role.value if member.expected_clerk_role else None
        ),
        "clerk_membership_id": member.clerk_membership_id,
        "clerk_invitation_id": member.clerk_invitation_id,
        "clerk_invitation_status": (
            member.clerk_invitation_status.value if member.clerk_invitation_status else None
        ),
        "lock_version": member.lock_version,
    }


async def _send_invitation(
    db: AsyncSession,
    *,
    member: models.OrganizationMembership,
    current_admin: models.User,
    clerk_access: ClerkAccessService,
    operation_type: models.MemberAccessOperationType,
    operation_service: MemberAccessOperationService | None = None,
    previous_snapshot: dict | None = None,
) -> None:
    org = await _organization(db, member.organization_id)
    clerk_org_id = _require_clerk_org(org, current_admin)
    operation_service = operation_service or MemberAccessOperationService()
    organization_id = member.organization_id
    membership_id = member.id
    account_id = member.account_id
    target_email = member.account.email
    admin_id = current_admin.id
    admin_clerk_user_id = current_admin.clerk_user_id
    expected_role = member.expected_clerk_role
    capabilities = {capability.capability for capability in member.capabilities}
    intent = {
        "capabilities": sorted(capability.value for capability in capabilities),
        "expected_role": expected_role.value if expected_role else None,
        "teacher_access_mode": (
            member.teacher_access_mode.value if member.teacher_access_mode else None
        ),
    }
    try:
        operation = await operation_service.create_pending(
            organization_id=organization_id,
            target_email=target_email,
            operation_type=operation_type,
            created_by_user_id=admin_id,
            intended_capabilities=capabilities,
            intended_role=expected_role,
            intent=intent,
            membership_id=membership_id,
            account_id=account_id,
            lock_version=member.lock_version,
            previous_snapshot=previous_snapshot or _access_snapshot(member),
            clerk_org_id=clerk_org_id,
            clerk_user_id=member.account.clerk_user_id,
            clerk_membership_id=member.clerk_membership_id,
            clerk_invitation_id=member.clerk_invitation_id,
        )
    except UnresolvedAccessOperationError as exc:
        _raise_unresolved_operation(exc)

    result = await clerk_access.create_organization_invitation(
        clerk_org_id=clerk_org_id,
        email=target_email,
        role=expected_role.value,
        inviter_user_id=admin_clerk_user_id,
        membership_id=membership_id,
    )
    if not result.ok:
        status_after_failure = models.MemberAccessOperationStatus.failed
        support_required = False
        if result.invitation_id:
            compensation = await clerk_access.revoke_organization_invitation(
                clerk_org_id=clerk_org_id,
                invitation_id=result.invitation_id,
                requesting_user_id=admin_clerk_user_id,
            )
            status_after_failure = (
                models.MemberAccessOperationStatus.compensated
                if compensation.ok
                else models.MemberAccessOperationStatus.support_required
            )
            support_required = not compensation.ok
        await operation_service.transition(
            operation.id,
            status_after_failure,
            clerk_invitation_id=result.invitation_id,
            error_category=result.error_category,
            safe_message=result.safe_message,
            compensation_attempted=bool(result.invitation_id),
            support_required=support_required,
        )
        if support_required:
            _raise_local_commit_failure(support_required=True)
        _raise_provider_failure(result)
    await operation_service.transition(
        operation.id,
        models.MemberAccessOperationStatus.clerk_succeeded,
        clerk_invitation_id=result.invitation_id,
    )
    member.clerk_invitation_id = result.invitation_id
    member.clerk_invitation_status = models.ClerkInvitationStatus.pending
    member.invitation_expires_at = normalize_clerk_datetime(result.expires_at)
    member.access_status = models.MembershipAccessStatus.pending_invite
    member.access_error_category = None
    member.access_error_safe_message = None
    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        compensation = await clerk_access.revoke_organization_invitation(
            clerk_org_id=clerk_org_id,
            invitation_id=result.invitation_id,
            requesting_user_id=admin_clerk_user_id,
        )
        support_required = not compensation.ok
        await operation_service.transition(
            operation.id,
            (
                models.MemberAccessOperationStatus.compensated
                if compensation.ok
                else models.MemberAccessOperationStatus.support_required
            ),
            clerk_invitation_id=result.invitation_id,
            error_category=compensation.error_category if support_required else "local_commit_failed",
            safe_message=compensation.safe_message if support_required else type(exc).__name__,
            compensation_attempted=True,
            support_required=support_required,
        )
        logger.error(
            "member_invitation_local_commit_failed",
            operation_id=operation.id,
            organization_id=organization_id,
            membership_id=membership_id,
            compensation_succeeded=compensation.ok,
            error_type=type(exc).__name__,
        )
        _raise_local_commit_failure(support_required=support_required)
    await operation_service.transition(
        operation.id,
        models.MemberAccessOperationStatus.local_committed,
        membership_id=membership_id,
        account_id=account_id,
        clerk_invitation_id=result.invitation_id,
    )


async def _change_provider_role(
    db: AsyncSession,
    *,
    member: models.OrganizationMembership,
    current_admin: models.User,
    clerk_access: ClerkAccessService,
    operation_type: models.MemberAccessOperationType,
    previous_role: models.ClerkOrganizationRole | None,
    previous_snapshot: dict,
    operation_service: MemberAccessOperationService | None = None,
) -> None:
    org = await _organization(db, member.organization_id)
    clerk_org_id = _require_clerk_org(org, current_admin)
    target_role = member.expected_clerk_role
    clerk_user_id = member.account.clerk_user_id
    if target_role is None or clerk_user_id is None:
        raise RuntimeError("A Clerk user and target role are required for a role change.")
    operation_service = operation_service or MemberAccessOperationService()
    capabilities = {item.capability for item in member.capabilities}
    try:
        operation = await operation_service.create_pending(
            organization_id=member.organization_id,
            target_email=member.account.email,
            operation_type=operation_type,
            created_by_user_id=current_admin.id,
            intended_capabilities=capabilities,
            intended_role=target_role,
            intent={"target_role": target_role.value},
            membership_id=member.id,
            account_id=member.account_id,
            lock_version=member.lock_version,
            previous_snapshot=previous_snapshot,
            clerk_org_id=clerk_org_id,
            clerk_user_id=clerk_user_id,
            clerk_membership_id=member.clerk_membership_id,
        )
    except UnresolvedAccessOperationError as exc:
        _raise_unresolved_operation(exc)
    result = await clerk_access.change_membership_role(
        clerk_org_id=clerk_org_id,
        clerk_user_id=clerk_user_id,
        role=target_role.value,
    )
    if not result.ok:
        await operation_service.transition(
            operation.id,
            models.MemberAccessOperationStatus.failed,
            error_category=result.error_category,
            safe_message=result.safe_message,
        )
        _raise_provider_failure(result)
    await operation_service.transition(
        operation.id,
        models.MemberAccessOperationStatus.clerk_succeeded,
        clerk_membership_id=result.membership_id,
    )
    member.clerk_membership_id = result.membership_id or member.clerk_membership_id
    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        compensation = ClerkAccessResult(error_category="compensation_unavailable")
        if previous_role is not None:
            compensation = await clerk_access.change_membership_role(
                clerk_org_id=clerk_org_id,
                clerk_user_id=clerk_user_id,
                role=previous_role.value,
            )
        support_required = not compensation.ok
        await operation_service.transition(
            operation.id,
            (
                models.MemberAccessOperationStatus.compensated
                if compensation.ok
                else models.MemberAccessOperationStatus.support_required
            ),
            clerk_membership_id=result.membership_id,
            error_category=(
                compensation.error_category if support_required else "local_commit_failed"
            ),
            safe_message=(
                compensation.safe_message if support_required else type(exc).__name__
            ),
            compensation_attempted=previous_role is not None,
            support_required=support_required,
        )
        logger.error(
            "member_role_local_commit_failed",
            operation_id=operation.id,
            organization_id=member.organization_id,
            membership_id=member.id,
            compensation_succeeded=compensation.ok,
            error_type=type(exc).__name__,
        )
        _raise_local_commit_failure(support_required=support_required)
    await operation_service.transition(
        operation.id,
        models.MemberAccessOperationStatus.local_committed,
        clerk_membership_id=member.clerk_membership_id,
    )


async def _revoke_provider_access(
    db: AsyncSession,
    *,
    member: models.OrganizationMembership,
    current_admin: models.User,
    clerk_access: ClerkAccessService,
    operation_service: MemberAccessOperationService | None = None,
) -> None:
    org = await _organization(db, member.organization_id)
    if not org.clerk_org_id:
        return
    operation_service = operation_service or MemberAccessOperationService()
    organization_id = member.organization_id
    membership_id = member.id
    account_id = member.account_id
    target_email = member.account.email
    admin_id = current_admin.id
    capabilities = {item.capability for item in member.capabilities}

    async def revoke(*, operation_type, provider_call, apply_local, intent) -> None:
        try:
            operation = await operation_service.create_pending(
                organization_id=organization_id,
                target_email=target_email,
                operation_type=operation_type,
                created_by_user_id=admin_id,
                intended_capabilities=capabilities,
                intended_role=None,
                intent=intent,
                membership_id=membership_id,
                account_id=account_id,
                lock_version=member.lock_version,
                previous_snapshot=_access_snapshot(member),
                clerk_org_id=org.clerk_org_id,
                clerk_user_id=member.account.clerk_user_id,
                clerk_membership_id=member.clerk_membership_id,
                clerk_invitation_id=member.clerk_invitation_id,
            )
        except UnresolvedAccessOperationError as exc:
            _raise_unresolved_operation(exc)
        result = await provider_call()
        if not result.ok:
            await operation_service.transition(
                operation.id,
                models.MemberAccessOperationStatus.failed,
                error_category=result.error_category,
                safe_message=result.safe_message,
            )
            _raise_provider_failure(result)
        await operation_service.transition(
            operation.id,
            models.MemberAccessOperationStatus.clerk_succeeded,
        )
        apply_local()
        try:
            await db.commit()
        except Exception as exc:
            await db.rollback()
            await operation_service.transition(
                operation.id,
                models.MemberAccessOperationStatus.support_required,
                error_category="local_commit_failed",
                safe_message=type(exc).__name__,
                support_required=True,
            )
            logger.error(
                "member_revoke_local_commit_failed",
                operation_id=operation.id,
                organization_id=organization_id,
                membership_id=membership_id,
                error_type=type(exc).__name__,
            )
            _raise_local_commit_failure(support_required=True)
        await operation_service.transition(
            operation.id,
            models.MemberAccessOperationStatus.local_committed,
        )

    if (
        member.clerk_invitation_id
        and member.clerk_invitation_status == models.ClerkInvitationStatus.pending
    ):
        invitation_id = member.clerk_invitation_id

        async def revoke_invitation():
            return await clerk_access.revoke_organization_invitation(
                clerk_org_id=org.clerk_org_id,
                invitation_id=invitation_id,
                requesting_user_id=current_admin.clerk_user_id,
            )

        def apply_invitation_revoke() -> None:
            member.clerk_invitation_status = models.ClerkInvitationStatus.revoked
            member.access_status = models.MembershipAccessStatus.invite_expired

        await revoke(
            operation_type=models.MemberAccessOperationType.revoke_invitation,
            provider_call=revoke_invitation,
            apply_local=apply_invitation_revoke,
            intent={"invitation_id": invitation_id},
        )
    if member.account.clerk_user_id and (
        member.clerk_membership_id
        or member.access_status == models.MembershipAccessStatus.active
    ):
        clerk_user_id = member.account.clerk_user_id
        clerk_membership_id = member.clerk_membership_id

        async def revoke_membership():
            return await clerk_access.revoke_organization_membership(
                clerk_org_id=org.clerk_org_id,
                clerk_user_id=clerk_user_id,
                clerk_membership_id=clerk_membership_id,
            )

        def apply_membership_revoke() -> None:
            member.access_status = models.MembershipAccessStatus.blocked
            member.clerk_membership_id = None

        await revoke(
            operation_type=models.MemberAccessOperationType.revoke_membership,
            provider_call=revoke_membership,
            apply_local=apply_membership_revoke,
            intent={
                "clerk_user_id": clerk_user_id,
                "clerk_membership_id": clerk_membership_id,
            },
        )


async def list_members(
    db: AsyncSession,
    *,
    organization_id: int,
    include_archived: bool = False,
    skip: int = 0,
    limit: int = 100,
) -> schemas.MemberListRead:
    now = datetime.now(timezone.utc)
    expired_result = await db.execute(
        select(models.OrganizationMembership).where(
            models.OrganizationMembership.organization_id == organization_id,
            models.OrganizationMembership.access_status == models.MembershipAccessStatus.pending_invite,
            models.OrganizationMembership.invitation_expires_at.is_not(None),
            models.OrganizationMembership.invitation_expires_at < now,
        )
    )
    for member in expired_result.scalars().all():
        member.access_status = models.MembershipAccessStatus.invite_expired
        member.clerk_invitation_status = models.ClerkInvitationStatus.expired

    filters = [models.OrganizationMembership.organization_id == organization_id]
    if not include_archived:
        filters.append(models.OrganizationMembership.lifecycle_status == models.MembershipLifecycleStatus.active)

    total = await db.scalar(select(func.count()).select_from(models.OrganizationMembership).where(*filters))
    result = await db.execute(
        select(models.OrganizationMembership)
        .where(*filters)
        .options(
            selectinload(models.OrganizationMembership.account),
            selectinload(models.OrganizationMembership.capabilities),
            selectinload(models.OrganizationMembership.teacher_profile).selectinload(models.Teacher.subjects),
        )
        .order_by(models.OrganizationMembership.organization_display_name)
        .offset(skip)
        .limit(limit)
    )
    members = result.scalars().all()
    history_ids = await _teacher_ids_with_history(
        db,
        organization_id,
        [member.teacher_profile.id for member in members if member.teacher_profile is not None],
    )
    return schemas.MemberListRead(
        items=[
            _to_read(
                member,
                has_history=member.teacher_profile is not None and member.teacher_profile.id in history_ids,
            )
            for member in members
        ],
        total=total or 0,
        limit=limit,
        offset=skip,
    )


async def get_member_read(db: AsyncSession, *, organization_id: int, member_id: int) -> schemas.MemberRead:
    member = await _load_member(db, organization_id, member_id)
    if member is None:
        raise member_error(404, "member_not_found", "Member not found.")
    history_ids = await _teacher_ids_with_history(
        db,
        organization_id,
        [member.teacher_profile.id] if member.teacher_profile is not None else [],
    )
    return _to_read(
        member,
        has_history=member.teacher_profile is not None and member.teacher_profile.id in history_ids,
    )


async def create_member(
    db: AsyncSession,
    member_in: schemas.MemberCreate,
    *,
    organization_id: int,
    current_admin: models.User,
    clerk_access: ClerkAccessService | None = None,
    operation_service: MemberAccessOperationService | None = None,
) -> schemas.MemberRead:
    capabilities = _capability_values(member_in.capabilities)
    teacher_access_mode = (
        models.TeacherAccessMode(member_in.teacher_access_mode)
        if member_in.teacher_access_mode
        else None
    )
    expected_role = _expected_role(capabilities, teacher_access_mode)
    normalized_email = _normalize_email(str(member_in.email))
    account = await db.scalar(select(models.User).where(func.lower(models.User.email) == normalized_email))

    if account is not None:
        existing = await db.scalar(
            select(models.OrganizationMembership).where(
                models.OrganizationMembership.organization_id == organization_id,
                models.OrganizationMembership.account_id == account.id,
            )
        )
        if existing is not None:
            raise member_error(409, "member_already_exists", "This member already exists in the organization.")

    clerk_access = clerk_access or ClerkAccessService()
    operation_service = operation_service or MemberAccessOperationService()
    admin_id = current_admin.id
    admin_clerk_user_id = current_admin.clerk_user_id
    invite_result: ClerkAccessResult | None = None
    operation_id: int | None = None
    clerk_org_id: str | None = None

    if expected_role is not None:
        org = await _organization(db, organization_id)
        clerk_org_id = _require_clerk_org(org, current_admin)
        intent = {
            "capabilities": sorted(capability.value for capability in capabilities),
            "teacher_access_mode": teacher_access_mode.value if teacher_access_mode else None,
            "subject_ids": sorted(member_in.subject_ids),
            "expected_role": expected_role.value,
        }
        try:
            operation = await operation_service.create_pending(
                organization_id=organization_id,
                target_email=normalized_email,
                operation_type=models.MemberAccessOperationType.create_invitation,
                created_by_user_id=admin_id,
                intended_capabilities=capabilities,
                intended_role=expected_role,
                intent=intent,
                draft_payload=member_in.model_dump(mode="json"),
                clerk_org_id=clerk_org_id,
                clerk_user_id=None,
            )
        except UnresolvedAccessOperationError as exc:
            _raise_unresolved_operation(exc)
        operation_id = operation.id
        invite_result = await clerk_access.create_organization_invitation(
            clerk_org_id=clerk_org_id,
            email=normalized_email,
            role=expected_role.value,
            inviter_user_id=admin_clerk_user_id,
            membership_id=None,
        )
        if not invite_result.ok:
            final_status = models.MemberAccessOperationStatus.failed
            support_required = False
            if invite_result.invitation_id:
                compensation = await clerk_access.revoke_organization_invitation(
                    clerk_org_id=clerk_org_id,
                    invitation_id=invite_result.invitation_id,
                    requesting_user_id=admin_clerk_user_id,
                )
                final_status = (
                    models.MemberAccessOperationStatus.compensated
                    if compensation.ok
                    else models.MemberAccessOperationStatus.support_required
                )
                support_required = not compensation.ok
            await operation_service.transition(
                operation_id,
                final_status,
                clerk_invitation_id=invite_result.invitation_id,
                error_category=invite_result.error_category,
                safe_message=invite_result.safe_message,
                compensation_attempted=bool(invite_result.invitation_id),
                support_required=support_required,
            )
            if support_required:
                _raise_local_commit_failure(support_required=True)
            _raise_provider_failure(invite_result)
        await operation_service.transition(
            operation_id,
            models.MemberAccessOperationStatus.clerk_succeeded,
            clerk_invitation_id=invite_result.invitation_id,
        )

    try:
        account = account or await _get_or_create_account(db, normalized_email, member_in.organization_display_name)
        membership = models.OrganizationMembership(
            organization_id=organization_id,
            account_id=account.id,
            organization_display_name=member_in.organization_display_name.strip(),
            lifecycle_status=models.MembershipLifecycleStatus.active,
            access_status=_access_status_for_draft(capabilities, teacher_access_mode),
            teacher_access_mode=teacher_access_mode,
            expected_clerk_role=expected_role,
            created_by_user_id=current_admin.id,
            updated_by_user_id=current_admin.id,
        )
        db.add(membership)
        await db.flush()
        await _replace_capabilities(db, membership, capabilities)
        await _sync_teacher_profile(
            db,
            membership,
            capabilities=capabilities,
            subject_ids=member_in.subject_ids,
            current_admin=current_admin,
        )
        if expected_role is not None:
            assert invite_result is not None
            membership.clerk_invitation_id = invite_result.invitation_id
            membership.clerk_invitation_status = models.ClerkInvitationStatus.pending
            membership.invitation_expires_at = normalize_clerk_datetime(invite_result.expires_at)
            membership.access_status = models.MembershipAccessStatus.pending_invite
        await db.flush()
        if expected_role is not None:
            await db.commit()
    except Exception as exc:
        await db.rollback()
        if invite_result is not None and operation_id is not None and clerk_org_id is not None:
            compensation = await clerk_access.revoke_organization_invitation(
                clerk_org_id=clerk_org_id,
                invitation_id=invite_result.invitation_id,
                requesting_user_id=admin_clerk_user_id,
            )
            support_required = not compensation.ok
            await operation_service.transition(
                operation_id,
                (
                    models.MemberAccessOperationStatus.compensated
                    if compensation.ok
                    else models.MemberAccessOperationStatus.support_required
                ),
                clerk_invitation_id=invite_result.invitation_id,
                error_category=compensation.error_category if support_required else "local_commit_failed",
                safe_message=compensation.safe_message if support_required else str(type(exc).__name__),
                compensation_attempted=True,
                support_required=support_required,
            )
            logger.error(
                "member_access_local_commit_failed",
                operation_id=operation_id,
                organization_id=organization_id,
                compensation_succeeded=compensation.ok,
                error_type=type(exc).__name__,
            )
            _raise_local_commit_failure(support_required=support_required)
        raise

    if operation_id is not None:
        await operation_service.transition(
            operation_id,
            models.MemberAccessOperationStatus.local_committed,
            membership_id=membership.id,
            account_id=account.id,
            clerk_invitation_id=invite_result.invitation_id if invite_result else None,
        )
    created = await _load_member(db, organization_id, membership.id)
    return _to_read(created)


async def update_member(
    db: AsyncSession,
    member_id: int,
    member_in: schemas.MemberUpdate,
    *,
    organization_id: int,
    current_admin: models.User,
    clerk_access: ClerkAccessService | None = None,
) -> schemas.MemberRead:
    member = await _load_member(db, organization_id, member_id)
    if member is None:
        raise member_error(404, "member_not_found", "Member not found.")
    if member.lifecycle_status != models.MembershipLifecycleStatus.active:
        raise member_error(409, "member_archived", "Restore the member before editing.")
    if member.access_status == models.MembershipAccessStatus.sync_error:
        raise member_error(409, "member_sync_error", "Resolve the synchronization error before editing.")
    if member_in.lock_version and member_in.lock_version != member.lock_version:
        raise member_error(409, "stale_member", "This member changed while you were editing.")

    current_caps = {cap.capability for cap in member.capabilities}
    next_caps = _capability_values(member_in.capabilities) if member_in.capabilities is not None else current_caps
    next_mode = member.teacher_access_mode
    if member_in.teacher_access_mode is not None:
        next_mode = models.TeacherAccessMode(member_in.teacher_access_mode)
    if models.MembershipCapability.teacher not in next_caps:
        next_mode = None
    elif next_mode is None:
        raise member_error(422, "validation_error", "Teacher access mode is required.", fields={"teacher_access_mode": "Required."})
    if models.MembershipCapability.admin in next_caps and next_mode == models.TeacherAccessMode.scheduler_only:
        raise member_error(422, "validation_error", "Admins require platform access.", fields={"teacher_access_mode": "Use platform."})

    await _assert_can_remove_admin_capability(db, member, current_admin, next_capabilities=next_caps)
    previous_snapshot = _access_snapshot(member)
    previous_role = member.expected_clerk_role
    target_role = _expected_role(next_caps, next_mode)
    clerk_access = clerk_access or ClerkAccessService()
    if models.MembershipCapability.teacher in next_caps and member_in.subject_ids is not None:
        await _validate_subject_ids(db, organization_id, member_in.subject_ids)

    if member_in.email and member.access_status != models.MembershipAccessStatus.active:
        member.account.email = _normalize_email(str(member_in.email))
    elif member_in.email and _normalize_email(str(member_in.email)) != member.account.email:
        raise member_error(
            409,
            "active_identity_email_locked",
            "The email of an active access account is managed by the user or support.",
            fields={"email": "Locked for active members."},
        )
    if member_in.organization_display_name is not None:
        member.organization_display_name = member_in.organization_display_name.strip()
    member.teacher_access_mode = next_mode
    member.expected_clerk_role = _expected_role(next_caps, next_mode)

    await _replace_capabilities(db, member, next_caps)
    await _sync_teacher_profile(
        db,
        member,
        capabilities=next_caps,
        subject_ids=member_in.subject_ids,
        current_admin=current_admin,
    )
    await db.flush()
    member = await _load_member(db, organization_id, member.id)
    member.updated_by_user_id = current_admin.id
    member.lock_version += 1

    if target_role is None and member.access_status != models.MembershipAccessStatus.none:
        await _revoke_provider_access(db, member=member, current_admin=current_admin, clerk_access=clerk_access)
        member.access_status = models.MembershipAccessStatus.none
        member.expected_clerk_role = None
    elif target_role is not None:
        member.expected_clerk_role = target_role
        if member.account.clerk_user_id and member.access_status == models.MembershipAccessStatus.active:
            if previous_role != target_role:
                await _change_provider_role(
                    db,
                    member=member,
                    current_admin=current_admin,
                    clerk_access=clerk_access,
                    operation_type=models.MemberAccessOperationType.change_role,
                    previous_role=previous_role,
                    previous_snapshot=previous_snapshot,
                )
        elif member.access_status == models.MembershipAccessStatus.none:
            await _send_invitation(
                db,
                member=member,
                current_admin=current_admin,
                clerk_access=clerk_access,
                operation_type=models.MemberAccessOperationType.create_invitation,
                previous_snapshot=previous_snapshot,
            )

    await db.flush()
    updated = await _load_member(db, organization_id, member.id)
    return _to_read(updated)


async def remove_member(
    db: AsyncSession,
    member_id: int,
    *,
    organization_id: int,
    current_admin: models.User,
    clerk_access: ClerkAccessService | None = None,
) -> dict:
    member = await _load_member(db, organization_id, member_id)
    if member is None:
        raise member_error(404, "member_not_found", "Member not found.")
    caps = {cap.capability for cap in member.capabilities}
    if member.account_id == current_admin.id and models.MembershipCapability.admin in caps:
        raise member_error(409, "self_admin_removal_blocked", "You cannot remove your own admin access.")
    if models.MembershipCapability.admin in caps and await _active_admin_count(db, organization_id, exclude_member_id=member.id) == 0:
        raise member_error(409, "last_active_admin_blocked", "At least one active admin must remain.")

    history_ids = await _teacher_ids_with_history(
        db,
        organization_id,
        [member.teacher_profile.id] if member.teacher_profile is not None else [],
    )
    actions = _member_actions(
        member,
        member.teacher_profile,
        has_history=member.teacher_profile is not None and member.teacher_profile.id in history_ids,
    )
    await _revoke_provider_access(db, member=member, current_admin=current_admin, clerk_access=clerk_access or ClerkAccessService())
    if actions.remove_effect == "hard_delete":
        if member.teacher_profile:
            await db.delete(member.teacher_profile)
        await db.delete(member)
        return {"status": "removed", "remove_effect": "hard_delete"}
    member.lifecycle_status = models.MembershipLifecycleStatus.archived
    member.access_status = models.MembershipAccessStatus.blocked if member.access_status != models.MembershipAccessStatus.none else models.MembershipAccessStatus.none
    member.updated_by_user_id = current_admin.id
    member.lock_version += 1
    return {"status": "removed", "remove_effect": "archive"}


async def restore_member(
    db: AsyncSession,
    member_id: int,
    *,
    restore_in: schemas.MemberRestore | None = None,
    organization_id: int,
    current_admin: models.User,
    clerk_access: ClerkAccessService | None = None,
) -> schemas.MemberRead:
    member = await _load_member(db, organization_id, member_id)
    if member is None:
        raise member_error(404, "member_not_found", "Member not found.")
    if member.lifecycle_status != models.MembershipLifecycleStatus.archived:
        raise member_error(409, "member_not_archived", "Only archived members can be restored.")
    previous_snapshot = _access_snapshot(member)
    previous_role = member.expected_clerk_role
    if restore_in and restore_in.capabilities is not None:
        next_caps = _capability_values(restore_in.capabilities)
        next_mode = models.TeacherAccessMode(restore_in.teacher_access_mode) if restore_in.teacher_access_mode else member.teacher_access_mode
        if models.MembershipCapability.teacher not in next_caps:
            next_mode = None
        elif next_mode is None:
            raise member_error(422, "validation_error", "Teacher access mode is required.", fields={"teacher_access_mode": "Required."})
        if not restore_in.restore_access and models.MembershipCapability.admin in next_caps:
            raise member_error(422, "validation_error", "Remove admin capability or restore access.", fields={"capabilities": "Admin requires platform access."})
        member.teacher_access_mode = next_mode
        member.expected_clerk_role = _expected_role(next_caps, next_mode) if restore_in.restore_access else None
        await _replace_capabilities(db, member, next_caps)
        await _sync_teacher_profile(
            db,
            member,
            capabilities=next_caps,
            subject_ids=restore_in.subject_ids,
            current_admin=current_admin,
        )
    elif restore_in and not restore_in.restore_access and member.expected_clerk_role is not None:
        raise member_error(422, "validation_error", "Choose non-platform capabilities before restoring without access.")
    member.lifecycle_status = models.MembershipLifecycleStatus.active
    member.updated_by_user_id = current_admin.id
    member.lock_version += 1
    if member.expected_clerk_role is None:
        member.access_status = models.MembershipAccessStatus.none
    elif member.account.clerk_user_id and member.clerk_membership_id:
        clerk_access = clerk_access or ClerkAccessService()
        member.access_status = models.MembershipAccessStatus.active
        member.access_error_category = None
        member.access_error_safe_message = None
        await _change_provider_role(
            db,
            member=member,
            current_admin=current_admin,
            clerk_access=clerk_access,
            operation_type=models.MemberAccessOperationType.restore_access,
            previous_role=previous_role,
            previous_snapshot=previous_snapshot,
        )
    else:
        await _send_invitation(
            db,
            member=member,
            current_admin=current_admin,
            clerk_access=clerk_access or ClerkAccessService(),
            operation_type=models.MemberAccessOperationType.restore_access,
            previous_snapshot=previous_snapshot,
        )
    await db.flush()
    restored = await _load_member(db, organization_id, member.id)
    return _to_read(restored)


async def resend_invitation(
    db: AsyncSession,
    member_id: int,
    *,
    organization_id: int,
    current_admin: models.User,
    clerk_access: ClerkAccessService | None = None,
) -> schemas.MemberRead:
    member = await _load_member(db, organization_id, member_id)
    if member is None:
        raise member_error(404, "member_not_found", "Member not found.")
    if member.access_status not in {models.MembershipAccessStatus.pending_invite, models.MembershipAccessStatus.invite_expired}:
        raise member_error(409, "resend_not_available", "Invitation resend is not available for this member.")
    if member.expected_clerk_role is None:
        raise member_error(409, "access_not_required", "This member does not require platform access.")
    clerk_access = clerk_access or ClerkAccessService()
    previous_snapshot = _access_snapshot(member)
    if member.clerk_invitation_id and member.clerk_invitation_status == models.ClerkInvitationStatus.pending:
        await _revoke_provider_access(db, member=member, current_admin=current_admin, clerk_access=clerk_access)
    member.lock_version += 1
    await _send_invitation(
        db,
        member=member,
        current_admin=current_admin,
        clerk_access=clerk_access,
        operation_type=models.MemberAccessOperationType.resend_invitation,
        previous_snapshot=previous_snapshot,
    )
    await db.flush()
    updated = await _load_member(db, organization_id, member.id)
    return _to_read(updated)


async def retry_sync(
    db: AsyncSession,
    member_id: int,
    *,
    organization_id: int,
    current_admin: models.User,
    clerk_access: ClerkAccessService | None = None,
) -> schemas.MemberRead:
    member = await _load_member(db, organization_id, member_id)
    if member is None:
        raise member_error(404, "member_not_found", "Member not found.")
    if member.access_status != models.MembershipAccessStatus.sync_error:
        raise member_error(409, "retry_not_available", "Retry is only available for members in sync error.")
    clerk_access = clerk_access or ClerkAccessService()
    previous_snapshot = _access_snapshot(member)
    previous_role = member.expected_clerk_role
    member.access_error_category = None
    member.access_error_safe_message = None
    member.lock_version += 1
    if member.expected_clerk_role is None:
        await _revoke_provider_access(db, member=member, current_admin=current_admin, clerk_access=clerk_access)
        member.access_status = models.MembershipAccessStatus.none
    elif member.account.clerk_user_id:
        member.access_status = models.MembershipAccessStatus.active
        await _change_provider_role(
            db,
            member=member,
            current_admin=current_admin,
            clerk_access=clerk_access,
            operation_type=models.MemberAccessOperationType.change_role,
            previous_role=previous_role,
            previous_snapshot=previous_snapshot,
        )
    else:
        await _send_invitation(
            db,
            member=member,
            current_admin=current_admin,
            clerk_access=clerk_access,
            operation_type=models.MemberAccessOperationType.restore_access,
            previous_snapshot=previous_snapshot,
        )
    await db.flush()
    updated = await _load_member(db, organization_id, member.id)
    return _to_read(updated)


async def current_member(db: AsyncSession, *, current_user: models.User) -> schemas.CurrentMemberRead:
    member = await db.scalar(
        select(models.OrganizationMembership)
        .where(
            models.OrganizationMembership.organization_id == current_user.organization_id,
            models.OrganizationMembership.account_id == current_user.id,
        )
        .options(selectinload(models.OrganizationMembership.capabilities), selectinload(models.OrganizationMembership.teacher_profile))
    )
    if member is None:
        raise member_error(403, "membership_required", "Membership required.")
    caps = sorted(cap.capability.value for cap in member.capabilities)
    modes = []
    if "admin" in caps:
        modes.append("admin")
    if "teacher" in caps:
        modes.append("teacher")
    return schemas.CurrentMemberRead(
        member_id=member.id,
        account_id=current_user.id,
        organization_id=current_user.organization_id,
        capabilities=caps,
        access_status=member.access_status.value,
        lifecycle_status=member.lifecycle_status.value,
        teacher_id=member.teacher_profile.id if member.teacher_profile else None,
        default_mode="admin" if "admin" in caps else "teacher",
        available_modes=modes,
    )
