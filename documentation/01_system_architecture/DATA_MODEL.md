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
| `organizations` | Tenant school entities | None |
| `users` | User identity accounts | `clerk_user_id` (unique string) |
| `organization_memberships` | User-to-school membership | `organization_id`, `user_id` |
| `teachers` | Teacher domain profiles | `organization_id`, `user_id` |
| `courses` | Vocational courses | `organization_id` |
| `classes` | Student cohorts (*Turmas*) | `organization_id`, `course_id` |
| `subjects` | Curricular subjects | `organization_id` |
| `modules` | Subject modules (*Módulos*) | `organization_id`, `subject_id` |
| `class_subject_links` | Subject assignment per class | `class_id`, `subject_id`, `teacher_id` |
| `rooms` | Classrooms and labs | `organization_id` |
| `timeslots` | Weekly schedule slot definitions | `organization_id` |
| `schedule_generation_jobs` | Solver execution jobs | `organization_id`, `created_by_user_id` |
| `schedule_drafts` | Unapproved generated schedules | `organization_id`, `job_id` |
| `active_schedule_blocks` | Published operational schedule | `organization_id`, `class_id`, `teacher_id`, `room_id` |
| `lesson_occurrences` | Logged lesson instances | `organization_id`, `active_block_id` |
| `lesson_logs` | Lesson summaries (*Sumários*) | `organization_id`, `occurrence_id`, `teacher_id` |
| `teacher_weekly_timesheets` | Weekly timesheet records | `organization_id`, `teacher_id` |

## Key Relationships Diagram

```mermaid
erDiagram
    ORGANIZATION ||--o{ USER_MEMBERSHIP : contains
    ORGANIZATION ||--o{ COURSE : offers
    COURSE ||--o{ CLASS : groups
    CLASS ||--o{ CLASS_SUBJECT_LINK : specifies
    TEACHER ||--o{ CLASS_SUBJECT_LINK : teaches
    SUBJECT ||--o{ MODULE : divides
    CLASS_SUBJECT_LINK ||--o{ ACTIVE_SCHEDULE_BLOCK : schedules
    ACTIVE_SCHEDULE_BLOCK ||--o{ LESSON_OCCURRENCE : executes
    LESSON_OCCURRENCE ||--o{ LESSON_LOG : logs
```

## Contracts and Invariants
- Every tenant table must contain an `organization_id` foreign key column.
- Primary keys use UUID string identifiers or auto-incrementing integers depending on table design.

## Failure Modes
- Foreign Key Constraint Failure: Deleting a referenced record without cascade handling throws a database exception.

## Verification Procedure
Inspect database schema using Alembic: run `alembic current` and `python backend/scripts/audit_database_integrity.py`.

## Source Map
- ORM Models: `backend/app/models.py`
- Pydantic Schemas: `backend/app/schemas.py`
- Database Migrations: `backend/alembic/versions/`

## Related Documents
- [System Architecture](SYSTEM_ARCHITECTURE.md)
- [Security and Tenant Isolation](../08_security_quality/SECURITY_AND_TENANT_ISOLATION.md)
