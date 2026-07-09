# Cronos Backend

FastAPI backend for Cronos, with SQLAlchemy async models, Alembic migrations,
PostgreSQL tenant isolation, Clerk-backed authentication, Celery workers, and
the scheduling engine services.

## Local Safety

Backend tests reset the target schema. The pytest fixture refuses to run
destructive tests unless the database name contains `test` or `ci`, unless
`ALLOW_NON_TEST_DATABASE=1` is set intentionally.

Use a dedicated database for local tests:

```powershell
$env:ENVIRONMENT='local'
$env:DATABASE_URL='postgresql+asyncpg://postgres:ci_pg_pass@localhost:55432/cronos_test_db'
$env:DATABASE_POOLING_ENABLED='false'
$env:SECRET_KEY='local-test-secret'
$env:RATELIMIT_ENABLED='false'
pytest tests/ -v
```

## Database Gates

Run these against a migrated test database before calling the backend baseline
healthy:

```powershell
alembic upgrade head
alembic current
alembic check
python scripts/audit_triggers.py
python -m scripts.audit_database_integrity
pytest tests/test_runtime_reality.py tests/test_rls_database_policies.py -m postgresql -v --tb=short
ruff check app scripts
```

## Coverage

Install local quality tooling with `pip install -r requirements-dev.txt`.
CI enforces 70% backend coverage with `pytest-cov` on the complete
database-backed suite.
