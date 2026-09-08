"""Remove the tutorial telemetry table after moving progress to local storage."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0008_remove_tutorial_telemetry"
down_revision = "0007_legal_acceptance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_tutorial_telemetry_append_only "
        "ON public.tutorial_telemetry_event"
    )
    op.execute("DROP FUNCTION IF EXISTS app_security.trg_fn_tutorial_telemetry_append_only()")
    op.drop_table("tutorial_telemetry_event", schema="public")


def downgrade() -> None:
    # Restore the immediately previous schema when an operator explicitly rolls
    # back this migration. The current application still does not call the table.
    op.create_table(
        "tutorial_telemetry_event",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("tutorial_run_id", postgresql.UUID(), nullable=False),
        sa.Column("client_event_id", postgresql.UUID(), nullable=False),
        sa.Column("tutorial_version", sa.Integer(), nullable=False),
        sa.Column("event_name", sa.String(length=40), nullable=False),
        sa.Column("chapter", sa.SmallInteger(), nullable=True),
        sa.Column("step_id", sa.String(length=80), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "event_name IN ('tutorial_opened', 'chapter_started', 'tutorial_exited', 'tutorial_completed', 'tutorial_repeated')",
            name="chk_tutorial_telemetry_event_name",
        ),
        sa.CheckConstraint(
            "chapter IS NULL OR chapter IN (1, 2)",
            name="chk_tutorial_telemetry_chapter",
        ),
        sa.CheckConstraint(
            "tutorial_version = 3",
            name="chk_tutorial_telemetry_version",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["public.organization.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "client_event_id",
            name="uq_tutorial_telemetry_client_event",
        ),
        schema="public",
    )
    op.create_index(
        "ix_tutorial_telemetry_event_organization_id",
        "tutorial_telemetry_event",
        ["organization_id"],
        schema="public",
    )
    op.create_index(
        "ix_tutorial_telemetry_run",
        "tutorial_telemetry_event",
        ["organization_id", "tutorial_run_id", "created_at"],
        schema="public",
    )
    op.create_index(
        "ix_tutorial_telemetry_version_event",
        "tutorial_telemetry_event",
        ["organization_id", "tutorial_version", "event_name"],
        schema="public",
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
    op.execute(
        "GRANT SELECT, INSERT ON public.tutorial_telemetry_event TO cronos_app"
    )
    op.execute(
        "GRANT USAGE, SELECT ON SEQUENCE public.tutorial_telemetry_event_id_seq TO cronos_app"
    )
    op.execute("REVOKE UPDATE, DELETE ON public.tutorial_telemetry_event FROM cronos_app")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app_security.trg_fn_tutorial_telemetry_append_only()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'tutorial_telemetry_event is append-only; % is prohibited', TG_OP
                USING ERRCODE = '42501';
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
