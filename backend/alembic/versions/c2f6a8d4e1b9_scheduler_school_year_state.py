"""scheduler school year state

Revision ID: c2f6a8d4e1b9
Revises: 9b7a4c2d1e6f, f4a9b2c8d1e7
Create Date: 2026-06-19
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c2f6a8d4e1b9"
down_revision: Union[str, tuple[str, str], None] = (
    "9b7a4c2d1e6f",
    "f4a9b2c8d1e7",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NEW_TENANT_TABLES = (
    "scheduler_school_year",
    "scheduler_school_year_state",
    "schedule_generation_job",
    "schedule_drafts",
    "schedule_draft_blocks",
    "schedule_diff_entries",
    "active_schedule_blocks",
    "planned_recovery_links",
    "scheduler_state_version_events",
)


def _quoted_identifier(name: str) -> str:
    clean_name = name.strip('"')
    return '"' + clean_name.replace('"', '""') + '"'


def _create_same_tenant_trigger(table: str, refs: dict[str, str]) -> None:
    checks = []
    for column, ref_table in refs.items():
        checks.append(
            f"""
            IF NEW.{column} IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM public.{_quoted_identifier(ref_table)}
                WHERE id = NEW.{column}
                  AND organization_id = NEW.organization_id
            ) THEN
                RAISE EXCEPTION
                    'cross-tenant reference rejected: {table}.{column} -> {ref_table}.id'
                    USING ERRCODE = '23514';
            END IF;
            """
        )
    op.execute(
        sa.text(
            f"""
            CREATE OR REPLACE FUNCTION app_security.validate_{table}_tenant_refs()
            RETURNS trigger
            LANGUAGE plpgsql
            SET search_path = pg_catalog, public
            AS $$
            BEGIN
                {''.join(checks)}
                RETURN NEW;
            END;
            $$;

            DROP TRIGGER IF EXISTS trg_{table}_tenant_refs
                ON public.{_quoted_identifier(table)};
            CREATE TRIGGER trg_{table}_tenant_refs
            BEFORE INSERT OR UPDATE ON public.{_quoted_identifier(table)}
            FOR EACH ROW
            EXECUTE FUNCTION app_security.validate_{table}_tenant_refs();
            """
        )
    )


def _drop_same_tenant_trigger(table: str) -> None:
    op.execute(
        f"DROP TRIGGER IF EXISTS trg_{table}_tenant_refs "
        f"ON public.{_quoted_identifier(table)}"
    )
    op.execute(f"DROP FUNCTION IF EXISTS app_security.validate_{table}_tenant_refs()")


publication_state = postgresql.ENUM(
    "UNPUBLISHED",
    "PUBLISHED",
    name="schoolyearpublicationstate",
    create_type=False,
)
generation_strategy = postgresql.ENUM(
    "COMPLETE_GENERATION",
    "ADAPTIVE_REPAIR",
    name="schedulegenerationstrategy",
    create_type=False,
)
generation_trigger = postgresql.ENUM(
    "FIRST_GENERATION",
    "EXPLICIT_DEBT",
    "SCHEDULER_CHANGE",
    "MIXED",
    name="schedulegenerationtrigger",
    create_type=False,
)
generation_job_status = postgresql.ENUM(
    "QUEUED",
    "RUNNING",
    "CANCEL_REQUESTED",
    "CANCELED",
    "SUCCEEDED",
    "FAILED",
    "NO_VALID_OUTPUT",
    name="schedulegenerationjobstatus",
    create_type=False,
)
generation_result_category = postgresql.ENUM(
    "COMPLETE_SUCCESS",
    "PARTIAL_RECOVERY",
    "NO_VALID_OUTPUT",
    name="schedulegenerationresultcategory",
    create_type=False,
)
draft_state = postgresql.ENUM(
    "PENDING",
    "APPROVED",
    "REJECTED",
    "REPLACED",
    "STALE",
    "INVALIDATED",
    name="scheduledraftstate",
    create_type=False,
)
draft_block_change_type = postgresql.ENUM(
    "UNCHANGED",
    "ADDED",
    "MOVED",
    "ROOM_ONLY",
    "REPLACED",
    name="scheduledraftblockchangetype",
    create_type=False,
)
diff_change_type = postgresql.ENUM(
    "ADDED",
    "MOVED",
    "CHANGED",
    "REMOVED",
    "UNCHANGED_IMPACTED",
    name="schedulediffchangetype",
    create_type=False,
)
diff_scope = postgresql.ENUM(
    "AFFECTED",
    "RELATED",
    "UNRELATED",
    name="schedulediffscope",
    create_type=False,
)
active_block_status = postgresql.ENUM(
    "ACTIVE",
    "REMOVED",
    "CANCELED",
    name="activescheduleblockstatus",
    create_type=False,
)
recovery_link_status = postgresql.ENUM(
    "PLANNED",
    "DELIVERED",
    "CANCELED",
    "REPLACED",
    name="plannedrecoverylinkstatus",
    create_type=False,
)
state_change_operation = postgresql.ENUM(
    "CREATE",
    "UPDATE",
    "DELETE",
    "BULK_IMPORT",
    name="schedulerstatechangeoperation",
    create_type=False,
)
state_change_scope = postgresql.ENUM(
    "FUTURE_IMPACTING",
    "PAST_ONLY",
    "NO_OP",
    "INACTIVE_RESOURCE",
    name="schedulerstatechangescope",
    create_type=False,
)
room_type = postgresql.ENUM(
    "normal",
    "lab",
    "gym",
    "art",
    name="roomtype",
    create_type=False,
)


def upgrade() -> None:
    publication_state.create(op.get_bind(), checkfirst=True)
    generation_strategy.create(op.get_bind(), checkfirst=True)
    generation_trigger.create(op.get_bind(), checkfirst=True)
    generation_job_status.create(op.get_bind(), checkfirst=True)
    generation_result_category.create(op.get_bind(), checkfirst=True)
    draft_state.create(op.get_bind(), checkfirst=True)
    draft_block_change_type.create(op.get_bind(), checkfirst=True)
    diff_change_type.create(op.get_bind(), checkfirst=True)
    diff_scope.create(op.get_bind(), checkfirst=True)
    active_block_status.create(op.get_bind(), checkfirst=True)
    recovery_link_status.create(op.get_bind(), checkfirst=True)
    state_change_operation.create(op.get_bind(), checkfirst=True)
    state_change_scope.create(op.get_bind(), checkfirst=True)

    op.create_unique_constraint(
        "uq_lesson_occurrence_id_org_revision",
        "lesson_occurrence",
        ["id", "organization_id", "revision"],
    )

    op.create_table(
        "scheduler_school_year",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=20), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("hard_end_date", sa.Date(), nullable=False),
        sa.Column(
            "timezone",
            sa.String(length=64),
            nullable=False,
            server_default="Europe/Lisbon",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "hard_end_date >= start_date",
            name="ck_scheduler_school_year_date_order",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organization.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id", "organization_id", name="uq_scheduler_school_year_id_org"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "label",
            name="uq_scheduler_school_year_org_label",
        ),
    )
    op.create_index(
        "ix_scheduler_school_year_organization_id",
        "scheduler_school_year",
        ["organization_id"],
    )
    if op.get_bind().dialect.name == "postgresql":
        op.create_index(
            "uq_scheduler_school_year_active_org",
            "scheduler_school_year",
            ["organization_id"],
            unique=True,
            postgresql_where=sa.text("is_active = TRUE"),
        )

    op.create_table(
        "scheduler_school_year_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("school_year_id", sa.Integer(), nullable=False),
        sa.Column(
            "school_year_publication_state",
            publication_state,
            nullable=False,
            server_default="UNPUBLISHED",
        ),
        sa.Column("active_schedule_version_id", sa.String(length=100), nullable=True),
        sa.Column(
            "scheduler_state_version",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("approved_scheduler_state_version", sa.Integer(), nullable=True),
        sa.Column("reset_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reset_by_user_id", sa.Integer(), nullable=True),
        sa.Column("lock_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "scheduler_state_version >= 0",
            name="ck_scheduler_school_year_state_version_nonnegative",
        ),
        sa.CheckConstraint(
            "lock_version >= 0",
            name="ck_scheduler_school_year_state_lock_version_nonnegative",
        ),
        sa.CheckConstraint(
            "school_year_publication_state <> 'PUBLISHED' "
            "OR active_schedule_version_id IS NOT NULL",
            name="ck_scheduler_school_year_state_published_has_version",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organization.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reset_by_user_id"],
            ["user.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["school_year_id", "organization_id"],
            ["scheduler_school_year.id", "scheduler_school_year.organization_id"],
            name="fk_scheduler_school_year_state_year_scope",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "school_year_id",
            name="uq_scheduler_school_year_state_org_year",
        ),
    )
    op.create_index(
        "ix_scheduler_school_year_state_organization_id",
        "scheduler_school_year_state",
        ["organization_id"],
    )
    op.create_index(
        "ix_scheduler_school_year_state_school_year_id",
        "scheduler_school_year_state",
        ["school_year_id"],
    )

    op.create_table(
        "schedule_generation_job",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("school_year_id", sa.Integer(), nullable=False),
        sa.Column("requested_by_user_id", sa.Integer(), nullable=True),
        sa.Column("strategy", generation_strategy, nullable=False),
        sa.Column("trigger_type", generation_trigger, nullable=True),
        sa.Column(
            "job_status",
            generation_job_status,
            nullable=False,
            server_default="QUEUED",
        ),
        sa.Column("result_category", generation_result_category, nullable=True),
        sa.Column("generation_input_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("debt_basis_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("scheduler_state_version_used", sa.Integer(), nullable=True),
        sa.Column("repair_policy_snapshot_hash", sa.String(length=64), nullable=True),
        sa.Column("input_snapshot_json", sa.JSON(), nullable=True),
        sa.Column(
            "queued_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("cancellation_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=50), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=100), nullable=True),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="ck_schedule_generation_job_duration_nonnegative",
        ),
        sa.CheckConstraint(
            "(job_status = 'SUCCEEDED' AND result_category IN "
            "('COMPLETE_SUCCESS', 'PARTIAL_RECOVERY')) OR "
            "(job_status = 'NO_VALID_OUTPUT' AND result_category = 'NO_VALID_OUTPUT') OR "
            "(job_status NOT IN ('SUCCEEDED', 'NO_VALID_OUTPUT') AND result_category IS NULL)",
            name="ck_schedule_generation_job_result_consistency",
        ),
        sa.CheckConstraint(
            "(job_status IN ('CANCELED', 'SUCCEEDED', 'FAILED', 'NO_VALID_OUTPUT') "
            "AND finished_at IS NOT NULL) OR "
            "(job_status NOT IN ('CANCELED', 'SUCCEEDED', 'FAILED', 'NO_VALID_OUTPUT') "
            "AND finished_at IS NULL)",
            name="ck_schedule_generation_job_terminal_finished",
        ),
        sa.CheckConstraint(
            "started_at IS NULL OR started_at >= queued_at",
            name="ck_schedule_generation_job_started_after_queued",
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR (started_at IS NOT NULL AND finished_at >= started_at)",
            name="ck_schedule_generation_job_finished_after_started",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organization.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"],
            ["user.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["school_year_id", "organization_id"],
            ["scheduler_school_year.id", "scheduler_school_year.organization_id"],
            name="fk_schedule_generation_job_year_scope",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id",
            "organization_id",
            "school_year_id",
            name="uq_schedule_generation_job_id_scope",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "school_year_id",
            "idempotency_key",
            name="uq_schedule_generation_job_idempotency",
        ),
    )
    op.create_index(
        "ix_schedule_generation_job_organization_id",
        "schedule_generation_job",
        ["organization_id"],
    )
    op.create_index(
        "ix_schedule_generation_job_school_year_id",
        "schedule_generation_job",
        ["school_year_id"],
    )
    if op.get_bind().dialect.name == "postgresql":
        op.create_index(
            "uq_schedule_generation_job_active_year",
            "schedule_generation_job",
            ["organization_id", "school_year_id"],
            unique=True,
            postgresql_where=sa.text(
                "job_status IN ('QUEUED', 'RUNNING', 'CANCEL_REQUESTED')"
            ),
        )

    op.create_table(
        "schedule_drafts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("school_year_id", sa.Integer(), nullable=False),
        sa.Column("generation_job_id", sa.Integer(), nullable=False),
        sa.Column("strategy", generation_strategy, nullable=False),
        sa.Column("draft_state", draft_state, nullable=False, server_default="PENDING"),
        sa.Column("result_category", generation_result_category, nullable=False),
        sa.Column("trigger_type", generation_trigger, nullable=False),
        sa.Column("generation_input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("scheduler_state_version_used", sa.Integer(), nullable=True),
        sa.Column("debt_basis_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("repair_policy_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("repair_policy_snapshot_hash", sa.String(length=64), nullable=True),
        sa.Column("editable_start_date", sa.Date(), nullable=True),
        sa.Column("recovery_escalation_level", sa.String(length=50), nullable=True),
        sa.Column("adaptation_level", sa.String(length=50), nullable=True),
        sa.Column("projected_completion_date", sa.Date(), nullable=False),
        sa.Column("hard_end_date", sa.Date(), nullable=False),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("partial_recovery_blocker_type", sa.String(length=50), nullable=True),
        sa.Column("main_blocker_message", sa.Text(), nullable=True),
        sa.Column("recommended_actions_json", sa.JSON(), nullable=True),
        sa.Column("warnings_json", sa.JSON(), nullable=True),
        sa.Column("metrics_json", sa.JSON(), nullable=True),
        sa.Column("stale_reason", sa.Text(), nullable=True),
        sa.Column("invalidated_reason", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("decided_by_user_id", sa.Integer(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "projected_completion_date <= hard_end_date",
            name="ck_schedule_drafts_completion_by_hard_end",
        ),
        sa.CheckConstraint(
            "result_category <> 'NO_VALID_OUTPUT'",
            name="ck_schedule_drafts_has_valid_output",
        ),
        sa.CheckConstraint(
            "scheduler_state_version_used IS NULL OR scheduler_state_version_used >= 0",
            name="ck_schedule_drafts_state_version_nonnegative",
        ),
        sa.CheckConstraint(
            "strategy = 'COMPLETE_GENERATION' OR editable_start_date IS NOT NULL",
            name="ck_schedule_drafts_adaptive_editable_start",
        ),
        sa.CheckConstraint(
            "(draft_state = 'PENDING' AND decided_at IS NULL AND decided_by_user_id IS NULL) "
            "OR (draft_state <> 'PENDING' AND decided_at IS NOT NULL)",
            name="ck_schedule_drafts_decision_consistency",
        ),
        sa.CheckConstraint(
            "(draft_state = 'STALE' AND stale_reason IS NOT NULL) OR "
            "(draft_state <> 'STALE' AND stale_reason IS NULL)",
            name="ck_schedule_drafts_stale_reason",
        ),
        sa.CheckConstraint(
            "(draft_state = 'INVALIDATED' AND invalidated_reason IS NOT NULL) OR "
            "(draft_state <> 'INVALIDATED' AND invalidated_reason IS NULL)",
            name="ck_schedule_drafts_invalidated_reason",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["user.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_user_id"], ["user.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["generation_job_id", "organization_id", "school_year_id"],
            [
                "schedule_generation_job.id",
                "schedule_generation_job.organization_id",
                "schedule_generation_job.school_year_id",
            ],
            name="fk_schedule_drafts_generation_job_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organization.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["school_year_id"], ["scheduler_school_year.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("generation_job_id", name="uq_schedule_drafts_generation_job"),
        sa.UniqueConstraint(
            "id",
            "organization_id",
            "school_year_id",
            name="uq_schedule_drafts_id_scope",
        ),
        sa.UniqueConstraint(
            "id",
            "generation_job_id",
            "organization_id",
            "school_year_id",
            name="uq_schedule_drafts_id_job_scope",
        ),
    )
    op.create_index(
        "ix_schedule_drafts_organization_id",
        "schedule_drafts",
        ["organization_id"],
    )
    op.create_index(
        "ix_schedule_drafts_school_year_id",
        "schedule_drafts",
        ["school_year_id"],
    )
    if op.get_bind().dialect.name == "postgresql":
        op.create_index(
            "uq_schedule_drafts_pending_year",
            "schedule_drafts",
            ["organization_id", "school_year_id"],
            unique=True,
            postgresql_where=sa.text("draft_state = 'PENDING'"),
        )

    op.add_column(
        "scheduler_school_year_state",
        sa.Column("pending_draft_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_scheduler_school_year_state_pending_draft_scope",
        "scheduler_school_year_state",
        "schedule_drafts",
        ["pending_draft_id", "organization_id", "school_year_id"],
        ["id", "organization_id", "school_year_id"],
    )

    op.create_table(
        "schedule_draft_blocks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("school_year_id", sa.Integer(), nullable=False),
        sa.Column("draft_id", sa.Integer(), nullable=False),
        sa.Column("source_active_block_id", sa.Integer(), nullable=True),
        sa.Column("stable_block_key", sa.String(length=64), nullable=False),
        sa.Column("class_id", sa.Integer(), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("teacher_id", sa.Integer(), nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=False),
        sa.Column("room_type_id", room_type, nullable=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("timeslot_id", sa.Integer(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("module_sequence_index", sa.Integer(), nullable=True),
        sa.Column("is_recovery_block", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("recovery_source_occurrence_id", sa.Integer(), nullable=True),
        sa.Column("recovery_source_occurrence_revision", sa.Integer(), nullable=True),
        sa.Column("change_type", draft_block_change_type, nullable=False),
        sa.Column("reason_code", sa.String(length=50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "duration_minutes > 0",
            name="ck_schedule_draft_blocks_duration_positive",
        ),
        sa.CheckConstraint(
            "module_sequence_index IS NULL OR module_sequence_index >= 0",
            name="ck_schedule_draft_blocks_module_sequence_nonnegative",
        ),
        sa.CheckConstraint(
            "(is_recovery_block AND recovery_source_occurrence_id IS NOT NULL AND "
            "recovery_source_occurrence_revision IS NOT NULL) OR "
            "(NOT is_recovery_block AND recovery_source_occurrence_id IS NULL AND "
            "recovery_source_occurrence_revision IS NULL)",
            name="ck_schedule_draft_blocks_recovery_source",
        ),
        sa.CheckConstraint(
            "recovery_source_occurrence_revision IS NULL "
            "OR recovery_source_occurrence_revision > 0",
            name="ck_schedule_draft_blocks_recovery_revision_positive",
        ),
        sa.CheckConstraint(
            "(change_type = 'ADDED' AND source_active_block_id IS NULL) OR "
            "(change_type <> 'ADDED' AND source_active_block_id IS NOT NULL)",
            name="ck_schedule_draft_blocks_change_source",
        ),
        sa.CheckConstraint(
            "length(trim(stable_block_key)) > 0",
            name="ck_schedule_draft_blocks_stable_key_nonempty",
        ),
        sa.ForeignKeyConstraint(["class_id"], ["class.id"]),
        sa.ForeignKeyConstraint(
            ["draft_id", "organization_id", "school_year_id"],
            [
                "schedule_drafts.id",
                "schedule_drafts.organization_id",
                "schedule_drafts.school_year_id",
            ],
            name="fk_schedule_draft_blocks_draft_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organization.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["room_id"], ["room.id"]),
        sa.ForeignKeyConstraint(
            ["recovery_source_occurrence_id"],
            ["lesson_occurrence.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["school_year_id"], ["scheduler_school_year.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["subject_id"], ["subject.id"]),
        sa.ForeignKeyConstraint(["teacher_id"], ["teacher.id"]),
        sa.ForeignKeyConstraint(["timeslot_id"], ["timeslot.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "draft_id", "stable_block_key",
            name="uq_schedule_draft_blocks_stable_key",
        ),
        sa.UniqueConstraint(
            "id", "organization_id", "school_year_id",
            name="uq_schedule_draft_blocks_id_scope",
        ),
        sa.UniqueConstraint(
            "draft_id", "class_id", "date", "timeslot_id",
            name="uq_schedule_draft_blocks_class_slot",
        ),
        sa.UniqueConstraint(
            "draft_id", "teacher_id", "date", "timeslot_id",
            name="uq_schedule_draft_blocks_teacher_slot",
        ),
        sa.UniqueConstraint(
            "draft_id", "room_id", "date", "timeslot_id",
            name="uq_schedule_draft_blocks_room_slot",
        ),
    )
    op.create_index(
        "ix_schedule_draft_blocks_organization_id",
        "schedule_draft_blocks",
        ["organization_id"],
    )
    op.create_index(
        "ix_schedule_draft_blocks_school_year_id",
        "schedule_draft_blocks",
        ["school_year_id"],
    )
    op.create_index(
        "ix_schedule_draft_blocks_draft_id",
        "schedule_draft_blocks",
        ["draft_id"],
    )

    op.create_table(
        "schedule_diff_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("school_year_id", sa.Integer(), nullable=False),
        sa.Column("generation_job_id", sa.Integer(), nullable=False),
        sa.Column("draft_id", sa.Integer(), nullable=False),
        sa.Column("class_id", sa.Integer(), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("teacher_id", sa.Integer(), nullable=False),
        sa.Column("before_active_block_id", sa.Integer(), nullable=True),
        sa.Column("after_draft_block_id", sa.Integer(), nullable=True),
        sa.Column("before_date", sa.Date(), nullable=True),
        sa.Column("before_timeslot_id", sa.Integer(), nullable=True),
        sa.Column("before_room_id", sa.Integer(), nullable=True),
        sa.Column("after_date", sa.Date(), nullable=True),
        sa.Column("after_timeslot_id", sa.Integer(), nullable=True),
        sa.Column("after_room_id", sa.Integer(), nullable=True),
        sa.Column("before_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("after_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("change_type", diff_change_type, nullable=False),
        sa.Column(
            "impact_scope", diff_scope, nullable=False, server_default="AFFECTED"
        ),
        sa.Column("reason_code", sa.String(length=50), nullable=True),
        sa.Column("reason_message", sa.Text(), nullable=True),
        sa.Column("recovery_link_impact_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "(change_type = 'ADDED' AND before_snapshot_json IS NULL "
            "AND after_snapshot_json IS NOT NULL) OR "
            "(change_type = 'REMOVED' AND before_snapshot_json IS NOT NULL "
            "AND after_snapshot_json IS NULL) OR "
            "(change_type NOT IN ('ADDED', 'REMOVED') "
            "AND before_snapshot_json IS NOT NULL AND after_snapshot_json IS NOT NULL)",
            name="ck_schedule_diff_entries_sides",
        ),
        sa.ForeignKeyConstraint(
            ["after_draft_block_id"],
            ["schedule_draft_blocks.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["after_room_id"], ["room.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["after_timeslot_id"], ["timeslot.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["before_room_id"], ["room.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["before_timeslot_id"], ["timeslot.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["class_id"], ["class.id"]),
        sa.ForeignKeyConstraint(
            ["draft_id", "generation_job_id", "organization_id", "school_year_id"],
            [
                "schedule_drafts.id",
                "schedule_drafts.generation_job_id",
                "schedule_drafts.organization_id",
                "schedule_drafts.school_year_id",
            ],
            name="fk_schedule_diff_entries_draft_job_scope",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organization.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["school_year_id"], ["scheduler_school_year.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["subject_id"], ["subject.id"]),
        sa.ForeignKeyConstraint(["teacher_id"], ["teacher.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_schedule_diff_entries_organization_id",
        "schedule_diff_entries",
        ["organization_id"],
    )
    op.create_index(
        "ix_schedule_diff_entries_school_year_id",
        "schedule_diff_entries",
        ["school_year_id"],
    )
    op.create_index(
        "ix_schedule_diff_entries_draft_id",
        "schedule_diff_entries",
        ["draft_id"],
    )

    op.create_table(
        "active_schedule_blocks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("school_year_id", sa.Integer(), nullable=False),
        sa.Column("schedule_version_id", sa.String(length=100), nullable=False),
        sa.Column("stable_block_key", sa.String(length=64), nullable=False),
        sa.Column("class_id", sa.Integer(), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("teacher_id", sa.Integer(), nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("timeslot_id", sa.Integer(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("source_draft_block_id", sa.Integer(), nullable=False),
        sa.Column("is_recovery_block", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", active_block_status, nullable=False, server_default="ACTIVE"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "duration_minutes > 0", name="ck_active_schedule_blocks_duration_positive"
        ),
        sa.CheckConstraint(
            "length(trim(stable_block_key)) > 0",
            name="ck_active_schedule_blocks_stable_key_nonempty",
        ),
        sa.ForeignKeyConstraint(["class_id"], ["class.id"]),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organization.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["room_id"], ["room.id"]),
        sa.ForeignKeyConstraint(
            ["school_year_id"], ["scheduler_school_year.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_draft_block_id", "organization_id", "school_year_id"],
            [
                "schedule_draft_blocks.id",
                "schedule_draft_blocks.organization_id",
                "schedule_draft_blocks.school_year_id",
            ],
            name="fk_active_schedule_blocks_draft_block_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["subject_id"], ["subject.id"]),
        sa.ForeignKeyConstraint(["teacher_id"], ["teacher.id"]),
        sa.ForeignKeyConstraint(["timeslot_id"], ["timeslot.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id", "organization_id", "school_year_id",
            name="uq_active_schedule_blocks_id_scope",
        ),
        sa.UniqueConstraint(
            "source_draft_block_id",
            name="uq_active_schedule_blocks_source_draft_block",
        ),
        sa.UniqueConstraint(
            "organization_id", "school_year_id", "schedule_version_id", "stable_block_key",
            name="uq_active_schedule_blocks_version_stable_key",
        ),
    )
    op.create_index(
        "ix_active_schedule_blocks_organization_id", "active_schedule_blocks",
        ["organization_id"],
    )
    op.create_index(
        "ix_active_schedule_blocks_school_year_id", "active_schedule_blocks",
        ["school_year_id"],
    )
    op.create_index(
        "ix_active_schedule_blocks_schedule_version_id", "active_schedule_blocks",
        ["schedule_version_id"],
    )
    if op.get_bind().dialect.name == "postgresql":
        for index_name, resource_column in (
            ("uq_active_schedule_blocks_class_slot", "class_id"),
            ("uq_active_schedule_blocks_teacher_slot", "teacher_id"),
            ("uq_active_schedule_blocks_room_slot", "room_id"),
        ):
            op.create_index(
                index_name,
                "active_schedule_blocks",
                [
                    "organization_id", "school_year_id", resource_column,
                    "date", "timeslot_id",
                ],
                unique=True,
                postgresql_where=sa.text("status = 'ACTIVE'"),
            )

    op.create_foreign_key(
        "fk_schedule_draft_blocks_source_active",
        "schedule_draft_blocks",
        "active_schedule_blocks",
        ["source_active_block_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_schedule_diff_entries_before_active",
        "schedule_diff_entries",
        "active_schedule_blocks",
        ["before_active_block_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.drop_constraint("ck_lesson_log_exactly_one_target", "lesson_log", type_="check")
    op.add_column(
        "lesson_log",
        sa.Column("active_schedule_block_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_lesson_log_active_schedule_block",
        "lesson_log",
        "active_schedule_blocks",
        ["active_schedule_block_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_lesson_log_active_schedule_block",
        "lesson_log",
        ["active_schedule_block_id"],
    )
    op.create_unique_constraint(
        "uq_lesson_log_id_org_active_block",
        "lesson_log",
        ["id", "organization_id", "active_schedule_block_id"],
    )
    op.create_check_constraint(
        "ck_lesson_log_exactly_one_target",
        "lesson_log",
        "(CASE WHEN schedule_output_id IS NOT NULL THEN 1 ELSE 0 END + "
        "CASE WHEN operational_block_id IS NOT NULL THEN 1 ELSE 0 END + "
        "CASE WHEN active_schedule_block_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
    )
    op.create_index(
        "ix_lesson_log_active_schedule_block_id",
        "lesson_log",
        ["active_schedule_block_id"],
    )

    op.create_table(
        "planned_recovery_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("school_year_id", sa.Integer(), nullable=False),
        sa.Column("debt_occurrence_id", sa.Integer(), nullable=False),
        sa.Column("debt_occurrence_revision", sa.Integer(), nullable=False),
        sa.Column("planned_active_block_id", sa.Integer(), nullable=True),
        sa.Column("planned_draft_block_id", sa.Integer(), nullable=True),
        sa.Column("planned_recovery_minutes", sa.Integer(), nullable=False),
        sa.Column("delivered_recovery_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("delivered_lesson_log_id", sa.Integer(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("class_id", sa.Integer(), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=False),
        sa.Column("teacher_id", sa.Integer(), nullable=True),
        sa.Column("status", recovery_link_status, nullable=False, server_default="PLANNED"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "planned_recovery_minutes > 0",
            name="ck_planned_recovery_links_planned_minutes_positive",
        ),
        sa.CheckConstraint(
            "delivered_recovery_minutes >= 0 AND "
            "delivered_recovery_minutes <= planned_recovery_minutes",
            name="ck_planned_recovery_links_delivered_minutes_range",
        ),
        sa.CheckConstraint(
            "planned_active_block_id IS NOT NULL OR planned_draft_block_id IS NOT NULL",
            name="ck_planned_recovery_links_has_target",
        ),
        sa.CheckConstraint(
            "(status = 'DELIVERED' AND planned_active_block_id IS NOT NULL "
            "AND delivered_recovery_minutes > 0 "
            "AND delivered_lesson_log_id IS NOT NULL AND delivered_at IS NOT NULL) OR "
            "(status <> 'DELIVERED' AND delivered_recovery_minutes = 0 "
            "AND delivered_lesson_log_id IS NULL AND delivered_at IS NULL)",
            name="ck_planned_recovery_links_delivery_evidence",
        ),
        sa.CheckConstraint(
            "debt_occurrence_revision > 0",
            name="ck_planned_recovery_links_debt_revision_positive",
        ),
        sa.ForeignKeyConstraint(["class_id"], ["class.id"]),
        sa.ForeignKeyConstraint(
            ["debt_occurrence_id", "organization_id", "debt_occurrence_revision"],
            [
                "lesson_occurrence.id", "lesson_occurrence.organization_id",
                "lesson_occurrence.revision",
            ],
            name="fk_planned_recovery_links_debt_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["delivered_lesson_log_id", "organization_id", "planned_active_block_id"],
            [
                "lesson_log.id", "lesson_log.organization_id",
                "lesson_log.active_schedule_block_id",
            ],
            name="fk_planned_recovery_links_delivery_evidence",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organization.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["planned_active_block_id", "organization_id", "school_year_id"],
            [
                "active_schedule_blocks.id", "active_schedule_blocks.organization_id",
                "active_schedule_blocks.school_year_id",
            ],
            name="fk_planned_recovery_links_active_block_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["planned_draft_block_id", "organization_id", "school_year_id"],
            [
                "schedule_draft_blocks.id", "schedule_draft_blocks.organization_id",
                "schedule_draft_blocks.school_year_id",
            ],
            name="fk_planned_recovery_links_draft_block_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["school_year_id"], ["scheduler_school_year.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["subject_id"], ["subject.id"]),
        sa.ForeignKeyConstraint(
            ["teacher_id"], ["teacher.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "planned_active_block_id", name="uq_planned_recovery_links_active_block"
        ),
        sa.UniqueConstraint(
            "planned_draft_block_id", name="uq_planned_recovery_links_draft_block"
        ),
        sa.UniqueConstraint(
            "delivered_lesson_log_id", name="uq_planned_recovery_links_delivery_log"
        ),
    )
    op.create_index(
        "ix_planned_recovery_links_organization_id", "planned_recovery_links",
        ["organization_id"],
    )
    op.create_index(
        "ix_planned_recovery_links_school_year_id", "planned_recovery_links",
        ["school_year_id"],
    )

    op.create_table(
        "scheduler_state_version_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("school_year_id", sa.Integer(), nullable=False),
        sa.Column("version_before", sa.Integer(), nullable=False),
        sa.Column("version_after", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.String(length=100), nullable=True),
        sa.Column("operation", state_change_operation, nullable=False),
        sa.Column("change_scope", state_change_scope, nullable=False),
        sa.Column("changed_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "changed_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("before_metadata_json", sa.JSON(), nullable=True),
        sa.Column("after_metadata_json", sa.JSON(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.CheckConstraint(
            "version_before >= 0 AND version_after >= 0",
            name="ck_scheduler_state_version_events_versions_nonnegative",
        ),
        sa.CheckConstraint(
            "(change_scope = 'FUTURE_IMPACTING' AND "
            "version_after = version_before + 1) OR "
            "(change_scope <> 'FUTURE_IMPACTING' AND version_after = version_before)",
            name="ck_scheduler_state_version_events_increment",
        ),
        sa.CheckConstraint(
            "length(trim(entity_type)) > 0",
            name="ck_scheduler_state_version_events_entity_type_nonempty",
        ),
        sa.ForeignKeyConstraint(
            ["changed_by_user_id"], ["user.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "school_year_id"],
            [
                "scheduler_school_year_state.organization_id",
                "scheduler_school_year_state.school_year_id",
            ],
            name="fk_scheduler_state_version_events_state_scope",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_scheduler_state_version_events_organization_id",
        "scheduler_state_version_events",
        ["organization_id"],
    )
    op.create_index(
        "ix_scheduler_state_version_events_school_year_id",
        "scheduler_state_version_events",
        ["school_year_id"],
    )
    if op.get_bind().dialect.name == "postgresql":
        op.create_index(
            "uq_scheduler_state_version_events_increment",
            "scheduler_state_version_events",
            ["organization_id", "school_year_id", "version_after"],
            unique=True,
            postgresql_where=sa.text("change_scope = 'FUTURE_IMPACTING'"),
        )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            INSERT INTO scheduler_school_year (
                organization_id,
                label,
                start_date,
                hard_end_date,
                timezone,
                is_active
            )
            SELECT
                organization_id,
                EXTRACT(YEAR FROM school_start_date)::int::text || '/' ||
                    EXTRACT(YEAR FROM school_hard_end_date)::int::text,
                school_start_date,
                school_hard_end_date,
                'Europe/Lisbon',
                TRUE
            FROM organization_settings
            WHERE school_start_date IS NOT NULL
              AND school_hard_end_date IS NOT NULL
            ON CONFLICT (organization_id, label) DO NOTHING
            """
        )
        op.execute(
            """
            INSERT INTO scheduler_school_year_state (
                organization_id,
                school_year_id,
                school_year_publication_state,
                scheduler_state_version,
                lock_version
            )
            SELECT organization_id, id, 'UNPUBLISHED', 0, 0
            FROM scheduler_school_year
            ON CONFLICT (organization_id, school_year_id) DO NOTHING
            """
        )

        same_tenant_refs = {
            "scheduler_school_year_state": {
                "reset_by_user_id": '"user"',
                "pending_draft_id": "schedule_drafts",
            },
            "schedule_generation_job": {"requested_by_user_id": '"user"'},
            "schedule_drafts": {
                "generation_job_id": "schedule_generation_job",
                "created_by_user_id": '"user"',
                "decided_by_user_id": '"user"',
            },
            "schedule_draft_blocks": {
                "draft_id": "schedule_drafts",
                "source_active_block_id": "active_schedule_blocks",
                "class_id": '"class"',
                "subject_id": "subject",
                "teacher_id": "teacher",
                "room_id": "room",
                "timeslot_id": "timeslot",
                "recovery_source_occurrence_id": "lesson_occurrence",
            },
            "schedule_diff_entries": {
                "generation_job_id": "schedule_generation_job",
                "draft_id": "schedule_drafts",
                "class_id": '"class"',
                "subject_id": "subject",
                "teacher_id": "teacher",
                "before_active_block_id": "active_schedule_blocks",
                "after_draft_block_id": "schedule_draft_blocks",
                "before_timeslot_id": "timeslot",
                "before_room_id": "room",
                "after_timeslot_id": "timeslot",
                "after_room_id": "room",
            },
            "active_schedule_blocks": {
                "source_draft_block_id": "schedule_draft_blocks",
                "class_id": '"class"',
                "subject_id": "subject",
                "teacher_id": "teacher",
                "room_id": "room",
                "timeslot_id": "timeslot",
            },
            "planned_recovery_links": {
                "debt_occurrence_id": "lesson_occurrence",
                "planned_active_block_id": "active_schedule_blocks",
                "planned_draft_block_id": "schedule_draft_blocks",
                "delivered_lesson_log_id": "lesson_log",
                "class_id": '"class"',
                "subject_id": "subject",
                "teacher_id": "teacher",
            },
            "scheduler_state_version_events": {
                "changed_by_user_id": '"user"',
            },
            "lesson_log": {
                "schedule_output_id": "schedule_output",
                "operational_block_id": "operational_schedule_block",
                "active_schedule_block_id": "active_schedule_blocks",
                "logged_by_user_id": '"user"',
            },
        }
        for table, refs in same_tenant_refs.items():
            _create_same_tenant_trigger(table, refs)

        for table in NEW_TENANT_TABLES:
            quoted_table = _quoted_identifier(table)
            op.execute(f"ALTER TABLE public.{quoted_table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE public.{quoted_table} FORCE ROW LEVEL SECURITY")
            op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON public.{quoted_table}")
            op.execute(
                f"CREATE POLICY tenant_isolation ON public.{quoted_table} "
                "USING (organization_id = app_security.current_organization_id()) "
                "WITH CHECK (organization_id = app_security.current_organization_id())"
            )
            op.execute(
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON public.{quoted_table} TO cronos_app"
            )

        op.execute(
            "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO cronos_app"
        )
        for append_only_table in (
            "schedule_draft_blocks",
            "schedule_diff_entries",
            "scheduler_state_version_events",
        ):
            op.execute(
                f"REVOKE UPDATE, DELETE ON public."
                f"{_quoted_identifier(append_only_table)} FROM cronos_app"
            )

    op.drop_column("organization_settings", "school_target_end_date")


def downgrade() -> None:
    op.add_column(
        "organization_settings",
        sa.Column("school_target_end_date", sa.Date(), nullable=True),
    )
    if op.get_bind().dialect.name == "postgresql":
        for table in (*NEW_TENANT_TABLES, "lesson_log"):
            _drop_same_tenant_trigger(table)
        _create_same_tenant_trigger(
            "lesson_log",
            {
                "schedule_output_id": "schedule_output",
                "operational_block_id": "operational_schedule_block",
            },
        )
        for table in NEW_TENANT_TABLES:
            quoted_table = _quoted_identifier(table)
            op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON public.{quoted_table}")
            op.execute(f"ALTER TABLE public.{quoted_table} DISABLE ROW LEVEL SECURITY")
    if op.get_bind().dialect.name == "postgresql":
        op.drop_index(
            "uq_scheduler_state_version_events_increment",
            table_name="scheduler_state_version_events",
        )
    op.drop_index(
        "ix_scheduler_state_version_events_school_year_id",
        table_name="scheduler_state_version_events",
    )
    op.drop_index(
        "ix_scheduler_state_version_events_organization_id",
        table_name="scheduler_state_version_events",
    )
    op.drop_table("scheduler_state_version_events")
    op.drop_index(
        "ix_planned_recovery_links_school_year_id", table_name="planned_recovery_links"
    )
    op.drop_index(
        "ix_planned_recovery_links_organization_id", table_name="planned_recovery_links"
    )
    op.drop_table("planned_recovery_links")
    op.drop_index(
        "ix_lesson_log_active_schedule_block_id", table_name="lesson_log"
    )
    op.drop_constraint("ck_lesson_log_exactly_one_target", "lesson_log", type_="check")
    op.drop_constraint(
        "uq_lesson_log_id_org_active_block", "lesson_log", type_="unique"
    )
    op.drop_constraint(
        "uq_lesson_log_active_schedule_block", "lesson_log", type_="unique"
    )
    op.drop_constraint(
        "fk_lesson_log_active_schedule_block", "lesson_log", type_="foreignkey"
    )
    op.drop_column("lesson_log", "active_schedule_block_id")
    op.create_check_constraint(
        "ck_lesson_log_exactly_one_target",
        "lesson_log",
        "(schedule_output_id IS NOT NULL AND operational_block_id IS NULL) OR "
        "(schedule_output_id IS NULL AND operational_block_id IS NOT NULL)",
    )
    if op.get_bind().dialect.name == "postgresql":
        op.drop_index("uq_active_schedule_blocks_room_slot", table_name="active_schedule_blocks")
        op.drop_index("uq_active_schedule_blocks_teacher_slot", table_name="active_schedule_blocks")
        op.drop_index("uq_active_schedule_blocks_class_slot", table_name="active_schedule_blocks")
    op.drop_constraint(
        "fk_schedule_diff_entries_before_active",
        "schedule_diff_entries",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_schedule_draft_blocks_source_active",
        "schedule_draft_blocks",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_active_schedule_blocks_schedule_version_id", table_name="active_schedule_blocks"
    )
    op.drop_index(
        "ix_active_schedule_blocks_school_year_id", table_name="active_schedule_blocks"
    )
    op.drop_index(
        "ix_active_schedule_blocks_organization_id", table_name="active_schedule_blocks"
    )
    op.drop_table("active_schedule_blocks")
    op.drop_index("ix_schedule_diff_entries_draft_id", table_name="schedule_diff_entries")
    op.drop_index(
        "ix_schedule_diff_entries_school_year_id", table_name="schedule_diff_entries"
    )
    op.drop_index(
        "ix_schedule_diff_entries_organization_id", table_name="schedule_diff_entries"
    )
    op.drop_table("schedule_diff_entries")
    op.drop_index("ix_schedule_draft_blocks_draft_id", table_name="schedule_draft_blocks")
    op.drop_index(
        "ix_schedule_draft_blocks_school_year_id", table_name="schedule_draft_blocks"
    )
    op.drop_index(
        "ix_schedule_draft_blocks_organization_id", table_name="schedule_draft_blocks"
    )
    op.drop_table("schedule_draft_blocks")
    op.drop_constraint(
        "fk_scheduler_school_year_state_pending_draft_scope",
        "scheduler_school_year_state",
        type_="foreignkey",
    )
    op.drop_column("scheduler_school_year_state", "pending_draft_id")
    if op.get_bind().dialect.name == "postgresql":
        op.drop_index("uq_schedule_drafts_pending_year", table_name="schedule_drafts")
    op.drop_index("ix_schedule_drafts_school_year_id", table_name="schedule_drafts")
    op.drop_index("ix_schedule_drafts_organization_id", table_name="schedule_drafts")
    op.drop_table("schedule_drafts")
    if op.get_bind().dialect.name == "postgresql":
        op.drop_index(
            "uq_schedule_generation_job_active_year",
            table_name="schedule_generation_job",
        )
    op.drop_index(
        "ix_schedule_generation_job_school_year_id",
        table_name="schedule_generation_job",
    )
    op.drop_index(
        "ix_schedule_generation_job_organization_id",
        table_name="schedule_generation_job",
    )
    op.drop_table("schedule_generation_job")
    op.drop_index(
        "ix_scheduler_school_year_state_school_year_id",
        table_name="scheduler_school_year_state",
    )
    op.drop_index(
        "ix_scheduler_school_year_state_organization_id",
        table_name="scheduler_school_year_state",
    )
    op.drop_table("scheduler_school_year_state")
    op.drop_index(
        "ix_scheduler_school_year_organization_id",
        table_name="scheduler_school_year",
    )
    if op.get_bind().dialect.name == "postgresql":
        op.drop_index(
            "uq_scheduler_school_year_active_org",
            table_name="scheduler_school_year",
        )
    op.drop_table("scheduler_school_year")
    generation_result_category.drop(op.get_bind(), checkfirst=True)
    draft_state.drop(op.get_bind(), checkfirst=True)
    draft_block_change_type.drop(op.get_bind(), checkfirst=True)
    diff_scope.drop(op.get_bind(), checkfirst=True)
    diff_change_type.drop(op.get_bind(), checkfirst=True)
    recovery_link_status.drop(op.get_bind(), checkfirst=True)
    active_block_status.drop(op.get_bind(), checkfirst=True)
    state_change_scope.drop(op.get_bind(), checkfirst=True)
    state_change_operation.drop(op.get_bind(), checkfirst=True)
    op.drop_constraint(
        "uq_lesson_occurrence_id_org_revision",
        "lesson_occurrence",
        type_="unique",
    )
    generation_job_status.drop(op.get_bind(), checkfirst=True)
    generation_trigger.drop(op.get_bind(), checkfirst=True)
    generation_strategy.drop(op.get_bind(), checkfirst=True)
    publication_state.drop(op.get_bind(), checkfirst=True)
