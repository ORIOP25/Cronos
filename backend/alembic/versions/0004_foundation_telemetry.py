"""Create the Foundation v1 schema and its append-only telemetry table."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0004_foundation_telemetry"
down_revision = "0003_remove_auto_confirm"
branch_labels = None
depends_on = None

BOOTSTRAP_SIGNATURE = "text, text, text, text, text, text"


def upgrade() -> None:
    op.execute(
        "CREATE TYPE organizationfoundationstatus AS ENUM ('NOT_STARTED', 'IN_PROGRESS', 'COMPLETED')"
    )
    op.execute(
        "ALTER TABLE public.organization ADD COLUMN foundation_status organizationfoundationstatus NOT NULL DEFAULT 'NOT_STARTED'"
    )
    op.execute(
        "ALTER TABLE public.organization ADD COLUMN foundation_completed_at TIMESTAMP WITH TIME ZONE"
    )
    op.execute(
        "ALTER TABLE public.organization ADD COLUMN first_real_schedule_approved_at TIMESTAMP WITH TIME ZONE"
    )
    op.create_check_constraint(
        "chk_organization_foundation_completed_at_required",
        "organization",
        "foundation_status != 'COMPLETED' OR foundation_completed_at IS NOT NULL",
        schema="public",
    )
    op.create_check_constraint(
        "chk_organization_first_real_schedule_requires_completed",
        "organization",
        "first_real_schedule_approved_at IS NULL OR foundation_status = 'COMPLETED'",
        schema="public",
    )

    op.create_table(
        "organization_foundation_draft",
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("current_step", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_by_membership_id", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("version > 0", name="chk_organization_foundation_draft_version"),
        sa.CheckConstraint("current_step BETWEEN 1 AND 9", name="chk_organization_foundation_draft_current_step"),
        sa.ForeignKeyConstraint(["organization_id"], ["public.organization.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id", "updated_by_membership_id"],
            ["public.organization_membership.organization_id", "public.organization_membership.id"],
            name="fk_org_foundation_draft_membership_tenant_scoped",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("organization_id"),
        schema="public",
    )
    op.create_table(
        "tutorial_telemetry_event",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("tutorial_run_id", sa.UUID(), nullable=False),
        sa.Column("client_event_id", sa.UUID(), nullable=False),
        sa.Column("tutorial_version", sa.Integer(), nullable=False),
        sa.Column("event_name", sa.String(length=40), nullable=False),
        sa.Column("chapter", sa.SmallInteger(), nullable=True),
        sa.Column("step_id", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint(
            "event_name IN ('tutorial_opened', 'chapter_started', 'step_skipped', 'tutorial_exited', 'tutorial_completed', 'tutorial_repeated')",
            name="chk_tutorial_telemetry_event_name",
        ),
        sa.CheckConstraint("chapter IS NULL OR chapter IN (1, 2)", name="chk_tutorial_telemetry_chapter"),
        sa.CheckConstraint("tutorial_version > 0", name="chk_tutorial_telemetry_version"),
        sa.ForeignKeyConstraint(["organization_id"], ["public.organization.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "client_event_id", name="uq_tutorial_telemetry_client_event"),
        schema="public",
    )
    op.create_index("ix_tutorial_telemetry_event_organization_id", "tutorial_telemetry_event", ["organization_id"], schema="public")
    op.create_index("ix_tutorial_telemetry_run", "tutorial_telemetry_event", ["organization_id", "tutorial_run_id", "created_at"], schema="public")
    op.create_index("ix_tutorial_telemetry_version_event", "tutorial_telemetry_event", ["organization_id", "tutorial_version", "event_name"], schema="public")

    op.execute("ALTER TABLE public.organization_foundation_draft ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.organization_foundation_draft FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY organization_foundation_draft_tenant_isolation
        ON public.organization_foundation_draft FOR ALL
        USING (organization_id = app_security.current_organization_id())
        WITH CHECK (organization_id = app_security.current_organization_id())
        """
    )
    op.execute("ALTER TABLE public.tutorial_telemetry_event ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.tutorial_telemetry_event FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tutorial_telemetry_event_tenant_isolation
        ON public.tutorial_telemetry_event FOR ALL
        USING (organization_id = app_security.current_organization_id())
        WITH CHECK (organization_id = app_security.current_organization_id())
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON public.organization_foundation_draft TO cronos_app")
    op.execute("GRANT SELECT, INSERT ON public.tutorial_telemetry_event TO cronos_app")
    op.execute("REVOKE UPDATE, DELETE ON public.tutorial_telemetry_event FROM cronos_app")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE public.tutorial_telemetry_event_id_seq TO cronos_app")

    # 0002 leaves the obsolete contract installed. The head exposes only the canonical name.
    op.execute(f"DROP FUNCTION IF EXISTS app_security.bootstrap_founder({BOOTSTRAP_SIGNATURE})")
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
            IF EXISTS (SELECT 1 FROM public.organization_membership WHERE organization_id = v_org) THEN
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
                requested_membership_id, v_account, v_account, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            ) RETURNING id INTO v_member;
            RETURN QUERY SELECT v_account, v_org, v_member;
        END;
        $$;
        """
    )
    op.execute(f"ALTER FUNCTION app_security.bootstrap_organization_admin({BOOTSTRAP_SIGNATURE}) OWNER TO cronos_auth_definer")
    op.execute(f"REVOKE ALL ON FUNCTION app_security.bootstrap_organization_admin({BOOTSTRAP_SIGNATURE}) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION app_security.bootstrap_organization_admin({BOOTSTRAP_SIGNATURE}) TO cronos_app")

    op.execute(
        """
        CREATE OR REPLACE FUNCTION app_security.trg_fn_organization_foundation_monotonic()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP IN ('INSERT', 'UPDATE') THEN
                IF NEW.foundation_status = 'COMPLETED' AND NEW.foundation_completed_at IS NULL THEN
                    RAISE EXCEPTION 'organization.foundation_completed_at is required when foundation_status is COMPLETED' USING ERRCODE = '23514';
                END IF;
                IF NEW.first_real_schedule_approved_at IS NOT NULL AND NEW.foundation_status <> 'COMPLETED' THEN
                    RAISE EXCEPTION 'first_real_schedule_approved_at requires foundation_status to be COMPLETED' USING ERRCODE = '23514';
                END IF;
                IF TG_OP = 'UPDATE' AND OLD.foundation_status = 'COMPLETED' AND NEW.foundation_status <> 'COMPLETED' THEN
                    RAISE EXCEPTION 'organization.foundation_status COMPLETED cannot regress' USING ERRCODE = '23514';
                END IF;
                IF TG_OP = 'UPDATE' AND OLD.foundation_completed_at IS NOT NULL AND NEW.foundation_completed_at IS DISTINCT FROM OLD.foundation_completed_at THEN
                    RAISE EXCEPTION 'organization.foundation_completed_at is immutable once set' USING ERRCODE = '23514';
                END IF;
                IF TG_OP = 'UPDATE' AND OLD.first_real_schedule_approved_at IS NOT NULL AND NEW.first_real_schedule_approved_at IS DISTINCT FROM OLD.first_real_schedule_approved_at THEN
                    RAISE EXCEPTION 'organization.first_real_schedule_approved_at is immutable once set' USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END IF;
            IF OLD.foundation_status = 'COMPLETED' OR OLD.foundation_completed_at IS NOT NULL OR OLD.first_real_schedule_approved_at IS NOT NULL THEN
                RAISE EXCEPTION 'Cannot delete organization with completed foundation or approved schedules' USING ERRCODE = '23514';
            END IF;
            RETURN OLD;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_organization_foundation_monotonic
        BEFORE INSERT OR UPDATE OR DELETE ON public.organization
        FOR EACH ROW EXECUTE FUNCTION app_security.trg_fn_organization_foundation_monotonic()
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app_security.trg_fn_tutorial_telemetry_append_only()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'tutorial_telemetry_event is append-only; % is prohibited', TG_OP USING ERRCODE = '42501';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_tutorial_telemetry_append_only
        BEFORE UPDATE OR DELETE ON public.tutorial_telemetry_event
        FOR EACH ROW EXECUTE FUNCTION app_security.trg_fn_tutorial_telemetry_append_only()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_tutorial_telemetry_append_only ON public.tutorial_telemetry_event")
    op.execute("DROP FUNCTION IF EXISTS app_security.trg_fn_tutorial_telemetry_append_only()")
    op.execute("DROP TRIGGER IF EXISTS trg_organization_foundation_monotonic ON public.organization")
    op.execute("DROP FUNCTION IF EXISTS app_security.trg_fn_organization_foundation_monotonic()")
    op.execute(f"DROP FUNCTION IF EXISTS app_security.bootstrap_organization_admin({BOOTSTRAP_SIGNATURE})")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app_security.bootstrap_founder(
            requested_clerk_user_id text, requested_clerk_org_id text,
            requested_organization_name text, requested_email text,
            requested_profile_name text, requested_membership_id text
        )
        RETURNS TABLE (account_id integer, organization_id integer, membership_id integer)
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
        DECLARE v_org integer; v_account integer; v_member integer;
        v_email text := lower(coalesce(nullif(trim(requested_email), ''), requested_clerk_user_id || '@clerk.local'));
        BEGIN
            PERFORM pg_advisory_xact_lock(hashtext(requested_clerk_org_id));
            SELECT id INTO v_org FROM public.organization WHERE clerk_org_id = requested_clerk_org_id;
            IF v_org IS NULL THEN
                INSERT INTO public.organization(name, clerk_org_id, plan_status)
                VALUES (requested_organization_name, requested_clerk_org_id, 'active') RETURNING id INTO v_org;
            ELSIF (SELECT plan_status FROM public.organization WHERE id = v_org) <> 'active' THEN RETURN; END IF;
            IF EXISTS (SELECT 1 FROM public.organization_membership WHERE organization_id = v_org) THEN
                RETURN QUERY SELECT u.id, v_org, m.id FROM public."user" u JOIN public.organization_membership m ON m.account_id = u.id
                WHERE m.organization_id = v_org AND u.clerk_user_id = requested_clerk_user_id
                  AND m.clerk_membership_id = requested_membership_id AND m.lifecycle_status = 'active'
                  AND m.access_status = 'active' AND m.can_admin;
                RETURN;
            END IF;
            SELECT id INTO v_account FROM public."user" WHERE clerk_user_id = requested_clerk_user_id;
            IF v_account IS NULL THEN SELECT id INTO v_account FROM public."user" WHERE lower(email) = v_email AND clerk_user_id IS NULL; END IF;
            IF v_account IS NULL AND EXISTS (SELECT 1 FROM public."user" WHERE lower(email) = v_email) THEN RETURN; END IF;
            IF v_account IS NULL THEN
                INSERT INTO public."user"(name, email, clerk_user_id, clerk_profile_name, last_clerk_sync_at, created_at, updated_at)
                VALUES (requested_profile_name, v_email, requested_clerk_user_id, requested_profile_name, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                RETURNING id INTO v_account;
            END IF;
            INSERT INTO public.organization_membership(
                organization_id, account_id, organization_display_name, lifecycle_status, access_status,
                can_admin, can_teach, clerk_membership_id, created_by_membership_id, updated_by_membership_id,
                lock_version, created_at, updated_at
            ) VALUES (v_org, v_account, requested_organization_name, 'active', 'active', true, false,
                      requested_membership_id, v_account, v_account, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING id INTO v_member;
            RETURN QUERY SELECT v_account, v_org, v_member;
        END;
        $$;
        """
    )
    op.execute(f"ALTER FUNCTION app_security.bootstrap_founder({BOOTSTRAP_SIGNATURE}) OWNER TO cronos_auth_definer")

    op.drop_index("ix_tutorial_telemetry_version_event", table_name="tutorial_telemetry_event", schema="public")
    op.drop_index("ix_tutorial_telemetry_run", table_name="tutorial_telemetry_event", schema="public")
    op.drop_index("ix_tutorial_telemetry_event_organization_id", table_name="tutorial_telemetry_event", schema="public")
    op.drop_table("tutorial_telemetry_event", schema="public")
    op.drop_table("organization_foundation_draft", schema="public")
    op.drop_constraint("chk_organization_first_real_schedule_requires_completed", "organization", schema="public", type_="check")
    op.drop_constraint("chk_organization_foundation_completed_at_required", "organization", schema="public", type_="check")
    op.drop_column("organization", "first_real_schedule_approved_at", schema="public")
    op.drop_column("organization", "foundation_completed_at", schema="public")
    op.drop_column("organization", "foundation_status", schema="public")
    op.execute("DROP TYPE IF EXISTS organizationfoundationstatus")
