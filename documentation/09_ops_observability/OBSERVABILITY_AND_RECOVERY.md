# Observability and Recovery

## Purpose

This document describes health signals, structured logs, scheduler telemetry, and recovery actions.

## Intended Reader

This document targets operators, backend support engineers, and release engineers.

## Prerequisites

Read [Local Runtime](LOCAL_RUNTIME.md) and [Testing and CI](../08_security_quality/TESTING_AND_CI.md).

## What the System Does

The API exposes liveness, readiness, and a public API health route.
The backend emits structured logs. It does not send request data to an external error tracker.
It writes colored console logs locally and JSON logs in every other environment.
A request-id context variable binds each log line to the `X-Request-ID` response header.
Scheduler jobs store status, diagnostics, and search evidence.

There is no Sentry or other error-tracker integration. Incident detection relies on Railway platform logs and alerts.

## Why the Behavior Exists

Health endpoints separate process availability from dependency readiness.
Persisted job evidence supports tenant-scoped operational review without logging request PII.

## Components and Ownership

| Signal | Source |
| :--- | :--- |
| Liveness | `backend/app/main.py` (`/health/live`) |
| Readiness | `backend/app/main.py`, `backend/app/api/v1/endpoints/health.py` |
| Public API health | `backend/app/api/v1/endpoints/health.py` (`/health`) |
| Structured logging | `backend/app/core/logging.py` |
| Request identity | `backend/app/main.py` (`X-Request-ID` context variable) |
| Scheduler diagnostics | `backend/app/scheduler/infrastructure/diagnostics.py`, `backend/app/scheduler_v1_worker.py` |
| Rate limiting | `backend/app/core/ratelimit.py` |
| Integrity audits | `backend/scripts/audit_triggers.py`, `backend/scripts/audit_database_integrity.py` |

## Data or Request Flow

1. A monitor calls `/health/live`.
2. A readiness check runs PostgreSQL `SELECT 1` and a Redis ping.
3. Scheduler phases record structured log events and job evidence.
4. Operators inspect logs and job fields.
5. Operators use the recovery procedure for the affected component.

## Contracts and Invariants

- Liveness returns `200` when the process handles requests.
- Liveness and readiness are rate-limit exempt.
- Readiness returns `revision`, `postgres`, and `redis` fields.
- Readiness returns `503` when PostgreSQL or Redis is unavailable.
- Health access lines are filtered from the access log.
- Scheduler diagnostics emit `scheduler_v1_phase_started`, `scheduler_v1_model_built`,
  `scheduler_v1_model_too_large`, `scheduler_v1_phase_finished`, and
  `scheduler_v1_search_finished`. These events
  include container memory and OOM metrics from `/sys/fs/cgroup`.
- When Redis cannot enforce a limit, the API returns `503` with code
  `RATE_LIMIT_UNAVAILABLE`.
- Scheduler jobs (`scheduler_job_v1`) expose `status`, `result_code`, `stop_reason`, `attempt_token`, `heartbeat_at` and `cancellation_requested_at`. Job evidence stays technical and internal.
- Logs must not contain contact form PII or provider secrets.
- Database audits run with the migrator role.

## States and Transitions

Jobs move from `QUEUED` through `RUNNING` and `VALIDATING` to `SUCCEEDED`, `CANCELLED`, `STALE`, `INFEASIBLE`, `INCONCLUSIVE` or `FAILED`. `QUEUED` age alone is an operational signal,
not proof that a job was lost: recovery never fails a queued job without
broker or worker evidence. The `scheduler.v1.supervise` task (every 60 seconds) closes a `RUNNING` or `VALIDATING` job whose heartbeat is older than `SCHEDULER_V1_ABANDONED_SECONDS` (default 120). A persisted cancellation request produces `CANCELLED`; otherwise the result is `FAILED` with result code `WORKER_STALLED`. The supervisor wakes the executor when work is queued and nothing runs.
Provider and webhook states remain queryable through their persisted status fields.

## Failure Modes and Recovery

| Symptom | Action |
| :--- | :--- |
| Liveness fails | Inspect API process and restart the API service. |
| Readiness returns `503` | Check PostgreSQL and Redis connectivity. |
| Job remains active | The supervisor finalizes jobs with a stale heartbeat. Inspect `result_code`, `stop_reason`, the scheduler events, and worker and supervisor logs. |
| Old queued jobs | Query the queued backlog and verify dispatcher, broker, worker, and deployment revision before taking action. Do not mark the job failed based on age alone. |
| Worker task is missing | Inspect Celery registration and worker command. |
| Migration or trigger audit fails | Stop release, inspect migration state, and restore from verified backup if required. |

## Verification Procedure

1. Query both health endpoints.
2. Inspect worker tasks with Celery inspect. Confirm one solver worker, and one `scheduler-supervisor` worker, which also runs the only Beat.
3. Run the trigger and integrity audits with the migrator role, as the [Command Reference](../00_getting_started/COMMAND_REFERENCE.md#backend-checks-outside-the-runner) shows.
4. Record incident evidence before changing data.

For an operational view of queued work, use:

```sql
SELECT id, organization_id, queued_at, status, result_code
FROM scheduler_job_v1
WHERE status = 'QUEUED'
ORDER BY queued_at ASC;
```

Before recovery or replay, verify that the API, worker, supervisor, and frontend
are running the same intended revision and that the broker contains the
corresponding dispatch message.

## Support workflow

Ask only for the visible reference and approximate time. Search structured logs
for `request_id` or the provider operation reference.
Identify the failing boundary. Apply the documented retry or recovery action.
Do not request passwords or screenshots with personal data. Escalate or roll
back when the reference indicates a systemic failure.

## Source Map

- `backend/app/main.py`
- `backend/app/api/v1/endpoints/health.py`
- `backend/app/core/logging.py`
- `backend/app/core/ratelimit.py`
- `backend/app/scheduler/infrastructure/diagnostics.py`
- `backend/app/scheduler_v1_worker.py`
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
