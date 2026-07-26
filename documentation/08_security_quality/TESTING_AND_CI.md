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
1. **Lint and Syntax Check**: Run `ruff check` (backend) and `eslint` (frontend).
2. **Backend Test Suite**: Execute Pytest with PostgreSQL database container.
3. **Database Migration Audit**: Verify `alembic check` for schema drift.
4. **Trigger Integrity Audit**: Execute `python backend/scripts/audit_triggers.py`.
5. **Frontend Build & Test**: Execute `npm run build` and Vitest suite.
6. **E2E Smoke Test**: Run Playwright suite against launched containers.

## Contracts and Invariants
- Backend tests must execute against a dedicated test database name containing `test` or `ci`.
- CI builds fail automatically if coverage falls below configured threshold.

## Failure Modes
- Destructive Test Prevention: Pytest fixture aborts if database URL does not contain `test` or `ci`.

## Verification Procedure
Execute local CI verification pipeline manually before pushing commits.

## Source Map
- Backend Tests: `backend/tests/`
- Frontend Tests: `frontend/src/test/`
- E2E Tests: `frontend/e2e/`
- CI Pipeline: `.github/workflows/ci.yml` (if present)

## Related Documents
- [Contributing Guidelines](../00_getting_started/CONTRIBUTING.md)
- [Security and Tenant Isolation](SECURITY_AND_TENANT_ISOLATION.md)
