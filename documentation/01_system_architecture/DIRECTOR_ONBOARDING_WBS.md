# WBS Técnico — Onboarding In-App do Diretor

> **Estado atual:** este documento mantém a especificação técnica e o plano de implementação históricos. O comportamento implementado e verificado está em [Director Onboarding](../00_getting_started/ONBOARDING.md). Em caso de divergência, use o código, os testes e a CI como fonte de verdade.

## 1. Finalidade

Este documento converte o contrato funcional do onboarding numa estrutura técnica de implementação.

O documento cobre apenas administradores e diretores.

Cada pacote produz código testado, migrável e observável.

### 1.1 Leitor previsto

Este documento destina-se a engenheiros backend, frontend, scheduler, QA e base de dados.

### 1.2 Pré-requisitos

Leia a arquitetura, o modelo de dados, a configuração escolar e os contratos de segurança referenciados na secção 15.

Inspecione sempre a implementação atual antes de alterar um fluxo.

## 2. Regras obrigatórias de engenharia

### 2.1 Clean Architecture aplicada ao repositório atual

Use as fronteiras existentes.

```text
React page -> feature model and hooks -> apiClient -> FastAPI router -> service -> SQLAlchemy model -> PostgreSQL
```

- Mantenha regras de domínio fora de componentes React e routers FastAPI.
- Mantenha transações e queries nos serviços backend.
- Mantenha validação de transporte nos schemas Pydantic.
- Mantenha máquinas de estados frontend em funções JavaScript puras.
- Não importe FastAPI nos serviços.
- Não importe `apiClient` nos modelos puros frontend.
- Não crie interfaces com uma única implementação.
- Não crie uma camada repository sobre SQLAlchemy.
- Não crie um novo bounded context para o onboarding.

### 2.2 Clean Code

- Use os termos `foundation`, `tutorial`, `readiness` e `prevalidation` nos identificadores técnicos.
- Elimine o termo funcional `founder` dos identificadores alterados.
- Use enums para estados persistidos.
- Use códigos estáveis para erros e problemas corrigíveis.
- Não use booleanos para representar estados com mais de duas possibilidades.
- Não capture `Exception` sem relançar ou registar o traceback.
- Não duplique validadores de datas, almoço ou grelha.
- Não faça `commit()` dentro de serviços.
- Não aceite `organization_id` enviado pelo cliente como autoridade.
- Inclua `organization_id` em cada query tenant-owned.
- Preserve RLS em todas as tabelas tenant-owned.

### 2.3 TDD obrigatório

Comece sempre num baseline `GREEN`.

Execute este ciclo em cada item da WBS:

1. Escreva ou atualize testes de caracterização do comportamento existente.
2. Execute-os e confirme que o baseline fica `GREEN`.
3. Escreva o teste mais pequeno do novo requisito.
4. Execute-o e confirme `RED` pelo motivo funcional esperado, nunca por fixture ou infraestrutura quebrada.
5. Implemente apenas o código necessário para obter `GREEN`.
6. Refatore nomes, duplicação e fronteiras mantendo `GREEN`.
7. Execute a suite local do pacote.
8. Remova um teste de caracterização temporário apenas depois de existir cobertura equivalente para o contrato novo.
9. Execute os gates completos antes do merge.

Não escreva testes que apenas confirmem mocks.

Teste regras puras sem base de dados.

Teste transações, RLS e concorrência com PostgreSQL real.

Teste routing e acessibilidade com Testing Library.

Teste o percurso crítico com Playwright.

### 2.4 Ponytail ultra

Use primeiro o código existente.

Reutilize estes elementos:

- `settings_service.upsert_settings` para o período letivo.
- `settings_service.save_and_regenerate_grid` para almoço e grelha.
- `timeslot_service.build_timeslot_signatures` para a matemática canónica.
- `SchedulerApprovalService` para a aprovação real.
- `preflight_service` para validações de geração.
- `GuidedFormShell` e `GuidedFormProgress` para o wizard.
- `timeslotsToGridFormData` e `toGridConfigurationPayload` para a grelha uniforme.
- `AvailabilityGrid`, `WeekGrid` e formulários puros aplicáveis.
- React `useReducer` para o tutorial.
- TanStack React Query para estado remoto.
- `localStorage` para progresso individual.
- `structlog` para falhas de integridade e telemetria operacional.

Não adicione estas peças:

- XState.
- Redux.
- Um SDK de analytics.
- Um segundo motor de preflight.
- Um novo worker ou job.
- Uma organização de demonstração.
- Dados tutoriais no backend.
- Uma API genérica de workflows.
- Feature flags sem requisito de rollout.
- Compatibilidade permanente com o onboarding antigo.

## 3. Decisões técnicas fechadas

### 3.1 Fontes de verdade

| Conceito | Fonte de verdade | Persistência |
| :--- | :--- | :--- |
| Fundação | `organization.foundation_status` | PostgreSQL |
| Rascunho da fundação | `organization_foundation_draft` | PostgreSQL |
| Primeiro horário real | `organization.first_real_schedule_approved_at` | PostgreSQL |
| Estado anual | `scheduler_school_year_state.school_year_publication_state` | PostgreSQL |
| Progresso tutorial | Chave versionada por utilizador e organização | `localStorage` |
| Bases da escola | Query coerente de prontidão | Calculado |
| Pré-validação | Resultado do pedido atual | Não persistido |
| Telemetria tutorial | `tutorial_telemetry_event` | PostgreSQL |

Nenhum metadado Clerk controla encaminhamento.

Nenhum estado tutorial controla prontidão organizacional.

### 3.2 Estados da fundação

Use o enum PostgreSQL `organizationfoundationstatus`.

Use o enum Python `OrganizationFoundationStatus`.

Os valores são `NOT_STARTED`, `IN_PROGRESS` e `COMPLETED`.

Transições permitidas:

```text
NOT_STARTED -> IN_PROGRESS -> COMPLETED
NOT_STARTED ----------------> COMPLETED
COMPLETED ------------------> COMPLETED
```

Rejeite todas as transições inversas.

### 3.3 Estados do tutorial

Use `NOT_STARTED`, `IN_PROGRESS`, `COMPLETED` e `SKIPPED`.

`SKIPPED` significa saída definitiva pelo comando “Saltar guia”.

Uma saída temporária mantém `IN_PROGRESS`.

“Repetir guia” substitui a chave local por um novo cenário `IN_PROGRESS`, no passo inicial e com novo `tutorialRunId`.

### 3.4 Estados da pré-validação

- `CHECKING` existe apenas no frontend durante o pedido.
- `BLOCKED` contém pelo menos um problema bloqueador.
- `READY_WITH_WARNINGS` contém avisos sem bloqueadores.
- `READY` não contém problemas.

O backend nunca persiste estes estados.

### 3.5 Semântica da disponibilidade

Use `PreferenceLevel.NEUTRAL.value` como valor neutro canónico.

Considere apenas `PreferenceLevel.IMPOSSIBLE.value` como indisponibilidade rígida.

Interprete uma linha ausente como neutra.

Em consultas, fingerprint, prontidão e preflight, devolva a anomalia de integridade sem escrever.

Repare linhas apenas numa fronteira de mutação explícita e na transação dessa mutação.

As fronteiras de reparação permitidas são criação de professor, regeneração da grelha e geração real.

Rotas `GET`, fingerprint, prontidão e prevalidation nunca invocam reparação.

## 4. Modelo de dados alvo

### 4.1 Alterações em `organization`

Adicione estes campos em `backend/app/models.py`:

| Campo | Tipo | Null | Regra |
| :--- | :--- | :--- | :--- |
| `foundation_status` | `OrganizationFoundationStatus` | Não | Default `NOT_STARTED` |
| `foundation_completed_at` | `DateTime(timezone=True)` | Sim | Obrigatório quando `COMPLETED`; imutável depois de preenchido |
| `first_real_schedule_approved_at` | `DateTime(timezone=True)` | Sim | Imutável depois de preenchido |

Adicione estas restrições:

- `COMPLETED` exige `foundation_completed_at`.
- `first_real_schedule_approved_at` exige `COMPLETED`.
- Um trigger impede `COMPLETED` de regressar.
- O trigger impede apagar ou alterar `foundation_completed_at` depois de preenchido.
- O trigger impede apagar ou alterar `first_real_schedule_approved_at` depois de preenchido.
- O trigger rejeita a primeira aprovação real quando a fundação não está `COMPLETED`.

O trigger usa o nome `trg_organization_foundation_monotonic`.

### 4.2 Tabela `organization_foundation_draft`

Crie uma linha máxima por organização.

| Campo | Tipo | Null | Regra |
| :--- | :--- | :--- | :--- |
| `organization_id` | `Integer` | Não | PK e FK para `organization` |
| `version` | `Integer` | Não | Começa em `1`; incrementa em cada gravação |
| `current_step` | `SmallInteger` | Não | Entre `1` e `9` |
| `payload_json` | `JSONB` | Não | Snapshot completo do rascunho |
| `updated_by_membership_id` | `Integer` | Não | FK tenant-scoped |
| `updated_at` | `DateTime(timezone=True)` | Não | Hora do servidor |

O `payload_json` aceita apenas estes campos:

```json
{
  "school_start_date": "2026-09-15",
  "school_hard_end_date": "2027-07-31",
  "repair_stability_window_days": 14,
  "days_of_week": [0, 1, 2, 3, 4],
  "opening_time": "08:00:00",
  "closing_time": "18:00:00",
  "slot_duration_minutes": 50,
  "break_duration_minutes": 10,
  "lunch_window_start": "12:30:00",
  "lunch_window_end": "14:00:00",
  "lunch_min_duration_minutes": 60
}
```

Durante o rascunho, cada valor pode ser `null`.

Na conclusão, nenhum valor pode ser `null`.

Não guarde a confirmação final no rascunho.

### 4.3 Tabela `tutorial_telemetry_event`

Crie uma tabela append-only.

| Campo | Tipo | Null | Regra |
| :--- | :--- | :--- | :--- |
| `id` | `BigInteger` | Não | PK |
| `organization_id` | `Integer` | Não | FK tenant-scoped |
| `tutorial_run_id` | `UUID` | Não | Uma execução aberta ou repetida do guia |
| `client_event_id` | `UUID` | Não | Idempotência dentro da organização |
| `tutorial_version` | `Integer` | Não | Maior que zero |
| `event_name` | `String(40)` | Não | Valor permitido |
| `chapter` | `SmallInteger` | Sim | `1` ou `2` |
| `step_id` | `String(80)` | Sim | Identificador técnico, nunca valor introduzido |
| `created_at` | `DateTime(timezone=True)` | Não | Hora do servidor |

Permita apenas estes eventos:

- `tutorial_opened`
- `chapter_started`
- `step_skipped`
- `tutorial_exited`
- `tutorial_completed`
- `tutorial_repeated`

Crie uma constraint `UNIQUE (organization_id, client_event_id)`.

Crie índices em `(organization_id, tutorial_run_id, created_at)` e `(organization_id, tutorial_version, event_name)`.

Não persista membership, utilizador, nome ou email neste evento.

Não crie endpoints de eliminação.

Revogue `UPDATE` e `DELETE` ao papel `cronos_app`.

Adicione um trigger `BEFORE UPDATE OR DELETE` que rejeita a operação, incluindo quando uma concessão futura é demasiado ampla.

### 4.4 RLS e integridade

Ative e force RLS nas duas tabelas novas.

Use `app_security.current_organization_id()` nas policies.

Conceda a `cronos_app` apenas as operações exigidas: leitura/escrita tenant-scoped do draft e `INSERT` tenant-scoped da telemetria.

Adicione ambas as tabelas aos testes de cobertura RLS.

Adicione os triggers monotónico e append-only ao `scripts.audit_triggers`.

Adicione constraints e policies ao `scripts.audit_database_integrity`.

## 5. Contratos HTTP alvo

### 5.1 Fundação

#### `GET /api/v1/foundation/status`

Permita qualquer membro ativo.

Resposta:

```json
{
  "foundation_status": "IN_PROGRESS",
  "organization_name": "Escola Exemplo",
  "first_real_schedule_approved_at": null,
  "active_school_year_state": "UNPUBLISHED"
}
```

#### `GET /api/v1/foundation/draft`

Permita apenas administradores.

Devolva `version: 0` quando não existe linha.

Inclua `current_step`, `data` e resumos read-only do calendário existente.

Não crie uma linha durante a leitura.

#### `PUT /api/v1/foundation/draft`

Permita apenas administradores.

Pedido:

```json
{
  "expected_version": 4,
  "current_step": 5,
  "data": {}
}
```

Trate `data` como snapshot completo.

Use `expected_version: 0` para a primeira gravação.

Bloqueie a linha da organização e o rascunho com `FOR UPDATE`.

Responda `409 FOUNDATION_DRAFT_VERSION_CONFLICT` numa versão obsoleta.

Inclua `current_version` no `detail` do conflito.

Não faça merge automático.

#### `POST /api/v1/foundation/complete`

Permita apenas administradores.

Pedido:

```json
{
  "expected_version": 8,
  "confirmed": true
}
```

Rejeite `confirmed: false` com `422`.

Resposta:

```json
{
  "foundation_status": "COMPLETED",
  "foundation_completed_at": "2026-08-21T10:00:00Z",
  "generated_timeslot_count": 50
}
```

Torne o comando idempotente depois de `COMPLETED`.

### 5.2 Bloqueio de domínio

Enquanto a fundação está incompleta, devolva:

```json
{
  "detail": {
    "code": "FOUNDATION_REQUIRED",
    "message": "Conclua a fundação da escola antes de usar esta operação."
  }
}
```

Use HTTP `409`.

Mantenha acessíveis apenas:

- Rotas públicas de autenticação.
- Health checks.
- Contacto público.
- Webhook Clerk.
- `POST /session/bootstrap`.
- `GET /members/me`.
- As quatro rotas da fundação.

Bloqueie todas as restantes rotas tenant-owned.

### 5.3 Prontidão

#### `GET /api/v1/readiness/bases`

Permita administradores depois da fundação.

Resposta:

```json
{
  "percentage": 71,
  "depth": 5,
  "complete": false,
  "fingerprint": null,
  "issues": [
    {
      "code": "ACTIVE_SCHOOL_YEAR_REQUIRED",
      "severity": "BLOCKER",
      "message": "Defina o ano letivo ativo antes de gerar.",
      "route": "/config"
    }
  ],
  "steps": [
    {
      "code": "COMPATIBLE_ROOM",
      "status": "COMPLETE",
      "route": "/rooms"
    }
  ]
}
```

Use percentagens `0`, `14`, `28`, `42`, `57`, `71`, `85` e `100`.

Calcule a percentagem pelo maior prefixo coerente.

Não some contagens independentes.

O backend resolve o `active_school_year_id`; o cliente nunca o fornece.

Quando não existe ano letivo ativo, mantenha o resultado das Bases, devolva `fingerprint: null` e inclua `ACTIVE_SCHOOL_YEAR_REQUIRED` como blocker estruturado.

Calcule o fingerprint apenas com:

```python
SchedulerFingerprintService.generation_input_fingerprint(
    organization_id=actor.organization_id,
    school_year_id=active_school_year.id,
    strategy=ScheduleGenerationStrategy.COMPLETE_GENERATION,
)
```

#### `GET /api/v1/readiness/prevalidation?fingerprint=<sha256-opcional>`

Permita administradores com Bases a `100`.

Não escreva na base de dados.

Não sincronize feriados.

Não crie jobs.

O parâmetro `fingerprint` é um token de concorrência opcional, nunca a fonte de verdade.

O backend resolve novamente a organização, o ano letivo ativo e a estratégia `COMPLETE_GENERATION`.

Sem ano letivo ativo, devolva `BLOCKED`, `fingerprint: null` e o issue `ACTIVE_SCHOOL_YEAR_REQUIRED`.

Resposta:

```json
{
  "status": "READY_WITH_WARNINGS",
  "fingerprint": "sha256",
  "issues": [
    {
      "code": "HOLIDAYS_NOT_SYNCHRONIZED",
      "severity": "WARNING",
      "message": "Sincronize os feriados antes de gerar.",
      "route": "/config"
    }
  ]
}
```

Recalcule o fingerprint no fim.

Devolva `409 PREFLIGHT_STALE` quando o fingerprint recebido ou o fingerprint final difere do inicial calculado.

O contrato interno único é:

```python
PreflightService.evaluate(
    *,
    organization_id: int,
    school_year_id: int,
    strategy: ScheduleGenerationStrategy,
) -> PreflightReport
```

`PreflightReport` contém `status`, `fingerprint` e `issues: list[PreflightIssue]`.

`PreflightIssue` contém `code`, `severity`, `message` e `route`.

```python
class PreflightIssue(BaseModel):
    code: str
    severity: Literal["BLOCKER", "WARNING"]
    message: str
    route: str


class PreflightReport(BaseModel):
    status: Literal["BLOCKED", "READY_WITH_WARNINGS", "READY"]
    fingerprint: str | None
    issues: list[PreflightIssue]
```

Derive `PreflightReport.status` sem exceções locais: qualquer `BLOCKER` produz `BLOCKED`; sem blockers e com pelo menos um `WARNING` produz `READY_WITH_WARNINGS`; sem issues produz `READY`.

Use estes mesmos tipos e a mesma semântica de warning/blocker em prontidão, prevalidation, geração e erro HTTP.

Todo o comando de geração volta a executar `PreflightService.evaluate()` no servidor imediatamente antes de criar o job; estado React Query nunca autoriza geração.

### 5.4 Disponibilidade

Use estes endpoints:

| Método | Rota | Permissão |
| :--- | :--- | :--- |
| `GET` | `/teachers/me/availability` | Professor autenticado |
| `PUT` | `/teachers/me/availability` | Professor autenticado |
| `GET` | `/teachers/{teacher_id}/availability` | Administrador read-only |

Elimine `POST /teachers/{teacher_id}/availability`.

O `PUT` exige exatamente uma linha por timeslot atual.

Rejeite duplicados, timeslots externos e matrizes incompletas antes da mutação.

### 5.5 Telemetria

#### `POST /api/v1/tutorial/telemetry`

Permita apenas administradores com fundação completa.

Use rate limit `60/minute`.

Derive `organization_id` do ator autenticado; nunca o aceite no payload.

Aceite apenas `client_event_id`, `tutorial_run_id`, `tutorial_version`, `event_name`, `chapter` e `step_id`.

Ignore timestamps enviados pelo cliente.

Responda `204` após inserção ou duplicado idempotente.

## 6. Predicado coerente das Bases

Avalie sete níveis pela mesma cadeia relacional.

| Profundidade | Condição cumulativa | Correção |
| :--- | :--- | :--- |
| 1 | Existe `Class.is_archived = false` | `/courses` |
| 2 | Existe `Module.required_minutes > 0` na organização | `/subjects` |
| 3 | A turma possui `ClassSubjectLink` no `grade_level` atual para uma disciplina com módulos | Página de disciplinas da turma |
| 4 | O `ClassSubjectLink` possui professor ativo com competência em `teacher_subject_link` | `/courses/{courseId}/classes/{classId}/subjects` |
| 5 | Existe sala com tipo exigido e capacidade suficiente | `/rooms` |
| 6 | Existe pelo menos um `Timeslot` da organização | `/config` |
| 7 | O professor possui disponibilidade diferente de `IMPOSSIBLE` nesse timeslot | `/members` |

Cada query de profundidade estende a query anterior.

Uma sala é compatível quando cumpre ambas as condições:

- `room.type == subject.required_room_type`.
- `room.capacity >= class.size`.

Calcule o fingerprint apenas na profundidade `7`, depois de o backend resolver um ano letivo ativo, sempre com estratégia `COMPLETE_GENERATION`.

Sem ano letivo ativo, devolva o blocker estruturado `ACTIVE_SCHOOL_YEAR_REQUIRED` e não invoque o serviço de fingerprint.

## 7. Encaminhamento frontend alvo

Avalie o encaminhamento nesta ordem:

1. Aguarde Clerk, organização, membro e fundação.
2. Encaminhe sem organização para `/create-org`.
3. Encaminhe fundação incompleta e administrador para `/foundation`.
4. Encaminhe fundação incompleta e não administrador para `/foundation/waiting`.
5. Encaminhe administrador com tutorial `NOT_STARTED` para `/guide`.
6. Marque o tutorial `IN_PROGRESS` ao montar `/guide`.
7. Encaminhe administrador ativado para o dashboard operacional.
8. Encaminhe administrador não ativado para o dashboard de preparação.
9. Encaminhe não administradores pela capacidade atual.

Uma saída explícita do tutorial impede nova abertura automática.

O dashboard mostra “Retomar guia” quando o estado local é `IN_PROGRESS`.

## 8. Máquina de estados local do tutorial

### 8.1 Chave e schema

Use esta chave:

```text
cronos:tutorial:v{version}:user:{clerkUserId}:org:{clerkOrgId}
```

Guarde apenas:

```json
{
  "version": 1,
  "tutorialRunId": "4ca99563-1c8a-4209-a149-e55b8c049324",
  "status": "IN_PROGRESS",
  "chapter": 1,
  "stepId": "subject_create",
  "values": {},
  "skippedStepIds": []
}
```

Valide o JSON depois da leitura.

Reinicie com o cenário inicial quando o JSON é inválido.

Registe o erro de parsing na consola.

Não migre estados entre versões do tutorial.

Gere `tutorialRunId` com `crypto.randomUUID()` ao abrir o guia pela primeira vez e ao executar “Repetir guia”.

Retomar uma execução `IN_PROGRESS` preserva o mesmo `tutorialRunId`.

No primeiro open, persista o estado antes de emitir `tutorial_opened`.

No repeat, gere e persista primeiro o novo `tutorialRunId`; emita `tutorial_repeated` e `tutorial_opened` com esse novo identificador e nunca apague os eventos associados ao identificador anterior.

### 8.2 Cenário local

Defina o cenário em `frontend/src/features/tutorial/tutorialScenario.js`.

Use exatamente:

- Dois cursos preparados.
- Três turmas preparadas.
- Cinco disciplinas com módulos positivos.
- Quatro professores.
- Três salas compatíveis.
- Uma grelha semanal uniforme.
- Um horário aprovado preparado.
- Uma ocorrência e reparação preparadas.

Use identificadores locais com prefixo `demo-`.

Não use UUIDs remotos.

### 8.3 Passos fechados

| Ordem | `stepId` | Ação principal | Efeito de `skip` |
| :--- | :--- | :--- | :--- |
| 1.1 | `structure_overview` | Continuar | Não aplicável |
| 1.2 | `subject_create` | Guardar disciplina | Aplicar nome preparado |
| 1.3 | `module_add` | Adicionar módulo positivo | Aplicar módulo preparado |
| 1.4 | `course_create` | Guardar curso | Aplicar curso preparado |
| 1.5 | `class_create` | Guardar turma | Aplicar turma preparada |
| 1.6 | `teacher_add` | Guardar professor | Aplicar professor preparado |
| 1.7 | `teacher_competency` | Guardar competência | Ligar competência preparada |
| 1.8 | `room_add` | Guardar sala | Aplicar sala preparada |
| 1.9 | `assignment_create` | Guardar associação | Aplicar associação preparada |
| 1.10 | `availability_review` | Confirmar disponibilidade | Aplicar matriz neutra preparada |
| 1.11 | `schedule_prepare` | Preparar exemplo | Aplicar resultado estático |
| 1.12 | `schedule_review` | Continuar | Não aplicável |
| 1.13 | `schedule_approve` | Aprovar exemplo | Marcar aprovação simulada |
| 1.14 | `chapter_transition` | Resolver a primeira ocorrência | “Continuar mais tarde” guarda o início do capítulo 2 |
| 2.1 | `published_block_open` | Abrir bloco | Não aplicável |
| 2.2 | `occurrence_create` | Criar ocorrência | Aplicar ocorrência preparada |
| 2.3 | `substitute_teacher_select` | Selecionar professor | Aplicar professor preparado |
| 2.4 | `substitute_subject_select` | Selecionar disciplina | Aplicar disciplina preparada |
| 2.5 | `substitution_complete` | Concluir substituição | Aplicar execução preparada |
| 2.6 | `debt_observe` | Continuar | Não aplicável |
| 2.7 | `repair_simulate` | Simular reparação | Aplicar reparação estática |
| 2.8 | `repair_compare` | Continuar | Não aplicável |
| 2.9 | `history_verify` | Confirmar preservação | Não aplicável |
| 2.10 | `repair_approve` | Aprovar reparação | Concluir tutorial |

Passos observacionais não mostram “Saltar este passo”.

Passos de exercício mostram uma ação principal e uma ação secundária de skip.

Desative todos os restantes controlos.

Use esta copy na transição:

> O primeiro horário está aprovado. Mas amanhã um professor falta e a turma recebe outra disciplina. O que acontece às horas que ficaram por dar?

Use “Resolver a primeira ocorrência” como ação principal.

Use “Continuar mais tarde” como ação secundária sempre visível.

### 8.4 Prova das combinações de skip

Implemente `applyTutorialTransition(state, action)` como função pura.

Extraia `SKIPPABLE_STEP_IDS` do cenário, sem uma segunda lista manual.

Para o storyboard fechado da secção 8.3, exija `SKIPPABLE_STEP_IDS.length === 17`; a suite executa `131072` sequências.

Enumere de forma determinística todas as máscaras entre `0` e `(2 ** SKIPPABLE_STEP_IDS.length) - 1`.

Para cada máscara, percorra o guia inteiro: aplique `SKIP` quando o bit correspondente é `1` e `COMPLETE` nos restantes passos exercitáveis.

Depois de cada transição, valide os invariantes do cenário e a pré-condição do passo seguinte.

No fim de cada sequência, exija `COMPLETED`, a dívida original preservada e o histórico da reparação intacto.

O teste falha se surgir um passo de skip não incluído na enumeração ou uma ordem não determinística.

## 9. Work Breakdown Structure

### 9.0 Governação e baseline

#### 9.0.1 Congelar contratos atuais

**Dependências:** nenhuma.

**Ficheiros de teste:**

- `backend/tests/test_onboarding.py`
- `backend/tests/test_session_bootstrap_integration.py`
- `frontend/src/test/Onboarding.test.jsx`
- `frontend/src/test/AppRouteGuards.test.jsx`

**Trabalho:**

1. Registe testes de caracterização do onboarding atual.
2. Confirme que uma linha `organization_settings` conclui hoje o onboarding.
3. Confirme que administradores escrevem hoje disponibilidade alheia.
4. Confirme que o preflight sincroniza hoje feriados.
5. Marque estes testes como contratos temporários a substituir.
6. Execute as suites afetadas e corrija fixtures ou infraestrutura até todos os testes de caracterização passarem.

**Saída:** baseline de caracterização `GREEN`; nenhum teste do novo requisito foi ainda introduzido.

#### 9.0.2 Fixar nomenclatura e fronteiras

**Dependências:** 9.0.1.

**Trabalho:**

1. Renomeie o conceito frontend `onboarding` para `foundation`.
2. Reserve `tutorial` para a simulação local.
3. Reserve `readiness` para Bases e pré-validação.
4. Proíba `bootstrap_founder` e novos identificadores técnicos com `founder`.
5. Documente os códigos de erro deste documento.

**Aceitação:** `rg -n "bootstrap_founder|founder_[a-zA-Z0-9_]*|[a-zA-Z0-9_]*_founder" backend/app` não devolve resultados; a mesma expressão em `backend/tests` devolve apenas o teste temporário do wrapper. Audite `backend/alembic/versions` separadamente para permitir apenas versões históricas, a migration de expansão, a migration de contração e os respetivos rollbacks. Não pesquise conteúdo editorial ou marketing.

### 9.1 Persistência e migração

#### 9.1.1 Escrever testes de modelo

**Dependências:** 9.0.2.

**Testes RED:**

1. `Organization` expõe os três campos novos.
2. `OrganizationFoundationDraft` exige versão positiva.
3. `TutorialTelemetryEvent` rejeita eventos desconhecidos.
4. A matriz de RLS inclui as tabelas novas.
5. O trigger impede reabertura da fundação.
6. O trigger impede apagar ou alterar `foundation_completed_at` depois de preenchido.
7. O trigger impede apagar ou alterar o primeiro instante real.
8. O trigger rejeita o primeiro instante real sem fundação concluída.
9. A telemetria exige `tutorial_run_id` e unicidade `(organization_id, client_event_id)`.
10. O papel `cronos_app` não consegue executar `UPDATE` ou `DELETE` na telemetria.

**Ficheiros:**

- `backend/tests/test_foundation_models.py`
- `backend/tests/test_rls_database_policies.py`
- `backend/tests/test_tenant_isolation_complete.py`
- `backend/tests/test_migration_foundation_backfill.py`

#### 9.1.2 Implementar modelos e migration `0004`

**Dependências:** 9.1.1.

**Trabalho:**

1. Adicione os enums Python e PostgreSQL.
2. Adicione os campos da organização.
3. Crie as duas tabelas.
4. Crie constraints, índices, FKs scoped e RLS.
5. Crie o trigger monotónico depois do backfill.
6. Crie `app_security.bootstrap_organization_admin(text, text, text, text, text, text)` com o comportamento atual integral de `bootstrap_founder`.
7. Declare `SECURITY DEFINER SET search_path = pg_catalog, public` e owner `cronos_auth_definer`.
8. Execute `REVOKE ALL ... FROM PUBLIC` e conceda apenas `EXECUTE` a `cronos_app`.
9. Substitua a implementação de `bootstrap_founder` por um wrapper SQL temporário com a mesma assinatura que delega em `bootstrap_organization_admin`.
10. Preserve no wrapper `SECURITY DEFINER`, `search_path`, owner, revoke e grant atuais.
11. Atualize `SessionBootstrapService` e `OperationalSeedService` para `bootstrap_organization_admin`.
12. Atualize fixtures e testes RLS que invoquem o identificador antigo.
13. Não remova `bootstrap_founder` nesta migration de expansão.

**Testes de migration obrigatórios:**

1. `upgrade` cria ambas as funções com assinaturas e ACL esperadas.
2. Uma ligação com o papel `cronos_app` invoca a função nova e recebe `account_id`, `organization_id` e `membership_id`.
3. O wrapper antigo devolve o mesmo contrato durante a janela de compatibilidade.
4. `downgrade` repõe a função antiga funcional e remove apenas a função nova.
5. `upgrade -> downgrade -> upgrade` termina com schema e permissões idênticos ao primeiro upgrade.

**Aceitação:** os dois consumidores de runtime usam a função nova; o identificador antigo existe apenas nas migrations históricas, na migration de expansão/rollback e no teste de compatibilidade.

#### 9.1.3 Implementar backfill determinístico

**Dependências:** 9.1.2.

**Ordem de classificação:**

1. Procure a primeira aprovação `COMPLETE_GENERATION` com `draft_state=APPROVED`.
2. Use `schedule_drafts.decided_at` como instante principal.
3. Use o menor `active_schedule_blocks.created_at` apenas como fallback.
4. Marque essas organizações `COMPLETED`.
5. Preencha `first_real_schedule_approved_at` com o instante encontrado.
6. Sem aprovação, valide período, estabilidade, almoço e grelha uniforme.
7. Marque configuração válida com blocos como `COMPLETED`.
8. Marque qualquer configuração parcial ou irregular como `IN_PROGRESS`.
9. Marque ausência total de configuração como `NOT_STARTED`.
10. Crie rascunho pré-preenchido apenas para `IN_PROGRESS`.
11. Ignore metadados Clerk antigos durante toda a classificação.
12. Não reabra organizações classificadas como `COMPLETED`.

**Validação da grelha existente:**

- Todos os dias possuem a mesma sequência.
- Todas as aulas possuem duração positiva igual.
- Todos os intervalos possuem duração não negativa igual.
- Existe pelo menos um bloco.

**Cenários de teste obrigatórios:** aprovação histórica, configuração válida, parcial, irregular e vazia.

### 9.2 Backend da fundação

#### 9.2.1 Definir schemas Pydantic

**Dependências:** 9.1.2.

**Testes RED:**

1. O rascunho aceita campos ausentes.
2. O rascunho rejeita campos extra.
3. A conclusão rejeita qualquer campo ausente.
4. A conclusão reutiliza validadores de datas e almoço.
5. A conclusão rejeita dias duplicados.
6. A conclusão rejeita grelha sem uma aula completa.
7. A conclusão exige `confirmed=true`.

**Trabalho:**

1. Crie `FoundationDraftData`.
2. Crie `FoundationDraftWrite`.
3. Crie `FoundationCompleteCommand`.
4. Reutilize `OrganizationSettingsUpsert`.
5. Reutilize `GridConfigurationCommand`.

#### 9.2.2 Implementar leitura e gravação concorrente

**Dependências:** 9.2.1.

**Serviço:** `backend/app/services/foundation_service.py`.

**Trabalho:**

1. Implemente `get_status` sem mutação.
2. Implemente `get_draft` sem criação implícita.
3. Implemente `save_draft` com locks.
4. Compare `expected_version` antes da escrita.
5. Substitua o snapshot completo.
6. Incremente a versão uma vez.
7. Mova `NOT_STARTED` para `IN_PROGRESS`.
8. Rejeite gravações depois de `COMPLETED`.

**Testes RED:** dois administradores gravam a mesma versão; apenas um vence.

**Aceitação:** o perdedor recebe a versão atual e nenhum merge.

#### 9.2.3 Implementar conclusão transacional

**Dependências:** 9.2.2.

**Ordem transacional:**

1. Bloqueie a organização.
2. Retorne sucesso se já está `COMPLETED`.
3. Bloqueie o rascunho.
4. Valide `expected_version`.
5. Valide o payload final.
6. Execute `upsert_settings`.
7. Execute `save_and_regenerate_grid`.
8. Conte timeslots persistidos.
9. Rejeite contagem zero.
10. Defina `foundation_status=COMPLETED`.
11. Defina `foundation_completed_at` com hora UTC do servidor.
12. Faça `flush` e deixe `get_db` fazer commit.

**Testes RED:**

1. Uma falha de settings faz rollback total.
2. Uma falha de grelha faz rollback total.
3. Zero blocos impede conclusão.
4. Dois pedidos concorrentes não duplicam blocos.
5. O rascunho permanece depois de falha.
6. Uma conclusão repetida é idempotente.

#### 9.2.4 Expandir as rotas sem quebrar assets em cache

**Dependências:** 9.2.3.

**Trabalho:**

1. Crie `backend/app/api/v1/endpoints/foundation.py`.
2. Registe as quatro rotas.
3. Mantenha `POST /onboarding` e `GET /onboarding/status` como adapters temporários para assets frontend da release anterior.
4. Faça os adapters delegarem em `FoundationService`; não duplique validação, transação ou escrita.
5. Preserve apenas o formato HTTP antigo e adicione `Deprecation: true` e `Sunset` com a data da release de contração.
6. Remova `complete_onboarding` como regra independente.
7. Remova `mark_onboarding_complete_in_clerk`.
8. Remova a escrita de `public_metadata.onboardingComplete`.
9. Atualize o inventário API e marque os dois aliases como temporários.

**Aceitação:** assets antigos e novos concluem a mesma transação de fundação; nenhuma conclusão depende do Clerk.

### 9.3 Bloqueio backend e encaminhamento

#### 9.3.1 Criar dependências de autorização explícitas

**Dependências:** 9.2.2.

**Trabalho:**

1. Preserve um `SessionActor` sem gate de fundação.
2. Preserve um `FoundationAdminActor` sem gate operacional.
3. Faça `ActiveActor` exigir fundação concluída.
4. Faça `AdminActor` exigir fundação concluída e capacidade admin.
5. Use `SessionActor` apenas em `/members/me` e status da fundação.
6. Use `FoundationAdminActor` apenas no draft e conclusão.

**Testes RED:**

1. Admin incompleto acede ao draft.
2. Professor incompleto acede ao status.
3. Admin incompleto recebe `409` em cada router de domínio.
4. Professor incompleto recebe `409` nas rotas próprias.
5. Membro completo mantém o comportamento atual.

#### 9.3.2 Auditar a allowlist

**Dependências:** 9.3.1.

**Trabalho:**

1. Crie teste parametrizado para a allowlist.
2. Crie teste parametrizado com uma rota por router bloqueado.
3. Falhe o teste quando uma nova rota tenant-owned não declarar o gate.

**Aceitação:** contornar o frontend nunca concede operações de domínio.

#### 9.3.3 Atualizar bootstrap de sessão

**Dependências:** 9.1.3 e 9.3.1.

**Trabalho:**

1. Substitua `onboarding_complete` por `foundation_status`.
2. Leia o enum na organização.
3. Remova a inferência pela presença de settings.
4. Atualize `activateAndBootstrapOrganization`.
5. Atualize testes de criação e retoma da organização.

### 9.4 Wizard frontend da fundação

#### 9.4.1 Criar modelo puro de nove passos

**Dependências:** 9.2.1.

**Ficheiros:**

- `frontend/src/features/foundation/foundationModel.js`
- `frontend/src/test/foundationModel.test.js`

**Passos:** período, dias, abertura, duração, intervalo, almoço, preview, calendário e confirmação.

**Testes RED:**

1. Cada passo valida apenas os seus campos.
2. O passo final valida o payload completo.
3. A preview usa a grelha uniforme.
4. Back preserva valores.
5. Um draft remoto hidrata o passo correto.
6. Aceder a `/foundation` depois da conclusão encaminha para o destino real.

#### 9.4.2 Implementar autosave serializado

**Dependências:** 9.4.1 e 9.2.2.

**Regras:**

1. Aguarde `600 ms` depois da última alteração.
2. Envie apenas um `PUT` de cada vez.
3. Use a última versão confirmada.
4. Se houver alterações pendentes, envie novo snapshot após a resposta.
5. Em `Continue`, serialize o snapshot completo com `current_step` igual ao passo de destino.
6. Em `Back`, serialize o snapshot completo com `current_step` igual ao passo de destino.
7. Aguarde a resposta do `PUT` antes de alterar o passo visível.
8. Em saída, serialize o passo atualmente visível antes de navegar.
9. Desative navegação enquanto o save forçado está pendente.
10. Mostre estado “A guardar”, “Guardado” ou “Conflito”.
11. Num `409`, mantenha o passo visível e os valores locais, congele o formulário e não aplique a transição pendente.
12. Mostre “Tentar guardar novamente” e “Carregar configuração mais recente”.
13. O retry repete o snapshot de destino apenas depois de obter uma versão confirmada; reload descarta o snapshot local e hidrata o remoto.
14. Não faça merge local.

**Testes RED:**

1. Alterações rápidas produzem saves serializados sem self-conflict.
2. `Continue` do passo `4` envia `current_step: 5` e mantém o passo `4` visível até `200`.
3. Um `409` nesse pedido mantém o passo `4`, não mostra o passo `5` e disponibiliza retry/reload.
4. Depois de `200`, o passo `5` torna-se visível e um reload hidrata diretamente o passo `5`.

#### 9.4.3 Implementar a interface

**Dependências:** 9.4.2.

**Trabalho:**

1. Renomeie `Onboarding.jsx` para `FoundationWizard.jsx`.
2. Reutilize `GuidedFormShell` e `GuidedFormProgress`.
3. Reutilize os payload helpers da configuração escolar.
4. Mostre uma preview semanal read-only.
5. Mostre eventos existentes read-only no passo oito.
6. Mantenha sincronização de feriados fora do wizard.
7. Exija checkbox e botão final explícitos.
8. Mostre erros recuperáveis sem apagar o draft.

**Acessibilidade:**

- Ligue todos os labels aos inputs.
- Mova foco para o título do novo passo.
- Use `role=status` no autosave.
- Use `role=alert` no conflito.
- Preserve navegação por teclado.

#### 9.4.4 Implementar ecrã de espera

**Dependências:** 9.3.3.

**Rota:** `/foundation/waiting`.

**Trabalho:**

1. Mostre o nome da organização.
2. Explique que um administrador prepara a escola.
3. Consulte novamente o status em foco e a cada `30 s`.
4. Encaminhe imediatamente após `COMPLETED`.
5. Não mostre controlos administrativos.

### 9.5 Guia interativo local

#### 9.5.1 Entregar storyboard e copy técnica

**Dependências:** 9.4.3.

**Saída:** uma tabela por passo com título, instrução, ação, skip, resultado e estado vazio.

**Aceitação:** nenhuma frase afirma que o solver executou durante a simulação.

#### 9.5.2 Implementar cenário e reducer

**Dependências:** 9.5.1.

**Ficheiros:**

- `frontend/src/features/tutorial/tutorialScenario.js`
- `frontend/src/features/tutorial/tutorialModel.js`
- `frontend/src/features/tutorial/tutorialStorage.js`

**Testes RED:**

1. O cenário tem as dimensões definidas.
2. IDs locais não colidem.
3. Cada transição preserva invariantes.
4. Cada skip fornece os valores seguintes.
5. Sair preserva o checkpoint.
6. Concluir define `COMPLETED`.
7. Saltar guia define `SKIPPED`.
8. Repetir regressa ao cenário inicial.
9. JSON inválido recupera sem crash.

#### 9.5.3 Implementar vistas simuladas

**Dependências:** 9.5.2.

**Vistas mínimas:**

- Estrutura curricular.
- Pessoas e recursos.
- Associações.
- Disponibilidade.
- Horário e aprovação.
- Ocorrência e substituição.
- Dívida original.
- Diff de reparação.

**Regras:**

1. Passe dados locais por props.
2. Não monte hooks de domínio real.
3. Desative todos os controlos fora da ação esperada.
4. Marque sempre “Simulação”.
5. Incorpore nomes introduzidos nos resultados preparados.
6. Preserve passado e horizonte congelado no diff estático.
7. Mostre dívida original depois da disciplina substituta.

#### 9.5.4 Garantir fronteira de rede

**Dependências:** 9.5.3.

**Testes RED:**

1. Nenhum método `apiClient` de domínio é chamado.
2. Nenhuma rota Clerk de escrita é chamada.
3. Nenhuma rota scheduler é chamada.
4. O percurso completa com scheduler abortado.
5. Apenas os pedidos da `GUIDE_NETWORK_ALLOWLIST` podem sair durante o percurso.

**Regras estáticas e E2E:**

1. Adicione um teste de imports que falha se `frontend/src/features/tutorial/**` importar `apiClient`, módulos `features/*/data`, Clerk SDK/hooks ou código de scheduler.
2. Permita apenas módulos React, componentes visuais puros e os módulos locais `tutorialScenario`, `tutorialModel`, `tutorialStorage` e `tutorialTelemetry`.
3. No Playwright, intercepte toda a rede enquanto `/guide` está aberto.
4. Autentique a identidade E2E antes de instalar a interceção; depois desse ponto, não permita pedidos à origem Clerk.
5. Declare `GUIDE_NETWORK_ALLOWLIST` no teste com pares exatos de método e pathname: `GET /api/v1/members/me`, `GET /api/v1/foundation/status` e `POST /api/v1/tutorial/telemetry`.
6. Permita `GET`/`HEAD` same-origin apenas quando `resourceType` é `document`, `script`, `stylesheet`, `font` ou `image`; não use um wildcard `/api/**`.
7. Faça o teste falhar imediatamente com URL, método e `stepId` perante qualquer pedido inesperado.

**Aceitação:** o guia funciona sem worker.

#### 9.5.5 Integrar entrada, saída e repetição

**Dependências:** 9.5.4 e 9.7.5.

**Trabalho:**

1. Crie `/guide` fora do layout operacional.
2. Abra automaticamente apenas em `NOT_STARTED`.
3. Grave `IN_PROGRESS` no primeiro mount.
4. Mostre saída temporária em ambos os capítulos.
5. Mostre skip definitivo sem padrão coercivo.
6. Mostre “Retomar guia” nos dois dashboards.
7. Mostre “Repetir guia” depois de conclusão ou skip.

### 9.6 Disponibilidade neutra

#### 9.6.1 Separar inspeção pura de reparação explícita

**Dependências:** 9.1.2.

**Ficheiro:** `backend/app/services/availability_matrix_service.py`.

**Trabalho:**

1. Crie `AvailabilityMatrixInspector.inspect(...)` como leitura pura.
2. Calcule o produto `Teacher x Timeslot` limitado à organização recebida.
3. Sobreponha as linhas persistidas e represente cada linha ausente como `PreferenceLevel.NEUTRAL` apenas no resultado em memória.
4. Devolva `AvailabilityMatrixInspection` com a matriz efetiva e `anomalies` identificadas por `teacher_id` e `timeslot_id`.
5. Proíba `INSERT`, `UPDATE`, `DELETE`, `flush` e `commit` no inspector.
6. Crie `AvailabilityMatrixRepairService.repair(...)` no mesmo ficheiro, sem interface adicional.
7. No reparador, insira apenas linhas ausentes com `NEUTRAL` e `ON CONFLICT DO NOTHING`.
8. Faça `flush`, nunca `commit`, e devolva a contagem efetivamente inserida.
9. Registe `availability_matrix_integrity_repaired` em nível error com organização, professores, timeslots e contagem.

**Testes RED:**

1. Uma linha ausente é devolvida como neutra e como anomalia, mantendo inalterada a contagem SQL.
2. Monkeypatch de `Session.execute` rejeita qualquer statement de escrita executado pelo inspector.
3. Duas reparações concorrentes não criam duplicados.
4. O reparador nunca inclui professores ou timeslots de outra organização.

#### 9.6.2 Preencher novos professores

**Dependências:** 9.6.1.

**Trabalho:**

1. Chame `AvailabilityMatrixRepairService` depois de criar `Teacher` em `member_service`.
2. Preencha todos os timeslots atuais.
3. Mantenha comportamento vazio quando não existe grelha.
4. Execute criação e reparação na mesma transação do serviço; não faça commit interno.

**Aceitação:** professor criado após a grelha começa totalmente neutro.

#### 9.6.3 Preservar regeneração da grelha

**Dependências:** 9.6.1.

**Trabalho:**

1. Preserve preferências por dia, início e fim.
2. Atribua neutro a blocos novos.
3. Chame `AvailabilityMatrixRepairService` na transação de regeneração antes do snapshot mutável.
4. Reutilize `_restore_availabilities_for_new_grid`.

**Aceitação:** a cardinalidade final é `professores x timeslots`.

#### 9.6.4 Uniformizar consumidores sem efeitos laterais

**Dependências:** 9.6.1.

**Consumidores:** fingerprint, preflight, candidatos, recomendações e validação de substituição.

**Trabalho:**

1. Faça fingerprint, readiness, preflight, candidatos, recomendações e validação de substituição consumirem `AvailabilityMatrixInspector`.
2. Não invoque `AvailabilityMatrixRepairService` em funções de consulta, rotas `GET`, fingerprint ou prevalidation.
3. Trate apenas `PreferenceLevel.IMPOSSIBLE.value` como indisponibilidade rígida.
4. Remova o fallback “linha ausente = indisponível”.
5. Use a constante enum, não `-1` nem outro número mágico.
6. Exponha as anomalias ao log estruturado sem alterar a base de dados.
7. Na fronteira mutável de geração real, execute esta ordem dentro da transação do pedido: autorizar e bloquear contexto; reparar a matriz; `flush`; calcular fingerprint; executar `PreflightService.evaluate()`; criar o job apenas sem blockers.
8. Não coloque reparação dentro do inspector, do serviço de fingerprint ou de `PreflightService`.

**Testes RED:**

1. Remova uma linha, execute fingerprint, readiness, preflight e cada `GET`, confirme valor neutro e contagem SQL inalterada.
2. Execute depois criação de professor, regeneração da grelha ou geração real e confirme que a linha é persistida como neutra.
3. Um blocker de preflight depois da reparação faz rollback da reparação e não cria job.

#### 9.6.5 Fechar permissões de escrita

**Dependências:** 9.6.2 e 9.6.4.

**Trabalho:**

1. Substitua a rota de escrita pelo `PUT /teachers/me/availability`.
2. Use o `teacher_id` do ator.
3. Não aceite `teacher_id` no payload.
4. Adicione GET administrativo read-only.
5. Atualize `MyAvailability` para a rota self.
6. Mostre a grelha read-only na ficha do professor.
7. Coloque identidade, acesso, estado e competências à esquerda.
8. Coloque grelha e resumo de disponibilidade à direita.
9. Empilhe as duas áreas em viewports estreitos.

**Testes RED:**

1. Admin sem perfil não escreve.
2. Admin-professor escreve apenas a própria matriz.
3. Professor não escreve outra matriz.
4. Diretor lê outras matrizes.

### 9.7 Bases, pré-validação e dashboard

#### 9.7.1 Implementar predicado das Bases

**Dependências:** 9.6.4.

**Serviço:** `backend/app/services/school_readiness_service.py`.

**Trabalho:**

1. Crie `PreflightIssue` em `backend/app/schemas.py` com `code`, `severity`, `message` e `route`.
2. Faça `severity` aceitar apenas `BLOCKER` ou `WARNING`.
3. Construa as sete queries cumulativas a partir do mesmo conjunto tenant-scoped de turmas ativas.
4. Resolva o ano letivo ativo com `SchedulerStateService.get_active_school_year(organization_id)`; não use `get_or_create_active_school_year` num percurso read-only.
5. Calcule o fingerprint apenas quando a profundidade é `7` e o ano ativo existe.
6. Passe explicitamente `organization_id`, `active_school_year.id` e `ScheduleGenerationStrategy.COMPLETE_GENERATION` a `generation_input_fingerprint`.
7. Devolva `issues: list[PreflightIssue]`; não crie um tipo paralelo de issue para readiness.

**Testes RED:**

1. Cinco entidades desligadas produzem menos de `100`.
2. Uma cadeia completa produz `100`.
3. Sala pequena não completa a cadeia.
4. Sala de tipo errado não completa a cadeia.
5. Disponibilidade toda impossível não completa a cadeia.
6. Uma disponibilidade neutra completa a cadeia.
7. Dados de outra organização nunca contam.
8. Sem ano letivo ativo, a resposta contém `ACTIVE_SCHOOL_YEAR_REQUIRED`, não calcula fingerprint e não consulta outra organização.
9. Com a cadeia completa, o fingerprint recebe o `school_year_id` ativo e `ScheduleGenerationStrategy.COMPLETE_GENERATION`.

#### 9.7.2 Refatorar preflight para leitura pura

**Dependências:** 9.7.1.

**Trabalho:**

1. Reutilize `PreflightIssue` e crie `PreflightReport` em `backend/app/schemas.py`.
2. Use apenas `code` estável em todos os issues.
3. Crie `PreflightService.evaluate()` como API pública em `backend/app/services/preflight_service.py`.
4. Elimine a importação privada `_preflight_check` de `scheduler_request_service.py`.
5. Atualize os dois percursos desse serviço — validação de configuração e pedido selecionado — para receber `PreflightReport`, nunca `tuple[list[str], dict]`.
6. Faça readiness e a rota de prevalidation invocarem a mesma API pública.
7. Serialize o mesmo `PreflightReport` no erro HTTP do comando de geração; não crie o campo paralelo `problems: list[str]`.
8. Atualize `PreflightErrorPanel` e `Schedules.jsx` para consumirem `issues`, usarem `issue.code` como key, distinguirem severidade e ligarem `issue.route` à correção.
9. Remova `_ensure_auto_holidays`, chamadas equivalentes e comentários que autorizem sincronização ou refresh automático do percurso de geração real.
10. Crie `HOLIDAYS_NOT_SYNCHRONIZED` como warning quando aplicável.
11. Preserve `sync-holidays` como comando explícito separado.
12. Reutilize as restantes verificações existentes e mantenha o cálculo de capacidade read-only.
13. Defina uma tabela de classificação testada para que cada `code` tenha a mesma severidade em readiness, prevalidation e geração.
14. Faça `PreflightService.evaluate()` consumir `AvailabilityMatrixInspector`; não permita reparação, `flush`, writes ou commit.

**Testes RED:**

1. Monkeypatch de `sync_holidays` falha se readiness, prevalidation ou geração o invocar.
2. Os dois call sites de `scheduler_request_service.py` recebem um `PreflightReport` estruturado.
3. Um blocker impede a criação de job; um warning permite-a.
4. O erro HTTP e `PreflightErrorPanel` preservam `code`, `severity`, `message` e `route`.
5. `rg -n "_preflight_check|problems" backend/app frontend/src/components/schedules frontend/src/pages/Schedules.jsx` não encontra o contrato antigo.
6. Uma execução contra PostgreSQL compara as tabelas afetadas antes e depois de `evaluate()` e confirma zero alteração.

#### 9.7.3 Implementar API e hooks de prontidão

**Dependências:** 9.7.2.

**Trabalho:**

1. Crie `backend/app/api/v1/endpoints/readiness.py`.
2. Crie `frontend/src/features/readiness/data.js`.
3. Ative prevalidation apenas com Bases a `100`.
4. Use `isFetching` como estado `CHECKING`.
5. Use o fingerprint na query key.
6. Resolva o ano letivo ativo apenas no backend; não aceite `school_year_id` do browser.
7. Mostre `ACTIVE_SCHOOL_YEAR_REQUIRED` como blocker corrigível quando o backend devolve `fingerprint: null`.
8. Não faça polling depois de resultado estável.
9. Configure `refetchOnWindowFocus: true` para Bases, prevalidation e dashboard, porque outro administrador pode alterar o contexto.
10. Reexecute após fingerprint novo.
11. Desative e desconsidere a prevalidation quando Bases desce de `100`.
12. No botão “Gerar”, use readiness apenas para apresentação e desativação preventiva; o `POST` de geração reexecuta sempre preflight no backend.

**Testes RED:** adulterar o cache React Query para `READY` não cria um job quando o preflight do servidor devolve blocker.

#### 9.7.4 Invalidar prontidão após mutações relevantes

**Dependências:** 9.7.3.

**Ficheiros:**

- `frontend/src/features/catalog/data.js`
- `frontend/src/features/members/data.js`
- `frontend/src/features/schoolConfig/data.js`
- `frontend/src/features/operations/data.js`
- `frontend/src/features/scheduling/data.js`

**Trabalho:**

1. Crie um helper de invalidação por organização.
2. Invalide `bases`, `prevalidation` e `dashboard` após mutações relevantes.
3. Não invalide por contacto, telemetria ou preferências visuais.
4. Revalide as três queries quando a janela recupera foco.

**Aceitação:** alterar um recurso reabre `CHECKING` sem reload manual.

#### 9.7.5 Criar dashboard discriminado

**Dependências:** 9.7.3 e 9.8.1.

**Contrato backend:** substitua `DashboardV1Response` por esta união Pydantic discriminada:

```python
DashboardResponse = Annotated[
    PreparationDashboardResponse | OperationalDashboardResponse,
    Field(discriminator="mode"),
]
```

`PreparationDashboardResponse.mode` é o literal `PREPARATION`.

`OperationalDashboardResponse.mode` é o literal `OPERATIONAL` e preserva `alerts`, `resources`, `schedule_health`, `class_progress`, `debts` e `org_name` do contrato atual.

Declare `response_model=DashboardResponse` na rota; não devolva um objeto híbrido com campos opcionais dos dois modos.

**Trabalho:**

1. Devolva preparação antes do primeiro horário real.
2. Preserve widgets atuais no modo operacional.
3. Mostre cinco blocos de preparação.
4. Mostre Fundação, Oferta, Pessoas, Associações e Primeiro horário.
5. Mostre uma única ação principal por bloco.
6. Mostre correções do preflight antes do botão.
7. Ative geração apenas em `READY` ou `READY_WITH_WARNINGS`.
8. Mostre o aviso sobre dados atualmente registados.
9. Não mencione importação em massa.
10. Faça `Dashboard.jsx` executar um switch exaustivo por `data.mode` antes de aceder aos campos específicos.
11. Faça `useDashboard` rejeitar um `mode` desconhecido como erro de contrato, sem fallback silencioso.

**Testes RED:**

1. O OpenAPI contém `discriminator.propertyName = mode` e os dois schemas.
2. O endpoint devolve `PREPARATION` sem widgets operacionais antes da primeira aprovação.
3. O endpoint devolve `OPERATIONAL` com todos os campos atuais depois da primeira aprovação.
4. Os testes de `useDashboard` e `Dashboard.jsx` cobrem separadamente os dois modos e um modo desconhecido.

#### 9.7.6 Preparar estados vazios nas páginas reais

**Dependências:** 9.7.5.

**Páginas:** Cursos, Disciplinas, Equipa, Salas, Associações, Configuração e Horários.

**Trabalho:**

1. Mostre uma explicação específica quando a coleção está vazia.
2. Mostre uma única ação principal por estado vazio.
3. Mostre um link para o dashboard de preparação.
4. Mostre lembretes contextuais sem modais bloqueantes.
5. Não crie um segundo tutorial obrigatório.
6. Não mencione importação em massa.
7. Limite esta garantia às páginas alcançáveis antes da ativação.

**Testes RED:** cada página vazia mostra explicação, ação principal e retorno ao dashboard.

### 9.8 Ativação permanente e ciclo anual

#### 9.8.1 Marcar a primeira aprovação real

**Dependências:** 9.1.2 e 9.2.3.

**Local:** `SchedulerApprovalService.approve` no ramo `COMPLETE_GENERATION`.

**Trabalho:**

1. Bloqueie a organização na transação de aprovação.
2. Preencha o marcador apenas quando está `null`.
3. Use o mesmo `instant` da decisão do draft.
4. Garanta `foundation_status=COMPLETED`.
5. Nunca altere o marcador numa reparação.

**Testes RED:**

1. Primeira aprovação preenche o marcador.
2. Reparação mantém o instante.
3. Segunda época mantém o instante.
4. Falha de promoção não preenche o marcador.

#### 9.8.2 Preservar marcador no novo ano

**Dependências:** 9.8.1.

**Local:** `school_year_reset_service.py`.

**Trabalho:**

1. Não altere os campos permanentes da organização.
2. Reponha apenas o estado anual para `UNPUBLISHED`.
3. Mostre preparação anual no dashboard operacional.

**Aceitação:** um novo ano nunca abre `/foundation` ou `/guide` automaticamente.

### 9.9 Telemetria do tutorial

#### 9.9.1 Implementar validação e persistência

**Dependências:** 9.1.2.

**Testes RED:**

1. Aceita os seis eventos.
2. Rejeita eventos desconhecidos.
3. Rejeita `values`, nomes e payloads extra.
4. Um `(organization_id, client_event_id)` repetido é idempotente.
5. O tenant não lê nem escreve eventos externos.
6. Repetir não apaga eventos antigos.
7. Cada evento exige `tutorial_run_id` válido.
8. `UPDATE` e `DELETE` falham com o papel `cronos_app`, mesmo depois de um `GRANT` temporário no teste do trigger.
9. Duas organizações podem usar o mesmo `client_event_id` sem colisão cross-tenant.

**Trabalho:**

1. Derive `organization_id` do `FoundationAdminActor`.
2. Insira com `ON CONFLICT (organization_id, client_event_id) DO NOTHING`.
3. Não implemente métodos update/delete no serviço.
4. Aplique a policy RLS de `INSERT` à organização corrente.
5. Revogue `UPDATE` e `DELETE` de `cronos_app` e mantenha o trigger append-only como defesa independente.

#### 9.9.2 Integrar uma porta frontend não bloqueante

**Dependências:** 9.9.1 e 9.5.2.

**Ficheiro:** `frontend/src/features/tutorial/tutorialTelemetry.js`.

**Trabalho:**

1. Gere `client_event_id` com `crypto.randomUUID()`.
2. Leia `tutorial_run_id` do estado local atual.
3. Gere um novo `tutorial_run_id` ao primeiro open e a cada repeat; preserve-o em resume.
4. Envie apenas os campos permitidos.
5. Não aguarde telemetria para mudar de passo.
6. Registe o erro completo na consola.
7. Não altere o estado local após falha.
8. Não reenvie automaticamente sem limite.

**Aceitação:** falha de rede não bloqueia o guia; repetir cria uma nova execução correlacionável e preserva todos os eventos das execuções anteriores.

### 9.10 Integração, rollout e documentação

#### 9.10.1 Testar percursos frontend

**Dependências:** 9.4, 9.5, 9.7 e 9.8.

**Component tests:**

1. Admin incompleto abre o wizard.
2. Não admin incompleto vê espera.
3. Admin completo sem estado abre o guia uma vez.
4. Saída abre dashboard de preparação.
5. Ativação abre dashboard operacional.
6. Guia em curso mostra retoma.
7. Guia concluído permite repetição.
8. Administrador existente sem chave local abre o guia uma vez.
9. `Dashboard.jsx` renderiza o contrato `PREPARATION` sem ler campos operacionais.
10. `Dashboard.jsx` renderiza o contrato `OPERATIONAL` com os widgets atuais.
11. Foco da janela revalida readiness, prevalidation e dashboard.

#### 9.10.2 Testar percursos E2E

**Dependências:** 9.10.1.

**Playwright separado por responsabilidade:**

1. `e2e/foundation/foundation.spec.js`: crie organização, persista o passo de destino, retome noutro contexto, simule conflito entre dois administradores e conclua a fundação.
2. `e2e/tutorial/tutorial-local.spec.js`: percorra o guia com dados locais, saia, retome, repita com novo `tutorial_run_id` e conclua sem worker.
3. `e2e/tutorial/tutorial-network-boundary.spec.js`: intercepte a rede, permita apenas assets, autenticação/status inventariados e telemetria, e falhe perante qualquer chamada de domínio, Clerk write ou scheduler.
4. `e2e/readiness/first-schedule.spec.js`: construa a cadeia real até Bases `100`, observe `CHECKING`, force um blocker server-side apesar de cache `READY`, gere, aprove e valide ativação.
5. `e2e/dashboard/dashboard-modes.spec.js`: valide a resposta e UI discriminadas antes e depois da primeira aprovação.
6. `e2e/year-reset/no-onboarding.spec.js`: reinicie o ano e confirme ausência de `/foundation` e `/guide` automáticos.

Use identidades Clerk E2E dedicadas.

Cada spec cria o mínimo de dados de que necessita e não depende da ordem dos outros specs.

#### 9.10.3 Atualizar documentação controlada

**Dependências:** 9.10.2.

Atualize:

- `documentation/01_system_architecture/DATA_MODEL.md`.
- `documentation/01_system_architecture/RUNTIME_FLOWS.md`.
- `documentation/02_domain_model/SCHOOL_CONFIGURATION.md`.
- `documentation/05_backend_api/API_REFERENCE.md`.
- `documentation/06_frontend_ux/FRONTEND_ARCHITECTURE.md`.
- `documentation/06_frontend_ux/ROUTES_AND_PERMISSIONS.md`.
- `documentation/08_security_quality/SECURITY_AND_TENANT_ISOLATION.md`.
- `documentation/09_ops_observability/OBSERVABILITY_AND_RECOVERY.md`.

Elimine a descrição do onboarding antigo.

#### 9.10.4 Executar gates de entrega

**Dependências:** 9.10.3.

Execute no backend:

```powershell
cd backend
python -c "import os; from tests.db import validated_test_database_url; validated_test_database_url(os.environ.get('TEST_DATABASE_URL'))"
ruff format --check .
ruff check .
pytest -m "unit and not slow" -q
pytest tests/ -v
alembic check
python -m scripts.audit_triggers
python -m scripts.audit_database_integrity
```

O primeiro comando é obrigatório antes de qualquer fixture destrutiva e aceita apenas `cronos_test_db` ou `cronos_ci_db`, conforme `backend/tests/db.py`.

Execute `alembic check`, `upgrade`, `downgrade` e os audits com a credencial do migrator, nunca com `cronos_app`.

Numa base PostgreSQL descartável e vazia, execute em processos separados:

```powershell
alembic upgrade head
alembic downgrade -1
alembic upgrade head
alembic check
```

Depois, ligue como `cronos_app` e execute o teste de integração de `bootstrap_organization_admin`; esse papel deve executar a função, mas não deve alterar schema nem telemetria existente.

Execute no frontend:

```powershell
cd frontend
npm run audit:production
npm run verify
npm run test:school-config:stability
npx playwright test e2e/foundation e2e/tutorial e2e/readiness e2e/dashboard e2e/year-reset --project=chromium
```

Execute na raiz:

```powershell
git diff --check
git status --short
```

#### 9.10.5 Contrair aliases na release seguinte

**Dependências:** 9.10.4, uma release completa em produção e expiração do TTL máximo dos assets frontend da release anterior.

**Pré-condições verificáveis:**

1. `SessionBootstrapService` e `OperationalSeedService` usam `bootstrap_organization_admin` na release em produção.
2. Os logs de acesso não registam `POST /onboarding` nem `GET /onboarding/status` durante o período de convergência acordado.
3. Os logs SQL/aplicacionais não registam chamadas a `bootstrap_founder` no mesmo período.
4. O inventário de assets confirma que a release anterior expirou ou foi invalidada.

**Trabalho:**

1. Remova os dois adapters HTTP antigos e os respetivos testes de compatibilidade.
2. Crie a migration de contração `0005_drop_bootstrap_founder_compat`.
3. Na migration, revogue `EXECUTE` e elimine apenas `app_security.bootstrap_founder(text, text, text, text, text, text)`.
4. No downgrade, recrie o wrapper com `SECURITY DEFINER`, `SET search_path = pg_catalog, public`, owner `cronos_auth_definer`, `REVOKE ALL FROM PUBLIC` e `GRANT EXECUTE TO cronos_app`.
5. Remova referências técnicas temporárias da documentação e do inventário API.
6. Repita o smoke `upgrade -> downgrade -1 -> upgrade` numa base descartável.

**Aceitação:** nenhum alias permanece; a compatibilidade foi temporária e removida apenas com evidência de convergência.

## 10. Dependências entre pacotes

```text
9.0 Baseline
  -> 9.1 Persistência
    -> 9.2 Fundação backend
      -> 9.3 Gate backend
      -> 9.4 Wizard frontend
    -> 9.6 Disponibilidade -> 9.7.1-9.7.4 Readiness
    -> 9.8 Ativação
    -> 9.9 Telemetria
9.4.3 -> 9.5.1 Storyboard -> 9.5.2-9.5.4 Guia local isolado
(9.7.3 + 9.8.1) -> 9.7.5-9.7.6 Dashboard discriminado e estados vazios
(9.5.4 + 9.7.5) -> 9.5.5 Entrada, saída, retoma e repetição
(9.4 + 9.5.5 + 9.7 + 9.8 + 9.9) -> 9.10 Integração e rollout
9.10.4 -> período de convergência -> 9.10.5 Contração na release seguinte
```

Não inicie a implementação visual final antes de 9.5.1.

Não ative o gate backend antes do backfill 9.1.3.

Na release de expansão, aplique a migration `0004`, depois o backend compatível e finalmente o frontend com invalidação dos assets HTML/manifest; mantenha assets imutáveis por hash.

Não remova funções SQL ou rotas antigas na release de expansão.

Remova os aliases apenas em 9.10.5, depois das pré-condições de convergência.

## 11. Critérios Definition of Done

Um item fica concluído apenas quando cumpre todos os pontos aplicáveis:

- O baseline de caracterização estava verde antes de introduzir o teste novo.
- O teste RED falhou pelo motivo esperado.
- A implementação mínima tornou o teste verde.
- Qualquer teste temporário removido possui cobertura equivalente no contrato novo.
- Nenhum teste existente regrediu.
- A query inclui `organization_id`.
- A tabela tenant-owned possui RLS forçada.
- O serviço não faz commit interno.
- O erro usa código estável.
- O frontend mostra loading, erro, vazio e sucesso aplicáveis.
- O fluxo funciona por teclado.
- A copy distingue simulação, Bases e prontidão.
- A documentação referencia comportamento implementado.
- Os gates relevantes foram executados.

## 12. Matriz de rastreabilidade

| Requisito funcional | WBS | Evidência principal |
| :--- | :--- | :--- |
| Fundação monotónica | 9.1 e 9.2 | Migration, trigger e testes transacionais |
| Draft multi-dispositivo | 9.2.2 e 9.4.2 | API versionada e autosave |
| Bloqueio backend | 9.3 | Teste de allowlist e routers |
| Guia sem dados reais | 9.5.4 | Teste de fronteira de rede |
| Todas as combinações de skip | 8.4 e 9.5.2 | Enumeração determinística de `2^n` sequências completas |
| Dashboard de preparação | 9.7.5 | União Pydantic discriminada e testes dos dois consumidores frontend |
| Cadeia coerente | 9.7.1 | Query cumulativa e testes cross-tenant |
| Preflight único e read-only | 9.7.2 e 9.7.3 | `PreflightReport` comum e testes que proíbem sync e writes |
| Matriz neutra completa | 9.6 | Inspector puro, reparador transacional e testes de ausência sem escrita |
| Escrita apenas self | 9.6.5 | Contratos `me` e testes de capacidades |
| Ativação permanente | 9.8 | Aprovação transacional e reset anual |
| Telemetria sem PII e append-only | 4.3 e 9.9 | `tutorial_run_id`, schema fechado, ACL e trigger |
| Migração previsível | 9.1.2, 9.1.3 e 9.10.5 | Expand/contract, smoke reversível e cinco cenários de backfill |
| Rollout progressivo | 9.2.4 e 9.10.5 | Aliases temporários, invalidação de assets e remoção condicionada |

## 13. Limites deliberados

- A primeira versão aceita apenas grelhas uniformes.
- O tutorial não sincroniza progresso entre dispositivos.
- A prevalidation não persiste resultados.
- O tutorial não usa o solver.
- O wizard não altera o calendário.
- A sincronização de feriados permanece uma ação explícita.
- Não existe importação em massa.
- Não existe revisão isolada de passos do tutorial.
- Não existe identidade persistente de fundador.

Adicione grelhas irregulares apenas após evolução explícita do modelo de timeslots.

Adicione persistência remota do tutorial apenas após requisito multi-dispositivo.

## 14. Modos de falha e recuperação

| Falha | Resultado obrigatório | Recuperação |
| :--- | :--- | :--- |
| Versão de draft obsoleta | `409 FOUNDATION_DRAFT_VERSION_CONFLICT` | Recarregar o snapshot atual |
| Conclusão parcial | Rollback integral | Corrigir o erro e repetir com o mesmo draft |
| Grelha irregular legada | Fundação `IN_PROGRESS` | Substituir por grelha uniforme |
| Dependência protegida da grelha | `409` com blocker específico | Resolver draft ou operação pendente |
| Estado local tutorial inválido | Reinício local controlado | Registar parsing e continuar |
| Telemetria indisponível | Guia continua | Registar erro; não alterar progresso |
| Linha ausente num percurso read-only | Valor neutro em memória; zero writes | Emitir anomalia estruturada e continuar |
| Linha ausente na mutação seguinte | Reparação neutra na mesma transação | Fazer rollback conjunto se a mutação falhar |
| Fingerprint alterado durante prevalidation | `409 PREFLIGHT_STALE` | Recalcular Bases e repetir |
| Falha RLS ou trigger | Gate CI falha | Corrigir migration antes do deploy |

Nunca apresente dados fictícios como recuperação de uma falha backend.

## 15. Referências técnicas

- [System Architecture](SYSTEM_ARCHITECTURE.md)
- [Data Model](DATA_MODEL.md)
- [School Configuration](../02_domain_model/SCHOOL_CONFIGURATION.md)
- [Scheduler Architecture](../03_scheduler_engine/SCHEDULER_ARCHITECTURE.md)
- [Backend Architecture](../05_backend_api/BACKEND_ARCHITECTURE.md)
- [Frontend Architecture](../06_frontend_ux/FRONTEND_ARCHITECTURE.md)
- [Testing and CI](../08_security_quality/TESTING_AND_CI.md)
- [Security and Tenant Isolation](../08_security_quality/SECURITY_AND_TENANT_ISOLATION.md)
