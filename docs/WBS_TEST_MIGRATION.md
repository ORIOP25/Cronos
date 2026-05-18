# WBS — Migração de Testes para Clerk

**Projeto:** Cronos
**Versão:** 1.0
**Base:** PRD Clerk Migration v2.1 | WBS Clerk Migration v1.0
**Data:** 2026-05-14

---

## Convenções

- `✅` — Resultado esperado (o que deves verificar após cada passo)
- `🔧` — Comando a executar
- `📦` — Ficheiro a criar/modificar
- Caminhos são relativos à raiz do monorepo (`MeuProjeto/`)

---

## Estado Atual

| Camada | Ficheiros | Testes | Estado |
|--------|-----------|--------|--------|
| Backend Clerk-native | 3 (`test_clerk_auth`, `test_webhooks`, `test_onboarding`) | 23 | ✅ 23/23 passam |
| Backend a migrar | 14 REWRITE + 6 UPDATE + ~20 KEEP | ~350+ | ❌ Bloqueados por `create_access_token` do `app.core.security` removido |
| Frontend | 14 | 83 | ⚠️ 81/83 passam (2 pré-existentes: WeekGrid + 1) |

---

# FASE 1 — Infraestrutura de Testes (Backend)

---

## Passo 1.1 — Criar fixture `admin_token_headers` no `conftest.py`

**📦 Ficheiro:** `backend/tests/conftest.py`

**Problema:** 10+ ficheiros de teste referenciam `admin_token_headers: dict` como parâmetro, mas esta fixture não existe em lado nenhum.

**Solução:** Criar fixture que gera headers de autenticação via `get_clerk_payload` mockado.

```python
@pytest.fixture
def admin_token_headers():
    """Headers de autenticação que simulam um admin Clerk autenticado."""
    return {"Authorization": "Bearer test_admin_token"}
```

✅ `docker compose exec backend python -m pytest tests/ -k "test_clerk" -v` → 23 passam

---

## Passo 1.2 — Criar fixture `clerk_auth_headers` genérica

**📦 Ficheiro:** `backend/tests/conftest.py`

**Problema:** Os testes precisam de headers flexíveis para simular diferentes roles (admin, teacher) e diferentes `clerk_user_id`.

**Solução:** Fixture parametrizável que aceita role e user_id.

```python
@pytest.fixture
def clerk_auth_headers():
    """Fixture base — usar com mock_clerk_payload nos testes que precisam de customização."""
    def _headers(clerk_user_id="user_test_admin", org_id="org_test_1", role="admin"):
        payload = mock_clerk_payload(clerk_user_id, org_id, role)
        return {"Authorization": f"Bearer mock_{clerk_user_id}"}
    return _headers
```

✅ `docker compose exec backend python -c "from tests.conftest import clerk_auth_headers; print('OK')"`

---

## Passo 1.3 — Criar helper `create_org_and_user` suporte a teacher

**📦 Ficheiro:** `backend/tests/conftest.py`

**Problema:** O helper `create_org_and_user` existe mas não aceita `teacher_id` explicitamente. Muitos testes de professor precisam disto.

```python
async def create_teacher_user(db_session, *, clerk_user_id, email, name, org_id, teacher_id):
    """Cria user com role=teacher e teacher_id vinculado."""
    user = models.User(
        clerk_user_id=clerk_user_id,
        email=email,
        name=name,
        role="teacher",
        organization_id=org_id,
        teacher_id=teacher_id,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user
```

✅ Testar com um teste simples que cria teacher user e verifica `teacher_id`.

---

## Passo 1.4 — Adicionar `RATELIMIT_ENABLED=false` ao `conftest.py`

**📦 Ficheiro:** `backend/tests/conftest.py`

**Problema:** Testes de rate limiting falham em CI porque o rate limiter está ativo por defeito.

```python
import os
os.environ.setdefault("RATELIMIT_ENABLED", "false")
```

✅ CI já injeta `RATELIMIT_ENABLED=false` — garantir que o `conftest.py` também o faz localmente.

---

# FASE 2 — Migrar Ficheiros UPDATE (6 ficheiros, ~50 testes)

Estes ficheiros têm importações mortas de `app.core.security` ou já usam padrões Clerk. São os mais rápidos de migrar.

---

## Passo 2.1 — `test_multi_tenant.py` (4 testes)

**📦 Ficheiro:** `backend/tests/test_multi_tenant.py`

**Ação:** Remover `from app.core.security import create_access_token` (linha 23) — nunca é chamado. O ficheiro usa `_register()` → `_bearer()` (hits `/auth/register` e usa o token retornado).

⚠️ **Edge case:** Se o endpoint `/auth/register` foi removido (PRD secção 5.1), este teste precisa de reescrita completa. Verificar se o endpoint ainda existe. Se não existir, mover para Grupo REWRITE.

✅ Testes passam após remoção do import morto.

---

## Passo 2.2 — `test_tenant_isolation_complete.py` (7 testes)

**📦 Ficheiro:** `backend/tests/test_tenant_isolation_complete.py`

**Ação:** Remover `from app.core.security import create_access_token` (linha 16) — nunca é chamado. Mesmo padrão `_register()` → `_bearer()`.

✅ Testes passam após remoção do import morto.

---

## Passo 2.3 — `test_occurrence_shared.py` (helper, 0 testes diretos)

**📦 Ficheiro:** `backend/tests/test_occurrence_shared.py`

**Ação:** Remover `from app.core.security import create_access_token` (linha 16) — import morto. Este é um helper module importado por 5+ ficheiros de teste de ocorrências.

⚠️ **Edge case:** Verificar que nenhum dos 5 ficheiros que importam `test_occurrence_shared` usa `create_access_token` via re-export.

✅ Testes de ocorrências passam.

---

## Passo 2.4 — `test_clerk_auth.py` (8 testes)

**📦 Ficheiro:** `backend/tests/test_clerk_auth.py`

**Ação:** Já está migrado e funcional (23/23 passam no CI). Apenas verificar que os mocks de `_verify_clerk_request_sync` estão corretos.

✅ 8/8 testes passam.

---

## Passo 2.5 — `test_onboarding.py` (5 testes)

**📦 Ficheiro:** `backend/tests/test_onboarding.py`

**Ação:** Já está migrado e funcional. Atualizado para esperar `status_code=201`.

✅ 5/5 testes passam.

---

## Passo 2.6 — `test_webhooks.py` (10 testes)

**📦 Ficheiro:** `backend/tests/test_webhooks.py`

**Ação:** Já está migrado e funcional. Usa `clerk_user_id` e fixtures Clerk-native.

✅ 10/10 testes passam.

---

## Passo 2.7 — Verificação Fase 2

```powershell
docker compose exec backend python -m pytest tests/test_multi_tenant.py tests/test_tenant_isolation_complete.py tests/test_clerk_auth.py tests/test_onboarding.py tests/test_webhooks.py -v
```

✅ Todos os testes da Fase 2 passam (~34 testes).

---

# FASE 3 — Migrar Ficheiros REWRITE (14 ficheiros, ~150 testes)

Estes ficheiros chamam `create_access_token()` ativamente e precisam de reescrita para usar autenticação Clerk.

---

## Passo 3.1 — Criar fixture `clerk_admin_headers` com mock automático

**📦 Ficheiro:** `backend/tests/conftest.py`

**Problema:** Os 14 ficheiros precisam de headers `Authorization: Bearer <token>` mas o `create_access_token` foi removido.

**Solução:** Fixture que automaticamente aplica `patch("app.api.deps.get_clerk_payload")` e retorna headers.

```python
@pytest.fixture
async def clerk_admin_headers():
    """Headers de admin autenticado via Clerk com mock automático de get_clerk_payload."""
    payload = mock_clerk_payload("user_admin_001", "org_001", "admin")
    with patch("app.api.deps.get_clerk_payload", return_value=payload):
        yield {"Authorization": "Bearer test_token_admin_001"}
```

✅ `docker compose exec backend python -c "from tests.conftest import clerk_admin_headers; print('OK')"`

---

## Passo 3.2 — Criar fixture `clerk_teacher_headers`

**📦 Ficheiro:** `backend/tests/conftest.py`

```python
@pytest.fixture
async def clerk_teacher_headers():
    """Headers de teacher autenticado via Clerk."""
    payload = mock_clerk_payload("user_teacher_001", "org_001", "member")
    payload["o"]["rol"] = "member"
    with patch("app.api.deps.get_clerk_payload", return_value=payload):
        yield {"Authorization": "Bearer test_token_teacher_001"}
```

✅ Teste simples com endpoint que requer teacher.

---

## Passo 3.3 — Migrar `test_schedule_draft_lifecycle.py` (28 testes)

**📦 Ficheiro:** `backend/tests/test_schedule_draft_lifecycle.py`

**Ação:** 
1. Remover `from app.core.security import create_access_token`
2. Substituir `draft_setup` fixture — em vez de criar token com `create_access_token`, usar `clerk_admin_headers` + `create_org_and_user`
3. Atualizar todos os `headers={"Authorization": f"Bearer {token}"}` para usar `clerk_admin_headers`

✅ 28/28 testes passam.

---

## Passo 3.4 — Migrar `test_lesson_registration.py` (30 testes)

**📦 Ficheiro:** `backend/tests/test_lesson_registration.py`

**Ação:**
1. Remover 5 `from app.core.security import hash_password, create_access_token` inline imports
2. Substituir criação de tokens inline por `clerk_admin_headers` fixture
3. O ficheiro tem 5 secções de teste que criam tokens inline — cada uma precisa de ser atualizada

✅ 30/30 testes passam.

---

## Passo 3.5 — Migrar `test_availability_paintbrush.py` (16 testes)

**📦 Ficheiro:** `backend/tests/test_availability_paintbrush.py`

**Ação:**
1. Remover `from app.core.security import hash_password, create_access_token`
2. Remover 4 chamadas `create_access_token()`
3. Substituir `_create_teacher_auth_headers()` importado de `test_business_logic_shared` por `clerk_teacher_headers`
4. Usar `create_org_and_user` com `teacher_id` para criar teacher users

⚠️ **Dependência:** Passo 1.3 (`create_teacher_user`) precisa estar completo.

✅ 16/16 testes passam.

---

## Passo 3.6 — Migrar `test_business_logic_shared.py` (helper)

**📦 Ficheiro:** `backend/tests/test_business_logic_shared.py`

**Ação:**
1. Remover `from app.core.security import hash_password, create_access_token`
2. Reescrever `_create_teacher_auth_headers()` para usar `mock_clerk_payload` em vez de `create_access_token`

```python
def _create_teacher_auth_headers(teacher_user_id="user_teacher_001", org_id="org_001"):
    payload = mock_clerk_payload(teacher_user_id, org_id, "member")
    return {"Authorization": f"Bearer test_token_{teacher_user_id}"}
```

✅ Função helper é importada e usada por `test_availability_paintbrush.py` e `test_teacher_role_regression.py`.

---

## Passo 3.7 — Migrar `test_teacher_role_regression.py` (9 testes)

**📦 Ficheiro:** `backend/tests/test_teacher_role_regression.py`

**Ação:**
1. Remover `from app.core.security import create_access_token, hash_password`
2. Substituir `_create_teacher_auth_headers()` local por versão Clerk
3. Substituir `admin_token_headers` por `clerk_admin_headers`

✅ 9/9 testes passam.

---

## Passo 3.8 — Migrar `test_dashboard.py` (8 testes)

**📦 Ficheiro:** `backend/tests/test_dashboard.py`

**Ação:**
1. Remover 2 `from app.core.security import hash_password, create_access_token` inline imports
2. Substituir criação de token inline por `clerk_admin_headers` / `clerk_teacher_headers`
3. Criar orgs e users via `create_org_and_user`

✅ 8/8 testes passam.

---

## Passo 3.9 — Migrar `test_schedule_generate_preflight.py` (10 testes)

**📦 Ficheiro:** `backend/tests/test_schedule_generate_preflight.py`

**Ação:**
1. Remover `from app.core.security import create_access_token, hash_password`
2. Substituir `create_access_token` por fixtures Clerk
3. Usar `create_org_and_user` para criar admin/teacher users

✅ 10/10 testes passam.

---

## Passo 3.10 — Migrar `test_alpha_release_gate.py` (6 testes)

**📦 Ficheiro:** `backend/tests/test_alpha_release_gate.py`

**Ação:**
1. Remover `from app.core.security import create_access_token, hash_password`
2. Substituir `_auth_headers()` helper (usa `create_access_token`) por `clerk_admin_headers`
3. Usar `create_org_and_user` em vez de `User()` com campos manuais

✅ 6/6 testes passam.

---

## Passo 3.11 — Migrar `test_analytics_import_endpoints.py` (14 testes)

**📦 Ficheiro:** `backend/tests/test_analytics_import_endpoints.py`

**Ação:**
1. Remover 2 `from app.core.security import create_access_token, hash_password` imports
2. Substituir token creation por `clerk_admin_headers`

✅ 14/14 testes passam.

---

## Passo 3.12 — Migrar `test_occurrence_endpoints.py` (12 testes)

**📦 Ficheiro:** `backend/tests/test_occurrence_endpoints.py`

**Ação:**
1. Remover `create_access_token` dos métodos `auth_headers()` e `teacher_auth_headers()` da classe de teste
2. Substituir por `clerk_admin_headers` e `clerk_teacher_headers` fixtures

✅ 12/12 testes passam.

---

## Passo 3.13 — Migrar `test_parametrized_error_contracts.py` (3 testes)

**📦 Ficheiro:** `backend/tests/test_parametrized_error_contracts.py`

**Ação:**
1. Remover `from app.core.security import create_access_token, hash_password`
2. Substituir token creation por `clerk_admin_headers`

✅ 3/3 testes passam.

---

## Passo 3.14 — Migrar `test_rate_limiting.py` (5 testes)

**📦 Ficheiro:** `backend/tests/test_rate_limiting.py`

**Ação:**
1. Remover 2 `from app.core.security import create_access_token, hash_password` inline imports
2. Substituir por `clerk_admin_headers`

✅ 5/5 testes passam.

---

## Passo 3.15 — Migrar `test_teacher_observability.py` (4 testes)

**📦 Ficheiro:** `backend/tests/test_teacher_observability.py`

**Ação:**
1. Remover `from app.core.security import create_access_token, hash_password`
2. Substituir helper de token por `clerk_admin_headers` / `clerk_teacher_headers`

✅ 4/4 testes passam.

---

## Passo 3.16 — Migrar `test_tenant_isolation_business.py` (4 testes)

**📦 Ficheiro:** `backend/tests/test_tenant_isolation_business.py`

**Ação:**
1. Remover `from app.core.security import hash_password, create_access_token`
2. Substituir `create_access_token` por `clerk_admin_headers`
3. Criar users com `clerk_user_id` via `create_org_and_user`

✅ 4/4 testes passam.

---

## Passo 3.17 — Verificação Fase 3

```powershell
docker compose exec backend python -m pytest tests/ -v --ignore=tests/test_clerk_auth.py --ignore=tests/test_webhooks.py --ignore=tests/test_onboarding.py -k "not (test_auth or test_classes_crud or test_class_subjects or test_course_centric or test_import or test_org_settings or test_rooms_crud or test_solver or test_subjects_crud or test_teachers_crud or test_timeslot or test_timesheets)" --tb=short
```

✅ Todos os ~150 testes REWRITE passam.

---

# FASE 4 — Migrar Ficheiros KEEP (que precisam de `admin_token_headers`)

Estes ficheiros não usam `create_access_token` mas referenciam a fixture `admin_token_headers` que não existe. Precisam que a fixture seja criada no `conftest.py` (Passo 1.1).

---

## Passo 4.1 — Verificar ficheiros que usam `admin_token_headers`

**Ficheiros afetados:** `test_classes_crud.py`, `test_class_subjects.py`, `test_combined_edge_cases.py`, `test_course_centric_model.py`, `test_import_endpoints.py`, `test_org_settings.py`, `test_rooms_crud.py`, `test_solver_v2_draft_lifecycle.py`, `test_subjects_crud.py`, `test_teachers_crud.py`, `test_timeslot_crud.py`, `test_timesheets_endpoints.py`, e outros.

**Ação:** Depois de criar `admin_token_headers` no Passo 1.1, correr cada ficheiro individualmente para verificar se passa.

✅ Cada ficheiro corre sem erros de importação.

---

## Passo 4.2 — `test_solver_v2_draft_lifecycle.py` (12 testes)

**📦 Ficheiro:** `backend/tests/test_solver_v2_draft_lifecycle.py`

**Ação:** Remover `from app.core.security import hash_password` (import morto, nunca chamado). O ficheiro usa `admin_token_headers` fixture.

✅ 12/12 testes passam.

---

## Passo 4.3 — `test_auth.py` (1 teste)

**📦 Ficheiro:** `backend/tests/test_auth.py`

⚠️ **Decisão:** Este ficheiro testa `/auth/register` e `/auth/token` — endpoints que foram removidos (PRD secção 5.1). **REMOVER este ficheiro.** O registo e autenticação agora são 100% Clerk.

🔧 `Remove-Item backend/tests/test_auth.py`

✅ O ficheiro já não existe.

---

## Passo 4.4 — Verificação Fase 4

```powershell
docker compose exec backend python -m pytest tests/ -v --tb=short
```

✅ Todos os ~350+ testes passam (23 Clerk + ~150 REWRITE + ~180 KEEP).

---

# FASE 5 — Frontend

---

## Passo 5.1 — Corrigir `WeekGrid.test.jsx` (1 falha pré-existente)

**📦 Ficheiro:** `frontend/src/test/WeekGrid.test.jsx`

**Problema:** Teste "mostra orientação quando ocorrência já está fechada" espera que o botão esteja `disabled`, mas o componente não desabilita o botão para ocorrências fechadas.

**Ação:** Atualizar o teste para refletir o comportamento real do componente:
- Em vez de `expect(slotButton).toBeDisabled()`, verificar que o texto "Ocorrência já fechada" aparece OU
- Corrigir o componente `WeekGrid` para desabilitar o botão quando a ocorrência está fechada

✅ Teste passa.

---

## Passo 5.2 — Atualizar mock de `useOrganization` no `setup.js`

**📦 Ficheiro:** `frontend/src/test/setup.js`

**Problema:** O mock atual de `useOrganization` retorna `publicMetadata` vazio. Com a migração Clerk, o `teacher_id` está em `membership.publicMetadata.teacher_id`, e o role está em `membership.role` (não em `user.publicMetadata`).

**Ação:** Atualizar o mock para refletir a estrutura real:

```js
useOrganization: () => ({
  organization: { id: 1, name: 'Test Org' },
  membership: {
    role: 'org:admin',
    publicMetadata: { teacher_id: null },
  },
  isLoaded: true,
}),
```

✅ Testes que dependem de `membership.publicMetadata.teacher_id` funcionam.

---

## Passo 5.3 — Executar todos os testes frontend

```powershell
cd frontend; if ($?) { npx vitest run }
```

✅ 93/93 testes passam (83 existentes + correções).

---

# FASE 6 — CI/CD

---

## Passo 6.1 — Atualizar `ci.yml` para correr TODOS os testes

**📦 Ficheiro:** `.github/workflows/ci.yml`

**ANTES (linha 63):**
```yaml
run: pytest tests/test_clerk_auth.py tests/test_webhooks.py tests/test_onboarding.py -v --cov=app --cov-report=xml:coverage.xml --tb=short
```

**DEPOIS:**
```yaml
run: pytest tests/ -v --cov=app --cov-report=xml:coverage.xml --tb=short
```

✅ CI corre todos os ~350+ testes backend.

---

## Passo 6.2 — Adicionar `coverage.json` summary ao job frontend

**📦 Ficheiro:** `.github/workflows/ci.yml`

Adicionar após o step "Test":
```yaml
- name: Test Coverage
  working-directory: frontend
  run: npx vitest run --coverage --coverage.thresholds.lines=80
```

✅ CI falha se cobertura < 80%.

---

## Passo 6.3 — Verificação final CI

Fazer push para a branch e verificar que o pipeline está verde em todos os jobs (backend, frontend).

✅ Pipeline verde: lint + test + build em ambos backend e frontend.

---

# Resumo de Esforço

| Fase | Descrição | Ficheiros | Testes | Esforço Estimado |
|------|-----------|-----------|--------|-----------------|
| Fase 1 | Infraestrutura (conftest.py) | 1 | 0 novos | 1-2 horas |
| Fase 2 | UPDATE (imports mortos) | 6 | ~50 | 1-2 horas |
| Fase 3 | REWRITE (create_access_token) | 14 | ~150 | 4-6 horas |
| Fase 4 | KEEP + admin_token_headers | ~20 | ~180 | 1-2 horas |
| Fase 5 | Frontend | 2 | ~10 | 1 hora |
| Fase 6 | CI/CD | 1 | — | 0.5 horas |
| **TOTAL** | | **~44** | **~380** | **8-12 horas** |

---

## Definição de "Done"

- [ ] `conftest.py` tem fixtures `clerk_admin_headers`, `clerk_teacher_headers`, `create_teacher_user`
- [ ] Zero referências a `create_access_token` em qualquer ficheiro de teste
- [ ] Zero referências a `hash_password` em qualquer ficheiro de teste
- [ ] Zero imports de `app.core.security` em qualquer ficheiro de teste
- [ ] `test_auth.py` removido (endpoints `/auth/*` já não existem)
- [ ] Todos os ~380 testes backend passam
- [ ] Todos os 93 testes frontend passam
- [ ] CI/CD pipeline verde (`pytest tests/ -v` + `npx vitest run`)
- [ ] Cobertura ≥ 80% em backend e frontend
