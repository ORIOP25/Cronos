# Endpoint standards

## Objetivo
Padronizar contratos da API para manter previsibilidade funcional e seguranca operacional.

## 5 Ws da camada API

### What
API HTTP da plataforma para operacao de horarios, disponibilidade e eventos operacionais.

### Who
Perfis suportados:
- admin: acesso total no tenant;
- professor: apenas disponibilidade e consulta do proprio horario.

### Where
Sempre no contexto da organizacao autenticada.
Qualquer endpoint deve respeitar organization_id.

### When
Aplicado em todo novo endpoint e em revisao de endpoints existentes.

### Why
Reduzir ambiguidade de contrato e evitar comportamentos inconsistentes entre frontend e backend.

## Regras obrigatorias de contrato

1. Dependencias FastAPI via Annotated.
2. Requests e responses tipados com Pydantic v2.
3. Status code explicito para sucesso e erro esperado.
4. Sem bare except.
5. Operacoes criticas dentro de transacao atomica.

## Regras de autorizacao

### admin
- pode executar operacoes de administracao da organizacao, geracao e aprovacao.

### professor
- pode apenas:
	- consultar a propria disponibilidade via endpoint self-service;
	- registar/atualizar a propria disponibilidade;
	- consultar o proprio horario.

Qualquer operacao fora deste escopo deve ser negada para professor.

## Contrato professor - disponibilidade self-service (Alpha V1 - Ponto 3)

### Endpoint de leitura da propria disponibilidade
- rota: `GET /api/v1/teachers/me/availability`;
- role: professor;
- objetivo: hidratar frontend com disponibilidade persistida do utilizador autenticado.

Resposta esperada (`200`):
- lista de objetos `{ timeslot_id, score }`;
- sempre tenant-scoped (organization_id do `current_user`).

Semantica de erro:
- `400`: utilizador autenticado inativo (conta desativada);
- `403`: utilizador sem role professor ou sem `teacher_id` associado;
- `404`: professor associado nao encontrado no tenant autenticado.

Regras de seguranca obrigatorias:
1. leitura sempre baseada no `current_user` (sem aceitar `teacher_id` externo na rota);
2. join/validacao de timeslot deve manter escopo da organizacao autenticada;
3. role admin nao reutiliza este endpoint para leitura transversal.

## Contrato professor - horizonte semanal self-service (Alpha V1 - Ponto 4)

### Endpoint de metadados para Meus Horarios
- rota: `GET /api/v1/schedule/me/horizon`;
- role: professor;
- objetivo: devolver metadados minimos para navegacao semanal segura em `Meus Horarios`.

Resposta esperada (`200`):
- objeto com:
	- `min_week_start` (date, limite inferior de navegacao semanal permitido para o professor);
	- `week_start_recommended` (date, segunda-feira recomendada para arranque da vista);
	- `hard_end_date` (date, limite absoluto de navegacao semanal);
	- `active_generation_id` (string|null, geracao ativa publicada para contexto operacional).

Semantica de erro:
- `400`: utilizador autenticado inativo (conta desativada);
- `403`: utilizador sem role professor ou sem `teacher_id` associado;
- `404`: tenant sem configuracao de horizonte semanal valida (sem org settings com hard end resolvivel).
- `429`: limite temporario de protecao do endpoint excedido.

Regras de seguranca obrigatorias:
1. endpoint nao aceita `teacher_id` por query/path; escopo sempre por `current_user`.
2. leitura de configuracoes e geracao ativa deve manter filtro por `organization_id` autenticado.
3. role admin deve ser explicitamente negada para este endpoint self-service.

Regras de estabilidade:
1. `min_week_start` define limite inferior de navegacao semanal do professor (normalizado para segunda-feira).
2. `week_start_recommended` deve estar sempre dentro de `[school_start_date, hard_end_date]` (normalizado para segunda-feira).
3. ausencia de geracao ativa nao deve quebrar contrato: `active_generation_id = null`.
4. endpoint tem limite dedicado de `300/hour` para suportar polling de 30s sem colidir com o limite global de `50/hour`.

## Contrato operacional de monitorizacao professor (Alpha V1 - Ponto 9)

### Objetivo
- medir taxa de erro e latencia tecnica dos endpoints criticos da experiencia professor;
- expor alertas operacionais para 403/5xx anormais por rota critica;
- manter isolamento por tenant em toda agregacao.

### Persistencia de observabilidade
- tabela: `teacher_endpoint_operational_event`;
- escopo: tenant-scoped por `org_id`;
- dados minimos por evento:
	- `endpoint_key`;
	- `http_status`;
	- `latency_ms`;
	- `actor_user_id` + `actor_role`;
	- `active_generation_id` (quando aplicavel, leitura de horizonte);
	- `created_at`.

### Endpoints criticos monitorizados
- `GET /api/v1/teachers/me/availability`;
- `POST /api/v1/teachers/{teacher_id}/availability`;
- `GET /api/v1/schedule/me/horizon`;
- `GET /api/v1/schedule/week` (somente chamadas de role professor).

### Endpoint de resumo para operacao
- rota: `GET /api/v1/teachers/observability/summary`;
- role: admin;
- query: `window_minutes` (5..1440, default=15).

Resposta minima (`200`):
- `window_minutes`;
- `total_events`;
- `endpoints[]` com:
	- `endpoint_key`, `total_requests`, `status_2xx`, `status_403`, `status_5xx`, `error_rate_percent`, `p95_latency_ms`;
- `alerts[]` com:
	- `endpoint_key`, `alert_code`, `severity`, `threshold`, `observed_value`.

### Regras de alerta operacional (calculadas por janela)
1. `ABNORMAL_403_RATE`:
	- dispara quando `status_403 >= 10` e taxa 403 >= 20% no endpoint.
2. `HIGH_5XX_RATE`:
	- dispara quando taxa 5xx > 2% no endpoint.

### Simulacao de falha controlada e recuperacao
- validacao automatizada cobre:
	- deteccao de burst 403 com alerta ativo;
	- reducao da taxa de erro apos recuperacao com supressao do alerta;
	- deteccao de 5xx acima de threshold por endpoint.

## Estado de alinhamento final por layer (Alpha V1 - Ponto 10)

### What foi validado
- contratos criticos da experiencia professor estao alinhados com menu/rotas da interface e com invariantes de negocio;
- semantica de erro dos endpoints self-service foi consolidada para evitar contradicao documental;
- monitorizacao de endpoints criticos permanece tenant-scoped e admin-only no consumo de resumo.

### Who
- admin: consome resumo operacional de observabilidade e governa rollout;
- professor: usa apenas contratos self-service do proprio contexto;
- equipa tecnica: usa matriz de status fechada para regressao e troubleshooting.

### Where
- endpoints `teachers` e `schedule`;
- persistencia de eventos em `teacher_endpoint_operational_event`;
- consumo frontend nas paginas `MyAvailability` e `MySchedules`.

### When
- valido durante operacao diaria do professor e durante rollout/piloto;
- valido em incidentes de permissao (403) e erro servidor (5xx) por rota critica.

### Why
- reduzir risco de divergencia entre comportamento real e documentacao;
- sustentar triagem operacional com sinais comparaveis por endpoint;
- preservar previsibilidade de autorizacao e tenant isolation.

### Matriz de semantica de erro validada (passo 10)
1. `GET /api/v1/teachers/me/availability`:
	- `200` sucesso;
	- `400` utilizador inativo;
	- `403` role sem permissao ou teacher sem perfil;
	- `404` professor nao encontrado no tenant autenticado.
2. `POST /api/v1/teachers/{teacher_id}/availability`:
	- `200` sucesso;
	- `400` timeslot invalido/fora da organizacao;
	- `403` professor tenta atualizar outro `teacher_id`;
	- `404` professor alvo nao encontrado no tenant.
3. `GET /api/v1/schedule/me/horizon`:
	- `200` sucesso;
	- `403` role sem permissao ou teacher sem perfil;
	- `404` horizonte semanal nao configurado no tenant;
	- `429` limite temporario de protecao do endpoint excedido.
4. `GET /api/v1/schedule/week` (escopo professor):
	- `200` sucesso no proprio escopo;
	- `403` role fora da matriz permitida (ex.: student);
	- `403` tentativa com `class_id` ou `teacher_id` de outro professor;
	- `429` limite temporario de protecao do endpoint excedido;
	- `422` `week_start` ausente/invalido.
5. `GET /api/v1/teachers/observability/summary`:
	- `200` admin;
	- `403` professor.

### Consistencia de dados e tenant scope
1. Todos os eventos de observabilidade do professor persistem `org_id` para agregacao tenant-scoped.
2. Agregacao operacional por janela usa filtro por `org_id` + `created_at`.
3. Alertas `ABNORMAL_403_RATE` e `HIGH_5XX_RATE` sao calculados por endpoint dentro do tenant.
4. Observabilidade nao substitui fonte de verdade funcional; e apenas mecanismo de sinal tecnico.

## Contrato de seguranca para operacao destrutiva de horario (Addendum 2026-04-17)

### Endpoint de reset operacional
- rota: `DELETE /api/v1/schedule/reset`;
- role: admin-only;
- objetivo: operacao destrutiva controlada para cenarios administrativos validos.

Semantica de resposta:
- `200`: dados operacionais de horario removidos no tenant autenticado;
- `401`: credenciais invalidas/ausentes;
- `403`: role sem permissao para operacao destrutiva.

Regras de seguranca obrigatorias:
1. endpoint usa gate admin-only com default deny para qualquer role nao admin.
2. operacao e sempre tenant-scoped por `organization_id` do utilizador autenticado.
3. tentativas negadas e operacoes aceites ficam com trilho de auditoria tecnico estruturado (metodo, path, actor, status, request_id).

### Item nao bloqueante
- dashboard visual dedicado no frontend para `GET /api/v1/teachers/observability/summary`: **a definir**.

## Modelo de erro (padrao minimo)

Mesmo sem formato final fechado, toda resposta de erro deve deixar claro:
- tipo do erro;
- motivo operacional;
- contexto suficiente para troubleshooting sem expor dados sensiveis.

## Contrato operacional de ocorrencias (Alpha V1 - Passo 1)

Para operacoes de update de ocorrencia:
- `200`: primeira decisao valida aplicada com sucesso;
- `404`: ocorrencia nao encontrada no tenant autenticado;
- `409`: ocorrencia ja fechada (imutavel) ou tentativa de sobrescrita destrutiva;
- `422`: payload invalido (ex.: `SUBSTITUTED` sem `substitute_teacher_id` e `substitute_subject_id`).

Regras de consistencia obrigatorias:
- update deve ser idempotente para retries de rede com payload identico;
- update deve ser transacional: decisao operacional + contabilizacao + auditoria no mesmo commit;
- em erro intermédio, rollback total sem persistencia parcial.
- ocorrencia com `decided_at != null` e fechada e nao aceita mudanca de estado.

### Estado atual de criacao (confirmado em 2026-04-12)

No estado atual, o dominio de ocorrencias exposto na API publica tem:
- `POST /api/v1/occurrences/` (criar/reutilizar por bloco planeado);
- `GET /api/v1/occurrences/` (listar);
- `GET /api/v1/occurrences/{occurrence_id}` (detalhe);
- `PATCH /api/v1/occurrences/{occurrence_id}` (decidir).

Regra de autorizacao operacional (estado atual):
- `GET /api/v1/occurrences/`, `GET /api/v1/occurrences/debts` e `GET /api/v1/occurrences/{occurrence_id}` sao admin-only;
- objetivo: evitar exposicao de dados operacionais globais para role professor.

Contrato aplicado para criacao por bloco:
1. endpoint de criacao operacional: `POST /api/v1/occurrences/`;
2. input minimo: `action=CREATE_OCCURRENCE` + `schedule_output_id`;
3. output: `LessonOccurrenceRead` com `id` e contexto para triagem na pagina de faltas;
4. `PATCH /occurrences/{occurrence_id}` permanece como etapa de decisao final.

Semantica de resposta para criacao por bloco:
- `201`: ocorrencia criada com sucesso;
- `200`: ocorrencia ja existia para o bloco/data e foi reutilizada (idempotencia);
- `404`: bloco inexistente no tenant autenticado;
- `409`: bloco sem contexto operacional valido (ex.: draft/sem data);
- `422`: payload invalido ou contexto sem relacoes minimas.

Observabilidade operacional associada:
- em `POST /api/v1/occurrences/`, o backend regista evento operacional com actor, bloco e resultado (`SUCCESS`, `VALIDATION_FAILURE`, `CONFLICT`, `ERROR`) sem expor dados sensiveis.

## Contrato operacional de substituicoes (Alpha V1 - Passo 2)

### Endpoint de recomendacao por ocorrencia
- rota: `GET /api/v1/occurrences/{occurrence_id}/substitutes/recommendations`;
- role: admin;
- respostas esperadas:
	- `200`: lista ordenada de candidatos elegiveis (pode ser vazia);
	- `404`: ocorrencia nao encontrada no tenant autenticado;
	- `422`: ocorrencia sem contexto valido para recomendacao.

Campos minimos de cada item:
- `rank`, `teacher_id`, `teacher_name`, `subject_id`, `subject_name`;
- `substitutions_in_period`, `daily_load_hours`, `days_since_last_substitution`;
- `justification`.

### Endpoint de confirmacao de substituicao
- rota: `PATCH /api/v1/occurrences/{occurrence_id}`;
- role: admin;
- payload para substituicao: `status=SUBSTITUTED` + `substitute_teacher_id` + `substitute_subject_id`.

Respostas esperadas para confirmacao:
- `200`: substituicao confirmada e persistida com auditoria;
- `404`: ocorrencia nao encontrada no tenant autenticado;
- `409`: conflito de regra de negocio (transicao invalida, conflito de slot, candidato deixou de ser elegivel, etc.);
- `422`: payload inconsistente ou contexto invalido.

Regra critica de seguranca operacional:
- backend deve revalidar elegibilidade no momento da confirmacao, mesmo que candidato tenha sido recomendado segundos antes.

Observabilidade operacional associada:
- em `PATCH /api/v1/occurrences/{occurrence_id}`, o backend regista evento operacional de decisao com actor, `occurrence_id`, `schedule_output_id` e resultado.

### Endpoint de resumo de observabilidade
- rota: `GET /api/v1/occurrences/observability/summary`;
- role: admin;
- objetivo: disponibilizar contadores basicos por organizacao para piloto.

Resposta minima:
- `window_days`;
- `total_events`;
- `decisions_success`;
- `validation_failures`;
- `conflicts`.

### Endpoint legado de disponibilidade por slot
- rota: `GET /api/v1/occurrences/substitutes`;
- role: admin;
- uso atual: suporte operacional complementar por slot/data.

Observacao:
- fluxo principal de decisao do Passo 2 usa recomendacao por ocorrencia, nao consulta generica por slot.

### Endpoint legado descontinuado (decisao 2026-04-12)
- rota: `GET /api/v1/substitutions/suggestions`.
- estado: descontinuado (deprecated + `410 Gone`).
- motivo: fluxo legado nao garante o mesmo nivel de seguranca/consistencia do fluxo canónico por ocorrencia.

Contrato de resposta:
- `410`: endpoint descontinuado com mensagem de migracao para
	`GET /api/v1/occurrences/{occurrence_id}/substitutes/recommendations`.

### Compatibilidade legacy durante Alpha (Ponto 12)
- rota legacy mantida: `POST /api/v1/substitutions/`.
- role: admin.

Comportamento interno (adaptador):
1. resolve bloco publicado por `lesson_id + timeslot_id + date` no tenant autenticado;
2. cria/reutiliza ocorrencia canónica por bloco (`LessonOccurrence`);
3. aplica decisao `SUBSTITUTED` no fluxo de ocorrencias (fonte de verdade funcional);
4. preserva resposta legacy (`SubstitutionResponse`) e escrita idempotente na tabela `substitutions` para consultas legacy.

Semantica de erro esperada no endpoint legacy:
- `400`: aula/timeslot/professor invalido ou fora da organizacao; mismatch de professor original;
- `409`: substituto sem elegibilidade no contexto da ocorrencia ou conflito operacional;
- `422`: contexto invalido para decisao operacional;
- `403`: role sem permissao (professor).

Garantia de compatibilidade:
- chamadas legacy e chamadas novas (`POST/PATCH /occurrences`) convergem para o mesmo estado final de ocorrencia;
- retries com payload identico nao duplicam contabilizacao em `ClassProgress`.

## Contrato operacional de repair mode (Alpha V1 - Passo 3)

### Trigger de regeneracao
- rota: `POST /api/v1/schedule/generate`;
- payload: `mode=full | repair`;
- role: admin.

Comportamento especifico para `mode=repair`:
1. preflight valida se existe horizonte fora da janela de estabilidade.
2. se `frozen_until >= hard_end_date`, resposta e erro de preflight e a task nao e enfileirada.
3. quando valido, a regeneracao considera apenas periodo fora da janela congelada.
4. antes de construir carga remanescente do solver, o backend reconcilia compromissos publicados ate `frozen_until`:
	- conta blocos ativos `NONE/GIVEN` como carga comprometida;
	- exclui do credito blocos `GAP/SUBSTITUTED` (mantem divida no planeado).

Status esperados no trigger:
- `200`: task aceite para processamento;
- `400`: `preflight_failed` (inclui problemas operacionais, incluindo bloqueio por janela de estabilidade sem horizonte valido).

### Aprovacao de draft
- rota: `POST /api/v1/schedule/drafts/{gen_id}/approve`;
- role: admin.

Regra obrigatoria de estabilidade:
- aprovacao nao pode reescrever horario publicado dentro da janela de estabilidade;
- apenas blocos fora da janela sao promovidos para ativo.

Objetivo funcional:
- garantir que ajustes de curto prazo dentro da janela sao tratados por ocorrencias (GAP/GIVEN/SUBSTITUTED), e nao por substituicao estrutural do publicado.

### Diff de draft (horizonte efetivo)
- rota: `GET /api/v1/schedule/drafts/{gen_id}/diff`.
- o diff compara apenas blocos com `date >= frozen_until + 1 dia`.
- resposta inclui metadados: `repair_window_days`, `frozen_until`, `compared_from_date`.

## Contrato operacional de geracao assincrona e cancelamento (Alpha V1 - Ponto 14)

### What mudou
- geracao passou a ter contrato explicito de continuidade assincrona por task;
- status da task passou a expor sinal de cancelamento solicitado;
- novo endpoint admin para cancelar geracao em curso;
- ownership da task e validado por tenant antes de status/cancel;
- contrato de persistencia reforca all-or-nothing (sem gravacao parcial em cancelamento/erro).

### Why mudou
- evitar perda de controlo operacional quando o utilizador navega para outra pagina;
- permitir cancelamento explicito com seguranca multi-tenant;
- garantir estabilidade de dados: ou publica horario completo, ou nao publica nada.

### Endpoints do fluxo
1. `POST /api/v1/schedule/generate`
2. `GET /api/v1/schedule/status/{task_id}`
3. `POST /api/v1/schedule/cancel/{task_id}`

### Regras de autorizacao e ownership
- `POST /schedule/generate`: admin-only.
- `POST /schedule/cancel/{task_id}`: admin-only.
- `GET /schedule/status/{task_id}`: utilizador autenticado da mesma organizacao da task.
- validacao de ownership obrigatoria por mapeamento `task_id -> organization_id`.
- task de outra organizacao deve falhar com `403`.

### Semantica de status
- `GET /schedule/status/{task_id}` retorna:
	- `task_id`, `status`, `result`, `detail`, `phase`, `progress`, `cancel_requested`.
- quando `result.status=Success`, o backend inclui `remaining_summary` para transparencia operacional:
	- `raw_remaining_hours`;
	- `reconciled_remaining_hours`;
	- `committed_credited_hours`;
	- `post_expand_remaining_hours`.
- quando `solver_version=v2`, o backend inclui tambem `candidate_pruning` no resultado da task:
	- `candidates_before`;
	- `candidates_after`;
	- `removed_total`;
	- `removed_ratio`;
	- `removed_by_reason`.
- quando status e terminal (`SUCCESS`, `FAILURE`, `REVOKED`), o backend limpa estado temporario de task ativa por organizacao.
- em `REVOKED` sem detalhe tecnico, backend devolve detalhe operacional explicito de cancelamento.

### Semantica de cancelamento
- `POST /schedule/cancel/{task_id}`:
	- marca flag cooperativa de cancelamento para a task;
	- tenta revoke imediato no worker para reduzir latencia;
	- se task ja terminou, devolve `Already finished` sem alterar estado historico.

### Matriz de respostas esperadas
- `POST /schedule/cancel/{task_id}`:
	- `200`: pedido de cancelamento aceite (`Cancel requested`) ou task ja terminal (`Already finished`);
	- `403`: task existe mas pertence a outro tenant;
	- `404`: task nao encontrada no mapeamento de ownership;
	- `503`: camada de validacao de ownership indisponivel.

### Garantia transacional (all-or-nothing)
- em modo `full`: limpeza de janela futura + escrita do novo horario + atualizacao de `projected_end_date` no mesmo commit.
- em modo `repair`: escrita de draft apenas no commit final.
- em erro/cancelamento durante o fluxo: rollback total da transacao em curso.
- historico executado de ocorrencias nao e reescrito para "corrigir" metricas.

### 4 pilares (verificacao)
- Otimizacao: cancelamento reduz consumo inutil de CPU em geracoes sem interesse operacional.
- Estabilidade: rollback evita estados parciais e corrupcao funcional.
- Escalabilidade: tracking de task por tenant permite monitorizacao consistente em execucao concorrente.
- Seguranca: ownership por organizacao bloqueia acesso cruzado a status/cancel.

### Itens ainda a definir
- politica final de retencao/TTL das chaves operacionais de task por tenant (valor atual tecnico existe, politica de governance ainda "a definir").

## Contrato operacional API e transacao (Alpha V1 - Passo 4)

### Validacao de payload (occurrences)
- `PATCH /api/v1/occurrences/{occurrence_id}` exige `status` no payload.
- payload parcial sem `status` retorna `422`.
- campos inesperados no payload sao rejeitados com `422` (contrato estrito, sem ignorar silenciosamente input extra).

### Matriz de status coberta para fluxo de substituicoes
- recomendacoes (`GET /occurrences/{occurrence_id}/substitutes/recommendations`):
	- `200` lista (incluindo lista vazia);
	- `404` ocorrencia inexistente no tenant;
	- `422` ocorrencia sem contexto operacional valido.
- confirmacao (`PATCH /occurrences/{occurrence_id}`):
	- `200` decisao persistida;
	- `404` ocorrencia inexistente no tenant;
	- `409` conflito de regra/estado concorrente;
	- `422` payload invalido.

### Autorizacao por role
- recomendacoes e confirmacao operacional sao admin-only.
- professor recebe `403` nestas operacoes.

### Garantias transacionais e concorrencia
- decisao + contabilizacao + auditoria executam no mesmo commit.
- em erro no meio do fluxo, rollback total sem persistencia parcial.
- confirmacoes simultaneas da mesma ocorrencia sao serializadas por lock de linha:
	- uma confirmacao vence;
	- tentativa concorrente conflitante falha com `409`.

### Retry seguro apos erro transitório
- pedido identico repetido (mesmo status e mesmo payload de substituicao) e idempotente.
- retry nao duplica progresso/divida nem cria segunda decisao historica.

## Contrato semanal enriquecido (Alpha V1 - Ponto 13, Pacote C)

### Endpoint semanal
- rota: `GET /api/v1/schedule/week`;
- role:
	- admin: pode consultar por `class_id` ou `teacher_id`;
	- professor: apenas consulta do proprio horario (escopo forçado para `teacher_id == current_user.teacher_id`);
- filtro obrigatorio: `class_id` ou `teacher_id`;
- rate limit dedicado: `30/minute;360/hour` para suportar navegacao semanal normal sem colidir com o limite global de `50/hour`;
- semantica: payload additive-first (campos antigos preservados + novos campos operacionais).

Guardas obrigatorias para professor:
- pedido com `class_id` deve falhar com `403`;
- pedido com `teacher_id` diferente do proprio deve falhar com `403`.

Campos novos por slot semanal:
1. `occurrence_id` (nullable): id da ocorrencia ligada ao bloco;
2. `occurrence_decided_at` (nullable): timestamp da decisao final quando existente;
3. `can_create_occurrence` (bool): indica se o bloco pode iniciar criacao operacional;
4. `can_decide_occurrence` (bool): indica se existe ocorrencia para triagem/decisao.

Garantias de compatibilidade:
- campos historicos (`schedule_output_id`, `occurrence_status`, `hours_given`, etc.) mantidos sem quebra;
- consumidores antigos continuam funcionais;
- consumidores novos podem tomar decisao de UX com os flags sem inferencia implícita.

Regra de consumo frontend (2026-04-17):
- estado operacional aberto/fechado deve priorizar `occurrence_decided_at`:
	- `occurrence_decided_at = null` => ocorrencia aberta (pendente de decisao);
	- `occurrence_decided_at != null` => ocorrencia fechada (resultado final em `occurrence_status`).
- disponibilidade de acao operacional no bloco deve seguir `can_create_occurrence` e `can_decide_occurrence` (sem bloqueio local por `is_past`).

## Clean architecture na API

API pertence a Layer Interface.
Portanto:
- recebe e valida input;
- chama casos de uso/servicos de negocio;
- devolve contrato de saida;
- nao decide regra de dominio por conta propria.

## Exemplo pratico (sem fixar rota)

Caso de uso: "professor atualiza disponibilidade"

Contrato esperado:
- autenticacao valida;
- professor so altera dados proprios;
- dados persistidos com tenant isolation;
- resposta confirma atualizacao sem expor dados de terceiros.

## Impacto por layer

### Interface
- contrato estavel e previsivel para consumo frontend.

### Regras de negocio
- negocio centralizado em servicos/casos de uso, nao no controlador HTTP.

### Base de dados
- persistencia com isolamento por organization_id e consistencia transacional.

## Addendum de contrato (2026-04-20)

### GET /api/v1/occurrences/debts
Semantica consolidada:
- divida e reconhecida no momento da decisao (`GAP`/`SUBSTITUTED`), sem filtro implicito de data passada.

Campos de resposta:
1. visao operacional total (retrocompativel):
	- `total_gaps`, `total_hours_owed`;
	- por item: `gap_occurrences`, `hours_owed`.
2. visao vencida ate data de referencia:
	- `total_gaps_overdue`, `total_hours_owed_overdue`, `as_of_date`;
	- por item: `gap_occurrences_overdue`, `hours_owed_overdue`.

Garantia de compatibilidade:
- consumidores existentes continuam a funcionar com `total_gaps`/`total_hours_owed` e `items[*].gap_occurrences`/`hours_owed`.

### LessonOccurrenceRead (create/list/get/patch)
Payload enriquecido para triagem operacional sem lookups obrigatorios:
- contexto letivo: `class_id`, `class_name`, `subject_id`, `subject_name`;
- contexto temporal do slot: `timeslot_id`, `timeslot_start_time`, `timeslot_end_time`;
- nomes de intervenientes: `planned_teacher_name`, `executed_teacher_name`, `decided_by_user_name`.

Regra de decisor:
- `decided_by_user_name` usa nome do utilizador quando disponivel;
- fallback para email quando `name` estiver vazio.