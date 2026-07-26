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
$env:DATABASE_URL='postgresql+asyncpg://postgres:ci_pg_pass@localhost:55432/cronos_test_db'
$env:DATABASE_POOLING_ENABLED='false'
$env:SECRET_KEY='local-test-secret'
$env:RATELIMIT_ENABLED='false'
pytest tests/ -v
```

## Mandatory Database Verification Gates

Run these verification commands before marking backend changes healthy:

```bash
alembic upgrade head
alembic current
alembic check
python scripts/audit_triggers.py
python -m scripts.audit_database_integrity
ruff check app scripts
```

## Coverage Requirements

CI enforces a minimum threshold of **70% backend code coverage** across the full database-backed test suite.
