"""Provision restricted PostgreSQL roles for Cronos."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping

import psycopg2
from psycopg2 import sql

ROLE_DEFINITIONS = {
    "cronos_migrator": "LOGIN NOSUPERUSER BYPASSRLS",
    "cronos_app": "LOGIN NOSUPERUSER NOBYPASSRLS",
    "cronos_auth_definer": "NOLOGIN NOSUPERUSER BYPASSRLS",
}


def _required(environment: Mapping[str, str], name: str) -> str:
    value = environment.get(name, "")
    if not value:
        raise RuntimeError(f"{name} is required.")
    return value


def _ensure_role(cursor, role_name: str, attributes: str) -> None:
    cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role_name,))
    if cursor.fetchone() is None:
        cursor.execute(
            sql.SQL("CREATE ROLE {} " + attributes).format(sql.Identifier(role_name))
        )
    cursor.execute(sql.SQL("ALTER ROLE {} " + attributes).format(sql.Identifier(role_name)))


def provision(environment: Mapping[str, str] = os.environ) -> None:
    database_url = _required(environment, "BOOTSTRAP_DATABASE_URL")
    migrator_password = _required(environment, "CRONOS_MIGRATOR_PASSWORD")
    app_password = _required(environment, "CRONOS_APP_PASSWORD")

    with psycopg2.connect(database_url) as connection:
        with connection.cursor() as cursor:
            for role_name, attributes in ROLE_DEFINITIONS.items():
                _ensure_role(cursor, role_name, attributes)
            cursor.execute(
                sql.SQL("ALTER ROLE {} PASSWORD %s").format(
                    sql.Identifier("cronos_migrator")
                ),
                (migrator_password,),
            )
            cursor.execute(
                sql.SQL("ALTER ROLE {} PASSWORD %s").format(sql.Identifier("cronos_app")),
                (app_password,),
            )
            cursor.execute(
                sql.SQL("GRANT {} TO {}").format(
                    sql.Identifier("cronos_auth_definer"),
                    sql.Identifier("cronos_migrator"),
                )
            )
            database_name = connection.get_dsn_parameters()["dbname"]
            cursor.execute(
                sql.SQL("ALTER DATABASE {} OWNER TO {}").format(
                    sql.Identifier(database_name),
                    sql.Identifier("cronos_migrator"),
                )
            )
            cursor.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    sql.Identifier(database_name),
                    sql.Identifier("cronos_app"),
                )
            )


def main() -> int:
    try:
        provision()
    except Exception as exc:
        print(f"Database bootstrap failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    print("Database bootstrap completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
