# Cronos AI Agent Suite

This directory contains specialized AI agent skills and guidance for developing Cronos.

## Core Foundation Skill

- [`cronos-base/SKILL.md`](skills/cronos-base/SKILL.md): Base foundation rules required by all Cronos skills.

## Specialist Cronos Skills

| Skill Name | Trigger Scenario | Primary Scope |
| :--- | :--- | :--- |
| **`cronos-backend`** | Backend API, SQLAlchemy models, Alembic, Clerk auth | `backend/app/`, `backend/tests/` |
| **`cronos-domain`** | Professional education rules, modules, course invariants | `documentation/02_domain_model/` |
| **`cronos-frontend`** | React 19 pages, Vite build, React Query, Clerk UI | `frontend/src/` |
| **`cronos-frontend-designer`** | Design system tokens, CSS styles, visual branding | `documentation/06_frontend_ux/`, `frontend/src/styles/brand.tokens.css`, `frontend/src/index.css` |
| **`cronos-operations`** | Lesson logs (*Sumários*), absences (*Faltas*), timesheets | `documentation/04_operational_features/` |
| **`cronos-scheduler`** | OR-Tools CP-SAT solver, draft promotion, repair jobs | `backend/app/scheduler/`, `backend/app/services/scheduler_*` |

## Protected Imported Skills

The following imported skill suites are protected and must not be modified:

- `.agents/skills/clerk*`: Official Clerk authentication skill suite.
- `.agents/skills/grill-me/`: Interactive design stress-testing skill.
- `.agents/skills/ponytail/`: Minimalist implementation methodology skill.
- `.agents/skills/design-taste-frontend/`: Imported frontend design skill.
- `skills-lock.json`: Skill lockfile.

Git tracks `.agents/skills/cronos-*` and `.agents/skills/ponytail/`, because AGENTS.md requires them. `.gitignore` ignores the other skill directories, so they exist only where installed locally.

## Source of Truth Policy

The actual codebase implementation and unit test suite are the sole source of truth.
Deployment contracts also live in `docker-compose*.yml`, `backend/railway/*.json`,
`.github/workflows/ci.yml`, and the environment example files.

Local, test, and CI stacks use PostgreSQL 18 and Redis 8.2.
Fresh databases use the frozen `0001_scheduler_v1_baseline` migration.
Railway JSON files record intended settings. Verify their dashboard application before deployment.
