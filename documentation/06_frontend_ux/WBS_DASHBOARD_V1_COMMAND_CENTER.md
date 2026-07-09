# WBS: Dashboard V1 — Command Center

> WBS histórico preservado como registo de implementação. Referências a stack,
> CI, caminhos e contagens de testes refletem Maio de 2026, não a árvore atual.
> Para o estado verificado da beta, consultar
> `../10_migration_map/BETA_BASELINE_READINESS_AUDIT_2026-07.md`.

**Data**: 2026-05-04
**Versão**: 1.0 (Concluído)
**Estado**: ✅ CONCLUÍDO
**Depende de**: Nenhum WBS anterior (funcionalidade nova)

---

## 1. Os 5 Ws

### What

Transformar a página `/dashboard` de um único widget (Raio-X de Disponibilidade) para um **Command Center** híbrido operacional + estratégico, com 5 zonas:

1. **🚨 Barra de Alertas** — O que precisa de ação imediata
2. **📊 Saúde do Horário** — Métricas de qualidade da última geração
3. **📈 Progresso Curricular** — Conclusão de módulos por turma
4. **🏫 Visão de Recursos** — Contagens de entidades + distribuição de salas
5. **🔗 Atalhos de Ação** — Navegação contextual para resolver pendências

### Why

O diretor/secretário de uma Escola Profissional atualmente não tem visibilidade imediata sobre o estado operacional da escola ao abrir a aplicação. Precisa de saber em segundos:

- Há faltas hoje por resolver?
- Há timesheets por aprovar?
- O horário está saudável (sem gaps, sem conflitos)?
- Que turmas estão atrasadas no progresso curricular?

**Problema atual**: O dashboard contém apenas o `AnalyticsHeatmap` (Raio-X de Disponibilidade). É uma landing page que não justifica ser a primeira página que o admin vê após login.

**Objetivo**: Fazer do dashboard o ponto de entrada natural para o fluxo de trabalho diário do diretor — da monitorização à ação.

### Who

| Papel | Responsabilidade |
|-------|-----------------|
| **Product Owner** | Validar seleção e prioridade de widgets |
| **Backend Developer** | Criar endpoint agregador `GET /api/v1/dashboard` + testes |
| **Frontend Developer** | Criar hooks, widgets, composição da página + testes |
| **QA / SDET** | Validar com dados de seed, verificar edge cases (org vazia) |
| **End User** | Diretor(a) / Secretário(a) da escola (role `admin`) |

### When

**Sprint de 5-6 dias:**

| Dia | Entregável |
|-----|-----------|
| 1 | Backend: schema + service + endpoint + testes unitários |
| 2 | Frontend: hook `useDashboard` + widgets AlertBar, ResourceCounts, QuickActions |
| 3 | Frontend: widgets ScheduleHealth, ClassProgress, DebtSummary + composição da página |
| 4 | E2E tooling setup (Playwright + MSW) + definição de cenários |
| 5 | Implementação dos testes E2E (6 user journeys) + integração no CI |
| 6 | Polish visual, documentação, validação final |

### Where

| Camada | Ficheiro | Ação |
|--------|---------|------|
| Backend Schema | `backend/app/schemas/dashboard.py` | **Novo** |
| Backend Service | `backend/app/services/dashboard_service.py` | **Novo** |
| Backend Router | `backend/app/api/v1/endpoints/dashboard.py` | **Novo** |
| Backend Router Registo | `backend/app/api/v1/__init__.py` | **Editar** |
| Backend Tests | `backend/tests/test_dashboard.py` | **Novo** |
| Frontend Hook | `frontend/src/hooks/useSchoolData.js` | **Editar** (adicionar `useDashboard`) |
| Frontend Components | `frontend/src/components/dashboard/` | **Novo diretório** |
| Frontend Page | `frontend/src/pages/Dashboard.jsx` | **Refactor completo** |
| Frontend Unit Tests | `frontend/src/test/Dashboard.test.jsx` | **Refactor completo** |
| E2E Test Config | `frontend/playwright.config.js` | **Novo** |
| E2E Mocks (MSW) | `frontend/src/test/mocks/` | **Novo diretório** |
| E2E Tests | `frontend/e2e/dashboard/` | **Novo diretório** |
| CI/CD Workflow | `.github/workflows/ci.yml` | **Editar** (adicionar job E2E) |
| Documentation | `documentation/06_frontend_ux/WBS_DASHBOARD_V1_COMMAND_CENTER.md` | **Este documento** |

---

## 2. Work Breakdown Structure

### Legenda de Estados
- ⬜ `PENDING` — Por iniciar
- 🟡 `IN_PROGRESS` — Em desenvolvimento
- ✅ `DONE` — Concluído
- ❌ `BLOCKED` — Bloqueado (com razão)

---

## FASE 0 — Pré-Requisitos & Discovery

### WBS 0.1 — Confirmar disponibilidade de dados no backend
**Status**: ✅ DONE
**Priority**: MAX
**Estimativa**: 1h (investigação)

**Tarefas**:
- [x] Verificar se `ClassProgress` tem registos para todas as turmas no seed data
- [x] Verificar se `GET /occurrences/` aceita filtro por `date=today` e `status=PENDING` sem paginação
- [x] Verificar se `GET /substitutions/` aceita filtro por `date=today`
- [x] Confirmar que `GET /schedule/audit/summary` retorna dados mesmo sem `generation_id` (usa latest)
- [x] Verificar se `GET /timesheets/?status=submitted` retorna contagem sem paginação pesada

**Risco**: Se algum dado não estiver disponível, será necessário criar endpoints auxiliares (WBS 0.1-A).

**Resultado**: Documento de confirmação com o que existe vs. o que falta.

### WBS 0.2 — Selecionar e configurar ferramenta E2E (Playwright + MSW)
**Status**: ✅ DONE
**Priority**: HIGH
**Estimativa**: 2h (investigação + setup inicial)
**Depende de**: Nenhum (pode correr em paralelo com FASE 1-4)

**Decisão de arquitetura de testes**:

A stack de testes será em 3 camadas, cada uma com um propósito distinto:

| Camada | Ferramenta | Propósito | Corre em CI? |
|--------|-----------|-----------|-------------|
| **Unit/Integration** | Vitest + RTL | Lógica de componentes, estados (loading/empty/error), navegação mockada | Sim (já existe) |
| **API Contract** | Pytest + httpx | Endpoint `GET /api/v1/dashboard`, schemas, tenant isolation | Sim (já existe) |
| **E2E — Comportamento Humano** | **Playwright + MSW** | Simular fluxos reais de utilizador: login, clique em widgets, navegação entre páginas, verificação de cores de estado | **Sim (a adicionar)** |

**Porquê Playwright + MSW (não Playwright contra backend real):**

| Abordagem | Prós | Contras |
|-----------|------|---------|
| Playwright + backend real | Testa stack completa | Lento (Docker Compose), flaky (timeouts de BD/Redis), difícil de isolar tenants em CI |
| **Playwright + MSW (Mock Service Worker)** | Rápido (< 30s por spec), determinístico, fácil de simular edge cases (org vazia, erros 500) | Não testa o backend real (mas isso já é coberto pelos testes Pytest) |
| Cypress | Bom DX | Overhead maior, não tão rápido quanto Playwright |

**Recomendação**: Playwright + MSW. O backend já é testado exaustivamente via Pytest. Os E2E devem focar-se em validar que a UI se comporta como um humano espera — cliques, navegação, cores de alerta, estados visuais.

**Tarefas deste WBS**:
- [x] Instalar `@playwright/test` como devDependency no `frontend/package.json`
- [x] Instalar browsers: `npx playwright install chromium`
- [x] Criar `frontend/playwright.config.js`:
  - `testDir: './e2e'`
  - `webServer` block: `npm run dev` (porta 5173)
  - `use.baseURL: 'http://localhost:5173'`
  - Timeout: 30s por teste
  - `retries: 1` em CI (0 localmente)
  - Screenshot on failure: `only-on-failure`
- [x] Instalar `msw` como devDependency
- [x] Criar `frontend/src/test/mocks/handlers.js` — handlers MSW para:
  - `GET /api/v1/dashboard` → resposta mock com dados completos
  - `GET /api/v1/dashboard` → resposta mock para org vazia (counts=0)
  - `GET /api/v1/dashboard` → resposta mock sem geração (schedule_health=null)
  - `GET /api/v1/analytics/availability-heatmap` → dados mock do heatmap
  - `GET /api/v1/import/timeslots` → dados mock da grelha horária
- [x] Criar `frontend/src/test/mocks/server.js` — setup/teardown do MSW no browser
- [x] Adicionar script `test:e2e` em `frontend/package.json`: `"test:e2e": "playwright test"`
- [x] Adicionar script `test:e2e:ui` para debug: `"test:e2e:ui": "playwright test --ui"`

**Estrutura de ficheiros resultante**:
```
frontend/
├── playwright.config.js           # Config Playwright
├── e2e/
│   └── dashboard/
│       ├── dashboard.spec.js      # Testes E2E do dashboard
│       └── fixtures/
│           └── dashboard-data.js  # Dados mock reutilizáveis
├── src/
│   └── test/
│       ├── mocks/
│       │   ├── handlers.js        # MSW request handlers
│       │   ├── server.js          # MSW server setup
│       │   └── data/
│       │       └── dashboard.js   # Respostas mock por cenário
│       └── setup.js               # Atualizar para iniciar MSW
└── package.json                   # + scripts test:e2e, test:e2e:ui
```

---

## FASE 1 — Backend: Dashboard Aggregation Endpoint

### WBS 1.1 — Criar schemas Pydantic `DashboardV1Response`
**Status**: ✅ DONE
**Priority**: MAX
**Estimativa**: 1h
**Ficheiro**: `backend/app/schemas/dashboard.py`
**Depende de**: WBS 0.1

**Schemas a criar**:

```python
class AlertCounts(BaseModel):
    """Contagens para a barra de alertas"""
    pending_occurrences_today: int       # faltas/GAP hoje por decidir
    pending_timesheets: int             # timesheets SUBMITTED por aprovar
    pending_drafts: int                 # rascunhos de horário pendentes
    active_substitutions_today: int     # substituições ativas hoje

class ResourceCounts(BaseModel):
    """Contagens de entidades e distribuição de salas"""
    teachers_count: int
    classes_count: int
    courses_count: int
    subjects_count: int
    rooms_count: int
    rooms_by_type: dict[str, int]       # {"normal": 16, "lab": 8, "gym": 3, "art": 3}

class ScheduleHealthWidget(BaseModel):
    """Métricas de qualidade da última geração"""
    generation_id: str | None           # None se não houver geração
    blocks_count: int
    classes_total: int
    classes_empty_week: int             # turmas sem aulas esta semana
    week_slots_avg: float               # média de blocos/turma/semana
    duplicate_teacher_slots: int        # conflitos detetados
    duplicate_class_slots: int
    weekly_fairness_spread: float       # desvio padrão de slots entre turmas
    teacher_week_slots_avg: float       # média de blocos/professor/semana

class ClassProgressSummary(BaseModel):
    """Progresso resumido de uma turma"""
    class_id: int
    class_name: str
    course_id: int | None
    course_name: str | None
    grade_level: int                    # 10, 11, 12
    overall_percentage: float           # 0.0 a 100.0
    completed_hours: float
    total_hours: float

class DebtSummary(BaseModel):
    """Resumo de dívidas de horas"""
    total_gaps: int                     # total de gap occurrences
    total_hours_owed: float             # total de horas em dívida
    total_gaps_overdue: int
    total_hours_owed_overdue: float
    affected_classes_count: int         # nº de turmas com dívidas
    as_of_date: date

class DashboardV1Response(BaseModel):
    """Resposta completa do dashboard"""
    alerts: AlertCounts
    resources: ResourceCounts
    schedule_health: ScheduleHealthWidget | None  # None se sem geração
    class_progress: list[ClassProgressSummary]    # ordenado por % crescente
    debts: DebtSummary
    organization_name: str
```

**Validações**:
- [x] Schemas alinhados com convenções do projeto (Pydantic v2, `model_config`)
- [x] Campos `| None` para dados opcionais (ex: sem geração de horário)
- [x] Sem dependências circulares

---

### WBS 1.2 — Criar `dashboard_service.py`
**Status**: ✅ DONE
**Priority**: MAX
**Estimativa**: 2h
**Ficheiro**: `backend/app/services/dashboard_service.py`
**Depende de**: WBS 1.1

**Queries a implementar** (todas com filtro `organization_id`):

| Método | Query | Notas |
|--------|-------|-------|
| `get_alert_counts(org_id)` | 4 sub-queries independentes | Usar `count()` em cada tabela relevante |
| `get_resource_counts(org_id)` | 5 counts + group by room type | `func.count()` + `group_by(Room.type)` |
| `get_schedule_health(org_id)` | Delegar a `audit_service.get_summary(latest_generation_id)` | Reutilizar serviço existente; mapear para `ScheduleHealthWidget` |
| `get_class_progress(org_id)` | JOIN `ClassProgress` + `Class` + `Course`; agregar `hours_completed / hours_total` | Agrupar por class_id; usar `selectinload` para evitar N+1 |
| `get_debt_summary(org_id)` | Delegar a `occurrence_service.get_debts()` | Reutilizar serviço existente; extrair totais + contar turmas únicas |

**Pilar Optimization**: Todas as queries numa transação read-only se possível, ou queries paralelas com `asyncio.gather`.

**Tratamento de edge cases**:
- Organização sem professores/turmas → counts = 0
- Organização sem geração de horário → `schedule_health = None`
- Organização sem progresso → `class_progress = []`
- Organização sem dívidas → `debts` com todos os campos a 0

---

### WBS 1.3 — Criar endpoint `GET /api/v1/dashboard`
**Status**: ✅ DONE
**Priority**: MAX
**Estimativa**: 30min
**Ficheiro**: `backend/app/api/v1/endpoints/dashboard.py`
**Depende de**: WBS 1.2

**Especificação**:
```python
@router.get("/dashboard", response_model=DashboardV1Response)
async def get_dashboard(
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """
    Dashboard V1 — Command Center para admin.
    Agrega alertas, saúde do horário, progresso curricular,
    contagens de recursos, e resumo de dívidas.
    """
    service = DashboardService(db)
    return await service.get_dashboard(org.id)
```

**Regras**:
- Apenas role `admin` (verificar no router)
- Middleware `get_current_organization` já garante tenant isolation
- Sem parâmetros de query para V1 (usa sempre today, latest generation)
- Status code: `200 OK` sempre (mesmo com dados vazios)
- Erro inesperado: `500 Internal Server Error`

---

### WBS 1.4 — Registar router
**Status**: ✅ DONE
**Priority**: MAX
**Estimativa**: 15min
**Ficheiro**: `backend/app/api/v1/__init__.py`
**Depende de**: WBS 1.3

- [x] Importar `dashboard_router` do módulo `endpoints.dashboard`
- [x] Registar com `prefix=""`, `tags=["dashboard"]`
- [x] Verificar que não há conflito de rotas

---

### WBS 1.5 — Testes backend
**Status**: ✅ DONE
**Priority**: HIGH
**Estimativa**: 1h30
**Ficheiro**: `backend/tests/test_dashboard.py`
**Depende de**: WBS 1.3

**Cenários de teste**:

| # | Cenário | Esperado |
|---|---------|----------|
| 1 | Admin acede ao dashboard com dados completos | 200, todos os campos preenchidos |
| 2 | Admin acede ao dashboard com org vazia (sem dados) | 200, todos os counts = 0, schedule_health = None, class_progress = [] |
| 3 | Teacher acede ao dashboard | 403 Forbidden |
| 4 | Utilizador não autenticado acede | 401 Unauthorized |
| 5 | Organização sem geração de horário | 200, schedule_health = None |
| 6 | Organização sem progresso de turmas | 200, class_progress = [] |
| 7 | Organização sem dívidas | 200, debts com valores a 0 |
| 8 | Estrutura da resposta válida contra o schema | Validar com Pydantic `model_validate` |

**Padrão de teste**: Seguir o padrão existente no projeto (pytest + httpx AsyncClient + fixtures para org/user).

---

## FASE 2 — Frontend: Hook & Data Layer

### WBS 2.1 — Criar hook `useDashboard`
**Status**: ✅ DONE
**Priority**: MAX
**Estimativa**: 30min
**Ficheiro**: `frontend/src/hooks/useSchoolData.js` (editar)
**Depende de**: WBS 1.3

**Especificação**:
```javascript
export function useDashboard() {
  const { organization } = useOrganization()
  const orgId = organization?.id
  return useQuery({
    queryKey: ['dashboard', orgId],
    queryFn: () => api.get('/dashboard').then(r => r.data),
    enabled: Boolean(orgId),
    ...DYNAMIC_OPTS,
  })
}
```

- [x] Cache: `DYNAMIC_OPTS` (staleTime 5min, refetchOnWindowFocus)
- [x] Exportado de `useSchoolData.js` (seguir convenção existente)
- [x] Tipado com a resposta do schema (criar tipos TypeScript ou usar JSDoc)

---

## FASE 3 — Frontend: Widget Components

### WBS 3.1 — Criar diretório de componentes
**Status**: ✅ DONE
**Priority**: MAX
**Estimativa**: 5min
**Ficheiro**: `frontend/src/components/dashboard/` (novo diretório)

- [x] Criar diretório `frontend/src/components/dashboard/`
- [x] Criar `index.js` para barrel exports

---

### WBS 3.2 — Widget `AlertBar`
**Status**: ✅ DONE
**Priority**: MAX
**Estimativa**: 2h
**Ficheiro**: `frontend/src/components/dashboard/AlertBar.jsx`
**Depende de**: WBS 2.1

**Especificação visual**:

4 cards horizontais, cada um com:
- Ícone CoreUI (`cilWarning`, `cilCheckCircle`, `cilClock`, `cilSwapHorizontal`)
- Número grande (ex: `3`) com cor dinâmica
- Rótulo em baixo (ex: "Ocorrências hoje")
- Cor de estado:
  - 🟢 0 itens → `var(--rs-success-300)` — tom neutro/subtil
  - 🟠 1-4 itens → `var(--rs-warning-400)` — âmbar
  - 🔴 5+ itens → `var(--rs-danger-400)` — vermelho coral
- **NOTA**: Não usar verde/vermelho CSS genéricos. Usar os tokens do design system (`--rs-*`).
- Clicável → `useNavigate` para a página respetiva com query params:
  - Ocorrências → `/absences?date=today&status=PENDING`
  - Timesheets → `/timesheets?status=submitted`
  - Rascunhos → `/schedules?tab=drafts`
  - Substituições → `/absences?view=substitutions&date=today`

**Props**:
```jsx
<AlertBar alerts={DashboardV1Response.alerts} isLoading={boolean} />
```

**Estados**:
- Loading: 4 cards skeleton (pulso de opacidade)
- Data: cards com valores reais e cores de estado
- Empty (tudo 0): todos em verde/subtil — estado desejável
- Error: não aplicável (tratado no nível da página)

---

### WBS 3.3 — Widget `ResourceCounts`
**Status**: ✅ DONE
**Priority**: HIGH
**Estimativa**: 1h30
**Ficheiro**: `frontend/src/components/dashboard/ResourceCounts.jsx`
**Depende de**: WBS 2.1

**Especificação visual**:

Linha de 5 "KPI cards" + mini-card de distribuição de salas:
```
┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐  ┌──────────────────┐
│    47   │ │    12   │ │    4    │ │    95   │ │    30   │  │ 🏫 Salas por tipo │
│Professores│ │ Turmas  │ │ Cursos  │ │Disciplinas│ │  Salas  │  │ Normal: 16       │
│          │ │         │ │         │ │          │ │         │  │ Lab: 8           │
└─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘  │ Gym: 3 · Arte: 3 │
                                                               └──────────────────┘
```

**Props**:
```jsx
<ResourceCounts resources={DashboardV1Response.resources} isLoading={boolean} />
```

**Estados**:
- Loading: 6 skeletons (retângulos com shimmer)
- Data: números reais
- Empty (tudo 0): mostrar 0 em vez de esconder

---

### WBS 3.4 — Widget `ScheduleHealthCard`
**Status**: ✅ DONE
**Priority**: HIGH
**Estimativa**: 2h
**Ficheiro**: `frontend/src/components/dashboard/ScheduleHealthCard.jsx`
**Depende de**: WBS 2.1

**Especificação visual**:

Card com título "Saúde do Horário" e grid de métricas:
```
┌─────────────────────────────────────────┐
│  📊 Saúde do Horário                    │
│                                         │
│  ┌──────────┐ ┌──────────┐ ┌─────────┐ │
│  │ Turmas   │ │ Média    │ │ Conflitos│ │
│  │ sem aula │ │ slots/   │ │ professor│ │
│  │    2     │ │ turma    │ │    0     │ │
│  │          │ │   28.5   │ │          │ │
│  └──────────┘ └──────────┘ └─────────┘ │
│                                         │
│  ┌──────────┐ ┌──────────┐ ┌─────────┐ │
│  │ Média    │ │ Equidade │ │ Conflitos│ │
│  │ slots/   │ │ (spread) │ │ turma    │ │
│  │ professor│ │   3.2    │ │    0     │ │
│  │   22.1   │ │          │ │          │ │
│  └──────────┘ └──────────┘ └─────────┘ │
│                                         │
│  1,247 blocos no total · Geração #abc123 │
└─────────────────────────────────────────┘
```

**Métricas a mostrar**:
1. Turmas sem aulas esta semana (`classes_empty_week`) — **alerta se > 0**
2. Média de slots por turma (`week_slots_avg`)
3. Conflitos de professor (`duplicate_teacher_slots`) — **alerta se > 0**
4. Média de slots por professor (`teacher_week_slots_avg`)
5. Equidade entre turmas (`weekly_fairness_spread`) — menor é melhor
6. Conflitos de turma (`duplicate_class_slots`) — **alerta se > 0**

**Props**:
```jsx
<ScheduleHealthCard health={DashboardV1Response.schedule_health} isLoading={boolean} />
```

**Empty state** (sem geração): "Nenhum horário gerado. Clique para criar o primeiro." com botão para `/schedules?action=new`.

---

### WBS 3.5 — Widget `ClassProgressOverview`
**Status**: ✅ DONE
**Priority**: HIGH
**Estimativa**: 2h30
**Ficheiro**: `frontend/src/components/dashboard/ClassProgressOverview.jsx`
**Depende de**: WBS 2.1

**Especificação visual**:

Tabela/lista de turmas ordenadas por % de progresso (menor primeiro = mais atrasadas primeiro):

```
┌─────────────────────────────────────────────────────────┐
│  📈 Progresso Curricular                                │
│                                                         │
│  Turma          Curso     Ano   Progresso               │
│  ─────────      ─────     ───   ─────────               │
│  1ºB TGPSI      TGPSI     10    ████░░░░░░  42%  ⚠️    │
│  1ºA TGPSI      TGPSI     10    ██████░░░░  64%         │
│  2ºA TGPSI      TGPSI     11    █████████░  91%         │
│  1ºA Téc. Aux.  TAuxSau    10    ████░░░░░░  38%  ⚠️    │
│  ...                                                    │
│                                                         │
│  Média global: 67%  ·  4 de 6 turmas com dados          │
└─────────────────────────────────────────────────────────┘
```

Cada linha:
- Nome da turma (clicável → `/courses/:courseId/classes/:classId`)
- Nome do curso
- Ano (10/11/12)
- Barra de progresso horizontal com percentagem
- Ícone ⚠️ se < 50%
- Cores da barra: baixo progresso → `--rs-warning-400`, alto → `--rs-success-400`

**Props**:
```jsx
<ClassProgressOverview progress={DashboardV1Response.class_progress} isLoading={boolean} />
```

**Estados**:
- Loading: 5 linhas skeleton com shimmer nas barras
- Data: tabela ordenada
- Empty: "Sem dados de progresso. Comece por registar horas nas turmas."
- Parcial (algumas turmas sem dados): mostrar apenas as que têm; badge com "X/Y turmas com dados"

---

### WBS 3.6 — Widget `DebtSummaryCard`
**Status**: ✅ DONE
**Priority**: MEDIUM
**Estimativa**: 1h
**Ficheiro**: `frontend/src/components/dashboard/DebtSummaryCard.jsx`
**Depende de**: WBS 2.1

**Especificação visual**:

Card compacto de resumo de dívidas:
```
┌─────────────────────────────────────────┐
│  ⏳ Dívidas de Horas                    │
│                                         │
│      34h          12 gaps               │
│   horas em dívida  ocorrências          │
│                                         │
│  4 turmas afetadas  ·  8h vencidas      │
│                                         │
│  [Ver detalhes →]                       │
└─────────────────────────────────────────┘
```

**Props**:
```jsx
<DebtSummaryCard debts={DashboardV1Response.debts} isLoading={boolean} />
```

**Cor de destaque**: Se `total_hours_owed > 0` → usar `--rs-warning-400` para o número grande. Se 0 → `--rs-success-300`.

**Clicável**: Link "Ver detalhes" → `/absences?view=debts`

---

### WBS 3.7 — Widget `QuickActions`
**Status**: ✅ DONE
**Priority**: MEDIUM
**Estimativa**: 1h
**Ficheiro**: `frontend/src/components/dashboard/QuickActions.jsx`
**Depende de**: WBS 2.1

**Especificação visual**:

Botões de ação, visíveis condicionalmente:

```
┌─────────────────────────────────────────┐
│  🔗 Ações Rápidas                       │
│                                         │
│  [Gerir ocorrências de hoje (3)]        │  ← só se > 0
│  [Aprovar timesheets (5)]               │  ← só se > 0
│  [Rever rascunho pendente (1)]          │  ← só se > 0
│  [Gerar novo horário]                   │  ← sempre visível
└─────────────────────────────────────────┘
```

**Lógica de visibilidade**:
| Botão | Condição | Destino |
|-------|---------|---------|
| Gerir ocorrências de hoje | `pending_occurrences_today > 0` | `/absences?date=today` |
| Aprovar timesheets | `pending_timesheets > 0` | `/timesheets?status=submitted` |
| Rever rascunho pendente | `pending_drafts > 0` | `/schedules?tab=drafts` |
| Gerar novo horário | Sempre | `/schedules?action=new` |

**Props**:
```jsx
<QuickActions alerts={DashboardV1Response.alerts} />
```

- [x] Botões CoreUI estilizados (não links de texto simples)
- [x] Badge com contagem integrado no botão
- [x] Loading state: botões desabilitados com skeleton

---

## FASE 4 — Frontend: Page Composition & Polish

### WBS 4.1 — Refatorar `Dashboard.jsx`
**Status**: ✅ DONE
**Priority**: MAX
**Estimativa**: 3h
**Ficheiro**: `frontend/src/pages/Dashboard.jsx`
**Depende de**: WBS 3.2 a 3.7

**Estrutura da página**:

```jsx
const Dashboard = () => {
  const { data, isLoading, isError, error } = useDashboard()

  // ── Layout ──────────────────────────────────────
  // ZONA 0: Header (manter estilo zen existente)
  //   "Visão Geral" / "Painel de Controlo" + luxury-line
  //
  // ZONA 1: 🚨 AlertBar (full width)
  //   <AlertBar alerts={data?.alerts} isLoading={isLoading} />
  //
  // ZONA 2: Grid 2 colunas
  //   Col A: <ScheduleHealthCard ... />
  //   Col B: <ClassProgressOverview ... />
  //
  // ZONA 3: Grid 2 colunas
  //   Col A: <DebtSummaryCard ... /> + <ResourceCounts ... />
  //   Col B: <AnalyticsHeatmap /> (manter existente)
  //
  // ZONA 4: QuickActions (full width, apenas se houver ações)
  //   <QuickActions alerts={data?.alerts} />
  //
  // ── Estados ────────────────────────────────────
  if (isError) → <CAlert color="danger"> com mensagem + retry
  // NOTA: Cada widget tem o seu próprio skeleton loading state,
  // a página não precisa de um loading state global
}
```

**Layout responsivo**:
```
Desktop (>1200px):     Mobile (<768px):
┌──────────────────┐   ┌────────────┐
│    AlertBar      │   │ AlertBar   │
├────────┬─────────┤   │ (scroll h) │
│ Health │Progress │   ├────────────┤
│        │         │   │ Health     │
├────────┼─────────┤   ├────────────┤
│ Debts  │Heatmap  │   │ Progress   │
│ +Counts│         │   ├────────────┤
├────────┴─────────┤   │ Debts      │
│  QuickActions    │   ├────────────┤
└──────────────────┘   │ Counts     │
                        ├────────────┤
                        │ Heatmap    │
                        ├────────────┤
                        │ Actions    │
                        └────────────┘
```

**Regras**:
- [x] Manter o header com classes zen existentes (`zen-reveal`, `text-display`, `text-editorial`, `luxury-line`)
- [x] Cada widget encapsula o seu próprio loading/empty/error state
- [x] Usar `CCol`, `CRow` do CoreUI para o grid responsivo
- [x] Adicionar `zen-stagger-1` a `zen-stagger-6` nos widgets para animação de entrada sequencial
- [x] Envolver cada widget em `<div className="zen-card">` com header + body
- [x] Não remover o `AnalyticsHeatmap` existente — mantê-lo como widget

---

### WBS 4.2 — Aplicar micro-animações
**Status**: ✅ DONE
**Priority**: LOW
**Estimativa**: 1h
**Ficheiro**: `frontend/src/pages/Dashboard.jsx` + CSS global
**Depende de**: WBS 4.1

**Animações a implementar**:
- [x] Cards com `zen-stagger-N` para entrada sequencial (fade-in + slide-up)
- [x] AlertBar: números com transição de cor quando mudam de valor
- [x] Hover nos cards: `transform: translateY(-2px)` + `box-shadow` suave (transição 200ms)
- [x] QuickActions: botões com hover que expande ligeiramente o badge
- [x] ClassProgress: barras de progresso animadas ao entrar no viewport (preenchimento da esquerda para a direita)

---

## FASE 5 — Testes (Unitários + E2E Comportamento Humano) & CI/CD

### WBS 5.1 — Testes unitários/integração frontend (Vitest + RTL)
**Status**: ✅ DONE
**Priority**: HIGH
**Estimativa**: 2h
**Ficheiro**: `frontend/src/test/Dashboard.test.jsx` (refactor; localização correta é `src/test/`, não `__tests__`)
**Depende de**: WBS 4.1

**Framework**: Vitest + React Testing Library (jsdom) — stack existente do projeto.

**Cenários**:

| # | Cenário | Esperado |
|---|---------|----------|
| 1 | Dashboard com dados completos | Todos os widgets renderizam com dados mock |
| 2 | Dashboard loading | Skeletons visíveis em todos os widgets |
| 3 | Dashboard com erro | CAlert com mensagem de erro visível |
| 4 | Dashboard sem geração de horário | ScheduleHealth mostra empty state |
| 5 | Dashboard sem progresso | ClassProgress mostra empty state |
| 6 | Dashboard com tudo a 0 (sem problemas) | AlertBar em estado verde/subtil; QuickActions sem botões condicionais |
| 7 | QuickActions: sem ocorrências → botão escondido | Apenas "Gerar novo horário" visível |
| 8 | QuickActions: com ocorrências → botão visível | Botão "Gerir ocorrências" com badge visível |
| 9 | Navegação: clique no alerta de ocorrências | `navigate` chamado com `/absences?date=today` |

**Mock strategy**:
- Mock `useDashboard` hook para injetar dados de teste
- Mock `useNavigate` para verificar navegação

---

### WBS 5.2 — Testes end-to-end manuais
**Status**: ✅ DONE
**Priority**: HIGH
**Estimativa**: 1h
**Depende de**: WBS 4.1

**Script de validação manual** (usando seed data):

1. [ ] Fazer login como admin (org com seed data completo)
2. [ ] Verificar que a barra de alertas mostra contagens corretas
3. [ ] Clicar em "Ocorrências hoje" → verificar que navega para `/absences` com filtros
4. [ ] Verificar que ResourceCounts mostra números consistentes com os CRUDs
5. [ ] Verificar que ScheduleHealth mostra métricas (se houver geração)
6. [ ] Verificar que ClassProgress mostra turmas ordenadas por progresso
7. [ ] Verificar que DebtSummary mostra valores consistentes com `/occurrences/debts`
8. [ ] Testar em viewport mobile (375px) — layout empilhado legível
9. [ ] Testar em viewport tablet (768px) — grid adaptado

---

### WBS 5.3 — Verificação dos 4 pilares
**Status**: ✅ DONE
**Priority**: MAX
**Estimativa**: 30min
**Depende de**: WBS 5.1, 5.2

| Pilar | Verificação | Critério |
|-------|-------------|----------|
| **Optimization** | 1 chamada API vs 6+ chamadas separadas | Tempo de resposta < 500ms com seed data |
| **Stability** | Endpoint não crasha com dados em falta | Todos os campos nullable preenchidos com None/0/[] |
| **Scalability** | Queries usam índices existentes; sem N+1 | `EXPLAIN ANALYZE` não mostra seq scans em tabelas grandes |
| **Security** | Tenant isolation em todas as queries | Todas as queries incluem `WHERE organization_id = $1` |

---

### WBS 5.4 — Testes E2E simulando comportamento humano (Playwright + MSW)
**Status**: ✅ DONE
**Priority**: MAX
**Estimativa**: 6h
**Ficheiros**:
- `frontend/e2e/dashboard/dashboard.spec.js` — **Novo**
- `frontend/e2e/dashboard/fixtures/dashboard-data.js` — **Novo**
- `frontend/src/test/mocks/handlers.js` — **Novo**
- `frontend/src/test/mocks/data/dashboard.js` — **Novo**
**Depende de**: WBS 0.2, WBS 4.1

**Filosofia**: Estes testes devem simular o que um Diretor/Secretário **realmente faz** ao abrir o dashboard. Não são testes de "renderização" (isso é coberto pelo Vitest) — são testes de **fluxo de utilizador completo**.

**User Journeys a implementar (6 cenários)**:

#### Journey 1: "Check-in matinal — há problemas hoje"
**Persona**: Diretor abre o dashboard de manhã para ver o estado da escola.

```javascript
test('Director morning check-in: sees alerts and navigates to resolve them', async ({ page }) => {
  // ARRANGE: Mock dashboard com 3 ocorrências pendentes, 5 timesheets, 1 draft
  await page.route('**/api/v1/dashboard', route => route.fulfill({
    body: JSON.stringify(dashboardWithAlerts)
  }))

  // ACT: Navega para o dashboard (já autenticado)
  await page.goto('/dashboard')

  // ASSERT: Vê a barra de alertas com as 3 contagens e cores corretas
  await expect(page.locator('[data-testid="alert-ocorrencias"]')).toContainText('3')
  await expect(page.locator('[data-testid="alert-ocorrencias"]')).toHaveClass(/danger/)  // 3 >= 1 → âmbar
  await expect(page.locator('[data-testid="alert-timesheets"]')).toContainText('5')
  await expect(page.locator('[data-testid="alert-timesheets"]')).toHaveClass(/danger/)    // 5 → vermelho
  await expect(page.locator('[data-testid="alert-drafts"]')).toContainText('1')
  await expect(page.locator('[data-testid="alert-drafts"]')).toHaveClass(/warning/)        // 1 → âmbar

  // ACT: Clica no card de ocorrências
  await page.locator('[data-testid="alert-ocorrencias"]').click()

  // ASSERT: Navegou para /absences com os filtros corretos
  await expect(page).toHaveURL(/\/absences\?.*date=today/)
  await expect(page.locator('h1, h2')).toContainText(/Ocorrências|Faltas/)
})
```

#### Journey 2: "Dia tranquilo — tudo a zero"
**Persona**: Diretor abre o dashboard e vê que está tudo em ordem.

```javascript
test('Director calm day: all alerts at zero, everything green', async ({ page }) => {
  // ARRANGE: Mock dashboard com todos os alertas a 0
  await page.route('**/api/v1/dashboard', route => route.fulfill({
    body: JSON.stringify(dashboardAllClear)
  }))

  await page.goto('/dashboard')

  // ASSERT: Todos os cards de alerta a 0 com cor verde/subtil
  for (const alert of ['ocorrencias', 'timesheets', 'drafts', 'substituicoes']) {
    await expect(page.locator(`[data-testid="alert-${alert}"]`)).toContainText('0')
    await expect(page.locator(`[data-testid="alert-${alert}"]`)).toHaveClass(/success/)
  }

  // ASSERT: QuickActions: botões condicionais NÃO visíveis
  await expect(page.locator('[data-testid="action-ocorrencias"]')).not.toBeVisible()
  await expect(page.locator('[data-testid="action-timesheets"]')).not.toBeVisible()
  await expect(page.locator('[data-testid="action-drafts"]')).not.toBeVisible()

  // ASSERT: Apenas "Gerar novo horário" visível
  await expect(page.locator('[data-testid="action-gerar-horario"]')).toBeVisible()
})
```

#### Journey 3: "Turma com baixo progresso — investigar"
**Persona**: Diretor nota uma turma com progresso crítico e clica para ver detalhes.

```javascript
test('Director investigates low-progress class from dashboard', async ({ page }) => {
  // ARRANGE: Mock com turmas ordenadas (menor progresso primeiro)
  await page.route('**/api/v1/dashboard', route => route.fulfill({
    body: JSON.stringify(dashboardWithProgress)
  }))

  await page.goto('/dashboard')

  // ASSERT: A primeira turma da lista tem < 50% e mostra ícone de alerta
  const firstClass = page.locator('[data-testid="class-progress-row"]').first()
  await expect(firstClass).toContainText('38%')
  await expect(firstClass.locator('[data-testid="warning-icon"]')).toBeVisible()

  // ACT: Clica na turma com baixo progresso
  await firstClass.click()

  // ASSERT: Navegou para a página de detalhe da turma
  await expect(page).toHaveURL(/\/courses\/\d+\/classes\/\d+/)
  await expect(page.locator('h1, h2')).toContainText(/1ºA Téc. Aux/)
})
```

#### Journey 4: "Aprovar itens pendentes via QuickActions"
**Persona**: Diretor usa os atalhos do dashboard para resolver pendências rapidamente.

```javascript
test('Director resolves pending items via QuickActions', async ({ page }) => {
  await page.route('**/api/v1/dashboard', route => route.fulfill({
    body: JSON.stringify(dashboardWithAlerts)
  }))

  await page.goto('/dashboard')

  // ACT: Clica "Aprovar timesheets (5)"
  await page.locator('[data-testid="action-timesheets"]').click()
  await expect(page).toHaveURL(/\/timesheets\?status=submitted/)

  // ACT: Volta ao dashboard
  await page.goto('/dashboard')

  // ACT: Clica "Rever rascunho pendente (1)"
  await page.locator('[data-testid="action-drafts"]').click()
  await expect(page).toHaveURL(/\/schedules\?tab=drafts/)
})
```

#### Journey 5: "Escola nova — sem dados"
**Persona**: Diretor de uma escola recém-criada abre o dashboard pela primeira vez.

```javascript
test('New school: empty dashboard with helpful empty states', async ({ page }) => {
  await page.route('**/api/v1/dashboard', route => route.fulfill({
    body: JSON.stringify(dashboardEmptyOrg)
  }))

  await page.goto('/dashboard')

  // ASSERT: Todos os counts = 0
  await expect(page.locator('[data-testid="resource-teachers"]')).toContainText('0')
  await expect(page.locator('[data-testid="resource-classes"]')).toContainText('0')

  // ASSERT: ScheduleHealth mostra empty state com CTA
  await expect(page.locator('[data-testid="schedule-health-empty"]')).toBeVisible()
  await expect(page.locator('[data-testid="schedule-health-empty"]')).toContainText('Nenhum horário gerado')

  // ASSERT: ClassProgress mostra empty state
  await expect(page.locator('[data-testid="class-progress-empty"]')).toBeVisible()

  // ASSERT: DebtSummary mostra 0h
  await expect(page.locator('[data-testid="debt-summary"]')).toContainText('0h')

  // ASSERT: AlertBar tudo a 0
  await expect(page.locator('[data-testid="alert-ocorrencias"]')).toContainText('0')
})
```

#### Journey 6: "Layout responsivo — mobile, tablet, desktop"
**Persona**: Diretor acede ao dashboard a partir de um tablet ou telemóvel.

```javascript
test('Dashboard renders correctly on mobile viewport', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 })  // iPhone X
  await page.route('**/api/v1/dashboard', route => route.fulfill({
    body: JSON.stringify(dashboardComplete)
  }))

  await page.goto('/dashboard')

  // ASSERT: Widgets empilhados verticalmente (não lado a lado)
  const alertBar = page.locator('[data-testid="alert-bar"]')
  await expect(alertBar).toBeVisible()

  // ASSERT: AlertBar tem scroll horizontal em mobile (4 cards)
  const alertCards = alertBar.locator('[data-testid^="alert-"]')
  await expect(alertCards).toHaveCount(4)

  // ASSERT: Todos os widgets estão presentes e visíveis
  await expect(page.locator('[data-testid="schedule-health"]')).toBeVisible()
  await expect(page.locator('[data-testid="class-progress"]')).toBeVisible()
  await expect(page.locator('[data-testid="debt-summary"]')).toBeVisible()
  await expect(page.locator('[data-testid="resource-counts"]')).toBeVisible()
})

test('Dashboard renders correctly on tablet viewport', async ({ page }) => {
  await page.setViewportSize({ width: 768, height: 1024 })  // iPad
  await page.route('**/api/v1/dashboard', route => route.fulfill({
    body: JSON.stringify(dashboardComplete)
  }))

  await page.goto('/dashboard')

  // ASSERT: Widgets adaptam-se a 1-2 colunas
  await expect(page.locator('[data-testid="schedule-health"]')).toBeVisible()
  await expect(page.locator('[data-testid="class-progress"]')).toBeVisible()
})
```

**Requisitos técnicos para os testes**:
- [x] Todos os widgets devem ter atributos `data-testid` para seletores estáveis:
  - `data-testid="alert-bar"`
  - `data-testid="alert-ocorrencias"`, `data-testid="alert-timesheets"`, etc.
  - `data-testid="action-ocorrencias"`, `data-testid="action-timesheets"`, etc.
  - `data-testid="resource-teachers"`, `data-testid="resource-classes"`, etc.
  - `data-testid="schedule-health"`, `data-testid="schedule-health-empty"`
  - `data-testid="class-progress"`, `data-testid="class-progress-empty"`, `data-testid="class-progress-row"`
  - `data-testid="debt-summary"`
  - `data-testid="warning-icon"` (ícone ⚠️)
- [x] Mock de autenticação: injetar token/admin role no localStorage antes de cada teste (simular sessão ativa)
- [x] Fixtures de dados reutilizáveis em `frontend/e2e/dashboard/fixtures/dashboard-data.js`:
  ```javascript
  export const dashboardComplete = { /* todos os campos preenchidos */ }
  export const dashboardWithAlerts = { /* 3 ocorrências, 5 timesheets, 1 draft */ }
  export const dashboardAllClear = { /* todos os alertas a 0 */ }
  export const dashboardWithProgress = { /* 4 turmas com progresso variado */ }
  export const dashboardEmptyOrg = { /* organização vazia */ }
  export const dashboardNoGeneration = { /* sem geração de horário */ }
  ```
- [x] MSW handlers devem interceptar também:
  - `GET /api/v1/analytics/availability-heatmap` (para o heatmap não quebrar)
  - `GET /api/v1/import/timeslots` (para o heatmap não quebrar)

---

### WBS 5.5 — Integrar testes E2E no pipeline CI/CD
**Status**: ✅ DONE
**Priority**: MAX
**Estimativa**: 2h
**Ficheiro**: `.github/workflows/ci.yml` (editar)
**Depende de**: WBS 5.4

**Especificação**:

Adicionar um novo job `e2e-tests` ao workflow existente, que corre **em paralelo** com `test-and-scan` (não sequencial — não depende do job de backend/frontend porque os E2E usam MSW para mockar a API).

```yaml
  e2e-tests:
    name: E2E — Dashboard User Journeys (Playwright)
    runs-on: ubuntu-latest
    timeout-minutes: 15

    steps:
      - uses: actions/checkout@v4

      - name: Setup Node.js ${{ env.NODE_VERSION }}
        uses: actions/setup-node@v4
        with:
          node-version: ${{ env.NODE_VERSION }}
          cache: npm
          cache-dependency-path: frontend/package-lock.json

      - name: Install Dependencies
        working-directory: frontend
        run: npm ci

      - name: Install Playwright Browsers
        working-directory: frontend
        run: npx playwright install --with-deps chromium

      - name: Run E2E Tests
        working-directory: frontend
        run: npx playwright test --project=chromium

      - name: Upload Screenshots (on failure)
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: playwright-screenshots
          path: frontend/test-results/
          retention-days: 7
```

**Regras de CI/CD**:
- [x] Job `e2e-tests` corre em paralelo com `test-and-scan` (não bloqueia)
- [x] Timeout: 15 minutos (Playwright + MSW é rápido, ~30s por spec × 6 specs = ~3min)
- [x] `--with-deps` instala dependências de sistema do Chromium (bibliotecas .so)
- [x] Screenshots dos testes falhados são upload como artifact para debugging
- [x] Playwright config deve ter `retries: 1` em CI (process.env.CI) para mitigar flakiness
- [x] Adicionar `webServer` block no `playwright.config.js`:
  ```javascript
  webServer: {
    command: 'npm run dev',
    port: 5173,
    reuseExistingServer: !process.env.CI,
    timeout: 120 * 1000,
  }
  ```
- [x] Não usar SonarQube no job de E2E (o job `test-and-scan` já cobre isso)

**SonarQube**: Não há ação necessária — o job `test-and-scan` existente continua a correr os testes Vitest (que geram `lcov.info`) e Pytest (que gera `coverage.xml`). Os E2E são complementares e não participam na cobertura do SonarQube (são testes de comportamento, não de cobertura de código).

---

## FASE 6 — Documentação

### WBS 6.1 — Atualizar documentação do projeto
**Status**: ✅ DONE
**Priority**: MEDIUM
**Estimativa**: 30min
**Depende de**: WBS 4.1

**Ficheiros a atualizar**:
- [x] `documentation/ARQUITETURA_COMPLETA.md` — adicionar endpoint `GET /api/v1/dashboard` na lista de API
- [x] `documentation/06_frontend_ux/README.md` — adicionar referência ao dashboard e seus componentes
- [x] `documentation/05_backend_api/README.md` — documentar o novo endpoint com schema

---

## 3. Dependências entre WBS Items

```
WBS 0.1 (discovery dados)        WBS 0.2 (playwright+msw setup — paralelo)
   │                                       │
   ▼                                       │
WBS 1.1 (schemas) ──► 1.2 (service) ──► 1.3 (endpoint) ──► 1.4 (router) ──► 1.5 (testes BE unit)
                                                      │
                                                      ▼
                                           WBS 2.1 (hook useDashboard)
                                                      │
                        ┌─────────────────────────────┤
                        ▼                             ▼
                 WBS 3.2 (AlertBar)            WBS 3.3 (ResourceCounts)
                 WBS 3.4 (ScheduleHealth)      WBS 3.5 (ClassProgress)
                 WBS 3.6 (DebtSummary)         WBS 3.7 (QuickActions)
                        │                             │
                        └──────────┬──────────────────┘
                                   ▼
                            WBS 4.1 (Dashboard.jsx)
                                   │
                                   ▼
                            WBS 4.2 (micro-animações)
                                   │
          ┌───────────────┬────────┴────────┬──────────────────┐
          ▼               ▼                 ▼                  ▼
   WBS 5.1 (Vitest)  WBS 5.2 (manuais)  WBS 5.3 (pilares)  WBS 5.4 (E2E Playwright)
                                                                    │
                                                                    ▼
                                                            WBS 5.5 (CI/CD pipeline)
                                                                    │
                                                                    ▼
                                                            WBS 6.1 (documentação)
```

---

## 4. Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|--------------|---------|-----------|
| `ClassProgress` sem dados para algumas turmas | Média | Baixo | Widget mostra apenas turmas com dados; badge informativo |
| `schedule/audit/summary` sem geração ativa | Alta | Baixo | `schedule_health = None`; widget mostra empty state com CTA |
| Ocorrências sem filtro por data no endpoint existente | Baixa | Alto | **A confirmar no WBS 0.1**. Se não existir, adicionar query param `date` ao endpoint de ocorrências |
| Seed data insuficiente para testar todos os cenários | Média | Médio | Criar seed data mínima com: 1 org, 4 professores, 2 cursos, 3 turmas, progresso, ocorrências |
| Performance: queries agregadas lentas com muitos dados | Baixa | Médio | Usar `selectinload`; adicionar índices se necessário; cache de 5min no frontend |
| Layout inconsistente com outras páginas | Baixa | Baixo | Seguir o padrão "zen" já existente no Dashboard atual |
| Testes E2E flaky em CI (timeouts, race conditions) | Média | Alto | `retries: 1` em CI; MSW em vez de backend real elimina timeout de rede; screenshots em falha para debug; seletores `data-testid` estáveis em vez de classes CSS |
| Playwright + MSW conflito com autenticação (cookies/httpOnly) | Baixa | Médio | Mock de autenticação via localStorage (Zustand persist); bypass do fluxo OAuth2 real; handler MSW para `POST /auth/refresh` evita 401 |

---

## 5. Incertezas (a confirmar)

As seguintes questões precisam de verificação antes ou durante a implementação:

1. **Endpoint de ocorrências com filtro por data**: O `GET /occurrences/` atual aceita `date_from`/`date_to` ou apenas `class_id`? Se não aceitar filtro por data, será necessário adicionar esse parâmetro para contar "ocorrências de hoje". *(Verificar no WBS 0.1)*

2. **ClassProgress — cobertura de dados**: O seed atual popula `ClassProgress` para todas as turmas? Se não, o widget `ClassProgressOverview` terá de lidar com dados parciais.

3. **Formato da data "today"**: Usar `date.today()` no backend ou receber como parâmetro? Para V1, `date.today()` no backend é suficiente. Para V2, considerar timezone da organização.

4. **AnalyticsHeatmap**: Manter como widget separado com a sua própria chamada API (como está agora) ou migrar para o endpoint agregado? **Recomendação para V1**: Manter separado para minimizar scope. Migrar para o endpoint agregado na V2.

5. **Orçamento total de horas vs horas completadas no ClassProgress**: Confirmar que `hours_completed` e `hours_total` existem no modelo `ClassProgress` e são calculados corretamente (já existem nos schemas `ModuleProgressRead` e `SubjectProgressRead`).

---

## 6. Definição de "Done"

O dashboard V1 está concluído quando:

- [x] `GET /api/v1/dashboard` retorna 200 com todos os campos documentados
- [x] 8/8 testes backend passam (pytest)
- [x] 9/9 testes unitários frontend passam (Vitest + RTL)
- [x] 6/6 testes E2E passam em CI (Playwright — 6 user journeys)
- [x] Job `e2e-tests` no GitHub Actions passa consistentemente (sem flaky)
- [x] Dashboard carrega em < 500ms com seed data completo
- [x] Todos os widgets têm loading, empty, error states implementados
- [x] Layout responsivo testado em 3 viewports via Playwright (mobile 375px, tablet 768px, desktop 1280px)
- [x] Cores usam tokens do design system (nada de verde/vermelho genéricos)
- [x] Todos os widgets têm atributos `data-testid` para seletores E2E estáveis
- [x] Tenant isolation verificada em todas as queries
- [x] Documentação atualizada (ARQUITETURA_COMPLETA.md + READMEs)
- [x] Validação manual com seed data passou em todos os checkpoints do WBS 5.2
- [x] Screenshots de E2E falhados são uploaded como artifact no CI
# Historical Dashboard WBS

This document is retained as pre-beta history. References to `/schedule/audit/*` are not current beta behavior; those routes were removed in the 2026-07-05 baseline cleanup.
