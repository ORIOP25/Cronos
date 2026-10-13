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

Backend test fixtures automatically reset the target database schema. To prevent accidental data loss, the test fixture execution enforces strict database name safeguards:
- Pytest refuses execution unless the database name contains `test` or `ci`.
- Overriding database safety requires explicit flag setting (`ALLOW_NON_TEST_DATABASE=1`).

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
with a database name containing `test` or `ci`.

## Coverage Requirements

CI runs the critical selection in `tests/critical_manifest.json` through `node ../scripts/test.mjs critical --scope backend`. The manifest owns the paths and the coverage thresholds.
