# Implementacao Ocorrencias, Divida e Registos (2026-04-20)

## Estado do documento
- Tipo: plano tecnico de implementacao e registo de execucao.
- Escopo: backend + frontend + testes + sincronizacao documental.
- Regra de execucao: sequencial por WBS (nao avancar para o ponto seguinte sem fechar o anterior).

## Objetivo
Corrigir inconsistencias entre regra de negocio e comportamento da aplicacao na gestao de ocorrencias, divida de horas e tab de registos operacionais.

## 5Ws da implementacao

### What
- alinhar contabilizacao e exposicao de divida operacional para ocorrencias GAP e SUBSTITUTED;
- enriquecer contrato da API de ocorrencias para suporte de decisao no frontend;
- corrigir comportamento de filtros/navegacao da tab "Ocorrencias Registadas";
- clarificar copy operacional e colunas da grelha;
- reforcar cobertura de regressao backend/frontend;
- sincronizar documentacao canonica apos mudancas.

### Why
- eliminar divergencia entre regra definida e resultado observado na operacao diaria;
- garantir previsibilidade na triagem administrativa;
- reduzir retrabalho por ocultacao involuntaria de dados;
- preservar confianca no fluxo de correcao e regeneracao do horario.

### Who
- backend lead (dominio e API);
- frontend lead (UX operacional e filtros);
- QA (regressao dirigida);
- arquitetura (validacao dos 4 pilares e sincronizacao documental).

### Where
- backend: servicos e endpoints de ocorrencias;
- frontend: pagina de ocorrencias, hooks de dados, navegacao a partir da grelha semanal;
- testes: backend e frontend;
- documentacao: operacional, API e UX.

### When
- execucao por lotes WBS-1 a WBS-8.
- cada lote fecha com validacao tecnica antes do proximo.

## Regras nao negociaveis desta implementacao
1. hard constraints e tenant isolation nunca podem ser relaxados.
2. historico de ocorrencias fechadas permanece imutavel.
3. mudancas sao additive-first (sem quebra de contrato existente quando evitavel).
4. janela de estabilidade (repair) continua valida para geracao, nao para ocultar divida operacional.

## WBS de execucao (checklist)

| ID | Entrega | Estado | Criterio de conclusao |
|---|---|---|---|
| WBS-1 | Divida operacional imediata para GAP/SUBSTITUTED decididos | Concluido | tab de divida reflete ocorrencia decidida mesmo se data for futura |
| WBS-2 | Contrato dual de divida (operacional total vs vencida) sem regressao | Concluido | API devolve ambas as visoes sem quebrar consumidores atuais |
| WBS-3 | Resposta de ocorrencias com turma, disciplina e nome do decisor | Concluido | frontend renderiza contexto completo sem lookup adicional obrigatorio |
| WBS-4 | Filtros da tab de registos sem ocultacao implicita por defeito | Concluido | refresh e mudanca de ecra nao escondem ocorrencias validas |
| WBS-5 | Copy e grelha: "Docente Definitivo", remover "Horas Dadas", incluir turma/disciplina | Concluido | terminologia operacional clara e consistente |
| WBS-6 | Navegacao Schedules -> Absences sem impor bloqueio de data | Concluido | abertura por contexto nao limita visibilidade global involuntariamente |
| WBS-7 | Regressao backend/frontend para cenarios reportados | Concluido | testes alvo passam e cobrem os dois cenarios principais |
| WBS-8 | Sync documental final (operacional, API, UX) | Concluido | docs atualizadas e alinhadas com comportamento final |

## Plano de validacao funcional (obrigatorio)
1. fechar ocorrencia futura (23/04) como GAP e verificar divida imediata + ocorrencia registada.
2. fechar ocorrencia passada (17/04) como GAP e verificar presenca simultanea em divida e registos.
3. confirmar que refresh em "Todas as turmas" nao faz desaparecer registos por estado/data implicitos.
4. validar SUBSTITUTED: divida no modulo planeado + horas no modulo executado.
5. validar GIVEN: sem divida adicional e horas contabilizadas no modulo planeado.
6. confirmar que janela de estabilidade de repair permanece inalterada (referencia: 14 dias default).
7. confirmar admin-only e tenant isolation nos endpoints operacionais.
8. confirmar idempotencia e imutabilidade de ocorrencias fechadas.

## Matriz de risco e mitigacao
- Risco: quebra de consumidores de API ao enriquecer payload.
  Mitigacao: manter campos existentes; adicionar campos novos opcionais.
- Risco: regressao em filtros de listagem.
  Mitigacao: testes frontend de estado inicial, refresh e query params.
- Risco: contagem de divida divergente entre visoes.
  Mitigacao: separar explicitamente "operacional total" e "vencida" no contrato.

## Verificacao dos 4 pilares
- Otimizacao: reduz retrabalho de triagem e planeamento reativo.
- Estabilidade: execucao sequencial com fecho por criterio e regressao por etapa.
- Escalabilidade: contrato de dados mais explicito, sem depender de heuristicas de UI.
- Seguranca: preserva isolamento por tenant, admin-only e imutabilidade historica.

## Registo de execucao por ponto

### WBS-1
- estado: Concluido.
- alteracoes aplicadas:
  - remocao do filtro `date <= today` em `get_debts_sync` para reconhecer divida no momento da decisao.
  - ajuste de docstring para semantica de divida operacional imediata.
- testes de validacao executados:
  - `test_future_gap_is_counted_immediately_in_debts`.
  - `test_get_debts_includes_future_decided_gap`.
  - regressao complementar: `test_get_debts_counts_gap_occurrences` e `test_given_to_substituted_moves_progress_and_creates_debt`.

### WBS-2
- estado: Concluido.
- alteracoes aplicadas:
  - contrato de divida estendido com visao vencida: `total_gaps_overdue`, `total_hours_owed_overdue`, `as_of_date`.
  - `DebtItem` passou a incluir `gap_occurrences_overdue` e `hours_owed_overdue`.
  - campos legacy (`total_gaps`, `total_hours_owed`, `gap_occurrences`, `hours_owed`) mantidos para compatibilidade.
- testes de validacao executados:
  - `test_debt_item_schema` e `test_debt_list_read_schema`.
  - `test_get_debts_empty_when_no_gaps`, `test_get_debts_counts_gap_occurrences`.
  - `test_get_debts_empty` e `test_get_debts_includes_future_decided_gap`.

### WBS-3
- estado: Concluido (backend/API).
- alteracoes aplicadas:
  - `LessonOccurrenceRead` enriquecido com contexto de turma/disciplina/slot e nomes (`class_*`, `subject_*`, `timeslot_*`, `planned_teacher_name`, `executed_teacher_name`, `decided_by_user_name`).
  - servico passou a hidratar e devolver contexto enriquecido em create/list/get/update.
  - nome do decisor com fallback para email quando `name` estiver vazio.
- testes de validacao executados:
  - `test_occurrence_payload_includes_context_and_decider_name`.
  - regressao de compatibilidade: `test_create_occurrence_from_block_returns_201_then_200` e `test_create_occurrence_then_first_decision_applies_accounting_once`.

### WBS-4
- estado: Concluido.
- alteracoes aplicadas:
  - filtro de resolucao inicial alterado de `pending` para `all`.
  - filtros de data iniciais removidos (sem janela implicita por defeito).
  - datas so sao aplicadas quando recebidas explicitamente por query params.
- testes de validacao executados:
  - `Occurrences.test.jsx`: `abre sem filtros implicitos de data e mostra todas as ocorrencias por defeito`.
  - regressao completa da pagina de ocorrencias (8 testes a passar).

### WBS-5
- estado: Concluido.
- alteracoes aplicadas:
  - grelha de ocorrencias passou a incluir `Turma` e `Disciplina`.
  - coluna `Execucao / Decisao Final` foi desdobrada com `Docente Definitivo` e `Decisao Final`.
  - coluna `Horas Dadas` removida da tab de registos.
  - resumo de decisao final passou a mostrar decisor real (`decided_by_user_name` com fallback por id).
- testes de validacao executados:
  - `Occurrences.test.jsx`: `mostra contexto de turma/disciplina e copy atualizado da grelha`.
  - regressao completa da pagina de ocorrencias (9 testes a passar).

### WBS-6
- estado: Concluido.
- alteracoes aplicadas:
  - navegacao `Schedules -> Absences` removeu injecao automatica de `date_from`/`date_to`.
  - passagem de contexto mantida com `occurrence_id` e `class_id`.
- testes de validacao executados:
  - `Schedules.test.jsx`: navegacao direta para faltas com ocorrencia existente.
  - `Schedules.test.jsx`: criacao de ocorrencia e navegacao contextual sem lock de data.

### WBS-7
- estado: Concluido.
- execucao backend (foco ocorrencias/dividas/payload): 8 testes a passar.
- execucao frontend (fluxo operacional): 13 testes a passar (`Occurrences` + `Schedules`).
- cenarios cobertos:
  - GAP futuro entra imediatamente na divida;
  - GAP passado continua consistente entre divida e registos;
  - UX sem ocultacao implicita de registos;
  - navegacao operacional sem bloqueio de data.

### WBS-8
- estado: Concluido.
- docs sincronizadas nesta tarefa:
  - `documentation/04_operational_features/FALTAS.md`.
  - `documentation/05_backend_api/ENDPOINT_STANDARDS.md`.
  - `documentation/06_frontend_ux/UX_CONSISTENCY_SCHEDULES.md`.
- alinhamento final:
  - regra de divida imediata documentada;
  - contrato dual (total vs vencida) documentado;
  - UX final de filtros, colunas e navegacao documentado.

## Notas de governance
- nao fazer commit/push automatico.
- manter alteracoes locais pre-existentes intactas.
- qualquer conflito entre regra de negocio e implementacao deve ser resolvido a favor da regra documentada ou marcado explicitamente como "a definir".