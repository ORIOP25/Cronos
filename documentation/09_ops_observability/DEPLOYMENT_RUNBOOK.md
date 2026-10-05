# Production Deployment Runbook

## Purpose

This document describes the repository deployment contract for Railway, the frontend host, DNS, secrets, verification, and rollback.

## Intended Reader

This document targets release engineers and operators with provider access.

## Prerequisites

Confirm provider access, billing, domain ownership, backups, and secret storage.
Do not treat this document as proof that an external dashboard is configured.

## What the System Does

The repository defines one API service, one worker, one supervisor, one Beat service, and one database bootstrap job for Railway.
The frontend builds from `frontend/` and produces `frontend/dist`.
The build emits `index.html`, `app-shell.html`, one marketing HTML file per route, and the `_worker.js` edge handler.

## Why the Behavior Exists

The API applies migrations before startup.
The worker, supervisor, and Beat reuse the backend image with separate commands.
The bootstrap job creates restricted roles before runtime deployment.

## Components and Ownership

| Service | Configuration | Command or purpose |
| :--- | :--- | :--- |
| API | `backend/railway/api.json` | Alembic pre-deploy, Uvicorn, readiness healthcheck |
| Worker | `backend/railway/worker.json` | Celery scheduler solver worker, concurrency one |
| Supervisor | `backend/railway/supervisor.json` | Celery recovery supervisor on the `scheduler-supervisor` queue |
| Beat | `backend/railway/beat.json` | One replica with reconciliation, maintenance, and supervisor dispatch |
| Bootstrap | `backend/railway/bootstrap.json` | `python -m app.ops.provision_database` |
| Frontend | `frontend/Dockerfile` or Pages project | Vite build output `dist` |

## Data or Request Flow

1. Confirm the exact immutable release SHA and passing test artifacts.
2. Create a production backup and restore it into a disposable database.
3. Run the additive migration, trigger audit, and integrity audit on the restore.
4. Run the bootstrap job with temporary administrator access if required.
5. Deploy the API and confirm readiness and revision.
6. Deploy one worker with concurrency `1`.
7. Deploy one Beat replica and verify all three periodic tasks.
8. Build and publish the frontend with the same release identity.
9. Configure domains and verify deep links, CORS, Clerk, and provider flows.

## Repository Deployment Contract

### Railway API

Use root directory `/backend` and `backend/railway/api.json`.
Set `DATABASE_POOLING_ENABLED=true` and `PORT=8000`.
Use the `cronos_app` URL for runtime access.
Use the `cronos_migrator` URL for migrations.
The API publishes `scheduler.v1.run_next_job` through `celery_app.send_task`.
Do not import `app.scheduler_v1_worker` in the API process.

### Railway worker and Beat

Use root directory `/backend` and their matching JSON files.
Set `DATABASE_POOLING_ENABLED=false`.
Use private PostgreSQL and Redis URLs.
Run one worker and one Beat replica.
The worker command includes `--include=app.scheduler_v1_worker`; this process owns the scheduler task and OR-Tools imports.
The supervisor command includes `--include=app.scheduler_recovery_worker` and consumes only the `scheduler-supervisor` queue.

### Database bootstrap

Set `BOOTSTRAP_DATABASE_URL`, `CRONOS_MIGRATOR_PASSWORD`, and `CRONOS_APP_PASSWORD` only on the temporary job.
The job creates `cronos_migrator`, `cronos_app`, and `cronos_auth_definer`.
Run it twice to verify idempotency.

### Frontend

Build from `frontend` with `npm ci && npm run build`.
Publish `dist`.
Set `VITE_API_BASE_URL`, `VITE_CLERK_PUBLISHABLE_KEY`, and `VITE_TURNSTILE_SITE_KEY` as public build variables.
Nginx serves public routes with `try_files $uri $uri.html =404` and application routes with `app-shell.html`.
Cloudflare Pages uses `public/_worker.js` to route public, application, and static paths.
Unknown HTML routes fetch the canonical `/404` asset and preserve the HTTP `404` status.
Fetching `/404.html` can return an empty canonical redirect. Never re-label that redirect as a `404` response.
Test every client route on the hosting provider before domain cutover.

### Secrets and environment

Set these names in the provider secret store. Never store them in Git.
Runtime: `DATABASE_URL`, `REDIS_URL`, `CELERY_BROKER_URL`, `CLERK_SECRET_KEY`,
`CLERK_WEBHOOK_SECRET`, `RESEND_API_KEY`, `TURNSTILE_SECRET_KEY`, and
`TRUSTED_PROXY_IPS`.
Migrations: `MIGRATION_DATABASE_URL`.
Release identity: `RAILWAY_GIT_COMMIT_SHA` or `DEPLOYED_REVISION`.

### Scheduler v1 baseline reset

To reinstall an empty consolidated baseline before real use, run the tested downgrade/upgrade cycle on the API service. The config file limits `preDeployCommand` to one shell line.

1. Stop job intake and scale the solver, supervisor, and Beat services to zero replicas.
2. Set the API `preDeployCommand` to `["alembic downgrade base && alembic upgrade head"]`.
3. Deploy the API at that revision. The pre-deploy drops every table and reinstalls the baseline.
4. Restore the API `preDeployCommand` to `["alembic upgrade head"]` and deploy again.
5. Restore the solver, supervisor, and Beat replicas.

Never run this cycle after real school data exists. Confirm that no generation job is active before step 2.

## Contracts and Invariants

- Never store secrets in Git, `VITE_*`, images, logs, screenshots, or tickets.
- Keep Redis private.
- Keep one Beat replica.
- Keep exactly one solver worker with concurrency `1` during the initial rollout.
- `SCHEDULER_V1_NUM_WORKERS` sets the CP-SAT search workers, not the Celery concurrency. Confirm the intended provider value before rollout.
- Run exactly one `scheduler-supervisor` replica on the `scheduler-supervisor` queue.
- Expose and verify the intended SHA on API and readiness health responses.
- Do not run automatic database downgrades during rollback.
- Confirm code and schema compatibility before reverting the API.
- Preserve existing mail records during application DNS changes.
- Configure `TRUSTED_PROXY_IPS` only for provider networks that the operator trusts.

## States and Transitions

`release verified` -> `backup restore verified` -> `migrate` -> `api healthy` -> `worker ready` -> `beat ready` -> `frontend verified` -> `DNS cutover`.

Rollback reverses frontend, API processes, and DNS only when required. Do not
downgrade the additive database migration during rollback.

## Failure Modes

- Missing production secrets prevent API startup.
- Migration failure prevents the API deployment from becoming healthy.
- Worker or Beat misconfiguration leaves jobs or reconciliation unprocessed.
- Missing SPA fallback causes deep-link `404` responses.
- Missing backups makes database-loss recovery unavailable.

## Verification Procedure

1. Check API `/health/live` and `/health/ready`.
2. Confirm the migration chain head is `0017_active_course_abbreviations`.
3. Confirm worker registration for `scheduler.v1.run_next_job`.
4. Confirm Beat schedules `members.run_scheduled_reconciliation`, `privacy.run_maintenance`, and `scheduler.v1.supervise`.
5. Check that API, worker, Beat, frontend, and migration reference the intended SHA.
   If queued jobs are old, treat that as an operational signal and verify the
   broker/dispatcher and worker on the same SHA; queued age alone does not
   justify failing a job.
6. Test contact delivery, authentication, invitations, schedule approval, occurrence decisions, and timesheets.
7. Test `/`, `/login`, `/register`, `/dashboard`, `/schedules`, `/my-schedules`, `/absences`, and `/cookies` after refresh.
8. Record deployment IDs, backup IDs, restore evidence, and the previous rollback target.

## Source Map

- `backend/railway/api.json`
- `backend/railway/worker.json`
- `backend/railway/supervisor.json`
- `backend/railway/beat.json`
- `backend/railway/bootstrap.json`
- `backend/app/ops/provision_database.py`
- `backend/app/main.py`
- `backend/app/api/v1/endpoints/health.py`
- `frontend/Dockerfile`
- `frontend/nginx.conf`
- `frontend/public/_worker.js`
- `frontend/public/_headers`
- `.env.example`, `backend/.env.example`

## Related Documents

- [Local Runtime](LOCAL_RUNTIME.md)
- [Observability and Recovery](OBSERVABILITY_AND_RECOVERY.md)
- [Testing and CI](../08_security_quality/TESTING_AND_CI.md)
