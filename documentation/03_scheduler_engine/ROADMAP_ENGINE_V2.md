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
2. Validacao de zero violacoes hard em cada entrega.
3. Comparacao de metricas soft entre versoes quando aplicavel.
4. Comunicacao transparente de limitacoes quando hard end date impossibilitar conclusao total.

## Pontos ainda a definir (nao fechados)
- estrategia detalhada de rollback por tipo de incidente;
- limiares numericos para promocao automatica entre ambientes.