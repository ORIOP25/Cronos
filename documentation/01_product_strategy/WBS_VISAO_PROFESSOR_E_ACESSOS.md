# WBS - Visao Professor e Controlo de Acessos

## Objetivo
Definir um plano tecnico detalhado para consolidar a experiencia por role na aplicacao:
- admin sem tab de preferencias pessoais de disponibilidade;
- professor com exatamente 2 tabs funcionais;
- sincronismo operacional de horario do professor com o horario publicado pela organizacao.

## 5 Ws

### What
Implementar separacao explicita de navegacao e acesso entre admin e professor, com contrato funcional fechado:
1. admin nao deve ver a tab "Minhas Preferencias";
2. professor deve ver apenas:
   - Minhas Preferencias (disponibilidade);
   - Meus Horarios (apenas o proprio horario atual ate ao fim do ano letivo);
3. horario do professor deve refletir publicacoes novas de horario feitas pelo admin, mantendo consistencia entre todos os utilizadores da organizacao.

### Who
- admin: governa geracao/publicacao, sem acesso de menu a experiencia pessoal de disponibilidade.
- professor: define disponibilidade e consulta apenas o proprio horario.
- equipa tecnica: frontend, backend API, testes e documentacao.

### Where
- Interface: sidebar, rotas protegidas e paginas professor.
- Regras de negocio/API: contratos de autorizacao e leitura do horario semanal por teacher_id do utilizador autenticado.
- Base de dados: leituras tenant-scoped de ScheduleOutput, Lesson, Timeslot e Availability.

### When
- No login: aplicacao deve abrir no fluxo correto por role.
- Na navegacao: menu e rotas devem manter coerencia de permissao.
- Apos publicacao de novo horario: visao professor deve atualizar sem depender de acao manual tecnica.

### Why
- reduzir ambiguidade de produto e risco de uso indevido;
- alinhar UI com invariantes do dominio (professor = disponibilidade + proprio horario);
- reforcar seguranca por role e previsibilidade operacional multi-tenant;
- manter confianca no sincronismo de horario entre admin e professores.

## Estado atual confirmado (baseline)
1. Login ja redireciona admin para dashboard e professor para my-availability.
2. Sidebar ainda mostra "Minhas Preferencias" para todos os utilizadores.
3. Endpoint semanal ja impõe escopo do professor para o proprio teacher_id.
4. Nao existe pagina dedicada "Meus Horarios" para professor.
5. Disponibilidade do professor e gravada, mas o carregamento inicial da disponibilidade no frontend ainda nao esta fechado end-to-end com endpoint dedicado de leitura "me".

## Escopo funcional alvo (fechado para implementacao)
1. Menu admin: remover tab "Minhas Preferencias".
2. Menu professor: exibir apenas 2 tabs:
   - Minhas Preferencias;
   - Meus Horarios.
3. Rotas professor:
   - acesso permitido apenas a /my-availability e /my-schedules;
   - tentativa de acesso a rotas admin => bloqueio com feedback claro e sem data leakage.
4. Meus Horarios:
   - mostra apenas horario do teacher_id autenticado;
   - navegacao semanal limitada ao horizonte da escola (ate hard_end_date do ano letivo ativo).
5. Sincronismo:
   - ao existir nova geracao publicada, visao professor deve refletir dados atualizados no SLA definido para Alpha.

## Decisoes fechadas (2026-04-17)
1. SLO de sincronismo professor-admin (Alpha):
   - alvo operacional: atualizacao visivel ate 30s apos publicacao ativa;
   - tolerancia maxima observavel: 60s em condicoes degradadas controladas.
2. Mecanismo de atualizacao em pagina aberta:
   - polling leve por endpoint de generation/version ativa (sem SSE/WebSocket nesta fase).
3. Politica de bloqueio de rota para admin em /my-availability:
   - admin redirecionado para /dashboard (separacao de experiencia por role).

---

## WBS tecnico detalhado

### 1.0 Governance de contrato por role

#### 1.1 Fechar contrato funcional de navegacao
Implementacao:
- formalizar matriz de permissao UI x role para menus e rotas;
- consolidar nomenclatura final: "Meus Horarios" com rota dedicada `/my-schedules`;
- fechar comportamento para acessos proibidos (redirect + mensagem).

Testes obrigatorios:
- matriz de permissao revisada e aprovada (admin/professor);
- checklist de nao regressao de rotas existentes.

Edge cases:
- user com role invalida ou nula na store;
- professor sem teacher_id associado.

#### 1.2 Definir SLO de sincronismo (alpha)
Implementacao:
- SLO fechado em 30s para atualizacao visivel ao professor apos publicacao ativa;
- medicao oficial: `schedule_sync_latency_seconds = teacher_view_update_ts - schedule_publish_ts`;
- criterio de aceite Alpha: `p95 <= 30s` e `p99 <= 60s`.

Testes obrigatorios:
- teste de observacao de delta de horario apos publicacao pelo admin dentro do SLA;
- executar 3 iteracoes consecutivas em ambiente seed canónico e registar latencias observadas.

Edge cases:
- latencia de rede alta;
- janela de deploy/rollback no backend.

### 2.0 Interface - menu e roteamento por role

#### 2.1 Reestruturar sidebar por role
Implementacao:
- admin: remover link "Minhas Preferencias";
- professor: renderizar apenas "Minhas Preferencias" e "Meus Horarios";
- manter estado visual consistente (sem links fantasma).

Testes obrigatorios:
- render menu admin sem tabs de professor;
- render menu professor com exatamente 2 tabs;
- snapshot/semantic assertions para labels corretas.

Edge cases:
- rehydration da store com dados antigos;
- troca rapida de sessao (logout/login com role diferente).

#### 2.2 Guardas de rota por role
Implementacao:
- criar guardas dedicadas:
  - AdminOnlyRoute (existente) para manter areas administrativas;
  - TeacherOnlyRoute para /my-availability e /my-schedules;
  - fallback robusto para role desconhecida.
- impedir que professor aceda a rotas administrativas por URL direta;
- impedir que admin aceda ao fluxo professor se decisao funcional for bloqueio total.

Testes obrigatorios:
- navegacao direta por URL com role professor para rota admin retorna bloqueio/redirect;
- navegacao direta por URL com role admin para rota teacher segue regra definida.

Edge cases:
- token expirado durante navegacao;
- isAuthenticated true com user incompleto.

### 3.0 Frontend - Minhas Preferencias (professor)

#### 3.1 Fechar carregamento inicial de disponibilidade
Implementacao:
- introduzir endpoint de leitura da propria disponibilidade (preferencialmente `/teachers/me/availability` ou equivalente);
- preencher availabilityMap inicial com dados persistidos;
- preservar comportamento de pintura e gravação bulk.

Testes obrigatorios:
- professor abre pagina e ve preferencia previamente gravada;
- atualizacao sobrescreve estado anterior sem duplicacao.

Edge cases:
- professor sem registos de disponibilidade (empty state);
- timeslots removidos/alterados entre gravações.

#### 3.2 UX de feedback operacional
Implementacao:
- substituir alerts genericos por feedback consistente (loading/success/error);
- mensagens orientadas a acao sem expor detalhe sensivel.

Testes obrigatorios:
- erro 403/404/400 mapeado para mensagem operacional correta;
- loading e disabled state durante save.

Edge cases:
- retries consecutivos;
- perda de conexao no submit.

### Estado de execucao - Ponto 3 (2026-04-17)

#### What foi fechado
1. Carregamento inicial end-to-end da disponibilidade do professor com endpoint self-service.
2. Hidratacao do availabilityMap no frontend com dados persistidos.
3. Feedback operacional consistente em pagina (sem alert generico) para loading/sucesso/erro.

#### Who impactado
- professor: passa a ver preferencias previamente gravadas no arranque da pagina;
- admin: sem impacto de permissao no fluxo professor;
- equipa tecnica: contrato API/UI fechado para leitura+escrita de disponibilidade.

#### Where foi aplicado
- interface: pagina `MyAvailability`;
- regras de negocio/API: `GET /api/v1/teachers/me/availability`;
- base de dados: leitura tenant-scoped de `Availability` + validacao de `Timeslot` por organizacao.

#### When e valido
- no primeiro load da pagina de preferencias;
- em cada gravacao de disponibilidade por bulk update;
- em cenarios de erro HTTP (400/403/404) com mensagem operacional dedicada.

#### Why esta decisao
- reduzir friccao operacional no uso diario do professor;
- eliminar ambiguidade de estado (sem dados vs erro real);
- reforcar coerencia de autorizacao por role com contrato self-service.

#### Fechos tecnicos confirmados
1. `GET /teachers/me/availability` devolve apenas disponibilidade do professor autenticado no tenant.
2. frontend filtra entradas antigas cuja referencia de timeslot ja nao existe no tenant atual.
3. save permanece bulk e sobrescreve estado anterior sem duplicacao no payload final.
4. save aplica disabled state explicito durante submissao.

#### Validacao executada
1. frontend: testes dedicados de load inicial, overwrite sem duplicacao, mapeamento de erros 400/403/404 e disabled state no save.
2. backend: testes de self-read do professor autenticado e bloqueio explicito para role admin.

### 4.0 Frontend - Meus Horarios (nova pagina professor)

#### 4.1 Criar pagina dedicada de horario do professor
Implementacao:
- nova pagina com foco professor-only:
  - sem controlos de geracao/cancelamento/aprovacao;
  - sem seletores de turma/professor;
  - teacher_id resolvido da sessao autenticada.
- reutilizar componentes de grelha semanal onde fizer sentido, retirando acoes admin.

Testes obrigatorios:
- render da grelha com horario do proprio professor;
- ausencia de botoes administrativos;
- comportamento de navegacao semanal.

Edge cases:
- professor sem teacher_id associado;
- semana sem blocos (empty state explicito).

#### 4.2 Limite temporal ate fim do ano
Implementacao:
- obter limite hard_end_date/ano letivo ativo via endpoint seguro para current_user;
- bloquear navegacao para semanas apos limite;
- mostrar feedback claro quando nao ha mais semanas validas.

Testes obrigatorios:
- tentativa de navegar apos hard_end_date bloqueada no frontend;
- semana dentro do limite carrega normalmente.

Edge cases:
- escola sem configuracao ativa de ano letivo (frontend recebe 404 e mostra mensagem operacional para contacto admin);
- diferenca de timezone no calculo da semana.

### Estado de execucao - Ponto 4 (2026-04-17)

#### What foi fechado
1. Criada pagina dedicada `Meus Horarios` para professor, separada da pagina operacional admin.
2. Nova leitura backend `GET /api/v1/schedule/me/horizon` para metadados minimos de horizonte semanal.
3. Navegacao semanal do professor bloqueada apos `hard_end_date` com feedback explicito em pagina.

#### Who impactado
- professor: consulta apenas o proprio horario semanal, sem controlos administrativos;
- admin: mantem fluxo operacional em `Schedules`, sem regressao de permissao;
- equipa tecnica: contrato frontend/backend fechado para limite temporal e semana recomendada.

#### Where foi aplicado
- interface: nova pagina `MySchedules` na rota `/my-schedules`;
- regras de negocio/API: endpoint `GET /schedule/me/horizon` teacher-only;
- base de dados: leitura tenant-scoped de `OrganizationSettings` + `ScheduleOutput` ativo.

#### When e valido
- ao abrir `Meus Horarios` (resolucao inicial da semana recomendada);
- ao tentar navegar para semana seguinte apos limite hard end date;
- em tenant sem configuracao valida de horizonte (retorno 404 com mensagem operacional).

#### Why esta decisao
- eliminar ambiguidade entre experiencia professor e operacao administrativa;
- garantir previsibilidade temporal da consulta semanal ate ao fim do ano letivo;
- reforcar seguranca de role, evitando parametros sensiveis no cliente para determinar escopo.

#### Fechos tecnicos confirmados
1. `/my-schedules` passa a usar pagina dedicada teacher-only (`MySchedules`).
2. endpoint `/schedule/me/horizon` devolve `week_start_recommended`, `hard_end_date` e `active_generation_id`.
3. role admin e bloqueada em `/schedule/me/horizon` com `403`.
4. ausencia de configuracao valida de horizonte devolve `404`.

#### Validacao executada
1. frontend: testes de ausencia de controlos admin, empty state, bloqueio apos hard end date e mapeamento de erro 404.
2. backend: testes de contrato 200/403/404 para endpoint de horizonte do professor.

### 5.0 Backend API - contratos professor

#### 5.1 Endpoint de leitura da propria disponibilidade
Implementacao:
- criar endpoint self-service para professor ler disponibilidade atual;
- garantir tenant isolation e escopo no current_user.

Testes obrigatorios:
- professor le proprio mapa;
- professor nao consegue ler disponibilidade de outro teacher_id;
- admin recebe 403 no endpoint self-service de professor.

Edge cases:
- teacher_id nao associado ao user;
- teacher_id associado mas professor desativado.

#### 5.2 Endpoint de metadados de horizonte de horario
Implementacao:
- expor contrato minimo para "Meus Horarios":
  - semana inicial recomendada;
  - data limite hard_end_date;
  - versao/geracao ativa para sincronismo.
- manter Annotated, respostas tipadas e status documentados.

Testes obrigatorios:
- resposta correta por tenant;
- 403 para acessos sem permissao;
- 404 para tenant sem horizonte configurado valido.

Edge cases:
- organizacao sem horario publicado;
- ausencia de org settings do ano letivo ativo.

### Estado de execucao - Ponto 5 (2026-04-17)

#### What foi fechado
1. Contrato backend self-service de disponibilidade consolidado em `GET /teachers/me/availability`.
2. Contrato backend de metadados de horizonte consolidado em `GET /schedule/me/horizon`.
3. Regras de permissao e edge cases de perfil/tenant cobertas por testes dedicados.

#### Who impactado
- professor: acede apenas aos contratos self-service do proprio contexto autenticado;
- admin: bloqueado nos endpoints self-service de professor;
- equipa tecnica: contratos backend com semantica de erro e tenant scope validados.

#### Where foi aplicado
- interface API: endpoints `teachers` e `schedule`;
- regras de negocio: scoping por `current_user` + `organization_id`;
- base de dados: leitura tenant-scoped de `Availability`, `OrganizationSettings` e `ScheduleOutput`.

#### When e valido
- em leitura de disponibilidade do professor autenticado;
- em leitura de horizonte semanal antes da carga da pagina `Meus Horarios`;
- em cenarios sem perfil docente, sem configuracao de horizonte e sem horario publicado.

#### Why esta decisao
- remover ambiguidade de permissao nos contratos self-service;
- garantir isolamento de tenant e previsibilidade operacional para o professor;
- alinhar comportamento real da API com o WBS e com a suite de regressao.

#### Fechos tecnicos confirmados
1. `GET /teachers/me/availability` devolve 403 para admin, 403 para teacher sem perfil e 400 para utilizador inativo.
2. professor nao consegue ler listagem global de professores (`GET /teachers/` bloqueado com 403).
3. `GET /schedule/me/horizon` devolve `active_generation_id = null` quando ainda nao existe horario publicado.
4. `GET /schedule/me/horizon` devolve 403 para admin/teacher sem perfil e 404 sem horizonte configurado.
5. horizonte semanal devolvido respeita scoping por tenant em orgs diferentes.

#### Validacao executada
1. backend: 14 testes focados em availability/horizon a passar (`tests/test_business_logic.py`).

### 6.0 Sincronismo admin-professor (consistencia de horario)

#### 6.1 Estrategia de refresh para professor
Implementacao:
- implementar polling por versao/geracao ativa no endpoint `GET /schedule/me/horizon`;
- invalidar leitura semanal do professor quando `active_generation_id` mudar;
- manter sem push (SSE/WebSocket) nesta fase Alpha.
- garantir que alteracao publicada pelo admin atualiza leitura do professor sem reload manual tecnico.

Testes obrigatorios:
- cenario end-to-end: admin publica horario novo, professor aberto em Meus Horarios recebe atualizacao no SLA.

Edge cases:
- nova geracao sem alteracao de blocos para aquele professor;
- atualizacao simultanea com troca de semana no cliente.

#### 6.2 Garantia de fonte unica de verdade
Implementacao:
- professor sempre consome ScheduleOutput ativo (is_draft=false) por semana;
- nenhum dado de cache local pode sobrepor resposta oficial do backend.

Testes obrigatorios:
- invalidacao de cache apos detecao de nova versao;
- sem dados stale apos voltar ao foco da janela.

Edge cases:
- race entre refetch e logout;
- falha temporaria do endpoint de versao.

### Estado de execucao - Ponto 6 (2026-04-17)

#### What foi fechado
1. Sincronismo professor-admin implementado com polling de horizonte a cada 30 segundos.
2. Mudanca de `active_generation_id` passou a invalidar cache de leitura semanal do professor.
3. Fonte unica de verdade mantida no backend ativo (`ScheduleOutput` com `is_draft=false`) sem sobreposicao por estado local.

#### Who impactado
- professor: recebe atualizacao de horario publicado sem reload manual tecnico;
- admin: publicacao ativa passa a refletir na vista do professor dentro do SLA definido;
- equipa tecnica: fluxo de sincronismo fechado sem introduzir canal push nesta fase.

#### Where foi aplicado
- interface: pagina `MySchedules`;
- regras de negocio/API consumida: `GET /schedule/me/horizon` (polling) + `GET /schedule/week` (dados semanais);
- cache cliente: invalidacao seletiva das queries semanais do professor autenticado.

#### When e valido
- enquanto a pagina `Meus Horarios` estiver aberta com sessao valida;
- a cada ciclo de polling do horizonte;
- sempre que a geracao ativa publicada for alterada.

#### Why esta decisao
- cumprir o contrato de sincronismo da Alpha (alvo 30s, tolerancia 60s);
- reduzir risco de dados stale na operacao diaria do professor;
- manter simplicidade operacional com menor superficie tecnica do que canais push nesta etapa.

#### Fechos tecnicos confirmados
1. `useTeacherScheduleHorizon` suporta `refetchInterval` e polling em background.
2. `MySchedules` compara `active_generation_id` atual vs anterior e invalida apenas cache semanal do professor no tenant.
3. UI apresenta feedback explicito quando deteta sincronizacao para nova geracao ativa.
4. Navegacao semanal continua limitada por `hard_end_date` sem regressao funcional.

#### Validacao executada
1. frontend: testes de polling configurado em 30s e invalidacao de cache quando a geracao ativa muda (`frontend/src/test/MySchedules.test.jsx`).

### 7.0 Seguranca, estabilidade e escalabilidade

#### 7.1 Seguranca por role e tenant
Implementacao:
- reforcar 403 em qualquer tentativa de professor consultar horario de outro professor;
- revisar endpoints consumidos pela experiencia professor para garantir least privilege.

Testes obrigatorios:
- testes de autorizacao negativa por role;
- testes cross-tenant para schedule e availability.

Edge cases:
- token valido com role alterada no servidor;
- sessao stale apos revogacao de permissao.

#### 7.2 Performance de leitura semanal
Implementacao:
- validar consultas de week schedule com filtros index-friendly;
- confirmar ausencia de N+1 em joins de Lesson/Teacher/Room/Timeslot.

Testes obrigatorios:
- teste com dataset large-scale e leitura semanal de professor dentro de threshold.

Edge cases:
- semana com alto volume de blocos;
- muitos professores simultaneos a consultar.

### Estado de execucao - Ponto 7 (2026-04-17)

#### What foi fechado
1. Hardening de seguranca em cenarios de perfil adulterado cross-tenant para endpoints teacher self-service.
2. Validacao de isolamento tenant em leitura semanal do professor sem vazamento de blocos de outra organizacao.
3. Otimizacao da leitura semanal com resolucao de modulo ativo sem padrao N+1.

#### Who impactado
- professor: mantem leitura do proprio horario/disponibilidade sem risco de leakage entre tenants;
- admin: beneficia de backend mais estavel em carga semanal por reduzir custo de queries;
- equipa tecnica: cobertura explicita de seguranca e escalabilidade para contratos do professor.

#### Where foi aplicado
- seguranca/API: `GET /teachers/me/availability` e `GET /schedule/week`;
- regras de negocio/performance: `schedule_service.get_week_schedule_sync` (resolucao de modulo ativo);
- testes backend: suites `test_business_logic.py` e `test_occurrences.py`.

#### When e valido
- em todas as leituras teacher self-service com sessao autenticada;
- em semanas com multiplos pares turma-disciplina na mesma consulta;
- em cenarios com volume crescente de blocos dentro da janela semanal.

#### Why esta decisao
- reforcar least privilege e tenant isolation contra cenarios de token/perfil inconsistentes;
- prevenir degradacao de performance por custo linear de queries no enriquecimento semanal;
- sustentar os 4 pilares para operacao real em escala de escola piloto.

#### Fechos tecnicos confirmados
1. `GET /teachers/me/availability` nao expõe dados fora do tenant mesmo quando `teacher_id` do utilizador aponta para outro tenant (retorno 404).
2. `GET /schedule/week` nao devolve blocos de outro tenant no mesmo cenario de perfil adulterado (retorno 200 com lista vazia no tenant autenticado).
3. Resolucao de modulo ativo no `schedule_service` passou de leitura por par (N+1) para leitura em batch de modulos e progresso.
4. Teste de regressao de carga semanal confirma custo de query estavel (limite maximo de queries na leitura semanal sob dataset ampliado).

#### Validacao executada
1. backend: `2 passed` em testes focados de seguranca tenant para teacher self-service (`tests/test_business_logic.py`).
2. backend: `1 passed` em teste focado de performance/N+1 da leitura semanal (`tests/test_occurrences.py`).

### 8.0 Testes (backend, frontend, integracao)

#### 8.1 Backend - contratos professor
Implementacao:
- novos testes para:
  - GET self availability;
  - metadados de horizonte/versao;
  - regras de 403/404/422 por role e contexto.

Testes obrigatorios:
- suite dedicada de regressao professor role.

Edge cases:
- teacher sem perfil;
- horario inexistente na organizacao.

#### 8.2 Frontend - navegacao e UI por role
Implementacao:
- testes de sidebar por role;
- testes de route guard;
- testes de Meus Horarios sem controlos admin;
- testes de sincronismo por mudanca de versao.

Testes obrigatorios:
- cobertura de fluxo completo login professor -> disponibilidade -> meus horarios.

Edge cases:
- role unknown;
- persistencia local quebrada.

#### 8.3 E2E funcional (piloto)
Implementacao:
- cenario 1: professor autenticado ve apenas 2 tabs;
- cenario 2: admin gera/publica horario e professor observa atualizacao;
- cenario 3: professor sem teacher_id recebe bloqueio claro.

Testes obrigatorios:
- smoke e2e em ambiente docker-compose com seed canonico.

Edge cases:
- restart backend durante polling;
- publicacao de draft fora da janela de estabilidade.

### Estado de execucao - Ponto 8 (2026-04-17)

#### What foi fechado
1. Suite backend dedicada para contratos de role professor criada e validada.
2. Cobertura frontend reforcada para guardas de role e estados corrompidos de autenticacao.
3. Cobertura frontend reforcada para fluxo professor sem perfil docente em `Meus Horarios`.

#### Who impactado
- professor: maior previsibilidade de bloqueios e mensagens operacionais em cenarios limite;
- admin: validacao explicita de bloqueio em fluxos self-service de professor;
- equipa tecnica: regressao automatizada mais robusta para contratos por role.

#### Where foi aplicado
- backend testes: `backend/tests/test_teacher_role_regression.py`;
- frontend testes de guardas: `frontend/src/test/AppRoleGuards.test.jsx`;
- frontend testes de horario professor: `frontend/src/test/MySchedules.test.jsx`.

#### When e valido
- em execucoes locais/CI de regressao focada por role;
- antes de promover alteracoes de navegacao/autorizacao para ambiente piloto;
- em cada alteracao dos endpoints self-service do professor.

#### Why esta decisao
- reduzir risco de regressao em permissao, tenant scope e UX de bloqueio;
- formalizar cobertura dos cenarios de erro previstos no WBS (403/404/422 + role unknown);
- sustentar estabilidade da feature antes do rollout controlado.

#### Fechos tecnicos confirmados
1. Backend cobre contratos de disponibilidade/horizonte/semanal para respostas 200/403/404/422 em role professor.
2. Guardas frontend tratam role desconhecida e estado autenticado corrompido com redirect seguro para login.
3. `MySchedules` valida cenario de professor sem `teacher_id` com mensagem operacional clara.

#### Validacao executada
1. backend: `5 passed` em `tests/test_teacher_role_regression.py`.
2. frontend: `22 passed` em execucao focada (`AppRoleGuards`, `DefaultLayoutRoleMenu`, `MyAvailability`, `MySchedules`).
3. smoke e2e docker-compose (8.3): **a definir** como automacao dedicada; nao existe suite e2e funcional ativa no repositorio neste momento.

### 9.0 Rollout e operacao

#### 9.1 Rollout controlado
Implementacao:
- ativar em ambiente de staging com contas admin/professor reais de seed;
- validar checklist funcional antes de promover para ambiente piloto.

Testes obrigatorios:
- checklist de go/no-go por role.

Edge cases:
- regressao em menu admin apos deploy;
- cache browser com assets antigos.

#### 9.2 Monitorizacao funcional minima
Implementacao:
- medir taxa de erro nos endpoints professor e latencia de sincronismo;
- registar alertas para 403/5xx anormais por rota critica.

Testes obrigatorios:
- simulacao de falha controlada e verificacao de recuperacao.

Edge cases:
- falso positivo de erro por timeout curto;
- burst de requests em troca de turno.

### Estado de execucao - Ponto 9 (2026-04-17)

#### What foi fechado
1. Rollout controlado formalizado com checklist operacional por role (staging -> piloto).
2. Monitorizacao minima implementada para endpoints criticos do professor com persistencia tenant-scoped.
3. Alertas operacionais ativos para 403/5xx anormais por rota critica, com validacao de falha controlada e recuperacao.

#### Who impactado
- professor: maior confianca operacional por deteccao precoce de degradacao nos contratos self-service;
- admin: passa a ter resumo tecnico objetivo para go/no-go de rollout;
- equipa tecnica: ganha trilho observavel para triagem de permissoes e erros de API no fluxo professor.

#### Where foi aplicado
- regras de negocio/API: instrumentacao em `GET /teachers/me/availability`, `POST /teachers/{teacher_id}/availability`, `GET /schedule/me/horizon` e `GET /schedule/week` (escopo professor);
- base de dados: nova tabela `teacher_endpoint_operational_event` para eventos de monitorizacao;
- interface API de operacao: endpoint admin-only `GET /teachers/observability/summary`.

#### When e valido
- durante rollout em staging com contas reais de seed;
- durante operacao piloto para monitorizacao em janela de 5 a 1440 minutos;
- em qualquer incidente de burst 403/5xx no fluxo professor.

#### Why esta decisao
- reduzir risco de promover regressao de autorizacao ou disponibilidade para piloto;
- suportar triagem operacional com dados objetivos (taxa de erro e latencia p95 por endpoint);
- manter resposta rapida a degradacoes sem depender de observacao manual ad-hoc.

#### Fechos tecnicos confirmados
1. Eventos por endpoint critico do professor ficam persistidos com `org_id`, `http_status`, `latency_ms` e timestamp.
2. Resumo operacional devolve agregacao por endpoint com `error_rate_percent` e `p95_latency_ms`.
3. Alerta `ABNORMAL_403_RATE` dispara com `count >= 10` e taxa >= 20% na janela.
4. Alerta `HIGH_5XX_RATE` dispara com taxa 5xx > 2% na janela.
5. Endpoint de observabilidade de professor e admin-only (`403` para role teacher).

#### Validacao executada
1. backend: `9 passed` em execucao focada (`tests/test_teacher_observability.py` + `tests/test_teacher_role_regression.py`).
2. simulacao de falha controlada + recuperacao: alerta 403 ativa em burst e e removido apos normalizacao da taxa.
3. simulacao de degradacao 5xx: alerta de taxa alta detetado por endpoint critico.

### 10.0 Documentacao e alinhamento final

#### 10.1 Atualizar docs por layer
Implementacao:
- Interface: UX de menu/rotas professor;
- Regras de negocio: contrato de role e sincronismo;
- Base de dados/API: endpoints novos e semantica de erro.

Testes obrigatorios:
- revisao cruzada para garantir ausencia de contradicao entre camadas.

Edge cases:
- requisito alterado apos inicio da implementacao;
- discrepancia entre comportamento real e doc.

### Estado de execucao - Ponto 10 (2026-04-17)

#### What foi fechado
1. Revisao cruzada concluida entre Interface, Regras de negocio e Base de dados/API para a feature professor/acessos.
2. Documentacao de interface atualizada com contrato final de menu, rotas e sincronismo por role.
3. Invariantes de negocio atualizados para refletir fronteira self-service do professor e sincronismo com horario publicado.
4. Contrato API/BD consolidado com matriz de status para endpoints criticos e regras de observabilidade por tenant.

#### Who impactado
- professor: passa a ter contrato funcional documentado ponta a ponta para disponibilidade e horario proprio;
- admin: passa a ter referencia operacional unica para go/no-go e monitorizacao dos endpoints professor;
- equipa tecnica: ganha baseline documental coerente para manutencao e regressao.

#### Where foi aplicado
- Interface: `documentation/06_frontend_ux/UX_CONSISTENCY_SCHEDULES.md`.
- Regras de negocio: `documentation/02_domain_model/ENSINO_PROFISSIONAL_INVARIANTS.md`.
- Base de dados/API: `documentation/05_backend_api/ENDPOINT_STANDARDS.md`.
- consolidacao do estado do plano: `documentation/01_product_strategy/WBS_VISAO_PROFESSOR_E_ACESSOS.md`.

#### When e valido
- em todas as alteracoes futuras que toquem menu/rotas self-service do professor;
- em revisoes de contrato dos endpoints `teachers` e `schedule`;
- em validacoes de rollout staging -> piloto da feature.

#### Why esta decisao
- eliminar contradicoes entre comportamento implementado e contrato documentado;
- reduzir risco de regressao funcional por leitura parcial de regras;
- sustentar os 4 pilares com rastreabilidade clara por layer.

#### Fechos tecnicos confirmados
1. Interface confirma separacao final por role: admin sem tabs professor; professor com exatamente 2 tabs e guardas dedicadas.
2. Regras de negocio confirmam least privilege para professor e fonte de verdade no horario publicado ativo.
3. API confirma semantica de erro harmonizada para disponibilidade, horizonte e leitura semanal professor.
4. Observabilidade de endpoints professor permanece tenant-scoped e com resumo admin-only.
5. Ponto sem implementacao visual dedicada foi marcado explicitamente como a definir (dashboard frontend do resumo de observabilidade).
6. `GET /schedule/me/horizon` recebeu limite dedicado (`300/hour`) para sustentar polling de 30s sem colisao com o limite global.

#### Validacao executada
1. Revisao cruzada documental por layer concluida sem contradicoes abertas.
2. Verificacao de aderencia ao codigo real concluida para guardas/menus frontend e contratos backend (`teachers`/`schedule`).
3. WBS atualizado com fecho formal do ponto 10 e evidencias de alinhamento.

---

## Criterios de aceite finais da feature
1. admin nao visualiza "Minhas Preferencias" no menu.
2. professor visualiza exatamente 2 tabs: Minhas Preferencias e Meus Horarios.
3. professor nao acede a rotas administrativas por URL direta.
4. Meus Horarios mostra apenas horario do professor autenticado.
5. sincronismo com horario publicado pelo admin ocorre dentro do SLA definido.
6. testes backend/frontend/e2e da feature passam.

## Verificacao dos 4 pilares
- Otimizacao: UI simplificada por role e estrategia de sync eficiente.
- Estabilidade: contratos de rota/autorizacao e regressao automatizada.
- Escalabilidade: sincronismo desacoplado por versao/geracao e consultas semanais index-friendly.
- Seguranca: menor superficie de permissao e reforco de tenant isolation.

---

## Addendum - Correcao de falhas e incidente de perda de dados (2026-04-17)

## Objetivo do addendum
Consolidar, num unico plano de execucao, os passos para corrigir:
1. falhas de seguranca e consistencia identificadas na auditoria hacker + utilizador leigo;
2. incidente reportado de perda aparente de dados apos alguns minutos sem interacao.

## 5 Ws do plano de correcao

### What
Executar hardening completo por camadas (Interface, Regras de negocio/API e Base de dados/Operacao), com foco em:
1. bloqueio de operacoes destrutivas sem autorizacao forte;
2. eliminacao de inconsistencias de contrato HTTP e de comportamento UX;
3. robustez transacional e observabilidade para deteccao precoce de degradacao.

### Who
- admin: mantem capacidade de governanca, com controlos destrutivos estritamente auditados;
- professor: mantem apenas self-service legitimo (disponibilidade + horario proprio);
- equipa tecnica: backend, frontend, QA, operacao e observabilidade.

### Where
- Interface: guardas de rota, feedback de bloqueio, resiliencia de ecras professor;
- Regras de negocio/API: endpoints `teachers` e `schedule`, incluindo endpoints destrutivos;
- Base de dados/operacao: persistencia Postgres, trilho de auditoria e politicas de seed/reset.

### When
- imediatamente (hotfix de contencao de seguranca);
- ciclo seguinte (hardening de contratos e UX);
- fecho de release (validacao E2E + checklist de rollout).

### Why
- proteger os 4 pilares sem regressao funcional;
- remover superficie de risco que permite perda real de dados operacionais;
- reduzir ambiguidade para utilizadores nao tecnicos quando existe erro temporario.

## Incidente adicional - perda aparente de dados apos inatividade

### Causa tecnica confirmada
Foi identificada uma causa real e critica que permite perda de dados operacionais:
1. existe endpoint destrutivo `DELETE /api/v1/schedule/reset`;
2. o endpoint usa `Depends(get_current_user)` em vez de `Depends(get_current_active_admin)`;
3. ao ser chamado, executa `delete_all_schedule_data(...)`, removendo `ScheduleOutput`, `Constraint`, `Lesson` e `Timeslot` do tenant.

### Evidencias confirmadas no codigo
1. `backend/app/api/v1/endpoints/schedule.py` define `@router.delete("/reset")` com `current_user` autenticado simples.
2. `backend/app/api/v1/endpoints/schedule.py` chama `schedule_service.delete_all_schedule_data(...)` no handler desse endpoint.
3. `backend/app/services/schedule_service.py` implementa `delete_all_schedule_data` com deletes em cadeia das tabelas operacionais.

### Importante sobre o trigger observado pelo utilizador
1. a rota destrutiva existe e pode apagar dados reais: **confirmado**;
2. nao foi encontrada chamada automatica dessa rota no frontend atual: **confirmado**;
3. origem exata do pedido destrutivo no ambiente real (manual, script externo, chamada indevida, etc.): **a definir** ate ativar trilho de auditoria de requests destrutivos.

### Estado de persistencia da base de dados
1. em `docker-compose.yml`, o Postgres usa volume nomeado `cronos_postgres_data`: **confirmado**;
2. isto reduz probabilidade de "perda por idle" associada a volume efemero local;
3. portanto, no estado atual, a causa principal de perda de dados identificada no codigo e a exposicao do endpoint destrutivo.

---

## WBS tecnico de correcao (ordem obrigatoria)

### 1.0 Contencao imediata de seguranca

#### 1.1 Fechar endpoint destrutivo a admin-only
Implementacao:
1. trocar dependencia para `get_current_active_admin` no endpoint de reset;
2. garantir resposta `403` para qualquer role nao admin;
3. manter tenant scope no delete.

Testes obrigatorios:
1. admin recebe sucesso no reset;
2. teacher recebe 403 no reset;
3. role invalida/desconhecida recebe 403.

Edge cases:
1. token valido mas user inativo;
2. user sem role reconhecida.

#### 1.2 Registar auditoria de operacoes destrutivas
Implementacao:
1. log estruturado por endpoint destrutivo com `org_id`, `user_id`, `role`, `method`, `path`, `status`, timestamp;
2. correlacao por request id;
3. persistencia minima para investigacao forense de incidentes.

Testes obrigatorios:
1. evento de auditoria criado em chamada de reset bem-sucedida;
2. evento de auditoria criado em tentativa negada (403).

Edge cases:
1. falha de escrita de auditoria nao pode impedir resposta principal;
2. retries nao podem duplicar efeitos destrutivos no dominio.

### 2.0 Regras de negocio/API - hardening transversal

#### 2.1 Default deny para roles fora da matriz
Implementacao:
1. explicitar roles permitidas endpoint a endpoint;
2. negar roles nao previstas (ex: `student`) em endpoints criticos;
3. harmonizar contratos com `ENDPOINT_STANDARDS`.

Testes obrigatorios:
1. matriz negativa por role para `teachers/me/availability`, `schedule/me/horizon`, `schedule/week` e `schedule/reset`;
2. regressao cross-tenant mantida.

Edge cases:
1. role alterada no servidor com token ainda valido;
2. teacher sem `teacher_id` associado.

#### 2.2 Robustez transacional em disponibilidade
Implementacao:
1. validar payload antes de delete massivo;
2. remover qualquer commit colateral que possa confirmar alteracoes parciais em cenarios de erro;
3. preservar atomicidade update disponibilidade + retorno de erro coerente.

Testes obrigatorios:
1. payload invalido nao altera estado anterior;
2. duplicacao de `timeslot_id` devolve erro controlado sem 500;
3. rollback validado em falha intermédia.

Edge cases:
1. timeout entre delete e insert;
2. erro de observabilidade durante finally.

#### 2.3 Contratos HTTP e semantica de erro
Implementacao:
1. alinhar `responses` declarados com erros reais (401/400/403/404/422/429);
2. documentar de forma uniforme por endpoint critico;
3. remover contradicoes entre WBS e API real.

Testes obrigatorios:
1. testes de contrato por status esperado;
2. snapshots de payload de erro sem leakage.

Edge cases:
1. dependencias de auth devolvendo 400 em cenarios inativos;
2. limiters devolvendo 429 em polling intenso.

### 3.0 Interface/UX - resiliencia e clareza para utilizador leigo

#### 3.1 Feedback explicito em bloqueio de rota
Implementacao:
1. manter redirect seguro;
2. adicionar mensagem contextual (sem detalhe sensivel) ao utilizador;
3. evitar percecao de "salto inesperado" sem explicacao.

Testes obrigatorios:
1. role teacher em rota admin: redirect + mensagem;
2. role admin em rota teacher: redirect + mensagem.

Edge cases:
1. store corrompida (user null);
2. role desconhecida.

#### 3.2 Resiliencia de `MySchedules` em falhas temporarias
Implementacao:
1. preservar ultimo estado semanal valido quando horizonte falha temporariamente;
2. fallback operacional com retry orientado;
3. manter bloqueio por hard end date sem regressao.

Testes obrigatorios:
1. erro 429 nao deve aparentar "apagou tudo" sem contexto;
2. erro transitorio com recuperacao automatico restaura vista.

Edge cases:
1. reconexao apos perda de rede;
2. troca de sessao durante polling.

#### 3.3 Limites temporais de navegacao semanal
Implementacao:
1. manter limite superior no hard end date;
2. definir limite inferior documentado em `min_week_start` (inicio do ano letivo normalizado para segunda-feira);
3. feedback claro ao atingir limite inferior/superior.

Testes obrigatorios:
1. nao permitir navegacao fora da janela definida;
2. mensagens consistentes em ambos os limites.

Edge cases:
1. timezone no browser;
2. tenant sem settings validas.

### 4.0 Base de dados e operacao

#### 4.1 Guardrails de operacoes destrutivas
Implementacao:
1. runbook explicito para `seed --reset`, `timeslots/generate` e `schedule/reset`;
2. confirmacao operacional para acoes destrutivas em ambiente piloto/producao;
3. segregacao de ambientes para evitar comando destrutivo acidental.

Testes obrigatorios:
1. validacao de runbook por operacao;
2. simulacao de incidente com trilho de auditoria completo.

Edge cases:
1. execucao de seed com profile errado;
2. reset em tenant indevido por erro humano.

#### 4.2 Protecao de persistencia e recuperacao
Implementacao:
1. checklist de volume Postgres + politica de backup por ambiente;
2. restauracao testada em staging;
3. KPI de RPO/RTO documentado para piloto.

Testes obrigatorios:
1. restore de backup com validacao funcional minima;
2. smoke de login + leitura semanal apos restore.

Edge cases:
1. backup incompleto;
2. restauracao parcial de tabelas operacionais.

### 5.0 Observabilidade, seguranca e SLA

#### 5.1 Cobertura de alertas
Implementacao:
1. incluir alertas para 429 anormal e para operacao destrutiva;
2. correlacionar alertas com role e endpoint;
3. separar sinal tecnico de degradacao vs sinal de seguranca.

Testes obrigatorios:
1. simulacao de burst 429 com alerta ativo;
2. simulacao de delete destrutivo com alerta de severidade alta.

Edge cases:
1. falso positivo em janela curta;
2. falha parcial de ingestao de eventos.

#### 5.2 Medicao real do SLA professor-admin
Implementacao:
1. instrumentar `schedule_sync_latency_seconds` em caminho real de publicacao -> vista professor;
2. acompanhar p95/p99 por tenant;
3. publicar relatorio operacional para go/no-go.

Testes obrigatorios:
1. 3 iteracoes consecutivas em seed canonico com medicao persistida;
2. validacao de p95 <= 30s e p99 <= 60s.

Edge cases:
1. publicacao sem mudanca de blocos para professor;
2. rede degradada durante polling.

### 6.0 Testes e regressao final

#### 6.1 Backend
Implementacao:
1. nova suite para endpoint destrutivo e matriz de roles;
2. testes transacionais de disponibilidade em erro;
3. testes de contrato HTTP harmonizado.

Testes obrigatorios:
1. `403` para teacher em `DELETE /schedule/reset`;
2. estado de dados preservado em erro de disponibilidade;
3. cobertura de roles nao previstas.

#### 6.2 Frontend
Implementacao:
1. testes de mensagens de bloqueio por role;
2. testes de resiliencia de `MySchedules` em 429/erro temporario;
3. testes de limites inferior/superior de navegacao semanal.

Testes obrigatorios:
1. fluxo professor completo sem ghost state;
2. fluxo admin sem regressao de operacao.

#### 6.3 E2E
Implementacao:
1. ativar automacao E2E minima para professor/acessos;
2. incluir cenario de tentativa destrutiva por role nao permitida;
3. incluir cenario de inatividade + retorno ao uso.

Testes obrigatorios:
1. smoke em docker-compose;
2. evidencia de nao perda de dados apos idle controlado.

### Estado de execucao - Addendum (2026-04-17)

#### What foi fechado
1. `DELETE /schedule/reset` passou a admin-only com trilho de auditoria estruturado em sucesso, erro e tentativa negada.
2. Endpoints criticos passaram a default deny para roles fora da matriz (ex.: `student`) em `schedule/week` e update de disponibilidade.
3. Fluxo de disponibilidade ficou robusto contra perda parcial: validacao de payload antes de delete massivo, deteccao de `timeslot_id` duplicado e rollback em erro.
4. `MySchedules` passou a operar com limite inferior e superior (`min_week_start` -> `hard_end_date`) e fallback para ultimo estado valido em falha temporaria.
5. Guardas de rota passaram a expor feedback explicito de acesso negado apos redirect seguro.

#### Validacao executada
1. backend focado: `18 passed` (`tests/test_teacher_role_regression.py` + `tests/test_schedule_generate_preflight.py`).
2. frontend focado: `16 passed` (`src/test/AppRoleGuards.test.jsx` + `src/test/MySchedules.test.jsx`).

### 7.0 Criterios de aceite do addendum
1. endpoint destrutivo protegido por admin-only e auditado.
2. inexistencia de perda de dados operacionais por chamada nao autorizada.
3. contratos de erro e autorizacao alinhados com documentacao por camada.
4. UX de bloqueio e erro clara para utilizador leigo, sem percecao de apagao silencioso.
5. suite backend/frontend/e2e da correcao a passar.

### 8.0 Itens marcados como a definir
1. origem exata do trigger no ambiente real que disparou o reset destrutivo antes deste hardening.
2. dashboard frontend dedicado para resumo de observabilidade operacional.

## Verificacao dos 4 pilares (addendum)
- Otimizacao: reduz retrabalho operacional causado por perdas e estados ambiguos.
- Estabilidade: reforca atomicidade, contratos consistentes e recuperacao previsivel.
- Escalabilidade: melhora robustez de polling, alertas e operacao multi-tenant.
- Seguranca: fecha superficie critica de delete destrutivo sem permissao forte.
