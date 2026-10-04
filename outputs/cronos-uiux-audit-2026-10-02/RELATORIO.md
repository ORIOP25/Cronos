# Relatório de caça ao bug e revisão UI/UX — Cronos

**Data:** 2 de outubro de 2026  
**Ambiente:** produção, https://cronos.pt  
**Sessão:** organização Rodrigo's Organization, perfil Diretor  
**Plano de referência:** [PLANO.md](PLANO.md)

## Resultado

Foi feita uma exploração manual extensa da interface, incluindo navegação, catálogos, operações de CRUD com dados sintéticos, importação CSV, tutorial, horários, folhas de horas e amostras em três larguras. Não foi uma execução integral dos 154 casos do plano: vários dependem de outro perfil, outra organização, uma Fundação incompleta, estado operacional preparado ou relógio controlado. Os casos que não foram exercitados permanecem pendentes ou condicionados; não contam como aprovados.

Os pontos mais relevantes são o arranque de uma geração de horário com um único clique, a conclusão antecipada de uma aula futura através da decisão de ocorrência, a apresentação de uma ocorrência com decisão final como ainda pendente, uma possível divergência na média de blocos por turma e tempos longos e pouco previsíveis ao gravar um curso ou remover uma turma. As restantes observações são melhorias de microcopy e de apresentação.

## Achados

### F01 — A geração do horário começa imediatamente ao clicar em “Atualizar horário”

**Prioridade:** P2 · **Tipo:** risco de UX/ação consequente · **Rota:** /schedules

**Reprodução:** abrir a ação de atualização do horário e clicar uma vez em “Atualizar horário”. A aplicação colocou a geração em fila e mostrou “A organizar as aulas”; não abriu opções nem pediu confirmação. Depois apareceu “Cancelar geração”.

Durante o ensaio, o clique foi acidental. A geração foi cancelada. O botão regressou ao estado inicial; o dashboard manteve 24 558 blocos, a referência de versão observada e zero conflitos. Não foi publicada uma versão nova.

**Impacto:** uma ação de uma só etapa pode iniciar trabalho de geração que o utilizador talvez pretendesse apenas configurar ou inspecionar. O cancelamento só fica disponível depois do início.

**Sugestão:** usar um rótulo inequívoco como “Iniciar geração” e mostrar antes um resumo do âmbito e do efeito. Uma confirmação curta ou um passo de revisão evitaria inícios acidentais.

### F02 — A média de blocos por turma parece usar mais turmas do que o catálogo atual

**Prioridade:** P2, por confirmar · **Tipo:** consistência de dados · **Rota:** /dashboard

O dashboard apresenta 24 558 blocos e média de 454,8 blocos por turma. Essa média implica cerca de 54 turmas. O catálogo apresentou 48 turmas ativas (16 cursos × 3 anos), e a seleção de turma no horário também expôs 48. A média por professor, 533,9, é compatível com 46 professores.

A implementação local calcula esta média a partir dos identificadores de turma encontrados nas linhas do horário. Isso pode incluir turmas antigas ou fora do catálogo atual. A inspeção da UI e do código não prova a origem dos seis identificadores adicionais na produção.

**Sugestão:** reconciliar a população usada no denominador com as turmas ativas e indicar claramente período e população da métrica. Confirmar a consulta e os dados de produção antes de abrir um bug definitivo.

### F03 — Gravações de curso e turma demoram muito sem progresso útil

**Prioridade:** P2 · **Tipo:** feedback/performance percebida · **Rota:** /courses

A gravação de um curso sintético mostrou “A gravar…” durante cerca de 24 segundos. A remoção de uma turma ficou em “A guardar…” por mais de 18 segundos e aproximadamente até 26 segundos. Após reabrir a página, a remoção estava persistida. Não apareceu erro final, mas a demora e a troca de rótulos deixam incerto se a ação continua ou ficou bloqueada.

**Sugestão:** manter o mesmo estado de progresso, indicar quando a operação continua ativa e impedir submissões repetidas. Se houver uma demora esperada, uma mensagem curta ajuda a evitar repetição ou abandono da página.

### F04 — A validação obrigatória aparece em inglês numa interface portuguesa

**Prioridade:** P3 · **Tipo:** localização/acessibilidade · **Rotas:** /rooms, /subjects e formulário de curso

Ao submeter os formulários de sala, disciplina e curso sem preencher o nome obrigatório, o browser apresentou “Please fill out this field.” em inglês. A validação nativa cumpre o bloqueio, mas interrompe a consistência linguística e não oferece uma mensagem contextual no formulário.

**Sugestão:** apresentar uma mensagem em português junto ao campo e associá-la ao controlo. Manter a validação do servidor como salvaguarda.

### F05 — Texto de competência tem discordância de número

**Prioridade:** P3 · **Tipo:** microcopy · **Rota:** /members

Várias linhas mostram “1 selecionadas”. O numeral singular pede “1 selecionada”; para mais de uma, usar o plural correspondente.

### F06 — Campos do calendário ficam apertados e o botão quebra a linha

**Prioridade:** P3 · **Tipo:** apresentação responsiva · **Rota:** /config

Na largura desktop observada, o texto da opção “Pausa Escolar” fica cortado no seletor de tipo e “Adicionar evento” quebra em duas linhas. A ação continua visível, mas a leitura do tipo depende da largura do campo e o botão torna a linha mais irregular.

**Sugestão:** reservar largura para o seletor, permitir que a linha se reorganize deliberadamente em ecrãs estreitos e evitar cortar o valor selecionado.

### F07 — Grelha de disponibilidade não comunica claramente o scroll horizontal

**Prioridade:** P3 · **Tipo:** descoberta/responsividade · **Rotas:** dashboard e horários

Em 375 e 768 px a matriz mostra apenas parte dos dias e exige deslocamento horizontal. A barra existe, mas não há indicação visual clara de que se pode deslizar. No telemóvel, a lista de 48 salas em cartões altos também obriga a bastante scroll.

**Sugestão:** acrescentar uma pista de gesto ou controlos de navegação para os dias; considerar filtros ou cartões mais compactos para listas longas em mobile.

### F08 — Download do modelo CSV não teve confirmação observável

**Prioridade:** P3 · **Tipo:** comportamento por confirmar · **Rota:** /imports

Dois cliques em “Descarregar modelo” não produziram um evento de download observável na sessão de browser usada e a página não mostrou feedback. Também não houve erro ou aviso JavaScript no registo consultado. Como a sessão de automação pode não refletir todos os downloads do browser, não está confirmado que a funcionalidade esteja avariada.

**Sugestão:** retestar no browser normal e, se necessário, mostrar confirmação de início ou erro de download. Não classificar como bug funcional até confirmar a ausência do ficheiro.

### F09 — Uma ocorrência permite concluir uma aula futura e creditar horas antes da data

**Prioridade:** P1 · **Tipo:** integridade operacional/guardas temporais · **Rota:** /schedules → /absences

**Reprodução:** numa aula de 12/10/2026, 09:00–09:50, da TAS 10 (Matemática, Nuno Ramos), criar uma ocorrência e selecionar “Dada”. Confirmar a decisão. Em 02/10/2026, o bloco era futuro. O horário passou a mostrá-lo como “Concluída” e o progresso da disciplina mostrou 0,8 h / 60 h (1,4%). No diálogo normal de sumário, a ação de marcar uma aula futura como dada estava desativada.

**Impacto:** uma decisão feita antes da aula pode contabilizar execução e progresso curricular prematuramente. A ocorrência deixa de aparecer nas listas de faltas. Não encontrei uma ação normal da interface para devolver esta aula a pendente; editar o texto do sumário não altera o estado. Este registo sintético continua concluído.

**Sugestão:** aplicar à decisão operacional a mesma guarda temporal da ação “Aula Dada”. Se houver uma exceção legítima para registo antecipado, explicar a consequência e permitir uma reversão normal e auditável.

### F10 — Uma falta decidida como “Furo” continua rotulada como decisão pendente

**Prioridade:** P2 · **Tipo:** estado e orientação operacional · **Rota:** /absences

**Reprodução:** criar uma ocorrência para 13/10/2026, escolher “Furo”, assinalar a confirmação e confirmar. A dívida de horas passou a incluir 0,8333333333333334 h, pelo que a decisão foi contabilizada. Apesar disso, a ocorrência continuou no separador “Decisões Pendentes” com o estado “Pendente”. Ao reabrir, “Decisão final” também dizia “Pendente de decisão”.

**Impacto:** o utilizador não consegue distinguir uma ocorrência por decidir de uma falta decidida que ainda tem dívida por recuperar. A ação de decisão continua exposta, aumentando o risco de uma nova decisão ou revisão acidental.

**Sugestão:** separar os estados “decisão pendente” e “dívida por resolver”; mostrar “Furo” como decisão final e manter a ocorrência na lista adequada para a etapa de recuperação.

### F11 — A dívida de horas mostra a precisão interna do cálculo

**Prioridade:** P3 · **Tipo:** formatação/legibilidade · **Rota:** /absences → Dívidas de Horas

Dois blocos de 50 minutos apareceram como `0.8333333333333334h` cada, e o total como `1.6666666666666667h`. Os valores expõem a representação decimal de ponto flutuante e estão em inglês técnico, sem arredondamento nem formatação local.

**Sugestão:** apresentar duração em minutos ou horas arredondadas de forma consistente, com rótulos localizados (por exemplo, “50 min” e “1 h 40 min”).

### F12 — A tabela de histórico comprime os campos e torna as linhas difíceis de comparar

**Prioridade:** P3 · **Tipo:** legibilidade/densidade de tabela · **Rota:** /absences → Histórico

Na viewport observada (~1178 px), a data/hora, nomes dos docentes e sumário quebram em várias linhas. Um sumário sintético curto ocupou cerca de seis linhas, aumentando bastante a altura do registo e separando visualmente os valores da mesma ocorrência.

Na mesma viewport, a tabela também excede a largura disponível: uma barra horizontal aparece no fundo e as colunas “Docente Efetivo” e “Ações” ficam fora da área visível até deslocar a tabela.

**Sugestão:** dar mais espaço ao sumário e manter data e hora juntas; tornar o scroll horizontal mais descobrível ou apresentar os campos como cartões em viewports estreitas. Para sumários longos, usar truncagem com acesso claro ao texto integral.

### F13 — Ao reabrir um bloco com ocorrência, os avisos repetem-se e indicam o responsável errado

**Prioridade:** P3 · **Tipo:** microcopy/feedback duplicado · **Rota:** /schedules → bloco com ocorrência

Depois de criar uma ocorrência, reabrir o bloco mostrou dois avisos: “Esta aula tem uma ocorrência registada. Contacte um administrador para reverter.” e “Ocorrência registada. Não é possível alterar. Contacte um administrador para reverter em Faltas & Ocorrências.” O utilizador atual é Diretor e consegue efetivamente reverter o registo nessa página.

**Impacto:** a mesma orientação aparece duas vezes e a primeira mensagem sugere que o utilizador não tem capacidade para resolver a situação.

**Sugestão:** consolidar num único aviso com uma ligação/ação direta para Faltas e Ocorrências e texto coerente com as permissões da sessão.

### F14 — Intervalo de datas invertido é apresentado como erro de ligação

**Prioridade:** P3 · **Tipo:** validação e recuperação · **Rota:** /absences

**Reprodução:** no histórico, preencher “De” com 14/10/2026 e “Até” com 12/10/2026. A lista mostrou “Não foi possível carregar as ocorrências. Verifique a ligação e volte a tentar.” Ao limpar os campos, os resultados voltaram a carregar.

**Impacto:** um erro de entrada não é explicado junto dos campos e parece uma falha de rede; não há indicação de que a data inicial tem de preceder a final.

**Sugestão:** validar a ordem do intervalo antes da consulta e apresentar o erro junto do par de datas. Se o servidor rejeitar o intervalo, preservar os filtros e distinguir erro de validação de falha de ligação.

### F15 — A grelha semanal falhou intermitentemente ao carregar uma semana com aulas

**Prioridade:** P2 · **Tipo:** disponibilidade/recuperação, por confirmar · **Rota:** /schedules

Na continuação do ensaio, a semana de 12–16/10/2026 mostrou “Não foi possível carregar o horário” para TAS 10 e TAS 11. “Tentar novamente” também terminou nesse estado. Uma carga intermédia da TAS 11 foi bem-sucedida, enquanto as semanas 28/09–02/10 e 05/10–09/10 mostraram corretamente o estado vazio. A consola não registou erros JavaScript.

**Limitação:** sem telemetria do servidor não é possível separar uma falha temporária do serviço de um problema específico desta consulta. Este estado impediu o teste do cancelamento antes de criar ocorrência e a continuação da duplicação após reversão.

**Sugestão:** recolher um identificador de pedido/erro no estado apresentado ao utilizador e verificar a estabilidade do endpoint nessa semana. Não classificar a causa como confirmada apenas com a mensagem de ligação.

### F16 — A opacidade das linhas revertidas reduz o contraste abaixo do mínimo

**Prioridade:** P2 · **Tipo:** acessibilidade/contraste · **Rota:** /absences → Histórico

As linhas no estado “Revertida” recebem `opacity: 0.5`. Composta sobre o fundo observado, essa opacidade reduz o contraste efetivo do sumário para **3,68:1** e do texto branco no badge “Revertida” para **1,97:1**. Ambos ficam abaixo de 4,5:1 para texto normal.

**Sugestão:** comunicar que o registo foi revertido através do texto e de um ícone/borda, sem atenuar toda a linha; ajustar o par de cores do badge para manter contraste suficiente.

### F17 — “Sem elegíveis” não indica a disponibilidade que falta nem como a configurar

**Prioridade:** P2 · **Tipo:** orientação operacional/fricção de configuração · **Rotas:** /members → /courses/:courseId/classes/:classId/subjects → /absences

Foi criado o perfil sintético “Professor QA UI 2026-10-02” como Professor, com Português e Matemática, no modo “Apenas recurso de horário” (sem convite nem acesso de sessão). Associei-o temporariamente a Matemática em TCO 10, mantendo a docente original em Português, e abri uma ocorrência sintética de Português para 14/10/2026 às 09:00. Ao escolher “Substituída”, a UI mostrou apenas “Sem elegíveis para este slot. Registe como GAP.” A decisão não foi confirmada; a ocorrência foi revertida e a associação da turma restaurada.

A implementação local da recomendação também exige uma disponibilidade explícita não negativa para o bloco. A interface administrativa não oferece edição de disponibilidade para este perfil sem sessão de professor; não foi enviado convite nem concedido acesso. A cópia publicada pode diferir do código local, por isso esta regra técnica é evidência de diagnóstico, não prova isolada do estado do serviço em produção.

**Impacto:** a direção não sabe se faltam competência, associação à turma, disponibilidade ou ausência de conflito; também não recebe um caminho para corrigir o motivo. Um professor de horário sem sessão pode parecer configurado, mas continua indisponível para a substituição.

**Sugestão:** indicar os critérios que excluíram candidatos e permitir à direção encaminhar a configuração em falta, ou tornar a edição administrativa da disponibilidade explícita e auditável. Não sugerir “Registe como GAP” como único próximo passo quando a ausência de disponibilidade é corrigível.

### F18 — O controlo de remoção da turma é um botão só com ícone e sem nome acessível

**Prioridade:** P2 · **Tipo:** acessibilidade/risco de ação destrutiva · **Rota:** /courses/:courseId

No cartão de TCO 10, os controlos de lápis, caixote e navegação aparecem como ícones. A árvore acessível expõe o botão do caixote sem texto, aria-label ou title. Ao procurar abrir a turma pelos controlos do cartão, esse botão sem nome abriu “Confirmar remoção da turma”; a confirmação foi cancelada e a turma não foi removida. Clicar no título da turma abriu os detalhes.

**Impacto:** leitores de ecrã e navegação por teclado não conseguem distinguir a ação de remoção; os alvos compactos também facilitam uma escolha destrutiva por engano.

**Sugestão:** atribuir nomes acessíveis específicos a todos os controlos de ícone, tornar a navegação para detalhes um link ou botão próprio e separar visualmente essa área da remoção.

## Cobertura exercitada

| Área | Percurso realizado | Estado |
| --- | --- | --- |
| Navegação e dashboard | Dashboard, menu e rotas administrativas disponíveis; métricas e listas observadas. | Parcial |
| Cursos e turmas | Abrir detalhe, validar obrigatório, criar curso sintético com três turmas, acrescentar/remover turma e apagar o curso; associar e restaurar docentes em TCO 10. | Exercitado com dados sintéticos; associações restauradas. F18 |
| Salas | Obrigatório, criação, edição e remoção de sala sintética; confirmação e retorno à lista. | Exercitado; limpo |
| Disciplinas e módulos | Criar disciplina sintética com módulo, confirmar na lista e remover. | Exercitado; limpo |
| Membros | Lista, pesquisa sem resultados, filtro de estado e membros arquivados; criado um professor sintético com competências, “Apenas recurso de horário” e sem convite. | Parcial; não foi enviado convite nem concedido acesso |
| Configuração | Datas, intervalos, feriados e eventos inspecionados; modal de personalização aberto e cancelado. | Leitura; sem gravação |
| Horários | Semanas sem aulas e semana com dados; vistas por turma e professor; diálogo de sumário consultado e cancelado. Geração iniciada acidentalmente e cancelada antes de publicar. A grelha TCO 10 carregou para 12–16/10 após tentativas noutros cursos falharem. | Parcial |
| Faltas e ocorrências | Criar, cancelar na decisão, reverter e reabrir ocorrências; testar duplicate guard, estados, filtros combinados, intervalo invertido e limites exatos (2 000/1 000); confirmar dívida e histórico. Criada e revertida mais uma ocorrência de teste; testada a recomendação com um perfil sintético sem disponibilidade. | Parcial; quatro ocorrências aparecem revertidas, sem pendentes nem dívida nova. A substituição bem-sucedida continua bloqueada por falta de disponibilidade configurada/acesso do professor (F17). Uma aula futura ainda consta como dada. |
| Folhas de horas | Estados, semanas e detalhe de professor consultados; filtros usados. | Leitura; sem submissão/aprovação |
| Importação | CSV sintético de sala validado, commit efetuado, resultado confirmado na lista e sala removida. | Exercitado; limpo |
| Tutorial | Os 13 passos percorridos até “Guia concluído” no modo de demonstração. | Exercitado em simulação |
| Responsividade | Amostras a 375, 768 e 1280 px em dashboard, lista e menu. | Parcial |
| Consola do browser | Nenhum erro ou aviso JavaScript apareceu nos registos consultados. | Verificação limitada |

## Estado dos dados após o ensaio

Os registos de catálogo/importação com o prefixo “QA UI TEST 2026-10-02” foram removidos pelas ações normais da UI, e o CSV local de ensaio foi apagado. Quatro ocorrências sintéticas foram revertidas e aparecem como “Revertida” no histórico; a fila pendente está vazia e não há dívida nova. Uma delas contém um sumário sintético no limite de 2 000 caracteres, preservado no histórico pela reversão. O perfil “Professor QA UI 2026-10-02” continua na organização como professor ativo, sem acesso, com competências de Português e Matemática; não tem convite nem associação de turma. As associações originais de Português e Matemática em TCO 10 foram restauradas. A ocorrência da TAS 10 em 12/10 foi decidida como “Dada” e continua a contar 50 min no progresso de Matemática (0,8 h / 60 h). Não encontrei reversão normal para esse estado, pelo que esse registo sintético também permanece na produção. Os indicadores de catálogo regressaram aos valores observados inicialmente. A geração de horário não publicou uma versão; não houve alteração permanente das associações nem de folha de horas.

## Limitações e próximos testes

- A sessão disponível era de Diretor numa única organização. Convites, permissões de professor, troca de organização e isolamento entre tenants não foram exercitados.
- Os fluxos de ocorrência e decisão foram executados parcialmente. Quatro blocos foram testados sem docente elegível. Foi criado um perfil de professor sem acesso e testada uma associação temporária de disciplina, restaurada no fim; a substituição continuou sem recomendações porque não havia disponibilidade configurada (F17). A sessão de Diretor não permite preencher essa disponibilidade, que depende de sessão de professor. A confirmação de criação cancelada e a repetição após reverter ficaram condicionadas pela falha intermitente da grelha (F15). Submissão/aprovação/reabertura de folha semanal não foi exercitada. O progresso curricular foi alterado pelo registo descrito em F09.
- A Fundação já estava concluída; não se testou uma organização nova ou incompleta.
- Não se induziram falhas de serviço ou rede, concorrência entre utilizadores, limites de recursos ou mudança de hora. A falha intermitente da grelha observada sem indução está descrita em F15.
- A inspeção visual não foi uma auditoria WCAG. A medição pontual corrigida para incluir a opacidade da linha encontrou 3,68:1 no sumário e 1,97:1 no badge “Revertida”, abaixo de 4,5:1 (F16). As restantes páginas e estados não foram medidos sistematicamente; também não houve teste completo por teclado, leitor de ecrã ou zoom.
- Não foram percorridas todas as rotas públicas, aliases, páginas inexistentes, todos os filtros nem todas as combinações dos 154 casos do plano.

Para fechar estes pontos com evidência, é necessário preparar perfis e dados de ensaio controlados (em especial um professor e uma semana operacional de teste) e completar a matriz do plano. Os itens acima são os achados confirmados e a suspeita explicitamente marcada como tal; os restantes pontos estão pendentes, não aprovados.
