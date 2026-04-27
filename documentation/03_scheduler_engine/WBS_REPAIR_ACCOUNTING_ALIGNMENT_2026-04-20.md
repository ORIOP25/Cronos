# WBS Tecnica - Repair Accounting Alignment (2026-04-20)

## 1) Objetivo

Resolver a inconsistencia operacional em `mode=repair` onde a divida observada (ex.: 10h) e pequena, mas o resultado reporta carga remanescente massiva (ex.: 2554h) para alem do `school_hard_end_date`.

Escopo desta WBS:
- analise e desenho tecnico;
- plano de execucao faseado;
- criterios de aceitacao e validacao;
- implementacao executada e validada ate WP-8.3 nesta iteracao.

## 2) Contexto e Contrato Atual

Regras que devem permanecer verdadeiras:
1. hard end date e absoluto;
2. repair congela janela curta (`today + repair_stability_window_days`);
3. regeneracao so atua fora da janela congelada;
4. historico de ocorrencias e imutavel;
5. isolamento por tenant (`organization_id`) em todas as leituras/escritas.

Referencias canonicas:
- `documentation/03_scheduler_engine/HARD_CONSTRAINTS_SOFT_OBJECTIVES.md`
- `documentation/04_operational_features/FALTAS.md`
- `documentation/05_backend_api/ENDPOINT_STANDARDS.md`

## 3) Diagnostico Consolidado (Causa-Raiz)

### 3.1 Evidencia de runtime (tenant 1, 2026-04-20)

Diagnostico read-only executado no ambiente atual:

- `TODAY=2026-04-20`
- `repair_window_days=14`
- `frozen_until=2026-05-04`
- `expansion_start=2026-05-05`
- `hard_end=2026-07-31`

Metrica de carga:
- `LESSONS=75`
- `TOTAL_REMAINING_H_RAW=5599.0h` (remanescente bruto usado pelo solver)

Horario ativo publicado:
- `PAST=4706 blocos / 4706.0h`
- `WINDOW(ate frozen)=243 blocos / 243.0h`
- `FUTURE(apos frozen)=651 blocos / 651.0h`

Ocorrencias:
- `GIVEN=1`
- `GAP=10`
- `NONE=5589`

Remanescente ajustado por compromissos ja publicados ate `frozen_until`:
- `TOTAL_REMAINING_H_ADJUSTED=657.0h`

Classe foco:
- `11A TAG`:
  - `remaining_raw_h=647.0h`
  - `remaining_adjusted_h=60.0h`
  - `debt_h=10.0h`

Leitura direta:
- a diferenca entre bruto e ajustado (~4942h) e quase toda a carga ja publicada no passado/janela congelada, mas ainda nao refletida em `ClassProgress`.

### 3.2 Evidencia de codigo

1. Remanescente base para o solver e derivado apenas de modulo total - `hours_completed`:
- `backend/app/solver_tasks.py` (funcao `_compute_remaining_minutes`)
- `backend/app/solver_tasks.py` (funcao `_build_lesson_inputs`)

2. O `progress_map` vem de `ClassProgress.hours_completed`:
- `backend/app/solver_tasks.py` (carregamento de `progress_map`)
- `backend/app/services/schedule_service.py` (funcao `get_class_progress_map_sync`)

3. Em repair, a expansao comeca em `max(school_start_date, frozen_until + 1 dia)`:
- `backend/app/solver_tasks.py` (funcao `_resolve_expansion_start_date`)

4. A expansao consome `remaining_map` ate hard end e retorna residual:
- `backend/app/solver_tasks.py` (funcao `expand_to_dates`)
- `backend/app/solver_tasks.py` (branch com `remaining_after_expand` e detalhe de hard limit)

5. Preflight de repair valida existencia de horizonte fora da janela, nao viabilidade de carga:
- `backend/app/api/v1/endpoints/schedule.py` (funcao `_validate_repair_generation_window`)
- `backend/app/api/v1/endpoints/schedule.py` (funcao `_preflight_check`)

6. Confirmacao automatica GIVEN existe, mas e diaria e para `target_date=today`:
- `backend/app/celery_worker.py` (beat diario 23:59)
- `backend/app/solver_tasks.py` (task `auto_confirm_occurrences_task` usa `today`)
- `backend/app/services/occurrence_service.py` (funcao `auto_confirm_daily_sync`)

### 3.3 Causa-raiz tecnica

A metrica de carga usada pelo repair esta ancorada em `ClassProgress`, enquanto o estado operacional real esta maioritariamente no horario publicado sem ocorrencia (`NONE`).

Assim:
- o solver entende que muito do passado/janela congelada ainda esta "por cumprir";
- mas a expansao so pode agendar de `2026-05-05` a `2026-07-31`;
- resultado: residual massivo e diff estrutural grande, mesmo com divida operacional pequena.

Em termos formais:

- modelo atual (bruto):
  `R_raw = f(ClassProgress.hours_completed)`
- necessidade operacional em repair:
  `R_repair = R_raw - C_committed_upto_frozen + D_explicita_upto_frozen`

onde:
- `C_committed_upto_frozen` = carga publicada ate `frozen_until` que deve contar como compromisso executavel/assumido;
- `D_explicita_upto_frozen` = GAP/SUBSTITUTED que devem continuar a pesar como divida.

## 4) Nao-Objetivos (desta iniciativa)

1. Nao alterar hard constraints do solver.
2. Nao reduzir tenant isolation para ganhar performance.
3. Nao reescrever historico de ocorrencias para "melhorar metricas".
4. Nao trocar repair por geracao class-isolada.

## 5) WBS Tecnica (Detalhada)

## Fase 0 - Governance e Baseline

### WP-0.1 Freeze de contrato funcional
- Descricao: formalizar contrato de accounting para repair (pasto, janela congelada, futuro marcado).
- Entregaveis:
  - ADR curta: "Repair accounting source of truth".
  - Matriz de estados `NONE/GIVEN/GAP/SUBSTITUTED` por periodo (`past`, `frozen`, `post_frozen`).
- Dependencias: nenhuma.
- Criterio de aceitacao:
  - regra univoca aprovada para todos os estados;
  - sem contradicao com docs canonicas de scheduler e ocorrencias.

### WP-0.2 Instrumentacao baseline
- Descricao: consolidar metricas antes de qualquer alteracao.
- Entregaveis:
  - snapshot com `R_raw`, `R_adjusted`, horas publicadas por janela, distribuicao de status.
- Criterio de aceitacao:
  - script read-only reproduzivel por tenant.

## Fase 1 - Modelo Canonico de Accounting

### WP-1.1 Definicao de "compromisso contabilizavel"
- Descricao: definir quando um bloco publicado conta para reduzir remanescente no repair.
- Regra proposta (para validacao):
  1. `date <= frozen_until` e `status in {NONE, GIVEN}` -> conta como compromisso.
  2. `status in {GAP, SUBSTITUTED}` -> nao conta no modulo planeado (mantem divida).
  3. `SUBSTITUTED` conta progresso no modulo executado (ja previsto no modelo de ocorrencias).
- Criterio de aceitacao:
  - tabela de verdade completa com exemplos por estado/data.

### WP-1.2 Fonte canonica de progresso em repair
- Opcao A: backfill de ocorrencias GIVEN historicas e depender de `ClassProgress`.
- Opcao B: manter `ClassProgress` + credito virtual de compromissos publicados ate `frozen_until` durante calculo repair.
- Opcao C: hibrido (B imediata + A como saneamento operacional).
- Criterio de decisao:
  - estabilidade e risco minimo no curto prazo;
  - custo de migracao/controlabilidade;
  - impacto em performance.
- Estado: a definir (recomendacao inicial: Opcao C).

## Fase 2 - Design de Dados e Query Layer

### WP-2.1 Query tenant-scoped para compromissos
- Descricao: desenhar consulta deterministica para `C_committed_upto_frozen` por lesson/modulo.
- Requisitos:
  - sempre filtrar `organization_id`;
  - excluir drafts;
  - respeitar relacao com ocorrencias por `schedule_output_id + date`.
- Criterio de aceitacao:
  - query plana, index-friendly, sem N+1.

### WP-2.2 Normalizacao por duracao de slot
- Descricao: garantir contabilizacao em minutos/hora usando duracao real de timeslot.
- Criterio de aceitacao:
  - sem arredondamentos inconsistentes;
  - soma por aula reproduzivel em reexecucoes.

### WP-2.3 Tratamento de casos limite
- Casos:
  1. `ScheduleOutput.date is null` legado.
  2. bloco com ocorrencia mas sem modulo resolvido.
  3. modulo concluido com excesso de horas.
- Criterio de aceitacao:
  - regras explicitas por caso;
  - sem `bare except`.

## Fase 3 - Scheduler Pipeline Alignment

### WP-3.1 Input de remanescente para repair
- Descricao: introduzir etapa de reconciliacao de remanescente antes de construir `LessonInput`.
- Objetivo:
  - reduzir remanescente inflacionado por carga ja comprometida em passado/janela congelada.
- Criterio de aceitacao:
  - `R_repair <= R_raw` por construcao;
  - diferenca explicavel por metrica auditavel.

### WP-3.2 Guardrail de nao-negatividade
- Descricao: garantir `remaining_minutes >= 0` por lesson apos reconciliacao.
- Criterio de aceitacao:
  - zero underflow;
  - logs com contagem de cortes para zero.

### WP-3.3 Transparencia no payload de status
- Descricao: detalhar no resultado da task:
  - remanescente bruto;
  - remanescente reconciliado;
  - horas comprometidas creditadas;
  - horas de divida explicita.
- Criterio de aceitacao:
  - diagnostico operacional legivel sem aceder a BD.

## Fase 4 - Preflight de Viabilidade Real

### WP-4.1 Feasibility check adicional para repair
- Descricao: manter check de janela e adicionar check de capacidade aproximada para remanescente reconciliado.
- Criterio:
  - erro antecipado quando inviavel de forma obvia;
  - evitar enfileirar tasks condenadas por falta de horizonte efetivo.

### WP-4.2 Contrato de erro explicito
- Descricao: enriquecer `preflight_failed` com motivo operacional objetivo.
- Criterio:
  - mensagem orientada a acao (janela/hard end/capacidade/remanescente).

## Fase 5 - Draft, Diff e Aprovação

### WP-5.1 Coerencia de diff com janela repair
- Descricao: validar se o diff apresentado representa apenas universo relevante de alteracao.
- Observacao:
  - hoje o diff usa `date > today`, nao `date > frozen_until`.
- Estado: a definir conforme UX desejada.
- Criterio de aceitacao:
  - operador entende claramente impacto dentro e fora da janela.

### WP-5.2 Conservacao da janela congelada
- Descricao: manter regra atual de aprovacao que nunca promove alteracoes dentro da janela.
- Criterio de aceitacao:
  - regressao zero desta garantia.

## Fase 6 - Operacoes (Ocorrencias/Auto-Confirm)

### WP-6.1 Estrategia de backlog de auto-confirm
- Problema: auto-confirm diario em `today` nao corrige backlog historico por si.
- Plano:
  - definir job de backfill controlado (por tenant e intervalo de datas), ou
  - manter reconciliacao virtual sem escrita historica (com runbook claro).
- Estado: a definir.
- Criterio de aceitacao:
  - nao existe volume massivo de `NONE` em datas passadas apos saneamento.

### WP-6.2 Runbook de operacao
- Descricao: procedimento para escola/ops ao aproximar hard end.
- Inclui:
  - checklist de ocorrencias pendentes;
  - validacao de divida total e vencida;
  - criterio para trigger de repair.

## Fase 7 - Testes e Qualidade

### WP-7.1 Unit tests (accounting)
Casos minimos:
1. `NONE` passado reduz remanescente em repair.
2. `GAP` passado nao reduz remanescente e conta divida.
3. `SUBSTITUTED` preserva divida no planeado e progresso no executado.
4. janelas mistas com `frozen_until`.

### WP-7.2 Integration tests (end-to-end)
Casos minimos:
1. cenario 11A TAG equivalente: divida 10h, sem residual massivo.
2. hard end curto com bloqueio transparente.
3. repair + ocorrencias futuras ja decididas.
4. aprovacao de draft sem mutar janela congelada.

### WP-7.3 Regressao multi-tenant e performance
- Validar isolamento total por org.
- Medir impacto de novas queries.
- Threshold inicial: aumento de latencia <= 10% no preflight/repair.

## Fase 8 - Rollout Seguro

### WP-8.1 Feature flag por tenant
- Descricao: ativar novo accounting de repair de forma gradual por organizacao.
- Criterio:
  - rollback rapido sem migracao destrutiva.

### WP-8.2 Monitores de rollout
Metricas:
1. `repair_remaining_raw_hours` vs `repair_remaining_reconciled_hours`.
2. `repair_hard_end_residual_hours`.
3. `%occurrences_none_past`.
4. `repair_diff_added_removed_ratio`.

### WP-8.3 Go/No-Go
Go quando:
- hard constraints = 100% preservadas;
- residual inflacionado eliminado nos tenants piloto;
- sem regressao de seguranca/tenant isolation;
- sem regressao relevante de performance.

## 6) Dependencias Tecnicas

1. Alinhamento entre Scheduler, Occurrence Service e API preflight.
2. Dados operacionais confiaveis por tenant.
3. Suites de regressao alpha e cenarios de carga moderada.

## 7) Riscos e Mitigacoes

1. Risco: dupla contabilizacao (compromisso + progresso ja gravado).
- Mitigacao: reconciliacao com guardrail por lesson/modulo + testes de idempotencia.

2. Risco: query pesada em repair.
- Mitigacao: agregacoes diretas por tenant, indices, evitar N+1.

3. Risco: drift documental.
- Mitigacao: atualizar docs canonicas no mesmo PR da implementacao.

4. Risco: efeito colateral em fluxo de dividas.
- Mitigacao: suite dedicada de ocorrencias/debts + canary por tenant.

## 8) Criterios de Aceitacao Globais

1. Cenario tipo 11A TAG:
- remanescente reportado compativel com `(compromissos faltantes + divida real)`;
- nao repetir residual massivo quando divida e baixa.

2. Repair proximo do hard end:
- bloqueio ou transparencia coerente com capacidade real.

3. Integridade operacional:
- janela congelada preservada;
- historico imutavel;
- GAP/GIVEN/SUBSTITUTED respeitados.

4. Quatro pilares:
- Optimization: melhoria do sinal de remanescente e do diff util.
- Stability: sem reescrever curto prazo e sem regressao de hard rules.
- Scalability: queries agregadas por tenant, sem explosao de custo.
- Security: isolamento `organization_id` preservado ponta a ponta.

## 9) Sequencia Recomendada (Execucao)

1. WP-0 + WP-1 (decisao canonica).
2. WP-2 + WP-3 (dados e pipeline repair).
3. WP-4 + WP-5 (preflight/diff/contrato de resposta).
4. WP-6 (operacao e backlog).
5. WP-7 (testes completos).
6. WP-8 (rollout gradual e go/no-go).

## 10) Decisoes Fechadas (2026-04-20)

1. Fonte canonica em repair (curto prazo): Opcao C.
- aplicacao imediata da Opcao B (credito virtual de compromissos publicados ate `frozen_until`);
- backfill historico (Opcao A) fica opcional e controlado por tenant, via runbook.

2. Politica de diff em repair: comparar apenas universo efetivo da reparacao.
- regra final: `date >= frozen_until + 1 dia`.

3. Backfill historico de auto-confirm: nao obrigatorio para entrar em producao.
- estrategia oficial: reconciliacao virtual por defeito;
- backfill manual apenas quando a escola precisar saneamento historico adicional.

4. Limiar de performance para gate de rollout (tenant piloto):
- sem regressao funcional e sem degradacao operacional relevante em preflight/repair;
- referencia inicial de controlo: variacao agregada ate 15% no p95 de preflight/repair durante janela de observacao.

## 11) Fecho de Execucao e Gate WP-8.3

Estado por pacote:
1. WP-2.1/WP-2.2/WP-2.3: concluido.
- query tenant-scoped para compromissos em `backend/app/services/schedule_service.py` (`get_repair_committed_minutes_by_lesson_sync`);
- contabilizacao por duracao real de timeslot;
- exclusao explicita de drafts e de estados `GAP/SUBSTITUTED` no credito.

2. WP-3.1/WP-3.2/WP-3.3: concluido.
- reconciliacao de remanescente no pipeline repair em `backend/app/solver_tasks.py`;
- guardrail de nao-negatividade aplicado por lesson;
- transparencia operacional com `remaining_summary` em respostas de sucesso.

3. WP-4.1/WP-4.2: concluido.
- preflight repair passou a incluir viabilidade por capacidade teorica agregada em `backend/app/api/v1/endpoints/schedule.py`;
- erros de preflight devolvem motivo operacional objetivo (janela/capacidade).

4. WP-5.1/WP-5.2: concluido.
- diff alinhado ao horizonte efetivo (`frozen_until + 1 dia`) em `backend/app/services/schedule_service.py`;
- aprovacao continua sem promover alteracoes dentro da janela congelada (regressao dedicada verde).

5. WP-6.1/WP-6.2: concluido (decisao + operacao).
- estrategia adotada: reconciliacao virtual por defeito;
- runbook operacional publicado em `documentation/09_ops_observability/REPAIR_OPERATIONS_RUNBOOK.md`.

6. WP-7.1/WP-7.2/WP-7.3: concluido.
- backend alvo: `53 passed` em `tests/test_sprint3.py`, `tests/test_solver_tasks_expansion.py`, `tests/test_schedule_generate_preflight.py`, `tests/test_alpha_release_gate.py`;
- frontend completo: `75 passed` (inclui fluxo click-by-click de aprovacao/rejeicao de draft em `frontend/src/test/Schedules.test.jsx`).

7. WP-8.1/WP-8.2/WP-8.3: fechado para piloto controlado.
- WP-8.1 nesta iteracao e aplicado por governance operacional (rollout em 1 tenant), sem feature flag codificada adicional;
- monitorizacao ativa dos sinais `remaining_raw/reconciled`, `hard_end_residual`, `%none_past` e `diff_ratio`;
- decisao final: GO controlado para piloto, mantendo rollback operativo por rejeicao de draft e runbook de saneamento.

---

Documento atualizado apos execucao tecnica e validacao de gate WP-8.3.
