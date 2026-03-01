"""Add num_per_week and is_double to class_subject_link

Revision ID: a1b2c3d4e5f6
Revises: f8a3b2c1d4e5
Create Date: 2026-02-17 10:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: str | None = 'f8a3b2c1d4e5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('class_subject_link', sa.Column('num_per_week', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('class_subject_link', sa.Column('is_double', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    op.drop_column('class_subject_link', 'is_double')
    op.drop_column('class_subject_link', 'num_per_week')
