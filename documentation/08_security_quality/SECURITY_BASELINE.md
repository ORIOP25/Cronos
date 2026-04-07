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

## Pontos ainda a definir (nao fechados)
- matriz formal de risco por severidade de negocio;
- evidencias de conformidade exigidas por ciclo de release.

## Impacto por layer

### Interface
- bloqueio de acoes nao autorizadas e mensagens de erro controladas.

### Regras de negocio
- enforcement de tenant isolation e invariantes operacionais.

### Base de dados
- persistencia segura, transacional e auditavel.