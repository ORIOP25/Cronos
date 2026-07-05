import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from unittest.mock import patch

from app import models
from app.config import settings
from tests.conftest import create_org_and_user, create_teacher_profile, mock_clerk_payload

API = settings.API_V1_STR


# ============================================================
#  HELPERS (Clerk mock)
# ============================================================

async def _setup_org_with_admin(
    db_session: AsyncSession,
    clerk_user_id: str,
    email: str,
    org_name: str,
    clerk_org_id: str,
    admin_name: str = "Admin",
) -> tuple[models.Organization, models.User]:
    """Cria org + admin user via create_org_and_user()."""
    org, user = await create_org_and_user(
        db_session,
        clerk_user_id=clerk_user_id,
        email=email,
        name=admin_name,
        role="admin",
        org_name=org_name,
        clerk_org_id=clerk_org_id,
    )
    return org, user


def _auth_headers(clerk_user_id: str, clerk_org_id: str, role: str = "admin") -> dict:
    """Retorna headers HTTP + mock do get_clerk_payload."""
    return {
        "Authorization": f"Bearer test_{clerk_user_id}",
        "X-Mock-Org-Id": clerk_org_id,
        "X-Mock-Role": role,
    }


# ============================================================
#  PARTE 1 — TRANSAÇÃO ATÓMICA (adaptado para Clerk)
# ============================================================

@pytest.mark.asyncio
async def test_create_org_and_user_atomically(
    db_session: AsyncSession,
):
    """
    create_org_and_user() deve criar Organization + User atómicamente
    com organization_id e role corretos.
    """
    org, user = await _setup_org_with_admin(
        db_session,
        clerk_user_id="user_mt_001",
        email="admin@escolaalfa.pt",
        org_name="Escola Alfa",
        clerk_org_id="org_mt_001",
        admin_name="Diretor Silva",
    )

    assert org is not None
    assert org.name == "Escola Alfa"
    assert org.clerk_org_id == "org_mt_001"

    assert user is not None
    assert user.email == "admin@escolaalfa.pt"
    assert user.organization_id == org.id
    assert user.role == models.UserRole.admin
    assert user.is_active is True

    # Verificar que a org está corretamente ligada
    org_check = await db_session.scalar(
        select(models.Organization).where(models.Organization.id == org.id)
    )
    assert org_check is not None
    assert org_check.name == "Escola Alfa"


@pytest.mark.asyncio
async def test_create_org_and_user_idempotent(
    db_session: AsyncSession,
):
    """
    create_org_and_user() chamado 2x com os mesmos IDs deve ser idempotente.
    """
    org_a, user_a = await _setup_org_with_admin(
        db_session,
        clerk_user_id="user_mt_002",
        email="dup@escola.pt",
        org_name="Escola Original",
        clerk_org_id="org_mt_002",
    )

    # Segunda chamada com os mesmos IDs — deve retornar os existentes
    org_b, user_b = await _setup_org_with_admin(
        db_session,
        clerk_user_id="user_mt_002",
        email="dup@escola.pt",
        org_name="Escola Diferente",
        clerk_org_id="org_mt_002",
    )

    # Deve retornar os mesmos registos (não duplicar)
    assert org_b.id == org_a.id
    assert user_b.id == user_a.id

    # Verificar que não foram criados duplicados
    org_count = await db_session.scalar(
        select(func.count()).select_from(models.Organization)
    )
    user_count = await db_session.scalar(
        select(func.count()).select_from(models.User)
    )
    assert org_count == 1, f"Esperada 1 org, encontradas {org_count}"
    assert user_count == 1, f"Esperado 1 user, encontrados {user_count}"


# ============================================================
#  PARTE 2 — ISOLAMENTO DE DADOS (ANTI-BLEEDING)
# ============================================================

@pytest.mark.asyncio
async def test_teachers_endpoint_isolates_data_between_orgs(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """
    Org A e Org B têm professores distintos.
    Nenhuma das organizações consegue ver os professores da outra.
    """
    # Setup: criar duas orgs com admins
    org_a, user_a = await _setup_org_with_admin(
        db_session,
        clerk_user_id="user_iso_a",
        email="admin@escola-a.pt",
        org_name="Escola A",
        clerk_org_id="org_iso_a",
        admin_name="Admin A",
    )
    org_b, user_b = await _setup_org_with_admin(
        db_session,
        clerk_user_id="user_iso_b",
        email="admin@escola-b.pt",
        org_name="Escola B",
        clerk_org_id="org_iso_b",
        admin_name="Admin B",
    )

    payload_a = mock_clerk_payload("user_iso_a", "org_iso_a", "admin")
    payload_b = mock_clerk_payload("user_iso_b", "org_iso_b", "admin")

    headers_a = {"Authorization": "Bearer test_user_iso_a"}
    headers_b = {"Authorization": "Bearer test_user_iso_b"}
    await create_teacher_profile(db_session, organization_id=org_a.id, name="Prof Exclusivo A")
    await create_teacher_profile(db_session, organization_id=org_b.id, name="Prof Exclusivo B")
    await db_session.commit()

    # Verificação: Admin A vê apenas professores da Org A
    with patch("app.api.deps.get_clerk_payload", return_value=payload_a):
        resp_a = await async_client.get(f"{API}/teachers/", headers=headers_a)
    assert resp_a.status_code == 200
    names_a = [t["name"] for t in resp_a.json()]

    assert any("Admin A" in n or "Prof Exclusivo A" in n for n in names_a), (
        f"Professores da Org A não encontrados: {names_a}"
    )
    assert not any("Admin B" in n or "Prof Exclusivo B" in n for n in names_a), (
        f"DATA BLEEDING! Professores da Org B visíveis para Org A: {names_a}"
    )

    # Verificação: Admin B vê apenas professores da Org B
    with patch("app.api.deps.get_clerk_payload", return_value=payload_b):
        resp_b = await async_client.get(f"{API}/teachers/", headers=headers_b)
    assert resp_b.status_code == 200
    names_b = [t["name"] for t in resp_b.json()]

    assert any("Admin B" in n or "Prof Exclusivo B" in n for n in names_b), (
        f"Professores da Org B não encontrados: {names_b}"
    )
    assert not any("Admin A" in n or "Prof Exclusivo A" in n for n in names_b), (
        f"DATA BLEEDING! Professores da Org A visíveis para Org B: {names_b}"
    )


@pytest.mark.asyncio
async def test_subjects_endpoint_isolates_data_between_orgs(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """
    Org A e Org B têm disciplinas distintas.
    Nenhuma das organizações consegue ver as disciplinas da outra.
    """
    # Setup: criar duas orgs com admins
    await _setup_org_with_admin(
        db_session,
        clerk_user_id="user_subj_a",
        email="admin@mat.pt",
        org_name="Escola Mat",
        clerk_org_id="org_subj_a",
        admin_name="Admin Mat",
    )
    await _setup_org_with_admin(
        db_session,
        clerk_user_id="user_subj_b",
        email="admin@art.pt",
        org_name="Escola Art",
        clerk_org_id="org_subj_b",
        admin_name="Admin Art",
    )

    payload_a = mock_clerk_payload("user_subj_a", "org_subj_a", "admin")
    payload_b = mock_clerk_payload("user_subj_b", "org_subj_b", "admin")

    # Criar disciplina em Org A
    with patch("app.api.deps.get_clerk_payload", return_value=payload_a):
        r = await async_client.post(
            f"{API}/subjects/",
            json={"name": "Matematica Avancada", "modules": []},
            headers={"Authorization": "Bearer test_user_subj_a"},
        )
        assert r.status_code == 200, f"Falhou criar disciplina A: {r.text}"

    # Criar disciplina em Org B
    with patch("app.api.deps.get_clerk_payload", return_value=payload_b):
        r = await async_client.post(
            f"{API}/subjects/",
            json={"name": "Escultura Contemporanea", "modules": []},
            headers={"Authorization": "Bearer test_user_subj_b"},
        )
        assert r.status_code == 200, f"Falhou criar disciplina B: {r.text}"

    # Verificação: Admin A vê apenas disciplinas da Org A
    with patch("app.api.deps.get_clerk_payload", return_value=payload_a):
        resp_a = await async_client.get(
            f"{API}/subjects/",
            headers={"Authorization": "Bearer test_user_subj_a"},
        )
    assert resp_a.status_code == 200
    names_a = [s["name"] for s in resp_a.json()]

    assert "Matematica Avancada" in names_a, (
        f"Disciplina da Org A não encontrada: {names_a}"
    )
    assert "Escultura Contemporanea" not in names_a, (
        f"DATA BLEEDING! Disciplina da Org B visível para Org A: {names_a}"
    )

    # Verificação: Admin B vê apenas disciplinas da Org B
    with patch("app.api.deps.get_clerk_payload", return_value=payload_b):
        resp_b = await async_client.get(
            f"{API}/subjects/",
            headers={"Authorization": "Bearer test_user_subj_b"},
        )
    assert resp_b.status_code == 200
    names_b = [s["name"] for s in resp_b.json()]

    assert "Escultura Contemporanea" in names_b, (
        f"Disciplina da Org B não encontrada: {names_b}"
    )
    assert "Matematica Avancada" not in names_b, (
        f"DATA BLEEDING! Disciplina da Org A visível para Org B: {names_b}"
    )
