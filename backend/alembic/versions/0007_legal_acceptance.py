"""Add append-only organization legal acceptance evidence."""

import sqlalchemy as sa

from alembic import op

revision = "0007_legal_acceptance"
down_revision = "0006_non_mutating_ensure_user"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organization_legal_acceptance",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("accepted_by_membership_id_snapshot", sa.Integer(), nullable=False),
        sa.Column("controller_legal_name", sa.String(length=200), nullable=False),
        sa.Column("controller_registration_number", sa.String(length=50), nullable=False),
        sa.Column("controller_registered_address", sa.String(length=500), nullable=False),
        sa.Column("controller_contact_email", sa.String(length=254), nullable=False),
        sa.Column("representative_name", sa.String(length=150), nullable=False),
        sa.Column("representative_role", sa.String(length=100), nullable=False),
        sa.Column("authority_confirmed", sa.Boolean(), nullable=False),
        sa.Column("terms_version", sa.String(length=40), nullable=False),
        sa.Column("dpa_version", sa.String(length=40), nullable=False),
        sa.Column(
            "accepted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(trim(controller_legal_name)) BETWEEN 1 AND 200",
            name="chk_legal_acceptance_controller_name",
        ),
        sa.CheckConstraint(
            "char_length(trim(controller_registration_number)) BETWEEN 1 AND 50",
            name="chk_legal_acceptance_registration_number",
        ),
        sa.CheckConstraint(
            "char_length(trim(controller_registered_address)) BETWEEN 1 AND 500",
            name="chk_legal_acceptance_address",
        ),
        sa.CheckConstraint(
            "char_length(trim(controller_contact_email)) BETWEEN 3 AND 254",
            name="chk_legal_acceptance_contact_email",
        ),
        sa.CheckConstraint(
            "char_length(trim(representative_name)) BETWEEN 1 AND 150",
            name="chk_legal_acceptance_representative_name",
        ),
        sa.CheckConstraint(
            "char_length(trim(representative_role)) BETWEEN 1 AND 100",
            name="chk_legal_acceptance_representative_role",
        ),
        sa.CheckConstraint("authority_confirmed IS TRUE", name="chk_legal_acceptance_authority"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["public.organization.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "terms_version",
            "dpa_version",
            name="uq_organization_legal_acceptance_versions",
        ),
        schema="public",
    )
    op.create_index(
        "ix_organization_legal_acceptance_organization_id",
        "organization_legal_acceptance",
        ["organization_id"],
        schema="public",
    )
    op.execute("ALTER TABLE public.organization_legal_acceptance ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.organization_legal_acceptance FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY organization_legal_acceptance_select
        ON public.organization_legal_acceptance FOR SELECT
        USING (organization_id = app_security.current_organization_id())
        """
    )
    op.execute(
        """
        CREATE POLICY organization_legal_acceptance_insert
        ON public.organization_legal_acceptance FOR INSERT
        WITH CHECK (organization_id = app_security.current_organization_id())
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app_security.trg_fn_organization_legal_acceptance_append_only()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY INVOKER
        SET search_path = pg_catalog, public
        AS $$
        BEGIN
            RAISE EXCEPTION 'organization_legal_acceptance is append-only; % is prohibited', TG_OP
                USING ERRCODE = '42501';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_organization_legal_acceptance_append_only
        BEFORE UPDATE OR DELETE ON public.organization_legal_acceptance
        FOR EACH ROW EXECUTE FUNCTION app_security.trg_fn_organization_legal_acceptance_append_only()
        """
    )
    op.execute("GRANT SELECT, INSERT ON public.organization_legal_acceptance TO cronos_app")
    op.execute(
        "GRANT USAGE, SELECT ON SEQUENCE public.organization_legal_acceptance_id_seq TO cronos_app"
    )
    op.execute("REVOKE UPDATE, DELETE ON public.organization_legal_acceptance FROM cronos_app")


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_organization_legal_acceptance_append_only "
        "ON public.organization_legal_acceptance"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS app_security.trg_fn_organization_legal_acceptance_append_only()"
    )
    op.drop_index(
        "ix_organization_legal_acceptance_organization_id",
        table_name="organization_legal_acceptance",
        schema="public",
    )
    op.drop_table("organization_legal_acceptance", schema="public")
