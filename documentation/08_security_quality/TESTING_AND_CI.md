# Testing and CI

## Purpose

This document describes local verification, test suites, coverage gates, and the current GitHub Actions workflow.

## Intended Reader

This document targets developers, QA engineers, and release engineers.

## Prerequisites

Install Python 3.12, Node 24, Docker, PostgreSQL tooling, and Redis support.
Read [Contributing Guidelines](../00_getting_started/CONTRIBUTING.md).

## What the System Does

CI validates backend dependencies, formatting, migrations, database contracts, backend tests, frontend quality, and full-stack E2E flows.

## Why the Behavior Exists

The pipeline checks both isolated workspaces and the composed application.
Database safeguards prevent destructive tests from targeting a real database.

## Components and Ownership

| Area | Tool or source | Gate |
| :--- | :--- | :--- |
| Backend tests | Pytest and coverage | Combined coverage at least 70% |
| Backend quality | Ruff, pip check, pip-audit | No unexpected drift or lint errors |
| Database | Alembic and audit scripts | Upgrade, check, downgrade, upgrade |
| Frontend tests | Vitest and V8 coverage | Thresholds in `frontend/vite.config.js` |
| Frontend quality | ESLint and Knip | `npm run verify` |
| E2E | Playwright and Docker Compose | Clerk test identities and full stack |
| Workflow | `.github/workflows/ci.yml` | Runs on `main`, `develop`, and pull requests |

## Data or Request Flow

1. CI starts PostgreSQL and Redis for the backend job.
2. CI installs locked Python dependencies and checks generated lock files.
3. CI runs Ruff, migrations, audits, and split Redis test suites.
4. CI builds the hardened backend image.
5. CI installs frontend dependencies and runs production audit and `npm run verify`.
6. CI builds the full Compose stack and runs Playwright E2E tests.
7. CI removes the Compose project and volumes in an `always()` cleanup step.

## Contracts and Invariants

- Test database names must contain `test` or `ci`.
- CI uses separate migrator and application database credentials.
- CI fails when backend coverage is below 70%.
- Scheduler domain constraints require full coverage in their dedicated report.
- Skipped tests fail the backend job.
- The current workflow has no tag-triggered image publication job.

## States and Transitions

CI moves through checkout, dependency installation, static checks, tests, image build, E2E, and cleanup.
Any failed required job prevents a green workflow.

## Failure Modes

- Lockfile drift fails the dependency job.
- Migration drift fails `alembic check`.
- Database trigger drift fails the audit job.
- Missing Clerk E2E secrets stops identity validation.
- Compose health failures stop the E2E stack.

## Verification Procedure

### Backend

```powershell
cd backend
ruff format --check .
ruff check .
pytest -q
```

Run migration and audit commands with the configured migrator role.

### Frontend

```powershell
cd frontend
npm ci
npm run audit:production
npm run verify
npm run test:school-config:stability
```

### Images and E2E

```powershell
docker build --target runtime -t cronos-backend:test backend
docker compose -f docker-compose.ci.yml config
```

Run the full E2E workflow only with dedicated Clerk test identities.

## Source Map

- Workflow: `.github/workflows/ci.yml`
- Compose CI: `docker-compose.ci.yml`
- Backend tests: `backend/tests/`
- Frontend tests: `frontend/src/test/`
- E2E tests: `frontend/e2e/`
- Frontend thresholds: `frontend/vite.config.js`

## Related Documents

- [Contributing Guidelines](../00_getting_started/CONTRIBUTING.md)
- [Security and Tenant Isolation](SECURITY_AND_TENANT_ISOLATION.md)
- [Local Runtime](../09_ops_observability/LOCAL_RUNTIME.md)
