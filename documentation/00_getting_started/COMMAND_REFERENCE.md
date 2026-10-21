# Command Reference

## Purpose

This document is the single authority for how to set up, verify, run, and inspect Cronos.
Other documents and skills link here instead of copying commands.

## Intended Reader

This document targets AI agents and engineers who change or verify the repository.

## Prerequisites

- Node 24, npm 11, Docker 29, and Docker Compose 5.
- Python 3.14 on Linux and macOS. On Windows the runner executes Python inside the `cronos-backend-test:local` image.
- Run every command from the repository root unless a row names another directory.

## What the System Does

The root runner `scripts/test.mjs` owns test execution.
It resolves Python, npm, and Docker for the current platform.
It writes one run report per invocation under `.test-artifacts/`.
Direct `pytest` or `npm` calls skip these protections. Use them only where this document names them.

## Why the Behavior Exists

On Windows, `python` is often missing from `PATH` and a global `npm` can be incomplete.
The runner removes that ambiguity, isolates test databases, and records revision and timings.
One reference prevents agents from following stale procedures.

## Components and Ownership

### Command categories

| Category | Effect | Approval |
| :--- | :--- | :--- |
| Diagnosis | Reads versions and files only. | None. |
| Preparation | Installs locked dependencies or builds local images. | None. |
| Isolated tests | Start and remove their own Compose project `cronos-test-<token>`. | None. |
| Local maintenance | Changes the local development database or containers. | None, except `docker compose down`. |
| Production | Reads or changes cloud providers. | Read-only is free. Any write needs explicit user approval. |

### Runner commands

| Task | Command | Prerequisites | Effects | Proves |
| :--- | :--- | :--- | :--- | :--- |
| Check tools | `node scripts/test.mjs doctor --profile fast` | None | None | Node 24, npm 11, Python 3.14, and installed dependencies. |
| Check Docker and E2E inputs | `node scripts/test.mjs doctor --profile all` | None | None | Also Docker 29, Compose 5, and the E2E environment variables. |
| Prepare | `node scripts/test.mjs setup --scope all` | Docker on Windows | Builds `cronos-backend-test:local` on Windows, or creates `backend/.venv` elsewhere. Runs `npm ci --ignore-scripts` and installs Playwright Chromium. | Locked dependencies install. |
| TDD loop | `node scripts/test.mjs fast --scope backend\|frontend\|all [-- args]` | `setup` | None | `backend/tests/unit/` with sockets disabled, and the Vitest `node`, `dom`, and `dom-network` projects. |
| Backend database tests | `node scripts/test.mjs integration [-- args]` | Docker | Starts a unique test stack on random loopback ports, then removes it. | `backend/tests/integration/` with four workers, then `backend/tests/contracts/`. |
| Backend CI gate | `node scripts/test.mjs critical --scope backend` | PostgreSQL and Redis at the URLs in `DATABASE_URL`, `MIGRATION_DATABASE_URL`, `TEST_DATABASE_URL`, and `REDIS_URL` | Writes `.coverage.*` files in `backend/` | The `unit` and `db` groups of `backend/tests/critical_manifest.json` and their coverage thresholds. |
| Browser journeys | `node scripts/test.mjs e2e [--project <name>]` | Clerk test keys and reserved test emails (see below); free port `5174` | Builds images, starts a full test stack on `127.0.0.1:5174`, prepares Clerk test state, then removes the stack. | Playwright projects `public`, `auth`, `app`, `isolated`, `readonly`, `provider`. |
| Capacity smoke | `node scripts/test.mjs capacity-smoke` | Same as `e2e` | Same as `e2e` | A 30-second bounded capacity profile. |
| Full corpus | `node scripts/test.mjs all --scope all` | Docker | Starts and removes a test stack | See [What each profile proves](#what-each-profile-proves). |
| Timing baseline | `node scripts/test.mjs benchmark --profile fast` | `setup` | Repeats a profile | Median durations only. |

Pass extra arguments only after `--`, and only to `fast`, `integration`, and `e2e`.
A filtered `integration` run (any argument after `--`) skips `backend/tests/contracts/`. The unfiltered run and CI run them.
`e2e` forwards the arguments to Playwright, for example `-g <test title>` to run one scenario.
With `--scope all`, `fast` forwards the same arguments to pytest and Vitest. Use one scope when you forward arguments.

Examples:

```bash
node scripts/test.mjs fast --scope backend -- -k timesheet
node scripts/test.mjs fast --scope frontend -- src/test/weekSubmission.test.js
node scripts/test.mjs integration -- -k occurrences
node scripts/test.mjs e2e -- -g "availability matrix"
```

`critical` is designed for CI, where services and credentials come from the workflow.
On Windows the runner starts pytest inside the test image without the test-stack network.
Use `integration` for local database proof.

The E2E inputs are `VITE_CLERK_PUBLISHABLE_KEY` (`pk_test_`), `CLERK_SECRET_KEY` (`sk_test_`), `E2E_CLERK_ADMIN_EMAIL`, and `E2E_CLERK_TEACHER_EMAIL`.
Every email must end with `+clerk_test@example.com`.
Never use live Clerk keys for tests.
The runner reads them from the shell, then fills any missing Clerk input from `~/.cronos/e2e.env` (or the file named by `CRONOS_E2E_ENV_FILE`).
That one file serves every worktree, because each worktree has its own gitignored `.env`.
Write plain `NAME=value` lines. `loadE2eEnvFile` in `scripts/test.mjs` loads only `CLERK_SECRET_KEY`, `VITE_CLERK_PUBLISHABLE_KEY`, and `E2E_CLERK_*` names.

### Frontend package scripts

Run these inside `frontend/`.

| Script | Runs |
| :--- | :--- |
| `npm test` | All Vitest projects once. |
| `npm run test:critical:coverage` | The critical Vitest selection in `src/test/criticalSelection.js` with coverage floors. |
| `npm run verify:critical:fast` | The `frontend` CI job: legal contract, marketing build tests, edge worker test, asset audit, and critical coverage. |
| `npm run verify:checks` | ESLint, both Knip runs, legal contract, marketing build tests, repository script tests, edge worker test, and asset audit. |
| `npm run verify` | `verify:checks`, full Vitest coverage, and the production build. |
| `npm run audit:production` | Production dependency audit. |
| `npm run build` | Vite build, marketing pages, and `revision.json`. |

### Backend checks outside the runner

CI runs these steps in the `backend` job before the critical gate.
Run them locally through the maintenance container, never with a host-side `alembic` against an unknown database.

| Check | Local command |
| :--- | :--- |
| Format and lint | Inside the test image or `backend/.venv`: `ruff format --check .` and `ruff check .` in `backend/` |
| Migration drift | `docker compose --profile maintenance run --rm db-maintenance alembic check` |
| Trigger audit | `docker compose --profile maintenance run --rm db-maintenance sh -c 'DATABASE_URL="$MIGRATION_DATABASE_URL" python -m scripts.audit_triggers'` |
| Integrity audit | `docker compose --profile maintenance run --rm db-maintenance sh -c 'DATABASE_URL="$MIGRATION_DATABASE_URL" python -m scripts.audit_database_integrity'` |

Alembic in `db-maintenance` connects through `MIGRATION_DATABASE_URL` with the `cronos_migrator` role.
The audits read `DATABASE_URL`, which is the RLS-bound `cronos_app` role. CI therefore sets `DATABASE_URL="$MIGRATION_DATABASE_URL"` for them, and so do the commands above.

## Data or Request Flow

### Local stack

1. Copy `.env.example` to `.env` and `backend/.env.example` to `backend/.env`. Use test provider values.
2. Run `docker compose build backend`. `db-maintenance` reuses the `cronos-backend:local` image and cannot build it.
3. Run `docker compose --profile maintenance run --rm provision-db` on a new database or after a password rotation.
4. Run `docker compose --profile maintenance run --rm db-maintenance` to apply migrations.
5. Run `docker compose up -d --build`.
6. Check `http://127.0.0.1:8000/health/live` and `http://127.0.0.1:8000/health/ready`.
7. Open `http://localhost:5173`.

After a frontend change, run `docker compose up -d --build frontend` so the local container serves the new build.

### Local stack in a worktree

`docker-compose.yml` sets the project name `cronos` and fixed ports. One local stack runs at a time, and it serves the last checkout that built it.

1. Copy `.env` and `backend/.env` from the main checkout into the worktree. The main checkout is the first line of `git worktree list`. Git ignores these files. Never commit or print them.
2. Run `docker compose up -d --build` from the worktree that holds the change.
3. Tell the owner which branch and commit the stack serves (`git log -1 --oneline`). The local `revision.json` does not identify the commit.
For Vite hot reload, run `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build`.

### Verification by change type

Run the narrowest proof during the TDD cycle. Open a pull request for the full CI proof.
`fast --scope backend` skips the tests marked `slow_solver`. The `e2e-runtime` CI job runs them. Pass `-m slow_solver` only to diagnose a failure of that job.

| Change | Local proof before the pull request |
| :--- | :--- |
| Documentation or skills only | Link check (see [Verification Procedure](#verification-procedure)) and `git diff --check`. |
| Backend pure logic | `fast --scope backend -- -k <area>`. |
| Backend endpoint, service, or query | `fast --scope backend`, then `integration -- -k <area>`. |
| Migration | `integration`, then the migration drift and audit checks above. |
| Tenant data or RLS | `integration`. Keep `test_rls_database_policies.py` and the tenant isolation tests green. |
| Frontend component or hook | `fast --scope frontend -- <test file>`, then `npm run verify:checks`. |
| Frontend route or user journey | The above, then `e2e --project <name> -- -g <test title>` for the changed scenario when Clerk test inputs exist. Run the whole project once before the pull request. |
| Scheduler solver | `fast --scope backend -- -k scheduler`. CI runs the `slow_solver` test in `e2e-runtime`. |
| Scheduler jobs, proposals, or API | `integration -- -k scheduler`. CI does not run `test_scheduler_v1_api.py` or `test_scheduler_v1_lifecycle.py`. |
| Priority benchmark | In the backend test image: `python -m app.scheduler.lab.priority_bench --scenario scale-3 --profile recommended --repetitions 3 --output /workspace/.test-artifacts/priority-bench.json`. Repeat `--scenario` and `--profile` for more cases; use `--scenario pilot-48` for the sample CSV pilot, `--scenario pilot-real` for the realistic pilot school (`lab/realistic_pilot.py`) or `--input /workspace/.test-artifacts/snapshot.json` for a JSON bundle. Keep exported schedules and input bundles under `.test-artifacts/` or another local path, outside source control. |
| CI, runner, or scripts | `npm run test:scripts` in `frontend/`. |

### Inspect without changing state

| Question | Command |
| :--- | :--- |
| Local services | `docker compose ps` |
| Local logs | `docker compose logs --tail 200 <service>` |
| Worker tasks | `docker compose exec worker celery -A app.celery_worker.celery_app inspect registered` |
| Production health and revision | `curl https://api.cronos.pt/health/ready` |
| Frontend revision | `curl https://cronos.pt/revision.json` |
| CI status of a pull request | `gh pr checks <number>` |
| Latest runs on `main` | `gh run list --branch main --limit 5` |

The [Cloud Operations](../09_ops_observability/CLOUD_OPERATIONS.md) guide covers Railway, Cloudflare, Clerk, Hostinger, and Resend.

## Contracts and Invariants

- Tests run only against `cronos_test_db`, `cronos_ci_db`, or the `cronos_test_gw<N>` and `cronos_ci_gw<N>` worker databases. `backend/tests/db.py` enforces this.
- `fast` never starts Docker or installs packages.
- Every isolated stack uses a new project name and generated passwords.
- Only one E2E run can use port `5174` at a time. Integration runs can run in parallel.
- Never run `docker compose down -v` or prune Docker volumes.
- Never point tests at production or at live provider keys.

## States and Transitions

`doctor` -> `setup` -> `fast` (TDD loop) -> `integration` or `e2e` (when relevant) -> pull request CI -> merge -> `Deploy check`.

## What each profile proves

| Profile | Includes | Excludes |
| :--- | :--- | :--- |
| `fast` | Backend unit corpus without the `slow_solver` tests. Vitest without coverage. | Database, Redis, coverage gates, lint, the 48-class CP-SAT test. |
| `critical` | The backend CI test selection with coverage. | Ruff, Alembic drift, audits, the full corpus. |
| `all --scope backend` | Ruff, full unit, integration, and contract corpus with coverage; 70% overall; 100% for `constraint_policy.py`. | Alembic drift and downgrade, trigger and integrity audits, `pip-audit`, and the 90% gate for `candidate_validation.py`. |
| `all --scope frontend` | ESLint, both Knip runs, marketing build tests, asset audit, full coverage, build, and production audit. | Legal contract, repository script tests, and the edge worker test. |
| `npm run verify` | Every frontend check except the production audit. | Backend and E2E. |
| CI on a pull request | `backend`, `frontend`, `e2e-runtime`, and `e2e-browser` jobs. | The full backend corpus. |

No local command equals CI. State the exact command when you report a verification result.
Never write "all tests passed" without naming the profile.

## Failure Modes

| Exit code | Meaning |
| :--- | :--- |
| `0` | Success. |
| `1` | A test, gate, or command failed. |
| `2` | Invalid runner arguments. The help text follows. |
| `3` | Invalid environment, for example a wrong tool version, missing E2E input, or busy port. Run `doctor`. |

- `E2E port 5174 is already in use`: another E2E run or local service owns the port. Wait or stop that run.
- A missing `cronos-backend:local` image fails `db-maintenance`. Run `docker compose build backend`.

## Verification Procedure

Validate the relative links of changed Markdown files:

```bash
node -e "const fs=require('fs'),p=require('path');let bad=0;for(const f of process.argv.slice(1)){const t=fs.readFileSync(f,'utf8');for(const m of t.matchAll(/\]\(([^)#\s]+)(#[^)]*)?\)/g)){const l=m[1];if(/^[a-z]+:/i.test(l))continue;if(!fs.existsSync(p.resolve(p.dirname(f),l))){bad++;console.log(f+': '+l)}}}process.exit(bad?1:0)" AGENTS.md README.md documentation/00_getting_started/COMMAND_REFERENCE.md
```

Pass every changed Markdown file as an argument.

## Source Map

- `scripts/test.mjs`
- `frontend/package.json`
- `backend/tests/critical_manifest.json`
- `backend/tests/db.py`
- `frontend/playwright.config.js`
- `docker-compose.yml`, `docker-compose.dev.yml`, `docker-compose.test.yml`, `docker-compose.ci.yml`
- `.github/workflows/ci.yml`, `.github/workflows/deploy-check.yml`

## Related Documents

- [Contributing Guidelines](CONTRIBUTING.md)
- [Testing and CI](../08_security_quality/TESTING_AND_CI.md)
- [Local Runtime](../09_ops_observability/LOCAL_RUNTIME.md)
- [Cloud Operations](../09_ops_observability/CLOUD_OPERATIONS.md)
