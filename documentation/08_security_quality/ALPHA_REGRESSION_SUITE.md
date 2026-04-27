# Alpha Regression Suite

## Objetivo
Consolidar a suite minima de regressao da Alpha V1 para gate tecnico antes de go/no-go.

## 5 Ws

### What
Bateria de regressao focada em:
- geracao base e repair mode;
- ocorrencias e substituicoes;
- autorizacao por role e tenant isolation;
- edge cases operacionais criticos definidos no WBS.

### Who
Consumidores principais:
- equipa tecnica (desenvolvimento/QA);
- operacao/suporte interno da plataforma.

### Where
Execucao em ambiente local e CI, com BD de teste isolada por run.

Regra operacional de isolamento:
- a suite usa base de dados de teste dedicada (por defeito, sufixo `_test` a partir de `DATABASE_URL`);
- opcionalmente, pode ser definida via `TEST_DATABASE_URL`;
- configuracoes que apontem testes para a BD principal sao bloqueadas para evitar perda de dados de desenvolvimento.

### When
Obrigatorio antes de decisao go/no-go da escola piloto e apos alteracoes nos fluxos criticos.

### Why
Sem gate consolidado, regressao funcional em operacao diaria pode chegar ao piloto com risco elevado.

## Escopo minimo (Passo 7.1)

### Regressao funcional de geracao base
- validar trigger de geracao full em contexto minimo valido;
- validar repair mode com horizonte permitido;
- validar bloqueio de repair quando hard end date nao deixa horizonte fora da janela.

### Regressao de ocorrencias e substituicoes
- validar recomendacao com multiplos elegiveis;
- validar confirmacao SUBSTITUTED com trilho de decisao;
- validar fallback operacional em ausencia de elegiveis.

### Regressao de autorizacao e tenant isolation
- professor bloqueado em acoes operacionais de ocorrencias;
- admin de tenant B nao acede ocorrencias/recomendacoes do tenant A;
- queries e mutacoes mantem organization_id como fronteira obrigatoria.

## Edge cases obrigatorios (WBS)

1. Combinacao repair + falta + substituicao no mesmo periodo.
2. Operacao perto do hard end date.
3. Rollback apos erro inesperado no meio da operacao.

## Implementacao tecnica atual

Suite dedicada:
- backend/tests/test_alpha_release_gate.py

Cobertura da suite:
- gate de geracao (full/repair + bloqueio por hard end);
- gate de operacao diaria (recomendacao, confirmacao, role e tenant);
- simulacao semanal com verificacao de auditoria;
- simulacao de carga moderada em janela critica;
- rollback forcado com verificacao de nao persistencia parcial.

## Comandos de execucao

Execucao focada da suite alpha:
- pytest tests/test_alpha_release_gate.py -q

Execucao regressao backend completa:
- pytest -q

## Criterio de aprovacao do gate

Gate aprovado quando:
1. suite alpha dedicada sem falhas;
2. regressao backend completa sem falhas;
3. sem issue P0/P1 aberta em fluxos criticos (geracao, ocorrencias, substituicoes, tenant isolation).

## Verificacao dos 4 pilares

- Otimizacao: suite focada reduz tempo de detecao de regressao critica.
- Estabilidade: edge cases obrigatorios ficam cobertos de forma automatica.
- Escalabilidade: inclui simulacao de carga moderada no fluxo operacional.
- Seguranca: reforca role enforcement e tenant isolation no gate.
