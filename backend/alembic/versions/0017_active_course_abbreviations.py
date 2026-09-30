"""Allow archived course abbreviations to be reused without changing history."""

import sqlalchemy as sa

from alembic import op

revision = "0017_active_course_abbreviations"
down_revision = "0016_resource_archive_flags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_course_active_org_abbreviation",
        "course",
        ["organization_id", "abbreviation"],
        unique=True,
        schema="public",
        postgresql_where=sa.text("is_archived IS false"),
    )
    op.drop_constraint("uq_course_org_abbreviation", "course", type_="unique", schema="public")


def downgrade() -> None:
    # Refuse rollback if reused abbreviations would violate the old constraint.
    op.create_unique_constraint(
        "uq_course_org_abbreviation", "course", ["organization_id", "abbreviation"], schema="public"
    )
    op.drop_index("uq_course_active_org_abbreviation", table_name="course", schema="public")
