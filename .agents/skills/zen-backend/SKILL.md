# Zen Backend Skill

> ⚠️ **IMPORTANT**: This skill REQUIRES `.agents/skills/SKILL_BASE.md` to be loaded first.
> The base skill contains shared rules (4 pillars, delivery protocol, documentation workflow, safety rules).
> Always load SKILL_BASE.md + this skill together.

You are the backend architect for Cronos.

## 1. Stack & Guardrails
- **Stack**: Python 3.12, FastAPI, SQLAlchemy Async, Pydantic v2.
- **Dependencies**: Use `Annotated` for FastAPI dependencies.
- **Transactions**: Use atomic transactions for critical operations.
- **Error Handling**: No `bare except`. Keep endpoint responses documented (including HTTPException status codes).
- **Literals**: Prefer constants for repeated literals.
- **Performance**: Prevent N+1 patterns; use `selectinload` / `joinedload` where appropriate. Keep queries index-friendly. Treat cache as optimization, never as source of truth.
- **Tenant Isolation**: Tenant isolation by `organization_id` is mandatory in every query and mutation.
- **Models**: Use `Mapped[T] = mapped_column(...)` style; do NOT use legacy `Column()`.

## 2. Key Files
- `app/models.py` — SQLAlchemy ORM models (Mapped[T] style)
- `app/schemas.py` — Pydantic v2 schemas
- `app/config.py` — Settings from .env (Pydantic BaseSettings)
- `app/db/database.py` — Async + Sync engines, SessionLocal factories
- `app/api/deps.py` — FastAPI dependencies (auth, DB sessions)
- `app/core/security.py` — JWT + bcrypt
- `app/services/` — Business logic layer
- `alembic/versions/` — Database migrations
