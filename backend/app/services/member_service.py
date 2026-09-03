from __future__ import annotations

from datetime import UTC, datetime

import structlog
from sqlalchemy import delete, func, insert, select, text, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import models, schemas
from app.core.auth import Actor
from app.core.exceptions import AppError
from app.db.tenant import set_async_tenant_context
from app.services.clerk_access_service import (
    SAFE_PROVIDER_ERROR,
    ClerkAccessResult,
    ClerkAccessService,
    normalize_clerk_datetime,
)
from app.services.member_access_operation_service import (
    MemberAccessOperationService,
    MemberAccessSagaCoordinator,
    UnresolvedAccessOperationError,
)
from app.services.scheduler_state_service import record_scheduler_change

logger = structlog.get_logger(__name__)


def _require_operation_service(
    service: MemberAccessOperationService | None,
) -> MemberAccessOperationService:
    if service is None:
        raise RuntimeError("Member access operations require an injected coordinator.")
    return service


def member_error(
    status_code: int,
    code: str,
    message: str,
    *,
    category: str | None = None,
    retryable: bool = False,
    support_required: bool = False,
    fields: dict[str, str] | None = None,
) -> AppError:
    kind = {
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        422: "validation",
    }.get(status_code, "unavailable")
    return AppError(
        kind=kind,
        code=code,
        detail=message,
        metadata={
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
    if (
        models.MembershipCapability.teacher in capabilities
        and teacher_access_mode == models.TeacherAccessMode.platform
    ):
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
    return member.access_error_category in {
        "provider_rate_limited",
        "provider_timeout",
        "provider_unconfirmed",
    }


def _provider_state(member: models.OrganizationMembership) -> str:
    if member.expected_clerk_role is None:
        return "not_required"
    return "unconfirmed" if _has_provider_outage(member) else "confirmed"


def _member_actions(
    member: models.OrganizationMembership,
    teacher: models.Teacher | None,
    *,
    has_history: bool = False,
) -> schemas.MemberActionFlags:
    return schemas.MemberActionFlags(
        can_edit=member.lifecycle_status == models.MembershipLifecycleStatus.active
        and member.access_status != models.MembershipAccessStatus.sync_error,
        can_remove=member.lifecycle_status == models.MembershipLifecycleStatus.active,
        remove_effect="archive"
        if has_history or member.access_status != models.MembershipAccessStatus.none
        else "hard_delete",
        can_restore=member.lifecycle_status == models.MembershipLifecycleStatus.archived,
        can_resend_invite=member.lifecycle_status == models.MembershipLifecycleStatus.active
        and member.access_status
        in {
            models.MembershipAccessStatus.pending_invite,
            models.MembershipAccessStatus.invite_expired,
        }
        and not _has_provider_outage(member),
        can_retry_sync=member.access_status == models.MembershipAccessStatus.sync_error,
        provider_state=_provider_state(member),
    )


def _to_read(
    member: models.OrganizationMembership,
    *,
    has_history: bool = False,
    reference_time: datetime | None = None,
) -> schemas.MemberRead:
    account = member.account
    teacher = member.teacher_profile
    caps = sorted(cap.capability.value for cap in member.capabilities)
    actions = _member_actions(member, teacher, has_history=has_history)
    invitation_expired = (
        reference_time is not None
        and member.access_status == models.MembershipAccessStatus.pending_invite
        and member.invitation_expires_at is not None
        and member.invitation_expires_at < reference_time
    )
    access_status = (
        models.MembershipAccessStatus.invite_expired if invitation_expired else member.access_status
    )
    invitation_status = (
        models.ClerkInvitationStatus.expired
        if invitation_expired
        else member.clerk_invitation_status
    )
    return schemas.MemberRead(
        id=member.id,
        account_id=member.account_id,
        organization_id=member.organization_id,
        organization_display_name=member.organization_display_name,
        email=account.email,
        capabilities=caps,
        lifecycle_status=member.lifecycle_status.value,
        access_status=access_status.value,
        teacher_access_mode=member.teacher_access_mode.value
        if member.teacher_access_mode
        else None,
        expected_clerk_role=member.expected_clerk_role.value
        if member.expected_clerk_role
        else None,
        clerk_user_id=account.clerk_user_id,
        clerk_membership_id=member.clerk_membership_id,
        clerk_invitation_id=member.clerk_invitation_id,
        clerk_invitation_status=invitation_status.value if invitation_status else None,
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


async def _ensure_pending_account_id(
    db: AsyncSession,
    *,
    organization_id: int,
    email: str,
    display_name: str,
) -> int:
    account_id = await db.scalar(
        text(
            """
            SELECT id
            FROM app_security.ensure_pending_account(
                :organization_id, :email, :display_name
            )
            """
        ),
        {
            "organization_id": organization_id,
            "email": _normalize_email(email),
            "display_name": display_name.strip(),
        },
    )
    if account_id is None:
        raise RuntimeError("The pending member account could not be created.")
    return int(account_id)


async def _link_account_to_clerk(
    db: AsyncSession,
    *,
    member: models.OrganizationMembership,
    clerk_user_id: str,
    role: models.ClerkOrganizationRole,
) -> None:
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
            "email": member.account.email,
            "display_name": member.organization_display_name,
            "role": role.value,
            "organization_id": member.organization_id,
        },
    )
    if linked_account_id != member.account_id:
        raise RuntimeError("The local email is linked to a different Clerk user.")
    await db.refresh(member.account)


async def _load_member(
    db: AsyncSession, organization_id: int, member_id: int
) -> models.OrganizationMembership | None:
    return await db.scalar(
        select(models.OrganizationMembership)
        .where(
            models.OrganizationMembership.id == member_id,
            models.OrganizationMembership.organization_id == organization_id,
        )
        .options(
            selectinload(models.OrganizationMembership.account),
            selectinload(models.OrganizationMembership.teacher_profile).selectinload(
                models.Teacher.subjects
            ),
        )
    )


async def _teacher_ids_with_history(
    db: AsyncSession, organization_id: int, teacher_ids: list[int]
) -> set[int]:
    teacher_ids = [teacher_id for teacher_id in teacher_ids if teacher_id]
    if not teacher_ids:
        return set()
    simple_checks = [
        (models.Availability, models.Availability.teacher_id),
        (models.TeacherWeeklyTimesheet, models.TeacherWeeklyTimesheet.teacher_id),
        (models.ClassSubjectLink, models.ClassSubjectLink.teacher_id),
        (models.ScheduleDraftBlock, models.ScheduleDraftBlock.teacher_id),
        (models.ScheduleDiffEntry, models.ScheduleDiffEntry.teacher_id),
        (models.ActiveScheduleBlock, models.ActiveScheduleBlock.teacher_id),
        (models.PlannedRecoveryLink, models.PlannedRecoveryLink.teacher_id),
        (models.OperationalScheduleBlock, models.OperationalScheduleBlock.teacher_id),
    ]
    columns = [column for _, column in simple_checks]
    columns.extend(
        (
            models.LessonOccurrence.substitute_teacher_id,
            models.LessonOccurrence.planned_teacher_id,
            models.LessonOccurrence.executed_teacher_id,
        )
    )
    history = union_all(
        *(
            select(column.label("teacher_id")).where(
                column.class_.organization_id == organization_id,
                column.in_(teacher_ids),
            )
            for column in columns
        )
    ).subquery()
    rows = await db.execute(select(history.c.teacher_id).distinct())
    return set(rows.scalars().all())


async def _teacher_ids_with_scheduler_references(
    db: AsyncSession, organization_id: int, teacher_ids: list[int]
) -> set[int]:
    """Return teachers whose state can affect the active scheduler year."""
    teacher_ids = [teacher_id for teacher_id in teacher_ids if teacher_id]
    if not teacher_ids:
        return set()
    active_year_id = await db.scalar(
        select(models.SchedulerSchoolYear.id).where(
            models.SchedulerSchoolYear.organization_id == organization_id,
            models.SchedulerSchoolYear.is_active.is_(True),
        )
    )
    if active_year_id is None:
        return set()

    references = [
        select(models.ClassSubjectLink.teacher_id)
        .join(models.Class, models.Class.id == models.ClassSubjectLink.class_id)
        .where(
            models.ClassSubjectLink.organization_id == organization_id,
            models.ClassSubjectLink.teacher_id.in_(teacher_ids),
            models.Class.organization_id == organization_id,
            models.Class.is_archived.is_(False),
            models.ClassSubjectLink.grade_level == models.Class.grade_level,
        ),
        select(models.ScheduleDraftBlock.teacher_id).where(
            models.ScheduleDraftBlock.organization_id == organization_id,
            models.ScheduleDraftBlock.school_year_id == active_year_id,
            models.ScheduleDraftBlock.teacher_id.in_(teacher_ids),
        ),
        select(models.ScheduleDiffEntry.teacher_id).where(
            models.ScheduleDiffEntry.organization_id == organization_id,
            models.ScheduleDiffEntry.school_year_id == active_year_id,
            models.ScheduleDiffEntry.teacher_id.in_(teacher_ids),
        ),
        select(models.ActiveScheduleBlock.teacher_id).where(
            models.ActiveScheduleBlock.organization_id == organization_id,
            models.ActiveScheduleBlock.school_year_id == active_year_id,
            models.ActiveScheduleBlock.status == models.ActiveScheduleBlockStatus.ACTIVE,
            models.ActiveScheduleBlock.teacher_id.in_(teacher_ids),
        ),
        select(models.PlannedRecoveryLink.teacher_id).where(
            models.PlannedRecoveryLink.organization_id == organization_id,
            models.PlannedRecoveryLink.school_year_id == active_year_id,
            models.PlannedRecoveryLink.teacher_id.in_(teacher_ids),
            models.PlannedRecoveryLink.status.notin_(
                {
                    models.PlannedRecoveryLinkStatus.CANCELED,
                    models.PlannedRecoveryLinkStatus.REPLACED,
                }
            ),
        ),
        select(models.OperationalScheduleBlock.teacher_id).where(
            models.OperationalScheduleBlock.organization_id == organization_id,
            models.OperationalScheduleBlock.teacher_id.in_(teacher_ids),
            models.OperationalScheduleBlock.status == models.OperationalBlockStatus.ACTIVE,
        ),
    ]
    references.extend(
        select(column)
        .join(
            models.ActiveScheduleBlock,
            models.ActiveScheduleBlock.id == models.LessonOccurrence.active_schedule_block_id,
        )
        .where(
            models.LessonOccurrence.organization_id == organization_id,
            models.LessonOccurrence.is_active.is_(True),
            models.ActiveScheduleBlock.organization_id == organization_id,
            models.ActiveScheduleBlock.school_year_id == active_year_id,
            column.in_(teacher_ids),
        )
        for column in (
            models.LessonOccurrence.substitute_teacher_id,
            models.LessonOccurrence.planned_teacher_id,
            models.LessonOccurrence.executed_teacher_id,
        )
    )
    rows = await db.execute(union_all(*references))
    return {row[0] for row in rows.all() if row[0] is not None}


async def _record_teacher_scheduler_change(
    db: AsyncSession,
    organization_id: int,
    *,
    teacher_id: int,
    active_resource: bool | None = None,
    **change,
) -> models.SchedulerStateVersionEvent | None:
    if active_resource is None:
        active_resource = teacher_id in await _teacher_ids_with_scheduler_references(
            db, organization_id, [teacher_id]
        )
    return await record_scheduler_change(
        db,
        organization_id,
        entity_type="TEACHER_PROFILE",
        entity_id=teacher_id,
        **change,
        active_resource=active_resource,
    )


async def _organization(db: AsyncSession, organization_id: int) -> models.Organization:
    org = await db.get(models.Organization, organization_id)
    if org is None:
        raise member_error(404, "organization_not_found", "Organization not found.")
    return org


def _require_clerk_org(org: models.Organization, current_admin: Actor) -> str:
    if not org.clerk_org_id or not current_admin.clerk_user_id:
        raise member_error(503, "clerk_configuration_required", SAFE_PROVIDER_ERROR)
    return org.clerk_org_id


async def _replace_capabilities(
    db: AsyncSession,
    member: models.OrganizationMembership,
    capabilities: set[models.MembershipCapability],
) -> None:
    member.can_admin = models.MembershipCapability.admin in capabilities
    member.can_teach = models.MembershipCapability.teacher in capabilities
    await db.flush()


async def _validate_subject_ids(
    db: AsyncSession, organization_id: int, subject_ids: list[int]
) -> list[int]:
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
    current_admin: Actor,
    previous_can_teach: bool | None = None,
    record_change: bool = True,
) -> None:
    wants_teacher = models.MembershipCapability.teacher in capabilities
    teacher = await db.scalar(
        select(models.Teacher)
        .where(
            models.Teacher.organization_id == member.organization_id,
            models.Teacher.organization_membership_id == member.id,
        )
        .options(
            selectinload(models.Teacher.subjects),
            selectinload(models.Teacher.availabilities),
            selectinload(models.Teacher.timesheets),
        )
    )
    teacher_was_created = False
    before_subjects: list[int] = []
    scheduler_relevant = False
    if wants_teacher and teacher is None:
        teacher = models.Teacher(
            organization_id=member.organization_id,
            organization_membership_id=member.id,
        )
        db.add(teacher)
        await db.flush()
        from app.services.availability_matrix_service import AvailabilityMatrixRepairService

        await AvailabilityMatrixRepairService.repair(
            db, organization_id=member.organization_id, teacher_ids=[teacher.id]
        )
        member.teacher_profile = teacher
        teacher_was_created = True
    elif not wants_teacher and teacher is not None:
        before_subjects = sorted(teacher.subject_ids)
        scheduler_relevant = teacher.id in await _teacher_ids_with_scheduler_references(
            db, member.organization_id, [teacher.id]
        )
        has_history = bool(teacher.availabilities or teacher.timesheets)
        if not has_history:
            await db.delete(teacher)
        if record_change and previous_can_teach is not False:
            await _record_teacher_scheduler_change(
                db,
                member.organization_id,
                teacher_id=teacher.id,
                operation=models.SchedulerStateChangeOperation.DELETE,
                before={"can_teach": previous_can_teach, "subject_ids": before_subjects},
                after={"can_teach": False, "subject_ids": before_subjects},
                changed_by_membership_id=current_admin.membership_id,
                active_resource=scheduler_relevant,
            )
        return

    if wants_teacher and teacher is not None:
        if not teacher_was_created:
            before_subjects = sorted(teacher.subject_ids)
            scheduler_relevant = teacher.id in await _teacher_ids_with_scheduler_references(
                db, member.organization_id, [teacher.id]
            )
        after_subjects = before_subjects
        if subject_ids is not None:
            valid_subject_ids = await _validate_subject_ids(db, member.organization_id, subject_ids)
            after_subjects = sorted(valid_subject_ids)
            if before_subjects != after_subjects:
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
        changed = (
            teacher_was_created
            or (previous_can_teach is not None and previous_can_teach is not True)
            or before_subjects != after_subjects
        )
        if record_change and changed:
            await _record_teacher_scheduler_change(
                db,
                member.organization_id,
                teacher_id=teacher.id,
                operation=(
                    models.SchedulerStateChangeOperation.CREATE
                    if teacher_was_created
                    else models.SchedulerStateChangeOperation.UPDATE
                ),
                before=(
                    None
                    if teacher_was_created
                    else {"can_teach": previous_can_teach, "subject_ids": before_subjects}
                ),
                after={"can_teach": True, "subject_ids": after_subjects},
                changed_by_membership_id=current_admin.membership_id,
                active_resource=scheduler_relevant,
            )


async def _active_admin_count(
    db: AsyncSession, organization_id: int, *, exclude_member_id: int | None = None
) -> int:
    stmt = (
        select(func.count())
        .select_from(models.OrganizationMembership)
        .join(models.User, models.User.id == models.OrganizationMembership.account_id)
        .where(
            models.OrganizationMembership.organization_id == organization_id,
            models.OrganizationMembership.lifecycle_status
            == models.MembershipLifecycleStatus.active,
            models.OrganizationMembership.access_status == models.MembershipAccessStatus.active,
            models.OrganizationMembership.can_admin.is_(True),
            models.User.clerk_user_id.is_not(None),
        )
    )
    if exclude_member_id is not None:
        stmt = stmt.where(models.OrganizationMembership.id != exclude_member_id)
    return await db.scalar(stmt) or 0


async def _assert_can_remove_admin_capability(
    db: AsyncSession,
    member: models.OrganizationMembership,
    current_admin: Actor,
    *,
    next_capabilities: set[models.MembershipCapability],
) -> None:
    current_caps = {cap.capability for cap in member.capabilities}
    removes_admin = (
        models.MembershipCapability.admin in current_caps
        and models.MembershipCapability.admin not in next_capabilities
    )
    if not removes_admin:
        return
    if member.account_id == current_admin.account_id:
        raise member_error(
            409, "self_admin_change_blocked", "You cannot remove your own admin access."
        )
    if await _active_admin_count(db, member.organization_id, exclude_member_id=member.id) == 0:
        raise member_error(
            409, "last_active_admin_blocked", "At least one active admin must remain."
        )


def _raise_provider_failure(result: ClerkAccessResult) -> None:
    status_code = 429 if result.error_category == "provider_rate_limited" else 502
    if result.retryable and status_code != 429:
        status_code = 503
    raise member_error(
        status_code,
        result.error_category or "provider_error",
        result.safe_message or SAFE_PROVIDER_ERROR,
        retryable=result.retryable,
    )


def _raise_unresolved_operation(exc: UnresolvedAccessOperationError) -> None:
    raise member_error(
        409,
        "member_access_operation_unresolved",
        "A previous access change still requires reconciliation. Contact support.",
        support_required=True,
    ) from exc


def _raise_local_commit_failure(*, support_required: bool) -> None:
    raise member_error(
        503 if support_required else 500,
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
    current_admin: Actor,
    clerk_access: ClerkAccessService,
    operation_type: models.MemberAccessOperationType,
    operation_service: MemberAccessOperationService | None = None,
    previous_snapshot: dict | None = None,
) -> None:
    org = await _organization(db, member.organization_id)
    clerk_org_id = _require_clerk_org(org, current_admin)
    operation_service = _require_operation_service(operation_service)
    organization_id = member.organization_id
    membership_id = member.id
    account_id = member.account_id
    target_email = member.account.email
    admin_membership_id = current_admin.membership_id
    admin_clerk_user_id = current_admin.clerk_user_id
    saga = MemberAccessSagaCoordinator(operation_service)
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
            created_by_membership_id=admin_membership_id,
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

    if expected_role is None:
        raise RuntimeError("A target Clerk role is required before granting platform access.")
    provider_user = await clerk_access.find_user_by_email(email=target_email)
    if not provider_user.ok:
        await operation_service.transition(
            operation.id,
            models.MemberAccessOperationStatus.failed,
            error_category=provider_user.error_category,
            safe_message=provider_user.safe_message,
        )
        _raise_provider_failure(provider_user)
    provider_membership = None
    if provider_user.user_id:
        provider_membership = await clerk_access.get_membership(
            clerk_org_id=clerk_org_id,
            clerk_user_id=provider_user.user_id,
        )
        if not provider_membership.ok:
            await operation_service.transition(
                operation.id,
                models.MemberAccessOperationStatus.failed,
                error_category=provider_membership.error_category,
                safe_message=provider_membership.safe_message,
            )
            _raise_provider_failure(provider_membership)

    created_invitation = False
    created_membership = False
    changed_role_from = None
    result = None
    if provider_membership and provider_membership.membership_id:
        actual_role = (
            models.ClerkOrganizationRole(provider_membership.role)
            if provider_membership.role in {role.value for role in models.ClerkOrganizationRole}
            else None
        )
        if actual_role != expected_role:
            result = await clerk_access.change_membership_role(
                clerk_org_id=clerk_org_id,
                clerk_user_id=provider_user.user_id,
                role=expected_role.value,
            )
            if not result.ok:
                await operation_service.transition(
                    operation.id,
                    models.MemberAccessOperationStatus.failed,
                    error_category=result.error_category,
                    safe_message=result.safe_message,
                )
                _raise_provider_failure(result)
            changed_role_from = actual_role
            provider_membership = result
    elif provider_user.user_id:
        result = await clerk_access.create_organization_membership(
            clerk_org_id=clerk_org_id,
            clerk_user_id=provider_user.user_id,
            role=expected_role.value,
        )
        if result.ok:
            provider_membership = result
            created_membership = True
    else:
        result = await clerk_access.find_pending_invitation(
            clerk_org_id=clerk_org_id,
            email=target_email,
        )
        if result.ok and not result.invitation_id:
            result = await clerk_access.create_organization_invitation(
                clerk_org_id=clerk_org_id,
                email=target_email,
                role=expected_role.value,
                inviter_user_id=admin_clerk_user_id,
                membership_id=membership_id,
            )
            created_invitation = result.ok
    if result is not None and not result.ok:
        if result.invitation_id:
            outcome = await saga.compensate_created_invitation(
                operation_id=operation.id,
                clerk_org_id=clerk_org_id,
                invitation_id=result.invitation_id,
                requesting_user_id=admin_clerk_user_id,
                error_category=result.error_category or "provider_failure",
                safe_message=result.safe_message or SAFE_PROVIDER_ERROR,
            )
            if outcome.support_required:
                _raise_local_commit_failure(support_required=True)
        else:
            await operation_service.transition(
                operation.id,
                models.MemberAccessOperationStatus.failed,
                error_category=result.error_category,
                safe_message=result.safe_message,
            )
        _raise_provider_failure(result)
    if provider_membership and provider_membership.membership_id:
        await operation_service.transition(
            operation.id,
            models.MemberAccessOperationStatus.clerk_succeeded,
            clerk_membership_id=provider_membership.membership_id,
        )
        await _link_account_to_clerk(
            db,
            member=member,
            clerk_user_id=provider_user.user_id,
            role=expected_role,
        )
        member.clerk_membership_id = provider_membership.membership_id
        member.clerk_invitation_id = None
        member.clerk_invitation_status = None
        member.invitation_expires_at = None
        member.access_status = models.MembershipAccessStatus.active
    if result is not None and result.invitation_id:
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
        await set_async_tenant_context(db, organization_id)
    except Exception as exc:
        await db.rollback()
        if created_membership and provider_user.user_id:
            outcome = await saga.compensate_created_membership(
                operation_id=operation.id,
                clerk_org_id=clerk_org_id,
                clerk_user_id=provider_user.user_id,
                clerk_membership_id=(
                    provider_membership.membership_id if provider_membership else None
                ),
                error_category="local_commit_failed",
                safe_message=type(exc).__name__,
            )
        elif created_invitation and result is not None and result.invitation_id:
            outcome = await saga.compensate_created_invitation(
                operation_id=operation.id,
                clerk_org_id=clerk_org_id,
                invitation_id=result.invitation_id,
                requesting_user_id=admin_clerk_user_id,
                error_category="local_commit_failed",
                safe_message=type(exc).__name__,
            )
        elif changed_role_from is not None and provider_user.user_id:
            outcome = await saga.compensate_role_change(
                operation_id=operation.id,
                clerk_org_id=clerk_org_id,
                clerk_user_id=provider_user.user_id,
                previous_role=changed_role_from,
                clerk_membership_id=(
                    provider_membership.membership_id if provider_membership else None
                ),
                error_category="local_commit_failed",
                safe_message=type(exc).__name__,
            )
        else:
            await operation_service.transition(
                operation.id,
                models.MemberAccessOperationStatus.failed,
                error_category="local_commit_failed",
                safe_message=type(exc).__name__,
            )
            outcome = None
        support_required = outcome.support_required if outcome else False
        logger.error(
            "member_invitation_local_commit_failed",
            operation_id=operation.id,
            organization_id=organization_id,
            membership_id=membership_id,
            compensation_succeeded=not support_required,
            error_type=type(exc).__name__,
        )
        _raise_local_commit_failure(support_required=support_required)
    await operation_service.transition(
        operation.id,
        models.MemberAccessOperationStatus.local_committed,
        membership_id=membership_id,
        account_id=account_id,
        clerk_invitation_id=(result.invitation_id if result is not None else None),
        clerk_membership_id=(provider_membership.membership_id if provider_membership else None),
    )


async def _change_provider_role(
    db: AsyncSession,
    *,
    member: models.OrganizationMembership,
    current_admin: Actor,
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
    operation_service = _require_operation_service(operation_service)
    saga = MemberAccessSagaCoordinator(operation_service)
    capabilities = {item.capability for item in member.capabilities}
    try:
        operation = await operation_service.create_pending(
            organization_id=member.organization_id,
            target_email=member.account.email,
            operation_type=operation_type,
            created_by_membership_id=current_admin.membership_id,
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
        await set_async_tenant_context(db, member.organization_id)
    except Exception as exc:
        await db.rollback()
        outcome = await saga.compensate_role_change(
            operation_id=operation.id,
            clerk_org_id=clerk_org_id,
            clerk_user_id=clerk_user_id,
            previous_role=previous_role,
            clerk_membership_id=result.membership_id,
            error_category="local_commit_failed",
            safe_message=type(exc).__name__,
        )
        support_required = outcome.support_required
        logger.error(
            "member_role_local_commit_failed",
            operation_id=operation.id,
            organization_id=member.organization_id,
            membership_id=member.id,
            compensation_succeeded=not support_required,
            error_type=type(exc).__name__,
        )
        _raise_local_commit_failure(support_required=support_required)
    await operation_service.transition(
        operation.id,
        models.MemberAccessOperationStatus.local_committed,
        membership_id=member.id,
        account_id=member.account_id,
        clerk_membership_id=member.clerk_membership_id,
    )


async def _revoke_provider_access(
    db: AsyncSession,
    *,
    member: models.OrganizationMembership,
    current_admin: Actor,
    clerk_access: ClerkAccessService,
    operation_service: MemberAccessOperationService | None = None,
) -> None:
    org = await _organization(db, member.organization_id)
    if not org.clerk_org_id:
        return
    operation_service = _require_operation_service(operation_service)
    organization_id = member.organization_id
    membership_id = member.id
    account_id = member.account_id
    target_email = member.account.email
    admin_membership_id = current_admin.membership_id
    capabilities = {item.capability for item in member.capabilities}

    async def revoke(*, operation_type, provider_call, apply_local, intent) -> None:
        try:
            operation = await operation_service.create_pending(
                organization_id=organization_id,
                target_email=target_email,
                operation_type=operation_type,
                created_by_membership_id=admin_membership_id,
                intended_capabilities=capabilities,
                intended_role=None,
                intent=intent,
                membership_id=membership_id,
                account_id=account_id,
                lock_version=member.lock_version,
                previous_snapshot=_access_snapshot(member),
                clerk_org_id=org.clerk_org_id,
                clerk_user_id=member.account.clerk_user_id,
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
            await set_async_tenant_context(db, organization_id)
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
            membership_id=membership_id,
            account_id=account_id,
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
        member.clerk_membership_id or member.access_status == models.MembershipAccessStatus.active
    ):
        clerk_user_id = member.account.clerk_user_id
        clerk_membership_id = member.clerk_membership_id

        async def revoke_membership():
            return await clerk_access.revoke_organization_membership(
                clerk_org_id=org.clerk_org_id,
                clerk_user_id=clerk_user_id,
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
    now = datetime.now(UTC)
    filters = [models.OrganizationMembership.organization_id == organization_id]
    if not include_archived:
        filters.append(
            models.OrganizationMembership.lifecycle_status
            == models.MembershipLifecycleStatus.active
        )

    total = await db.scalar(
        select(func.count()).select_from(models.OrganizationMembership).where(*filters)
    )
    result = await db.execute(
        select(models.OrganizationMembership)
        .where(*filters)
        .options(
            selectinload(models.OrganizationMembership.account),
            selectinload(models.OrganizationMembership.teacher_profile).selectinload(
                models.Teacher.subjects
            ),
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
                has_history=member.teacher_profile is not None
                and member.teacher_profile.id in history_ids,
                reference_time=now,
            )
            for member in members
        ],
        total=total or 0,
        limit=limit,
        offset=skip,
    )


async def get_member_read(
    db: AsyncSession, *, organization_id: int, member_id: int
) -> schemas.MemberRead:
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
    current_admin: Actor,
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
    account = await db.scalar(
        select(models.User).where(func.lower(models.User.email) == normalized_email)
    )

    if account is not None:
        existing = await db.scalar(
            select(models.OrganizationMembership).where(
                models.OrganizationMembership.organization_id == organization_id,
                models.OrganizationMembership.account_id == account.id,
            )
        )
        if existing is not None:
            raise member_error(
                409, "member_already_exists", "This member already exists in the organization."
            )

    clerk_access = clerk_access or ClerkAccessService()
    admin_membership_id = current_admin.membership_id
    admin_clerk_user_id = current_admin.clerk_user_id
    invite_result: ClerkAccessResult | None = None
    provider_user: ClerkAccessResult | None = None
    provider_membership: ClerkAccessResult | None = None
    operation_id: int | None = None
    clerk_org_id: str | None = None
    saga: MemberAccessSagaCoordinator | None = None
    created_invitation = False
    created_membership = False
    changed_role_from: models.ClerkOrganizationRole | None = None

    if expected_role is not None:
        operation_service = _require_operation_service(operation_service)
        saga = MemberAccessSagaCoordinator(operation_service)
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
                created_by_membership_id=admin_membership_id,
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
        provider_user = await clerk_access.find_user_by_email(email=normalized_email)
        if not provider_user.ok:
            await operation_service.transition(
                operation_id,
                models.MemberAccessOperationStatus.failed,
                error_category=provider_user.error_category,
                safe_message=provider_user.safe_message,
            )
            _raise_provider_failure(provider_user)
        if provider_user.user_id:
            provider_membership = await clerk_access.get_membership(
                clerk_org_id=clerk_org_id,
                clerk_user_id=provider_user.user_id,
            )
            if not provider_membership.ok:
                await operation_service.transition(
                    operation_id,
                    models.MemberAccessOperationStatus.failed,
                    error_category=provider_membership.error_category,
                    safe_message=provider_membership.safe_message,
                )
                _raise_provider_failure(provider_membership)

        if provider_membership and provider_membership.membership_id:
            actual_role = (
                models.ClerkOrganizationRole(provider_membership.role)
                if provider_membership.role in {role.value for role in models.ClerkOrganizationRole}
                else None
            )
            if actual_role != expected_role:
                role_result = await clerk_access.change_membership_role(
                    clerk_org_id=clerk_org_id,
                    clerk_user_id=provider_user.user_id,
                    role=expected_role.value,
                )
                if not role_result.ok:
                    await operation_service.transition(
                        operation_id,
                        models.MemberAccessOperationStatus.failed,
                        error_category=role_result.error_category,
                        safe_message=role_result.safe_message,
                    )
                    _raise_provider_failure(role_result)
                changed_role_from = actual_role
                provider_membership = role_result
        elif provider_user.user_id:
            provider_membership = await clerk_access.create_organization_membership(
                clerk_org_id=clerk_org_id,
                clerk_user_id=provider_user.user_id,
                role=expected_role.value,
            )
            if not provider_membership.ok:
                await operation_service.transition(
                    operation_id,
                    models.MemberAccessOperationStatus.failed,
                    error_category=provider_membership.error_category,
                    safe_message=provider_membership.safe_message,
                )
                _raise_provider_failure(provider_membership)
            created_membership = True
        else:
            invite_result = await clerk_access.find_pending_invitation(
                clerk_org_id=clerk_org_id,
                email=normalized_email,
            )
            if invite_result.ok and not invite_result.invitation_id:
                invite_result = await clerk_access.create_organization_invitation(
                    clerk_org_id=clerk_org_id,
                    email=normalized_email,
                    role=expected_role.value,
                    inviter_user_id=admin_clerk_user_id,
                    membership_id=None,
                )
                created_invitation = invite_result.ok
        if invite_result is not None and not invite_result.ok:
            if invite_result.invitation_id:
                outcome = await saga.compensate_created_invitation(
                    operation_id=operation_id,
                    clerk_org_id=clerk_org_id,
                    invitation_id=invite_result.invitation_id,
                    requesting_user_id=admin_clerk_user_id,
                    error_category=invite_result.error_category or "provider_failure",
                    safe_message=invite_result.safe_message or SAFE_PROVIDER_ERROR,
                )
                if outcome.support_required:
                    _raise_local_commit_failure(support_required=True)
            else:
                await operation_service.transition(
                    operation_id,
                    models.MemberAccessOperationStatus.failed,
                    error_category=invite_result.error_category,
                    safe_message=invite_result.safe_message,
                )
            _raise_provider_failure(invite_result)
        if invite_result is not None:
            await operation_service.transition(
                operation_id,
                models.MemberAccessOperationStatus.clerk_succeeded,
                clerk_invitation_id=invite_result.invitation_id,
            )
        if provider_membership and provider_membership.membership_id:
            await operation_service.transition(
                operation_id,
                models.MemberAccessOperationStatus.clerk_succeeded,
                clerk_membership_id=provider_membership.membership_id,
            )

    try:
        account_id = (
            account.id
            if account is not None
            else await _ensure_pending_account_id(
                db,
                organization_id=organization_id,
                email=normalized_email,
                display_name=member_in.organization_display_name,
            )
        )
        if provider_user and provider_user.user_id and account is not None:
            if account.clerk_user_id and account.clerk_user_id != provider_user.user_id:
                raise RuntimeError("The local email is linked to a different Clerk user.")
        membership = models.OrganizationMembership(
            organization_id=organization_id,
            account_id=account_id,
            organization_display_name=member_in.organization_display_name.strip(),
            lifecycle_status=models.MembershipLifecycleStatus.active,
            access_status=_access_status_for_draft(capabilities, teacher_access_mode),
            teacher_access_mode=teacher_access_mode,
            can_admin=models.MembershipCapability.admin in capabilities,
            can_teach=models.MembershipCapability.teacher in capabilities,
            created_by_membership_id=current_admin.membership_id,
            updated_by_membership_id=current_admin.membership_id,
        )
        db.add(membership)
        await db.flush()
        if provider_user and provider_user.user_id:
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
                    "clerk_user_id": provider_user.user_id,
                    "email": normalized_email,
                    "display_name": member_in.organization_display_name.strip(),
                    "role": expected_role.value if expected_role else "member",
                    "organization_id": organization_id,
                },
            )
            if linked_account_id != account_id:
                raise RuntimeError("The local email is linked to a different Clerk user.")
        account = await db.get(models.User, account_id)
        if account is None:
            raise RuntimeError("The pending member account could not be loaded.")
        await _replace_capabilities(db, membership, capabilities)
        await _sync_teacher_profile(
            db,
            membership,
            capabilities=capabilities,
            subject_ids=member_in.subject_ids,
            current_admin=current_admin,
        )
        if expected_role is not None:
            if provider_membership and provider_membership.membership_id:
                membership.clerk_membership_id = provider_membership.membership_id
                membership.access_status = models.MembershipAccessStatus.active
            else:
                assert invite_result is not None
                membership.clerk_invitation_id = invite_result.invitation_id
                membership.clerk_invitation_status = models.ClerkInvitationStatus.pending
                membership.invitation_expires_at = normalize_clerk_datetime(
                    invite_result.expires_at
                )
                membership.access_status = models.MembershipAccessStatus.pending_invite
        await db.flush()
        if expected_role is not None:
            await db.commit()
            await set_async_tenant_context(db, organization_id)
    except Exception as exc:
        await db.rollback()
        if (
            created_membership
            and provider_user is not None
            and provider_user.user_id
            and operation_id is not None
            and clerk_org_id is not None
        ):
            assert saga is not None
            outcome = await saga.compensate_created_membership(
                operation_id=operation_id,
                clerk_org_id=clerk_org_id,
                clerk_user_id=provider_user.user_id,
                clerk_membership_id=(
                    provider_membership.membership_id if provider_membership else None
                ),
                error_category="local_commit_failed",
                safe_message=type(exc).__name__,
            )
            _raise_local_commit_failure(support_required=outcome.support_required)
        if (
            created_invitation
            and invite_result is not None
            and operation_id is not None
            and clerk_org_id is not None
        ):
            assert saga is not None
            outcome = await saga.compensate_created_invitation(
                operation_id=operation_id,
                clerk_org_id=clerk_org_id,
                invitation_id=invite_result.invitation_id,
                requesting_user_id=admin_clerk_user_id,
                error_category="local_commit_failed",
                safe_message=type(exc).__name__,
            )
            logger.error(
                "member_access_local_commit_failed",
                operation_id=operation_id,
                organization_id=organization_id,
                compensation_succeeded=not outcome.support_required,
                error_type=type(exc).__name__,
            )
            _raise_local_commit_failure(support_required=outcome.support_required)
        if (
            changed_role_from is not None
            and provider_user is not None
            and provider_user.user_id
            and operation_id is not None
            and clerk_org_id is not None
        ):
            assert saga is not None
            outcome = await saga.compensate_role_change(
                operation_id=operation_id,
                clerk_org_id=clerk_org_id,
                clerk_user_id=provider_user.user_id,
                previous_role=changed_role_from,
                clerk_membership_id=(
                    provider_membership.membership_id if provider_membership else None
                ),
                error_category="local_commit_failed",
                safe_message=type(exc).__name__,
            )
            _raise_local_commit_failure(support_required=outcome.support_required)
        if operation_id is not None:
            await operation_service.transition(
                operation_id,
                models.MemberAccessOperationStatus.failed,
                error_category="local_commit_failed",
                safe_message=type(exc).__name__,
            )
        raise

    if operation_id is not None:
        await operation_service.transition(
            operation_id,
            models.MemberAccessOperationStatus.local_committed,
            membership_id=membership.id,
            account_id=account.id,
            clerk_invitation_id=invite_result.invitation_id if invite_result else None,
            clerk_membership_id=(
                provider_membership.membership_id if provider_membership else None
            ),
        )
    created = await _load_member(db, organization_id, membership.id)
    return _to_read(created)


async def update_member(
    db: AsyncSession,
    member_id: int,
    member_in: schemas.MemberUpdate,
    *,
    organization_id: int,
    current_admin: Actor,
    clerk_access: ClerkAccessService | None = None,
    operation_service: MemberAccessOperationService | None = None,
) -> schemas.MemberRead:
    member = await _load_member(db, organization_id, member_id)
    if member is None:
        raise member_error(404, "member_not_found", "Member not found.")
    if member.lifecycle_status != models.MembershipLifecycleStatus.active:
        raise member_error(409, "member_archived", "Restore the member before editing.")
    if member.access_status == models.MembershipAccessStatus.sync_error:
        raise member_error(
            409, "member_sync_error", "Resolve the synchronization error before editing."
        )
    if member_in.lock_version and member_in.lock_version != member.lock_version:
        raise member_error(409, "stale_member", "This member changed while you were editing.")

    current_caps = {cap.capability for cap in member.capabilities}
    previous_can_teach = member.can_teach
    next_caps = (
        _capability_values(member_in.capabilities)
        if member_in.capabilities is not None
        else current_caps
    )
    next_mode = member.teacher_access_mode
    if member_in.teacher_access_mode is not None:
        next_mode = models.TeacherAccessMode(member_in.teacher_access_mode)
    if models.MembershipCapability.teacher not in next_caps:
        next_mode = None
    elif next_mode is None:
        raise member_error(
            422,
            "validation_error",
            "Teacher access mode is required.",
            fields={"teacher_access_mode": "Required."},
        )
    if (
        models.MembershipCapability.admin in next_caps
        and next_mode == models.TeacherAccessMode.scheduler_only
    ):
        raise member_error(
            422,
            "validation_error",
            "Admins require platform access.",
            fields={"teacher_access_mode": "Use platform."},
        )

    await _assert_can_remove_admin_capability(
        db, member, current_admin, next_capabilities=next_caps
    )
    previous_snapshot = _access_snapshot(member)
    previous_role = member.expected_clerk_role
    target_role = _expected_role(next_caps, next_mode)
    clerk_access = clerk_access or ClerkAccessService()
    if models.MembershipCapability.teacher in next_caps and member_in.subject_ids is not None:
        await _validate_subject_ids(db, organization_id, member_in.subject_ids)

    if member_in.email and member.access_status != models.MembershipAccessStatus.active:
        updated = await db.scalar(
            text(
                """
                SELECT app_security.update_pending_account_email(
                    :organization_id, :account_id, :email
                )
                """
            ),
            {
                "organization_id": organization_id,
                "account_id": member.account_id,
                "email": _normalize_email(str(member_in.email)),
            },
        )
        if not updated:
            raise RuntimeError("The pending member email could not be updated.")
        await db.refresh(member.account)
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

    await _replace_capabilities(db, member, next_caps)
    await _sync_teacher_profile(
        db,
        member,
        capabilities=next_caps,
        subject_ids=member_in.subject_ids,
        current_admin=current_admin,
        previous_can_teach=previous_can_teach,
    )
    await db.flush()
    member = await _load_member(db, organization_id, member.id)
    member.updated_by_membership_id = current_admin.membership_id
    member.lock_version += 1

    if target_role is None and member.access_status != models.MembershipAccessStatus.none:
        await _revoke_provider_access(
            db,
            member=member,
            current_admin=current_admin,
            clerk_access=clerk_access,
            operation_service=operation_service,
        )
        member.access_status = models.MembershipAccessStatus.none
    elif target_role is not None:
        if (
            member.account.clerk_user_id
            and member.access_status == models.MembershipAccessStatus.active
        ):
            if previous_role != target_role:
                await _change_provider_role(
                    db,
                    member=member,
                    current_admin=current_admin,
                    clerk_access=clerk_access,
                    operation_type=models.MemberAccessOperationType.change_role,
                    previous_role=previous_role,
                    previous_snapshot=previous_snapshot,
                    operation_service=operation_service,
                )
        elif member.access_status == models.MembershipAccessStatus.none:
            await _send_invitation(
                db,
                member=member,
                current_admin=current_admin,
                clerk_access=clerk_access,
                operation_type=models.MemberAccessOperationType.create_invitation,
                previous_snapshot=previous_snapshot,
                operation_service=operation_service,
            )

    await db.flush()
    updated = await _load_member(db, organization_id, member.id)
    return _to_read(updated)


async def remove_member(
    db: AsyncSession,
    member_id: int,
    *,
    organization_id: int,
    current_admin: Actor,
    clerk_access: ClerkAccessService | None = None,
    operation_service: MemberAccessOperationService | None = None,
) -> dict:
    member = await _load_member(db, organization_id, member_id)
    if member is None:
        raise member_error(404, "member_not_found", "Member not found.")
    caps = {cap.capability for cap in member.capabilities}
    if member.account_id == current_admin.account_id and models.MembershipCapability.admin in caps:
        raise member_error(
            409, "self_admin_removal_blocked", "You cannot remove your own admin access."
        )
    if (
        models.MembershipCapability.admin in caps
        and await _active_admin_count(db, organization_id, exclude_member_id=member.id) == 0
    ):
        raise member_error(
            409, "last_active_admin_blocked", "At least one active admin must remain."
        )

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
    teacher_id = member.teacher_profile.id if member.teacher_profile else None
    teacher_subjects = sorted(member.teacher_profile.subject_ids) if member.teacher_profile else []
    scheduler_relevant = (
        teacher_id is not None
        and teacher_id
        in await _teacher_ids_with_scheduler_references(db, organization_id, [teacher_id])
    )
    await _revoke_provider_access(
        db,
        member=member,
        current_admin=current_admin,
        clerk_access=clerk_access or _require_operation_service(operation_service).clerk_access,
        operation_service=operation_service,
    )
    if actions.remove_effect == "hard_delete":
        if member.teacher_profile:
            await db.delete(member.teacher_profile)
            await _record_teacher_scheduler_change(
                db,
                member.organization_id,
                teacher_id=teacher_id,
                operation=models.SchedulerStateChangeOperation.DELETE,
                before={
                    "status": "active",
                    "can_teach": member.can_teach,
                    "subject_ids": teacher_subjects,
                },
                after=None,
                changed_by_membership_id=current_admin.membership_id,
                active_resource=scheduler_relevant,
            )
        await db.delete(member)
        return {"status": "removed", "remove_effect": "hard_delete"}
    member.lifecycle_status = models.MembershipLifecycleStatus.archived
    member.access_status = (
        models.MembershipAccessStatus.blocked
        if member.access_status != models.MembershipAccessStatus.none
        else models.MembershipAccessStatus.none
    )
    member.updated_by_membership_id = current_admin.membership_id
    member.lock_version += 1
    if member.teacher_profile or member.can_teach:
        teacher_id = teacher_id or member.id
        await _record_teacher_scheduler_change(
            db,
            member.organization_id,
            teacher_id=teacher_id,
            operation=models.SchedulerStateChangeOperation.DELETE,
            before={
                "status": "active",
                "can_teach": member.can_teach,
                "subject_ids": teacher_subjects,
            },
            after={
                "status": "archived",
                "can_teach": member.can_teach,
                "subject_ids": teacher_subjects,
            },
            changed_by_membership_id=current_admin.membership_id,
            active_resource=scheduler_relevant,
        )
    return {"status": "removed", "remove_effect": "archive"}


async def restore_member(
    db: AsyncSession,
    member_id: int,
    *,
    restore_in: schemas.MemberRestore | None = None,
    organization_id: int,
    current_admin: Actor,
    clerk_access: ClerkAccessService | None = None,
    operation_service: MemberAccessOperationService | None = None,
) -> schemas.MemberRead:
    member = await _load_member(db, organization_id, member_id)
    if member is None:
        raise member_error(404, "member_not_found", "Member not found.")
    if member.lifecycle_status != models.MembershipLifecycleStatus.archived:
        raise member_error(409, "member_not_archived", "Only archived members can be restored.")
    previous_snapshot = _access_snapshot(member)
    previous_role = member.expected_clerk_role
    previous_can_teach = member.can_teach
    previous_teacher_id = member.teacher_profile.id if member.teacher_profile else None
    previous_subjects = sorted(member.teacher_profile.subject_ids) if member.teacher_profile else []
    scheduler_relevant_before = (
        previous_teacher_id is not None
        and previous_teacher_id
        in await _teacher_ids_with_scheduler_references(db, organization_id, [previous_teacher_id])
    )
    if restore_in and restore_in.capabilities is not None:
        next_caps = _capability_values(restore_in.capabilities)
        next_mode = (
            models.TeacherAccessMode(restore_in.teacher_access_mode)
            if restore_in.teacher_access_mode
            else member.teacher_access_mode
        )
        if models.MembershipCapability.teacher not in next_caps:
            next_mode = None
        elif next_mode is None:
            raise member_error(
                422,
                "validation_error",
                "Teacher access mode is required.",
                fields={"teacher_access_mode": "Required."},
            )
        if not restore_in.restore_access and _expected_role(next_caps, next_mode) is not None:
            raise member_error(
                422,
                "validation_error",
                "Choose scheduler-only teacher access or restore platform access.",
                fields={"capabilities": "Platform capabilities require access."},
            )
        member.teacher_access_mode = next_mode
        await _replace_capabilities(db, member, next_caps)
        await _sync_teacher_profile(
            db,
            member,
            capabilities=next_caps,
            subject_ids=restore_in.subject_ids,
            current_admin=current_admin,
            previous_can_teach=previous_can_teach,
            record_change=False,
        )
    elif restore_in and not restore_in.restore_access and member.expected_clerk_role is not None:
        raise member_error(
            422,
            "validation_error",
            "Choose non-platform capabilities before restoring without access.",
        )
    member.lifecycle_status = models.MembershipLifecycleStatus.active
    member.updated_by_membership_id = current_admin.membership_id
    member.lock_version += 1
    if member.teacher_profile or member.can_teach:
        teacher_id = member.teacher_profile.id if member.teacher_profile else previous_teacher_id
        if teacher_id is not None:
            scheduler_relevant_after = teacher_id in await _teacher_ids_with_scheduler_references(
                db, organization_id, [teacher_id]
            )
            await _record_teacher_scheduler_change(
                db,
                member.organization_id,
                teacher_id=teacher_id,
                operation=models.SchedulerStateChangeOperation.CREATE,
                before={
                    "status": "archived",
                    "can_teach": previous_can_teach,
                    "subject_ids": previous_subjects,
                },
                after={
                    "status": "active",
                    "can_teach": member.can_teach,
                    "subject_ids": sorted(member.teacher_profile.subject_ids)
                    if member.teacher_profile and member.can_teach
                    else [],
                },
                changed_by_membership_id=current_admin.membership_id,
                active_resource=scheduler_relevant_before or scheduler_relevant_after,
            )
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
            operation_service=operation_service,
        )
    else:
        await _send_invitation(
            db,
            member=member,
            current_admin=current_admin,
            clerk_access=clerk_access or ClerkAccessService(),
            operation_type=models.MemberAccessOperationType.restore_access,
            previous_snapshot=previous_snapshot,
            operation_service=operation_service,
        )
    await db.flush()
    restored = await _load_member(db, organization_id, member.id)
    return _to_read(restored)


async def resend_invitation(
    db: AsyncSession,
    member_id: int,
    *,
    organization_id: int,
    current_admin: Actor,
    clerk_access: ClerkAccessService | None = None,
    operation_service: MemberAccessOperationService | None = None,
) -> schemas.MemberRead:
    member = await _load_member(db, organization_id, member_id)
    if member is None:
        raise member_error(404, "member_not_found", "Member not found.")
    if member.access_status not in {
        models.MembershipAccessStatus.pending_invite,
        models.MembershipAccessStatus.invite_expired,
    }:
        raise member_error(
            409, "resend_not_available", "Invitation resend is not available for this member."
        )
    if member.expected_clerk_role is None:
        raise member_error(
            409, "access_not_required", "This member does not require platform access."
        )
    clerk_access = clerk_access or ClerkAccessService()
    previous_snapshot = _access_snapshot(member)
    if (
        member.clerk_invitation_id
        and member.clerk_invitation_status == models.ClerkInvitationStatus.pending
    ):
        await _revoke_provider_access(
            db,
            member=member,
            current_admin=current_admin,
            clerk_access=clerk_access,
            operation_service=operation_service,
        )
    member.lock_version += 1
    await _send_invitation(
        db,
        member=member,
        current_admin=current_admin,
        clerk_access=clerk_access,
        operation_type=models.MemberAccessOperationType.resend_invitation,
        previous_snapshot=previous_snapshot,
        operation_service=operation_service,
    )
    await db.flush()
    updated = await _load_member(db, organization_id, member.id)
    return _to_read(updated)


async def retry_sync(
    db: AsyncSession,
    member_id: int,
    *,
    organization_id: int,
    current_admin: Actor,
    clerk_access: ClerkAccessService | None = None,
    operation_service: MemberAccessOperationService | None = None,
) -> schemas.MemberRead:
    member = await _load_member(db, organization_id, member_id)
    if member is None:
        raise member_error(404, "member_not_found", "Member not found.")
    if member.access_status != models.MembershipAccessStatus.sync_error:
        raise member_error(
            409, "retry_not_available", "Retry is only available for members in sync error."
        )
    clerk_access = clerk_access or ClerkAccessService()
    previous_snapshot = _access_snapshot(member)
    previous_role = member.expected_clerk_role
    member.access_error_category = None
    member.access_error_safe_message = None
    member.lock_version += 1
    if member.expected_clerk_role is None:
        await _revoke_provider_access(
            db,
            member=member,
            current_admin=current_admin,
            clerk_access=clerk_access,
            operation_service=operation_service,
        )
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
            operation_service=operation_service,
        )
    else:
        await _send_invitation(
            db,
            member=member,
            current_admin=current_admin,
            clerk_access=clerk_access,
            operation_type=models.MemberAccessOperationType.restore_access,
            previous_snapshot=previous_snapshot,
            operation_service=operation_service,
        )
    await db.flush()
    updated = await _load_member(db, organization_id, member.id)
    return _to_read(updated)


async def current_member(db: AsyncSession, *, current_user: Actor) -> schemas.CurrentMemberRead:
    member = await db.scalar(
        select(models.OrganizationMembership)
        .where(
            models.OrganizationMembership.organization_id == current_user.organization_id,
            models.OrganizationMembership.account_id == current_user.account_id,
        )
        .options(selectinload(models.OrganizationMembership.teacher_profile))
    )
    if member is None:
        raise member_error(403, "membership_required", "Membership required.")
    caps = sorted(cap.capability.value for cap in member.capabilities)
    modes = []
    if "admin" in caps:
        modes.append("admin")
    if "teacher" in caps:
        modes.append("teacher")

    foundation_status = await db.scalar(
        select(models.Organization.foundation_status).where(
            models.Organization.id == current_user.organization_id
        )
    )
    status_str = foundation_status.value if foundation_status else "NOT_STARTED"

    return schemas.CurrentMemberRead(
        member_id=member.id,
        account_id=current_user.account_id,
        organization_id=current_user.organization_id,
        capabilities=caps,
        access_status=member.access_status.value,
        lifecycle_status=member.lifecycle_status.value,
        teacher_id=member.teacher_profile.id if member.teacher_profile else None,
        default_mode="admin" if "admin" in caps else "teacher",
        available_modes=modes,
        foundation_status=status_str,
    )
