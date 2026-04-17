# Metrics and alerts

## Objetivo
Definir observabilidade minima para operar o sistema com confianca em ambiente real.

## Definicao de "alarme" neste projeto

Alarme e um sinal tecnico interno da plataforma para detetar comportamentos de risco.
Nao e, por defeito, uma notificacao enviada a todos os utilizadores finais.

## 5 Ws da observabilidade

### What
Metricas e alarmes internos da geracao, operacao diaria e consistencia multi-tenant.

### Who
Recebedores e consumidores de informacao:
- operacao/suporte da plataforma: recebe alarmes tecnicos agregados dos tenants;
- admin da escola cliente: recebe feedback funcional contextual dentro da app (ex.: bloqueio por conflito hard);
- professor: nao recebe alarmes tecnicos globais da plataforma.

### Where
Ambiente de execucao da plataforma e processos de suporte tecnico.

### When
Durante geracao, replaneamento e tratamento de ocorrencias operacionais.

### Why
Sem sinais objetivos, incidentes demoram a ser detetados e resolvidos.

## Porque isto faz sentido em modelo self-service

1. No modelo self-service, a escola usa a plataforma sem acompanhamento privado continuo.
2. Alarmes tecnicos existem para detetar problemas cedo e reduzir friccao para o cliente.
3. Isto nao implica servico dedicado por escola, apenas operacao responsavel da plataforma.

## SLA no contexto atual do produto

- Nesta fase, SLA deve ser entendido como compromisso interno de confiabilidade e suporte.
- Nao existe acompanhamento privado contratado por cliente como requisito do produto.
- O objetivo pratico e manter experiencia previsivel para qualquer escola que subscreva autonomamente.

## Tipos de alarme interno (plataforma)

1. Violacao hard na tentativa de geracao/publicacao.
2. Possivel risco de isolamento entre tenants.
3. Falhas repetidas em operacoes criticas (geracao, ocorrencias, persistencia).
4. Comportamento anomalo de jobs/servicos de fundo necessarios para operacao.

Cada alarme e para acao tecnica interna, nao para broadcast a todos os utilizadores.

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

Implementacao atual (2026-04-12):
- trilho operacional persistido em tabela dedicada por tenant (`occurrence_operational_event`);
- evento inclui actor, occurrence_id/schedule_output_id, tipo de evento e resultado;
- contadores basicos disponiveis por API em `GET /api/v1/occurrences/observability/summary`.

### Grupo C - Isolamento e seguranca
- tentativas bloqueadas por autorizacao;
- tentativas bloqueadas por tenant mismatch;
- erros de validacao de input em endpoints criticos.

### Grupo D - Endpoints criticos do professor (Passo 9)
- volume por endpoint critico self-service;
- taxa de 403 por endpoint (anomalias de permissao/uso);
- taxa de 5xx por endpoint critico;
- latencia p95 (ms) em:
	- `GET /teachers/me/availability`;
	- `POST /teachers/{teacher_id}/availability`;
	- `GET /schedule/me/horizon`;
	- `GET /schedule/week` (escopo professor).

Implementacao atual (2026-04-17):
- eventos por endpoint persistidos em `teacher_endpoint_operational_event` com contexto tenant;
- agregacao operacional disponivel em `GET /api/v1/teachers/observability/summary` (admin-only);
- resumo inclui contadores por status e latencia p95 por endpoint, com lista de alertas ativos.

## Alertas minimos

Disparar alarme interno quando ocorrer:
- qualquer violacao hard;
- indicio de vazamento entre tenants;
- falha repetida em operacoes criticas de geracao/ocorrencia.
- 403 anormal em endpoint critico do professor;
- 5xx acima de threshold em endpoint critico do professor.

## Exemplo pratico

Cenario:
- escola cliente em modo self-service tenta gerar horario e recebe bloqueio por conflito hard.

Comportamento esperado:
- a plataforma impede publicacao invalida;
- alarme interno e emitido para operacao/suporte da plataforma;
- cliente recebe mensagem clara e pode agir (corrigir dados e regenerar);
- se houver comportamento anomalo de sistema, suporte consegue atuar rapidamente sem acompanhamento privado continuo.

## Decisao fechada para Alpha V1 (sem pendencias)

### Limiares numericos de alarme (alpha/piloto)
- qualquer violacao hard detectada: alarme imediato (threshold = 1 evento).
- qualquer indicio de tenant mismatch: alarme imediato (threshold = 1 evento).
- falhas em operacoes criticas (geracao/ocorrencia/persistencia): alarme quando >= 3 falhas em 15 minutos.
- falha de job critico em background: alarme quando >= 2 falhas consecutivas.
- erro HTTP 5xx em endpoint critico: alarme quando taxa > 2% por janela de 15 minutos.
- 403 anormal em endpoint critico do professor: alarme quando `count >= 10` e taxa >= 20% na janela de 15 minutos.

### Runbook minimo por tipo de incidente
1. Classificar incidente (hard, tenant, operacional, performance).
2. Conter impacto (bloquear acao invalida ou pausar fluxo afetado).
3. Diagnosticar causa raiz com contexto tenant e timestamp.
4. Corrigir e validar com teste focado/regressao.
5. Registar incidente e decisao final para auditoria interna.

## Impacto por layer

### Interface
- mensagens e estados devem refletir se operacao foi validada ou bloqueada.

### Regras de negocio
- metricas devem refletir diretamente hard constraints e ocorrencias.

### Base de dados
- logs e eventos precisam de contexto tenant para auditoria e diagnostico.