"""Allow a deleted Clerk identity to start a new local account safely."""

from alembic import op

revision = "0005_reclaim_deleted_identity"
down_revision = "0004_foundation_telemetry"
branch_labels = None
depends_on = None


IDENTITY_SIGNATURE = "text"
FINDER_SIGNATURE = "text, text"


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app_security.find_clerk_user_by_email(
            requested_email text,
            excluded_clerk_user_id text
        )
        RETURNS text
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT clerk_user_id
            FROM public."user"
            WHERE lower(email) = lower(requested_email)
              AND clerk_user_id IS NOT NULL
              AND clerk_user_id <> excluded_clerk_user_id
            LIMIT 1
        $$;
        """
    )
    op.execute(
        f"ALTER FUNCTION app_security.find_clerk_user_by_email({FINDER_SIGNATURE}) "
        "OWNER TO cronos_auth_definer"
    )
    op.execute(
        f"REVOKE ALL ON FUNCTION app_security.find_clerk_user_by_email({FINDER_SIGNATURE}) "
        "FROM PUBLIC"
    )
    op.execute(
        f"GRANT EXECUTE ON FUNCTION app_security.find_clerk_user_by_email({FINDER_SIGNATURE}) "
        "TO cronos_app"
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app_security.reclaim_deleted_clerk_identity(
            requested_clerk_user_id text
        )
        RETURNS boolean
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            v_account_id integer;
            v_tombstone_email text;
        BEGIN
            SELECT id INTO v_account_id
            FROM public."user"
            WHERE clerk_user_id = requested_clerk_user_id
            FOR UPDATE;

            IF v_account_id IS NULL THEN
                RETURN false;
            END IF;

            v_tombstone_email :=
                'deleted+' || md5(requested_clerk_user_id) || '@invalid.local';

            UPDATE public.organization_membership
            SET lifecycle_status = 'archived',
                access_status = 'none',
                clerk_membership_id = NULL,
                access_block_reason = 'provider_user_deleted',
                updated_at = CURRENT_TIMESTAMP
            WHERE account_id = v_account_id;

            UPDATE public."user"
            SET clerk_user_id = NULL,
                email = v_tombstone_email,
                clerk_primary_email_id = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = v_account_id;

            RETURN true;
        END;
        $$;
        """
    )
    op.execute(
        f"ALTER FUNCTION app_security.reclaim_deleted_clerk_identity({IDENTITY_SIGNATURE}) "
        "OWNER TO cronos_auth_definer"
    )
    op.execute(
        f"REVOKE ALL ON FUNCTION app_security.reclaim_deleted_clerk_identity({IDENTITY_SIGNATURE}) "
        "FROM PUBLIC"
    )
    op.execute(
        f"GRANT EXECUTE ON FUNCTION app_security.reclaim_deleted_clerk_identity({IDENTITY_SIGNATURE}) "
        "TO cronos_app"
    )


def downgrade() -> None:
    op.execute(f"DROP FUNCTION IF EXISTS app_security.find_clerk_user_by_email({FINDER_SIGNATURE})")
    op.execute(
        f"DROP FUNCTION IF EXISTS app_security.reclaim_deleted_clerk_identity({IDENTITY_SIGNATURE})"
    )
