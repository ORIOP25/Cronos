# Production Deployment Runbook

## Purpose

This document describes the repository deployment contract for Railway, the frontend host, DNS, secrets, verification, and rollback.

## Intended Reader

This document targets release engineers and operators with provider access.

## Prerequisites

Confirm provider access, billing, domain ownership, backups, and secret storage.
Do not treat this document as proof that an external dashboard is configured.

## What the System Does

The repository stores deployment settings for one API service, one worker, one supervisor, one Beat service, and an on-demand bootstrap job.
The provider topology requires private PostgreSQL and Redis services.
Railway deprecated `railway.json` config-as-code for new service attachments.
The `api`, `worker`, and `beat` services still use their `backend/railway/*.json` files.
The `scheduler-supervisor` service is configured in the Railway dashboard with the command and restart policy from `backend/railway/supervisor.json`.
The supervisor file stays in the repository as the reference for those dashboard settings.
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
| Supervisor | Railway dashboard; reference in `backend/railway/supervisor.json` | Celery recovery supervisor on the `scheduler-supervisor` queue |
| Beat | `backend/railway/beat.json` | One replica with reconciliation, maintenance, and supervisor dispatch |
| Bootstrap | `backend/railway/bootstrap.json` | `python -m app.ops.provision_database`; for a temporary job only, there is no standing Railway service |
| Frontend | Cloudflare Pages project (the `production` target of `frontend/Dockerfile` serves the same build behind `frontend/nginx.conf`) | Vite build output `dist` |

### Production topology

This table defines the provider configuration to verify before release.
Repository files and historical conversation reports do not prove the current external state.

| Where | Item | State |
| :--- | :--- | :--- |
| Railway | `api` | Verify `api.cronos.pt` and the settings recorded in `backend/railway/api.json`. |
| | `worker` | Verify the settings recorded in `backend/railway/worker.json`. |
| | `beat` | Verify the settings recorded in `backend/railway/beat.json`. |
| | `scheduler-supervisor` | Verify that the dashboard command, Dockerfile builder, `ON_FAILURE` restart policy, and five retries match `backend/railway/supervisor.json`. |
| | `Postgres` | Verify PostgreSQL 18 and private runtime/migration connections. |
| | `Redis` | Verify Redis 8.2 and private broker access. |
| Cloudflare | DNS for `cronos.pt` | Verify Pages apex delivery, permanent `www` redirection, and the Railway API CNAME. |
| Hostinger | Mailbox mail for `cronos.pt` | Preserve Hostinger MX/SPF/DKIM records. The `_dmarc` record is `p=none` (monitor only). Operator step: enable Cloudflare DMARC Management for aggregate reports, then review them before raising the policy. |
| Resend | Contact form delivery | Verify `forms.cronos.pt` sender authentication and delivery from `website@forms.cronos.pt` to `contacto@cronos.pt`. |

Docker Compose, isolated tests, and CI use `postgres:18-alpine` and `redis:8.2-alpine`, pinned by digest.
Deleting a GitHub secret does not revoke its provider token. Confirm any required Cloudflare or Sonar token revocation in that provider.

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

Use root directory `/backend` and the settings recorded in `/backend/railway/api.json`.
Set `DATABASE_POOLING_ENABLED=true` and `PORT=8000`.
Use the `cronos_app` URL for runtime access.
Use the `cronos_migrator` URL for migrations.
The API publishes `scheduler.v1.run_next_job` through `celery_app.send_task`.
Do not import `app.scheduler_v1_worker` in the API process.

### Railway worker and Beat

Use root directory `/backend` and the settings in `worker.json` and `beat.json`.
Configure `scheduler-supervisor` in the dashboard with the command and restart policy from `supervisor.json`.
Confirm the dashboard commands match those files.
Set `DATABASE_POOLING_ENABLED=false`.
Use private PostgreSQL and Redis URLs.
Run one worker and one Beat replica.
The worker command includes `--include=app.scheduler_v1_worker`; this process owns the scheduler task and OR-Tools imports.
The supervisor command includes `--include=app.scheduler_recovery_worker`, consumes only the `scheduler-supervisor` queue, and runs the `--pool=solo` pool so it stays a single process.

### Database bootstrap

Create a temporary service with the settings in `backend/railway/bootstrap.json` and delete it afterwards.
Set `BOOTSTRAP_DATABASE_URL`, `CRONOS_MIGRATOR_PASSWORD`, and `CRONOS_APP_PASSWORD` only on that job.
The job creates `cronos_migrator`, `cronos_app`, and `cronos_auth_definer`.
Run it twice to verify idempotency.

### Frontend

Build from `frontend` with `npm ci && npm run build`.
Publish `dist` to the Cloudflare Pages project.
Set `VITE_API_BASE_URL`, `VITE_CLERK_PUBLISHABLE_KEY`, and `VITE_TURNSTILE_SITE_KEY` as public build variables.
Nginx serves public routes with `try_files $uri $uri.html =404` and application routes with `app-shell.html`.
The nginx runtime does not execute `_worker.js`; content negotiation applies to the Pages deployment only.
Cloudflare Pages uses `public/_worker.js` to route public, application, and static paths.
Content negotiation reads the `Accept` quality values in the edge handler.
HTML is the default. Markdown is served when `text/markdown` outranks every supported HTML alternative.
Markdown also wins a quality tie against a wildcard fallback, but not against an explicit HTML type.
The supported HTML alternatives are `text/html` and `application/xhtml+xml`.
Each alternative matches its exact type first, then its subtype wildcard, then `*/*`.
A missing `Accept` header, a `q=0` Markdown range, or a malformed quality value yields HTML.
Unknown paths keep the `404` status and negotiate the same preference.
Asset lookups remove query parameters before calling the Pages asset binding.
Versioned image URLs therefore resolve the same physical files.
The browser keeps the original URL and its query parameters.
Conditional requests with `If-None-Match` or `If-Modified-Since` keep the `304 Not Modified` status and its validators for existing public pages and static assets.
Missing files still return `404` with `Cache-Control: no-store`.
Unknown HTML routes fetch the canonical `/404` asset and preserve the HTTP `404` status.
Fetching `/404.html` can return an empty canonical redirect. Never re-label that redirect as a `404` response.
Test every client route on the hosting provider before domain cutover.

### Domain accessibility

Verify the apex host serves the site over HTTPS with a `200` response.
Verify `api.cronos.pt` resolves to Railway and `/health/ready` answers `ok`.
Verify `www` permanently redirects to the apex and preserves the path and query.
Verify plain HTTP redirects to HTTPS.
Verify the `A` and `AAAA` records resolve on at least two public resolvers.
Verify `robots.txt` still allows public crawling.
Do not weaken TLS, security headers, or bot rules to satisfy a client tool.

### Secrets and environment

Set these names in the provider secret store. Never store them in Git.

`Settings` validation in `backend/app/config.py` runs in every process that imports it, so the `api`, `worker`, `beat` and `scheduler-supervisor` services each need the production values, not only the API. With `ENVIRONMENT=production` the process refuses to start without:

- `TRUSTED_PROXY_IPS` (not `0.0.0.0/0` or `::/0`) and `CORS_ORIGINS`.
- HTTPS, non-localhost values for `FRONTEND_URL`, `CORS_ORIGINS` and `CLERK_AUTHORIZED_PARTIES`, with `FRONTEND_URL` listed in both.
- `CLERK_SECRET_KEY` and `CLERK_WEBHOOK_SECRET`.
- `RESEND_API_KEY`.
- `TURNSTILE_SECRET_KEY`.
- `CELERY_BROKER_URL`.

Per service:

| Service | Names |
| :--- | :--- |
| `api` | `DATABASE_URL` (`cronos_app`), `MIGRATION_DATABASE_URL` (`cronos_migrator`, used by the pre-deploy migration), `REDIS_URL`, `CELERY_BROKER_URL`, `ENVIRONMENT`, `FRONTEND_URL`, `CORS_ORIGINS`, `CLERK_AUTHORIZED_PARTIES`, `TRUSTED_PROXY_IPS`, `CLERK_SECRET_KEY`, `CLERK_WEBHOOK_SECRET`, `RESEND_API_KEY`, `TURNSTILE_SECRET_KEY`, `DATABASE_POOLING_ENABLED=true`, `PORT` |
| `worker`, `scheduler-supervisor`, `beat` | The same required production values, with `DATABASE_POOLING_ENABLED=false`. |
| Bootstrap job | `BOOTSTRAP_DATABASE_URL`, `CRONOS_MIGRATOR_PASSWORD`, `CRONOS_APP_PASSWORD` |

Release identity comes from `RAILWAY_GIT_COMMIT_SHA` (set by Railway) or `DEPLOYED_REVISION`.
`SECRET_KEY`, `SOLVER_*` and `SENTRY_*` variables no longer exist in the code; remove them if they reappear in a dashboard.
The frontend build variables (`VITE_API_BASE_URL`, `VITE_CLERK_PUBLISHABLE_KEY`, `VITE_TURNSTILE_SITE_KEY`) are public and live in the Pages project, not in Railway.

### Migration baseline and reset rule

The migration chain starts at the frozen baseline `0001_scheduler_v1_baseline`.
It is a PostgreSQL 18 SQL schema dump. New migrations stack linearly in `backend/alembic/versions/`.
A database created on the old chain cannot upgrade to this baseline.
The new tree cannot resolve the removed revision identifiers.
Reset such a database before the new code deploys. The reset drops all application tables.
Run it only before real school use and with explicit reset authorization.
Preserve a backup and verify it before starting.

1. Stop job intake and stop API writes, solver, supervisor, and Beat processes.
2. Confirm that no generation job is active.
3. Keep the previous code deployed. Run `alembic downgrade base` with the migrator credential.
4. Verify that the old schema and the `alembic_version` revision are gone.
5. Deploy the new code. The normal `alembic upgrade head` pre-deploy command installs the baseline.
6. Verify schema, forced RLS, health, bootstrap, and release identity.
7. Restore application processes and verify generation and approval.

A fresh database needs no reset. Local downgrade and upgrade checks use the same revision tree.

### Required migration: Railway configuration as code

Railway sets 1 December 2026 as the end of support for existing `railway.json` config-as-code.
The `api`, `worker`, and `beat` services still depend on `backend/railway/*.json`.
Migrate their settings before that date, for example to `.railway/railway.ts` or to verified dashboard settings.
The migration must also cover the dashboard-only supervisor.
The repository does not contain `.railway/railway.ts` today.
This work is planned, not done. Confirm the current deadline in the Railway documentation before you start.

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
- Preserve existing mail records (Hostinger MX/SPF/DKIM, Resend `forms` records) during application DNS changes.
- Configure `TRUSTED_PROXY_IPS` only for provider networks that the operator trusts.
- On Railway, set `TRUSTED_PROXY_IPS=100.64.0.0/10`. This is the Railway proxy CGNAT range, seen in the production logs.

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
2. Compare `alembic current` with `alembic heads` for the deployed revision.
3. Confirm worker registration for `scheduler.v1.run_next_job`.
4. Confirm Beat schedules `members.run_scheduled_reconciliation`, `privacy.run_maintenance`, and `scheduler.v1.supervise`.
5. Check that API, worker, Beat, frontend, and migration reference the intended SHA.
   If queued jobs are old, treat that as an operational signal and verify the
   broker/dispatcher and worker on the same SHA; queued age alone does not
   justify failing a job.
6. Test contact delivery, authentication, invitations, schedule approval, occurrence decisions, and timesheets.
7. Test `/`, `/login`, `/register`, `/dashboard`, `/schedules`, `/my-schedules`, `/absences`, and `/cookies` after refresh.
8. Verify content negotiation on the Pages host with `curl`.
   - `curl -sI -H 'Accept: text/html;q=1,text/markdown;q=0.1' https://cronos.pt/` returns `text/html`.
   - `curl -sI -H 'Accept: text/markdown' https://cronos.pt/` returns `text/markdown`.
   - `curl -sI -H 'Accept: text/markdown;q=0' https://cronos.pt/` returns `text/html`.
   - Confirm GET and HEAD return the same media type for each header.
9. Record deployment IDs, backup IDs, restore evidence, and the previous rollback target.

## Source Map

- `backend/railway/api.json`
- `backend/railway/worker.json`
- `backend/railway/supervisor.json` (reference for the dashboard-configured supervisor)
- `backend/railway/beat.json`
- `backend/railway/bootstrap.json`
- `backend/app/config.py`
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
