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


def test_class_availability_is_tenant_hardened_and_least_privileged(migrated_test_database):
    with runtime_sync_test_engine.connect() as connection:
        hardened = connection.scalar(
            text(
                "SELECT relrowsecurity AND relforcerowsecurity FROM pg_class "
                "WHERE relnamespace = 'public'::regnamespace AND relname = 'class_availability'"
            )
        )
        assert hardened is True
        policies = connection.execute(
            text(
                "SELECT policyname, roles::text FROM pg_policies "
                "WHERE schemaname = 'public' AND tablename = 'class_availability'"
            )
        ).all()
        assert policies == [("tenant_isolation", "{cronos_app}")]
        grants = set(
            connection.execute(
                text(
                    "SELECT privilege_type FROM information_schema.role_table_grants "
                    "WHERE table_schema = 'public' AND table_name = 'class_availability' "
                    "AND grantee = 'cronos_app'"
                )
            )
            .scalars()
            .all()
        )
        assert grants == {"SELECT", "INSERT", "DELETE"}


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
        room_type_b = connection.execute(
            text("SELECT id FROM room_type WHERE organization_id = :organization_id AND is_normal"),
            {"organization_id": org_b},
        ).scalar_one()
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
                    "INSERT INTO room(name, capacity, room_type_id, organization_id) "
                    "VALUES ('cross tenant', 10, :room_type_id, :org)"
                ),
                {"room_type_id": room_type_b, "org": org_b},
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


def test_legal_acceptance_rls_is_tenant_scoped_and_read_only_for_runtime(clean_database):
    marker = uuid.uuid4().hex
    with sync_test_engine.begin() as connection:
        organization_a = connection.execute(
            text(
                "INSERT INTO organization(name, clerk_org_id, plan_status) "
                "VALUES ('Legal A', :clerk_org_id, 'active') RETURNING id"
            ),
            {"clerk_org_id": f"legal-a-{marker}"},
        ).scalar_one()
        organization_b = connection.execute(
            text(
                "INSERT INTO organization(name, clerk_org_id, plan_status) "
                "VALUES ('Legal B', :clerk_org_id, 'active') RETURNING id"
            ),
            {"clerk_org_id": f"legal-b-{marker}"},
        ).scalar_one()
        for organization_id in (organization_a, organization_b):
            connection.execute(
                text(
                    "INSERT INTO organization_legal_acceptance ("
                    "organization_id, accepted_by_membership_id_snapshot, "
                    "controller_legal_name, controller_registration_number, "
                    "controller_registered_address, controller_contact_email, "
                    "representative_name, representative_role, authority_confirmed, "
                    "terms_version, dpa_version, privacy_version"
                    ") VALUES (:organization_id, 1, 'Entidade', '999999990', 'Rua 1', "
                    "'legal@test.com', 'Representante', 'Administrador', true, '2026-01', '2026-01', '2026-01')"
                ),
                {"organization_id": organization_id},
            )

    with runtime_sync_test_engine.connect() as connection:
        connection.execute(
            text("SELECT set_config('app.current_organization_id', :organization_id, true)"),
            {"organization_id": str(organization_a)},
        )
        visible = (
            connection.execute(text("SELECT organization_id FROM organization_legal_acceptance"))
            .scalars()
            .all()
        )
        hidden = connection.execute(
            text(
                "SELECT organization_id FROM organization_legal_acceptance "
                "WHERE organization_id = :organization_id"
            ),
            {"organization_id": organization_b},
        ).all()
        assert visible == [organization_a]
        assert hidden == []
        with pytest.raises(DBAPIError):
            connection.execute(
                text(
                    "DELETE FROM organization_legal_acceptance WHERE organization_id = :organization_id"
                ),
                {"organization_id": organization_a},
            )


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
