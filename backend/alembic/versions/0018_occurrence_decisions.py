"""Persist v1 occurrence decisions and v1-origin operational blocks.

An occurrence decision must be explicit. Debt is no longer inferred from a
balance, so the v1 lesson log stores the decision, its instant, its author and
the revocation audit. Operational blocks gain a v1 origin: the substitute
lesson links to the v1 lesson log and to the substitute curricular assignment,
without a legacy occurrence or active block.

The downgrade refuses to run when decision or v1-origin data exists, because the
old schema cannot represent it without losing audit evidence.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0018_occurrence_decisions"
down_revision = "0017_active_course_abbreviations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE TYPE public.operationalblockorigin AS ENUM ('LEGACY', 'V1')")

    op.add_column(
        "scheduler_lesson_log_v1",
        sa.Column("decision", sa.String(length=20), nullable=True),
        schema="public",
    )
    op.add_column(
        "scheduler_lesson_log_v1",
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        schema="public",
    )
    op.add_column(
        "scheduler_lesson_log_v1",
        sa.Column("decided_by_membership_id", sa.Integer(), nullable=True),
        schema="public",
    )
    op.add_column(
        "scheduler_lesson_log_v1",
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        schema="public",
    )
    op.add_column(
        "scheduler_lesson_log_v1",
        sa.Column("revoked_by_membership_id", sa.Integer(), nullable=True),
        schema="public",
    )
    op.add_column(
        "scheduler_lesson_log_v1",
        sa.Column("revoked_reason", sa.String(length=250), nullable=True),
        schema="public",
    )
    op.create_unique_constraint(
        "uq_scheduler_lesson_log_v1_org_id",
        "scheduler_lesson_log_v1",
        ["organization_id", "id"],
        schema="public",
    )
    op.create_check_constraint(
        "ck_scheduler_lesson_log_v1_decision",
        "scheduler_lesson_log_v1",
        "decision IS NULL OR decision IN ('GIVEN', 'GAP', 'SUBSTITUTED')",
        schema="public",
    )
    op.create_check_constraint(
        "ck_scheduler_lesson_log_v1_decision_metadata",
        "scheduler_lesson_log_v1",
        "(decision IS NULL) = (decided_at IS NULL)",
        schema="public",
    )
    op.create_foreign_key(
        "fk_scheduler_lesson_log_v1_decider_org",
        "scheduler_lesson_log_v1",
        "organization_membership",
        ["organization_id", "decided_by_membership_id"],
        ["organization_id", "id"],
        source_schema="public",
        referent_schema="public",
    )
    op.create_foreign_key(
        "fk_scheduler_lesson_log_v1_revoker_org",
        "scheduler_lesson_log_v1",
        "organization_membership",
        ["organization_id", "revoked_by_membership_id"],
        ["organization_id", "id"],
        source_schema="public",
        referent_schema="public",
    )

    op.alter_column(
        "operational_schedule_block",
        "source_occurrence_id",
        existing_type=sa.Integer(),
        nullable=True,
        schema="public",
    )
    op.add_column(
        "operational_schedule_block",
        sa.Column(
            "origin_kind",
            postgresql.ENUM("LEGACY", "V1", name="operationalblockorigin", create_type=False),
            nullable=False,
            server_default="LEGACY",
        ),
        schema="public",
    )
    op.add_column(
        "operational_schedule_block",
        sa.Column("source_v1_lesson_log_id", sa.Integer(), nullable=True),
        schema="public",
    )
    op.add_column(
        "operational_schedule_block",
        sa.Column("substitute_curricular_assignment_id", sa.Integer(), nullable=True),
        schema="public",
    )
    op.create_index(
        "ix_operational_schedule_block_source_v1_lesson_log_id",
        "operational_schedule_block",
        ["source_v1_lesson_log_id"],
        schema="public",
    )
    op.create_check_constraint(
        "ck_operational_block_origin_exclusive",
        "operational_schedule_block",
        "(origin_kind = 'LEGACY' AND source_occurrence_id IS NOT NULL "
        "AND planned_active_schedule_block_id IS NOT NULL "
        "AND source_v1_lesson_log_id IS NULL "
        "AND substitute_curricular_assignment_id IS NULL) "
        "OR (origin_kind = 'V1' AND source_v1_lesson_log_id IS NOT NULL "
        "AND substitute_curricular_assignment_id IS NOT NULL "
        "AND source_occurrence_id IS NULL "
        "AND planned_active_schedule_block_id IS NULL)",
        schema="public",
    )
    op.create_check_constraint(
        "ck_operational_block_revision_positive",
        "operational_schedule_block",
        "source_occurrence_revision > 0",
        schema="public",
    )
    op.create_foreign_key(
        "fk_operational_block_v1_log_org",
        "operational_schedule_block",
        "scheduler_lesson_log_v1",
        ["organization_id", "source_v1_lesson_log_id"],
        ["organization_id", "id"],
        source_schema="public",
        referent_schema="public",
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_operational_block_substitute_assignment_org",
        "operational_schedule_block",
        "curricular_assignment",
        ["organization_id", "substitute_curricular_assignment_id"],
        ["organization_id", "id"],
        source_schema="public",
        referent_schema="public",
        ondelete="RESTRICT",
    )
    op.create_index(
        "uq_operational_block_active_legacy",
        "operational_schedule_block",
        ["organization_id", "source_occurrence_id", "source_occurrence_revision"],
        unique=True,
        schema="public",
        postgresql_where=sa.text("status = 'ACTIVE' AND origin_kind = 'LEGACY'"),
    )
    op.create_index(
        "uq_operational_block_active_v1",
        "operational_schedule_block",
        ["organization_id", "source_v1_lesson_log_id", "source_occurrence_revision"],
        unique=True,
        schema="public",
        postgresql_where=sa.text("status = 'ACTIVE' AND origin_kind = 'V1'"),
    )


def downgrade() -> None:
    connection = op.get_bind()
    decisions = connection.execute(
        sa.text("SELECT count(*) FROM public.scheduler_lesson_log_v1 WHERE decision IS NOT NULL")
    ).scalar_one()
    revocation_metadata = connection.execute(
        sa.text(
            "SELECT count(*) FROM public.scheduler_lesson_log_v1 "
            "WHERE revoked_at IS NOT NULL OR revoked_by_membership_id IS NOT NULL "
            "OR revoked_reason IS NOT NULL"
        )
    ).scalar_one()
    v1_blocks = connection.execute(
        sa.text("SELECT count(*) FROM public.operational_schedule_block WHERE origin_kind = 'V1'")
    ).scalar_one()
    if decisions or v1_blocks or revocation_metadata:
        raise RuntimeError(
            "Downgrade refused: occurrence decisions, revocation metadata "
            "or v1 operational blocks exist."
        )

    op.drop_index(
        "uq_operational_block_active_v1",
        table_name="operational_schedule_block",
        schema="public",
    )
    op.drop_index(
        "uq_operational_block_active_legacy",
        table_name="operational_schedule_block",
        schema="public",
    )
    op.drop_constraint(
        "fk_operational_block_substitute_assignment_org",
        "operational_schedule_block",
        type_="foreignkey",
        schema="public",
    )
    op.drop_constraint(
        "fk_operational_block_v1_log_org",
        "operational_schedule_block",
        type_="foreignkey",
        schema="public",
    )
    op.drop_constraint(
        "ck_operational_block_revision_positive",
        "operational_schedule_block",
        type_="check",
        schema="public",
    )
    op.drop_constraint(
        "ck_operational_block_origin_exclusive",
        "operational_schedule_block",
        type_="check",
        schema="public",
    )
    op.drop_index(
        "ix_operational_schedule_block_source_v1_lesson_log_id",
        table_name="operational_schedule_block",
        schema="public",
    )
    op.drop_column(
        "operational_schedule_block", "substitute_curricular_assignment_id", schema="public"
    )
    op.drop_column("operational_schedule_block", "source_v1_lesson_log_id", schema="public")
    op.drop_column("operational_schedule_block", "origin_kind", schema="public")
    op.alter_column(
        "operational_schedule_block",
        "source_occurrence_id",
        existing_type=sa.Integer(),
        nullable=False,
        schema="public",
    )
    op.execute("DROP TYPE public.operationalblockorigin")

    op.drop_constraint(
        "fk_scheduler_lesson_log_v1_revoker_org",
        "scheduler_lesson_log_v1",
        type_="foreignkey",
        schema="public",
    )
    op.drop_constraint(
        "fk_scheduler_lesson_log_v1_decider_org",
        "scheduler_lesson_log_v1",
        type_="foreignkey",
        schema="public",
    )
    op.drop_constraint(
        "ck_scheduler_lesson_log_v1_decision_metadata",
        "scheduler_lesson_log_v1",
        type_="check",
        schema="public",
    )
    op.drop_constraint(
        "ck_scheduler_lesson_log_v1_decision",
        "scheduler_lesson_log_v1",
        type_="check",
        schema="public",
    )
    op.drop_constraint(
        "uq_scheduler_lesson_log_v1_org_id",
        "scheduler_lesson_log_v1",
        type_="unique",
        schema="public",
    )
    op.drop_column("scheduler_lesson_log_v1", "revoked_reason", schema="public")
    op.drop_column("scheduler_lesson_log_v1", "revoked_by_membership_id", schema="public")
    op.drop_column("scheduler_lesson_log_v1", "revoked_at", schema="public")
    op.drop_column("scheduler_lesson_log_v1", "decided_by_membership_id", schema="public")
    op.drop_column("scheduler_lesson_log_v1", "decided_at", schema="public")
    op.drop_column("scheduler_lesson_log_v1", "decision", schema="public")
