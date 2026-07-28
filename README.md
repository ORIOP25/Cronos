# Cronos

Cronos is a Software-as-a-Service (SaaS) platform for course scheduling and operational management in Portuguese Professional Education (*Ensino Profissional*). The system manages school structures, course modules, teacher availability, automated schedule generation, lesson logging (*Sumários*), teacher absences (*Faltas*), and cover arrangements (*Substituições*).

## Technology Stack

| Layer | Technologies |
| :--- | :--- |
| **Backend API** | Python 3.12, FastAPI, Async SQLAlchemy, Pydantic v2, Celery |
| **Frontend UI** | React 19, Vite 8, CoreUI, React Query, Clerk Auth |
| **Database** | PostgreSQL 15 (Local) / PostgreSQL 16 (CI) with Row-Level Security |
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

5. **Seed realistic test data**:
   ```bash
   docker compose exec backend python scripts/seed.py --scenario small-realistic
   ```

6. **Access application services**:
   - Frontend Application: `http://localhost:8080`
   - Backend API Documentation: `http://localhost:8000/docs`
   - Health Check Endpoint: `http://localhost:8000/api/v1/health`

## First Verification Commands

Run backend and frontend verification commands to test your setup:

```bash
# Run backend tests
cd backend && pytest tests/ -v

# Run frontend tests
cd frontend && npm run test
```

For Vite hot reload, use `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build`.
The development frontend is available at `http://localhost:5173`.

## Documentation Reading Paths

Complete technical documentation resides in the [`documentation/`](documentation/) directory:

- [Project Overview](documentation/00_getting_started/PROJECT_OVERVIEW.md)
- [Repository Map](documentation/00_getting_started/REPOSITORY_MAP.md)
- [Glossary](documentation/00_getting_started/GLOSSARY.md)
- [Technical Walkthrough](documentation/00_getting_started/TECHNICAL_WALKTHROUGH.md)
- [System Architecture](documentation/01_system_architecture/SYSTEM_ARCHITECTURE.md)
- [API Reference](documentation/05_backend_api/API_REFERENCE.md)
