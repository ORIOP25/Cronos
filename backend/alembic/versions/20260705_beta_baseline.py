"""Beta baseline schema.

Revision ID: 20260705_beta_baseline
Revises:
Create Date: 2026-07-05
"""

from typing import Mapping, Sequence, Union

from alembic import op
from sqlalchemy import MetaData

from app.db.database import Base
from app import models  # noqa: F401 - registers SQLAlchemy metadata


revision: str = "20260705_beta_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TENANT_TABLES = (
    "active_schedule_blocks",
    "availability",
    "class",
    "class_progress",
    "class_subject_link",
    "constraint",
    "course",
    "course_subject_link",
    "lesson",
    "lesson_log",
    "lesson_occurrence",
    "member_access_operation",
    "module",
    "occurrence_operational_event",
    "operational_schedule_block",
    "organization_grid_settings",
    "organization_membership",
    "organization_settings",
    "planned_recovery_links",
    "progress_ledger_entry",
    "room",
    "schedule_diff_entries",
    "schedule_draft_blocks",
    "schedule_drafts",
    "schedule_generation_job",
    "schedule_output",
    "scheduler_school_year",
    "scheduler_school_year_state",
    "scheduler_state_version_events",
    "school_calendar_event",
    "subject",
    "substitutions",
    "teacher",
    "teacher_endpoint_operational_event",
    "teacher_subject_link",
    "teacher_weekly_timesheet",
    "timeslot",
    "user",
)


APPEND_ONLY_TABLES = (
    "schedule_draft_blocks",
    "schedule_diff_entries",
    "scheduler_state_version_events",
)


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


def _install_security_objects() -> None:
    _validate_same_tenant_refs()
    op.execute("CREATE SCHEMA IF NOT EXISTS app_security")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cronos_auth_definer') THEN
                CREATE ROLE cronos_auth_definer NOLOGIN BYPASSRLS;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cronos_app') THEN
                CREATE ROLE cronos_app NOLOGIN;
            END IF;
        END
        $$;
        GRANT cronos_app TO CURRENT_USER;
        GRANT USAGE ON SCHEMA public, app_security TO cronos_app;
        GRANT USAGE ON SCHEMA public, app_security TO cronos_auth_definer;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO cronos_app;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
            GRANT USAGE, SELECT ON SEQUENCES TO cronos_app;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
            GRANT USAGE, SELECT ON SEQUENCES TO cronos_auth_definer;
        DO $grant_tables$
        DECLARE
            table_name text;
        BEGIN
            FOR table_name IN
                SELECT c.relname
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public'
                  AND c.relkind IN ('r', 'p')
                  AND c.relname <> 'alembic_version'
            LOOP
                EXECUTE format(
                    'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.%I TO cronos_app',
                    table_name
                );
            END LOOP;
        END
        $grant_tables$;
        REVOKE ALL ON public.alembic_version FROM cronos_app;
        GRANT SELECT, INSERT, UPDATE ON
            public.organization,
            public."user",
            public.organization_membership
        TO cronos_auth_definer;
        GRANT SELECT, INSERT, UPDATE, DELETE ON
            public.organization_membership_capability
        TO cronos_auth_definer;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO cronos_auth_definer;
        """
    )
    for table in APPEND_ONLY_TABLES:
        op.execute(f"REVOKE UPDATE, DELETE ON public.{_q(table)} FROM cronos_app")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app_security.current_organization_id()
        RETURNS integer
        LANGUAGE plpgsql
        STABLE
        SET search_path = pg_catalog
        AS $$
        DECLARE
            raw_value text := current_setting('app.current_organization_id', true);
            parsed_value bigint;
        BEGIN
            IF raw_value IS NULL OR raw_value !~ '^[0-9]{1,10}$' THEN
                RETURN NULL;
            END IF;

            parsed_value := raw_value::bigint;
            IF parsed_value < 1 OR parsed_value > 2147483647 THEN
                RETURN NULL;
            END IF;

            RETURN parsed_value::integer;
        EXCEPTION
            WHEN invalid_text_representation OR numeric_value_out_of_range THEN
                RETURN NULL;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app_security.resolve_auth_context(
            clerk_user_id text,
            clerk_org_id text
        )
        RETURNS TABLE(user_id integer, organization_id integer, role text, is_active boolean)
        LANGUAGE sql
        SECURITY DEFINER
        STABLE
        SET search_path = pg_catalog, public
        AS $$
            SELECT
                u.id,
                om.organization_id,
                CASE
                    WHEN EXISTS (
                        SELECT 1
                        FROM public.organization_membership_capability omc
                        WHERE omc.organization_membership_id = om.id
                          AND omc.capability = 'admin'
                    ) THEN 'admin'
                    WHEN EXISTS (
                        SELECT 1
                        FROM public.organization_membership_capability omc
                        WHERE omc.organization_membership_id = om.id
                          AND omc.capability = 'teacher'
                    ) THEN 'teacher'
                    ELSE NULL
                END,
                coalesce(u.is_active, false)
            FROM public.organization_membership om
            JOIN public."user" u ON u.id = om.account_id
            JOIN public.organization o ON o.id = om.organization_id
            WHERE resolve_auth_context.clerk_user_id IS NOT NULL
              AND resolve_auth_context.clerk_org_id IS NOT NULL
              AND length(resolve_auth_context.clerk_user_id) BETWEEN 1 AND 255
              AND length(resolve_auth_context.clerk_org_id) BETWEEN 1 AND 255
              AND u.clerk_user_id = resolve_auth_context.clerk_user_id
              AND o.clerk_org_id = resolve_auth_context.clerk_org_id
              AND u.is_active = true
              AND om.lifecycle_status = 'active'
              AND om.access_status = 'active'
            LIMIT 1;
        $$;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app_security.ensure_organization(
            p_clerk_org_id text,
            p_org_name text
        )
        RETURNS TABLE(id integer)
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        BEGIN
            IF p_clerk_org_id IS NULL OR length(p_clerk_org_id) NOT BETWEEN 1 AND 255 THEN
                RAISE EXCEPTION 'clerk_org_id is required';
            END IF;

            INSERT INTO public.organization (name, clerk_org_id, plan_status)
            VALUES (coalesce(nullif(p_org_name, ''), 'Organizacao'), p_clerk_org_id, 'active')
            ON CONFLICT (clerk_org_id) DO NOTHING
            RETURNING public.organization.id INTO id;

            IF id IS NULL THEN
                UPDATE public.organization
                SET name = coalesce(nullif(p_org_name, ''), public.organization.name),
                    plan_status = 'active'
                WHERE public.organization.clerk_org_id = p_clerk_org_id
                  AND (
                    public.organization.name IS DISTINCT FROM coalesce(nullif(p_org_name, ''), public.organization.name)
                    OR public.organization.plan_status IS DISTINCT FROM 'active'
                  )
                RETURNING public.organization.id INTO id;
            END IF;

            IF id IS NULL THEN
                SELECT public.organization.id
                INTO id
                FROM public.organization
                WHERE public.organization.clerk_org_id = p_clerk_org_id;
            END IF;

            RETURN NEXT;
        END;
        $$;

        CREATE OR REPLACE FUNCTION app_security.ensure_user(
            p_clerk_user_id text,
            p_email text,
            p_display_name text,
            p_app_role text,
            p_organization_id integer,
            p_teacher_id integer
        )
        RETURNS TABLE(id integer, organization_id integer)
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            normalized_clerk_user_id text := nullif(btrim(p_clerk_user_id), '');
            normalized_email text := lower(nullif(btrim(p_email), ''));
            normalized_display_name text := nullif(btrim(p_display_name), '');
            parsed_role public.userrole;
            desired_capability public.membershipcapability;
            desired_clerk_role public.clerkorganizationrole;
            desired_teacher_mode public.teacheraccessmode;
            conflicting_user_id integer;
            ensured_user_id integer;
            ensured_organization_id integer;
            ensured_membership_id integer;
        BEGIN
            IF normalized_clerk_user_id IS NULL OR length(normalized_clerk_user_id) > 255 THEN
                RAISE EXCEPTION 'clerk_user_id is required';
            END IF;
            IF normalized_email IS NULL THEN
                RAISE EXCEPTION 'email is required';
            END IF;
            IF p_organization_id IS NULL OR NOT EXISTS (
                SELECT 1 FROM public.organization WHERE public.organization.id = p_organization_id
            ) THEN
                RAISE EXCEPTION 'organization_id is required';
            END IF;

            CASE coalesce(nullif(p_app_role, ''), '')
                WHEN 'admin' THEN
                    parsed_role := 'admin'::public.userrole;
                    desired_capability := 'admin'::public.membershipcapability;
                    desired_clerk_role := 'org:admin'::public.clerkorganizationrole;
                    desired_teacher_mode := NULL;
                WHEN 'org:admin' THEN
                    parsed_role := 'admin'::public.userrole;
                    desired_capability := 'admin'::public.membershipcapability;
                    desired_clerk_role := 'org:admin'::public.clerkorganizationrole;
                    desired_teacher_mode := NULL;
                WHEN 'member' THEN
                    parsed_role := 'teacher'::public.userrole;
                    desired_capability := 'teacher'::public.membershipcapability;
                    desired_clerk_role := 'org:member'::public.clerkorganizationrole;
                    desired_teacher_mode := 'platform'::public.teacheraccessmode;
                WHEN 'teacher' THEN
                    parsed_role := 'teacher'::public.userrole;
                    desired_capability := 'teacher'::public.membershipcapability;
                    desired_clerk_role := 'org:member'::public.clerkorganizationrole;
                    desired_teacher_mode := 'platform'::public.teacheraccessmode;
                WHEN 'org:member' THEN
                    parsed_role := 'teacher'::public.userrole;
                    desired_capability := 'teacher'::public.membershipcapability;
                    desired_clerk_role := 'org:member'::public.clerkorganizationrole;
                    desired_teacher_mode := 'platform'::public.teacheraccessmode;
                ELSE
                    RAISE EXCEPTION 'unsupported app_role';
            END CASE;

            SELECT public."user".id, public."user".organization_id
            INTO ensured_user_id, ensured_organization_id
            FROM public."user"
            WHERE public."user".clerk_user_id = normalized_clerk_user_id;

            SELECT public."user".id
            INTO conflicting_user_id
            FROM public."user"
            WHERE lower(public."user".email) = normalized_email
              AND (ensured_user_id IS NULL OR public."user".id <> ensured_user_id)
            LIMIT 1;

            IF conflicting_user_id IS NOT NULL THEN
                RAISE EXCEPTION 'email is already linked to a different user';
            END IF;

            IF ensured_user_id IS NULL THEN
                INSERT INTO public."user" (
                    email,
                    name,
                    role,
                    teacher_id,
                    organization_id,
                    clerk_user_id,
                    clerk_profile_name,
                    is_active,
                    is_superuser,
                    last_clerk_sync_at,
                    created_at,
                    updated_at
                )
                VALUES (
                    normalized_email,
                    coalesce(normalized_display_name, normalized_email),
                    parsed_role,
                    p_teacher_id,
                    p_organization_id,
                    normalized_clerk_user_id,
                    normalized_display_name,
                    true,
                    false,
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP
                )
                RETURNING public."user".id, public."user".organization_id
                INTO ensured_user_id, ensured_organization_id;
            ELSE
                UPDATE public."user"
                SET email = normalized_email,
                    name = coalesce(normalized_display_name, public."user".name, normalized_email),
                    role = parsed_role,
                    teacher_id = p_teacher_id,
                    organization_id = p_organization_id,
                    clerk_profile_name = coalesce(normalized_display_name, public."user".clerk_profile_name),
                    is_active = true,
                    last_clerk_sync_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE public."user".id = ensured_user_id
                RETURNING public."user".id, public."user".organization_id
                INTO ensured_user_id, ensured_organization_id;
            END IF;

            INSERT INTO public.organization_membership (
                organization_id,
                account_id,
                organization_display_name,
                lifecycle_status,
                access_status,
                teacher_access_mode,
                expected_clerk_role,
                lock_version,
                created_at,
                updated_at
            )
            VALUES (
                p_organization_id,
                ensured_user_id,
                coalesce(normalized_display_name, normalized_email),
                'active',
                'active',
                desired_teacher_mode,
                desired_clerk_role,
                1,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            )
            ON CONFLICT ON CONSTRAINT uq_org_membership_account DO UPDATE
            SET organization_display_name = EXCLUDED.organization_display_name,
                lifecycle_status = 'active',
                access_status = 'active',
                teacher_access_mode = EXCLUDED.teacher_access_mode,
                expected_clerk_role = EXCLUDED.expected_clerk_role,
                updated_at = CURRENT_TIMESTAMP
            RETURNING public.organization_membership.id
            INTO ensured_membership_id;

            DELETE FROM public.organization_membership_capability
            WHERE organization_membership_id = ensured_membership_id
              AND capability <> desired_capability;

            INSERT INTO public.organization_membership_capability (
                organization_membership_id,
                capability
            )
            VALUES (ensured_membership_id, desired_capability)
            ON CONFLICT DO NOTHING;

            id := ensured_user_id;
            organization_id := ensured_organization_id;
            RETURN NEXT;
        END;
        $$;

        CREATE OR REPLACE FUNCTION app_security.update_user_profile(
            p_clerk_user_id text,
            p_email text,
            p_display_name text,
            p_app_role text,
            p_teacher_id integer
        )
        RETURNS TABLE(id integer, organization_id integer)
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            parsed_role public.userrole := (
                CASE coalesce(nullif(p_app_role, ''), '')
                    WHEN 'admin' THEN 'admin'
                    WHEN 'org:admin' THEN 'admin'
                    WHEN 'teacher' THEN 'teacher'
                    WHEN 'member' THEN 'teacher'
                    WHEN 'org:member' THEN 'teacher'
                    ELSE NULL
                END
            )::public.userrole;
        BEGIN
            UPDATE public."user"
            SET email = coalesce(p_email, public."user".email),
                name = coalesce(p_display_name, public."user".name),
                role = coalesce(parsed_role, public."user".role),
                teacher_id = coalesce(p_teacher_id, public."user".teacher_id),
                clerk_profile_name = coalesce(p_display_name, public."user".clerk_profile_name),
                last_clerk_sync_at = CURRENT_TIMESTAMP
            WHERE public."user".clerk_user_id = p_clerk_user_id
              AND (
                public."user".email IS DISTINCT FROM coalesce(p_email, public."user".email)
                OR public."user".name IS DISTINCT FROM coalesce(p_display_name, public."user".name)
                OR public."user".role IS DISTINCT FROM coalesce(parsed_role, public."user".role)
                OR public."user".teacher_id IS DISTINCT FROM coalesce(p_teacher_id, public."user".teacher_id)
                OR public."user".clerk_profile_name IS DISTINCT FROM coalesce(p_display_name, public."user".clerk_profile_name)
              )
            RETURNING public."user".id, public."user".organization_id
            INTO id, organization_id;

            IF id IS NULL THEN
                SELECT public."user".id, public."user".organization_id
                INTO id, organization_id
                FROM public."user"
                WHERE public."user".clerk_user_id = p_clerk_user_id;
            END IF;

            IF id IS NOT NULL THEN
                RETURN NEXT;
            END IF;
        END;
        $$;

        CREATE OR REPLACE FUNCTION app_security.deactivate_organization(p_clerk_org_id text)
        RETURNS boolean
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            affected_count integer;
        BEGIN
            UPDATE public.organization
            SET plan_status = 'inactive'
            WHERE public.organization.clerk_org_id = p_clerk_org_id
              AND public.organization.plan_status IS DISTINCT FROM 'inactive';
            GET DIAGNOSTICS affected_count = ROW_COUNT;
            RETURN affected_count > 0;
        END;
        $$;

        CREATE OR REPLACE FUNCTION app_security.deactivate_user(p_clerk_user_id text)
        RETURNS boolean
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            target_user_id integer;
            target_is_superuser boolean;
            affected_count integer;
        BEGIN
            SELECT public."user".id, public."user".is_superuser
            INTO target_user_id, target_is_superuser
            FROM public."user"
            WHERE public."user".clerk_user_id = p_clerk_user_id;

            IF target_user_id IS NULL OR target_is_superuser THEN
                RETURN false;
            END IF;

            IF EXISTS (
                SELECT 1
                FROM public.organization_membership om
                JOIN public.organization_membership_capability omc
                  ON omc.organization_membership_id = om.id
                 AND omc.capability = 'admin'
                WHERE om.account_id = target_user_id
                  AND om.lifecycle_status = 'active'
                  AND om.access_status = 'active'
                  AND NOT EXISTS (
                    SELECT 1
                    FROM public.organization_membership other_om
                    JOIN public.organization_membership_capability other_omc
                      ON other_omc.organization_membership_id = other_om.id
                     AND other_omc.capability = 'admin'
                    JOIN public."user" other_user
                      ON other_user.id = other_om.account_id
                    WHERE other_om.organization_id = om.organization_id
                      AND other_om.lifecycle_status = 'active'
                      AND other_om.access_status = 'active'
                      AND other_user.is_active = true
                      AND other_user.id <> target_user_id
                  )
            ) THEN
                RETURN false;
            END IF;

            UPDATE public."user"
            SET is_active = false
            WHERE public."user".id = target_user_id
              AND public."user".is_active = true
              AND public."user".is_superuser = false;
            GET DIAGNOSTICS affected_count = ROW_COUNT;
            RETURN affected_count > 0;
        END;
        $$;
        """
    )
    op.execute(
        """
        REVOKE ALL ON FUNCTION app_security.current_organization_id() FROM PUBLIC;
        REVOKE ALL ON FUNCTION app_security.resolve_auth_context(text, text) FROM PUBLIC;
        REVOKE ALL ON FUNCTION app_security.ensure_organization(text, text) FROM PUBLIC;
        REVOKE ALL ON FUNCTION app_security.ensure_user(text, text, text, text, integer, integer) FROM PUBLIC;
        REVOKE ALL ON FUNCTION app_security.update_user_profile(text, text, text, text, integer) FROM PUBLIC;
        REVOKE ALL ON FUNCTION app_security.deactivate_organization(text) FROM PUBLIC;
        REVOKE ALL ON FUNCTION app_security.deactivate_user(text) FROM PUBLIC;
        ALTER FUNCTION app_security.resolve_auth_context(text, text) OWNER TO cronos_auth_definer;
        ALTER FUNCTION app_security.ensure_organization(text, text) OWNER TO cronos_auth_definer;
        ALTER FUNCTION app_security.ensure_user(text, text, text, text, integer, integer) OWNER TO cronos_auth_definer;
        ALTER FUNCTION app_security.update_user_profile(text, text, text, text, integer) OWNER TO cronos_auth_definer;
        ALTER FUNCTION app_security.deactivate_organization(text) OWNER TO cronos_auth_definer;
        ALTER FUNCTION app_security.deactivate_user(text) OWNER TO cronos_auth_definer;
        GRANT EXECUTE ON FUNCTION app_security.current_organization_id() TO cronos_app;
        GRANT EXECUTE ON FUNCTION app_security.resolve_auth_context(text, text) TO cronos_app;
        GRANT EXECUTE ON FUNCTION app_security.ensure_organization(text, text) TO cronos_app;
        GRANT EXECUTE ON FUNCTION app_security.ensure_user(text, text, text, text, integer, integer) TO cronos_app;
        GRANT EXECUTE ON FUNCTION app_security.update_user_profile(text, text, text, text, integer) TO cronos_app;
        GRANT EXECUTE ON FUNCTION app_security.deactivate_organization(text) TO cronos_app;
        GRANT EXECUTE ON FUNCTION app_security.deactivate_user(text) TO cronos_app;
        """
    )
    for table, refs in SAME_TENANT_REFS.items():
        _create_same_tenant_trigger(table, refs)

    op.execute("ALTER TABLE public.organization ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.organization FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON public.organization")
    op.execute(
        "CREATE POLICY tenant_isolation ON public.organization "
        "USING (id = app_security.current_organization_id()) "
        "WITH CHECK (id = app_security.current_organization_id())"
    )
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE public.{_q(table)} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE public.{_q(table)} FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON public.{_q(table)}")
        op.execute(
            f"CREATE POLICY tenant_isolation ON public.{_q(table)} "
            "USING (organization_id = app_security.current_organization_id()) "
            "WITH CHECK (organization_id = app_security.current_organization_id())"
        )


def _drop_security_objects() -> None:
    for table in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON public.{_q(table)}")
        op.execute(f"ALTER TABLE public.{_q(table)} DISABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON public.organization")
    op.execute("ALTER TABLE public.organization DISABLE ROW LEVEL SECURITY")
    for table in SAME_TENANT_REFS:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_tenant_refs ON public.{_q(table)}")
        op.execute(f"DROP FUNCTION IF EXISTS app_security.validate_{table}_tenant_refs()")
    op.execute("DROP FUNCTION IF EXISTS app_security.deactivate_user(text)")
    op.execute("DROP FUNCTION IF EXISTS app_security.deactivate_organization(text)")
    op.execute("DROP FUNCTION IF EXISTS app_security.update_user_profile(text, text, text, text, integer)")
    op.execute("DROP FUNCTION IF EXISTS app_security.ensure_user(text, text, text, text, integer, integer)")
    op.execute("DROP FUNCTION IF EXISTS app_security.ensure_organization(text, text)")
    op.execute("DROP FUNCTION IF EXISTS app_security.resolve_auth_context(text, text)")
    op.execute("DROP FUNCTION IF EXISTS app_security.current_organization_id()")
    op.execute("DROP SCHEMA IF EXISTS app_security")


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    if _is_postgresql():
        _install_security_objects()


def downgrade() -> None:
    bind = op.get_bind()
    if _is_postgresql():
        _drop_security_objects()
    Base.metadata.drop_all(bind=bind)
