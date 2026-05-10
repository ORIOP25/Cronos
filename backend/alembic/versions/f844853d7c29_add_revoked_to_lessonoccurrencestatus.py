"""add REVOKED to lessonoccurrencestatus

Revision ID: f844853d7c29
Revises: d6fc61979dd3
Create Date: 2026-05-05 18:53:07.748366

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f844853d7c29'
down_revision: Union[str, None] = 'd6fc61979dd3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE lessonoccurrencestatus ADD VALUE 'REVOKED'")


def downgrade() -> None:
    # PostgreSQL does not support removing values from an enum type.
    # A full enum rebuild would be required, which is not safe for production.
    pass