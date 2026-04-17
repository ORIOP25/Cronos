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

    # Bootstrap opcional e idempotente de admin para ambiente local Docker.
    # Objetivo: garantir login previsível após arranque "do zero".
    python - <<'PY'
import os
from datetime import date, time

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app import models
from app.core.security import hash_password

bootstrap_enabled = os.environ.get("BOOTSTRAP_DEFAULT_ADMIN", "0") == "1"
if not bootstrap_enabled:
    print("[entrypoint] Default admin bootstrap disabled (BOOTSTRAP_DEFAULT_ADMIN!=1).")
    raise SystemExit(0)

admin_email = os.environ.get("BOOTSTRAP_ADMIN_EMAIL", "admin@horariozen.local").strip().lower()
admin_password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "admin1234")
admin_name = os.environ.get("BOOTSTRAP_ADMIN_NAME", "Admin Horario Zen").strip() or "Admin Horario Zen"
org_name = os.environ.get("BOOTSTRAP_ORG_NAME", "Escola Demo Horario Zen").strip() or "Escola Demo Horario Zen"

if len(admin_password) < 6:
    raise SystemExit("[entrypoint] ERROR: BOOTSTRAP_ADMIN_PASSWORD must have at least 6 characters.")

raw_url = os.environ.get("DATABASE_URL", "")
base_url = raw_url.replace("+asyncpg", "").replace("+psycopg2", "")
if base_url.startswith("postgres://"):
    base_url = base_url.replace("postgres://", "postgresql://", 1)

if not base_url:
    raise SystemExit("[entrypoint] ERROR: DATABASE_URL is empty; cannot bootstrap default admin.")

today = date.today()
academic_year = f"{today.year}/{today.year + 1}"

engine = create_engine(base_url)
with Session(engine) as db:
    existing_admin = db.execute(
        select(models.User).where(models.User.email == admin_email)
    ).scalar_one_or_none()
    if existing_admin is not None:
        print(f"[entrypoint] Default admin already present: {admin_email}.")
        raise SystemExit(0)

    org = db.execute(select(models.Organization).order_by(models.Organization.id.asc())).scalar_one_or_none()
    if org is None:
        org = models.Organization(name=org_name, plan_status="active")
        db.add(org)
        db.flush()
        print(f"[entrypoint] Created default organization: {org_name} (id={org.id}).")

    org_settings = db.execute(
        select(models.OrganizationSettings).where(models.OrganizationSettings.org_id == org.id)
    ).scalar_one_or_none()
    if org_settings is None:
        org_settings = models.OrganizationSettings(
            org_id=org.id,
            academic_year=academic_year,
            school_start_date=date(today.year, 9, 1),
            school_target_end_date=date(today.year + 1, 6, 30),
            school_hard_end_date=date(today.year + 1, 7, 31),
            repair_stability_window_days=14,
            region_code="11",
            lunch_window_start=time(12, 0),
            lunch_window_end=time(14, 0),
            lunch_min_duration_minutes=60,
        )
        db.add(org_settings)

    default_admin = models.User(
        name=admin_name,
        email=admin_email,
        hashed_password=hash_password(admin_password),
        role=models.UserRole.admin,
        organization_id=org.id,
        is_active=True,
    )
    db.add(default_admin)
    db.commit()
    print(f"[entrypoint] Created default admin user: {admin_email}.")
PY
else
    echo "[entrypoint] Skipping Alembic migrations (RUN_MIGRATIONS=${RUN_MIGRATIONS})."
fi

echo "[entrypoint] Starting process..."
exec "$@"
