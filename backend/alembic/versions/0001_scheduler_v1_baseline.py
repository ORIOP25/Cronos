"""Scheduler v1 consolidated baseline.

Fresh installs start from this single revision. It replaces the historical
chain (0001-0014) and installs the frozen v1 schema end state: core identity,
academic catalogue, operational lesson records, the scheduler v1 curricular
tables, queue access functions and lesson logs, with roles, RLS, grants and
indexes revalidated against the ORM metadata. The provisional revision
0011_scheduler_v1_curricular is no longer reachable from the installed head.
"""

from alembic import op

revision = "0001_scheduler_v1_baseline"
down_revision = None
branch_labels = None
depends_on = None

BASELINE_SQL = r"""--
-- PostgreSQL database dump
--


-- Dumped from database version 16.15
-- Dumped by pg_dump version 16.15

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: app_security; Type: SCHEMA; Schema: -; Owner: cronos_auth_definer
--



ALTER SCHEMA app_security OWNER TO cronos_auth_definer;

--
-- Name: activescheduleblockstatus; Type: TYPE; Schema: public; Owner: cronos_migrator
--

CREATE TYPE public.activescheduleblockstatus AS ENUM (
    'ACTIVE',
    'REMOVED',
    'CANCELED'
);


ALTER TYPE public.activescheduleblockstatus OWNER TO cronos_migrator;

--
-- Name: calendareventsource; Type: TYPE; Schema: public; Owner: cronos_migrator
--

CREATE TYPE public.calendareventsource AS ENUM (
    'auto',
    'manual'
);


ALTER TYPE public.calendareventsource OWNER TO cronos_migrator;

--
-- Name: calendareventtype; Type: TYPE; Schema: public; Owner: cronos_migrator
--

CREATE TYPE public.calendareventtype AS ENUM (
    'national_holiday',
    'school_break',
    'exam_period',
    'other'
);


ALTER TYPE public.calendareventtype OWNER TO cronos_migrator;

--
-- Name: clerkinvitationstatus; Type: TYPE; Schema: public; Owner: cronos_migrator
--

CREATE TYPE public.clerkinvitationstatus AS ENUM (
    'pending',
    'accepted',
    'revoked',
    'expired'
);


ALTER TYPE public.clerkinvitationstatus OWNER TO cronos_migrator;

--
-- Name: clerkwebhookprocessingstatus; Type: TYPE; Schema: public; Owner: cronos_migrator
--

CREATE TYPE public.clerkwebhookprocessingstatus AS ENUM (
    'received',
    'processing',
    'processed',
    'ignored',
    'retryable_failed',
    'sync_error',
    'dead_letter'
);


ALTER TYPE public.clerkwebhookprocessingstatus OWNER TO cronos_migrator;

--
-- Name: constrainttype; Type: TYPE; Schema: public; Owner: cronos_migrator
--

CREATE TYPE public.constrainttype AS ENUM (
    'specific_room',
    'lock_time',
    'teacher_unavailable',
    'teacher_preferred'
);


ALTER TYPE public.constrainttype OWNER TO cronos_migrator;

--
-- Name: lessonlogstatus; Type: TYPE; Schema: public; Owner: cronos_migrator
--

CREATE TYPE public.lessonlogstatus AS ENUM (
    'PENDING',
    'COMPLETED',
    'OCCURRENCE'
);


ALTER TYPE public.lessonlogstatus OWNER TO cronos_migrator;

--
-- Name: lessonoccurrencestatus; Type: TYPE; Schema: public; Owner: cronos_migrator
--

CREATE TYPE public.lessonoccurrencestatus AS ENUM (
    'GIVEN',
    'GAP',
    'SUBSTITUTED',
    'REVOKED'
);


ALTER TYPE public.lessonoccurrencestatus OWNER TO cronos_migrator;

--
-- Name: memberaccessoperationstatus; Type: TYPE; Schema: public; Owner: cronos_migrator
--

CREATE TYPE public.memberaccessoperationstatus AS ENUM (
    'pending',
    'clerk_succeeded',
    'local_committed',
    'failed',
    'compensated',
    'compensation_failed',
    'support_required'
);


ALTER TYPE public.memberaccessoperationstatus OWNER TO cronos_migrator;

--
-- Name: memberaccessoperationtype; Type: TYPE; Schema: public; Owner: cronos_migrator
--

CREATE TYPE public.memberaccessoperationtype AS ENUM (
    'create_invitation',
    'revoke_invitation',
    'revoke_membership',
    'change_role',
    'resend_invitation',
    'restore_access',
    'block_access'
);


ALTER TYPE public.memberaccessoperationtype OWNER TO cronos_migrator;

--
-- Name: membershipaccessstatus; Type: TYPE; Schema: public; Owner: cronos_migrator
--

CREATE TYPE public.membershipaccessstatus AS ENUM (
    'none',
    'pending_invite',
    'invite_expired',
    'active',
    'blocked',
    'sync_error'
);


ALTER TYPE public.membershipaccessstatus OWNER TO cronos_migrator;

--
-- Name: membershiplifecyclestatus; Type: TYPE; Schema: public; Owner: cronos_migrator
--

CREATE TYPE public.membershiplifecyclestatus AS ENUM (
    'active',
    'archived'
);


ALTER TYPE public.membershiplifecyclestatus OWNER TO cronos_migrator;

--
-- Name: operationalblockexecutionstatus; Type: TYPE; Schema: public; Owner: cronos_migrator
--

CREATE TYPE public.operationalblockexecutionstatus AS ENUM (
    'PENDING_LOG',
    'COMPLETED',
    'CANCELLED'
);


ALTER TYPE public.operationalblockexecutionstatus OWNER TO cronos_migrator;

--
-- Name: operationalblockstatus; Type: TYPE; Schema: public; Owner: cronos_migrator
--

CREATE TYPE public.operationalblockstatus AS ENUM (
    'ACTIVE',
    'CANCELLED'
);


ALTER TYPE public.operationalblockstatus OWNER TO cronos_migrator;

--
-- Name: organizationfoundationstatus; Type: TYPE; Schema: public; Owner: cronos_migrator
--

CREATE TYPE public.organizationfoundationstatus AS ENUM (
    'NOT_STARTED',
    'IN_PROGRESS',
    'COMPLETED'
);


ALTER TYPE public.organizationfoundationstatus OWNER TO cronos_migrator;

--
-- Name: organizationplanstatus; Type: TYPE; Schema: public; Owner: cronos_migrator
--

CREATE TYPE public.organizationplanstatus AS ENUM (
    'inactive',
    'active',
    'suspended'
);


ALTER TYPE public.organizationplanstatus OWNER TO cronos_migrator;

--
-- Name: plannedrecoverylinkstatus; Type: TYPE; Schema: public; Owner: cronos_migrator
--

CREATE TYPE public.plannedrecoverylinkstatus AS ENUM (
    'PLANNED',
    'DELIVERED',
    'CANCELED',
    'REPLACED'
);


ALTER TYPE public.plannedrecoverylinkstatus OWNER TO cronos_migrator;

--
-- Name: roomtype; Type: TYPE; Schema: public; Owner: cronos_migrator
--

CREATE TYPE public.roomtype AS ENUM (
    'normal',
    'lab',
    'gym',
    'art'
);


ALTER TYPE public.roomtype OWNER TO cronos_migrator;

--
-- Name: schedulediffchangetype; Type: TYPE; Schema: public; Owner: cronos_migrator
--

CREATE TYPE public.schedulediffchangetype AS ENUM (
    'ADDED',
    'MOVED',
    'CHANGED',
    'REMOVED',
    'UNCHANGED_IMPACTED'
);


ALTER TYPE public.schedulediffchangetype OWNER TO cronos_migrator;

--
-- Name: schedulediffscope; Type: TYPE; Schema: public; Owner: cronos_migrator
--

CREATE TYPE public.schedulediffscope AS ENUM (
    'AFFECTED',
    'RELATED',
    'UNRELATED'
);


ALTER TYPE public.schedulediffscope OWNER TO cronos_migrator;

--
-- Name: scheduledraftblockchangetype; Type: TYPE; Schema: public; Owner: cronos_migrator
--

CREATE TYPE public.scheduledraftblockchangetype AS ENUM (
    'UNCHANGED',
    'ADDED',
    'MOVED',
    'ROOM_ONLY',
    'REPLACED'
);


ALTER TYPE public.scheduledraftblockchangetype OWNER TO cronos_migrator;

--
-- Name: scheduledraftstate; Type: TYPE; Schema: public; Owner: cronos_migrator
--

CREATE TYPE public.scheduledraftstate AS ENUM (
    'PENDING',
    'APPROVED',
    'REJECTED',
    'REPLACED',
    'STALE',
    'INVALIDATED'
);


ALTER TYPE public.scheduledraftstate OWNER TO cronos_migrator;

--
-- Name: schedulegenerationjobstatus; Type: TYPE; Schema: public; Owner: cronos_migrator
--

CREATE TYPE public.schedulegenerationjobstatus AS ENUM (
    'QUEUED',
    'RUNNING',
    'CANCEL_REQUESTED',
    'CANCELED',
    'SUCCEEDED',
    'FAILED',
    'NO_VALID_OUTPUT'
);


ALTER TYPE public.schedulegenerationjobstatus OWNER TO cronos_migrator;

--
-- Name: schedulegenerationresultcategory; Type: TYPE; Schema: public; Owner: cronos_migrator
--

CREATE TYPE public.schedulegenerationresultcategory AS ENUM (
    'COMPLETE_SUCCESS',
    'PARTIAL_RECOVERY',
    'NO_VALID_OUTPUT'
);


ALTER TYPE public.schedulegenerationresultcategory OWNER TO cronos_migrator;

--
-- Name: schedulegenerationstrategy; Type: TYPE; Schema: public; Owner: cronos_migrator
--

CREATE TYPE public.schedulegenerationstrategy AS ENUM (
    'COMPLETE_GENERATION',
    'ADAPTIVE_REPAIR'
);


ALTER TYPE public.schedulegenerationstrategy OWNER TO cronos_migrator;

--
-- Name: schedulegenerationtrigger; Type: TYPE; Schema: public; Owner: cronos_migrator
--

CREATE TYPE public.schedulegenerationtrigger AS ENUM (
    'FIRST_GENERATION',
    'EXPLICIT_DEBT',
    'SCHEDULER_CHANGE',
    'MIXED'
);


ALTER TYPE public.schedulegenerationtrigger OWNER TO cronos_migrator;

--
-- Name: schedulerstatechangeoperation; Type: TYPE; Schema: public; Owner: cronos_migrator
--

CREATE TYPE public.schedulerstatechangeoperation AS ENUM (
    'CREATE',
    'UPDATE',
    'DELETE',
    'BULK_IMPORT'
);


ALTER TYPE public.schedulerstatechangeoperation OWNER TO cronos_migrator;

--
-- Name: schedulerstatechangescope; Type: TYPE; Schema: public; Owner: cronos_migrator
--

CREATE TYPE public.schedulerstatechangescope AS ENUM (
    'FUTURE_IMPACTING',
    'PAST_ONLY',
    'NO_OP',
    'INACTIVE_RESOURCE'
);


ALTER TYPE public.schedulerstatechangescope OWNER TO cronos_migrator;

--
-- Name: schoolyearpublicationstate; Type: TYPE; Schema: public; Owner: cronos_migrator
--

CREATE TYPE public.schoolyearpublicationstate AS ENUM (
    'UNPUBLISHED',
    'PUBLISHED'
);


ALTER TYPE public.schoolyearpublicationstate OWNER TO cronos_migrator;

--
-- Name: teacheraccessmode; Type: TYPE; Schema: public; Owner: cronos_migrator
--

CREATE TYPE public.teacheraccessmode AS ENUM (
    'platform',
    'scheduler_only'
);


ALTER TYPE public.teacheraccessmode OWNER TO cronos_migrator;

--
-- Name: timesheetstatus; Type: TYPE; Schema: public; Owner: cronos_migrator
--

CREATE TYPE public.timesheetstatus AS ENUM (
    'OPEN',
    'SUBMITTED',
    'APPROVED'
);


ALTER TYPE public.timesheetstatus OWNER TO cronos_migrator;

--
-- Name: bootstrap_organization_admin(text, text, text, text, text, text); Type: FUNCTION; Schema: app_security; Owner: cronos_auth_definer
--

CREATE FUNCTION app_security.bootstrap_organization_admin(requested_clerk_user_id text, requested_clerk_org_id text, requested_organization_name text, requested_email text, requested_profile_name text, requested_membership_id text) RETURNS TABLE(account_id integer, organization_id integer, membership_id integer)
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
        DECLARE
            v_org integer;
            v_account integer;
            v_member integer;
            v_email text := lower(coalesce(nullif(trim(requested_email), ''), requested_clerk_user_id || '@clerk.local'));
        BEGIN
            PERFORM pg_advisory_xact_lock(hashtext(requested_clerk_org_id));
            SELECT id INTO v_org FROM public.organization WHERE clerk_org_id = requested_clerk_org_id;
            IF v_org IS NULL THEN
                INSERT INTO public.organization(name, clerk_org_id, plan_status, foundation_status)
                VALUES (requested_organization_name, requested_clerk_org_id, 'active', 'NOT_STARTED')
                RETURNING id INTO v_org;
            ELSIF (SELECT plan_status FROM public.organization WHERE id = v_org) <> 'active' THEN
                RETURN;
            END IF;
            IF EXISTS (SELECT 1 FROM public.organization_membership m WHERE m.organization_id = v_org) THEN
                RETURN QUERY SELECT u.id, v_org, m.id FROM public."user" u
                JOIN public.organization_membership m ON m.account_id = u.id
                WHERE m.organization_id = v_org AND u.clerk_user_id = requested_clerk_user_id
                  AND m.clerk_membership_id = requested_membership_id AND m.lifecycle_status = 'active'
                  AND m.access_status = 'active' AND m.can_admin;
                RETURN;
            END IF;
            SELECT id INTO v_account FROM public."user" WHERE clerk_user_id = requested_clerk_user_id;
            IF v_account IS NULL THEN
                SELECT id INTO v_account FROM public."user" WHERE lower(email) = v_email AND clerk_user_id IS NULL;
            END IF;
            IF v_account IS NULL AND EXISTS (SELECT 1 FROM public."user" WHERE lower(email) = v_email) THEN
                RETURN;
            END IF;
            IF v_account IS NULL THEN
                INSERT INTO public."user"(name, email, clerk_user_id, clerk_profile_name, last_clerk_sync_at, created_at, updated_at)
                VALUES (requested_profile_name, v_email, requested_clerk_user_id, requested_profile_name, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                RETURNING id INTO v_account;
            END IF;
            INSERT INTO public.organization_membership(
                organization_id, account_id, organization_display_name, lifecycle_status, access_status,
                can_admin, can_teach, clerk_membership_id, created_by_membership_id,
                updated_by_membership_id, lock_version, created_at, updated_at
            ) VALUES (
                v_org, v_account, requested_organization_name, 'active', 'active', true, false,
                requested_membership_id, NULL, NULL, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            ) RETURNING id INTO v_member;
            UPDATE public.organization_membership
            SET created_by_membership_id = v_member,
                updated_by_membership_id = v_member
            WHERE id = v_member;
            RETURN QUERY SELECT v_account, v_org, v_member;
        END;
        $$;


ALTER FUNCTION app_security.bootstrap_organization_admin(requested_clerk_user_id text, requested_clerk_org_id text, requested_organization_name text, requested_email text, requested_profile_name text, requested_membership_id text) OWNER TO cronos_auth_definer;

--
-- Name: current_organization_id(); Type: FUNCTION; Schema: app_security; Owner: cronos_migrator
--

CREATE FUNCTION app_security.current_organization_id() RETURNS integer
    LANGUAGE sql STABLE
    AS $_$
  SELECT CASE
    WHEN current_setting('app.current_organization_id', true) ~ '^[1-9][0-9]{0,9}$'
     AND current_setting('app.current_organization_id', true)::numeric <= 2147483647
    THEN current_setting('app.current_organization_id', true)::integer
    ELSE NULL
  END
$_$;


ALTER FUNCTION app_security.current_organization_id() OWNER TO cronos_migrator;

--
-- Name: deactivate_organization(text); Type: FUNCTION; Schema: app_security; Owner: cronos_auth_definer
--

CREATE FUNCTION app_security.deactivate_organization(requested_clerk_org_id text) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
DECLARE v_organization_id integer;
BEGIN
  UPDATE public.organization SET plan_status = 'inactive'
  WHERE clerk_org_id = requested_clerk_org_id RETURNING id INTO v_organization_id;
  IF v_organization_id IS NULL THEN RETURN FALSE; END IF;
  UPDATE public.organization_membership
  SET lifecycle_status = 'archived', access_status = 'none', updated_at = CURRENT_TIMESTAMP
  WHERE organization_id = v_organization_id;
  RETURN TRUE;
END
$$;


ALTER FUNCTION app_security.deactivate_organization(requested_clerk_org_id text) OWNER TO cronos_auth_definer;

--
-- Name: deactivate_user(text); Type: FUNCTION; Schema: app_security; Owner: cronos_auth_definer
--

CREATE FUNCTION app_security.deactivate_user(requested_clerk_user_id text) RETURNS boolean
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
WITH account AS (SELECT id FROM public."user" WHERE clerk_user_id = requested_clerk_user_id),
changed AS (UPDATE public.organization_membership m SET lifecycle_status = 'archived', access_status = 'none', updated_at = CURRENT_TIMESTAMP FROM account a WHERE m.account_id = a.id RETURNING m.id)
SELECT EXISTS (SELECT 1 FROM changed) $$;


ALTER FUNCTION app_security.deactivate_user(requested_clerk_user_id text) OWNER TO cronos_auth_definer;

--
-- Name: ensure_organization(text, text); Type: FUNCTION; Schema: app_security; Owner: cronos_auth_definer
--

CREATE FUNCTION app_security.ensure_organization(requested_clerk_org_id text, requested_name text) RETURNS TABLE(id integer)
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
  INSERT INTO public.organization (name, clerk_org_id, plan_status)
  VALUES (requested_name, requested_clerk_org_id, 'active')
  ON CONFLICT (clerk_org_id) DO UPDATE
    SET name = EXCLUDED.name, plan_status = 'active'
  RETURNING organization.id
$$;


ALTER FUNCTION app_security.ensure_organization(requested_clerk_org_id text, requested_name text) OWNER TO cronos_auth_definer;

--
-- Name: ensure_pending_account(integer, text, text); Type: FUNCTION; Schema: app_security; Owner: cronos_auth_definer
--

CREATE FUNCTION app_security.ensure_pending_account(requested_organization_id integer, requested_email text, requested_name text) RETURNS TABLE(id integer)
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
DECLARE v_account_id integer;
BEGIN
  IF current_setting('app.current_organization_id', true)
       IS DISTINCT FROM requested_organization_id::text THEN
    RAISE insufficient_privilege USING MESSAGE = 'Tenant context mismatch';
  END IF;
  SELECT u.id INTO v_account_id
  FROM public."user" u
  WHERE lower(u.email) = lower(requested_email)
  LIMIT 1;
  IF v_account_id IS NULL THEN
    INSERT INTO public."user" (email, name, created_at, updated_at)
    VALUES (
      lower(requested_email), requested_name,
      CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
    )
    RETURNING public."user".id INTO v_account_id;
  END IF;
  RETURN QUERY SELECT v_account_id;
END
$$;


ALTER FUNCTION app_security.ensure_pending_account(requested_organization_id integer, requested_email text, requested_name text) OWNER TO cronos_auth_definer;

--
-- Name: ensure_user(text, text, text, text, integer, integer); Type: FUNCTION; Schema: app_security; Owner: cronos_auth_definer
--

CREATE FUNCTION app_security.ensure_user(requested_clerk_user_id text, requested_email text, requested_name text, requested_role text, requested_organization_id integer, requested_teacher_id integer) RETURNS TABLE(id integer, organization_id integer)
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
        DECLARE
          v_account_id integer;
          v_existing_clerk_account_id integer;
          v_matching_accounts integer;
          v_email text := lower(nullif(trim(requested_email), ''));
        BEGIN
          IF nullif(trim(requested_clerk_user_id), '') IS NULL
             OR requested_organization_id IS NULL THEN
            RETURN;
          END IF;

          SELECT u.id INTO v_existing_clerk_account_id
          FROM public."user" AS u
          WHERE u.clerk_user_id = requested_clerk_user_id;

          IF v_existing_clerk_account_id IS NOT NULL THEN
            SELECT m.account_id INTO v_account_id
            FROM public.organization_membership AS m
            WHERE m.organization_id = requested_organization_id
              AND m.account_id = v_existing_clerk_account_id;
            IF v_account_id IS NULL THEN
              RETURN;
            END IF;
          ELSE
            IF v_email IS NULL THEN
              RETURN;
            END IF;

            SELECT count(*), min(u.id)
              INTO v_matching_accounts, v_account_id
            FROM public."user" AS u
            JOIN public.organization_membership AS m ON m.account_id = u.id
            WHERE m.organization_id = requested_organization_id
              AND u.clerk_user_id IS NULL
              AND lower(u.email) = v_email;

            IF v_matching_accounts <> 1 THEN
              RETURN;
            END IF;
          END IF;

          UPDATE public."user" AS u SET
            clerk_user_id = requested_clerk_user_id,
            email = coalesce(v_email, u.email),
            name = coalesce(nullif(requested_name, ''), u.name),
            clerk_profile_name = coalesce(nullif(requested_name, ''), u.clerk_profile_name),
            last_clerk_sync_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
          WHERE u.id = v_account_id;

          RETURN QUERY SELECT v_account_id, requested_organization_id;
        END
        $$;


ALTER FUNCTION app_security.ensure_user(requested_clerk_user_id text, requested_email text, requested_name text, requested_role text, requested_organization_id integer, requested_teacher_id integer) OWNER TO cronos_auth_definer;

--
-- Name: find_clerk_user_by_email(text, text); Type: FUNCTION; Schema: app_security; Owner: cronos_auth_definer
--

CREATE FUNCTION app_security.find_clerk_user_by_email(requested_email text, excluded_clerk_user_id text) RETURNS text
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
            SELECT clerk_user_id
            FROM public."user"
            WHERE lower(email) = lower(requested_email)
              AND clerk_user_id IS NOT NULL
              AND clerk_user_id <> excluded_clerk_user_id
            LIMIT 1
        $$;


ALTER FUNCTION app_security.find_clerk_user_by_email(requested_email text, excluded_clerk_user_id text) OWNER TO cronos_auth_definer;

--
-- Name: list_reconciliation_organization_ids(); Type: FUNCTION; Schema: app_security; Owner: cronos_auth_definer
--

CREATE FUNCTION app_security.list_reconciliation_organization_ids() RETURNS SETOF integer
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
          SELECT id
          FROM public.organization
          WHERE plan_status = 'active'
          ORDER BY id
        $$;


ALTER FUNCTION app_security.list_reconciliation_organization_ids() OWNER TO cronos_auth_definer;

--
-- Name: list_scheduler_v1_jobs_for_executor(); Type: FUNCTION; Schema: app_security; Owner: cronos_auth_definer
--

CREATE FUNCTION app_security.list_scheduler_v1_jobs_for_executor() RETURNS TABLE(job_id integer, organization_id integer, school_year_id integer, status text, queued_at timestamp with time zone, heartbeat_at timestamp with time zone, attempt_token integer)
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
          SELECT id, organization_id, school_year_id, status, queued_at,
                 heartbeat_at, attempt_token
          FROM public.scheduler_job_v1
          WHERE status IN ('QUEUED', 'RUNNING', 'VALIDATING')
          ORDER BY queued_at, id
        $$;


ALTER FUNCTION app_security.list_scheduler_v1_jobs_for_executor() OWNER TO cronos_auth_definer;

--
-- Name: reclaim_deleted_clerk_identity(text); Type: FUNCTION; Schema: app_security; Owner: cronos_auth_definer
--

CREATE FUNCTION app_security.reclaim_deleted_clerk_identity(requested_clerk_user_id text) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
        DECLARE
            v_account_id integer;
            v_tombstone_email text;
        BEGIN
            SELECT id INTO v_account_id
            FROM public."user"
            WHERE clerk_user_id = requested_clerk_user_id
            FOR UPDATE;

            IF v_account_id IS NULL THEN
                RETURN false;
            END IF;

            v_tombstone_email :=
                'deleted+' || md5(requested_clerk_user_id) || '@invalid.local';

            UPDATE public.organization_membership
            SET lifecycle_status = 'archived',
                access_status = 'none',
                clerk_membership_id = NULL,
                access_block_reason = 'provider_user_deleted',
                updated_at = CURRENT_TIMESTAMP
            WHERE account_id = v_account_id;

            UPDATE public."user"
            SET clerk_user_id = NULL,
                email = v_tombstone_email,
                clerk_primary_email_id = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = v_account_id;

            RETURN true;
        END;
        $$;


ALTER FUNCTION app_security.reclaim_deleted_clerk_identity(requested_clerk_user_id text) OWNER TO cronos_auth_definer;

--
-- Name: resolve_principal(text, text); Type: FUNCTION; Schema: app_security; Owner: cronos_auth_definer
--

CREATE FUNCTION app_security.resolve_principal(requested_clerk_user_id text, requested_clerk_org_id text) RETURNS TABLE(account_id integer, clerk_user_id text, organization_id integer, membership_id integer, can_admin boolean, can_teach boolean, teacher_id integer)
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
SELECT u.id, u.clerk_user_id, m.organization_id, m.id, m.can_admin, m.can_teach, t.id
FROM public."user" u JOIN public.organization_membership m ON m.account_id = u.id
JOIN public.organization o ON o.id = m.organization_id
LEFT JOIN public.teacher t ON t.organization_membership_id = m.id
WHERE u.clerk_user_id = requested_clerk_user_id AND o.clerk_org_id = requested_clerk_org_id
  AND o.plan_status = 'active' AND m.lifecycle_status = 'active' AND m.access_status = 'active' LIMIT 1
$$;


ALTER FUNCTION app_security.resolve_principal(requested_clerk_user_id text, requested_clerk_org_id text) OWNER TO cronos_auth_definer;

--
-- Name: resolve_webhook_organization(text); Type: FUNCTION; Schema: app_security; Owner: cronos_auth_definer
--

CREATE FUNCTION app_security.resolve_webhook_organization(requested_clerk_org_id text) RETURNS integer
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$ SELECT id FROM public.organization WHERE clerk_org_id = requested_clerk_org_id LIMIT 1 $$;


ALTER FUNCTION app_security.resolve_webhook_organization(requested_clerk_org_id text) OWNER TO cronos_auth_definer;

--
-- Name: scheduler_v1_queue_position(integer); Type: FUNCTION; Schema: app_security; Owner: cronos_auth_definer
--

CREATE FUNCTION app_security.scheduler_v1_queue_position(requested_job_id integer) RETURNS integer
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
          SELECT count(*)::integer
          FROM public.scheduler_job_v1 AS jobs
          WHERE jobs.status = 'QUEUED'
            AND (jobs.queued_at, jobs.id) <= (
                SELECT target.queued_at, target.id
                FROM public.scheduler_job_v1 AS target
                WHERE target.id = requested_job_id
            )
        $$;


ALTER FUNCTION app_security.scheduler_v1_queue_position(requested_job_id integer) OWNER TO cronos_auth_definer;

--
-- Name: trg_fn_organization_foundation_monotonic(); Type: FUNCTION; Schema: app_security; Owner: cronos_migrator
--

CREATE FUNCTION app_security.trg_fn_organization_foundation_monotonic() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
            IF TG_OP IN ('INSERT', 'UPDATE') THEN
                IF NEW.foundation_status = 'COMPLETED' AND NEW.foundation_completed_at IS NULL THEN
                    RAISE EXCEPTION 'organization.foundation_completed_at is required when foundation_status is COMPLETED' USING ERRCODE = '23514';
                END IF;
                IF NEW.first_real_schedule_approved_at IS NOT NULL AND NEW.foundation_status <> 'COMPLETED' THEN
                    RAISE EXCEPTION 'first_real_schedule_approved_at requires foundation_status to be COMPLETED' USING ERRCODE = '23514';
                END IF;
                IF TG_OP = 'UPDATE' AND OLD.foundation_status = 'COMPLETED' AND NEW.foundation_status <> 'COMPLETED' THEN
                    RAISE EXCEPTION 'organization.foundation_status COMPLETED cannot regress' USING ERRCODE = '23514';
                END IF;
                IF TG_OP = 'UPDATE' AND OLD.foundation_completed_at IS NOT NULL AND NEW.foundation_completed_at IS DISTINCT FROM OLD.foundation_completed_at THEN
                    RAISE EXCEPTION 'organization.foundation_completed_at is immutable once set' USING ERRCODE = '23514';
                END IF;
                IF TG_OP = 'UPDATE' AND OLD.first_real_schedule_approved_at IS NOT NULL AND NEW.first_real_schedule_approved_at IS DISTINCT FROM OLD.first_real_schedule_approved_at THEN
                    RAISE EXCEPTION 'organization.first_real_schedule_approved_at is immutable once set' USING ERRCODE = '23514';
                END IF;
                RETURN NEW;
            END IF;
            IF OLD.foundation_status = 'COMPLETED' OR OLD.foundation_completed_at IS NOT NULL OR OLD.first_real_schedule_approved_at IS NOT NULL THEN
                RAISE EXCEPTION 'Cannot delete organization with completed foundation or approved schedules' USING ERRCODE = '23514';
            END IF;
            RETURN OLD;
        END;
        $$;


ALTER FUNCTION app_security.trg_fn_organization_foundation_monotonic() OWNER TO cronos_migrator;

--
-- Name: trg_fn_organization_legal_acceptance_append_only(); Type: FUNCTION; Schema: app_security; Owner: cronos_migrator
--

CREATE FUNCTION app_security.trg_fn_organization_legal_acceptance_append_only() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'public'
    AS $$
        BEGIN
            RAISE EXCEPTION 'organization_legal_acceptance is append-only; % is prohibited', TG_OP
                USING ERRCODE = '42501';
        END;
        $$;


ALTER FUNCTION app_security.trg_fn_organization_legal_acceptance_append_only() OWNER TO cronos_migrator;

--
-- Name: update_pending_account_email(integer, integer, text); Type: FUNCTION; Schema: app_security; Owner: cronos_auth_definer
--

CREATE FUNCTION app_security.update_pending_account_email(requested_organization_id integer, requested_account_id integer, requested_email text) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
BEGIN
  IF current_setting('app.current_organization_id', true)
       IS DISTINCT FROM requested_organization_id::text THEN
    RAISE insufficient_privilege USING MESSAGE = 'Tenant context mismatch';
  END IF;
  UPDATE public."user" u
  SET email = lower(requested_email), updated_at = CURRENT_TIMESTAMP
  WHERE u.id = requested_account_id
    AND EXISTS (
      SELECT 1 FROM public.organization_membership m
      WHERE m.organization_id = requested_organization_id
        AND m.account_id = u.id AND m.access_status <> 'active'
    );
  RETURN FOUND;
END
$$;


ALTER FUNCTION app_security.update_pending_account_email(requested_organization_id integer, requested_account_id integer, requested_email text) OWNER TO cronos_auth_definer;

--
-- Name: update_user_profile(text, text, text, text, integer); Type: FUNCTION; Schema: app_security; Owner: cronos_auth_definer
--

CREATE FUNCTION app_security.update_user_profile(requested_clerk_user_id text, requested_email text, requested_name text, requested_role text, requested_teacher_id integer) RETURNS TABLE(id integer, organization_id integer)
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
  WITH updated AS (
    UPDATE public."user" SET
      email = coalesce(nullif(lower(requested_email), ''), email),
      name = coalesce(requested_name, name), clerk_profile_name = requested_name,
      last_clerk_sync_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
    WHERE clerk_user_id = requested_clerk_user_id
    RETURNING public."user".id
  )
  SELECT updated.id, min(m.organization_id) FROM updated
  JOIN public.organization_membership m ON m.account_id = updated.id
  GROUP BY updated.id
$$;


ALTER FUNCTION app_security.update_user_profile(requested_clerk_user_id text, requested_email text, requested_name text, requested_role text, requested_teacher_id integer) OWNER TO cronos_auth_definer;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: active_schedule_blocks; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.active_schedule_blocks (
    id integer NOT NULL,
    organization_id integer NOT NULL,
    school_year_id integer NOT NULL,
    schedule_version_id character varying(100) NOT NULL,
    stable_block_key character varying(64) NOT NULL,
    class_id integer NOT NULL,
    subject_id integer NOT NULL,
    teacher_id integer NOT NULL,
    room_id integer NOT NULL,
    date date NOT NULL,
    timeslot_id integer NOT NULL,
    duration_minutes integer NOT NULL,
    source_draft_block_id integer NOT NULL,
    is_recovery_block boolean NOT NULL,
    status public.activescheduleblockstatus NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_active_schedule_blocks_duration_positive CHECK ((duration_minutes > 0)),
    CONSTRAINT ck_active_schedule_blocks_stable_key_nonempty CHECK ((length(TRIM(BOTH FROM stable_block_key)) > 0))
);

ALTER TABLE ONLY public.active_schedule_blocks FORCE ROW LEVEL SECURITY;


ALTER TABLE public.active_schedule_blocks OWNER TO cronos_migrator;

--
-- Name: active_schedule_blocks_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.active_schedule_blocks_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.active_schedule_blocks_id_seq OWNER TO cronos_migrator;

--
-- Name: active_schedule_blocks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.active_schedule_blocks_id_seq OWNED BY public.active_schedule_blocks.id;


--
-- Name: availability; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.availability (
    id integer NOT NULL,
    organization_id integer NOT NULL,
    teacher_id integer NOT NULL,
    timeslot_id integer NOT NULL,
    score integer NOT NULL
);

ALTER TABLE ONLY public.availability FORCE ROW LEVEL SECURITY;


ALTER TABLE public.availability OWNER TO cronos_migrator;

--
-- Name: availability_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.availability_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.availability_id_seq OWNER TO cronos_migrator;

--
-- Name: availability_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.availability_id_seq OWNED BY public.availability.id;


--
-- Name: class; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.class (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    size integer NOT NULL,
    start_year integer NOT NULL,
    end_year integer NOT NULL,
    grade_level integer NOT NULL,
    projected_end_date date,
    is_archived boolean NOT NULL,
    course_id integer NOT NULL,
    organization_id integer NOT NULL
);

ALTER TABLE ONLY public.class FORCE ROW LEVEL SECURITY;


ALTER TABLE public.class OWNER TO cronos_migrator;

--
-- Name: class_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.class_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.class_id_seq OWNER TO cronos_migrator;

--
-- Name: class_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.class_id_seq OWNED BY public.class.id;


--
-- Name: class_subject_link; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.class_subject_link (
    id integer NOT NULL,
    organization_id integer NOT NULL,
    class_id integer NOT NULL,
    subject_id integer NOT NULL,
    grade_level integer NOT NULL,
    teacher_id integer
);

ALTER TABLE ONLY public.class_subject_link FORCE ROW LEVEL SECURITY;


ALTER TABLE public.class_subject_link OWNER TO cronos_migrator;

--
-- Name: class_subject_link_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.class_subject_link_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.class_subject_link_id_seq OWNER TO cronos_migrator;

--
-- Name: class_subject_link_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.class_subject_link_id_seq OWNED BY public.class_subject_link.id;


--
-- Name: clerk_webhook_event; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.clerk_webhook_event (
    id integer NOT NULL,
    svix_id character varying(255) NOT NULL,
    event_type character varying(120) NOT NULL,
    clerk_object_id character varying(255),
    clerk_org_id character varying(255),
    clerk_user_id character varying(255),
    payload_json json NOT NULL,
    processing_status public.clerkwebhookprocessingstatus NOT NULL,
    error_category character varying(80),
    support_resolution_action character varying(80),
    support_resolved_by_user_id integer,
    support_resolved_at timestamp with time zone,
    support_resolution_note character varying(500),
    attempt_count integer NOT NULL,
    last_attempt_at timestamp with time zone,
    next_retry_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL,
    processed_at timestamp with time zone
);


ALTER TABLE public.clerk_webhook_event OWNER TO cronos_migrator;

--
-- Name: clerk_webhook_event_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.clerk_webhook_event_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.clerk_webhook_event_id_seq OWNER TO cronos_migrator;

--
-- Name: clerk_webhook_event_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.clerk_webhook_event_id_seq OWNED BY public.clerk_webhook_event.id;


--
-- Name: constraint; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public."constraint" (
    id integer NOT NULL,
    organization_id integer NOT NULL,
    rule_type public.constrainttype NOT NULL,
    class_id integer,
    subject_id integer,
    teacher_id integer,
    room_id integer,
    timeslot_id integer,
    constraint_date date,
    day_of_week integer,
    CONSTRAINT ck_constraint_day CHECK (((day_of_week IS NULL) OR ((day_of_week >= 0) AND (day_of_week <= 6)))),
    CONSTRAINT ck_constraint_typed_shape CHECK ((((rule_type = 'specific_room'::public.constrainttype) AND (class_id IS NOT NULL) AND (subject_id IS NOT NULL) AND (room_id IS NOT NULL) AND (teacher_id IS NULL) AND (timeslot_id IS NULL) AND (constraint_date IS NULL) AND (day_of_week IS NULL)) OR ((rule_type = 'lock_time'::public.constrainttype) AND (class_id IS NOT NULL) AND (subject_id IS NOT NULL) AND (timeslot_id IS NOT NULL) AND (teacher_id IS NULL) AND (room_id IS NULL) AND (constraint_date IS NULL) AND (day_of_week IS NULL)) OR ((rule_type = 'teacher_preferred'::public.constrainttype) AND (teacher_id IS NOT NULL) AND (timeslot_id IS NOT NULL) AND (class_id IS NULL) AND (subject_id IS NULL) AND (room_id IS NULL) AND (constraint_date IS NULL) AND (day_of_week IS NULL)) OR ((rule_type = 'teacher_unavailable'::public.constrainttype) AND (teacher_id IS NOT NULL) AND (class_id IS NULL) AND (subject_id IS NULL) AND (room_id IS NULL) AND (((timeslot_id IS NOT NULL) AND (constraint_date IS NULL) AND (day_of_week IS NULL)) OR ((timeslot_id IS NULL) AND (constraint_date IS NOT NULL) AND (day_of_week IS NULL)) OR ((timeslot_id IS NULL) AND (constraint_date IS NULL) AND (day_of_week IS NOT NULL)) OR ((timeslot_id IS NOT NULL) AND (constraint_date IS NOT NULL) AND (day_of_week IS NULL))))))
);

ALTER TABLE ONLY public."constraint" FORCE ROW LEVEL SECURITY;


ALTER TABLE public."constraint" OWNER TO cronos_migrator;

--
-- Name: constraint_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.constraint_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.constraint_id_seq OWNER TO cronos_migrator;

--
-- Name: constraint_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.constraint_id_seq OWNED BY public."constraint".id;


--
-- Name: course; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.course (
    id integer NOT NULL,
    name character varying(150) NOT NULL,
    abbreviation character varying(10) NOT NULL,
    organization_id integer NOT NULL
);

ALTER TABLE ONLY public.course FORCE ROW LEVEL SECURITY;


ALTER TABLE public.course OWNER TO cronos_migrator;

--
-- Name: course_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.course_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.course_id_seq OWNER TO cronos_migrator;

--
-- Name: course_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.course_id_seq OWNED BY public.course.id;


--
-- Name: course_subject_link; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.course_subject_link (
    organization_id integer NOT NULL,
    course_id integer NOT NULL,
    subject_id integer NOT NULL
);

ALTER TABLE ONLY public.course_subject_link FORCE ROW LEVEL SECURITY;


ALTER TABLE public.course_subject_link OWNER TO cronos_migrator;

--
-- Name: curricular_assignment; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.curricular_assignment (
    id integer NOT NULL,
    organization_id integer NOT NULL,
    school_year_id integer NOT NULL,
    class_id integer NOT NULL,
    subject_id integer NOT NULL,
    teacher_id integer NOT NULL
);

ALTER TABLE ONLY public.curricular_assignment FORCE ROW LEVEL SECURITY;


ALTER TABLE public.curricular_assignment OWNER TO cronos_migrator;

--
-- Name: curricular_assignment_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.curricular_assignment_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.curricular_assignment_id_seq OWNER TO cronos_migrator;

--
-- Name: curricular_assignment_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.curricular_assignment_id_seq OWNED BY public.curricular_assignment.id;


--
-- Name: curricular_debt; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.curricular_debt (
    id integer NOT NULL,
    organization_id integer NOT NULL,
    assignment_id integer NOT NULL,
    origin character varying(160) NOT NULL,
    origin_revision integer NOT NULL,
    origin_date date NOT NULL,
    created_minutes integer NOT NULL,
    author_membership_id integer NOT NULL,
    reason text NOT NULL,
    recorded_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_curricular_debt_minutes_positive CHECK ((created_minutes > 0)),
    CONSTRAINT ck_curricular_debt_reason_nonempty CHECK ((length(TRIM(BOTH FROM reason)) > 0)),
    CONSTRAINT ck_curricular_debt_revision_positive CHECK ((origin_revision > 0))
);

ALTER TABLE ONLY public.curricular_debt FORCE ROW LEVEL SECURITY;


ALTER TABLE public.curricular_debt OWNER TO cronos_migrator;

--
-- Name: curricular_debt_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.curricular_debt_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.curricular_debt_id_seq OWNER TO cronos_migrator;

--
-- Name: curricular_debt_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.curricular_debt_id_seq OWNED BY public.curricular_debt.id;


--
-- Name: curricular_debt_revision; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.curricular_debt_revision (
    id integer NOT NULL,
    organization_id integer NOT NULL,
    debt_id integer NOT NULL,
    origin character varying(160) NOT NULL,
    revision integer NOT NULL,
    delta_minutes integer NOT NULL,
    author_membership_id integer NOT NULL,
    reason text NOT NULL,
    recorded_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_curricular_debt_revision_nonzero CHECK ((delta_minutes <> 0)),
    CONSTRAINT ck_curricular_debt_revision_number_positive CHECK ((revision > 0)),
    CONSTRAINT ck_curricular_debt_revision_reason_nonempty CHECK ((length(TRIM(BOTH FROM reason)) > 0))
);

ALTER TABLE ONLY public.curricular_debt_revision FORCE ROW LEVEL SECURITY;


ALTER TABLE public.curricular_debt_revision OWNER TO cronos_migrator;

--
-- Name: curricular_debt_revision_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.curricular_debt_revision_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.curricular_debt_revision_id_seq OWNER TO cronos_migrator;

--
-- Name: curricular_debt_revision_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.curricular_debt_revision_id_seq OWNED BY public.curricular_debt_revision.id;


--
-- Name: curricular_debt_settlement; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.curricular_debt_settlement (
    id integer NOT NULL,
    organization_id integer NOT NULL,
    debt_id integer NOT NULL,
    execution_id integer NOT NULL,
    minutes integer NOT NULL,
    reversal_of_id integer,
    CONSTRAINT ck_curricular_debt_settlement_nonzero CHECK ((minutes <> 0)),
    CONSTRAINT ck_curricular_debt_settlement_not_self_reversal CHECK (((reversal_of_id IS NULL) OR (reversal_of_id <> id)))
);

ALTER TABLE ONLY public.curricular_debt_settlement FORCE ROW LEVEL SECURITY;


ALTER TABLE public.curricular_debt_settlement OWNER TO cronos_migrator;

--
-- Name: curricular_debt_settlement_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.curricular_debt_settlement_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.curricular_debt_settlement_id_seq OWNER TO cronos_migrator;

--
-- Name: curricular_debt_settlement_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.curricular_debt_settlement_id_seq OWNED BY public.curricular_debt_settlement.id;


--
-- Name: curricular_execution; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.curricular_execution (
    id integer NOT NULL,
    organization_id integer NOT NULL,
    assignment_id integer NOT NULL,
    origin character varying(160) NOT NULL,
    revision integer NOT NULL,
    author_membership_id integer NOT NULL,
    reason text NOT NULL,
    recorded_at timestamp with time zone NOT NULL,
    planning_relevant boolean NOT NULL,
    reversal_of_id integer,
    CONSTRAINT ck_curricular_execution_not_self_reversal CHECK (((reversal_of_id IS NULL) OR (reversal_of_id <> id))),
    CONSTRAINT ck_curricular_execution_origin_nonempty CHECK ((length(TRIM(BOTH FROM origin)) > 0)),
    CONSTRAINT ck_curricular_execution_reason_nonempty CHECK ((length(TRIM(BOTH FROM reason)) > 0)),
    CONSTRAINT ck_curricular_execution_revision_positive CHECK ((revision > 0))
);

ALTER TABLE ONLY public.curricular_execution FORCE ROW LEVEL SECURITY;


ALTER TABLE public.curricular_execution OWNER TO cronos_migrator;

--
-- Name: curricular_execution_credit; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.curricular_execution_credit (
    id integer NOT NULL,
    organization_id integer NOT NULL,
    execution_id integer NOT NULL,
    module_id integer NOT NULL,
    offset_minutes integer NOT NULL,
    delta_minutes integer NOT NULL,
    CONSTRAINT ck_curricular_execution_credit_nonzero CHECK ((delta_minutes <> 0)),
    CONSTRAINT ck_curricular_execution_credit_offset CHECK ((offset_minutes >= 0))
);

ALTER TABLE ONLY public.curricular_execution_credit FORCE ROW LEVEL SECURITY;


ALTER TABLE public.curricular_execution_credit OWNER TO cronos_migrator;

--
-- Name: curricular_execution_credit_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.curricular_execution_credit_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.curricular_execution_credit_id_seq OWNER TO cronos_migrator;

--
-- Name: curricular_execution_credit_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.curricular_execution_credit_id_seq OWNED BY public.curricular_execution_credit.id;


--
-- Name: curricular_execution_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.curricular_execution_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.curricular_execution_id_seq OWNER TO cronos_migrator;

--
-- Name: curricular_execution_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.curricular_execution_id_seq OWNED BY public.curricular_execution.id;


--
-- Name: curricular_requirement; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.curricular_requirement (
    id integer NOT NULL,
    organization_id integer NOT NULL,
    assignment_id integer NOT NULL,
    module_id integer NOT NULL,
    sequence integer NOT NULL,
    required_minutes integer NOT NULL,
    CONSTRAINT ck_curricular_requirement_minutes_positive CHECK ((required_minutes > 0)),
    CONSTRAINT ck_curricular_requirement_sequence_positive CHECK ((sequence > 0))
);

ALTER TABLE ONLY public.curricular_requirement FORCE ROW LEVEL SECURITY;


ALTER TABLE public.curricular_requirement OWNER TO cronos_migrator;

--
-- Name: curricular_requirement_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.curricular_requirement_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.curricular_requirement_id_seq OWNER TO cronos_migrator;

--
-- Name: curricular_requirement_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.curricular_requirement_id_seq OWNED BY public.curricular_requirement.id;


--
-- Name: lesson_log; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.lesson_log (
    id integer NOT NULL,
    organization_id integer NOT NULL,
    operational_block_id integer,
    active_schedule_block_id integer,
    status public.lessonlogstatus NOT NULL,
    version integer NOT NULL,
    summary text,
    notes text,
    logged_by_membership_id integer,
    logged_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_lesson_log_exactly_one_target CHECK (((
CASE
    WHEN (operational_block_id IS NOT NULL) THEN 1
    ELSE 0
END +
CASE
    WHEN (active_schedule_block_id IS NOT NULL) THEN 1
    ELSE 0
END) = 1))
);

ALTER TABLE ONLY public.lesson_log FORCE ROW LEVEL SECURITY;


ALTER TABLE public.lesson_log OWNER TO cronos_migrator;

--
-- Name: lesson_log_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.lesson_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.lesson_log_id_seq OWNER TO cronos_migrator;

--
-- Name: lesson_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.lesson_log_id_seq OWNED BY public.lesson_log.id;


--
-- Name: lesson_occurrence; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.lesson_occurrence (
    id integer NOT NULL,
    organization_id integer NOT NULL,
    active_schedule_block_id integer,
    date date NOT NULL,
    class_id integer,
    subject_id integer,
    status public.lessonoccurrencestatus,
    revision integer NOT NULL,
    is_active boolean NOT NULL,
    version integer NOT NULL,
    created_by_membership_id integer,
    creation_source character varying(40),
    reason character varying(250),
    revoked_at timestamp with time zone,
    revoked_by_membership_id integer,
    revoked_reason character varying(250),
    planned_timeslot_id integer,
    planned_room_id integer,
    planned_generation_id character varying(100),
    planned_minutes integer NOT NULL,
    substitute_teacher_id integer,
    substitute_subject_id integer,
    planned_teacher_id integer,
    executed_teacher_id integer,
    planned_module_id integer,
    executed_module_id integer,
    given_minutes integer NOT NULL,
    decided_by_membership_id integer,
    decided_at timestamp with time zone,
    created_at timestamp with time zone,
    CONSTRAINT ck_occurrence_given_minutes CHECK ((given_minutes >= 0)),
    CONSTRAINT ck_occurrence_planned_minutes CHECK ((planned_minutes >= 0))
);

ALTER TABLE ONLY public.lesson_occurrence FORCE ROW LEVEL SECURITY;


ALTER TABLE public.lesson_occurrence OWNER TO cronos_migrator;

--
-- Name: lesson_occurrence_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.lesson_occurrence_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.lesson_occurrence_id_seq OWNER TO cronos_migrator;

--
-- Name: lesson_occurrence_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.lesson_occurrence_id_seq OWNED BY public.lesson_occurrence.id;


--
-- Name: member_access_operation; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.member_access_operation (
    id integer NOT NULL,
    organization_id integer NOT NULL,
    membership_id integer,
    account_id integer,
    target_email character varying(255) NOT NULL,
    operation_type public.memberaccessoperationtype NOT NULL,
    operation_status public.memberaccessoperationstatus NOT NULL,
    idempotency_key character varying(160) NOT NULL,
    intended_capabilities_json json NOT NULL,
    intended_clerk_role character varying(40),
    previous_access_snapshot_json json,
    draft_payload_json json,
    clerk_org_id character varying(255),
    clerk_user_id character varying(255),
    clerk_membership_id character varying(255),
    clerk_invitation_id character varying(255),
    provider_error_category character varying(80),
    provider_error_safe_message character varying(240),
    provider_error_reference character varying(120),
    compensation_attempted_at timestamp with time zone,
    support_required_at timestamp with time zone,
    support_resolution_action character varying(80),
    support_resolved_by_user_id integer,
    support_resolved_at timestamp with time zone,
    support_resolution_note character varying(500),
    created_by_membership_id integer NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);

ALTER TABLE ONLY public.member_access_operation FORCE ROW LEVEL SECURITY;


ALTER TABLE public.member_access_operation OWNER TO cronos_migrator;

--
-- Name: member_access_operation_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.member_access_operation_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.member_access_operation_id_seq OWNER TO cronos_migrator;

--
-- Name: member_access_operation_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.member_access_operation_id_seq OWNED BY public.member_access_operation.id;


--
-- Name: module; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.module (
    id integer NOT NULL,
    organization_id integer NOT NULL,
    name character varying(150) NOT NULL,
    code character varying(50),
    required_minutes integer NOT NULL,
    "order" integer NOT NULL,
    subject_id integer NOT NULL,
    CONSTRAINT ck_module_order_nonnegative CHECK (("order" >= 0)),
    CONSTRAINT ck_module_required_minutes CHECK ((required_minutes > 0))
);

ALTER TABLE ONLY public.module FORCE ROW LEVEL SECURITY;


ALTER TABLE public.module OWNER TO cronos_migrator;

--
-- Name: module_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.module_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.module_id_seq OWNER TO cronos_migrator;

--
-- Name: module_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.module_id_seq OWNED BY public.module.id;


--
-- Name: occurrence_operational_event; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.occurrence_operational_event (
    id integer NOT NULL,
    organization_id integer NOT NULL,
    occurrence_id integer,
    active_schedule_block_id integer,
    actor_membership_id integer,
    event_type character varying(50) NOT NULL,
    result character varying(50) NOT NULL,
    decision_status character varying(20),
    detail character varying(240),
    created_at timestamp with time zone
);

ALTER TABLE ONLY public.occurrence_operational_event FORCE ROW LEVEL SECURITY;


ALTER TABLE public.occurrence_operational_event OWNER TO cronos_migrator;

--
-- Name: occurrence_operational_event_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.occurrence_operational_event_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.occurrence_operational_event_id_seq OWNER TO cronos_migrator;

--
-- Name: occurrence_operational_event_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.occurrence_operational_event_id_seq OWNED BY public.occurrence_operational_event.id;


--
-- Name: operational_schedule_block; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.operational_schedule_block (
    id integer NOT NULL,
    organization_id integer NOT NULL,
    source_occurrence_id integer NOT NULL,
    source_occurrence_revision integer NOT NULL,
    planned_active_schedule_block_id integer,
    date date NOT NULL,
    timeslot_id integer NOT NULL,
    room_id integer,
    class_id integer NOT NULL,
    teacher_id integer NOT NULL,
    subject_id integer NOT NULL,
    module_id integer,
    status public.operationalblockstatus NOT NULL,
    execution_status public.operationalblockexecutionstatus NOT NULL,
    created_by_membership_id integer,
    created_at timestamp with time zone NOT NULL,
    cancelled_at timestamp with time zone
);

ALTER TABLE ONLY public.operational_schedule_block FORCE ROW LEVEL SECURITY;


ALTER TABLE public.operational_schedule_block OWNER TO cronos_migrator;

--
-- Name: operational_schedule_block_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.operational_schedule_block_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.operational_schedule_block_id_seq OWNER TO cronos_migrator;

--
-- Name: operational_schedule_block_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.operational_schedule_block_id_seq OWNED BY public.operational_schedule_block.id;


--
-- Name: organization; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.organization (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    clerk_org_id character varying(255),
    plan_status public.organizationplanstatus NOT NULL,
    foundation_status public.organizationfoundationstatus DEFAULT 'NOT_STARTED'::public.organizationfoundationstatus NOT NULL,
    foundation_completed_at timestamp with time zone,
    first_real_schedule_approved_at timestamp with time zone,
    CONSTRAINT chk_organization_first_real_schedule_requires_completed CHECK (((first_real_schedule_approved_at IS NULL) OR (foundation_status = 'COMPLETED'::public.organizationfoundationstatus))),
    CONSTRAINT chk_organization_foundation_completed_at_required CHECK (((foundation_status <> 'COMPLETED'::public.organizationfoundationstatus) OR (foundation_completed_at IS NOT NULL)))
);

ALTER TABLE ONLY public.organization FORCE ROW LEVEL SECURITY;


ALTER TABLE public.organization OWNER TO cronos_migrator;

--
-- Name: organization_foundation_draft; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.organization_foundation_draft (
    organization_id integer NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    current_step smallint DEFAULT '1'::smallint NOT NULL,
    payload_json jsonb NOT NULL,
    updated_by_membership_id integer NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT chk_organization_foundation_draft_current_step CHECK (((current_step >= 1) AND (current_step <= 9))),
    CONSTRAINT chk_organization_foundation_draft_version CHECK ((version > 0))
);

ALTER TABLE ONLY public.organization_foundation_draft FORCE ROW LEVEL SECURITY;


ALTER TABLE public.organization_foundation_draft OWNER TO cronos_migrator;

--
-- Name: organization_grid_settings; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.organization_grid_settings (
    id integer NOT NULL,
    organization_id integer NOT NULL,
    lunch_window_start time without time zone,
    lunch_window_end time without time zone,
    lunch_min_duration_minutes integer
);

ALTER TABLE ONLY public.organization_grid_settings FORCE ROW LEVEL SECURITY;


ALTER TABLE public.organization_grid_settings OWNER TO cronos_migrator;

--
-- Name: organization_grid_settings_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.organization_grid_settings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.organization_grid_settings_id_seq OWNER TO cronos_migrator;

--
-- Name: organization_grid_settings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.organization_grid_settings_id_seq OWNED BY public.organization_grid_settings.id;


--
-- Name: organization_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.organization_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.organization_id_seq OWNER TO cronos_migrator;

--
-- Name: organization_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.organization_id_seq OWNED BY public.organization.id;


--
-- Name: organization_legal_acceptance; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.organization_legal_acceptance (
    id integer NOT NULL,
    organization_id integer NOT NULL,
    accepted_by_membership_id_snapshot integer NOT NULL,
    controller_legal_name character varying(200),
    controller_registration_number character varying(50),
    controller_registered_address character varying(500),
    controller_contact_email character varying(254),
    representative_name character varying(150),
    representative_role character varying(100),
    authority_confirmed boolean NOT NULL,
    terms_version character varying(40) NOT NULL,
    dpa_version character varying(40) NOT NULL,
    accepted_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    privacy_version character varying(40),
    CONSTRAINT chk_legal_acceptance_address CHECK (((char_length(TRIM(BOTH FROM controller_registered_address)) >= 1) AND (char_length(TRIM(BOTH FROM controller_registered_address)) <= 500))),
    CONSTRAINT chk_legal_acceptance_authority CHECK ((authority_confirmed IS TRUE)),
    CONSTRAINT chk_legal_acceptance_contact_email CHECK (((char_length(TRIM(BOTH FROM controller_contact_email)) >= 3) AND (char_length(TRIM(BOTH FROM controller_contact_email)) <= 254))),
    CONSTRAINT chk_legal_acceptance_controller_name CHECK (((char_length(TRIM(BOTH FROM controller_legal_name)) >= 1) AND (char_length(TRIM(BOTH FROM controller_legal_name)) <= 200))),
    CONSTRAINT chk_legal_acceptance_registration_number CHECK (((char_length(TRIM(BOTH FROM controller_registration_number)) >= 1) AND (char_length(TRIM(BOTH FROM controller_registration_number)) <= 50))),
    CONSTRAINT chk_legal_acceptance_representative_name CHECK (((char_length(TRIM(BOTH FROM representative_name)) >= 1) AND (char_length(TRIM(BOTH FROM representative_name)) <= 150))),
    CONSTRAINT chk_legal_acceptance_representative_role CHECK (((char_length(TRIM(BOTH FROM representative_role)) >= 1) AND (char_length(TRIM(BOTH FROM representative_role)) <= 100)))
);

ALTER TABLE ONLY public.organization_legal_acceptance FORCE ROW LEVEL SECURITY;


ALTER TABLE public.organization_legal_acceptance OWNER TO cronos_migrator;

--
-- Name: organization_legal_acceptance_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.organization_legal_acceptance_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.organization_legal_acceptance_id_seq OWNER TO cronos_migrator;

--
-- Name: organization_legal_acceptance_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.organization_legal_acceptance_id_seq OWNED BY public.organization_legal_acceptance.id;


--
-- Name: organization_membership; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.organization_membership (
    id integer NOT NULL,
    organization_id integer NOT NULL,
    account_id integer NOT NULL,
    organization_display_name character varying(150) NOT NULL,
    lifecycle_status public.membershiplifecyclestatus NOT NULL,
    access_status public.membershipaccessstatus NOT NULL,
    teacher_access_mode public.teacheraccessmode,
    can_admin boolean NOT NULL,
    can_teach boolean NOT NULL,
    clerk_membership_id character varying(255),
    clerk_invitation_id character varying(255),
    clerk_invitation_status public.clerkinvitationstatus,
    invitation_expires_at timestamp with time zone,
    access_error_category character varying(80),
    access_error_safe_message character varying(240),
    access_block_reason character varying(120),
    created_by_membership_id integer,
    updated_by_membership_id integer,
    lock_version integer NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_membership_active_has_account CHECK (((access_status <> 'active'::public.membershipaccessstatus) OR (account_id IS NOT NULL))),
    CONSTRAINT ck_membership_admin_not_scheduler_only CHECK ((NOT (can_admin AND (teacher_access_mode = 'scheduler_only'::public.teacheraccessmode)))),
    CONSTRAINT ck_membership_has_capability CHECK ((can_admin OR can_teach)),
    CONSTRAINT ck_membership_teacher_mode CHECK ((can_teach = (teacher_access_mode IS NOT NULL)))
);

ALTER TABLE ONLY public.organization_membership FORCE ROW LEVEL SECURITY;


ALTER TABLE public.organization_membership OWNER TO cronos_migrator;

--
-- Name: organization_membership_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.organization_membership_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.organization_membership_id_seq OWNER TO cronos_migrator;

--
-- Name: organization_membership_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.organization_membership_id_seq OWNED BY public.organization_membership.id;


--
-- Name: organization_settings; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.organization_settings (
    id integer NOT NULL,
    organization_id integer NOT NULL,
    school_start_date date,
    school_hard_end_date date,
    repair_stability_window_days integer,
    automatic_holidays_enabled boolean DEFAULT false NOT NULL
);

ALTER TABLE ONLY public.organization_settings FORCE ROW LEVEL SECURITY;


ALTER TABLE public.organization_settings OWNER TO cronos_migrator;

--
-- Name: organization_settings_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.organization_settings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.organization_settings_id_seq OWNER TO cronos_migrator;

--
-- Name: organization_settings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.organization_settings_id_seq OWNED BY public.organization_settings.id;


--
-- Name: planned_recovery_links; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.planned_recovery_links (
    id integer NOT NULL,
    organization_id integer NOT NULL,
    school_year_id integer NOT NULL,
    debt_occurrence_id integer NOT NULL,
    debt_occurrence_revision integer NOT NULL,
    planned_active_block_id integer,
    planned_draft_block_id integer,
    planned_recovery_minutes integer NOT NULL,
    delivered_recovery_minutes integer NOT NULL,
    delivered_lesson_log_id integer,
    delivered_at timestamp with time zone,
    class_id integer NOT NULL,
    subject_id integer NOT NULL,
    teacher_id integer,
    status public.plannedrecoverylinkstatus NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_planned_recovery_links_debt_revision_positive CHECK ((debt_occurrence_revision > 0)),
    CONSTRAINT ck_planned_recovery_links_delivered_minutes_range CHECK (((delivered_recovery_minutes >= 0) AND (delivered_recovery_minutes <= planned_recovery_minutes))),
    CONSTRAINT ck_planned_recovery_links_delivery_evidence CHECK ((((status = 'DELIVERED'::public.plannedrecoverylinkstatus) AND (planned_active_block_id IS NOT NULL) AND (delivered_recovery_minutes > 0) AND (delivered_lesson_log_id IS NOT NULL) AND (delivered_at IS NOT NULL)) OR ((status <> 'DELIVERED'::public.plannedrecoverylinkstatus) AND (delivered_recovery_minutes = 0) AND (delivered_lesson_log_id IS NULL) AND (delivered_at IS NULL)))),
    CONSTRAINT ck_planned_recovery_links_has_target CHECK (((planned_active_block_id IS NOT NULL) OR (planned_draft_block_id IS NOT NULL))),
    CONSTRAINT ck_planned_recovery_links_planned_minutes_positive CHECK ((planned_recovery_minutes > 0))
);

ALTER TABLE ONLY public.planned_recovery_links FORCE ROW LEVEL SECURITY;


ALTER TABLE public.planned_recovery_links OWNER TO cronos_migrator;

--
-- Name: planned_recovery_links_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.planned_recovery_links_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.planned_recovery_links_id_seq OWNER TO cronos_migrator;

--
-- Name: planned_recovery_links_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.planned_recovery_links_id_seq OWNED BY public.planned_recovery_links.id;


--
-- Name: progress_ledger_entry; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.progress_ledger_entry (
    id integer NOT NULL,
    organization_id integer NOT NULL,
    source_type character varying(40) NOT NULL,
    source_id integer NOT NULL,
    source_revision integer,
    class_id integer NOT NULL,
    module_id integer NOT NULL,
    completed_minutes_delta integer NOT NULL,
    debt_minutes_delta integer NOT NULL,
    idempotency_key character varying(160) NOT NULL,
    created_by_membership_id integer,
    created_at timestamp with time zone NOT NULL,
    reverses_ledger_entry_id integer,
    CONSTRAINT ck_progress_ledger_nonzero_delta CHECK (((completed_minutes_delta <> 0) OR (debt_minutes_delta <> 0)))
);

ALTER TABLE ONLY public.progress_ledger_entry FORCE ROW LEVEL SECURITY;


ALTER TABLE public.progress_ledger_entry OWNER TO cronos_migrator;

--
-- Name: progress_ledger_entry_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.progress_ledger_entry_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.progress_ledger_entry_id_seq OWNER TO cronos_migrator;

--
-- Name: progress_ledger_entry_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.progress_ledger_entry_id_seq OWNED BY public.progress_ledger_entry.id;


--
-- Name: room; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.room (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    capacity integer NOT NULL,
    type public.roomtype NOT NULL,
    organization_id integer NOT NULL
);

ALTER TABLE ONLY public.room FORCE ROW LEVEL SECURITY;


ALTER TABLE public.room OWNER TO cronos_migrator;

--
-- Name: room_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.room_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.room_id_seq OWNER TO cronos_migrator;

--
-- Name: room_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.room_id_seq OWNED BY public.room.id;


--
-- Name: schedule_diff_entries; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.schedule_diff_entries (
    id integer NOT NULL,
    organization_id integer NOT NULL,
    school_year_id integer NOT NULL,
    generation_job_id integer NOT NULL,
    draft_id integer NOT NULL,
    class_id integer NOT NULL,
    subject_id integer NOT NULL,
    teacher_id integer NOT NULL,
    before_active_block_id integer,
    after_draft_block_id integer,
    before_date date,
    before_timeslot_id integer,
    before_room_id integer,
    after_date date,
    after_timeslot_id integer,
    after_room_id integer,
    before_snapshot_json json,
    after_snapshot_json json,
    change_type public.schedulediffchangetype NOT NULL,
    impact_scope public.schedulediffscope NOT NULL,
    reason_code character varying(50),
    reason_message text,
    recovery_link_impact_json json,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_schedule_diff_entries_sides CHECK ((((change_type = 'ADDED'::public.schedulediffchangetype) AND (before_snapshot_json IS NULL) AND (after_snapshot_json IS NOT NULL)) OR ((change_type = 'REMOVED'::public.schedulediffchangetype) AND (before_snapshot_json IS NOT NULL) AND (after_snapshot_json IS NULL)) OR ((change_type <> ALL (ARRAY['ADDED'::public.schedulediffchangetype, 'REMOVED'::public.schedulediffchangetype])) AND (before_snapshot_json IS NOT NULL) AND (after_snapshot_json IS NOT NULL))))
);

ALTER TABLE ONLY public.schedule_diff_entries FORCE ROW LEVEL SECURITY;


ALTER TABLE public.schedule_diff_entries OWNER TO cronos_migrator;

--
-- Name: schedule_diff_entries_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.schedule_diff_entries_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.schedule_diff_entries_id_seq OWNER TO cronos_migrator;

--
-- Name: schedule_diff_entries_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.schedule_diff_entries_id_seq OWNED BY public.schedule_diff_entries.id;


--
-- Name: schedule_draft_blocks; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.schedule_draft_blocks (
    id integer NOT NULL,
    organization_id integer NOT NULL,
    school_year_id integer NOT NULL,
    draft_id integer NOT NULL,
    source_active_block_id integer,
    stable_block_key character varying(64) NOT NULL,
    class_id integer NOT NULL,
    subject_id integer NOT NULL,
    teacher_id integer NOT NULL,
    room_id integer NOT NULL,
    room_type_id public.roomtype,
    date date NOT NULL,
    timeslot_id integer NOT NULL,
    duration_minutes integer NOT NULL,
    module_sequence_index integer,
    is_recovery_block boolean NOT NULL,
    recovery_source_occurrence_id integer,
    recovery_source_occurrence_revision integer,
    change_type public.scheduledraftblockchangetype NOT NULL,
    reason_code character varying(50),
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_schedule_draft_blocks_change_source CHECK ((((change_type = 'ADDED'::public.scheduledraftblockchangetype) AND (source_active_block_id IS NULL)) OR ((change_type <> 'ADDED'::public.scheduledraftblockchangetype) AND (source_active_block_id IS NOT NULL)))),
    CONSTRAINT ck_schedule_draft_blocks_duration_positive CHECK ((duration_minutes > 0)),
    CONSTRAINT ck_schedule_draft_blocks_module_sequence_nonnegative CHECK (((module_sequence_index IS NULL) OR (module_sequence_index >= 0))),
    CONSTRAINT ck_schedule_draft_blocks_recovery_revision_positive CHECK (((recovery_source_occurrence_revision IS NULL) OR (recovery_source_occurrence_revision > 0))),
    CONSTRAINT ck_schedule_draft_blocks_recovery_source CHECK (((is_recovery_block AND (recovery_source_occurrence_id IS NOT NULL) AND (recovery_source_occurrence_revision IS NOT NULL)) OR ((NOT is_recovery_block) AND (recovery_source_occurrence_id IS NULL) AND (recovery_source_occurrence_revision IS NULL)))),
    CONSTRAINT ck_schedule_draft_blocks_stable_key_nonempty CHECK ((length(TRIM(BOTH FROM stable_block_key)) > 0))
);

ALTER TABLE ONLY public.schedule_draft_blocks FORCE ROW LEVEL SECURITY;


ALTER TABLE public.schedule_draft_blocks OWNER TO cronos_migrator;

--
-- Name: schedule_draft_blocks_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.schedule_draft_blocks_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.schedule_draft_blocks_id_seq OWNER TO cronos_migrator;

--
-- Name: schedule_draft_blocks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.schedule_draft_blocks_id_seq OWNED BY public.schedule_draft_blocks.id;


--
-- Name: schedule_drafts; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.schedule_drafts (
    id integer NOT NULL,
    organization_id integer NOT NULL,
    school_year_id integer NOT NULL,
    generation_job_id integer NOT NULL,
    strategy public.schedulegenerationstrategy NOT NULL,
    draft_state public.scheduledraftstate NOT NULL,
    result_category public.schedulegenerationresultcategory NOT NULL,
    trigger_type public.schedulegenerationtrigger NOT NULL,
    generation_input_fingerprint character varying(64) NOT NULL,
    scheduler_state_version_used integer,
    debt_basis_fingerprint character varying(64),
    repair_policy_snapshot_json json,
    repair_policy_snapshot_hash character varying(64),
    editable_start_date date,
    recovery_escalation_level character varying(50),
    adaptation_level character varying(50),
    projected_completion_date date NOT NULL,
    hard_end_date date NOT NULL,
    summary_json json NOT NULL,
    partial_recovery_blocker_type character varying(50),
    main_blocker_message text,
    recommended_actions_json json,
    warnings_json json,
    metrics_json json,
    stale_reason text,
    invalidated_reason text,
    created_by_membership_id integer NOT NULL,
    created_at timestamp with time zone NOT NULL,
    decided_by_membership_id integer,
    decided_at timestamp with time zone,
    CONSTRAINT ck_schedule_drafts_adaptive_editable_start CHECK (((strategy = 'COMPLETE_GENERATION'::public.schedulegenerationstrategy) OR (editable_start_date IS NOT NULL))),
    CONSTRAINT ck_schedule_drafts_completion_by_hard_end CHECK ((projected_completion_date <= hard_end_date)),
    CONSTRAINT ck_schedule_drafts_decision_consistency CHECK ((((draft_state = 'PENDING'::public.scheduledraftstate) AND (decided_at IS NULL) AND (decided_by_membership_id IS NULL)) OR ((draft_state <> 'PENDING'::public.scheduledraftstate) AND (decided_at IS NOT NULL)))),
    CONSTRAINT ck_schedule_drafts_has_valid_output CHECK ((result_category <> 'NO_VALID_OUTPUT'::public.schedulegenerationresultcategory)),
    CONSTRAINT ck_schedule_drafts_invalidated_reason CHECK ((((draft_state = 'INVALIDATED'::public.scheduledraftstate) AND (invalidated_reason IS NOT NULL)) OR ((draft_state <> 'INVALIDATED'::public.scheduledraftstate) AND (invalidated_reason IS NULL)))),
    CONSTRAINT ck_schedule_drafts_stale_reason CHECK ((((draft_state = 'STALE'::public.scheduledraftstate) AND (stale_reason IS NOT NULL)) OR ((draft_state <> 'STALE'::public.scheduledraftstate) AND (stale_reason IS NULL)))),
    CONSTRAINT ck_schedule_drafts_state_version_nonnegative CHECK (((scheduler_state_version_used IS NULL) OR (scheduler_state_version_used >= 0)))
);

ALTER TABLE ONLY public.schedule_drafts FORCE ROW LEVEL SECURITY;


ALTER TABLE public.schedule_drafts OWNER TO cronos_migrator;

--
-- Name: schedule_drafts_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.schedule_drafts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.schedule_drafts_id_seq OWNER TO cronos_migrator;

--
-- Name: schedule_drafts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.schedule_drafts_id_seq OWNED BY public.schedule_drafts.id;


--
-- Name: schedule_generation_job; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.schedule_generation_job (
    id integer NOT NULL,
    organization_id integer NOT NULL,
    school_year_id integer NOT NULL,
    requested_by_membership_id integer,
    strategy public.schedulegenerationstrategy NOT NULL,
    trigger_type public.schedulegenerationtrigger,
    job_status public.schedulegenerationjobstatus NOT NULL,
    result_category public.schedulegenerationresultcategory,
    generation_input_fingerprint character varying(64),
    debt_basis_fingerprint character varying(64),
    scheduler_state_version_used integer,
    repair_policy_snapshot_hash character varying(64),
    input_snapshot_json json,
    queued_at timestamp with time zone NOT NULL,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    deadline_at timestamp with time zone,
    duration_ms integer,
    cancellation_requested_at timestamp with time zone,
    failure_code character varying(50),
    failure_message text,
    idempotency_key character varying(100),
    failure_reference character varying(32),
    CONSTRAINT ck_schedule_generation_job_duration_nonnegative CHECK (((duration_ms IS NULL) OR (duration_ms >= 0))),
    CONSTRAINT ck_schedule_generation_job_finished_after_started CHECK (((finished_at IS NULL) OR ((started_at IS NOT NULL) AND (finished_at >= started_at)))),
    CONSTRAINT ck_schedule_generation_job_result_consistency CHECK ((((job_status = 'SUCCEEDED'::public.schedulegenerationjobstatus) AND (result_category = ANY (ARRAY['COMPLETE_SUCCESS'::public.schedulegenerationresultcategory, 'PARTIAL_RECOVERY'::public.schedulegenerationresultcategory]))) OR ((job_status = 'NO_VALID_OUTPUT'::public.schedulegenerationjobstatus) AND (result_category = 'NO_VALID_OUTPUT'::public.schedulegenerationresultcategory)) OR ((job_status <> ALL (ARRAY['SUCCEEDED'::public.schedulegenerationjobstatus, 'NO_VALID_OUTPUT'::public.schedulegenerationjobstatus])) AND (result_category IS NULL)))),
    CONSTRAINT ck_schedule_generation_job_started_after_queued CHECK (((started_at IS NULL) OR (started_at >= queued_at))),
    CONSTRAINT ck_schedule_generation_job_terminal_finished CHECK ((((job_status = ANY (ARRAY['CANCELED'::public.schedulegenerationjobstatus, 'SUCCEEDED'::public.schedulegenerationjobstatus, 'FAILED'::public.schedulegenerationjobstatus, 'NO_VALID_OUTPUT'::public.schedulegenerationjobstatus])) AND (finished_at IS NOT NULL)) OR ((job_status <> ALL (ARRAY['CANCELED'::public.schedulegenerationjobstatus, 'SUCCEEDED'::public.schedulegenerationjobstatus, 'FAILED'::public.schedulegenerationjobstatus, 'NO_VALID_OUTPUT'::public.schedulegenerationjobstatus])) AND (finished_at IS NULL))))
);

ALTER TABLE ONLY public.schedule_generation_job FORCE ROW LEVEL SECURITY;


ALTER TABLE public.schedule_generation_job OWNER TO cronos_migrator;

--
-- Name: schedule_generation_job_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.schedule_generation_job_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.schedule_generation_job_id_seq OWNER TO cronos_migrator;

--
-- Name: schedule_generation_job_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.schedule_generation_job_id_seq OWNED BY public.schedule_generation_job.id;


--
-- Name: scheduler_job_v1; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.scheduler_job_v1 (
    id integer NOT NULL,
    organization_id integer NOT NULL,
    school_year_id integer NOT NULL,
    strategy character varying(30) NOT NULL,
    status character varying(20) NOT NULL,
    origin character varying(160) NOT NULL,
    revision integer NOT NULL,
    attempt_token integer NOT NULL,
    requested_by_membership_id integer,
    base_version_id integer,
    input_revision_used integer,
    planning_revision_used integer,
    snapshot_digest character varying(64),
    result_code character varying(50),
    stop_reason character varying(50),
    cancellation_requested_at timestamp with time zone,
    heartbeat_at timestamp with time zone,
    queued_at timestamp with time zone NOT NULL,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    CONSTRAINT ck_scheduler_job_v1_attempt_positive CHECK ((attempt_token > 0)),
    CONSTRAINT ck_scheduler_job_v1_revision_positive CHECK ((revision > 0)),
    CONSTRAINT ck_scheduler_job_v1_status CHECK (((status)::text = ANY ((ARRAY['QUEUED'::character varying, 'RUNNING'::character varying, 'VALIDATING'::character varying, 'SUCCEEDED'::character varying, 'CANCELLED'::character varying, 'STALE'::character varying, 'FAILED'::character varying, 'INFEASIBLE'::character varying, 'INCONCLUSIVE'::character varying])::text[]))),
    CONSTRAINT ck_scheduler_job_v1_strategy CHECK (((strategy)::text = ANY ((ARRAY['COMPLETE_GENERATION'::character varying, 'ADAPTIVE_RECOVERY'::character varying])::text[]))),
    CONSTRAINT ck_scheduler_job_v1_terminal_finished CHECK (((((status)::text = ANY ((ARRAY['SUCCEEDED'::character varying, 'CANCELLED'::character varying, 'STALE'::character varying, 'FAILED'::character varying, 'INFEASIBLE'::character varying, 'INCONCLUSIVE'::character varying])::text[])) AND (finished_at IS NOT NULL)) OR (((status)::text <> ALL ((ARRAY['SUCCEEDED'::character varying, 'CANCELLED'::character varying, 'STALE'::character varying, 'FAILED'::character varying, 'INFEASIBLE'::character varying, 'INCONCLUSIVE'::character varying])::text[])) AND (finished_at IS NULL))))
);

ALTER TABLE ONLY public.scheduler_job_v1 FORCE ROW LEVEL SECURITY;


ALTER TABLE public.scheduler_job_v1 OWNER TO cronos_migrator;

--
-- Name: scheduler_job_v1_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.scheduler_job_v1_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.scheduler_job_v1_id_seq OWNER TO cronos_migrator;

--
-- Name: scheduler_job_v1_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.scheduler_job_v1_id_seq OWNED BY public.scheduler_job_v1.id;


--
-- Name: scheduler_lesson_log_v1; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.scheduler_lesson_log_v1 (
    id integer NOT NULL,
    organization_id integer NOT NULL,
    school_year_id integer NOT NULL,
    lesson_id integer NOT NULL,
    status character varying(20) NOT NULL,
    summary text,
    notes text,
    revision integer DEFAULT 1 NOT NULL,
    logged_by_membership_id integer NOT NULL,
    logged_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_scheduler_lesson_log_v1_revision CHECK ((revision > 0)),
    CONSTRAINT ck_scheduler_lesson_log_v1_status CHECK (((status)::text = ANY ((ARRAY['COMPLETED'::character varying, 'OCCURRENCE'::character varying, 'REVOKED'::character varying])::text[])))
);

ALTER TABLE ONLY public.scheduler_lesson_log_v1 FORCE ROW LEVEL SECURITY;


ALTER TABLE public.scheduler_lesson_log_v1 OWNER TO cronos_migrator;

--
-- Name: scheduler_lesson_log_v1_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.scheduler_lesson_log_v1_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.scheduler_lesson_log_v1_id_seq OWNER TO cronos_migrator;

--
-- Name: scheduler_lesson_log_v1_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.scheduler_lesson_log_v1_id_seq OWNED BY public.scheduler_lesson_log_v1.id;


--
-- Name: scheduler_lesson_slice_v1; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.scheduler_lesson_slice_v1 (
    id integer NOT NULL,
    organization_id integer NOT NULL,
    school_year_id integer NOT NULL,
    lesson_id integer NOT NULL,
    module_id integer NOT NULL,
    offset_minutes integer NOT NULL,
    minutes integer NOT NULL,
    CONSTRAINT ck_scheduler_lesson_slice_v1_minutes CHECK ((minutes > 0)),
    CONSTRAINT ck_scheduler_lesson_slice_v1_offset CHECK ((offset_minutes >= 0))
);

ALTER TABLE ONLY public.scheduler_lesson_slice_v1 FORCE ROW LEVEL SECURITY;


ALTER TABLE public.scheduler_lesson_slice_v1 OWNER TO cronos_migrator;

--
-- Name: scheduler_lesson_slice_v1_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.scheduler_lesson_slice_v1_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.scheduler_lesson_slice_v1_id_seq OWNER TO cronos_migrator;

--
-- Name: scheduler_lesson_slice_v1_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.scheduler_lesson_slice_v1_id_seq OWNED BY public.scheduler_lesson_slice_v1.id;


--
-- Name: scheduler_lesson_v1; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.scheduler_lesson_v1 (
    id integer NOT NULL,
    organization_id integer NOT NULL,
    school_year_id integer NOT NULL,
    version_id integer NOT NULL,
    assignment_id integer NOT NULL,
    stable_key character varying(64) NOT NULL,
    school_date date NOT NULL,
    starts_at timestamp with time zone NOT NULL,
    ends_at timestamp with time zone NOT NULL,
    room_id integer NOT NULL,
    physical_minutes integer NOT NULL,
    credit_minutes integer NOT NULL,
    source_lesson_id integer,
    CONSTRAINT ck_scheduler_lesson_v1_credit CHECK (((credit_minutes > 0) AND (credit_minutes <= physical_minutes))),
    CONSTRAINT ck_scheduler_lesson_v1_interval CHECK ((ends_at > starts_at)),
    CONSTRAINT ck_scheduler_lesson_v1_key CHECK ((length(TRIM(BOTH FROM stable_key)) > 0)),
    CONSTRAINT ck_scheduler_lesson_v1_physical CHECK ((physical_minutes > 0)),
    CONSTRAINT ck_scheduler_lesson_v1_physical_matches_interval CHECK ((((physical_minutes * 60))::numeric = EXTRACT(epoch FROM (ends_at - starts_at))))
);

ALTER TABLE ONLY public.scheduler_lesson_v1 FORCE ROW LEVEL SECURITY;


ALTER TABLE public.scheduler_lesson_v1 OWNER TO cronos_migrator;

--
-- Name: scheduler_lesson_v1_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.scheduler_lesson_v1_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.scheduler_lesson_v1_id_seq OWNER TO cronos_migrator;

--
-- Name: scheduler_lesson_v1_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.scheduler_lesson_v1_id_seq OWNED BY public.scheduler_lesson_v1.id;


--
-- Name: scheduler_proposal_v1; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.scheduler_proposal_v1 (
    id integer NOT NULL,
    organization_id integer NOT NULL,
    school_year_id integer NOT NULL,
    job_id integer NOT NULL,
    version_id integer,
    base_version_id integer,
    status character varying(20) NOT NULL,
    snapshot_digest character varying(64) NOT NULL,
    policy_version character varying(64) NOT NULL,
    input_revision_used integer NOT NULL,
    planning_revision_used integer NOT NULL,
    metrics_json jsonb,
    diff_json jsonb,
    reason text,
    created_at timestamp with time zone NOT NULL,
    decided_at timestamp with time zone,
    decided_by_membership_id integer,
    CONSTRAINT ck_scheduler_proposal_v1_decision CHECK (((((status)::text = 'PENDING'::text) AND (decided_at IS NULL) AND (decided_by_membership_id IS NULL)) OR (((status)::text <> 'PENDING'::text) AND (decided_at IS NOT NULL)))),
    CONSTRAINT ck_scheduler_proposal_v1_digest_length CHECK ((length((snapshot_digest)::text) = 64)),
    CONSTRAINT ck_scheduler_proposal_v1_input_revision CHECK ((input_revision_used >= 0)),
    CONSTRAINT ck_scheduler_proposal_v1_planning_revision CHECK ((planning_revision_used >= 0)),
    CONSTRAINT ck_scheduler_proposal_v1_policy CHECK ((length(TRIM(BOTH FROM policy_version)) > 0)),
    CONSTRAINT ck_scheduler_proposal_v1_status CHECK (((status)::text = ANY ((ARRAY['PENDING'::character varying, 'APPROVED'::character varying, 'REJECTED'::character varying, 'STALE'::character varying, 'SUPERSEDED'::character varying])::text[])))
);

ALTER TABLE ONLY public.scheduler_proposal_v1 FORCE ROW LEVEL SECURITY;


ALTER TABLE public.scheduler_proposal_v1 OWNER TO cronos_migrator;

--
-- Name: scheduler_proposal_v1_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.scheduler_proposal_v1_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.scheduler_proposal_v1_id_seq OWNER TO cronos_migrator;

--
-- Name: scheduler_proposal_v1_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.scheduler_proposal_v1_id_seq OWNED BY public.scheduler_proposal_v1.id;


--
-- Name: scheduler_recovery_reservation_v1; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.scheduler_recovery_reservation_v1 (
    id integer NOT NULL,
    organization_id integer NOT NULL,
    school_year_id integer NOT NULL,
    version_id integer NOT NULL,
    assignment_id integer NOT NULL,
    lesson_id integer NOT NULL,
    debt_id integer NOT NULL,
    minutes integer NOT NULL,
    CONSTRAINT ck_scheduler_recovery_reservation_v1_minutes CHECK ((minutes > 0))
);

ALTER TABLE ONLY public.scheduler_recovery_reservation_v1 FORCE ROW LEVEL SECURITY;


ALTER TABLE public.scheduler_recovery_reservation_v1 OWNER TO cronos_migrator;

--
-- Name: scheduler_recovery_reservation_v1_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.scheduler_recovery_reservation_v1_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.scheduler_recovery_reservation_v1_id_seq OWNER TO cronos_migrator;

--
-- Name: scheduler_recovery_reservation_v1_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.scheduler_recovery_reservation_v1_id_seq OWNED BY public.scheduler_recovery_reservation_v1.id;


--
-- Name: scheduler_school_year; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.scheduler_school_year (
    id integer NOT NULL,
    organization_id integer NOT NULL,
    label character varying(20) NOT NULL,
    start_date date NOT NULL,
    hard_end_date date NOT NULL,
    timezone character varying(64) NOT NULL,
    is_active boolean NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    preferred_end_date date,
    CONSTRAINT ck_scheduler_school_year_date_order CHECK ((hard_end_date >= start_date)),
    CONSTRAINT ck_scheduler_school_year_preferred_order CHECK (((preferred_end_date IS NULL) OR ((start_date <= preferred_end_date) AND (preferred_end_date <= hard_end_date))))
);

ALTER TABLE ONLY public.scheduler_school_year FORCE ROW LEVEL SECURITY;


ALTER TABLE public.scheduler_school_year OWNER TO cronos_migrator;

--
-- Name: scheduler_school_year_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.scheduler_school_year_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.scheduler_school_year_id_seq OWNER TO cronos_migrator;

--
-- Name: scheduler_school_year_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.scheduler_school_year_id_seq OWNED BY public.scheduler_school_year.id;


--
-- Name: scheduler_school_year_state; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.scheduler_school_year_state (
    id integer NOT NULL,
    organization_id integer NOT NULL,
    school_year_id integer NOT NULL,
    school_year_publication_state public.schoolyearpublicationstate NOT NULL,
    active_schedule_version_id character varying(100),
    pending_draft_id integer,
    scheduler_state_version integer NOT NULL,
    approved_scheduler_state_version integer,
    reset_at timestamp with time zone,
    reset_by_membership_id integer,
    lock_version integer NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    input_revision integer DEFAULT 0 NOT NULL,
    planning_revision integer DEFAULT 0 NOT NULL,
    last_completed_planning_revision integer,
    last_successful_generation_at timestamp with time zone,
    CONSTRAINT ck_scheduler_school_year_state_lock_version_nonnegative CHECK ((lock_version >= 0)),
    CONSTRAINT ck_scheduler_school_year_state_published_has_version CHECK (((school_year_publication_state <> 'PUBLISHED'::public.schoolyearpublicationstate) OR (active_schedule_version_id IS NOT NULL))),
    CONSTRAINT ck_scheduler_school_year_state_version_nonnegative CHECK ((scheduler_state_version >= 0)),
    CONSTRAINT ck_scheduler_state_completed_revision_nonnegative CHECK (((last_completed_planning_revision IS NULL) OR (last_completed_planning_revision >= 0))),
    CONSTRAINT ck_scheduler_state_input_revision_nonnegative CHECK ((input_revision >= 0)),
    CONSTRAINT ck_scheduler_state_planning_revision_nonnegative CHECK ((planning_revision >= 0))
);

ALTER TABLE ONLY public.scheduler_school_year_state FORCE ROW LEVEL SECURITY;


ALTER TABLE public.scheduler_school_year_state OWNER TO cronos_migrator;

--
-- Name: scheduler_school_year_state_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.scheduler_school_year_state_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.scheduler_school_year_state_id_seq OWNER TO cronos_migrator;

--
-- Name: scheduler_school_year_state_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.scheduler_school_year_state_id_seq OWNED BY public.scheduler_school_year_state.id;


--
-- Name: scheduler_state_version_events; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.scheduler_state_version_events (
    id integer NOT NULL,
    organization_id integer NOT NULL,
    school_year_id integer NOT NULL,
    version_before integer NOT NULL,
    version_after integer NOT NULL,
    entity_type character varying(80) NOT NULL,
    entity_id character varying(100),
    operation public.schedulerstatechangeoperation NOT NULL,
    change_scope public.schedulerstatechangescope NOT NULL,
    changed_by_membership_id integer,
    changed_at timestamp with time zone NOT NULL,
    before_metadata_json json,
    after_metadata_json json,
    metadata_json json,
    CONSTRAINT ck_scheduler_state_version_events_entity_type_nonempty CHECK ((length(TRIM(BOTH FROM entity_type)) > 0)),
    CONSTRAINT ck_scheduler_state_version_events_increment CHECK ((((change_scope = 'FUTURE_IMPACTING'::public.schedulerstatechangescope) AND (version_after = (version_before + 1))) OR ((change_scope <> 'FUTURE_IMPACTING'::public.schedulerstatechangescope) AND (version_after = version_before)))),
    CONSTRAINT ck_scheduler_state_version_events_versions_nonnegative CHECK (((version_before >= 0) AND (version_after >= 0)))
);

ALTER TABLE ONLY public.scheduler_state_version_events FORCE ROW LEVEL SECURITY;


ALTER TABLE public.scheduler_state_version_events OWNER TO cronos_migrator;

--
-- Name: scheduler_state_version_events_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.scheduler_state_version_events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.scheduler_state_version_events_id_seq OWNER TO cronos_migrator;

--
-- Name: scheduler_state_version_events_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.scheduler_state_version_events_id_seq OWNED BY public.scheduler_state_version_events.id;


--
-- Name: scheduler_version_v1; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.scheduler_version_v1 (
    id integer NOT NULL,
    organization_id integer NOT NULL,
    school_year_id integer NOT NULL,
    origin character varying(160) NOT NULL,
    status character varying(20) NOT NULL,
    snapshot_digest character varying(64) NOT NULL,
    previous_version_id integer,
    created_at timestamp with time zone NOT NULL,
    approved_at timestamp with time zone,
    CONSTRAINT ck_scheduler_version_v1_active_approved CHECK ((((status)::text <> 'ACTIVE'::text) OR (approved_at IS NOT NULL))),
    CONSTRAINT ck_scheduler_version_v1_digest_length CHECK ((length((snapshot_digest)::text) = 64)),
    CONSTRAINT ck_scheduler_version_v1_origin CHECK ((length(TRIM(BOTH FROM origin)) > 0)),
    CONSTRAINT ck_scheduler_version_v1_status CHECK (((status)::text = ANY ((ARRAY['CANDIDATE'::character varying, 'ACTIVE'::character varying, 'SUPERSEDED'::character varying])::text[])))
);

ALTER TABLE ONLY public.scheduler_version_v1 FORCE ROW LEVEL SECURITY;


ALTER TABLE public.scheduler_version_v1 OWNER TO cronos_migrator;

--
-- Name: scheduler_version_v1_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.scheduler_version_v1_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.scheduler_version_v1_id_seq OWNER TO cronos_migrator;

--
-- Name: scheduler_version_v1_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.scheduler_version_v1_id_seq OWNED BY public.scheduler_version_v1.id;


--
-- Name: school_calendar_event; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.school_calendar_event (
    id integer NOT NULL,
    organization_id integer NOT NULL,
    name character varying(150) NOT NULL,
    start_date date NOT NULL,
    end_date date NOT NULL,
    event_type public.calendareventtype NOT NULL,
    source public.calendareventsource NOT NULL
);

ALTER TABLE ONLY public.school_calendar_event FORCE ROW LEVEL SECURITY;


ALTER TABLE public.school_calendar_event OWNER TO cronos_migrator;

--
-- Name: school_calendar_event_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.school_calendar_event_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.school_calendar_event_id_seq OWNER TO cronos_migrator;

--
-- Name: school_calendar_event_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.school_calendar_event_id_seq OWNED BY public.school_calendar_event.id;


--
-- Name: subject; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.subject (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    required_room_type public.roomtype NOT NULL,
    organization_id integer NOT NULL
);

ALTER TABLE ONLY public.subject FORCE ROW LEVEL SECURITY;


ALTER TABLE public.subject OWNER TO cronos_migrator;

--
-- Name: subject_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.subject_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.subject_id_seq OWNER TO cronos_migrator;

--
-- Name: subject_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.subject_id_seq OWNED BY public.subject.id;


--
-- Name: teacher; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.teacher (
    id integer NOT NULL,
    organization_id integer NOT NULL,
    organization_membership_id integer NOT NULL
);

ALTER TABLE ONLY public.teacher FORCE ROW LEVEL SECURITY;


ALTER TABLE public.teacher OWNER TO cronos_migrator;

--
-- Name: teacher_endpoint_operational_event; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.teacher_endpoint_operational_event (
    id integer NOT NULL,
    organization_id integer NOT NULL,
    actor_membership_id integer,
    actor_role character varying(20),
    endpoint_key character varying(80) NOT NULL,
    http_status integer NOT NULL,
    latency_ms integer NOT NULL,
    active_generation_id character varying(100),
    created_at timestamp with time zone NOT NULL
);

ALTER TABLE ONLY public.teacher_endpoint_operational_event FORCE ROW LEVEL SECURITY;


ALTER TABLE public.teacher_endpoint_operational_event OWNER TO cronos_migrator;

--
-- Name: teacher_endpoint_operational_event_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.teacher_endpoint_operational_event_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.teacher_endpoint_operational_event_id_seq OWNER TO cronos_migrator;

--
-- Name: teacher_endpoint_operational_event_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.teacher_endpoint_operational_event_id_seq OWNED BY public.teacher_endpoint_operational_event.id;


--
-- Name: teacher_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.teacher_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.teacher_id_seq OWNER TO cronos_migrator;

--
-- Name: teacher_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.teacher_id_seq OWNED BY public.teacher.id;


--
-- Name: teacher_subject_link; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.teacher_subject_link (
    organization_id integer NOT NULL,
    teacher_id integer NOT NULL,
    subject_id integer NOT NULL
);

ALTER TABLE ONLY public.teacher_subject_link FORCE ROW LEVEL SECURITY;


ALTER TABLE public.teacher_subject_link OWNER TO cronos_migrator;

--
-- Name: teacher_weekly_timesheet; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.teacher_weekly_timesheet (
    id integer NOT NULL,
    organization_id integer NOT NULL,
    teacher_id integer NOT NULL,
    week_start_date date NOT NULL,
    status public.timesheetstatus NOT NULL,
    submitted_at timestamp with time zone,
    approved_at timestamp with time zone,
    approved_by_membership_id integer,
    created_at timestamp with time zone NOT NULL
);

ALTER TABLE ONLY public.teacher_weekly_timesheet FORCE ROW LEVEL SECURITY;


ALTER TABLE public.teacher_weekly_timesheet OWNER TO cronos_migrator;

--
-- Name: teacher_weekly_timesheet_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.teacher_weekly_timesheet_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.teacher_weekly_timesheet_id_seq OWNER TO cronos_migrator;

--
-- Name: teacher_weekly_timesheet_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.teacher_weekly_timesheet_id_seq OWNED BY public.teacher_weekly_timesheet.id;


--
-- Name: timeslot; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public.timeslot (
    id integer NOT NULL,
    day_of_week integer NOT NULL,
    start_time time without time zone NOT NULL,
    end_time time without time zone NOT NULL,
    organization_id integer NOT NULL
);

ALTER TABLE ONLY public.timeslot FORCE ROW LEVEL SECURITY;


ALTER TABLE public.timeslot OWNER TO cronos_migrator;

--
-- Name: timeslot_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.timeslot_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.timeslot_id_seq OWNER TO cronos_migrator;

--
-- Name: timeslot_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.timeslot_id_seq OWNED BY public.timeslot.id;


--
-- Name: user; Type: TABLE; Schema: public; Owner: cronos_migrator
--

CREATE TABLE public."user" (
    id integer NOT NULL,
    name character varying(150),
    email character varying(100) NOT NULL,
    clerk_user_id character varying(255),
    clerk_primary_email_id character varying(255),
    clerk_profile_name character varying(255),
    last_clerk_sync_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);

ALTER TABLE ONLY public."user" FORCE ROW LEVEL SECURITY;


ALTER TABLE public."user" OWNER TO cronos_migrator;

--
-- Name: user_id_seq; Type: SEQUENCE; Schema: public; Owner: cronos_migrator
--

CREATE SEQUENCE public.user_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.user_id_seq OWNER TO cronos_migrator;

--
-- Name: user_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: cronos_migrator
--

ALTER SEQUENCE public.user_id_seq OWNED BY public."user".id;


--
-- Name: active_schedule_blocks id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.active_schedule_blocks ALTER COLUMN id SET DEFAULT nextval('public.active_schedule_blocks_id_seq'::regclass);


--
-- Name: availability id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.availability ALTER COLUMN id SET DEFAULT nextval('public.availability_id_seq'::regclass);


--
-- Name: class id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.class ALTER COLUMN id SET DEFAULT nextval('public.class_id_seq'::regclass);


--
-- Name: class_subject_link id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.class_subject_link ALTER COLUMN id SET DEFAULT nextval('public.class_subject_link_id_seq'::regclass);


--
-- Name: clerk_webhook_event id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.clerk_webhook_event ALTER COLUMN id SET DEFAULT nextval('public.clerk_webhook_event_id_seq'::regclass);


--
-- Name: constraint id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public."constraint" ALTER COLUMN id SET DEFAULT nextval('public.constraint_id_seq'::regclass);


--
-- Name: course id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.course ALTER COLUMN id SET DEFAULT nextval('public.course_id_seq'::regclass);


--
-- Name: curricular_assignment id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_assignment ALTER COLUMN id SET DEFAULT nextval('public.curricular_assignment_id_seq'::regclass);


--
-- Name: curricular_debt id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_debt ALTER COLUMN id SET DEFAULT nextval('public.curricular_debt_id_seq'::regclass);


--
-- Name: curricular_debt_revision id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_debt_revision ALTER COLUMN id SET DEFAULT nextval('public.curricular_debt_revision_id_seq'::regclass);


--
-- Name: curricular_debt_settlement id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_debt_settlement ALTER COLUMN id SET DEFAULT nextval('public.curricular_debt_settlement_id_seq'::regclass);


--
-- Name: curricular_execution id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_execution ALTER COLUMN id SET DEFAULT nextval('public.curricular_execution_id_seq'::regclass);


--
-- Name: curricular_execution_credit id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_execution_credit ALTER COLUMN id SET DEFAULT nextval('public.curricular_execution_credit_id_seq'::regclass);


--
-- Name: curricular_requirement id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_requirement ALTER COLUMN id SET DEFAULT nextval('public.curricular_requirement_id_seq'::regclass);


--
-- Name: lesson_log id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_log ALTER COLUMN id SET DEFAULT nextval('public.lesson_log_id_seq'::regclass);


--
-- Name: lesson_occurrence id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_occurrence ALTER COLUMN id SET DEFAULT nextval('public.lesson_occurrence_id_seq'::regclass);


--
-- Name: member_access_operation id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.member_access_operation ALTER COLUMN id SET DEFAULT nextval('public.member_access_operation_id_seq'::regclass);


--
-- Name: module id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.module ALTER COLUMN id SET DEFAULT nextval('public.module_id_seq'::regclass);


--
-- Name: occurrence_operational_event id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.occurrence_operational_event ALTER COLUMN id SET DEFAULT nextval('public.occurrence_operational_event_id_seq'::regclass);


--
-- Name: operational_schedule_block id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.operational_schedule_block ALTER COLUMN id SET DEFAULT nextval('public.operational_schedule_block_id_seq'::regclass);


--
-- Name: organization id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.organization ALTER COLUMN id SET DEFAULT nextval('public.organization_id_seq'::regclass);


--
-- Name: organization_grid_settings id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.organization_grid_settings ALTER COLUMN id SET DEFAULT nextval('public.organization_grid_settings_id_seq'::regclass);


--
-- Name: organization_legal_acceptance id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.organization_legal_acceptance ALTER COLUMN id SET DEFAULT nextval('public.organization_legal_acceptance_id_seq'::regclass);


--
-- Name: organization_membership id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.organization_membership ALTER COLUMN id SET DEFAULT nextval('public.organization_membership_id_seq'::regclass);


--
-- Name: organization_settings id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.organization_settings ALTER COLUMN id SET DEFAULT nextval('public.organization_settings_id_seq'::regclass);


--
-- Name: planned_recovery_links id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.planned_recovery_links ALTER COLUMN id SET DEFAULT nextval('public.planned_recovery_links_id_seq'::regclass);


--
-- Name: progress_ledger_entry id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.progress_ledger_entry ALTER COLUMN id SET DEFAULT nextval('public.progress_ledger_entry_id_seq'::regclass);


--
-- Name: room id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.room ALTER COLUMN id SET DEFAULT nextval('public.room_id_seq'::regclass);


--
-- Name: schedule_diff_entries id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_diff_entries ALTER COLUMN id SET DEFAULT nextval('public.schedule_diff_entries_id_seq'::regclass);


--
-- Name: schedule_draft_blocks id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_draft_blocks ALTER COLUMN id SET DEFAULT nextval('public.schedule_draft_blocks_id_seq'::regclass);


--
-- Name: schedule_drafts id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_drafts ALTER COLUMN id SET DEFAULT nextval('public.schedule_drafts_id_seq'::regclass);


--
-- Name: schedule_generation_job id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_generation_job ALTER COLUMN id SET DEFAULT nextval('public.schedule_generation_job_id_seq'::regclass);


--
-- Name: scheduler_job_v1 id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_job_v1 ALTER COLUMN id SET DEFAULT nextval('public.scheduler_job_v1_id_seq'::regclass);


--
-- Name: scheduler_lesson_log_v1 id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_lesson_log_v1 ALTER COLUMN id SET DEFAULT nextval('public.scheduler_lesson_log_v1_id_seq'::regclass);


--
-- Name: scheduler_lesson_slice_v1 id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_lesson_slice_v1 ALTER COLUMN id SET DEFAULT nextval('public.scheduler_lesson_slice_v1_id_seq'::regclass);


--
-- Name: scheduler_lesson_v1 id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_lesson_v1 ALTER COLUMN id SET DEFAULT nextval('public.scheduler_lesson_v1_id_seq'::regclass);


--
-- Name: scheduler_proposal_v1 id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_proposal_v1 ALTER COLUMN id SET DEFAULT nextval('public.scheduler_proposal_v1_id_seq'::regclass);


--
-- Name: scheduler_recovery_reservation_v1 id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_recovery_reservation_v1 ALTER COLUMN id SET DEFAULT nextval('public.scheduler_recovery_reservation_v1_id_seq'::regclass);


--
-- Name: scheduler_school_year id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_school_year ALTER COLUMN id SET DEFAULT nextval('public.scheduler_school_year_id_seq'::regclass);


--
-- Name: scheduler_school_year_state id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_school_year_state ALTER COLUMN id SET DEFAULT nextval('public.scheduler_school_year_state_id_seq'::regclass);


--
-- Name: scheduler_state_version_events id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_state_version_events ALTER COLUMN id SET DEFAULT nextval('public.scheduler_state_version_events_id_seq'::regclass);


--
-- Name: scheduler_version_v1 id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_version_v1 ALTER COLUMN id SET DEFAULT nextval('public.scheduler_version_v1_id_seq'::regclass);


--
-- Name: school_calendar_event id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.school_calendar_event ALTER COLUMN id SET DEFAULT nextval('public.school_calendar_event_id_seq'::regclass);


--
-- Name: subject id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.subject ALTER COLUMN id SET DEFAULT nextval('public.subject_id_seq'::regclass);


--
-- Name: teacher id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.teacher ALTER COLUMN id SET DEFAULT nextval('public.teacher_id_seq'::regclass);


--
-- Name: teacher_endpoint_operational_event id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.teacher_endpoint_operational_event ALTER COLUMN id SET DEFAULT nextval('public.teacher_endpoint_operational_event_id_seq'::regclass);


--
-- Name: teacher_weekly_timesheet id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.teacher_weekly_timesheet ALTER COLUMN id SET DEFAULT nextval('public.teacher_weekly_timesheet_id_seq'::regclass);


--
-- Name: timeslot id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.timeslot ALTER COLUMN id SET DEFAULT nextval('public.timeslot_id_seq'::regclass);


--
-- Name: user id; Type: DEFAULT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public."user" ALTER COLUMN id SET DEFAULT nextval('public.user_id_seq'::regclass);


--
-- Name: active_schedule_blocks active_schedule_blocks_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.active_schedule_blocks
    ADD CONSTRAINT active_schedule_blocks_pkey PRIMARY KEY (id);


--
-- Name: availability availability_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.availability
    ADD CONSTRAINT availability_pkey PRIMARY KEY (id);


--
-- Name: class class_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.class
    ADD CONSTRAINT class_pkey PRIMARY KEY (id);


--
-- Name: class_subject_link class_subject_link_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.class_subject_link
    ADD CONSTRAINT class_subject_link_pkey PRIMARY KEY (id);


--
-- Name: clerk_webhook_event clerk_webhook_event_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.clerk_webhook_event
    ADD CONSTRAINT clerk_webhook_event_pkey PRIMARY KEY (id);


--
-- Name: constraint constraint_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public."constraint"
    ADD CONSTRAINT constraint_pkey PRIMARY KEY (id);


--
-- Name: course course_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.course
    ADD CONSTRAINT course_pkey PRIMARY KEY (id);


--
-- Name: course_subject_link course_subject_link_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.course_subject_link
    ADD CONSTRAINT course_subject_link_pkey PRIMARY KEY (organization_id, course_id, subject_id);


--
-- Name: curricular_assignment curricular_assignment_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_assignment
    ADD CONSTRAINT curricular_assignment_pkey PRIMARY KEY (id);


--
-- Name: curricular_debt curricular_debt_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_debt
    ADD CONSTRAINT curricular_debt_pkey PRIMARY KEY (id);


--
-- Name: curricular_debt_revision curricular_debt_revision_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_debt_revision
    ADD CONSTRAINT curricular_debt_revision_pkey PRIMARY KEY (id);


--
-- Name: curricular_debt_settlement curricular_debt_settlement_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_debt_settlement
    ADD CONSTRAINT curricular_debt_settlement_pkey PRIMARY KEY (id);


--
-- Name: curricular_execution_credit curricular_execution_credit_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_execution_credit
    ADD CONSTRAINT curricular_execution_credit_pkey PRIMARY KEY (id);


--
-- Name: curricular_execution curricular_execution_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_execution
    ADD CONSTRAINT curricular_execution_pkey PRIMARY KEY (id);


--
-- Name: curricular_requirement curricular_requirement_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_requirement
    ADD CONSTRAINT curricular_requirement_pkey PRIMARY KEY (id);


--
-- Name: lesson_log lesson_log_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_log
    ADD CONSTRAINT lesson_log_pkey PRIMARY KEY (id);


--
-- Name: lesson_occurrence lesson_occurrence_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_occurrence
    ADD CONSTRAINT lesson_occurrence_pkey PRIMARY KEY (id);


--
-- Name: member_access_operation member_access_operation_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.member_access_operation
    ADD CONSTRAINT member_access_operation_pkey PRIMARY KEY (id);


--
-- Name: module module_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.module
    ADD CONSTRAINT module_pkey PRIMARY KEY (id);


--
-- Name: occurrence_operational_event occurrence_operational_event_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.occurrence_operational_event
    ADD CONSTRAINT occurrence_operational_event_pkey PRIMARY KEY (id);


--
-- Name: operational_schedule_block operational_schedule_block_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.operational_schedule_block
    ADD CONSTRAINT operational_schedule_block_pkey PRIMARY KEY (id);


--
-- Name: organization organization_clerk_org_id_key; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.organization
    ADD CONSTRAINT organization_clerk_org_id_key UNIQUE (clerk_org_id);


--
-- Name: organization_foundation_draft organization_foundation_draft_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.organization_foundation_draft
    ADD CONSTRAINT organization_foundation_draft_pkey PRIMARY KEY (organization_id);


--
-- Name: organization_grid_settings organization_grid_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.organization_grid_settings
    ADD CONSTRAINT organization_grid_settings_pkey PRIMARY KEY (id);


--
-- Name: organization_legal_acceptance organization_legal_acceptance_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.organization_legal_acceptance
    ADD CONSTRAINT organization_legal_acceptance_pkey PRIMARY KEY (id);


--
-- Name: organization_membership organization_membership_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.organization_membership
    ADD CONSTRAINT organization_membership_pkey PRIMARY KEY (id);


--
-- Name: organization organization_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.organization
    ADD CONSTRAINT organization_pkey PRIMARY KEY (id);


--
-- Name: organization_settings organization_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.organization_settings
    ADD CONSTRAINT organization_settings_pkey PRIMARY KEY (id);


--
-- Name: planned_recovery_links planned_recovery_links_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.planned_recovery_links
    ADD CONSTRAINT planned_recovery_links_pkey PRIMARY KEY (id);


--
-- Name: progress_ledger_entry progress_ledger_entry_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.progress_ledger_entry
    ADD CONSTRAINT progress_ledger_entry_pkey PRIMARY KEY (id);


--
-- Name: room room_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.room
    ADD CONSTRAINT room_pkey PRIMARY KEY (id);


--
-- Name: schedule_diff_entries schedule_diff_entries_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_diff_entries
    ADD CONSTRAINT schedule_diff_entries_pkey PRIMARY KEY (id);


--
-- Name: schedule_draft_blocks schedule_draft_blocks_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_draft_blocks
    ADD CONSTRAINT schedule_draft_blocks_pkey PRIMARY KEY (id);


--
-- Name: schedule_drafts schedule_drafts_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_drafts
    ADD CONSTRAINT schedule_drafts_pkey PRIMARY KEY (id);


--
-- Name: schedule_generation_job schedule_generation_job_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_generation_job
    ADD CONSTRAINT schedule_generation_job_pkey PRIMARY KEY (id);


--
-- Name: scheduler_job_v1 scheduler_job_v1_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_job_v1
    ADD CONSTRAINT scheduler_job_v1_pkey PRIMARY KEY (id);


--
-- Name: scheduler_lesson_log_v1 scheduler_lesson_log_v1_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_lesson_log_v1
    ADD CONSTRAINT scheduler_lesson_log_v1_pkey PRIMARY KEY (id);


--
-- Name: scheduler_lesson_slice_v1 scheduler_lesson_slice_v1_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_lesson_slice_v1
    ADD CONSTRAINT scheduler_lesson_slice_v1_pkey PRIMARY KEY (id);


--
-- Name: scheduler_lesson_v1 scheduler_lesson_v1_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_lesson_v1
    ADD CONSTRAINT scheduler_lesson_v1_pkey PRIMARY KEY (id);


--
-- Name: scheduler_proposal_v1 scheduler_proposal_v1_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_proposal_v1
    ADD CONSTRAINT scheduler_proposal_v1_pkey PRIMARY KEY (id);


--
-- Name: scheduler_recovery_reservation_v1 scheduler_recovery_reservation_v1_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_recovery_reservation_v1
    ADD CONSTRAINT scheduler_recovery_reservation_v1_pkey PRIMARY KEY (id);


--
-- Name: scheduler_school_year scheduler_school_year_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_school_year
    ADD CONSTRAINT scheduler_school_year_pkey PRIMARY KEY (id);


--
-- Name: scheduler_school_year_state scheduler_school_year_state_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_school_year_state
    ADD CONSTRAINT scheduler_school_year_state_pkey PRIMARY KEY (id);


--
-- Name: scheduler_state_version_events scheduler_state_version_events_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_state_version_events
    ADD CONSTRAINT scheduler_state_version_events_pkey PRIMARY KEY (id);


--
-- Name: scheduler_version_v1 scheduler_version_v1_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_version_v1
    ADD CONSTRAINT scheduler_version_v1_pkey PRIMARY KEY (id);


--
-- Name: school_calendar_event school_calendar_event_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.school_calendar_event
    ADD CONSTRAINT school_calendar_event_pkey PRIMARY KEY (id);


--
-- Name: subject subject_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.subject
    ADD CONSTRAINT subject_pkey PRIMARY KEY (id);


--
-- Name: teacher_endpoint_operational_event teacher_endpoint_operational_event_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.teacher_endpoint_operational_event
    ADD CONSTRAINT teacher_endpoint_operational_event_pkey PRIMARY KEY (id);


--
-- Name: teacher teacher_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.teacher
    ADD CONSTRAINT teacher_pkey PRIMARY KEY (id);


--
-- Name: teacher_subject_link teacher_subject_link_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.teacher_subject_link
    ADD CONSTRAINT teacher_subject_link_pkey PRIMARY KEY (organization_id, teacher_id, subject_id);


--
-- Name: teacher_weekly_timesheet teacher_weekly_timesheet_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.teacher_weekly_timesheet
    ADD CONSTRAINT teacher_weekly_timesheet_pkey PRIMARY KEY (id);


--
-- Name: timeslot timeslot_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.timeslot
    ADD CONSTRAINT timeslot_pkey PRIMARY KEY (id);


--
-- Name: active_schedule_blocks uq_active_schedule_blocks_id_org; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.active_schedule_blocks
    ADD CONSTRAINT uq_active_schedule_blocks_id_org UNIQUE (id, organization_id);


--
-- Name: active_schedule_blocks uq_active_schedule_blocks_id_scope; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.active_schedule_blocks
    ADD CONSTRAINT uq_active_schedule_blocks_id_scope UNIQUE (id, organization_id, school_year_id);


--
-- Name: active_schedule_blocks uq_active_schedule_blocks_org_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.active_schedule_blocks
    ADD CONSTRAINT uq_active_schedule_blocks_org_id UNIQUE (organization_id, id);


--
-- Name: active_schedule_blocks uq_active_schedule_blocks_source_draft_block; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.active_schedule_blocks
    ADD CONSTRAINT uq_active_schedule_blocks_source_draft_block UNIQUE (source_draft_block_id);


--
-- Name: active_schedule_blocks uq_active_schedule_blocks_version_stable_key; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.active_schedule_blocks
    ADD CONSTRAINT uq_active_schedule_blocks_version_stable_key UNIQUE (organization_id, school_year_id, schedule_version_id, stable_block_key);


--
-- Name: availability uq_availability_org_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.availability
    ADD CONSTRAINT uq_availability_org_id UNIQUE (organization_id, id);


--
-- Name: class uq_class_org_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.class
    ADD CONSTRAINT uq_class_org_id UNIQUE (organization_id, id);


--
-- Name: class_subject_link uq_class_subject_grade; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.class_subject_link
    ADD CONSTRAINT uq_class_subject_grade UNIQUE (organization_id, class_id, subject_id, grade_level);


--
-- Name: class_subject_link uq_class_subject_link_org_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.class_subject_link
    ADD CONSTRAINT uq_class_subject_link_org_id UNIQUE (organization_id, id);


--
-- Name: constraint uq_constraint_org_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public."constraint"
    ADD CONSTRAINT uq_constraint_org_id UNIQUE (organization_id, id);


--
-- Name: course uq_course_org_abbreviation; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.course
    ADD CONSTRAINT uq_course_org_abbreviation UNIQUE (organization_id, abbreviation);


--
-- Name: course uq_course_org_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.course
    ADD CONSTRAINT uq_course_org_id UNIQUE (organization_id, id);


--
-- Name: curricular_assignment uq_curricular_assignment_class_subject; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_assignment
    ADD CONSTRAINT uq_curricular_assignment_class_subject UNIQUE (organization_id, school_year_id, class_id, subject_id);


--
-- Name: curricular_assignment uq_curricular_assignment_org_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_assignment
    ADD CONSTRAINT uq_curricular_assignment_org_id UNIQUE (organization_id, id);


--
-- Name: curricular_assignment uq_curricular_assignment_year_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_assignment
    ADD CONSTRAINT uq_curricular_assignment_year_id UNIQUE (organization_id, school_year_id, id);


--
-- Name: curricular_debt uq_curricular_debt_assignment_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_debt
    ADD CONSTRAINT uq_curricular_debt_assignment_id UNIQUE (organization_id, assignment_id, id);


--
-- Name: curricular_debt uq_curricular_debt_org_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_debt
    ADD CONSTRAINT uq_curricular_debt_org_id UNIQUE (organization_id, id);


--
-- Name: curricular_debt uq_curricular_debt_origin; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_debt
    ADD CONSTRAINT uq_curricular_debt_origin UNIQUE (assignment_id, origin, origin_revision);


--
-- Name: curricular_debt_revision uq_curricular_debt_revision_org_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_debt_revision
    ADD CONSTRAINT uq_curricular_debt_revision_org_id UNIQUE (organization_id, id);


--
-- Name: curricular_debt_revision uq_curricular_debt_revision_origin; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_debt_revision
    ADD CONSTRAINT uq_curricular_debt_revision_origin UNIQUE (debt_id, origin, revision);


--
-- Name: curricular_debt_settlement uq_curricular_debt_settlement_execution; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_debt_settlement
    ADD CONSTRAINT uq_curricular_debt_settlement_execution UNIQUE (debt_id, execution_id);


--
-- Name: curricular_debt_settlement uq_curricular_debt_settlement_org_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_debt_settlement
    ADD CONSTRAINT uq_curricular_debt_settlement_org_id UNIQUE (organization_id, id);


--
-- Name: curricular_execution_credit uq_curricular_execution_credit_module; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_execution_credit
    ADD CONSTRAINT uq_curricular_execution_credit_module UNIQUE (execution_id, module_id);


--
-- Name: curricular_execution uq_curricular_execution_org_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_execution
    ADD CONSTRAINT uq_curricular_execution_org_id UNIQUE (organization_id, id);


--
-- Name: curricular_execution uq_curricular_execution_origin_revision; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_execution
    ADD CONSTRAINT uq_curricular_execution_origin_revision UNIQUE (organization_id, origin, revision);


--
-- Name: curricular_requirement uq_curricular_requirement_module; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_requirement
    ADD CONSTRAINT uq_curricular_requirement_module UNIQUE (assignment_id, module_id);


--
-- Name: curricular_requirement uq_curricular_requirement_org_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_requirement
    ADD CONSTRAINT uq_curricular_requirement_org_id UNIQUE (organization_id, id);


--
-- Name: curricular_requirement uq_curricular_requirement_sequence; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_requirement
    ADD CONSTRAINT uq_curricular_requirement_sequence UNIQUE (assignment_id, sequence);


--
-- Name: lesson_log uq_lesson_log_active_schedule_block; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_log
    ADD CONSTRAINT uq_lesson_log_active_schedule_block UNIQUE (active_schedule_block_id);


--
-- Name: lesson_log uq_lesson_log_id_org_active_block; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_log
    ADD CONSTRAINT uq_lesson_log_id_org_active_block UNIQUE (id, organization_id, active_schedule_block_id);


--
-- Name: lesson_log uq_lesson_log_org_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_log
    ADD CONSTRAINT uq_lesson_log_org_id UNIQUE (organization_id, id);


--
-- Name: lesson_occurrence uq_lesson_occurrence_active_block_date_revision; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_occurrence
    ADD CONSTRAINT uq_lesson_occurrence_active_block_date_revision UNIQUE (organization_id, active_schedule_block_id, date, revision);


--
-- Name: lesson_occurrence uq_lesson_occurrence_id_org_revision; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_occurrence
    ADD CONSTRAINT uq_lesson_occurrence_id_org_revision UNIQUE (id, organization_id, revision);


--
-- Name: lesson_occurrence uq_lesson_occurrence_org_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_occurrence
    ADD CONSTRAINT uq_lesson_occurrence_org_id UNIQUE (organization_id, id);


--
-- Name: member_access_operation uq_member_access_operation_org_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.member_access_operation
    ADD CONSTRAINT uq_member_access_operation_org_id UNIQUE (organization_id, id);


--
-- Name: module uq_module_order_per_subject; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.module
    ADD CONSTRAINT uq_module_order_per_subject UNIQUE (organization_id, subject_id, "order");


--
-- Name: module uq_module_org_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.module
    ADD CONSTRAINT uq_module_org_id UNIQUE (organization_id, id);


--
-- Name: occurrence_operational_event uq_occurrence_operational_event_org_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.occurrence_operational_event
    ADD CONSTRAINT uq_occurrence_operational_event_org_id UNIQUE (organization_id, id);


--
-- Name: operational_schedule_block uq_operational_schedule_block_org_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.operational_schedule_block
    ADD CONSTRAINT uq_operational_schedule_block_org_id UNIQUE (organization_id, id);


--
-- Name: organization_membership uq_org_membership_account; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.organization_membership
    ADD CONSTRAINT uq_org_membership_account UNIQUE (organization_id, account_id);


--
-- Name: organization_grid_settings uq_organization_grid_settings_org_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.organization_grid_settings
    ADD CONSTRAINT uq_organization_grid_settings_org_id UNIQUE (organization_id, id);


--
-- Name: organization_legal_acceptance uq_organization_legal_acceptance_versions; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.organization_legal_acceptance
    ADD CONSTRAINT uq_organization_legal_acceptance_versions UNIQUE (organization_id, terms_version, dpa_version, privacy_version);


--
-- Name: organization_membership uq_organization_membership_org_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.organization_membership
    ADD CONSTRAINT uq_organization_membership_org_id UNIQUE (organization_id, id);


--
-- Name: organization_settings uq_organization_settings_org_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.organization_settings
    ADD CONSTRAINT uq_organization_settings_org_id UNIQUE (organization_id, id);


--
-- Name: planned_recovery_links uq_planned_recovery_links_active_block; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.planned_recovery_links
    ADD CONSTRAINT uq_planned_recovery_links_active_block UNIQUE (planned_active_block_id);


--
-- Name: planned_recovery_links uq_planned_recovery_links_delivery_log; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.planned_recovery_links
    ADD CONSTRAINT uq_planned_recovery_links_delivery_log UNIQUE (delivered_lesson_log_id);


--
-- Name: planned_recovery_links uq_planned_recovery_links_draft_block; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.planned_recovery_links
    ADD CONSTRAINT uq_planned_recovery_links_draft_block UNIQUE (planned_draft_block_id);


--
-- Name: planned_recovery_links uq_planned_recovery_links_org_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.planned_recovery_links
    ADD CONSTRAINT uq_planned_recovery_links_org_id UNIQUE (organization_id, id);


--
-- Name: progress_ledger_entry uq_progress_ledger_entry_org_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.progress_ledger_entry
    ADD CONSTRAINT uq_progress_ledger_entry_org_id UNIQUE (organization_id, id);


--
-- Name: room uq_room_org_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.room
    ADD CONSTRAINT uq_room_org_id UNIQUE (organization_id, id);


--
-- Name: schedule_diff_entries uq_schedule_diff_entries_org_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_diff_entries
    ADD CONSTRAINT uq_schedule_diff_entries_org_id UNIQUE (organization_id, id);


--
-- Name: schedule_draft_blocks uq_schedule_draft_blocks_class_slot; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_draft_blocks
    ADD CONSTRAINT uq_schedule_draft_blocks_class_slot UNIQUE (draft_id, class_id, date, timeslot_id);


--
-- Name: schedule_draft_blocks uq_schedule_draft_blocks_id_scope; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_draft_blocks
    ADD CONSTRAINT uq_schedule_draft_blocks_id_scope UNIQUE (id, organization_id, school_year_id);


--
-- Name: schedule_draft_blocks uq_schedule_draft_blocks_org_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_draft_blocks
    ADD CONSTRAINT uq_schedule_draft_blocks_org_id UNIQUE (organization_id, id);


--
-- Name: schedule_draft_blocks uq_schedule_draft_blocks_room_slot; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_draft_blocks
    ADD CONSTRAINT uq_schedule_draft_blocks_room_slot UNIQUE (draft_id, room_id, date, timeslot_id);


--
-- Name: schedule_draft_blocks uq_schedule_draft_blocks_stable_key; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_draft_blocks
    ADD CONSTRAINT uq_schedule_draft_blocks_stable_key UNIQUE (draft_id, stable_block_key);


--
-- Name: schedule_draft_blocks uq_schedule_draft_blocks_teacher_slot; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_draft_blocks
    ADD CONSTRAINT uq_schedule_draft_blocks_teacher_slot UNIQUE (draft_id, teacher_id, date, timeslot_id);


--
-- Name: schedule_drafts uq_schedule_drafts_generation_job; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_drafts
    ADD CONSTRAINT uq_schedule_drafts_generation_job UNIQUE (generation_job_id);


--
-- Name: schedule_drafts uq_schedule_drafts_id_job_scope; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_drafts
    ADD CONSTRAINT uq_schedule_drafts_id_job_scope UNIQUE (id, generation_job_id, organization_id, school_year_id);


--
-- Name: schedule_drafts uq_schedule_drafts_id_scope; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_drafts
    ADD CONSTRAINT uq_schedule_drafts_id_scope UNIQUE (id, organization_id, school_year_id);


--
-- Name: schedule_drafts uq_schedule_drafts_org_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_drafts
    ADD CONSTRAINT uq_schedule_drafts_org_id UNIQUE (organization_id, id);


--
-- Name: schedule_generation_job uq_schedule_generation_job_id_scope; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_generation_job
    ADD CONSTRAINT uq_schedule_generation_job_id_scope UNIQUE (id, organization_id, school_year_id);


--
-- Name: schedule_generation_job uq_schedule_generation_job_idempotency; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_generation_job
    ADD CONSTRAINT uq_schedule_generation_job_idempotency UNIQUE (organization_id, school_year_id, idempotency_key);


--
-- Name: schedule_generation_job uq_schedule_generation_job_org_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_generation_job
    ADD CONSTRAINT uq_schedule_generation_job_org_id UNIQUE (organization_id, id);


--
-- Name: scheduler_job_v1 uq_scheduler_job_v1_org_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_job_v1
    ADD CONSTRAINT uq_scheduler_job_v1_org_id UNIQUE (organization_id, id);


--
-- Name: scheduler_job_v1 uq_scheduler_job_v1_origin_revision; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_job_v1
    ADD CONSTRAINT uq_scheduler_job_v1_origin_revision UNIQUE (organization_id, origin, revision);


--
-- Name: scheduler_job_v1 uq_scheduler_job_v1_year_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_job_v1
    ADD CONSTRAINT uq_scheduler_job_v1_year_id UNIQUE (organization_id, school_year_id, id);


--
-- Name: scheduler_lesson_log_v1 uq_scheduler_lesson_log_v1_lesson; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_lesson_log_v1
    ADD CONSTRAINT uq_scheduler_lesson_log_v1_lesson UNIQUE (lesson_id);


--
-- Name: scheduler_lesson_slice_v1 uq_scheduler_lesson_slice_v1_module; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_lesson_slice_v1
    ADD CONSTRAINT uq_scheduler_lesson_slice_v1_module UNIQUE (lesson_id, module_id);


--
-- Name: scheduler_lesson_v1 uq_scheduler_lesson_v1_assignment_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_lesson_v1
    ADD CONSTRAINT uq_scheduler_lesson_v1_assignment_id UNIQUE (organization_id, school_year_id, assignment_id, id);


--
-- Name: scheduler_lesson_v1 uq_scheduler_lesson_v1_stable_key; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_lesson_v1
    ADD CONSTRAINT uq_scheduler_lesson_v1_stable_key UNIQUE (version_id, stable_key);


--
-- Name: scheduler_lesson_v1 uq_scheduler_lesson_v1_version_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_lesson_v1
    ADD CONSTRAINT uq_scheduler_lesson_v1_version_id UNIQUE (organization_id, school_year_id, version_id, id);


--
-- Name: scheduler_lesson_v1 uq_scheduler_lesson_v1_year_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_lesson_v1
    ADD CONSTRAINT uq_scheduler_lesson_v1_year_id UNIQUE (organization_id, school_year_id, id);


--
-- Name: scheduler_proposal_v1 uq_scheduler_proposal_v1_job; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_proposal_v1
    ADD CONSTRAINT uq_scheduler_proposal_v1_job UNIQUE (job_id);


--
-- Name: scheduler_proposal_v1 uq_scheduler_proposal_v1_org_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_proposal_v1
    ADD CONSTRAINT uq_scheduler_proposal_v1_org_id UNIQUE (organization_id, id);


--
-- Name: scheduler_recovery_reservation_v1 uq_scheduler_recovery_reservation_v1_debt; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_recovery_reservation_v1
    ADD CONSTRAINT uq_scheduler_recovery_reservation_v1_debt UNIQUE (version_id, lesson_id, debt_id);


--
-- Name: scheduler_school_year uq_scheduler_school_year_id_org; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_school_year
    ADD CONSTRAINT uq_scheduler_school_year_id_org UNIQUE (id, organization_id);


--
-- Name: scheduler_school_year uq_scheduler_school_year_org_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_school_year
    ADD CONSTRAINT uq_scheduler_school_year_org_id UNIQUE (organization_id, id);


--
-- Name: scheduler_school_year uq_scheduler_school_year_org_label; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_school_year
    ADD CONSTRAINT uq_scheduler_school_year_org_label UNIQUE (organization_id, label);


--
-- Name: scheduler_school_year_state uq_scheduler_school_year_state_org_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_school_year_state
    ADD CONSTRAINT uq_scheduler_school_year_state_org_id UNIQUE (organization_id, id);


--
-- Name: scheduler_school_year_state uq_scheduler_school_year_state_org_year; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_school_year_state
    ADD CONSTRAINT uq_scheduler_school_year_state_org_year UNIQUE (organization_id, school_year_id);


--
-- Name: scheduler_state_version_events uq_scheduler_state_version_events_org_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_state_version_events
    ADD CONSTRAINT uq_scheduler_state_version_events_org_id UNIQUE (organization_id, id);


--
-- Name: scheduler_version_v1 uq_scheduler_version_v1_year_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_version_v1
    ADD CONSTRAINT uq_scheduler_version_v1_year_id UNIQUE (organization_id, school_year_id, id);


--
-- Name: school_calendar_event uq_school_calendar_event_org_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.school_calendar_event
    ADD CONSTRAINT uq_school_calendar_event_org_id UNIQUE (organization_id, id);


--
-- Name: subject uq_subject_org_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.subject
    ADD CONSTRAINT uq_subject_org_id UNIQUE (organization_id, id);


--
-- Name: teacher_endpoint_operational_event uq_teacher_endpoint_operational_event_org_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.teacher_endpoint_operational_event
    ADD CONSTRAINT uq_teacher_endpoint_operational_event_org_id UNIQUE (organization_id, id);


--
-- Name: teacher uq_teacher_org_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.teacher
    ADD CONSTRAINT uq_teacher_org_id UNIQUE (organization_id, id);


--
-- Name: availability uq_teacher_timeslot_availability; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.availability
    ADD CONSTRAINT uq_teacher_timeslot_availability UNIQUE (organization_id, teacher_id, timeslot_id);


--
-- Name: teacher_weekly_timesheet uq_teacher_weekly_timesheet; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.teacher_weekly_timesheet
    ADD CONSTRAINT uq_teacher_weekly_timesheet UNIQUE (organization_id, teacher_id, week_start_date);


--
-- Name: teacher_weekly_timesheet uq_teacher_weekly_timesheet_org_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.teacher_weekly_timesheet
    ADD CONSTRAINT uq_teacher_weekly_timesheet_org_id UNIQUE (organization_id, id);


--
-- Name: timeslot uq_timeslot; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.timeslot
    ADD CONSTRAINT uq_timeslot UNIQUE (day_of_week, start_time, organization_id);


--
-- Name: timeslot uq_timeslot_org_id; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.timeslot
    ADD CONSTRAINT uq_timeslot_org_id UNIQUE (organization_id, id);


--
-- Name: user user_clerk_user_id_key; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public."user"
    ADD CONSTRAINT user_clerk_user_id_key UNIQUE (clerk_user_id);


--
-- Name: user user_pkey; Type: CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public."user"
    ADD CONSTRAINT user_pkey PRIMARY KEY (id);


--
-- Name: ix_active_schedule_blocks_organization_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_active_schedule_blocks_organization_id ON public.active_schedule_blocks USING btree (organization_id);


--
-- Name: ix_active_schedule_blocks_schedule_version_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_active_schedule_blocks_schedule_version_id ON public.active_schedule_blocks USING btree (schedule_version_id);


--
-- Name: ix_active_schedule_blocks_school_year_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_active_schedule_blocks_school_year_id ON public.active_schedule_blocks USING btree (school_year_id);


--
-- Name: ix_availability_organization_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_availability_organization_id ON public.availability USING btree (organization_id);


--
-- Name: ix_availability_teacher_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_availability_teacher_id ON public.availability USING btree (teacher_id);


--
-- Name: ix_availability_timeslot_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_availability_timeslot_id ON public.availability USING btree (timeslot_id);


--
-- Name: ix_class_subject_link_class_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_class_subject_link_class_id ON public.class_subject_link USING btree (class_id);


--
-- Name: ix_class_subject_link_organization_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_class_subject_link_organization_id ON public.class_subject_link USING btree (organization_id);


--
-- Name: ix_class_subject_link_subject_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_class_subject_link_subject_id ON public.class_subject_link USING btree (subject_id);


--
-- Name: ix_class_subject_link_teacher_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_class_subject_link_teacher_id ON public.class_subject_link USING btree (teacher_id);


--
-- Name: ix_clerk_webhook_due_work; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_clerk_webhook_due_work ON public.clerk_webhook_event USING btree (processing_status, next_retry_at, created_at);


--
-- Name: ix_clerk_webhook_event_clerk_object_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_clerk_webhook_event_clerk_object_id ON public.clerk_webhook_event USING btree (clerk_object_id);


--
-- Name: ix_clerk_webhook_event_clerk_org_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_clerk_webhook_event_clerk_org_id ON public.clerk_webhook_event USING btree (clerk_org_id);


--
-- Name: ix_clerk_webhook_event_clerk_user_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_clerk_webhook_event_clerk_user_id ON public.clerk_webhook_event USING btree (clerk_user_id);


--
-- Name: ix_clerk_webhook_event_event_type; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_clerk_webhook_event_event_type ON public.clerk_webhook_event USING btree (event_type);


--
-- Name: ix_clerk_webhook_event_processing_status; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_clerk_webhook_event_processing_status ON public.clerk_webhook_event USING btree (processing_status);


--
-- Name: ix_clerk_webhook_event_svix_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE UNIQUE INDEX ix_clerk_webhook_event_svix_id ON public.clerk_webhook_event USING btree (svix_id);


--
-- Name: ix_constraint_organization_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_constraint_organization_id ON public."constraint" USING btree (organization_id);


--
-- Name: ix_course_subject_link_organization_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_course_subject_link_organization_id ON public.course_subject_link USING btree (organization_id);


--
-- Name: ix_curricular_debt_assignment_origin; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_curricular_debt_assignment_origin ON public.curricular_debt USING btree (organization_id, assignment_id, origin_date);


--
-- Name: ix_curricular_execution_assignment_date; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_curricular_execution_assignment_date ON public.curricular_execution USING btree (organization_id, assignment_id, recorded_at);


--
-- Name: ix_lesson_log_active_schedule_block_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_lesson_log_active_schedule_block_id ON public.lesson_log USING btree (active_schedule_block_id);


--
-- Name: ix_lesson_log_operational_block_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE UNIQUE INDEX ix_lesson_log_operational_block_id ON public.lesson_log USING btree (operational_block_id);


--
-- Name: ix_lesson_log_organization_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_lesson_log_organization_id ON public.lesson_log USING btree (organization_id);


--
-- Name: ix_lesson_occurrence_active_schedule_block_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_lesson_occurrence_active_schedule_block_id ON public.lesson_occurrence USING btree (active_schedule_block_id);


--
-- Name: ix_lesson_occurrence_date; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_lesson_occurrence_date ON public.lesson_occurrence USING btree (date);


--
-- Name: ix_lesson_occurrence_is_active; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_lesson_occurrence_is_active ON public.lesson_occurrence USING btree (is_active);


--
-- Name: ix_lesson_occurrence_org_active_date; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_lesson_occurrence_org_active_date ON public.lesson_occurrence USING btree (organization_id, is_active, date);


--
-- Name: ix_lesson_occurrence_organization_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_lesson_occurrence_organization_id ON public.lesson_occurrence USING btree (organization_id);


--
-- Name: ix_member_access_operation_account_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_member_access_operation_account_id ON public.member_access_operation USING btree (account_id);


--
-- Name: ix_member_access_operation_idempotency_key; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE UNIQUE INDEX ix_member_access_operation_idempotency_key ON public.member_access_operation USING btree (idempotency_key);


--
-- Name: ix_member_access_operation_membership_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_member_access_operation_membership_id ON public.member_access_operation USING btree (membership_id);


--
-- Name: ix_member_access_operation_operation_status; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_member_access_operation_operation_status ON public.member_access_operation USING btree (operation_status);


--
-- Name: ix_member_access_operation_organization_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_member_access_operation_organization_id ON public.member_access_operation USING btree (organization_id);


--
-- Name: ix_member_access_operation_target_email; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_member_access_operation_target_email ON public.member_access_operation USING btree (target_email);


--
-- Name: ix_module_organization_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_module_organization_id ON public.module USING btree (organization_id);


--
-- Name: ix_occ_event_org_created; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_occ_event_org_created ON public.occurrence_operational_event USING btree (organization_id, created_at);


--
-- Name: ix_occurrence_operational_event_active_schedule_block_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_occurrence_operational_event_active_schedule_block_id ON public.occurrence_operational_event USING btree (active_schedule_block_id);


--
-- Name: ix_occurrence_operational_event_actor_membership_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_occurrence_operational_event_actor_membership_id ON public.occurrence_operational_event USING btree (actor_membership_id);


--
-- Name: ix_occurrence_operational_event_created_at; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_occurrence_operational_event_created_at ON public.occurrence_operational_event USING btree (created_at);


--
-- Name: ix_occurrence_operational_event_occurrence_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_occurrence_operational_event_occurrence_id ON public.occurrence_operational_event USING btree (occurrence_id);


--
-- Name: ix_occurrence_operational_event_organization_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_occurrence_operational_event_organization_id ON public.occurrence_operational_event USING btree (organization_id);


--
-- Name: ix_operational_block_org_class_date; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_operational_block_org_class_date ON public.operational_schedule_block USING btree (organization_id, class_id, date);


--
-- Name: ix_operational_block_org_teacher_date_slot; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_operational_block_org_teacher_date_slot ON public.operational_schedule_block USING btree (organization_id, teacher_id, date, timeslot_id);


--
-- Name: ix_operational_schedule_block_class_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_operational_schedule_block_class_id ON public.operational_schedule_block USING btree (class_id);


--
-- Name: ix_operational_schedule_block_date; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_operational_schedule_block_date ON public.operational_schedule_block USING btree (date);


--
-- Name: ix_operational_schedule_block_organization_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_operational_schedule_block_organization_id ON public.operational_schedule_block USING btree (organization_id);


--
-- Name: ix_operational_schedule_block_planned_active_schedule_block_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_operational_schedule_block_planned_active_schedule_block_id ON public.operational_schedule_block USING btree (planned_active_schedule_block_id);


--
-- Name: ix_operational_schedule_block_source_occurrence_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_operational_schedule_block_source_occurrence_id ON public.operational_schedule_block USING btree (source_occurrence_id);


--
-- Name: ix_operational_schedule_block_subject_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_operational_schedule_block_subject_id ON public.operational_schedule_block USING btree (subject_id);


--
-- Name: ix_operational_schedule_block_teacher_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_operational_schedule_block_teacher_id ON public.operational_schedule_block USING btree (teacher_id);


--
-- Name: ix_operational_schedule_block_timeslot_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_operational_schedule_block_timeslot_id ON public.operational_schedule_block USING btree (timeslot_id);


--
-- Name: ix_organization_grid_settings_organization_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE UNIQUE INDEX ix_organization_grid_settings_organization_id ON public.organization_grid_settings USING btree (organization_id);


--
-- Name: ix_organization_legal_acceptance_organization_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_organization_legal_acceptance_organization_id ON public.organization_legal_acceptance USING btree (organization_id);


--
-- Name: ix_organization_membership_access_status; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_organization_membership_access_status ON public.organization_membership USING btree (access_status);


--
-- Name: ix_organization_membership_account_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_organization_membership_account_id ON public.organization_membership USING btree (account_id);


--
-- Name: ix_organization_membership_clerk_invitation_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_organization_membership_clerk_invitation_id ON public.organization_membership USING btree (clerk_invitation_id);


--
-- Name: ix_organization_membership_clerk_membership_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_organization_membership_clerk_membership_id ON public.organization_membership USING btree (clerk_membership_id);


--
-- Name: ix_organization_membership_lifecycle_status; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_organization_membership_lifecycle_status ON public.organization_membership USING btree (lifecycle_status);


--
-- Name: ix_organization_membership_organization_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_organization_membership_organization_id ON public.organization_membership USING btree (organization_id);


--
-- Name: ix_organization_settings_organization_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE UNIQUE INDEX ix_organization_settings_organization_id ON public.organization_settings USING btree (organization_id);


--
-- Name: ix_planned_recovery_links_organization_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_planned_recovery_links_organization_id ON public.planned_recovery_links USING btree (organization_id);


--
-- Name: ix_planned_recovery_links_school_year_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_planned_recovery_links_school_year_id ON public.planned_recovery_links USING btree (school_year_id);


--
-- Name: ix_progress_ledger_entry_class_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_progress_ledger_entry_class_id ON public.progress_ledger_entry USING btree (class_id);


--
-- Name: ix_progress_ledger_entry_idempotency_key; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE UNIQUE INDEX ix_progress_ledger_entry_idempotency_key ON public.progress_ledger_entry USING btree (idempotency_key);


--
-- Name: ix_progress_ledger_entry_module_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_progress_ledger_entry_module_id ON public.progress_ledger_entry USING btree (module_id);


--
-- Name: ix_progress_ledger_entry_organization_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_progress_ledger_entry_organization_id ON public.progress_ledger_entry USING btree (organization_id);


--
-- Name: ix_progress_ledger_entry_source_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_progress_ledger_entry_source_id ON public.progress_ledger_entry USING btree (source_id);


--
-- Name: ix_progress_ledger_entry_source_type; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_progress_ledger_entry_source_type ON public.progress_ledger_entry USING btree (source_type);


--
-- Name: ix_progress_ledger_org_source; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_progress_ledger_org_source ON public.progress_ledger_entry USING btree (organization_id, source_type, source_id);


--
-- Name: ix_schedule_diff_entries_draft_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_schedule_diff_entries_draft_id ON public.schedule_diff_entries USING btree (draft_id);


--
-- Name: ix_schedule_diff_entries_organization_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_schedule_diff_entries_organization_id ON public.schedule_diff_entries USING btree (organization_id);


--
-- Name: ix_schedule_diff_entries_school_year_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_schedule_diff_entries_school_year_id ON public.schedule_diff_entries USING btree (school_year_id);


--
-- Name: ix_schedule_draft_blocks_draft_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_schedule_draft_blocks_draft_id ON public.schedule_draft_blocks USING btree (draft_id);


--
-- Name: ix_schedule_draft_blocks_organization_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_schedule_draft_blocks_organization_id ON public.schedule_draft_blocks USING btree (organization_id);


--
-- Name: ix_schedule_draft_blocks_school_year_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_schedule_draft_blocks_school_year_id ON public.schedule_draft_blocks USING btree (school_year_id);


--
-- Name: ix_schedule_drafts_organization_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_schedule_drafts_organization_id ON public.schedule_drafts USING btree (organization_id);


--
-- Name: ix_schedule_drafts_school_year_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_schedule_drafts_school_year_id ON public.schedule_drafts USING btree (school_year_id);


--
-- Name: ix_schedule_generation_job_organization_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_schedule_generation_job_organization_id ON public.schedule_generation_job USING btree (organization_id);


--
-- Name: ix_schedule_generation_job_school_year_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_schedule_generation_job_school_year_id ON public.schedule_generation_job USING btree (school_year_id);


--
-- Name: ix_scheduler_lesson_v1_assignment_date; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_scheduler_lesson_v1_assignment_date ON public.scheduler_lesson_v1 USING btree (organization_id, school_year_id, assignment_id, school_date);


--
-- Name: ix_scheduler_school_year_organization_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_scheduler_school_year_organization_id ON public.scheduler_school_year USING btree (organization_id);


--
-- Name: ix_scheduler_school_year_state_organization_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_scheduler_school_year_state_organization_id ON public.scheduler_school_year_state USING btree (organization_id);


--
-- Name: ix_scheduler_school_year_state_school_year_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_scheduler_school_year_state_school_year_id ON public.scheduler_school_year_state USING btree (school_year_id);


--
-- Name: ix_scheduler_state_version_events_organization_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_scheduler_state_version_events_organization_id ON public.scheduler_state_version_events USING btree (organization_id);


--
-- Name: ix_scheduler_state_version_events_school_year_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_scheduler_state_version_events_school_year_id ON public.scheduler_state_version_events USING btree (school_year_id);


--
-- Name: ix_school_calendar_event_organization_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_school_calendar_event_organization_id ON public.school_calendar_event USING btree (organization_id);


--
-- Name: ix_teacher_endpoint_event_org_created; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_teacher_endpoint_event_org_created ON public.teacher_endpoint_operational_event USING btree (organization_id, created_at);


--
-- Name: ix_teacher_endpoint_event_org_endpoint_created; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_teacher_endpoint_event_org_endpoint_created ON public.teacher_endpoint_operational_event USING btree (organization_id, endpoint_key, created_at);


--
-- Name: ix_teacher_endpoint_operational_event_actor_membership_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_teacher_endpoint_operational_event_actor_membership_id ON public.teacher_endpoint_operational_event USING btree (actor_membership_id);


--
-- Name: ix_teacher_endpoint_operational_event_created_at; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_teacher_endpoint_operational_event_created_at ON public.teacher_endpoint_operational_event USING btree (created_at);


--
-- Name: ix_teacher_endpoint_operational_event_endpoint_key; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_teacher_endpoint_operational_event_endpoint_key ON public.teacher_endpoint_operational_event USING btree (endpoint_key);


--
-- Name: ix_teacher_endpoint_operational_event_http_status; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_teacher_endpoint_operational_event_http_status ON public.teacher_endpoint_operational_event USING btree (http_status);


--
-- Name: ix_teacher_endpoint_operational_event_organization_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_teacher_endpoint_operational_event_organization_id ON public.teacher_endpoint_operational_event USING btree (organization_id);


--
-- Name: ix_teacher_organization_membership_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE UNIQUE INDEX ix_teacher_organization_membership_id ON public.teacher USING btree (organization_membership_id);


--
-- Name: ix_teacher_subject_link_organization_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_teacher_subject_link_organization_id ON public.teacher_subject_link USING btree (organization_id);


--
-- Name: ix_teacher_weekly_timesheet_organization_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_teacher_weekly_timesheet_organization_id ON public.teacher_weekly_timesheet USING btree (organization_id);


--
-- Name: ix_teacher_weekly_timesheet_teacher_id; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_teacher_weekly_timesheet_teacher_id ON public.teacher_weekly_timesheet USING btree (teacher_id);


--
-- Name: ix_timesheet_org_week; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE INDEX ix_timesheet_org_week ON public.teacher_weekly_timesheet USING btree (organization_id, week_start_date);


--
-- Name: ix_user_email; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE UNIQUE INDEX ix_user_email ON public."user" USING btree (email);


--
-- Name: uq_active_schedule_blocks_class_slot; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE UNIQUE INDEX uq_active_schedule_blocks_class_slot ON public.active_schedule_blocks USING btree (organization_id, school_year_id, class_id, date, timeslot_id) WHERE (status = 'ACTIVE'::public.activescheduleblockstatus);


--
-- Name: uq_active_schedule_blocks_room_slot; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE UNIQUE INDEX uq_active_schedule_blocks_room_slot ON public.active_schedule_blocks USING btree (organization_id, school_year_id, room_id, date, timeslot_id) WHERE (status = 'ACTIVE'::public.activescheduleblockstatus);


--
-- Name: uq_active_schedule_blocks_teacher_slot; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE UNIQUE INDEX uq_active_schedule_blocks_teacher_slot ON public.active_schedule_blocks USING btree (organization_id, school_year_id, teacher_id, date, timeslot_id) WHERE (status = 'ACTIVE'::public.activescheduleblockstatus);


--
-- Name: uq_member_operation_unresolved_email; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE UNIQUE INDEX uq_member_operation_unresolved_email ON public.member_access_operation USING btree (organization_id, lower((target_email)::text)) WHERE (operation_status = ANY (ARRAY['pending'::public.memberaccessoperationstatus, 'clerk_succeeded'::public.memberaccessoperationstatus, 'compensation_failed'::public.memberaccessoperationstatus, 'support_required'::public.memberaccessoperationstatus]));


--
-- Name: uq_member_operation_unresolved_membership; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE UNIQUE INDEX uq_member_operation_unresolved_membership ON public.member_access_operation USING btree (organization_id, membership_id) WHERE ((membership_id IS NOT NULL) AND (operation_status = ANY (ARRAY['pending'::public.memberaccessoperationstatus, 'clerk_succeeded'::public.memberaccessoperationstatus, 'compensation_failed'::public.memberaccessoperationstatus, 'support_required'::public.memberaccessoperationstatus])));


--
-- Name: uq_org_membership_clerk_invitation; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE UNIQUE INDEX uq_org_membership_clerk_invitation ON public.organization_membership USING btree (clerk_invitation_id) WHERE (clerk_invitation_id IS NOT NULL);


--
-- Name: uq_org_membership_clerk_membership; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE UNIQUE INDEX uq_org_membership_clerk_membership ON public.organization_membership USING btree (clerk_membership_id) WHERE (clerk_membership_id IS NOT NULL);


--
-- Name: uq_schedule_drafts_pending_year; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE UNIQUE INDEX uq_schedule_drafts_pending_year ON public.schedule_drafts USING btree (organization_id, school_year_id) WHERE (draft_state = 'PENDING'::public.scheduledraftstate);


--
-- Name: uq_schedule_generation_job_active_year; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE UNIQUE INDEX uq_schedule_generation_job_active_year ON public.schedule_generation_job USING btree (organization_id, school_year_id) WHERE (job_status = ANY (ARRAY['QUEUED'::public.schedulegenerationjobstatus, 'RUNNING'::public.schedulegenerationjobstatus, 'CANCEL_REQUESTED'::public.schedulegenerationjobstatus]));


--
-- Name: uq_scheduler_job_v1_active_year; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE UNIQUE INDEX uq_scheduler_job_v1_active_year ON public.scheduler_job_v1 USING btree (organization_id, school_year_id) WHERE ((status)::text = ANY ((ARRAY['QUEUED'::character varying, 'RUNNING'::character varying, 'VALIDATING'::character varying])::text[]));


--
-- Name: uq_scheduler_job_v1_running_global; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE UNIQUE INDEX uq_scheduler_job_v1_running_global ON public.scheduler_job_v1 USING btree ((true)) WHERE ((status)::text = ANY ((ARRAY['RUNNING'::character varying, 'VALIDATING'::character varying])::text[]));


--
-- Name: uq_scheduler_proposal_v1_current_year; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE UNIQUE INDEX uq_scheduler_proposal_v1_current_year ON public.scheduler_proposal_v1 USING btree (organization_id, school_year_id) WHERE ((status)::text = 'PENDING'::text);


--
-- Name: uq_scheduler_school_year_active_org; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE UNIQUE INDEX uq_scheduler_school_year_active_org ON public.scheduler_school_year USING btree (organization_id) WHERE (is_active IS TRUE);


--
-- Name: uq_scheduler_state_version_events_increment; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE UNIQUE INDEX uq_scheduler_state_version_events_increment ON public.scheduler_state_version_events USING btree (organization_id, school_year_id, version_after) WHERE (change_scope = 'FUTURE_IMPACTING'::public.schedulerstatechangescope);


--
-- Name: uq_scheduler_version_v1_active_year; Type: INDEX; Schema: public; Owner: cronos_migrator
--

CREATE UNIQUE INDEX uq_scheduler_version_v1_active_year ON public.scheduler_version_v1 USING btree (organization_id, school_year_id) WHERE ((status)::text = 'ACTIVE'::text);


--
-- Name: organization trg_organization_foundation_monotonic; Type: TRIGGER; Schema: public; Owner: cronos_migrator
--

CREATE TRIGGER trg_organization_foundation_monotonic BEFORE INSERT OR DELETE OR UPDATE ON public.organization FOR EACH ROW EXECUTE FUNCTION app_security.trg_fn_organization_foundation_monotonic();


--
-- Name: organization_legal_acceptance trg_organization_legal_acceptance_append_only; Type: TRIGGER; Schema: public; Owner: cronos_migrator
--

CREATE TRIGGER trg_organization_legal_acceptance_append_only BEFORE DELETE OR UPDATE ON public.organization_legal_acceptance FOR EACH ROW EXECUTE FUNCTION app_security.trg_fn_organization_legal_acceptance_append_only();


--
-- Name: active_schedule_blocks active_schedule_blocks_class_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.active_schedule_blocks
    ADD CONSTRAINT active_schedule_blocks_class_id_fkey FOREIGN KEY (class_id) REFERENCES public.class(id);


--
-- Name: active_schedule_blocks active_schedule_blocks_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.active_schedule_blocks
    ADD CONSTRAINT active_schedule_blocks_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id) ON DELETE CASCADE;


--
-- Name: active_schedule_blocks active_schedule_blocks_room_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.active_schedule_blocks
    ADD CONSTRAINT active_schedule_blocks_room_id_fkey FOREIGN KEY (room_id) REFERENCES public.room(id);


--
-- Name: active_schedule_blocks active_schedule_blocks_school_year_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.active_schedule_blocks
    ADD CONSTRAINT active_schedule_blocks_school_year_id_fkey FOREIGN KEY (school_year_id) REFERENCES public.scheduler_school_year(id) ON DELETE CASCADE;


--
-- Name: active_schedule_blocks active_schedule_blocks_subject_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.active_schedule_blocks
    ADD CONSTRAINT active_schedule_blocks_subject_id_fkey FOREIGN KEY (subject_id) REFERENCES public.subject(id);


--
-- Name: active_schedule_blocks active_schedule_blocks_teacher_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.active_schedule_blocks
    ADD CONSTRAINT active_schedule_blocks_teacher_id_fkey FOREIGN KEY (teacher_id) REFERENCES public.teacher(id);


--
-- Name: active_schedule_blocks active_schedule_blocks_timeslot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.active_schedule_blocks
    ADD CONSTRAINT active_schedule_blocks_timeslot_id_fkey FOREIGN KEY (timeslot_id) REFERENCES public.timeslot(id);


--
-- Name: availability availability_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.availability
    ADD CONSTRAINT availability_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id) ON DELETE CASCADE;


--
-- Name: availability availability_teacher_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.availability
    ADD CONSTRAINT availability_teacher_id_fkey FOREIGN KEY (teacher_id) REFERENCES public.teacher(id);


--
-- Name: availability availability_timeslot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.availability
    ADD CONSTRAINT availability_timeslot_id_fkey FOREIGN KEY (timeslot_id) REFERENCES public.timeslot(id);


--
-- Name: class class_course_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.class
    ADD CONSTRAINT class_course_id_fkey FOREIGN KEY (course_id) REFERENCES public.course(id);


--
-- Name: class class_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.class
    ADD CONSTRAINT class_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id);


--
-- Name: class_subject_link class_subject_link_class_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.class_subject_link
    ADD CONSTRAINT class_subject_link_class_id_fkey FOREIGN KEY (class_id) REFERENCES public.class(id) ON DELETE CASCADE;


--
-- Name: class_subject_link class_subject_link_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.class_subject_link
    ADD CONSTRAINT class_subject_link_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id) ON DELETE CASCADE;


--
-- Name: class_subject_link class_subject_link_subject_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.class_subject_link
    ADD CONSTRAINT class_subject_link_subject_id_fkey FOREIGN KEY (subject_id) REFERENCES public.subject(id) ON DELETE CASCADE;


--
-- Name: class_subject_link class_subject_link_teacher_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.class_subject_link
    ADD CONSTRAINT class_subject_link_teacher_id_fkey FOREIGN KEY (teacher_id) REFERENCES public.teacher(id) ON DELETE SET NULL;


--
-- Name: clerk_webhook_event clerk_webhook_event_support_resolved_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.clerk_webhook_event
    ADD CONSTRAINT clerk_webhook_event_support_resolved_by_user_id_fkey FOREIGN KEY (support_resolved_by_user_id) REFERENCES public."user"(id) ON DELETE SET NULL;


--
-- Name: constraint constraint_class_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public."constraint"
    ADD CONSTRAINT constraint_class_id_fkey FOREIGN KEY (class_id) REFERENCES public.class(id);


--
-- Name: constraint constraint_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public."constraint"
    ADD CONSTRAINT constraint_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id) ON DELETE CASCADE;


--
-- Name: constraint constraint_room_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public."constraint"
    ADD CONSTRAINT constraint_room_id_fkey FOREIGN KEY (room_id) REFERENCES public.room(id);


--
-- Name: constraint constraint_subject_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public."constraint"
    ADD CONSTRAINT constraint_subject_id_fkey FOREIGN KEY (subject_id) REFERENCES public.subject(id);


--
-- Name: constraint constraint_teacher_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public."constraint"
    ADD CONSTRAINT constraint_teacher_id_fkey FOREIGN KEY (teacher_id) REFERENCES public.teacher(id);


--
-- Name: constraint constraint_timeslot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public."constraint"
    ADD CONSTRAINT constraint_timeslot_id_fkey FOREIGN KEY (timeslot_id) REFERENCES public.timeslot(id);


--
-- Name: course course_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.course
    ADD CONSTRAINT course_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id);


--
-- Name: course_subject_link course_subject_link_course_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.course_subject_link
    ADD CONSTRAINT course_subject_link_course_id_fkey FOREIGN KEY (course_id) REFERENCES public.course(id) ON DELETE CASCADE;


--
-- Name: course_subject_link course_subject_link_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.course_subject_link
    ADD CONSTRAINT course_subject_link_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id) ON DELETE CASCADE;


--
-- Name: course_subject_link course_subject_link_subject_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.course_subject_link
    ADD CONSTRAINT course_subject_link_subject_id_fkey FOREIGN KEY (subject_id) REFERENCES public.subject(id) ON DELETE CASCADE;


--
-- Name: curricular_assignment curricular_assignment_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_assignment
    ADD CONSTRAINT curricular_assignment_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id);


--
-- Name: curricular_debt curricular_debt_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_debt
    ADD CONSTRAINT curricular_debt_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id);


--
-- Name: curricular_debt_revision curricular_debt_revision_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_debt_revision
    ADD CONSTRAINT curricular_debt_revision_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id);


--
-- Name: curricular_debt_settlement curricular_debt_settlement_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_debt_settlement
    ADD CONSTRAINT curricular_debt_settlement_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id);


--
-- Name: curricular_execution_credit curricular_execution_credit_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_execution_credit
    ADD CONSTRAINT curricular_execution_credit_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id);


--
-- Name: curricular_execution curricular_execution_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_execution
    ADD CONSTRAINT curricular_execution_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id);


--
-- Name: curricular_requirement curricular_requirement_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_requirement
    ADD CONSTRAINT curricular_requirement_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id);


--
-- Name: active_schedule_blocks fk_active_schedule_blocks_class_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.active_schedule_blocks
    ADD CONSTRAINT fk_active_schedule_blocks_class_id_org FOREIGN KEY (organization_id, class_id) REFERENCES public.class(organization_id, id);


--
-- Name: active_schedule_blocks fk_active_schedule_blocks_draft_block_scope; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.active_schedule_blocks
    ADD CONSTRAINT fk_active_schedule_blocks_draft_block_scope FOREIGN KEY (source_draft_block_id, organization_id, school_year_id) REFERENCES public.schedule_draft_blocks(id, organization_id, school_year_id) ON DELETE RESTRICT;


--
-- Name: active_schedule_blocks fk_active_schedule_blocks_room_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.active_schedule_blocks
    ADD CONSTRAINT fk_active_schedule_blocks_room_id_org FOREIGN KEY (organization_id, room_id) REFERENCES public.room(organization_id, id);


--
-- Name: active_schedule_blocks fk_active_schedule_blocks_school_year_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.active_schedule_blocks
    ADD CONSTRAINT fk_active_schedule_blocks_school_year_id_org FOREIGN KEY (organization_id, school_year_id) REFERENCES public.scheduler_school_year(organization_id, id);


--
-- Name: active_schedule_blocks fk_active_schedule_blocks_subject_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.active_schedule_blocks
    ADD CONSTRAINT fk_active_schedule_blocks_subject_id_org FOREIGN KEY (organization_id, subject_id) REFERENCES public.subject(organization_id, id);


--
-- Name: active_schedule_blocks fk_active_schedule_blocks_teacher_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.active_schedule_blocks
    ADD CONSTRAINT fk_active_schedule_blocks_teacher_id_org FOREIGN KEY (organization_id, teacher_id) REFERENCES public.teacher(organization_id, id);


--
-- Name: active_schedule_blocks fk_active_schedule_blocks_timeslot_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.active_schedule_blocks
    ADD CONSTRAINT fk_active_schedule_blocks_timeslot_id_org FOREIGN KEY (organization_id, timeslot_id) REFERENCES public.timeslot(organization_id, id);


--
-- Name: availability fk_availability_teacher_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.availability
    ADD CONSTRAINT fk_availability_teacher_id_org FOREIGN KEY (organization_id, teacher_id) REFERENCES public.teacher(organization_id, id);


--
-- Name: availability fk_availability_timeslot_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.availability
    ADD CONSTRAINT fk_availability_timeslot_id_org FOREIGN KEY (organization_id, timeslot_id) REFERENCES public.timeslot(organization_id, id);


--
-- Name: class fk_class_course_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.class
    ADD CONSTRAINT fk_class_course_id_org FOREIGN KEY (organization_id, course_id) REFERENCES public.course(organization_id, id);


--
-- Name: class_subject_link fk_class_subject_link_class_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.class_subject_link
    ADD CONSTRAINT fk_class_subject_link_class_id_org FOREIGN KEY (organization_id, class_id) REFERENCES public.class(organization_id, id);


--
-- Name: class_subject_link fk_class_subject_link_subject_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.class_subject_link
    ADD CONSTRAINT fk_class_subject_link_subject_id_org FOREIGN KEY (organization_id, subject_id) REFERENCES public.subject(organization_id, id);


--
-- Name: class_subject_link fk_class_subject_link_teacher_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.class_subject_link
    ADD CONSTRAINT fk_class_subject_link_teacher_id_org FOREIGN KEY (organization_id, teacher_id) REFERENCES public.teacher(organization_id, id);


--
-- Name: constraint fk_constraint_class_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public."constraint"
    ADD CONSTRAINT fk_constraint_class_id_org FOREIGN KEY (organization_id, class_id) REFERENCES public.class(organization_id, id);


--
-- Name: constraint fk_constraint_room_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public."constraint"
    ADD CONSTRAINT fk_constraint_room_id_org FOREIGN KEY (organization_id, room_id) REFERENCES public.room(organization_id, id);


--
-- Name: constraint fk_constraint_subject_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public."constraint"
    ADD CONSTRAINT fk_constraint_subject_id_org FOREIGN KEY (organization_id, subject_id) REFERENCES public.subject(organization_id, id);


--
-- Name: constraint fk_constraint_teacher_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public."constraint"
    ADD CONSTRAINT fk_constraint_teacher_id_org FOREIGN KEY (organization_id, teacher_id) REFERENCES public.teacher(organization_id, id);


--
-- Name: constraint fk_constraint_timeslot_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public."constraint"
    ADD CONSTRAINT fk_constraint_timeslot_id_org FOREIGN KEY (organization_id, timeslot_id) REFERENCES public.timeslot(organization_id, id);


--
-- Name: course_subject_link fk_course_subject_link_course_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.course_subject_link
    ADD CONSTRAINT fk_course_subject_link_course_id_org FOREIGN KEY (organization_id, course_id) REFERENCES public.course(organization_id, id);


--
-- Name: course_subject_link fk_course_subject_link_subject_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.course_subject_link
    ADD CONSTRAINT fk_course_subject_link_subject_id_org FOREIGN KEY (organization_id, subject_id) REFERENCES public.subject(organization_id, id);


--
-- Name: curricular_assignment fk_curricular_assignment_class_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_assignment
    ADD CONSTRAINT fk_curricular_assignment_class_org FOREIGN KEY (organization_id, class_id) REFERENCES public.class(organization_id, id);


--
-- Name: curricular_assignment fk_curricular_assignment_subject_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_assignment
    ADD CONSTRAINT fk_curricular_assignment_subject_org FOREIGN KEY (organization_id, subject_id) REFERENCES public.subject(organization_id, id);


--
-- Name: curricular_assignment fk_curricular_assignment_teacher_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_assignment
    ADD CONSTRAINT fk_curricular_assignment_teacher_org FOREIGN KEY (organization_id, teacher_id) REFERENCES public.teacher(organization_id, id);


--
-- Name: curricular_assignment fk_curricular_assignment_year_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_assignment
    ADD CONSTRAINT fk_curricular_assignment_year_org FOREIGN KEY (organization_id, school_year_id) REFERENCES public.scheduler_school_year(organization_id, id);


--
-- Name: curricular_debt fk_curricular_debt_assignment_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_debt
    ADD CONSTRAINT fk_curricular_debt_assignment_org FOREIGN KEY (organization_id, assignment_id) REFERENCES public.curricular_assignment(organization_id, id);


--
-- Name: curricular_debt fk_curricular_debt_author_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_debt
    ADD CONSTRAINT fk_curricular_debt_author_org FOREIGN KEY (organization_id, author_membership_id) REFERENCES public.organization_membership(organization_id, id);


--
-- Name: curricular_debt_revision fk_curricular_debt_revision_author_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_debt_revision
    ADD CONSTRAINT fk_curricular_debt_revision_author_org FOREIGN KEY (organization_id, author_membership_id) REFERENCES public.organization_membership(organization_id, id);


--
-- Name: curricular_debt_revision fk_curricular_debt_revision_debt_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_debt_revision
    ADD CONSTRAINT fk_curricular_debt_revision_debt_org FOREIGN KEY (organization_id, debt_id) REFERENCES public.curricular_debt(organization_id, id);


--
-- Name: curricular_debt_settlement fk_curricular_debt_settlement_debt_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_debt_settlement
    ADD CONSTRAINT fk_curricular_debt_settlement_debt_org FOREIGN KEY (organization_id, debt_id) REFERENCES public.curricular_debt(organization_id, id);


--
-- Name: curricular_debt_settlement fk_curricular_debt_settlement_execution_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_debt_settlement
    ADD CONSTRAINT fk_curricular_debt_settlement_execution_org FOREIGN KEY (organization_id, execution_id) REFERENCES public.curricular_execution(organization_id, id);


--
-- Name: curricular_debt_settlement fk_curricular_debt_settlement_reversal_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_debt_settlement
    ADD CONSTRAINT fk_curricular_debt_settlement_reversal_org FOREIGN KEY (organization_id, reversal_of_id) REFERENCES public.curricular_debt_settlement(organization_id, id);


--
-- Name: curricular_execution fk_curricular_execution_assignment_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_execution
    ADD CONSTRAINT fk_curricular_execution_assignment_org FOREIGN KEY (organization_id, assignment_id) REFERENCES public.curricular_assignment(organization_id, id);


--
-- Name: curricular_execution fk_curricular_execution_author_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_execution
    ADD CONSTRAINT fk_curricular_execution_author_org FOREIGN KEY (organization_id, author_membership_id) REFERENCES public.organization_membership(organization_id, id);


--
-- Name: curricular_execution_credit fk_curricular_execution_credit_execution_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_execution_credit
    ADD CONSTRAINT fk_curricular_execution_credit_execution_org FOREIGN KEY (organization_id, execution_id) REFERENCES public.curricular_execution(organization_id, id);


--
-- Name: curricular_execution_credit fk_curricular_execution_credit_module_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_execution_credit
    ADD CONSTRAINT fk_curricular_execution_credit_module_org FOREIGN KEY (organization_id, module_id) REFERENCES public.module(organization_id, id);


--
-- Name: curricular_execution fk_curricular_execution_reversal_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_execution
    ADD CONSTRAINT fk_curricular_execution_reversal_org FOREIGN KEY (organization_id, reversal_of_id) REFERENCES public.curricular_execution(organization_id, id);


--
-- Name: curricular_requirement fk_curricular_requirement_assignment_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_requirement
    ADD CONSTRAINT fk_curricular_requirement_assignment_org FOREIGN KEY (organization_id, assignment_id) REFERENCES public.curricular_assignment(organization_id, id);


--
-- Name: curricular_requirement fk_curricular_requirement_module_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.curricular_requirement
    ADD CONSTRAINT fk_curricular_requirement_module_org FOREIGN KEY (organization_id, module_id) REFERENCES public.module(organization_id, id);


--
-- Name: lesson_log fk_lesson_log_active_schedule_block_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_log
    ADD CONSTRAINT fk_lesson_log_active_schedule_block_id_org FOREIGN KEY (organization_id, active_schedule_block_id) REFERENCES public.active_schedule_blocks(organization_id, id);


--
-- Name: lesson_log fk_lesson_log_logged_by_membership_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_log
    ADD CONSTRAINT fk_lesson_log_logged_by_membership_id_org FOREIGN KEY (organization_id, logged_by_membership_id) REFERENCES public.organization_membership(organization_id, id);


--
-- Name: lesson_log fk_lesson_log_operational_block_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_log
    ADD CONSTRAINT fk_lesson_log_operational_block_id_org FOREIGN KEY (organization_id, operational_block_id) REFERENCES public.operational_schedule_block(organization_id, id);


--
-- Name: lesson_occurrence fk_lesson_occurrence_active_block_scope; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_occurrence
    ADD CONSTRAINT fk_lesson_occurrence_active_block_scope FOREIGN KEY (active_schedule_block_id, organization_id) REFERENCES public.active_schedule_blocks(id, organization_id) ON DELETE RESTRICT;


--
-- Name: lesson_occurrence fk_lesson_occurrence_class_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_occurrence
    ADD CONSTRAINT fk_lesson_occurrence_class_id_org FOREIGN KEY (organization_id, class_id) REFERENCES public.class(organization_id, id);


--
-- Name: lesson_occurrence fk_lesson_occurrence_created_by_membership_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_occurrence
    ADD CONSTRAINT fk_lesson_occurrence_created_by_membership_id_org FOREIGN KEY (organization_id, created_by_membership_id) REFERENCES public.organization_membership(organization_id, id);


--
-- Name: lesson_occurrence fk_lesson_occurrence_decided_by_membership_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_occurrence
    ADD CONSTRAINT fk_lesson_occurrence_decided_by_membership_id_org FOREIGN KEY (organization_id, decided_by_membership_id) REFERENCES public.organization_membership(organization_id, id);


--
-- Name: lesson_occurrence fk_lesson_occurrence_executed_module_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_occurrence
    ADD CONSTRAINT fk_lesson_occurrence_executed_module_id_org FOREIGN KEY (organization_id, executed_module_id) REFERENCES public.module(organization_id, id);


--
-- Name: lesson_occurrence fk_lesson_occurrence_executed_teacher_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_occurrence
    ADD CONSTRAINT fk_lesson_occurrence_executed_teacher_id_org FOREIGN KEY (organization_id, executed_teacher_id) REFERENCES public.teacher(organization_id, id);


--
-- Name: lesson_occurrence fk_lesson_occurrence_planned_module_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_occurrence
    ADD CONSTRAINT fk_lesson_occurrence_planned_module_id_org FOREIGN KEY (organization_id, planned_module_id) REFERENCES public.module(organization_id, id);


--
-- Name: lesson_occurrence fk_lesson_occurrence_planned_room_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_occurrence
    ADD CONSTRAINT fk_lesson_occurrence_planned_room_id_org FOREIGN KEY (organization_id, planned_room_id) REFERENCES public.room(organization_id, id);


--
-- Name: lesson_occurrence fk_lesson_occurrence_planned_teacher_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_occurrence
    ADD CONSTRAINT fk_lesson_occurrence_planned_teacher_id_org FOREIGN KEY (organization_id, planned_teacher_id) REFERENCES public.teacher(organization_id, id);


--
-- Name: lesson_occurrence fk_lesson_occurrence_planned_timeslot_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_occurrence
    ADD CONSTRAINT fk_lesson_occurrence_planned_timeslot_id_org FOREIGN KEY (organization_id, planned_timeslot_id) REFERENCES public.timeslot(organization_id, id);


--
-- Name: lesson_occurrence fk_lesson_occurrence_revoked_by_membership_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_occurrence
    ADD CONSTRAINT fk_lesson_occurrence_revoked_by_membership_id_org FOREIGN KEY (organization_id, revoked_by_membership_id) REFERENCES public.organization_membership(organization_id, id);


--
-- Name: lesson_occurrence fk_lesson_occurrence_subject_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_occurrence
    ADD CONSTRAINT fk_lesson_occurrence_subject_id_org FOREIGN KEY (organization_id, subject_id) REFERENCES public.subject(organization_id, id);


--
-- Name: lesson_occurrence fk_lesson_occurrence_substitute_subject_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_occurrence
    ADD CONSTRAINT fk_lesson_occurrence_substitute_subject_id_org FOREIGN KEY (organization_id, substitute_subject_id) REFERENCES public.subject(organization_id, id);


--
-- Name: lesson_occurrence fk_lesson_occurrence_substitute_teacher_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_occurrence
    ADD CONSTRAINT fk_lesson_occurrence_substitute_teacher_id_org FOREIGN KEY (organization_id, substitute_teacher_id) REFERENCES public.teacher(organization_id, id);


--
-- Name: member_access_operation fk_member_access_operation_created_by_membership_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.member_access_operation
    ADD CONSTRAINT fk_member_access_operation_created_by_membership_id_org FOREIGN KEY (organization_id, created_by_membership_id) REFERENCES public.organization_membership(organization_id, id);


--
-- Name: member_access_operation fk_member_access_operation_membership_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.member_access_operation
    ADD CONSTRAINT fk_member_access_operation_membership_id_org FOREIGN KEY (organization_id, membership_id) REFERENCES public.organization_membership(organization_id, id);


--
-- Name: module fk_module_subject_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.module
    ADD CONSTRAINT fk_module_subject_id_org FOREIGN KEY (organization_id, subject_id) REFERENCES public.subject(organization_id, id);


--
-- Name: occurrence_operational_event fk_occurrence_operational_event_active_schedule_block_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.occurrence_operational_event
    ADD CONSTRAINT fk_occurrence_operational_event_active_schedule_block_id_org FOREIGN KEY (organization_id, active_schedule_block_id) REFERENCES public.active_schedule_blocks(organization_id, id);


--
-- Name: occurrence_operational_event fk_occurrence_operational_event_actor_membership_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.occurrence_operational_event
    ADD CONSTRAINT fk_occurrence_operational_event_actor_membership_id_org FOREIGN KEY (organization_id, actor_membership_id) REFERENCES public.organization_membership(organization_id, id);


--
-- Name: occurrence_operational_event fk_occurrence_operational_event_occurrence_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.occurrence_operational_event
    ADD CONSTRAINT fk_occurrence_operational_event_occurrence_id_org FOREIGN KEY (organization_id, occurrence_id) REFERENCES public.lesson_occurrence(organization_id, id);


--
-- Name: operational_schedule_block fk_operational_block_planned_active_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.operational_schedule_block
    ADD CONSTRAINT fk_operational_block_planned_active_org FOREIGN KEY (organization_id, planned_active_schedule_block_id) REFERENCES public.active_schedule_blocks(organization_id, id);


--
-- Name: operational_schedule_block fk_operational_schedule_block_class_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.operational_schedule_block
    ADD CONSTRAINT fk_operational_schedule_block_class_id_org FOREIGN KEY (organization_id, class_id) REFERENCES public.class(organization_id, id);


--
-- Name: operational_schedule_block fk_operational_schedule_block_created_by_membership_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.operational_schedule_block
    ADD CONSTRAINT fk_operational_schedule_block_created_by_membership_id_org FOREIGN KEY (organization_id, created_by_membership_id) REFERENCES public.organization_membership(organization_id, id);


--
-- Name: operational_schedule_block fk_operational_schedule_block_module_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.operational_schedule_block
    ADD CONSTRAINT fk_operational_schedule_block_module_id_org FOREIGN KEY (organization_id, module_id) REFERENCES public.module(organization_id, id);


--
-- Name: operational_schedule_block fk_operational_schedule_block_room_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.operational_schedule_block
    ADD CONSTRAINT fk_operational_schedule_block_room_id_org FOREIGN KEY (organization_id, room_id) REFERENCES public.room(organization_id, id);


--
-- Name: operational_schedule_block fk_operational_schedule_block_source_occurrence_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.operational_schedule_block
    ADD CONSTRAINT fk_operational_schedule_block_source_occurrence_id_org FOREIGN KEY (organization_id, source_occurrence_id) REFERENCES public.lesson_occurrence(organization_id, id);


--
-- Name: operational_schedule_block fk_operational_schedule_block_subject_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.operational_schedule_block
    ADD CONSTRAINT fk_operational_schedule_block_subject_id_org FOREIGN KEY (organization_id, subject_id) REFERENCES public.subject(organization_id, id);


--
-- Name: operational_schedule_block fk_operational_schedule_block_teacher_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.operational_schedule_block
    ADD CONSTRAINT fk_operational_schedule_block_teacher_id_org FOREIGN KEY (organization_id, teacher_id) REFERENCES public.teacher(organization_id, id);


--
-- Name: operational_schedule_block fk_operational_schedule_block_timeslot_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.operational_schedule_block
    ADD CONSTRAINT fk_operational_schedule_block_timeslot_id_org FOREIGN KEY (organization_id, timeslot_id) REFERENCES public.timeslot(organization_id, id);


--
-- Name: organization_foundation_draft fk_org_foundation_draft_membership_tenant_scoped; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.organization_foundation_draft
    ADD CONSTRAINT fk_org_foundation_draft_membership_tenant_scoped FOREIGN KEY (organization_id, updated_by_membership_id) REFERENCES public.organization_membership(organization_id, id) ON DELETE RESTRICT;


--
-- Name: organization_membership fk_organization_membership_created_by_membership_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.organization_membership
    ADD CONSTRAINT fk_organization_membership_created_by_membership_id_org FOREIGN KEY (organization_id, created_by_membership_id) REFERENCES public.organization_membership(organization_id, id);


--
-- Name: organization_membership fk_organization_membership_updated_by_membership_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.organization_membership
    ADD CONSTRAINT fk_organization_membership_updated_by_membership_id_org FOREIGN KEY (organization_id, updated_by_membership_id) REFERENCES public.organization_membership(organization_id, id);


--
-- Name: planned_recovery_links fk_planned_recovery_links_active_block_scope; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.planned_recovery_links
    ADD CONSTRAINT fk_planned_recovery_links_active_block_scope FOREIGN KEY (planned_active_block_id, organization_id, school_year_id) REFERENCES public.active_schedule_blocks(id, organization_id, school_year_id) ON DELETE RESTRICT;


--
-- Name: planned_recovery_links fk_planned_recovery_links_class_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.planned_recovery_links
    ADD CONSTRAINT fk_planned_recovery_links_class_id_org FOREIGN KEY (organization_id, class_id) REFERENCES public.class(organization_id, id);


--
-- Name: planned_recovery_links fk_planned_recovery_links_debt_scope; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.planned_recovery_links
    ADD CONSTRAINT fk_planned_recovery_links_debt_scope FOREIGN KEY (debt_occurrence_id, organization_id, debt_occurrence_revision) REFERENCES public.lesson_occurrence(id, organization_id, revision) ON DELETE RESTRICT;


--
-- Name: planned_recovery_links fk_planned_recovery_links_delivery_evidence; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.planned_recovery_links
    ADD CONSTRAINT fk_planned_recovery_links_delivery_evidence FOREIGN KEY (delivered_lesson_log_id, organization_id, planned_active_block_id) REFERENCES public.lesson_log(id, organization_id, active_schedule_block_id) ON DELETE RESTRICT;


--
-- Name: planned_recovery_links fk_planned_recovery_links_draft_block_scope; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.planned_recovery_links
    ADD CONSTRAINT fk_planned_recovery_links_draft_block_scope FOREIGN KEY (planned_draft_block_id, organization_id, school_year_id) REFERENCES public.schedule_draft_blocks(id, organization_id, school_year_id) ON DELETE RESTRICT;


--
-- Name: planned_recovery_links fk_planned_recovery_links_school_year_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.planned_recovery_links
    ADD CONSTRAINT fk_planned_recovery_links_school_year_id_org FOREIGN KEY (organization_id, school_year_id) REFERENCES public.scheduler_school_year(organization_id, id);


--
-- Name: planned_recovery_links fk_planned_recovery_links_subject_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.planned_recovery_links
    ADD CONSTRAINT fk_planned_recovery_links_subject_id_org FOREIGN KEY (organization_id, subject_id) REFERENCES public.subject(organization_id, id);


--
-- Name: planned_recovery_links fk_planned_recovery_links_teacher_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.planned_recovery_links
    ADD CONSTRAINT fk_planned_recovery_links_teacher_id_org FOREIGN KEY (organization_id, teacher_id) REFERENCES public.teacher(organization_id, id);


--
-- Name: progress_ledger_entry fk_progress_ledger_entry_class_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.progress_ledger_entry
    ADD CONSTRAINT fk_progress_ledger_entry_class_id_org FOREIGN KEY (organization_id, class_id) REFERENCES public.class(organization_id, id);


--
-- Name: progress_ledger_entry fk_progress_ledger_entry_created_by_membership_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.progress_ledger_entry
    ADD CONSTRAINT fk_progress_ledger_entry_created_by_membership_id_org FOREIGN KEY (organization_id, created_by_membership_id) REFERENCES public.organization_membership(organization_id, id);


--
-- Name: progress_ledger_entry fk_progress_ledger_entry_module_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.progress_ledger_entry
    ADD CONSTRAINT fk_progress_ledger_entry_module_id_org FOREIGN KEY (organization_id, module_id) REFERENCES public.module(organization_id, id);


--
-- Name: progress_ledger_entry fk_progress_ledger_entry_reverses_ledger_entry_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.progress_ledger_entry
    ADD CONSTRAINT fk_progress_ledger_entry_reverses_ledger_entry_id_org FOREIGN KEY (organization_id, reverses_ledger_entry_id) REFERENCES public.progress_ledger_entry(organization_id, id);


--
-- Name: schedule_diff_entries fk_schedule_diff_entries_after_draft_block_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_diff_entries
    ADD CONSTRAINT fk_schedule_diff_entries_after_draft_block_id_org FOREIGN KEY (organization_id, after_draft_block_id) REFERENCES public.schedule_draft_blocks(organization_id, id);


--
-- Name: schedule_diff_entries fk_schedule_diff_entries_after_room_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_diff_entries
    ADD CONSTRAINT fk_schedule_diff_entries_after_room_id_org FOREIGN KEY (organization_id, after_room_id) REFERENCES public.room(organization_id, id);


--
-- Name: schedule_diff_entries fk_schedule_diff_entries_after_timeslot_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_diff_entries
    ADD CONSTRAINT fk_schedule_diff_entries_after_timeslot_id_org FOREIGN KEY (organization_id, after_timeslot_id) REFERENCES public.timeslot(organization_id, id);


--
-- Name: schedule_diff_entries fk_schedule_diff_entries_before_active; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_diff_entries
    ADD CONSTRAINT fk_schedule_diff_entries_before_active FOREIGN KEY (before_active_block_id) REFERENCES public.active_schedule_blocks(id) ON DELETE SET NULL;


--
-- Name: schedule_diff_entries fk_schedule_diff_entries_before_active_block_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_diff_entries
    ADD CONSTRAINT fk_schedule_diff_entries_before_active_block_id_org FOREIGN KEY (organization_id, before_active_block_id) REFERENCES public.active_schedule_blocks(organization_id, id);


--
-- Name: schedule_diff_entries fk_schedule_diff_entries_before_room_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_diff_entries
    ADD CONSTRAINT fk_schedule_diff_entries_before_room_id_org FOREIGN KEY (organization_id, before_room_id) REFERENCES public.room(organization_id, id);


--
-- Name: schedule_diff_entries fk_schedule_diff_entries_before_timeslot_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_diff_entries
    ADD CONSTRAINT fk_schedule_diff_entries_before_timeslot_id_org FOREIGN KEY (organization_id, before_timeslot_id) REFERENCES public.timeslot(organization_id, id);


--
-- Name: schedule_diff_entries fk_schedule_diff_entries_class_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_diff_entries
    ADD CONSTRAINT fk_schedule_diff_entries_class_id_org FOREIGN KEY (organization_id, class_id) REFERENCES public.class(organization_id, id);


--
-- Name: schedule_diff_entries fk_schedule_diff_entries_draft_job_scope; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_diff_entries
    ADD CONSTRAINT fk_schedule_diff_entries_draft_job_scope FOREIGN KEY (draft_id, generation_job_id, organization_id, school_year_id) REFERENCES public.schedule_drafts(id, generation_job_id, organization_id, school_year_id) ON DELETE CASCADE;


--
-- Name: schedule_diff_entries fk_schedule_diff_entries_school_year_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_diff_entries
    ADD CONSTRAINT fk_schedule_diff_entries_school_year_id_org FOREIGN KEY (organization_id, school_year_id) REFERENCES public.scheduler_school_year(organization_id, id);


--
-- Name: schedule_diff_entries fk_schedule_diff_entries_subject_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_diff_entries
    ADD CONSTRAINT fk_schedule_diff_entries_subject_id_org FOREIGN KEY (organization_id, subject_id) REFERENCES public.subject(organization_id, id);


--
-- Name: schedule_diff_entries fk_schedule_diff_entries_teacher_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_diff_entries
    ADD CONSTRAINT fk_schedule_diff_entries_teacher_id_org FOREIGN KEY (organization_id, teacher_id) REFERENCES public.teacher(organization_id, id);


--
-- Name: schedule_draft_blocks fk_schedule_draft_blocks_class_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_draft_blocks
    ADD CONSTRAINT fk_schedule_draft_blocks_class_id_org FOREIGN KEY (organization_id, class_id) REFERENCES public.class(organization_id, id);


--
-- Name: schedule_draft_blocks fk_schedule_draft_blocks_draft_scope; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_draft_blocks
    ADD CONSTRAINT fk_schedule_draft_blocks_draft_scope FOREIGN KEY (draft_id, organization_id, school_year_id) REFERENCES public.schedule_drafts(id, organization_id, school_year_id) ON DELETE CASCADE;


--
-- Name: schedule_draft_blocks fk_schedule_draft_blocks_recovery_source_occurrence_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_draft_blocks
    ADD CONSTRAINT fk_schedule_draft_blocks_recovery_source_occurrence_id_org FOREIGN KEY (organization_id, recovery_source_occurrence_id) REFERENCES public.lesson_occurrence(organization_id, id);


--
-- Name: schedule_draft_blocks fk_schedule_draft_blocks_room_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_draft_blocks
    ADD CONSTRAINT fk_schedule_draft_blocks_room_id_org FOREIGN KEY (organization_id, room_id) REFERENCES public.room(organization_id, id);


--
-- Name: schedule_draft_blocks fk_schedule_draft_blocks_school_year_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_draft_blocks
    ADD CONSTRAINT fk_schedule_draft_blocks_school_year_id_org FOREIGN KEY (organization_id, school_year_id) REFERENCES public.scheduler_school_year(organization_id, id);


--
-- Name: schedule_draft_blocks fk_schedule_draft_blocks_source_active; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_draft_blocks
    ADD CONSTRAINT fk_schedule_draft_blocks_source_active FOREIGN KEY (source_active_block_id) REFERENCES public.active_schedule_blocks(id) ON DELETE RESTRICT;


--
-- Name: schedule_draft_blocks fk_schedule_draft_blocks_source_active_block_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_draft_blocks
    ADD CONSTRAINT fk_schedule_draft_blocks_source_active_block_id_org FOREIGN KEY (organization_id, source_active_block_id) REFERENCES public.active_schedule_blocks(organization_id, id);


--
-- Name: schedule_draft_blocks fk_schedule_draft_blocks_subject_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_draft_blocks
    ADD CONSTRAINT fk_schedule_draft_blocks_subject_id_org FOREIGN KEY (organization_id, subject_id) REFERENCES public.subject(organization_id, id);


--
-- Name: schedule_draft_blocks fk_schedule_draft_blocks_teacher_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_draft_blocks
    ADD CONSTRAINT fk_schedule_draft_blocks_teacher_id_org FOREIGN KEY (organization_id, teacher_id) REFERENCES public.teacher(organization_id, id);


--
-- Name: schedule_draft_blocks fk_schedule_draft_blocks_timeslot_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_draft_blocks
    ADD CONSTRAINT fk_schedule_draft_blocks_timeslot_id_org FOREIGN KEY (organization_id, timeslot_id) REFERENCES public.timeslot(organization_id, id);


--
-- Name: schedule_drafts fk_schedule_drafts_created_by_membership_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_drafts
    ADD CONSTRAINT fk_schedule_drafts_created_by_membership_id_org FOREIGN KEY (organization_id, created_by_membership_id) REFERENCES public.organization_membership(organization_id, id);


--
-- Name: schedule_drafts fk_schedule_drafts_decided_by_membership_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_drafts
    ADD CONSTRAINT fk_schedule_drafts_decided_by_membership_id_org FOREIGN KEY (organization_id, decided_by_membership_id) REFERENCES public.organization_membership(organization_id, id);


--
-- Name: schedule_drafts fk_schedule_drafts_generation_job_scope; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_drafts
    ADD CONSTRAINT fk_schedule_drafts_generation_job_scope FOREIGN KEY (generation_job_id, organization_id, school_year_id) REFERENCES public.schedule_generation_job(id, organization_id, school_year_id) ON DELETE RESTRICT;


--
-- Name: schedule_drafts fk_schedule_drafts_school_year_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_drafts
    ADD CONSTRAINT fk_schedule_drafts_school_year_id_org FOREIGN KEY (organization_id, school_year_id) REFERENCES public.scheduler_school_year(organization_id, id);


--
-- Name: schedule_generation_job fk_schedule_generation_job_requested_by_membership_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_generation_job
    ADD CONSTRAINT fk_schedule_generation_job_requested_by_membership_id_org FOREIGN KEY (organization_id, requested_by_membership_id) REFERENCES public.organization_membership(organization_id, id);


--
-- Name: schedule_generation_job fk_schedule_generation_job_year_scope; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_generation_job
    ADD CONSTRAINT fk_schedule_generation_job_year_scope FOREIGN KEY (school_year_id, organization_id) REFERENCES public.scheduler_school_year(id, organization_id) ON DELETE CASCADE;


--
-- Name: scheduler_job_v1 fk_scheduler_job_v1_base_version; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_job_v1
    ADD CONSTRAINT fk_scheduler_job_v1_base_version FOREIGN KEY (organization_id, school_year_id, base_version_id) REFERENCES public.scheduler_version_v1(organization_id, school_year_id, id);


--
-- Name: scheduler_job_v1 fk_scheduler_job_v1_requester_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_job_v1
    ADD CONSTRAINT fk_scheduler_job_v1_requester_org FOREIGN KEY (organization_id, requested_by_membership_id) REFERENCES public.organization_membership(organization_id, id);


--
-- Name: scheduler_job_v1 fk_scheduler_job_v1_year_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_job_v1
    ADD CONSTRAINT fk_scheduler_job_v1_year_org FOREIGN KEY (organization_id, school_year_id) REFERENCES public.scheduler_school_year(organization_id, id);


--
-- Name: scheduler_lesson_log_v1 fk_scheduler_lesson_log_v1_author_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_lesson_log_v1
    ADD CONSTRAINT fk_scheduler_lesson_log_v1_author_org FOREIGN KEY (organization_id, logged_by_membership_id) REFERENCES public.organization_membership(organization_id, id);


--
-- Name: scheduler_lesson_log_v1 fk_scheduler_lesson_log_v1_lesson; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_lesson_log_v1
    ADD CONSTRAINT fk_scheduler_lesson_log_v1_lesson FOREIGN KEY (organization_id, school_year_id, lesson_id) REFERENCES public.scheduler_lesson_v1(organization_id, school_year_id, id);


--
-- Name: scheduler_lesson_slice_v1 fk_scheduler_lesson_slice_v1_lesson; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_lesson_slice_v1
    ADD CONSTRAINT fk_scheduler_lesson_slice_v1_lesson FOREIGN KEY (organization_id, school_year_id, lesson_id) REFERENCES public.scheduler_lesson_v1(organization_id, school_year_id, id);


--
-- Name: scheduler_lesson_slice_v1 fk_scheduler_lesson_slice_v1_module; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_lesson_slice_v1
    ADD CONSTRAINT fk_scheduler_lesson_slice_v1_module FOREIGN KEY (organization_id, module_id) REFERENCES public.module(organization_id, id);


--
-- Name: scheduler_lesson_v1 fk_scheduler_lesson_v1_assignment; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_lesson_v1
    ADD CONSTRAINT fk_scheduler_lesson_v1_assignment FOREIGN KEY (organization_id, school_year_id, assignment_id) REFERENCES public.curricular_assignment(organization_id, school_year_id, id);


--
-- Name: scheduler_lesson_v1 fk_scheduler_lesson_v1_room; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_lesson_v1
    ADD CONSTRAINT fk_scheduler_lesson_v1_room FOREIGN KEY (organization_id, room_id) REFERENCES public.room(organization_id, id);


--
-- Name: scheduler_lesson_v1 fk_scheduler_lesson_v1_source; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_lesson_v1
    ADD CONSTRAINT fk_scheduler_lesson_v1_source FOREIGN KEY (organization_id, school_year_id, source_lesson_id) REFERENCES public.scheduler_lesson_v1(organization_id, school_year_id, id);


--
-- Name: scheduler_lesson_v1 fk_scheduler_lesson_v1_version; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_lesson_v1
    ADD CONSTRAINT fk_scheduler_lesson_v1_version FOREIGN KEY (organization_id, school_year_id, version_id) REFERENCES public.scheduler_version_v1(organization_id, school_year_id, id);


--
-- Name: scheduler_proposal_v1 fk_scheduler_proposal_v1_base_version; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_proposal_v1
    ADD CONSTRAINT fk_scheduler_proposal_v1_base_version FOREIGN KEY (organization_id, school_year_id, base_version_id) REFERENCES public.scheduler_version_v1(organization_id, school_year_id, id);


--
-- Name: scheduler_proposal_v1 fk_scheduler_proposal_v1_decider_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_proposal_v1
    ADD CONSTRAINT fk_scheduler_proposal_v1_decider_org FOREIGN KEY (organization_id, decided_by_membership_id) REFERENCES public.organization_membership(organization_id, id);


--
-- Name: scheduler_proposal_v1 fk_scheduler_proposal_v1_job; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_proposal_v1
    ADD CONSTRAINT fk_scheduler_proposal_v1_job FOREIGN KEY (organization_id, school_year_id, job_id) REFERENCES public.scheduler_job_v1(organization_id, school_year_id, id);


--
-- Name: scheduler_proposal_v1 fk_scheduler_proposal_v1_version; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_proposal_v1
    ADD CONSTRAINT fk_scheduler_proposal_v1_version FOREIGN KEY (organization_id, school_year_id, version_id) REFERENCES public.scheduler_version_v1(organization_id, school_year_id, id);


--
-- Name: scheduler_proposal_v1 fk_scheduler_proposal_v1_year_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_proposal_v1
    ADD CONSTRAINT fk_scheduler_proposal_v1_year_org FOREIGN KEY (organization_id, school_year_id) REFERENCES public.scheduler_school_year(organization_id, id);


--
-- Name: scheduler_recovery_reservation_v1 fk_scheduler_recovery_reservation_v1_debt; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_recovery_reservation_v1
    ADD CONSTRAINT fk_scheduler_recovery_reservation_v1_debt FOREIGN KEY (organization_id, debt_id) REFERENCES public.curricular_debt(organization_id, id);


--
-- Name: scheduler_recovery_reservation_v1 fk_scheduler_recovery_reservation_v1_debt_assignment; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_recovery_reservation_v1
    ADD CONSTRAINT fk_scheduler_recovery_reservation_v1_debt_assignment FOREIGN KEY (organization_id, assignment_id, debt_id) REFERENCES public.curricular_debt(organization_id, assignment_id, id);


--
-- Name: scheduler_recovery_reservation_v1 fk_scheduler_recovery_reservation_v1_lesson; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_recovery_reservation_v1
    ADD CONSTRAINT fk_scheduler_recovery_reservation_v1_lesson FOREIGN KEY (organization_id, school_year_id, version_id, lesson_id) REFERENCES public.scheduler_lesson_v1(organization_id, school_year_id, version_id, id);


--
-- Name: scheduler_recovery_reservation_v1 fk_scheduler_recovery_reservation_v1_lesson_assignment; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_recovery_reservation_v1
    ADD CONSTRAINT fk_scheduler_recovery_reservation_v1_lesson_assignment FOREIGN KEY (organization_id, school_year_id, assignment_id, lesson_id) REFERENCES public.scheduler_lesson_v1(organization_id, school_year_id, assignment_id, id);


--
-- Name: scheduler_school_year_state fk_scheduler_school_year_state_pending_draft_scope; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_school_year_state
    ADD CONSTRAINT fk_scheduler_school_year_state_pending_draft_scope FOREIGN KEY (pending_draft_id, organization_id, school_year_id) REFERENCES public.schedule_drafts(id, organization_id, school_year_id);


--
-- Name: scheduler_school_year_state fk_scheduler_school_year_state_reset_by_membership_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_school_year_state
    ADD CONSTRAINT fk_scheduler_school_year_state_reset_by_membership_id_org FOREIGN KEY (organization_id, reset_by_membership_id) REFERENCES public.organization_membership(organization_id, id);


--
-- Name: scheduler_school_year_state fk_scheduler_school_year_state_year_scope; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_school_year_state
    ADD CONSTRAINT fk_scheduler_school_year_state_year_scope FOREIGN KEY (school_year_id, organization_id) REFERENCES public.scheduler_school_year(id, organization_id) ON DELETE CASCADE;


--
-- Name: scheduler_state_version_events fk_scheduler_state_version_events_changed_by_membership_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_state_version_events
    ADD CONSTRAINT fk_scheduler_state_version_events_changed_by_membership_id_org FOREIGN KEY (organization_id, changed_by_membership_id) REFERENCES public.organization_membership(organization_id, id);


--
-- Name: scheduler_state_version_events fk_scheduler_state_version_events_state_scope; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_state_version_events
    ADD CONSTRAINT fk_scheduler_state_version_events_state_scope FOREIGN KEY (organization_id, school_year_id) REFERENCES public.scheduler_school_year_state(organization_id, school_year_id) ON DELETE CASCADE;


--
-- Name: scheduler_version_v1 fk_scheduler_version_v1_previous; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_version_v1
    ADD CONSTRAINT fk_scheduler_version_v1_previous FOREIGN KEY (organization_id, school_year_id, previous_version_id) REFERENCES public.scheduler_version_v1(organization_id, school_year_id, id);


--
-- Name: scheduler_version_v1 fk_scheduler_version_v1_year_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_version_v1
    ADD CONSTRAINT fk_scheduler_version_v1_year_org FOREIGN KEY (organization_id, school_year_id) REFERENCES public.scheduler_school_year(organization_id, id);


--
-- Name: teacher_endpoint_operational_event fk_teacher_endpoint_operational_event_actor_membership_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.teacher_endpoint_operational_event
    ADD CONSTRAINT fk_teacher_endpoint_operational_event_actor_membership_id_org FOREIGN KEY (organization_id, actor_membership_id) REFERENCES public.organization_membership(organization_id, id);


--
-- Name: teacher fk_teacher_organization_membership; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.teacher
    ADD CONSTRAINT fk_teacher_organization_membership FOREIGN KEY (organization_membership_id) REFERENCES public.organization_membership(id);


--
-- Name: teacher fk_teacher_organization_membership_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.teacher
    ADD CONSTRAINT fk_teacher_organization_membership_id_org FOREIGN KEY (organization_id, organization_membership_id) REFERENCES public.organization_membership(organization_id, id);


--
-- Name: teacher_subject_link fk_teacher_subject_link_subject_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.teacher_subject_link
    ADD CONSTRAINT fk_teacher_subject_link_subject_id_org FOREIGN KEY (organization_id, subject_id) REFERENCES public.subject(organization_id, id);


--
-- Name: teacher_subject_link fk_teacher_subject_link_teacher_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.teacher_subject_link
    ADD CONSTRAINT fk_teacher_subject_link_teacher_id_org FOREIGN KEY (organization_id, teacher_id) REFERENCES public.teacher(organization_id, id);


--
-- Name: teacher_weekly_timesheet fk_teacher_weekly_timesheet_approved_by_membership_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.teacher_weekly_timesheet
    ADD CONSTRAINT fk_teacher_weekly_timesheet_approved_by_membership_id_org FOREIGN KEY (organization_id, approved_by_membership_id) REFERENCES public.organization_membership(organization_id, id);


--
-- Name: teacher_weekly_timesheet fk_teacher_weekly_timesheet_teacher_id_org; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.teacher_weekly_timesheet
    ADD CONSTRAINT fk_teacher_weekly_timesheet_teacher_id_org FOREIGN KEY (organization_id, teacher_id) REFERENCES public.teacher(organization_id, id);


--
-- Name: lesson_log lesson_log_active_schedule_block_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_log
    ADD CONSTRAINT lesson_log_active_schedule_block_id_fkey FOREIGN KEY (active_schedule_block_id) REFERENCES public.active_schedule_blocks(id) ON DELETE RESTRICT;


--
-- Name: lesson_log lesson_log_logged_by_membership_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_log
    ADD CONSTRAINT lesson_log_logged_by_membership_id_fkey FOREIGN KEY (logged_by_membership_id) REFERENCES public.organization_membership(id) ON DELETE SET NULL;


--
-- Name: lesson_log lesson_log_operational_block_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_log
    ADD CONSTRAINT lesson_log_operational_block_id_fkey FOREIGN KEY (operational_block_id) REFERENCES public.operational_schedule_block(id) ON DELETE CASCADE;


--
-- Name: lesson_log lesson_log_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_log
    ADD CONSTRAINT lesson_log_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id) ON DELETE CASCADE;


--
-- Name: lesson_occurrence lesson_occurrence_class_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_occurrence
    ADD CONSTRAINT lesson_occurrence_class_id_fkey FOREIGN KEY (class_id) REFERENCES public.class(id) ON DELETE SET NULL;


--
-- Name: lesson_occurrence lesson_occurrence_created_by_membership_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_occurrence
    ADD CONSTRAINT lesson_occurrence_created_by_membership_id_fkey FOREIGN KEY (created_by_membership_id) REFERENCES public.organization_membership(id) ON DELETE SET NULL;


--
-- Name: lesson_occurrence lesson_occurrence_decided_by_membership_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_occurrence
    ADD CONSTRAINT lesson_occurrence_decided_by_membership_id_fkey FOREIGN KEY (decided_by_membership_id) REFERENCES public.organization_membership(id) ON DELETE SET NULL;


--
-- Name: lesson_occurrence lesson_occurrence_executed_module_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_occurrence
    ADD CONSTRAINT lesson_occurrence_executed_module_id_fkey FOREIGN KEY (executed_module_id) REFERENCES public.module(id) ON DELETE SET NULL;


--
-- Name: lesson_occurrence lesson_occurrence_executed_teacher_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_occurrence
    ADD CONSTRAINT lesson_occurrence_executed_teacher_id_fkey FOREIGN KEY (executed_teacher_id) REFERENCES public.teacher(id) ON DELETE SET NULL;


--
-- Name: lesson_occurrence lesson_occurrence_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_occurrence
    ADD CONSTRAINT lesson_occurrence_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id) ON DELETE CASCADE;


--
-- Name: lesson_occurrence lesson_occurrence_planned_module_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_occurrence
    ADD CONSTRAINT lesson_occurrence_planned_module_id_fkey FOREIGN KEY (planned_module_id) REFERENCES public.module(id) ON DELETE SET NULL;


--
-- Name: lesson_occurrence lesson_occurrence_planned_room_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_occurrence
    ADD CONSTRAINT lesson_occurrence_planned_room_id_fkey FOREIGN KEY (planned_room_id) REFERENCES public.room(id) ON DELETE SET NULL;


--
-- Name: lesson_occurrence lesson_occurrence_planned_teacher_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_occurrence
    ADD CONSTRAINT lesson_occurrence_planned_teacher_id_fkey FOREIGN KEY (planned_teacher_id) REFERENCES public.teacher(id) ON DELETE SET NULL;


--
-- Name: lesson_occurrence lesson_occurrence_planned_timeslot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_occurrence
    ADD CONSTRAINT lesson_occurrence_planned_timeslot_id_fkey FOREIGN KEY (planned_timeslot_id) REFERENCES public.timeslot(id) ON DELETE SET NULL;


--
-- Name: lesson_occurrence lesson_occurrence_revoked_by_membership_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_occurrence
    ADD CONSTRAINT lesson_occurrence_revoked_by_membership_id_fkey FOREIGN KEY (revoked_by_membership_id) REFERENCES public.organization_membership(id) ON DELETE SET NULL;


--
-- Name: lesson_occurrence lesson_occurrence_subject_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_occurrence
    ADD CONSTRAINT lesson_occurrence_subject_id_fkey FOREIGN KEY (subject_id) REFERENCES public.subject(id) ON DELETE SET NULL;


--
-- Name: lesson_occurrence lesson_occurrence_substitute_subject_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_occurrence
    ADD CONSTRAINT lesson_occurrence_substitute_subject_id_fkey FOREIGN KEY (substitute_subject_id) REFERENCES public.subject(id) ON DELETE SET NULL;


--
-- Name: lesson_occurrence lesson_occurrence_substitute_teacher_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.lesson_occurrence
    ADD CONSTRAINT lesson_occurrence_substitute_teacher_id_fkey FOREIGN KEY (substitute_teacher_id) REFERENCES public.teacher(id) ON DELETE SET NULL;


--
-- Name: member_access_operation member_access_operation_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.member_access_operation
    ADD CONSTRAINT member_access_operation_account_id_fkey FOREIGN KEY (account_id) REFERENCES public."user"(id) ON DELETE SET NULL;


--
-- Name: member_access_operation member_access_operation_created_by_membership_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.member_access_operation
    ADD CONSTRAINT member_access_operation_created_by_membership_id_fkey FOREIGN KEY (created_by_membership_id) REFERENCES public.organization_membership(id) ON DELETE RESTRICT;


--
-- Name: member_access_operation member_access_operation_membership_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.member_access_operation
    ADD CONSTRAINT member_access_operation_membership_id_fkey FOREIGN KEY (membership_id) REFERENCES public.organization_membership(id) ON DELETE SET NULL;


--
-- Name: member_access_operation member_access_operation_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.member_access_operation
    ADD CONSTRAINT member_access_operation_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id) ON DELETE CASCADE;


--
-- Name: member_access_operation member_access_operation_support_resolved_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.member_access_operation
    ADD CONSTRAINT member_access_operation_support_resolved_by_user_id_fkey FOREIGN KEY (support_resolved_by_user_id) REFERENCES public."user"(id) ON DELETE SET NULL;


--
-- Name: module module_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.module
    ADD CONSTRAINT module_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id) ON DELETE CASCADE;


--
-- Name: module module_subject_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.module
    ADD CONSTRAINT module_subject_id_fkey FOREIGN KEY (subject_id) REFERENCES public.subject(id);


--
-- Name: occurrence_operational_event occurrence_operational_event_active_schedule_block_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.occurrence_operational_event
    ADD CONSTRAINT occurrence_operational_event_active_schedule_block_id_fkey FOREIGN KEY (active_schedule_block_id) REFERENCES public.active_schedule_blocks(id) ON DELETE RESTRICT;


--
-- Name: occurrence_operational_event occurrence_operational_event_actor_membership_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.occurrence_operational_event
    ADD CONSTRAINT occurrence_operational_event_actor_membership_id_fkey FOREIGN KEY (actor_membership_id) REFERENCES public.organization_membership(id) ON DELETE SET NULL;


--
-- Name: occurrence_operational_event occurrence_operational_event_occurrence_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.occurrence_operational_event
    ADD CONSTRAINT occurrence_operational_event_occurrence_id_fkey FOREIGN KEY (occurrence_id) REFERENCES public.lesson_occurrence(id) ON DELETE SET NULL;


--
-- Name: occurrence_operational_event occurrence_operational_event_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.occurrence_operational_event
    ADD CONSTRAINT occurrence_operational_event_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id) ON DELETE CASCADE;


--
-- Name: operational_schedule_block operational_schedule_block_class_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.operational_schedule_block
    ADD CONSTRAINT operational_schedule_block_class_id_fkey FOREIGN KEY (class_id) REFERENCES public.class(id);


--
-- Name: operational_schedule_block operational_schedule_block_created_by_membership_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.operational_schedule_block
    ADD CONSTRAINT operational_schedule_block_created_by_membership_id_fkey FOREIGN KEY (created_by_membership_id) REFERENCES public.organization_membership(id) ON DELETE SET NULL;


--
-- Name: operational_schedule_block operational_schedule_block_module_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.operational_schedule_block
    ADD CONSTRAINT operational_schedule_block_module_id_fkey FOREIGN KEY (module_id) REFERENCES public.module(id) ON DELETE SET NULL;


--
-- Name: operational_schedule_block operational_schedule_block_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.operational_schedule_block
    ADD CONSTRAINT operational_schedule_block_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id) ON DELETE CASCADE;


--
-- Name: operational_schedule_block operational_schedule_block_planned_active_schedule_block_i_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.operational_schedule_block
    ADD CONSTRAINT operational_schedule_block_planned_active_schedule_block_i_fkey FOREIGN KEY (planned_active_schedule_block_id) REFERENCES public.active_schedule_blocks(id) ON DELETE RESTRICT;


--
-- Name: operational_schedule_block operational_schedule_block_room_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.operational_schedule_block
    ADD CONSTRAINT operational_schedule_block_room_id_fkey FOREIGN KEY (room_id) REFERENCES public.room(id) ON DELETE SET NULL;


--
-- Name: operational_schedule_block operational_schedule_block_source_occurrence_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.operational_schedule_block
    ADD CONSTRAINT operational_schedule_block_source_occurrence_id_fkey FOREIGN KEY (source_occurrence_id) REFERENCES public.lesson_occurrence(id) ON DELETE CASCADE;


--
-- Name: operational_schedule_block operational_schedule_block_subject_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.operational_schedule_block
    ADD CONSTRAINT operational_schedule_block_subject_id_fkey FOREIGN KEY (subject_id) REFERENCES public.subject(id);


--
-- Name: operational_schedule_block operational_schedule_block_teacher_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.operational_schedule_block
    ADD CONSTRAINT operational_schedule_block_teacher_id_fkey FOREIGN KEY (teacher_id) REFERENCES public.teacher(id);


--
-- Name: operational_schedule_block operational_schedule_block_timeslot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.operational_schedule_block
    ADD CONSTRAINT operational_schedule_block_timeslot_id_fkey FOREIGN KEY (timeslot_id) REFERENCES public.timeslot(id);


--
-- Name: organization_foundation_draft organization_foundation_draft_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.organization_foundation_draft
    ADD CONSTRAINT organization_foundation_draft_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id) ON DELETE CASCADE;


--
-- Name: organization_grid_settings organization_grid_settings_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.organization_grid_settings
    ADD CONSTRAINT organization_grid_settings_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id) ON DELETE CASCADE;


--
-- Name: organization_legal_acceptance organization_legal_acceptance_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.organization_legal_acceptance
    ADD CONSTRAINT organization_legal_acceptance_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id) ON DELETE RESTRICT;


--
-- Name: organization_membership organization_membership_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.organization_membership
    ADD CONSTRAINT organization_membership_account_id_fkey FOREIGN KEY (account_id) REFERENCES public."user"(id) ON DELETE CASCADE;


--
-- Name: organization_membership organization_membership_created_by_membership_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.organization_membership
    ADD CONSTRAINT organization_membership_created_by_membership_id_fkey FOREIGN KEY (created_by_membership_id) REFERENCES public.organization_membership(id) ON DELETE SET NULL;


--
-- Name: organization_membership organization_membership_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.organization_membership
    ADD CONSTRAINT organization_membership_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id) ON DELETE CASCADE;


--
-- Name: organization_membership organization_membership_updated_by_membership_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.organization_membership
    ADD CONSTRAINT organization_membership_updated_by_membership_id_fkey FOREIGN KEY (updated_by_membership_id) REFERENCES public.organization_membership(id) ON DELETE SET NULL;


--
-- Name: organization_settings organization_settings_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.organization_settings
    ADD CONSTRAINT organization_settings_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id) ON DELETE CASCADE;


--
-- Name: planned_recovery_links planned_recovery_links_class_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.planned_recovery_links
    ADD CONSTRAINT planned_recovery_links_class_id_fkey FOREIGN KEY (class_id) REFERENCES public.class(id);


--
-- Name: planned_recovery_links planned_recovery_links_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.planned_recovery_links
    ADD CONSTRAINT planned_recovery_links_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id) ON DELETE CASCADE;


--
-- Name: planned_recovery_links planned_recovery_links_school_year_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.planned_recovery_links
    ADD CONSTRAINT planned_recovery_links_school_year_id_fkey FOREIGN KEY (school_year_id) REFERENCES public.scheduler_school_year(id) ON DELETE CASCADE;


--
-- Name: planned_recovery_links planned_recovery_links_subject_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.planned_recovery_links
    ADD CONSTRAINT planned_recovery_links_subject_id_fkey FOREIGN KEY (subject_id) REFERENCES public.subject(id);


--
-- Name: planned_recovery_links planned_recovery_links_teacher_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.planned_recovery_links
    ADD CONSTRAINT planned_recovery_links_teacher_id_fkey FOREIGN KEY (teacher_id) REFERENCES public.teacher(id) ON DELETE SET NULL;


--
-- Name: progress_ledger_entry progress_ledger_entry_class_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.progress_ledger_entry
    ADD CONSTRAINT progress_ledger_entry_class_id_fkey FOREIGN KEY (class_id) REFERENCES public.class(id);


--
-- Name: progress_ledger_entry progress_ledger_entry_created_by_membership_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.progress_ledger_entry
    ADD CONSTRAINT progress_ledger_entry_created_by_membership_id_fkey FOREIGN KEY (created_by_membership_id) REFERENCES public.organization_membership(id) ON DELETE SET NULL;


--
-- Name: progress_ledger_entry progress_ledger_entry_module_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.progress_ledger_entry
    ADD CONSTRAINT progress_ledger_entry_module_id_fkey FOREIGN KEY (module_id) REFERENCES public.module(id);


--
-- Name: progress_ledger_entry progress_ledger_entry_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.progress_ledger_entry
    ADD CONSTRAINT progress_ledger_entry_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id) ON DELETE CASCADE;


--
-- Name: progress_ledger_entry progress_ledger_entry_reverses_ledger_entry_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.progress_ledger_entry
    ADD CONSTRAINT progress_ledger_entry_reverses_ledger_entry_id_fkey FOREIGN KEY (reverses_ledger_entry_id) REFERENCES public.progress_ledger_entry(id) ON DELETE SET NULL;


--
-- Name: room room_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.room
    ADD CONSTRAINT room_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id);


--
-- Name: schedule_diff_entries schedule_diff_entries_after_draft_block_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_diff_entries
    ADD CONSTRAINT schedule_diff_entries_after_draft_block_id_fkey FOREIGN KEY (after_draft_block_id) REFERENCES public.schedule_draft_blocks(id) ON DELETE SET NULL;


--
-- Name: schedule_diff_entries schedule_diff_entries_after_room_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_diff_entries
    ADD CONSTRAINT schedule_diff_entries_after_room_id_fkey FOREIGN KEY (after_room_id) REFERENCES public.room(id) ON DELETE SET NULL;


--
-- Name: schedule_diff_entries schedule_diff_entries_after_timeslot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_diff_entries
    ADD CONSTRAINT schedule_diff_entries_after_timeslot_id_fkey FOREIGN KEY (after_timeslot_id) REFERENCES public.timeslot(id) ON DELETE SET NULL;


--
-- Name: schedule_diff_entries schedule_diff_entries_before_room_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_diff_entries
    ADD CONSTRAINT schedule_diff_entries_before_room_id_fkey FOREIGN KEY (before_room_id) REFERENCES public.room(id) ON DELETE SET NULL;


--
-- Name: schedule_diff_entries schedule_diff_entries_before_timeslot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_diff_entries
    ADD CONSTRAINT schedule_diff_entries_before_timeslot_id_fkey FOREIGN KEY (before_timeslot_id) REFERENCES public.timeslot(id) ON DELETE SET NULL;


--
-- Name: schedule_diff_entries schedule_diff_entries_class_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_diff_entries
    ADD CONSTRAINT schedule_diff_entries_class_id_fkey FOREIGN KEY (class_id) REFERENCES public.class(id);


--
-- Name: schedule_diff_entries schedule_diff_entries_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_diff_entries
    ADD CONSTRAINT schedule_diff_entries_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id) ON DELETE CASCADE;


--
-- Name: schedule_diff_entries schedule_diff_entries_school_year_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_diff_entries
    ADD CONSTRAINT schedule_diff_entries_school_year_id_fkey FOREIGN KEY (school_year_id) REFERENCES public.scheduler_school_year(id) ON DELETE CASCADE;


--
-- Name: schedule_diff_entries schedule_diff_entries_subject_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_diff_entries
    ADD CONSTRAINT schedule_diff_entries_subject_id_fkey FOREIGN KEY (subject_id) REFERENCES public.subject(id);


--
-- Name: schedule_diff_entries schedule_diff_entries_teacher_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_diff_entries
    ADD CONSTRAINT schedule_diff_entries_teacher_id_fkey FOREIGN KEY (teacher_id) REFERENCES public.teacher(id);


--
-- Name: schedule_draft_blocks schedule_draft_blocks_class_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_draft_blocks
    ADD CONSTRAINT schedule_draft_blocks_class_id_fkey FOREIGN KEY (class_id) REFERENCES public.class(id);


--
-- Name: schedule_draft_blocks schedule_draft_blocks_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_draft_blocks
    ADD CONSTRAINT schedule_draft_blocks_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id) ON DELETE CASCADE;


--
-- Name: schedule_draft_blocks schedule_draft_blocks_recovery_source_occurrence_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_draft_blocks
    ADD CONSTRAINT schedule_draft_blocks_recovery_source_occurrence_id_fkey FOREIGN KEY (recovery_source_occurrence_id) REFERENCES public.lesson_occurrence(id) ON DELETE RESTRICT;


--
-- Name: schedule_draft_blocks schedule_draft_blocks_room_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_draft_blocks
    ADD CONSTRAINT schedule_draft_blocks_room_id_fkey FOREIGN KEY (room_id) REFERENCES public.room(id);


--
-- Name: schedule_draft_blocks schedule_draft_blocks_school_year_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_draft_blocks
    ADD CONSTRAINT schedule_draft_blocks_school_year_id_fkey FOREIGN KEY (school_year_id) REFERENCES public.scheduler_school_year(id) ON DELETE CASCADE;


--
-- Name: schedule_draft_blocks schedule_draft_blocks_subject_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_draft_blocks
    ADD CONSTRAINT schedule_draft_blocks_subject_id_fkey FOREIGN KEY (subject_id) REFERENCES public.subject(id);


--
-- Name: schedule_draft_blocks schedule_draft_blocks_teacher_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_draft_blocks
    ADD CONSTRAINT schedule_draft_blocks_teacher_id_fkey FOREIGN KEY (teacher_id) REFERENCES public.teacher(id);


--
-- Name: schedule_draft_blocks schedule_draft_blocks_timeslot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_draft_blocks
    ADD CONSTRAINT schedule_draft_blocks_timeslot_id_fkey FOREIGN KEY (timeslot_id) REFERENCES public.timeslot(id);


--
-- Name: schedule_drafts schedule_drafts_created_by_membership_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_drafts
    ADD CONSTRAINT schedule_drafts_created_by_membership_id_fkey FOREIGN KEY (created_by_membership_id) REFERENCES public.organization_membership(id) ON DELETE RESTRICT;


--
-- Name: schedule_drafts schedule_drafts_decided_by_membership_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_drafts
    ADD CONSTRAINT schedule_drafts_decided_by_membership_id_fkey FOREIGN KEY (decided_by_membership_id) REFERENCES public.organization_membership(id) ON DELETE SET NULL;


--
-- Name: schedule_drafts schedule_drafts_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_drafts
    ADD CONSTRAINT schedule_drafts_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id) ON DELETE CASCADE;


--
-- Name: schedule_drafts schedule_drafts_school_year_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_drafts
    ADD CONSTRAINT schedule_drafts_school_year_id_fkey FOREIGN KEY (school_year_id) REFERENCES public.scheduler_school_year(id) ON DELETE CASCADE;


--
-- Name: schedule_generation_job schedule_generation_job_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_generation_job
    ADD CONSTRAINT schedule_generation_job_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id) ON DELETE CASCADE;


--
-- Name: schedule_generation_job schedule_generation_job_requested_by_membership_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.schedule_generation_job
    ADD CONSTRAINT schedule_generation_job_requested_by_membership_id_fkey FOREIGN KEY (requested_by_membership_id) REFERENCES public.organization_membership(id) ON DELETE SET NULL;


--
-- Name: scheduler_job_v1 scheduler_job_v1_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_job_v1
    ADD CONSTRAINT scheduler_job_v1_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id);


--
-- Name: scheduler_lesson_log_v1 scheduler_lesson_log_v1_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_lesson_log_v1
    ADD CONSTRAINT scheduler_lesson_log_v1_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id) ON DELETE CASCADE;


--
-- Name: scheduler_lesson_slice_v1 scheduler_lesson_slice_v1_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_lesson_slice_v1
    ADD CONSTRAINT scheduler_lesson_slice_v1_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id);


--
-- Name: scheduler_lesson_v1 scheduler_lesson_v1_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_lesson_v1
    ADD CONSTRAINT scheduler_lesson_v1_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id);


--
-- Name: scheduler_proposal_v1 scheduler_proposal_v1_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_proposal_v1
    ADD CONSTRAINT scheduler_proposal_v1_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id);


--
-- Name: scheduler_recovery_reservation_v1 scheduler_recovery_reservation_v1_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_recovery_reservation_v1
    ADD CONSTRAINT scheduler_recovery_reservation_v1_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id);


--
-- Name: scheduler_school_year scheduler_school_year_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_school_year
    ADD CONSTRAINT scheduler_school_year_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id) ON DELETE CASCADE;


--
-- Name: scheduler_school_year_state scheduler_school_year_state_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_school_year_state
    ADD CONSTRAINT scheduler_school_year_state_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id) ON DELETE CASCADE;


--
-- Name: scheduler_school_year_state scheduler_school_year_state_reset_by_membership_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_school_year_state
    ADD CONSTRAINT scheduler_school_year_state_reset_by_membership_id_fkey FOREIGN KEY (reset_by_membership_id) REFERENCES public.organization_membership(id) ON DELETE SET NULL;


--
-- Name: scheduler_state_version_events scheduler_state_version_events_changed_by_membership_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_state_version_events
    ADD CONSTRAINT scheduler_state_version_events_changed_by_membership_id_fkey FOREIGN KEY (changed_by_membership_id) REFERENCES public.organization_membership(id) ON DELETE SET NULL;


--
-- Name: scheduler_version_v1 scheduler_version_v1_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.scheduler_version_v1
    ADD CONSTRAINT scheduler_version_v1_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id);


--
-- Name: school_calendar_event school_calendar_event_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.school_calendar_event
    ADD CONSTRAINT school_calendar_event_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id) ON DELETE CASCADE;


--
-- Name: subject subject_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.subject
    ADD CONSTRAINT subject_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id);


--
-- Name: teacher_endpoint_operational_event teacher_endpoint_operational_event_actor_membership_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.teacher_endpoint_operational_event
    ADD CONSTRAINT teacher_endpoint_operational_event_actor_membership_id_fkey FOREIGN KEY (actor_membership_id) REFERENCES public.organization_membership(id) ON DELETE SET NULL;


--
-- Name: teacher_endpoint_operational_event teacher_endpoint_operational_event_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.teacher_endpoint_operational_event
    ADD CONSTRAINT teacher_endpoint_operational_event_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id) ON DELETE CASCADE;


--
-- Name: teacher teacher_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.teacher
    ADD CONSTRAINT teacher_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id);


--
-- Name: teacher_subject_link teacher_subject_link_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.teacher_subject_link
    ADD CONSTRAINT teacher_subject_link_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id) ON DELETE CASCADE;


--
-- Name: teacher_subject_link teacher_subject_link_subject_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.teacher_subject_link
    ADD CONSTRAINT teacher_subject_link_subject_id_fkey FOREIGN KEY (subject_id) REFERENCES public.subject(id) ON DELETE CASCADE;


--
-- Name: teacher_subject_link teacher_subject_link_teacher_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.teacher_subject_link
    ADD CONSTRAINT teacher_subject_link_teacher_id_fkey FOREIGN KEY (teacher_id) REFERENCES public.teacher(id) ON DELETE CASCADE;


--
-- Name: teacher_weekly_timesheet teacher_weekly_timesheet_approved_by_membership_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.teacher_weekly_timesheet
    ADD CONSTRAINT teacher_weekly_timesheet_approved_by_membership_id_fkey FOREIGN KEY (approved_by_membership_id) REFERENCES public.organization_membership(id) ON DELETE SET NULL;


--
-- Name: teacher_weekly_timesheet teacher_weekly_timesheet_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.teacher_weekly_timesheet
    ADD CONSTRAINT teacher_weekly_timesheet_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id) ON DELETE CASCADE;


--
-- Name: teacher_weekly_timesheet teacher_weekly_timesheet_teacher_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.teacher_weekly_timesheet
    ADD CONSTRAINT teacher_weekly_timesheet_teacher_id_fkey FOREIGN KEY (teacher_id) REFERENCES public.teacher(id) ON DELETE CASCADE;


--
-- Name: timeslot timeslot_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: cronos_migrator
--

ALTER TABLE ONLY public.timeslot
    ADD CONSTRAINT timeslot_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id);


--
-- Name: active_schedule_blocks; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.active_schedule_blocks ENABLE ROW LEVEL SECURITY;

--
-- Name: availability; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.availability ENABLE ROW LEVEL SECURITY;

--
-- Name: class; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.class ENABLE ROW LEVEL SECURITY;

--
-- Name: class_subject_link; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.class_subject_link ENABLE ROW LEVEL SECURITY;

--
-- Name: constraint; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public."constraint" ENABLE ROW LEVEL SECURITY;

--
-- Name: course; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.course ENABLE ROW LEVEL SECURITY;

--
-- Name: course_subject_link; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.course_subject_link ENABLE ROW LEVEL SECURITY;

--
-- Name: curricular_assignment; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.curricular_assignment ENABLE ROW LEVEL SECURITY;

--
-- Name: curricular_debt; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.curricular_debt ENABLE ROW LEVEL SECURITY;

--
-- Name: curricular_debt_revision; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.curricular_debt_revision ENABLE ROW LEVEL SECURITY;

--
-- Name: curricular_debt_settlement; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.curricular_debt_settlement ENABLE ROW LEVEL SECURITY;

--
-- Name: curricular_execution; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.curricular_execution ENABLE ROW LEVEL SECURITY;

--
-- Name: curricular_execution_credit; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.curricular_execution_credit ENABLE ROW LEVEL SECURITY;

--
-- Name: curricular_requirement; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.curricular_requirement ENABLE ROW LEVEL SECURITY;

--
-- Name: lesson_log; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.lesson_log ENABLE ROW LEVEL SECURITY;

--
-- Name: lesson_occurrence; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.lesson_occurrence ENABLE ROW LEVEL SECURITY;

--
-- Name: member_access_operation; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.member_access_operation ENABLE ROW LEVEL SECURITY;

--
-- Name: module; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.module ENABLE ROW LEVEL SECURITY;

--
-- Name: occurrence_operational_event; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.occurrence_operational_event ENABLE ROW LEVEL SECURITY;

--
-- Name: operational_schedule_block; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.operational_schedule_block ENABLE ROW LEVEL SECURITY;

--
-- Name: organization; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.organization ENABLE ROW LEVEL SECURITY;

--
-- Name: organization_foundation_draft; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.organization_foundation_draft ENABLE ROW LEVEL SECURITY;

--
-- Name: organization_foundation_draft organization_foundation_draft_tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY organization_foundation_draft_tenant_isolation ON public.organization_foundation_draft USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: organization_grid_settings; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.organization_grid_settings ENABLE ROW LEVEL SECURITY;

--
-- Name: organization_legal_acceptance; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.organization_legal_acceptance ENABLE ROW LEVEL SECURITY;

--
-- Name: organization_legal_acceptance organization_legal_acceptance_insert; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY organization_legal_acceptance_insert ON public.organization_legal_acceptance FOR INSERT WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: organization_legal_acceptance organization_legal_acceptance_select; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY organization_legal_acceptance_select ON public.organization_legal_acceptance FOR SELECT USING ((organization_id = app_security.current_organization_id()));


--
-- Name: organization_membership; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.organization_membership ENABLE ROW LEVEL SECURITY;

--
-- Name: organization_settings; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.organization_settings ENABLE ROW LEVEL SECURITY;

--
-- Name: planned_recovery_links; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.planned_recovery_links ENABLE ROW LEVEL SECURITY;

--
-- Name: progress_ledger_entry; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.progress_ledger_entry ENABLE ROW LEVEL SECURITY;

--
-- Name: room; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.room ENABLE ROW LEVEL SECURITY;

--
-- Name: schedule_diff_entries; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.schedule_diff_entries ENABLE ROW LEVEL SECURITY;

--
-- Name: schedule_draft_blocks; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.schedule_draft_blocks ENABLE ROW LEVEL SECURITY;

--
-- Name: schedule_drafts; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.schedule_drafts ENABLE ROW LEVEL SECURITY;

--
-- Name: schedule_generation_job; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.schedule_generation_job ENABLE ROW LEVEL SECURITY;

--
-- Name: scheduler_job_v1; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.scheduler_job_v1 ENABLE ROW LEVEL SECURITY;

--
-- Name: scheduler_lesson_log_v1; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.scheduler_lesson_log_v1 ENABLE ROW LEVEL SECURITY;

--
-- Name: scheduler_lesson_slice_v1; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.scheduler_lesson_slice_v1 ENABLE ROW LEVEL SECURITY;

--
-- Name: scheduler_lesson_v1; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.scheduler_lesson_v1 ENABLE ROW LEVEL SECURITY;

--
-- Name: scheduler_proposal_v1; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.scheduler_proposal_v1 ENABLE ROW LEVEL SECURITY;

--
-- Name: scheduler_recovery_reservation_v1; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.scheduler_recovery_reservation_v1 ENABLE ROW LEVEL SECURITY;

--
-- Name: scheduler_school_year; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.scheduler_school_year ENABLE ROW LEVEL SECURITY;

--
-- Name: scheduler_school_year_state; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.scheduler_school_year_state ENABLE ROW LEVEL SECURITY;

--
-- Name: scheduler_state_version_events; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.scheduler_state_version_events ENABLE ROW LEVEL SECURITY;

--
-- Name: scheduler_version_v1; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.scheduler_version_v1 ENABLE ROW LEVEL SECURITY;

--
-- Name: school_calendar_event; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.school_calendar_event ENABLE ROW LEVEL SECURITY;

--
-- Name: subject; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.subject ENABLE ROW LEVEL SECURITY;

--
-- Name: teacher; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.teacher ENABLE ROW LEVEL SECURITY;

--
-- Name: teacher_endpoint_operational_event; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.teacher_endpoint_operational_event ENABLE ROW LEVEL SECURITY;

--
-- Name: teacher_subject_link; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.teacher_subject_link ENABLE ROW LEVEL SECURITY;

--
-- Name: teacher_weekly_timesheet; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.teacher_weekly_timesheet ENABLE ROW LEVEL SECURITY;

--
-- Name: active_schedule_blocks tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.active_schedule_blocks TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: availability tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.availability TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: class tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.class TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: class_subject_link tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.class_subject_link TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: constraint tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public."constraint" TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: course tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.course TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: course_subject_link tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.course_subject_link TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: curricular_assignment tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.curricular_assignment TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: curricular_debt tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.curricular_debt TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: curricular_debt_revision tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.curricular_debt_revision TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: curricular_debt_settlement tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.curricular_debt_settlement TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: curricular_execution tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.curricular_execution TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: curricular_execution_credit tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.curricular_execution_credit TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: curricular_requirement tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.curricular_requirement TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: lesson_log tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.lesson_log TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: lesson_occurrence tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.lesson_occurrence TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: member_access_operation tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.member_access_operation TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: module tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.module TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: occurrence_operational_event tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.occurrence_operational_event TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: operational_schedule_block tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.operational_schedule_block TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: organization tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.organization TO cronos_app USING ((id = app_security.current_organization_id())) WITH CHECK ((id = app_security.current_organization_id()));


--
-- Name: organization_grid_settings tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.organization_grid_settings TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: organization_membership tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.organization_membership TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: organization_settings tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.organization_settings TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: planned_recovery_links tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.planned_recovery_links TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: progress_ledger_entry tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.progress_ledger_entry TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: room tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.room TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: schedule_diff_entries tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.schedule_diff_entries TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: schedule_draft_blocks tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.schedule_draft_blocks TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: schedule_drafts tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.schedule_drafts TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: schedule_generation_job tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.schedule_generation_job TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: scheduler_job_v1 tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.scheduler_job_v1 TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: scheduler_lesson_log_v1 tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.scheduler_lesson_log_v1 TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: scheduler_lesson_slice_v1 tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.scheduler_lesson_slice_v1 TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: scheduler_lesson_v1 tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.scheduler_lesson_v1 TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: scheduler_proposal_v1 tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.scheduler_proposal_v1 TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: scheduler_recovery_reservation_v1 tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.scheduler_recovery_reservation_v1 TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: scheduler_school_year tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.scheduler_school_year TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: scheduler_school_year_state tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.scheduler_school_year_state TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: scheduler_state_version_events tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.scheduler_state_version_events TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: scheduler_version_v1 tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.scheduler_version_v1 TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: school_calendar_event tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.school_calendar_event TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: subject tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.subject TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: teacher tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.teacher TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: teacher_endpoint_operational_event tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.teacher_endpoint_operational_event TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: teacher_subject_link tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.teacher_subject_link TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: teacher_weekly_timesheet tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.teacher_weekly_timesheet TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: timeslot tenant_isolation; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_isolation ON public.timeslot TO cronos_app USING ((organization_id = app_security.current_organization_id())) WITH CHECK ((organization_id = app_security.current_organization_id()));


--
-- Name: user tenant_membership_accounts; Type: POLICY; Schema: public; Owner: cronos_migrator
--

CREATE POLICY tenant_membership_accounts ON public."user" TO cronos_app USING ((EXISTS ( SELECT 1
   FROM public.organization_membership m
  WHERE ((m.account_id = "user".id) AND (m.organization_id = app_security.current_organization_id())))));


--
-- Name: timeslot; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public.timeslot ENABLE ROW LEVEL SECURITY;

--
-- Name: user; Type: ROW SECURITY; Schema: public; Owner: cronos_migrator
--

ALTER TABLE public."user" ENABLE ROW LEVEL SECURITY;

--
-- Name: SCHEMA app_security; Type: ACL; Schema: -; Owner: cronos_auth_definer
--

GRANT USAGE ON SCHEMA app_security TO cronos_app;


--
-- Name: SCHEMA public; Type: ACL; Schema: -; Owner: pg_database_owner
--

GRANT USAGE ON SCHEMA public TO cronos_app;
GRANT USAGE ON SCHEMA public TO cronos_auth_definer;


--
-- Name: FUNCTION bootstrap_organization_admin(requested_clerk_user_id text, requested_clerk_org_id text, requested_organization_name text, requested_email text, requested_profile_name text, requested_membership_id text); Type: ACL; Schema: app_security; Owner: cronos_auth_definer
--

REVOKE ALL ON FUNCTION app_security.bootstrap_organization_admin(requested_clerk_user_id text, requested_clerk_org_id text, requested_organization_name text, requested_email text, requested_profile_name text, requested_membership_id text) FROM PUBLIC;
GRANT ALL ON FUNCTION app_security.bootstrap_organization_admin(requested_clerk_user_id text, requested_clerk_org_id text, requested_organization_name text, requested_email text, requested_profile_name text, requested_membership_id text) TO cronos_app;


--
-- Name: FUNCTION current_organization_id(); Type: ACL; Schema: app_security; Owner: cronos_migrator
--

REVOKE ALL ON FUNCTION app_security.current_organization_id() FROM PUBLIC;
GRANT ALL ON FUNCTION app_security.current_organization_id() TO cronos_app;


--
-- Name: FUNCTION deactivate_organization(requested_clerk_org_id text); Type: ACL; Schema: app_security; Owner: cronos_auth_definer
--

REVOKE ALL ON FUNCTION app_security.deactivate_organization(requested_clerk_org_id text) FROM PUBLIC;
GRANT ALL ON FUNCTION app_security.deactivate_organization(requested_clerk_org_id text) TO cronos_app;


--
-- Name: FUNCTION deactivate_user(requested_clerk_user_id text); Type: ACL; Schema: app_security; Owner: cronos_auth_definer
--

REVOKE ALL ON FUNCTION app_security.deactivate_user(requested_clerk_user_id text) FROM PUBLIC;
GRANT ALL ON FUNCTION app_security.deactivate_user(requested_clerk_user_id text) TO cronos_app;


--
-- Name: FUNCTION ensure_organization(requested_clerk_org_id text, requested_name text); Type: ACL; Schema: app_security; Owner: cronos_auth_definer
--

REVOKE ALL ON FUNCTION app_security.ensure_organization(requested_clerk_org_id text, requested_name text) FROM PUBLIC;
GRANT ALL ON FUNCTION app_security.ensure_organization(requested_clerk_org_id text, requested_name text) TO cronos_app;


--
-- Name: FUNCTION ensure_pending_account(requested_organization_id integer, requested_email text, requested_name text); Type: ACL; Schema: app_security; Owner: cronos_auth_definer
--

REVOKE ALL ON FUNCTION app_security.ensure_pending_account(requested_organization_id integer, requested_email text, requested_name text) FROM PUBLIC;
GRANT ALL ON FUNCTION app_security.ensure_pending_account(requested_organization_id integer, requested_email text, requested_name text) TO cronos_app;


--
-- Name: FUNCTION ensure_user(requested_clerk_user_id text, requested_email text, requested_name text, requested_role text, requested_organization_id integer, requested_teacher_id integer); Type: ACL; Schema: app_security; Owner: cronos_auth_definer
--

REVOKE ALL ON FUNCTION app_security.ensure_user(requested_clerk_user_id text, requested_email text, requested_name text, requested_role text, requested_organization_id integer, requested_teacher_id integer) FROM PUBLIC;
GRANT ALL ON FUNCTION app_security.ensure_user(requested_clerk_user_id text, requested_email text, requested_name text, requested_role text, requested_organization_id integer, requested_teacher_id integer) TO cronos_app;


--
-- Name: FUNCTION find_clerk_user_by_email(requested_email text, excluded_clerk_user_id text); Type: ACL; Schema: app_security; Owner: cronos_auth_definer
--

REVOKE ALL ON FUNCTION app_security.find_clerk_user_by_email(requested_email text, excluded_clerk_user_id text) FROM PUBLIC;
GRANT ALL ON FUNCTION app_security.find_clerk_user_by_email(requested_email text, excluded_clerk_user_id text) TO cronos_app;


--
-- Name: FUNCTION list_reconciliation_organization_ids(); Type: ACL; Schema: app_security; Owner: cronos_auth_definer
--

REVOKE ALL ON FUNCTION app_security.list_reconciliation_organization_ids() FROM PUBLIC;
GRANT ALL ON FUNCTION app_security.list_reconciliation_organization_ids() TO cronos_app;


--
-- Name: FUNCTION list_scheduler_v1_jobs_for_executor(); Type: ACL; Schema: app_security; Owner: cronos_auth_definer
--

REVOKE ALL ON FUNCTION app_security.list_scheduler_v1_jobs_for_executor() FROM PUBLIC;
GRANT ALL ON FUNCTION app_security.list_scheduler_v1_jobs_for_executor() TO cronos_app;


--
-- Name: FUNCTION reclaim_deleted_clerk_identity(requested_clerk_user_id text); Type: ACL; Schema: app_security; Owner: cronos_auth_definer
--

REVOKE ALL ON FUNCTION app_security.reclaim_deleted_clerk_identity(requested_clerk_user_id text) FROM PUBLIC;
GRANT ALL ON FUNCTION app_security.reclaim_deleted_clerk_identity(requested_clerk_user_id text) TO cronos_app;


--
-- Name: FUNCTION resolve_principal(requested_clerk_user_id text, requested_clerk_org_id text); Type: ACL; Schema: app_security; Owner: cronos_auth_definer
--

REVOKE ALL ON FUNCTION app_security.resolve_principal(requested_clerk_user_id text, requested_clerk_org_id text) FROM PUBLIC;
GRANT ALL ON FUNCTION app_security.resolve_principal(requested_clerk_user_id text, requested_clerk_org_id text) TO cronos_app;


--
-- Name: FUNCTION resolve_webhook_organization(requested_clerk_org_id text); Type: ACL; Schema: app_security; Owner: cronos_auth_definer
--

REVOKE ALL ON FUNCTION app_security.resolve_webhook_organization(requested_clerk_org_id text) FROM PUBLIC;
GRANT ALL ON FUNCTION app_security.resolve_webhook_organization(requested_clerk_org_id text) TO cronos_app;


--
-- Name: FUNCTION scheduler_v1_queue_position(requested_job_id integer); Type: ACL; Schema: app_security; Owner: cronos_auth_definer
--

REVOKE ALL ON FUNCTION app_security.scheduler_v1_queue_position(requested_job_id integer) FROM PUBLIC;
GRANT ALL ON FUNCTION app_security.scheduler_v1_queue_position(requested_job_id integer) TO cronos_app;


--
-- Name: FUNCTION update_pending_account_email(requested_organization_id integer, requested_account_id integer, requested_email text); Type: ACL; Schema: app_security; Owner: cronos_auth_definer
--

REVOKE ALL ON FUNCTION app_security.update_pending_account_email(requested_organization_id integer, requested_account_id integer, requested_email text) FROM PUBLIC;
GRANT ALL ON FUNCTION app_security.update_pending_account_email(requested_organization_id integer, requested_account_id integer, requested_email text) TO cronos_app;


--
-- Name: FUNCTION update_user_profile(requested_clerk_user_id text, requested_email text, requested_name text, requested_role text, requested_teacher_id integer); Type: ACL; Schema: app_security; Owner: cronos_auth_definer
--

REVOKE ALL ON FUNCTION app_security.update_user_profile(requested_clerk_user_id text, requested_email text, requested_name text, requested_role text, requested_teacher_id integer) FROM PUBLIC;
GRANT ALL ON FUNCTION app_security.update_user_profile(requested_clerk_user_id text, requested_email text, requested_name text, requested_role text, requested_teacher_id integer) TO cronos_app;


--
-- Name: TABLE active_schedule_blocks; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.active_schedule_blocks TO cronos_app;


--
-- Name: SEQUENCE active_schedule_blocks_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.active_schedule_blocks_id_seq TO cronos_app;
GRANT SELECT,USAGE ON SEQUENCE public.active_schedule_blocks_id_seq TO cronos_auth_definer;


--
-- Name: TABLE availability; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.availability TO cronos_app;


--
-- Name: SEQUENCE availability_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.availability_id_seq TO cronos_app;
GRANT SELECT,USAGE ON SEQUENCE public.availability_id_seq TO cronos_auth_definer;


--
-- Name: TABLE class; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.class TO cronos_app;


--
-- Name: SEQUENCE class_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.class_id_seq TO cronos_app;
GRANT SELECT,USAGE ON SEQUENCE public.class_id_seq TO cronos_auth_definer;


--
-- Name: TABLE class_subject_link; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.class_subject_link TO cronos_app;


--
-- Name: SEQUENCE class_subject_link_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.class_subject_link_id_seq TO cronos_app;
GRANT SELECT,USAGE ON SEQUENCE public.class_subject_link_id_seq TO cronos_auth_definer;


--
-- Name: TABLE clerk_webhook_event; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.clerk_webhook_event TO cronos_app;


--
-- Name: SEQUENCE clerk_webhook_event_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.clerk_webhook_event_id_seq TO cronos_app;
GRANT SELECT,USAGE ON SEQUENCE public.clerk_webhook_event_id_seq TO cronos_auth_definer;


--
-- Name: TABLE "constraint"; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public."constraint" TO cronos_app;


--
-- Name: SEQUENCE constraint_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.constraint_id_seq TO cronos_app;
GRANT SELECT,USAGE ON SEQUENCE public.constraint_id_seq TO cronos_auth_definer;


--
-- Name: TABLE course; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.course TO cronos_app;


--
-- Name: SEQUENCE course_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.course_id_seq TO cronos_app;
GRANT SELECT,USAGE ON SEQUENCE public.course_id_seq TO cronos_auth_definer;


--
-- Name: TABLE course_subject_link; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.course_subject_link TO cronos_app;


--
-- Name: TABLE curricular_assignment; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.curricular_assignment TO cronos_app;


--
-- Name: SEQUENCE curricular_assignment_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.curricular_assignment_id_seq TO cronos_app;


--
-- Name: TABLE curricular_debt; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT ON TABLE public.curricular_debt TO cronos_app;


--
-- Name: SEQUENCE curricular_debt_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.curricular_debt_id_seq TO cronos_app;


--
-- Name: TABLE curricular_debt_revision; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT ON TABLE public.curricular_debt_revision TO cronos_app;


--
-- Name: SEQUENCE curricular_debt_revision_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.curricular_debt_revision_id_seq TO cronos_app;


--
-- Name: TABLE curricular_debt_settlement; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT ON TABLE public.curricular_debt_settlement TO cronos_app;


--
-- Name: SEQUENCE curricular_debt_settlement_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.curricular_debt_settlement_id_seq TO cronos_app;


--
-- Name: TABLE curricular_execution; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT ON TABLE public.curricular_execution TO cronos_app;


--
-- Name: TABLE curricular_execution_credit; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT ON TABLE public.curricular_execution_credit TO cronos_app;


--
-- Name: SEQUENCE curricular_execution_credit_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.curricular_execution_credit_id_seq TO cronos_app;


--
-- Name: SEQUENCE curricular_execution_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.curricular_execution_id_seq TO cronos_app;


--
-- Name: TABLE curricular_requirement; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.curricular_requirement TO cronos_app;


--
-- Name: SEQUENCE curricular_requirement_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.curricular_requirement_id_seq TO cronos_app;


--
-- Name: TABLE lesson_log; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.lesson_log TO cronos_app;


--
-- Name: SEQUENCE lesson_log_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.lesson_log_id_seq TO cronos_app;
GRANT SELECT,USAGE ON SEQUENCE public.lesson_log_id_seq TO cronos_auth_definer;


--
-- Name: TABLE lesson_occurrence; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.lesson_occurrence TO cronos_app;


--
-- Name: SEQUENCE lesson_occurrence_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.lesson_occurrence_id_seq TO cronos_app;
GRANT SELECT,USAGE ON SEQUENCE public.lesson_occurrence_id_seq TO cronos_auth_definer;


--
-- Name: TABLE member_access_operation; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.member_access_operation TO cronos_app;


--
-- Name: SEQUENCE member_access_operation_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.member_access_operation_id_seq TO cronos_app;
GRANT SELECT,USAGE ON SEQUENCE public.member_access_operation_id_seq TO cronos_auth_definer;


--
-- Name: TABLE module; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.module TO cronos_app;


--
-- Name: SEQUENCE module_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.module_id_seq TO cronos_app;
GRANT SELECT,USAGE ON SEQUENCE public.module_id_seq TO cronos_auth_definer;


--
-- Name: TABLE occurrence_operational_event; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT ON TABLE public.occurrence_operational_event TO cronos_app;


--
-- Name: SEQUENCE occurrence_operational_event_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.occurrence_operational_event_id_seq TO cronos_app;
GRANT SELECT,USAGE ON SEQUENCE public.occurrence_operational_event_id_seq TO cronos_auth_definer;


--
-- Name: TABLE operational_schedule_block; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.operational_schedule_block TO cronos_app;


--
-- Name: SEQUENCE operational_schedule_block_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.operational_schedule_block_id_seq TO cronos_app;
GRANT SELECT,USAGE ON SEQUENCE public.operational_schedule_block_id_seq TO cronos_auth_definer;


--
-- Name: TABLE organization; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.organization TO cronos_app;
GRANT SELECT,INSERT,UPDATE ON TABLE public.organization TO cronos_auth_definer;


--
-- Name: TABLE organization_foundation_draft; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.organization_foundation_draft TO cronos_app;


--
-- Name: TABLE organization_grid_settings; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.organization_grid_settings TO cronos_app;


--
-- Name: SEQUENCE organization_grid_settings_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.organization_grid_settings_id_seq TO cronos_app;
GRANT SELECT,USAGE ON SEQUENCE public.organization_grid_settings_id_seq TO cronos_auth_definer;


--
-- Name: SEQUENCE organization_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.organization_id_seq TO cronos_app;
GRANT SELECT,USAGE ON SEQUENCE public.organization_id_seq TO cronos_auth_definer;


--
-- Name: TABLE organization_legal_acceptance; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT ON TABLE public.organization_legal_acceptance TO cronos_app;


--
-- Name: SEQUENCE organization_legal_acceptance_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.organization_legal_acceptance_id_seq TO cronos_app;


--
-- Name: TABLE organization_membership; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.organization_membership TO cronos_app;
GRANT SELECT,INSERT,UPDATE ON TABLE public.organization_membership TO cronos_auth_definer;


--
-- Name: SEQUENCE organization_membership_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.organization_membership_id_seq TO cronos_app;
GRANT SELECT,USAGE ON SEQUENCE public.organization_membership_id_seq TO cronos_auth_definer;


--
-- Name: TABLE organization_settings; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.organization_settings TO cronos_app;


--
-- Name: SEQUENCE organization_settings_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.organization_settings_id_seq TO cronos_app;
GRANT SELECT,USAGE ON SEQUENCE public.organization_settings_id_seq TO cronos_auth_definer;


--
-- Name: TABLE planned_recovery_links; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.planned_recovery_links TO cronos_app;


--
-- Name: SEQUENCE planned_recovery_links_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.planned_recovery_links_id_seq TO cronos_app;
GRANT SELECT,USAGE ON SEQUENCE public.planned_recovery_links_id_seq TO cronos_auth_definer;


--
-- Name: TABLE progress_ledger_entry; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT ON TABLE public.progress_ledger_entry TO cronos_app;


--
-- Name: SEQUENCE progress_ledger_entry_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.progress_ledger_entry_id_seq TO cronos_app;
GRANT SELECT,USAGE ON SEQUENCE public.progress_ledger_entry_id_seq TO cronos_auth_definer;


--
-- Name: TABLE room; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.room TO cronos_app;


--
-- Name: SEQUENCE room_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.room_id_seq TO cronos_app;
GRANT SELECT,USAGE ON SEQUENCE public.room_id_seq TO cronos_auth_definer;


--
-- Name: TABLE schedule_diff_entries; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT ON TABLE public.schedule_diff_entries TO cronos_app;


--
-- Name: SEQUENCE schedule_diff_entries_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.schedule_diff_entries_id_seq TO cronos_app;
GRANT SELECT,USAGE ON SEQUENCE public.schedule_diff_entries_id_seq TO cronos_auth_definer;


--
-- Name: TABLE schedule_draft_blocks; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT ON TABLE public.schedule_draft_blocks TO cronos_app;


--
-- Name: SEQUENCE schedule_draft_blocks_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.schedule_draft_blocks_id_seq TO cronos_app;
GRANT SELECT,USAGE ON SEQUENCE public.schedule_draft_blocks_id_seq TO cronos_auth_definer;


--
-- Name: TABLE schedule_drafts; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.schedule_drafts TO cronos_app;


--
-- Name: SEQUENCE schedule_drafts_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.schedule_drafts_id_seq TO cronos_app;
GRANT SELECT,USAGE ON SEQUENCE public.schedule_drafts_id_seq TO cronos_auth_definer;


--
-- Name: TABLE schedule_generation_job; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.schedule_generation_job TO cronos_app;


--
-- Name: SEQUENCE schedule_generation_job_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.schedule_generation_job_id_seq TO cronos_app;
GRANT SELECT,USAGE ON SEQUENCE public.schedule_generation_job_id_seq TO cronos_auth_definer;


--
-- Name: TABLE scheduler_job_v1; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.scheduler_job_v1 TO cronos_app;
GRANT SELECT ON TABLE public.scheduler_job_v1 TO cronos_auth_definer;


--
-- Name: SEQUENCE scheduler_job_v1_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.scheduler_job_v1_id_seq TO cronos_app;


--
-- Name: TABLE scheduler_lesson_log_v1; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.scheduler_lesson_log_v1 TO cronos_app;


--
-- Name: SEQUENCE scheduler_lesson_log_v1_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.scheduler_lesson_log_v1_id_seq TO cronos_app;


--
-- Name: TABLE scheduler_lesson_slice_v1; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT ON TABLE public.scheduler_lesson_slice_v1 TO cronos_app;


--
-- Name: SEQUENCE scheduler_lesson_slice_v1_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.scheduler_lesson_slice_v1_id_seq TO cronos_app;


--
-- Name: TABLE scheduler_lesson_v1; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT ON TABLE public.scheduler_lesson_v1 TO cronos_app;


--
-- Name: SEQUENCE scheduler_lesson_v1_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.scheduler_lesson_v1_id_seq TO cronos_app;


--
-- Name: TABLE scheduler_proposal_v1; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.scheduler_proposal_v1 TO cronos_app;


--
-- Name: SEQUENCE scheduler_proposal_v1_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.scheduler_proposal_v1_id_seq TO cronos_app;


--
-- Name: TABLE scheduler_recovery_reservation_v1; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT ON TABLE public.scheduler_recovery_reservation_v1 TO cronos_app;


--
-- Name: SEQUENCE scheduler_recovery_reservation_v1_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.scheduler_recovery_reservation_v1_id_seq TO cronos_app;


--
-- Name: TABLE scheduler_school_year; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.scheduler_school_year TO cronos_app;


--
-- Name: SEQUENCE scheduler_school_year_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.scheduler_school_year_id_seq TO cronos_app;
GRANT SELECT,USAGE ON SEQUENCE public.scheduler_school_year_id_seq TO cronos_auth_definer;


--
-- Name: TABLE scheduler_school_year_state; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.scheduler_school_year_state TO cronos_app;


--
-- Name: SEQUENCE scheduler_school_year_state_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.scheduler_school_year_state_id_seq TO cronos_app;
GRANT SELECT,USAGE ON SEQUENCE public.scheduler_school_year_state_id_seq TO cronos_auth_definer;


--
-- Name: TABLE scheduler_state_version_events; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT ON TABLE public.scheduler_state_version_events TO cronos_app;


--
-- Name: SEQUENCE scheduler_state_version_events_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.scheduler_state_version_events_id_seq TO cronos_app;
GRANT SELECT,USAGE ON SEQUENCE public.scheduler_state_version_events_id_seq TO cronos_auth_definer;


--
-- Name: TABLE scheduler_version_v1; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.scheduler_version_v1 TO cronos_app;


--
-- Name: SEQUENCE scheduler_version_v1_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.scheduler_version_v1_id_seq TO cronos_app;


--
-- Name: TABLE school_calendar_event; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.school_calendar_event TO cronos_app;


--
-- Name: SEQUENCE school_calendar_event_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.school_calendar_event_id_seq TO cronos_app;
GRANT SELECT,USAGE ON SEQUENCE public.school_calendar_event_id_seq TO cronos_auth_definer;


--
-- Name: TABLE subject; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.subject TO cronos_app;


--
-- Name: SEQUENCE subject_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.subject_id_seq TO cronos_app;
GRANT SELECT,USAGE ON SEQUENCE public.subject_id_seq TO cronos_auth_definer;


--
-- Name: TABLE teacher; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.teacher TO cronos_app;
GRANT SELECT ON TABLE public.teacher TO cronos_auth_definer;


--
-- Name: TABLE teacher_endpoint_operational_event; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.teacher_endpoint_operational_event TO cronos_app;


--
-- Name: SEQUENCE teacher_endpoint_operational_event_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.teacher_endpoint_operational_event_id_seq TO cronos_app;
GRANT SELECT,USAGE ON SEQUENCE public.teacher_endpoint_operational_event_id_seq TO cronos_auth_definer;


--
-- Name: SEQUENCE teacher_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.teacher_id_seq TO cronos_app;
GRANT SELECT,USAGE ON SEQUENCE public.teacher_id_seq TO cronos_auth_definer;


--
-- Name: TABLE teacher_subject_link; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.teacher_subject_link TO cronos_app;


--
-- Name: TABLE teacher_weekly_timesheet; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.teacher_weekly_timesheet TO cronos_app;


--
-- Name: SEQUENCE teacher_weekly_timesheet_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.teacher_weekly_timesheet_id_seq TO cronos_app;
GRANT SELECT,USAGE ON SEQUENCE public.teacher_weekly_timesheet_id_seq TO cronos_auth_definer;


--
-- Name: TABLE timeslot; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.timeslot TO cronos_app;


--
-- Name: SEQUENCE timeslot_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.timeslot_id_seq TO cronos_app;
GRANT SELECT,USAGE ON SEQUENCE public.timeslot_id_seq TO cronos_auth_definer;


--
-- Name: TABLE "user"; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT ON TABLE public."user" TO cronos_app;
GRANT SELECT,INSERT,UPDATE ON TABLE public."user" TO cronos_auth_definer;


--
-- Name: SEQUENCE user_id_seq; Type: ACL; Schema: public; Owner: cronos_migrator
--

GRANT SELECT,USAGE ON SEQUENCE public.user_id_seq TO cronos_app;
GRANT SELECT,USAGE ON SEQUENCE public.user_id_seq TO cronos_auth_definer;


--
-- PostgreSQL database dump complete
--
"""


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS public")
    op.execute("CREATE SCHEMA IF NOT EXISTS app_security")
    op.execute(BASELINE_SQL)


def downgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE r RECORD;
        BEGIN
            FOR r IN SELECT tablename FROM pg_tables
                     WHERE schemaname = 'public' AND tablename <> 'alembic_version'
            LOOP
                EXECUTE format('DROP TABLE IF EXISTS public.%I CASCADE', r.tablename);
            END LOOP;
            FOR r IN SELECT t.typname FROM pg_type t
                     JOIN pg_namespace n ON n.oid = t.typnamespace
                     WHERE n.nspname = 'public' AND t.typtype = 'e'
            LOOP
                EXECUTE format('DROP TYPE IF EXISTS public.%I CASCADE', r.typname);
            END LOOP;
        END $$;
        """
    )
    op.execute("DROP SCHEMA IF EXISTS app_security CASCADE")
