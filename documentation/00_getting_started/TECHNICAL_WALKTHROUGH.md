# Technical Walkthrough

## Purpose
This document provides a technical walkthrough of primary administrator and teacher workflows. It replaces the legacy demonstration script.

## Intended Reader
This document targets software developers, QA engineers, and system evaluators.

## Prerequisites
Provision roles, apply migrations, and start the stack. Use real Clerk test identities for interactive login.

## Workflow 1: Administrator Initial Setup and Schedule Generation

```mermaid
sequenceDiagram
    autonumber
    actor Admin as School Administrator
    participant FE as React Frontend
    participant BE as FastAPI Backend
    participant DB as PostgreSQL DB
    participant Celery as Celery Worker
    participant Solver as CP-SAT Solver V2

    Admin->>FE: 1. Login at /login with Clerk
    FE->>FE: 2. Clerk creates an organization-scoped session
    Admin->>FE: 4. Open School Configuration (/config)
    FE->>BE: 5. GET /api/v1/school/settings/
    BE-->>FE: 6. Return Settings & Shift Grid
    Admin->>FE: 7. Open Team View (/members)
    FE->>BE: 8. GET /api/v1/members/
    BE-->>FE: 9. Return Organization Members
    Admin->>FE: 10. Trigger Schedule Generation (/schedules)
    FE->>BE: 11. POST /api/v1/scheduler/generate (mode: full)
    BE->>Celery: 12. Dispatch solver task
    Celery->>Solver: 13. Compute CP-SAT Schedule
    Solver-->>Celery: 14. Return Schedule Output
    Celery->>DB: 15. Store Schedule Draft
    FE->>BE: 16. Poll GET /api/v1/scheduler/status
    BE-->>FE: 17. Return Status: SUCCEEDED
    Admin->>FE: 18. Review & Approve Draft
    FE->>BE: 19. POST /api/v1/scheduler/drafts/{id}/approve
    BE->>DB: 20. Promote Draft to Active Schedule
```

### Step-by-Step Procedure
1. Access the application at `http://localhost:8080`.
2. Log in with an active Clerk administrator membership.
3. Navigate to **Configuração da Escola** (`/config`). Verify weekly shift times, slot durations, and active school year parameters.
4. Navigate to **Equipa** (`/members`). Inspect organization members and role assignments.
5. Navigate to **Horários** (`/schedules`). Click **Gerar Horário Completo**.
6. The system dispatches a Celery task. The status widget displays generation progress.
7. Upon completion, inspect the generated draft. Compare projected completion dates and gap metrics.
8. Click **Aprovar Rascunho**. The system promotes the draft to active schedule status.

## Workflow 2: Teacher Daily Operations and Lesson Logging

```mermaid
sequenceDiagram
    autonumber
    actor Teacher as Teacher (Ana Matos)
    participant FE as React Frontend
    participant BE as FastAPI Backend
    participant DB as PostgreSQL DB

    Teacher->>FE: 1. Login at /login with Clerk
    Teacher->>FE: 2. View My Schedule (/my-schedules)
    FE->>BE: 3. GET /api/v1/schedule/week (my slots)
    BE-->>FE: 6. Return Teacher Schedule
    Teacher->>FE: 4. Click Lesson Block -> Open Log Modal
    Teacher->>FE: 5. Select Status, Enter Summary and Notes
    FE->>BE: 6. PUT /api/v1/schedule/active-blocks/{id}/log
    BE->>DB: 7. Upsert LessonLog and append ledger deltas
    BE-->>FE: 8. Return Updated LessonLog
```

### Step-by-Step Procedure
1. Log out from the administrator account.
2. Log in with an active Clerk teacher membership and linked teacher profile.
3. View **O Meu Horário** (`/my-schedules`). The page shows personal weekly schedule blocks.
4. Click a scheduled lesson block. The **Registo de Aula** modal opens.
5. Select `COMPLETED` or `OCCURRENCE`. Add optional summary and notes.
6. Click **Guardar Sumário**. A completed log credits the block duration to the active module.

## Source Map
- Admin Pages: `frontend/src/pages/SchoolConfig.jsx`, `frontend/src/pages/Schedules.jsx`
- Teacher Pages: `frontend/src/pages/MySchedules.jsx`, `frontend/src/components/LessonLogModal.jsx`
- API Routers: `backend/app/api/v1/endpoints/scheduler.py`, `backend/app/api/v1/endpoints/schedule.py`

## Related Documents
- [Project Overview](PROJECT_OVERVIEW.md)
- [Scheduler Behavior](../03_scheduler_engine/SCHEDULER_BEHAVIOR.md)
- [Lesson Execution](../04_operational_features/LESSON_EXECUTION.md)
