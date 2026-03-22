#!/bin/bash
set -e

# DB connection info (from docker-compose service name: "db")
DB_HOST=${DB_HOST:-db}
DB_PORT=${DB_PORT:-5432}
RUN_MIGRATIONS=${RUN_MIGRATIONS:-1}

echo "[entrypoint] Waiting for PostgreSQL at ${DB_HOST}:${DB_PORT}..."
attempt=0
max_attempts=30
while [[ $attempt -lt $max_attempts ]]; do
    if nc -z "$DB_HOST" "$DB_PORT" 2>/dev/null; then
        echo "[entrypoint] PostgreSQL is ready."
        break
    fi
    attempt=$((attempt + 1))
    echo "[entrypoint] Attempt ${attempt}/${max_attempts}: waiting ${DB_HOST}:${DB_PORT}"
    sleep 1
done

if [[ $attempt -eq $max_attempts ]]; then
    echo "[entrypoint] ERROR: PostgreSQL did not respond after ${max_attempts} attempts."
    exit 1
fi

if [[ "$RUN_MIGRATIONS" == "1" ]]; then
    echo "[entrypoint] Running Alembic migrations..."

    # Repair inconsistent migration states before upgrade.
    # Case handled explicitly: alembic_version exists, but core tables were never created.
    python - <<'PY'
import os
import subprocess
from sqlalchemy import create_engine, text

raw_url = os.environ.get("DATABASE_URL", "")
base_url = raw_url.replace("+asyncpg", "").replace("+psycopg2", "")
if base_url.startswith("postgres://"):
    base_url = base_url.replace("postgres://", "postgresql://", 1)

needs_stamp_head = False
needs_reset_to_base = False
if base_url:
    engine = create_engine(base_url)
    with engine.connect() as conn:
        table_exists = conn.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'organization'
            )
        """)).scalar()
        user_table_exists = conn.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'user'
            )
        """)).scalar()
        version_exists = conn.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'alembic_version'
            )
        """)).scalar()
        non_version_table_count = conn.execute(text("""
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name <> 'alembic_version'
        """)).scalar() or 0

        needs_stamp_head = bool(table_exists) and not bool(version_exists)

        # Inconsistent state: DB says "head" but no real schema exists.
        if bool(version_exists) and not bool(user_table_exists):
            if int(non_version_table_count) == 0:
                needs_reset_to_base = True
            else:
                raise SystemExit(
                    "[entrypoint] ERROR: alembic_version exists but required tables are missing "
                    "and a partial schema was detected. Manual intervention required."
                )

if needs_reset_to_base:
    print("[entrypoint] Inconsistent stamped DB detected. Resetting revision to base...")
    subprocess.run(["alembic", "stamp", "base"], check=True)

if needs_stamp_head:
    print("[entrypoint] Existing schema detected without alembic_version; stamping head...")
    subprocess.run(["alembic", "stamp", "head"], check=True)
PY

    alembic upgrade head

    # Hard guard: API must never boot without core schema.
    python - <<'PY'
import os
from sqlalchemy import create_engine, text

raw_url = os.environ.get("DATABASE_URL", "")
base_url = raw_url.replace("+asyncpg", "").replace("+psycopg2", "")
if base_url.startswith("postgres://"):
    base_url = base_url.replace("postgres://", "postgresql://", 1)

if base_url:
    engine = create_engine(base_url)
    with engine.connect() as conn:
        user_table_exists = conn.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'user'
            )
        """)).scalar()
        if not bool(user_table_exists):
            raise SystemExit("[entrypoint] ERROR: migrations finished but table 'user' is still missing.")
PY

    echo "[entrypoint] Alembic migrations completed."
else
    echo "[entrypoint] Skipping Alembic migrations (RUN_MIGRATIONS=${RUN_MIGRATIONS})."
fi

echo "[entrypoint] Starting process..."
exec "$@"
