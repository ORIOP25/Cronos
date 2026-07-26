# System Architecture

## Purpose
This document describes the high-level software architecture, container layout, and component boundaries of Cronos.

## Intended Reader
This document targets software architects, backend engineers, and DevOps specialists.

## Prerequisites
Read the [Project Overview](../00_getting_started/PROJECT_OVERVIEW.md).

## What the System Does
Cronos implements a multi-tenant, web-based platform using a 3-layer Clean Architecture model:

```mermaid
graph TD
    Client[React 19 Frontend UI] -->|HTTP REST + Bearer JWT| API[FastAPI Backend Layer 1]
    API -->|Services & Invariants| Domain[Domain Logic Layer 2]
    Domain -->|Async SQLAlchemy| DB[(PostgreSQL 15/16 + RLS Layer 3)]
    API -->|Redis Queue Jobs| Worker[Celery Async Worker]
    Worker -->|OR-Tools CP-SAT| Solver[Solver V2 Engine]
    Worker -->|Read/Write State| DB
    Client -->|Auth Tokens| Clerk[Clerk Identity Provider]
    BE_Webhook[FastAPI Webhook Handler] <--|HTTP Webhooks| Clerk
```

## Why the Behavior Exists
Clean Architecture isolates user interface concerns from business logic and database persistence. Multi-tenant isolation ensures data privacy across schools. Asynchronous worker queues prevent long-running solver computations from blocking API HTTP threads.

## Components and Ownership

| Layer | Component | File Path / Directory | Responsibility |
| :--- | :--- | :--- | :--- |
| **Layer 1: Interface** | FastAPI Routers | `backend/app/api/v1/endpoints/` | HTTP request handling, payload validation, status codes |
| **Layer 1: Interface** | React UI Pages | `frontend/src/pages/` | Client rendering, route guards, state management |
| **Layer 2: Domain** | Domain Services | `backend/app/services/` | Business rules, solver job orchestration, occurrence state |
| **Layer 2: Domain** | Solver Engine | `backend/app/core/solver.py` | CP-SAT mathematical optimization model |
| **Layer 3: Data** | SQLAlchemy Models | `backend/app/models.py` | ORM definitions, table relationships, foreign keys |
| **Layer 3: Data** | Alembic Migrations | `backend/alembic/versions/` | Database schema version control |

## Data or Request Flow
1. The client sends an HTTP request containing a Clerk Bearer JWT token.
2. FastAPI middleware validates the JWT and resolves the user identity and tenant (`organization_id`).
3. The database session sets PostgreSQL session variable `app.current_organization_id`.
4. Row-Level Security policies filter table queries automatically.
5. Domain services execute business rules and commit database transactions.
6. FastAPI serializes Pydantic response models and returns JSON responses.

## Contracts and Invariants
- All database queries must evaluate against tenant isolation bounds (`organization_id`).
- Direct database modifications bypass domain services only during automated Alembic migrations.

## States and Transitions
System runtime states transition from API request receipt to background Celery execution and persistent storage.

## Failure Modes
- Database Connection Lost: Backend returns HTTP `500 Internal Server Error` and logs database error.
- Redis Down: Async schedule generation requests fail during task queue dispatch.

## Verification Procedure
Inspect running containers using `docker compose ps`. Verify health endpoint using `curl http://localhost:8000/api/v1/health`.

## Source Map
- FastAPI Entry: `backend/app/main.py`
- Database Session Setup: `backend/app/core/database.py`
- Docker Architecture: `docker-compose.yml`

## Related Documents
- [Runtime Flows](RUNTIME_FLOWS.md)
- [Data Model](DATA_MODEL.md)
