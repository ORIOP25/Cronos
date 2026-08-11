# Data Model

## Purpose
This document details database tables, entity relationships, foreign keys, and primary model attributes.

## Intended Reader
This document targets backend developers and database administrators.

## Prerequisites
Read [System Architecture](SYSTEM_ARCHITECTURE.md).

## What the System Does
Cronos stores persistent domain data in PostgreSQL. Row-Level Security (RLS) policies isolate tenant data using `organization_id`.

## Core Entity Table Summary

| Table Name | Primary Purpose | Key Foreign Keys |
| :--- | :--- | :--- |
| `organization` | Tenant school entity | None |
| `user` | Clerk-linked account | None |
| `organization_membership` | Account access and capabilities | `organization_id`, `account_id` |
| `teacher` | Teacher profile linked to one membership | `organization_id`, `organization_membership_id` |
| `course` | Vocational course | `organization_id` |
| `class` | Student cohort (*Turma*) | `organization_id`, `course_id` |
| `subject` | Curricular subject | `organization_id` |
| `module` | Ordered subject module | `organization_id`, `subject_id` |
| `class_subject_link` | Subject and teacher assignment by grade | `organization_id`, `class_id`, `subject_id`, `teacher_id` |
| `room` | Room with capacity and type | `organization_id` |
| `timeslot` | Weekly grid slot | `organization_id` |
| `schedule_generation_job` | Solver execution job | `organization_id`, `school_year_id`, `requested_by_membership_id` |
| `schedule_drafts` | Unapproved generated schedules | `organization_id`, `job_id` |
| `active_schedule_blocks` | Published operational schedule | `organization_id`, `class_id`, `teacher_id`, `room_id` |
| `lesson_occurrence` | Operational decision for a published block | `organization_id`, `active_schedule_block_id` |
| `operational_schedule_block` | Substitute lesson block | `organization_id`, `source_occurrence_id` |
| `lesson_log` | Execution status, summary, and notes | `organization_id`, one schedule block target |
| `progress_ledger_entry` | Append-only progress and debt deltas | `organization_id`, `class_id`, `module_id` |
| `teacher_weekly_timesheet` | Weekly closure record | `organization_id`, `teacher_id` |

## Key Relationships Diagram

```mermaid
erDiagram
    ORGANIZATION ||--o{ ORGANIZATION_MEMBERSHIP : contains
    USER ||--o{ ORGANIZATION_MEMBERSHIP : owns
    ORGANIZATION ||--o{ COURSE : offers
    COURSE ||--o{ CLASS : groups
    CLASS ||--o{ CLASS_SUBJECT_LINK : specifies
    TEACHER ||--o{ CLASS_SUBJECT_LINK : teaches
    SUBJECT ||--o{ MODULE : divides
    CLASS_SUBJECT_LINK ||--o{ ACTIVE_SCHEDULE_BLOCK : schedules
    ACTIVE_SCHEDULE_BLOCK ||--o{ LESSON_OCCURRENCE : reports
    ACTIVE_SCHEDULE_BLOCK ||--o| LESSON_LOG : logs
    LESSON_OCCURRENCE ||--o{ OPERATIONAL_SCHEDULE_BLOCK : creates
```

## Contracts and Invariants
- Tenant-owned tables contain `organization_id`; global identity rows use membership-aware RLS policies.
- ORM primary keys use auto-incrementing integers. Scheduler fingerprints and task IDs use strings where required.

## Failure Modes
- Foreign Key Constraint Failure: Deleting a referenced record without cascade handling throws a database exception.

## Verification Procedure
From `backend/`, run `alembic current`, `python -m scripts.audit_triggers`, and `python -m scripts.audit_database_integrity`.

## Source Map
- ORM Models: `backend/app/models.py`
- Pydantic Schemas: `backend/app/schemas.py`
- Database Migrations: `backend/alembic/versions/`

## Related Documents
- [System Architecture](SYSTEM_ARCHITECTURE.md)
- [Security and Tenant Isolation](../08_security_quality/SECURITY_AND_TENANT_ISOLATION.md)
