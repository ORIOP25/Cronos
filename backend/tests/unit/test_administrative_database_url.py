import pytest

from app.db.database import async_database_url
from scripts import privacy


@pytest.mark.parametrize(
    "raw",
    [
        "postgresql://user:secret@db:5432/cronos",
        "postgres://user:secret@db:5432/cronos",
        "postgresql+psycopg2://user:secret@db:5432/cronos",
        "postgresql+asyncpg://user:secret@db:5432/cronos",
    ],
)
def test_every_postgres_url_form_uses_the_async_driver(raw):
    assert async_database_url(raw) == "postgresql+asyncpg://user:secret@db:5432/cronos"


def test_the_erasure_command_uses_the_async_driver_for_a_plain_url(monkeypatch):
    monkeypatch.setenv("MIGRATION_DATABASE_URL", "postgresql://user:secret@db:5432/cronos")
    assert privacy._administrative_url() == "postgresql+asyncpg://user:secret@db:5432/cronos"
