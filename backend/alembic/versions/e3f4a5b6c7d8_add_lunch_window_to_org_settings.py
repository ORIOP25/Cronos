"""add_lunch_window_to_org_settings

Revision ID: e3f4a5b6c7d8
Revises: a2b3c4d5e6f7
Create Date: 2026-03-22
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'e3f4a5b6c7d8'
down_revision: str | None = 'a2b3c4d5e6f7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('organization_settings', sa.Column('lunch_window_start', sa.Time(), nullable=True))
    op.add_column('organization_settings', sa.Column('lunch_window_end', sa.Time(), nullable=True))
    op.add_column('organization_settings', sa.Column('lunch_min_duration_minutes', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('organization_settings', 'lunch_min_duration_minutes')
    op.drop_column('organization_settings', 'lunch_window_end')
    op.drop_column('organization_settings', 'lunch_window_start')
