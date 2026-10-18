# Cloud Operations

## Purpose

This document tells agents where Cronos runs, how to inspect each provider safely, and which operations need owner approval.

## Intended Reader

This document targets AI agents and operators who diagnose production or verify a deploy.

## Prerequisites

- Read the [Deployment Runbook](DEPLOYMENT_RUNBOOK.md) for the deployment contract.
- The `railway` and `gh` CLIs must be logged in on the machine. No Cloudflare CLI is installed.
- Provider dashboards need the owner's login. Agents cannot sign in for the owner.

## What the System Does

| Provider | Role | Identifier |
| :--- | :--- | :--- |
| GitHub | Source, CI, Deploy check | Repository `ORIOP25/Cronos` |
| Railway | API, worker, supervisor, Beat, PostgreSQL, Redis | Project `hopeful-enthusiasm`, environment `production` |
| Cloudflare | DNS for `cronos.pt`, Pages for the frontend | Apex `cronos.pt`; `www` redirects to the apex |
| Clerk | Identity, organizations, invitations, webhooks | Development instance for local and CI tests; production instance for `cronos.pt` |
| Hostinger | Mailbox `contacto@cronos.pt` | MX, SPF, and DKIM records on `cronos.pt` |
| Resend | Contact form delivery | Sender domain `forms.cronos.pt` |

Railway services: `api` (`api.cronos.pt`), `worker`, `scheduler-supervisor`, `beat`, `Postgres`, `Redis`.
`Postgres` runs with `max_connections` 100 from `postgresql.auto.conf`. Changing it needs `ALTER SYSTEM` and a PostgreSQL restart.
A second Railway project, `cronos-w11-isolated`, exists. Its purpose is undocumented; do not change it.

## Why the Behavior Exists

Every merge to `main` deploys to Railway and Cloudflare Pages.
Agents need a fast, read-only path to confirm what runs, and a clear line before any write.

## Components and Ownership

### Read-only inspection

| Question | Command or place |
| :--- | :--- |
| Served API revision and readiness | `curl https://api.cronos.pt/health/ready` |
| Served frontend revision | `curl https://cronos.pt/revision.json` |
| Deploy check result | `gh run list --workflow "Deploy check" --limit 5` |
| Railway topology | `railway status --json` |
| Railway logs | `railway logs --service <name> --lines 200` (add `--deployment` or `--build` for those logs) |
| Railway variable names | See [List variable names without values](#list-variable-names-without-values). |
| DNS records | `Resolve-DnsName cronos.pt -Type MX` on Windows, or `dig cronos.pt MX` elsewhere |
| Clerk, Cloudflare, Resend, Hostinger settings | Provider dashboard, read by the owner or with the owner present |

### List variable names without values

`railway variable list --json` and `--kv` print raw secret values. Never print them into a transcript or log.
Pipe the output so only names appear:

```bash
railway variable list --service api --json | node -e "let d='';process.stdin.on('data',c=>d+=c).on('end',()=>console.log(Object.keys(JSON.parse(d)).sort().join('\n')))"
```

### Configuration per process

| Process | Local source | Production source |
| :--- | :--- | :--- |
| `backend` (API) | Compose shared environment plus `backend/.env` | Railway `api` variables |
| `worker`, `scheduler-supervisor` | Compose shared environment plus `backend/.env` | Railway service variables |
| `beat` | Compose shared environment only | Railway `beat` variables |
| Frontend | Root `.env` (`VITE_*` build arguments) | Cloudflare Pages build variables |

Locally, Beat does not load `backend/.env`. It only publishes tasks; the workers execute them with their own secrets.
Beat imports no task module. `backend/app/scheduler_v1_worker.py` imports the member and privacy tasks that the solver worker executes, and the supervisor imports only `backend/app/scheduler_recovery_worker.py`.
In production, `Settings` validation runs in every process, so all four backend services need the production values.
The [Deployment Runbook](DEPLOYMENT_RUNBOOK.md#secrets-and-environment) lists the required names.

## Data or Request Flow

1. Merge to `main`.
2. Railway rebuilds the backend services when `backend/` changed. Cloudflare Pages rebuilds the frontend.
3. The `Deploy check` workflow waits up to 20 minutes for the expected revision.
4. It checks readiness, revision, `/`, and `/login` in Chromium.

The Deploy check proves the API, PostgreSQL, Redis, the site, and the login page.
It does not prove solver execution, supervisor recovery, member reconciliation, or privacy maintenance.
For those, read the service logs:

| Process | Evidence |
| :--- | :--- |
| `worker` | `railway logs --service worker` shows `scheduler_v1_phase_*` events after a generation. |
| `scheduler-supervisor` | `railway logs --service scheduler-supervisor` shows the `scheduler.v1.supervise` task every 60 seconds. |
| `beat` | `railway logs --service beat` shows the three periodic schedules being sent. |

## Contracts and Invariants

Read-only inspection needs no approval.
These operations need explicit owner approval each time:

- Changing, adding, or deleting Railway, Cloudflare, Clerk, Resend, or Hostinger settings or variables.
- Changing DNS records. Always preserve the Hostinger MX, SPF, and DKIM records and the Resend `forms` records.
- Redeploying, restarting, or scaling a production service outside a normal merge.
- Any production database write, reset, restore, or migration outside the API pre-deploy step.
- Creating or revoking provider keys or tokens.

Other rules:

- Never use a live Clerk key (`sk_live_`, `pk_live_`) in local runs or tests.
- Never copy secret values into Git, documents, pull requests, or chat.
- Report external state as observed with a date. Do not present a repository file as proof of provider configuration.

## States and Transitions

`merged` -> `Railway and Pages build` -> `Deploy check running` -> `Deploy check passed` or `failed`.
On failure, read the workflow errors, then the Railway build and deploy logs, before you change anything.

## Failure Modes

| Symptom | First check |
| :--- | :--- |
| Deploy check waits for the revision | `railway logs --service api --build` for a failed build. A frontend-only merge keeps the previous API revision. |
| Readiness `503` | PostgreSQL and Redis service state in `railway status --json`. |
| Contact form fails | Resend sender authentication for `forms.cronos.pt`, then `RESEND_API_KEY` presence on `api` (names only). |
| Invitations fail | Clerk production instance webhooks and `CLERK_WEBHOOK_SECRET` presence (names only). |
| Mail stops arriving at `contacto@cronos.pt` | MX, SPF, and DKIM records still point to Hostinger. |

### Known open items

These items were observed on 2026-10-14 and are not resolved. Re-verify them before you rely on them.

- Railway ends support for existing `railway.json` config-as-code on 1 December 2026. See the [Deployment Runbook](DEPLOYMENT_RUNBOOK.md#required-migration-railway-configuration-as-code).
- The `scheduler-supervisor` settings live only in the Railway dashboard. Compare them with `backend/railway/supervisor.json`.
- Railway showed a warning on `Postgres` without a cause in the consulted view.
- Backup policy, restore evidence, log retention, and alerts are unverified.
- The Cloudflare API returned `403` to the available token. Cloudflare state is readable only through the dashboard or public endpoints.
- Locally, the API reports revision `unknown` because no `DEPLOYED_REVISION` is set.

Resolved on 2026-10-14: the owner removed the unused shared variables `SECRET_KEY`, `SOLVER_ENGINE_VERSION`, and `SOLVER_V2_ROLLING_WEEKS` in the Railway dashboard.

## Verification Procedure

1. Run `curl https://api.cronos.pt/health/ready` and confirm `ok` and the expected revision.
2. Run `curl https://cronos.pt/revision.json` and confirm the expected revision.
3. Run `gh run list --workflow "Deploy check" --limit 1` and confirm success.
4. For a backend process change, read that service's logs for the evidence above.

## Source Map

- `.github/workflows/deploy-check.yml`
- `scripts/verify-production-deploy.mjs`
- `frontend/scripts/verify-production-browser.mjs`
- `backend/railway/*.json`
- `docker-compose.yml`
- `backend/app/config.py`

## Related Documents

- [Deployment Runbook](DEPLOYMENT_RUNBOOK.md)
- [Observability and Recovery](OBSERVABILITY_AND_RECOVERY.md)
- [Local Runtime](LOCAL_RUNTIME.md)
- [Command Reference](../00_getting_started/COMMAND_REFERENCE.md)
