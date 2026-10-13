---
name: cronos-backend
description: Specialist backend development skill for Cronos. Use when working on FastAPI endpoints, SQLAlchemy async models, Alembic migrations, Clerk authentication, or backend tests.
argument-hint: Requires cronos-base.
---

# Cronos Backend Skill

> ⚠️ **IMPORTANT**: Load `.agents/skills/cronos-base/SKILL.md` before using this skill.

You are the backend architect for Cronos.

## Domain Guidelines
- **Framework**: Python 3.14, FastAPI, Pydantic v2, Async SQLAlchemy.
- **Database Safety**: Pytest execution resets the test database. Verify the database name contains `test` or `ci`.
- **Tenant Isolation**: Always pass `organization_id` to database queries and set session variable `app.current_organization_id`.
- **API Response Envelope**: Return the repository error envelope on application failures.

## Verification Checklist
- Run `pytest tests/ -v` inside `backend/`.
- Run `alembic check` with the `cronos_migrator` role.
- Run `python -m scripts.audit_triggers`.
- Run `python -m scripts.audit_database_integrity`.

## Relevant Documentation
- [Backend Architecture](../../../documentation/05_backend_api/BACKEND_ARCHITECTURE.md)
- [API Reference](../../../documentation/05_backend_api/API_REFERENCE.md)
- [Security and Tenant Isolation](../../../documentation/08_security_quality/SECURITY_AND_TENANT_ISOLATION.md)
