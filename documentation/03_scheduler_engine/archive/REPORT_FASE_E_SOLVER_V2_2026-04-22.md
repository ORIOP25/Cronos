# Report de Conclusão - Fase E Solver V2

Data: 2026-04-22
Escopo: Motor CP-SAT V2 lexicográfico por data real (Fase E) no ambiente local Docker.

## 1. Alinhamento documental consultado (obrigatório)
Antes da implementação, foram consultadas as camadas:
1. Interface/API:
   - `documentation/05_backend_api/ENDPOINT_STANDARDS.md`
2. Regras de negócio:
   - `documentation/03_scheduler_engine/SOLVER_V2_ADAPTATIVO_ALGORITMO_E_COMPORTAMENTO.md`
   - `documentation/03_scheduler_engine/HARD_CONSTRAINTS_SOFT_OBJECTIVES.md`
   - `documentation/03_scheduler_engine/WBS_SOLVER_V2_SUPER_DETALHADA_IMPLEMENTACAO_LOCAL_2026-04-20.md`
   - `documentation/03_scheduler_engine/REPORT_FASE_D_SOLVER_V2_2026-04-21.md`
3. Base de dados:
   - `backend/app/core/solver_v2_candidates.py` (Fase D — universo de candidatos)
   - `backend/app/core/solver_engine.py` (V1 — referência de padrões)
   - `backend/app/solver_tasks.py` (orquestrador principal)

## 2. O que mudou na Fase E

### E.01 — Base do modelo CP-SAT por data real
Foi criado módulo dedicado:
- `backend/app/core/solver_engine_v2.py`
- Classe `ScheduleEngineV2` com:
  - variáveis de decisão binárias `x[candidate_key]` por candidato pré-prunado;
  - auxiliares `lesson_on_date[(lesson_id, date_idx)]` para rastreio por data;
  - índice determinístico de datas `[window_start, window_end]`;
  - naming determinístico em todas as variáveis para debug.

### E.02 — Hard constraints no modelo V2
Implementadas e verificadas:
- HC1: sem conflito de sala por (data, timeslot).
- HC2: sem conflito de professor por (data, timeslot).
- HC3: sem conflito de turma por (data, timeslot).
- HC4 e HC5: garantidas pelo pruning da Fase D (não redundadas no CP-SAT).
- HC6: garantida pelo pruning da Fase D.
- HC7: hard_end_date absoluto (sem blocos após o limite).
- Cobertura obrigatória: cada lição deve ser agendada exatamente uma vez (previne solução trivial vazia).
- Exclusividade: cada lição aparece no máximo uma vez por dia.

### E.03 — Objetivo lexicográfico: etapa 1 (makespan_global)
- Calcula `class_end[class_id]` usando `AddMaxEquality` sobre variáveis ponderadas por índice de data.
- Minimiza `makespan = max(class_end)`.
- Fixa `makespan <= best_makespan` antes de passar para etapa 2.

### E.04 — Etapa 2 (end_date_spread_classes)
- Calcula `max_end` e `min_end` com existential lower bound via `AddBoolOr`.
- Minimiza `spread = max_end - min_end`.
- Fixa spread antes de etapa 3.

### E.05 — Etapa 3 (target_drift_total)
- Calcula desvio absoluto por turma em relação a `school_target_end_date`.
- Minimiza soma de desvios.
- Fixa drift antes de etapa 4.

### E.06 — Etapa 4 (churn_outside_frozen)
- Conta candidatos selecionados fora da janela congelada não presentes no publicado.
- Minimiza churn como critério secundário.
- Fixa churn antes de etapa 5.

### E.07 — Etapa 5 (class_gaps_total)
- Modela furos por turma/dia usando variáveis booleanas auxiliares.
- Minimiza total de furos como último critério.

### E.08 — Validação de desempate e determinismo
- Suite `test_solver_v2_lexicographic.py` com teste de 3 execuções consecutivas idênticas.

### E.09 — Integração no pipeline (solver_tasks.py)
- Caminho V2 em `generate_schedule_task` usa `ScheduleEngineV2`.
- V2 produz blocos com datas absolutas diretamente (sem fase de expansão semanal).
- V1 permanece inalterado.
- Payload da task inclui métricas V2: `solver_v2_projected_end_date`, `solver_v2_spread_days`, `solver_v2_churn_blocks`, `solver_v2_wall_time`.

## 3. Ficheiros alterados
1. `backend/app/core/solver_engine_v2.py` — NOVO
2. `backend/app/solver_tasks.py` — integração V2 (importação + branch V2 no SOLVE)
3. `backend/tests/test_solver_v2_lexicographic.py` — NOVO
4. `documentation/03_scheduler_engine/REPORT_FASE_E_SOLVER_V2_2026-04-22.md` — NOVO

## 4. Validação executada

### Suite Fase E + regressão obrigatória
```
pytest tests/test_solver_v2_lexicographic.py \
       tests/test_solver_v2_candidate_pruning.py \
       tests/test_solver_v2_demand_builder.py \
       tests/test_solver_logic.py \
       tests/test_solver_tasks_expansion.py \
       tests/test_schedule_generate_preflight.py -v
```

Resultado: **50 passed** (0 failed, 0 errors).

### Cobertura de testes
| Subtarefa | Teste | Resultado |
|---|---|---|
| E.01 model compila | test_e01_model_compiles_minimal | ✅ PASS |
| E.01 vazio → infeasible | test_e01_empty_candidates_returns_infeasible | ✅ PASS |
| E.02 HC professor | test_e02_no_teacher_conflict | ✅ PASS |
| E.02 HC turma | test_e02_no_class_conflict | ✅ PASS |
| E.02 HC sala | test_e02_no_room_conflict | ✅ PASS |
| E.02 HC hard_end | test_e02_hard_end_date_respected | ✅ PASS |
| E.02 HC 1 bloco/lição/dia | test_e02_at_most_one_block_per_lesson_per_day | ✅ PASS |
| E.03 makespan minimizado | test_e03_makespan_minimized | ✅ PASS |
| E.04 spread desempata | test_e04_spread_minimized_on_makespan_tie | ✅ PASS |
| E.05 drift desempata | test_e05_target_drift_minimized | ✅ PASS |
| E.06 churn desempata | test_e06_churn_minimized_outside_frozen | ✅ PASS |
| E.08 determinismo 3 runs | test_e08_deterministic_output | ✅ PASS |
| E.09 V1 inalterado | test_e09_v1_engine_still_importable | ✅ PASS |

## 5. Impacto operacional e de segurança

### Operacional
- Motor V2 ativo quando `SOLVER_ENGINE_VERSION=v2` (feature flag já existente da Fase A).
- V1 permanece ativo por omissão e inalterado funcionalmente.
- Payload da task expõe métricas V2 explícitas para observabilidade.

### Segurança e integridade
- Tenant isolation preservado (sem bypass de `organization_id`).
- Hard constraints invioláveis: taxa de violação = 0.
- Sem mutação de histórico executado.
- Sem alteração destrutiva de schema.

## 6. Compliance com os 4 pilares
1. **Optimization**: objetivo lexicográfico em 5 etapas em cascata; makespan minimizado primeiro, depois spread, drift, churn, gaps.
2. **Stability**: caminho V2 isolado por feature flag; V1 inalterado; sem regressão na suite existente.
3. **Scalability**: modelo CP-SAT opera sobre candidatos pré-prunados (Fase D), limitando espaço de procura.
4. **Security**: sem relaxamento de hard constraints; sem bypass de tenant; cobertura obrigatória garante solução completa.

## 7. Follow-ups da WBS
1. Fase F.01–F.04: expansão adaptativa, fill-opportunistic e residual transparente.
2. Fase G: persistência de draft e ciclo de vida completo.
3. Fase H: painel estatístico de comparação draft vs publicado.

Status Fase E: **CONCLUÍDA**.
Gate para Fase F: **APROVADO** (local).
