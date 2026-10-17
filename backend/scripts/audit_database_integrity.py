"""Read-only structural and relational integrity audit for PostgreSQL."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable

from sqlalchemy import inspect, text

from app import models  # noqa: F401 - registers SQLAlchemy metadata
from app.db.database import Base, engine_async

IGNORED_TABLES = {"alembic_version"}


def _quoted(preparer, identifier: str) -> str:
    return preparer.quote(identifier)


def _duplicate_groups_sql(
    preparer,
    table: str,
    columns: Iterable[str],
) -> str:
    quoted_columns = ", ".join(_quoted(preparer, column) for column in columns)
    quoted_table = _quoted(preparer, table)
    populated_key = " AND ".join(f"{_quoted(preparer, column)} IS NOT NULL" for column in columns)
    return (
        "SELECT COUNT(*) FROM ("
        f"SELECT {quoted_columns} FROM public.{quoted_table} "
        f"WHERE {populated_key} "
        f"GROUP BY {quoted_columns} HAVING COUNT(*) > 1"
        ") duplicate_groups"
    )


def _orphan_count_sql(preparer, table: str, foreign_key: dict) -> str:
    local_columns = foreign_key["constrained_columns"]
    remote_columns = foreign_key["referred_columns"]
    remote_table = foreign_key["referred_table"]

    local_not_null = " AND ".join(
        f"child.{_quoted(preparer, column)} IS NOT NULL" for column in local_columns
    )
    reference_match = " AND ".join(
        f"parent.{_quoted(preparer, remote)} = child.{_quoted(preparer, local)}"
        for local, remote in zip(local_columns, remote_columns, strict=True)
    )

    return (
        f"SELECT COUNT(*) FROM public.{_quoted(preparer, table)} child "
        f"WHERE {local_not_null} AND NOT EXISTS ("
        f"SELECT 1 FROM public.{_quoted(preparer, remote_table)} parent "
        f"WHERE {reference_match}"
        ")"
    )


def _unique_column_sets(inspector, table: str) -> set[tuple[str, ...]]:
    column_sets: set[tuple[str, ...]] = set()
    primary_key = inspector.get_pk_constraint(table, schema="public")
    if primary_key.get("constrained_columns"):
        column_sets.add(tuple(primary_key["constrained_columns"]))

    for constraint in inspector.get_unique_constraints(table, schema="public"):
        columns = tuple(constraint.get("column_names") or ())
        if columns:
            column_sets.add(columns)

    for index in inspector.get_indexes(table, schema="public"):
        columns = tuple(index.get("column_names") or ())
        is_partial = bool(index.get("dialect_options", {}).get("postgresql_where"))
        # Expression indexes expose ``None`` in ``column_names``; there is no
        # plain column to quote, and the database already enforces them.
        if index.get("unique") and columns and None not in columns and not is_partial:
            column_sets.add(columns)

    return column_sets


def _audit_unique_keys(connection, inspector, preparer, table: str) -> list[str]:
    errors = []
    for columns in sorted(_unique_column_sets(inspector, table)):
        duplicate_groups = connection.execute(
            text(_duplicate_groups_sql(preparer, table, columns))
        ).scalar_one()
        if duplicate_groups:
            errors.append(f"{table} has {duplicate_groups} duplicate group(s) for {columns}")
    return errors


def _audit_foreign_keys(connection, inspector, preparer, table: str) -> list[str]:
    errors = []
    for foreign_key in inspector.get_foreign_keys(table, schema="public"):
        if foreign_key.get("referred_schema") not in (None, "public"):
            continue
        orphan_count = connection.execute(
            text(_orphan_count_sql(preparer, table, foreign_key))
        ).scalar_one()
        if orphan_count:
            errors.append(
                f"{table} has {orphan_count} orphan row(s) for "
                f"{tuple(foreign_key['constrained_columns'])}"
            )
    return errors


def _audit_rls_policies(connection) -> list[str]:
    errors = []
    unhardened = (
        connection.execute(
            text(
                """
            SELECT c.relname
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN information_schema.columns col
              ON col.table_schema = n.nspname AND col.table_name = c.relname
            WHERE n.nspname = 'public'
              AND c.relkind = 'r'
              AND col.column_name = 'organization_id'
              AND (NOT c.relrowsecurity OR NOT c.relforcerowsecurity)
            ORDER BY c.relname
            """
            )
        )
        .scalars()
        .all()
    )
    if unhardened:
        errors.append(f"Tables missing row security or forced row security: {unhardened}")
    return errors


def _audit_connection(connection) -> list[str]:
    errors: list[str] = []

    inspector = inspect(connection)
    preparer = connection.dialect.identifier_preparer
    actual_tables = set(inspector.get_table_names(schema="public")) - IGNORED_TABLES
    expected_tables = set(Base.metadata.tables)

    for table in sorted(expected_tables - actual_tables):
        errors.append(f"missing table: public.{table}")
    for table in sorted(actual_tables - expected_tables):
        errors.append(f"unexpected table: public.{table}")

    for table in sorted(actual_tables & expected_tables):
        errors.extend(_audit_unique_keys(connection, inspector, preparer, table))
        errors.extend(_audit_foreign_keys(connection, inspector, preparer, table))

    # Audit required check constraints
    check_constraints_sql = """
    SELECT conname
    FROM pg_constraint
    WHERE connamespace = 'public'::regnamespace
      AND contype = 'c'
    """
    existing_checks = set(connection.execute(text(check_constraints_sql)).scalars())
    required_checks = {
        "chk_organization_foundation_completed_at_required",
        "chk_organization_first_real_schedule_requires_completed",
        "chk_organization_foundation_draft_version",
        "chk_organization_foundation_draft_current_step",
        "chk_legal_acceptance_authority",
        "chk_legal_acceptance_controller_name",
        "chk_legal_acceptance_registration_number",
        "chk_legal_acceptance_address",
        "chk_legal_acceptance_contact_email",
        "chk_legal_acceptance_representative_name",
        "chk_legal_acceptance_representative_role",
    }
    missing_checks = required_checks - existing_checks
    if missing_checks:
        errors.append(f"Missing required check constraints: {sorted(missing_checks)}")

    errors.extend(_audit_rls_policies(connection))

    legal_policies = set(
        connection.execute(
            text(
                "SELECT policyname FROM pg_policies "
                "WHERE schemaname = 'public' AND tablename = 'organization_legal_acceptance'"
            )
        ).scalars()
    )
    required_legal_policies = {
        "organization_legal_acceptance_select",
        "organization_legal_acceptance_insert",
    }
    missing_legal_policies = required_legal_policies - legal_policies
    if missing_legal_policies:
        errors.append(f"Missing legal acceptance RLS policies: {sorted(missing_legal_policies)}")
    return errors


async def audit_database() -> list[str]:
    async with engine_async.connect() as connection:
        return await connection.run_sync(_audit_connection)


def main() -> None:
    errors = asyncio.run(audit_database())
    if errors:
        details = "\n- ".join(errors)
        raise SystemExit(f"Database integrity audit failed:\n- {details}")
    print("Database integrity audit passed: tables, unique keys, and foreign keys are consistent.")


if __name__ == "__main__":
    main()
