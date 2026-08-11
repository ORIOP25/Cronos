# Data Model

## Purpose

This document maps the main PostgreSQL tables, relationships, and tenant boundaries.

## Intended Reader

This document targets backend engineers and database administrators.

## Prerequisites

Read [System Architecture](SYSTEM_ARCHITECTURE.md) and [Security and Tenant Isolation](../08_security_quality/SECURITY_AND_TENANT_ISOLATION.md).

## What the System Does

Cronos stores school, identity, scheduling, execution, progress, and audit data in PostgreSQL.
Tenant-owned tables carry `organization_id` and use forced RLS policies.

## Why the Behavior Exists

Explicit tenant keys support scoped foreign keys, audit queries, and database-enforced isolation.
Separate operational records preserve what the schedule planned and what the school executed.

## Components and Ownership

| Area | Tables or source |
| :--- | :--- |
| Identity | `organization`, `user`, `organization_membership`, `teacher` |
| Access audit | `member_access_operation`, `clerk_webhook_event` |
| Curriculum | `course`, `class`, `subject`, `module`, link tables |
| Resources | `room`, `timeslot`, `availability`, `constraint` |
| School calendar | `organization_settings`, `organization_grid_settings`, `school_calendar_event` |
| Scheduler | `scheduler_school_year`, `scheduler_school_year_state`, `schedule_generation_job`, `schedule_drafts`, `schedule_draft_blocks`, `schedule_diff_entries`, `active_schedule_blocks` |
| Recovery | `lesson_occurrence`, `operational_schedule_block`, `planned_recovery_links` |
| Execution | `lesson_log`, `progress_ledger_entry`, `teacher_weekly_timesheet` |
| Observability | `occurrence_operational_event`, `teacher_endpoint_operational_event`, scheduler fields |
| Definitions | `backend/app/models.py` and `backend/alembic/versions/` |

## Data or Request Flow

```mermaid
erDiagram
    ORGANIZATION ||--o{ ORGANIZATION_MEMBERSHIP : contains
    USER ||--o{ ORGANIZATION_MEMBERSHIP : owns
    ORGANIZATION ||--o{ COURSE : offers
    COURSE ||--o{ CLASS : groups
    CLASS ||--o{ CLASS_SUBJECT_LINK : assigns
    SUBJECT ||--o{ MODULE : orders
    CLASS_SUBJECT_LINK ||--o{ ACTIVE_SCHEDULE_BLOCK : schedules
    ACTIVE_SCHEDULE_BLOCK ||--o{ LESSON_OCCURRENCE : records
    ACTIVE_SCHEDULE_BLOCK ||--o| LESSON_LOG : logs
    LESSON_OCCURRENCE ||--o{ OPERATIONAL_SCHEDULE_BLOCK : creates
    MODULE ||--o{ PROGRESS_LEDGER_ENTRY : measures
```

1. A membership selects an organization tenant.
2. Curriculum and resources define scheduler input.
3. A generation job stores a snapshot and produces a draft.
4. Approval promotes draft blocks to active blocks.
5. Logs and occurrences produce ledger deltas and recovery evidence.

## Contracts and Invariants

- `organization_id` scopes tenant-owned rows.
- Cross-tenant foreign keys use organization-scoped constraints where required.
- Module `required_minutes` is positive.
- Ledger entries use an idempotency key and cannot contain zero deltas.
- Occurrence revisions preserve active history and support explicit revoke operations.
- Application queries run under the `cronos_app` role with `NOBYPASSRLS`.

## States and Transitions

- Generation jobs use the statuses documented in [Project Overview](../00_getting_started/PROJECT_OVERVIEW.md).
- Occurrences use `OPEN_PENDING`, `DECIDED_GIVEN`, `DECIDED_GAP`, `DECIDED_SUBSTITUTED`, or `REVOKED` at the API boundary.
- Recovery links use `PLANNED`, `DELIVERED`, `CANCELED`, or `REPLACED`.

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
- Schemas: `backend/app/schemas.py`
- Migrations: `backend/alembic/versions/`
- RLS tests: `backend/tests/test_rls_database_policies.py`
- Integrity tests: `backend/tests/test_tenant_isolation_complete.py`

## Related Documents

- [System Architecture](SYSTEM_ARCHITECTURE.md)
- [Security and Tenant Isolation](../08_security_quality/SECURITY_AND_TENANT_ISOLATION.md)
- [Data and Seed](../07_data_and_seed/DATA_AND_SEED.md)
