# Project Overview

## Purpose

This document summarizes the current Cronos platform, its runtime components, and its primary workflows.

## Intended Reader

This document targets new developers, architects, product specialists, and release engineers.

## Prerequisites

No previous repository knowledge is required.

## What the System Does

Cronos supports Portuguese Professional Education (*Ensino Profissional*).
It manages curriculum, teacher availability, schedules, lesson logs (*Sumários*), absences (*Faltas*), substitutions (*Substituições*), progress, and timesheets.

The application uses one React SPA, one FastAPI API, PostgreSQL, Redis, and Celery processes.

## Why the Behavior Exists

Courses contain ordered modules (*Módulos*) with required instructional minutes.
Schedules must account for resource conflicts, availability, calendar events, execution history, and recovery work.

## Components and Ownership

| Component | Responsibility | Technology |
| :--- | :--- | :--- |
| Backend API | HTTP, authentication, domain services, persistence | Python 3.14, FastAPI, Async SQLAlchemy |
| Frontend | Public site, authenticated UI, client state | React 19, Vite 8, CoreUI, TanStack Query |
| Scheduler | Complete generation and adaptive repair | Google OR-Tools CP-SAT |
| Worker | Background generation jobs | Celery and Redis |
| Beat | Hourly member reconciliation | Celery Beat and Redis |
| Database | Tenant data, RLS, audit records | PostgreSQL 16 |
| Identity | Users, organizations, roles, webhooks | Clerk |

## Data or Request Flow

1. Clerk authenticates the user and selects an organization.
2. An organization administrator completes the nine-step Foundation and creates the school grid.
3. The administrator uses the optional local tutorial or continues with real configuration.
4. The administrator builds the six readiness bases: active classes, positive modules, active teachers, valid teacher assignments, compatible rooms, and availability. Foundation creates the timeslot grid, while final prevalidation protects generation when it is missing.
5. The administrator starts complete generation or adaptive repair.
6. The API creates a job and publishes the registered task name `scheduler.run_generation_job` through Redis.
7. The worker computes a bounded result and stores a schedule draft.
8. An administrator reviews the draft and approves or rejects it.
9. The first real approval changes the dashboard from `PREPARATION` to `OPERATIONAL`.
10. Teachers record `COMPLETED` or `OCCURRENCE` lesson logs.
11. Administrators decide occurrences and review debt, recovery, progress, and timesheets.

## Contracts and Invariants

- Tenant-owned data uses `organization_id` and forced PostgreSQL RLS.
- The application role uses `NOBYPASSRLS`; the migration role is separate.
- Administrative routes require the `admin` capability.
- Teacher routes require the `teacher` capability and a linked teacher profile.
- Generation prevents class, teacher, and room overlap.

## States and Transitions

- School year: `UNPUBLISHED` -> `PUBLISHED`.
- Job: `QUEUED` -> `RUNNING` -> `SUCCEEDED`, `FAILED`, `NO_VALID_OUTPUT`, or `CANCELED`.
- Draft: `PENDING` -> `APPROVED`, `REJECTED`, `REPLACED`, `STALE`, or `INVALIDATED`.
- Timesheet: `OPEN` -> `SUBMITTED` -> `APPROVED`; approval can return to `OPEN`.

## Failure Modes

- Invalid Clerk credentials return an authentication error.
- Missing tenant context prevents access to tenant rows.
- A missing Redis or PostgreSQL dependency makes readiness fail.
- A blocked solve records `NO_VALID_OUTPUT` or `FAILED` with diagnostic fields.

## Verification Procedure

1. Copy the root environment example.
2. Provision database roles with the maintenance profile.
3. Apply migrations with the maintenance profile.
4. Start the stack and verify `/health/live` and `/health/ready`.

## Source Map

- Backend entry: `backend/app/main.py`
- Frontend entry: `frontend/src/main.jsx`
- Route definitions: `frontend/src/App.jsx`
- Models: `backend/app/models.py`
- Scheduler services: `backend/app/services/scheduler_*.py`
- Scheduler dispatch boundary: `backend/app/scheduler/infrastructure/task_dispatcher.py`
- Worker task registration: `backend/app/scheduler_worker.py`
- Local runtime: `docker-compose.yml`

## Related Documents

- [Director Onboarding](ONBOARDING.md)
- [Repository Map](REPOSITORY_MAP.md)
- [System Architecture](../01_system_architecture/SYSTEM_ARCHITECTURE.md)
- [Glossary](GLOSSARY.md)
