# Report de Conclusão - Fase F Solver V2

Data: 2026-04-22
Escopo: Expansão adaptativa, fill-opportunistic e residual transparente (Fase F) — ambiente local Docker.

## 1. Alinhamento documental consultado
- `documentation/03_scheduler_engine/WBS_SOLVER_V2_SUPER_DETALHADA_IMPLEMENTACAO_LOCAL_2026-04-20.md` (F.01–F.04)
- `documentation/03_scheduler_engine/SOLVER_V2_ADAPTATIVO_ALGORITMO_E_COMPORTAMENTO.md` (§5.4 Fill-opportunistic)
- `documentation/03_scheduler_engine/HARD_CONSTRAINTS_SOFT_OBJECTIVES.md` (hard constraints durante fill)
- `documentation/03_scheduler_engine/REPORT_FASE_E_SOLVER_V2_2026-04-22.md` (baseline de entrada)

## 2. O que mudou na Fase F

### F.01 — Validação de calendário (safety net)
- Função `validate_v2_blocks_calendar(blocks, blocked_dates, hard_end_date)`.
- Particiona blocos V2 em válidos vs rejeitados.
- Rejeitados: datas bloqueadas por calendário OU após `hard_end_date`.
- Em pipeline correto (Fase D já excluiu essas datas dos candidatos), rejected=[] sempre.
- Emite `logger.warning` se ocorrer rejeição inesperada.

### F.02 — Fill-opportunistic
- Função `fill_opportunistic_v2(primary_blocks, ...)`.
- Estratégia: o CP-SAT (Fase E) escolhe o slot ótimo (1 ocorrência/lição). O fill repete esse
  padrão semanal para cobrir o backlog remanescente de cada lição.
- Mantém hard constraints durante fill:
  - sem dupla-reserva de professor por (data, timeslot);
  - sem dupla-reserva de turma por (data, timeslot);
  - sem dupla-reserva de sala por (data, timeslot).
- Respeita datas bloqueadas (`blocked_dates`).
- Respeita `hard_end_date` absoluto.
- Para quando backlog chega a 0 (não gera blocos desnecessários).

### F.03 — Residual transparente
- Função `compute_residual_summary(backlog_by_lesson, fill_result, hard_end_date)`.
- Computa `backlog_remaining_minutes` após fill.
- Expõe `backlog_remaining_hours`, `hard_limit_reached`, `detail` (mensagem explícita).
- Nunca mascara impossibilidade: se carga não coube, `detail` inclui data-limite e horas residuais.

### F.04 — Suite de testes
- `backend/tests/test_solver_v2_expansion_fill.py` — 13 testes cobrindo F.01, F.02, F.03.

### Integração no pipeline V2 (solver_tasks.py)
- Importação do módulo `solver_v2_expansion`.
- Na branch V2 pós-solve:
  1. F.01: `validate_v2_blocks_calendar` (safety net).
  2. F.02: `fill_opportunistic_v2` (backlog → janela completa).
  3. F.03: `compute_residual_summary`.
  4. Métricas V2 enriquecidas: `solver_v2_fill_blocks_added`, `solver_v2_backlog_remaining_hours`, `solver_v2_hard_limit_reached`.
  5. `residual.detail` usado diretamente no campo `detail` do resultado da task.

## 3. Ficheiros alterados
| Ficheiro | Estado | Escopo |
|---|---|---|
| `backend/app/core/solver_v2_expansion.py` | NOVO | F.01, F.02, F.03 |
| `backend/tests/test_solver_v2_expansion_fill.py` | NOVO | Suite F.04 |
| `backend/app/solver_tasks.py` | MODIFICADO | Wiring F.01–F.03 na branch V2 |
| `documentation/03_scheduler_engine/REPORT_FASE_F_SOLVER_V2_2026-04-22.md` | NOVO | Este relatório |

## 4. Resultado dos testes

```
pytest tests/test_solver_v2_expansion_fill.py \
       tests/test_solver_v2_lexicographic.py \
       tests/test_solver_v2_candidate_pruning.py \
       tests/test_solver_v2_demand_builder.py \
       tests/test_solver_logic.py \
       tests/test_solver_tasks_expansion.py \
       tests/test_schedule_generate_preflight.py -v
```

**63 passed, 0 failed** (22.42s).

### Cobertura Fase F
| Subtarefa | Teste | Resultado |
|---|---|---|
| F.01 blocos válidos passam | test_f01_valid_blocks_pass_unchanged | ✅ PASS |
| F.01 blocos em data bloqueada rejeitados | test_f01_blocks_on_blocked_date_are_rejected | ✅ PASS |
| F.01 blocos após hard_end rejeitados | test_f01_blocks_after_hard_end_are_rejected | ✅ PASS |
| F.01 particionamento misto | test_f01_mixed_blocks_partitioned_correctly | ✅ PASS |
| F.02 fill cobre backlog multi-semana | test_f02_fill_covers_backlog_across_window | ✅ PASS |
| F.02 fill para quando backlog=0 | test_f02_fill_stops_when_backlog_zero | ✅ PASS |
| F.02 fill ignora datas bloqueadas | test_f02_fill_skips_blocked_dates | ✅ PASS |
| F.02 fill respeita conflito professor | test_f02_fill_respects_teacher_conflict | ✅ PASS |
| F.02 fill respeita conflito sala | test_f02_fill_respects_room_conflict | ✅ PASS |
| F.02 primary vazio → sem fill | test_f02_empty_primary_returns_zero_blocks | ✅ PASS |
| F.03 residual=0 quando coberto | test_f03_residual_zero_when_fully_covered | ✅ PASS |
| F.03 horas residuais explícitas | test_f03_residual_reports_remaining_hours_explicitly | ✅ PASS |
| F.03 invariante scheduled+remaining=total | test_f03_residual_scheduled_plus_remaining_equals_total | ✅ PASS |

## 5. Compliance com os 4 pilares
1. **Optimization**: fill-opportunistic melhora ou mantém `projected_end`, nunca piora.
2. **Stability**: V1 inalterado; branch V2 isolada por feature flag; sem regressão (63/63).
3. **Scalability**: fill percorre apenas candidatos do padrão CP-SAT — O(dias × lições).
4. **Security**: hard constraints mantidas durante fill; tenant isolation preservado.

## 6. Follow-ups da WBS
1. Fase G: persistência de draft e ciclo de vida completo (aprovação manual).
2. Fase H: painel estatístico comparativo draft vs publicado.

Status Fase F: **CONCLUÍDA**.
Gate para Fase G: **APROVADO** (local).
