from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models


@dataclass(slots=True)
class CutoverReport:
    admins_without_membership: list[dict[str, Any]] = field(default_factory=list)
    duplicate_emails: list[dict[str, Any]] = field(default_factory=list)
    duplicate_clerk_user_ids: list[dict[str, Any]] = field(default_factory=list)
    teacher_links_without_membership: list[dict[str, Any]] = field(default_factory=list)
    local_login_stubs: list[dict[str, Any]] = field(default_factory=list)
    pending_invites: list[dict[str, Any]] = field(default_factory=list)
    active_admins_missing_provider_verification: list[dict[str, Any]] = field(default_factory=list)
    zero_admin_organizations: list[dict[str, Any]] = field(default_factory=list)
    organizations_missing_clerk_webhook: list[dict[str, Any]] = field(default_factory=list)
    legacy_write_quarantined: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def blockers(self) -> list[str]:
        blockers: list[str] = []
        if self.duplicate_emails:
            blockers.append("duplicate_emails")
        if self.duplicate_clerk_user_ids:
            blockers.append("duplicate_clerk_user_ids")
        if self.local_login_stubs:
            blockers.append("local_login_stubs")
        if self.zero_admin_organizations:
            blockers.append("zero_admin_organizations")
        if self.active_admins_missing_provider_verification:
            blockers.append("active_admins_missing_provider_verification")
        if self.organizations_missing_clerk_webhook:
            blockers.append("organizations_missing_clerk_webhook")
        return blockers


async def generate_cutover_report(db: AsyncSession, *, webhook_secret_configured: bool = False) -> CutoverReport:
    report = CutoverReport()

    duplicate_email_rows = await db.execute(
        select(func.lower(models.User.email), func.count())
        .group_by(func.lower(models.User.email))
        .having(func.count() > 1)
    )
    report.duplicate_emails = [{"email": email, "count": count} for email, count in duplicate_email_rows.all()]

    duplicate_clerk_rows = await db.execute(
        select(models.User.clerk_user_id, func.count())
        .where(models.User.clerk_user_id.is_not(None))
        .group_by(models.User.clerk_user_id)
        .having(func.count() > 1)
    )
    report.duplicate_clerk_user_ids = [{"clerk_user_id": clerk_user_id, "count": count} for clerk_user_id, count in duplicate_clerk_rows.all()]

    stub_rows = await db.execute(
        select(models.User).where(
            models.User.clerk_user_id.is_(None),
            models.User.organization_id.is_not(None),
            models.User.role.is_not(None),
        )
    )
    report.local_login_stubs = [
        {"user_id": user.id, "email": user.email, "organization_id": user.organization_id, "role": user.role.value if user.role else None}
        for user in stub_rows.scalars().all()
    ]

    admin_rows = await db.execute(
        select(models.User)
        .outerjoin(
            models.OrganizationMembership,
            (models.OrganizationMembership.account_id == models.User.id)
            & (models.OrganizationMembership.organization_id == models.User.organization_id),
        )
        .where(
            models.User.role == models.UserRole.admin,
            models.User.organization_id.is_not(None),
            models.OrganizationMembership.id.is_(None),
        )
    )
    report.admins_without_membership = [
        {"user_id": user.id, "email": user.email, "organization_id": user.organization_id}
        for user in admin_rows.scalars().all()
    ]

    teacher_rows = await db.execute(
        select(models.Teacher)
        .where(models.Teacher.organization_membership_id.is_(None), models.Teacher.archived_at.is_(None))
    )
    report.teacher_links_without_membership = [
        {"teacher_id": teacher.id, "name": teacher.name, "organization_id": teacher.organization_id}
        for teacher in teacher_rows.scalars().all()
    ]

    pending_rows = await db.execute(
        select(models.OrganizationMembership).where(
            models.OrganizationMembership.access_status == models.MembershipAccessStatus.pending_invite
        )
    )
    report.pending_invites = [
        {"membership_id": member.id, "organization_id": member.organization_id, "invitation_id": member.clerk_invitation_id}
        for member in pending_rows.scalars().all()
    ]

    unverified_admin_rows = await db.execute(
        select(models.OrganizationMembership, models.User, models.Organization)
        .join(models.OrganizationMembershipCapability)
        .join(models.User, models.User.id == models.OrganizationMembership.account_id)
        .join(models.Organization, models.Organization.id == models.OrganizationMembership.organization_id)
        .where(
            models.OrganizationMembership.lifecycle_status == models.MembershipLifecycleStatus.active,
            models.OrganizationMembership.access_status == models.MembershipAccessStatus.active,
            models.OrganizationMembership.expected_clerk_role == models.ClerkOrganizationRole.admin,
            models.OrganizationMembership.clerk_membership_id.is_(None),
            models.OrganizationMembershipCapability.capability == models.MembershipCapability.admin,
            models.User.clerk_user_id.is_not(None),
        )
    )
    report.active_admins_missing_provider_verification = [
        {
            "membership_id": member.id,
            "user_id": user.id,
            "email": user.email,
            "organization_id": org.id,
            "clerk_org_id": org.clerk_org_id,
            "clerk_user_id": user.clerk_user_id,
        }
        for member, user, org in unverified_admin_rows.all()
    ]

    org_rows = await db.execute(select(models.Organization))
    organizations = org_rows.scalars().all()
    for org in organizations:
        active_admin_count = await db.scalar(
            select(func.count())
            .select_from(models.OrganizationMembership)
            .join(models.OrganizationMembershipCapability)
            .join(models.User, models.User.id == models.OrganizationMembership.account_id)
            .where(
                models.OrganizationMembership.organization_id == org.id,
                models.OrganizationMembership.lifecycle_status == models.MembershipLifecycleStatus.active,
                models.OrganizationMembership.access_status == models.MembershipAccessStatus.active,
                models.OrganizationMembership.expected_clerk_role == models.ClerkOrganizationRole.admin,
                models.OrganizationMembership.clerk_membership_id.is_not(None),
                models.OrganizationMembershipCapability.capability == models.MembershipCapability.admin,
                models.User.clerk_user_id.is_not(None),
            )
        )
        if not active_admin_count:
            report.zero_admin_organizations.append({"organization_id": org.id, "name": org.name, "clerk_org_id": org.clerk_org_id})
        if org.clerk_org_id and not webhook_secret_configured:
            report.organizations_missing_clerk_webhook.append({"organization_id": org.id, "name": org.name, "clerk_org_id": org.clerk_org_id})
    return report


async def bootstrap_legacy_memberships(db: AsyncSession, *, apply: bool = False) -> dict[str, Any]:
    created = 0
    linked_teachers = 0
    user_rows = await db.execute(
        select(models.User).where(models.User.organization_id.is_not(None), models.User.role.is_not(None))
    )
    for user in user_rows.scalars().all():
        existing = await db.scalar(
            select(models.OrganizationMembership).where(
                models.OrganizationMembership.organization_id == user.organization_id,
                models.OrganizationMembership.account_id == user.id,
            )
        )
        if existing is not None:
            continue
        if not apply:
            created += 1
            continue
        capabilities = [models.MembershipCapability.admin] if user.role == models.UserRole.admin else [models.MembershipCapability.teacher]
        access_mode = models.TeacherAccessMode.platform if user.role == models.UserRole.teacher and user.clerk_user_id else None
        if user.role == models.UserRole.teacher and user.teacher_id and not user.clerk_user_id:
            access_mode = models.TeacherAccessMode.scheduler_only
        expected_role = models.ClerkOrganizationRole.admin if user.role == models.UserRole.admin else (
            models.ClerkOrganizationRole.member if access_mode == models.TeacherAccessMode.platform else None
        )
        member = models.OrganizationMembership(
            organization_id=user.organization_id,
            account_id=user.id,
            organization_display_name=user.name or user.email,
            lifecycle_status=models.MembershipLifecycleStatus.active,
            access_status=models.MembershipAccessStatus.sync_error if user.clerk_user_id and expected_role else models.MembershipAccessStatus.none,
            teacher_access_mode=access_mode,
            expected_clerk_role=expected_role,
        )
        db.add(member)
        await db.flush()
        for capability in capabilities:
            db.add(models.OrganizationMembershipCapability(organization_membership_id=member.id, capability=capability))
        if user.teacher_id:
            teacher = await db.get(models.Teacher, user.teacher_id)
            if teacher and teacher.organization_membership_id is None:
                teacher.organization_membership_id = member.id
                linked_teachers += 1
        created += 1
    await db.flush()
    return {"memberships": created, "teacher_links": linked_teachers, "applied": apply}
