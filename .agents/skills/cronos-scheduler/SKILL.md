---
name: cronos-scheduler
description: Cronos scheduler engine skill. Use for OR-Tools CP-SAT models, schedule generation and adaptive recovery jobs, the Celery worker and supervisor, proposals (approve, reject, diff), readiness fingerprints, and scheduler tests.
---

# Cronos Scheduler

Load `cronos-base`, `ponytail`, and `cronos-backend` first.
Read the [Scheduler V1 Tech Spec](../../../documentation/03_scheduler_engine/SCHEDULER_V1_TECH_SPEC_V2.md) before changing behavior. It holds the product decisions.

## Start here

- Layers: `backend/app/scheduler/domain/` (pure rules) -> `application/` (use cases) -> `infrastructure/` (SQLAlchemy, OR-Tools) -> `composition.py` (wiring).
- API: `backend/app/api/v1/endpoints/scheduler.py`. Dispatch: `backend/app/scheduler/infrastructure/task_dispatcher.py` sends `scheduler.v1.run_next_job`.
- Worker: `backend/app/scheduler_v1_worker.py`. Supervisor: `backend/app/scheduler_recovery_worker.py`. Celery app and Beat: `backend/app/celery_worker.py`.
- Jobs, proposals, and input snapshot: `backend/app/scheduler/infrastructure/jobs.py`, `proposals.py`, and `snapshot.py`.
- Readiness fingerprint: `backend/app/services/scheduler_fingerprint_service.py` (`generation_input_snapshot`), outside the scheduler package.
- Frontend: `frontend/src/features/scheduling/data.js` and `frontend/src/pages/Schedules.jsx`.

## Reference implementation

- Endpoint: `cancel_generation_job` in `scheduler.py` with `request_cancellation` in `backend/app/scheduler/infrastructure/jobs.py`.
- Hook: `useCancelScheduleTask` in `frontend/src/features/scheduling/data.js`.
- Do not copy `generate_schedule` in `scheduler.py` as a template; it mixes dispatch and error mapping.

## Minimal proof

- Domain rules: `node scripts/test.mjs fast --scope backend -- -k "scheduler and (policy or validation or debt or progress)"`.
- Solver changes: `node scripts/test.mjs fast --scope backend -- -k scheduler`. Real CP-SAT tests run for minutes.
- Jobs, proposals, or API: `node scripts/test.mjs integration -- -k scheduler`. CI does not run `test_scheduler_v1_api.py` or `test_scheduler_v1_lifecycle.py`, so this local run is the only proof.

## Boundaries

- `domain/` imports no FastAPI, SQLAlchemy, Celery, Redis, `app.api`, or `app.services`. `application/` imports no OR-Tools or infrastructure. `backend/tests/unit/test_backend_foundation_contracts.py` enforces this.
- Only `placement_model.py`, `constructive.py`, and `annual_model.py` import OR-Tools. The API process never imports `app.scheduler_v1_worker`.
- One solver at a time: worker concurrency 1 and a PostgreSQL advisory lock.
- Lock order: school state row first, then job or proposal.
- Generation never publishes by itself. Approval revalidates `expected_input_revision` and never runs the solver.
- Terminal jobs never return to `RUNNING`; a retry is a new attempt.
- `constraint_policy.py` coverage stays at 100% and `candidate_validation.py` at 90%.

## Pitfalls

- `placement_model.py`, `search.py`, `snapshot.py`, and `proposals.py` are large. Read by function name.
- The endpoint imports infrastructure modules directly; no test guards the endpoint layer.
- The terminal job status list is duplicated in `frontend/src/pages/Schedules.jsx` and `frontend/src/features/scheduling/data.js`.
- A worker started without `--include=app.scheduler_v1_worker` does not register the task, and jobs stay `QUEUED`.
- Availability and catalog writes bump scheduler revisions and can make a pending proposal `STALE`.

## Done when

- The proof above passed, including `integration` for any job or proposal change, and the pull request names it.
- The tech spec or the [Scheduler Engine](../../../documentation/03_scheduler_engine/README.md) guide reflects any changed rule.

## Documentation

- [Scheduler Engine](../../../documentation/03_scheduler_engine/README.md)
- [Scheduler V1 Tech Spec](../../../documentation/03_scheduler_engine/SCHEDULER_V1_TECH_SPEC_V2.md)
- [Observability and Recovery](../../../documentation/09_ops_observability/OBSERVABILITY_AND_RECOVERY.md)
