# Data Model

## Purpose

This document maps the main PostgreSQL tables, relationships, and tenant boundaries.

## Intended Reader

This document targets backend engineers and database administrators.

## Prerequisites

Read [System Architecture](SYSTEM_ARCHITECTURE.md) and [Security and Tenant Isolation](../08_security_quality/SECURITY_AND_TENANT_ISOLATION.md).

## What the System Does

Cronos stores school, identity, scheduling, execution, progress, and audit data in PostgreSQL.
Tenant-owned tables carry `organization_id` and use forced row-level security.
The scheduler v1 tables store curricular assignments, requirements, execution, debt, versions, lessons, and proposals.

## Why the Behavior Exists

Explicit tenant keys support scoped foreign keys, audit queries, and database-enforced isolation.
Separate operational records preserve what the schedule planned and what the school executed.
Separate scheduler v1 records preserve curricular demand, execution evidence, debt, and version history.

## Components and Ownership

| Area | Tables or source |
| :--- | :--- |
| Identity | `organization`, `user`, `organization_membership`, `teacher` |
| Access audit | `member_access_operation`, `clerk_webhook_event` |
| Legal evidence | `organization_legal_acceptance` |
| Curriculum | `course`, `class`, `subject`, `module`, `course_subject_link`, `teacher_subject_link`, `class_subject_link` |
| Resources | `room`, `timeslot`, `grid_version`, `availability`, `constraint` |
| School calendar | `organization_settings`, `organization_grid_settings`, `school_calendar_event`, `school_calendar_event_class` |
| Scheduler lifecycle | `scheduler_school_year`, `scheduler_school_year_state`, `scheduler_state_version_events` |
| Operational records | `lesson_occurrence`, `operational_schedule_block` |
| Execution | `lesson_log`, `progress_ledger_entry`, `teacher_weekly_timesheet` |
| Scheduler v1 curriculum | `curricular_assignment`, `curricular_requirement`, `curricular_execution`, `curricular_execution_credit`, `curricular_debt`, `curricular_debt_revision`, `curricular_debt_settlement` |
| Scheduler v1 schedule | `scheduler_version_v1`, `scheduler_lesson_v1`, `scheduler_lesson_slice_v1`, `scheduler_recovery_reservation_v1`, `scheduler_lesson_log_v1`, `scheduler_job_v1`, `scheduler_proposal_v1` |
| Definitions | `backend/app/models.py` and `backend/app/scheduler/infrastructure/models.py` |

## Data or Request Flow

```mermaid
erDiagram
    ORGANIZATION ||--o{ ORGANIZATION_MEMBERSHIP : contains
    USER ||--o{ ORGANIZATION_MEMBERSHIP : owns
    ORGANIZATION ||--o{ COURSE : offers
    COURSE ||--o{ CLASS : groups
    CLASS ||--o{ CLASS_SUBJECT_LINK : assigns
    SUBJECT ||--o{ MODULE : orders
    SCHEDULER_LESSON_LOG_V1 ||--o{ OPERATIONAL_SCHEDULE_BLOCK : creates
    OPERATIONAL_SCHEDULE_BLOCK ||--o| LESSON_LOG : logs
    MODULE ||--o{ PROGRESS_LEDGER_ENTRY : measures
    CURRICULAR_ASSIGNMENT ||--o{ CURRICULAR_REQUIREMENT : requires
    CURRICULAR_ASSIGNMENT ||--o{ CURRICULAR_DEBT : owes
    SCHEDULER_VERSION_V1 ||--o{ SCHEDULER_LESSON_V1 : contains
    SCHEDULER_LESSON_V1 ||--o| SCHEDULER_LESSON_LOG_V1 : executes
```

1. A membership selects an organization tenant.
2. Curriculum and resources define scheduler input.
3. A generation job stores a snapshot and produces a proposal.
4. Approval promotes the proposal to an active version and its lessons.
5. Logs and occurrences produce ledger deltas and recovery evidence.

## Contracts and Invariants

- `organization_id` scopes tenant-owned rows.
- A database created on the removed pre-baseline chain cannot upgrade. Run `alembic downgrade base` with the previous code first; see the [Deployment Runbook](../09_ops_observability/DEPLOYMENT_RUNBOOK.md#migration-baseline-and-reset-rule).
- Cross-tenant foreign keys use organization-scoped constraints where required.
- Module `required_minutes` is positive.
- Ledger entries use an idempotency key and cannot contain zero deltas.
- Occurrence revisions preserve active history and support explicit revoke operations.
- Application queries run under the `cronos_app` role with `NOBYPASSRLS`.
- Row-level security is enabled and forced on tenant tables.
- The `app_security` schema owns `SECURITY DEFINER` helper functions.

## States and Transitions

- Generation strategies are `COMPLETE_GENERATION`, `ADAPTIVE_REPAIR`, or `GRID_CHANGE`.
- Generation triggers are `FIRST_GENERATION`, `EXPLICIT_DEBT`, `SCHEDULER_CHANGE`, `MIXED`, or `GRID_CHANGE`.
- Scheduler v1 jobs in `scheduler_job_v1` use `QUEUED`, `RUNNING`, `VALIDATING`, `SUCCEEDED`, `CANCELLED`, `STALE`, `FAILED`, `INFEASIBLE`, or `INCONCLUSIVE`.
- Scheduler v1 proposals in `scheduler_proposal_v1` use `PENDING`, `APPROVED`, `REJECTED`, `STALE`, or `SUPERSEDED`.
- Scheduler v1 versions in `scheduler_version_v1` use `CANDIDATE`, `ACTIVE`, or `SUPERSEDED`.
- Scheduler v1 lesson logs use `COMPLETED`, `OCCURRENCE`, or `REVOKED`.
- `scheduler_lesson_log_v1.withdrawn_at` records an internship-flow withdrawal without deleting the published lesson.
- `LessonOccurrenceStatus` uses `GIVEN`, `GAP`, `SUBSTITUTED`, or `REVOKED`; NULL means open.
- The API maps occurrences to `OPEN_PENDING`, `DECIDED_GIVEN`, `DECIDED_GAP`, `DECIDED_SUBSTITUTED`, or `REVOKED`.
- `lesson_log` uses `PENDING`, `COMPLETED`, or `OCCURRENCE`.
- Timesheets use `OPEN`, `SUBMITTED`, or `APPROVED`.
- Grid versions use `PENDING`, `ACTIVE`, or `REJECTED`.
- Scheduler state change scopes are `FUTURE_IMPACTING`, `PAST_ONLY`, `NO_OP`, or `INACTIVE_RESOURCE`.
- Room types are `normal`, `lab`, `gym`, or `art`.
- Calendar event types are `national_holiday`, `school_break`, `exam_period`, `other`, or `internship_flow`.
- Membership lifecycle states are `active` or `archived`.
- Membership access states are `none`, `pending_invite`, `invite_expired`, `active`, `blocked`, or `sync_error`.
- Teacher access modes are `platform` or `scheduler_only`.
- Membership capabilities are `teacher` or `admin`.
- Foundation states are `NOT_STARTED`, `IN_PROGRESS`, or `COMPLETED`.
- Clerk webhook events use `received`, `processing`, `processed`, `ignored`, `retryable_failed`, `sync_error`, or `dead_letter`.

## Failure Modes

- A foreign-key or scoped-key violation rejects inconsistent data.
- A missing tenant context hides rows and rejects writes.
- Migration drift fails `alembic check`.
- Trigger or RLS drift fails the database audit scripts.

## Verification Procedure

1. Run `alembic upgrade head` with the migrator role.
2. Run `alembic check`.
3. Run `python -m scripts.audit_triggers` from `backend/`.
4. Run `python -m scripts.audit_database_integrity` from `backend/`.

## Source Map

- ORM models: `backend/app/models.py`
- Scheduler v1 models: `backend/app/scheduler/infrastructure/models.py`
- Schemas: `backend/app/schemas.py`
- Migrations: `backend/alembic/versions/` holds the single baseline `0001_scheduler_v1_baseline`, a PostgreSQL 18 SQL schema dump. New migrations stack on it.
- RLS tests: `backend/tests/contracts/test_rls_database_policies.py`
- Integrity tests: `backend/tests/integration/committed/test_tenant_isolation_complete.py`

## Onboarding Data Contract

The onboarding lifecycle uses tenant-scoped records and explicit state fields.

| Record | Important fields | Integrity rule |
| :--- | :--- | :--- |
| `organization` | `foundation_status`, `foundation_completed_at`, `first_real_schedule_approved_at` | A completed Foundation requires `foundation_completed_at`; the first real approval requires a completed Foundation. |
| `organization_foundation_draft` | `organization_id`, `version`, `current_step`, JSONB `payload_json`, `updated_by_membership_id` | One draft exists per organization. `version` is positive and increases on each accepted write. |
| `organization_legal_acceptance` | Legal entity, representative, immutable membership-id snapshot, terms version, DPA version, privacy version, server timestamp | One append-only acceptance exists per organization and current document triple. RLS limits reads and inserts to the active tenant; the organization FK is restrictive so evidence is never cascaded away. |

Foundation settings and generated timeslots are written in the same completion unit of work.
The API database dependency commits the unit before it returns a successful response.
The tutorial scenario and its minimal resumable checkpoint remain in browser storage with a 30-day TTL. No tutorial telemetry table exists.

## Related Documents

- [System Architecture](SYSTEM_ARCHITECTURE.md)
- [Security and Tenant Isolation](../08_security_quality/SECURITY_AND_TENANT_ISOLATION.md)
- [Data and Seed](../07_data_and_seed/DATA_AND_SEED.md)
