# Roadmap Engine v2

## Objetivo
Evoluir o motor sem comprometer a operacao ja estavel da fase atual.

## 5 Ws do roadmap

### What
Plano de evolucao do motor para consolidar confiabilidade e suportar operacao diaria com faltas/substituicoes.

### Who
Equipa tecnica com validacao funcional de operacao administrativa (admin).

### Where
Escopo por organizacao, mantendo isolamento multi-tenant.

### When
Roadmap por fases iterativas, com validacao a cada marco.

### Why
Evitar regressao de regras hard enquanto novas capacidades operacionais entram em producao.

## Fases confirmadas

### Fase 1 - Consolidacao da baseline
- manter hard constraints estaveis;
- manter bloqueio absoluto por hard end date;
- consolidar repair mode conservador com janela fixa configuravel por escola;
- melhorar transparencia de resultados quando ha carga remanescente.

### Fase 2 - Operacao de faltas e substituicoes
- consolidar separacao planeado vs executado;
- garantir historico imutavel de ocorrencias;
- aplicar checks de elegibilidade de substituicao.

### Fase 3 - Qualidade operacional continua
- reforcar metricas de validacao hard;
- evoluir criterios soft sem violar viabilidade;
- manter estabilidade em cenarios de regeneracao.

## Backlog tecnico por prioridade

### Prioridade maxima
- qualquer risco de violacao hard;
- qualquer risco de quebra de tenant isolation;
- qualquer risco de mutacao indevida do historico executado.

### Prioridade alta
- lacunas em rastreabilidade de ocorrencias;
- inconsistencias no fluxo operacional de substituicao.

### Prioridade continua
- melhorias de qualidade soft (fairness, furos, drift) com medicao comparavel.

## Validacao e seguranca de evolucao

1. Testes focados por organizacao.
2. Testes de repair mode com janela fixa configurada em 2 semanas.
3. Validacao de zero violacoes hard em cada entrega.
4. Comparacao de metricas soft entre versoes quando aplicavel.
5. Comunicacao transparente de limitacoes quando hard end date impossibilitar conclusao total.

## Decisao fechada para Alpha V1 (sem pendencias)

### Estrategia de rollback por tipo de incidente
1. Violacao hard ou risco de tenant isolation:
- rollback imediato para a ultima versao estavel;
- congelar operacoes de escrita do fluxo afetado ate correcao validada.

2. Falha operacional em faltas/substituicoes sem violacao hard:
- rollback do pacote funcional afetado na release seguinte;
- manter operacao restante disponivel com comunicacao transparente.

3. Degradacao apenas de objetivos soft:
- sem rollback imediato;
- abrir correcao priorizada e comparar metricas antes/depois.

### Limiares numericos para promocao entre ambientes
- zero violacoes hard na suite de regressao;
- zero falhas de tenant isolation na suite multi-tenant;
- 100% de passagem na suite critica da Alpha V1 (unitarios + integracao + regressao hard);
- zero incidente P0/P1 aberto no fluxo de ocorrencias/substituicoes no momento da promocao.