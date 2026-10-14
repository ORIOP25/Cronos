# Cronos Backend Workspace

FastAPI backend application for Cronos. Manages REST API endpoints, SQLAlchemy database models, Alembic migrations, Clerk authentication verification, PostgreSQL tenant isolation, Celery worker queues, and the OR-Tools CP-SAT solver engine.

## Python Setup and Local Runtime

1. **Create and activate Python virtual environment**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Linux / macOS
   .venv\Scripts\activate     # Windows PowerShell
   ```

2. **Install development dependencies**:
   ```bash
   pip install -r requirements-dev.txt
   ```

## Database Safety and Safeguards

Backend test fixtures automatically reset the target database schema. To prevent accidental data loss, `tests/db.py` refuses any database other than `cronos_test_db`, `cronos_ci_db`, or the per-worker `cronos_test_gw<N>` and `cronos_ci_gw<N>` databases. No override exists.

Run backend tests and database gates through the root runner and the maintenance container.
The [Command Reference](../documentation/00_getting_started/COMMAND_REFERENCE.md) lists the commands, prerequisites, and effects.
Do not run bare host-side `alembic` or audit scripts against an unknown database.

The migration chain has one baseline, `0001_scheduler_v1_baseline`, a PostgreSQL 18 schema dump. Add new migrations on top of it.
A database on the old chain must run `alembic downgrade base` with the previous code first; see the [Deployment Runbook](../documentation/09_ops_observability/DEPLOYMENT_RUNBOOK.md#migration-baseline-and-reset-rule).

## Coverage Requirements

CI runs the critical selection in `tests/critical_manifest.json` through `node ../scripts/test.mjs critical --scope backend`. The manifest owns the paths and the coverage thresholds.
