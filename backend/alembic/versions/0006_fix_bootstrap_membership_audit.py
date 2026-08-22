from alembic import op

revision = "0006_bootstrap_membership_audit"
down_revision = "0005_reclaim_deleted_identity"
branch_labels = None
depends_on = None


BOOTSTRAP_SIGNATURE = "text, text, text, text, text, text"


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app_security.bootstrap_organization_admin(
            requested_clerk_user_id text, requested_clerk_org_id text,
            requested_organization_name text, requested_email text,
            requested_profile_name text, requested_membership_id text
        )
        RETURNS TABLE (account_id integer, organization_id integer, membership_id integer)
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
        DECLARE
            v_org integer;
            v_account integer;
            v_member integer;
            v_email text := lower(coalesce(nullif(trim(requested_email), ''), requested_clerk_user_id || '@clerk.local'));
        BEGIN
            PERFORM pg_advisory_xact_lock(hashtext(requested_clerk_org_id));
            SELECT id INTO v_org FROM public.organization WHERE clerk_org_id = requested_clerk_org_id;
            IF v_org IS NULL THEN
                INSERT INTO public.organization(name, clerk_org_id, plan_status, foundation_status)
                VALUES (requested_organization_name, requested_clerk_org_id, 'active', 'NOT_STARTED')
                RETURNING id INTO v_org;
            ELSIF (SELECT plan_status FROM public.organization WHERE id = v_org) <> 'active' THEN
                RETURN;
            END IF;
            IF EXISTS (SELECT 1 FROM public.organization_membership m WHERE m.organization_id = v_org) THEN
                RETURN QUERY SELECT u.id, v_org, m.id FROM public."user" u
                JOIN public.organization_membership m ON m.account_id = u.id
                WHERE m.organization_id = v_org AND u.clerk_user_id = requested_clerk_user_id
                  AND m.clerk_membership_id = requested_membership_id AND m.lifecycle_status = 'active'
                  AND m.access_status = 'active' AND m.can_admin;
                RETURN;
            END IF;
            SELECT id INTO v_account FROM public."user" WHERE clerk_user_id = requested_clerk_user_id;
            IF v_account IS NULL THEN
                SELECT id INTO v_account FROM public."user" WHERE lower(email) = v_email AND clerk_user_id IS NULL;
            END IF;
            IF v_account IS NULL AND EXISTS (SELECT 1 FROM public."user" WHERE lower(email) = v_email) THEN
                RETURN;
            END IF;
            IF v_account IS NULL THEN
                INSERT INTO public."user"(name, email, clerk_user_id, clerk_profile_name, last_clerk_sync_at, created_at, updated_at)
                VALUES (requested_profile_name, v_email, requested_clerk_user_id, requested_profile_name, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                RETURNING id INTO v_account;
            END IF;
            INSERT INTO public.organization_membership(
                organization_id, account_id, organization_display_name, lifecycle_status, access_status,
                can_admin, can_teach, clerk_membership_id, created_by_membership_id,
                updated_by_membership_id, lock_version, created_at, updated_at
            ) VALUES (
                v_org, v_account, requested_organization_name, 'active', 'active', true, false,
                requested_membership_id, NULL, NULL, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            ) RETURNING id INTO v_member;
            UPDATE public.organization_membership
            SET created_by_membership_id = v_member,
                updated_by_membership_id = v_member
            WHERE id = v_member;
            RETURN QUERY SELECT v_account, v_org, v_member;
        END;
        $$;
        """
    )
    op.execute(
        f"ALTER FUNCTION app_security.bootstrap_organization_admin({BOOTSTRAP_SIGNATURE}) "
        "OWNER TO cronos_auth_definer"
    )
    op.execute(
        f"REVOKE ALL ON FUNCTION app_security.bootstrap_organization_admin({BOOTSTRAP_SIGNATURE}) FROM PUBLIC"
    )
    op.execute(
        f"GRANT EXECUTE ON FUNCTION app_security.bootstrap_organization_admin({BOOTSTRAP_SIGNATURE}) TO cronos_app"
    )


def downgrade() -> None:
    # The previous function remains available through migration 0004.
    pass
