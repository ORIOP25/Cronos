# Contributing Guidelines

## Purpose
This document specifies engineering standards, Git workflow rules, and mandatory quality gates for repository contributions.

## Intended Reader
This document targets all software developers submitting code changes to Cronos.

## Prerequisites
Review the [Repository Map](REPOSITORY_MAP.md) and set up the local runtime environment.

## Git Branching Model
- `main`: Production release branch. Must remain stable at all times.
- `review-backend` / `feature/*`: Development feature branches.
- Commit messages must use concise imperative descriptions (e.g., `fix: update RLS policy for occurrences`).

## Code Standards and Tooling

### Backend (Python)
- Code formatter and linter: `ruff`
- Run linter check: `ruff check app scripts`
- Database migrations: Use Alembic for all schema alterations (`alembic revision --autogenerate -m "description"`).
- Never execute destructive database operations without migration scripts.

### Frontend (React)
- Linter: ESLint (`npm run lint` inside `frontend/`)
- Dead code scanner: Knip (`npm run lint:dead-code` inside `frontend/`)
- Component styling: Follow `DESIGN_SYSTEM.md` tokens. Do not introduce ad-hoc CSS frameworks.

## Mandatory Pre-Commit Quality Gates
Before pushing code, run the following verification pipeline:

1. **Backend Tests**:
   ```bash
   cd backend
   pytest tests/ -v
   ```
2. **Backend Database Integrity Check**:
   ```bash
   python backend/scripts/audit_database_integrity.py
   ```
3. **Frontend Tests**:
   ```bash
   cd frontend
   npm run test
   npm run build
   ```

## Source Map
- Backend Quality Rules: `backend/README.md`
- Frontend Quality Rules: `frontend/README.md`
- CI Pipeline Config: `.github/workflows/ci.yml` (if configured)

## Related Documents
- [Testing and CI](../08_security_quality/TESTING_AND_CI.md)
- [Documentation Standard](DOCUMENTATION_STANDARD.md)
