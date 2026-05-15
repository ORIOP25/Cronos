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


# ============================================================
# FIXTURES DE AUTENTICAÇÃO (Fase 3 — com mock + user DB)
# ============================================================

ADMIN_USER_ID = "user_admin_001"
TEACHER_USER_ID = "user_teacher_001"
MOCK_ORG_ID = "org_test_001"


@pytest_asyncio.fixture
async def clerk_admin_headers(db_session: AsyncSession):
    """Headers de admin com mock + user criado automaticamente na DB."""
    from unittest.mock import patch
    org, user = await create_org_and_user(
        db_session,
        clerk_user_id=ADMIN_USER_ID,
        email="admin@test.com",
        role="admin",
        clerk_org_id=MOCK_ORG_ID,
    )
    payload = mock_clerk_payload(ADMIN_USER_ID, org.clerk_org_id, "admin")
    patcher = patch("app.api.deps.get_clerk_payload", return_value=payload)
    patcher.start()
    yield {"Authorization": f"Bearer test_{ADMIN_USER_ID}"}
    patcher.stop()


@pytest_asyncio.fixture
async def clerk_teacher_headers(db_session: AsyncSession):
    """Headers de teacher com mock + user criado automaticamente na DB."""
    from unittest.mock import patch
    org, user = await create_org_and_user(
        db_session,
        clerk_user_id=TEACHER_USER_ID,
        email="teacher@test.com",
        role="teacher",
        clerk_org_id=MOCK_ORG_ID + "_t",
    )
    payload = mock_clerk_payload(TEACHER_USER_ID, org.clerk_org_id, "member")
    patcher = patch("app.api.deps.get_clerk_payload", return_value=payload)
    patcher.start()
    yield {"Authorization": f"Bearer test_{TEACHER_USER_ID}"}
    patcher.stop()


@pytest.fixture
def admin_token_headers(clerk_admin_headers) -> dict:
    """Alias compatível com testes que usam admin_token_headers: dict."""
    return clerk_admin_headers


@pytest.fixture
def clerk_auth_headers(clerk_admin_headers):
    """Factory de headers — compatível com código existente."""
    def _headers(clerk_user_id="user_test_admin", org_id="org_test_1", role="admin"):
        return clerk_admin_headers
    return _headers


async def create_teacher_user(
    db_session: AsyncSession,
    *,
    clerk_user_id: str,
    email: str | None = None,
    name: str | None = None,
    org_id: int,
    teacher_id: int,
) -> models.User:
    """Cria um User com role=teacher e teacher_id vinculado — atalho para testes de professor."""
    user = models.User(
        clerk_user_id=clerk_user_id,
        email=email or f"{clerk_user_id}@test.com",
        name=name or "Teacher User",
        role="teacher",
        organization_id=org_id,
        teacher_id=teacher_id,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user
