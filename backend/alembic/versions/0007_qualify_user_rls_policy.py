from alembic import op

revision = "0007_qualify_user_rls_policy"
down_revision = "0006_bootstrap_membership_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('DROP POLICY IF EXISTS "tenant_membership_accounts" ON "user"')
    op.execute(
        """
        CREATE POLICY "tenant_membership_accounts" ON "user"
        TO cronos_app
        USING (
            EXISTS (
                SELECT 1
                FROM organization_membership AS m
                WHERE m.account_id = "user".id
                  AND m.organization_id = app_security.current_organization_id()
            )
        )
        """
    )


def downgrade() -> None:
    op.execute('DROP POLICY IF EXISTS "tenant_membership_accounts" ON "user"')
    op.execute(
        """
        CREATE POLICY "tenant_membership_accounts" ON "user"
        TO cronos_app
        USING (
            EXISTS (
                SELECT 1
                FROM organization_membership AS m
                WHERE m.account_id = id
                  AND m.organization_id = app_security.current_organization_id()
            )
        )
        """
    )
