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
## Database Tenant Isolation

Tenant-owned database access must use direct `organization_id` ownership plus
PostgreSQL RLS. The canonical session setting is
`app.current_organization_id`, set transaction-locally with
`set_config(..., true)`. Missing, empty, malformed, zero, negative, or
out-of-range tenant settings fail closed through
`app_security.current_organization_id()`.

Every tenant-owned table must either be `organization` itself or carry a
non-null `organization_id`. Link and derived tables are not allowed to infer
tenant ownership only through parent rows. Same-tenant references are enforced
by database validation triggers in the RLS migration, with app-level tenant
filters kept as defense in depth.

Authenticated API dependencies must reject users without an organization before
tenant data access and set the tenant context before normal ORM reads/writes.
Worker jobs must do the same with the sync tenant helper before calling
tenant-scoped services. Public endpoints must not set tenant context and must
not query tenant-owned data.
