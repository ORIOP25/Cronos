"""Repair tenant-ref trigger functions.

Revision ID: 20260706_repair_tenant_refs
Revises: 20260705_beta_baseline
Create Date: 2026-07-06
"""

from typing import Mapping, Sequence, Union

from alembic import op
from sqlalchemy import MetaData

from app.db.database import Base
from app import models  # noqa: F401 - registers SQLAlchemy metadata


revision: str = "20260706_repair_tenant_refs"
down_revision: Union[str, None] = "20260705_beta_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SAME_TENANT_REFS = {
    "availability": {"teacher_id": "teacher", "timeslot_id": "timeslot"},
    "course_subject_link": {"course_id": "course", "subject_id": "subject"},
    "teacher_subject_link": {"teacher_id": "teacher", "subject_id": "subject"},
    "class_subject_link": {"class_id": '"class"', "subject_id": "subject", "teacher_id": "teacher"},
    "module": {"subject_id": "subject"},
    "class_progress": {"class_id": '"class"', "module_id": "module"},
    "lesson": {"class_id": '"class"', "subject_id": "subject", "teacher_id": "teacher"},
    "schedule_output": {"lesson_id": "lesson", "timeslot_id": "timeslot", "room_id": "room"},
    "teacher_weekly_timesheet": {"teacher_id": "teacher"},
    "lesson_occurrence": {
        "schedule_output_id": "schedule_output",
        "class_id": '"class"',
        "subject_id": "subject",
        "planned_teacher_id": "teacher",
        "executed_teacher_id": "teacher",
        "substitute_teacher_id": "teacher",
        "substitute_subject_id": "subject",
        "planned_module_id": "module",
        "executed_module_id": "module",
        "planned_timeslot_id": "timeslot",
        "planned_room_id": "room",
        "created_by_user_id": '"user"',
        "decided_by_user_id": '"user"',
        "revoked_by_user_id": '"user"',
    },
    "operational_schedule_block": {
        "source_occurrence_id": "lesson_occurrence",
        "planned_schedule_output_id": "schedule_output",
        "class_id": '"class"',
        "subject_id": "subject",
        "module_id": "module",
        "teacher_id": "teacher",
        "timeslot_id": "timeslot",
        "room_id": "room",
        "created_by_user_id": '"user"',
    },
    "progress_ledger_entry": {"class_id": '"class"', "module_id": "module"},
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
        "class_id": '"class"',
        "subject_id": "subject",
        "teacher_id": "teacher",
        "timeslot_id": "timeslot",
        "room_id": "room",
        "source_active_block_id": "active_schedule_blocks",
        "recovery_source_occurrence_id": "lesson_occurrence",
    },
    "schedule_diff_entries": {
        "draft_id": "schedule_drafts",
        "class_id": '"class"',
        "subject_id": "subject",
        "teacher_id": "teacher",
        "before_room_id": "room",
        "after_room_id": "room",
        "before_timeslot_id": "timeslot",
        "after_timeslot_id": "timeslot",
    },
    "active_schedule_blocks": {
        "source_draft_block_id": "schedule_draft_blocks",
        "class_id": '"class"',
        "subject_id": "subject",
        "teacher_id": "teacher",
        "timeslot_id": "timeslot",
        "room_id": "room",
    },
    "planned_recovery_links": {
        "debt_occurrence_id": "lesson_occurrence",
        "planned_active_block_id": "active_schedule_blocks",
        "planned_draft_block_id": "schedule_draft_blocks",
    },
    "scheduler_state_version_events": {
        "school_year_id": "scheduler_school_year",
        "changed_by_user_id": '"user"',
    },
    "lesson_log": {
        "schedule_output_id": "schedule_output",
        "operational_block_id": "operational_schedule_block",
        "active_schedule_block_id": "active_schedule_blocks",
        "logged_by_user_id": '"user"',
    },
}


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _q(identifier: str) -> str:
    if identifier.startswith('"') and identifier.endswith('"'):
        return identifier
    return f'"{identifier}"'


def _normalize_table_name(identifier: str) -> str:
    if identifier.startswith('"') and identifier.endswith('"'):
        return identifier[1:-1].replace('""', '"')
    return identifier


def _tenant_ref_contract_errors(
    refs: Mapping[str, Mapping[str, str]] | None = None,
    metadata: MetaData | None = None,
) -> list[str]:
    refs = SAME_TENANT_REFS if refs is None else refs
    metadata = Base.metadata if metadata is None else metadata
    tables = metadata.tables
    errors: list[str] = []

    for table, local_refs in refs.items():
        table_name = _normalize_table_name(table)
        table_obj = tables.get(table_name)
        if table_obj is None:
            errors.append(
                f"SAME_TENANT_REFS references missing local table public.{table_name}"
            )
            continue

        local_columns = set(table_obj.c.keys())
        for column, ref_table in local_refs.items():
            if column not in local_columns:
                errors.append(
                    f"SAME_TENANT_REFS[{table_name}].{column} is not a column on public.{table_name}"
                )

            ref_table_name = _normalize_table_name(ref_table)
            ref_table_obj = tables.get(ref_table_name)
            if ref_table_obj is None:
                errors.append(
                    f"SAME_TENANT_REFS[{table_name}].{column} references missing table public.{ref_table_name}"
                )
                continue

            ref_columns = set(ref_table_obj.c.keys())
            if "id" not in ref_columns:
                errors.append(
                    f"SAME_TENANT_REFS[{table_name}].{column} references public.{ref_table_name} without an id column"
                )
            if ref_table_name != "organization" and "organization_id" not in ref_columns:
                errors.append(
                    f"SAME_TENANT_REFS[{table_name}].{column} references public.{ref_table_name} without an organization_id column"
                )

    return errors


def _validate_same_tenant_refs() -> None:
    errors = _tenant_ref_contract_errors()
    if errors:
        detail = "\n- ".join(errors)
        raise RuntimeError(f"Invalid SAME_TENANT_REFS contract:\n- {detail}")


def _create_same_tenant_trigger(table: str, refs: dict[str, str]) -> None:
    checks = []
    for column, ref_table in refs.items():
        checks.append(
            f"""
            IF NEW.{_q(column)} IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM public.{_q(ref_table)} ref
                WHERE ref.id = NEW.{_q(column)}
                  AND ref.organization_id = NEW.organization_id
            ) THEN
                RAISE EXCEPTION 'Tenant mismatch for {table}.{column}';
            END IF;
            """
        )
    body = "\n".join(checks)
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION app_security.validate_{table}_tenant_refs()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        BEGIN
            {body}
            RETURN NEW;
        END;
        $$;

        DROP TRIGGER IF EXISTS trg_{table}_tenant_refs ON public.{_q(table)};
        CREATE TRIGGER trg_{table}_tenant_refs
        BEFORE INSERT OR UPDATE ON public.{_q(table)}
        FOR EACH ROW
        EXECUTE FUNCTION app_security.validate_{table}_tenant_refs();
        """
    )


def upgrade() -> None:
    if not _is_postgresql():
        return

    _validate_same_tenant_refs()
    op.execute("CREATE SCHEMA IF NOT EXISTS app_security")
    for table, refs in SAME_TENANT_REFS.items():
        _create_same_tenant_trigger(table, refs)


def downgrade() -> None:
    pass
