"""tenant_hardening_rls

Revision ID: f4a9b2c8d1e7
Revises: 9b7a4c2d1e6f
Create Date: 2026-05-29

Development reset note:
This migration is designed for the pre-production development database. If real
production tenant data exists, stop and create a data-preserving migration plan.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f4a9b2c8d1e7"
down_revision: Union[str, None] = "9b7a4c2d1e6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TENANT_TABLES = (
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
    "module",
    "occurrence_operational_event",
    "operational_schedule_block",
    "organization_grid_settings",
    "organization_settings",
    "progress_ledger_entry",
    "room",
    "schedule_output",
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


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _q(name: str) -> str:
    name = name.strip('"')
    return '"' + name.replace('"', '""') + '"'


def _add_tenant_column(table: str) -> None:
    op.add_column(table, sa.Column("organization_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        f"fk_{table}_organization_id",
        table,
        "organization",
        ["organization_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(f"ix_{table}_organization_id", table, ["organization_id"])


def _replace_unique(table: str, old_name: str, columns: list[str]) -> None:
    op.drop_constraint(old_name, table, type_="unique")
    op.create_unique_constraint(old_name, table, columns)


def _create_same_tenant_trigger(table: str, refs: dict[str, str]) -> None:
    checks = []
    for column, ref_table in refs.items():
        checks.append(
            f"""
            IF NEW.{column} IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM public.{_q(ref_table)}
                WHERE id = NEW.{column}
                  AND organization_id = NEW.organization_id
            ) THEN
                RAISE EXCEPTION
                    'cross-tenant reference rejected: {table}.{column} -> {ref_table}.id'
                    USING ERRCODE = '23514';
            END IF;
            """
        )
    body = "\n".join(checks)
    op.execute(
        sa.text(
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

            CREATE TRIGGER trg_{table}_tenant_refs
            BEFORE INSERT OR UPDATE ON public.{_q(table)}
            FOR EACH ROW
            EXECUTE FUNCTION app_security.validate_{table}_tenant_refs();
            """
        )
    )


def upgrade() -> None:
    _add_tenant_column("availability")
    _add_tenant_column("course_subject_link")
    _add_tenant_column("teacher_subject_link")
    _add_tenant_column("class_subject_link")
    _add_tenant_column("module")
    _add_tenant_column("class_progress")

    op.execute("UPDATE availability a SET organization_id = t.organization_id FROM teacher t WHERE t.id = a.teacher_id")
    op.execute("UPDATE course_subject_link l SET organization_id = c.organization_id FROM course c WHERE c.id = l.course_id")
    op.execute("UPDATE teacher_subject_link l SET organization_id = t.organization_id FROM teacher t WHERE t.id = l.teacher_id")
    op.execute('UPDATE class_subject_link l SET organization_id = c.organization_id FROM "class" c WHERE c.id = l.class_id')
    op.execute("UPDATE module m SET organization_id = s.organization_id FROM subject s WHERE s.id = m.subject_id")
    op.execute('UPDATE class_progress p SET organization_id = c.organization_id FROM "class" c WHERE c.id = p.class_id')

    for table in ("availability", "course_subject_link", "teacher_subject_link", "class_subject_link", "module", "class_progress"):
        op.alter_column(table, "organization_id", nullable=False)

    op.alter_column("user", "organization_id", nullable=False)

    _replace_unique("availability", "uq_teacher_timeslot_availability", ["organization_id", "teacher_id", "timeslot_id"])
    op.drop_constraint("course_subject_link_pkey", "course_subject_link", type_="primary")
    op.create_primary_key("course_subject_link_pkey", "course_subject_link", ["organization_id", "course_id", "subject_id"])
    op.drop_constraint("teacher_subject_link_pkey", "teacher_subject_link", type_="primary")
    op.create_primary_key("teacher_subject_link_pkey", "teacher_subject_link", ["organization_id", "teacher_id", "subject_id"])
    _replace_unique("class_subject_link", "uq_class_subject_grade", ["organization_id", "class_id", "subject_id", "grade_level"])
    _replace_unique("module", "uq_module_order_per_subject", ["organization_id", "subject_id", "order"])
    _replace_unique("class_progress", "uq_class_module", ["organization_id", "class_id", "module_id"])
    _replace_unique("teacher_weekly_timesheet", "uq_teacher_weekly_timesheet", ["organization_id", "teacher_id", "week_start_date"])

    if not _is_postgresql():
        return

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
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO cronos_app;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
            GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO cronos_app;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
            GRANT USAGE, SELECT ON SEQUENCES TO cronos_app;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
            GRANT SELECT, INSERT, UPDATE ON TABLES TO cronos_auth_definer;
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
        GRANT SELECT, INSERT, UPDATE ON public.organization, public."user" TO cronos_auth_definer;
        GRANT USAGE, SELECT ON SEQUENCE public.organization_id_seq, public.user_id_seq TO cronos_auth_definer;
        """
    )
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
            SELECT u.id, u.organization_id, u.role::text, u.is_active
            FROM public."user" u
            JOIN public.organization o ON o.id = u.organization_id
            WHERE clerk_user_id IS NOT NULL
              AND clerk_org_id IS NOT NULL
              AND length(clerk_user_id) BETWEEN 1 AND 255
              AND length(clerk_org_id) BETWEEN 1 AND 255
              AND u.clerk_user_id = resolve_auth_context.clerk_user_id
              AND o.clerk_org_id = resolve_auth_context.clerk_org_id
              AND u.organization_id IS NOT NULL
            LIMIT 1;
        $$;
        REVOKE ALL ON FUNCTION app_security.resolve_auth_context(text, text) FROM PUBLIC;
        ALTER FUNCTION app_security.resolve_auth_context(text, text) OWNER TO cronos_auth_definer;
        GRANT EXECUTE ON FUNCTION app_security.resolve_auth_context(text, text) TO cronos_app;
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
            parsed_role public.userrole := (
                CASE coalesce(nullif(p_app_role, ''), 'teacher')
                    WHEN 'admin' THEN 'admin'
                    WHEN 'org:admin' THEN 'admin'
                    WHEN 'teacher' THEN 'teacher'
                    WHEN 'member' THEN 'teacher'
                    WHEN 'org:member' THEN 'teacher'
                    ELSE 'teacher'
                END
            )::public.userrole;
        BEGIN
            IF p_clerk_user_id IS NULL OR length(p_clerk_user_id) NOT BETWEEN 1 AND 255 THEN
                RAISE EXCEPTION 'clerk_user_id is required';
            END IF;
            IF p_organization_id IS NULL OR p_organization_id < 1 THEN
                RAISE EXCEPTION 'organization_id is required';
            END IF;

            INSERT INTO public."user" (
                clerk_user_id,
                email,
                name,
                role,
                organization_id,
                teacher_id,
                is_active,
                is_superuser
            )
            VALUES (
                p_clerk_user_id,
                coalesce(p_email, ''),
                p_display_name,
                parsed_role,
                p_organization_id,
                p_teacher_id,
                true,
                false
            )
            ON CONFLICT (clerk_user_id) DO UPDATE
                SET email = coalesce(EXCLUDED.email, public."user".email),
                    name = coalesce(EXCLUDED.name, public."user".name),
                    role = EXCLUDED.role,
                    organization_id = EXCLUDED.organization_id,
                    teacher_id = coalesce(EXCLUDED.teacher_id, public."user".teacher_id),
                    is_active = true
                WHERE public."user".email IS DISTINCT FROM coalesce(EXCLUDED.email, public."user".email)
                   OR public."user".name IS DISTINCT FROM coalesce(EXCLUDED.name, public."user".name)
                   OR public."user".role IS DISTINCT FROM EXCLUDED.role
                   OR public."user".organization_id IS DISTINCT FROM EXCLUDED.organization_id
                   OR public."user".teacher_id IS DISTINCT FROM coalesce(EXCLUDED.teacher_id, public."user".teacher_id)
                   OR public."user".is_active IS DISTINCT FROM true
            RETURNING public."user".id, public."user".organization_id
            INTO id, organization_id;

            IF id IS NULL THEN
                SELECT public."user".id, public."user".organization_id
                INTO id, organization_id
                FROM public."user"
                WHERE public."user".clerk_user_id = p_clerk_user_id;
            END IF;

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
                teacher_id = coalesce(p_teacher_id, public."user".teacher_id)
            WHERE public."user".clerk_user_id = p_clerk_user_id
              AND (
                public."user".email IS DISTINCT FROM coalesce(p_email, public."user".email)
                OR public."user".name IS DISTINCT FROM coalesce(p_display_name, public."user".name)
                OR public."user".role IS DISTINCT FROM coalesce(parsed_role, public."user".role)
                OR public."user".teacher_id IS DISTINCT FROM coalesce(p_teacher_id, public."user".teacher_id)
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
            affected_count integer;
        BEGIN
            UPDATE public."user"
            SET is_active = false
            WHERE public."user".clerk_user_id = p_clerk_user_id
              AND public."user".is_active = true
              AND public."user".is_superuser = false
              AND NOT (
                public."user".role = 'admin'
                AND (
                    SELECT count(*)
                    FROM public."user" active_admin
                    WHERE active_admin.organization_id = public."user".organization_id
                      AND active_admin.role = 'admin'
                      AND active_admin.is_active = true
                      AND active_admin.is_superuser = false
                ) <= 1
              );
            GET DIAGNOSTICS affected_count = ROW_COUNT;
            RETURN affected_count > 0;
        END;
        $$;

        REVOKE ALL ON FUNCTION app_security.ensure_organization(text, text) FROM PUBLIC;
        REVOKE ALL ON FUNCTION app_security.ensure_user(text, text, text, text, integer, integer) FROM PUBLIC;
        REVOKE ALL ON FUNCTION app_security.update_user_profile(text, text, text, text, integer) FROM PUBLIC;
        REVOKE ALL ON FUNCTION app_security.deactivate_organization(text) FROM PUBLIC;
        REVOKE ALL ON FUNCTION app_security.deactivate_user(text) FROM PUBLIC;
        ALTER FUNCTION app_security.ensure_organization(text, text) OWNER TO cronos_auth_definer;
        ALTER FUNCTION app_security.ensure_user(text, text, text, text, integer, integer) OWNER TO cronos_auth_definer;
        ALTER FUNCTION app_security.update_user_profile(text, text, text, text, integer) OWNER TO cronos_auth_definer;
        ALTER FUNCTION app_security.deactivate_organization(text) OWNER TO cronos_auth_definer;
        ALTER FUNCTION app_security.deactivate_user(text) OWNER TO cronos_auth_definer;
        GRANT EXECUTE ON FUNCTION app_security.ensure_organization(text, text) TO cronos_app;
        GRANT EXECUTE ON FUNCTION app_security.ensure_user(text, text, text, text, integer, integer) TO cronos_app;
        GRANT EXECUTE ON FUNCTION app_security.update_user_profile(text, text, text, text, integer) TO cronos_app;
        GRANT EXECUTE ON FUNCTION app_security.deactivate_organization(text) TO cronos_app;
        GRANT EXECUTE ON FUNCTION app_security.deactivate_user(text) TO cronos_app;
        """
    )
    op.execute(
        """
        GRANT EXECUTE ON FUNCTION app_security.current_organization_id() TO cronos_app;
        """
    )

    same_tenant_refs = {
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
        "lesson_log": {"schedule_output_id": "schedule_output", "operational_block_id": "operational_schedule_block"},
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
    }
    for table, refs in same_tenant_refs.items():
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


def downgrade() -> None:
    if _is_postgresql():
        for table in TENANT_TABLES:
            op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON public.{_q(table)}")
            op.execute(f"ALTER TABLE public.{_q(table)} DISABLE ROW LEVEL SECURITY")
        op.execute("DROP POLICY IF EXISTS tenant_isolation ON public.organization")
        op.execute("ALTER TABLE public.organization DISABLE ROW LEVEL SECURITY")
        for table in (
            "availability",
            "course_subject_link",
            "teacher_subject_link",
            "class_subject_link",
            "module",
            "class_progress",
            "lesson",
            "schedule_output",
            "teacher_weekly_timesheet",
            "lesson_occurrence",
            "lesson_log",
            "operational_schedule_block",
            "progress_ledger_entry",
        ):
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_tenant_refs ON public.{_q(table)}")
            op.execute(f"DROP FUNCTION IF EXISTS app_security.validate_{table}_tenant_refs()")
        op.execute("DROP FUNCTION IF EXISTS app_security.deactivate_user(text)")
        op.execute("DROP FUNCTION IF EXISTS app_security.deactivate_organization(text)")
        op.execute("DROP FUNCTION IF EXISTS app_security.update_user_profile(text, text, text, text, integer)")
        op.execute("DROP FUNCTION IF EXISTS app_security.update_user_profile(text, text, text)")
        op.execute("DROP FUNCTION IF EXISTS app_security.ensure_user(text, text, text, text, integer, integer)")
        op.execute("DROP FUNCTION IF EXISTS app_security.ensure_organization(text, text)")
        op.execute("DROP FUNCTION IF EXISTS app_security.resolve_auth_context(text, text)")
        op.execute("DROP FUNCTION IF EXISTS app_security.current_organization_id()")
        op.execute("DROP SCHEMA IF EXISTS app_security")
        op.execute(
            """
            REVOKE cronos_app FROM CURRENT_USER;
            DROP ROLE IF EXISTS cronos_app;
            DROP ROLE IF EXISTS cronos_auth_definer;
            """
        )

    op.alter_column("user", "organization_id", nullable=True)
    _replace_unique("teacher_weekly_timesheet", "uq_teacher_weekly_timesheet", ["teacher_id", "week_start_date"])
    _replace_unique("class_progress", "uq_class_module", ["class_id", "module_id"])
    _replace_unique("module", "uq_module_order_per_subject", ["subject_id", "order"])
    _replace_unique("class_subject_link", "uq_class_subject_grade", ["class_id", "subject_id", "grade_level"])
    op.drop_constraint("teacher_subject_link_pkey", "teacher_subject_link", type_="primary")
    op.create_primary_key("teacher_subject_link_pkey", "teacher_subject_link", ["teacher_id", "subject_id"])
    op.drop_constraint("course_subject_link_pkey", "course_subject_link", type_="primary")
    op.create_primary_key("course_subject_link_pkey", "course_subject_link", ["course_id", "subject_id"])
    _replace_unique("availability", "uq_teacher_timeslot_availability", ["teacher_id", "timeslot_id"])

    for table in ("class_progress", "module", "class_subject_link", "teacher_subject_link", "course_subject_link", "availability"):
        op.drop_index(f"ix_{table}_organization_id", table_name=table)
        op.drop_constraint(f"fk_{table}_organization_id", table, type_="foreignkey")
        op.drop_column(table, "organization_id")
