"""Remove unused automatic occurrence confirmation settings."""

import sqlalchemy as sa

from alembic import op

revision = "0003_remove_auto_confirm"
down_revision = "0002_security_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("organization_settings", "auto_confirm_cutoff_time")
    op.drop_column("organization_settings", "auto_confirm_enabled")


def downgrade() -> None:
    op.add_column(
        "organization_settings",
        sa.Column("auto_confirm_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("organization_settings", "auto_confirm_enabled", server_default=None)
    op.add_column(
        "organization_settings",
        sa.Column("auto_confirm_cutoff_time", sa.Time(), nullable=True),
    )
