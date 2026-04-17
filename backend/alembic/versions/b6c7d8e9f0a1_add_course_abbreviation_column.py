"""Add course abbreviation column compatibility fix.

Revision ID: b6c7d8e9f0a1
Revises: a4d5e6f7a8b9
Create Date: 2026-04-17
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "b6c7d8e9f0a1"
down_revision: str | None = "a4d5e6f7a8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _column_exists(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return any(col.get("name") == column_name for col in inspector.get_columns(table_name))


def _has_unique_for_columns(inspector: sa.Inspector, table_name: str, column_names: list[str]) -> bool:
    expected = set(column_names)
    for constraint in inspector.get_unique_constraints(table_name):
        if set(constraint.get("column_names") or []) == expected:
            return True
    return False


def _has_unique_constraint_name(inspector: sa.Inspector, table_name: str, constraint_name: str) -> bool:
    for constraint in inspector.get_unique_constraints(table_name):
        if constraint.get("name") == constraint_name:
            return True
    return False


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _column_exists(inspector, "course", "abbreviation"):
        op.add_column("course", sa.Column("abbreviation", sa.String(length=10), nullable=True))
        inspector = sa.inspect(bind)

    op.execute(
        sa.text(
            "UPDATE course "
            "SET abbreviation = CONCAT('C', LPAD(id::text, 9, '0')) "
            "WHERE abbreviation IS NULL OR abbreviation = ''"
        )
    )

    op.alter_column(
        "course",
        "abbreviation",
        existing_type=sa.String(length=10),
        nullable=False,
    )

    inspector = sa.inspect(bind)
    if not _has_unique_for_columns(inspector, "course", ["abbreviation"]):
        op.create_unique_constraint("uq_course_abbreviation", "course", ["abbreviation"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _column_exists(inspector, "course", "abbreviation"):
        return

    if _has_unique_constraint_name(inspector, "course", "uq_course_abbreviation"):
        op.drop_constraint("uq_course_abbreviation", "course", type_="unique")
        op.drop_column("course", "abbreviation")
