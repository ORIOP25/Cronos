"""Add archive flags to rooms, subjects and courses.

Removing a resource from current management must not destroy history. The
frontal tables therefore gain an additive `is_archived` flag, initialised to
`false` for existing rows so current behaviour is unchanged until a removal
decides between a physical delete and an archive.
"""

import sqlalchemy as sa

from alembic import op

revision = "0016_resource_archive_flags"
down_revision = "0015_scheduler_v1_grid_change"
branch_labels = None
depends_on = None

_TABLES = ("room", "subject", "course")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column(
                "is_archived",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            schema="public",
        )
        op.alter_column(table, "is_archived", server_default=None, schema="public")


def downgrade() -> None:
    for table in _TABLES:
        op.drop_column(table, "is_archived", schema="public")
