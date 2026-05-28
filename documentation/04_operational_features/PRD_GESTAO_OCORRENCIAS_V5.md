# PRD - Gestao de Ocorrencias V5

Data: 2026-05-28
Estado: pronto para execucao
Area: funcionalidades operacionais apos publicacao de horario
Documento supersede, em caso de conflito, `FALTAS.md` e `SUBSTITUICOES.md`.

## 1. Objetivo

Fechar a gestao de ocorrencias como uma feature estavel, auditavel e previsivel para producao.

A feature deve permitir que a escola registe o que aconteceu a uma aula planeada quando ha uma falta, substituicao ou correcao operacional, mantendo coerencia entre:

- horario planeado;
- execucao real;
- logs de aula;
- progresso e divida curricular;
- historico auditavel;
- interface administrativa.

O objetivo desta versao nao e adicionar notificacoes nem melhorar o algoritmo de geracao/reparacao de horarios. O objetivo e estabilizar o workflow existente para que decisoes simples nao partam dados, progresso, historico ou UX em producao.

## 2. Problema

O sistema atual tem uma base funcional solida, mas ainda deixa ambiguidades perigosas:

- uma ocorrencia aberta e representada como `status=GIVEN` + `decided_at=null`;
- `REVOKED` preserva historico, mas a unicidade atual pode bloquear nova ocorrencia para o mesmo bloco/data;
- auto-confirmacao pode duplicar accounting quando ja existe `LessonLog.COMPLETED`;
- substituicoes criam `ScheduleOutput` e podem criar/usar `Lesson` estrutural como se fosse horario curricular normal;
- redecisao/reversao de substituicoes pode deixar logs, progresso e blocos derivados inconsistentes;
- erros HTTP e validacoes de input nao estao suficientemente fechados;
- testes existentes cobrem varios caminhos, mas alguns sao permissivos ou tautologicos e nao protegem os riscos reais.

## 3. Principios Nao Negociaveis

1. O horario planeado nao e apagado nem reescrito para fingir que a operacao correu como planeado.
2. A execucao real e representada separadamente do planeado.
3. Uma decisao historica nao e alterada in-place; correcao cria nova revisao, evento ou ledger compensatorio.
4. So pode existir uma ocorrencia ativa por `organization_id + schedule_output_id + date`.
5. Accounting nunca e aplicado diretamente sem uma chave idempotente/auditavel.
6. Retry, concorrencia e auto-confirmacao nao podem duplicar progresso ou divida.
7. A UI mostra estados operacionais reais, nao inferencias ambiguas.
8. O backend e a fonte de verdade para permissoes, elegibilidade, conflitos, tenant scope e accounting.
9. O frontend nunca transforma erro de API em sucesso silencioso.
10. Todos os contextos historicos necessarios devem ser snapshotados na ocorrencia no momento de criacao.

## 4. Escopo

### In scope

- Modelo de estados de ocorrencias.
- Criacao de ocorrencia a partir de bloco publicado.
- Decisao administrativa como `GIVEN`, `GAP` ou `SUBSTITUTED`.
- Reversao e redecisao sem perda de historico.
- Representacao de substituicoes como blocos operacionais, nao como aulas estruturais.
- Integracao entre substituicao e `LessonLog`.
- Accounting por ledger/idempotency key.
- Auto-confirmacao diaria idempotente e opcional/configuravel.
- Validacao de inputs em schema, service e API.
- Tratamento de erros HTTP e mensagens de UI.
- Tenant isolation e permissoes.
- Testes unitarios, integracao, frontend, concorrencia e E2E minimo.
- Limpeza de testes falsos positivos relacionados com ocorrencias/logs.

### Out of scope

- Notificacoes para professores disponiveis.
- Matching automatico final sem decisao humana.
- Alteracoes ao algoritmo de geracao/reparacao de horarios.
- Reescrita completa do modulo de timesheets.
- Redesign global da aplicacao.
- App mobile ou portal separado de professor.
- Workflow legal/disciplinar de faltas de funcionario.
- Payroll, RH ou desconto salarial.
- Otimizacao avancada de recomendacoes para alem do ranking deterministico atual.

## 5. Definicoes

- Bloco planeado: `ScheduleOutput` publicado pelo gerador.
- Log de aula: `LessonLog` registado por professor/admin para confirmar execucao.
- Ocorrencia: excecao operacional associada a um bloco planeado/data.
- Ocorrencia ativa: revisao atual que representa o estado operacional valido.
- Ocorrencia historica: revisao inativa, revogada ou substituida por nova revisao.
- Bloco operacional: bloco derivado de uma ocorrencia, visivel em horarios, mas fora do modelo curricular estrutural.
- Decision status: decisao persistida da ocorrencia (`GIVEN`, `GAP`, `SUBSTITUTED`, `REVOKED` ou `null` enquanto aberta).
- Operational state: estado calculado para API/UI (`OPEN_PENDING`, `DECIDED_GIVEN`, `DECIDED_GAP`, `DECIDED_SUBSTITUTED`, `REVOKED`).
- Ledger de progresso: registo auditavel e idempotente de cada delta aplicado a progresso/divida.

## 6. Decisoes de Produto e Arquitetura

### 6.1 Fonte de verdade

`LessonLog` representa execucao registada de uma aula.
`LessonOccurrence` representa a excecao operacional, decisao e auditoria.

Rotas canonicas:

- Professor cria ocorrencia via `PUT /schedule/outputs/{id}/log` com `status=OCCURRENCE`.
- Professor regista aula dada via `PUT /schedule/outputs/{id}/log` com `status=COMPLETED`.
- Admin cria ocorrencia via `POST /occurrences/`.
- Admin decide/redecide via `PATCH /occurrences/{id}`.
- Admin reverte via `POST /occurrences/{id}/cancel`.

Todos estes caminhos devem chamar o mesmo service de dominio. Qualquer hook/endpoint legado que nao seja usado deve ser removido ou convertido em adaptador fino para o caminho canonico.

### 6.2 Estado aberto sem ambiguidade

Decisao V5:

- `LessonOccurrence.status` passa a significar decision status.
- `status` deve ser nullable para ocorrencias abertas.
- ocorrencia aberta = `is_active=true`, `status=null`, `decided_at=null`;
- API devolve `operational_state=OPEN_PENDING`;
- API/UI nunca apresentam uma ocorrencia aberta como `GIVEN`.

Compatibilidade:

- migrar dados legacy `status=GIVEN` + `decided_at=null` para `status=null`;
- durante migracao, normalizador API deve proteger UI mesmo antes de todos os dados estarem limpos.

### 6.3 Revisoes e reversao

Reverter nao apaga historico nem bloqueia nova ocorrencia.

Modelo alvo:

- `LessonOccurrence.revision` inteiro, comecando em 1;
- `LessonOccurrence.is_active` boolean;
- unicidade por `(organization_id, schedule_output_id, date, revision)`;
- invariantes de service e, quando o motor suportar, indice parcial para uma unica ativa por `(organization_id, schedule_output_id, date)`;
- `revoked_at`, `revoked_by_user_id`, `revoked_reason`;
- `version` inteiro para optimistic concurrency.

Regras:

- reverter fecha revisao atual como `REVOKED` e `is_active=false`;
- nova ocorrencia para o mesmo bloco/data cria `revision = max(revision) + 1`;
- redecisao `GAP <-> SUBSTITUTED` pode acontecer na mesma revisao, mas deve criar evento e ledger compensatorio;
- `REVOKED` e terminal.

### 6.4 Blocos operacionais de substituicao

Uma substituicao nao pode criar uma aula curricular permanente so para aparecer no horario.

Modelo alvo:

Criar `OperationalScheduleBlock` com, no minimo:

- `id`;
- `organization_id`;
- `source_occurrence_id`;
- `source_occurrence_revision`;
- `planned_schedule_output_id`;
- `date`;
- `timeslot_id`;
- `room_id` opcional;
- `class_id`;
- `teacher_id`;
- `subject_id`;
- `module_id`;
- `status` (`ACTIVE`, `CANCELLED`);
- `execution_status` (`PENDING_LOG`, `COMPLETED`, `CANCELLED`);
- `created_by_user_id`;
- `created_at`;
- `cancelled_at` opcional.

Regras:

- o horario semanal deve juntar `ScheduleOutput` planeado com `OperationalScheduleBlock`;
- o bloco operacional aparece para admin, turma e professor substituto;
- o gerador/reparador de horarios nao usa blocos operacionais como input curricular;
- reverter/redecidir inativa o bloco operacional anterior;
- nenhum `Lesson` estrutural novo deve ser criado apenas por causa de uma substituicao.

Ligacao a `LessonLog`:

- log de bloco planeado usa `schedule_output_id` preenchido e `operational_block_id=null`;
- log de bloco operacional usa `operational_block_id` preenchido e `schedule_output_id=null`;
- a base de dados deve garantir "exatamente um alvo" por `LessonLog`;
- unicidade de log deve existir por alvo: um log por `schedule_output_id` ou um log por `operational_block_id`;
- respostas de horario devem expor `block_source=planned|operational` e o id correto para o modal de log.

### 6.5 Mesma disciplina vs disciplina diferente

Substituicao por professor da mesma disciplina deve ser suportada quando o professor e elegivel, disponivel e pertence ao tenant.

Regras:

- o professor substituto nao pode ser o professor planeado;
- o professor substituto deve ter ligacao valida a disciplina/turma ou qualificacao explicitamente permitida pelo dominio;
- mesma disciplina/modulo: nao ha divida curricular no momento da decisao;
- disciplina/modulo diferente: ha divida no modulo planeado no momento da decisao;
- progresso do modulo executado so e creditado quando ha `LessonLog.COMPLETED` do bloco operacional.

Esta regra corrige a contradicao anterior: decisao de substituicao nao pode contar progresso e depois o log do substituto contar outra vez.

### 6.6 Accounting por ledger

Todo delta em `ClassProgress` deve passar por um helper unico que cria uma entrada de ledger idempotente.

Campos minimos do ledger:

- `organization_id`;
- `source_type` (`LESSON_LOG`, `OCCURRENCE_DECISION`, `OCCURRENCE_REVERSAL`, `AUTO_CONFIRM`);
- `source_id`;
- `source_revision` opcional;
- `class_id`;
- `module_id`;
- `completed_delta`;
- `debt_delta`;
- `idempotency_key` unica;
- `created_by_user_id` ou `system`;
- `created_at`;
- `reverses_ledger_entry_id` opcional.

Regras de accounting:

- ocorrencia aberta: sem ledger;
- `LessonLog.COMPLETED` do bloco planeado: progresso no modulo planeado;
- `GIVEN` decidido/auto-confirmado: progresso no modulo planeado apenas se nao existir log completed equivalente;
- `GAP`: divida no modulo planeado;
- `SUBSTITUTED` mesma disciplina/modulo: sem divida na decisao; progresso quando o substituto regista completed;
- `SUBSTITUTED` disciplina/modulo diferente: divida no modulo planeado na decisao; progresso no modulo executado quando o substituto regista completed;
- redecisao/reversao cria ledger compensatorio antes de aplicar novo efeito;
- `ClassProgress` nunca pode ficar negativo apos compensacao.

### 6.7 Reverter substituicao ja concluida

Se uma substituicao tem bloco operacional com `LessonLog.COMPLETED`:

- se a semana/timesheet do substituto estiver aberta, a reversao pode cancelar o log operacional, criar ledger compensatorio e inativar o bloco;
- se a semana/timesheet estiver submetida ou aprovada, a reversao deve falhar com `409 SUBSTITUTE_LOG_LOCKED`;
- a UI deve explicar que a semana precisa ser reaberta antes de corrigir.

Nao pode existir reversao silenciosa que deixe progresso do substituto ativo depois de remover a ocorrencia.

### 6.8 Auto-confirmacao diaria

Auto-confirmacao e mecanismo de fallback, nao substituto do workflow do professor.

Regras:

- deve ser controlada por configuracao (`auto_confirm_enabled`, cutoff horario);
- se existe `LessonLog.COMPLETED`, nao cria ocorrencia nem aplica progresso;
- se existe `LessonLog.OCCURRENCE`, garante ocorrencia aberta, sem decidir automaticamente;
- se existe ocorrencia ativa, nao cria outra;
- se nao existe log nem ocorrencia apos cutoff, pode criar ocorrencia decidida `GIVEN` com ator `system`;
- processamento deve ser isolado por bloco;
- `IntegrityError` ou conflito devem afetar apenas o bloco atual;
- correr a task duas vezes deve produzir o mesmo estado final.

## 7. Estados e Transicoes

### Estados persistidos

- `status=null`, `is_active=true`: aberta.
- `status=GIVEN`, `decided_at!=null`: dada/conferida.
- `status=GAP`, `decided_at!=null`: furo/divida.
- `status=SUBSTITUTED`, `decided_at!=null`: substituida.
- `status=REVOKED`, `is_active=false`: revisao revogada.

### Estados API

- `OPEN_PENDING`
- `DECIDED_GIVEN`
- `DECIDED_GAP`
- `DECIDED_SUBSTITUTED`
- `REVOKED`

### Transicoes permitidas

- inexistente -> `OPEN_PENDING`;
- `OPEN_PENDING` -> `DECIDED_GIVEN`;
- `OPEN_PENDING` -> `DECIDED_GAP`;
- `OPEN_PENDING` -> `DECIDED_SUBSTITUTED`;
- `DECIDED_GAP` -> `DECIDED_SUBSTITUTED`;
- `DECIDED_SUBSTITUTED` -> `DECIDED_GAP`;
- `DECIDED_GIVEN` -> `REVOKED`, apenas admin e com motivo;
- `DECIDED_GAP` -> `REVOKED`;
- `DECIDED_SUBSTITUTED` -> `REVOKED`;
- `REVOKED` -> terminal.

### Transicoes proibidas

- alterar revisao `REVOKED`;
- decidir ocorrencia inativa;
- decidir ocorrencia de outro tenant;
- mudar decisao sem ledger compensatorio;
- criar substituicao sem professor e disciplina;
- enviar campos de substituicao para `GIVEN` ou `GAP`;
- aceitar `REVOKED` no payload normal de update;
- concluir aula planeada quando existe ocorrencia ativa `GAP` ou `SUBSTITUTED`, salvo fluxo explicito de correcao.

## 8. Workflows

### 8.1 Professor regista aula dada

1. Professor abre bloco planeado.
2. Backend valida professor, tenant, semana aberta e bloco nao futuro.
3. Backend cria/atualiza `LessonLog.COMPLETED`.
4. Ledger credita progresso uma unica vez.
5. Nenhuma ocorrencia e criada.

### 8.2 Professor cria ocorrencia

1. Professor abre bloco que lhe pertence.
2. Backend valida tenant, semana aberta e ausencia de ocorrencia ativa.
3. `LessonLog` fica `OCCURRENCE`.
4. Service cria `LessonOccurrence` aberta (`status=null`, `is_active=true`).
5. Pagina de ocorrencias mostra item em pendentes.

### 8.3 Admin cria ocorrencia

1. Admin usa `POST /occurrences/` ou acao equivalente na grelha.
2. Backend valida tenant, bloco publicado e ausencia de log completed.
3. Service cria ou devolve ocorrencia ativa idempotentemente.
4. Se ultima revisao esta `REVOKED`, cria nova revisao.

### 8.4 Admin decide GAP

1. Admin abre ocorrencia pendente.
2. Seleciona `GAP`.
3. Backend valida versao atual.
4. Ledger cria divida no modulo planeado.
5. Ocorrencia fica decidida e auditada.

### 8.5 Admin decide SUBSTITUTED

1. Admin consulta recomendacoes/lista elegivel.
2. Seleciona professor e disciplina.
3. Backend revalida elegibilidade e conflito.
4. Backend cria `OperationalScheduleBlock`.
5. Ledger aplica divida apenas se modulo executado for diferente do modulo planeado.
6. Progresso do modulo executado aguarda `LessonLog.COMPLETED` no bloco operacional.
7. UI atualiza ocorrencias, horario e dividas.

### 8.6 Substituto regista aula dada

1. Professor substituto ve bloco operacional no horario.
2. Regista `LessonLog.COMPLETED`.
3. Backend valida que o bloco operacional esta ativo.
4. Ledger credita progresso do modulo executado.
5. `OperationalScheduleBlock.execution_status` passa a `COMPLETED`.

### 8.7 Admin redecide GAP/SUBSTITUTED

1. Admin abre ocorrencia decidida.
2. UI envia `version` atual e nova decisao.
3. Backend reverte ledger anterior com compensacao.
4. Backend cancela/inativa bloco operacional anterior se existir.
5. Backend aplica nova decisao e novo ledger.
6. Historico de eventos preserva antes/depois.

### 8.8 Admin reverte

1. Admin aciona "Reverter".
2. UI pede confirmacao e mostra impacto.
3. Backend valida versao, permissao e estado.
4. Backend compensa ledger da revisao ativa.
5. Backend cancela bloco operacional conforme regras de timesheet.
6. Revisao fica `REVOKED`, `is_active=false`.
7. O mesmo bloco/data pode receber nova ocorrencia futura.

## 9. Requisitos Funcionais

### RF1 - Lista de ocorrencias

- Suportar filtros por estado operacional, turma, professor, disciplina, intervalo de datas e texto quando aplicavel.
- Query `status` aceita `OPEN_PENDING`, `GIVEN`, `GAP`, `SUBSTITUTED`, `REVOKED`; alias legacy `OPEN` pode mapear para `OPEN_PENDING`.
- `status` invalido devolve `422`, nunca lista completa.
- Resposta paginada em formato `items`, `total`, `limit`, `offset`.
- Pendentes ordenadas por data, hora inicial e id.

### RF2 - Detalhe de ocorrencia

- Devolver snapshot historico completo: turma, disciplina, professor planeado, slot, data, sala quando aplicavel, modulo planeado, horas planeadas, revision, active flag, version e decisor.
- Devolver blocos operacionais derivados.
- Devolver resumo de ledger aplicado.
- Campos exibidos pela UI devem existir no schema.

### RF3 - Recomendacoes de substitutos

- Lista ordenada deterministicamente.
- Inclui candidatos de mesma disciplina quando elegiveis.
- Explica criterios de ranking.
- Revalida tudo no momento da confirmacao.
- Nunca cruza tenant.

### RF4 - Decisao

- Exige `version`.
- E transacional.
- E idempotente para retry identico.
- Devolve `409` se a ocorrencia mudou desde que o admin abriu o modal.

### RF5 - Reversao

- Exige confirmacao na UI.
- Exige `version`.
- Tem loading per-row/per-modal.
- Impede duplo clique.
- Preserva historico e permite nova revisao.

### RF6 - UI administrativa

- Tabs refletem URL params corretamente.
- "Pendentes" mostra apenas `OPEN_PENDING`.
- "Historico" mostra decididas e revogadas.
- Labels vem de fonte unica de terminologia.
- `REVOKED`, `GAP`, `SUBSTITUTED`, `GIVEN` e `OPEN_PENDING` tem aparencia distinta.
- Erros de API aparecem como erro, nao como lista vazia.

## 10. Validacao de Inputs

### Payload `PATCH /occurrences/{id}`

- `status` obrigatorio e limitado a `GIVEN`, `GAP`, `SUBSTITUTED`.
- `REVOKED` proibido no update normal.
- `version` obrigatorio.
- `substitute_teacher_id` e `substitute_subject_id` obrigatorios apenas para `SUBSTITUTED`.
- Campos de substituicao proibidos para `GIVEN` e `GAP`.
- `reason` opcional, trim aplicado, tamanho maximo definido.
- Campos desconhecidos rejeitados.

### Payload `POST /occurrences/{id}/cancel`

- `version` obrigatorio.
- `reason` obrigatorio para estados decididos.
- flag explicita obrigatoria se a reversao for cancelar log completed de substituto em semana aberta.

### Query params

- ids numericos positivos;
- `date_from <= date_to`;
- `limit` com maximo configurado;
- filtros sempre scoping por `organization_id`;
- `status` invalido devolve `422`.

### Elegibilidade de substituto

- professor existe e pertence ao tenant;
- professor nao e o docente planeado;
- professor esta disponivel no slot;
- professor nao tem outro bloco planeado ou operacional no mesmo slot;
- disciplina pertence a turma ou e explicitamente autorizada pelo dominio;
- par professor/disciplina e valido;
- substituicao nao atravessa tenant.

## 11. Tratamento de Erros

### Contrato HTTP

- `400`: acao coerente mas impossivel por regra simples de negocio.
- `401`: nao autenticado.
- `403`: autenticado sem permissao.
- `404`: recurso inexistente dentro do tenant; frontend nunca trata como sucesso.
- `409`: conflito de estado, stale version, concorrencia, candidato indisponivel ou timesheet bloqueada.
- `422`: input invalido, enum invalido, datas invalidas, campos desconhecidos.
- `500`: erro inesperado com correlation id.

### Codigos de erro obrigatorios

- `OCCURRENCE_NOT_FOUND`
- `OCCURRENCE_STALE_VERSION`
- `OCCURRENCE_INACTIVE`
- `OCCURRENCE_ALREADY_ACTIVE`
- `OCCURRENCE_INVALID_TRANSITION`
- `OCCURRENCE_REVOKED`
- `SUBSTITUTE_NOT_AVAILABLE`
- `SUBSTITUTE_INVALID_FOR_CLASS`
- `SUBSTITUTE_CROSS_TENANT`
- `SUBSTITUTE_SLOT_CONFLICT`
- `SUBSTITUTE_LOG_LOCKED`
- `ACCOUNTING_CONFLICT`
- `AUTO_CONFIRM_PARTIAL_FAILURE`

### UX de erro

- Modal de decisao nao fecha em erro.
- Reversao de tabela mostra confirmacao antes da chamada.
- Loading bloqueia clique duplicado.
- Erros `409` sugerem recarregar dados.
- Erros `422` apontam campos invalidos.
- Erro de log/timesheet bloqueada explica a acao necessaria.

## 12. Permissoes

- Professor pode registar aula dada nos seus blocos planeados/operacionais quando a semana permite.
- Professor pode criar ocorrencia apenas nos seus blocos planeados.
- Admin pode listar, criar, decidir, redecidir e reverter ocorrencias do tenant.
- Backend valida tudo, mesmo quando o frontend esconde a acao.
- Nenhum endpoint de ocorrencias devolve ou altera dados de outro tenant.

## 13. Dados e Migracao

### Alteracoes minimas de dados

`LessonOccurrence`:

- tornar `status` nullable;
- adicionar `revision`;
- adicionar `is_active`;
- adicionar `version`;
- adicionar `created_by_user_id`;
- adicionar `creation_source`;
- adicionar `reason`;
- adicionar `revoked_at`, `revoked_by_user_id`, `revoked_reason`;
- adicionar snapshots que ainda faltem: `planned_timeslot_id`, `planned_room_id`, `planned_generation_id`.

`LessonLog`:

- adicionar `operational_block_id` nullable;
- permitir `schedule_output_id` nullable apenas quando `operational_block_id` estiver preenchido;
- adicionar check constraint para exatamente um alvo (`schedule_output_id` ou `operational_block_id`);
- ajustar unicidade para impedir dois logs do mesmo alvo.

Novas entidades:

- `OperationalScheduleBlock`;
- `ProgressLedgerEntry` ou nome equivalente para ledger de progresso/divida.

Indices/invariantes:

- unique `(organization_id, schedule_output_id, date, revision)`;
- indice por `(organization_id, is_active, date)`;
- se suportado, partial unique para uma ativa por `(organization_id, schedule_output_id, date)` onde `is_active=true`;
- unique `idempotency_key` no ledger.

### Migracao

1. Popular `revision=1`, `is_active=true`, `version=1`.
2. Migrar `status=GIVEN` + `decided_at=null` para `status=null`.
3. Marcar `REVOKED` como `is_active=false`.
4. Snapshotar contexto a partir de `schedule_output` enquanto ainda existe.
5. Identificar ocorrencias sem contexto minimo e gerar relatorio de reparacao manual.
6. Criar ledger baseline ou reconciliar `ClassProgress` com dados existentes antes de ativar ledger idempotente.
7. Validar migracao em base de teste/staging.

## 14. Observabilidade e Auditoria

Eventos obrigatorios:

- `occurrence.created`
- `occurrence.decided`
- `occurrence.redecided`
- `occurrence.revoked`
- `occurrence.auto_confirmed`
- `occurrence.auto_confirm_failed`
- `occurrence.accounting_applied`
- `occurrence.accounting_reverted`
- `operational_block.created`
- `operational_block.cancelled`

Cada evento inclui:

- `organization_id`;
- `occurrence_id`;
- `revision`;
- ator (`user_id` ou `system`);
- estado anterior e novo;
- `version`;
- correlation/request id;
- resumo do impacto em progresso/divida.

## 15. Plano de Testes

### Backend unitario

- Normalizacao `status=null` -> `OPEN_PENDING`.
- Tabela de transicoes permitidas/proibidas.
- Validacao de schemas create/update/cancel.
- Elegibilidade de substituto incluindo mesma disciplina.
- Ledger idempotente e compensatorio.
- Accounting para `GIVEN`, `GAP`, `SUBSTITUTED` mesma disciplina e `SUBSTITUTED` disciplina diferente.
- Auto-confirm idempotente.

### Backend integracao/API

- `GET /occurrences` com filtros validos, invalidos, paginacao e alias `OPEN`.
- `PATCH /occurrences/{id}` com version correta e stale.
- `POST /occurrences/{id}/cancel` com version correta, stale e reason obrigatorio.
- Dois admins decidem a mesma ocorrencia; um vence, outro recebe `409`.
- Tenant isolation em lista, detalhe, recomendacoes, update e cancel.
- Reverter e criar nova revisao para o mesmo bloco/data.
- Substituicao cria bloco operacional, nao cria `Lesson` estrutural.
- Substituto completa bloco operacional e progresso e creditado uma vez.
- Reverter substituicao concluida em semana aberta compensa ledger.
- Reverter substituicao concluida em semana submetida/aprovada devolve `409 SUBSTITUTE_LOG_LOCKED`.
- Auto-confirm executado duas vezes nao duplica ledger.
- Falha parcial na auto-confirmacao nao aborta tenant inteiro.

### Frontend

- Tabs respeitam URL params.
- Pendentes nao mostram decididas.
- Historico mostra `REVOKED` com label proprio.
- Modal inicializa decisao sem perder estado existente.
- Campos de substituicao aparecem apenas para `SUBSTITUTED`.
- Confirmacao antes de reverter.
- Loading per-row/per-modal.
- Erros 404/409/422 aparecem como erro.
- Labels usam terminologia centralizada.
- WeekGrid diferencia blocos planeados, ocorrencias e blocos operacionais.

### E2E minimo

1. Professor cria ocorrencia; admin decide `GAP`; divida aparece.
2. Professor cria ocorrencia; admin decide `SUBSTITUTED` mesma disciplina; substituto completa; sem divida e com progresso uma vez.
3. Professor cria ocorrencia; admin decide `SUBSTITUTED` disciplina diferente; divida planeada e progresso executado apos log.
4. Admin reverte decisao; historico preserva revisao; nova ocorrencia pode ser criada.
5. Dois admins abrem a mesma ocorrencia; segunda decisao recebe conflito.
6. Auto-confirm executado duas vezes nao duplica progresso.

### Testes a remover/substituir

- asserts tautologicos;
- `len(collection) >= 0`;
- testes que apenas verificam existencia de funcao/enum;
- source inspection como substituto de comportamento;
- mocks que impedem o comportamento real de falhar.

## 16. Criterios de Aceite Globais

- Nenhuma ocorrencia aberta aparece como `GIVEN`.
- Reverter preserva historico e nao bloqueia nova revisao.
- Substituicoes nao criam aulas estruturais permanentes.
- Progress/divida sao explicaveis por ledger.
- Retry, concorrencia e auto-confirmacao nao duplicam accounting.
- Erros de API sao tratados explicitamente.
- Inputs invalidos falham com `422`.
- Conflitos reais falham com `409`.
- A UI nao fecha modais em erro.
- Todos os cenarios criticos tem testes que falham se o comportamento partir.
- Documentos antigos ficam alinhados ou marcados como superseded.

## 17. Riscos e Mitigacoes

- Risco: migracao de `status` nullable quebra queries antigas.
  Mitigacao: introduzir normalizador e atualizar queries por `operational_state` antes de remover compatibilidade.

- Risco: ledger diverge de `ClassProgress` existente.
  Mitigacao: script de reconciliacao e relatorio antes de ativar escrita obrigatoria via ledger.

- Risco: blocos operacionais exigem alteracao no horario semanal.
  Mitigacao: endpoint retorna `source` explicito e UI trata planeado/operacional com componentes existentes primeiro.

- Risco: reverter substituicao concluida mexe em dados de professor.
  Mitigacao: permitir apenas com semana aberta; bloquear com `409` quando timesheet estiver submetida/aprovada.

---

# WBS - Implementacao Gestao de Ocorrencias V5

## 0. Preparacao e Guardrails

0.1. Marcar este PRD como fonte de verdade na documentacao.
0.2. Criar matriz de regressao com todos os cenarios do PRD.
0.3. Identificar todos os testes legacy de ocorrencias/logs e classifica-los como manter, reescrever ou remover.
0.4. Criar fixtures base para professor, admin, turma, modulo, horario planeado, substituicao e timesheet bloqueada.

Entregavel: matriz de cenarios + lista de testes legacy.

## 1. Contrato de Dominio e API

1.1. Definir `OperationalOccurrenceState`.
1.2. Atualizar schemas read/update/cancel com `status` nullable em read, `operational_state`, `revision`, `is_active`, `version`.
1.3. Restringir update para `GIVEN`, `GAP`, `SUBSTITUTED`.
1.4. Criar schema de cancel com `version`, `reason` e flags explicitas.
1.5. Validar query params e paginacao.
1.6. Adicionar testes unitarios de schemas.

Entregavel: contrato API fechado e testado.

## 2. Migracao de Dados

2.1. Criar migracao de `LessonOccurrence`: `status` nullable, `revision`, `is_active`, `version`, campos de criacao/revogacao e snapshots.
2.2. Alterar unicidade para suportar revisoes.
2.3. Migrar ocorrencias abertas legacy para `status=null`.
2.4. Marcar `REVOKED` como inativas.
2.5. Criar `OperationalScheduleBlock`.
2.6. Alterar `LessonLog` para suportar alvo planeado ou operacional com check constraint.
2.7. Criar `ProgressLedgerEntry`.
2.8. Criar script de integridade/reconciliacao.

Entregavel: migracao validada em base de teste.

## 3. State Machine e Concorrencia

3.1. Extrair state machine para modulo testavel.
3.2. Implementar normalizacao `OPEN_PENDING`.
3.3. Implementar criacao de nova revision apos `REVOKED`.
3.4. Implementar optimistic concurrency por `version`.
3.5. Manter lock transacional para serializar escrita.
3.6. Garantir idempotencia de retry identico.
3.7. Adicionar testes de transicao, revision e concorrencia.

Entregavel: state machine deterministica.

## 4. Ledger e Accounting

4.1. Implementar helper unico de ledger + update de `ClassProgress`.
4.2. Bloquear escrita direta em `ClassProgress` nos fluxos de ocorrencia/log.
4.3. Implementar regras de `GIVEN`, `GAP`, `SUBSTITUTED` mesma disciplina e `SUBSTITUTED` disciplina diferente.
4.4. Implementar compensacao de redecisao/reversao.
4.5. Garantir que `ClassProgress` nao fica negativo.
4.6. Adicionar testes de idempotencia e compensacao.

Entregavel: accounting auditavel e sem duplo credito.

## 5. Blocos Operacionais e LessonLog

5.1. Implementar `OperationalScheduleBlock`.
5.2. Adaptar decisao `SUBSTITUTED` para criar bloco operacional.
5.3. Adaptar horario semanal para juntar blocos planeados e operacionais.
5.4. Adaptar `LessonLog` para aceitar `operational_block_id`.
5.5. Atualizar completion do substituto para creditar progresso via ledger.
5.6. Implementar cancelamento de bloco operacional em redecisao/reversao.
5.7. Adicionar testes de horario, log e reversao.

Entregavel: substituicao visivel e executavel sem poluir `Lesson`.

## 6. Elegibilidade e Recomendacoes

6.1. Rever query de candidatos com tenant scope explicito.
6.2. Permitir mesma disciplina quando elegivel.
6.3. Validar conflito contra blocos planeados e operacionais.
6.4. Manter ranking deterministico.
6.5. Atualizar explicacoes de recomendacao.
6.6. Adicionar testes de elegibilidade, conflito e ordenacao.

Entregavel: recomendacoes alinhadas ao dominio V5.

## 7. Reversao e Redecisao

7.1. Implementar cancel com `version` e `reason`.
7.2. Implementar nova revision apos reversao.
7.3. Implementar redecisao `GAP <-> SUBSTITUTED` com compensacao.
7.4. Implementar regra de substituicao concluida em semana aberta.
7.5. Implementar bloqueio `SUBSTITUTE_LOG_LOCKED` para semana submetida/aprovada.
7.6. Adicionar testes API e service.

Entregavel: correcao operacional segura.

## 8. Auto-confirmacao

8.1. Adicionar configuracao `auto_confirm_enabled` e cutoff.
8.2. Rever query de candidatos.
8.3. Saltar `LessonLog.COMPLETED`.
8.4. Garantir pendencia para `LessonLog.OCCURRENCE`.
8.5. Processar bloco a bloco com falha isolada.
8.6. Usar ledger idempotente para `GIVEN` automatico.
8.7. Adicionar testes de idempotencia e falha parcial.

Entregavel: task segura para execucao repetida.

## 9. API e Erros

9.1. Padronizar `400/403/404/409/422`.
9.2. Adicionar codigos de erro obrigatorios.
9.3. Corrigir `GET /occurrences` para status invalido devolver `422`.
9.4. Implementar resposta paginada.
9.5. Garantir atores `decided_by`, `revoked_by`, `system`.
9.6. Atualizar testes de endpoint.

Entregavel: API previsivel e consumivel.

## 10. Frontend - Dados e Hooks

10.1. Remover tratamento global que transforma 404 em sucesso ou limitar a casos explicitamente justificados.
10.2. Atualizar hooks para `operational_state`, paginacao e version.
10.3. Centralizar invalidacoes de cache apos decide/redecide/revert/log.
10.4. Tratar `409` com recarregamento orientado.
10.5. Atualizar testes de hooks/apiClient.

Entregavel: React Query reflete estado real.

## 11. Frontend - UI de Ocorrencias e Horario

11.1. Corrigir tabs por URL params.
11.2. Separar pendentes, historico e dividas por `operational_state`.
11.3. Corrigir modal para nao perder decisao existente.
11.4. Adicionar confirmacao e loading no reverter.
11.5. Mostrar erros sem fechar modal.
11.6. Usar terminologia centralizada.
11.7. Diferenciar visualmente `REVOKED`, `OPEN_PENDING` e blocos operacionais.
11.8. Adicionar testes RTL.

Entregavel: workflow administrativo claro.

## 12. Limpeza de Testes Legacy

12.1. Reescrever testes tautologicos.
12.2. Remover source inspection.
12.3. Substituir mocks permissivos por fixtures realistas.
12.4. Garantir que testes de regressao falham sem as correcoes V5.
12.5. Documentar casos removidos.

Entregavel: suite confiavel.

## 13. Observabilidade

13.1. Emitir eventos obrigatorios.
13.2. Incluir correlation id.
13.3. Logar falhas parciais da auto-confirmacao.
13.4. Adicionar testes/snapshots de payload minimo.

Entregavel: trilho operacional auditavel.

## 14. QA Final e Go/No-Go

14.1. Correr suite backend completa.
14.2. Correr suite frontend completa.
14.3. Correr lint/build.
14.4. Executar E2E minimo dos seis cenarios criticos.
14.5. Validar migracao e reconciliacao em staging/teste.
14.6. Fazer checklist manual de UX admin/professor.
14.7. Confirmar que documentos antigos foram alinhados ou marcados como superseded.

Entregavel: decisao go/no-go de ocorrencias V5.

## 15. Sequencia Recomendada

1. Contrato API + schemas.
2. Migracao + ledger + blocos operacionais.
3. State machine + concorrencia.
4. Accounting + LessonLog.
5. Substituicoes/recomendacoes.
6. Reversao/redecisao.
7. Auto-confirmacao.
8. Frontend dados/UI.
9. Testes legacy, observabilidade e QA final.

Esta ordem estabiliza primeiro a fonte de verdade e so depois adapta UI, tarefas automaticas e limpeza de testes.
