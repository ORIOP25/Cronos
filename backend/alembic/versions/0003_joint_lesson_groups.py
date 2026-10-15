"""Joint lesson groups and the teaching-unit key on published lessons.

Adds ``joint_lesson_group`` (subject + members + joint modules), the two link
tables, and ``scheduler_lesson_v1.teaching_unit_key``. Every existing lesson is
backfilled with ``A:{assignment_id}`` and the unique identity of a lesson gains
``assignment_id`` so sibling lessons of a joint lesson can share a ``stable_key``.

Revision ID: 0003_joint_lesson_groups
Revises: 0002_class_subject_modules
"""

import sqlalchemy as sa

from alembic import op

revision = "0003_joint_lesson_groups"
down_revision = "0002_class_subject_modules"
branch_labels = None
depends_on = None

GROUP_TABLE = "joint_lesson_group"
MEMBER_TABLE = "joint_lesson_group_member"
MODULE_TABLE = "joint_lesson_group_module"
LESSON_TABLE = "scheduler_lesson_v1"


def _create_group_table() -> None:
    op.create_table(
        GROUP_TABLE,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organization.id"],
            name="joint_lesson_group_organization_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "subject_id"],
            ["subject.organization_id", "subject.id"],
            name="fk_joint_lesson_group_subject_org",
        ),
        sa.PrimaryKeyConstraint("id", name="joint_lesson_group_pkey"),
        sa.UniqueConstraint("organization_id", "id", name="uq_joint_lesson_group_org_id"),
    )
    op.create_index("ix_joint_lesson_group_organization_id", GROUP_TABLE, ["organization_id"])


def _create_member_table() -> None:
    op.create_table(
        MEMBER_TABLE,
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("class_subject_link_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organization.id"],
            name="joint_lesson_group_member_organization_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "group_id"],
            [f"{GROUP_TABLE}.organization_id", f"{GROUP_TABLE}.id"],
            name="fk_joint_lesson_group_member_group_org",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "class_subject_link_id"],
            ["class_subject_link.organization_id", "class_subject_link.id"],
            name="fk_joint_lesson_group_member_link_org",
        ),
        sa.PrimaryKeyConstraint(
            "organization_id", "class_subject_link_id", name="joint_lesson_group_member_pkey"
        ),
    )
    op.create_index(
        "ix_joint_lesson_group_member_organization_id_group_id",
        MEMBER_TABLE,
        ["organization_id", "group_id"],
    )


def _create_module_table() -> None:
    op.create_table(
        MODULE_TABLE,
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("module_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organization.id"],
            name="joint_lesson_group_module_organization_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "group_id"],
            [f"{GROUP_TABLE}.organization_id", f"{GROUP_TABLE}.id"],
            name="fk_joint_lesson_group_module_group_org",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "module_id"],
            ["module.organization_id", "module.id"],
            name="fk_joint_lesson_group_module_module_org",
        ),
        sa.PrimaryKeyConstraint(
            "organization_id",
            "group_id",
            "module_id",
            name="joint_lesson_group_module_pkey",
        ),
    )


def _harden_table(table: str) -> None:
    op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON public.{table} TO cronos_app "
        "USING ((organization_id = app_security.current_organization_id())) "
        "WITH CHECK ((organization_id = app_security.current_organization_id()))"
    )
    op.execute(f"GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.{table} TO cronos_app")


def upgrade() -> None:
    _create_group_table()
    _create_member_table()
    _create_module_table()
    for table in (GROUP_TABLE, MEMBER_TABLE, MODULE_TABLE):
        _harden_table(table)
    op.execute("GRANT SELECT,USAGE ON SEQUENCE public.joint_lesson_group_id_seq TO cronos_app")

    op.add_column(
        LESSON_TABLE,
        sa.Column("teaching_unit_key", sa.String(length=80), nullable=True),
    )
    op.execute(f"UPDATE public.{LESSON_TABLE} SET teaching_unit_key = 'A:' || assignment_id::text")
    op.alter_column(LESSON_TABLE, "teaching_unit_key", nullable=False)

    op.drop_constraint("uq_scheduler_lesson_v1_stable_key", LESSON_TABLE, type_="unique")
    op.create_unique_constraint(
        "uq_scheduler_lesson_v1_stable_key",
        LESSON_TABLE,
        ["version_id", "stable_key", "assignment_id"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    # The old identity is ``(version_id, stable_key)``. Downgrading is safe while
    # no version holds two sibling lessons with the same key; a single ``S``/``J``
    # or ``D`` unit is fine because dropping the column loses no sibling row.
    sibling = connection.scalar(
        sa.text(
            f"SELECT EXISTS(SELECT 1 FROM public.{LESSON_TABLE} "
            "GROUP BY version_id, stable_key HAVING count(*) > 1)"
        )
    )
    if sibling:
        raise RuntimeError("downgrade refused: published sibling lessons share a stable key")
    op.drop_constraint("uq_scheduler_lesson_v1_stable_key", LESSON_TABLE, type_="unique")
    op.create_unique_constraint(
        "uq_scheduler_lesson_v1_stable_key",
        LESSON_TABLE,
        ["version_id", "stable_key"],
    )
    op.drop_column(LESSON_TABLE, "teaching_unit_key")
    op.drop_table(MODULE_TABLE)
    op.drop_table(MEMBER_TABLE)
    op.drop_table(GROUP_TABLE)
