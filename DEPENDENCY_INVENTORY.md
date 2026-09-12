# Dependency inventory

Last reviewed: 2026-09-12

The committed lockfiles are the complete transitive dependency inventories. The input manifests below are the maintained direct-dependency inventories.

## Runtime baselines

| Component | Baseline | Source |
| --- | --- | --- |
| Node.js | 24.19.0 LTS | `.nvmrc`, `frontend/package.json`, CI, `frontend/Dockerfile` |
| Python | 3.14 for CI and containers; `>=3.12` remains the package support floor | CI, `backend/Dockerfile`, `backend/pyproject.toml` |
| PostgreSQL | 16-alpine, digest-pinned | Compose files and CI |
| Redis | 7-alpine, digest-pinned | Compose files and CI |
| Nginx | 1.29-alpine, digest-pinned | `frontend/Dockerfile` |

## Frontend direct dependencies

### Production

| Package | Version |
| --- | --- |
| `@clerk/localizations` | `^4.16.1` |
| `@clerk/react` | `^6.15.2` |
| `@coreui/coreui` | `^5.9.0` |
| `@coreui/icons` | `^3.1.0` |
| `@coreui/icons-react` | `^2.3.0` |
| `@coreui/react` | `^5.13.0` |
| `@tanstack/react-query` | `^5.102.8` |
| `axios` | `^1.20.0` |
| `msw` | `^2.15.0` |
| `react` | `^19.3.0` |
| `react-dom` | `^19.3.0` |
| `react-router-dom` | `^7.18.3` |

### Development and quality tooling

| Package | Version |
| --- | --- |
| `@axe-core/playwright` | `^4.13.0` |
| `@clerk/backend` | `^3.17.2` |
| `@clerk/testing` | `^2.2.34` |
| `@eslint/js` | `^9.39.5` |
| `@playwright/test` | `^1.63.0` |
| `@testing-library/jest-dom` | `^7.0.1` |
| `@testing-library/react` | `^16.3.3` |
| `@testing-library/user-event` | `^14.6.7` |
| `@types/react` / `@types/react-dom` | `^19.3.0` |
| `@vitejs/plugin-react` | `^6.1.1` |
| `@vitest/coverage-v8` | `^5.0.0` |
| `eslint` | `^9.39.5` |
| `eslint-plugin-react` | `^7.37.5` |
| `eslint-plugin-react-hooks` | `^7.1.1` |
| `eslint-plugin-react-refresh` | `^0.5.6` |
| `globals` | `^17.12.0` |
| `jsdom` | `^30.0.1` |
| `knip` | `^6.35.1` |
| `vite` | `^8.3.0` |
| `vitest` | `^5.0.0` |

## Backend direct dependencies

### Runtime (`backend/requirements.in`)

`alembic==1.20.0`, `asyncpg==0.31.0`, `celery==5.6.3`, `clerk-backend-api==7.0.0`, `email-validator==2.3.0`, `fastapi==0.141.1`, `holidays==0.104`, `ortools==9.15.6755`, `psycopg2-binary==2.9.13`, `pydantic-settings==2.15.0`, `redis==8.1.0`, `slowapi==0.1.10`, `structlog==26.1.0`, `svix==2.5.0`, `uvicorn==0.52.4`.

### Development and security tooling (`backend/requirements-dev.in`)

`httpx==0.28.1`, `pip==26.2.1`, `pip-audit==2.10.1`, `pip-tools==7.6.1`, `pytest==9.1.1`, `pytest-asyncio==1.4.0`, `pytest-cov==7.1.0`, `pytest-socket==0.8.1`, `pytest-xdist==3.8.0`, `ruff==0.16.7`.

## Update and security controls

- Dependabot checks npm, pip, Docker, and GitHub Actions weekly, with production/development grouping for npm and pip.
- `frontend/package-lock.json`, `backend/requirements.txt`, and `backend/requirements-dev.txt` are regenerated lockfiles; Python locks include hashes.
- Frontend production audit: 0 vulnerabilities.
- Backend `pip-audit -r requirements.txt`: 0 known vulnerabilities.
- Backend `pip check`: no broken requirements.
- ESLint remains on the latest compatible 9.x line because the current React ESLint plugin does not yet accept ESLint 10 as a peer.
