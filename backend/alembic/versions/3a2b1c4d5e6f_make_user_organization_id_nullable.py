"""make_user_organization_id_nullable

Revision ID: 3a2b1c4d5e6f
Revises: 036e15372ca1
Create Date: 2026-05-12 13:06:16.161859

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '3a2b1c4d5e6f'
down_revision: Union[str, None] = '036e15372ca1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('user', 'organization_id',
                    existing_type=sa.Integer(),
                    nullable=True)


def downgrade() -> None:
    op.alter_column('user', 'organization_id',
                    existing_type=sa.Integer(),
                    nullable=False)
