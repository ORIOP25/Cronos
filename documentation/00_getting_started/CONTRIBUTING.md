# Contributing Guidelines

## Purpose
This document specifies engineering standards, Git workflow rules, and mandatory quality gates for repository contributions.

## Intended Reader
This document targets all software developers submitting code changes to Cronos.

## Prerequisites
Review the [Repository Map](REPOSITORY_MAP.md) and set up the local runtime environment.
Install Python 3.14, Node 24, and npm 11. The root test runner checks these versions.

## Git Branching Model
- `main`: Production release branch. Must remain stable at all times.
- `develop`: Integration branch for the next release.
- `feature/*`: Optional development feature branches.
- CI runs on every push and pull request.
- Commit messages must use concise imperative descriptions (e.g., `fix: update RLS policy for occurrences`).

## Code Standards and Tooling

### Backend (Python)
- Runtime: Python 3.14.
- Code formatter and linter: `ruff`
- Run formatter check: `ruff format --check .`
- Run linter check: `ruff check .`
- Database migrations: Use Alembic for all schema alterations (`alembic revision --autogenerate -m "description"`).
- Keep one linear migration chain from the baseline `0001_scheduler_v1_baseline` to the head `0017_active_course_abbreviations`. Do not create branches or merge revisions.
- Run migrations with the privileged `cronos_migrator` role through the maintenance container.
- Never execute destructive database operations without migration scripts.

### Frontend (React)
- Runtime: Node 24 and npm 11.
- Linter: ESLint (`npm run lint` inside `frontend/`)
- Dead code scanner: Knip (`npm run lint:dead-code` and `npm run lint:dead-code:production` inside `frontend/`)
- Component styling: Follow the [Design System](../06_frontend_ux/DESIGN_SYSTEM.md) tokens. Do not introduce ad-hoc CSS frameworks.

## TDD Feedback Cycle
Run the fast suites while developing:

```powershell
# Backend unit tests. No database or external network.
cd backend
pytest tests/unit -q

# Frontend unit tests.
cd ..\frontend
npm test
```

The root runner provides the same fast profile:

```powershell
node scripts/test.mjs fast --scope all
```

## Mandatory Pre-Integration Quality Gates
Before integrating code, run the complete verification pipeline.

### Backend gates

```bash
cd backend
ruff format --check .
ruff check .
alembic upgrade head
alembic check
alembic downgrade base
alembic upgrade head
python -m scripts.audit_triggers
python -m scripts.audit_database_integrity
pytest tests/unit
pytest -n 4 --dist=loadscope tests/integration
pytest tests/contracts
```

Run the database steps with the privileged `cronos_migrator` role through the maintenance container.

### Backend coverage gates

- Overall coverage is at least `70%`.
- `app/scheduler/domain/constraint_policy.py` coverage is `100%`.
- `app/scheduler/domain/candidate_validation.py` coverage is `90%`.
- The suite must report zero skipped tests.

### Frontend gates

```bash
cd frontend
npm ci --ignore-scripts
npm run audit:production
npm run verify
```

`npm run verify` runs ESLint, Knip in default and production mode, the legal and marketing build checks, Vitest coverage, and the production build.

## Diagnostics

Run the school configuration scheduler settings test only when investigating scheduler settings:

```bash
cd frontend
npm test -- src/test/SchoolConfigSchedulerSettings.test.jsx
```

This command is diagnostic. Do not treat it as a pre-integration gate.

## Source Map
- Backend Quality Rules: `backend/README.md`
- Frontend Quality Rules: `frontend/README.md`
- CI Pipeline Config: `.github/workflows/ci.yml`
- Unified Test Runner: `scripts/test.mjs`

## Related Documents
- [Testing and CI](../08_security_quality/TESTING_AND_CI.md)
- [Documentation Standard](DOCUMENTATION_STANDARD.md)
