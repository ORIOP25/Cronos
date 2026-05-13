# Ficheiro: backend/tests/conftest.py
#
# CRÍTICO: RATELIMIT_ENABLED deve ser definido ANTES de qualquer import da app.
import os
os.environ["RATELIMIT_ENABLED"] = "false"

import pytest
import pytest_asyncio
from typing import AsyncGenerator
from uuid import uuid4
from httpx import AsyncClient, ASGITransport
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.db.database import Base, ASYNC_DB_URL, SYNC_DB_URL
from app.api.deps import get_db
from app.main import app
from app import models
from app.models import UserRole

# --- Engines de Teste ---
test_engine = create_async_engine(ASYNC_DB_URL, poolclass=NullPool, echo=False)
sync_test_engine = create_engine(SYNC_DB_URL, echo=False)
SyncTestSession = sessionmaker(bind=sync_test_engine, autocommit=False, autoflush=False)

TestingSessionLocal = async_sessionmaker(
    bind=test_engine, class_=AsyncSession, expire_on_commit=False
)

# --- Fixture: BD Assíncrona ---
@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with TestingSessionLocal() as session:
        app.dependency_overrides[get_db] = lambda: session
        yield session
        app.dependency_overrides.pop(get_db, None)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

# --- Fixture: BD Síncrona ---
@pytest.fixture
def sync_db(db_session):
    db = SyncTestSession()
    try:
        yield db
    finally:
        db.close()

# --- Fixture: Cliente API ---
@pytest_asyncio.fixture(scope="function")
async def async_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ============================================================
# HELPERS COM CLERK (mock get_clerk_payload)
# ============================================================

async def create_org_and_user(
    db_session: AsyncSession,
    *,
    clerk_user_id: str,
    email: str | None = None,
    name: str | None = None,
    role: str = "admin",
    org_name: str = "Escola Teste",
    clerk_org_id: str | None = None,
    teacher_id: int | None = None,
) -> tuple[models.Organization, models.User]:
    org = models.Organization(
        name=org_name,
        clerk_org_id=clerk_org_id or f"org_{uuid4().hex[:8]}",
        plan_status="active",
    )
    db_session.add(org)
    await db_session.flush()

    user = models.User(
        clerk_user_id=clerk_user_id,
        email=email or f"{clerk_user_id}@test.com",
        name=name or "Test User",
        role=role,
        organization_id=org.id,
        teacher_id=teacher_id,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    return org, user


def mock_clerk_payload(clerk_user_id: str, org_id: str | None = None, role: str = "admin") -> dict:
    payload = {"sub": clerk_user_id}
    if org_id:
        payload["o"] = {"id": org_id, "rol": role}
    return payload
