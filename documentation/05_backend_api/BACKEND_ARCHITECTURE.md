# Backend Architecture

## Purpose

This document describes the FastAPI lifecycle, dependency injection, middleware, services, and provider adapters.

## Intended Reader

This document targets Python backend engineers.

## Prerequisites

Read [System Architecture](../01_system_architecture/SYSTEM_ARCHITECTURE.md) and [API Reference](API_REFERENCE.md).

## What the System Does

The backend exposes a JSON API under `/api/v1`.
It uses async SQLAlchemy sessions, synchronous service helpers where required, Clerk authentication, and PostgreSQL RLS.

## Why the Behavior Exists

Dependencies centralize tenant context and access checks.
Provider adapters isolate external HTTP calls from application services.

## Components and Ownership

| Component | Implementation | Responsibility |
| :--- | :--- | :--- |
| Application | `backend/app/main.py` | Lifespan, middleware, handlers, routes |
| Dependencies | `backend/app/api/deps.py` | DB, Clerk, actor, admin context |
| Services | `backend/app/services/` | Transactions and domain rules |
| Contact adapters | `backend/app/contact/` | Turnstile and Resend integration |
| Database | `backend/app/db/` | Async engine and tenant context |
| Schemas | `backend/app/schemas.py` | Request and response validation |
| Scheduler dispatch | `backend/app/scheduler/infrastructure/task_dispatcher.py` | Publish named Celery tasks without importing the solver worker |
| Exceptions | `backend/app/core/exceptions.py` | Error classification and mapping |

## Data or Request Flow

```mermaid
flowchart TD
    Request[HTTP request] --> Headers[Security headers]
    Headers --> Context[Request context and X-Request-ID]
    Context --> CORS[CORS middleware]
    CORS --> Limit[Route body limit]
    Limit --> Rate[Fail-closed rate limit]
    Rate --> Auth[Clerk dependency]
    Auth --> Tenant[Resolve actor and tenant context]
    Tenant --> Handler[Endpoint handler]
    Handler --> Service[Application service]
    Service --> DB[(Async SQLAlchemy and PostgreSQL)]
    Service --> Provider[Provider adapter when required]
```

1. The outermost server-error middleware catches unhandled exceptions.
2. Security headers, request context, CORS, body limit, and rate limit wrap every request.
3. Protected dependencies verify Clerk and resolve the active actor.
4. The database session installs tenant context.
5. A handler calls a service and returns a schema or error.
6. The session commits on success and rolls back on failure.

## Contracts and Invariants

- Queries scope tenant-owned data by `organization_id`.
- The database session sets `app.current_organization_id` before protected work.
- Contact delivery uses one lifespan-scoped `httpx.AsyncClient`.
- The contact application service does not import FastAPI, Resend, Cloudflare, or `httpx`.
- Production validates required secrets and HTTPS origin settings at startup.
- API error handlers return JSON `detail` values.

## States and Transitions

Application errors map to `400`, `401`, `403`, `404`, `409`, `422`, `429`, or `503` by error kind.
Unhandled errors log a traceback and return a safe `500` response.
Rate-limit storage failure returns `503 RATE_LIMIT_UNAVAILABLE`.

## Failure Modes

- Invalid configuration prevents production startup.
- Redis unavailable during lifespan logs a readiness warning.
- Database failure returns a dependency or application error.
- Provider timeout returns `503` without retrying the web request.

## Verification Procedure

1. Run backend tests against a test database (`cronos_test_db` or `cronos_ci_db`).
2. Run `ruff format --check .` and `ruff check .`.
3. Run migration drift and database audits.
4. Build the hardened backend runtime image.

## Source Map

- `backend/app/main.py`
- `backend/app/api/deps.py`
- `backend/app/db/database.py`
- `backend/app/db/tenant.py`
- `backend/app/scheduler/infrastructure/task_dispatcher.py`
- `backend/app/contact/`
- `backend/app/middleware/request_body_limit.py`
- `backend/app/core/ratelimit.py`
- `backend/tests/unit/test_error_handlers.py`

## Onboarding Backend Boundary

The onboarding backend follows the existing request boundary:

`FastAPI router -> actor dependency -> application service -> SQLAlchemy model -> PostgreSQL`

The session endpoint bootstraps the tenant and current member.
The Foundation router delegates draft and completion rules to `FoundationService`.
Readiness and dashboard routers expose derived state after Foundation completion.
All endpoint database dependencies use function scope so `commit` or `rollback` finishes before the response.

## Related Documents

- [API Reference](API_REFERENCE.md)
- [Errors and Transactions](ERRORS_AND_TRANSACTIONS.md)
- [Security and Tenant Isolation](../08_security_quality/SECURITY_AND_TENANT_ISOLATION.md)
