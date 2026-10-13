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
│   └── skills/                   # Cronos skills, tracked ponytail skill, and ignored imported skills
├── .github/                      # GitHub Action workflows and agent definitions
│   ├── agents/                   # Agent_Cronos.md router
│   ├── workflows/                # CI workflow specifications
│   └── dependabot.yml            # Automated dependency update configuration
├── backend/                      # Python FastAPI application
│   ├── alembic/                  # Single baseline: 0001_scheduler_v1_baseline
│   ├── app/                      # Backend application source
│   │   ├── api/                  # API routers (v1 endpoints)
│   │   ├── contact/              # Contact service, ports, and provider gateways
│   │   ├── core/                 # Authentication, exceptions, logging, and rate limits
│   │   ├── db/                   # Database engine and tenant context
│   │   ├── middleware/           # Request body limit middleware
│   │   ├── ops/                  # Database provisioning operations
│   │   ├── models.py             # SQLAlchemy ORM models
│   │   ├── schemas.py            # Pydantic data schemas
│   │   ├── services/             # Business logic and domain services
│   │   └── scheduler/            # Scheduler domain and infrastructure adapters
│   ├── railway/                  # Railway service deployment definitions
│   │   └── *.json                # api, beat, bootstrap, supervisor, and worker services
│   ├── scripts/                  # Database provisioning, audits, privacy, and E2E preparation
│   ├── tests/                    # Pytest test suite
│   ├── Dockerfile                # Multi-stage BuildKit backend image file
│   └── README.md                 # Backend workspace documentation
├── frontend/                    # React 19 + Vite frontend application
│   ├── e2e/                      # Playwright end-to-end tests
│   ├── public/                   # Static graphics and response headers
│   ├── scripts/                  # Marketing build, legal contract, and production verification scripts
│   ├── src/                      # React source code
│   │   ├── components/           # Reusable UI components
│   │   ├── features/             # Feature-specific logic and hooks
│   │   ├── hooks/                # Custom React hooks
│   │   ├── pages/                # Top-level page views
│   │   ├── styles/               # Page and component style sheets
│   │   ├── test/                 # Vitest unit and component tests
│   │   ├── utils/                # Shared browser utility modules
│   │   ├── App.jsx               # Route definitions and layout router
│   │   ├── index.css             # Global design tokens and styles
│   │   └── main.jsx              # React entry point
│   ├── Dockerfile                # Multi-stage Nginx / Node frontend image file
│   ├── nginx.conf                # Production Nginx SPA server configuration
│   ├── nginx.ci.conf             # Nginx configuration for the CI and local images
│   └── README.md                 # Frontend workspace documentation
├── documentation/                # Controlled ASD-STE100 technical documentation
│   ├── 00_getting_started/       # Onboarding and repository guides
│   │   ├── ONBOARDING.md         # Canonical Foundation and tutorial contract
│   ├── 01_system_architecture/   # System architecture and data models
│   ├── 02_domain_model/          # Professional education domain rules
│   ├── 03_scheduler_engine/      # Scheduler engine documentation
│   ├── 04_operational_features/  # Operational workflows and timesheets
│   ├── 05_backend_api/           # REST API reference and standards
│   ├── 06_frontend_ux/           # UI architecture, routes, design tokens
│   ├── 07_data_and_seed/         # Seed scenarios and test data
│   │   └── sample_import_48_classes/ # Sample CSV import set (48 classes, 16 courses)
│   ├── 08_security_quality/      # Security controls, RLS, and CI workflows
│   └── 09_ops_observability/     # Local runtime and observability runbooks
├── scripts/                      # Root test and quality runners
│   ├── test.mjs                  # Unified local and CI test runner
│   ├── loc-report.mjs            # Measured lines-of-code report
│   └── sanitize-test-artifacts.mjs # Test artifact sanitizer
├── .env.example                  # Template root environment variable file
├── docker-compose.yml             # Production-like local Compose deployment
├── docker-compose.dev.yml         # Development override for Vite hot reload
├── docker-compose.ci.yml          # CI workflow Compose deployment
├── docker-compose.test.yml        # Isolated test Compose deployment
├── README.md                      # Root repository quick start guide
├── skills-lock.json               # Version lockfile for AI skills
└── .sonarcloud.properties         # SonarQube Cloud automatic analysis scope
```

## Component Ownership and Boundaries

| Workspace | Primary Languages | Boundary Rule |
| :--- | :--- | :--- |
| `backend/` | Python | Handles data persistence, authentication checks, business logic, and solver computation. |
| `frontend/` | JavaScript, JSX, CSS | Handles user interfaces, client routing, API requests, and state management. |
| `documentation/` | Markdown | Maintains technical guides following ASD-STE100 rules. |
| `.agents/` | Markdown | Defines specialized agent skills and routing guidance. |

## Source Map

- Backend entry: `backend/app/main.py`
- Frontend entry: `frontend/src/main.jsx`
- Onboarding routes: `frontend/src/App.jsx`, `frontend/src/routeGuards.jsx`
- Foundation feature: `frontend/src/features/foundation/`
- Tutorial feature: `frontend/src/features/tutorial/`
- Onboarding API: `backend/app/api/v1/endpoints/session.py`, `backend/app/api/v1/endpoints/foundation.py`, `backend/app/api/v1/endpoints/readiness.py`
- Onboarding services: `backend/app/services/foundation_service.py`, `backend/app/services/school_readiness_service.py`, `backend/app/services/dashboard_service.py`
- Compose configurations: `docker-compose.yml`, `docker-compose.dev.yml`, `docker-compose.ci.yml`, `docker-compose.test.yml`
- Railway service definitions: `backend/railway/*.json` (supervisor is a dashboard reference)
- Sample CSV import set: `documentation/07_data_and_seed/sample_import_48_classes/`

## Related Documents

- [Director Onboarding](ONBOARDING.md)
- [Project Overview](PROJECT_OVERVIEW.md)
- [Local Runtime Guide](../09_ops_observability/LOCAL_RUNTIME.md)
