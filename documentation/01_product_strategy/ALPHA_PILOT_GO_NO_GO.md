# Alpha Pilot Go No Go

## Objetivo
Definir o gate final de prontidao tecnica e funcional para iniciar o piloto com 1 organizacao real em escala real.

## 5 Ws

### What
Checklist go/no-go com tres blocos obrigatorios:
- readiness tecnica e funcional;
- plano de suporte reativo durante piloto;
- plano de recolha de feedback funcional do admin.

### Who
- decisao go/no-go: equipa interna de produto + engenharia;
- operacao diaria no piloto: admin da escola piloto;
- suporte tecnico: operacao/suporte da plataforma.

### Where
Escopo do piloto:
- 1 organizacao real (escola piloto), sem limite artificial de turmas/disciplina.

### When
Aplicado no fecho da Alpha V1 e revisto semanalmente durante o piloto.

### Why
Garantir previsibilidade operacional no arranque e reduzir risco de bloqueio funcional critico.

## Checklist de readiness tecnica e funcional (obrigatoria)

### A. Qualidade tecnica
1. Suite minima de regressao alpha aprovada.
2. Regressao backend completa aprovada.
3. Sem issue P0/P1 aberta em fluxos criticos.

### B. Regras de negocio criticas
1. Maquina de estados de ocorrencias valida e auditavel.
2. Ranking de recomendacao deterministico com decisao final humana.
3. Reparacao adaptativa respeita a janela de estabilidade e a data-limite rigida.
4. Tenant isolation validado em leitura e escrita.

### C. Operacao funcional
1. Fluxo admin de ocorrencias funciona end-to-end.
2. Feedback de erro operacional e claro para decisoes diarias.
3. Professor permanece sem privilegios de administracao global.

## Plano de suporte reativo (piloto)

### Triagem diaria
- Janela de triagem: diaria em dias letivos.
- Priorizacao por impacto:
  - P0: bloqueio total de operacao critica;
  - P1: degradacao relevante com workaround limitado;
  - P2/P3: sem bloqueio critico.

### SLA interno de resposta (fase alpha)
- P0: acao inicial imediata.
- P1: acao inicial no mesmo periodo operacional.
- P2/P3: tratamento por backlog priorizado.

### Escalacao tecnica
1. Confirmar tenant afetado e timestamp.
2. Classificar incidente (hard, tenant, operacional, performance).
3. Aplicar contencao segura.
4. Validar correcao com teste focado/regressao.
5. Registar incidente para auditoria interna.

## Plano de recolha de feedback funcional (admin da escola)

### Cadencia
- recolha semanal estruturada durante piloto;
- canal unico para evitar dispersao de contexto.

### Template minimo de recolha
1. Fluxo afetado (geracao, ocorrencias, substituicoes, configuracao).
2. Objetivo operacional pretendido.
3. Resultado observado.
4. Impacto real no dia a dia (baixo/medio/alto/critico).
5. Exemplo concreto (data, turma, slot).

### Critero de classificacao
- Feedback critico: risco de bloqueio funcional.
- Feedback relevante: friccao operacional sem bloqueio.
- Feedback evolutivo: melhoria de UX/performance sem risco imediato.

## Testes obrigatorios de prontidao (Passo 7.2)

1. Semana operacional simulada com estados GIVEN, GAP e SUBSTITUTED.
2. Teste de carga moderada em horario critico.
3. Validacao final de trilho de auditoria (quem decidiu, quando decidiu, estado final).

## Edge cases obrigatorios no gate

1. Escola com disponibilidade muito restritiva.
2. Semana com faltas acima do normal.
3. Alteracoes operacionais em cima da hora.

## Criterio final de decisao

Go:
- todos os checkpoints obrigatorios aprovados;
- sem bloqueio funcional critico aberto;
- suporte reativo e observabilidade ativos.

No-Go:
- qualquer falha em hard constraints, tenant isolation ou gate de regressao critica.

## Confirmacao dos 4 pilares

- Otimizacao: priorizacao por impacto e feedback estruturado reduzem ciclos de correcao.
- Estabilidade: gate tecnico + triagem diaria evita regressao em operacao real.
- Escalabilidade: piloto em escala real valida comportamento sem limite artificial.
- Seguranca: decisao go/no-go bloqueia arranque com risco de tenant ou autorizacao.
