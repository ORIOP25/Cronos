# W08–W09 — Execução, publicação, API e aplicação escolar (registo as-built)

Data: 26 de setembro de 2026.
Branch: `codex/scheduler-v1-revamp`.
Estado: W08.1–W08.5 e W09.1–W09.5 concluídos com testes verdes. W10–W14 permanecem plano. Nenhum push, reset remoto ou ensaio Railway/Cloudflare foi executado.

Documentos de referência: [plano v2](SCHEDULER_V1_REVAMP_PLAN_V2.md), [WBS v2](SCHEDULER_V1_WBS_V2.md), [especificação técnica v2](SCHEDULER_V1_TECH_SPEC_V2.md).

## 1. Resultado

- O motor v1 está ligado à fila global, à persistência e à publicação. Os endpoints deixam de usar o ciclo de vida legado; o motor antigo permanece no repositório até à remoção da W12.
- Existe um único cálculo global. A fila FIFO é persistida, o executor usa um advisory lock e cada escrita de resultado verifica o token da tentativa.
- O snapshot é imutável e tem digest estável entre o pedido e a execução. As revisões e a versão de base decidem a atualidade.
- A proposta é persistida numa transação. O relógio de 28 dias reinicia na conclusão válida, não na aprovação nem na rejeição.
- A aprovação revalida dados, fronteira e candidato e ativa a versão numa única transação. Uma proposta desatualizada fica `STALE` e não é aprovada em silêncio.
- A API e o frontend falam linguagem escolar. O mapa semanal mostra parcelas modulares múltiplas por aula e minutos conservados.

## 2. W08 — Execução e publicação

| ID | Entrega | Ficheiros principais | Teste/evidência |
| :--- | :--- | :--- | :--- |
| W08.1 | Revisões, snapshots e verificação de atualidade. | `infrastructure/snapshot.py`, `infrastructure/jobs.py`, `domain/serialization.py` | T24: `test_a_change_while_queued_marks_the_request_stale`; digest estável entre enfileirar e reclamar; `load_snapshot` recusa configuração em falta com código tipado. |
| W08.2 | FIFO global, lock e token de tentativa. | `infrastructure/jobs.py` (`enqueue_generation`, `claim_next_job`, `try_acquire_executor_lock`), migração `0012_scheduler_v1_queue_access` | T23: `test_fifo_claim_is_single_and_global`, `test_enqueue_is_idempotent`, `test_stale_attempt_token_cannot_write`; índice único parcial de `RUNNING`/`VALIDATING` global. |
| W08.3 | Heartbeat, supervisor e recuperação de processo. | `scheduler_v1_worker.py` (`_monitor_attempt`), `scheduler_recovery_worker.py` (`scheduler.v1.supervise`), `infrastructure/jobs.py` (`reconcile_abandoned`, `heartbeat_and_poll`) | C16: `test_abandoned_attempt_is_failed_and_retried`, `test_cancellation_is_idempotent_in_each_phase`; heartbeat e cancelamento usam ligação própria durante o solve (search em `asyncio.to_thread`). |
| W08.4 | Proposta e relógio de 28 dias atómicos. | `infrastructure/proposals.py` (`persist_proposal`), `application/publishing.py` | T21–T22 persistidos: `test_successful_generation_persists_a_proposal_and_restarts_the_clock`, `test_rejection_keeps_the_clock_and_does_not_unlock_a_reroll`, `test_periodic_renewal_unlocks_after_28_days`. |
| W08.5 | Aprovação e reconciliação numa transação. | `infrastructure/proposals.py` (`approve_proposal`, `reject_proposal`) | T27/T24: `test_approval_revalidates_and_activates_the_version`; conflito de revisões marca `STALE` e mantém a versão ativa; `test_pending_proposal_diff_and_approval_through_the_api`. |

Fecho: a fila é reclamada por ordem FIFO, um cálculo global de cada vez, e cada resultado é escrito com verificação de token.
O supervisor do Beat recupera tentativas abandonadas e acorda o executor quando há trabalho em espera.
O dispatcher só acorda o executor; a base de dados decide o pedido elegível.

## 3. W09 — API e aplicação escolar

| ID | Entrega | Ficheiros principais | Teste/evidência |
| :--- | :--- | :--- | :--- |
| W09.1 | Contratos, autorização e geração idempotente. | `api/v1/endpoints/scheduler.py`, `schemas.py` (`SchedulerV1*`), `features/scheduling/data.js` | `test_generate_returns_202_and_dispatches_once`, `test_generate_is_idempotent_for_the_same_click`, `test_generate_commits_the_job_before_dispatching`, `test_generate_conflicts_with_a_stale_revision`; `GET /status` não escreve (`test_cancel_is_idempotent_and_get_does_not_write`). Organização deriva do utilizador autenticado. |
| W09.2 | Estado, fila, cancelamento e motivos de elegibilidade. | `infrastructure/queries.py`, `Schedules.jsx`, `GenerationStatusPanel.jsx` | `test_status_reports_first_generation_for_a_configured_year`, `test_status_never_writes`, `test_enqueue_requires_a_reason_after_a_success`; mensagens escolares para fila, impossibilidade e interrupção. Nenhuma ocorrência inicia o solver. |
| W09.3 | Proposta, diferenças, alertas e aprovação. | `application/publishing.py` (`build_diff`), `DraftPanel.jsx`, `queries.py` | `test_scheduler_publishing_v1` separa alterações físicas de atualizações modulares; alerta de excesso sobre a preferência permanece visível; proposal `STALE` bloqueia a aprovação com explicação. |
| W09.4 | Turmas, sumários, ocorrências, mapas e acertos. | `infrastructure/operations.py`, `services/schedule_*`, `services/class_service.py`, `LessonLogModal.jsx`, `features/operations/data.js` | `test_a_completed_lesson_log_credits_the_ledger_once`, `test_an_occurrence_creates_audited_debt_and_completion_settles_it`, `test_manual_adjustments_add_and_remove_minutes`, `test_the_week_map_exposes_multiple_slices_and_conserved_minutes`; `week_schedule` devolve `slices` com minutos por módulo e `lesson_log_status` do ledger v1. |
| W09.5 | Acessibilidade e percurso escolar completo. | `Schedules.jsx`, `DraftPanel.jsx`, `GenerationStatusPanel.jsx`, adaptador do tutorial | Testes de frontend (409) incluem fluxo de geração/aprovação, proposta desatualizada, alerta da preferência e tutorial; `npm run verify` e `npm run audit:production` verdes; imagens Docker locais reconstruídas. |

Fecho: o percurso manual do proprietário usa apenas a interface, sem linguagem técnica e sem intervenção na base de dados.

## 4. Decisões e fronteiras desta entrega

- A estratégia é escolhida pelo servidor: `ADAPTIVE_RECOVERY` quando existe versão publicada; `COMPLETE_GENERATION` caso contrário.
- O `POST /scheduler/generate` recebe chave idempotente e revisão esperada. Devolve `202`; `409` para estado/revisão incompatível; `422` para configuração inválida.
- Falhas de dispatch mantêm o pedido em fila. O supervisor acorda o executor; reenviar o mesmo pedido é permitido.
- Regras `lock_time` são recusadas com `LOCKED_TIMESLOT_UNSUPPORTED` (422), porque a interseção de elegibilidade v1 não tem um campo de restrição por atribuição. É uma limitação explícita, não um silêncio.
- A política de recuperação v1 (`v1-uncalibrated`) tem coeficientes explícitos e versionados. A calibração é trabalho de W11.
- O aviso de conclusão depois da data preferencial é persistente enquanto a proposta pendente o mostrar.
- O registo de aula/ocorrência v1 escreve no ledger curricular v1 (tabela `scheduler_lesson_log_v1`). A página de análise de ocorrências continua a ler o modelo antigo até W12.

## 5. Verificações executadas

| Verificação | Resultado |
| :--- | :--- |
| `pytest tests/unit` (backend) | 756 passed (753 anteriores + teste de `build_diff`). |
| `node scripts/test.mjs integration` (Docker local, PostgreSQL real) | 333 passed + 47 testes de contratos. Inclui os novos `test_scheduler_v1_lifecycle`, `test_scheduler_v1_operations`, `test_scheduler_v1_api` e a adaptação de `test_scheduler_status`, `test_scheduler_tenant_isolation`. |
| `ruff check` e `ruff format` (backend) | limpos. |
| `npm run lint`, `lint:dead-code`, `verify`, `audit:production` (frontend) | verdes; `npm run test` 409 passed. |
| Imagens Docker locais | `cronos-backend:local` e `cronos-frontend:local` reconstruídas; `cronos-backend-1` saudável; frontend 200. |
| Migrações locais | `0011` → `0012` → `0013` aplicadas (`docker compose --profile maintenance run --rm db-maintenance`). |

Regressões permanentes novas: `test_scheduler_v1_lifecycle`, `test_scheduler_v1_operations`, `test_scheduler_v1_api`, `test_scheduler_publishing_v1`.
As regressões das nove otimizações (`test_scheduler_w05_audit`, `test_scheduler_w04_w05_regressions_v1`, `test_scheduler_search_v1`, `test_scheduler_generation_v1`) continuam verdes.

## 6. Limites conhecidos

- A campanha C16–C17 em containers com falhas induzidas completas é da W10; a W08 ensaia falha e recuperação ao nível da fila e do processo com PostgreSQL real.
- O E2E Playwright foi adaptado ao novo contrato, mas exige a pilha local com Clerk. A execução fica registada para o proprietário.
- A calibração de coeficientes, workers 1/2/4/8 e agrupamento de salas é da W11.
- A remoção do motor antigo, dos endpoints de reset legado e dos consumidores de progresso antigos é da W12.

A próxima ação é W10 (campanhas combinadas e anuais) com os corpus existentes e as novas campanhas C12–C17.
