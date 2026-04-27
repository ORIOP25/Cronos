# Report de Conclusao - Fase D Solver V2

Data: 2026-04-21
Escopo: Universo de candidatos por data real, pruning hard-first e telemetria (Fase D) no ambiente local Docker.

## 1. Alinhamento documental consultado (obrigatorio)
Antes da implementacao, foram consultadas as camadas:
1. Interface/API:
- `documentation/05_backend_api/ENDPOINT_STANDARDS.md`
2. Regras de negocio:
- `documentation/03_scheduler_engine/SOLVER_V2_ADAPTATIVO_ALGORITMO_E_COMPORTAMENTO.md`
- `documentation/03_scheduler_engine/HARD_CONSTRAINTS_SOFT_OBJECTIVES.md`
- `documentation/03_scheduler_engine/WBS_SOLVER_V2_SUPER_DETALHADA_IMPLEMENTACAO_LOCAL_2026-04-20.md`
3. Base de dados:
- `documentation/07_data_and_seed/SEED_SCENARIOS.md`
- `documentation/07_data_and_seed/README.md`
- `documentation/README.md`

## 2. O que mudou na Fase D

### D.01 - Gerador de candidatos por data real
Foi criado modulo dedicado para o universo de candidatos V2:
- `backend/app/core/solver_v2_candidates.py`
- estrutura `SolverV2Candidate` com chave deterministica por `lesson/date/timeslot/room`;
- builder `build_candidate_universe(...)` com:
  - recorte por janela rolling primaria;
  - exclusao de datas bloqueadas;
  - expansao por dia real e slots compativeis com `weekday`.

Resultado:
- universo de candidatos reproduzivel para a mesma seed e mesma janela.

### D.02 - Filtro hard de conflitos
Implementado pruning hard-first com remocao de candidatos invalidos por:
- conflito de professor (locks fixos por `teacher/date/timeslot`);
- conflito de turma (locks fixos por `class/date/timeslot`);
- conflito de sala (locks fixos por `room/date/timeslot`).

Nota de arquitetura:
- os locks sao opcionais e preparados para fases seguintes; neste momento o pipeline usa foco em pruning unario e regras hard pre-solve para V2.

### D.03 - Filtro hard de sala, impossible e almoco
No mesmo pruning hard-first:
- remove `room_type` incompatível com `required_room_type`;
- remove disponibilidade `IMPOSSIBLE` (`score=-1`);
- aplica regra hard de almoco por sobreposicao invalida de slot na janela de almoco.

Resultado:
- candidatos intrinsecamente invalidos deixam de entrar no solve do caminho V2.

### D.04 - Telemetria de pruning
Foi adicionada telemetria dedicada:
- `CandidatePruningTelemetry` com:
  - `candidates_before`
  - `candidates_after`
  - `removed_total`
  - `removed_ratio`
  - `removed_by_reason`
- o resultado da task inclui `candidate_pruning` quando `solver_version=v2`.

### D.05 - Suite dedicada da Fase D
Nova suite criada:
- `backend/tests/test_solver_v2_candidate_pruning.py`

Cobertura:
- cardinalidade/determinismo do universo;
- pruning por `room_type`;
- pruning por disponibilidade `IMPOSSIBLE`;
- pruning por locks de conflito (`teacher/class/room`);
- pruning por regra hard de almoco + ratio de remocao.

## 3. Integracao no pipeline
Arquivo alterado:
- `backend/app/solver_tasks.py`

Integracao aplicada:
1. caminho V2 (`solver_version=v2`) constroi universo de candidatos na janela primaria;
2. aplica pruning hard-first antes do solve;
3. publica telemetria no payload final da task;
4. se `candidates_after=0`, retorna `Impossible` imediatamente.

Garantia de estabilidade:
- caminho V1 permanece sem alteracoes funcionais de comportamento.

## 4. Ficheiros alterados
1. `backend/app/core/solver_v2_candidates.py`
2. `backend/app/solver_tasks.py`
3. `backend/tests/test_solver_v2_candidate_pruning.py`
4. `documentation/03_scheduler_engine/README.md`
5. `documentation/05_backend_api/ENDPOINT_STANDARDS.md`
6. `documentation/03_scheduler_engine/REPORT_FASE_D_SOLVER_V2_2026-04-21.md`

## 5. Validacao executada

### Suite Fase D + regressao focada
- `tests/test_solver_v2_candidate_pruning.py`
- `tests/test_solver_tasks_expansion.py`
- `tests/test_solver_v2_demand_builder.py`
- `tests/test_schedule_generate_preflight.py`

Resultado agregado: 31 passed.

### Gate alpha focado
- `tests/test_alpha_release_gate.py -k generation_full_and_repair_allowed`

Resultado: 1 passed.

## 6. Impacto operacional e de seguranca

### Operacional
- prepara o caminho V2 para reduzir espaco de procura com pruning hard-first observavel;
- adiciona sinal operativo de qualidade de entrada (`candidate_pruning`) por run;
- facilita comparacao de execucoes V2 em fases seguintes (E/F).

### Seguranca e integridade
- tenant isolation preservado (sem bypass de `organization_id`);
- hard constraints reforcadas no pre-processamento do caminho V2;
- sem mutacao de historico executado;
- sem alteracao destrutiva de schema.

## 7. Compliance com os 4 pilares
1. Optimization:
- pruning hard-first elimina candidatos inviaveis antes do solve no caminho V2.

2. Stability:
- mudanca isolada ao caminho V2 por feature flag (`solver_version`), mantendo V1 intacto.

3. Scalability:
- telemetria de pruning cria base objetiva para tuning de cardinalidade nas fases E/F.

4. Security:
- sem relaxamento de regras hard; sem alteracoes de autorizacao/ownership.

## 8. Follow-ups da WBS
1. Fase E.01-E.09: modelo CP-SAT V2 por data real com objetivo lexicografico.
2. Reusar `candidate_pruning` como sinal de entrada para tuning de desempenho e explainability.

Status Fase D: CONCLUIDA.
Gate para Fase E: APROVADO (local).
