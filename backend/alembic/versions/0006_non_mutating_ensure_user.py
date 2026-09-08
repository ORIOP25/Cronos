"""Prevent identity synchronization from changing membership authorization."""

from alembic import op

revision = "0006_non_mutating_ensure_user"
down_revision = "0005_automatic_holidays"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
CREATE OR REPLACE FUNCTION app_security.ensure_user(
  requested_clerk_user_id text, requested_email text, requested_name text,
  requested_role text, requested_organization_id integer, requested_teacher_id integer
) RETURNS TABLE (id integer, organization_id integer)
LANGUAGE plpgsql SECURITY DEFINER
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
        "ALTER FUNCTION app_security.ensure_user(text, text, text, text, integer, integer) OWNER TO cronos_auth_definer"
    )
    op.execute(
        "REVOKE ALL ON FUNCTION app_security.ensure_user(text, text, text, text, integer, integer) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION app_security.ensure_user(text, text, text, text, integer, integer) TO cronos_app"
    )
    op.execute(
        "ALTER FUNCTION app_security.list_reconciliation_organization_ids() OWNER TO cronos_auth_definer"
    )
    op.execute(
        "REVOKE ALL ON FUNCTION app_security.list_reconciliation_organization_ids() FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION app_security.list_reconciliation_organization_ids() TO cronos_app"
    )


def downgrade() -> None:
    # Keep the non-mutating security boundary when rolling back unrelated schema changes.
    pass
