"""occurrences_v5_operational_blocks

Revision ID: 9b7a4c2d1e6f
Revises: d6fc61979dd3
Create Date: 2026-05-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9b7a4c2d1e6f"
down_revision: Union[str, None] = "d6fc61979dd3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("organization_settings", sa.Column("auto_confirm_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("organization_settings", sa.Column("auto_confirm_cutoff_time", sa.Time(), nullable=True))

    op.add_column("lesson_occurrence", sa.Column("revision", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("lesson_occurrence", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("lesson_occurrence", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("lesson_occurrence", sa.Column("created_by_user_id", sa.Integer(), nullable=True))
    op.add_column("lesson_occurrence", sa.Column("creation_source", sa.String(length=40), nullable=True))
    op.add_column("lesson_occurrence", sa.Column("reason", sa.String(length=250), nullable=True))
    op.add_column("lesson_occurrence", sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("lesson_occurrence", sa.Column("revoked_by_user_id", sa.Integer(), nullable=True))
    op.add_column("lesson_occurrence", sa.Column("revoked_reason", sa.String(length=250), nullable=True))
    op.add_column("lesson_occurrence", sa.Column("planned_timeslot_id", sa.Integer(), nullable=True))
    op.add_column("lesson_occurrence", sa.Column("planned_room_id", sa.Integer(), nullable=True))
    op.add_column("lesson_occurrence", sa.Column("planned_generation_id", sa.String(length=100), nullable=True))
    op.alter_column("lesson_occurrence", "status", existing_type=sa.Enum("GIVEN", "GAP", "SUBSTITUTED", "REVOKED", name="lessonoccurrencestatus"), nullable=True)

    op.create_foreign_key("fk_lesson_occurrence_created_by_user", "lesson_occurrence", "user", ["created_by_user_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_lesson_occurrence_revoked_by_user", "lesson_occurrence", "user", ["revoked_by_user_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_lesson_occurrence_planned_timeslot", "lesson_occurrence", "timeslot", ["planned_timeslot_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_lesson_occurrence_planned_room", "lesson_occurrence", "room", ["planned_room_id"], ["id"], ondelete="SET NULL")

    op.execute("UPDATE lesson_occurrence SET status = NULL WHERE status = 'GIVEN' AND decided_at IS NULL")
    op.execute("UPDATE lesson_occurrence SET is_active = FALSE WHERE status = 'REVOKED'")

    op.drop_constraint("uq_lesson_occurrence_output_date", "lesson_occurrence", type_="unique")
    op.create_unique_constraint(
        "uq_lesson_occurrence_output_date_revision",
        "lesson_occurrence",
        ["organization_id", "schedule_output_id", "date", "revision"],
    )
    op.create_index("ix_lesson_occurrence_org_active_date", "lesson_occurrence", ["organization_id", "is_active", "date"])
    if op.get_bind().dialect.name == "postgresql":
        op.create_index(
            "uq_lesson_occurrence_active_output_date",
            "lesson_occurrence",
            ["organization_id", "schedule_output_id", "date"],
            unique=True,
            postgresql_where=sa.text("is_active = true"),
        )

    op.create_table(
        "operational_schedule_block",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("source_occurrence_id", sa.Integer(), nullable=False),
        sa.Column("source_occurrence_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("planned_schedule_output_id", sa.Integer(), nullable=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("timeslot_id", sa.Integer(), nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=True),
        sa.Column("class_id", sa.Integer(), nullable=False),
        sa.Column("teacher_id", sa.Integer(), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("module_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.Enum("ACTIVE", "CANCELLED", name="operationalblockstatus"), nullable=False),
        sa.Column("execution_status", sa.Enum("PENDING_LOG", "COMPLETED", "CANCELLED", name="operationalblockexecutionstatus"), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["class_id"], ["class.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["module_id"], ["module.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["planned_schedule_output_id"], ["schedule_output.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["room_id"], ["room.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_occurrence_id"], ["lesson_occurrence.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subject_id"], ["subject.id"]),
        sa.ForeignKeyConstraint(["teacher_id"], ["teacher.id"]),
        sa.ForeignKeyConstraint(["timeslot_id"], ["timeslot.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_operational_block_org_teacher_date_slot", "operational_schedule_block", ["organization_id", "teacher_id", "date", "timeslot_id"])
    op.create_index("ix_operational_block_org_class_date", "operational_schedule_block", ["organization_id", "class_id", "date"])

    op.add_column("lesson_log", sa.Column("operational_block_id", sa.Integer(), nullable=True))
    op.add_column("lesson_log", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.alter_column("lesson_log", "schedule_output_id", existing_type=sa.Integer(), nullable=True)
    op.create_foreign_key("fk_lesson_log_operational_block", "lesson_log", "operational_schedule_block", ["operational_block_id"], ["id"], ondelete="CASCADE")
    op.create_unique_constraint("uq_lesson_log_operational_block", "lesson_log", ["operational_block_id"])
    op.create_check_constraint(
        "ck_lesson_log_exactly_one_target",
        "lesson_log",
        "(schedule_output_id IS NOT NULL AND operational_block_id IS NULL) OR (schedule_output_id IS NULL AND operational_block_id IS NOT NULL)",
    )

    op.create_table(
        "progress_ledger_entry",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("source_revision", sa.Integer(), nullable=True),
        sa.Column("class_id", sa.Integer(), nullable=False),
        sa.Column("module_id", sa.Integer(), nullable=False),
        sa.Column("completed_delta", sa.Float(), nullable=False),
        sa.Column("debt_delta", sa.Float(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reverses_ledger_entry_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["class_id"], ["class.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["module_id"], ["module.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reverses_ledger_entry_id"], ["progress_ledger_entry.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index("ix_progress_ledger_org_source", "progress_ledger_entry", ["organization_id", "source_type", "source_id"])


def downgrade() -> None:
    op.drop_index("ix_progress_ledger_org_source", table_name="progress_ledger_entry")
    op.drop_table("progress_ledger_entry")
    op.drop_constraint("ck_lesson_log_exactly_one_target", "lesson_log", type_="check")
    op.drop_constraint("uq_lesson_log_operational_block", "lesson_log", type_="unique")
    op.drop_constraint("fk_lesson_log_operational_block", "lesson_log", type_="foreignkey")
    op.drop_column("lesson_log", "version")
    op.drop_column("lesson_log", "operational_block_id")
    op.alter_column("lesson_log", "schedule_output_id", existing_type=sa.Integer(), nullable=False)
    op.drop_index("ix_operational_block_org_class_date", table_name="operational_schedule_block")
    op.drop_index("ix_operational_block_org_teacher_date_slot", table_name="operational_schedule_block")
    op.drop_table("operational_schedule_block")
    if op.get_bind().dialect.name == "postgresql":
        op.drop_index("uq_lesson_occurrence_active_output_date", table_name="lesson_occurrence")
    op.drop_index("ix_lesson_occurrence_org_active_date", table_name="lesson_occurrence")
    op.drop_constraint("uq_lesson_occurrence_output_date_revision", "lesson_occurrence", type_="unique")
    op.create_unique_constraint("uq_lesson_occurrence_output_date", "lesson_occurrence", ["schedule_output_id", "date"])
    op.execute("UPDATE lesson_occurrence SET status = 'GIVEN' WHERE status IS NULL")
    for column in [
        "planned_generation_id",
        "planned_room_id",
        "planned_timeslot_id",
        "revoked_reason",
        "revoked_by_user_id",
        "revoked_at",
        "reason",
        "creation_source",
        "created_by_user_id",
        "version",
        "is_active",
        "revision",
    ]:
        op.drop_column("lesson_occurrence", column)
    op.alter_column("lesson_occurrence", "status", existing_type=sa.Enum("GIVEN", "GAP", "SUBSTITUTED", "REVOKED", name="lessonoccurrencestatus"), nullable=False)
    op.drop_column("organization_settings", "auto_confirm_cutoff_time")
    op.drop_column("organization_settings", "auto_confirm_enabled")
