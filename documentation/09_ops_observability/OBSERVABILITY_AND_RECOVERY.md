# Observability and Recovery

## Purpose
This document specifies health monitoring metrics, Celery queue alerts, log formatting, and incident recovery runbooks.

## Intended Reader
This document targets site reliability engineers and backend support engineers.

## Prerequisites
Read [Local Runtime](LOCAL_RUNTIME.md).

## What the System Does
Cronos monitors runtime health, task queue depth, solver execution latency, and database connection pools.

## Health Metrics and Alert Thresholds

| Metric Name | Normal Threshold | Critical Alert Target | Action on Alert |
| :--- | :--- | :--- | :--- |
| **API Response Time** | < 200 ms | > 2000 ms (5 min) | Inspect database slow queries and pool locks |
| **Celery Queue Length** | < 10 tasks | > 50 tasks | Scale solver worker container instances |
| **Solver Failure Rate** | < 1% | > 5% | Check input constraint sanity and solver timeouts |
| **DB Pool Saturation** | < 70% | > 90% | Adjust SQLAlchemy connection pool sizes |

## Incident Recovery Runbooks

### Runbook 1: Backend CI Failure Recovery
1. Pull target branch and run local backend test suite: `pytest tests/ -v`.
2. Inspect failure stack trace. If database error occurs, verify local test database URL.
3. Check Alembic migration status: `alembic check`.
4. If schema drift exists, create missing migration revision.

### Runbook 2: Stuck Scheduler Celery Worker
1. List pending generation jobs: `GET /api/v1/scheduler/status`.
2. Send cancellation request for hung task: `POST /api/v1/scheduler/jobs/{id}/cancel`.
3. Restart worker container: `docker compose restart cronos-worker`.

### Runbook 3: Database Trigger / Integrity Failure
1. Execute database trigger audit script: `python backend/scripts/audit_triggers.py`.
2. Execute integrity scanner: `python -m scripts.audit_database_integrity`.
3. Apply migration repair scripts if corrupt state is detected.

## Verification Procedure
Execute `python backend/scripts/audit_triggers.py`. Confirm zero reported trigger anomalies.

## Source Map
- Audit Scripts: `backend/scripts/audit_triggers.py`, `backend/scripts/audit_database_integrity.py`
- Recovery Runbook Source: `documentation/08_security_quality/BACKEND_CI_FAILURE_RECOVERY_PLAN.md` (historical source)

## Related Documents
- [Local Runtime](LOCAL_RUNTIME.md)
- [Testing and CI](../08_security_quality/TESTING_AND_CI.md)
