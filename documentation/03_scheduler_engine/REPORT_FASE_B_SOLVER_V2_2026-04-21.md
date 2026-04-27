# Report de Conclusao - Fase B Solver V2

Data: 2026-04-21
Escopo: Fase B (modelo de demanda e backlog unico) no ambiente local Docker.

## 1. O que mudou

### 1.1 Estrutura de demanda V2
Implementado no pipeline de solver:
- novo tipo interno `SolverV2Demand` com campos:
  - `class_id`
  - `subject_id`
  - `module_id` (modulo ativo)
  - `backlog_minutes`
  - `target_end_date`

### 1.2 Backlog unico por licao
A construcao de demanda passou a usar backlog unico de minutos por licao:
- sem separacao por categorias de divida no caminho de geracao;
- normalizacao defensiva com `max(0, ...)` e minutos inteiros.

### 1.3 Regra de modulo ativo e transicao imediata
Implementada resolucao sequencial de modulo ativo por ordem:
- identifica o primeiro modulo nao concluido (`hours_completed < hours_total`);
- calcula backlog total a partir do modulo ativo em diante;
- quando modulo atual fecha a 100 por cento, o seguinte torna-se ativo no mesmo ciclo (sem intervalo artificial).

### 1.4 Integracao no builder de inputs do solver
`_build_lesson_inputs` passou a ser alimentado pela demanda V2:
- mantem compatibilidade com fluxo atual;
- continua a suportar credito de minutos comprometidos em repair.

## 2. Porque mudou
Ajuste para alinhar o motor com as decisoes fechadas do Solver V2:
1. demanda orientada ao modulo ativo;
2. backlog unico de horas por alocar;
3. cadeia modular com ordem estrita e transicao imediata.

## 3. Impacto operacional e de seguranca

### Operacional
- melhora rastreabilidade da carga curricular por licao e modulo ativo;
- prepara base tecnica para horizonte hibrido e solve lexicografico das fases seguintes;
- nao altera o contrato externo de endpoints nesta fase.

### Seguranca e integridade
- tenant isolation mantido (nenhuma mudanca em filtros por organizacao);
- hard constraints nao foram alteradas;
- historico executado continua imutavel;
- sem escrita parcial nova: alteracao ficou no build de inputs (camada de preparacao).

## 4. Validacao executada

### Suite dedicada Fase B
- `tests/test_solver_v2_demand_builder.py`
- resultado: 4 passed em 3 execucoes consecutivas.

### Regressao solver
- `tests/test_solver_tasks_expansion.py` + `tests/test_solver_logic.py`
- resultado: 17 passed.

### Regressao preflight/API
- `tests/test_schedule_generate_preflight.py`
- resultado: 13 passed.

### Gate alpha focado
- `tests/test_alpha_release_gate.py -k generation_full_and_repair_allowed`
- resultado: 1 passed.

## 5. Ficheiros alterados na Fase B
- `backend/app/solver_tasks.py`
- `backend/tests/test_solver_v2_demand_builder.py`

## 6. Verificacao dos 4 pilares
1. Optimization:
- demanda V2 reduz ambiguidade de carga e prepara pruning/solve posterior sem retrabalho estrutural.

2. Stability:
- alteracao encapsulada no builder; contratos de API e fluxos existentes mantidos.

3. Scalability:
- estrutura de demanda explicita facilita evolucao para heuristicas e telemetria nas fases C/D/E.

4. Security:
- sem alteracao de fronteiras de autorizacao/tenant;
- sem relaxamento de hard constraints.

## 7. Follow-ups obrigatorios (a definir nesta fase)
1. Fase C.01: builder de janela rolling de 8 semanas com datas bloqueadas.
2. Fase C.02: validador de viabilidade ate hard_end_date com residual transparente.
3. Fase C.03: ajuste do contrato de preflight para metadados da janela hibrida.

Status Fase B: CONCLUIDA.
Gate para Fase C: APROVADO (local).
