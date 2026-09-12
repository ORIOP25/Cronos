# Cronos

Cronos is a Software-as-a-Service (SaaS) platform for course scheduling and operational management in Portuguese Professional Education (*Ensino Profissional*). The system manages school structures, course modules, teacher availability, automated schedule generation, lesson logging (*Sumários*), teacher absences (*Faltas*), and cover arrangements (*Substituições*).

## Technology Stack

| Layer | Technologies |
| :--- | :--- |
| **Backend API** | Python 3.14, FastAPI, Async SQLAlchemy, Pydantic v2, Celery |
| **Frontend UI** | React 19, Vite 8, CoreUI, React Query, Clerk Auth |
| **Database** | PostgreSQL 16 with forced Row-Level Security |
| **Cache / Queue** | Redis 7 |
| **Scheduler Engine** | Google OR-Tools CP-SAT (Solver V2 Engine) |

## Supported User Roles
- **Administrator (`admin`)**: Full access to school settings, curriculum, team management (`Equipa`), solver execution, and draft approvals.
- **Teacher (`teacher`)**: Access to self-service portal, availability configuration, personal timetable, and assigned class lesson logs (*Sumários*).

## Quick Start (Local Docker Environment)

1. **Clone repository and prepare environment files**:
   ```bash
   cp .env.example .env
   cp backend/.env.example backend/.env
   ```

2. **Provision database roles on first installation or password rotation**:
   ```bash
   docker compose --profile maintenance run --rm provision-db
   ```

3. **Apply database migrations on first installation and each release**:
   ```bash
   docker compose --profile maintenance run --rm db-maintenance
   ```

4. **Start or reconcile the production-like local stack**:
   ```bash
   docker compose up -d --build
   ```

5. **Seed realistic test data from the backend workspace**:
   ```bash
   cd backend
   python seed_data.py
   ```

6. **Access application services**:
   - Frontend Application: `http://localhost:5173`
   - Backend API documentation: `http://localhost:8000/docs` in `local` mode
   - Liveness endpoint: `http://localhost:8000/health/live`
   - Readiness endpoint: `http://localhost:8000/health/ready`
   - API health endpoint: `http://localhost:8000/api/v1/health`

## First Verification Commands

Use the fast suites during the TDD cycle:

```powershell
# Backend TDD cycle. Requires no PostgreSQL or Redis.
cd backend
pytest -m "unit and not slow" -q

# Frontend TDD cycle.
cd ..\frontend
npm test
```

Run the complete validation before integration:

- Backend with PostgreSQL and Redis configured: `pytest tests/ -v`.
- Frontend with `npm run verify`.
- E2E only with reserved Clerk test identities.

For Vite hot reload, use `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build`.
The development frontend is available at `http://localhost:5173`.

The local frontend uses Nginx on `http://localhost:5173`.
The Vite development override also uses `http://localhost:5173`.

The root Compose file requires database, Clerk, Turnstile, and Resend variables.
Use test provider credentials for local work.

## Documentation Reading Paths

Complete technical documentation resides in the [`documentation/`](documentation/) directory:

- [Director Onboarding](documentation/00_getting_started/ONBOARDING.md)
- [Project Overview](documentation/00_getting_started/PROJECT_OVERVIEW.md)
- [Repository Map](documentation/00_getting_started/REPOSITORY_MAP.md)
- [Glossary](documentation/00_getting_started/GLOSSARY.md)
- [Technical Walkthrough](documentation/00_getting_started/TECHNICAL_WALKTHROUGH.md)
- [System Architecture](documentation/01_system_architecture/SYSTEM_ARCHITECTURE.md)
- [API Reference](documentation/05_backend_api/API_REFERENCE.md)
