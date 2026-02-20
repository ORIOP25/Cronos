"""remove num_per_week and is_double from class_subject_link and lesson

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2025-01-20

Audit: O1 + O3 — Remoção de colunas obsoletas.
Estas colunas foram substituídas pelo cálculo dinâmico do Solver
baseado no progresso modular (Ensino Profissional).
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # O1: Remover de class_subject_link
    op.drop_column('class_subject_link', 'num_per_week')
    op.drop_column('class_subject_link', 'is_double')

    # O3: Remover de lesson
    op.drop_column('lesson', 'num_per_week')
    op.drop_column('lesson', 'is_double')


def downgrade() -> None:
    # Restaurar em lesson
    op.add_column('lesson', sa.Column('is_double', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('lesson', sa.Column('num_per_week', sa.Integer(), server_default='1', nullable=False))

    # Restaurar em class_subject_link
    op.add_column('class_subject_link', sa.Column('is_double', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('class_subject_link', sa.Column('num_per_week', sa.Integer(), server_default='1', nullable=False))
