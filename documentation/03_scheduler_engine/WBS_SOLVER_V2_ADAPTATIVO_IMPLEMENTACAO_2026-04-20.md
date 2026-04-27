# WBS Tecnica - Solver V2 Adaptativo (2026-04-20)

## Estado do documento
- Tipo: plano tecnico de implementacao.
- Escopo: backend solver e pipeline de geracao para validacao local em Docker (single-user).
- Objetivo: implementacao incremental do Solver V2 sem quebra do contrato hard da plataforma.

## 1. Objetivo
Implementar um solver adaptativo por data real que maximize conclusao antecipada das aulas no Ensino Profissional, preservando:
1. hard constraints;
2. isolamento por tenant;
3. historico imutavel de execucao;
4. operacao local robusta (gerar, comparar diff, aprovar/rejeitar draft, persistir com seguranca).

## 2. 5 Ws da implementacao

### What
Implementacao do Solver V2 por datas absolutas, com prioridade maxima para reduzir data final de conclusao e tratar backlog unico de horas por alocar.

### Who
- admin: continua dono da decisao operacional (geracao manual e aprovacao de draft);
- plataforma: executa otimizacao e controlo de capacidade;
- equipa tecnica: garante hard constraints, seguranca e escalabilidade.

### Where
- backend Python/FastAPI/CP-SAT;
- base de dados PostgreSQL tenant-scoped em ambiente Docker local.

### When
Implementacao faseada em ondas, com gate tecnico por fase e rollout progressivo por tenant.

### Why
O modelo atual (padrao semanal + expansao) nao aproveita de forma total espacos que surgem mais tarde no mesmo ciclo. O V2 deve capturar esse dinamismo para terminar aulas mais cedo.

## 3. Decisoes fechadas para esta WBS
1. Perfil operacional alvo: agressivo 100% para terminar aulas o mais cedo possivel.
2. Estabilidade e secundaria face ao objetivo de conclusao antecipada.
3. Geracao permanece manual (sem auto-trigger de repair em producao nesta fase).
4. Backlog unico de horas por alocar (sem diferenciar divida normal e divida vencida).
5. Objetivo do solver sera lexicografico por prioridade.
6. Horizonte hibrido: janela rolling principal de 8 semanas + validacao de viabilidade ate hard_end_date.
7. Com draft pendente, nova geracao fica bloqueada ate aprovar/rejeitar.

## 4. Nao objetivos desta iteracao
1. Nao remover janela congelada de repair.
2. Nao permitir mudanca de historico executado.
3. Nao violar hard constraints para ganhar velocidade de conclusao.
4. Nao definir quotas/SLA/autoscaling de ambiente multi-cliente nesta fase local.

## 5. Arquitetura alvo (resumo)
1. Solver por datas reais com horizonte hibrido (rolling de 8 semanas + validacao ate hard end).
2. Pipeline em 2 estagios: solve principal + fill-opportunistic.
3. Backlog unico de horas por alocar, sem reserva fixa para divida.
4. Persistencia transacional em draft + aprovacao/rejeicao manual.
5. Rejeicao apaga draft sem sequelas; nova geracao bloqueada enquanto existir draft pendente.

## 6. WBS detalhada

## Fase 0 - Baseline tecnico local

### WP-0.1 Baseline tecnico atual
- Medir RAM p50/p95 por geracao (full e repair) por perfil de seed.
- Medir duracao p50/p95 por geracao.
- Capturar tamanho medio de problema (lessons, slots reais, candidatos).

Criterio de aceite:
- baseline reproduzivel com relatorio por tenant.

### WP-0.2 Baseline operacional
- Definir metricas minimas locais: solver_runtime_seconds, projected_end_delta_days, success_rate.
- Registar baseline por seed para comparacao entre versoes.

Criterio de aceite:
- baseline local reproduzivel para validacao funcional.

## Fase 1 - Modelo de dados e dominio para solver por data real

### WP-1.1 Entidade de demanda adaptativa
- Introduzir estrutura interna de tarefa operacional por class+subject+module ativo.
- Consolidar backlog unico de minutos por alocar (sem classes de divida).

Criterio de aceite:
- tarefa adaptativa reproduzivel por tenant com totalizadores auditaveis.

### WP-1.2 Estado de modulo e cadeia
- Garantir ativacao de modulo seguinte apenas apos fecho valido do modulo atual.
- Manter ordem obrigatoria de modulos sem atalhos.

Criterio de aceite:
- testes de cadeia de modulo sem regressao de invariantes.

## Fase 2 - Oferta por data real e reducao de espaco de procura

### WP-2.1 Slots absolutos
- Gerar universo de slots por data real em janela rolling principal de 8 semanas.
- Validar viabilidade global ate hard_end_date.
- Excluir datas bloqueadas por calendario.

Criterio de aceite:
- 100% dos slots fora de hard end date.

### WP-2.2 Filtro de candidatos hard-first
- Eliminar candidatos inviaveis por conflito, disponibilidade e tipo de sala antes do solve.
- Reduzir custo de memoria e tempo por pruning.

Criterio de aceite:
- reducao observavel de candidatos sem perda de viabilidade.

## Fase 3 - Solver V2 core (CP-SAT)

### WP-3.1 Variaveis por data real
- Criar variavel binaria por tarefa+slot+sala.
- Garantir coerencia com conflitos professor/turma/sala.

Criterio de aceite:
- zero violacoes hard em suite dedicada.

### WP-3.2 Objetivo com prioridade de conclusao antecipada
- Funcao objetivo lexicografica orientada a fim mais cedo como prioridade maxima.
- Backlog tratado como horas normais por alocar; equilibrio entre turmas como prioridade secundaria.

Criterio de aceite:
- melhoria de projected_end_date vs baseline em cenarios de referencia.

### WP-3.3 Modo agressivo 100%
- Definir perfil agressivo que nao limita mudanca fora da janela congelada.
- Guardar rastreabilidade de delta para auditoria operacional.

Criterio de aceite:
- capacidade de alterar universo reparavel completo sem tocar zona congelada.

## Fase 4 - Expansao adaptativa e pos-otimizacao

### WP-4.1 Solve principal por impacto
- Priorizar tarefas com maior impacto em projected end date global.
- Sem reserva fixa de capacidade para backlog.

### WP-4.2 Fill-opportunistic
- Preencher espacos livres restantes com tarefas elegiveis para antecipar fim global.

### WP-4.3 Refinamento local
- Melhorias locais de gaps e fairness sem violar objetivo principal.

Criterio de aceite:
- aumento de utilizacao de slots livres sem regressao hard.

## Fase 5 - Persistencia, diff e aprovacao

### WP-5.1 Persistencia atomica em draft
- Escrever apenas fora da janela congelada.
- Sem persistencia parcial em cancelamento/erro.

### WP-5.2 Diff orientado a operacao
- Expor comparacao estatistica entre draft e plano publicado (sem vista aula-a-aula obrigatoria).
- Incluir no minimo: projected_end_date delta, end_date_spread_days, churn_outside_frozen_ratio, total de blocos alterados fora da janela e backlog_remaining_hours.
- Manter aprovacao manual admin.
- Rejeicao de draft remove permanentemente o draft sem alterar o publicado.

Criterio de aceite:
- painel estatistico legivel para decisao operacional antes de publicar.

## Fase 6 - Infraestrutura multi-tenant (postergada pre-1.0)
- Esta fase fica fora do escopo do MVP local em Docker.
- Quotas, autoscaling, SLA e controlo de concorrencia multi-cliente serao tratados na preparacao para producao.

## Fase 8 - Testes e hardening

### WP-8.1 Unitarios
- demand builder, candidate pruning, objetivo agressivo, lock org.

### WP-8.2 Integracao
- cenarios com espacos libertados no medio prazo e backlog unico por alocar.

### WP-8.3 Regressao
- suites hard + fluxo draft (aprovar/rejeitar) + seguranca sem regressao.

Criterio de aceite:
- gate sem violacao hard e sem risco de tenant leak.

## Fase 9 - Rollout de producao (postergado pre-1.0)
- Fora do escopo desta iteracao local.

## 7. Criterios globais de aceite
1. Objetivo principal cumprido: melhoria consistente da data de conclusao.
2. Zero violacoes hard.
3. Zero violacoes de tenant isolation.
4. Sem mutacao de historico executado.
5. Fluxo funcional completo: gerar draft, comparar resumo estatistico do diff, aprovar/rejeitar sem efeitos colaterais.

## 8. Riscos e mitigacoes
1. Risco de runtime excessivo.
- Mitigacao: pruning agressivo de candidatos + solve em estagios + janela rolling.

2. Risco de churn operacional alto fora da janela.
- Mitigacao: diff explicito + aprovacao manual obrigatoria.

3. Risco de regressao de dominio modular.
- Mitigacao: testes de cadeia de modulos e invariantes por tenant.

## 9. Dependencias
1. Scheduler engine (core) e solver_tasks.
2. Servicos de schedule/occurrence/progress.
3. Persistencia de draft e fluxo de aprovacao/rejeicao.

## 10. Itens a definir
Sem itens pendentes no escopo local de implementacao do Solver V2.