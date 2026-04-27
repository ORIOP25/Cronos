# Solver V2 - Arquitetura de Capacidade para Multi-Escola

## Estado do documento
- Tipo: arquitetura operacional para producao.
- Escopo: gestao de RAM, concorrencia, filas, quotas e rollout multi-tenant.
- Objetivo: permitir uso real por varias escolas sem degradacao critica de servico.

## 1. Problema operacional
Cada geracao pode consumir memoria elevada. Sem controlo de concorrencia, multiplas geracoes simultaneas causam:
1. saturacao de RAM;
2. latencia extrema;
3. risco de kill de processos;
4. indisponibilidade para outros tenants.

## 2. Principio de capacidade
Nao escalar por "numero de cliques". Escalar por "numero de geracoes pesadas em paralelo".

## 3. Componentes obrigatorios da arquitetura

## 3.1 Queue dedicada de solver
- Separar tasks pesadas de geracao em fila propria.
- Evitar competicao com tarefas leves de API/operacao.

## 3.2 Worker pool dedicado
- Workers exclusivos para geracao.
- Concorrencia baixa por processo para previsibilidade de RAM.

## 3.3 Lock por organizacao
- Uma org nao executa 2 geracoes ao mesmo tempo.
- Evita desperdicio e corrida de resultados dentro do mesmo tenant.

## 3.4 Semaforo global de tokens
- Cada geracao precisa de token global para iniciar.
- Sem token disponivel, task fica em fila com ETA.
- Tokens dimensionados por capacidade real de memoria.

## 3.5 Quotas por tenant/plano
- Limite diario/mensal de geracoes por organizacao.
- Protege plataforma de abuso e ajuda previsao de custo.

## 3.6 Preflight de custo
Antes de enfileirar:
1. estimar tamanho do problema;
2. estimar RAM e runtime;
3. classificar tarefa em classe de custo.

## 4. Politica de execucao recomendada

## 4.1 Trigger de geracao
- Manual por admin (nao automatico nesta fase).

## 4.2 Ordem de priorizacao de fila
1. prioridade por impacto operacional (proximidade hard end + divida vencida);
2. fairness entre tenants (evitar starvation);
3. FIFO dentro do mesmo nivel.

## 4.3 Timeout de seguranca
- Manter timeout de infraestrutura para evitar job zombie.
- Nao usar timeout curto como substituto de modelagem/otimizacao.

## 5. Perfis de capacidade (base inicial)

## 5.1 Ambiente pequeno
- tokens globais: 1 a 2
- worker concurrency por processo: 1
- foco: estabilidade minima e custo baixo.

## 5.2 Ambiente medio
- tokens globais: 3 a 6
- pool de workers dedicado por fila solver.
- foco: suportar multiplas escolas com SLA interno controlado.

## 5.3 Ambiente alto volume
- tokens globais dinamicos por telemetria de RAM.
- autoscaling de workers solver.
- particionamento por fila/tenant class (enterprise vs standard).

## 6. Dimensionamento por memoria
Formula operacional de referencia:
- `max_parallel_jobs = floor((RAM_disponivel_para_solver * safety_factor) / RAM_p95_por_job)`

Sugestao inicial:
- `safety_factor` entre 0.65 e 0.75 para absorver picos.

Exemplo ilustrativo:
- RAM disponivel solver: 32 GB
- RAM p95 por job: 2.5 GB
- safety factor: 0.7
- paralelo maximo aproximado: `floor((32 * 0.7) / 2.5) = 8`

## 7. SLA interno e experiencia do utilizador

## 7.1 O que mostrar ao admin
1. posicao na fila;
2. ETA estimado;
3. estado (queued/running/success/error/canceled);
4. resumo de custo estimado (leve/medio/pesado).

## 7.2 Objetivo de produto
Priorizar conclusao mais cedo das aulas (respeitando hard constraints), mantendo transparencia de fila e previsibilidade operacional.

## 8. Alertas obrigatorios de capacidade
1. `queue_wait_p95` acima do limiar.
2. `ram_peak_mb` acima do orcamento por job.
3. taxa de falha por OOM.
4. taxa de timeout acima do limiar.
5. saturacao persistente de tokens.

## 9. Seguranca e isolamento
1. Lock e quotas sempre tenant-scoped.
2. Semaforo global nao pode quebrar isolamento de dados.
3. Logs de capacidade com org_id e request_id para auditoria.

## 10. Rollout recomendado
1. piloto com poucos tenants e tokens conservadores.
2. ajuste por telemetria real de RAM/runtime.
3. aumento progressivo de tokens sem perder margem de seguranca.
4. revisao mensal de quotas por adocao real.

## 11. Integracao com Solver V2
Este documento operacional suporta a especificacao do algoritmo em:
- `documentation/03_scheduler_engine/SOLVER_V2_ADAPTATIVO_ALGORITMO_E_COMPORTAMENTO.md`

A implementacao tecnica faseada do V2 esta em:
- `documentation/03_scheduler_engine/WBS_SOLVER_V2_ADAPTATIVO_IMPLEMENTACAO_2026-04-20.md`

## 12. Itens a definir
1. limiares finais de quota por plano comercial (a definir);
2. SLA externo contratual por tier (a definir);
3. estrategia final de autoscaling por cloud alvo (a definir).