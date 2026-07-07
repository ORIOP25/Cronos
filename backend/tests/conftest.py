# Ficheiro: backend/tests/conftest.py
#
# CRÍTICO: RATELIMIT_ENABLED deve ser definido ANTES de qualquer import da app.
import os
os.environ["RATELIMIT_ENABLED"] = "false"

import pytest
import pytest_asyncio
from typing import AsyncGenerator
from uuid import uuid4
from alembic import command
from alembic.config import Config
from httpx import AsyncClient, ASGITransport
from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.engine import make_url
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


def _assert_safe_test_database() -> None:
    db_name = make_url(SYNC_DB_URL).database or ""
    if os.environ.get("ALLOW_NON_TEST_DATABASE") == "1":
        return
    if any(marker in db_name.lower() for marker in ("test", "ci")):
        return
    raise RuntimeError(
        "Refusing to run destructive tests against a non-test database. "
        f"Current database is {db_name!r}. Use a dedicated *_test database "
        "or set ALLOW_NON_TEST_DATABASE=1 intentionally."
    )


def _alembic_config() -> Config:
    backend_root = os.path.dirname(os.path.dirname(__file__))
    return Config(os.path.join(backend_root, "alembic.ini"))


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _truncate_public_tables() -> None:
    with sync_test_engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = 'public'
                  AND tablename <> 'alembic_version'
                ORDER BY tablename
                """
            )
        ).scalars().all()
        if rows:
            table_list = ", ".join(f"public.{_quote_identifier(table)}" for table in rows)
            conn.execute(text(f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE"))


@pytest.fixture(scope="session", autouse=True)
def migrated_test_database():
    """Build the test schema through Alembic so triggers/RLS/functions exist."""
    _assert_safe_test_database()
    with sync_test_engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.execute(text("GRANT ALL ON SCHEMA public TO public"))
    command.upgrade(_alembic_config(), "head")
    yield
    _truncate_public_tables()

# --- Fixture: BD Assíncrona ---
@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    _truncate_public_tables()
    async with TestingSessionLocal() as session:
        yield session
    _truncate_public_tables()


@pytest_asyncio.fixture(scope="function")
async def orm_schema_session() -> AsyncGenerator[AsyncSession, None]:
    """Opt-in ORM-only fixture for tests that intentionally bypass Alembic."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with TestingSessionLocal() as session:
        yield session
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
    command.upgrade(_alembic_config(), "head")

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
    app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture(scope="function")
async def real_async_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """ASGI client that uses the app's real SessionLocal per request."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


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
    """Cria org + user. Idempotente: se já existirem, retorna os existentes."""
    from sqlalchemy.future import select as _sel

    async def _ensure_membership(org: models.Organization, user: models.User) -> None:
        membership = (await db_session.execute(
            _sel(models.OrganizationMembership).where(
                models.OrganizationMembership.organization_id == org.id,
                models.OrganizationMembership.account_id == user.id,
            )
        )).scalar_one_or_none()
        if membership is None:
            capability = models.MembershipCapability.admin if role == "admin" else models.MembershipCapability.teacher
            expected_role = models.ClerkOrganizationRole.admin if role == "admin" else models.ClerkOrganizationRole.member
            membership = models.OrganizationMembership(
                organization_id=org.id,
                account_id=user.id,
                organization_display_name=user.name or user.email,
                lifecycle_status=models.MembershipLifecycleStatus.active,
                access_status=models.MembershipAccessStatus.active,
                teacher_access_mode=models.TeacherAccessMode.platform if capability == models.MembershipCapability.teacher else None,
                expected_clerk_role=expected_role,
            )
            db_session.add(membership)
            await db_session.flush()
            db_session.add(models.OrganizationMembershipCapability(
                organization_membership_id=membership.id,
                capability=capability,
            ))
        if user.teacher_id:
            teacher = await db_session.get(models.Teacher, user.teacher_id)
            if teacher is not None and teacher.organization_membership_id is None:
                teacher.organization_membership_id = membership.id

    # Verificar se user já existe
    existing_user = (await db_session.execute(
        _sel(models.User).where(models.User.clerk_user_id == clerk_user_id)
    )).scalar_one_or_none()
    if existing_user is not None:
        org = (await db_session.execute(
            _sel(models.Organization).where(models.Organization.id == existing_user.organization_id)
        )).scalar_one_or_none()
        if org is not None:
            CLERK_ORG_BY_USER[clerk_user_id] = org.clerk_org_id
            await _ensure_membership(org, existing_user)
            await db_session.commit()
        return org, existing_user

    # Verificar se org já existe
    c_org_id = clerk_org_id or f"org_{uuid4().hex[:8]}"
    org = (await db_session.execute(
        _sel(models.Organization).where(models.Organization.clerk_org_id == c_org_id)
    )).scalar_one_or_none()

    if org is None:
        org = models.Organization(
            name=org_name,
            clerk_org_id=c_org_id,
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
    await db_session.flush()
    CLERK_ORG_BY_USER[clerk_user_id] = org.clerk_org_id
    await _ensure_membership(org, user)
    await db_session.commit()
    return org, user


async def ensure_membership_capabilities(
    db_session: AsyncSession,
    *,
    organization_id: int,
    user: models.User,
    capabilities: list[models.MembershipCapability],
    display_name: str | None = None,
    expected_clerk_role: models.ClerkOrganizationRole | None = None,
    teacher_access_mode: models.TeacherAccessMode | None = None,
) -> models.OrganizationMembership:
    """Create or update the local membership shape used by the Clerk baseline."""
    from sqlalchemy.future import select as _sel

    organization = await db_session.get(models.Organization, organization_id)
    if organization is not None and not organization.clerk_org_id:
        organization.clerk_org_id = f"org_test_{organization_id}"
        await db_session.flush()
    if organization is not None and user.clerk_user_id:
        CLERK_ORG_BY_USER[user.clerk_user_id] = organization.clerk_org_id

    membership = (await db_session.execute(
        _sel(models.OrganizationMembership).where(
            models.OrganizationMembership.organization_id == organization_id,
            models.OrganizationMembership.account_id == user.id,
        )
    )).scalar_one_or_none()
    if membership is None:
        membership = models.OrganizationMembership(
            organization_id=organization_id,
            account_id=user.id,
            organization_display_name=display_name or user.name or user.email,
            lifecycle_status=models.MembershipLifecycleStatus.active,
            access_status=models.MembershipAccessStatus.active,
            teacher_access_mode=teacher_access_mode,
            expected_clerk_role=expected_clerk_role,
        )
        db_session.add(membership)
        await db_session.flush()
    else:
        membership.lifecycle_status = models.MembershipLifecycleStatus.active
        membership.access_status = models.MembershipAccessStatus.active
        membership.teacher_access_mode = teacher_access_mode
        membership.expected_clerk_role = expected_clerk_role

    existing = set((await db_session.execute(
        _sel(models.OrganizationMembershipCapability.capability).where(
            models.OrganizationMembershipCapability.organization_membership_id == membership.id,
        )
    )).scalars().all())
    for capability in capabilities:
        if capability not in existing:
            db_session.add(models.OrganizationMembershipCapability(
                organization_membership_id=membership.id,
                capability=capability,
            ))
    await db_session.flush()
    return membership


def ensure_membership_capabilities_sync(
    db_session,
    *,
    organization_id: int,
    user: models.User,
    capabilities: list[models.MembershipCapability],
    display_name: str | None = None,
    expected_clerk_role: models.ClerkOrganizationRole | None = None,
    teacher_access_mode: models.TeacherAccessMode | None = None,
) -> models.OrganizationMembership:
    """Synchronous twin for legacy service tests that now need Clerk memberships."""
    from sqlalchemy import select as _sel

    organization = db_session.get(models.Organization, organization_id)
    if organization is not None and not organization.clerk_org_id:
        organization.clerk_org_id = f"org_test_{organization_id}"
        db_session.flush()
    if organization is not None and user.clerk_user_id:
        CLERK_ORG_BY_USER[user.clerk_user_id] = organization.clerk_org_id

    membership = db_session.execute(
        _sel(models.OrganizationMembership).where(
            models.OrganizationMembership.organization_id == organization_id,
            models.OrganizationMembership.account_id == user.id,
        )
    ).scalar_one_or_none()
    if membership is None:
        membership = models.OrganizationMembership(
            organization_id=organization_id,
            account_id=user.id,
            organization_display_name=display_name or user.name or user.email,
            lifecycle_status=models.MembershipLifecycleStatus.active,
            access_status=models.MembershipAccessStatus.active,
            teacher_access_mode=teacher_access_mode,
            expected_clerk_role=expected_clerk_role,
        )
        db_session.add(membership)
        db_session.flush()
    else:
        membership.lifecycle_status = models.MembershipLifecycleStatus.active
        membership.access_status = models.MembershipAccessStatus.active
        membership.teacher_access_mode = teacher_access_mode
        membership.expected_clerk_role = expected_clerk_role

    existing = set(db_session.execute(
        _sel(models.OrganizationMembershipCapability.capability).where(
            models.OrganizationMembershipCapability.organization_membership_id == membership.id,
        )
    ).scalars().all())
    for capability in capabilities:
        if capability not in existing:
            db_session.add(models.OrganizationMembershipCapability(
                organization_membership_id=membership.id,
                capability=capability,
            ))
    db_session.flush()
    return membership


async def create_teacher_profile(
    db_session: AsyncSession,
    *,
    organization_id: int,
    name: str = "Prof. Teste",
    subject_ids: list[int] | None = None,
    organization_membership_id: int | None = None,
) -> models.Teacher:
    """Create a teacher domain profile directly for tests that are not member-CRUD tests."""
    from sqlalchemy.future import select as _sel

    teacher = models.Teacher(
        name=name,
        organization_id=organization_id,
        organization_membership_id=organization_membership_id,
    )
    db_session.add(teacher)
    await db_session.flush()
    if subject_ids:
        valid_subject_ids = set((await db_session.execute(
            _sel(models.Subject.id).where(
                models.Subject.organization_id == organization_id,
                models.Subject.id.in_(subject_ids),
            )
        )).scalars().all())
        for subject_id in valid_subject_ids:
            await db_session.execute(
                models.teacher_subject_link.insert().values(
                    organization_id=organization_id,
                    teacher_id=teacher.id,
                    subject_id=subject_id,
                )
            )
    return teacher


def mock_clerk_payload(clerk_user_id: str, org_id: str | None = None, role: str = "admin") -> dict:
    payload = {"sub": clerk_user_id}
    if org_id is None:
        org_id = CLERK_ORG_BY_USER.get(clerk_user_id)
    if org_id:
        payload["o"] = {"id": org_id, "rol": role}
    return payload


# ============================================================
# FIXTURES DE AUTENTICAÇÃO (Fase 3 — com mock + user DB)
# ============================================================

ADMIN_USER_ID = "user_admin_001"
TEACHER_USER_ID = "user_teacher_001"
MOCK_ORG_ID = "org_test_001"
CLERK_ORG_BY_USER: dict[str, str] = {}


@pytest_asyncio.fixture
async def clerk_admin_headers(db_session: AsyncSession, monkeypatch):
    """Headers de admin com mock + user criado automaticamente na DB."""
    org, _ = await create_org_and_user(
        db_session,
        clerk_user_id=ADMIN_USER_ID,
        email="admin@test.com",
        role="admin",
        clerk_org_id=MOCK_ORG_ID,
    )
    payload = mock_clerk_payload(ADMIN_USER_ID, org.clerk_org_id, "admin")

    async def _mock_payload(_request):
        return payload

    monkeypatch.setattr("app.api.deps.get_clerk_payload", _mock_payload)
    yield {"Authorization": f"Bearer test_{ADMIN_USER_ID}"}


@pytest_asyncio.fixture
async def clerk_teacher_headers(db_session: AsyncSession, monkeypatch):
    """Headers de teacher com mock + user criado automaticamente na DB."""
    org, _ = await create_org_and_user(
        db_session,
        clerk_user_id=TEACHER_USER_ID,
        email="teacher@test.com",
        role="teacher",
        clerk_org_id=MOCK_ORG_ID + "_t",
    )
    payload = mock_clerk_payload(TEACHER_USER_ID, org.clerk_org_id, "member")

    async def _mock_payload(_request):
        return payload

    monkeypatch.setattr("app.api.deps.get_clerk_payload", _mock_payload)
    yield {"Authorization": f"Bearer test_{TEACHER_USER_ID}"}


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
    membership = await ensure_membership_capabilities(
        db_session,
        organization_id=org_id,
        user=user,
        capabilities=[models.MembershipCapability.teacher],
        expected_clerk_role=models.ClerkOrganizationRole.member,
        teacher_access_mode=models.TeacherAccessMode.platform,
    )
    teacher = await db_session.get(models.Teacher, teacher_id)
    if teacher is not None and teacher.organization_membership_id is None:
        teacher.organization_membership_id = membership.id
    await db_session.flush()
    return user
