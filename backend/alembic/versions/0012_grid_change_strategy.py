"""Add the GRID_CHANGE strategy and trigger to the scheduler enums."""

from alembic import op

revision = "0012_grid_change_strategy"
down_revision = "0011_grid_versions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE schedulegenerationstrategy ADD VALUE IF NOT EXISTS 'GRID_CHANGE'")
    op.execute("ALTER TYPE schedulegenerationtrigger ADD VALUE IF NOT EXISTS 'GRID_CHANGE'")


def downgrade() -> None:
    # PostgreSQL cannot remove enum values without rewriting dependent data.
    # GRID_CHANGE rows are terminal audit records and stay valid after downgrade.
    pass
