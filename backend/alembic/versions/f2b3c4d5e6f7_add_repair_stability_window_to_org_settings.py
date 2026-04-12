"""add repair_stability_window_days to organization_settings

Revision ID: f2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-04-11
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'f2b3c4d5e6f7'
down_revision: str | None = 'f1a2b3c4d5e6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'organization_settings',
        sa.Column('repair_stability_window_days', sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('organization_settings', 'repair_stability_window_days')
