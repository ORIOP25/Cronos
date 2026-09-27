# Scheduler v1 — W00 local inventory and evidence

Date: 23 September 2026. Branch: `codex/scheduler-v1-revamp`.
Starting commit: `facd1d93bead7fc6ed481de6761644afd2e0be81`.

This is a work record, not acceptance of W00 or a release gate. The v1 plan,
technical specification, and WBS are the target contracts. Current code is
only the baseline being replaced.

Review 24 September 2026: W00 is not integrally accepted. External auto-deploy
settings remain undocumented by the repository and the E2E identities remain
unconfigured. See the correction WBS and its work record.

## W00.1 — Consumers and replacement contracts

| Consumer | Current contract | v1 destination |
| :--- | :--- | :--- |
| `app/api/v1/endpoints/scheduler.py` and `frontend/src/features/scheduling/data.js` | Status, generate, job, draft, diff, approve, reject, cancel | Manual, idempotent request; typed result; revision checked proposal and approval |
| `app/services/scheduler_*` and `app/scheduler/` | Complete, near/far and repair paths with module indexes in blocks | CompleteGeneration and AdaptiveRecovery over exact minute demand; independent validation |
| `app/models.py`, `alembic/versions/` | School year state, jobs, drafts, active blocks, recovery links and module ledger | New relational baseline with revisions, versions, slices, debt and allocations |
| `app/services/schedule_service.py` | Maps resolve one active module per lesson | Multiple projected module slices per future lesson |
| `app/services/lesson_log_service.py` and `occurrence_service.py` | Execution and cancellation use one planned/executed module ID | Audited execution slices and debt reconciliation without duplicate credit |
| `app/services/timesheet_service.py` | Reads lesson and occurrence totals | Keep physical teaching time distinct from curricular credit |
| `frontend/src/pages/Schedules.jsx` | Generation and approval UI uses legacy status fields | Queue, eligibility, proposal quality, separate physical and modular diff |
| `frontend/src/pages/ClassDetails.jsx`, `Occurrences.jsx`, `MySchedules.jsx`, `components/LessonLogModal.jsx` | Progress, occurrences, maps and lesson logging use legacy module semantics | Exact minute projections and executed slices |
| `scripts/test.mjs`, `docker-compose.test.yml`, `.github/workflows/ci.yml` | Host Python runner, isolated PostgreSQL/Redis test stack and CI checks | Container capable local runner and v1 campaigns with reproducible evidence |

## W00.2 — Local execution boundary

Docker Desktop reports 8 logical CPUs and 16,605,478,912 bytes of memory.
Docker Engine is 29.8.0 and Compose is 5.5.1. The built local test image is
`cronos-backend-test:local` at
`sha256:8ecfee9d6f78e29624c9226f208aaff7f0888a149dde648b0860f67ff1f5ad44`.
It runs Python 3.14.7 with the locked development dependencies.

The existing `cronos` development stack has backend, worker, beat, frontend,
PostgreSQL, and Redis running. Its persistent volumes are
`cronos_postgres_data_v16_baseline` and `cronos_redis_data`.
The test Compose file uses a separate project and a temporary PostgreSQL
filesystem. No reset or mutation of the development volumes was performed.

## W00.3 — Deployment boundary

`.github/workflows/ci.yml` has checks on push and pull request, with no deploy
job. Railway service configurations exist under `backend/railway/`.
An external Railway or Cloudflare GitHub auto deploy setting cannot be proven
from this repository. Do not push the branch before checking those settings.
No remote test, reset, or deployment has run in this work record.

## W00.4 — Current checks and environment issues

| Check | Result |
| :--- | :--- |
| `node --test scripts/test.test.mjs` | 17 passed |
| `node scripts/test.mjs setup --scope backend` | Failed: `.venv` points to removed host Python 3.12 |
| `node scripts/test.mjs doctor --profile fast` | Failed: `python.exe` unavailable |
| `node scripts/test.mjs doctor --profile all` | Failed: host Python unavailable; E2E Clerk test key not configured |
| Backend unit tests in the locked Docker `ci` image | 399 passed; JUnit at `.test-artifacts/w00/backend-unit.xml` |
| `node scripts/test.mjs setup --scope backend` after runner correction | Passed; rebuilt locked Docker `ci` image |
| `node scripts/test.mjs doctor --profile fast` | Passed with Python 3.14.7 in Docker |
| `node scripts/test.mjs doctor --profile integration` | Passed |
| `node scripts/test.mjs fast --scope backend` | 444 passed; JUnit in `.test-artifacts/1790179759481-1864/` |
| `node scripts/test.mjs integration -- -k scheduler_state_service` | 9 integration and 47 contract tests passed; JUnit in `.test-artifacts/1790179830424-11916/` |

The original runner's Python 3.12 check conflicted with the Python 3.14.7
image and CI. The runner now uses the locked Docker image on Windows. Its
integration commands join only the temporary Compose test network. The runner
removed that project's containers and network after the integration check.

## W00.5 — Laboratory safety

Use `.test-artifacts/` for local manifests, outcomes, and logs. Use only the
Compose test project with a `cronos_test_db` target for database tests.
Record seeds and image digests. Keep credentials and personal data out of
artifacts. Do not run production provider tests until the W12 local gate is
accepted. A short smoke run and its files belong under `.test-artifacts/w00/`.

## State

W00 remains **in validation**. E2E test identities are not configured in this
shell, and the repository does not show external auto deploy settings. The
backend unit, PostgreSQL integration, and contract baselines are reproducible
through the runner. Do not push or attempt remote validation until the deploy
settings are checked.
