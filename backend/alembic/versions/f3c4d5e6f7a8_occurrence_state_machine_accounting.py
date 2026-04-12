"""Occurrence state machine accounting and audit fields

Revision ID: f3c4d5e6f7a8
Revises: f2b3c4d5e6f7
Create Date: 2026-04-11
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "f3c4d5e6f7a8"
down_revision: str | None = "f2b3c4d5e6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "class_progress",
        "hours_completed",
        existing_type=sa.Integer(),
        type_=sa.Float(),
        existing_nullable=False,
        postgresql_using="hours_completed::double precision",
    )

    op.add_column(
        "class_progress",
        sa.Column("hours_debt", sa.Float(), nullable=False, server_default="0"),
    )
    op.alter_column("class_progress", "hours_debt", server_default=None)

    op.add_column(
        "lesson_occurrence",
        sa.Column("planned_hours", sa.Float(), nullable=False, server_default="0"),
    )
    op.alter_column("lesson_occurrence", "planned_hours", server_default=None)

    op.add_column(
        "lesson_occurrence",
        sa.Column(
            "planned_teacher_id",
            sa.Integer(),
            sa.ForeignKey("teacher.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "lesson_occurrence",
        sa.Column(
            "executed_teacher_id",
            sa.Integer(),
            sa.ForeignKey("teacher.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "lesson_occurrence",
        sa.Column(
            "planned_module_id",
            sa.Integer(),
            sa.ForeignKey("module.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "lesson_occurrence",
        sa.Column(
            "executed_module_id",
            sa.Integer(),
            sa.ForeignKey("module.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "lesson_occurrence",
        sa.Column(
            "decided_by_user_id",
            sa.Integer(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "lesson_occurrence",
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("lesson_occurrence", "decided_at")
    op.drop_column("lesson_occurrence", "decided_by_user_id")
    op.drop_column("lesson_occurrence", "executed_module_id")
    op.drop_column("lesson_occurrence", "planned_module_id")
    op.drop_column("lesson_occurrence", "executed_teacher_id")
    op.drop_column("lesson_occurrence", "planned_teacher_id")
    op.drop_column("lesson_occurrence", "planned_hours")

    op.drop_column("class_progress", "hours_debt")
    op.alter_column(
        "class_progress",
        "hours_completed",
        existing_type=sa.Float(),
        type_=sa.Integer(),
        existing_nullable=False,
        postgresql_using="round(hours_completed)::integer",
    )
