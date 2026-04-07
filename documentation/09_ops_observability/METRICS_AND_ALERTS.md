# Metrics and alerts

## Objetivo
Definir observabilidade minima para operar o sistema com confianca em ambiente real.

## 5 Ws da observabilidade

### What
Metricas e alertas da geracao, operacao diaria e consistencia multi-tenant.

### Who
Equipas de operacao e desenvolvimento que suportam o produto.

### Where
Ambiente de execucao da plataforma e processos de suporte tecnico.

### When
Durante geracao, replaneamento e tratamento de ocorrencias operacionais.

### Why
Sem sinais objetivos, incidentes demoram a ser detetados e resolvidos.

## KPI minimos obrigatorios

### Grupo A - Viabilidade hard
- numero de conflitos de professor no resultado;
- numero de conflitos de turma no resultado;
- numero de conflitos de sala no resultado;
- numero de aulas apos hard end date.

Expectativa funcional:
- todos os indicadores hard devem estar em zero para resultado valido.

### Grupo B - Integridade operacional
- numero de ocorrencias registadas por estado (GAP, GIVEN, SUBSTITUTED);
- diferenca entre planeado e executado por periodo;
- eventos de falha em validacao de substituicao.

### Grupo C - Isolamento e seguranca
- tentativas bloqueadas por autorizacao;
- tentativas bloqueadas por tenant mismatch;
- erros de validacao de input em endpoints criticos.

## Alertas minimos

Disparar alerta quando ocorrer:
- qualquer violacao hard;
- indicio de vazamento entre tenants;
- falha repetida em operacoes criticas de geracao/ocorrencia.

## Exemplo pratico

Cenario:
- uma geracao retorna conflito de sala.

Comportamento esperado:
- alerta tecnico e gerado;
- resultado nao e promovido como horario valido;
- equipa identifica causa e repete geracao apos correcao.

## Pontos ainda a definir (nao fechados)
- limiares numericos de alerta por ambiente;
- runbook detalhado por tipo de incidente.

## Impacto por layer

### Interface
- mensagens e estados devem refletir se operacao foi validada ou bloqueada.

### Regras de negocio
- metricas devem refletir diretamente hard constraints e ocorrencias.

### Base de dados
- logs e eventos precisam de contexto tenant para auditoria e diagnostico.