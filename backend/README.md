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

Execute backend tests against a dedicated test database:

```powershell
$env:ENVIRONMENT='local'
$env:TEST_DATABASE_URL='postgresql+asyncpg://cronos_app:app-ci@localhost:5432/cronos_test_db'
$env:DATABASE_URL=$env:TEST_DATABASE_URL
$env:DATABASE_POOLING_ENABLED='false'
$env:RATELIMIT_ENABLED='false'
pytest tests/ -v
```

## Mandatory Database Verification Gates

Run these verification commands before marking backend changes healthy:

```bash
docker compose -f ../docker-compose.yml -f ../docker-compose.dev.yml --profile maintenance run --rm db-maintenance
# Drift check uses the privileged cronos_migrator role. Do not run bare host-side alembic check.
docker compose -f ../docker-compose.yml -f ../docker-compose.dev.yml --profile maintenance run --rm db-maintenance alembic check
python -m scripts.audit_triggers
python -m scripts.audit_database_integrity
ruff check app scripts
```

Run migrations with the privileged `cronos_migrator` role. Run application tests
only against the database names listed above.

The migration chain has one baseline, `0001_scheduler_v1_baseline`, a PostgreSQL 18 schema dump. Add new migrations on top of it.
A database on the old chain must run `alembic downgrade base` with the previous code first; see the [Deployment Runbook](../documentation/09_ops_observability/DEPLOYMENT_RUNBOOK.md#migration-baseline-and-reset-rule).

## Coverage Requirements

CI runs the critical selection in `tests/critical_manifest.json` through `node ../scripts/test.mjs critical --scope backend`. The manifest owns the paths and the coverage thresholds.
