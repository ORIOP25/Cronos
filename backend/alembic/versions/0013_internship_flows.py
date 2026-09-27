"""Add internship flows and the calendar-event class association."""

import sqlalchemy as sa

from alembic import op

revision = "0013_internship_flows"
down_revision = "0012_grid_change_strategy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE calendareventtype ADD VALUE IF NOT EXISTS 'internship_flow'")
    op.add_column(
        "school_calendar_event",
        sa.Column("school_year_start_year", sa.Integer(), nullable=True),
        schema="public",
    )
    op.create_index(
        "ix_school_calendar_event_school_year_start_year",
        "school_calendar_event",
        ["school_year_start_year"],
        schema="public",
    )

    op.create_table(
        "school_calendar_event_class",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("calendar_event_id", sa.Integer(), nullable=False),
        sa.Column("class_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["public.organization.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "calendar_event_id"],
            ["public.school_calendar_event.organization_id", "public.school_calendar_event.id"],
            name="fk_school_calendar_event_class_event_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "class_id"],
            ["public.class.organization_id", "public.class.id"],
            name="fk_school_calendar_event_class_class_scope",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "calendar_event_id",
            "class_id",
            name="uq_school_calendar_event_class",
        ),
        schema="public",
    )
    op.create_index(
        "ix_school_calendar_event_class_organization_id",
        "school_calendar_event_class",
        ["organization_id"],
        schema="public",
    )
    op.create_index(
        "ix_school_calendar_event_class_calendar_event_id",
        "school_calendar_event_class",
        ["calendar_event_id"],
        schema="public",
    )
    op.create_index(
        "ix_school_calendar_event_class_class_id",
        "school_calendar_event_class",
        ["class_id"],
        schema="public",
    )
    op.execute("ALTER TABLE public.school_calendar_event_class ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.school_calendar_event_class FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY school_calendar_event_class_tenant_isolation
        ON public.school_calendar_event_class FOR ALL
        USING (organization_id = app_security.current_organization_id())
        WITH CHECK (organization_id = app_security.current_organization_id())
        """
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON public.school_calendar_event_class TO cronos_app"
    )
    op.execute(
        "GRANT USAGE, SELECT ON SEQUENCE public.school_calendar_event_class_id_seq TO cronos_app"
    )


def downgrade() -> None:
    op.drop_index(
        "ix_school_calendar_event_class_class_id",
        table_name="school_calendar_event_class",
        schema="public",
    )
    op.drop_index(
        "ix_school_calendar_event_class_calendar_event_id",
        table_name="school_calendar_event_class",
        schema="public",
    )
    op.drop_index(
        "ix_school_calendar_event_class_organization_id",
        table_name="school_calendar_event_class",
        schema="public",
    )
    op.drop_table("school_calendar_event_class", schema="public")
    op.drop_index(
        "ix_school_calendar_event_school_year_start_year",
        table_name="school_calendar_event",
        schema="public",
    )
    op.drop_column("school_calendar_event", "school_year_start_year", schema="public")
    # PostgreSQL cannot remove enum values without rewriting dependent data.
