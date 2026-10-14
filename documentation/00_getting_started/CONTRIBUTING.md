# Contributing Guidelines

## Purpose
This document specifies engineering standards, the Git workflow, and the quality gates for repository contributions.

## Intended Reader
This document targets every contributor. Most contributors are AI agents.

## Prerequisites
Read [AGENTS.md](../../AGENTS.md), the [Repository Map](REPOSITORY_MAP.md), and the [Command Reference](COMMAND_REFERENCE.md).
Install Python 3.14, Node 24, npm 11, Docker 29, and Docker Compose 5.
Run `node scripts/test.mjs doctor --profile fast` to check them.

## Git Workflow
- `main`: Production release branch. Every merge deploys to Railway and Cloudflare Pages.
- Work branches: one branch per change, for example `feat/<topic>`, `fix/<topic>`, or `docs/<topic>`.
- Open a pull request for every branch. A branch without a pull request gets no automatic CI.
- Squash-merge only when every required check is green: `backend`, `frontend`, `e2e-runtime`, and `e2e-browser`.
- After the merge, monitor the `Deploy check` workflow on `main` until it passes.
- Commit messages use Conventional Commits with an imperative description, for example `fix: update RLS policy for occurrences`.
- Never force-push `main`, skip hooks, or merge a red or pending pull request.

[AGENTS.md](../../AGENTS.md#git-ci-and-delivery) gives agents the standing authorization for this workflow.

## Code Standards and Tooling

### Backend (Python)
- Runtime: Python 3.14.
- Formatter and linter: `ruff`. CI runs `ruff format --check .` and `ruff check .` in `backend/`.
- Database migrations: Use Alembic for all schema changes (`alembic revision --autogenerate -m "description"`).
- Keep one linear migration chain from `0001_scheduler_v1_baseline` in `backend/alembic/versions/`. Do not create branches or merge revisions.
- Run migrations with the privileged `cronos_migrator` role through the maintenance container.
- Never execute destructive database operations without migration scripts.

### Frontend (React)
- Runtime: Node 24 and npm 11.
- Linter: ESLint (`npm run lint` inside `frontend/`).
- Dead code scanner: Knip (`npm run lint:dead-code` and `npm run lint:dead-code:production` inside `frontend/`).
- Component styling: Follow the [Design System](../06_frontend_ux/DESIGN_SYSTEM.md) tokens. Do not introduce ad-hoc CSS frameworks.

## Quality Gates

The [Command Reference](COMMAND_REFERENCE.md) owns every command, prerequisite, and side effect.
It also defines the [verification required for each change type](COMMAND_REFERENCE.md#verification-by-change-type).
The CI workflow is the release authority. Local commands give fast feedback before the pull request.

Coverage policy:

- Whole-application backend coverage is at least `70%` in the full run.
- `backend/tests/critical_manifest.json` owns the critical coverage sources and thresholds.
- `app/scheduler/domain/constraint_policy.py` stays at `100%` and `app/scheduler/domain/candidate_validation.py` at `90%`.
- The suites must report zero skipped tests.

## Source Map
- Backend workspace: `backend/README.md`
- Frontend workspace: `frontend/README.md`
- CI pipeline: `.github/workflows/ci.yml`
- Deploy check: `.github/workflows/deploy-check.yml`
- Unified test runner: `scripts/test.mjs`

## Related Documents
- [Command Reference](COMMAND_REFERENCE.md)
- [Testing and CI](../08_security_quality/TESTING_AND_CI.md)
- [Documentation Standard](DOCUMENTATION_STANDARD.md)
