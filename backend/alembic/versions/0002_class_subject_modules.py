"""Per-class module selection and retired-module flag.

Adds ``class_subject_module``: one row per module selected on a
class/subject link. Existing links keep every module of their subject, so the
projection behaviour is unchanged until an administrator deselects a module.
Adds ``curricular_requirement.planned`` to mark a retired module that keeps
executed history.

Revision ID: 0002_class_subject_modules
Revises: 0001_scheduler_v1_baseline
"""

import sqlalchemy as sa

from alembic import op

revision = "0002_class_subject_modules"
down_revision = "0001_scheduler_v1_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "class_subject_module",
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("class_subject_link_id", sa.Integer(), nullable=False),
        sa.Column("module_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organization.id"],
            name="class_subject_module_organization_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "class_subject_link_id"],
            ["class_subject_link.organization_id", "class_subject_link.id"],
            name="fk_class_subject_module_link_org",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "module_id"],
            ["module.organization_id", "module.id"],
            name="fk_class_subject_module_module_org",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "organization_id",
            "class_subject_link_id",
            "module_id",
            name="class_subject_module_pkey",
        ),
    )
    op.create_index(
        "ix_class_subject_module_organization_id",
        "class_subject_module",
        ["organization_id"],
    )
    op.create_index(
        "ix_class_subject_module_organization_id_module_id",
        "class_subject_module",
        ["organization_id", "module_id"],
    )
    op.execute("ALTER TABLE public.class_subject_module ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.class_subject_module FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON public.class_subject_module TO cronos_app "
        "USING ((organization_id = app_security.current_organization_id())) "
        "WITH CHECK ((organization_id = app_security.current_organization_id()))"
    )
    op.execute("GRANT SELECT,INSERT,DELETE ON TABLE public.class_subject_module TO cronos_app")
    # D04: every existing link keeps all its subject modules. Runs as
    # cronos_migrator, which bypasses the forced row-level security.
    op.execute(
        """
        INSERT INTO public.class_subject_module
            (organization_id, class_subject_link_id, module_id)
        SELECT l.organization_id, l.id, m.id
        FROM public.class_subject_link l
        JOIN public.module m
          ON m.organization_id = l.organization_id
         AND m.subject_id = l.subject_id
        """
    )
    op.add_column(
        "curricular_requirement",
        sa.Column("planned", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )


def downgrade() -> None:
    op.drop_column("curricular_requirement", "planned")
    op.drop_table("class_subject_module")
