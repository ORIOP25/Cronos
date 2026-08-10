# Testing and CI

## Purpose
This document details testing strategies, test suite organization, coverage requirements, and GitHub Actions CI pipelines.

## Intended Reader
This document targets QA engineers, backend developers, and DevOps engineers.

## Prerequisites
Read [Contributing Guidelines](../00_getting_started/CONTRIBUTING.md).

## What the System Does
Cronos maintains automated unit, integration, database contract, and end-to-end (E2E) test suites.

## Test Suites Summary Table

| Workspace | Test Tool | Scope | Minimum Coverage Target |
| :--- | :--- | :--- | :--- |
| `backend/` | Pytest | API endpoints, services, database models, RLS | **70% Code Coverage** |
| `frontend/` | Vitest | React components, hooks, and utilities | Coverage collected by `npm run verify` |
| `frontend/e2e/` | Playwright | Full browser E2E workflows | Critical path workflows |

## Running Test Suites

### Backend Unit and Integration Tests
```bash
cd backend
pytest tests/ -v
```

To run coverage reporting:

```bash
pytest tests/ --cov=app --cov-report=term-missing
```

### Frontend Component Tests
```bash
cd frontend
npm run test
```

To run frontend coverage:

```bash
npm run test:coverage
```

### Playwright E2E Tests
```bash
cd frontend
npx playwright test
```

## Continuous Integration (CI) Workflow Steps
1. **Backend Locks and Security**: Rebuild lock files, run `pip check`, and run `pip-audit` with recorded exceptions.
2. **Backend Static Checks**: Run Ruff format and lint checks.
3. **Migration Verification**: Upgrade, check drift, downgrade, and upgrade again.
4. **Database Audits**: Run trigger and integrity audits with the migrator role.
5. **Backend Tests**: Run non-Redis and Redis suites with combined branch coverage.
6. **Frontend Verification**: Run production audit, lint, Knip, coverage, build, and configuration stability checks.
7. **E2E Stack**: Build Compose services, provision roles, migrate, prepare Clerk state, and run Playwright.
8. **Release Build**: On semantic version tags, publish and attest the backend image.

## Contracts and Invariants
- Backend tests must execute against a dedicated test database name containing `test` or `ci`.
- CI builds fail automatically if coverage falls below configured threshold.
- E2E CI tears down its Compose project and volumes in an `always()` step.

## Failure Modes
- Destructive Test Prevention: Pytest fixture aborts if database URL does not contain `test` or `ci`.

## Verification Procedure
Execute local CI verification pipeline manually before pushing commits.

## Source Map
- Backend Tests: `backend/tests/`
- Frontend Tests: `frontend/src/test/`
- E2E Tests: `frontend/e2e/`
- CI Pipeline Spec: `docker-compose.ci.yml`, `.github/workflows/ci.yml`

## Related Documents
- [Contributing Guidelines](../00_getting_started/CONTRIBUTING.md)
- [Security and Tenant Isolation](SECURITY_AND_TENANT_ISOLATION.md)
- [Local Runtime](../09_ops_observability/LOCAL_RUNTIME.md)

## Lifecycle Regressions

Run webhook lifecycle and session bootstrap integration suites with the production database role before release.
