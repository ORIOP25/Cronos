# Report de Conclusao - Fase C Solver V2

Data: 2026-04-21
Escopo: Horizonte hibrido e preflight (Fase C) no ambiente local Docker.

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

## 2. O que mudou na Fase C

### C.01 - Builder da janela rolling principal (8 semanas)
Implementado no backend do solver:
- nova funcao para construir janela principal rolling com:
  - inicio por modo (`full` ou `repair`),
  - limite por `hard_end_date`,
  - exclusao de dias bloqueados por calendario,
  - metadados de total/bloqueados/uteis.
- semanas de planeamento passam a ser derivadas da janela principal util.

Resultado:
- o planeamento semanal passa a refletir o horizonte principal V2 (8 semanas), sem ignorar feriados/bloqueios no calculo de capacidade util.

### C.02 - Validador de viabilidade ate hard end
Implementado no preflight:
- calculo de backlog curricular estimado (com fallback para `ClassSubjectLink` quando `Lesson` ainda nao estiver sincronizada);
- calculo de capacidade teorica agregada ate hard end;
- calculo de residual esperado (`expected_residual_hours`).

Politica aplicada:
- `full`: nao bloqueia por insuficiencia; expõe viabilidade e residual esperado no preflight;
- `repair`: bloqueia quando inviavel ate hard end, com mensagem explicita e residual esperado.

### C.03 - Contrato do endpoint de geracao
`POST /api/v1/schedule/generate` agora retorna metadados de preflight hibrido:
- `preflight.mode`
- `preflight.primary_window`
- `preflight.hard_end_feasibility`

Em erro de preflight (`400`):
- payload inclui `error`, `problems` e `preflight` (serializado), evitando erro ambiguo e sem perda de contexto.

## 3. Ficheiros alterados
1. `backend/app/solver_tasks.py`
2. `backend/app/api/v1/endpoints/schedule.py`
3. `backend/app/schemas.py`
4. `backend/tests/test_solver_tasks_expansion.py`
5. `backend/tests/test_schedule_generate_preflight.py`

## 4. Validacao executada

### Suite Fase C
- `tests/test_schedule_generate_preflight.py` -> 14 passed

### Regressao de suporte
- `tests/test_solver_tasks_expansion.py` + `tests/test_solver_v2_demand_builder.py` + `tests/test_solver_logic.py` -> 19 passed
- `tests/test_alpha_release_gate.py -k generation_full_and_repair_allowed` -> 1 passed

## 5. Impacto operacional e de seguranca

### Operacional
- preflight agora e explicito sobre janela principal e viabilidade ate hard end;
- admins recebem contexto de residual esperado antes da execucao;
- `repair` evita runs inviaveis sem horizonte util suficiente.

### Seguranca e integridade
- tenant isolation mantido em queries de preflight;
- hard constraints nao foram relaxadas;
- historico executado continua imutavel;
- sem alteracoes destrutivas de schema/migracao nesta fase.

## 6. Compliance com os 4 pilares
1. Optimization:
- preflight reduz tentativas inviaveis em repair e aumenta qualidade de decisao com metadados objetivos.

2. Stability:
- contrato de erro/sucesso padronizado, com regressao automatizada e serializacao segura.

3. Scalability:
- metadados de janela/viabilidade preparam metricas comparaveis para evolucao das fases D/E.

4. Security:
- isolamento por organizacao preservado; sem bypass de autorizacao; sem mutacao de historico passado.

## 7. Follow-ups da WBS
1. Fase D.01-D.05: universo de candidatos por data real e pruning hard-first com telemetria.
2. Em Fase D, aproveitar `primary_window` e `hard_end_feasibility` como entradas observaveis para auditoria de candidatos.

Status Fase C: CONCLUIDA.
Gate para Fase D: APROVADO (local).
