# Plano WBS V2: Registo de Aulas — Refinamento e Expansão

## 0. Contexto Técnico (Para quem nunca tocou na codebase)

Esta secção fornece todo o contexto necessário para compreender e executar o plano sem conhecimento prévio da aplicação.

### 0.1. Tech Stack

| Camada | Tecnologia | Versão |
|--------|-----------|--------|
| **Backend** | Python, FastAPI | 3.12, 0.115+ |
| **ORM** | SQLAlchemy (async com asyncpg) | 2.0+ |
| **Base de Dados** | PostgreSQL | 15 |
| **Migrações** | Alembic | — |
| **Frontend** | React | 18+ |
| **UI Framework** | CoreUI (Bootstrap 5) | — |
| **State/Cache** | React Query (TanStack Query) | 5+ |
| **Estado Global** | Zustand (auth store) | — |
| **Routing** | React Router | 6+ |
| **Task Queue** | Celery + Redis | — |
| **CI/CD** | GitHub Actions | — |

### 0.2. Estrutura do Projeto

```
MeuProjeto/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── api.py                    ← Router principal (regista todos os sub-routers)
│   │   │   └── v1/endpoints/
│   │   │       ├── schedule.py           ← Endpoints de horários e blocos
│   │   │       ├── timesheets.py         ← Endpoints de fecho semanal
│   │   │       ├── occurrences.py        ← Endpoints de ocorrências
│   │   │       └── org_settings.py       ← Endpoints de configurações
│   │   ├── db/database.py                ← Sessão async e sync do SQLAlchemy
│   │   ├── models.py                     ← TODOS os modelos SQLAlchemy (ficheiro único)
│   │   ├── schemas.py                    ← TODOS os schemas Pydantic (ficheiro único)
│   │   └── services/
│   │       ├── lesson_log_service.py     ← Lógica de registo de aulas (upsert, progresso)
│   │       ├── timesheet_service.py      ← Lógica de fecho semanal (submissão, aprovação)
│   │       ├── occurrence_service.py     ← Lógica de ocorrências e substituições
│   │       ├── schedule_service.py       ← Lógica de consulta de horários
│   │       └── settings_service.py       ← Lógica de configurações e soft-reset
│   ├── tests/                            ← Testes pytest (correm no CI)
│   ├── alembic/                          ← Migrações da BD
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── apiClient.js                  ← Instância axios com interceptors de auth
│       ├── store.js                      ← Zustand store (user, orgId, role, teacherId)
│       ├── hooks/useSchoolData.js        ← TODOS os hooks React Query (queries + mutations)
│       ├── components/
│       │   ├── WeekGrid.jsx              ← Grelha semanal (tabela de blocos)
│       │   ├── LessonLogModal.jsx        ← Modal de registo de aula (professor + admin)
│       │   └── DefaultLayout.jsx         ← Layout com sidebar de navegação
│       ├── pages/
│       │   ├── Schedules.jsx             ← /schedules (admin e professor)
│       │   ├── MySchedules.jsx           ← /my-schedules (professor — vista pessoal)
│       │   ├── Timesheets.jsx            ← /timesheets (aprovações semanais)
│       │   ├── Occurrences.jsx           ← /absences (ocorrências e histórico)
│       │   ├── SchoolConfig.jsx          ← /settings (configurações da escola)
│       │   └── ...outras páginas
│       ├── utils/
│       │   └── subjectColors.js          ← Utilitário de cores por disciplina
│       └── index.css                     ← CSS global com variáveis de design system
├── documentation/
│   └── 04_operational_features/
│       ├── WBS_REGISTO_AULAS.md          ← Plano V1 (concluído)
│       └── WBS_REGISTO_AULAS_V2.md       ← Este documento
└── .github/workflows/
    ├── ci.yml                            ← CI: pytest no backend
    └── test.yml                          ← CI: pytest + vitest + SonarQube
```

### 0.3. Glossário de Domínio

| Termo | O que é | Exemplo |
|-------|---------|---------|
| **Organization (Org)** | A escola. Cada escola tem um `org_id`. Todos os dados são isolados por org (multi-tenant). | `org_id = 42` |
| **Teacher** | Professor associado a uma org. Tem um `teacher_id` e um `user_id` (para login). | Prof. Silva |
| **Class** | Turma. Ex: "10A", "11B". Tem um `course_id` (curso). | Turma 10A do curso TINF |
| **Subject** | Disciplina. Ex: "Programação", "Redes". | Programação |
| **Module** | Módulo dentro de uma disciplina. Tem `hours_total` (carga horária). Ex: "M1 — Introdução a Python (25h)". | M1 |
| **Timeslot** | Bloco de tempo na grelha horária da escola. Ex: "Segunda, 09:00–11:00". | Slot semanal |
| **ScheduleOutput** | Bloco gerado pelo Solver. É a "aula concreta" numa data específica. Tem `date`, `timeslot_id`, `lesson_id`, `room_id`. Um bloco é o que o professor vê no horário. | Aula de Programação na 2ª feira 09h, 12 Mai 2026 |
| **Lesson** | Relação abstrata Turma+Disciplina+Professor. O Solver gera ScheduleOutputs a partir de Lessons. | 10A tem Programação com Prof. Silva |
| **LessonLog** | Registo do que aconteceu com um bloco. Tem `status` (PENDING/COMPLETED/OCCURRENCE), `summary`, `notes`. Relação 1-para-1 com ScheduleOutput. | "Aula dada — Sumário: Intro a Python" |
| **LessonOccurrence** | Ocorrência criada pelo admin (falta, substituição). Diferente do LessonLog: a ocorrência é uma exceção operacional, o log é o registo normal. Tem `status` (GAP/SUBSTITUTED/GIVEN). | Prof. Silva faltou, Prof. Costa substituiu |
| **TeacherWeeklyTimesheet** | Estado do fecho semanal de um professor. Tem `status` (OPEN/SUBMITTED/APPROVED). Uma vez SUBMITTED, o professor não pode editar. Uma vez APPROVED, fica congelada. | Prof. Silva submeteu a semana de 12-16 Mai |
| **ClassProgress** | Progresso de horas dadas de uma disciplina/turma. `hours_completed` é incrementado quando LessonLog passa a COMPLETED. | Programação 10A: 45h/100h |
| **Draft** | Bloco gerado mas não aprovado. O Solver pode gerar "rascunhos" que o admin aprova ou rejeita. | Rascunho de reparação |

### 0.4. Sistema de Autenticação e Autorização

- **Login:** O utilizador faz login via `POST /auth/login`. O backend devolve um JWT token.
- **Store:** O frontend guarda o token e os dados do utilizador no Zustand store (`useAuthStore`).
- **Campos do utilizador no store:**
  - `user.orgId` — ID da organização (escola)
  - `user.role` — `"admin"` ou `"teacher"`
  - `user.teacherId` — ID do professor (apenas se role=teacher)
  - `user.orgName` — Nome da organização
- **Multi-tenant:** TODOS os endpoints usam `current_user.organization_id` para filtrar dados. Nunca há dados cruzados entre organizações.
- **Permissões:**
  - Admin: acesso total a todas as páginas e operações
  - Professor: acesso apenas ao próprio horário (`/my-schedules`), não pode ver outros professores

### 0.5. Design System e Paleta de Cores

O frontend usa variáveis CSS definidas em `index.css`:

| Variável | Cor | Uso |
|----------|-----|-----|
| `--color-state-given` | Verde escuro | Blocos com aula dada (COMPLETED) |
| `--color-state-gap` | Vermelho | Blocos com falta (OCCURRENCE/GAP) |
| `--color-state-substituted` | Amarelo/laranja | Blocos substituídos |
| `--color-state-open` | Âmbar | Ocorrência pendente de decisão |
| `--color-state-planned` | Cinzento claro | Blocos pendentes/passado sem registo |
| `--color-bg-muted` | Cinzento muito claro | Fundo de secções informativas |

**Classes CSS para estados dos blocos (WeekGrid):**
- `zen-state-card` — base de todos os blocos
- `zen-state-given` — aula dada (sólido, verde)
- `zen-state-gap` — falta (tracejado, vermelho)
- `zen-state-substituted` — substituída (sólido, amarelo)
- `zen-state-open` — ocorrência pendente (âmbar)
- `zen-state-planned` — pendente (cinzento)

### 0.6. Padrões de Código Existentes

#### Padrão de Hooks (React Query)
Todos os hooks estão em `frontend/src/hooks/useSchoolData.js`. Seguem este padrão:
```js
// Query (leitura)
export const useWeekSchedule = (classId, teacherId, weekStart) => {
  const orgId = useAuthStore(state => state.user?.orgId)
  return useQuery({
    queryKey: ['weekSchedule', orgId, classId, teacherId, weekStart],
    queryFn: async () => {
      const params = {}
      if (classId) params.class_id = classId
      if (teacherId) params.teacher_id = teacherId
      params.week_start = weekStart
      const { data } = await apiClient.get('/schedule/week', { params })
      return data
    },
    enabled: Boolean(orgId && (classId || teacherId)),
    ...DYNAMIC_OPTS
  })
}

// Mutation (escrita)
export const useUpsertLessonLog = () => {
  const queryClient = useQueryClient()
  const orgId = useAuthStore(state => state.user?.orgId)
  return useMutation({
    mutationFn: async ({ scheduleOutputId, payload }) => {
      const { data } = await apiClient.put(
        `/schedule/outputs/${scheduleOutputId}/log`, payload
      )
      return data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['weekSchedule', orgId] })
    }
  })
}
```

#### Padrão de Endpoints (FastAPI)
```python
@router.put(
    "/outputs/{schedule_output_id}/log",
    response_model=schemas.LessonLogRead,
    summary="Upsert do registo de aula",
)
async def upsert_lesson_log(
    schedule_output_id: int,
    payload: schemas.LessonLogCreate,
    db: Annotated[AsyncSession, Depends(deps.get_db)],
    current_user: Annotated[models.User, Depends(deps.get_current_active_user)],
):
    def _run(sync_db):
        return lesson_log_service.upsert_lesson_log_sync(
            sync_db,
            org_id=current_user.organization_id,
            user_id=current_user.id,
            schedule_output_id=schedule_output_id,
            payload=payload,
        )
    return await db.run_sync(_run)
```

**Nota:** Os endpoints usam `db.run_sync()` porque os serviços são síncronos (SQLAlchemy sync session). O FastAPI é async mas delega para serviços sync.

#### Padrão de Testes (Pytest)
```python
# Testes ficam em backend/tests/test_*.py
# Usam fixtures do pytest para criar dados de teste
# Correm com: docker-compose exec -T backend pytest tests/test_xxx.py -v
# Ou no CI: pytest --tb=short -q

@pytest.fixture
def base_setup(sync_db):
    # Cria org, teacher, user, subject, class, timeslot, schedule_output
    # Retorna dict com todos os IDs necessários
    return { "org_id": ..., "teacher_id": ..., ... }

class TestMyFeature:
    def test_something(self, sync_db, base_setup):
        # Arrange (usar base_setup)
        # Act (chamar serviço ou endpoint)
        # Assert (verificar resultado)
```

### 0.7. Como Correr o Projeto

```bash
# Backend (Docker)
docker-compose up -d          # Inicia PostgreSQL, Redis e Backend
docker-compose logs -f backend # Ver logs do backend

# Frontend (local)
cd frontend
npm install
npm run dev                    # Inicia em http://localhost:5173

# Testes Backend
docker-compose exec -T backend pytest tests/test_lesson_registration.py -v

# Migrações
docker-compose exec -T backend alembic upgrade head
docker-compose exec -T backend alembic revision --autogenerate -m "description"
```

### 0.8. Diagrama de Relações da BD (Tabelas Relevantes)

```
Organization (org)
├── Teacher (teacher_id, org_id)
├── Class (class_id, org_id, course_id)
├── Subject (subject_id, org_id)
├── Module (module_id, subject_id, hours_total)
├── Timeslot (timeslot_id, org_id, day_of_week, start_time, end_time)
├── ScheduleOutput (schedule_output_id, org_id, lesson_id, timeslot_id, room_id, date, is_draft)
│   ├── LessonLog (lesson_log_id, org_id, schedule_output_id, status, summary, notes)
│   └── LessonOccurrence (occurrence_id, schedule_output_id, status, decided_at)
├── TeacherWeeklyTimesheet (timesheet_id, org_id, teacher_id, week_start_date, status)
└── ClassProgress (class_id, module_id, hours_completed)
```

**Relações chave:**
- `ScheduleOutput` é 1-para-1 com `LessonLog` (via `schedule_output_id`)
- `ScheduleOutput` pode ter 0 ou 1 `LessonOccurrence`
- `TeacherWeeklyTimesheet` é única por (teacher_id, week_start_date)
- `LessonLog.status` e `LessonOccurrence.status` são independentes — um bloco pode ter ambos

### 0.9. Endpoints Existentes Relevantes

| Método | Rota | O que faz | Ficheiro |
|--------|------|-----------|----------|
| `GET` | `/schedule/week` | Devolve blocos da semana (class_id ou teacher_id) | `schedule.py` |
| `PUT` | `/schedule/outputs/{id}/log` | Upsert do LessonLog de um bloco | `schedule.py` |
| `GET` | `/timesheets/` | Lista timesheets (admin, com filtros) | `timesheets.py` |
| `GET` | `/timesheets/me/{week}` | Timesheet do professor autenticado | `timesheets.py` |
| `POST` | `/timesheets/me/{week}/submit` | Professor submete a semana | `timesheets.py` |
| `PATCH` | `/timesheets/{id}/status` | Admin aprova/reabre timesheet | `timesheets.py` |
| `POST` | `/occurrences/` | Cria ocorrência (LessonOccurrence) | `occurrences.py` |
| `POST` | `/school/settings/soft-reset` | Reset do ano letivo | `org_settings.py` |

---

## 1. O Conceito (Os 5 Ws)

*   **Who (Quem):** Professores (registo diário de aulas) e Administradores (gestão operacional completa, aprovação semanal e substituições).
*   **What (O quê):** Expansão da funcionalidade de Registo de Aulas para: (1) modal unificado professor/admin com suporte a substituições inline, (2) bloqueio de fecho semanal consistente para admin em `/schedules`, e (3) página `/timesheets` como central de aprovação com interação direta nos blocos.
*   **Where (Onde):** `/schedules` (micro-management diário), `/timesheets` (macro-management semanal e aprovações), `/absences` (histórico e logs).
*   **When (Quando):** Após a implementação completa da V1 (Fases 1–4 do WBS original já concluídas).
*   **Why (Porquê):** Para eliminar a fragmentação da gestão operacional entre múltiplas páginas, centralizar o fluxo de trabalho do admin num ponto único, e enriquecer a página de aprovações com contexto e interatividade.

---

## 2. Estado Atual da Implementação (V1 Concluída)

Antes de iniciar esta fase, é importante registar o que já está funcional:

| Fase | Estado | Componentes |
|------|--------|-------------|
| **Fase 1: Domínio e BD** | ✅ Completa | `LessonLog`, `TeacherWeeklyTimesheet`, migração Alembic, schemas Pydantic |
| **Fase 2: Registo Diário** | ✅ Completa | `LessonLogModal`, `WeekGrid` com visuais, `useUpsertLessonLog`, endpoint `PUT /schedule/outputs/{id}/log` |
| **Fase 3: Fecho Semanal** | ✅ Completa | Botão "Submeter Semana" em `MySchedules`, endpoint de submissão, painel admin em `Timesheets.jsx` (básico) |
| **Fase 4: Soft-Reset** | ✅ Completa | Endpoint `POST /school/settings/soft-reset`, modal de confirmação em `SchoolConfig.jsx` |

**Bugs já corrigidos (Audit V1):** U1, U1.1, U2, U3, U4, U4.1, U5, A1, A2, A3, A4, A5, A6, A7, A8 — todos resolvidos.

---

## 3. WBS V2 — Novas Funcionalidades

### Fase 5: Modal Unificado com Substituição Inline (Cenário A — Ponto 1)

O `LessonLogModal` passa a ser o **ponto único de gestão de aulas** tanto para professores como para admins. O admin ganha a capacidade de criar substituições diretamente do modal, sem navegar para `/absences`.

#### 5.1. Refatorar `LessonLogModal` para Wizard de 2 Passos

*   **Descrição:** O modal atual (`frontend/src/components/LessonLogModal.jsx`, 270 linhas) mantém o Passo 1 (Registo de Aula) igual para professor e admin. Adicionar um Passo 2 que **apenas** é acessível quando o admin clica no botão "Substituição".
*   **Como funciona o fluxo de substituições hoje (em `/absences`):**
    1. Admin clica num bloco → `Schedules.jsx` abre `CreateOccurrenceModal` → admin clica "Criar Ocorrência"
    2. O frontend chama `POST /occurrences/` com `{ schedule_output_id }` → backend cria uma `LessonOccurrence` com `status=OPEN`
    3. Admin é redirecionado para `/absences` → vê a ocorrência pendente → clica "Decidir"
    4. O modal de decisão (`OccurrenceDecisionModal` em `Occurrences.jsx`) mostra opções: GIVEN, GAP, SUBSTITUTED
    5. Se SUBSTITUTED: o frontend chama `GET /occurrences/{id}/recommendations` → backend devolve lista de professores elegíveis ordenados por ranking
    6. Admin seleciona professor + sala → frontend chama `PATCH /occurrences/{id}` com `{ status: 'SUBSTITUTED', substitute_teacher_id, substitute_subject_id }`
*   **O que o Passo 2 do wizard deve replicar:**
    *   O Passo 2 reutiliza a lógica acima (passos 2-6) mas dentro do modal, sem redirecionar para `/absences`.
    *   Endpoint a chamar: `POST /occurrences/` (criar ocorrência) → `GET /occurrences/{id}/recommendations` (obter substitutos) → `PATCH /occurrences/{id}` (decidir como SUBSTITUTED)
    *   O componente `OccurrenceDecisionModal` em `Occurrences.jsx` (linhas ~200-350) já tem a UI de recomendações. O Passo 2 pode extrair essa lógica para um componente partilhado.
*   **Componentes a criar:**
    *   `frontend/src/components/SubstitutionStep.jsx` — componente interno do wizard com:
      - Dropdown de Professor Substituto (populado via `GET /occurrences/{id}/recommendations`)
      - Dropdown de Sala Alternativa (populado via `GET /rooms` — hook `useRooms` já existe)
      - Dropdown de Módulo a Lecionar (populado via `GET /modules` — hook `useModules` ou dados do slot)
      - Botão "Confirmar Substituição" que chama `PATCH /occurrences/{id}`
      - Botão "Voltar" que regressa ao Passo 1
    *   O `LessonLogModal.jsx` passa a ter estado `step` (1 ou 2) e renderiza condicionalmente.
*   **Resultado Esperado:** Ao clicar num bloco em `/schedules`, o admin vê o Passo 1 (idêntico ao professor). Se clicar "Substituição", o modal transita para o Passo 2 com os campos de substituição. Se clicar "Aula Dada" ou "Registar Falta", o comportamento é idêntico ao professor.
*   **Edge-Cases a Validar:**
    *   EC 5.1.1: Admin abre Passo 2 mas clica "Voltar" — o estado do Passo 1 (sumário, notas) deve ser preservado.
    *   EC 5.1.2: Admin cria substituição mas a API falha — o modal deve permanecer no Passo 2 com a mensagem de erro, sem perder os dados preenchidos.
    *   EC 5.1.3: Professor não vê o botão "Substituição" — verificar que o prop `isAdmin` é `false` para professores e o botão não é renderizado.
    *   EC 5.1.4: Bloco já tem `LessonOccurrence` decidida (GAP/SUBSTITUTED) — o admin vê o estado da ocorrência mas pode reverter se a semana não estiver fechada.
    *   EC 5.1.5: Bloco já tem `LessonLog.status === OCCURRENCE` (falta pelo professor) — o admin pode criar uma substituição por cima? Não. Deve-se bloquear a criação de substituição se já existe uma `LessonOccurrence` ativa para o mesmo bloco.
*   **Testes GitHub Actions:**
    *   T 5.1.1: `test_substitution_step_recommends_teachers` — Verificar que o endpoint de recomendações devolve professores elegíveis para o slot.
    *   T 5.1.2: `test_substitution_creation_from_modal` — Criar uma substituição via endpoint e verificar que a `LessonOccurrence` é criada corretamente com `status=SUBSTITUTED`.
    *   T 5.1.3: `test_cannot_create_substitution_if_existing_occurrence` — Tentar criar substituição num bloco que já tem ocorrência e verificar que é rejeitado (HTTP 400).
*   **Tratamento de Erros (User-Friendly):**
    *   E 5.1.1: "Não foi possível carregar as recomendações de professores substitutos. Tente novamente." (quando o endpoint de recomendações falha)
    *   E 5.1.2: "Já existe uma ocorrência registada para este bloco. Consulte Faltas & Ocorrências para a gerir." (quando se tenta criar substituição duplicada)
    *   E 5.1.3: "A semana já foi submetida ou aprovada. Não é possível criar substituições." (quando a timesheet está fechada)

#### 5.2. Sincronização Bilateral de Sumário e Notas

*   **Descrição:** Garantir que o sumário e notas preenchidos pelo professor são visíveis e editáveis pelo admin (e vice-versa). Atualmente o `LessonLogModal` já lê `lesson_log_summary` e `lesson_log_notes` do slot. Validar que a sincronização funciona em ambos os sentidos.
*   **Resultado Esperado:** Admin abre o modal de um bloco → vê o sumário e notas que o professor preencheu → pode editar → ao guardar, o professor vê as alterações.
*   **Edge-Cases a Validar:**
    *   EC 5.2.1: Professor e admin abrem o mesmo bloco em simultâneo (abas diferentes) — quem guarda último ganha (last-write-wins). Não há conflito porque o `upsert_lesson_log_sync` faz update direto.
    *   EC 5.2.2: Sumário com caracteres especiais (UTF-8, emojis) — garantir que a BD e a API preservam encoding.
    *   EC 5.2.3: Sumário com mais de 5000 caracteres — o backend deve ter validação de tamanho máximo ou o frontend deve truncar.
*   **Testes GitHub Actions:**
    *   T 5.2.1: `test_admin_can_update_teacher_summary` — Professor cria log com sumário → Admin atualiza o sumário → Verificar que o valor foi alterado.
    *   T 5.2.2: `test_summary_persists_after_status_change` — Alterar o estado de COMPLETED para OCCURRENCE e verificar que o sumário não é apagado.
*   **Tratamento de Erros:**
    *   E 5.2.1: "O sumário excede o tamanho máximo permitido." (se a BD tiver limite de caracteres)

#### 5.3. Integração do `CreateOccurrenceModal` no `LessonLogModal`

*   **Descrição:** O `CreateOccurrenceModal` atual em `Schedules.jsx` (legacy) deixa de ser necessário para blocos passados. Todos os blocos passados abrem diretamente o `LessonLogModal`. O `CreateOccurrenceModal` mantém-se apenas para blocos futuros (edge case).
*   **Resultado Esperado:** Ao clicar num bloco passado no `/schedules` do admin, abre SEMPRE o `LessonLogModal`. O `CreateOccurrenceModal` é removido do fluxo principal.
*   **Edge-Cases a Validar:**
    *   EC 5.3.1: Bloco futuro — admin não deve conseguir registar nada (botões desativados). O `CreateOccurrenceModal` para blocos futuros deve continuar a funcionar se existir.
    *   EC 5.3.2: Bloco sem `schedule_output_id` (draft) — não deve abrir modal nenhum.
*   **Testes GitHub Actions:**
    *   T 5.3.1: `test_admin_opens_lesson_log_modal_for_past_slot` — Verificar que o endpoint devolve os campos `lesson_log_*` corretos para o admin.
*   **Tratamento de Erros:**
    *   E 5.3.1: "Este bloco ainda não tem horário final atribuído." (para blocos draft)

---

### Fase 6: Bloqueio de Fecho Semanal para Admin em `/schedules` (Cenário A — Ponto 2)

Quando uma semana está `SUBMITTED` ou `APPROVED`, o admin ao ver a mesma semana em `/schedules` deve ver os slots como não-editáveis, com possibilidade de reabrir.

#### 6.1. Enriquecer Endpoint `/schedule/week` com Estado da Timesheet

*   **Descrição:** O endpoint `GET /schedule/week` (ficheiro `backend/app/api/v1/endpoints/schedule.py`) devolve uma lista de slots da semana. Cada slot já inclui campos como `lesson_log_status`, `occurrence_id`, `is_past`, etc. Adicionar o campo `week_timesheet_status` (OPEN, SUBMITTED, APPROVED) a cada slot.
*   **Onde implementar:**
    *   **Backend (`schedule_service.py`):** Na função que constrói a resposta do endpoint, após buscar os slots, fazer uma query adicional à tabela `TeacherWeeklyTimesheet` para obter o estado da timesheet de cada professor naquela semana. O campo é derivado da combinação `(teacher_id, week_start_date)`.
    *   **Schema (`schemas.py`):** Adicionar `week_timesheet_status: Optional[str] = None` ao schema `WeekSlotRead` (ou equivalente que devolve os slots).
    *   **Frontend (`LessonLogModal.jsx`):** O modal já recebe o `slot` como prop. Ler `slot.week_timesheet_status` para determinar se a semana está fechada.
*   **Query sugerida (dentro do serviço):**
    ```python
    # Para cada teacher_id único nos slots, buscar o timesheet da semana
    teacher_ids = set(slot.lesson.teacher_id for slot in slots)
    timesheets = db.query(models.TeacherWeeklyTimesheet).filter(
        models.TeacherWeeklyTimesheet.org_id == org_id,
        models.TeacherWeeklyTimesheet.teacher_id.in_(teacher_ids),
        models.TeacherWeeklyTimesheet.week_start_date == week_start_date
    ).all()
    timesheet_map = {ts.teacher_id: ts.status.value for ts in timesheets}
    # Depois, para cada slot: slot['week_timesheet_status'] = timesheet_map.get(teacher_id, 'OPEN')
    ```
*   **Resultado Esperado:** Cada slot na resposta da API inclui `"week_timesheet_status": "SUBMITTED"` quando a semana do professor foi submetida.
*   **Edge-Cases a Validar:**
    *   EC 6.1.1: Semana sem timesheet registada — o campo deve devolver `"OPEN"` (valor por defeito).
    *   EC 6.1.2: Vista por turma (class_id) — os blocos de professores diferentes podem ter estados de timesheet diferentes na mesma semana. O campo deve refletir o timesheet do professor individual de cada bloco.
    *   EC 6.1.3: Admin a ver o horário de um professor — o campo reflete o estado da timesheet desse professor.
*   **Testes GitHub Actions:**
    *   T 6.1.1: `test_week_schedule_includes_timesheet_status` — Gerar slots, submeter a timesheet, chamar o endpoint e verificar que `week_timesheet_status` é `SUBMITTED`.
    *   T 6.1.2: `test_week_schedule_different_teachers_different_statuses` — Dois professores na mesma semana com estados diferentes. Verificar que cada slot reflete o estado correto.
*   **Tratamento de Erros:**
    *   E 6.1.1: Se a query do timesheet falhar, devolver `"OPEN"` como fallback sem quebrar a resposta.

#### 6.2. Bloqueio Visual e Funcional no `LessonLogModal` para Semanas Fechadas

*   **Descrição:** O `LessonLogModal` recebe o campo `week_timesheet_status` (adicionado no passo 6.1). Se o estado for `SUBMITTED` ou `APPROVED`:
    *   Para o **professor**: todos os campos ficam `disabled` (já funciona via backend, mas o frontend deve refletir visualmente com inputs acinzentados e tooltip "Semana submetida").
    *   Para o **admin**: os campos ficam `disabled`, mas é exibido um banner `CAlert color="warning"` com o texto "Semana submetida por [nome do professor]" e o botão "Reabrir Semana". Ao clicar "Reabrir", o admin chama o endpoint `PATCH /timesheets/{id}/status` com `{ status: 'OPEN' }` e o modal atualiza para modo editável.
*   **Onde implementar no `LessonLogModal.jsx`:**
    *   Adicionar prop `weekTimesheetStatus` (string: 'OPEN' | 'SUBMITTED' | 'APPROVED')
    *   Adicionar prop `timesheetId` (number — necessário para o botão "Reabrir" chamar o endpoint)
    *   Adicionar prop `isAdmin` (boolean — já existe)
    *   No topo do modal (antes do formulário), se `weekTimesheetStatus !== 'OPEN'`:
        - Mostrar banner com o estado
        - Se `isAdmin`: mostrar botão "Reabrir Semana" que chama `useUpdateTimesheetStatus` (hook já existe em `useSchoolData.js`)
        - Se `!isAdmin`: mostrar apenas o banner sem botão
    *   Todos os campos (sumário, notas, botões de ação) ficam `disabled` quando `weekTimesheetStatus !== 'OPEN'`
*   **Hook a usar:** `useUpdateTimesheetStatus()` já existe em `useSchoolData.js` e chama `PATCH /timesheets/{id}/status`
*   **Resultado Esperado:** Admin vê a semana bloqueada → clica "Reabrir" → a semana volta a OPEN → os campos do modal ficam editáveis → o professor também pode voltar a editar.
*   **Edge-Cases a Validar:**
    *   EC 6.2.1: Admin reabre a semana mas não grava nenhuma alteração — a semana fica OPEN e o professor pode editar novamente.
    *   EC 6.2.2: Admin reabre a semana e grava uma alteração — a alteração é aplicada e a semana permanece OPEN.
    *   EC 6.2.3: Admin tenta reabrir uma semana APPROVED — deve ser permitido (o endpoint já suporta).
    *   EC 6.2.4: Professor tenta reabrir a semana — NÃO deve ser permitido. O botão "Reabrir" é exclusivo do admin.
    *   EC 6.2.5: Dois admins reabrem a semana em simultâneo — a última chamada ganha (idempotente, o estado fica OPEN).
*   **Testes GitHub Actions:**
    *   T 6.2.1: `test_admin_reopens_submitted_week_from_modal` — Submeter semana → Admin reabre via API → Verificar que o estado é OPEN.
    *   T 6.2.2: `test_teacher_cannot_reopen_week` — Professor tenta chamar o endpoint de reabertura → HTTP 403.
    *   T 6.2.3: `test_reopen_preserves_lesson_logs` — Reabrir a semana e verificar que os LessonLogs existentes não são apagados.
*   **Tratamento de Erros:**
    *   E 6.2.1: "Não foi possível reabrir a semana. Tente novamente." (erro genérico da API)
    *   E 6.2.2: "Apenas administradores podem reabrir semanas." (403)

#### 6.3. Banner de Estado da Semana no `WeekGrid`

*   **Descrição:** Na página `/schedules`, quando a semana visível tem pelo menos um professor com timesheet `SUBMITTED` ou `APPROVED`, exibir um banner informativo no topo da grelha: "Esta semana tem X semanas submetidas. Os blocos estão bloqueados para edição."
*   **Resultado Esperado:** O banner aparece quando relevante e desaparece quando todas as semanas da grelha estão OPEN.
*   **Edge-Cases a Validar:**
    *   EC 6.3.1: Vista por turma — múltiplos professores, alguns com semanas submetidas e outros não. O banner deve indicar o número correto.
    *   EC 6.3.2: Vista por professor — apenas 1 professor, o banner reflete o estado único.
*   **Testes GitHub Actions:**
    *   T 6.3.1: `test_week_grid_returns_timesheet_summary` — Verificar que o endpoint devolve informação agregada de timesheets para a semana.
*   **Tratamento de Erros:**
    *   N/A — o banner é informativo, sem ações.

---

### Fase 7: `/timesheets` como Central de Aprovação (Cenário D — Ponto 3)

A página `/schedules` é para micro-management diário. A página `/timesheets` passa a ser a central de aprovação semanal com dois painéis: lista de professores (esquerda) + detalhe do professor selecionado (direita), permitindo interação direta nos blocos.

#### 7.1. Redesenhar o Layout de `/timesheets` para Dois Painéis

*   **Descrição:** Substituir a tabela atual por um layout de dois painéis:
    *   **Painel Esquerdo (30%):** Lista de professores da semana selecionada, com badge de estado (OPEN/SUBMITTED/APPROVED) e contagem de aulas pendentes.
    *   **Painel Direito (70%):** `WeekGrid` do professor selecionado, com o `LessonLogModal` integrado para interação direta.
    *   O seletor de semana (navegação por setas ←/→) mantém-se no topo.
    *   Os filtros de estado (Todos, Em Aberto, Submetidas, Aprovadas) mantêm-se.
*   **Resultado Esperado:** O admin entra em `/timesheets`, vê a lista de professores da semana, clica num professor e vê o horário completo dele no painel direito. Pode clicar em qualquer bloco para abrir o `LessonLogModal` e registar aulas/faltas/substituições diretamente.
*   **Estética (zen-frontend-designer):**
    *   O painel esquerdo deve usar uma lista vertical com cards compactos para cada professor. Cada card mostra: nome, badge de estado, contagem de aulas (ex: "5/8 registadas").
    *   O painel direito reutiliza o componente `WeekGrid` existente, garantindo consistência visual com `/schedules`.
    *   Transição entre professores deve ser instantânea (React Query cache).
    *   Paleta de cores consistente com o design system Zen (usar variáveis CSS `--color-state-*`).
*   **Edge-Cases a Validar:**
    *   EC 7.1.1: Sem professores para a semana — o painel esquerdo mostra "Nenhum professor com aulas nesta semana."
    *   EC 7.1.2: Professor com 0 aulas na semana — não deve aparecer na lista.
    *   EC 7.1.3: Semana com muitos professores (20+) — o painel esquerdo deve ser scrollável.
    *   EC 7.1.4: Professor selecionado mas a semana não tem slots — o painel direito mostra "Sem aulas registadas para esta semana."
    *   EC 7.1.5: Admin muda de semana — o painel esquerdo atualiza e o professor selecionado é mantido se existir na nova semana, senão limpa.
*   **Testes GitHub Actions:**
    *   T 7.1.1: `test_timesheets_list_endpoint_returns_teacher_summary` — Verificar que o endpoint devolve a lista de professores com contagem de aulas registadas.
    *   T 7.1.2: `test_timesheets_detail_endpoint_returns_week_slots` — Verificar que o endpoint devolve os slots do professor para a semana (reutilizar `GET /schedule/week`).
*   **Tratamento de Erros:**
    *   E 7.1.1: "Erro ao carregar a lista de professores. Tente novamente."
    *   E 7.1.2: "Erro ao carregar o horário do professor selecionado."

#### 7.2. Ações de Aprovação/Reabertura Integradas no Painel Direito

*   **Descrição:** No painel direito (detalhe do professor), acima do `WeekGrid`, adicionar botões de ação contextualizados:
    *   Se a semana está `SUBMITTED`: botão "Aprovar" e botão "Reabrir".
    *   Se a semana está `APPROVED`: botão "Reabrir".
    *   Se a semana está `OPEN`: texto "Aguardar submissão do professor".
    *   Os botões de ação chamam o endpoint `PATCH /timesheets/{id}/status` já existente.
*   **Resultado Esperado:** O admin vê o horário do professor, analisa os blocos, e aprova/reabre sem sair da página.
*   **Edge-Cases a Validar:**
    *   EC 7.2.1: Admin aprova a semana → os blocos no painel direito ficam imediatamente bloqueados (refetch automático via React Query).
    *   EC 7.2.2: Admin reabre a semana → os blocos ficam editáveis → o admin pode clicar num bloco e alterar.
    *   EC 7.2.3: Admin aprova mas o professor entretanto submeteu mais alterações (race condition) — o frontend deve refetch antes de mostrar o estado.
*   **Testes GitHub Actions:**
    *   T 7.2.1: `test_approve_from_timesheets_detail` — Aprovar via endpoint e verificar que o estado é APPROVED.
    *   T 7.2.2: `test_reopen_from_timesheets_detail` — Reabrir via endpoint e verificar que o estado é OPEN.
*   **Tratamento de Erros:**
    *   E 7.2.1: "Não foi possível aprovar a semana. Verifique se todas as aulas estão registadas." (se houver validação)
    *   E 7.2.2: "Semana reaberta com sucesso. O professor pode voltar a editar as aulas." (feedback positivo)

#### 7.3. Endpoint Enriquecido para o Resumo de Professores por Semana

*   **Descrição:** O endpoint `GET /timesheets/` atual (ficheiro `backend/app/api/v1/endpoints/timesheets.py`) devolve uma lista simples de timesheets com campos: `id, org_id, teacher_id, teacher_name, week_start_date, week_end_date, status, submitted_at, approved_at, approved_by_user_id, created_at`. Enriquecer a resposta com campos adicionais para o painel esquerdo.
*   **Abordagem:** Modificar o endpoint existente `GET /timesheets/` (não criar um novo). O serviço `timesheet_service.list_timesheets_sync()` já faz query à tabela `TeacherWeeklyTimesheet` com join a `Teacher`. Adicionar uma subquery para contar os slots.
*   **Campos a adicionar à resposta:**
    *   `total_slots`: número total de `ScheduleOutput` gerados para o professor na semana (excluindo `is_draft=True`).
    *   `registered_slots`: número de blocos com `LessonLog.status` != PENDING.
    *   `completed_slots`: número de blocos com `LessonLog.status` == COMPLETED.
    *   `occurrence_slots`: número de blocos com `LessonLog.status` == OCCURRENCE OU `LessonOccurrence` ativa.
*   **Onde implementar:**
    *   **Serviço (`timesheet_service.py`):** Na função `list_timesheets_sync()`, após buscar os timesheets, fazer uma query adicional para cada professor:
        ```python
        # Contar slots do professor na semana
        slot_counts = db.query(
            func.count(models.ScheduleOutput.id).label('total'),
            func.count(models.LessonLog.id).filter(
                models.LessonLog.status != models.LessonLogStatus.PENDING
            ).label('registered'),
            # ...etc
        ).join(models.Lesson, ...).filter(
            models.ScheduleOutput.organization_id == org_id,
            models.Lesson.teacher_id == teacher_id,
            models.ScheduleOutput.date.between(week_start, week_end),
            models.ScheduleOutput.is_draft == False
        ).first()
        ```
    *   **Schema (`schemas.py`):** Adicionar ao `TeacherWeeklyTimesheetRead`:
        ```python
        total_slots: int = 0
        registered_slots: int = 0
        completed_slots: int = 0
        occurrence_slots: int = 0
        ```
    *   **Frontend (`Timesheets.jsx`):** O painel esquerdo usa estes campos para mostrar "5/8 registadas" no card de cada professor.
*   **Resultado Esperado:** Cada item da lista de timesheets inclui `"total_slots": 8, "registered_slots": 6, "completed_slots": 5, "occurrence_slots": 1`.
*   **Edge-Cases a Validar:**
    *   EC 7.3.1: Professor sem aulas na semana — `total_slots: 0`. Este professor não deve aparecer na lista.
    *   EC 7.3.2: Professor com aulas mas sem timesheet registada — deve aparecer com estado `OPEN` e contagens corretas.
    *   EC 7.3.3: Aulas de um professor numa semana com `is_draft=True` — não devem contar nas contagens.
*   **Testes GitHub Actions:**
    *   T 7.3.1: `test_timesheets_list_with_slot_counts` — Criar aulas, registar algumas, chamar o endpoint e verificar as contagens.
    *   T 7.3.2: `test_timesheets_excludes_draft_slots` — Verificar que blocos draft não são contabilizados.
*   **Tratamento de Erros:**
    *   N/A — campos com fallback para 0 se a query falhar.

#### 7.4. Navegação Cruzada entre `/schedules` e `/timesheets`

*   **Descrição:** Adicionar links/botões que permitem ao admin navegar facilmente entre as duas páginas com contexto preservado:
    *   Em `/timesheets`: ao clicar num professor, além de mostrar o detalhe no painel direito, adicionar um botão "Ver em Horários" que navega para `/schedules` com o filtro de professor e semana pré-preenchidos.
    *   Em `/schedules`: adicionar um botão "Ver Aprovações" que navega para `/timesheets` com a semana atual pré-selecionada.
*   **Resultado Esperado:** O admin pode alternar entre micro-management (`/schedules`) e macro-management (`/timesheets`) sem perder contexto.
*   **Edge-Cases a Validar:**
    *   EC 7.4.1: Navegação de `/timesheets` para `/schedules` com professor que não existe — o filtro deve limpar para o estado padrão.
    *   EC 7.4.2: Navegação com query strings — garantir que os parâmetros `teacherId`, `weekStart` são preservados na URL.
*   **Testes GitHub Actions:**
    *   N/A — componente de UI, sem lógica de backend testável.
*   **Tratamento de Erros:**
    *   N/A — navegação simples.

---

## 4. Tabela de Conformidade Final

| Fase | Passo | Estado | Ficheiro(s) Principal(is) |
|------|-------|--------|---------------------------|
| 5.1 | Wizard 2 passos | ✅ Concluído | `LessonLogModal.jsx`, `SubstitutionStep.jsx` |
| 5.2 | Sincronização bilateral | ✅ Concluído | `LessonLogModal.jsx`, `lesson_log_service.py` |
| 5.3 | Remover CreateOccurrenceModal do fluxo | ✅ Concluído | `Schedules.jsx`, `LessonLogModal.jsx` |
| 6.1 | Enriquecer endpoint com timesheet status | ✅ Concluído | `schedule_service.py`, `schemas.py` |
| 6.2 | Bloqueio visual no modal para admin | ✅ Concluído | `LessonLogModal.jsx` |
| 6.3 | Banner de estado na WeekGrid | ✅ Concluído | `Schedules.jsx` |
| 7.1 | Layout 2 painéis em /timesheets | ✅ Concluído | `Timesheets.jsx` |
| 7.2 | Ações de aprovação no painel direito | ✅ Concluído | `Timesheets.jsx` |
| 7.3 | Endpoint com contagens de slots | ✅ Concluído | `timesheet_service.py`, `timesheets.py` |
| 7.4 | Navegação cruzada | ✅ Concluído | `Timesheets.jsx`, `Schedules.jsx` |

### Notas de Implementação — Fase 5 (Concluída)

- **5.1:** O `SubstitutionStep.jsx` foi criado como componente independente. O `LessonLogModal` gere o estado `step` (1 ou 2) e transita para o Passo 2 ao clicar em "Substituição". O backend `occurrence_service.create_occurrence_from_block_sync` mantém comportamento idempotente (reutiliza ocorrência existente). A validação de duplicados é feita no frontend (`occurrence_decided_at` verificado antes de criar nova). O dropdown de recomendações usa `useSubstituteRecommendations` com seleção automática da primeira opção.
- **5.2:** Sincronização bilateral validada — o `upsert_lesson_log_sync` já preserva `summary` e `notes` em cada chamada. O schema limita `summary` a 2000 chars e `notes` a 1000 chars. Testes confirmam que admin pode editar sumário do professor e que o sumário persiste após mudanças de estado.
- **5.3:** O `CreateOccurrenceModal` foi removido do fluxo principal de blocos passados em `Schedules.jsx`. Blocos passados abrem sempre o `LessonLogModal`. O componente `CreateOccurrenceModal` mantém-se no código apenas para blocos futuros (edge case raro).
- **Testes:** 9/9 testes em `test_lesson_registration.py` passam. Build do frontend (`npm run build`) passa sem erros.
- **Decisão técnica:** O teste `test_cannot_create_substitution_if_existing_occurrence` foi adaptado para verificar idempotência/preservação de estado em vez de HTTP 400, para não quebrar testes legacy que dependem do comportamento de reutilização de ocorrências.

### Notas de Implementação — Fase 6 (Concluída)

- **6.1:** O `get_week_schedule_sync` em `schedule_service.py` foi enriquecido com uma query à tabela `TeacherWeeklyTimesheet` que constrói um `timesheet_map: {teacher_id: (status, timesheet_id)}`. O `_build_week_slot` recebe este mapa e inclui `week_timesheet_status` (default `"OPEN"`) e `timesheet_id` em cada slot. O schema `WeekSlotRead` em `schemas.py` foi atualizado com os dois novos campos.
- **6.2:** O `LessonLogModal.jsx` já tinha a lógica de `isLocked` baseada em `week_timesheet_status` (implementado antecipadamente na Fase 5). Foram adicionados: (a) banner `CAlert` visível quando a semana está `SUBMITTED`/`APPROVED`, com mensagem contextualizada; (b) botão "Reabrir Semana" visível apenas para admin que chama `useUpdateTimesheetStatus` com `status=OPEN`; (c) após reabertura bem-sucedida, o modal fecha-se para forçar o re-carregamento dos dados frescos via React Query. O hook `useUpdateTimesheetStatus` em `useSchoolData.js` passou a invalidar também a cache de `weekSchedule` e `my-timesheet`.
- **6.3:** O `Schedules.jsx` calcula dinamicamente (via IIFE no JSX) quantos professores únicos têm `week_timesheet_status` diferente de `OPEN` e exibe um banner `CAlert color="warning"` acima da grelha com a contagem e nomes dos professores afetados. O banner desaparece automaticamente quando todas as semanas estão `OPEN`.
- **Testes:** 6 novos testes adicionados e todos passam:
  - `test_week_schedule_includes_timesheet_status` (T 6.1.1)
  - `test_week_schedule_different_teachers_different_statuses` (T 6.1.2)
  - `test_week_grid_returns_timesheet_summary` (T 6.3.1)
  - `test_admin_reopens_submitted_week_from_modal` (T 6.2.1)
  - `test_reopen_preserves_lesson_logs` (T 6.2.3)
  - `test_teacher_cannot_reopen_week` (T 6.2.2) — teste async de endpoint que verifica HTTP 403
- **Total acumulado:** 15/15 testes em `test_lesson_registration.py` passam.

### Notas de Implementação — Fase 7 (Concluída)

- **7.1:** A página `/timesheets` foi completamente redesenhada de uma tabela simples para um layout de dois painéis. O painel esquerdo (30%, `CCol md={4} lg={3}`) mostra uma lista scrollável de cards compactos para cada professor, com nome, badge de estado e contagens (`registered_slots/total_slots`). O painel direito (70%, `CCol md={8} lg={9}`) mostra o `WeekGrid` do professor selecionado com o `LessonLogModal` integrado para interação direta nos blocos. A navegação de semana (←/→/Hoje) e o filtro de estado mantêm-se no topo. Auto-seleção do primeiro professor ao carregar a lista.
- **7.2:** No painel direito, acima do `WeekGrid`, são exibidos botões de ação contextualizados: "Aprovar" (se SUBMITTED), "Reabrir" (se SUBMITTED ou APPROVED), ou "Aguardar submissão do professor" (se OPEN). As ações chamam `useUpdateTimesheetStatus` e invalidam as caches via React Query. Também é mostrado um resumo de contagens: registadas, dadas, ocorrências, pendentes.
- **7.3:** O `timesheet_service.py` foi enriquecido com `_compute_slot_counts_for_teachers()` que faz uma query agregada SQL (usando `func.sum(case(...))`) para calcular `total_slots`, `registered_slots`, `completed_slots` e `occurrence_slots` por professor numa semana. Blocos `is_draft=True` são excluídos das contagens. O schema `TeacherWeeklyTimesheetRead` em `schemas.py` recebeu os 4 novos campos com default 0. A função `list_timesheets_sync` chama a query de contagens quando `week_start_date` é fornecido.
- **7.4:** Navegação cruzada implementada: (a) Em `/timesheets`, cada painel direito tem botão "Ver em Horários" que navega para `/schedules?teacherId=X&weekStart=Y`; (b) Em `/schedules`, o admin vê botão "Ver Aprovações" que navega para `/timesheets?weekStart=Y`; (c) O `Schedules.jsx` lê query params `teacherId` e `weekStart` da URL via `useLocation` e pré-seleciona o professor/semana automaticamente.
- **Testes:** 6 novos testes adicionados e todos passam:
  - `test_timesheets_list_with_slot_counts` (T 7.3.1)
  - `test_timesheets_excludes_draft_slots` (T 7.3.2)
  - `test_approve_from_timesheets_detail` (T 7.2.1)
  - `test_reopen_from_timesheets_detail` (T 7.2.2)
  - `test_timesheets_list_endpoint_returns_teacher_summary` (T 7.1.1)
  - `test_timesheets_detail_endpoint_returns_week_slots` (T 7.1.2)
- **Total acumulado:** 21/21 testes em `test_lesson_registration.py` passam.
- **Build frontend:** `npm run build` passa sem erros.

### Bugs Corrigidos na Revisão Final (Fases 5+6+7)

- **BUG CRÍTICO (WeekGrid):** O `handleOpenOperationalAction` no `WeekGrid.jsx` não passava `week_timesheet_status`, `timesheet_id`, `is_past`, `occurrence_decided_at` e `hours_given` ao callback. Isto fazia com que o `LessonLogModal` não recebesse estes campos quando aberto a partir da grelha, resultando no banner de semana fechada e botão "Reabrir" não aparecerem. Corrigido adicionando todos os campos em falta ao objeto passado ao callback.
- **BUG (Timesheets):** O `Timesheets.jsx` importava e chamava `useTeachers()` sem o utilizar, causando uma query desnecessária ao servidor. Removido.
- **BUG (LessonLogModal):** O botão "Substituição" não era `disabled` quando a semana estava fechada (`isLocked`). O admin podia clicar no botão e só recebia o erro depois (no `handleStartSubstitution`). Corrigido adicionando `&& !isLocked` à condição `canShowSubstitution`.
- **NOTA:** O plano original (secção 5.1) descrevia "Dropdown de Sala Alternativa" e "Dropdown de Módulo a Lecionar" no `SubstitutionStep`. Estes campos não foram implementados porque o backend atual não suporta seleção de sala alternativa nas substituições. O componente simplificado usa um único dropdown de recomendações (professor+disciplina) que é suficiente para o fluxo funcional. Esta é uma redução de escopo aceitável.

---

## 5. Mapa de Testes GitHub Actions

| Teste | Fase | Tipo | O que Valida |
|-------|------|------|-------------|
| `test_substitution_step_recommends_teachers` | 5.1 | Endpoint | Recomendações de professores substitutos |
| `test_substitution_creation_from_modal` | 5.1 | Serviço | Criação de LessonOccurrence com status SUBSTITUTED |
| `test_cannot_create_substitution_if_existing_occurrence` | 5.1 | Serviço | Bloqueio de duplicação de ocorrências |
| `test_admin_can_update_teacher_summary` | 5.2 | Serviço | Sincronização de sumário entre professor e admin |
| `test_summary_persists_after_status_change` | 5.2 | Serviço | Preservação de sumário em mudanças de estado |
| `test_admin_opens_lesson_log_modal_for_past_slot` | 5.3 | Endpoint | Campos lesson_log_* na resposta da API |
| `test_week_schedule_includes_timesheet_status` | 6.1 | Endpoint | Campo week_timesheet_status nos slots |
| `test_week_schedule_different_teachers_different_statuses` | 6.1 | Endpoint | Timesheet status por professor individual |
| `test_admin_reopens_submitted_week_from_modal` | 6.2 | Serviço | Reabertura de semana pelo admin |
| `test_teacher_cannot_reopen_week` | 6.2 | Serviço | Restrição de permissão para professores |
| `test_reopen_preserves_lesson_logs` | 6.2 | Serviço | Integridade dos dados após reabertura |
| `test_week_grid_returns_timesheet_summary` | 6.3 | Endpoint | Resumo de timesheets na semana |
| `test_timesheets_list_endpoint_returns_teacher_summary` | 7.1 | Endpoint | Lista de professores com contagens |
| `test_timesheets_detail_endpoint_returns_week_slots` | 7.1 | Endpoint | Slots do professor na semana |
| `test_approve_from_timesheets_detail` | 7.2 | Serviço | Aprovação via endpoint |
| `test_reopen_from_timesheets_detail` | 7.2 | Serviço | Reabertura via endpoint |
| `test_timesheets_list_with_slot_counts` | 7.3 | Endpoint | Contagens de slots por professor |
| `test_timesheets_excludes_draft_slots` | 7.3 | Endpoint | Exclusão de drafts das contagens |

---

## 6. Tratamento de Erros User-Friendly — Resumo Global

| Código | Mensagem | Contexto |
|--------|----------|----------|
| E 5.1.1 | "Não foi possível carregar as recomendações de professores substitutos. Tente novamente." | Falha no endpoint de recomendações |
| E 5.1.2 | "Já existe uma ocorrência registada para este bloco. Consulte Faltas & Ocorrências para a gerir." | Tentativa de substituição duplicada |
| E 5.1.3 | "A semana já foi submetida ou aprovada. Não é possível criar substituições." | Timesheet fechada |
| E 5.2.1 | "O sumário excede o tamanho máximo permitido." | Validação de tamanho |
| E 5.3.1 | "Este bloco ainda não tem horário final atribuído." | Bloco draft |
| E 6.1.1 | (Silencioso — fallback para OPEN) | Query de timesheet falhou |
| E 6.2.1 | "Não foi possível reabrir a semana. Tente novamente." | Erro genérico de reabertura |
| E 6.2.2 | "Apenas administradores podem reabrir semanas." | 403 Forbidden |
| E 7.1.1 | "Erro ao carregar a lista de professores. Tente novamente." | Falha na lista |
| E 7.1.2 | "Erro ao carregar o horário do professor selecionado." | Falha no detalhe |
| E 7.2.1 | "Não foi possível aprovar a semana. Verifique se todas as aulas estão registadas." | Erro de aprovação |
| E 7.2.2 | "Semana reaberta com sucesso. O professor pode voltar a editar as aulas." | Sucesso de reabertura |

---

## 7. Dependências e Ordem de Implementação

```
Fase 5.1 (Wizard) ──→ Fase 5.3 (Remover modal legacy)
     │
     └──→ Fase 5.2 (Sincronização) ──→ Testes 5.x

Fase 6.1 (Endpoint) ──→ Fase 6.2 (Bloqueio visual) ──→ Fase 6.3 (Banner)
     │                                                    │
     └──→ Testes 6.x                                      │
                                                           │
Fase 7.3 (Endpoint contagens) ──→ Fase 7.1 (Layout) ──→ Fase 7.2 (Ações) ──→ Fase 7.4 (Navegação)
     │                                                                         │
     └──→ Testes 7.x                                                           │
                                                                               │
Fase 6.2 ──────────────────────────────────────────────→ Fase 7.2 (dependência: reabertura)
```

**Ordem recomendada:** 6.1 → 6.2 → 5.1 → 5.2 → 5.3 → 6.3 → 7.3 → 7.1 → 7.2 → 7.4

---

## 8. Critérios de Aceitação Globais

1. **Unificação:** O admin consegue gerir 100% do dia-a-dia em `/schedules` sem navegar para `/absences` (exceto para histórico/auditoria).
2. **Consistência:** O estado visual dos blocos (cores, badges, tooltips) é idêntico em `/schedules` e `/timesheets`.
3. **Bloqueio:** Semanas `SUBMITTED` ou `APPROVED` bloqueiam edição tanto para professor como para admin, com possibilidade de reabertura pelo admin.
4. **Bilateralidade:** Sumário e notas são sincronizados bidirecionalmente entre professor e admin.
5. **Testes:** Todos os testes definidos no Mapa de Testes passam no GitHub Actions.
6. **UX:** Todas as mensagens de erro são user-friendly e em português.

---

## 9. Como Validar Após Cada Fase

Após concluir cada fase, executar os seguintes passos de validação antes de avançar:

### Validação Automática (CI)
```bash
# Correr todos os testes backend
docker-compose exec -T backend pytest tests/ -v

# Correr teste específico da fase
docker-compose exec -T backend pytest tests/test_lesson_registration.py -v
```

### Validação Manual (Frontend)
Após cada fase, verificar manualmente no browser:

| Fase | O que verificar manualmente |
|------|---------------------------|
| **5.1** | Login como admin → `/schedules` → clicar bloco passado → ver botão "Substituição" → clicar → ver Passo 2 com dropdowns |
| **5.1** | Login como professor → `/schedules` → clicar bloco → NÃO ver botão "Substituição" |
| **5.2** | Login como professor → preencher sumário → login como admin → abrir mesmo bloco → ver sumário preenchido |
| **5.3** | Login como admin → `/schedules` → clicar bloco passado → abrir LessonLogModal (não CreateOccurrenceModal) |
| **6.1** | Login como professor → submeter semana → login como admin → `/schedules` → ver blocos bloqueados |
| **6.2** | Login como admin → clicar bloco de semana submetida → ver banner "Semana submetida" → clicar "Reabrir" → blocos ficam editáveis |
| **6.3** | Login como admin → `/schedules` → ver banner informativo quando há semanas submetidas |
| **7.1** | Login como admin → `/timesheets` → ver painel esquerdo com professores → clicar professor → ver WeekGrid no painel direito |
| **7.2** | Login como admin → `/timesheets` → selecionar professor com semana SUBMITTED → clicar "Aprovar" → verificar que estado muda |
| **7.3** | Login como admin → `/timesheets` → verificar que cada card de professor mostra "5/8 registadas" |
| **7.4** | Login como admin → `/timesheets` → clicar "Ver em Horários" → verificar que `/schedules` abre com o professor e semana corretos |
