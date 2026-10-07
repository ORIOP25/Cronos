# Testing and CI

The [production-browser acceptance PRD](REAL_BROWSER_TESTING_PLAN.md) and its [four-part WBS](REAL_BROWSER_TESTING_WBS.md) describe the agreed redesign.
The [implementation record](REAL_BROWSER_TESTING_IMPLEMENTATION.md) lists which parts are already proven and which dependencies remain.
This guide describes the implemented behaviour.

Cronos runs backend, frontend, and end-to-end suites through one root runner.
GitHub Actions enforces the same gates on every push and pull request.

## Quick start

The supported entry point is the root runner:

```powershell
node scripts/test.mjs setup --scope all
node scripts/test.mjs doctor --profile all
node scripts/test.mjs fast --scope all
node scripts/test.mjs integration
node scripts/test.mjs e2e --project public
node scripts/test.mjs capacity-smoke
node scripts/test.mjs acceptance
node scripts/test.mjs all --scope all
node scripts/test.mjs benchmark --profile fast
node scripts/test.mjs campaign --manifest backend/tests/scheduler_lab/manifest.json
```

The runner exposes `setup`, `doctor`, `fast`, `integration`, `e2e`, `capacity`, `capacity-smoke`, `acceptance`, `all`, `benchmark`, and `campaign`. The `e2e` command accepts `--project public|auth|app|provider|faults|capacity`. E2E starts its own stack on port `5174`.

`fast` never starts Docker or installs packages. Forwarded arguments are accepted only after `--` by `fast` and `integration`, and are passed as separate process arguments. Run artefacts are written to `.test-artifacts/`.

## Backend suites

| Suite | Location | Execution |
| :--- | :--- | :--- |
| Unit | `backend/tests/unit/` | no database or external network; loopback-only socket policy |
| Transactional integration | `backend/tests/integration/transactional/` | real PostgreSQL/Redis stack |
| Committed integration | `backend/tests/integration/committed/` | real PostgreSQL/Redis stack, xdist=4 |
| Contracts | `backend/tests/contracts/` | real PostgreSQL/Redis stack, serial |

Suite membership is structural. PostgreSQL migrations always run through Alembic; SQLite and `metadata.create_all` are not valid substitutes. The runner creates `cronos_test_gw0` through `cronos_test_gw3` for xdist and uses separate migrator/runtime credentials. Destructive operations are accepted only for exact test database names.

Integration runs with `-n 4 --dist=loadscope`. Contracts run serially with rate limiting enabled. The coverage gate requires 70 percent overall, 100 percent for `app/scheduler/domain/constraint_policy.py`, and 90 percent for `app/scheduler/domain/candidate_validation.py`. Any skipped test fails the run.

## Frontend suites

The 48-class correctness test uses the production 900-second safety budget and stops at the first complete candidate.
It validates curricular coverage and completion dates. Short optimization deadlines must not make correctness depend on host load.

Vitest is configured in `frontend/vitest.config.js` with isolated `node` and `dom` projects, thread pooling, MSW server setup and strict unhandled-request failures. Coverage uses V8 and enforces thresholds of 45 percent statements, 40 percent branches, 35 percent functions, and 45 percent lines. React interactions that cross async boundaries use Testing Library `user-event`.

Playwright is configured in `frontend/playwright.config.js`. The `setup` project feeds `public`, `auth`, and `auth-state`. The `app` project depends on `auth-state`, the `provider` project depends on `app`, and the `faults` project depends on `app` and `provider`. The `capacity` project runs only when `CAPACITY_ENABLED=1`. The `acceptance` project matches `frontend/e2e/acceptance/*.spec.js`, uses the installed Chrome channel, one worker, no setup dependency and no test credentials. The `app`, `provider`, and `faults` projects use one worker because they mutate shared E2E state. Retries are disabled; traces are retained on failure and screenshots are captured on failure.

All projects use the shared `E2E_BASE_URL`, which defaults to `http://127.0.0.1:5174`.
This address matches the owned Docker stack's IPv4 binding and avoids other processes listening on `localhost` over IPv6.
The runner supplies `http://localhost:5173` for an external stack.

After sign-in, the E2E helper waits for the loaded Clerk session and expected identity before activating the organization.
This prevents organization activation during a sign-in navigation while the browser reloads Clerk.

## CI gates

The owned local E2E stack builds the frontend `ci` target, which permits the dedicated Clerk test domain.
Its Nginx application routes include `/imports`. Production keeps its runtime browser policy.

GitHub Actions keeps backend, frontend and E2E in separate jobs. The backend job has a 45-minute timeout, the frontend job has a 20-minute timeout, and the E2E job has a 30-minute timeout.

Backend gates use Python 3.14 with `postgres:16` and `redis:7` services. The job provisions `cronos_migrator`, `cronos_app`, and `cronos_auth_definer`, installs locked dependencies with `--require-hashes`, runs `pip check` and `pip-audit`, checks Ruff formatting and linting, runs Alembic upgrade/check/downgrade/upgrade, runs the database integrity audits, runs unit then integration then contract tests, applies the coverage gates, and builds the hardened runtime image.

Frontend gates use Node 24 with `npm ci --ignore-scripts`, `npm run audit:production`, and `npm run verify`. The job also runs `node scripts/loc-report.mjs` against `documentation/08_security_quality/loc-baseline.json`.

E2E uses `docker-compose.ci.yml`. The job prepares dedicated Clerk test identities, runs `node scripts/test.mjs e2e` and `node scripts/test.mjs capacity-smoke`, sanitizes `.test-artifacts/` and Playwright output, and always cleans Compose resources and revokes Clerk invitations. The E2E job is skipped for Dependabot.

Skipped tests, retries, missing artifacts and migration drift are release failures. E2E credentials must be dedicated Clerk test identities; they are not generated or persisted by local test setup.

## Production acceptance

`node scripts/test.mjs acceptance` is the entry point for the real-browser campaign against `https://cronos.pt`.
It runs the reporter-backed Playwright `acceptance` project in Chrome, verifies the Gmail mailboxes and the deployment revisions before and after the run, protects every binary artifact with the campaign key, and evaluates the case matrix with `frontend/e2e/utils/acceptance-policy.js`.
The runner exits `3` while any campaign dependency is missing, and writes the missing names to `.test-artifacts/<run>/acceptance-plan.json`.
The result document is `.test-artifacts/<run>/acceptance-result.json`; only `validated` for the complete matrix can certify production.

The campaign is fail-closed: a failed or missing reporter, an unprotected artifact, a revision mismatch, an unfinished cleanup or a retried case cannot produce green.
Cleanup is supplied by the administrative wrapper (`backend/scripts/cleanup_e2e_run.py`) through `E2E_CLEANUP_RESULT`; while it is absent the campaign is `failed`.
The legacy local `e2e` command remains a diagnostic until each substituted group has real proof.

`.github/workflows/acceptance.yml` runs the same command on the `main` SHA, serialized without automatic cancellation, and uploads sanitized artifacts on success and failure.
It activates only when the `E2E_ACCEPTANCE_ENABLED` repository variable is `true` and the documented `E2E_*` secrets and variables exist; PRs never receive them.
The real campaign still requires the two Gmail OAuth consents, the Cloudflare and Railway read tokens, the browser/admin credentials, the signed persistent registry and the protected secret registry.
Isolated worker recovery is verified with real PostgreSQL, Redis, a real broker message and an owned Celery worker process in `backend/tests/integration/committed/test_worker_process_recovery.py`.

## References

- [Contributing Guidelines](../00_getting_started/CONTRIBUTING.md)
- [Security and Tenant Isolation](SECURITY_AND_TENANT_ISOLATION.md)
- [Local Runtime](../09_ops_observability/LOCAL_RUNTIME.md)
- [Real browser testing WBS](REAL_BROWSER_TESTING_WBS.md)
- Workflows: `.github/workflows/ci.yml`, `.github/workflows/acceptance.yml`
