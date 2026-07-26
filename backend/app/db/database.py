# Ficheiro: app/db/database.py

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import settings

raw_url = str(settings.DATABASE_URL)
base_url = raw_url.replace("+asyncpg", "").replace("+psycopg2", "")
if base_url.startswith("postgres://"):
    base_url = base_url.replace("postgres://", "postgresql://", 1)

async_db_url = base_url.replace("postgresql://", "postgresql+asyncpg://")


async_engine_kwargs = {"echo": False}
if settings.DATABASE_POOLING_ENABLED:
    async_engine_kwargs["pool_pre_ping"] = True
else:
    async_engine_kwargs["poolclass"] = NullPool

engine_async = create_async_engine(async_db_url, **async_engine_kwargs)

SessionLocal = async_sessionmaker(
    bind=engine_async,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass
