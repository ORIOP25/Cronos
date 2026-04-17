"""Add missing class/module/progress columns for course-centric schema.

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
Create Date: 2026-04-17
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "c7d8e9f0a1b2"
down_revision: str | None = "b6c7d8e9f0a1"
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

    # class: start_year, end_year, grade_level
    if not _column_exists(inspector, "class", "start_year"):
        op.add_column("class", sa.Column("start_year", sa.Integer(), nullable=True))
    if not _column_exists(inspector, "class", "end_year"):
        op.add_column("class", sa.Column("end_year", sa.Integer(), nullable=True))
    if not _column_exists(inspector, "class", "grade_level"):
        op.add_column("class", sa.Column("grade_level", sa.Integer(), nullable=True))

    inspector = sa.inspect(bind)
    if _column_exists(inspector, "class", "start_year") and _column_exists(inspector, "class", "end_year") and _column_exists(inspector, "class", "grade_level"):
        op.execute(
            sa.text(
                "UPDATE \"class\" "
                "SET start_year = COALESCE(start_year, EXTRACT(YEAR FROM CURRENT_DATE)::int), "
                "end_year = COALESCE(end_year, EXTRACT(YEAR FROM CURRENT_DATE)::int + 3), "
                "grade_level = COALESCE(grade_level, 10)"
            )
        )
        op.alter_column("class", "start_year", existing_type=sa.Integer(), nullable=False)
        op.alter_column("class", "end_year", existing_type=sa.Integer(), nullable=False)
        op.alter_column("class", "grade_level", existing_type=sa.Integer(), nullable=False)

    # module: order + unique(subject_id, order)
    inspector = sa.inspect(bind)
    if not _column_exists(inspector, "module", "order"):
        op.add_column("module", sa.Column("order", sa.Integer(), nullable=True))

    inspector = sa.inspect(bind)
    if _column_exists(inspector, "module", "order"):
        op.execute(
            sa.text(
                "WITH ranked AS ("
                "  SELECT id, ROW_NUMBER() OVER (PARTITION BY subject_id ORDER BY id) AS rn"
                "  FROM module"
                ") "
                "UPDATE module AS m "
                "SET \"order\" = ranked.rn "
                "FROM ranked "
                "WHERE m.id = ranked.id AND m.\"order\" IS NULL"
            )
        )
        op.alter_column("module", "order", existing_type=sa.Integer(), nullable=False)

        inspector = sa.inspect(bind)
        if not _has_unique_for_columns(inspector, "module", ["subject_id", "order"]):
            op.create_unique_constraint(
                "uq_module_order_per_subject",
                "module",
                ["subject_id", "order"],
            )

    # class_progress: updated_at
    inspector = sa.inspect(bind)
    if not _column_exists(inspector, "class_progress", "updated_at"):
        op.add_column(
            "class_progress",
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
        )
        op.alter_column("class_progress", "updated_at", server_default=None)
    else:
        op.execute(
            sa.text(
                "UPDATE class_progress "
                "SET updated_at = COALESCE(updated_at, CURRENT_TIMESTAMP)"
            )
        )
        op.alter_column(
            "class_progress",
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_unique_constraint_name(inspector, "module", "uq_module_order_per_subject"):
        op.drop_constraint("uq_module_order_per_subject", "module", type_="unique")

    inspector = sa.inspect(bind)
    if _column_exists(inspector, "module", "order"):
        op.drop_column("module", "order")

    inspector = sa.inspect(bind)
    if _column_exists(inspector, "class_progress", "updated_at"):
        op.drop_column("class_progress", "updated_at")

    inspector = sa.inspect(bind)
    if _column_exists(inspector, "class", "grade_level"):
        op.drop_column("class", "grade_level")
    if _column_exists(inspector, "class", "end_year"):
        op.drop_column("class", "end_year")
    if _column_exists(inspector, "class", "start_year"):
        op.drop_column("class", "start_year")
