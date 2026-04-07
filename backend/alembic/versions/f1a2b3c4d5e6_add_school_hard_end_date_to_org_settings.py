"""add_school_hard_end_date_to_org_settings

Revision ID: f1a2b3c4d5e6
Revises: e3f4a5b6c7d8
Create Date: 2026-03-27
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'f1a2b3c4d5e6'
down_revision: str | None = 'e3f4a5b6c7d8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('organization_settings', sa.Column('school_hard_end_date', sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column('organization_settings', 'school_hard_end_date')
