# W06–W07 — relatório do gate G3 após o ciclo de correção

Data: 25 de setembro de 2026. Branch: `codex/scheduler-v1-revamp`.

Referências: [revisão e WBS de correção](SCHEDULER_V1_W06_W07_REVIEW_WBS.md), [registo as-built](SCHEDULER_V1_W06_W07_STATUS.md), [plano v2](SCHEDULER_V1_REVAMP_PLAN_V2.md), [WBS v2](SCHEDULER_V1_WBS_V2.md).

## 1. Decisão

As correções R67.01–R67.09 foram aplicadas com testes vermelho-primeiro `E01`–`E08`, bateria de oráculo alargada e campanhas combinadas. O gate G3 é reconsiderado como **aceite no âmbito corrigido**, com os limites declarados na secção 6.

Nenhum push, deployment ou ensaio Railway/Cloudflare foi executado. A fila, a aprovação e os replays anuais mantêm-se em W08–W12.

## 2. Contraexemplos da revisão

Todos têm regressão permanente em `backend/tests/unit/test_scheduler_w06_w07_review_regressions_v1.py`.

| ID | Falha reproduzida | Correção | Resultado |
| :--- | :--- | :--- | :--- |
| E01 | Reparação substituía um baseline válido por uma solução pior pelo próprio vetor. | Incumbente inicial = baseline validado; poda por limite seguro derivado do vetor; estabilização por identidade publicada (R67.01, R67.03). | `test_e01_a_valid_baseline_is_never_replaced_by_a_worse_repair`: vetor do resultado ≤ vetor do baseline. |
| E02 | Matching de salas trocava salas coordenadamente e piorava a perturbação. | Penalização de sala publicada como primeira etapa subordinada em `_solve_scope` e `_optimize_rooms` (R67.02). | `test_e02_room_matching_cannot_worsen_the_adaptive_vector`: perturbação 0 e salas publicadas mantidas. |
| E03 | Movimento sem `source_lesson_id` contado como remoção + inserção. | Emparelhamento de identidades por atribuição e ordem cronológica no detalhe e na métrica (R67.03). | `test_e03_a_moved_lesson_keeps_its_published_identity`: um `MOVED`, custo `move_cost`. |
| E04 | Aula protegida contava como excesso de cobertura. | Cobertura avaliada apenas na parte editável; o residual já desconta crédito protegido (R67.04). | `test_e04_a_protected_lesson_is_not_counted_as_excess`. |
| E05 | Baseline com conflito físico era declarado válido. | Baseline completo é revalidado pelo validador independente, incluindo conflitos, duplicados, cronologia e proteção (R67.04). | `test_e05_a_baseline_with_a_resource_conflict_is_invalid`. |
| E06 | Orçamento somava construção e pesquisa duas vezes; finalização contava desde o início. | Contabilidade por deltas monotónicos de fase (R67.05). | `test_e06_the_budget_sums_phase_deltas_without_double_counting`: fases 1+2+1 = 4 s = tempo de parede. |
| E07 | Cancelamento durante a finalização devolvia `COMPLETE` com proposta. | Verificação de cancelamento antes da finalização e antes de entregar a proposta (R67.06). | `test_e07_cancellation_after_the_search_response_is_respected`: `CANCELLED` sem candidato. |
| E08 | Limites `inf` e `nan` aceites. | `ExecutionBudget` exige limite finito e positivo (R67.05). | `test_e08_the_safety_limit_must_be_finite`. |

## 3. Correções estruturais

| ID | Trabalho | Evidência |
| :--- | :--- | :--- |
| R67.01 | Baseline validado como incumbente, poda com limite inferior seguro (`preferred_day + excesso`), exploração de semanas posteriores permitida. | Bateria de oráculo; E01; `test_the_repair_prunes_by_the_incumbent_week_allowing_the_same_week`. |
| R67.02 | Salas passam a respeitar o vetor adaptativo em ambos os caminhos de matching; refinamento só com melhoria estrita. | E02; `test_audit_room_continuity_can_reopen_positions_in_one_window` (regressão W05 mantida). |
| R67.03 | Origem única do baseline: emparelhamento explícito no detalhe e na métrica; cada transformação contada uma vez. | E03; `test_a_displacement_without_a_source_is_one_movement`; oráculo de correspondência nos casos pequenos. |
| R67.04 | Diagnóstico de cobertura editável; validade pelo validador independente. | E04, E05; `test_missing_and_excess_coverage_are_reported_separately`. |
| R67.05 | Orçamento por deltas; validação, qualidade e sumário medidos antes do fecho; `inf`/`nan` rejeitados. | E06, E08; `test_budget_phases_cover_construction_search_and_persistence`. |
| R67.06 | Cancelamento consultado antes da finalização e da entrega; persistência condicionada em W08. | E07; `test_an_explicit_cancellation_never_returns_a_partial_repair`. |
| R67.07 | Trajetória sobre o vetor adaptativo completo, exploração mínima após a primeira solução, mínimo de propostas exploradas, replay pelo vetor completo. | `test_scheduler_stop_policy_v1.py`; `test_r67_07_*`. |
| R67.08 | Bateria alargada: eventos corretos por turma/professor/sala, créditos parciais, escassez, semanas distantes, meta ultrapassada, hard end, aula protegida, urgência, reincidência e dívida aberta. | `test_scheduler_w06_oracle_battery_v1.py` (15 testes contra o oráculo enumerativo). |
| R67.09 | Campanhas combinadas `w06-w07-combined` (18 casos, C02–C15 + anual) e trajetórias C19. | Secções 4 e 5. |

## 4. Campanha combinada C02–C15

`python -m app.scheduler.lab.campaign --manifest backend/tests/scheduler_lab/repair_manifest.json --mode repair --time-limit 5`

Resultado: 18 casos, **12 `VALID`**, **5 `INFEASIBLE`**, **1 `INCONCLUSIVE`**.

| Caso | Família | Resultado | Excesso (dias) | Perturbação | Alterações | Tempo (ms) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| c02-single-cancel | C02 | VALID | 0 | 10 | 1 | 15 |
| c02-room-closed | C02 | VALID | 0 | 10 | 1 | 16 |
| c03-shared-cancel | C03 | VALID | 0 | 10 | 1 | 14 |
| c03-shared-absence | C03 | INFEASIBLE | — | — | — | 0 |
| c04-proven-impossible | C04 | INFEASIBLE | — | — | — | 0 |
| c04-room-impossible | C04 | INFEASIBLE | — | — | — | 0 |
| c05-multi-mutation | C05 | VALID | 0 | 10 | 1 | 0 |
| c06-teacher-scarce | C06 | INFEASIBLE | — | — | — | 0 |
| c07-scarce-room | C07 | VALID | 0 | 10 | 1 | 31 |
| c08-intersection | C08 | VALID | 0 | 10 | 1 | 30 |
| c09-distant-weeks | C09 | VALID | 0 | 10 | 1 | 16 |
| c10-margin | C10 | VALID | 0 | 10 | 1 | 14 |
| c11-urgency | C11 | VALID | 0 | 100 | 1 | 16 |
| c12-multi-mutation | C12 | VALID | 0 | 10 | 1 | 15 |
| c13-partial-credit | C13 | INFEASIBLE | — | — | — | 0 |
| c14-reserved | C14 | VALID | 0 | 10 | 1 | 16 |
| c15-protected-window | C15 | VALID | 0 | 110 | 1 | 0 |
| annual-10-loose-cancel | C14 | INCONCLUSIVE (limite 5 s) | — | — | — | 4500 |

Casos infeasíveis: ausência/indisponibilidade removem a única interseção elegível do professor partilhado ou do recurso indispensável; são impossibilidades demonstradas, não falhas de pesquisa. O caso anual ficou inconclusivo dentro de 5 s e está identificado como tal, sem ser apresentado como sucesso nem como impossibilidade.

Qualidade face ao baseline: quando o baseline publicado continua válido, o resultado nunca é pior pelo vetor completo (E01 e a bateria de oráculo verificam `resultado ≤ baseline`); quando o baseline está obsoleto, o teste compara o resultado com o mínimo enumerado pelo oráculo.

## 5. C19 — trajetórias e política de paragem

`--mode trajectory --time-limit 10` sobre o corpus de escala:

| Caso | Pontos | Resultado | Política | Motivo | Ganho perdido | Tempo poupado |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| gen-scale-10 | 1 | VALID | eager | LOW_EXPECTED_RETURN | não | 8,86 s |
| gen-scale-10 | 1 | VALID | balanced/patient | TRAJECTORY_EXHAUSTED | não | 8,86 s |
| gen-scale-30 | 1 | VALID | eager | LOW_EXPECTED_RETURN | não | 0 s (limite atingido) |

O primeiro candidato nunca produz sozinho `LOW_EXPECTED_RETURN`: o controlador exige o mínimo de propostas exploradas e a exploração mínima após a primeira solução. O replay mede o vetor final e o melhor vetor posterior, com `lost_gain` pelo vetor completo. Trajetórias prolongadas e calibração de coeficientes são W11.

## 6. Verificações e limites

| Verificação | Resultado |
| :--- | :--- |
| `pytest tests/unit` | 753 passed |
| `pytest tests/unit -k scheduler` | 532 passed |
| Integração scheduler v1 (Docker) | 321 passed |
| Contratos backend | 47 passed |
| `ruff check` / `ruff format --check` | limpos em `app/scheduler` e testes novos |
| `node --test scripts/test.test.mjs` | 17 passed (modos `repair` e `trajectory`) |
| Campanha C02–C15 + anual | 12 VALID, 5 INFEASIBLE, 1 INCONCLUSIVE |
| Bateria de oráculo | 15 cenários com vetor igual ao mínimo enumerado |

Limites conhecidos:

- O annual-10 não concluiu em 5 s; fica `INCONCLUSIVE` identificado. Limites reais de laboratório e calibração são W11.
- As trajetórias C19 de casos pequenos têm poucos pontos; os replays ilustram a mecânica, não uma calibração final.
- Persistência, promoção de proposta e cancelamento em W08 usam o mesmo estado de cancelamento e orçamento agora preparados, mas a condição de persistência é implementada lá.
- `w06-w07-combined` cobre C02–C15 em casos pequenos; os replays anuais com eventos acumulados continuam em W10.
