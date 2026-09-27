# W08–W09 — Registo de correção da revisão R89

Data: 26 de setembro de 2026.
Branch: `codex/scheduler-v1-revamp`.
Revisão aplicada: [SCHEDULER_V1_W08_W09_REVIEW_WBS.md](SCHEDULER_V1_W08_W09_REVIEW_WBS.md).
Estado: R89.01–R89.10 implementados com teste falhado primeiro. W10–W14 permanecem plano. Nenhum push, reset remoto ou ensaio Railway/Cloudflare foi executado.

## 1. Correções por item

| ID | Correção mínima aplicada | Regressão e resultado |
| :--- | :--- | :--- |
| R89.01 | `domain/candidate.py` ganha `split_consumed_lessons`: aulas totalmente cobertas pela execução saem da baseline planeável; sobreposição parcial falha em voz alta. `snapshot.py` aplica a regra e converte inconsistências em `SnapshotConfigurationError`. `proposals.py` volta a anexar o histórico consumido à nova versão (`_carry_consumed_lessons`) e reconcilia sumários por identidade estável na aprovação (`_repoint_lesson_logs`). O crédito repetido é impedido pela origem `lesson-log:{identidade}`. | `test_a_completed_lesson_log_follows_the_lesson_into_the_next_version`: publicar, registar, reparar com relógio posterior, aprovar; o sumário aparece na semana da nova versão e os minutos não duplicam. |
| R89.02 | `jobs.py` ganha `executor_lock_alive` com prova de posse em `pg_locks` (não basta a ligação responder). O monitor do worker (`scheduler_v1_worker.py`) verifica a posse a cada batida; ao perder o lock, cancela o cálculo e falha o job como `LOCK_LOST` com escrita guardada por token. O supervisor corre num serviço dedicado (`scheduler-supervisor`, fila `scheduler-supervisor`) fora do worker de cálculo; Beat agenda com `options.queue`. Compose local/CI e `railway/supervisor.json` criados. | `test_the_executor_lock_is_exclusive_and_has_a_liveness_proof`; `test_a_lost_lock_fails_the_attempt_and_stops_the_solve` (lock morto, sem proposta, sem duplo cálculo). Worker regista `scheduler.v1.run_next_job`; supervisor regista `scheduler.v1.supervise`. |
| R89.03 | `persist_proposal` reconstrói o snapshot com o relógio atual dentro da transação sob lock do estado, compara digest/revisões/versão e revalida o candidato; qualquer desvio termina `STALE` sem tocar no relógio de 28 dias (`REVALIDATION_FAILED` quando a fronteira invalida o candidato). | `test_finalization_rejects_a_candidate_that_the_current_clock_invalidated`: proposta recusada, relógio intacto, sem versão nem proposta persistida. |
| R89.04 | `application/publishing.py` ganha `plan_recovery_allocations`: distribui a dívida aberta pelas aulas candidatas da mesma atribuição, dívida mais antiga primeiro, sem exceder crédito da aula nem dívida aberta; sobra impossível falha em voz alta. `persist_proposal` persiste estas alocações (ordem por `origin_date`) na mesma transação. | 4 testes unitários de divisão/ordem/limites; `test_a_repair_persists_planned_recovery_allocations`: soma igual à dívida, limites por aula e por dívida verificados. |
| R89.05 | `operations.py`: reversões calculadas por `(origem, módulo)` em `_record_manual_reduction` e `_reverse_lesson_execution`; a passagem a ocorrência reverte só o saldo ainda creditado por módulo. | `test_manual_reductions_are_per_module_on_a_crossing_lesson`; `test_an_occurrence_reverses_only_the_remaining_module_balance`. |
| R89.06 | `finish_job` decide sob lock do estado e do job: cancelamento pedido vence (`CANCELLED`), depois atualidade de revisões/versão (`STALE`), só então o resultado calculado. Devolve o estado efetivamente escrito (`LOST` se a tentativa já não é dona). Worker propaga o estado real. | `test_finish_prefers_cancellation_and_staleness_over_the_result`; testes existentes atualizados para o novo contrato (`FAILED`/`LOST`). |
| R89.07 | `approve_proposal` reconhece repetição de aprovação confirmada (mesma versão ainda ativa → devolve a ativação original, mesmo com revisão esperada divergente) e preserva conflito `proposal_superseded` para versão substituída. | `test_repeated_approval_returns_the_same_activation`: segunda chamada idêntica, uma única ativação; proposta antiga após nova aprovação → `proposal_superseded`. |
| R89.08 | Novo `infrastructure/occurrences.py`: quando existe versão v1 ativa, listar/detalhar/dívidas/recomendações/decidir (GIVEN/GAP/SUBSTITUTED)/reverter usam só o ledger v1 (logs + dívida + execuções). Substituição credita a disciplina lecionada na fronteira residual; reversão desfaz substituições por `(origem, módulo)` e revê a dívida (novo estado `REVOKED`, migração `0014`). Endpoints comutam por `is_active`; legado intacto caso contrário. | `test_scheduler_v1_occurrences.py` (4 testes): listar/decidir GIVEN, substituição com dívida preservada e reversão completa, agregação de dívidas, recomendações. |
| R89.09 | Regressões R89.01–R89.08 acima; `test_a_failure_during_approval_rolls_everything_back` injeta falha a meio da aprovação e confirma versão anterior intacta, proposta `PENDING` e auditoria coerente. C16 coberta por lock/supervisor/reconciliação/cancelamento/duplicação em PostgreSQL real; C17 por isolamento e integridade existentes; C20 aguarda E2E com Clerk (não executável neste ambiente). | Ver secção 2. |
| R89.10 | `publishing.py` persiste `evidence` tipada completa em `metrics_json` com `policy_version`. `queries.py` expõe `quality_summary` (`stop_reason`, âmbito, etapas certificadas/totais, `claims_optimum` só com todas as etapas provadas, política). `DraftPanel.jsx` mostra a linha de certificação sem declarar ótimo. | Assertions no teste de geração com sucesso; 2 testes frontend da linha de certificação. |

## 2. Verificações executadas

| Verificação | Resultado |
| :--- | :--- |
| `pytest tests/unit` (backend) | 760 passed. |
| `node scripts/test.mjs integration` (Docker local, PostgreSQL real) | 347 passed + 47 contratos. |
| `ruff check` e `ruff format` (backend) | limpos. |
| `npm run lint`, `npm run test` (frontend) | verdes; 73 ficheiros, 411 testes. |
| Migrações locais | `0014_scheduler_v1_log_revoked` aplicada (`db-maintenance`). |
| Stack local | backend saudável, frontend 200, `scheduler-supervisor` registado na fila dedicada. |

## 3. Triagem (R89.09)

- Casos críticos omitidos na revisão anterior: execução+proteção (R89.01), perda de lock (R89.02), fronteira na finalização (R89.03), reservas de recuperação (R89.04), reversões por módulo (R89.05), precedência de cancelamento (R89.06), repetição de aprovação (R89.07), ocorrências v1 (R89.08), evidência (R89.10). Todos têm agora regressão dedicada.
- Resultados inconclusivos continuam explícitos (`INCONCLUSIVE`, `STALE`, `LOCK_LOST`); nenhum vira prova.
- C20 (percurso escolar completo com teclado/refresh/duplo clique/sessão) exige E2E com Clerk e fica para o proprietário com a pilha local; fixtures E2E já seguem o contrato v1.
- Limite conhecido: sobreposição parcial execução↔protegida (ex. acerto manual a meio de uma aula congelada) é rejeitada como `EXECUTION_OVERLAPS_PROTECTED`/`INVALID_INPUT` em vez de resolvida; resolver exigiria re-projeção de crédito congelado, fora do âmbito desta correção.

A próxima ação é W10 (campanhas combinadas e anuais) com os corpus existentes.
