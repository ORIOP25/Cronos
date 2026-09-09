# Production Deployment Runbook

## Purpose

This document describes the repository deployment contract for Railway, the frontend host, DNS, secrets, verification, and rollback.

## Intended Reader

This document targets release engineers and operators with provider access.

## Prerequisites

Confirm provider access, billing, domain ownership, backups, and secret storage.
Do not treat this document as proof that an external dashboard is configured.

## What the System Does

The repository defines one API service, one worker, one Beat service, and one database bootstrap job for Railway.
The frontend builds from `frontend/` and produces `frontend/dist`.
The build emits `index.html`, `vantagens.html`, `como-funciona.html`, `sobre.html`, `ajuda.html`, `contacto.html`, and `cookies.html`.

## Why the Behavior Exists

The API applies migrations before startup.
The worker and Beat reuse the backend image with separate commands.
The bootstrap job creates restricted roles before runtime deployment.

## Components and Ownership

| Service | Configuration | Command or purpose |
| :--- | :--- | :--- |
| API | `backend/railway/api.json` | Alembic pre-deploy, Uvicorn, readiness healthcheck |
| Worker | `backend/railway/worker.json` | Celery scheduler worker, concurrency one |
| Beat | `backend/railway/beat.json` | Celery hourly schedule under `/tmp` |
| Bootstrap | `backend/railway/bootstrap.json` | `python -m app.ops.provision_database` |
| Frontend | `frontend/Dockerfile` or Pages project | Vite build output `dist` |

## Data or Request Flow

1. Create PostgreSQL and Redis on a private provider network.
2. Run the bootstrap job with temporary administrator access.
3. Remove the bootstrap URL after successful idempotent execution.
4. Deploy the API and confirm health.
5. Deploy one worker and one Beat replica.
6. Build and publish the frontend.
7. Configure domains and verify deep links, CORS, Clerk, and provider flows.

## Repository Deployment Contract

### Railway API

Use root directory `/backend` and `backend/railway/api.json`.
Set `DATABASE_POOLING_ENABLED=true` and `PORT=8000`.
Use the `cronos_app` URL for runtime access.
Use the `cronos_migrator` URL for migrations.
The API publishes `scheduler.run_generation_job` through `celery_app.send_task`.
Do not import `app.scheduler_worker` in the API process.

### Railway worker and Beat

Use root directory `/backend` and their matching JSON files.
Set `DATABASE_POOLING_ENABLED=false`.
Use private PostgreSQL and Redis URLs.
Run one worker and one Beat replica.
The worker command includes `--include=app.scheduler_worker`; this process owns the scheduler task and OR-Tools imports.

### Database bootstrap

Set `BOOTSTRAP_DATABASE_URL`, `CRONOS_MIGRATOR_PASSWORD`, and `CRONOS_APP_PASSWORD` only on the temporary job.
The job creates `cronos_migrator`, `cronos_app`, and `cronos_auth_definer`.
Run it twice to verify idempotency.

### Frontend

Build from `frontend` with `npm ci && npm run build`.
Publish `dist`.
Set `VITE_API_BASE_URL`, `VITE_CLERK_PUBLISHABLE_KEY`, and `VITE_TURNSTILE_SITE_KEY` as public build variables.
Nginx resolves public deep links with `try_files $uri $uri.html $uri/ /index.html`.
Cloudflare Pages uses `public/_redirects` for the nine public route HTML files.
Test every client route on the hosting provider before domain cutover.

## Contracts and Invariants

- Never store secrets in Git, `VITE_*`, images, logs, screenshots, or tickets.
- Keep Redis private.
- Keep one Beat replica.
- Do not run automatic database downgrades during rollback.
- Confirm code and schema compatibility before reverting the API.
- Preserve existing mail records during application DNS changes.
- Configure `TRUSTED_PROXY_IPS` only for provider networks that the operator trusts.

## States and Transitions

`bootstrap` -> `migrate` -> `api healthy` -> `worker ready` -> `beat ready` -> `frontend verified` -> `DNS cutover`.

Rollback reverses frontend, API processes, and DNS only when required.

## Failure Modes

- Missing production secrets prevent API startup.
- Migration failure prevents the API deployment from becoming healthy.
- Worker or Beat misconfiguration leaves jobs or reconciliation unprocessed.
- Missing SPA fallback causes deep-link `404` responses.
- Missing backups makes database-loss recovery unavailable.

## Verification Procedure

1. Check API `/health/live` and `/health/ready`.
2. Confirm worker registration for `scheduler.run_generation_job`.
3. Confirm Beat schedules `members.run_scheduled_reconciliation`.
4. Confirm Beat schedules `privacy.run_maintenance`.
5. Test contact delivery, authentication, invitations, schedule approval, occurrence decisions, and timesheets.
6. Test `/`, `/login`, `/register`, `/dashboard`, `/schedules`, `/my-schedules`, `/absences`, and `/cookies` after refresh.
7. Record deployment IDs, backup IDs, and rollback target.

## Source Map

- `backend/railway/api.json`
- `backend/railway/worker.json`
- `backend/railway/beat.json`
- `backend/railway/bootstrap.json`
- `backend/app/ops/provision_database.py`
- `frontend/Dockerfile`
- `frontend/nginx.conf`
- `frontend/public/_headers`
- `.env.example`, `backend/.env.example`

## Related Documents

- [Local Runtime](LOCAL_RUNTIME.md)
- [Observability and Recovery](OBSERVABILITY_AND_RECOVERY.md)
- [Testing and CI](../08_security_quality/TESTING_AND_CI.md)
