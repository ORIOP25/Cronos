# WBS Técnico de Correção — Onboarding In-App do Diretor

## 1. Finalidade

Este documento transforma a auditoria da implementação do plano `DIRECTOR_ONBOARDING_WBS.md` num plano de correção executável.

O estado auditado é **NO-GO**. A implementação não pode ser integrada nem promovida enquanto os gates P0 deste documento não estiverem concluídos.

Este WBS não autoriza atalhos funcionais. O contrato alvo continua a ser o contrato fechado no plano original: fundação com nove passos, guia local com vinte e quatro passos, disponibilidade neutra, readiness coerente, preflight sem efeitos laterais, dashboard discriminado e telemetria append-only.

### 1.1 Resultado observado em 2026-08-21

| Verificação | Resultado auditado |
| :--- | :--- |
| Novos testes backend | `20 passed in 37.24s` numa PostgreSQL `cronos_ci_db` descartável |
| Suite backend sem Redis, equivalente à seleção principal da CI | `133 failed, 444 passed, 1 deselected` |
| Teste dirigido do seed operacional | Falha com `NameError: datetime is not defined` |
| `alembic check` como migrador | Falha com quatro alterações de tipo e um índice por migrar |
| Smoke `upgrade -> downgrade base -> upgrade` | Passa |
| `audit_triggers.py` | Passa, mas não deteta as invariantes de `INSERT`/`DELETE` em falta |
| `audit_database_integrity.py` | Passa, mas não deteta o drift identificado pelo Alembic |
| Vitest sem cobertura | `54` ficheiros e `273` testes passam |
| Vitest com cobertura, exatamente como a CI | `1 failed, 272 passed`; `AppRoutes.test.jsx` é dependente de ordem/estado global |
| ESLint | Falha com `13` erros |
| Knip | Falha com quatro ficheiros e um export não usados; em produção falha com cinco ficheiros |
| Build Vite | Passa |
| Build das páginas de marketing | Passa |
| Estabilidade de configuração escolar | Passa nas repetições configuradas |
| CI em `push` | Executa apenas para `main` e `develop`; não executa na branch auditada `codex/update-onboarding` |
| E2E específicos do novo onboarding | Não existem |
| `walkthrough.md` referido no resumo | Não existe no repositório, incluindo ficheiros ignorados |

### 1.2 Interpretação dos resultados

Os `20/20` novos testes não constituem uma verificação integral. Eles cobrem apenas os cenários escritos para a implementação nova. A suite existente demonstra regressões sistémicas, sobretudo porque o gate de fundação passou a bloquear organizações de teste que não declaram a pré-condição `COMPLETED`.

Os scripts de auditoria de base de dados também não substituem `alembic check`: passaram apesar de existir drift real entre metadata SQLAlchemy e a migration.

## 2. Regras obrigatórias de engenharia

### 2.1 Clean Architecture

1. Routers FastAPI validam HTTP, resolvem o ator e delegam; não contêm regras de persistência.
2. Serviços de aplicação recebem `AsyncSession`, executam a unidade de trabalho e fazem apenas `flush`; o limite HTTP controla `commit`/`rollback`.
3. Regras de domínio e reducers puros não importam FastAPI, React Query, Clerk, `apiClient` ou SQLAlchemy quando não precisam de infraestrutura.
4. `SessionActor`, `FoundationAdminActor`, `ActiveActor` e `AdminActor` têm responsabilidades distintas; não se reutiliza um gate operacional numa rota de bootstrap.
5. Readiness, prevalidation, erro de geração e pedido real de geração usam um único `PreflightService.evaluate()` e os mesmos `PreflightIssue`/`PreflightReport`.
6. Inspeção de disponibilidade é read-only. Reparação de disponibilidade é um comando explícito dentro de uma transação mutável.
7. A API do dashboard devolve uma união discriminada. O frontend não reconstrói o modo com uma segunda fonte de dados.
8. Telemetria é persistida por um serviço de aplicação pequeno; o router não constrói diretamente modelos ORM.

### 2.2 Clean Code

1. Não silenciar exceções, violações de invariantes, parsing inválido ou falhas de telemetria sem registar o erro completo.
2. Não usar `datetime.now()` para mascarar um `foundation_completed_at` inválido já persistido.
3. Não manter dois contratos para preflight, dois serviços de conclusão ou dois estados de onboarding.
4. Remover imports, exports, ficheiros e componentes mortos apenas depois de confirmar que não são adapters temporários exigidos pelo rollout.
5. Proibir payloads extra com Pydantic `ConfigDict(extra="forbid")` nos comandos de fundação e telemetria.
6. Usar nomes estáveis de erro em maiúsculas: `FOUNDATION_REQUIRED`, `FOUNDATION_DRAFT_VERSION_CONFLICT`, `PREFLIGHT_STALE` e os códigos de `PreflightIssue`.
7. Não usar índices de arrays como `key` quando existe `code`, `stepId` ou outro identificador estável.
8. Não introduzir comentários que descrevem comportamento diferente do código.

### 2.3 TDD obrigatório

Cada item deste WBS segue esta sequência:

1. Escrever ou corrigir um teste que falha pelo motivo funcional esperado.
2. Executar apenas o teste dirigido e registar o estado **RED**.
3. Aplicar a alteração mínima que satisfaz o contrato.
4. Executar o teste dirigido e registar o estado **GREEN**.
5. Executar a suite do subsistema afetado.
6. Refatorar apenas com a suite verde.
7. Executar os gates globais antes de iniciar a fase dependente.

É proibido:

- Alterar uma asserção para aceitar o comportamento incorreto.
- Marcar testes como `skip`, `xfail`, `todo` ou reduzir thresholds.
- Copiar SQL da migration para o teste e chamar isso um teste de migration.
- Marcar testes puros como PostgreSQL apenas para reutilizar uma fixture global.
- Tornar todas as organizações implicitamente completas no código de produção para fazer a suite passar.

As fixtures operacionais existentes devem declarar `foundation_status=COMPLETED` e `foundation_completed_at` porque esses testes exercitam módulos pós-fundação. Os testes do gate devem usar fixtures separadas e explicitamente incompletas.

### 2.4 Ponytail ultra

1. Não adicionar dependências npm ou Python.
2. Não criar repositories, buses, factories ou interfaces sem dois consumidores reais.
3. Reutilizar `SchedulerFingerprintService`, `SchedulerStateService`, os serviços de settings, React Query e os componentes guiados existentes.
4. Substituir implementações duplicadas em vez de criar uma terceira camada de compatibilidade.
5. Usar um reducer puro para a fundação e um reducer puro para o tutorial; não adicionar Redux ou outra store.
6. Manter o adapter HTTP antigo apenas durante a janela de rollout definida; removê-lo na release de contração.
7. Não simplificar RLS, concorrência, idempotência, rate limit ou invariantes de base de dados.

## 3. Registo de desvios auditados

| ID | Prioridade | Desvio |
| :--- | :--- | :--- |
| `AUD-001` | P0 | O workflow só reage a pushes em `main`/`develop`; os ficheiros novos estão untracked e não seriam enviados num push atual. |
| `AUD-002` | P0 | A CI frontend falha em ESLint, Knip e na execução Vitest com cobertura. |
| `AUD-003` | P0 | A CI backend falha em `alembic check`, no seed operacional e em `133` testes sem Redis. |
| `AUD-004` | P0 | ORM e migration divergem em `SmallInteger/Integer`, `JSONB/JSON`, `BigInteger/Integer`, `chapter` e índice de organização. |
| `AUD-005` | P0 | É possível inserir `COMPLETED` sem timestamp; o trigger de delete devolve `NEW` e suprime silenciosamente deletes válidos. |
| `AUD-006` | P0 | `organization_foundation_draft.updated_by_membership_id` é nullable e não tem FK composta tenant-scoped. |
| `AUD-007` | P0 | `/members/me` usa `ActiveActor` e não devolve `foundation_status`; o frontend pode encaminhar um admin incompleto para `/create-org`. |
| `AUD-008` | P0 | O gate devolve `403 ORGANIZATION_FOUNDATION_REQUIRED`, em divergência com `409 FOUNDATION_REQUIRED`. |
| `AUD-009` | P0 | O onboarding legado continua a concluir por um serviço independente e ainda escreve metadata Clerk. |
| `AUD-010` | P0 | O wizard tem quatro passos, não nove; persiste o passo de origem, não aguarda o save e permite overwrite após conflito. |
| `AUD-011` | P0 | O serviço novo de preflight não é usado pelo comando real; o percurso antigo ainda sincroniza feriados e devolve strings. |
| `AUD-012` | P0 | O pacote de disponibilidade neutra, inspeção/reparação e permissões self-service não foi implementado. |
| `AUD-013` | P0 | A primeira aprovação lê a organização sem `FOR UPDATE`; concorrência pode fazer a segunda transação falhar no trigger. |
| `AUD-014` | P1 | O dashboard backend não é discriminado e o frontend faz queries paralelas para inferir o modo. |
| `AUD-015` | P1 | O tutorial tem dez slides informativos, não vinte e quatro exercícios; não existe prova das 131072 composições de skip. |
| `AUD-016` | P1 | A chave local do tutorial não inclui utilizador, não retoma corretamente o run e silencia erros de storage/telemetria. |
| `AUD-017` | P1 | A copy do tutorial descreve valores de disponibilidade incorretos e sugere sincronização/execução que não ocorre. |
| `AUD-018` | P1 | A telemetria está no router, não tem rate limit, aceita campos extra por omissão e responde `200`, não `204`. |
| `AUD-019` | P1 | O backfill valida apenas a presença parcial de settings/timeslots e o teste volta a executar uma cópia do SQL. |
| `AUD-020` | P1 | Não existem os E2E separados de fundação, tutorial local/rede, readiness, modos de dashboard e reset anual. |
| `AUD-021` | P1 | O resumo de implementação refere um `walkthrough.md` inexistente. |

## 4. Decisões de correção fechadas

### 4.1 Contratos que não podem ser alterados para acomodar a implementação

1. O wizard tem exatamente nove passos: período, dias, abertura, duração, intervalo, almoço, preview, calendário e confirmação.
2. `current_step` está entre `1` e `9` em Pydantic, ORM, migration, reducer e testes.
3. O guia tem exatamente vinte e quatro passos, dezassete deles skippable, e a suite percorre `2 ** 17 = 131072` combinações.
4. O gate operacional usa HTTP `409` e `detail.code="FOUNDATION_REQUIRED"`.
5. `/members/me`, bootstrap e rotas de fundação permanecem acessíveis antes da conclusão.
6. O backend resolve o ano letivo ativo e usa `COMPLETE_GENERATION`; o browser não envia `school_year_id` para readiness.
7. `GET`, fingerprint, readiness e prevalidation nunca escrevem nem sincronizam feriados.
8. A telemetria responde `204` tanto em insert como em duplicado idempotente.
9. A primeira aprovação real é permanente e só é escrita no ramo `COMPLETE_GENERATION`.
10. A existência de um novo ano letivo não reabre fundação nem guia automaticamente.

### 4.2 Tipos persistidos canónicos

| Campo | Tipo canónico |
| :--- | :--- |
| `organization_foundation_draft.version` | `Integer`, `CHECK version > 0` |
| `organization_foundation_draft.current_step` | `SmallInteger`, `CHECK current_step BETWEEN 1 AND 9` |
| `organization_foundation_draft.payload_json` | PostgreSQL `JSONB` |
| `organization_foundation_draft.updated_by_membership_id` | `Integer NOT NULL`, FK composta com `organization_id` |
| `tutorial_telemetry_event.id` | `BigInteger` autoincremental |
| `tutorial_telemetry_event.chapter` | `SmallInteger`, nullable, limitado a `1` ou `2` |
| `tutorial_telemetry_event.organization_id` | `Integer`, FK tenant-scoped e indexado uma única vez |

## 5. Work Breakdown Structure de correção

### 5.0 Congelar evidência e recuperar o baseline executável

#### 5.0.1 Preservar o snapshot auditado

**Dependências:** nenhuma.

**Trabalho:**

1. Guardar o output dos gates num artefacto de CI ou comentário de PR; não adicionar logs efémeros ao repositório.
2. Confirmar que o documento original e este WBS são os contratos de implementação.
3. Inventariar todos os ficheiros modified/untracked e excluir explicitamente o documento comercial `.docx` do commit técnico.
4. Não declarar a implementação concluída enquanto existirem ficheiros técnicos untracked.

**Aceitação:** a PR mostra apenas código, migrations, testes e documentação pertencentes a este pacote.

#### 5.0.2 Criar fixtures de fundação explícitas

**Dependências:** 5.0.1.

**Ficheiros principais:** `backend/tests/conftest.py`, factories de teste que criam organizações e headers autenticados.

**Testes RED:** executar uma amostra de cada router operacional e confirmar que falha hoje com `409/403` por usar uma organização `NOT_STARTED` implícita.

**Trabalho:**

1. Criar helper `create_completed_organization(...)` que define `foundation_status=COMPLETED` e um `foundation_completed_at` fixo.
2. Fazer as fixtures operacionais existentes usarem esse helper.
3. Criar helpers separados `create_not_started_organization(...)` e `create_in_progress_organization(...)` apenas para testes de fundação/gate.
4. Não alterar defaults de produção.
5. Atualizar `test_migration_tenant_ref_contract.py` para preservar o hash/imutabilidade da baseline histórica e reconhecer `0004` como migration incremental legítima.

**Aceitação:** a suite existente deixa de falhar por pré-condições implícitas, mas os testes dedicados continuam a provar o bloqueio de organizações incompletas.

#### 5.0.3 Recuperar qualidade estática antes de trabalho funcional

**Dependências:** 5.0.2.

**Trabalho:**

1. Importar `UTC` e `datetime` em `operational_seed_service.py` ou reutilizar o helper temporal já usado no módulo; não duplicar relógios.
2. Remover imports Python/React não usados, incluindo `FoundationAlreadyCompletedError`, `TUTORIAL_VERSION`, `completed`, `CBadge` e imports React desnecessários.
3. Decidir os ficheiros antigos de onboarding: se forem substituídos, removê-los com os respetivos exports; se forem adapter de rollout, referenciá-los explicitamente. Não os deixar mortos.
4. Executar format e lint com as versões locked da CI.
5. Corrigir isolamento de metadata em `AppRoutes.test.jsx`: cada teste restaura `document.title`, description, canonical e mocks no `afterEach`; não aumentar timeouts.

**Gates:**

```powershell
cd backend
ruff format --check .
ruff check .
pytest tests/test_operational_seed.py -q

cd ../frontend
npm run lint
npm run lint:dead-code
npm run lint:dead-code:production
npm run test:coverage
```

**Aceitação:** os quatro comandos frontend e os três comandos backend terminam com exit code `0`.

### 5.1 Corrigir persistência, migration e integridade

#### 5.1.1 Fazer ORM e migration convergir

**Dependências:** 5.0.3.

**Testes RED:**

1. Executar `alembic upgrade head && alembic check` e conservar as cinco operações detetadas como prova RED.
2. Adicionar testes de introspeção PostgreSQL para os tipos canónicos da secção 4.2.
3. Testar os nomes exatos de PK, unique, índices e FKs.

**Trabalho:**

1. Como `0004_foundation_telemetry.py` ainda está untracked e não existe evidência de deployment, corrigir a própria `0004`; não criar uma migration corretiva artificial. Se surgir evidência de que `0004` já foi aplicada fora de ambientes descartáveis, parar esta tarefa e criar uma migration forward-only em vez de reescrever histórico aplicado.
2. Alterar `OrganizationFoundationDraft.current_step` para `SmallInteger` no ORM.
3. Alterar `payload_json` para `postgresql.JSONB` no ORM.
4. Alterar `TutorialTelemetryEvent.id` para `BigInteger` no ORM.
5. Alterar `chapter` para `SmallInteger` no ORM.
6. Remover `index=True` implícito de `organization_id` ou materializar o índice com o mesmo nome na migration; manter uma única definição.
7. Alinhar `server_default`, nulabilidade e nomes de constraints para que autogenerate não proponha alterações.

**Aceitação:** `alembic check` devolve `No new upgrade operations detected`.

#### 5.1.2 Fechar constraints tenant-scoped do draft

**Dependências:** 5.1.1.

**Testes RED:**

1. `version=0` falha com SQLSTATE `23514`.
2. `current_step=0` e `current_step=10` falham.
3. Membership de outra organização falha.
4. Membership nula falha.
5. Membership da mesma organização é aceite.

**Trabalho:**

1. Adicionar `CHECK (version > 0)`.
2. Adicionar `CHECK (current_step BETWEEN 1 AND 9)`.
3. Tornar `updated_by_membership_id` não nulo.
4. Criar FK composta `(organization_id, updated_by_membership_id) -> organization_membership(organization_id, id)`.
5. Usar `ON DELETE RESTRICT`; não usar `SET NULL` num campo auditável obrigatório.
6. No backfill de draft, escolher deterministicamente o menor membership ativo com capacidade admin da própria organização.
7. Fazer a migration abortar com organização identificada quando um caso `IN_PROGRESS` não tem admin elegível; não inserir `NULL`.

#### 5.1.3 Corrigir invariantes da organização e semântica do trigger

**Dependências:** 5.1.1.

**Testes RED:**

1. `INSERT COMPLETED` sem `foundation_completed_at` falha.
2. `INSERT` com `first_real_schedule_approved_at` e fundação incompleta falha.
3. `UPDATE COMPLETED -> IN_PROGRESS` falha.
4. Alterar/remover qualquer timestamp permanente falha.
5. Delete de organização `NOT_STARTED` realmente remove uma linha.
6. Delete de organização concluída falha explicitamente.

**Trabalho:**

1. Adicionar `CHECK` para `COMPLETED -> foundation_completed_at IS NOT NULL`.
2. Adicionar `CHECK` para `first_real_schedule_approved_at IS NULL OR foundation_status='COMPLETED'`.
3. Manter o trigger para monotonicidade e imutabilidade em updates.
4. No ramo `DELETE`, devolver `OLD` quando o delete é permitido.
5. Não devolver `NEW` num trigger `BEFORE DELETE`.
6. Estender `audit_triggers.py` para verificar eventos do trigger (`UPDATE OR DELETE`) e o corpo/retorno esperado.
7. Estender `audit_database_integrity.py` para verificar as duas `CHECK`, a FK composta, nulabilidade, tipos e ACLs.

#### 5.1.4 Corrigir RLS e ACLs

**Dependências:** 5.1.2 e 5.1.3.

**Testes RED:**

1. `cronos_app` não lê/escreve draft de outro tenant.
2. `cronos_app` só insere e lê telemetria da organização atual.
3. `UPDATE` e `DELETE` de telemetria falham por ACL e, após grant temporário no teste, falham pelo trigger.
4. A sequence da telemetria funciona sem conceder acesso global a todas as sequences.

**Trabalho:**

1. Adicionar as tabelas novas à matriz existente em `test_rls_database_policies.py` e `test_tenant_isolation_complete.py`.
2. Substituir `GRANT ... ON ALL SEQUENCES` por grant apenas na sequence de telemetria.
3. Verificar `ENABLE ROW LEVEL SECURITY` e `FORCE ROW LEVEL SECURITY`.
4. Separar policies por operação quando isso tornar `WITH CHECK` e `USING` explícitos; não usar uma policy ampla sem testes de cada operação.

#### 5.1.5 Reescrever o teste de backfill para executar a migration real

**Dependências:** 5.1.4.

**Trabalho:**

1. Criar a base em revisão `0003`.
2. Inserir os cinco cenários: aprovação histórica, configuração válida uniforme, parcial, irregular e vazia.
3. Executar `alembic upgrade 0004_foundation_telemetry` pelo API Alembic.
4. Não copiar o SQL de classificação para o teste.
5. Validar a primeira aprovação por `decided_at`, fallback por menor `active_schedule_blocks.created_at`, estado, timestamps e criação de draft apenas em `IN_PROGRESS`.
6. Validar período, estabilidade, almoço, sequência uniforme por dia, duração positiva e intervalos uniformes.
7. Executar novo upgrade sem reabrir entidades concluídas.
8. Testar `upgrade -> downgrade -> upgrade`, funções bootstrap, owner, `search_path`, revoke e grants.

**Gate da fase:** migrations, audits, testes RLS e `alembic check` passam numa base vazia descartável e com os papéis reais da CI.

### 5.2 Corrigir serviço de fundação, contratos HTTP e rollout

#### 5.2.1 Fechar schemas Pydantic

**Dependências:** 5.1.

**Testes RED:**

1. Campo extra em draft ou telemetria devolve `422`.
2. `current_step=10` devolve `422`.
3. `confirmed=false` devolve `422` antes de chamar o serviço.
4. Dias duplicados/fora do domínio, datas invertidas, grelha impossível e janelas incompatíveis falham.

**Trabalho:**

1. Aplicar `ConfigDict(extra="forbid")` a `FoundationDraftData`, `FoundationDraftWrite`, `FoundationCompleteCommand` e `TutorialTelemetryEventCreate`.
2. Definir `current_step: Field(ge=1, le=9)`.
3. Definir `confirmed: Literal[True]` sem default permissivo.
4. Reutilizar os validators canónicos de configuração/grelha; não duplicar fórmulas divergentes no frontend e backend.
5. Tornar `membership_id` obrigatório nos comandos de escrita da fundação.

#### 5.2.2 Fortalecer `FoundationService`

**Dependências:** 5.2.1.

**Testes RED:**

1. Falha no upsert de settings faz rollback total.
2. Falha na geração da grelha faz rollback total.
3. Zero timeslots não completa a organização.
4. Duas conclusões concorrentes produzem uma conclusão e uma resposta idempotente consistente.
5. Organização `COMPLETED` com timestamp nulo gera erro de integridade, não um timestamp inventado.
6. Draft de outro tenant nunca é lido por engano.

**Trabalho:**

1. Manter `FOR UPDATE` na organização e no draft.
2. Extrair apenas uma função pura de validação do snapshot completo se isso eliminar a lista manual; não criar uma nova camada.
3. Remover `FoundationAlreadyCompletedError` se não existir transição que o utilize.
4. Na resposta idempotente, exigir o timestamp persistido e contar a grelha existente; não usar `datetime.now()` como fallback.
5. Manter `flush` no serviço e um único commit no limite de request.
6. Encadear `HTTPException` com `raise ... from exc` para satisfazer Ruff e preservar causa.

#### 5.2.3 Corrigir gate e bootstrap de sessão

**Dependências:** 5.2.2.

**Trabalho:**

1. Fazer `ActiveActor` devolver HTTP `409` com `FOUNDATION_REQUIRED`.
2. Mudar `GET /members/me` de `ActiveActor` para `SessionActor`.
3. Adicionar `foundation_status` a `CurrentMemberRead` e preencher a partir da organização.
4. Manter `FoundationAdminActor` sem o gate operacional para draft/complete.
5. Garantir que o bootstrap devolve o mesmo enum e nunca infere conclusão pela presença de settings.
6. Criar teste parametrizado de allowlist e teste parametrizado com uma rota por router tenant-owned.
7. Criar uma verificação que falha quando uma nova rota tenant-owned não declara explicitamente um dos atores permitidos.

**Aceitação:** admin incompleto abre `/foundation`, membro incompleto consulta `/members/me`, não admin incompleto abre waiting, e qualquer operação de domínio devolve `409 FOUNDATION_REQUIRED`.

#### 5.2.4 Transformar onboarding antigo em adapter real

**Dependências:** 5.2.2.

**Trabalho:**

1. Remover a regra independente `complete_onboarding`.
2. Fazer `POST /onboarding` traduzir o contrato antigo e delegar na mesma unidade de trabalho do `FoundationService`.
3. Fazer `GET /onboarding/status` ler `organization.foundation_status`.
4. Remover `mark_onboarding_complete_in_clerk` e toda a escrita `public_metadata.onboardingComplete`.
5. Adicionar `Deprecation: true` e `Sunset` com data concreta da release de contração.
6. Se o payload antigo não contém todos os dados necessários, responder com erro compatível e instrução de upgrade; nunca marcar `COMPLETED` sem grelha válida.
7. Manter o wrapper SQL `bootstrap_founder` apenas durante a janela expand/contract e verificar ambos os consumidores runtime na função nova.

### 5.3 Corrigir o wizard e encaminhamento frontend

#### 5.3.1 Implementar o reducer puro de nove passos

**Dependências:** 5.2.3.

**Ficheiros:** `foundationModel.js`, `foundationData.js`, `foundationModel.test.js` e componentes de passo.

**Trabalho:**

1. Definir os nove passos fechados e identificadores estáveis.
2. Fazer cada passo validar apenas os campos que introduz.
3. Fazer confirmação validar o snapshot completo.
4. Alinhar estabilidade, duração, intervalos e dias com os validators backend.
5. Remover o tutorial do wizard; preview e calendário são read-only.
6. Exigir checkbox explícito antes de ativar.

#### 5.3.2 Implementar autosave serializado e navegação confirmada

**Dependências:** 5.3.1.

**Testes RED obrigatórios:**

1. Alterações rápidas geram um único save após `600 ms`.
2. Nunca existem dois `PUT` em voo.
3. `Continue` do passo quatro envia `current_step=5`, mantém passo quatro visível e só avança após `200`.
4. `Back` usa a mesma regra com o passo de destino.
5. `409` mantém passo e valores, congela edição e não navega.
6. Retry usa uma versão confirmada; reload descarta local e hidrata remoto.
7. Saída persiste o passo visível antes de navegar.

**Trabalho:**

1. Substituir `dispatch NEXT/PREV + void saveCurrentDraft()` por um comando `persistDestination(destinationStep)` aguardado.
2. Guardar a versão confirmada num único local do reducer/hook.
3. Enfileirar um snapshot pendente quando surgem alterações durante um request.
4. Remover overwrite/merge do modal de conflito.
5. Remover o campo artificial `_dismiss`; fechar o modal através de uma transição explícita que mantém o estado coerente.
6. Desativar navegação e conclusão durante save forçado.
7. Implementar `role=status`, `role=alert` e gestão de foco no título do passo.

#### 5.3.3 Corrigir rotas e ecrã de espera

**Dependências:** 5.3.2.

**Trabalho:**

1. Expor `/foundation` como rota canónica.
2. Manter `/onboarding` apenas como redirect temporário para assets antigos.
3. Criar `/foundation/waiting` sem controlos administrativos.
4. No guard, aguardar Clerk, organização, `/members/me` e foundation antes de decidir.
5. Aplicar a ordem de encaminhamento da secção 7 do WBS original.
6. No waiting, refetch em foco e a cada `30 s`; parar polling depois de `COMPLETED`.

### 5.4 Implementar disponibilidade neutra e permissões corretas

#### 5.4.1 Criar inspector puro e repair service explícito

**Dependências:** 5.1.4.

**Ficheiro:** `backend/app/services/availability_matrix_service.py`.

**Trabalho:**

1. Implementar `AvailabilityMatrixInspector.inspect(organization_id, teacher_ids, timeslot_ids)` como leitura pura.
2. Interpretar célula ausente como `PreferenceLevel.NEUTRAL.value` e devolver anomalias separadas.
3. Considerar apenas `IMPOSSIBLE=-1` como indisponibilidade rígida.
4. Implementar `AvailabilityMatrixRepairService.repair(...)` sem commit.
5. Invocar reparação apenas em criação de professor, regeneração de grelha e fronteira de geração real.
6. Em geração real: bloquear contexto, reparar, `flush`, recalcular fingerprint, executar preflight e criar job; qualquer blocker faz rollback de tudo.

**Testes RED:** snapshots SQL antes/depois provam zero writes em inspector, GET, fingerprint, readiness e preflight; a mutação seguinte repara as células neutras.

#### 5.4.2 Fechar API de disponibilidade

**Dependências:** 5.4.1.

**Trabalho:**

1. Substituir escrita administrativa por `PUT /teachers/me/availability`.
2. Derivar `teacher_id` do ator e rejeitar o campo no payload.
3. Exigir uma célula por timeslot atual, sem duplicados nem IDs externos.
4. Manter `GET /teachers/me/availability` para professor.
5. Criar `GET /teachers/{teacher_id}/availability` administrativo read-only.
6. Remover `POST /teachers/{teacher_id}/availability` após atualizar o frontend e testes.
7. Atualizar `MyAvailability` e a ficha read-only do professor.

### 5.5 Unificar Bases, readiness, preflight e geração

#### 5.5.1 Implementar o predicado cumulativo de sete níveis

**Dependências:** 5.4.

**Trabalho:**

1. Criar `SchoolReadinessService` com sete queries cumulativas sobre a mesma cadeia tenant-scoped.
2. Calcular apenas percentagens `0, 14, 28, 42, 57, 71, 85, 100` pelo maior prefixo coerente.
3. Não somar seis booleanos independentes.
4. Validar sala compatível/capacidade, competências, associações e disponibilidade não impossível na cadeia real.
5. Resolver o ano letivo ativo com API read-only.
6. Calcular fingerprint apenas com depth sete, ano ativo e `COMPLETE_GENERATION`.
7. Devolver `ACTIVE_SCHOOL_YEAR_REQUIRED` sem invocar fingerprint quando falta ano ativo.

#### 5.5.2 Criar um único contrato de preflight

**Dependências:** 5.5.1.

**Trabalho:**

1. Definir `PreflightIssue(code, severity, message, route)` e `PreflightReport(status, fingerprint, issues)` uma única vez.
2. Tornar `PreflightService.evaluate(...)` a única API pública.
3. Remover a importação privada `_preflight_check` do `scheduler_request_service.py`.
4. Atualizar ambos os call sites do pedido real de geração.
5. Remover `_ensure_auto_holidays`, refresh pós-sincronização e qualquer write do preflight.
6. Tratar feriados não sincronizados como `WARNING`; manter sync como comando explícito.
7. Usar a mesma tabela testada de severidades em readiness, prevalidation e geração.
8. Serializar o report no erro HTTP; remover `problems: list[str]`.
9. Atualizar `PreflightErrorPanel` para `issue.code` como key, severidade visual e link `route`.

**Aceitação:** `rg -n "_preflight_check|problems"` não encontra o contrato legado nos consumidores; monkeypatch de qualquer função de sync falha se um percurso GET/preflight a chamar.

#### 5.5.3 Implementar endpoints e concorrência de readiness

**Dependências:** 5.5.2.

**Trabalho:**

1. Expor `GET /readiness/bases` e `GET /readiness/prevalidation?fingerprint=...`.
2. Não aceitar `school_year_id` do browser.
3. Calcular fingerprint inicial e final; devolver `409 PREFLIGHT_STALE` se o token recebido ou o final divergir.
4. Reexecutar sempre o preflight no servidor antes de criar o job; cache React Query é apenas apresentação.
5. Criar hooks de readiness com keys por organização/fingerprint e `refetchOnWindowFocus: true`.
6. Invalidar bases, prevalidation e dashboard após mutações de catálogo, membros, configuração, operações e scheduling.
7. Não invalidar por telemetria ou preferências visuais.

### 5.6 Corrigir primeira aprovação e dashboard discriminado

#### 5.6.1 Tornar o marcador de primeira aprovação concorrente e transacional

**Dependências:** 5.2.2 e 5.5.2.

**Trabalho:**

1. No ramo `COMPLETE_GENERATION`, selecionar a organização com `FOR UPDATE` antes de testar o marcador.
2. Exigir `foundation_status=COMPLETED`.
3. Usar o mesmo `instant` de `draft.decided_at`.
4. Preencher apenas quando nulo.
5. Não tocar no marcador em `ADAPTIVE_REPAIR`, segunda época ou reset anual.
6. Manter a escrita na mesma transação da promoção do draft.

**Testes RED:** primeira aprovação, duas aprovações concorrentes, reparação, segunda época, falha de promoção e reset anual.

#### 5.6.2 Implementar união discriminada do dashboard

**Dependências:** 5.5.3 e 5.6.1.

**Trabalho:**

1. Substituir `DashboardV1Response` por `PreparationDashboardResponse | OperationalDashboardResponse` discriminada por `mode`.
2. Devolver `PREPARATION` enquanto `first_real_schedule_approved_at` é nulo.
3. Devolver `OPERATIONAL` depois da primeira aprovação e preservar todos os widgets existentes.
4. Incluir readiness estruturado no modo de preparação.
5. Fazer `Dashboard.jsx` depender apenas de `useDashboard` e executar switch exaustivo por `mode`.
6. Rejeitar modo desconhecido como erro de contrato; não fazer fallback.
7. Remover a query paralela de foundation usada apenas para inferir modo.

**Testes RED:** OpenAPI discriminator, respostas exclusivas dos dois modos, hook, componentes e modo desconhecido.

### 5.7 Reconstruir tutorial local e telemetria

#### 5.7.1 Corrigir storyboard, cenário e copy

**Dependências:** 5.3.3.

**Trabalho:**

1. Implementar os vinte e quatro `stepId` fechados na secção 8.3 do WBS original.
2. Definir cenário local com dois cursos, três turmas, cinco disciplinas, quatro professores, três salas, grelha, horário aprovado, ocorrência e reparação.
3. Prefixar IDs com `demo-`.
4. Mostrar sempre “Simulação”.
5. Não afirmar que o solver executou ou encontrou um ótimo.
6. Não afirmar que feriados são sincronizados automaticamente.
7. Descrever os valores reais: `PREFERRED=2`, `NEUTRAL=1`, `AVOID=0`, `IMPOSSIBLE=-1`.
8. Separar `tutorialScenario.js`, `tutorialModel.js` e `tutorialStorage.js`; remover o motor/slides substituídos.

#### 5.7.2 Provar todas as composições e a fronteira local

**Dependências:** 5.7.1.

**Testes RED:**

1. Derivar `SKIPPABLE_STEP_IDS` do cenário e exigir comprimento `17`.
2. Percorrer deterministicamente as `131072` máscaras.
3. Validar invariantes depois de cada transição e pré-condições do passo seguinte.
4. Exigir estado final `COMPLETED`, dívida preservada e histórico de reparação intacto.
5. Falhar imports de `apiClient`, Clerk, scheduler ou hooks de dados reais dentro do tutorial.
6. Completar o guia com worker/scheduler indisponível.

#### 5.7.3 Corrigir storage, retoma, saída e repetição

**Dependências:** 5.7.2.

**Trabalho:**

1. Usar `cronos:tutorial:v{version}:user:{clerkUserId}:org:{clerkOrgId}`.
2. Validar o JSON lido; registar parsing completo e reiniciar apenas estado inválido.
3. Persistir `NOT_STARTED`, `IN_PROGRESS`, `COMPLETED` e `SKIPPED`.
4. Primeiro open cria/persiste `tutorialRunId` antes da telemetria.
5. Resume preserva o run e checkpoint.
6. Saída temporária mantém `IN_PROGRESS`; “Saltar guia” define `SKIPPED`.
7. Repeat cria/persiste novo run e não apaga histórico.
8. Criar `/guide` fora do layout operacional e disponibilizar Retomar/Repetir nos dashboards.

#### 5.7.4 Encapsular e endurecer telemetria

**Dependências:** 5.1.4 e 5.7.3.

**Trabalho:**

1. Criar `TutorialTelemetryService.record(...)`; o router apenas delega.
2. Expor `POST /tutorial/telemetry` e remover `/telemetry/tutorial-event` após adapter temporário, se necessário.
3. Usar `AdminActor`, que deriva a organização e exige fundação concluída; não usar `SessionActor` nem o bypass `FoundationAdminActor` nesta rota.
4. Aplicar rate limit `60/minute` com a infraestrutura existente.
5. Derivar organização do ator.
6. Fazer `ON CONFLICT (organization_id, client_event_id) DO NOTHING`.
7. Responder `204` sem body em insert e duplicado.
8. Registar falhas frontend com o objeto de erro completo, sem bloquear a transição local.
9. Emitir os seis eventos aceites, incluindo `tutorial_repeated`.

### 5.8 Fechar cobertura, CI e rollout

#### 5.8.1 Criar E2E separados por responsabilidade

**Dependências:** 5.3, 5.5, 5.6 e 5.7.

**Ficheiros obrigatórios:**

- `frontend/e2e/foundation/foundation.spec.js`
- `frontend/e2e/tutorial/tutorial-local.spec.js`
- `frontend/e2e/tutorial/tutorial-network-boundary.spec.js`
- `frontend/e2e/readiness/first-schedule.spec.js`
- `frontend/e2e/dashboard/dashboard-modes.spec.js`
- `frontend/e2e/year-reset/no-onboarding.spec.js`

**Regras:**

1. Cada spec cria o mínimo de dados e não depende de ordem.
2. O conflito de draft usa dois contextos de browser.
3. A boundary de rede permite apenas assets, `GET /members/me`, `GET /foundation/status` e `POST /tutorial/telemetry` depois da autenticação.
4. Qualquer request inesperado falha com método, URL e `stepId`.
5. Readiness adulterado no browser não permite criar job quando o servidor encontra blocker.

#### 5.8.2 Fazer toda a suite voltar a verde

**Dependências:** 5.8.1.

**Backend:**

```powershell
cd backend
python -c "import os; from tests.db import validated_test_database_url; validated_test_database_url(os.environ.get('TEST_DATABASE_URL'))"
ruff format --check .
ruff check .
coverage run --branch -m pytest -q -m "not redis"
coverage run --branch --append -m pytest -q -m redis
coverage report --fail-under=70
alembic check
python -m scripts.audit_triggers
python -m scripts.audit_database_integrity
```

**Frontend:**

```powershell
cd frontend
npm run audit:production
npm run verify
npm run test:school-config:stability
npm run test:e2e
```

**Regras de aceitação:** zero falhas, zero skips, zero warnings Ruff/ESLint, thresholds inalterados e sem retries usados para esconder testes instáveis.

#### 5.8.3 Garantir execução em qualquer push

**Dependências:** 5.8.2.

**Ficheiro:** `.github/workflows/ci.yml`.

**Trabalho:**

1. Remover o filtro `branches: [main, develop]` de `push`, fazendo o workflow executar em qualquer branch.
2. Manter `pull_request` para `main` e `develop`.
3. Não adicionar `paths-ignore` que exclua backend, frontend, migrations, testes ou workflow.
4. Adicionar `npm run test:school-config:stability` ao job frontend.
5. Confirmar que `pytest -m "not redis"` recolhe todos os novos testes PostgreSQL e que o passo Redis mantém cobertura agregada.
6. Confirmar que `vitest run --coverage` recolhe `foundationModel`, wizard, tutorial, dashboard e contratos.
7. Confirmar que `npm run test:e2e` recolhe as seis pastas novas pelo `testDir` atual.
8. Publicar JUnit/coverage/Playwright report como artefactos em falha, usando actions já aprovadas ou a action de upload pinada; não introduzir serviço externo.
9. Configurar concurrency por `${{ github.workflow }}-${{ github.ref }}` com cancelamento de runs antigas da mesma branch.
10. Antes do push de validação, confirmar que todos os ficheiros de implementação e testes estão committed; CI não executa ficheiros untracked.

**Prova obrigatória:** um push para uma branch `codex/...` inicia os jobs `backend`, `frontend` e `e2e`, e os três terminam verdes.

#### 5.8.4 Atualizar documentação e walkthrough verificável

**Dependências:** 5.8.3.

**Trabalho:**

1. Atualizar os oito documentos controlados listados na secção 9.10.3 do WBS original.
2. Criar `walkthrough.md` apenas depois de os gates passarem.
3. Incluir no walkthrough: contratos finais, migrations, rotas, estados, comandos executados, contagens reais e limitações conhecidas.
4. Não afirmar “integralmente implementado” sem links para CI verde e E2E.
5. Documentar a data `Sunset` dos adapters e a migration futura `0005_drop_bootstrap_founder_compat`.

#### 5.8.5 Executar aceitação manual final

**Dependências:** 5.8.4.

1. Criar organização como admin e concluir nove passos.
2. Recarregar e retomar em cada passo de destino persistido.
3. Produzir conflito com dois admins e testar retry/reload sem overwrite.
4. Entrar como não admin incompleto e validar waiting.
5. Percorrer, sair, retomar, saltar e repetir o guia; inspecionar a rede.
6. Construir dados até Bases `100`, observar warnings/blockers e gerar o primeiro horário.
7. Aprovar, validar dashboard operacional e confirmar timestamp permanente.
8. Reparar horário e iniciar novo ano sem reabrir fundação/guia.
9. Validar teclado, foco, `role=status`, `role=alert`, viewport estreito e copy portuguesa.

**Aceitação:** checklist assinada com identidade/organização E2E dedicadas e sem correções manuais diretas na base.

## 6. Dependências entre pacotes

```text
5.0 baseline/qualidade
  -> 5.1 persistência e migration
      -> 5.2 fundação/gate/rollout
          -> 5.3 wizard/rotas
          -> 5.4 disponibilidade
              -> 5.5 readiness/preflight/geração
                  -> 5.6 aprovação/dashboard
          -> 5.7 tutorial/telemetria
5.3 + 5.5 + 5.6 + 5.7
  -> 5.8 E2E, suite completa, CI, docs e manual
```

Não iniciar tutorial integrado antes de existirem rotas/guard corretos. Não implementar dashboard de preparação antes do contrato único de readiness. Não aprovar rollout antes de `alembic check` e suite global verdes.

## 7. Estratégia de commits

Use commits pequenos, reversíveis e ordenados:

1. `test(onboarding): expose audited regressions`
2. `fix(testing): make foundation preconditions explicit`
3. `fix(db): align foundation schema and invariants`
4. `fix(api): unify foundation gate and compatibility adapter`
5. `fix(frontend): serialize nine-step foundation wizard`
6. `fix(availability): separate inspection and repair`
7. `fix(scheduler): unify readiness and pure preflight`
8. `fix(dashboard): return discriminated modes`
9. `fix(tutorial): implement local state machine and telemetry`
10. `test(e2e): cover onboarding lifecycle`
11. `ci: run complete verification on every push`
12. `docs: record verified onboarding rollout`

Cada commit funcional deve conter os testes RED/GREEN do seu contrato. Não misturar limpeza estética não relacionada.

## 8. Definition of Done

O pacote só está concluído quando todas as condições são verdadeiras:

1. `git status --short` não mostra ficheiros técnicos untracked.
2. `ruff format --check`, `ruff check`, ESLint e ambos os modos Knip passam.
3. Suite backend completa passa com e sem Redis e cobertura mínima de `70%`.
4. Vitest com cobertura passa `273+` testes sem dependência de ordem e com thresholds atuais.
5. `alembic check` não propõe operações.
6. Smoke upgrade/downgrade/upgrade passa com migrador.
7. Audits verificam tipos, constraints, RLS, policies, ACLs e eventos dos triggers.
8. Os nove passos persistem sempre o destino confirmado.
9. As `131072` composições de skip terminam com invariantes válidos.
10. Readiness, prevalidation e geração usam o mesmo report e zero writes em leitura.
11. Dashboard é discriminado no OpenAPI e nos dois consumidores frontend.
12. A primeira aprovação é concorrente, monotónica e preservada em reparação/reset.
13. Os seis E2E novos passam no stack real.
14. Um push para branch de feature executa backend, frontend e E2E.
15. `walkthrough.md` existe e contém apenas resultados efetivamente verificados.
16. Não existe escrita de onboarding no Clerk.
17. Não existem dependencies novas nem abstrações sem consumidor.

## 9. Matriz de rastreabilidade

| Achado | Pacote de correção | Prova principal |
| :--- | :--- | :--- |
| `AUD-001` | 5.8.3 | Run de CI num push `codex/...` |
| `AUD-002`, `AUD-003` | 5.0.2, 5.0.3, 5.8.2 | Suites completas verdes |
| `AUD-004` | 5.1.1 | `alembic check` verde |
| `AUD-005` | 5.1.3 | Testes SQL de INSERT/UPDATE/DELETE |
| `AUD-006` | 5.1.2 | FK composta e testes cross-tenant |
| `AUD-007`, `AUD-008` | 5.2.3, 5.3.3 | Allowlist e rotas frontend |
| `AUD-009` | 5.2.4 | Adapter delega e ausência de Clerk write |
| `AUD-010` | 5.3.1, 5.3.2 | Testes de nove passos e save destino |
| `AUD-011` | 5.5.2 | Único `PreflightReport`, zero sync |
| `AUD-012` | 5.4 | Inspector/repair e API self-service |
| `AUD-013` | 5.6.1 | Teste concorrente de aprovação |
| `AUD-014` | 5.6.2 | OpenAPI discriminator e testes dos modos |
| `AUD-015` a `AUD-018` | 5.7 | 24 passos, 131072 sequências, boundary e 204 |
| `AUD-019` | 5.1.5 | Upgrade real sobre cinco cenários |
| `AUD-020` | 5.8.1 | Seis specs Playwright |
| `AUD-021` | 5.8.4 | Walkthrough verificado |

## 10. Condições de NO-GO

Qualquer uma destas condições mantém a entrega bloqueada:

- CI não inicia em push de feature.
- Existem ficheiros técnicos untracked.
- `alembic check`, Ruff, ESLint, Knip, cobertura ou qualquer suite falha.
- Um GET altera dados.
- Uma organização incompleta consegue operar módulos de domínio ou não consegue consultar bootstrap/status.
- O wizard muda de passo antes de o save de destino ser confirmado.
- Existe overwrite automático após `409`.
- O tutorial acede a dados reais ou faz requests fora da allowlist.
- O marcador da primeira aprovação pode mudar ou desaparecer.
- O walkthrough contém contagens não reproduzidas pela CI.
