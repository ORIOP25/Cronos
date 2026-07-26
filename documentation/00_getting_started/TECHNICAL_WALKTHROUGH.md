# Technical Walkthrough

## Purpose
This document provides a technical walkthrough of primary administrator and teacher workflows. It replaces the legacy demonstration script.

## Intended Reader
This document targets software developers, QA engineers, and system evaluators.

## Prerequisites
Start the local application using `docker compose up -d` and seed the database using `python backend/scripts/seed.py --scenario small-realistic`.

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

    Admin->>FE: 1. Login at /login (ana.silva@escola.pt)
    FE->>BE: 2. POST /api/v1/auth/token
    BE-->>FE: 3. Return Bearer JWT Token
    Admin->>FE: 4. Open School Configuration (/config)
    FE->>BE: 5. GET /api/v1/org-settings/settings/
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
    BE-->>FE: 17. Return Status: Success
    Admin->>FE: 18. Review & Approve Draft
    FE->>BE: 19. POST /api/v1/scheduler/drafts/{id}/approve
    BE->>DB: 20. Promote Draft to Active Schedule
```

### Step-by-Step Procedure
1. Access the application at `http://localhost:5173`.
2. Log in using administrator credentials (`ana.silva@escola.pt` / `1234`).
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

    Teacher->>FE: 1. Login at /login (ana.matos@epnorte.pt)
    FE->>BE: 2. POST /api/v1/auth/token
    BE-->>FE: 3. Return Teacher JWT Token
    Teacher->>FE: 4. View Dashboard (/dashboard)
    FE->>BE: 5. GET /api/v1/schedule/week (my slots)
    BE-->>FE: 6. Return Teacher Schedule
    Teacher->>FE: 7. Click Lesson Block -> Open Log Modal
    Teacher->>FE: 8. Enter Summary Text & Attendance -> Click Save
    FE->>BE: 9. PUT /api/v1/schedule/active-blocks/{id}/log
    BE->>DB: 10. Update LessonLog & ProgressLedgerEntry
    BE-->>FE: 11. Return Updated Block State
```

### Step-by-Step Procedure
1. Log out from the administrator account.
2. Log in using teacher credentials (`ana.matos@epnorte.pt` / `1234`).
3. View the **Dashboard** (`/dashboard`). The page shows personal daily schedule blocks and pending lesson summaries.
4. Click a scheduled lesson block. The **Registo de Aula** modal opens.
5. Enter lesson summary text, covered module hours, and student attendance status.
6. Click **Guardar Sumário**. The system updates the lesson log and updates module completion progress.

## Source Map
- Admin Pages: `frontend/src/pages/SchoolConfig.jsx`, `frontend/src/pages/Schedules.jsx`
- Teacher Pages: `frontend/src/pages/Dashboard.jsx`, `frontend/src/components/LessonLogModal.jsx`
- API Routers: `backend/app/api/v1/endpoints/scheduler.py`, `backend/app/api/v1/endpoints/schedule.py`

## Related Documents
- [Project Overview](PROJECT_OVERVIEW.md)
- [Scheduler Behavior](../03_scheduler_engine/SCHEDULER_BEHAVIOR.md)
- [Lesson Execution](../04_operational_features/LESSON_EXECUTION.md)
