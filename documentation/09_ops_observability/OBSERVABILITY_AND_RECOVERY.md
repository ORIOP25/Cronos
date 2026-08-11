# Observability and Recovery

## Purpose

This document describes health signals, structured logs, scheduler telemetry, and recovery actions.

## Intended Reader

This document targets operators, backend support engineers, and release engineers.

## Prerequisites

Read [Local Runtime](LOCAL_RUNTIME.md) and [Testing and CI](../08_security_quality/TESTING_AND_CI.md).

## What the System Does

The API exposes liveness and readiness.
The backend emits structured logs and optional Sentry events.
Scheduler, occurrence, and teacher endpoints store operational telemetry.

## Why the Behavior Exists

Health endpoints separate process availability from dependency readiness.
Persisted event summaries support tenant-scoped operational review without logging request PII.

## Components and Ownership

| Signal | Source |
| :--- | :--- |
| Liveness | `backend/app/main.py` (`/health/live`) |
| Readiness | `backend/app/main.py`, `backend/app/api/v1/endpoints/health.py` |
| Structured logging | `backend/app/core/logging.py` |
| Scheduler telemetry | `backend/app/services/scheduler_observability.py` |
| Occurrence telemetry | `backend/app/models.py`, `occurrence_service.py` |
| Teacher telemetry | `backend/app/services/teacher_observability_service.py` |
| Integrity audits | `backend/scripts/audit_triggers.py`, `audit_database_integrity.py` |

## Data or Request Flow

1. A monitor calls `/health/live`.
2. A readiness check queries PostgreSQL and Redis.
3. Services record scheduler, occurrence, or teacher operational events.
4. Operators inspect logs, job fields, and event summaries.
5. Operators use the recovery procedure for the affected component.

## Contracts and Invariants

- Liveness returns `200` when the process handles requests.
- Readiness returns `503` when PostgreSQL or Redis is unavailable.
- Scheduler jobs expose terminal status, failure code, and duration fields.
- Logs must not contain contact form PII or provider secrets.
- Database audits run with the migrator role.

## States and Transitions

Jobs move from queued or running states to success, cancellation, no-valid-output, or failure.
Provider and webhook states remain queryable through their persisted status fields.

## Failure Modes and Recovery

| Symptom | Action |
| :--- | :--- |
| Liveness fails | Inspect API process and restart the API service. |
| Readiness returns `503` | Check PostgreSQL and Redis connectivity. |
| Job remains active | Inspect job fields, request cancellation, and inspect worker logs. |
| Worker task is missing | Inspect Celery registration and worker command. |
| Migration or trigger audit fails | Stop release, inspect migration state, and restore from verified backup if required. |

## Verification Procedure

1. Query both health endpoints.
2. Inspect worker tasks with Celery inspect.
3. Run `python -m scripts.audit_triggers` from `backend/`.
4. Run `python -m scripts.audit_database_integrity` from `backend/`.
5. Record incident evidence before changing data.

## Source Map

- `backend/app/main.py`
- `backend/app/api/v1/endpoints/health.py`
- `backend/app/services/scheduler_observability.py`
- `backend/app/services/teacher_observability_service.py`
- `backend/scripts/audit_triggers.py`
- `backend/scripts/audit_database_integrity.py`

## Related Documents

- [Local Runtime](LOCAL_RUNTIME.md)
- [Deployment Runbook](DEPLOYMENT_RUNBOOK.md)
- [Security and Tenant Isolation](../08_security_quality/SECURITY_AND_TENANT_ISOLATION.md)
