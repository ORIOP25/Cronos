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
| **Scheduler Engine** | Mathematical optimization for timetables | Google OR-Tools CP-SAT (Solver V2) |
| **Worker Queue** | Asynchronous generation and repair jobs | Redis 7, Celery |
| **Database** | Persistent data storage and tenant isolation | PostgreSQL 15 / 16 (RLS enabled) |
| **Authentication** | User identity, organizations, and RBAC | Clerk Authentication |

## Data or Request Flow
1. School administrators log into Cronos and configure school parameters.
2. Administrators invite staff members through the team view (`Equipa`).
3. Teachers record weekly availability through the self-service portal.
4. Administrators trigger full schedule generation.
5. The scheduler worker computes optimal timetable slots using OR-Tools CP-SAT.
6. Administrators review and approve schedule drafts.
7. Teachers mark lesson logs (*Sumários*) and report absences (*Faltas*).
8. The engine computes adaptive schedule repairs when required.

## Contracts and Invariants
- Each school operates inside an isolated organization tenant (`organization_id`).
- Teachers do not have direct access to internal administrative settings.
- The system enforces hard constraints (zero teacher double-booking, room capacity limits).

## States and Transitions
- **School Year Lifecycle**: `DRAFT` -> `ACTIVE` -> `ARCHIVED`.
- **Schedule Draft Lifecycle**: `GENERATING` -> `REVIEW_PENDING` -> `APPROVED` (or `REJECTED`).

## Failure Modes
- **Authentication Failure**: Invalid Clerk JWT results in HTTP `401 Unauthorized`.
- **Tenant Context Missing**: Database query without `organization_id` fails Row-Level Security policy.
- **Unfeasible Constraints**: Solver returns `Impossible` status if hard constraints cannot be satisfied.

## Verification Procedure
Run the local Docker environment and access `http://localhost:5173`. Perform administrator login and verify dashboard widgets.

## Source Map
- Backend Core: `backend/app/main.py`
- Frontend App Entry: `frontend/src/App.jsx`
- Database Models: `backend/app/models.py`

## Related Documents
- [System Architecture](../01_system_architecture/SYSTEM_ARCHITECTURE.md)
- [Glossary](GLOSSARY.md)
