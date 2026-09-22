# Ficheiro: backend/tests/conftest.py
#
# CRÍTICO: RATELIMIT_ENABLED deve ser definido ANTES de qualquer import da app.
import os

os.environ.setdefault("RATELIMIT_ENABLED", "false")
os.environ["DATABASE_POOLING_ENABLED"] = "false"

import re
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import pytest_asyncio
from alembic.config import Config
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from alembic import command
from app import models
from app.config import settings
from tests.db import validated_test_database_url


# --- Engines de Teste ---
def _worker_database_url(value: str, worker_id: str | None) -> str:
    if worker_id is None:
        return value
    if not re.fullmatch(r"gw\d+", worker_id):
        raise RuntimeError(f"Unsupported pytest worker id: {worker_id!r}")
    url = make_url(value)
    database = url.database or ""
    if database.endswith("_db"):
        database = database[:-3]
    return url.set(database=f"{database}_{worker_id}").render_as_string(hide_password=False)


def _database_urls(worker_id: str | None) -> tuple[str, str, str, str]:
    runtime_url = _worker_database_url(
        os.environ.get("TEST_DATABASE_URL", str(settings.DATABASE_URL)),
        worker_id,
    )
    migration_url = _worker_database_url(
        os.environ.get(
            "MIGRATION_DATABASE_URL",
            str(settings.MIGRATION_DATABASE_URL or runtime_url),
        ),
        worker_id,
    )
    runtime_sync_url = (
        make_url(runtime_url)
        .set(drivername="postgresql+psycopg2")
        .render_as_string(hide_password=False)
    )
    migration_sync_url = (
        make_url(migration_url)
        .set(drivername="postgresql+psycopg2")
        .render_as_string(hide_password=False)
    )
    return (
        runtime_sync_url,
        migration_sync_url,
        make_url(migration_sync_url)
        .set(drivername="postgresql+asyncpg")
        .render_as_string(hide_password=False),
        make_url(runtime_url)
        .set(drivername="postgresql+asyncpg")
        .render_as_string(hide_password=False),
    )


_worker_id = os.environ.get("PYTEST_XDIST_WORKER")
_configured_test_url = _worker_database_url(
    os.environ.get("TEST_DATABASE_URL", str(settings.DATABASE_URL)),
    _worker_id,
)
_runtime_sync_test_url, _migration_sync_test_url, _async_test_url, _runtime_async_test_url = (
    _database_urls(_worker_id)
)
test_engine = create_async_engine(_async_test_url, poolclass=NullPool, echo=False)
runtime_test_engine = create_async_engine(
    _runtime_async_test_url,
    poolclass=NullPool,
    echo=False,
)
sync_test_engine = create_engine(_migration_sync_test_url, echo=False)
runtime_sync_test_engine = create_engine(_runtime_sync_test_url, echo=False)
SyncTestSession = sessionmaker(bind=sync_test_engine, autocommit=False, autoflush=False)

TestingSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)
RuntimeTestingSessionLocal = async_sessionmaker(
    bind=runtime_test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


def _configure_worker_database(worker_id: str) -> None:
    global _async_test_url
    global _configured_test_url
    global _migration_sync_test_url
    global _runtime_async_test_url
    global _runtime_sync_test_url
    global _worker_id
    global runtime_sync_test_engine
    global runtime_test_engine
    global sync_test_engine
    global test_engine

    if worker_id == "master":
        return
    if worker_id == _worker_id:
        os.environ["TEST_DATABASE_URL"] = _configured_test_url
        os.environ["MIGRATION_DATABASE_URL"] = _migration_sync_test_url
        return
    _worker_id = worker_id
    base_runtime_url = os.environ.get("TEST_DATABASE_URL", str(settings.DATABASE_URL))
    base_migration_url = os.environ.get(
        "MIGRATION_DATABASE_URL",
        str(settings.MIGRATION_DATABASE_URL or base_runtime_url),
    )
    _configured_test_url = _worker_database_url(
        base_runtime_url,
        worker_id,
    )
    (
        _runtime_sync_test_url,
        _migration_sync_test_url,
        _async_test_url,
        _runtime_async_test_url,
    ) = _database_urls(worker_id)
    os.environ["TEST_DATABASE_URL"] = _configured_test_url
    os.environ["MIGRATION_DATABASE_URL"] = _worker_database_url(base_migration_url, worker_id)
    test_engine = create_async_engine(_async_test_url, poolclass=NullPool, echo=False)
    runtime_test_engine = create_async_engine(
        _runtime_async_test_url,
        poolclass=NullPool,
        echo=False,
    )
    sync_test_engine = create_engine(_migration_sync_test_url, echo=False)
    runtime_sync_test_engine = create_engine(_runtime_sync_test_url, echo=False)
    SyncTestSession.configure(bind=sync_test_engine)
    TestingSessionLocal.configure(bind=test_engine)
    RuntimeTestingSessionLocal.configure(bind=runtime_test_engine)


def _assert_safe_test_database() -> None:
    validated_test_database_url(_configured_test_url)


def _alembic_config() -> Config:
    backend_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    config = Config(os.path.join(backend_root, "alembic.ini"))
    config.set_main_option("sqlalchemy.url", _migration_sync_test_url)
    return config


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _public_table_list() -> str:
    with sync_test_engine.begin() as conn:
        rows = (
            conn.execute(
                text(
                    """
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = 'public'
                  AND tablename <> 'alembic_version'
                ORDER BY tablename
                """
                )
            )
            .scalars()
            .all()
        )
    return ", ".join(f"public.{_quote_identifier(table)}" for table in rows)


def _truncate_public_tables(table_list: str) -> None:
    if table_list:
        with sync_test_engine.begin() as conn:
            conn.execute(text(f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE"))


@pytest.fixture(scope="session")
def migrated_test_database(worker_id):
    """Build the test schema through Alembic so triggers/RLS/functions exist."""
    _configure_worker_database(worker_id)
    _assert_safe_test_database()
    with sync_test_engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS app_security CASCADE"))
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.execute(text("GRANT ALL ON SCHEMA public TO public"))
    command.upgrade(_alembic_config(), "head")
    yield _public_table_list()


@pytest.fixture
def clean_database(migrated_test_database):
    yield
    _truncate_public_tables(migrated_test_database)


# --- Fixture: BD Assíncrona ---
@pytest_asyncio.fixture(scope="function")
async def db_session(clean_database) -> AsyncGenerator[AsyncSession, None]:
    async with TestingSessionLocal() as session:
        try:
            yield session
        finally:
            await session.rollback()


@pytest_asyncio.fixture(scope="function")
async def runtime_db_session(clean_database) -> AsyncGenerator[AsyncSession, None]:
    async with RuntimeTestingSessionLocal() as session:
        try:
            yield session
        finally:
            await session.rollback()


# --- Fixture: BD Síncrona ---
@pytest.fixture
def sync_db(db_session):
    db = SyncTestSession()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


# --- Fixture: Cliente API ---
@pytest_asyncio.fixture(scope="function")
async def async_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    from app.api import deps
    from app.main import app

    get_db = deps.get_db
    original_session_local = deps.SessionLocal

    class _TestClerkGateway:
        sdk = None

    async def override_get_clerk_payload(request: Request) -> dict:
        authorization = request.headers.get("authorization", "")
        token = authorization.removeprefix("Bearer ")
        principal = token.removeprefix("test_") if token else ""
        clerk_user_id, separator, explicit_org_id = principal.partition("|")
        clerk_org_id = explicit_org_id if separator else None
        if clerk_user_id and clerk_org_id is None:
            clerk_org_id = await db_session.scalar(
                select(models.Organization.clerk_org_id)
                .select_from(models.User)
                .join(
                    models.OrganizationMembership,
                    models.OrganizationMembership.account_id == models.User.id,
                )
                .join(
                    models.Organization,
                    models.Organization.id == models.OrganizationMembership.organization_id,
                )
                .where(
                    models.User.clerk_user_id == clerk_user_id,
                    models.OrganizationMembership.lifecycle_status
                    == models.MembershipLifecycleStatus.active,
                )
            )
        payload = {"sub": clerk_user_id} if clerk_user_id else {}
        if clerk_org_id:
            payload["o"] = {"id": clerk_org_id}
        return payload

    async def override_get_db():
        async with RuntimeTestingSessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[deps.get_clerk_payload] = override_get_clerk_payload
    app.dependency_overrides[deps.get_clerk_gateway] = _TestClerkGateway
    deps.SessionLocal = RuntimeTestingSessionLocal
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as ac:
            yield ac
    finally:
        deps.SessionLocal = original_session_local
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(deps.get_clerk_payload, None)
        app.dependency_overrides.pop(deps.get_clerk_gateway, None)


@pytest_asyncio.fixture(scope="function")
async def real_async_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """ASGI client that uses the app's real SessionLocal per request."""
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as ac:
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
    foundation_status: models.OrganizationFoundationStatus = models.OrganizationFoundationStatus.COMPLETED,
    foundation_completed_at: datetime | None = None,
    legal_accepted: bool = True,
) -> tuple[models.Organization, models.User]:
    """Cria org + user. Idempotente: se já existirem, retorna os existentes."""
    from sqlalchemy.future import select as _sel

    async def _ensure_membership(
        org: models.Organization, user: models.User
    ) -> models.OrganizationMembership:
        membership = (
            await db_session.execute(
                _sel(models.OrganizationMembership).where(
                    models.OrganizationMembership.organization_id == org.id,
                    models.OrganizationMembership.account_id == user.id,
                )
            )
        ).scalar_one_or_none()
        if membership is None:
            capability = (
                models.MembershipCapability.admin
                if role == "admin"
                else models.MembershipCapability.teacher
            )
            membership = models.OrganizationMembership(
                organization_id=org.id,
                account_id=user.id,
                organization_display_name=user.name or user.email,
                lifecycle_status=models.MembershipLifecycleStatus.active,
                access_status=models.MembershipAccessStatus.active,
                teacher_access_mode=models.TeacherAccessMode.platform
                if capability == models.MembershipCapability.teacher
                else None,
                can_admin=capability == models.MembershipCapability.admin,
                can_teach=capability == models.MembershipCapability.teacher,
            )
            db_session.add(membership)
            await db_session.flush()
        if teacher_id:
            teacher = await db_session.get(models.Teacher, teacher_id)
            if teacher is not None and teacher.organization_membership_id is None:
                teacher.organization_membership_id = membership.id
        return membership

    async def _ensure_legal_acceptance(
        org: models.Organization, membership: models.OrganizationMembership
    ) -> None:
        if not legal_accepted:
            return
        await accept_current_legal_documents(
            db_session,
            organization_id=org.id,
            membership_id=membership.id,
        )

    # Verificar se user já existe
    existing_user = (
        await db_session.execute(
            _sel(models.User).where(models.User.clerk_user_id == clerk_user_id)
        )
    ).scalar_one_or_none()
    if existing_user is not None:
        org = (
            await db_session.execute(
                _sel(models.Organization)
                .join(models.OrganizationMembership)
                .where(models.OrganizationMembership.account_id == existing_user.id)
            )
        ).scalar_one_or_none()
        if org is not None:
            membership = await _ensure_membership(org, existing_user)
            await _ensure_legal_acceptance(org, membership)
        return org, existing_user

    # Verificar se org já existe
    c_org_id = clerk_org_id or f"org_{uuid4().hex[:8]}"
    org = (
        await db_session.execute(
            _sel(models.Organization).where(models.Organization.clerk_org_id == c_org_id)
        )
    ).scalar_one_or_none()

    if org is None:
        completed_at = foundation_completed_at
        if (
            foundation_status == models.OrganizationFoundationStatus.COMPLETED
            and completed_at is None
        ):
            completed_at = datetime.now(UTC)
        org = models.Organization(
            name=org_name,
            clerk_org_id=c_org_id,
            plan_status="active",
            foundation_status=foundation_status,
            foundation_completed_at=completed_at,
        )
        db_session.add(org)
        await db_session.flush()

    user = models.User(
        clerk_user_id=clerk_user_id,
        email=email or f"{clerk_user_id}@test.com",
        name=name or "Test User",
    )
    db_session.add(user)
    await db_session.flush()
    membership = await _ensure_membership(org, user)
    await _ensure_legal_acceptance(org, membership)
    return org, user


async def accept_current_legal_documents(
    db_session: AsyncSession,
    *,
    organization_id: int,
    membership_id: int,
) -> models.OrganizationLegalAcceptance:
    """Seed the current legal acceptance for tests creating data manually."""
    from app.legal import CURRENT_DPA_VERSION, CURRENT_PRIVACY_VERSION, CURRENT_TERMS_VERSION

    acceptance = await db_session.scalar(
        select(models.OrganizationLegalAcceptance).where(
            models.OrganizationLegalAcceptance.organization_id == organization_id,
            models.OrganizationLegalAcceptance.terms_version == CURRENT_TERMS_VERSION,
            models.OrganizationLegalAcceptance.dpa_version == CURRENT_DPA_VERSION,
            models.OrganizationLegalAcceptance.privacy_version == CURRENT_PRIVACY_VERSION,
        )
    )
    if acceptance is None:
        acceptance = models.OrganizationLegalAcceptance(
            organization_id=organization_id,
            accepted_by_membership_id_snapshot=membership_id,
            authority_confirmed=True,
            terms_version=CURRENT_TERMS_VERSION,
            dpa_version=CURRENT_DPA_VERSION,
            privacy_version=CURRENT_PRIVACY_VERSION,
        )
        db_session.add(acceptance)
        await db_session.flush()
    return acceptance


async def create_completed_organization(
    db_session: AsyncSession,
    *,
    clerk_user_id: str = "clerk_test_admin_completed",
    org_name: str = "Escola Completa Teste",
    clerk_org_id: str | None = None,
) -> tuple[models.Organization, models.User]:
    return await create_org_and_user(
        db_session,
        clerk_user_id=clerk_user_id,
        org_name=org_name,
        clerk_org_id=clerk_org_id,
        foundation_status=models.OrganizationFoundationStatus.COMPLETED,
        foundation_completed_at=datetime.now(UTC),
    )


async def create_not_started_organization(
    db_session: AsyncSession,
    *,
    clerk_user_id: str = "clerk_test_admin_not_started",
    org_name: str = "Escola Nao Iniciada Teste",
    clerk_org_id: str | None = None,
) -> tuple[models.Organization, models.User]:
    return await create_org_and_user(
        db_session,
        clerk_user_id=clerk_user_id,
        org_name=org_name,
        clerk_org_id=clerk_org_id,
        foundation_status=models.OrganizationFoundationStatus.NOT_STARTED,
        foundation_completed_at=None,
    )


async def create_in_progress_organization(
    db_session: AsyncSession,
    *,
    clerk_user_id: str = "clerk_test_admin_in_progress",
    org_name: str = "Escola Em Progresso Teste",
    clerk_org_id: str | None = None,
) -> tuple[models.Organization, models.User]:
    return await create_org_and_user(
        db_session,
        clerk_user_id=clerk_user_id,
        org_name=org_name,
        clerk_org_id=clerk_org_id,
        foundation_status=models.OrganizationFoundationStatus.IN_PROGRESS,
        foundation_completed_at=None,
    )


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

    can_teach = models.MembershipCapability.teacher in capabilities
    if can_teach and teacher_access_mode is None:
        teacher_access_mode = models.TeacherAccessMode.platform

    organization = await db_session.get(models.Organization, organization_id)
    if organization is not None and not organization.clerk_org_id:
        organization.clerk_org_id = f"org_test_{organization_id}"
        await db_session.flush()
    membership = (
        await db_session.execute(
            _sel(models.OrganizationMembership).where(
                models.OrganizationMembership.organization_id == organization_id,
                models.OrganizationMembership.account_id == user.id,
            )
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
            can_admin=models.MembershipCapability.admin in capabilities,
            can_teach=can_teach,
        )
        db_session.add(membership)
        await db_session.flush()
    else:
        membership.lifecycle_status = models.MembershipLifecycleStatus.active
        membership.access_status = models.MembershipAccessStatus.active
        membership.teacher_access_mode = teacher_access_mode
        membership.can_admin = models.MembershipCapability.admin in capabilities
        membership.can_teach = can_teach
    await db_session.flush()
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

    if organization_membership_id is None:
        account = models.User(
            email=f"teacher-{uuid4().hex}@test.invalid",
            name=name,
        )
        db_session.add(account)
        await db_session.flush()
        membership = models.OrganizationMembership(
            organization_id=organization_id,
            account_id=account.id,
            organization_display_name=name,
            lifecycle_status=models.MembershipLifecycleStatus.active,
            access_status=models.MembershipAccessStatus.none,
            teacher_access_mode=models.TeacherAccessMode.scheduler_only,
            can_admin=False,
            can_teach=True,
        )
        db_session.add(membership)
        await db_session.flush()
        organization_membership_id = membership.id

    teacher = models.Teacher(
        organization_id=organization_id,
        organization_membership_id=organization_membership_id,
    )
    db_session.add(teacher)
    await db_session.flush()
    if subject_ids:
        valid_subject_ids = set(
            (
                await db_session.execute(
                    _sel(models.Subject.id).where(
                        models.Subject.organization_id == organization_id,
                        models.Subject.id.in_(subject_ids),
                    )
                )
            )
            .scalars()
            .all()
        )
        for subject_id in valid_subject_ids:
            await db_session.execute(
                models.teacher_subject_link.insert().values(
                    organization_id=organization_id,
                    teacher_id=teacher.id,
                    subject_id=subject_id,
                )
            )
    return teacher


# ============================================================
# FIXTURES DE AUTENTICAÇÃO (Fase 3 — com mock + user DB)
# ============================================================

ADMIN_USER_ID = "user_admin_001"
TEACHER_USER_ID = "user_teacher_001"
MOCK_ORG_ID = "org_test_001"


@pytest_asyncio.fixture
async def clerk_admin_headers(db_session: AsyncSession):
    """Headers de admin com utilizador e membership persistidos na BD."""
    await create_org_and_user(
        db_session,
        clerk_user_id=ADMIN_USER_ID,
        email="admin@test.com",
        role="admin",
        clerk_org_id=MOCK_ORG_ID,
    )
    await db_session.commit()
    yield {"Authorization": f"Bearer test_{ADMIN_USER_ID}"}


@pytest_asyncio.fixture
async def clerk_teacher_headers(db_session: AsyncSession):
    """Headers de professor com utilizador e membership persistidos na BD."""
    await create_org_and_user(
        db_session,
        clerk_user_id=TEACHER_USER_ID,
        email="teacher@test.com",
        role="teacher",
        clerk_org_id=MOCK_ORG_ID + "_t",
    )
    await db_session.commit()
    yield {"Authorization": f"Bearer test_{TEACHER_USER_ID}"}


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
    teacher = await db_session.get(models.Teacher, teacher_id)
    if teacher is not None:
        membership = await db_session.get(
            models.OrganizationMembership,
            teacher.organization_membership_id,
        )
        if membership is not None and membership.organization_id == org_id:
            user = await db_session.get(models.User, membership.account_id)
            user.clerk_user_id = clerk_user_id
            user.email = email or f"{clerk_user_id}@test.com"
            user.name = name or teacher.name
            await ensure_membership_capabilities(
                db_session,
                organization_id=org_id,
                user=user,
                capabilities=[models.MembershipCapability.teacher],
                expected_clerk_role=models.ClerkOrganizationRole.member,
                teacher_access_mode=models.TeacherAccessMode.platform,
            )
            await db_session.flush()
            return user
        raise ValueError("Teacher profile does not belong to the requested organization.")

    user = models.User(
        clerk_user_id=clerk_user_id,
        email=email or f"{clerk_user_id}@test.com",
        name=name or "Teacher User",
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
    if teacher is not None:
        teacher.organization_membership_id = membership.id
    await db_session.flush()
    return user
