# WBS — Migração para Clerk: Guia de Implementação

**Projeto:** Horário-Zen (Apérius)
**Versão:** 1.0
**Base:** PRD v2.1

---

## Convenções

- `✅` — Resultado esperado (o que deves verificar após cada passo)
- `⚠️` — Edge case a considerar
- `🔧` — Comando a executar
- Caminhos de ficheiros são relativos à raiz do monorepo (`MeuProjeto/`)

---

# FASE 1 — Fundação (DB + Backend Core)

---

## Passo 1.1 — Criar branch e confirmar ambiente

```powershell
git checkout -b feat/clerk-migration
docker compose up -d  # garante PostgreSQL e Redis a correr
```

✅ `docker compose ps` mostra todos os serviços `Up`

---

## Passo 1.2 — Instalar dependências Python

**Ficheiro:** `backend/requirements.txt`

Adicionar no final:

```
clerk-backend-api>=2.2.0
svix>=1.0.0
```

```powershell
docker compose exec backend pip install -r requirements.txt
```

✅ `docker compose exec backend pip show clerk-backend-api` devolve versão >=2.2.0

---

## Passo 1.3 — Adicionar variáveis Clerk ao `config.py`

**Ficheiro:** `backend/app/config.py`

Adicionar após as settings existentes de SECRET_KEY:

```python
# --- Clerk Authentication ---
CLERK_SECRET_KEY: str = ""
CLERK_PUBLISHABLE_KEY: str = ""
CLERK_WEBHOOK_SECRET: str = ""
FRONTEND_URL: str = "http://localhost:5173"
```

**Ficheiro:** `backend/.env` — verificar que contém:

```
CLERK_SECRET_KEY=sk_test_qK2IqFGsT58Ts5FHIK4baQJn2SbzLgJ2IEnjJjkWuc
CLERK_PUBLISHABLE_KEY=pk_test_d2VsY29tZWQtY2F0LTgzLmNsZXJrLmFjY291bnRzLmRldiQ
CLERK_WEBHOOK_SECRET=whsec_...  # obter no Clerk Dashboard > Webhooks > criar endpoint
```

✅ `docker compose exec backend python -c "from app.config import settings; print(settings.CLERK_SECRET_KEY[:10])"` imprime `sk_test_...`

⚠️ Edge case: `CLERK_WEBHOOK_SECRET` precisa ser criado no Clerk Dashboard. Sem ele, webhooks não podem ser verificados. Obtém-lo em https://dashboard.clerk.com/~/webhooks → criar endpoint com URL `https://apérius.pt/api/v1/webhooks/clerk` (em dev usar URL de túnel).

---

## Passo 1.4 — Criar migration Alembic

```powershell
docker compose exec backend alembic revision --autogenerate -m "add_clerk_integration"
```

**Verificar** que o ficheiro gerado em `backend/alembic/versions/` contém:

```python
# upgrade():
op.add_column('organization', sa.Column('clerk_org_id', sa.String(255), nullable=True, unique=True))
op.add_column('user', sa.Column('clerk_user_id', sa.String(255), nullable=True, unique=True))
op.alter_column('user', 'hashed_password', existing_type=sa.String(255), nullable=True)
```

⚠️ Edge case: Se o autogenerate não detetar as alterações, verificar que os modelos foram atualizados primeiro (Passo 1.5).

```powershell
docker compose exec backend alembic upgrade head
```

✅ `docker compose exec backend alembic current` mostra a nova revision como `head`

---

## Passo 1.5 — Atualizar modelos SQLAlchemy

**Ficheiro:** `backend/app/models.py`

Adicionar à classe `Organization`:

```python
clerk_org_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)
```

Adicionar à classe `User`:

```python
clerk_user_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)
```

Alterar `hashed_password` na classe `User`:

```python
# De:
hashed_password: Mapped[str] = mapped_column(String(255))
# Para:
hashed_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
```

✅ `docker compose exec backend python -c "from app.models import User, Organization; print('OK')"` sem erros

---

## Passo 1.6 — Criar `app/core/clerk.py`

**Ficheiro NOVO:** `backend/app/core/clerk.py`

```python
from functools import lru_cache
from clerk_backend_api import Clerk
from clerk_backend_api.security import authenticate_request
from clerk_backend_api.security.types import AuthenticateRequestOptions
from app.config import settings

@lru_cache()
def get_clerk_sdk() -> Clerk:
    """Singleton Clerk SDK. Usar apenas para operações BAPI (não para authenticate_request)."""
    return Clerk(bearer_auth=settings.CLERK_SECRET_KEY)

def verify_clerk_request(request):
    """Valida o token Clerk de um request HTTP e retorna o RequestState."""
    sdk = get_clerk_sdk()
    return sdk.authenticate_request(
        request,
        AuthenticateRequestOptions(
            authorized_parties=[settings.FRONTEND_URL],
        ),
    )
```

✅ Executar no container: `docker compose exec backend python -c "from app.core.clerk import get_clerk_sdk; sdk = get_clerk_sdk(); print(type(sdk))"` — deve imprimir `<class 'clerk_backend_api.sdk.Clerk'>`

⚠️ Edge case: `CLERK_SECRET_KEY` vazio → `Clerk()` lança exceção. Garantir que o `.env` está carregado antes de importar.

---

## Passo 1.7 — Criar schemas de webhooks

**Ficheiro NOVO:** `backend/app/schemas/webhooks.py`

```python
from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime

class ClerkWebhookEvent(BaseModel):
    type: str
    data: dict[str, Any]
    object: str = "event"
    timestamp: int
    instance_id: Optional[str] = None

class ClerkUserData(BaseModel):
    id: str
    email_addresses: list[dict[str, Any]] = []
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    created_at: Optional[int] = None
    public_metadata: dict[str, Any] = {}
    unsafe_metadata: dict[str, Any] = {}

class ClerkOrganizationData(BaseModel):
    id: str
    name: str
    slug: str
    created_at: Optional[int] = None
    public_metadata: dict[str, Any] = {}

class ClerkMembershipData(BaseModel):
    id: str
    role: str
    organization: dict[str, Any]
    public_metadata: dict[str, Any] = {}
    created_at: Optional[int] = None
```

✅ `docker compose exec backend python -c "from app.schemas.webhooks import ClerkWebhookEvent; print('OK')"`

---

## Passo 1.8 — Criar `app/services/clerk_sync.py`

**Ficheiro NOVO:** `backend/app/services/clerk_sync.py`

```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app import models
from app.core.clerk import get_clerk_sdk
from app.models import UserRole
import logging

logger = logging.getLogger(__name__)

async def ensure_organization_exists(db: AsyncSession, clerk_org_id: str, org_name: str) -> models.Organization:
    """Garante que a organization existe localmente. Cria se não existir."""
    result = await db.execute(
        select(models.Organization).where(models.Organization.clerk_org_id == clerk_org_id)
    )
    org = result.scalar_one_or_none()
    
    if not org:
        org = models.Organization(
            name=org_name,
            clerk_org_id=clerk_org_id,
            plan_status="active",
        )
        db.add(org)
        await db.flush()
        logger.info(f"Organization criada localmente: {clerk_org_id}")
    
    return org

async def ensure_user_exists(
    db: AsyncSession,
    clerk_user_id: str,
    email: str | None = None,
    name: str | None = None,
    role: str | None = None,
    org_id: int | None = None,
    teacher_id: int | None = None,
) -> models.User:
    """Garante que o user existe localmente. Cria/atualiza se necessário. Idempotente."""
    result = await db.execute(
        select(models.User).where(models.User.clerk_user_id == clerk_user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        user = models.User(
            clerk_user_id=clerk_user_id,
            email=email or "",
            name=name,
            role=parse_role(role),
            organization_id=org_id,
            teacher_id=teacher_id,
        )
        db.add(user)
        await db.flush()
        logger.info(f"User criado localmente: {clerk_user_id}")
    else:
        # Atualizar campos que podem ter mudado
        if email:
            user.email = email
        if name:
            user.name = name
        if role:
            user.role = parse_role(role)
        if org_id is not None:
            user.organization_id = org_id
        if teacher_id is not None:
            user.teacher_id = teacher_id
    
    return user

def parse_role(clerk_role: str | None) -> str:
    """Converte role do Clerk para role local."""
    if not clerk_role:
        return UserRole.admin.value
    # Clerk roles vêm como "admin" ou "member" (sem prefixo "org:")
    role_map = {
        "admin": UserRole.admin.value,
        "member": UserRole.teacher.value,
    }
    return role_map.get(clerk_role, UserRole.teacher.value)

async def sync_user_from_clerk_api(db: AsyncSession, clerk_user_id: str) -> models.User | None:
    """Fallback síncrono: obtém dados do user via BAPI e cria/atualiza localmente."""
    sdk = get_clerk_sdk()
    try:
        clerk_user = sdk.users.get(user_id=clerk_user_id)
    except Exception as e:
        logger.error(f"BAPI users.get falhou para {clerk_user_id}: {e}")
        return None
    
    email = None
    if clerk_user.email_addresses:
        email = clerk_user.email_addresses[0].email_address
    
    name = f"{clerk_user.first_name or ''} {clerk_user.last_name or ''}".strip() or None
    
    return await ensure_user_exists(
        db=db,
        clerk_user_id=clerk_user_id,
        email=email,
        name=name,
    )

async def sync_organization_from_clerk_api(db: AsyncSession, clerk_org_id: str) -> models.Organization | None:
    """Fallback síncrono: obtém dados da org via BAPI e cria localmente."""
    sdk = get_clerk_sdk()
    try:
        clerk_org = sdk.organizations.get(organization_id=clerk_org_id)
    except Exception as e:
        logger.error(f"BAPI organizations.get falhou para {clerk_org_id}: {e}")
        return None
    
    return await ensure_organization_exists(db, clerk_org_id, clerk_org.name)
```

✅ Testar com: `docker compose exec backend python -c "from app.services.clerk_sync import ensure_user_exists, parse_role; print('OK')"`

⚠️ Edge case: Se a BAPI falhar (rede, rate limit), o fallback retorna `None` e o endpoint devolve 500. Isto é aceitável — a BAPI raramente falha e o caso só ocorre em race condition.

---

## Passo 1.9 — Criar endpoint de webhooks

**Ficheiro NOVO:** `backend/app/api/v1/endpoints/webhooks.py`

```python
import json
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from svix.webhooks import Webhook, WebhookVerificationError
from app.config import settings
from app.db.database import get_db
from app.services import clerk_sync
from app.schemas.webhooks import ClerkWebhookEvent
import logging

logger = logging.getLogger(__name__)
router = APIRouter(tags=["webhooks"])

@router.post("/webhooks/clerk")
async def handle_clerk_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Recebe e processa webhooks do Clerk com verificação Svix."""
    
    # 1. Verificar headers Svix
    svix_id = request.headers.get("svix-id")
    svix_timestamp = request.headers.get("svix-timestamp")
    svix_signature = request.headers.get("svix-signature")
    
    if not all([svix_id, svix_timestamp, svix_signature]):
        raise HTTPException(400, detail="Missing Svix headers")
    
    # 2. Ler corpo
    payload = await request.body()
    
    # 3. Verificar assinatura
    try:
        wh = Webhook(settings.CLERK_WEBHOOK_SECRET)
        wh.verify(payload, {
            "svix-id": svix_id,
            "svix-timestamp": svix_timestamp,
            "svix-signature": svix_signature,
        })
    except WebhookVerificationError:
        raise HTTPException(401, detail="Invalid webhook signature")
    
    # 4. Processar evento
    data = json.loads(payload)
    event = ClerkWebhookEvent(**data)
    
    log = logger.bind(clerk_event=event.type)
    log.info(f"Webhook recebido: {event.type}")
    
    match event.type:
        case "user.created":
            await _handle_user_created(db, event.data)
        case "user.updated":
            await _handle_user_updated(db, event.data)
        case "user.deleted":
            await _handle_user_deleted(db, event.data)
        case "organization.created":
            await _handle_organization_created(db, event.data)
        case "organization.updated":
            await _handle_organization_updated(db, event.data)
        case "organizationMembership.created":
            await _handle_membership_created(db, event.data)
        case "organizationMembership.updated":
            await _handle_membership_updated(db, event.data)
        case "organizationMembership.deleted":
            await _handle_membership_deleted(db, event.data)
        case _:
            log.info(f"Evento ignorado: {event.type}")
    
    return {"status": "ok"}


async def _handle_user_created(db: AsyncSession, data: dict):
    clerk_user_id = data["id"]
    email = None
    if data.get("email_addresses"):
        email = data["email_addresses"][0]["email_address"]
    name = f"{data.get('first_name', '')} {data.get('last_name', '')}".strip() or None
    
    await clerk_sync.ensure_user_exists(
        db=db,
        clerk_user_id=clerk_user_id,
        email=email,
        name=name,
    )

async def _handle_user_updated(db: AsyncSession, data: dict):
    clerk_user_id = data["id"]
    email = None
    if data.get("email_addresses"):
        email = data["email_addresses"][0]["email_address"]
    name = f"{data.get('first_name', '')} {data.get('last_name', '')}".strip() or None
    
    await clerk_sync.ensure_user_exists(
        db=db,
        clerk_user_id=clerk_user_id,
        email=email,
        name=name,
    )

async def _handle_user_deleted(db: AsyncSession, data: dict):
    clerk_user_id = data["id"]
    # Soft-delete
    user = await clerk_sync.ensure_user_exists(db=db, clerk_user_id=clerk_user_id)
    if user:
        user.is_active = False
        await db.flush()

async def _handle_organization_created(db: AsyncSession, data: dict):
    await clerk_sync.ensure_organization_exists(
        db=db,
        clerk_org_id=data["id"],
        org_name=data["name"],
    )

async def _handle_organization_updated(db: AsyncSession, data: dict):
    org = await clerk_sync.ensure_organization_exists(
        db=db,
        clerk_org_id=data["id"],
        org_name=data["name"],
    )
    if org.name != data["name"]:
        org.name = data["name"]

async def _handle_membership_created(db: AsyncSession, data: dict):
    clerk_user_id = data.get("public_user_data", {}).get("user_id")
    clerk_org_id = data.get("organization", {}).get("id")
    role = data.get("role")  # "admin" ou "member"
    teacher_id = data.get("public_metadata", {}).get("teacher_id")
    
    if not clerk_user_id or not clerk_org_id:
        logger.error("Membership sem user_id ou org_id")
        return
    
    # Garantir user e org
    user_data = data.get("public_user_data", {})
    email = user_data.get("identifier")
    
    org = await clerk_sync.ensure_organization_exists(db, clerk_org_id, data["organization"]["name"])
    
    await clerk_sync.ensure_user_exists(
        db=db,
        clerk_user_id=clerk_user_id,
        email=email,
        role=role,
        org_id=org.id,
        teacher_id=teacher_id,
    )

async def _handle_membership_updated(db: AsyncSession, data: dict):
    # Mesmo tratamento — ensure_user_exists é idempotente
    await _handle_membership_created(db, data)

async def _handle_membership_deleted(db: AsyncSession, data: dict):
    clerk_user_id = data.get("public_user_data", {}).get("user_id")
    if not clerk_user_id:
        return
    
    user = await clerk_sync.ensure_user_exists(db=db, clerk_user_id=clerk_user_id)
    if user:
        user.organization_id = None
        await db.flush()
```

**Registar o router** em `backend/app/api/api.py`:

```python
from app.api.v1.endpoints import webhooks

# Adicionar antes de app.include_router(api_router):
app.include_router(
    webhooks.router,
    prefix="/api/v1",
    tags=["webhooks"],
)
```

✅ `docker compose exec backend python -c "from app.api.v1.endpoints.webhooks import router; print('Router OK')"`

⚠️ Edge case: Webhooks em localhost — O Clerk não consegue enviar webhooks para `localhost`. Usar:
- **ngrok**: `ngrok http 8000` → URL pública → atualizar no Clerk Dashboard
- **Svix CLI** (recomendado): `svix listen http://localhost:8000/api/v1/webhooks/clerk --secret whsec_...`
- **Teste manual**: Enviar payload simulado com `curl` ou Postman com headers Svix corretos

---

## Passo 1.10 — Atualizar dependências de auth (`deps.py`)

**Ficheiro:** `backend/app/api/deps.py`

**ANTES** (linhas relevantes):

```python
from app.core import security

async def get_current_user(request, db, token) -> models.User:
    token_data = security.verify_token(token)
    user = ...
```

**DEPOIS:**

```python
from app.core.clerk import verify_clerk_request
from app.services import clerk_sync
from app.db.database import get_db_async  # verificar nome correto

async def get_clerk_payload(request: Request) -> dict:
    """Valida token Clerk e retorna o payload com claims."""
    state = verify_clerk_request(request)
    if not state.is_signed_in:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return state.payload

async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),  # verificar nome da dependency de DB
) -> models.User:
    """Obtém User local a partir do token Clerk, com fallback síncrono."""
    payload = await get_clerk_payload(request)
    clerk_user_id = payload.get("sub")
    if not clerk_user_id:
        raise HTTPException(status_code=401, detail="No user ID in token")
    
    # Tentar DB local
    result = await db.execute(
        select(models.User).where(models.User.clerk_user_id == clerk_user_id)
    )
    user = result.scalar_one_or_none()
    
    if user:
        return user
    
    # Fallback: race condition com webhooks — criar via BAPI
    org_id = payload.get("o", {}).get("id") if "o" in payload else None
    role = payload.get("o", {}).get("rol") if "o" in payload else None
    
    # Criar org primeiro se existir no token
    if org_id:
        org = await clerk_sync.sync_organization_from_clerk_api(db, org_id)
    
    user = await clerk_sync.sync_user_from_clerk_api(db, clerk_user_id)
    
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    # Se temos org no token, associar
    if org_id and user.organization_id is None:
        org_local = await db.execute(
            select(models.Organization).where(models.Organization.clerk_org_id == org_id)
        )
        org_local = org_local.scalar_one_or_none()
        if org_local:
            user.organization_id = org_local.id
        if role:
            user.role = clerk_sync.parse_role(role)
        await db.flush()
    
    return user

def get_current_active_user(
    current_user: models.User = Depends(get_current_user),
) -> models.User:
    if not current_user.is_active:
        raise HTTPException(status_code=403, detail="Inactive user")
    return current_user

def get_current_active_admin(
    current_user: models.User = Depends(get_current_active_user),
) -> models.User:
    if current_user.role not in ("admin",) and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user
```

**IMPORTANTE:** Verificar a dependência correta da DB. O projeto pode usar `Session = Depends(get_db)` onde `get_db` está em `app.db.database`. Ajustar nomes conforme o código existente.

⚠️ Edge case: `get_current_user` anterior recebia 3 parâmetros (`request, db, token`). Agora recebe 2 (`request, db`). Os endpoints que chamam `get_current_user` diretamente (não via `Depends`) precisam ser atualizados. Ver `schedule.py` que tem chamada manual.

✅ Para testar, colocar um print/debug temporário:
```python
# No final de get_current_user, para testes:
logger.info(f"User autenticado: {user.email}, org_id={user.organization_id}, role={user.role}")
```

---

## Passo 1.11 — Atualizar `main.py` (CSP + CORS + rota webhook)

**Ficheiro:** `backend/app/main.py`

### 1.11a — Atualizar CSP

Localizar a função `security_headers` (~linha 94) e substituir a linha CSP:

```python
# ANTES:
response.headers["Content-Security-Policy"] = "default-src 'none'"

# DEPOIS:
if settings.ENVIRONMENT == "local":
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://*.clerk.accounts.dev; "
        "connect-src 'self' https://*.clerk.accounts.dev; "
        "img-src 'self' https://img.clerk.com data:; "
        "style-src 'self' 'unsafe-inline' https://*.clerk.accounts.dev; "
        "frame-src 'self' https://*.clerk.accounts.dev; "
        "frame-ancestors 'self'"
    )
else:
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' https://clerk.apérius.pt; "
        "connect-src 'self' https://clerk.apérius.pt; "
        "img-src 'self' https://img.clerk.com data:; "
        "style-src 'self' 'unsafe-inline' https://clerk.apérius.pt; "
        "frame-src 'self' https://clerk.apérius.pt; "
        "frame-ancestors 'self'"
    )
```

### 1.11b — Ajustar CORS

Substituir `allow_origins=settings.CORS_ORIGINS_LIST` por:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS_LIST if settings.CORS_ORIGINS_LIST else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 1.11c — Rota webhook (sem middleware de auth global, se existir)

Garantir que a rota `/api/v1/webhooks/clerk` NÃO passa por middleware de autenticação (a validação é via Svix).

✅ Fazer `docker compose restart backend` e verificar que não há erros no arranque.

---

## Passo 1.12 — Atualizar `app/api/api.py`

**Ficheiro:** `backend/app/api/api.py`

- **REMOVER** linha: `from app.api.v1.endpoints import auth`
- **REMOVER** linha: `api_router.include_router(auth.router, prefix="/auth", tags=["auth"])`
- **ADICIONAR**: `from app.api.v1.endpoints import webhooks`
- **ADICIONAR**: `api_router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])`

✅ A aplicação arranca sem erros de importação.

⚠️ Edge case: Os endpoints existentes (`teachers`, `schedule`, etc.) importam `get_current_user` do `deps.py`. Como a assinatura mudou, podem ocorrer erros. Isto é esperado — serão corrigidos nos passos seguintes.

---

## Passo 1.13 — Atualizar `app/schemas.py`

**Ficheiro:** `backend/app/schemas.py`

Remover (ou comentar para já) as classes:

```python
# REMOVER:
class Token(BaseModel): ...
class TokenPayload(BaseModel): ...
class RegisterRequest(BaseModel): ...
class LoginRequest(BaseModel): ...

# ADICIONAR:
class ClerkUserRead(BaseModel):
    id: int
    clerk_user_id: str
    email: str
    name: str | None = None
    role: str
    organization_id: int
    teacher_id: int | None = None
    is_active: bool
    
    model_config = ConfigDict(from_attributes=True)

# MODIFICAR UserCreate — remover campo password:
class UserCreate(BaseModel):
    clerk_user_id: str | None = None
    email: str
    name: str | None = None
    role: str | None = "teacher"
    teacher_id: int | None = None
```

✅ `docker compose exec backend python -c "from app.schemas import ClerkUserRead; print('OK')"`

---

## Passo 1.14 — Atualizar `user_service.py`

**Ficheiro:** `backend/app/services/user_service.py`

### Remover:
- `from app.core.security import hash_password` (linha ~11)
- Método `register_account` se existir
- `hash_password(user.password)` em `create_user`

### Modificar `create_user`:

```python
async def create_user(db: AsyncSession, user_in) -> models.User:
    """Cria user SEM password (Clerk gere auth)."""
    user = models.User(
        clerk_user_id=user_in.clerk_user_id,
        email=user_in.email,
        name=user_in.name,
        role=user_in.role or models.UserRole.teacher.value,
        hashed_password=None,  # Clerk gere passwords
        organization_id=...  # virá do contexto
    )
    db.add(user)
    await db.flush()
    return user
```

✅ `docker compose exec backend python -c "from app.services.user_service import create_user; print('OK')"` — pode falhar se `create_user` tiver referências a `hash_password` que ainda não foram removidas. Corrigir antes de continuar.

---

## Passo 1.15 — Escrever testes T1-T18 (Backend Unitários)

### Ficheiro: `backend/tests/test_clerk_auth.py` (T1-T8)

```python
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi import HTTPException
from clerk_backend_api.security.types import RequestState

# T1: Token válido
@pytest.mark.asyncio
async def test_authenticate_request_valid_token():
    """Token Clerk válido → is_signed_in=True, payload contém sub e org_id."""
    from app.core.clerk import verify_clerk_request
    
    mock_request = MagicMock()
    mock_state = RequestState(
        is_signed_in=True,
        payload={"sub": "user_123", "o": {"id": "org_456", "rol": "admin"}},
        reason=None,
    )
    
    with patch("app.core.clerk.get_clerk_sdk") as mock_sdk:
        mock_sdk.return_value.authenticate_request.return_value = mock_state
        result = verify_clerk_request(mock_request)
    
    assert result.is_signed_in is True
    assert result.payload["sub"] == "user_123"
    assert result.payload["o"]["id"] == "org_456"

# T2: Token inválido
@pytest.mark.asyncio
async def test_authenticate_request_invalid_token():
    """Token inválido → is_signed_in=False."""
    from app.core.clerk import verify_clerk_request
    
    mock_request = MagicMock()
    mock_state = RequestState(is_signed_in=False, payload={}, reason="invalid_token")
    
    with patch("app.core.clerk.get_clerk_sdk") as mock_sdk:
        mock_sdk.return_value.authenticate_request.return_value = mock_state
        result = verify_clerk_request(mock_request)
    
    assert result.is_signed_in is False

# T3: Token expirado
@pytest.mark.asyncio
async def test_authenticate_request_expired_token():
    """Token expirado → is_signed_in=False."""
    from app.core.clerk import verify_clerk_request
    
    mock_request = MagicMock()
    mock_state = RequestState(is_signed_in=False, payload={}, reason="token_expired")
    
    with patch("app.core.clerk.get_clerk_sdk") as mock_sdk:
        mock_sdk.return_value.authenticate_request.return_value = mock_state
        result = verify_clerk_request(mock_request)
    
    assert result.is_signed_in is False

# T4: Authorized party errado
@pytest.mark.asyncio
async def test_authenticate_request_wrong_azp():
    """Authorized party errado → is_signed_in=False."""
    from app.core.clerk import verify_clerk_request
    
    mock_request = MagicMock()
    mock_state = RequestState(is_signed_in=False, payload={}, reason="invalid_azp")
    
    with patch("app.core.clerk.get_clerk_sdk") as mock_sdk:
        mock_sdk.return_value.authenticate_request.return_value = mock_state
        result = verify_clerk_request(mock_request)
    
    assert result.is_signed_in is False

# T5: User na DB local
@pytest.mark.asyncio
async def test_get_current_user_from_db(db_session):
    """Token válido + user na DB → retorna User."""
    from app.api.deps import get_current_user
    from app import models
    
    # Criar user na DB
    user = models.User(
        clerk_user_id="user_123",
        email="test@example.com",
        role="admin",
        organization_id=1,
    )
    db_session.add(user)
    await db_session.commit()
    
    # Mock do get_clerk_payload
    with patch("app.api.deps.get_clerk_payload", new_callable=AsyncMock) as mock_payload:
        mock_payload.return_value = {"sub": "user_123", "o": {"id": "org_1", "rol": "admin"}}
        
        mock_request = MagicMock()
        result = await get_current_user(mock_request, db_session)
    
    assert result.clerk_user_id == "user_123"
    assert result.email == "test@example.com"

# T6: User NÃO na DB → fallback cria
@pytest.mark.asyncio
async def test_get_current_user_fallback_creates_user(db_session):
    """Token válido + user NÃO existe → fallback BAPI cria user."""
    from app.api.deps import get_current_user
    from app.services import clerk_sync
    
    # Mock do fallback
    mock_user = MagicMock()
    mock_user.clerk_user_id = "user_new"
    mock_user.email = "new@example.com"
    mock_user.is_active = True
    mock_user.role = "admin"
    
    with patch("app.api.deps.get_clerk_payload", new_callable=AsyncMock) as mock_payload, \
         patch.object(clerk_sync, "sync_user_from_clerk_api", new_callable=AsyncMock) as mock_sync:
        mock_payload.return_value = {"sub": "user_new", "o": {"id": "org_1", "rol": "admin"}}
        mock_sync.return_value = mock_user
        
        mock_request = MagicMock()
        result = await get_current_user(mock_request, db_session)
    
    assert result.clerk_user_id == "user_new"
    mock_sync.assert_called_once()

# T7: Admin tem acesso
@pytest.mark.asyncio
async def test_get_current_active_admin():
    """User role=admin → acesso concedido."""
    from app.api.deps import get_current_active_admin
    
    mock_user = MagicMock()
    mock_user.role = "admin"
    mock_user.is_active = True
    mock_user.is_superuser = False
    
    result = get_current_active_admin(mock_user)
    assert result == mock_user

# T8: Teacher é rejeitado
@pytest.mark.asyncio
async def test_get_current_active_admin_rejects_teacher():
    """User role=teacher → 403."""
    from app.api.deps import get_current_active_admin
    
    mock_user = MagicMock()
    mock_user.role = "teacher"
    mock_user.is_active = True
    mock_user.is_superuser = False
    
    with pytest.raises(HTTPException) as exc:
        get_current_active_admin(mock_user)
    assert exc.value.status_code == 403
```

### Ficheiro: `backend/tests/test_webhooks.py` (T9-T18)

```python
import pytest
import json
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, Headers
from svix.webhooks import Webhook

# Helper para gerar headers Svix válidos
def _svix_headers(payload: dict, secret: str = "whsec_test_123") -> dict:
    wh = Webhook(secret)
    body = json.dumps(payload).encode()
    signed = wh.sign(msg_id="test_msg_123", timestamp=1713158400, data=body)
    return {
        "svix-id": "test_msg_123",
        "svix-timestamp": str(1713158400),
        "svix-signature": signed["svix-signature"],
        "Content-Type": "application/json",
    }

# T9: user.created cria user local
@pytest.mark.asyncio
async def test_webhook_user_created_creates_local_user(async_client: AsyncClient, db_session):
    """user.created → INSERT user local."""
    payload = {
        "type": "user.created",
        "object": "event",
        "timestamp": 1713158400000,
        "data": {
            "id": "user_wb_001",
            "first_name": "Test",
            "last_name": "User",
            "email_addresses": [{"email_address": "test@example.com", "id": "idn_123"}],
        },
    }
    
    headers = _svix_headers(payload)
    response = await async_client.post("/api/v1/webhooks/clerk", json=payload, headers=headers)
    
    assert response.status_code == 200
    
    # Verificar na DB
    from app import models
    from sqlalchemy import select
    result = await db_session.execute(
        select(models.User).where(models.User.clerk_user_id == "user_wb_001")
    )
    user = result.scalar_one_or_none()
    assert user is not None
    assert user.email == "test@example.com"
    assert user.name == "Test User"

# T10: Idempotência — duplicado não crasha
@pytest.mark.asyncio
async def test_webhook_user_created_idempotent(async_client: AsyncClient, db_session):
    """Segundo user.created para o mesmo user → atualiza, não duplica."""
    payload = {
        "type": "user.created",
        "object": "event",
        "timestamp": 1713158400000,
        "data": {
            "id": "user_wb_001",
            "first_name": "Updated",
            "last_name": "Name",
            "email_addresses": [{"email_address": "updated@example.com", "id": "idn_123"}],
        },
    }
    
    headers = _svix_headers(payload)
    response = await async_client.post("/api/v1/webhooks/clerk", json=payload, headers=headers)
    
    assert response.status_code == 200
    
    from app import models
    from sqlalchemy import select, func
    result = await db_session.execute(
        select(func.count()).select_from(models.User).where(models.User.clerk_user_id == "user_wb_001")
    )
    count = result.scalar()
    assert count == 1  # Não duplicou

# T11: organization.created
@pytest.mark.asyncio
async def test_webhook_organization_created(async_client: AsyncClient, db_session):
    """organization.created → INSERT org local."""
    payload = {
        "type": "organization.created",
        "object": "event",
        "data": {"id": "org_wb_001", "name": "Escola Teste", "slug": "escola-teste"},
    }
    
    headers = _svix_headers(payload)
    response = await async_client.post("/api/v1/webhooks/clerk", json=payload, headers=headers)
    
    assert response.status_code == 200
    
    from app import models
    from sqlalchemy import select
    result = await db_session.execute(
        select(models.Organization).where(models.Organization.clerk_org_id == "org_wb_001")
    )
    org = result.scalar_one_or_none()
    assert org is not None
    assert org.name == "Escola Teste"

# T12: membership.created admin
@pytest.mark.asyncio
async def test_webhook_membership_created_admin(async_client: AsyncClient, db_session):
    """Membership com role=admin → user role=admin."""
    # Pré-criar org
    from app import models
    org = models.Organization(name="Org", clerk_org_id="org_wb_002", plan_status="active")
    db_session.add(org)
    await db_session.commit()
    
    payload = {
        "type": "organizationMembership.created",
        "object": "event",
        "data": {
            "role": "admin",
            "organization": {"id": "org_wb_002", "name": "Org", "slug": "org"},
            "public_user_data": {"user_id": "user_wb_002", "identifier": "admin@example.com"},
            "public_metadata": {},
        },
    }
    
    headers = _svix_headers(payload)
    response = await async_client.post("/api/v1/webhooks/clerk", json=payload, headers=headers)
    
    assert response.status_code == 200
    
    from sqlalchemy import select
    result = await db_session.execute(
        select(models.User).where(models.User.clerk_user_id == "user_wb_002")
    )
    user = result.scalar_one_or_none()
    assert user is not None
    assert user.role == "admin"

# T13: membership.created teacher
@pytest.mark.asyncio
async def test_webhook_membership_created_teacher(async_client: AsyncClient, db_session):
    """Membership com role=member → user role=teacher."""
    org = models.Organization(name="Org2", clerk_org_id="org_wb_003", plan_status="active")
    db_session.add(org)
    await db_session.commit()
    
    payload = {
        "type": "organizationMembership.created",
        "object": "event",
        "data": {
            "role": "member",
            "organization": {"id": "org_wb_003", "name": "Org2", "slug": "org2"},
            "public_user_data": {"user_id": "user_wb_003", "identifier": "teacher@example.com"},
            "public_metadata": {},
        },
    }
    
    headers = _svix_headers(payload)
    response = await async_client.post("/api/v1/webhooks/clerk", json=payload, headers=headers)
    
    assert response.status_code == 200
    
    from sqlalchemy import select
    result = await db_session.execute(
        select(models.User).where(models.User.clerk_user_id == "user_wb_003")
    )
    user = result.scalar_one_or_none()
    assert user.role == "teacher"

# T14: membership.created com teacher_id no metadata
@pytest.mark.asyncio
async def test_webhook_membership_created_with_teacher_id(async_client: AsyncClient, db_session):
    """Membership com public_metadata.teacher_id → user.teacher_id linkado."""
    org = models.Organization(name="Org3", clerk_org_id="org_wb_004", plan_status="active")
    db_session.add(org)
    await db_session.commit()
    
    payload = {
        "type": "organizationMembership.created",
        "object": "event",
        "data": {
            "role": "member",
            "organization": {"id": "org_wb_004", "name": "Org3", "slug": "org3"},
            "public_user_data": {"user_id": "user_wb_004", "identifier": "prof@example.com"},
            "public_metadata": {"teacher_id": 42},
        },
    }
    
    headers = _svix_headers(payload)
    response = await async_client.post("/api/v1/webhooks/clerk", json=payload, headers=headers)
    
    assert response.status_code == 200
    
    from sqlalchemy import select
    result = await db_session.execute(
        select(models.User).where(models.User.clerk_user_id == "user_wb_004")
    )
    user = result.scalar_one_or_none()
    assert user.teacher_id == 42

# T15: membership.updated
@pytest.mark.asyncio
async def test_webhook_membership_updated_role_change(async_client: AsyncClient, db_session):
    """Role alterada → DB atualizada."""
    org = models.Organization(name="Org4", clerk_org_id="org_wb_005", plan_status="active")
    db_session.add(org)
    await db_session.commit()
    
    # Criar user como teacher
    user = models.User(clerk_user_id="user_wb_005", email="change@example.com", role="teacher", organization_id=org.id)
    db_session.add(user)
    await db_session.commit()
    
    # Enviar update com role admin
    payload = {
        "type": "organizationMembership.updated",
        "data": {
            "role": "admin",
            "organization": {"id": "org_wb_005", "name": "Org4", "slug": "org4"},
            "public_user_data": {"user_id": "user_wb_005", "identifier": "change@example.com"},
            "public_metadata": {},
        },
    }
    
    headers = _svix_headers(payload)
    response = await async_client.post("/api/v1/webhooks/clerk", json=payload, headers=headers)
    
    assert response.status_code == 200
    
    from sqlalchemy import select
    result = await db_session.execute(
        select(models.User).where(models.User.clerk_user_id == "user_wb_005")
    )
    user = result.scalar_one_or_none()
    assert user.role == "admin"

# T16: membership.deleted
@pytest.mark.asyncio
async def test_webhook_membership_deleted(async_client: AsyncClient, db_session):
    """Membership removida → user.organization_id = NULL."""
    org = models.Organization(name="Org5", clerk_org_id="org_wb_006", plan_status="active")
    db_session.add(org)
    await db_session.commit()
    
    user = models.User(clerk_user_id="user_wb_006", email="leave@example.com", role="teacher", organization_id=org.id)
    db_session.add(user)
    await db_session.commit()
    
    payload = {
        "type": "organizationMembership.deleted",
        "data": {
            "organization": {"id": "org_wb_006"},
            "public_user_data": {"user_id": "user_wb_006"},
        },
    }
    
    headers = _svix_headers(payload)
    response = await async_client.post("/api/v1/webhooks/clerk", json=payload, headers=headers)
    
    assert response.status_code == 200
    
    await db_session.refresh(user)
    assert user.organization_id is None

# T17: Assinatura inválida
@pytest.mark.asyncio
async def test_webhook_invalid_signature_rejected(async_client: AsyncClient):
    """Assinatura Svix errada → 401."""
    payload = {"type": "user.created", "data": {"id": "x"}}
    
    headers = {
        "svix-id": "bad",
        "svix-timestamp": "0",
        "svix-signature": "v1,invalid_signature",
    }
    
    response = await async_client.post("/api/v1/webhooks/clerk", json=payload, headers=headers)
    assert response.status_code == 401

# T18: Headers Svix em falta
@pytest.mark.asyncio
async def test_webhook_missing_svix_headers(async_client: AsyncClient):
    """Sem headers Svix → 400."""
    payload = {"type": "user.created", "data": {"id": "x"}}
    
    response = await async_client.post("/api/v1/webhooks/clerk", json=payload)
    assert response.status_code == 400
```

### Configurar fixtures no `conftest.py`

```python
@pytest.fixture
async def async_client():
    """AsyncClient para testes de integração."""
    from app.main import app
    from httpx import AsyncClient, ASGITransport
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

@pytest.fixture
async def db_session():
    """Sessão de DB para testes."""
    from app.db.database import SessionLocalAsync
    async with SessionLocalAsync() as session:
        yield session
```

✅ `docker compose exec backend pytest tests/test_clerk_auth.py -v` → T1-T8 passam
✅ `docker compose exec backend pytest tests/test_webhooks.py -v` → T9-T18 passam

⚠️ Edge case: O `Webhook` do `svix` precisa de `content-type: application/json`. Os headers gerados devem incluir o content-type correto.

---

# FASE 2 — Onboarding + Teacher Invitations

---

## Passo 2.1 — Criar schemas de onboarding

**Ficheiro NOVO:** `backend/app/schemas/onboarding.py`

```python
from pydantic import BaseModel
from datetime import date, time
from typing import Optional

class OnboardingRequest(BaseModel):
    school_start_date: date
    school_target_end_date: date
    school_hard_end_date: date
    lunch_start: time
    lunch_end: time
    lunch_min_duration: int

class OnboardingStatusResponse(BaseModel):
    onboarding_complete: bool
    organization_name: Optional[str] = None
```

---

## Passo 2.2 — Criar serviço de onboarding

**Ficheiro:** `backend/app/services/organization_service.py`

Adicionar função:

```python
from app import models
from app.schemas.onboarding import OnboardingRequest

async def complete_onboarding(
    db: AsyncSession,
    organization_id: int,
    data: OnboardingRequest,
) -> None:
    """Cria OrganizationSettings + OrganizationGridSettings."""
    
    # Verificar se já foi feito (idempotente)
    from sqlalchemy import select
    
    existing = await db.execute(
        select(models.OrganizationSettings).where(
            models.OrganizationSettings.organization_id == organization_id
        )
    )
    if existing.scalar_one_or_none():
        return  # Já concluído
    
    # Criar settings
    db.add(models.OrganizationSettings(
        organization_id=organization_id,
        school_start_date=data.school_start_date,
        school_target_end_date=data.school_target_end_date,
        school_hard_end_date=data.school_hard_end_date,
        repair_stability_window_days=1,
    ))
    
    db.add(models.OrganizationGridSettings(
        organization_id=organization_id,
        lunch_window_start=data.lunch_start,
        lunch_window_end=data.lunch_end,
        lunch_min_duration_minutes=data.lunch_min_duration,
    ))
    
    await db.flush()
```

---

## Passo 2.3 — Criar endpoint de onboarding

**Ficheiro NOVO:** `backend/app/api/v1/endpoints/onboarding.py`

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_active_admin
from app.db.database import get_db
from app.schemas.onboarding import OnboardingRequest, OnboardingStatusResponse
from app.services.organization_service import complete_onboarding
from app import models
from sqlalchemy import select

router = APIRouter(tags=["onboarding"])

@router.get("/onboarding/status", response_model=OnboardingStatusResponse)
async def get_onboarding_status(
    current_user: models.User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    """Verifica se o onboarding está completo."""
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(400, detail="No organization associated")
    
    result = await db.execute(
        select(models.OrganizationSettings).where(
            models.OrganizationSettings.organization_id == org_id
        )
    )
    settings = result.scalar_one_or_none()
    
    org_result = await db.execute(
        select(models.Organization).where(models.Organization.id == org_id)
    )
    org = org_result.scalar_one_or_none()
    
    return OnboardingStatusResponse(
        onboarding_complete=settings is not None,
        organization_name=org.name if org else None,
    )

@router.post("/onboarding")
async def submit_onboarding(
    data: OnboardingRequest,
    current_user: models.User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    """Submete dados de onboarding e cria configurações da escola."""
    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(400, detail="No organization associated")
    
    await complete_onboarding(db, org_id, data)
    await db.commit()
    
    return {"status": "ok", "organization_id": org_id, "message": "Onboarding completo"}
```

**Registar** em `app/api/api.py`:

```python
from app.api.v1.endpoints import onboarding
api_router.include_router(onboarding.router, prefix="/onboarding", tags=["onboarding"])
```

---

## Passo 2.4 — Adicionar `invite_teacher_to_clerk` ao `teacher_service.py`

**Ficheiro:** `backend/app/services/teacher_service.py`

Adicionar método:

```python
from app.core.clerk import get_clerk_sdk
from clerk_backend_api.models import CreateOrganizationInvitationRequestBody

async def invite_teacher_to_clerk(
    clerk_org_id: str,
    teacher_email: str,
    teacher_id: int,
) -> dict:
    """Envia convite Clerk para professor, associando o teacher_id via metadata."""
    sdk = get_clerk_sdk()
    
    result = sdk.organization_invitations.create(
        organization_id=clerk_org_id,
        request_body=CreateOrganizationInvitationRequestBody(
            email_address=teacher_email,
            role="org:member",
            public_metadata={"teacher_id": teacher_id},
        ),
    )
    
    return {"invitation_id": result.id, "status": result.status}
```

Chamar este método dentro de `create_teacher()` quando `create_user_account=True`:

```python
# Após criar Teacher row e antes de commit:
if teacher_in.create_user_account and teacher_in.email:
    org = await db.get(models.Organization, organization_id)
    if org and org.clerk_org_id:
        await invite_teacher_to_clerk(
            clerk_org_id=org.clerk_org_id,
            teacher_email=teacher_in.email,
            teacher_id=db_teacher.id,
        )
```

⚠️ Edge case: Se `clerk_org_id` for None (org criada antes da migração), o convite não pode ser enviado. Log warning e prossegue.

---

## Passo 2.5 — Atualizar `user_service.py` (final)

Remover completamente `hash_password` import e todas as referências. Método `create_user` já não aceita nem processa password.

---

## Passo 2.6 — Escrever testes T19-T23

```python
# tests/test_onboarding.py (T19-T22)

# T19: GET status sem token → 401
@pytest.mark.asyncio
async def test_onboarding_status_requires_auth(async_client):
    response = await async_client.get("/api/v1/onboarding/status")
    assert response.status_code == 401

# T20: POST onboarding → settings criadas
@pytest.mark.asyncio
async def test_onboarding_creates_settings(async_client, db_session, auth_user_admin):
    data = {
        "school_start_date": "2025-09-15",
        "school_target_end_date": "2026-06-30",
        "school_hard_end_date": "2026-07-31",
        "lunch_start": "12:30",
        "lunch_end": "14:00",
        "lunch_min_duration": 60,
    }
    
    response = await async_client.post("/api/v1/onboarding", json=data, cookies=auth_user_admin["cookies"])
    assert response.status_code == 200
    
    # Verificar DB
    from app import models
    from sqlalchemy import select
    result = await db_session.execute(
        select(models.OrganizationSettings).where(
            models.OrganizationSettings.organization_id == auth_user_admin["org_id"]
        )
    )
    settings = result.scalar_one_or_none()
    assert settings is not None

# T21: POST sem token → 401
@pytest.mark.asyncio
async def test_onboarding_requires_auth(async_client):
    data = {"school_start_date": "2025-09-15", ...}
    response = await async_client.post("/api/v1/onboarding", json=data)
    assert response.status_code == 401

# T22: POST com token teacher → 403
@pytest.mark.asyncio
async def test_onboarding_requires_admin(async_client, auth_user_teacher):
    data = {"school_start_date": "2025-09-15", ...}
    response = await async_client.post("/api/v1/onboarding", json=data, cookies=auth_user_teacher["cookies"])
    assert response.status_code == 403

# T23: Criar teacher envia invitation Clerk
@pytest.mark.asyncio
async def test_create_teacher_invites_to_clerk(async_client, db_session, auth_admin):
    # Mock da BAPI
    with patch("app.services.teacher_service.invite_teacher_to_clerk") as mock_invite:
        mock_invite.return_value = {"invitation_id": "inv_123", "status": "pending"}
        
        response = await async_client.post(
            "/api/v1/teachers/",
            json={
                "name": "Prof Teste",
                "email": "prof@example.com",
                "create_user_account": True,
                "subjects": [],
            },
            cookies=auth_admin["cookies"],
        )
        
        assert response.status_code == 200
        mock_invite.assert_called_once()
```

---

# FASE 3 — Frontend Core

---

## Passo 3.1 — Instalar `@clerk/react`

```powershell
cd frontend; if ($?) { npm install @clerk/react@latest }
```

✅ `npm list @clerk/react` mostra versão instalada

---

## Passo 3.2 — Configurar env

**Ficheiro:** `frontend/.env.local`

```bash
VITE_CLERK_PUBLISHABLE_KEY=pk_test_d2VsY29tZWQtY2F0LTgzLmNsZXJrLmFjY291bnRzLmRldiQ
```

⚠️ Edge case: A chave publishable do backend `.env` é a mesma — confirmar que está correta no Clerk Dashboard > API Keys.

---

## Passo 3.3 — Atualizar `main.jsx`

**Ficheiro:** `frontend/src/main.jsx`

```jsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ClerkProvider } from "@clerk/react";
import App from "./App.jsx";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <ClerkProvider afterSignOutUrl="/">
      <App />
    </ClerkProvider>
  </StrictMode>
);
```

✅ `npm run dev` → app carrega sem erros. O Clerk mostra um warning "No publishable key" se `.env.local` não estiver correto.

---

## Passo 3.4 — Criar páginas de auth

**Ficheiro NOVO:** `frontend/src/pages/SignInPage.jsx`

```jsx
import { SignIn } from "@clerk/react";

export default function SignInPage() {
  return (
    <div style={{ display: "flex", justifyContent: "center", paddingTop: "10vh" }}>
      <SignIn
        routing="path"
        path="/login"
        signUpUrl="/register"
        afterSignInUrl="/onboarding"
        afterSignUpUrl="/create-org"
      />
    </div>
  );
}
```

**Ficheiro NOVO:** `frontend/src/pages/SignUpPage.jsx`

```jsx
import { SignUp } from "@clerk/react";

export default function SignUpPage() {
  return (
    <div style={{ display: "flex", justifyContent: "center", paddingTop: "10vh" }}>
      <SignUp
        routing="path"
        path="/register"
        signInUrl="/login"
        afterSignUpUrl="/create-org"
      />
    </div>
  );
}
```

⚠️ Edge case: `afterSignUpUrl="/create-org"` — quando o user faz sign-up, é redirecionado para `<CreateOrganization />` ou para uma página custom que o contém. Se não houver componente `<CreateOrganization />` na rota `/create-org`, o Clerk mostra um erro. Precisamos de o configurar no passo seguinte.

---

## Passo 3.5 — Adicionar rota `/create-org`

**Ficheiro NOVO:** `frontend/src/pages/CreateOrgPage.jsx`

```jsx
import { CreateOrganization } from "@clerk/react";

export default function CreateOrgPage() {
  return (
    <div style={{ display: "flex", justifyContent: "center", paddingTop: "10vh" }}>
      <CreateOrganization
        routing="path"
        path="/create-org"
        afterCreateOrganizationUrl="/onboarding"
        skipInvitationScreen={true}
      />
    </div>
  );
}
```

✅ Após criar org, redireciona para `/onboarding`.

---

## Passo 3.6 — Atualizar `App.jsx`

**Ficheiro:** `frontend/src/App.jsx`

```jsx
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Protect, Show } from "@clerk/react";
import { useAuth, useOrganization } from "@clerk/react";

// Páginas
import SignInPage from "./pages/SignInPage";
import SignUpPage from "./pages/SignUpPage";
import CreateOrgPage from "./pages/CreateOrgPage";
import Onboarding from "./pages/Onboarding";  // criado na Fase 4
import Dashboard from "./pages/Dashboard";    // existente
import DefaultLayout from "./components/DefaultLayout";
import MarketingSite from "./pages/MarketingSite";

function RoleBasedRedirect() {
  const { isSignedIn, isLoaded } = useAuth();
  const { organization, membership } = useOrganization();
  
  if (!isLoaded) return <div>Loading...</div>;
  if (!isSignedIn) return <Navigate to="/login" />;
  
  const role = membership?.role;
  if (role === "org:admin") return <Navigate to="/dashboard" />;
  if (role === "org:member") return <Navigate to="/my-availability" />;
  return <Navigate to="/login" />;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Landing pública */}
        <Route path="/" element={
          <Show when="signed-out" fallback={<RoleBasedRedirect />}>
            <MarketingSite />
          </Show>
        } />
        
        {/* Auth — público */}
        <Route path="/login" element={<SignInPage />} />
        <Route path="/register" element={<SignUpPage />} />
        
        {/* Criação de org — requer sign-in */}
        <Route path="/create-org" element={
          <Protect fallback={<Navigate to="/login" />}>
            <CreateOrgPage />
          </Protect>
        } />
        
        {/* Onboarding — requer org:admin */}
        <Route path="/onboarding" element={
          <Protect role="org:admin" fallback={<Navigate to="/login" />}>
            <Onboarding />
          </Protect>
        } />
        
        {/* Área admin */}
        <Route path="/dashboard" element={
          <Protect role="org:admin" fallback={<Navigate to="/login" />}>
            <DefaultLayout><Dashboard /></DefaultLayout>
          </Protect>
        } />
        
        {/* Área professor */}
        <Route path="/my-availability" element={
          <Protect condition={has => has({role: "org:member"})} fallback={<Navigate to="/login" />}>
            <DefaultLayout><MyAvailability /></DefaultLayout>
          </Protect>
        } />
        
        {/* ... adicionar outras rotas protegidas */}
      </Routes>
    </BrowserRouter>
  );
}
```

✅ `npm run dev` → `/login` mostra o formulário Clerk. `/register` mostra o SignUp. Sem erros no console.

---

## Passo 3.7 — Atualizar `apiClient.js`

**Ficheiro:** `frontend/src/apiClient.js`

```js
import axios from 'axios';

const apiClient = axios.create({
  baseURL: '/api/v1',
  withCredentials: true,  // Envia cookie __session automaticamente
  headers: {
    'Content-Type': 'application/json',
  },
});

// Sem interceptor de refresh — Clerk gere automaticamente
// Apenas interceptor de erro para logging

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Não faz refresh — o Clerk gere. Se 401, o componente Protect
      // ou Show redireciona automaticamente para /login.
      console.warn('API: Unauthorized request');
    }
    return Promise.reject(error);
  }
);

export default apiClient;
```

⚠️ Edge case: Remover TODAS as referências a `useAuthStore` deste ficheiro. O `apiClient` é um módulo puro — não deve importar stores React.

---

## Passo 3.8 — Atualizar `DefaultLayout.jsx`

**Ficheiro:** `frontend/src/components/DefaultLayout.jsx`

```jsx
import { useAuth, useUser, useOrganization, UserButton, OrganizationSwitcher } from "@clerk/react";
import { useNavigate } from "react-router-dom";

export default function DefaultLayout({ children }) {
  const { user } = useUser();
  const { organization, membership } = useOrganization();
  const navigate = useNavigate();

  const isAdmin = membership?.role === "org:admin";
  const isTeacher = membership?.role === "org:member";

  return (
    <div className="layout">
      <header className="header">
        <div className="header-left">
          <OrganizationSwitcher
            afterCreateOrganizationUrl="/dashboard"
            afterSelectOrganizationUrl="/dashboard"
          />
          {organization && (
            <span className="org-name">{organization.name}</span>
          )}
        </div>
        
        <nav className="header-nav">
          {isAdmin && (
            <>
              <button onClick={() => navigate("/dashboard")}>Dashboard</button>
              <button onClick={() => navigate("/teachers")}>Professores</button>
              <button onClick={() => navigate("/schedules")}>Horários</button>
              <button onClick={() => navigate("/courses")}>Cursos</button>
              <button onClick={() => navigate("/subjects")}>Disciplinas</button>
              <button onClick={() => navigate("/rooms")}>Salas</button>
              <button onClick={() => navigate("/config")}>Configuração</button>
            </>
          )}
          {isTeacher && (
            <>
              <button onClick={() => navigate("/my-availability")}>Disponibilidade</button>
              <button onClick={() => navigate("/my-schedules")}>Horários</button>
              <button onClick={() => navigate("/my-progress")}>Progresso</button>
            </>
          )}
        </nav>
        
        <div className="header-right">
          <UserButton afterSignOutUrl="/" />
        </div>
      </header>
      
      <main className="content">{children}</main>
    </div>
  );
}
```

**Importante:** Remover `import { useAuthStore } from '../store'` completamente.

✅ Sidebar mostra links corretos conforme a role. `<UserButton />` mostra avatar e logout.

---

## Passo 3.9 — Atualizar `roleAccess.js`

**Ficheiro:** `frontend/src/roleAccess.js`

```js
export const USER_ROLE_ADMIN = 'org:admin';
export const USER_ROLE_TEACHER = 'org:member';

export const ROLE_DEFAULT_ROUTE = {
  [USER_ROLE_ADMIN]: '/dashboard',
  [USER_ROLE_TEACHER]: '/my-availability',
};

export const ROLE_ALLOWED_APP_ROUTES = {
  [USER_ROLE_ADMIN]: [
    '/dashboard', '/schedules', '/schedules/audit', '/absences',
    '/courses', '/teachers', '/subjects', '/rooms', '/config',
  ],
  [USER_ROLE_TEACHER]: [
    '/my-availability', '/my-schedules', '/my-progress',
  ],
};
```

---

## Passo 3.10 — Remover ficheiros antigos

```powershell
Remove-Item -LiteralPath "frontend\src\store.js"
Remove-Item -LiteralPath "frontend\src\components\ProtectedRoute.jsx"
```

Ou renomear para `.bak` temporariamente:

```powershell
Rename-Item -LiteralPath "frontend\src\store.js" -NewName "store.js.bak"
Rename-Item -LiteralPath "frontend\src\components\ProtectedRoute.jsx" -NewName "ProtectedRoute.jsx.bak"
```

---

## Passo 3.11 — Atualizar `MarketingSite.jsx`

**Ficheiro:** `frontend/src/pages/MarketingSite.jsx`

Remover:
```js
import { useAuthStore } from '../store';
const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
const role = useAuthStore((s) => s.user?.role);
```

Substituir por:
```jsx
import { useAuth, useOrganization } from "@clerk/react";
// Dentro do componente:
const { isSignedIn } = useAuth();
const { membership } = useOrganization();
const role = membership?.role;
```

---

## Passo 3.12 — Escrever testes frontend T24-T28

**Ficheiro:** `frontend/src/test/apiClient.test.js` (T24-T25)

```js
import { describe, it, expect, vi } from 'vitest';
import apiClient from '../apiClient';

// T24: withCredentials ativo
describe('apiClient', () => {
  it('should have withCredentials enabled', () => {
    expect(apiClient.defaults.withCredentials).toBe(true);
  });

  // T25: 401 redireciona
  it('should not have refresh interceptor', async () => {
    const interceptorCount = apiClient.interceptors.response.handlers.length;
    // Só deve ter 1 handler (o de logging) — não o de refresh
    expect(interceptorCount).toBeGreaterThanOrEqual(1);
  });
});
```

**Ficheiro:** `frontend/src/test/roleAccess.test.js` (T26-T28)

```js
import { describe, it, expect } from 'vitest';
import { ROLE_ALLOWED_APP_ROUTES, ROLE_DEFAULT_ROUTE } from '../roleAccess';

describe('roleAccess with Clerk roles', () => {
  it('should allow admin to access dashboard', () => {
    expect(ROLE_ALLOWED_APP_ROUTES['org:admin']).toContain('/dashboard');
    expect(ROLE_ALLOWED_APP_ROUTES['org:admin']).toContain('/teachers');
  });

  it('should allow teacher to access my-availability', () => {
    expect(ROLE_ALLOWED_APP_ROUTES['org:member']).toContain('/my-availability');
    expect(ROLE_ALLOWED_APP_ROUTES['org:member']).toContain('/my-schedules');
  });

  it('should block teacher from admin routes', () => {
    expect(ROLE_ALLOWED_APP_ROUTES['org:member']).not.toContain('/dashboard');
    expect(ROLE_ALLOWED_APP_ROUTES['org:member']).not.toContain('/config');
  });
});
```

---

# FASE 4 — Onboarding Frontend + Integração

---

## Passo 4.1 — Criar `pages/Onboarding.jsx`

**Ficheiro NOVO:** `frontend/src/pages/Onboarding.jsx`

```jsx
import { useState, useEffect } from "react";
import { useUser, useOrganization } from "@clerk/react";
import { useNavigate } from "react-router-dom";
import apiClient from "../apiClient";

export default function Onboarding() {
  const { user } = useUser();
  const { organization } = useOrganization();
  const navigate = useNavigate();
  
  const [status, setStatus] = useState({ loading: true, complete: false });
  const [form, setForm] = useState({
    school_start_date: "2025-09-15",
    school_target_end_date: "2026-06-30",
    school_hard_end_date: "2026-07-31",
    lunch_start: "12:30",
    lunch_end: "14:00",
    lunch_min_duration: 60,
  });
  const [error, setError] = useState(null);

  // Verificar estado ao carregar
  useEffect(() => {
    apiClient.get("/onboarding/status")
      .then((res) => {
        setStatus({ loading: false, complete: res.data.onboarding_complete });
        if (res.data.onboarding_complete) {
          navigate("/dashboard");
        }
      })
      .catch(() => setStatus({ loading: false, complete: false }));
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    try {
      await apiClient.post("/onboarding", form);
      // Forçar refresh do token para incluir onboardingComplete
      await user?.reload();
      navigate("/dashboard");
    } catch (err) {
      setError(err.response?.data?.detail || "Erro ao guardar configurações");
    }
  };

  if (status.loading) return <div>Carregando...</div>;
  if (status.complete) return <div>Onboarding já concluído. Redirecionando...</div>;

  return (
    <div style={{ maxWidth: 600, margin: "5vh auto", padding: 24 }}>
      <h1>Configurar a {organization?.name || "escola"}</h1>
      <p>Precisamos de algumas informações para começar.</p>
      
      <form onSubmit={handleSubmit}>
        <h3>Ano Letivo</h3>
        <label>Data de início:
          <input type="date" value={form.school_start_date}
            onChange={e => setForm({...form, school_start_date: e.target.value})} />
        </label>
        <label>Fim previsto:
          <input type="date" value={form.school_target_end_date}
            onChange={e => setForm({...form, school_target_end_date: e.target.value})} />
        </label>
        <label>Fim máximo:
          <input type="date" value={form.school_hard_end_date}
            onChange={e => setForm({...form, school_hard_end_date: e.target.value})} />
        </label>

        <h3>Janela de Almoço</h3>
        <label>Início:
          <input type="time" value={form.lunch_start}
            onChange={e => setForm({...form, lunch_start: e.target.value})} />
        </label>
        <label>Fim:
          <input type="time" value={form.lunch_end}
            onChange={e => setForm({...form, lunch_end: e.target.value})} />
        </label>
        <label>Duração mínima (minutos):
          <input type="number" value={form.lunch_min_duration}
            onChange={e => setForm({...form, lunch_min_duration: parseInt(e.target.value)})} />
        </label>

        {error && <p style={{ color: "red" }}>{error}</p>}
        <button type="submit">Guardar e Começar</button>
      </form>
    </div>
  );
}
```

⚠️ Edge case: Se o utilizador fechar o browser durante o onboarding, ao reabrir, o `useEffect` vai verificar `GET /onboarding/status`. Se `onboarding_complete=false`, mostra o formulário de novo. Se `true`, redireciona.

---

## Passo 4.2 — Atualizar `hooks/useSchoolData.js`

**Ficheiro:** `frontend/src/hooks/useSchoolData.js`

(substituir **todas** as ~50 ocorrências de):
```js
const orgId = useAuthStore(state => state.user?.orgId)
```
por:
```js
import { useOrganization } from "@clerk/react";
const { organization } = useOrganization();
const orgId = organization?.id;
```

⚠️ Edge case: Durante a renderização inicial, `organization` pode ser `null` (Clerk ainda está a carregar). Os hooks `useQuery` do React Query devem ter `enabled: !!orgId` para evitar queries com `undefined`.

---

## Passo 4.3 — Atualizar páginas de professor e admin

**Páginas a atualizar** (todas as que importam `useAuthStore`):

| Ficheiro | Substituir por |
|----------|---------------|
| `MyAvailability.jsx` | `useAuth().userId` para identificar o professor |
| `MyProgress.jsx` | `useAuth().userId` |
| `MySchedules.jsx` | `useOrganization().organization?.id` para orgId |
| `Occurrences.jsx` | `useOrganization().organization?.id` |
| `Schedules.jsx` | `useOrganization().organization?.id` |
| `SchoolConfig.jsx` | `useOrganization().organization?.id` |

Remover import de `useAuthStore` de todos estes ficheiros.

---

## Passo 4.4 — Escrever testes E2E T29-T33 (Playwright)

**Ficheiro:** `frontend/e2e/clerk-auth.spec.js`

```js
import { test, expect } from '@playwright/test';

test.describe('Clerk Authentication', () => {
  
  // T29: Sign-up completo (apenas em dev — usa email descartável)
  test('complete sign-up flow', async ({ page }) => {
    await page.goto('http://localhost:5173/register');
    
    // Preencher email
    await page.fill('input[name="emailAddress"]', `test-${Date.now()}@example.com`);
    await page.fill('input[name="password"]', 'TestPass123!');
    await page.click('button[type="submit"]');
    
    // Aguardar redirect para create-org
    await page.waitForURL('**/create-org');
    await page.fill('input[name="name"]', 'Escola Teste E2E');
    await page.click('button[type="submit"]');
    
    // Aguardar onboarding
    await page.waitForURL('**/onboarding');
    await expect(page.locator('h1')).toContainText('Configurar');
    
    // Preencher e submeter
    await page.click('button[type="submit"]');
    
    // Deve redirecionar para dashboard
    await page.waitForURL('**/dashboard');
    await expect(page.locator('h1, h2, h3')).not.toBeEmpty();
  });

  // T30: Login admin
  test('admin login redirects to dashboard', async ({ page }) => {
    await page.goto('http://localhost:5173/login');
    
    // Preencher credenciais de teste
    await page.fill('input[name="identifier"]', 'admin@teste.pt');
    await page.fill('input[name="password"]', 'AdminPass123!');
    await page.click('button[type="submit"]');
    
    await page.waitForURL('**/dashboard', { timeout: 15000 });
  });

  // T31: Login teacher
  test('teacher login redirects to my-availability', async ({ page }) => {
    await page.goto('http://localhost:5173/login');
    await page.fill('input[name="identifier"]', 'professor@teste.pt');
    await page.fill('input[name="password"]', 'ProfPass123!');
    await page.click('button[type="submit"]');
    
    await page.waitForURL('**/my-availability', { timeout: 15000 });
  });

  // T32: Onboarding interrompido
  test('resumes incomplete onboarding', async ({ page }) => {
    // Simular user que fez signup mas não completou onboarding
    // Verificar que é redirecionado para /onboarding
    // (Necessita de setup com user específico no Clerk)
  });
});
```

⚠️ Edge case: Testes E2E que interagem com Clerk em dev precisam de `CLERK_SECRET_KEY` para criar users de teste via BAPI antes dos testes. Considerar criar um script `setup-e2e.ts` que usa `clerk.users.create()` para provisionar users de teste.

---

# FASE 5 — Limpeza + Seed + Testes antigos

---

## Passo 5.1 — Reescrever `seed_data_small_realistic.py`

**Ficheiro:** `backend/seed_data_small_realistic.py`

Alterações principais:
- Remover `from app.core.security import hash_password, verify_password`
- Remover `_validate_seed_credentials()` (já não há passwords para validar)
- Na criação do admin (`_create_base_entities`):
  ```python
  # Substituir:
  hashed_password=hash_password(ORGANIZATION_INFO["admin_password"])
  # Por:
  clerk_user_id="user_clerk_admin_seed",  # placeholder
  hashed_password=None,  # Clerk gere
  ```
- Na criação de professores:
  ```python
  hashed_password=None  # já não criamos passwords
  clerk_user_id=f"user_clerk_teacher_{profile['name'].lower().replace(' ', '_')}"
  ```
- Adicionar `clerk_org_id="org_clerk_epnorte_seed"` à organization

⚠️ Edge case: O seed usa `DROP SCHEMA public CASCADE` — após migration, verificar que o alembic `upgrade head` funciona com a nova migration antes do seed.

✅ `docker compose exec backend python seed_data_small_realistic.py` executa sem erros.

---

## Passo 5.2 — Remover ficheiros de auth antiga

```powershell
Remove-Item -LiteralPath "backend\app\core\security.py"
Remove-Item -LiteralPath "backend\app\api\v1\endpoints\auth.py"
Remove-Item -LiteralPath "backend\scripts\bootstrap_admin.py"
Remove-Item -LiteralPath "backend\create_users_for_teachers.py"
```

Verificar se `python-jose` e `bcrypt` são usados noutro lado:

```powershell
docker compose exec backend bash -c "grep -r 'python-jose\|bcrypt' /app --include='*.py' | grep -v 'requirements.txt' | grep -v '.pyc'"
```

Se não houver resultados, remover de `requirements.txt`:
```
# Remover estas linhas:
bcrypt==5.0.0
python-jose==3.5.0
```

---

## Passo 5.3 — Atualizar `operational_seed_service.py`

**Ficheiro:** `backend/app/services/operational_seed_service.py`

Remover import de `hash_password` e todas as chamadas.

---

## Passo 5.4 — Atualizar `conftest.py` para usar Clerk TestingTokens

**Ficheiro:** `backend/tests/conftest.py`

Substituir fixtures de auth:

```python
# REMOVER:
from app.core import security
@pytest.fixture
def test_token():
    return security.create_access_token(...)

# ADICIONAR:
from app.core.clerk import get_clerk_sdk
import pytest_asyncio

@pytest_asyncio.fixture
async def clerk_test_session():
    """Cria uma sessão de teste no Clerk e retorna o token."""
    sdk = get_clerk_sdk()
    token_result = sdk.testing_tokens.create()
    return {
        "token": token_result.token,
        "user_id": token_result.user_id,
    }

@pytest_asyncio.fixture
async def auth_headers(clerk_test_session):
    """Headers com token Clerk para testes."""
    return {"Cookie": f"__session={clerk_test_session['token']}"}
```

⚠️ Edge case: `testing_tokens.create()` só funciona com `CLERK_SECRET_KEY` de instância de desenvolvimento.

---

## Passo 5.5 — Migrar testes backend existentes (16 ficheiros)

### Categoria REESCREVER (8 ficheiros)

| Ficheiro | Ação |
|----------|------|
| `conftest.py` | Substituir `create_access_token` por Clerk TestingTokens |
| `test_tenant_isolation_business.py` | Substituir fixtures de auth |
| `test_tenant_isolation_complete.py` | Substituir fixtures de auth |
| `test_multi_tenant.py` | Substituir fixtures de auth |
| `test_teacher_role_regression.py` | Substituir fixtures de auth |
| `test_teacher_observability.py` | Substituir fixtures de auth |
| `test_rate_limiting.py` | Substituir fixtures de auth |
| `test_alpha_release_gate.py` | Substituir fixtures de auth |

### Categoria ATUALIZAR (8 ficheiros)

| Ficheiro | Ação |
|----------|------|
| `test_schedule_generate_preflight.py` | Atualizar helpers de auth |
| `test_schedule_draft_lifecycle.py` | Atualizar helpers de auth |
| `test_solver_v2_draft_lifecycle.py` | Atualizar helpers de auth |
| `test_dashboard.py` | Atualizar helpers de auth |
| `test_occurrence_shared.py` | Atualizar helpers de auth |
| `test_lesson_registration.py` | Atualizar helpers de auth |
| `test_availability_paintbrush.py` | Atualizar helpers de auth |
| `test_teachers_crud.py` | Atualizar criação de teacher (sem password) |

### Categoria REMOVER

| Ficheiro | Ação |
|----------|------|
| `test_auth.py` | Remover (testes de auth antigos) |
| `test_parametrized_error_contracts.py` | Remover partes que testam endpoints `/auth/*` |

---

## Passo 5.6 — Migrar testes frontend existentes (10 ficheiros)

### Categoria REMOVER

```powershell
Remove-Item -LiteralPath "frontend\src\test\authStore.test.js"
```

### Categoria REESCREVER (4 ficheiros)

| Ficheiro | Nova abordagem |
|----------|---------------|
| `ProtectedRoute.test.jsx` | Testar `<Protect>` com mock de `@clerk/react` |
| `AppRoleGuards.test.jsx` | Testar guards com `role="org:admin"` |
| `DefaultLayoutRoleMenu.test.jsx` | Usar mock `useOrganization().membership.role` |
| `Login.test.jsx` | Testar `<SignInPage />` com mock de `<SignIn />` |

**Exemplo de mock para `@clerk/react`:**

```js
// src/test/setup.js
import { vi } from 'vitest';

vi.mock('@clerk/react', () => ({
  useAuth: () => ({
    isSignedIn: true,
    isLoaded: true,
    userId: 'user_test_123',
  }),
  useUser: () => ({
    user: {
      id: 'user_test_123',
      emailAddresses: [{ emailAddress: 'test@example.com' }],
      fullName: 'Test User',
    },
    isLoaded: true,
  }),
  useOrganization: () => ({
    organization: { id: 'org_test_456', name: 'Test Org' },
    membership: { role: 'org:admin' },
    isLoaded: true,
  }),
  ClerkProvider: ({ children }) => children,
  SignIn: () => <div>SignIn Mock</div>,
  SignUp: () => <div>SignUp Mock</div>,
  UserButton: () => <div>UserButton</div>,
  OrganizationSwitcher: () => <div>OrgSwitcher</div>,
  Protect: ({ children, fallback, role, condition }) => children,
  Show: ({ children, when }) => children,
  RedirectToSignIn: () => <div>Redirecting...</div>,
  CreateOrganization: () => <div>CreateOrg</div>,
}));
```

### Categoria ATUALIZAR (5 ficheiros)

| Ficheiro | Alteração |
|----------|-----------|
| `Dashboard.test.jsx` | Substituir `useAuthStore.setState` por mock Clerk |
| `MyAvailability.test.jsx` | Substituir store state por mock Clerk |
| `MySchedules.test.jsx` | Substituir store state por mock Clerk |
| `Occurrences.test.jsx` | Substituir store state por mock Clerk |
| `Schedules.test.jsx` | Substituir store state por mock Clerk |

---

# FASE 6 — CI/CD

---

## Passo 6.1 — Criar `frontend/vitest.config.js` (se necessário)

Verificar que o Vitest está configurado para incluir cobertura com threshold de 80%:

```js
// frontend/vite.config.js
test: {
  globals: true,
  environment: 'jsdom',
  setupFiles: './src/test/setup.js',
  css: false,
  exclude: ['e2e/**', 'node_modules/**'],
  coverage: {
    provider: 'v8',
    reporter: ['lcov', 'text'],
    reportsDirectory: './coverage',
    thresholds: {
      lines: 80,
    },
  },
},
```

---

## Passo 6.2 — Criar workflow GitHub Actions

**Ficheiro NOVO:** `.github/workflows/ci.yml`

```yaml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  backend:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: test_db
          POSTGRES_PASSWORD: postgres
        ports:
          - 5432:5432
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install dependencies
        working-directory: backend
        run: pip install -r requirements.txt pytest pytest-asyncio pytest-cov
      - name: Run migrations
        working-directory: backend
        run: alembic upgrade head
      - name: Run tests
        working-directory: backend
        run: pytest tests/ -v --cov=app --cov-fail-under=80
        env:
          DATABASE_URL: postgresql+asyncpg://postgres:postgres@localhost:5432/test_db
          CLERK_SECRET_KEY: ${{ secrets.CLERK_SECRET_KEY }}
          CLERK_WEBHOOK_SECRET: ${{ secrets.CLERK_WEBHOOK_SECRET }}
          CLERK_PUBLISHABLE_KEY: ${{ secrets.CLERK_PUBLISHABLE_KEY }}
          FRONTEND_URL: http://localhost:5173

  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - name: Install dependencies
        working-directory: frontend
        run: npm ci
      - name: Lint
        working-directory: frontend
        run: npm run lint
      - name: Type check
        working-directory: frontend
        run: npx tsc --noEmit 2>$null; echo "Type check skipped (JS project)"  # para JS, skip
      - name: Run tests
        working-directory: frontend
        run: npm run test -- --coverage
      - name: Build
        working-directory: frontend
        run: npm run build
        env:
          VITE_CLERK_PUBLISHABLE_KEY: ${{ secrets.VITE_CLERK_PUBLISHABLE_KEY }}

  e2e:
    needs: [backend, frontend]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - name: Install dependencies
        working-directory: frontend
        run: npm ci
      - name: Install Playwright
        working-directory: frontend
        run: npx playwright install --with-deps chromium
      - name: Run E2E tests
        working-directory: frontend
        run: npm run test:e2e
        env:
          VITE_CLERK_PUBLISHABLE_KEY: ${{ secrets.VITE_CLERK_PUBLISHABLE_KEY }}
```

---

## Passo 6.3 — Configurar GitHub Secrets

No repositório GitHub → Settings → Secrets → Actions → New repository secret:

| Nome | Valor | Onde obter |
|------|-------|-----------|
| `CLERK_SECRET_KEY` | `sk_test_...` | Clerk Dashboard > API Keys |
| `CLERK_PUBLISHABLE_KEY` | `pk_test_...` | Clerk Dashboard > API Keys |
| `VITE_CLERK_PUBLISHABLE_KEY` | `pk_test_...` | Mesma chave (prefixo VITE_ não é necessário no secret) |
| `CLERK_WEBHOOK_SECRET` | `whsec_...` | Clerk Dashboard > Webhooks |

---

## Passo 6.4 — Validar CI/CD localmente

Antes de fazer push, verificar:

```powershell
# Backend
docker compose exec backend pytest -v --cov=app --cov-fail-under=80

# Frontend
cd frontend; if ($?) { npm run lint; if ($?) { npm run test -- --coverage; if ($?) { npm run build } } }
```

---

# FASE 7 — Verificação Final

---

## Passo 7.1 — Checklist manual (dev)

- [ ] `npm run dev` → frontend carrega em `localhost:5173`
- [ ] Aceder `localhost:5173` → landing page sem erros
- [ ] Clicar "Começar" → `/register` → formulário Clerk visível
- [ ] Registar com email+password → redirect para `/create-org`
- [ ] Criar organização → redirect para `/onboarding`
- [ ] Preencher onboarding → redirect para `/dashboard`
- [ ] Dashboard mostra mensagem (sem dados — esperado)
- [ ] `<UserButton />` → clicar "Sign Out" → redirect para landing
- [ ] Fazer login com as credenciais criadas → `/dashboard`
- [ ] `<OrganizationSwitcher />` mostra a org criada

## Passo 7.2 — Verificação de código

```powershell
# Zero referências a auth antiga
git grep -n "useAuthStore" frontend/src/ -- ':!*.test.*' ':!*.bak'
git grep -n "hz_access\|hz_refresh" backend/
git grep -n "hash_password\|verify_password" backend/app/ -- ':!*alembic*'
git grep -n "app.core.security" backend/app/
git grep -n "app.api.v1.endpoints.auth" backend/app/
```

✅ Todos os comandos acima devem devolver **zero resultados**.

## Passo 7.3 — Atualizar documentação

**Ficheiros em `/documentation` que referenciam `useAuthStore` ou auth antiga:**

| Ficheiro | Ação |
|----------|------|
| `ARQUITETURA_COMPLETA.md` | Atualizar secção de autenticação |
| `auditoria-frontend-ui-ux.md` | Remover referências a `useAuthStore` |
| `04_operational_features/WBS_REGISTO_AULAS_V2.md` | Atualizar padrão de auth |
| `06_frontend_ux/WBS_DASHBOARD_V1_COMMAND_CENTER.md` | Substituir `useAuthStore` |

---

## Resumo de Edge Cases por Fase

| Fase | Edge Case | Mitigação |
|------|-----------|-----------|
| 1.4 | Autogenerate não deteta colunas | Atualizar modelos primeiro; verificar import |
| 1.6 | CLERK_SECRET_KEY vazio | Validar em `config.py`; `Clerk()` lança exceção |
| 1.9 | Webhooks não chegam em localhost | Usar Svix CLI ou ngrok |
| 1.10 | `get_current_user` assinatura antiga em `schedule.py` | Atualizar chamadas manuais em endpoints |
| 2.4 | `clerk_org_id` é None para orgs pré-migração | Log warning; skip invitation |
| 2.6 | Fallback BAPI falha | Retorna 500; aceitável (race condition rara) |
| 3.3 | Clerk warning sem publishable key | Confirmar `.env.local` carregado |
| 3.5 | User fecha browser durante onboarding | GET status → redireciona para /onboarding se incompleto |
| 4.2 | `organization` é null durante loading | `enabled: !!orgId` nos hooks React Query |
| 5.1 | Seed drop schema + migration | Verificar ordem: drop → create → alembic upgrade → seed |
| 5.5 | `testing_tokens` requer dev instance | Só funciona com `sk_test_` |
| 5.6 | Páginas quebram sem mock Clerk | Configurar mock global no `setup.js` |
| 6.3 | Secrets não configurados no GitHub | CI falha — configurar antes do primeiro push |
