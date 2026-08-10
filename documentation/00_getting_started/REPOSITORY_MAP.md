# Repository Map

## Purpose
This document maps the repository file tree, component boundaries, and directory ownership.

## Intended Reader
This document targets all developers working on the Cronos codebase.

## Prerequisites
Read the [Project Overview](PROJECT_OVERVIEW.md).

## What the System Does
Cronos organizes source into backend, frontend, documentation, workflow, and agent-skill areas.

## Repository Tree Structure

```text
MeuProjeto/
├── .agents/                      # AI agent skills and configuration
│   ├── README.md                 # Agent suite documentation
│   └── skills/                   # Modular skills (cronos-*, clerk*, grill-me, ponytail)
├── .github/                      # GitHub Action workflows and agent definitions
│   ├── agents/                   # Agent_Cronos.md router
│   └── workflows/                # CI workflow specifications
├── backend/                      # Python FastAPI application
│   ├── alembic/                  # Database migration scripts
│   ├── app/                      # Backend application source
│   │   ├── api/                  # API routers (v1 endpoints)
│   │   ├── core/                 # Authentication, exceptions, logging, and rate limits
│   │   ├── db/                   # Database engine and tenant context
│   │   ├── models.py             # SQLAlchemy ORM models
│   │   ├── schemas.py            # Pydantic data schemas
│   │   ├── services/             # Business logic and domain services
│   │   └── scheduler/            # Scheduler domain and infrastructure adapters
│   ├── scripts/                  # Database audits, member support, and E2E preparation
│   ├── seed_data.py              # Canonical operational seed entry point
│   ├── tests/                    # Pytest test suite
│   ├── Dockerfile                # Multi-stage BuildKit backend image file
│   └── README.md                 # Backend workspace documentation
├── frontend/                     # React 19 + Vite frontend application
│   ├── e2e/                      # Playwright end-to-end tests
│   ├── public/                   # Static graphics and marketing assets
│   ├── scripts/                  # Quality and CSS coverage scripts
│   ├── src/                      # React source code
│   │   ├── components/           # Reusable UI components
│   │   │   └── marketing/        # Modular marketing site sections
│   │   ├── data/                 # Extracted static content data
│   │   ├── features/             # Feature-specific logic and hooks
│   │   ├── hooks/                # Custom React hooks
│   │   ├── pages/                # Top-level page views
│   │   ├── App.jsx               # Route definitions and layout router
│   │   ├── index.css             # Global design tokens and styles
│   │   └── main.jsx              # React entry point
│   ├── .dockerignore             # Docker build exclusion rules
│   ├── Dockerfile                # Multi-stage Nginx / Node frontend image file
│   ├── nginx.conf                # Production Nginx SPA server configuration
│   └── README.md                 # Frontend workspace documentation
├── documentation/                # Controlled ASD-STE100 technical documentation
│   ├── 00_getting_started/       # Onboarding and repository guides
│   ├── 01_system_architecture/   # System architecture and data models
│   ├── 02_domain_model/          # Professional education domain rules
│   ├── 03_scheduler_engine/      # Solver V2 engine documentation
│   ├── 04_operational_features/  # Operational workflows and timesheets
│   ├── 05_backend_api/           # REST API reference and standards
│   ├── 06_frontend_ux/           # UI architecture, routes, design tokens
│   ├── 07_data_and_seed/         # Seed scenarios and test data
│   ├── 08_security_quality/      # Security controls, RLS, and CI workflows
│   └── 09_ops_observability/     # Local runtime and observability runbooks
├── .env.example                  # Template root environment variable file
├── docker-compose.yml            # Production-like local Compose deployment
├── docker-compose.dev.yml        # Development override file for Vite hot reload
├── docker-compose.ci.yml         # CI workflow Compose deployment
├── README.md                     # Root repository quick start guide
├── skills-lock.json              # Version lockfile for AI skills
└── sonar-project.properties      # SonarQube quality analysis configuration
```

## Component Ownership and Boundaries

| Workspace | Primary Languages | Boundary Rule |
| :--- | :--- | :--- |
| `backend/` | Python | Handles data persistence, authentication checks, business logic, solver computation. |
| `frontend/` | JavaScript, JSX, CSS | Handles user interfaces, client routing, API requests, state management. |
| `documentation/` | Markdown | Maintains technical guides following ASD-STE100 rules. |
| `.agents/` | Markdown | Defines specialized agent skills and routing guidance. |

## Source Map
- Backend Entry: `backend/app/main.py`
- Frontend Entry: `frontend/src/main.jsx`
- Compose Configurations: `docker-compose.yml`, `docker-compose.dev.yml`, `docker-compose.ci.yml`

## Related Documents
- [Project Overview](PROJECT_OVERVIEW.md)
- [Local Runtime Guide](../09_ops_observability/LOCAL_RUNTIME.md)
