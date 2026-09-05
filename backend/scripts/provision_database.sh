#!/bin/sh
set -eu

: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${CRONOS_MIGRATOR_PASSWORD:?CRONOS_MIGRATOR_PASSWORD is required}"
: "${CRONOS_APP_PASSWORD:?CRONOS_APP_PASSWORD is required}"

psql --set=ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=migrator_password="$CRONOS_MIGRATOR_PASSWORD" \
  --set=app_password="$CRONOS_APP_PASSWORD" \
  --set=db_name="$POSTGRES_DB" <<'SQL'
DO $$ BEGIN
  CREATE ROLE cronos_migrator LOGIN NOSUPERUSER BYPASSRLS;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
  CREATE ROLE cronos_app LOGIN NOSUPERUSER NOBYPASSRLS;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
  CREATE ROLE cronos_auth_definer NOLOGIN NOSUPERUSER BYPASSRLS;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
ALTER ROLE cronos_migrator PASSWORD :'migrator_password';
ALTER ROLE cronos_migrator NOSUPERUSER BYPASSRLS;
ALTER ROLE cronos_app PASSWORD :'app_password';
ALTER ROLE cronos_auth_definer NOLOGIN NOSUPERUSER BYPASSRLS;
GRANT cronos_auth_definer TO cronos_migrator;
ALTER DATABASE :"db_name" OWNER TO cronos_migrator;
GRANT CONNECT ON DATABASE :"db_name" TO cronos_app;
SQL

for worker in 0 1 2 3; do
  worker_db="${POSTGRES_DB}_gw${worker}"
  psql --set=ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
    --set=db_name="$worker_db" <<'SQL'
SELECT format('CREATE DATABASE %I OWNER cronos_migrator', :'db_name')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'db_name')\gexec
GRANT CONNECT ON DATABASE :"db_name" TO cronos_app;
SQL
done
