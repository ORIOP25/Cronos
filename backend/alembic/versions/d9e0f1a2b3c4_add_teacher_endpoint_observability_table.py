"""Add teacher endpoint observability table.

Revision ID: d9e0f1a2b3c4
Revises: c7d8e9f0a1b2
Create Date: 2026-04-17
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "d9e0f1a2b3c4"
down_revision: str | None = "c7d8e9f0a1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "teacher_endpoint_operational_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organization.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actor_role", sa.String(length=20), nullable=True),
        sa.Column("endpoint_key", sa.String(length=80), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("active_generation_id", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_index(
        "ix_teacher_endpoint_operational_event_org_id",
        "teacher_endpoint_operational_event",
        ["org_id"],
    )
    op.create_index(
        "ix_teacher_endpoint_operational_event_actor_user_id",
        "teacher_endpoint_operational_event",
        ["actor_user_id"],
    )
    op.create_index(
        "ix_teacher_endpoint_operational_event_endpoint_key",
        "teacher_endpoint_operational_event",
        ["endpoint_key"],
    )
    op.create_index(
        "ix_teacher_endpoint_operational_event_http_status",
        "teacher_endpoint_operational_event",
        ["http_status"],
    )
    op.create_index(
        "ix_teacher_endpoint_operational_event_created_at",
        "teacher_endpoint_operational_event",
        ["created_at"],
    )
    op.create_index(
        "ix_teacher_endpoint_event_org_created",
        "teacher_endpoint_operational_event",
        ["org_id", "created_at"],
    )
    op.create_index(
        "ix_teacher_endpoint_event_org_endpoint_created",
        "teacher_endpoint_operational_event",
        ["org_id", "endpoint_key", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_teacher_endpoint_event_org_endpoint_created", table_name="teacher_endpoint_operational_event")
    op.drop_index("ix_teacher_endpoint_event_org_created", table_name="teacher_endpoint_operational_event")
    op.drop_index("ix_teacher_endpoint_operational_event_created_at", table_name="teacher_endpoint_operational_event")
    op.drop_index("ix_teacher_endpoint_operational_event_http_status", table_name="teacher_endpoint_operational_event")
    op.drop_index("ix_teacher_endpoint_operational_event_endpoint_key", table_name="teacher_endpoint_operational_event")
    op.drop_index("ix_teacher_endpoint_operational_event_actor_user_id", table_name="teacher_endpoint_operational_event")
    op.drop_index("ix_teacher_endpoint_operational_event_org_id", table_name="teacher_endpoint_operational_event")
    op.drop_table("teacher_endpoint_operational_event")
