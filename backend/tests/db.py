from __future__ import annotations

from sqlalchemy.engine import make_url

TEST_DATABASE_NAMES = {"cronos_test_db", "cronos_ci_db"}


def validated_test_database_url(value: str | None) -> str:
    if not value:
        raise RuntimeError("TEST_DATABASE_URL is required for database tests")
    database = make_url(value).database
    if database not in TEST_DATABASE_NAMES:
        raise RuntimeError(
            f"Refusing destructive tests against database {database!r}; "
            f"expected one of {sorted(TEST_DATABASE_NAMES)}"
        )
    return value


def test_database_urls(value: str | None) -> tuple[str, str]:
    url = validated_test_database_url(value)
    sync = url.replace("+asyncpg", "").replace("postgres://", "postgresql://")
    return sync, sync.replace("postgresql://", "postgresql+asyncpg://")
