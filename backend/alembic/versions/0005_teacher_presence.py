"""Teacher presence rule columns.

Adds ``lunch_required``, ``minimum_presence_hours`` and
``maximum_presence_gap_hours`` to ``teacher``, with the range checks and the
paired-null check that keep the minimum and the maximum gap together.

Revision ID: 0005_teacher_presence
Revises: 0004_joint_lesson_groups
"""

import sqlalchemy as sa

from alembic import op

revision = "0005_teacher_presence"
down_revision = "0004_joint_lesson_groups"
branch_labels = None
depends_on = None

TABLE = "teacher"
COLUMNS = ("lunch_required", "minimum_presence_hours", "maximum_presence_gap_hours")


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column("lunch_required", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(TABLE, sa.Column("minimum_presence_hours", sa.SmallInteger(), nullable=True))
    op.add_column(TABLE, sa.Column("maximum_presence_gap_hours", sa.SmallInteger(), nullable=True))
    op.create_check_constraint(
        "ck_teacher_minimum_presence_hours_range",
        TABLE,
        "minimum_presence_hours BETWEEN 1 AND 12",
    )
    op.create_check_constraint(
        "ck_teacher_maximum_presence_gap_hours_range",
        TABLE,
        "maximum_presence_gap_hours BETWEEN 0 AND 12",
    )
    op.create_check_constraint(
        "ck_teacher_presence_pair",
        TABLE,
        "(minimum_presence_hours IS NULL) = (maximum_presence_gap_hours IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_teacher_presence_pair", TABLE, type_="check")
    op.drop_constraint("ck_teacher_maximum_presence_gap_hours_range", TABLE, type_="check")
    op.drop_constraint("ck_teacher_minimum_presence_hours_range", TABLE, type_="check")
    for column in reversed(COLUMNS):
        op.drop_column(TABLE, column)
