"""Persist the organization preference for automatic national holidays."""

import sqlalchemy as sa

from alembic import op

revision = "0005_automatic_holidays"
down_revision = "0004_foundation_telemetry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organization_settings",
        sa.Column(
            "automatic_holidays_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        schema="public",
    )


def downgrade() -> None:
    op.drop_column("organization_settings", "automatic_holidays_enabled", schema="public")
