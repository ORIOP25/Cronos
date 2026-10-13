# Dependency inventory

Last reviewed: 2026-10-13

The committed lockfiles are the complete transitive dependency inventories. The input manifests below are the maintained direct-dependency inventories.

## Runtime baselines

| Component | Baseline | Source |
| --- | --- | --- |
| Node.js | 24.19.0 (`.nvmrc`); `>=24.15.0` engine floor | `.nvmrc`, `frontend/package.json`, `frontend/Dockerfile` |
| Python | 3.14.7 in containers; `>=3.12` remains the package support floor | `backend/Dockerfile`, `backend/pyproject.toml` |
| PostgreSQL | 16-alpine, digest-pinned | Compose files and CI |
| Redis | 7-alpine, digest-pinned | Compose files and CI |
| Nginx | `nginx-unprivileged` 1.29-alpine, digest-pinned | `frontend/Dockerfile` |

## Frontend direct dependencies (`frontend/package.json`)

### Production

| Package | Version |
| --- | --- |
| `@clerk/localizations` | `^4.23.0` |
| `@clerk/react` | `^6.17.8` |
| `@coreui/coreui` | `^5.9.1` |
| `@coreui/icons` | `^3.1.0` |
| `@coreui/icons-react` | `^2.3.0` |
| `@coreui/react` | `^5.13.1` |
| `@tanstack/react-query` | `^5.104.1` |
| `axios` | `^1.20.0` |
| `react` | `^19.3.0` |
| `react-dom` | `^19.3.0` |
| `react-hot-toast` | `^2.6.1` |
| `react-router-dom` | `^7.18.4` |

### Development and quality tooling

| Package | Version |
| --- | --- |
| `@axe-core/playwright` | `^4.13.0` |
| `@clerk/backend` | `^3.23.2` |
| `@clerk/testing` | `^2.2.45` |
| `@eslint/js` | `^9.39.5` |
| `@playwright/test` | `^1.64.0` |
| `@testing-library/jest-dom` | `^7.0.1` |
| `@testing-library/react` | `^16.3.3` |
| `@testing-library/user-event` | `14.6.7` |
| `@types/react` / `@types/react-dom` | `^19.3.0` |
| `@vitejs/plugin-react` | `^6.1.2` |
| `@vitest/coverage-v8` | `^5.0.3` |
| `eslint` | `^9.39.5` |
| `eslint-plugin-react` | `^7.37.5` |
| `eslint-plugin-react-hooks` | `^7.1.1` |
| `eslint-plugin-react-refresh` | `^0.5.7` |
| `globals` | `^17.13.0` |
| `jsdom` | `^30.1.2` |
| `knip` | `^6.41.0` |
| `msw` | `3.0.3` |
| `vite` | `^8.3.4` |
| `vitest` | `^5.0.0` |

## Backend direct dependencies

### Runtime (`backend/requirements.in`)

`alembic==1.20.0`, `asyncpg==0.32.0`, `celery==5.6.3`, `clerk-backend-api==7.0.0`, `email-validator==2.3.0`, `fastapi==0.143.0`, `holidays==0.106`, `httpx==0.28.1`, `ortools==9.15.6755`, `psycopg2-binary==2.9.13`, `pydantic-settings==2.15.0`, `redis==8.1.0`, `slowapi==0.1.10`, `structlog==26.1.0`, `svix==2.8.0`, `uvicorn==0.54.0`.

### Development and security tooling (`backend/requirements-dev.in`)

It includes `requirements.in`, then adds `pip==26.2.1`, `pip-audit==2.10.1`, `pip-tools==7.6.2`, `pytest==9.1.1`, `pytest-asyncio==1.4.0`, `pytest-cov==7.1.0`, `pytest-socket==0.8.1`, `pytest-xdist==3.8.0`, and `ruff==0.17.0`.

## Update and security controls

- Dependabot checks GitHub Actions, Docker (`/backend` and `/frontend`), npm, and pip weekly, with production/development grouping for npm and pip.
- `frontend/package-lock.json`, `backend/requirements.txt`, and `backend/requirements-dev.txt` are regenerated lockfiles; Python locks include hashes.
- `npm run audit:production` in `frontend/` audits the production dependencies. `pip-audit` in the backend development tooling audits the Python lock.
- ESLint remains on the 9.x line.
