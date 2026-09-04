# Testing and CI

## Quick start

The supported entry point is the root runner:

```powershell
node scripts/test.mjs setup --scope all
node scripts/test.mjs doctor --profile all
node scripts/test.mjs fast --scope all
node scripts/test.mjs integration
node scripts/test.mjs e2e --project public
node scripts/test.mjs all --scope all
node scripts/test.mjs benchmark --profile fast
```

`fast` never starts Docker or installs packages. Forwarded arguments are accepted only after `--` by `fast` and `integration`, and are passed as separate process arguments. Run artefacts are written to `.test-artifacts/`.

## Backend suites

| Suite | Location | Execution |
| :--- | :--- | :--- |
| Unit | `backend/tests/unit/` | no database or external network; loopback-only socket policy |
| Transactional integration | `backend/tests/integration/transactional/` | real PostgreSQL/Redis stack |
| Committed integration | `backend/tests/integration/committed/` | real PostgreSQL/Redis stack, xdist=2 |
| Contracts | `backend/tests/contracts/` | real PostgreSQL/Redis stack, serial |

Suite membership is structural. The former fixture/marker collection classifier and its tests were removed. PostgreSQL migrations always run through Alembic; SQLite and `metadata.create_all` are not valid substitutes. The runner creates `cronos_test_gw0` and `cronos_test_gw1` for xdist and uses separate migrator/runtime credentials. Destructive operations are accepted only for exact test database names.

## Frontend suites

Vitest is configured in `frontend/vitest.config.js` with isolated `node` and `dom` projects, thread pooling, MSW server setup and strict unhandled-request failures. Coverage uses V8 and enforces the configured thresholds. React interactions that cross async boundaries use Testing Library `user-event`.

Playwright is configured in `frontend/playwright.config.js` with five independent projects: `public`, `auth`, `app`, `provider` and `faults`. Only the technical setup project is a dependency. Retries are disabled; traces are retained on failure and screenshots are captured on failure.

## CI gates

GitHub Actions keeps backend, frontend and E2E in separate jobs. Backend gates include locked dependency verification, `pip check`, `pip-audit`, Ruff, Alembic upgrade/check/downgrade/upgrade, database audits, unit/integration/contracts, coverage and the hardened image build. Frontend gates include `npm ci`, production audit, ESLint, Knip, Vitest coverage and build. E2E validates dedicated Clerk test identities, runs the independent Playwright projects and always uploads reports and cleans Compose resources.

Skipped tests, retries, missing artifacts and migration drift are release failures. E2E credentials must be dedicated Clerk test identities; they are not generated or persisted by local test setup.

## Baseline evidence

See [TEST_BASELINE_WBS.md](TEST_BASELINE_WBS.md), [TEST_BASELINE_REPORT.md](TEST_BASELINE_REPORT.md), and the JSON baseline/disposition files in this directory.

## References

- [Contributing Guidelines](../00_getting_started/CONTRIBUTING.md)
- [Security and Tenant Isolation](SECURITY_AND_TENANT_ISOLATION.md)
- [Local Runtime](../09_ops_observability/LOCAL_RUNTIME.md)
- Workflow: `.github/workflows/ci.yml`
