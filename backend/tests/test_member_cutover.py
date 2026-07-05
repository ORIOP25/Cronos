import pytest


pytestmark = pytest.mark.asyncio


async def test_cutover_report_requires_provider_verified_active_admin(db_session):
    from app import models
    from app.services.member_cutover_service import generate_cutover_report

    org = models.Organization(name="Cutover Org", clerk_org_id="org_cutover", plan_status="active")
    admin = models.User(email="cutover.admin@example.com", name="Cutover Admin", clerk_user_id="user_cutover_admin")
    db_session.add_all([org, admin])
    await db_session.flush()
    member = models.OrganizationMembership(
        organization_id=org.id,
        account_id=admin.id,
        organization_display_name="Cutover Admin",
        lifecycle_status=models.MembershipLifecycleStatus.active,
        access_status=models.MembershipAccessStatus.active,
        expected_clerk_role=models.ClerkOrganizationRole.admin,
        clerk_membership_id=None,
    )
    db_session.add(member)
    await db_session.flush()
    db_session.add(
        models.OrganizationMembershipCapability(
            organization_membership_id=member.id,
            capability=models.MembershipCapability.admin,
        )
    )
    await db_session.commit()

    report = await generate_cutover_report(db_session, webhook_secret_configured=True)

    assert report.active_admins_missing_provider_verification == [
        {
            "membership_id": member.id,
            "user_id": admin.id,
            "email": admin.email,
            "organization_id": org.id,
            "clerk_org_id": org.clerk_org_id,
            "clerk_user_id": admin.clerk_user_id,
        }
    ]
    assert report.zero_admin_organizations == [
        {"organization_id": org.id, "name": org.name, "clerk_org_id": org.clerk_org_id}
    ]
    assert "active_admins_missing_provider_verification" in report.blockers
    assert "zero_admin_organizations" in report.blockers
