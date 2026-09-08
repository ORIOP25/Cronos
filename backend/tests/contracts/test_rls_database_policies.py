import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests._support.db_fixtures import runtime_sync_test_engine, sync_test_engine

pytestmark = pytest.mark.postgresql


def test_runtime_role_and_every_tenant_table_are_hardened(migrated_test_database):
    with runtime_sync_test_engine.connect() as connection:
        role = connection.execute(
            text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
        ).one()
        assert role == (False, False)
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM pg_tables "
                    "WHERE schemaname = 'public' AND tableowner = current_user"
                )
            )
            == 0
        )
        unhardened = (
            connection.execute(
                text(
                    """
                SELECT c.relname
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                JOIN information_schema.columns col
                  ON col.table_schema = n.nspname AND col.table_name = c.relname
                WHERE n.nspname = 'public'
                  AND c.relkind = 'r'
                  AND col.column_name = 'organization_id'
                  AND (NOT c.relrowsecurity OR NOT c.relforcerowsecurity)
                ORDER BY c.relname
                """
                )
            )
            .scalars()
            .all()
        )
        assert unhardened == []


def test_principal_resolution_and_cross_tenant_write_denial(clean_database):
    marker = uuid.uuid4().hex
    with runtime_sync_test_engine.connect() as connection:

        def founder(suffix: str):
            return connection.execute(
                text(
                    """
                    SELECT * FROM app_security.bootstrap_organization_admin(
                      :user_id, :org_id, :org_name, :email, :profile, :membership_id
                    )
                    """
                ),
                {
                    "user_id": f"user-{suffix}-{marker}",
                    "org_id": f"org-{suffix}-{marker}",
                    "org_name": f"Organization {suffix}",
                    "email": f"{suffix}-{marker}@example.test",
                    "profile": f"Admin {suffix}",
                    "membership_id": f"membership-{suffix}-{marker}",
                },
            ).one()

        account_a, org_a, membership_a = founder("a")
        _, org_b, _ = founder("b")
        connection.commit()

        principal = connection.execute(
            text("SELECT * FROM app_security.resolve_principal(:user_id, :org_id)"),
            {"user_id": f"user-a-{marker}", "org_id": f"org-a-{marker}"},
        ).one()
        assert principal.account_id == account_a
        assert principal.organization_id == org_a
        assert principal.membership_id == membership_a
        assert principal.can_admin is True

        connection.execute(
            text("SELECT set_config('app.current_organization_id', :org, true)"),
            {"org": str(org_a)},
        )
        assert connection.execute(text("SELECT id FROM organization")).scalars().all() == [org_a]
        with pytest.raises(DBAPIError):
            connection.execute(
                text(
                    "INSERT INTO room(name, capacity, type, organization_id) "
                    "VALUES ('cross tenant', 10, 'normal', :org)"
                ),
                {"org": org_b},
            )
        connection.rollback()


def test_user_rls_exposes_membership_accounts_to_the_current_tenant(clean_database):
    marker = uuid.uuid4().hex
    with runtime_sync_test_engine.connect() as connection:

        def founder(suffix: str):
            return connection.execute(
                text(
                    """
                    SELECT * FROM app_security.bootstrap_organization_admin(
                      :user_id, :org_id, :org_name, :email, :profile, :membership_id
                    )
                    """
                ),
                {
                    "user_id": f"user-{suffix}-{marker}",
                    "org_id": f"org-{suffix}-{marker}",
                    "org_name": f"Organization {suffix}",
                    "email": f"{suffix}-{marker}@example.test",
                    "profile": f"Admin {suffix}",
                    "membership_id": f"membership-{suffix}-{marker}",
                },
            ).one()

        account_a, org_a, _ = founder("a")
        account_b, _, _ = founder("b")
        connection.commit()

        connection.execute(
            text("SELECT set_config('app.current_organization_id', :org, true)"),
            {"org": str(org_a)},
        )
        visible_account = connection.execute(
            text('SELECT id, email FROM "user" WHERE id = :account_id'),
            {"account_id": account_a},
        ).one()
        hidden_accounts = connection.execute(
            text('SELECT id FROM "user" WHERE id = :account_id'),
            {"account_id": account_b},
        ).all()

        assert visible_account.id == account_a
        assert hidden_accounts == []


def test_identity_sync_cannot_reactivate_blocked_membership(clean_database):
    marker = uuid.uuid4().hex
    with runtime_sync_test_engine.connect() as connection:
        account_id, organization_id, membership_id = connection.execute(
            text(
                """
                SELECT * FROM app_security.bootstrap_organization_admin(
                  :user_id, :org_id, :org_name, :email, :profile, :membership_id
                )
                """
            ),
            {
                "user_id": f"user-blocked-{marker}",
                "org_id": f"org-blocked-{marker}",
                "org_name": "Blocked Organization",
                "email": f"blocked-{marker}@example.test",
                "profile": "Blocked User",
                "membership_id": f"membership-blocked-{marker}",
            },
        ).one()
        connection.commit()

    with sync_test_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE organization_membership "
                "SET access_status = 'blocked', can_admin = true "
                "WHERE id = :membership_id"
            ),
            {"membership_id": membership_id},
        )

    with runtime_sync_test_engine.connect() as connection:
        synced = connection.execute(
            text(
                """
                SELECT * FROM app_security.ensure_user(
                  :user_id, :email, :profile, 'admin', :organization_id, NULL
                )
                """
            ),
            {
                "user_id": f"user-blocked-{marker}",
                "email": f"blocked-{marker}@example.test",
                "profile": "Blocked User Updated",
                "organization_id": organization_id,
            },
        ).one()
        connection.execute(
            text("SELECT set_config('app.current_organization_id', :org, true)"),
            {"org": str(organization_id)},
        )
        status = connection.execute(
            text(
                "SELECT access_status, lifecycle_status, can_admin "
                "FROM organization_membership WHERE id = :membership_id"
            ),
            {"membership_id": membership_id},
        ).one()
        principal = connection.execute(
            text("SELECT * FROM app_security.resolve_principal(:user_id, :org_id)"),
            {
                "user_id": f"user-blocked-{marker}",
                "org_id": f"org-blocked-{marker}",
            },
        ).all()

    assert synced.id == account_id
    assert synced.organization_id == organization_id
    assert status == ("blocked", "active", True)
    assert principal == []
