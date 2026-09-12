# Observability and Recovery

## Purpose

This document describes health signals, structured logs, scheduler telemetry, and recovery actions.

## Intended Reader

This document targets operators, backend support engineers, and release engineers.

## Prerequisites

Read [Local Runtime](LOCAL_RUNTIME.md) and [Testing and CI](../08_security_quality/TESTING_AND_CI.md).

## What the System Does

The API exposes liveness and readiness.
The backend emits structured logs. It does not send request data to an external error tracker.
Scheduler, occurrence, and teacher endpoints store operational telemetry.

The `rgpd-cookies` rollout removes Sentry request telemetry. Production
rollout requires an operator approval that platform logs and alerts cover the
same incident-detection needs. A rollback restores application code only; data
already excluded from Sentry cannot be recovered.

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
- Scheduler jobs expose terminal status, failure code, duration, and an opaque
  failure reference. Stored failure messages remain technical and internal.
- Logs must not contain contact form PII or provider secrets.
- Database audits run with the migrator role.

## States and Transitions

Jobs move from queued or running states to success, cancellation,
no-valid-output, or failure. A queued job older than two minutes becomes
`FAILED / DISPATCH_STALLED`. A running job past its deadline by 30 seconds
becomes `FAILED / WORKER_STALLED`. A cancel request older than two minutes
becomes `CANCELED`.
Provider and webhook states remain queryable through their persisted status fields.

## Failure Modes and Recovery

| Symptom | Action |
| :--- | :--- |
| Liveness fails | Inspect API process and restart the API service. |
| Readiness returns `503` | Check PostgreSQL and Redis connectivity. |
| Job remains active | Beat recovery finalizes stale jobs. Inspect `failure_reference`, the scheduler event, and worker logs. |
| Worker task is missing | Inspect Celery registration and worker command. |
| Migration or trigger audit fails | Stop release, inspect migration state, and restore from verified backup if required. |

## Verification Procedure

1. Query both health endpoints.
2. Inspect worker tasks with Celery inspect. Confirm one solver worker and one Beat replica.
3. Run `python -m scripts.audit_triggers` from `backend/`.
4. Run `python -m scripts.audit_database_integrity` from `backend/`.
5. Record incident evidence before changing data.

## Support workflow

Ask only for the visible reference and approximate time. Search structured logs
for `request_id`, `failure_reference`, or the provider operation reference.
Identify the failing boundary. Apply the documented retry or recovery action.
Do not request passwords or screenshots with personal data. Escalate or roll
back when the reference indicates a systemic failure.

## Source Map

- `backend/app/main.py`
- `backend/app/api/v1/endpoints/health.py`
- `backend/app/services/scheduler_observability.py`
- `backend/app/services/teacher_observability_service.py`
- `backend/scripts/audit_triggers.py`
- `backend/scripts/audit_database_integrity.py`

## Onboarding Observability and Recovery

Monitor these onboarding boundaries:

- session bootstrap success and provider `503` failures;
- Foundation draft version conflicts;
- incomplete or already-completed Foundation commands;
- generated timeslot count at completion;
- readiness blockers and stale prevalidation fingerprints;
- dashboard mode changes after the first real schedule approval;
- legal acceptance conflicts and stale document versions;
- privacy maintenance counts and failures.

The tutorial is local-only and has no backend request to monitor.

When a Foundation completion appears successful but the UI shows the previous state:

1. inspect the API response and database status;
2. refresh `foundation-status`, `foundation-draft`, and `current-member`;
3. inspect the frontend network log for the invalidation requests;
4. confirm that the organization has generated at least one timeslot;
5. repeat only after identifying the stale boundary.

When an E2E onboarding test fails in CI, download `playwright-report` and `test-results`.
Playwright retains a trace on failure and CI uploads both artifacts even when the suite fails.
Retries are disabled, so the first failure is the diagnostic signal.

## Related Documents

- [Local Runtime](LOCAL_RUNTIME.md)
- [Deployment Runbook](DEPLOYMENT_RUNBOOK.md)
- [Security and Tenant Isolation](../08_security_quality/SECURITY_AND_TENANT_ISOLATION.md)
