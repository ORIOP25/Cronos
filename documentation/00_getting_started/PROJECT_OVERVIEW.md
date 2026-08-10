# Project Overview

## Purpose
This document provides an overview of the Cronos software platform. It outlines the core problem, business goals, and supported user profiles.

## Intended Reader
This document targets new developers, technical architects, and product managers.

## Prerequisites
No prior codebase knowledge is required.

## What the System Does
Cronos is a Software-as-a-Service (SaaS) platform designed for Portuguese Professional Education (*Ensino Profissional*). The application manages school structures, course modules, teacher availability, automated schedule generation, lesson execution logs (*Sumários*), teacher absences (*Faltas*), and cover arrangements (*Substituições*).

Cronos is a dynamic operational system. It plans initial schedules, tracks real-world execution, and calculates schedule repairs when disruptions occur.

## Why the Behavior Exists
Professional education in Portugal operates under non-linear course structures. Courses contain multiple independent modules (*Módulos*). Each module requires a specific number of instructional hours. Static annual calendars cannot accommodate modular execution rates or frequent teacher absences. Cronos automates schedule generation and execution tracking to guarantee compliance with educational regulations.

## Components and Ownership

| Component | Responsibility | Tech Stack |
| :--- | :--- | :--- |
| **Backend API** | Business logic, endpoints, database management | Python 3.12, FastAPI, Async SQLAlchemy |
| **Frontend UI** | User web interface, interactive grids | React 19, Vite, CoreUI, React Query |
| **Scheduler Engine** | Complete generation and adaptive schedule repair | Google OR-Tools CP-SAT |
| **Worker Queue** | Asynchronous generation and repair jobs | Redis 7, Celery |
| **Database** | Persistent data storage and tenant isolation | PostgreSQL 16 (forced RLS) |
| **Authentication** | User identity, organizations, and RBAC | Clerk Authentication |

## Data or Request Flow
1. School administrators log into Cronos and configure school parameters.
2. Administrators invite staff members through the team view (`Equipa`).
3. Teachers record timeslot preferences through the self-service portal.
4. Administrators trigger full schedule generation.
5. The scheduler worker computes optimal timetable slots using OR-Tools CP-SAT.
6. Administrators review and approve schedule drafts.
7. Teachers complete lesson logs or report lesson occurrences.
8. The engine computes adaptive schedule repairs when required.

## Contracts and Invariants
- Each school operates inside an isolated organization tenant (`organization_id`).
- Teachers do not have direct access to administrative routes.
- The scheduler prevents class, teacher, and room overlap for selected schedule blocks.

## States and Transitions
- **School Year Publication**: `UNPUBLISHED` -> `PUBLISHED`.
- **Generation Job**: `QUEUED` -> `RUNNING` -> `SUCCEEDED`, `FAILED`, `NO_VALID_OUTPUT`, or `CANCELED`.
- **Schedule Draft**: `PENDING` -> `APPROVED`, `REJECTED`, `REPLACED`, `STALE`, or `INVALIDATED`.

## Failure Modes
- **Authentication Failure**: Invalid Clerk JWT results in HTTP `401 Unauthorized`.
- **Tenant Context Missing**: Forced RLS hides tenant rows and rejects writes outside the active tenant.
- **No Valid Output**: The job records `NO_VALID_OUTPUT` when generation cannot produce an approvable draft.

## Verification Procedure
Run the production-like Docker environment and access `http://localhost:8080`. Verify `/health/ready` before login.

## Source Map
- Backend Core: `backend/app/main.py`
- Frontend App Entry: `frontend/src/App.jsx`
- Database Models: `backend/app/models.py`
- Scheduler Services: `backend/app/services/scheduler_*`

## Related Documents
- [System Architecture](../01_system_architecture/SYSTEM_ARCHITECTURE.md)
- [Glossary](GLOSSARY.md)
