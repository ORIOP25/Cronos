# UX consistency schedules

## Objetivo
Garantir experiencia premium e consistente na operacao diaria da escola.

## 5 Ws da UX

### What
Interface para consulta e operacao de horarios conforme role.

### Who
- admin: experiencia de controlo operacional completo da organizacao.
- professor: experiencia simples e focada em duas tarefas.

### Where
Uso em contexto escolar profissional privado, com foco administrativo.

### When
Uso diario na preparacao, consulta e ajuste de operacao.

### Why
Produto premium exige clareza, confiabilidade percebida e baixa friccao.

## Escopo funcional por role na interface

### Admin
- acesso a fluxos de governanca operacional;
- visao global da organizacao para horarios e ocorrencias.

### Professor
- registar disponibilidade;
- consultar apenas o proprio horario.

A interface nao deve sugerir capacidades alem do role autenticado.

### Contrato de navegacao por role (2026-04-17)
- rota inicial de sessao admin: `/dashboard`;
- rota inicial de sessao professor: `/my-availability`;
- rota dedicada para consulta de horario do professor: `/my-schedules`;
- acesso proibido por role deve redirecionar para a rota inicial desse role;
- redirecionamento por bloqueio de role deve mostrar feedback explicito de acesso negado (sem detalhe sensivel);
- menu deve refletir apenas rotas permitidas para evitar sugestao de capacidade nao autorizada.
- sincronismo da vista de horario do professor: polling por generation/version ativa com alvo de 30s apos publicacao ativa (p95), tolerancia maxima de 60s (p99) na Alpha.

### Matriz de menu e guardas de rota (2026-04-17)
- admin: menu sem `Minhas Preferencias` e sem `Meus Horarios`;
- professor: menu com exatamente 2 tabs (`Minhas Preferencias`, `Meus Horarios`);
- rotas administrativas estao protegidas por guarda admin-only;
- rotas professor (`/my-availability`, `/my-schedules`) estao protegidas por guarda teacher-only.

### Alpha V1 - Ponto 3 (Minhas Preferencias end-to-end)

#### What mudou
- pagina `Minhas Preferencias` passou a carregar disponibilidade persistida no arranque;
- feedback de operacao deixou de usar `alert()` e passou para mensagens em pagina (info/sucesso/erro);
- submit em curso bloqueia interacao (toolbar, grelha e botao) ate conclusao da gravacao.

#### Who
- professor: passa a ter continuidade visual do estado real da propria disponibilidade;
- admin: sem alteracao de experiencia nesta pagina (continua sem acesso ao fluxo professor).

#### Where
- frontend: `MyAvailability` + grelha de disponibilidade;
- backend consumido: `GET /teachers/me/availability` e `POST /teachers/{teacher_id}/availability`.

#### When
- no primeiro carregamento da pagina;
- em cada tentativa de gravacao;
- em erros de contrato HTTP (400/403/404).

#### Why
- reduzir erro humano por falta de contexto inicial;
- evitar feedback abrupto/generico;
- tornar o fluxo diario previsivel e operacionalmente explicito.

#### Regras UX obrigatorias (Ponto 3)
1. disponibilidade persistida deve ser refletida antes da primeira interacao de pintura.
2. `alert()` nao deve ser usado para sucesso/erro neste fluxo.
3. save em curso deve exibir estado `A gravar...` e impedir cliques concorrentes.
4. mensagens de erro devem ser orientadas a acao sem detalhe sensivel.
5. entradas antigas de timeslot removido devem ser ignoradas sem quebrar a pagina.

#### Criterios de aceite UX (Ponto 3)
1. professor abre pagina e ve preferencias previamente gravadas.
2. gravacao sucessiva no mesmo bloco substitui valor anterior sem duplicacao.
3. erros 400/403/404 mostram mensagem operacional especifica.
4. loading e disabled state de save sao explicitamente visiveis.

#### 4 pilares (confirmacao)
- Otimizacao: reduz retrabalho de remarcacao manual por perda de estado inicial.
- Estabilidade: bloqueio de interacao durante submit evita concorrencia no cliente.
- Escalabilidade: contrato self-service desacopla leitura do teacher_id de URL manual no frontend.
- Seguranca: mensagens sem leakage e acesso professor restrito ao proprio contexto autenticado.

### Alpha V1 - Ponto 4 (Meus Horarios professor-only)

#### What mudou
- rota `/my-schedules` passou a usar pagina dedicada (`MySchedules`) em vez de reutilizar pagina operacional admin;
- pagina professor deixou de expor controlos de geracao/aprovacao/cancelamento e seletores de turma/professor;
- navegacao semanal passou a respeitar limites inferior e superior de horizonte (`min_week_start` ate `hard_end_date`) com bloqueio explicito.

#### Who
- professor: experiencia focada apenas em leitura do proprio horario;
- admin: fluxo operacional permanece isolado na pagina `Schedules`;
- suporte escolar: recebe feedback UX claro quando tenant nao tem horizonte configurado.

#### Where
- frontend: `MySchedules`, guard teacher-only, consumo de `GET /schedule/me/horizon` e `GET /schedule/week`;
- backend consumido: metadados de horizonte + horario semanal tenant-scoped.

#### When
- no primeiro carregamento de `Meus Horarios` para definir semana recomendada;
- em cada clique de navegacao semanal;
- em tentativa de ultrapassar o limite temporal da escola.

#### Why
- manter separacao funcional por role sem ambiguidades de permissao;
- evitar consulta de semanas fora do ano letivo valido;
- reduzir suporte reativo com mensagens operacionais claras para 403/404.

#### Regras UX obrigatorias (Ponto 4)
1. professor nao deve ver controlos administrativos na pagina de horarios pessoais.
2. contexto semanal deve iniciar em `week_start_recommended` do backend.
3. tentativa de navegar para semana fora de `[min_week_start, hard_end_date]` deve ficar bloqueada com feedback visivel.
4. semana sem blocos deve mostrar empty state explicito.
5. erro de horizonte inexistente (`404`) deve orientar contacto com admin.
6. em erro temporario de horizonte/semana, a UI deve manter ultimo estado valido e mostrar aviso de degradacao.

#### Criterios de aceite UX (Ponto 4)
1. `/my-schedules` renderiza horario do professor autenticado sem filtros de turma/professor.
2. botoes semanal anterior/seguinte nao permitem sair da janela `[min_week_start, hard_end_date]`.
3. utilizador recebe mensagem clara quando atinge limite inferior ou superior.
4. tenant sem configuracao ativa recebe mensagem operacional sem stack/error tecnico cru.
5. em falha temporaria com ultimo estado valido, a pagina permanece utilizavel com aviso de degradacao.

#### 4 pilares (confirmacao)
- Otimizacao: pagina professor reduz carga cognitiva removendo comandos sem relevancia ao role.
- Estabilidade: bloqueio de horizonte evita estados inconsistentes de navegacao semanal.
- Escalabilidade: contrato de metadados desacopla limite temporal do cliente e suporta multiplos tenants.
- Seguranca: scoping por sessao autenticada elimina risco de consulta por teacher_id arbitrario no frontend.

### Alpha V1 - Ponto 6 (sincronismo admin-professor)

#### What mudou
- `MySchedules` passou a usar polling por horizonte (`GET /schedule/me/horizon`) com intervalo de 30 segundos;
- mudanca de `active_generation_id` passou a invalidar cache semanal do professor autenticado;
- interface passou a mostrar feedback explicito quando a sincronizacao detecta publicacao ativa mais recente.

#### Who
- professor: ve atualizacoes de horario publicado sem reload manual;
- admin: publicacao passa a refletir na vista professor dentro do SLA da Alpha;
- suporte tecnico: ganha previsibilidade para diagnostico de dados stale.

#### Where
- frontend: pagina `MySchedules` + cache React Query da chave `weekSchedule`;
- backend consumido: `GET /schedule/me/horizon` para deteccao de versao ativa e `GET /schedule/week` para leitura oficial.

#### When
- enquanto a pagina de `Meus Horarios` estiver aberta;
- a cada ciclo de polling;
- sempre que a geracao ativa for alterada por publicacao admin.

#### Why
- cumprir o contrato de sincronismo da Alpha (alvo 30s, tolerancia 60s);
- reduzir risco de divergencia entre horario publicado e horario visivel ao professor;
- manter simplicidade operacional sem push nesta fase.

#### Regras UX obrigatorias (Ponto 6)
1. sincronismo deve ocorrer por polling em intervalo fixo de 30s.
2. mudanca de geracao ativa deve invalidar dados semanais do professor no cliente.
3. leitura semanal deve continuar a vir do backend ativo (sem sobrepor com estado local manual).
4. feedback de sincronismo deve ser claro e nao intrusivo.
5. quando polling falhar temporariamente, a UI deve exibir aviso e manter ultimo estado valido.

#### Criterios de aceite UX (Ponto 6)
1. sem reload manual, professor recebe atualizacao apos publicacao ativa dentro do ciclo de polling.
2. cache semanal anterior e invalidada quando `active_generation_id` muda.
3. pagina mantem comportamento de limite por `hard_end_date` sem regressao.

#### 4 pilares (confirmacao)
- Otimizacao: evita refresh manual repetitivo para obter horario atualizado.
- Estabilidade: invalidacao seletiva reduz risco de stale state no cliente.
- Escalabilidade: polling leve por metadados evita custo de push nesta fase.
- Seguranca: sincronismo mantem escopo por teacher autenticado e tenant.

### Alpha V1 - Ponto 10 (alinhamento final Interface x Regras x API)

#### What foi fechado
- contrato UX final por role consolidado com base no comportamento real de menu e guardas de rota;
- mapeamento de mensagens operacionais alinhado com a semantica de erro dos endpoints self-service do professor;
- fronteira de observabilidade clarificada: resumo operacional de endpoints do professor existe em API admin-only e consumo visual dedicado em frontend permanece a definir.

#### Who
- professor: experiencia final fica limitada a disponibilidade + horario proprio, sem ambiguidades de permissao;
- admin: opera apenas nas areas administrativas e valida saude tecnica do fluxo professor por endpoint dedicado;
- equipa tecnica: passa a ter contrato UX/API fechado para manutencao e regressao.

#### Where
- frontend: `DefaultLayout`, `App`, `MyAvailability`, `MySchedules`;
- backend consumido pela interface: `GET /teachers/me/availability`, `POST /teachers/{teacher_id}/availability`, `GET /schedule/me/horizon`, `GET /schedule/week`.

#### When
- valido no login, na navegacao protegida por role e durante uso continuo de `Meus Horarios` com polling ativo;
- valido em erro operacional de contrato (400/403/404/429) com mensagem orientada a acao.

#### Why
- eliminar contradicoes entre o que a interface mostra e o que a API permite;
- reduzir risco de leakage funcional por links/rotas indevidas;
- sustentar rollout com previsibilidade operacional por role.

#### Matriz final de consistencia UX (Passo 10)
1. admin: menu sem tabs professor e bloqueio de rotas teacher-only por redirect seguro.
2. professor: menu com exatamente 2 tabs (`Minhas Preferencias`, `Meus Horarios`) e acesso apenas a `/my-availability` e `/my-schedules`.
3. sincronismo: polling de 30s em `/schedule/me/horizon` e invalidacao seletiva de cache semanal quando muda `active_generation_id`.
4. limite temporal: navegacao semanal bloqueada apos `hard_end_date` com feedback explicito.
5. observabilidade: sem dashboard visual dedicado nesta fase; uso operacional do resumo admin-only via API.

#### 4 pilares (confirmacao)
- Otimizacao: reduz cliques improdutivos e elimina navegacao em areas nao permitidas.
- Estabilidade: contrato de mensagens/rotas evita estados inesperados e suporte reativo ad-hoc.
- Escalabilidade: separacao por role e sincronismo por metadados mantem comportamento previsivel em multiplos tenants.
- Seguranca: UX nao expoe capacidades fora do role autenticado e respeita fronteira self-service.

## Regras de consistencia de estado

1. Loading: estado explicito e previsivel.
2. Erro: mensagem clara com acao de recuperacao quando aplicavel.
3. Empty state: texto explicativo sem ambiguidade.
4. Troca de contexto (ex.: semana/filtro): sem ghost state nem dados stale invisiveis.

### Aplicacao concreta - auditoria tecnica por geracao
- quando nao existem geracoes ativas, a pagina mostra empty state informativo com acao explicita (gerar horario primeiro);
- o frontend nao deve chamar `/schedule/audit/summary` sem geracoes disponiveis;
- objetivo: evitar erro generico de carregamento quando o estado real e ausencia de dados gerados.

## Regras tecnicas de implementacao (confirmadas)

- usar elementos semanticos nativos quando aplicavel;
- evitar nested ternaries;
- usar compare function explicita em ordenacao;
- manter comportamento consistente de selecao/troca de contexto.
- em fluxos criticos, feedback de sucesso/erro deve aparecer dentro da pagina e nao via `alert()` do browser.
- estados de ocorrencia devem usar a mesma copy em toda a interface: `Dada`, `Furo` e `Substituída`.
- confirmacoes de alteracoes criticas devem acontecer dentro da pagina, com aviso inline e sem `window.confirm()`.

## Direcao visual premium (confirmada no posicionamento)

Principios:
- visual profissional e intencional;
- clareza de hierarquia informativa;
- comunicacao de confiabilidade para perfil administrativo.

Nota:
este documento define direcao, nao congela um tema grafico unico.

## Exemplo pratico

Caso: professor entra para atualizar disponibilidade.

Experiencia esperada:
- ve apenas as funcoes permitidas;
- conclui acao em poucos passos;
- recebe feedback claro de sucesso/erro.

Caso: admin consulta operacao diaria.

Experiencia esperada:
- ve contexto global da organizacao;
- identifica rapidamente situacoes que exigem decisao.

## Impacto por layer

### Interface
- principal camada responsavel por usabilidade e percecao de produto premium.

### Regras de negocio
- UX deve refletir regras reais, nao criar atalho que viole autorizacao.

### Base de dados
- estados de interface dependem de respostas consistentes e tenant-scoped.

## Alpha V1 - Passo 5 (operacao diaria de ocorrencias)

### What mudou
- painel de ocorrencias passou a separar visualizacao por estado operacional de resolucao: pendentes, resolvidas e todas;
- linha de ocorrencia passou a mostrar: estado atual, docente previsto, contexto de execucao e decisao final;
- fluxo de decisao foi simplificado para uma modal unica com:
	- selecao direta da decisao (GIVEN, GAP, SUBSTITUTED),
	- ranking de candidatos quando SUBSTITUTED,
	- confirmacao explicita antes de persistir;
- feedback de erro backend passou a ser exibido com mensagem operacional (detail) em vez de texto generico;
- role professor fica em modo leitura, com bloqueio explicito de acoes operacionais no frontend.

### Why (compatibilidade com passos anteriores e seguintes)
- preserva os contratos hardenizados do Passo 4 (payload estrito, erros 409/422/403);
- respeita as regras de dominio dos Passos 1 e 2 (imutabilidade, decisao humana final, substituicao com revalidacao backend);
- mantem o repair mode do Passo 3 intacto, pois opera sobre ocorrencias e nao sobre reescrita de publicado;
- prepara os Passos 6 e 7 ao reduzir ambiguidade de operacao real, facilitando reproducao em seeds e regressao funcional.

### 4 pilares (confirmacao)
- Otimizacao: filtro de pendentes/resolvidas reduz tempo de triagem operacional.
- Estabilidade: confirmacao explicita e mensagens claras reduzem erro humano.
- Escalabilidade: estados padronizados e sem ghost state suportam volume real de escola piloto.
- Seguranca: defesa em profundidade por role no frontend, sem substituir autorizacao backend.

### Validacao minima esperada
- loading, erro e empty state explicitos na area de ocorrencias;
- aviso claro quando nao ha elegiveis para SUBSTITUTED;
- professor sem permissao para confirmar decisoes;
- erro transacional backend refletido na UI sem ocultacao do motivo operacional.

## Delta de UX para fechar interatividade end-to-end (2026-04-12)

### Estado atual confirmado
- pagina de faltas permite decidir ocorrencias existentes;
- grelha semanal inicia fluxo operacional por clique no bloco para role admin;
- criacao encaminha para a pagina de faltas com contexto da ocorrencia;
- quando o bloco ja tem ocorrencia, a acao de grelha privilegia "Ir para Faltas" (sem recriar ocorrencia);
- decisao final invalida caches de forma granular e reflete nas visoes relevantes.

### Workflow UX alvo (aprovado)
1. Admin clica no bloco da aula na grelha semanal.
2. Abre modal contextual com dados da aula.
3. Acao "Criar Ocorrencia" cria entrada operacional vinculada ao bloco.
4. Entrada aparece imediatamente na pagina de faltas.
5. Gestao detalhada permanece na pagina de faltas (GAP/SUBSTITUTED).
6. Se SUBSTITUTED, UI mostra ate 3 recomendacoes principais.
7. Confirmacao atualiza grelha semanal e visoes por professor/turma.

### 5 Ws da decisao de UX

What:
- separar inicio rapido no bloco da gestao em escala na pagina de faltas.

Who:
- admin ganha velocidade operacional;
- professores e turmas recebem reflexo coerente da decisao.

Where:
- inicio no ecrã de horarios;
- triagem e decisao na pagina de faltas.

When:
- imediatamente apos comunicacao da falta.

Why:
- reduz friccao de entrada sem perder organizacao para volume alto de ocorrencias.

### Criterios de aceite UX para este delta
1. maximo de 3 cliques para iniciar ocorrencia a partir do bloco.
2. sem ghost state entre grelha semanal e pagina de faltas.
3. feedback de sucesso/erro em linguagem operacional clara.
4. bloqueio explicito para roles sem permissao.

## Delta de UX para geracao assincrona resiliente (Alpha V1 - Ponto 14)

### What mudou
- pagina de horarios passou a persistir `task_id` ativo de geracao por organizacao;
- ao sair e voltar ao ecrã, o utilizador retoma o estado da geracao sem perder contexto visual;
- controlo explicito `Cancelar geracao` disponivel enquanto a task esta em execucao;
- estados `CANCELED/REVOKED` mostram feedback operacional claro (nao silencioso).

### Who
- admin: inicia, acompanha e cancela geracao quando necessario;
- professor: nao recebe controlos de geracao/cancelamento.

### Where
- ecrã de horarios (`Schedules`) com painel de estado de geracao e controlos no header.

### When
- durante task em curso (polling de status ativo);
- apos remount/navegacao entre paginas, desde que task ainda esteja ativa no backend.

### Why
- reduzir ansiedade operacional de "perdi a geracao" ao navegar na aplicacao;
- melhorar controlo humano em tarefas longas sem sacrificar seguranca de dados.

### Regras UX obrigatorias
1. Sair da pagina nao implica cancelamento automatico da task backend.
2. Reentrada na pagina deve tentar retomar `task_id` persistido para o tenant atual.
3. Botao `Gerar Horario` desativa durante execucao ativa.
4. Botao `Cancelar geracao` aparece apenas com task ativa e role admin.
5. Erro de cancelamento deve mostrar alerta explicito com acao de retry.

### Criterios de aceite UX (Ponto 14)
1. iniciar geracao, navegar para outra pagina e regressar: status da task continua visivel.
2. clicar `Cancelar geracao` envia pedido para backend com o `task_id` ativo.
3. ao terminar/cancelar/falhar, estado persistido da task ativa e limpo para evitar ghost tracking.

### 4 pilares (verificacao)
- Otimizacao: evita repeticao manual de operacoes por perda de contexto visual.
- Estabilidade: estado persistido por tenant reduz inconsistencias de UI em remount.
- Escalabilidade: padrao funciona para multiplos admins sem acoplamento a um unico ecrã.
- Seguranca: controlo de acao sensivel restrito a admin, sem elevar permissao no frontend.

## Delta de UX para operacao real (Alpha V1 - 2026-04-17)

### What mudou
- ocorrencias abertas passaram a ter estado visual explicito `Pendente de decisao`;
- badges de resultado final (`Dada`, `Furo`, `Substituida`) passaram a aparecer apenas para ocorrencias fechadas;
- lista de ocorrencias passou a usar ordenacao deterministica no cliente (data, hora quando disponivel, id);
- acao operacional em bloco passado passou a ser permitida quando os flags da API indicam acao valida;
- quando um bloco nao permite acao, a interface passou a mostrar motivo de bloqueio em linguagem operacional;
- copy tecnica foi simplificada em ecras de operacao (`Schedules`, `MySchedules`, `SchoolConfig`, `Occurrences`, `ScheduleAuditDashboard`).

### Who
- admin: reduz ambiguidade na triagem de faltas/substituicoes e ganha previsibilidade de ordenacao;
- professor: recebe mensagens mais claras na consulta semanal;
- suporte escolar: reduz interpretacao errada de estado pendente como estado final fechado.

### Where
- `Occurrences`: estado operacional aberto/fechado + detalhe de decisao final;
- `WeekGrid`: estado pendente para ocorrencia aberta e acao operacional sem bloqueio por passado;
- `Schedules` e `MySchedules`: substituicao de termos tecnicos por linguagem orientada a tarefa;
- `SchoolConfig` e `ScheduleAuditDashboard`: cabecalhos e hints com terminologia funcional.

### When
- durante triagem diaria de ocorrencias;
- durante navegacao semanal (admin/professor);
- durante acompanhamento de geracao de horario em curso.

### Why
- evitar erro operacional por leitura ambigua de estado;
- reduzir carga cognitiva da equipa administrativa;
- manter consistencia entre Interface e regra de negocio (`decided_at` define aberto/fechado).

### Regras UX obrigatorias deste delta
1. ocorrencia com `decided_at = null` nunca pode parecer decisao final fechada.
2. resultado final (`GIVEN/GAP/SUBSTITUTED`) so aparece com `decided_at != null`.
3. acao operacional no bloco deve seguir flags API (`can_create_occurrence`, `can_decide_occurrence`) sem bloqueio local por `is_past`.
4. lista de ocorrencias deve manter ordenacao deterministica para triagem previsivel.
5. textos visiveis ao utilizador final devem evitar jargao tecnico quando existir equivalente operacional claro.

### Criterios de aceite UX deste delta
1. ocorrencia aberta aparece como `Pendente de decisao` em painel e grelha.
2. lista de ocorrencias preserva ordem reproduzivel em recarregamentos com mesmo dataset.
3. bloco passado elegivel permite iniciar fluxo operacional.
4. bloco sem acao valida mostra orientacao clara ao operador.
5. termos tecnicos mapeados (ex.: CP-SAT, hard end date, hard stop) deixam de aparecer nos ecras operacionais alvo.

### 4 pilares (verificacao)
- Otimizacao: menos retrabalho por triagem errada e menos tempo de interpretacao de mensagens.
- Estabilidade: contrato aberto/fechado consistente reduz contradicoes visuais.
- Escalabilidade: ordenacao deterministica e estados padronizados suportam volume real da escola piloto.
- Seguranca: sem alteracao de permissao; frontend continua a respeitar role boundaries e flags backend.

## Delta de UX para operacao real (2026-04-20)

### What mudou
- tab de `Ocorrencias Registadas` passa a abrir em `Todas` por defeito (sem filtro implícito de resolucao);
- filtros de data deixam de ser aplicados por defeito (vazios), evitando esconder ocorrencias em refresh/reentrada;
- grelha de ocorrencias passa a exibir `Turma`, `Disciplina`, `Docente Definitivo` e `Decisao Final`;
- coluna `Horas Dadas` foi removida da tabela de registos para reduzir ambiguidade operacional;
- resumo de decisao final passa a mostrar o decisor real (`decided_by_user_name`, com fallback adequado);
- navegacao `Schedules -> Absences` deixa de injetar `date_from/date_to` automaticamente.

### Why
- evitar desaparecimento aparente de registos por filtros escondidos;
- reduzir duvida operacional sobre quem decidiu e qual foi o docente efetivo;
- manter foco em triagem global sem perder contexto da ocorrencia selecionada.

### Regras UX obrigatorias deste delta
1. filtros de estado/data devem ser sempre explicitos para o utilizador.
2. contexto minimo por linha de ocorrencia: data, turma, disciplina, estado, docente previsto, docente definitivo, decisao final.
3. abertura contextual a partir do horario nao pode bloquear a listagem global por data do bloco.

### Criterios de aceite UX deste delta
1. ao abrir `Ocorrencias`, pendentes e resolvidas podem coexistir sem acao extra do utilizador.
2. ocorrencia decidida mostra explicitamente `Decidida em ... por <utilizador>`.
3. coluna `Horas Dadas` nao aparece na grelha de registos.
4. navegacao a partir de bloco com ocorrencia usa apenas contexto necessario (`occurrence_id`/`class_id`).

### 4 pilares (verificacao)
- Otimizacao: menos cliques de correccao de filtros e menor tempo de triagem.
- Estabilidade: elimina variabilidade causada por filtros implícitos ao refrescar.
- Escalabilidade: grelha com contexto completo evita roundtrips e lookup manual em volume alto.
- Seguranca: sem alteracao de permissoes; continua admin-only para decisao operacional.