"""Store optional organization schedule priorities."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0008_schedule_priorities"
down_revision = "0007_class_home_room"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organization_settings",
        sa.Column("schedule_priorities", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("organization_settings", "schedule_priorities")
