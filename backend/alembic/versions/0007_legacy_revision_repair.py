"""Repair databases created with the pre-RGPD migration history.

The compatibility revision is kept as a no-op alias. The repair migration
following it applies the missing current schema changes.
"""

from alembic import op

revision = "0007_legacy_revision_repair"
down_revision = "0007_qualify_user_rls_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0005 was renamed between migration histories. Keep the operation
    # idempotent for both fresh databases and legacy databases.
    op.execute(
        """
        ALTER TABLE public.organization_settings
        ADD COLUMN IF NOT EXISTS automatic_holidays_enabled BOOLEAN
        NOT NULL DEFAULT FALSE
        """
    )
    op.execute(
        """
        ALTER TABLE public.organization_settings
        ALTER COLUMN automatic_holidays_enabled SET DEFAULT FALSE
        """
    )
    op.execute(
        """
        UPDATE public.organization_settings
        SET automatic_holidays_enabled = FALSE
        WHERE automatic_holidays_enabled IS NULL
        """
    )
    op.execute(
        """
        ALTER TABLE public.organization_settings
        ALTER COLUMN automatic_holidays_enabled SET NOT NULL
        """
    )

    # 0006 changed identity synchronization into a strictly tenant-scoped,
    # non-mutating lookup/update.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app_security.ensure_user(
          requested_clerk_user_id text, requested_email text, requested_name text,
          requested_role text, requested_organization_id integer, requested_teacher_id integer
        ) RETURNS TABLE (id integer, organization_id integer)
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
          v_account_id integer;
          v_existing_clerk_account_id integer;
          v_matching_accounts integer;
          v_email text := lower(nullif(trim(requested_email), ''));
        BEGIN
          IF nullif(trim(requested_clerk_user_id), '') IS NULL
             OR requested_organization_id IS NULL THEN
            RETURN;
          END IF;

          SELECT u.id INTO v_existing_clerk_account_id
          FROM public."user" AS u
          WHERE u.clerk_user_id = requested_clerk_user_id;

          IF v_existing_clerk_account_id IS NOT NULL THEN
            SELECT m.account_id INTO v_account_id
            FROM public.organization_membership AS m
            WHERE m.organization_id = requested_organization_id
              AND m.account_id = v_existing_clerk_account_id;
            IF v_account_id IS NULL THEN
              RETURN;
            END IF;
          ELSE
            IF v_email IS NULL THEN
              RETURN;
            END IF;

            SELECT count(*), min(u.id)
              INTO v_matching_accounts, v_account_id
            FROM public."user" AS u
            JOIN public.organization_membership AS m ON m.account_id = u.id
            WHERE m.organization_id = requested_organization_id
              AND u.clerk_user_id IS NULL
              AND lower(u.email) = v_email;

            IF v_matching_accounts <> 1 THEN
              RETURN;
            END IF;
          END IF;

          UPDATE public."user" AS u SET
            clerk_user_id = requested_clerk_user_id,
            email = coalesce(v_email, u.email),
            name = coalesce(nullif(requested_name, ''), u.name),
            clerk_profile_name = coalesce(nullif(requested_name, ''), u.clerk_profile_name),
            last_clerk_sync_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
          WHERE u.id = v_account_id;

          RETURN QUERY SELECT v_account_id, requested_organization_id;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app_security.list_reconciliation_organization_ids()
        RETURNS SETOF integer
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
          SELECT id
          FROM public.organization
          WHERE plan_status = 'active'
          ORDER BY id
        $$
        """
    )
    op.execute(
        """
        ALTER FUNCTION app_security.ensure_user(
          text, text, text, text, integer, integer
        ) OWNER TO cronos_auth_definer
        """
    )
    op.execute(
        """
        REVOKE ALL ON FUNCTION app_security.ensure_user(
          text, text, text, text, integer, integer
        ) FROM PUBLIC
        """
    )
    op.execute(
        """
        GRANT EXECUTE ON FUNCTION app_security.ensure_user(
          text, text, text, text, integer, integer
        ) TO cronos_app
        """
    )
    op.execute(
        """
        ALTER FUNCTION app_security.list_reconciliation_organization_ids()
        OWNER TO cronos_auth_definer
        """
    )
    op.execute(
        """
        REVOKE ALL ON FUNCTION app_security.list_reconciliation_organization_ids()
        FROM PUBLIC
        """
    )
    op.execute(
        """
        GRANT EXECUTE ON FUNCTION app_security.list_reconciliation_organization_ids()
        TO cronos_app
        """
    )

    # The old revision already qualified this policy, but recreating it keeps
    # partially migrated databases within the tenant isolation contract.
    op.execute('DROP POLICY IF EXISTS "tenant_membership_accounts" ON public."user"')
    op.execute(
        """
        CREATE POLICY "tenant_membership_accounts" ON public."user"
        TO cronos_app
        USING (
            EXISTS (
                SELECT 1
                FROM public.organization_membership AS m
                WHERE m.account_id = public."user".id
                  AND m.organization_id = app_security.current_organization_id()
            )
        )
        """
    )


def downgrade() -> None:
    # Do not undo the current security boundary or data shape.
    pass
