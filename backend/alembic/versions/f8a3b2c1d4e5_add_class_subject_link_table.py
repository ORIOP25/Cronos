"""Add class_subject_link table for course-centric teacher management

Revision ID: f8a3b2c1d4e5
Revises: 1c29964dc01c
Create Date: 2026-02-16 21:30:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f8a3b2c1d4e5'
down_revision: str | None = '1c29964dc01c'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('class_subject_link',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('class_id', sa.Integer(), nullable=False),
        sa.Column('subject_id', sa.Integer(), nullable=False),
        sa.Column('grade_level', sa.Integer(), nullable=False),
        sa.Column('teacher_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['class_id'], ['class.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['subject_id'], ['subject.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['teacher_id'], ['teacher.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('class_id', 'subject_id', 'grade_level', name='uq_class_subject_grade')
    )
    op.create_index(op.f('ix_class_subject_link_class_id'), 'class_subject_link', ['class_id'], unique=False)
    op.create_index(op.f('ix_class_subject_link_subject_id'), 'class_subject_link', ['subject_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_class_subject_link_subject_id'), table_name='class_subject_link')
    op.drop_index(op.f('ix_class_subject_link_class_id'), table_name='class_subject_link')
    op.drop_table('class_subject_link')
