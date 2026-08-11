# Observability and Recovery

## Purpose
This document specifies health monitoring metrics, Celery queue alerts, log formatting, and incident recovery runbooks.

## Intended Reader
This document targets site reliability engineers and backend support engineers.

## Prerequisites
Read [Local Runtime](LOCAL_RUNTIME.md).

## What the System Does
Cronos exposes health endpoints, structured logs, optional Sentry reporting, and persisted scheduler and teacher endpoint telemetry.

## Health Metrics and Alert Thresholds

| Signal | Source | Repository Threshold | Action on Failure |
| :--- | :--- | :--- | :--- |
| **Liveness** | `GET /health/live` | HTTP `200` | Restart the backend process if unavailable |
| **Readiness** | `GET /health/ready` | HTTP `200`; otherwise `503` | Inspect PostgreSQL and Redis connectivity |
| **Scheduler Jobs** | Job status, duration, failure fields | Terminal status required | Inspect failure code, message, and worker logs |
| **Teacher Endpoints** | Persisted endpoint event summary | API returns alerts from stored policy | Inspect endpoint status and latency samples |
| **Application Errors** | Structured logs and optional Sentry | No static alert threshold in repository | Correlate request path and exception type |

## Incident Recovery Runbooks

### Runbook 1: Backend CI Failure Recovery
1. Pull target branch and run local backend test suite: `pytest tests/ -v`.
2. Inspect failure stack trace. If database error occurs, verify local test database URL.
3. Check Alembic migration status: `docker compose --profile maintenance run --rm db-maintenance alembic check`. This uses the privileged migrator role.
4. If schema drift exists, create missing migration revision.

### Runbook 2: Stuck Scheduler Celery Worker
1. Inspect current state with `GET /api/v1/scheduler/status` and one job with `/jobs/{id}`.
2. Send cancellation request for hung task: `POST /api/v1/scheduler/jobs/{id}/cancel`.
3. Restart the worker container: `docker compose restart worker`.

### Runbook 3: Database Trigger / Integrity Failure
1. Execute database trigger audit script: `python backend/scripts/audit_triggers.py`.
2. From `backend/`, execute `python -m scripts.audit_database_integrity`.
3. Apply migration repair scripts if corrupt state is detected.

## Verification Procedure
From `backend/`, execute both `python -m scripts.audit_triggers` and `python -m scripts.audit_database_integrity`.

## Source Map
- Audit Scripts: `backend/scripts/audit_triggers.py`, `backend/scripts/audit_database_integrity.py`
- Health Implementation: `backend/app/api/v1/endpoints/health.py`
- Scheduler Telemetry: `backend/app/services/scheduler_observability.py`

## Related Documents
- [Local Runtime](LOCAL_RUNTIME.md)
- [Testing and CI](../08_security_quality/TESTING_AND_CI.md)
