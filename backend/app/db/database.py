# Ficheiro: app/db/database.py

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool

from app.config import settings


raw_url = str(settings.DATABASE_URL)
base_url = raw_url.replace("+asyncpg", "").replace("+psycopg2", "")
if base_url.startswith("postgres://"):
    base_url = base_url.replace("postgres://", "postgresql://", 1)

SYNC_DB_URL = base_url
ASYNC_DB_URL = base_url.replace("postgresql://", "postgresql+asyncpg://")


async_engine_kwargs = {"echo": False}
if settings.DATABASE_POOLING_ENABLED:
    async_engine_kwargs["pool_pre_ping"] = True
else:
    async_engine_kwargs["poolclass"] = NullPool

engine_async = create_async_engine(ASYNC_DB_URL, **async_engine_kwargs)

SessionLocal = async_sessionmaker(
    bind=engine_async,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

engine_sync = create_engine(
    SYNC_DB_URL,
    echo=False,
    pool_pre_ping=True,
)

SessionLocalSync = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine_sync,
)


class Base(DeclarativeBase):
    pass
