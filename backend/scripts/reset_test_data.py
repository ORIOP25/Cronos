"""Reset named scheduler test targets on an isolated test database.

The command refuses any database that is not one of the owned test databases.
It deletes children before parents, bypasses row-level security as the table
owner, never contacts an external provider and is safe to repeat.
"""

from __future__ import annotations

import argparse
import re

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

TEST_DATABASE_NAMES = {"cronos_test_db", "cronos_ci_db"}
TEST_DATABASE_PATTERN = re.compile(r"^cronos_(?:test|ci)_gw\d+$")

TARGETS: dict[str, tuple[str, ...]] = {
    "versions": (
        "scheduler_recovery_reservation_v1",
        "scheduler_lesson_slice_v1",
        "scheduler_lesson_v1",
        "scheduler_proposal_v1",
        "scheduler_job_v1",
        "scheduler_version_v1",
    ),
    "evidence": (
        "scheduler_recovery_reservation_v1",
        "curricular_debt_settlement",
        "curricular_debt_revision",
        "curricular_debt",
        "curricular_execution_credit",
        "curricular_execution",
    ),
    "curriculum": (
        "curricular_requirement",
        "curricular_assignment",
    ),
}
TARGETS["scheduler-v1"] = TARGETS["versions"] + TARGETS["evidence"] + TARGETS["curriculum"]


def validate_test_database_url(value: str) -> str:
    if not value:
        raise ValueError("A test database URL is required.")
    database = make_url(value).database
    if database not in TEST_DATABASE_NAMES and not TEST_DATABASE_PATTERN.fullmatch(database or ""):
        raise ValueError(
            f"Refusing to reset database {database!r}; expected one of "
            f"{sorted(TEST_DATABASE_NAMES)} or a pytest worker database."
        )
    return value


def _sync_url(value: str) -> str:
    return value.replace("+asyncpg", "+psycopg2") if "+asyncpg" in value else value


def _ordered_tables(targets: tuple[str, ...]) -> list[str]:
    ordered: list[str] = []
    for target in targets:
        for table in TARGETS[target]:
            if table not in ordered:
                ordered.append(table)
    return ordered


def reset_test_data(database_url: str, targets: tuple[str, ...]) -> dict[str, object]:
    """Delete the named targets and return the row counts seen before reset."""
    validate_test_database_url(database_url)
    if not targets:
        raise ValueError("At least one reset target is required.")
    unknown = sorted(set(targets) - set(TARGETS))
    if unknown:
        raise ValueError(f"Unknown reset targets: {unknown}")
    tables = _ordered_tables(targets)
    engine = create_engine(_sync_url(database_url))
    before: dict[str, int] = {}
    try:
        with engine.begin() as connection:
            connection.execute(text("SET LOCAL row_security = off"))
            for table in tables:
                before[table] = int(
                    connection.scalar(text(f'SELECT count(*) FROM public."{table}"'))
                )
            for table in tables:
                connection.execute(text(f'DELETE FROM public."{table}"'))
    finally:
        engine.dispose()
    return {"targets": list(targets), "tables": tables, "rows_before": before}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m scripts.reset_test_data")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--target", action="append", required=True, dest="targets")
    args = parser.parse_args(argv)
    print(reset_test_data(args.database_url, tuple(args.targets)))


if __name__ == "__main__":
    main()
