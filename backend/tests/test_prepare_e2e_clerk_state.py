import pytest
from sqlalchemy import func, select

from app import models
from app.services.e2e_clerk_state import (
    ClerkOrganization,
    ClerkOrganizationMembership,
    ClerkUser,
    E2EClerkPreflightError,
    E2EClerkPrepConfig,
    config_from_env,
    prepare_e2e_clerk_state,
)


class FakeClerkDirectory:
    def __init__(self, *, users, organizations, memberships):
        self.users = {user.email: user for user in users}
        self.organizations = {org.id: org for org in organizations}
        self.memberships = memberships

    async def get_user_by_email(self, email):
        return self.users.get(email)

    async def get_organization(self, organization_id):
        return self.organizations.get(organization_id)

    async def list_user_organization_memberships(self, user_id):
        return [membership for membership in self.memberships if membership.user_id == user_id]

    async def get_organization_membership(self, organization_id, user_id):
        return next(
            (
                membership
                for membership in self.memberships
                if membership.organization_id == organization_id and membership.user_id == user_id
            ),
            None,
        )


def _directory(*, extra_admin_org=False, teacher_role="org:member"):
    orgs = [
        ClerkOrganization(id="org_e2e", name="Escola E2E"),
        ClerkOrganization(id="org_other", name="Outra Escola"),
    ]
    memberships = [
        ClerkOrganizationMembership(
            id="mem_admin",
            organization_id="org_e2e",
            user_id="user_admin",
            role="org:admin",
        ),
        ClerkOrganizationMembership(
            id="mem_teacher",
            organization_id="org_e2e",
            user_id="user_teacher",
            role=teacher_role,
        ),
    ]
    if extra_admin_org:
        memberships.append(
            ClerkOrganizationMembership(
                id="mem_admin_other",
                organization_id="org_other",
                user_id="user_admin",
                role="org:admin",
            )
        )
    return FakeClerkDirectory(
        users=[
            ClerkUser(
                id="user_admin",
                email="admin@example.com",
                name="Admin Real",
            ),
            ClerkUser(
                id="user_teacher",
                email="teacher@example.com",
                name="Teacher Real",
            ),
        ],
        organizations=orgs,
        memberships=memberships,
    )


def _config(org_id="org_e2e"):
    return E2EClerkPrepConfig(
        admin_email="admin@example.com",
        teacher_email="teacher@example.com",
        clerk_org_id=org_id,
    )


async def test_e2e_env_rejects_real_person_emails():
    with pytest.raises(E2EClerkPreflightError) as exc:
        config_from_env(
            {
                "CLERK_SECRET_KEY": "sk_test_example",
                "E2E_CLERK_ADMIN_EMAIL": "real.admin@example.com",
                "E2E_CLERK_TEACHER_EMAIL": "real.teacher@example.com",
                "E2E_CLERK_ORG_ID": "org_e2e",
            }
        )

    assert "Real-person emails are forbidden" in str(exc.value)


async def test_e2e_env_accepts_reserved_test_users_in_dedicated_org():
    config = config_from_env(
        {
            "CLERK_SECRET_KEY": "sk_test_example",
            "E2E_CLERK_ADMIN_EMAIL": "cronos-admin+clerk_test@example.com",
            "E2E_CLERK_TEACHER_EMAIL": "cronos-teacher+clerk_test@example.com",
            "E2E_CLERK_ORG_ID": "org_e2e",
        }
    )

    assert config.clerk_org_id == "org_e2e"


async def test_e2e_env_allows_org_discovery_for_reserved_test_users():
    config = config_from_env(
        {
            "CLERK_SECRET_KEY": "sk_test_example",
            "E2E_CLERK_ADMIN_EMAIL": "cronos-admin+clerk_test@example.com",
            "E2E_CLERK_TEACHER_EMAIL": "cronos-teacher+clerk_test@example.com",
        }
    )

    assert config.clerk_org_id is None


async def test_prepare_e2e_clerk_state_creates_admin_teacher_membership_idempotently(db_session):
    directory = _directory()

    first = await prepare_e2e_clerk_state(db_session, directory=directory, config=_config())
    await db_session.commit()
    second = await prepare_e2e_clerk_state(db_session, directory=directory, config=_config())
    await db_session.commit()

    assert first.organization_id == second.organization_id
    assert first.admin_user_id == second.admin_user_id
    assert first.teacher_user_id == second.teacher_user_id

    assert await db_session.scalar(select(func.count(models.Organization.id))) == 1
    assert await db_session.scalar(select(func.count(models.User.id))) == 2
    assert await db_session.scalar(select(func.count(models.OrganizationMembership.id))) == 2
    assert await db_session.scalar(select(func.count(models.Teacher.id))) == 1

    admin_user = await db_session.scalar(
        select(models.User).where(models.User.clerk_user_id == "user_admin")
    )
    teacher_user = await db_session.scalar(
        select(models.User).where(models.User.clerk_user_id == "user_teacher")
    )
    admin_membership = await db_session.scalar(
        select(models.OrganizationMembership).where(
            models.OrganizationMembership.account_id == admin_user.id
        )
    )
    teacher_membership = await db_session.scalar(
        select(models.OrganizationMembership).where(
            models.OrganizationMembership.account_id == teacher_user.id
        )
    )
    teacher_profile = await db_session.scalar(
        select(models.Teacher).where(
            models.Teacher.organization_membership_id == teacher_membership.id
        )
    )

    assert admin_membership.can_admin is True
    assert admin_membership.can_teach is False
    assert teacher_membership.can_admin is False
    assert teacher_membership.can_teach is True
    assert teacher_profile is not None
    assert teacher_profile.organization_membership_id is not None


async def test_prepare_e2e_clerk_state_requires_org_id_when_admin_has_multiple_orgs(db_session):
    with pytest.raises(E2EClerkPreflightError) as exc:
        await prepare_e2e_clerk_state(
            db_session,
            directory=_directory(extra_admin_org=True),
            config=_config(org_id=None),
        )

    assert "E2E_CLERK_ORG_ID" in str(exc.value)
    assert "exactly one" in str(exc.value)


async def test_prepare_e2e_clerk_state_rejects_teacher_without_member_role(db_session):
    with pytest.raises(E2EClerkPreflightError) as exc:
        await prepare_e2e_clerk_state(
            db_session,
            directory=_directory(teacher_role="org:admin"),
            config=_config(),
        )

    assert "teacher@example.com" in str(exc.value)
    assert "org:member" in str(exc.value)
