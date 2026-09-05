# Contributing Guidelines

## Purpose
This document specifies engineering standards, Git workflow rules, and mandatory quality gates for repository contributions.

## Intended Reader
This document targets all software developers submitting code changes to Cronos.

## Prerequisites
Review the [Repository Map](REPOSITORY_MAP.md) and set up the local runtime environment.

## Git Branching Model
- `main`: Production release branch. Must remain stable at all times.
- `develop`: Integration branch accepted by the CI workflow.
- `feature/*`: Optional development feature branches.
- Commit messages must use concise imperative descriptions (e.g., `fix: update RLS policy for occurrences`).

## Code Standards and Tooling

### Backend (Python)
- Code formatter and linter: `ruff`
- Run formatter check: `ruff format --check .`
- Run linter check: `ruff check .`
- Database migrations: Use Alembic for all schema alterations (`alembic revision --autogenerate -m "description"`).
- Never execute destructive database operations without migration scripts.

### Frontend (React)
- Linter: ESLint (`npm run lint` inside `frontend/`)
- Dead code scanner: Knip (`npm run lint:dead-code` inside `frontend/`)
- Component styling: Follow `DESIGN_SYSTEM.md` tokens. Do not introduce ad-hoc CSS frameworks.

## TDD Feedback Cycle
Run the fast suites while developing:

```powershell
cd backend
pytest -m "unit and not slow" -q

cd ..\frontend
npm test
```

## Mandatory Pre-Integration Quality Gates
Before integrating code, run the complete verification pipeline:

1. **Backend Tests**:
   ```bash
   cd backend
   pytest tests/ -v
   ```
2. **Backend Database Integrity Check**:
   ```bash
   cd backend
   alembic upgrade head
   alembic check
   python -m scripts.audit_triggers
   python -m scripts.audit_database_integrity
   ```

   Use the CI or maintenance container when local PostgreSQL is not configured for `cronos_migrator`.
3. **Frontend Tests**:
   ```bash
   cd frontend
   npm run verify
   ```

Coverage, lint, dependency audits, database audits, and E2E remain required gates.

## Diagnostics

Run the frontend stability check only when investigating scheduler settings:

```bash
cd frontend
```

This command is diagnostic. Do not treat it as a pre-integration gate.

## Source Map
- Backend Quality Rules: `backend/README.md`
- Frontend Quality Rules: `frontend/README.md`
- CI Pipeline Config: `.github/workflows/ci.yml`

## Related Documents
- [Testing and CI](../08_security_quality/TESTING_AND_CI.md)
- [Documentation Standard](DOCUMENTATION_STANDARD.md)
