# Security baseline

## Objetivo
Definir controlos minimos obrigatorios de seguranca e integridade operacional.

## 5 Ws da baseline

### What
Conjunto de regras que protegem dados, autorizacao e consistencia funcional.

### Who
Aplicavel a qualquer alteracao de backend, frontend e base de dados.

### Where
Em todas as operacoes do sistema, com foco critico em multi-tenant.

### When
Desde design ate deploy e operacao continua.

### Why
SaaS para escolas exige confiabilidade, isolamento de dados e rastreabilidade de decisoes.

## Controlos obrigatorios

1. Tenant isolation obrigatorio por organization_id.
2. Autorizacao por role obrigatoria (admin vs professor).
3. Professor sem privilegios de administracao da organizacao.
4. Validacao de input e contratos de API tipados.
5. Operacoes criticas em transacao atomica.
6. Sem bare except.
7. Historico de execucao e ocorrencias tratado como imutavel.

## Checklist pratico de revisao

- A query e filtrada por organization_id?
- A mutacao impede acesso cruzado entre tenants?
- O endpoint respeita o role autenticado?
- Erros sao explicitos sem exposicao de dados sensiveis?
- A alteracao preserva historico em vez de o reescrever?

## Exemplo pratico

Caso:
professor autenticado tenta executar acao administrativa.

Comportamento esperado:
- autorizacao negada;
- nenhum efeito colateral em dados;
- log/erro suficiente para auditoria tecnica.

## Decisao fechada para Alpha V1 (sem pendencias)

### Matriz formal de risco por severidade de negocio
- P0 Critico: violacao hard, risco de tenant isolation, acesso indevido a dados.
- P1 Alto: quebra de autorizacao por role, falha transacional com impacto operacional relevante.
- P2 Medio: inconsistencias sem violacao hard e com workaround operacional.
- P3 Baixo: melhoria de robustez/manutencao sem impacto funcional imediato.

### Evidencias minimas de conformidade por ciclo de release
- P0/P1: teste de regressao focado + evidencias de fix + revisao tecnica obrigatoria.
- P2: teste funcional do fluxo impactado + registo da validacao.
- P3: validacao local/documentada + backlog priorizado.

Gate de release:
- nenhuma issue P0/P1 aberta para fluxos criticos (geracao, ocorrencias, substituicoes, tenant isolation).

## Impacto por layer

### Interface
- bloqueio de acoes nao autorizadas e mensagens de erro controladas.

### Regras de negocio
- enforcement de tenant isolation e invariantes operacionais.

### Base de dados
- persistencia segura, transacional e auditavel.