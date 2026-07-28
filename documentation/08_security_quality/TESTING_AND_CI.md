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
| `frontend/` | Vitest | React components, custom hooks, utilities | Whole-source component coverage |
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
1. **Lint and Syntax Check**: Execute `ruff check` for backend and `eslint` for frontend.
2. **Build Application Images**: Build backend and frontend container images once.
3. **Database Role Provisioning**: Run `docker compose --profile maintenance run --rm provision-db`.
4. **Database Migration Execution**: Run `docker compose --profile maintenance run --rm db-maintenance`.
5. **Start Runtime Stack**: Launch `db`, `redis`, `backend`, and `frontend` Nginx containers.
6. **Backend and Database Audits**: Verify `alembic check` and execute `python backend/scripts/audit_triggers.py`.
7. **Frontend Unit Tests**: Run Vitest component test suite.
8. **Playwright E2E Tests**: Run Playwright against the Nginx frontend container.
9. **Compose Project Teardown**: Execute `docker compose down -v --remove-orphans`.

## Contracts and Invariants
- Backend tests must execute against a dedicated test database name containing `test` or `ci`.
- CI builds fail automatically if coverage falls below configured threshold.
- CI workflows must tear down Compose projects cleanly upon job completion.

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
