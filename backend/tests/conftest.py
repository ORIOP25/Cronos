import os

# Keep unit collection independent from local .env files and live services.
os.environ.setdefault("ENVIRONMENT", "local")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://cronos_app:test@127.0.0.1:5432/cronos_test_db",
)
os.environ.setdefault(
    "MIGRATION_DATABASE_URL",
    "postgresql+psycopg2://cronos_migrator:test@127.0.0.1:5432/cronos_test_db",
)
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:9/0")
os.environ.setdefault("CELERY_BROKER_URL", "redis://127.0.0.1:9/0")
os.environ["DATABASE_POOLING_ENABLED"] = "false"
os.environ["RATELIMIT_ENABLED"] = "false"
pytest_plugins = ("tests._support.db_fixtures",)
