"""Add opaque support references to terminal scheduler failures."""

import sqlalchemy as sa

from alembic import op

revision = "0010_scheduler_failure_reference"
down_revision = "0009_integrated_legal_acceptance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "schedule_generation_job",
        sa.Column("failure_reference", sa.String(length=32), nullable=True),
        schema="public",
    )


def downgrade() -> None:
    op.drop_column("schedule_generation_job", "failure_reference", schema="public")
