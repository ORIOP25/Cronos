# PRD — Migração de Autenticação para Clerk

**Projeto:** Cronos
**Data:** 2026-05-12
**Versão:** 2.1 (com correções de revisão)
**Status:** Aprovado para implementação

---

## 1. Sumário Executivo

Migração completa do sistema de autenticação customizado (email+password, JWT HS256, bcrypt) para o Clerk, usando **Clerk Organizations para B2B multi-tenant** e **autenticação de utilizador para B2C**.

### 1.1 Motivação

- Segurança reforçada (Clerk gere passwords, 2FA, deteção de fraude, rate limiting)
- B2B nativo: Organizations, convites, roles, domínios verificados
- Plano gratuito generoso (100 Monthly Retained Organizations em produção)
- Menos código para manter (zero linhas de auth customizada)

### 1.2 Objetivos Mensuráveis

| Métrica | Alvo |
|---------|------|
| Zero passwords em plaintext na BD | ✅ |
| Login/Sign-up 100% via Clerk (sem endpoints custom de auth) | ✅ |
| Multi-tenancy via Clerk Organizations mapeada 1:1 com `organization` local | ✅ |
| RBAC funcional com `org:admin` (diretor) e `org:member` (professor) | ✅ |
| Cobertura de testes ≥ 80% em auth e webhook handlers | ✅ |
| Pipeline CI/CD (GitHub Actions) com lint + test + typecheck por commit | ✅ |

---

## 2. Decisões de Arquitetura

### 2.1 Abordagem escolhida: Clerk Organizations (Opção A)

Cada escola = 1 Clerk Organization. O diretor cria a Organization via `<CreateOrganization />`. Professores são convidados via Clerk Invitations. Webhooks sincronizam a BD local.

### 2.2 Domínio único (mesma origin)

**Um único domínio** `apérius.pt` serve tanto o frontend como o backend:

```
apérius.pt          →  Frontend (React + Vite)
apérius.pt/api/*    →  Backend (FastAPI), via proxy reverso (nginx em produção, Vite proxy em dev)
```

**Vantagens desta abordagem:**
- **Same-origin**: o cookie `__session` do Clerk é enviado automaticamente em todos os pedidos à API — zero complexidade de `getToken()` manual ou headers `Authorization`.
- Sem CORS cross-origin em produção (mesmo domínio).
- Um único certificado TLS.
- Setup mais simples e menor superfície de ataque.

**Em desenvolvimento local:**
- Frontend: `http://localhost:5173` (Vite)
- Backend: `http://localhost:8000` (FastAPI)
- Vite faz proxy de `/api/*` → `localhost:8000` (já configurado em `vite.config.js`).
- Axios com `withCredentials: true` para envio de cookies cross-port.
- Clerk em dev usa `__clerk_db_jwt` (querystring) — funciona sem configuração extra.

### 2.3 Onboarding pós sign-up (tudo dentro de apérius.pt)

Os componentes `<SignIn />`, `<SignUp />`, `<CreateOrganization />` do Clerk são **componentes React que renderizam dentro da aplicação**, no domínio `apérius.pt`. O utilizador **nunca sai do site** nem visita clerk.com.

```
Fluxo completo (tudo em apérius.pt):

  apérius.pt
    │
    ├─ /              → Landing page
    │                   [botão "Começar"]
    │
    ├─ /register      → <SignUp />
    │                   Email+password ou Google/Microsoft (renderizado na app)
    │                   ↓
    ├─ /create-org    → <CreateOrganization />
    │                   Utilizador dá nome à escola
    │                   ↓ Clerk dispara webhooks (ASSÍNCRONO — pode chegar depois do redirect!)
    │
    ├─ /onboarding    → Página NOSSA (custom)
    │   (GET)         → Verifica se user local existe. Se não → cria via BAPI do Clerk (fallback síncrono)
    │   (POST)        → Guarda OrganizationSettings + OrganizationGridSettings
    │                   ↓
    └─ /dashboard     → App (admin)
```

**Tratamento de race condition (webhook vs onboarding):**
1. User acede a `/onboarding` → frontend faz GET ao backend
2. Backend tenta `get_current_user()` pela DB local
3. Se user NÃO existe → faz fallback: chama `clerk_client.users.get(user_id)` via BAPI + `clerk_client.organizations.get(org_id)` → cria `user` + `organization` row local **sincronamente**
4. Se user existe → segue normalmente
5. POST `/api/v1/onboarding` → guarda configurações

### 2.4 Roles

| Clerk Role | Role local | Quem |
|------------|-----------|------|
| `org:admin` | `admin` | Diretores de escola |
| `org:member` | `teacher` | Professores |

**Justificação:** Roles customizadas (`org:teacher`) requerem plano pago em produção. Os defaults gratuitos (`org:admin`, `org:member`) cobrem o caso de uso.

### 2.5 Métodos de Autenticação

- Email + password (obrigatório, sempre disponível)
- Google OAuth (ativado no Dashboard)
- Microsoft OAuth (ativado no Dashboard)

### 2.6 Metadata Strategy

`public_metadata` no Clerk (disponível no plano gratuito) para dados leves:
- `teacher_id` — link para a tabela `teacher` local (definido no convite ou após criação)

Dados pesados (configurações da escola, disciplinas) ficam na BD local.

### 2.7 Fluxo de criação de professores com Clerk

```
1. Admin preenche formulário "Criar Professor" (nome, email, disciplinas)
2. Backend cria Teacher row local (organização, nome)
3. Backend chama Clerk BAPI:
   POST /organizations/{clerk_org_id}/invitations
   Body: { email_address, role: "org:member", public_metadata: { teacher_id: 123 } }
4. Professor recebe email do Clerk, clica em "Accept"
5. Webhook organizationMembership.created → backend:
   - Cria/atualiza User row local (clerk_user_id, email, role='teacher', org_id)
   - Lê public_metadata.teacher_id → define user.teacher_id = 123
6. Professor faz login → já tem teacher_id associado → vê MyAvailability
```

**Professores sem user account (`create_user_account=False`):**
- Apenas `Teacher` rows sem `User` vinculado. Sem convite Clerk. Continuam a existir como dados.
- O campo `teacher_id` na tabela `user` continua a permitir NULL.

### 2.8 Campo `is_superuser`

Mantém-se como campo manual na BD local (`is_superuser BOOLEAN DEFAULT FALSE`). Não é gerido pelo Clerk. Usado apenas para administração interna/debug — atribuído diretamente na BD.

---

## 3. Arquitetura Técnica

### 3.1 Diagrama de Componentes

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           CLERK (SaaS)                                    │
│  ┌──────────┐  ┌──────────────────┐  ┌───────────────────────────────┐  │
│  │  Users   │  │  Organizations   │  │  Webhooks (Svix)              │  │
│  │  - email │  │  - org_xxx       │  │  → user.created               │  │
│  │  - name  │  │  - name          │  │  → organization.created       │  │
│  │  - meta  │  │  - members       │  │  → organizationMembership.*   │  │
│  │          │  │  - roles         │  │  → session.created/ended      │  │
│  └──────────┘  └──────────────────┘  └───────────────────────────────┘  │
│                                                                          │
│  ┌────────────────────────────────────┐  ┌───────────────────────────┐  │
│  │  FAPI (Frontend API)               │  │  BAPI (Backend API)       │  │
│  │  ┌────────────────────────────┐    │  │  - authenticate_request() │  │
│  │  │ Session Token (60s)        │    │  │  - users.get()            │  │
│  │  │ claims: sub, o.id, o.rol   │    │  │  - organizations.get()    │  │
│  │  │ o.slg, sid, azp, ...       │    │  │  - invitations.create()   │  │
│  │  └────────────────────────────┘    │  │  - testing_tokens.create()│  │
│  └────────────────────────────────────┘  └───────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
          │                                              ▲
          │  ┌──────────────────────────────┐            │
          │  │ Componentes React (na app)   │            │
          │  │ <SignIn /> <SignUp />        │            │
          │  │ <CreateOrganization />       │            │
          │  │ <OrganizationSwitcher />     │            │
          │  │ <UserButton />               │   Webhooks │
          │  └──────────────────────────────┘   (Svix)   │
          │                                              │
          ▼                                              │
┌──────────────────────────────────────────────────────────────────┐
│                     apérius.pt (mesmo domínio)                    │
│                                                                   │
│  ┌─────────────────────────┐    ┌─────────────────────────────┐  │
│  │  FRONTEND (Vite+React)  │    │  BACKEND (FastAPI)          │  │
│  │  /, /login, /register,  │    │  /api/v1/*                  │  │
│  │  /dashboard, /onboarding│    │  /api/v1/webhooks/clerk     │◄─┤
│  │                         │    │                             │  │
│  │  <ClerkProvider>        │    │  clerk_auth() -> deps       │  │
│  │  Cookie __session       │    │  clerk_sync.py              │  │
│  │  (same-origin, auto)────┼───→│  PostgreSQL                 │  │
│  │                         │    │                             │  │
│  │  Proxy reverso:         │    │                             │  │
│  │  / → frontend           │    │                             │  │
│  │  /api/* → backend       │    │                             │  │
│  └─────────────────────────┘    └─────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### 3.2 Fluxo de Autenticação por Pedido (same-origin)

```
1. Browser → GET https://apérius.pt/api/v1/teachers
2. Cookie __session enviado automaticamente (same-origin)
3. Backend: clerk_sdk.authenticate_request(request, authorized_parties=[settings.FRONTEND_URL])
4. Backend: extrai user_id do payload.sub, org_id do payload.o.id, role do payload.o.rol
5. Backend: query à DB local para metadados extra (teacher_id, is_active, etc.)
6. Se user NÃO existe na DB → fallback: cria via BAPI (ver secção 3.4)
7. Backend: retorna dados filtrados por organization_id
```

### 3.3 Estrutura do Token (Session Token v2)

```json
{
  "sub": "user_xxx",        // Clerk User ID
  "sid": "sess_xxx",        // Session ID
  "azp": "https://apérius.pt",
  "iss": "https://clerk.apérius.pt",
  "iat": 1713158400,
  "exp": 1713158460,
  "o": {
    "id": "org_xxx",        // Clerk Organization ID
    "rol": "admin",         // Role sem prefixo (admin | member)
    "slg": "escola-x"
  }
}
```

### 3.4 Fallback síncrono — User não existe na DB local

```python
# app/api/deps.py — get_current_user()

async def get_current_user(request: Request, db: Session) -> models.User:
    claims = get_clerk_payload(request)
    user_id = claims["sub"]
    
    # 1. Tentar DB local
    user = await db.query(models.User).filter(
        models.User.clerk_user_id == user_id
    ).first()
    
    if user:
        return user
    
    # 2. Fallback: criar via BAPI (race condition com webhooks)
    clerk = get_clerk_sdk()
    clerk_user = await clerk.users.get_async(user_id)
    
    # Extrair org_id do token
    org_id = claims.get("o", {}).get("id")
    clerk_org = await clerk.organizations.get_async(org_id) if org_id else None
    
    # Criar registos locais sincronamente
    user = await clerk_sync.create_user_and_org_sync(db, clerk_user, clerk_org, claims)
    
    return user
```

---

## 4. Alterações à Base de Dados

### 4.1 Nova Migration: `add_clerk_integration`

```sql
-- Tabela organization
ALTER TABLE organization
  ADD COLUMN clerk_org_id VARCHAR(255) UNIQUE;

-- Tabela user
ALTER TABLE "user"
  ADD COLUMN clerk_user_id VARCHAR(255) UNIQUE,
  ALTER COLUMN hashed_password DROP NOT NULL;

-- Migration final (após migração completa, numa fase posterior):
-- ALTER TABLE "user" DROP COLUMN hashed_password;
```

### 4.2 Seed atualizado

O ficheiro `seed_data_small_realistic.py` será reescrito para:
- Não usar `hash_password` / `verify_password`
- Usar `clerk_user_id` e `clerk_org_id` com valores placeholder
- Dados de domínio (cursos, turmas, professores) mantêm-se
- Criar registos de teste via BAPI do Clerk (`POST /testing_tokens`)

---

## 5. Backend — Plano de Alterações

### 5.1 Ficheiros a REMOVER

| Ficheiro | Justificação |
|----------|-------------|
| `app/core/security.py` | bcrypt + JWT custom |
| `app/api/v1/endpoints/auth.py` | `/token`, `/register`, `/refresh`, `/logout` |
| `scripts/bootstrap_admin.py` | Usa `hash_password` |
| `create_users_for_teachers.py` | Usa `hash_password` |

### 5.2 Ficheiros a CRIAR

| Ficheiro | Responsabilidade |
|----------|-----------------|
| `app/core/clerk.py` | Singleton `Clerk` SDK, `authenticate_request()` wrapper |
| `app/api/v1/endpoints/webhooks.py` | Handler de webhooks Clerk (Svix) |
| `app/schemas/webhooks.py` | Schemas Pydantic para payloads de webhook |
| `app/api/v1/endpoints/onboarding.py` | Endpoint de onboarding pós-signup |
| `app/schemas/onboarding.py` | Schema para dados de onboarding |
| `app/services/clerk_sync.py` | Sincronização Clerk ↔ BD local + fallback síncrono |

### 5.3 Ficheiros a MODIFICAR

| Ficheiro | Alteração |
|----------|-----------|
| `app/config.py` | Adicionar `CLERK_SECRET_KEY`, `CLERK_WEBHOOK_SECRET`, `CLERK_PUBLISHABLE_KEY`, `FRONTEND_URL` |
| `app/models.py` | Adicionar `clerk_user_id`, `clerk_org_id`; `hashed_password` → nullable |
| `app/schemas.py` | Remover `Token`, `TokenPayload`, `RegisterRequest`, `LoginRequest`; adicionar `ClerkUserRead`; `UserCreate` sem `password` |
| `app/api/deps.py` | Substituir `get_current_user` → verificação Clerk + fallback BAPI; manter `get_current_active_user`, `get_current_active_admin` |
| `app/api/api.py` | Remover router de auth; adicionar routers de webhooks e onboarding |
| `app/main.py` | **Atualizar CSP** para permitir Clerk; ajustar CORS; adicionar rota webhook sem auth |
| `app/services/user_service.py` | Remover `hash_password`, `create_user` com password; adicionar `get_or_create_user_by_clerk_id()`, `sync_user_from_clerk()` |
| `app/services/teacher_service.py` | `create_teacher()` já não gera password; adicionar `invite_teacher_to_clerk()` |
| `app/services/organization_service.py` | Onboarding + `create_organization_from_clerk()` |
| `app/services/operational_seed_service.py` | Remover `hash_password` |
| `requirements.txt` | Adicionar `clerk-backend-api`, `svix`; remover `bcrypt`, `python-jose` (se não usados noutro lado) |

### 5.4 Middleware CSP — atualização crítica

```python
# app/main.py — security_headers middleware
# ANTES:
response.headers["Content-Security-Policy"] = "default-src 'none'"

# DEPOIS (dev):
response.headers["Content-Security-Policy"] = (
    "default-src 'self'; "
    "script-src 'self' https://*.clerk.accounts.dev; "
    "connect-src 'self' https://*.clerk.accounts.dev; "
    "img-src 'self' https://img.clerk.com data:; "
    "style-src 'self' 'unsafe-inline' https://*.clerk.accounts.dev; "
    "frame-src 'self' https://*.clerk.accounts.dev; "
    "frame-ancestors 'self'"
)
# Em produção, substituir *.clerk.accounts.dev por clerk.apérius.pt
```

---

## 6. Frontend — Plano de Alterações

### 6.1 Ficheiros a REMOVER

| Ficheiro | Justificação |
|----------|-------------|
| `components/ProtectedRoute.jsx` | Substituído por `<Protect>` do Clerk |
| `store.js` | Ficheiro completo — só contém auth store. Sem outros stores. |

### 6.2 Ficheiros a CRIAR

| Ficheiro | Responsabilidade |
|----------|-----------------|
| `pages/Onboarding.jsx` | Formulário de onboarding pós-signup |
| `pages/SignInPage.jsx` | Página `/login` com `<SignIn />` |
| `pages/SignUpPage.jsx` | Página `/register` com `<SignUp />` |

### 6.3 Ficheiros a MODIFICAR

| Ficheiro | Alteração |
|----------|-----------|
| `main.jsx` | Adicionar `<ClerkProvider>` (sem prop manual de `publishableKey` — usa `VITE_CLERK_PUBLISHABLE_KEY` automático) |
| `App.jsx` | Rotas: `/login`, `/register`, `/onboarding`; substituir guards por `<Protect>`; `<Show>` para landing |
| `apiClient.js` | Remover interceptor de refresh JWT; `withCredentials: true`; remover `useAuthStore` |
| `pages/Login.jsx` | Substituir formulário por `<SignIn />` |
| `pages/Register.jsx` | Substituir por `<SignUp />` |
| `pages/MarketingSite.jsx` | Substituir `useAuthStore` por `<Show>` / `useAuth()` |
| `pages/Occurrences.jsx` | Substituir `useAuthStore` por `useOrganization()` |
| `pages/Schedules.jsx` | Substituir `useAuthStore` por `useOrganization()` |
| `pages/SchoolConfig.jsx` | Substituir `useAuthStore` por `useOrganization()` |
| `pages/MyAvailability.jsx` | Substituir `useAuthStore` por `useAuth()` / `useOrganization()` |
| `pages/MyProgress.jsx` | Substituir `useAuthStore` por `useAuth()` / `useOrganization()` |
| `pages/MySchedules.jsx` | Substituir `useAuthStore` por `useAuth()` / `useOrganization()` |
| `components/DefaultLayout.jsx` | Substituir Zustand por `useAuth()`, `useUser()`, `useOrganization()`; `<UserButton />`, `<OrganizationSwitcher />` |
| `roleAccess.js` | Roles: `org:admin` / `org:member` |
| `hooks/useSchoolData.js` | Substituir `useAuthStore(state => state.user?.orgId)` (~50 ocorrências) por `useOrganization().organization?.id` |

### 6.4 Dependências Novas

```json
// package.json
{
  "dependencies": {
    "@clerk/react": "^latest"
  }
}
```

---

## 7. Webhooks — Eventos e Ações

### 7.1 Endpoint

`POST https://apérius.pt/api/v1/webhooks/clerk`

Header obrigatório: `svix-id`, `svix-timestamp`, `svix-signature`

Verificação de assinatura com `CLERK_WEBHOOK_SECRET`.

### 7.2 Eventos Tratados

| Evento | Ação no backend |
|--------|----------------|
| `user.created` | Criar/atualizar row local `user` (`clerk_user_id`, `email`, `name` ← concatenar `first_name` + `last_name`). Sem role/org — definido via membership. |
| `user.updated` | Sincronizar `email`, `name`, `is_active`. |
| `user.deleted` | Soft-delete: `is_active = False`. |
| `organization.created` | Criar row `organization` com `clerk_org_id` + `name`. |
| `organization.updated` | Sincronizar `name`. |
| `organization.deleted` | Soft-delete organization. |
| `organizationMembership.created` | Criar/atualizar `user` local com `organization_id` e `role`. `org:admin` → `role=admin`, `org:member` → `role=teacher`. Se `public_metadata.teacher_id` existe → definir `user.teacher_id`. |
| `organizationMembership.updated` | Atualizar `role` na row local. |
| `organizationMembership.deleted` | Remover associação (`user.organization_id = NULL`). |

---

## 8. Fluxo de Onboarding

### 8.1 Passo a passo (tudo em apérius.pt)

```
1. Utilizador acede a https://apérius.pt
2. Clica em "Começar" → /register
3. <SignUp /> (renderizado DENTRO da app, NUNCA sai de apérius.pt)
4. Após sign-up, redirect para <CreateOrganization /> em /create-org
5. Utilizador dá nome à escola → cria Clerk Organization
6. Clerk envia webhooks (ASSÍNCRONO — podem chegar antes ou depois do passo 7)
7. Utilizador é redirecionado para /onboarding (página NOSSA)
8. Ao carregar /onboarding:
   a. Frontend faz GET /api/v1/onboarding/status
   b. Backend tenta get_current_user() pela DB local
   c. Se user NÃO existe → fallback síncrono: cria via BAPI do Clerk
   d. Se user existe → segue
9. Utilizador preenche formulário de onboarding
10. POST /api/v1/onboarding → backend cria OrganizationSettings + OrganizationGridSettings
11. Backend atualiza public_metadata do Clerk: { onboardingComplete: true }
12. Redirect para /dashboard
```

### 8.2 Endpoints de Onboarding

```
GET /api/v1/onboarding/status
Auth: Cookie __session
Response 200: { onboarding_complete: boolean, organization_name: string }

POST /api/v1/onboarding
Auth: Cookie __session
Body: {
  school_start_date: "2025-09-15",
  school_target_end_date: "2026-06-30",
  school_hard_end_date: "2026-07-31",
  lunch_start: "12:30",
  lunch_end: "14:00",
  lunch_min_duration: 60
}
Response 200: { organization_id, message: "Onboarding completo" }
```

---

## 9. RBAC — Controlo de Acessos

### 9.1 Backend Dependencies (FastAPI)

```python
# app/api/deps.py

def get_clerk_payload(request: Request) -> dict:
    """Valida token Clerk e retorna claims."""
    sdk = get_clerk_sdk()
    state = sdk.authenticate_request(
        request,
        AuthenticateRequestOptions(
            authorized_parties=[settings.FRONTEND_URL]
        )
    )
    if not state.is_signed_in:
        raise HTTPException(401)
    return state.payload

async def get_current_user(request: Request, db: AsyncSession) -> models.User:
    """User local a partir do token Clerk, com fallback síncrono."""
    claims = get_clerk_payload(request)
    user = await db.query(models.User).filter(
        models.User.clerk_user_id == claims["sub"]
    ).first()
    
    if user:
        return user
    
    # Fallback: race condition webhooks — cria via BAPI
    user = await clerk_sync.ensure_user_exists(db, claims)
    return user

def get_current_active_user(current_user: models.User) -> models.User:
    if not current_user.is_active:
        raise HTTPException(403)
    return current_user

def get_current_active_admin(current_user: models.User) -> models.User:
    if current_user.role not in ("admin",) and not current_user.is_superuser:
        raise HTTPException(403)
    return current_user
```

### 9.2 Frontend Guards

```jsx
// App.jsx
import { Protect, RedirectToSignIn } from "@clerk/react";
import { Show } from "@clerk/react";

// Landing page — mostra conteúdo público
<Route path="/" element={
  <Show when="signed-out" fallback={<Navigate to={roleDefaultRoute} />}>
    <MarketingSite />
  </Show>
} />

// Rotas protegidas por role
<Route path="/dashboard" element={
  <Protect role="org:admin" fallback={<RedirectToSignIn />}>
    <Dashboard />
  </Protect>
} />

<Route path="/my-availability" element={
  <Protect condition={has => has({role: "org:member"})} fallback={<RedirectToSignIn />}>
    <MyAvailability />
  </Protect>
} />
```

---

## 10. Estratégia de Testes

### 10.1 Testes OBRIGATÓRIOS (a escrever ANTES do código)

#### Backend — Testes Unitários

| # | Teste | Ficheiro | Critério de Aceitação |
|---|-------|----------|----------------------|
| T1 | `test_authenticate_request_valid_token` | `tests/test_clerk_auth.py` | Token Clerk válido → `is_signed_in=True` |
| T2 | `test_authenticate_request_invalid_token` | `tests/test_clerk_auth.py` | Token inválido → `is_signed_in=False` |
| T3 | `test_authenticate_request_expired_token` | `tests/test_clerk_auth.py` | Token expirado → `is_signed_in=False` |
| T4 | `test_authenticate_request_wrong_azp` | `tests/test_clerk_auth.py` | `authorized_party` errado → `is_signed_in=False` |
| T5 | `test_get_current_user_from_db` | `tests/test_clerk_auth.py` | Token válido + user existe → retorna `User` |
| T6 | `test_get_current_user_fallback_creates_user` | `tests/test_clerk_auth.py` | Token válido + user NÃO existe → cria via BAPI + retorna `User` |
| T7 | `test_get_current_active_admin` | `tests/test_clerk_auth.py` | role=admin → acesso |
| T8 | `test_get_current_active_admin_rejects_teacher` | `tests/test_clerk_auth.py` | role=teacher → 403 |
| T9 | `test_webhook_user_created_creates_local_user` | `tests/test_webhooks.py` | `user.created` → INSERT user local |
| T10 | `test_webhook_user_created_idempotent` | `tests/test_webhooks.py` | Duplicado → não crasha |
| T11 | `test_webhook_organization_created` | `tests/test_webhooks.py` | `organization.created` → INSERT org |
| T12 | `test_webhook_membership_created_admin` | `tests/test_webhooks.py` | role=admin → role local=admin |
| T13 | `test_webhook_membership_created_teacher` | `tests/test_webhooks.py` | role=member → role local=teacher |
| T14 | `test_webhook_membership_created_with_teacher_id` | `tests/test_webhooks.py` | metadata.teacher_id → user.teacher_id linkado |
| T15 | `test_webhook_membership_updated_role_change` | `tests/test_webhooks.py` | Role alterado → DB atualizada |
| T16 | `test_webhook_membership_deleted` | `tests/test_webhooks.py` | Membership removida → user.org_id = NULL |
| T17 | `test_webhook_invalid_signature_rejected` | `tests/test_webhooks.py` | Assinatura Svix inválida → 401 |
| T18 | `test_webhook_missing_svix_headers` | `tests/test_webhooks.py` | Headers ausentes → 400 |
| T19 | `test_onboarding_status_creates_user_if_missing` | `tests/test_onboarding.py` | GET status → user não existe → fallback cria |
| T20 | `test_onboarding_creates_settings` | `tests/test_onboarding.py` | POST onboarding → settings criadas |
| T21 | `test_onboarding_requires_auth` | `tests/test_onboarding.py` | Sem token → 401 |
| T22 | `test_onboarding_requires_admin` | `tests/test_onboarding.py` | Token teacher → 403 |
| T23 | `test_create_teacher_invites_to_clerk` | `tests/test_teacher_service.py` | Criar teacher → invitation enviada via BAPI com metadata.teacher_id |

#### Frontend — Testes Unitários

| # | Teste | Ficheiro | Critério |
|---|-------|----------|----------|
| T24 | `test_api_client_sends_cookie` | `src/test/apiClient.test.js` | Axios `withCredentials: true` |
| T25 | `test_api_client_handles_401` | `src/test/apiClient.test.js` | 401 → redirect `/login` |
| T26 | `test_role_access_admin_routes` | `src/test/roleAccess.test.js` | `org:admin` → acesso a `/dashboard`, `/teachers` |
| T27 | `test_role_access_teacher_routes` | `src/test/roleAccess.test.js` | `org:member` → acesso a `/my-availability` |
| T28 | `test_role_access_teacher_blocked_from_admin` | `src/test/roleAccess.test.js` | `org:member` → sem acesso a `/dashboard` |

#### Frontend — Testes E2E (Playwright)

| # | Cenário | Critério |
|---|---------|----------|
| T29 | Sign-up completo | Registo → cria org → onboarding → dashboard |
| T30 | Login admin | Admin login → vê dashboard |
| T31 | Login teacher | Professor login → vê MyAvailability, não vê admin links |
| T32 | Convite professor | Admin cria professor → invitation enviada → professor aceita |
| T33 | Onboarding interrompido | User fecha após sign-up → reabre → onboarding pendente → força conclusão |

### 10.2 Testes existentes — Plano de migração

#### Backend (16 ficheiros afetados)

| Estratégia | Ficheiros |
|------------|-----------|
| **REESCREVER** (usam `create_access_token`/`hash_password` como core) | `conftest.py`, `test_tenant_isolation_business.py`, `test_tenant_isolation_complete.py`, `test_multi_tenant.py`, `test_teacher_role_regression.py`, `test_teacher_observability.py`, `test_rate_limiting.py`, `test_alpha_release_gate.py` |
| **ATUALIZAR** (auth helper nos fixtures) | `test_schedule_generate_preflight.py`, `test_schedule_draft_lifecycle.py`, `test_solver_v2_draft_lifecycle.py`, `test_dashboard.py`, `test_occurrence_shared.py`, `test_lesson_registration.py`, `test_availability_paintbrush.py`, `test_teachers_crud.py` |
| **REMOVER** (testes específicos de auth antiga) | `test_auth.py`, `test_parametrized_error_contracts.py` (partes de auth) |

**Nova fixture base (`conftest.py`):**
```python
# Usar Clerk TestingTokens em vez de create_access_token
@pytest.fixture
async def clerk_test_token():
    """Gera token de teste via Clerk BAPI."""
    sdk = get_clerk_sdk()
    token = await sdk.testing_tokens.create_async()
    return token.token

@pytest.fixture
async def auth_headers(clerk_test_token):
    return {"Authorization": f"Bearer {clerk_test_token}"}
```

#### Frontend (10 ficheiros afetados)

| Estratégia | Ficheiros |
|------------|-----------|
| **REMOVER** | `authStore.test.js` |
| **REESCREVER** (mockam `useAuthStore`) | `ProtectedRoute.test.jsx`, `AppRoleGuards.test.jsx`, `DefaultLayoutRoleMenu.test.jsx`, `Login.test.jsx` |
| **ATUALIZAR** (mockam store para orgId/role) | `Dashboard.test.jsx`, `MyAvailability.test.jsx`, `MySchedules.test.jsx`, `Occurrences.test.jsx`, `Schedules.test.jsx` |

---

## 11. CI/CD — GitHub Actions

### 11.1 Pipeline por Commit

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
      - run: pip install -r backend/requirements.txt
      - run: pip install pytest pytest-asyncio pytest-cov
      - run: alembic upgrade head
      - run: pytest backend/tests/ -v --cov=app --cov-fail-under=80
        env:
          DATABASE_URL: postgresql+asyncpg://postgres:postgres@localhost:5432/test_db
          CLERK_SECRET_KEY: ${{ secrets.CLERK_SECRET_KEY }}
          CLERK_WEBHOOK_SECRET: ${{ secrets.CLERK_WEBHOOK_SECRET }}

  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - run: npm ci
        working-directory: frontend
      - run: npm run lint
        working-directory: frontend
      - run: npm run test -- --coverage --coverage.thresholds.lines=80
        working-directory: frontend
      - run: npm run build
        working-directory: frontend
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
      - run: npm ci
        working-directory: frontend
      - run: npx playwright install --with-deps
      - run: npm run test:e2e
        working-directory: frontend
        env:
          VITE_CLERK_PUBLISHABLE_KEY: ${{ secrets.VITE_CLERK_PUBLISHABLE_KEY }}
```

---

## 12. Variáveis de Ambiente

### Backend (`.env`)

```bash
# Já existentes
SECRET_KEY=...               # Manter (outras operações não-auth)
DATABASE_URL=...
REDIS_URL=...
SENTRY_DSN=...

# Clerk (CLERK_SECRET_KEY e CLERK_PUBLISHABLE_KEY já existem)
CLERK_SECRET_KEY=sk_test_...
CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_WEBHOOK_SECRET=whsec_...   # NOVO — obter no Clerk Dashboard > Webhooks

# Domínio
FRONTEND_URL=http://localhost:5173        # dev
# FRONTEND_URL=https://apérius.pt         # produção
```

### Frontend (`.env.local`)

```bash
VITE_CLERK_PUBLISHABLE_KEY=pk_test_...
```

---

## 13. Riscos e Mitigações

| Risco | Impacto | Probabilidade | Mitigação |
|-------|---------|--------------|-----------|
| Webhook chega depois do redirect onboarding | 401 na página /onboarding | Alta | Fallback síncrono via BAPI (secção 3.4) |
| Webhooks não chegam em dev (localhost) | Impossível testar sync local | Certa | Túnel ngrok/cloudflare; Svix CLI para testes locais; fallback BAPI |
| CSP `default-src 'none'` bloqueia Clerk | App não carrega componentes Clerk | Certa | Atualizar CSP (secção 5.4) |
| Clerk rate limit (BAPI) | Fallback síncrono bloqueado | Baixa | Fallback só ocorre em race condition rara; BAPI = 100 req/10s em dev |
| Custom roles pagas em produção | Bloqueio se exceder free tier | Média | Usar apenas roles default (admin, member) |
| Tamanho do token > 4KB | Sessão quebrada | Baixa | Sem metadata pesada no token |
| 25 testes existentes quebram | CI vermelho | Certa | Plano de migração de testes (secção 10.2) |
| `teacher_id` não linkado após convite | Professor sem acesso a MyAvailability | Alta | Metadata no convite Clerk (secção 2.7) |

---

## 14. Ordem de Implementação

### Fase 1 — Fundação (DB + Backend Core)
1. Criar migration `add_clerk_integration`
2. Instalar `clerk-backend-api`, `svix`
3. Atualizar `app/config.py` (adicionar vars Clerk)
4. Atualizar `app/models.py` (adicionar clerk_user_id, clerk_org_id; hashed_password nullable)
5. Criar `app/core/clerk.py`
6. Criar `app/schemas/webhooks.py`
7. Criar `app/services/clerk_sync.py` (inclui fallback síncrono)
8. Criar `app/api/v1/endpoints/webhooks.py`
9. Atualizar `app/api/deps.py` (get_current_user com fallback)
10. Atualizar `app/api/api.py` (remover auth router, adicionar webhooks)
11. Atualizar `app/main.py` (CSP, CORS, rota webhook)
12. **Escrever e passar T1-T18**

### Fase 2 — Onboarding + Teacher Invitations
13. Criar `app/schemas/onboarding.py`
14. Criar `app/services/organization_service.py`
15. Criar `app/api/v1/endpoints/onboarding.py`
16. Atualizar `app/services/teacher_service.py` (invite_teacher_to_clerk com metadata.teacher_id)
17. Atualizar `app/services/user_service.py` (remover passwords)
18. Atualizar `app/api/api.py`
19. **Escrever e passar T19-T23**

### Fase 3 — Frontend Core
20. Instalar `@clerk/react`
21. Adicionar `VITE_CLERK_PUBLISHABLE_KEY` ao `.env.local`
22. Atualizar `main.jsx` com `<ClerkProvider>`
23. Criar `pages/SignInPage.jsx` e `pages/SignUpPage.jsx`
24. Atualizar `App.jsx` (rotas + Protect + Show)
25. Atualizar `apiClient.js` (withCredentials, remover useAuthStore)
26. Atualizar `DefaultLayout.jsx` (useAuth, UserButton, OrgSwitcher)
27. Atualizar `roleAccess.js`
28. Remover `store.js`, `ProtectedRoute.jsx`, `Login.jsx` antigo, `Register.jsx` antigo
29. Atualizar `MarketingSite.jsx` (remover useAuthStore)
30. **Escrever e passar T24-T28**

### Fase 4 — Onboarding Frontend + Integração
31. Criar `pages/Onboarding.jsx`
32. Atualizar `hooks/useSchoolData.js` (~50 ocorrências de useAuthStore)
33. Atualizar páginas de professor (MyAvailability, MySchedules, MyProgress)
34. Atualizar páginas de admin (Occurrences, Schedules, SchoolConfig)
35. **Escrever e passar T29-T33**

### Fase 5 — Limpeza + Seed + Testes existentes
36. Reescrever `seed_data_small_realistic.py`
37. Remover `app/core/security.py`
38. Remover `app/api/v1/endpoints/auth.py`
39. Remover `scripts/bootstrap_admin.py`
40. Remover `create_users_for_teachers.py`
41. Atualizar `app/services/operational_seed_service.py`
42. Remover `bcrypt` e `python-jose` de `requirements.txt` (se não usados noutro lado)
43. Atualizar `conftest.py` (Clerk TestingTokens)
44. Migrar/reescrever 16 ficheiros de teste backend (secção 10.2)
45. Migrar/reescrever 10 ficheiros de teste frontend (secção 10.2)

### Fase 6 — CI/CD
46. Criar `.github/workflows/ci.yml`
47. Configurar secrets no GitHub
48. **Pipeline verde em todos os jobs**

---

## 15. Definição de "Done"

- [x] Todos os 33 testes (T1-T33) passam
- [x] 16 testes backend existentes migrados/atualizados e passam
- [x] 10 testes frontend existentes migrados/atualizados e passam
- [x] CI/CD pipeline verde (lint + test + typecheck + build)
- [x] `app/core/security.py` e `app/api/v1/endpoints/auth.py` removidos
- [x] Zero referências a `hash_password`, `verify_password`, `hz_access`, `hz_refresh`, `useAuthStore` no código fonte
- [x] CSP atualizado para permitir Clerk FAPI
- [ ] Seed executa sem erros
- [x] Login, sign-up, onboarding, convite de professor funcionam manualmente em dev
- [x] Utilizador nunca visita domínio que não seja `apérius.pt`
- [x] Documentação em `/documentation` atualizada para refletir o novo sistema

---

## 16. Pós-Migração — Reforço de Testes (WBS_TEST_COVERAGE v2.0)

**Data:** 2026-05-18

Após a migração inicial, foi executado o plano `docs/WBS_TEST_COVERAGE.md` que:

### Backend (Fase 1)
- Reativou **11 testes** de isolamento multitenant (`test_multi_tenant.py` + `test_tenant_isolation_complete.py`)
- Adicionou **14 testes novos**: claims inválidas (5), race condition webhook/BAPI (1), `user.deleted` (3), onboarding borda (4), org sem `clerk_org_id` (1)
- Removeu **3 ficheiros** obsoletos (`test_business_logic.py`, `test_occurrences.py`, `test_solver_logic.py`)
- Removeu **1 teste** que referenciava endpoint removido (`/auth/token`)
- Resultado: **56/56 passam** (1 skipped flaky)

### Frontend (Fase 2)
- Mock Clerk configurável (`setClerkState` / `resetClerkState`)
- Adicionou **23 testes novos**: routing guards (8), SignedInRedirect (4), DefaultLayout (2), apiClient interceptor (4), Onboarding UI (5)
- Resultado: **18/18 ficheiros, 116/116 testes passam**

### E2E (Fase 3)
- Criou **3 specs E2E** com Clerk real via `testing_tokens`
- Criou **infraestrutura** de token caching (`clerk-tokens.js`, `clerk-helpers.js`)
- CI/CD atualizado com `CLERK_SECRET_KEY` no job E2E + validação de skipped tests

### Totais
- **+48 novos testes** (14 backend + 23 frontend + 11 reativados)
- **11 reativados** (multi_tenant + tenant_isolation)
- **3 ficheiros removidos**
- Cobertura de auth: **0% → cobertura real de integração Clerk**
- Falsos positivos no CI: **Alto → Baixo**
