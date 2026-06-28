"""link lesson occurrences to active schedule blocks

Revision ID: d3a7e5b9c2f1
Revises: c2f6a8d4e1b9
Create Date: 2026-06-22
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d3a7e5b9c2f1"
down_revision: Union[str, None] = "c2f6a8d4e1b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cronos_auth_definer') THEN
                GRANT USAGE ON SCHEMA public, app_security TO cronos_auth_definer;
            END IF;
        END
        $$;
        """
    )
    op.create_unique_constraint(
        "uq_active_schedule_blocks_id_org",
        "active_schedule_blocks",
        ["id", "organization_id"],
    )
    op.add_column(
        "lesson_occurrence",
        sa.Column("active_schedule_block_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_lesson_occurrence_active_block_scope",
        "lesson_occurrence",
        "active_schedule_blocks",
        ["active_schedule_block_id", "organization_id"],
        ["id", "organization_id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_lesson_occurrence_active_block_date_revision",
        "lesson_occurrence",
        ["organization_id", "active_schedule_block_id", "date", "revision"],
    )
    op.create_index(
        "ix_lesson_occurrence_active_schedule_block_id",
        "lesson_occurrence",
        ["active_schedule_block_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_lesson_occurrence_active_schedule_block_id",
        table_name="lesson_occurrence",
    )
    op.drop_constraint(
        "uq_lesson_occurrence_active_block_date_revision",
        "lesson_occurrence",
        type_="unique",
    )
    op.drop_constraint(
        "fk_lesson_occurrence_active_block_scope",
        "lesson_occurrence",
        type_="foreignkey",
    )
    op.drop_column("lesson_occurrence", "active_schedule_block_id")
    op.drop_constraint(
        "uq_active_schedule_blocks_id_org",
        "active_schedule_blocks",
        type_="unique",
    )
