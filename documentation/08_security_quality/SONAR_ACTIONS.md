# Sonar actions

## Objetivo
Transformar findings de qualidade e seguranca em acoes executaveis e auditaveis.

## 5 Ws do processo Sonar

### What
Processo de triagem, priorizacao, execucao e fecho de achados Sonar.

### Who
Equipa tecnica responsavel por backend, frontend e base de dados.

### Where
Aplicado no repositorio e no ciclo de entrega tecnica.

### When
Sempre que houver nova analise ou alteracoes relevantes no codigo.

### Why
Sem processo claro, findings acumulam e aumentam risco tecnico e operacional.

## Fluxo minimo obrigatorio

1. Capturar finding com contexto tecnico.
2. Classificar impacto (seguranca, confiabilidade, manutencao).
3. Definir dono tecnico.
4. Corrigir e validar.
5. Fechar com evidencia objetiva (teste, diff, analise limpa).

## Priorizacao base

- Alto impacto de seguranca ou tenant isolation: prioridade maxima.
- Violacao de regra hard do dominio: prioridade maxima.
- Qualidade estrutural sem impacto imediato: backlog priorizado.

## Criterio de fecho

Um item so fecha quando:
- a causa raiz foi tratada;
- nao ha regressao visivel no comportamento esperado;
- evidencia de verificacao foi registada.

## Exemplo pratico

Finding:
risco de acesso sem filtro tenant num endpoint.

Acao:
- corrigir query para organization_id;
- validar com teste de nao vazamento entre orgs;
- anexar evidencias e fechar item.

## Pontos ainda a definir (nao fechados)
- SLA numerico por severidade para resolucao;
- formato unico de report de fecho para toda equipa.