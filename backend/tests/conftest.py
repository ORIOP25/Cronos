# Ficheiro: backend/tests/conftest.py
import pytest
import pytest_asyncio
from typing import AsyncGenerator
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.db.database import Base, ASYNC_DB_URL
from app.api.deps import get_db
from app.main import app
from app.services import user_service
from app.schemas import UserCreate
from app.core.security import create_access_token

# 1. Configurar Engine de Teste (Usando Postgres)
# Usamos NullPool para garantir que as conexões são fechadas após cada teste
test_engine = create_async_engine(
    ASYNC_DB_URL,
    poolclass=NullPool,
    echo=False
)

TestingSessionLocal = async_sessionmaker(
    bind=test_engine, class_=AsyncSession, expire_on_commit=False
)

# 2. Fixture da Base de Dados (Setup e Teardown)
@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    # A) Criar Tabelas (Limpar tudo antes para garantir estado limpo)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    
    # B) Criar Sessão
    async with TestingSessionLocal() as session:
        yield session
    
    # C) Limpar no final (Opcional, pois o drop_all do início já trata disso)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

# 3. Fixture do Cliente API
@pytest_asyncio.fixture(scope="function")
async def async_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    # Override da dependência de BD
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    
    # Cliente HTTP Assíncrono
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    
    app.dependency_overrides.clear()

# 4. Fixture de Autenticação (User Token)
@pytest_asyncio.fixture(scope="function")
async def authorized_client(async_client: AsyncClient, db_session: AsyncSession) -> AsyncClient:
    email = "prof@teste.com"
    password = "password123"
    
    # Criar User na BD de teste
    user_in = UserCreate(email=email, password=password)
    await user_service.create_user(db_session, user_in)
    
    # Gerar Token
    access_token = create_access_token(data={"sub": email})
    
    # Injetar Token no Header
    async_client.headers.update({"Authorization": f"Bearer {access_token}"})
    return async_client