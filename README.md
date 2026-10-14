# Cronos

Cronos is a Software-as-a-Service (SaaS) platform for course scheduling and operational management in Portuguese Professional Education (*Ensino Profissional*). The system manages school structures, course modules, teacher availability, automated schedule generation, lesson logging (*Sumários*), teacher absences (*Faltas*), and cover arrangements (*Substituições*).

## Technology Stack

| Layer | Technologies |
| :--- | :--- |
| **Backend API** | Python 3.14, FastAPI, Async SQLAlchemy, Pydantic v2, Celery |
| **Frontend UI** | React 19, Vite 8, CoreUI, React Query, Clerk Auth |
| **Database** | PostgreSQL 18 with forced Row-Level Security |
| **Cache / Queue** | Redis 8.2 |
| **Scheduler Engine** | Google OR-Tools CP-SAT (Scheduler v1) |

## Supported User Roles
- **Administrator (`admin`)**: Full access to school settings, curriculum, team management (`Equipa`), solver execution, and draft approvals.
- **Teacher (`teacher`)**: Access to self-service portal, availability configuration, personal timetable, and assigned class lesson logs (*Sumários*).

## Quick Start (Local Docker Environment)

1. **Clone repository and prepare environment files**:
   ```bash
   cp .env.example .env
   cp backend/.env.example backend/.env
   ```
   Replace every placeholder in `.env` (database passwords, Clerk publishable key, Turnstile and Resend test values).
   Set `CLERK_SECRET_KEY` and `CLERK_WEBHOOK_SECRET` in `backend/.env`. Compose loads that file for the `backend`, `worker`, and `scheduler-supervisor` services.

2. **Build the backend image** (`db-maintenance` reuses `cronos-backend:local` and cannot build it):
   ```bash
   docker compose build backend
   ```

3. **Provision database roles on first installation or password rotation**:
   ```bash
   docker compose --profile maintenance run --rm provision-db
   ```

4. **Apply database migrations on first installation and each release**:
   ```bash
   docker compose --profile maintenance run --rm db-maintenance
   ```

5. **Start or reconcile the production-like local stack**:
   ```bash
   docker compose up -d --build
   ```

6. **Bootstrap application data**:
   The application bootstraps the first organization and administrator at the first admin login. The backend exposes this through `POST /api/v1/session/bootstrap`.
   E2E fixtures are prepared by `node scripts/test.mjs e2e`. It runs `backend/scripts/prepare_e2e_clerk_state.py` inside an isolated test stack and needs reserved Clerk test identities.
   See [Data and Seed](documentation/07_data_and_seed/DATA_AND_SEED.md).

7. **Access application services**:
   - Frontend Application: `http://localhost:5173`
   - Backend API documentation: `http://localhost:8000/docs` in `local` mode
   - Liveness endpoint: `http://localhost:8000/health/live`
   - Readiness endpoint: `http://localhost:8000/health/ready`
   - API health endpoint: `http://localhost:8000/api/v1/health`

## Verification Commands

Run tests through the root runner `scripts/test.mjs`.
It selects the correct Python, npm, and Docker paths on every platform.
The [Command Reference](documentation/00_getting_started/COMMAND_REFERENCE.md) lists every command, its prerequisites, its effects, and what it proves.

```bash
node scripts/test.mjs doctor --profile fast
node scripts/test.mjs fast --scope all
```

For Vite hot reload, use `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build`.
The development frontend is available at `http://localhost:5173`.

The local frontend uses Nginx on `http://localhost:5173`.
The Vite development override also uses `http://localhost:5173`.

The root Compose file requires database, Clerk, Turnstile, and Resend variables.
Use test provider credentials for local work.

## Documentation Reading Paths

Complete technical documentation resides in the [`documentation/`](documentation/) directory:

- [Agent Instructions](AGENTS.md)
- [Command Reference](documentation/00_getting_started/COMMAND_REFERENCE.md)
- [Director Onboarding](documentation/00_getting_started/ONBOARDING.md)
- [Project Overview](documentation/00_getting_started/PROJECT_OVERVIEW.md)
- [Repository Map](documentation/00_getting_started/REPOSITORY_MAP.md)
- [Glossary](documentation/00_getting_started/GLOSSARY.md)
- [Technical Walkthrough](documentation/00_getting_started/TECHNICAL_WALKTHROUGH.md)
- [System Architecture](documentation/01_system_architecture/SYSTEM_ARCHITECTURE.md)
- [API Reference](documentation/05_backend_api/API_REFERENCE.md)
