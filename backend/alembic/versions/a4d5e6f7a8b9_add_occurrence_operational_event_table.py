"""Add occurrence operational event table for observability

Revision ID: a4d5e6f7a8b9
Revises: f3c4d5e6f7a8
Create Date: 2026-04-12
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "a4d5e6f7a8b9"
down_revision: str | None = "f3c4d5e6f7a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "occurrence_operational_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organization.id", ondelete="CASCADE"), nullable=False),
        sa.Column("occurrence_id", sa.Integer(), sa.ForeignKey("lesson_occurrence.id", ondelete="SET NULL"), nullable=True),
        sa.Column("schedule_output_id", sa.Integer(), sa.ForeignKey("schedule_output.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("result", sa.String(length=50), nullable=False),
        sa.Column("decision_status", sa.String(length=20), nullable=True),
        sa.Column("detail", sa.String(length=240), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_index("ix_occurrence_operational_event_org_id", "occurrence_operational_event", ["org_id"])
    op.create_index("ix_occurrence_operational_event_occurrence_id", "occurrence_operational_event", ["occurrence_id"])
    op.create_index("ix_occurrence_operational_event_schedule_output_id", "occurrence_operational_event", ["schedule_output_id"])
    op.create_index("ix_occurrence_operational_event_actor_user_id", "occurrence_operational_event", ["actor_user_id"])
    op.create_index("ix_occurrence_operational_event_created_at", "occurrence_operational_event", ["created_at"])
    op.create_index("ix_occ_event_org_created", "occurrence_operational_event", ["org_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_occ_event_org_created", table_name="occurrence_operational_event")
    op.drop_index("ix_occurrence_operational_event_created_at", table_name="occurrence_operational_event")
    op.drop_index("ix_occurrence_operational_event_actor_user_id", table_name="occurrence_operational_event")
    op.drop_index("ix_occurrence_operational_event_schedule_output_id", table_name="occurrence_operational_event")
    op.drop_index("ix_occurrence_operational_event_occurrence_id", table_name="occurrence_operational_event")
    op.drop_index("ix_occurrence_operational_event_org_id", table_name="occurrence_operational_event")
    op.drop_table("occurrence_operational_event")
