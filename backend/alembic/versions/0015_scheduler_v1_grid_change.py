"""Pin the proposed grid version on scheduler v1 jobs.

A grid-change proposal generates a schedule under the pending grid version and
publishes both together. The job records the pinned version so the snapshot,
the claim revalidation and the approval transaction all resolve the same grid.
"""

import sqlalchemy as sa

from alembic import op

revision = "0015_scheduler_v1_grid_change"
down_revision = "0014_foundation_internship_step"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scheduler_job_v1",
        sa.Column("grid_version_id", sa.Integer(), nullable=True),
        schema="public",
    )
    op.create_index(
        "ix_scheduler_job_v1_grid_version_id",
        "scheduler_job_v1",
        ["grid_version_id"],
        schema="public",
    )
    op.create_foreign_key(
        "fk_scheduler_job_v1_grid_version_tenant_scoped",
        "scheduler_job_v1",
        "grid_version",
        ["organization_id", "grid_version_id"],
        ["organization_id", "id"],
        source_schema="public",
        referent_schema="public",
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_scheduler_job_v1_grid_version_tenant_scoped",
        "scheduler_job_v1",
        schema="public",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_scheduler_job_v1_grid_version_id",
        table_name="scheduler_job_v1",
        schema="public",
    )
    op.drop_column("scheduler_job_v1", "grid_version_id", schema="public")
