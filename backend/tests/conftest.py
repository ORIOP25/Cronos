# Ficheiro: backend/tests/conftest.py
#
# CRÍTICO: RATELIMIT_ENABLED deve ser definido ANTES de qualquer import da app.
import os
os.environ["RATELIMIT_ENABLED"] = "false"

import pytest
import pytest_asyncio
from typing import AsyncGenerator
from httpx import AsyncClient, ASGITransport
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.db.database import Base, ASYNC_DB_URL, SYNC_DB_URL
from app.api.deps import get_db
from app.main import app
from app.services import user_service
from app.schemas import UserCreate
from app.core.security import create_access_token
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
        yield session
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

# --- Fixture: BD Síncrona (partilhada — depende de db_session para garantir tabelas) ---
@pytest.fixture
def sync_db(db_session):
    """Sessão síncrona isolada com savepoint (rollback no teardown).
    Depende de db_session para garantir que as tabelas foram criadas."""
    db = SyncTestSession()
    db.begin_nested()
    try:
        yield db
    finally:
        db.rollback()
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

# --- Fixture: Autenticação (User genérico) ---
@pytest_asyncio.fixture(scope="function")
async def authorized_client(async_client: AsyncClient, db_session: AsyncSession) -> AsyncClient:
    email = "prof@teste.com"
    password = "password123"
    user_in = UserCreate(email=email, password=password)
    await user_service.create_user(db_session, user_in)
    access_token = create_access_token(data={"sub": email})
    async_client.headers.update({"Authorization": f"Bearer {access_token}"})
    return async_client

# --- Fixture: Autenticação Admin ---
@pytest_asyncio.fixture(scope="function")
async def admin_token_headers(async_client: AsyncClient, db_session: AsyncSession) -> dict:
    from app import models
    from app.core.security import hash_password

    org = models.Organization(name="Escola Teste", plan_status="active")
    db_session.add(org)
    await db_session.flush()

    admin_user = models.User(
        email="admin@escola.com",
        hashed_password=hash_password("adminpass"),
        is_active=True,
        role=UserRole.admin,
        organization_id=org.id,
    )
    db_session.add(admin_user)
    await db_session.commit()

    access_token = create_access_token(data={"sub": "admin@escola.com"})
    return {"Authorization": f"Bearer {access_token}"}