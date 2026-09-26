# W06–W07 — AdaptiveRecovery e diagnóstico (registo as-built)

Data: 25 de setembro de 2026.
Branch: `codex/scheduler-v1-revamp`.
Estado: W06.1–W06.6 e W07.1–W07.4 concluídos após o ciclo de correção da revisão independente (R67.01–R67.09), com testes verdes e campanhas combinadas executadas no Docker local. W08–W14 permanecem plano. Nenhum push, reset ou ensaio Railway/Cloudflare foi executado.

Documentos de referência: [plano v2](SCHEDULER_V1_REVAMP_PLAN_V2.md), [WBS v2](SCHEDULER_V1_WBS_V2.md), [especificação técnica v2](SCHEDULER_V1_TECH_SPEC_V2.md).
Revisão independente e correções: [SCHEDULER_V1_W06_W07_REVIEW_WBS.md](SCHEDULER_V1_W06_W07_REVIEW_WBS.md).
Decisão do gate G3: [SCHEDULER_V1_W06_W07_G3_REPORT.md](SCHEDULER_V1_W06_W07_G3_REPORT.md).

## 1. Resultado

- A reparação usa a mesma coordenação master/detalhe reabrível da geração, com o vetor progressivo de qualidade adaptativa e a versão publicada como referência de perturbação.
- Um baseline invalidado por professor, sala, calendário ou datas é diagnosticado e nunca conservado por ter sido publicado; a reparação recalcula a partir do estado atual.
- A perturbação é medida por transformações físicas reais (inserção, remoção, movimento, mudança de sala), com urgência junto da fronteira editável e reincidência auditável; trocar identificadores não esconde movimentos e uma atualização modular não conta como alteração física.
- Um baseline ainda válido é o incumbente inicial: nenhuma reparação o substitui por uma solução pior pelo vetor completo.
- Certificados, diagnósticos, orçamento e cancelamento são tipados e honestos: interrupção nunca vira impossibilidade, ótimo local não vira ótimo anual e execuções fora do orçamento não são reportadas como dentro.

## 2. W06 — AdaptiveRecovery

| ID | Entrega | Ficheiros principais | Teste/evidência |
| :--- | :--- | :--- | :--- |
| W06.1 | Falta, excesso e aulas inválidas do baseline publicado. | `domain/recovery.py` (`assess_baseline`, `BaselineAssessment`, `BaselineIssue`), `candidate.py` (`baseline_lessons`) | T20: `test_t20_a_teacher_reassignment_is_repaired_instead_of_kept`, `test_e04_a_protected_lesson_is_not_counted_as_excess`, `test_e05_a_baseline_with_a_resource_conflict_is_invalid` |
| W06.2 | Inserção, movimentos e expansão por conflitos sobre o master/detalhe reabrível. | `infrastructure/search.py` (`search_adaptive_schedule`, `_joint_search`), `infrastructure/placement_model.py` (salt de cache, cancelamento) | `test_a_local_infeasibility_reopens_weeks_and_finds_the_witness` (rondas ≥ 2, corte integral), cache por salt |
| W06.3 | Identidades e custo de perturbação; salas após movimentos. | `domain/recovery.py` (`measure_disruption`, `RecoveryPolicy`), `placement_model.py` (`_pair_published_identities`, `_build_candidate`), `search.py` (`_stabilize_recovery`) | `test_swapping_lesson_ids_does_not_hide_an_identical_position`, `test_a_displacement_without_a_source_is_one_movement`, `test_e03_a_moved_lesson_keeps_its_published_identity`, `test_stabilization_returns_a_lesson_to_its_published_position` |
| W06.4 | Proteção progressiva da margem e excesso prioritário. | `domain/quality.py` (`adaptive_quality_vector`), `domain/recovery.py` (`RecoveryQualityMetrics.vector`) | T15–T18 no solver: `test_the_repair_matches_the_enumerated_adaptive_optimum` (seeds com turma, professor e sala) e bateria de oráculo `test_scheduler_w06_oracle_battery_v1` |
| W06.5 | Reconciliação de propostas, dívida e currículo. | `domain/recovery.py` (`reconcile_after_repair`), `domain/debt.py` (reutilizado) | `test_a_proposal_never_settles_debt_but_binds_active_reservations`, `test_open_debt_survives_a_repair_without_being_credited_as_execution` |
| W06.6 | As nove otimizações preservadas sob reparação. | `search.py`, `placement_model.py` | Oráculo adaptativo, salt/invalidação de cache, congelamento (certified_stages 0 sob `SAFETY`), poda pela semana do incumbente com a mesma semana, salas globais, fronteira editável. Regressões W05 continuam verdes. |

Fecho: a reparação guarda o melhor vetor completo e a evidência do âmbito explorado; nunca devolve a primeira cobertura completa por pertencer ao primeiro nível, e nunca piora um baseline válido.

## 3. W07 — Paragem e diagnóstico

| ID | Entrega | Ficheiros principais | Teste/evidência |
| :--- | :--- | :--- | :--- |
| W07.1 | Resultados e certificados tipados. | `domain/results.py` (`OUTCOME_CANCELLED`, `OUTCOME_STALE`), `domain/quality.py` (`SearchEvidence`, prefixo certificado) | `test_scheduler_w07_results_v1.py`: ótimo de janela é `CONDITIONAL_ON_QUOTA_DISTRIBUTION`; ótimo anual é `UNRESTRICTED_EXACT_MODEL`; desconhecido nunca vira impossível |
| W07.2 | Pré-verificações e explicações de conflitos. | `domain/diagnostics.py` (`Diagnosis`, `EvidenceKind`, `diagnose_capacity`, `diagnose_inconclusive`, `diagnose_baseline_stale`, `diagnose_scope_proof`) | `test_scheduler_w07_diagnostics_v1.py`; mínimo de défice só com `PROVEN_LOWER_BOUND`; baseline inválido explicado |
| W07.3 | Controlador de exploração, retorno adicional e honestidade de orçamento. | `domain/stop.py` (`ExecutionBudget`, `ExplorationPolicy`, `TrajectoryPoint`, `decide_stop`, `replay_stop_policy`) | `test_scheduler_stop_policy_v1.py` (C19: ganhos perdidos e esforço poupado); trajetória pelo vetor completo; faseamento em `application/recovery.py` |
| W07.4 | Segurança, finalização e cancelamento. | `domain/stop.py` (`BudgetPhase`, limites finitos), `application/recovery.py` (orçamento por fases e cancelamento antes da finalização), `search.py`/`placement_model.py` (`should_cancel`) | `test_an_explicit_cancellation_never_returns_a_partial_repair`, `test_e07_cancellation_after_the_search_response_is_respected`, `test_e06_the_budget_sums_phase_deltas_without_double_counting`, `test_e08_the_safety_limit_must_be_finite`, `test_an_interrupted_repair_stage_is_never_certified` |

Fecho: política explicável e mensurada, sem p95 como comando de paragem; os coeficientes são explícitos e experimentais até à calibração de W11.

## 4. Integração e laboratório

- Casos de uso: `application/recovery.py` (`repair_schedule`, `RepairResult`) e raiz de composição `repair_published_schedule`.
- Fixtures de reparação: `lab/recovery.py` (eventos determinísticos `CANCEL_LESSON`, `TEACHER_ABSENCE`, `ROOM_CLOSED`, eventos adicionais para mutações múltiplas; expectativa por oráculo em casos pequenos, exploratória em casos construídos).
- Corpus: `backend/tests/scheduler_lab/repair_manifest.json` (campanha `w06-w07-combined`, famílias C02–C15 e um caso anual).
- Modos de campanha: `repair` e `trajectory` (C19), disponíveis na CLI e no runner.
- Serialização: `lab/payload.py` e `lab/manifest.py` transportam baseline, avaliação, diagnósticos, sumário de reparação, orçamento e replays de trajetória; o digest de entrada inclui o baseline.
- Nota deliberada: o hint da reparação continua a ser o arranque greedy earliest-week da geração; um hint derivado do baseline fica para quando houver medição (W11) que o justifique.

## 5. Verificações executadas

| Verificação | Resultado |
| :--- | :--- |
| `pytest tests/unit` | 753 passed |
| `pytest tests/unit -k scheduler` | 532 passed (445 antes de W06/W07; +87 novos) |
| `node scripts/test.mjs integration` (subset scheduler v1) | 321 passed, 0 falhas |
| Contracts backend | 47 passed |
| `ruff check` e `ruff format --check` (`app/scheduler` e testes novos) | limpos |
| `node --test scripts/test.test.mjs` | 17 passed (modos `repair` e `trajectory` incluídos) |
| Campanha `w06-w07-combined` (18 casos, C02–C15 + anual, limite 5s) | 12 `VALID`, 5 `INFEASIBLE` provado, 1 `INCONCLUSIVE` identificado |
| Bateria de oráculo alargada (R67.08) | 15 cenários com vetor igual ao mínimo enumerado |

Regressões permanentes relevantes: `test_scheduler_recovery_v1`, `test_scheduler_recovery_solver_v1`, `test_scheduler_w07_diagnostics_v1`, `test_scheduler_w07_results_v1`, `test_scheduler_stop_policy_v1`, `test_scheduler_lab_recovery_v1`, `test_scheduler_w06_w07_review_regressions_v1`, `test_scheduler_w06_oracle_battery_v1`, a par de `test_scheduler_w05_audit`, `test_scheduler_w04_w05_regressions_v1`, `test_scheduler_search_v1` e `test_scheduler_generation_v1`.

## 6. Ciclo de correção da revisão (R67)

A revisão independente rejeitou o gate com os contraexemplos E01–E08. Correções aplicadas com teste vermelho-primeiro:

- R67.01: o baseline validado é o incumbente inicial e a poda usa um limite inferior seguro derivado do vetor adaptativo, permitindo semanas posteriores.
- R67.02: o matching de salas (modelo de janela e pós-passe) penaliza a sala publicada antes de continuidade e preferências.
- R67.03: o argumento do baseline alimenta o emparelhamento de identidades no detalhe e na métrica; um deslocamento é um movimento único.
- R67.04: o baseline completo é revalidado pelo validador independente e a cobertura é medida só na parte editável.
- R67.05: orçamento por deltas de fase, validação/qualidade/sumário medidos antes do fecho e limites finitos obrigatórios.
- R67.06: cancelamento consultado antes da finalização e antes de entregar a proposta.
- R67.07: trajetória de paragem pelo vetor adaptativo completo, exploração mínima após a primeira solução e replay com ganho perdido pelo vetor.
- R67.08: bateria de oráculo alargada com turmas, professores e salas reais, créditos parciais, urgência, semanas distantes, meta ultrapassada, hard end, aulas protegidas, reincidência e dívida aberta.
- R67.09: campanhas combinadas C02–C15 + anual e modo `trajectory` para C19, com resultados no [relatório G3](SCHEDULER_V1_W06_W07_G3_REPORT.md).

## 7. Limites conhecidos

- A ligação da reparação à fila global, persistência de propostas e aprovação é da W08; `CANCELLED`/`STALE` persistidos e o supervisor são lá completados. A persistência também passa a consumir o orçamento e o estado de cancelamento já preparados.
- A calibração de `g`, `lambda`, custos de perturbação, urgência e limiar de retorno é da W11; o laboratório usa a política `laboratory-default` explicitamente identificada.
- O corpus de reparação cobre casos pequenos; topologias anuais com eventos acumulados são da W10. O caso annual-10 em 5 s fica inconclusivo e identificado como tal.
- Nenhuma medição de qualidade/tempo desta fase constitui baseline de produção.
