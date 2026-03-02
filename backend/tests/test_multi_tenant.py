# Ficheiro: backend/tests/test_multi_tenant.py
"""
Testes de Multi-Tenancy para o Horário Zen.

Cobre dois cenários críticos de segurança:
  Parte 1 — Registo e Transação Atómica
    - Sucesso: verifica que Organization + Teacher + User são criados numa
      única transação e com o mesmo organization_id.
    - Falha: verifica que uma tentativa de registo com email duplicado
      resulta em rollback limpo (sem Organization órfã na BD).

  Parte 2 — Isolamento de Dados (Anti-Bleeding)
    - Professores: Org A só vê os seus professores; dados da Org B são invisíveis.
    - Disciplinas: Org A só vê as suas disciplinas; dados da Org B são invisíveis.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app import models
from app.config import settings
from app.core.security import create_access_token

API = settings.API_V1_STR


# ============================================================
#  HELPERS
# ============================================================

def _register_payload(school: str, admin: str, email: str, password: str = "senha_segura_123") -> dict:
    """Constrói um payload válido para POST /auth/register."""
    return {
        "school_name": school,
        "admin_name": admin,
        "email": email,
        "password": password,
    }


async def _register(client: AsyncClient, school: str, admin: str, email: str) -> dict:
    """Regista uma escola e devolve o Token (dict) da resposta."""
    resp = await client.post(
        f"{API}/auth/register",
        json=_register_payload(school, admin, email),
    )
    assert resp.status_code == 200, f"Registo falhou ({resp.status_code}): {resp.text}"
    return resp.json()


def _bearer(token_data: dict) -> dict:
    """Devolve o header Authorization para os pedidos HTTP."""
    return {"Authorization": f"Bearer {token_data['access_token']}"}


# ============================================================
#  PARTE 1 — REGISTO E TRANSAÇÃO ATÓMICA
# ============================================================

@pytest.mark.asyncio
async def test_register_creates_org_teacher_and_admin_atomically(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """
    POST /auth/register deve criar, numa única transação atómica:
      - 1 Organization com o nome da escola
      - 1 Teacher (perfil do administrador)
      - 1 User (admin) ligado à mesma org_id e com teacher_id válido

    Verifica a resposta Token E o estado directo na BD.
    """
    token_data = await _register(
        async_client,
        school="Escola Alfa",
        admin="Diretor Silva",
        email="silva@escolaalfa.pt",
    )

    # --- Verificações no Token ---
    assert token_data["role"] == "admin"
    assert token_data["organization_name"] == "Escola Alfa"
    org_id = token_data["organization_id"]
    teacher_id = token_data["teacher_id"]
    assert org_id is not None
    assert teacher_id is not None

    # --- Verificações directas na BD ---
    org = await db_session.scalar(
        select(models.Organization).where(models.Organization.id == org_id)
    )
    assert org is not None
    assert org.name == "Escola Alfa"

    user = await db_session.scalar(
        select(models.User).where(models.User.email == "silva@escolaalfa.pt")
    )
    assert user is not None
    assert user.organization_id == org_id
    assert user.role == models.UserRole.admin
    assert user.teacher_id == teacher_id
    assert user.is_active is True

    teacher = await db_session.scalar(
        select(models.Teacher).where(models.Teacher.id == teacher_id)
    )
    assert teacher is not None
    assert teacher.organization_id == org_id
    assert teacher.name == "Diretor Silva"


@pytest.mark.asyncio
async def test_register_duplicate_email_rolls_back_organisation(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """
    Quando o email já existe, o endpoint devolve 400 e NÃO deixa
    nenhuma Organization órfã na BD (rollback atómico confirmado).
    """
    payload = _register_payload("Escola Original", "Admin Original", "dup@escola.pt")

    # Primeiro registo — deve ter sucesso
    r1 = await async_client.post(f"{API}/auth/register", json=payload)
    assert r1.status_code == 200

    orgs_after_first: int = await db_session.scalar(
        select(func.count()).select_from(models.Organization)
    )
    assert orgs_after_first == 1

    # Segundo registo com o mesmo email — deve falhar com 400
    payload_dup = {**payload, "school_name": "Escola Duplicada"}
    r2 = await async_client.post(f"{API}/auth/register", json=payload_dup)
    assert r2.status_code == 400, f"Esperado 400, obtido {r2.status_code}: {r2.text}"

    detail = r2.json().get("detail", "").lower()
    assert "email" in detail or "registado" in detail, (
        f"Mensagem de erro inesperada: '{detail}'"
    )

    # Garantir que NÃO foi criada uma Organization órfã
    orgs_after_dup: int = await db_session.scalar(
        select(func.count()).select_from(models.Organization)
    )
    assert orgs_after_dup == 1, (
        f"DATA INTEGRITY ERROR: esperada 1 organização, encontradas {orgs_after_dup}. "
        "O rollback falhou — existe uma Organization órfã!"
    )

    # Verificar igualmente que não há Teacher nem User extras
    teacher_count: int = await db_session.scalar(
        select(func.count()).select_from(models.Teacher)
    )
    user_count: int = await db_session.scalar(
        select(func.count()).select_from(models.User)
    )
    assert teacher_count == 1, f"Esperado 1 Teacher, encontrados {teacher_count}"
    assert user_count == 1, f"Esperado 1 User, encontrados {user_count}"


# ============================================================
#  PARTE 2 — ISOLAMENTO DE DADOS (ANTI-BLEEDING)
# ============================================================

@pytest.mark.asyncio
async def test_teachers_endpoint_isolates_data_between_orgs(
    async_client: AsyncClient,
):
    """
    Org A e Org B têm professores distintos.
    Nenhuma das organizações consegue ver os professores da outra.
    """
    # --- Setup: Criar duas escolas ---
    token_a = await _register(async_client, "Escola A", "Admin A", "admin@escola-a.pt")
    token_b = await _register(async_client, "Escola B", "Admin B", "admin@escola-b.pt")

    # Criar professor extra em Org A
    async_client.headers.update(_bearer(token_a))
    r = await async_client.post(
        f"{API}/teachers/", json={"name": "Prof Exclusivo A"}
    )
    assert r.status_code == 200

    # Criar professor extra em Org B
    async_client.headers.update(_bearer(token_b))
    r = await async_client.post(
        f"{API}/teachers/", json={"name": "Prof Exclusivo B"}
    )
    assert r.status_code == 200

    # --- Verificação: Admin A vê apenas os professores da Org A ---
    async_client.headers.update(_bearer(token_a))
    resp_a = await async_client.get(f"{API}/teachers/")
    assert resp_a.status_code == 200
    names_a = [t["name"] for t in resp_a.json()]

    assert any("Admin A" in n or "Prof Exclusivo A" in n for n in names_a), (
        f"Professores da Org A não encontrados na resposta: {names_a}"
    )
    assert not any("Admin B" in n or "Prof Exclusivo B" in n for n in names_a), (
        f"DATA BLEEDING detectado! Professores da Org B visíveis para Org A: {names_a}"
    )

    # --- Verificação: Admin B vê apenas os professores da Org B ---
    async_client.headers.update(_bearer(token_b))
    resp_b = await async_client.get(f"{API}/teachers/")
    assert resp_b.status_code == 200
    names_b = [t["name"] for t in resp_b.json()]

    assert any("Admin B" in n or "Prof Exclusivo B" in n for n in names_b), (
        f"Professores da Org B não encontrados na resposta: {names_b}"
    )
    assert not any("Admin A" in n or "Prof Exclusivo A" in n for n in names_b), (
        f"DATA BLEEDING detectado! Professores da Org A visíveis para Org B: {names_b}"
    )


@pytest.mark.asyncio
async def test_subjects_endpoint_isolates_data_between_orgs(
    async_client: AsyncClient,
):
    """
    Org A e Org B têm disciplinas distintas.
    Nenhuma das organizações consegue ver as disciplinas da outra.
    """
    # --- Setup: Criar duas escolas ---
    token_a = await _register(async_client, "Escola Mat", "Admin Mat", "admin@mat.pt")
    token_b = await _register(async_client, "Escola Art", "Admin Art", "admin@art.pt")

    # Criar disciplina em Org A (admin é gestor — deps.get_current_active_admin)
    async_client.headers.update(_bearer(token_a))
    r = await async_client.post(
        f"{API}/subjects/",
        json={"name": "Matemática Avançada", "modules": []},
    )
    assert r.status_code == 200, f"Falhou ao criar disciplina A: {r.text}"

    # Criar disciplina em Org B
    async_client.headers.update(_bearer(token_b))
    r = await async_client.post(
        f"{API}/subjects/",
        json={"name": "Escultura Contemporânea", "modules": []},
    )
    assert r.status_code == 200, f"Falhou ao criar disciplina B: {r.text}"

    # --- Verificação: Admin A vê apenas disciplinas da Org A ---
    async_client.headers.update(_bearer(token_a))
    resp_a = await async_client.get(f"{API}/subjects/")
    assert resp_a.status_code == 200
    names_a = [s["name"] for s in resp_a.json()]

    assert "Matemática Avançada" in names_a, (
        f"Disciplina da Org A não encontrada: {names_a}"
    )
    assert "Escultura Contemporânea" not in names_a, (
        f"DATA BLEEDING detectado! Disciplina da Org B visível para Org A: {names_a}"
    )

    # --- Verificação: Admin B vê apenas disciplinas da Org B ---
    async_client.headers.update(_bearer(token_b))
    resp_b = await async_client.get(f"{API}/subjects/")
    assert resp_b.status_code == 200
    names_b = [s["name"] for s in resp_b.json()]

    assert "Escultura Contemporânea" in names_b, (
        f"Disciplina da Org B não encontrada: {names_b}"
    )
    assert "Matemática Avançada" not in names_b, (
        f"DATA BLEEDING detectado! Disciplina da Org A visível para Org B: {names_b}"
    )
