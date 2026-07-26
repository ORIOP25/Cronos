# Local Runtime

## Purpose
This document provides instructions for deploying, configuring, and operating the Cronos runtime environment locally.

## Intended Reader
This document targets all software developers and DevOps engineers.

## Prerequisites
Install Docker Desktop (with Docker Compose) and Python 3.12 locally.

## What the System Does
The application executes locally using Docker Compose (`docker-compose.yml`).

## Container Topology Table

| Container Name | Internal Service | Exposed Host Port | Container Base Image |
| :--- | :--- | :--- | :--- |
| `cronos-db` | PostgreSQL Database | `5432` | `postgres:15-alpine` |
| `cronos-redis` | Redis Queue & Cache | `6379` | `redis:7-alpine` |
| `cronos-backend` | FastAPI REST API | `8000` | Custom Python 3.12 |
| `cronos-worker` | Celery Solver Worker | N/A | Custom Python 3.12 |
| `cronos-frontend` | React Nginx / Vite Dev | `5173` | Custom Node 20 / Nginx |

## Environment Groups and Configuration

### Backend Environment Variables (`backend/.env`)
- `ENVIRONMENT`: Runtime mode (`local`, `testing`, `production`).
- `DATABASE_URL`: PostgreSQL connection string (`postgresql+asyncpg://postgres:pass@db:5432/cronos_db`).
- `REDIS_URL`: Redis connection string (`redis://redis:6379/0`).
- `CLERK_SECRET_KEY`: Secret API key for Clerk authentication verification.
- `CLERK_WEBHOOK_SECRET`: SVIX signing secret for incoming webhooks.

### Frontend Environment Variables (`frontend/.env.local`)
- `VITE_API_URL`: Backend API base URL (`http://localhost:8000/api/v1`).
- `VITE_CLERK_PUBLISHABLE_KEY`: Publishable key for Clerk client SDK.

## Quick Start Commands

1. **Start Infrastructure Services**:
   ```bash
   docker compose up -d
   ```
2. **Apply Database Migrations**:
   ```bash
   docker compose exec cronos-backend alembic upgrade head
   ```
3. **Seed Test Data**:
   ```bash
   docker compose exec cronos-backend python scripts/seed.py --scenario small-realistic
   ```

## Service Access URLs

| Application Service | Local Access URL |
| :--- | :--- |
| **Frontend Web App** | `http://localhost:5173` |
| **Backend API Docs** | `http://localhost:8000/docs` |
| **Health Endpoint** | `http://localhost:8000/api/v1/health` |

## Failure Modes
- Container Startup Order: Backend container retries database connection until PostgreSQL accepts connections.

## Verification Procedure
Access `http://localhost:8000/health`. Verify HTTP status `200` response.

## Source Map
- Docker Compose: `docker-compose.yml`
- Backend Environment: `backend/app/core/config.py`
- Frontend Environment: `frontend/vite.config.js`

## Related Documents
- [Repository Map](../00_getting_started/REPOSITORY_MAP.md)
- [Observability and Recovery](OBSERVABILITY_AND_RECOVERY.md)
