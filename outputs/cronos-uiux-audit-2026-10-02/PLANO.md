# Plano de caça ao bug e revisão UI/UX — Cronos

Data: 2 de outubro de 2026. Ambiente principal: `https://cronos.pt`.
Organização principal: **Rodrigo's Organization**. Perfil observado: **Diretor**.
Estado: **auditoria manual executada parcialmente; ver matriz e limitações no resultado abaixo**.

## Objetivo

Testar os percursos disponíveis pela interface. Procurar falhas funcionais, inconsistências entre páginas e fricção de utilização.
Rever também alinhamento, contraste, legibilidade, textos, responsividade e acessibilidade.
Repetir ações em ordens diferentes. Verificar cada transição relevante, incluindo cancelamentos e recuperação de erros.

O objetivo de cobertura é o inventário de rotas, ações, estados e sequências deste plano.
Não equivale a provar ausência de bugs em todas as combinações possíveis.

## Base de conhecimento

Foram lidos os **45 ficheiros Markdown** de `documentation/`.
A leitura inclui os dez subsistemas e os três documentos extensos do scheduler v1.
As referências principais estão no final deste plano.
As rotas foram conferidas em `frontend/src/App.jsx`.
Os formulários, a configuração e o conteúdo do tutorial foram consultados para conferir ações concretas.

O código e os testes definem o comportamento esperado quando a documentação diverge.
A versão publicada pode diferir da cópia local. Uma divergência será registada antes de ser classificada como bug.
Uma afirmação documental sobre testes verdes não prova que a produção atual passa esses testes.

## Contexto inicial observado

A navegação para `/login` redirecionou automaticamente para `/dashboard`, com uma sessão já ativa.
Não foi necessário introduzir credenciais.
O dashboard apresentou 16 cursos, 48 turmas, 52 disciplinas, 46 professores e 48 salas.
Também apresentou um horário com 24 558 blocos e progresso curricular médio de 0%.
Estes valores são contexto inicial. Ainda não foram reconciliados com as páginas de detalhe.

Antes deste plano, foram apenas observados o dashboard e o menu em duas larguras.
Não foram guardadas alterações operacionais nem iniciada uma geração.

## Ambientes e condições

| Código | Ambiente | Utilização |
| --- | --- | --- |
| P | Produção, organização existente | Navegação, leitura, filtros, formulários sem gravação e pré-visualizações sem efeitos. |
| D | Tutorial local em produção | Ações simuladas permitidas nos 13 passos. Não comprova a persistência real. |
| T | Dados próprios de teste | Criação, edição e persistência com nomes identificados. Ações com impacto exigem alvos definidos. |
| A | Sessão alternativa | Professor associado, membro sem administração ou segunda organização acessível. |
| L | Ambiente isolado | Relógio controlado, falhas de infraestrutura, concorrência destrutiva e limites de recursos. |

As ações T podem decorrer na organização existente se os registos forem próprios do ensaio e o impacto estiver identificado.
Não considerar os registos existentes descartáveis por estarem numa organização escolhida para testes.
Uma nova organização só entra no plano se for necessária para testar estados indisponíveis na organização existente.

Aprovação de horário, alteração de progresso, fecho semanal e mudanças de grelha afetam dados operacionais.
Esses casos terão alvos e efeitos identificados antes da ação final.
Remoção permanente e expansão de acesso exigem confirmação no momento aplicável.
Não executar resets, aceitar documentos legais, enviar convites ou alterar credenciais como efeito lateral de exploração.

Se uma condição faltar, registar o caso como bloqueado. Continuar os casos independentes.
Não apresentar uma simulação D como aprovação de um teste real T.

## Modelo funcional que orienta a avaliação

1. A identidade e a organização ativa determinam o membro e as capacidades.
2. A Fundação tem dez passos e precede as funcionalidades operacionais.
3. A preparação tem seis bases cumulativas; a grelha pertence à Fundação.
4. O dashboard torna-se operacional após a primeira aprovação de um horário real.
5. Gerar cria uma proposta. Aprovar publica a versão após nova validação.
6. O servidor escolhe geração inicial ou reparação, conforme a existência de um horário publicado.
7. Sumários e ocorrências registam execução. Recuperação planeada ainda não representa horas cumpridas.
8. O fecho semanal segue `OPEN → SUBMITTED → APPROVED`; reabrir devolve a `OPEN`.
9. O tutorial ensina estes fluxos com dados locais e um ponto de retoma.

## Ordem de execução

| Passagem | Trabalho | Resultado esperado |
| --- | --- | --- |
| 1 | Inventário de produção e registo do contexto | Rotas, controlos, estado inicial e condições dos testes identificados. |
| 2 | Leitura de todas as áreas administrativas | Percursos básicos, filtros, detalhes e relações verificados sem alterações. |
| 3 | Formulários e validações | Campos, mensagens, cancelamentos e sequência de preenchimento avaliados. |
| 4 | Tutorial completo | As 13 etapas e ações simuladas disponíveis exercitadas. |
| 5 | Persistência com registos próprios | Criação e edição verificadas após navegação e atualização da página. |
| 6 | Operações letivas e horários | Fluxos reais disponíveis exercitados com alvos controlados. |
| 7 | Perfis, ordens alternativas e concorrência | Guardas, estado obsoleto e percursos cruzados verificados. |
| 8 | Responsividade e acessibilidade | Problemas transversais conferidos nas páginas e estados relevantes. |
| 9 | Reprodução e relatório | Achados priorizados, evidências e cobertura efetiva publicados. |

A revisão visual acompanha todas as passagens. Não fica limitada à passagem 8.
Um bloqueio funcional não impede avaliar o restante ecrã.

## Inventário de rotas

| Área | Rotas a conferir |
| --- | --- |
| Público | `/`, `/vantagens`, `/como-funciona`, `/sobre`, `/about`, `/ajuda`, `/contacto`, `/contact`. |
| Documentos | `/privacidade`, `/privacy`, `/termos`, `/dpa`, `/cookies`. |
| Acesso | `/login/*`, `/register/*`, `/recuperar-palavra-passe`, `/sign-in/*`, `/sign-up/*`. |
| Inicialização | `/foundation`, `/foundation/waiting`, `/guide`, tarefa Clerk de seleção de organização. |
| Administração | `/dashboard`, `/schedules`, `/absences`, `/timesheets`, `/config`, `/imports`. |
| Catálogos | `/courses`, `/subjects`, `/members`, `/rooms`. |
| Hierarquia | `/courses/:id`, `/courses/:courseId/classes/:classId`, `/courses/:courseId/classes/:classId/subjects`. |
| Professor | `/my-schedules`, `/my-availability`, `/my-progress`. |
| Recuperação de navegação | Rota inexistente, detalhe inexistente, atualização de página e histórico do browser. |

Rotas públicas podem redirecionar utilizadores autenticados. Conferir a mesma rota com o estado de sessão adequado.
Os aliases devem manter o comportamento da rota principal.

## Catálogo de testes

Todos os casos começam como **pendentes**.
Cada resultado terá identificação, ambiente, sequência e evidência.
Os cenários de erro só contam como aprovados se a mensagem e a recuperação forem adequadas.

### Acesso, organização e navegação

| ID | Caso | Resultado esperado | Ambiente |
| --- | --- | --- | --- |
| NAV-01 | Entrar por `/login`, raiz e ligação direta autenticada | Destino consistente com sessão, capacidades e Fundação. | P/A |
| NAV-02 | Visitar uma rota protegida sem sessão | Login acessível e destino de retoma coerente. | A |
| NAV-03 | Abrir, fechar e colapsar o menu; usar teclado | Estado visível, foco previsível e navegação utilizável. | P |
| NAV-04 | Navegar por menu, breadcrumb, botão voltar e browser | Todos chegam ao contexto correto, sem ciclos. | P |
| NAV-05 | Atualizar páginas e detalhes diretamente | Conteúdo carrega; o hosting não devolve um 404 indevido. | P |
| NAV-06 | Abrir uma rota e um identificador inexistentes | Mensagem clara e saída útil. Sem ecrã branco. | P |
| NAV-07 | Abrir conta e conferir seleção de organização | Escola ativa inequívoca e ações disponíveis compreensíveis. | P/A |
| NAV-08 | Alternar organizações e voltar ao mesmo percurso | Listas, seleções e dados correspondem ao tenant atual. | A |
| NAV-09 | Tentar páginas administrativas com professor | Redirecionamento coerente; nenhuma ação administrativa disponível. | A |
| NAV-10 | Tentar páginas docentes sem perfil associado | Acesso tratado; sem dados de outro professor. | P/A |
| NAV-11 | Conferir login, registo e recuperação por teclado | Labels, foco, erros e ligações acessíveis. Parar antes de criar ou alterar credenciais. | A |

### Dashboard

| ID | Caso | Resultado esperado | Ambiente |
| --- | --- | --- | --- |
| DASH-01 | Conferir cursos, turmas, professores, salas e disciplinas | Contagens reconciliadas com listas, filtros e recursos ativos. | P |
| DASH-02 | Filtrar curso e faixa em ambas as ordens | Resultados correspondem à interseção dos filtros. | P |
| DASH-03 | Selecionar uma combinação sem resultados | Estado vazio explícito e filtros recuperáveis. | P |
| DASH-04 | Abrir uma turma a partir do progresso | Curso e turma corretos; regresso previsível. | P |
| DASH-05 | Abrir detalhes de dívida e atenção | Ligação conserva o contexto relevante. | P/D |
| DASH-06 | Conferir saúde e disponibilidade contra grelhas | Métricas identificam unidade, período e significado. | P |
| DASH-07 | Conferir preparação versus operação | Fundação e tutorial não substituem a primeira aprovação real. | T/D |
| DASH-08 | Voltar após uma alteração e após atualização | Dados e estados não permanecem obsoletos. | T |

### Cursos, turmas e plano de estudos

| ID | Caso | Resultado esperado | Ambiente |
| --- | --- | --- | --- |
| CUR-01 | Pesquisa, ordenação e paginação existentes | Dados corretos; combinação de controlos não perde registos. | P |
| CUR-02 | Curso → turma → plano de estudos → voltar | Identidades, breadcrumbs e totais consistentes. | P |
| CUR-03 | Criar curso sem turmas; depois adicionar turma | Gravação coerente e contagens atualizadas. | T |
| CUR-04 | Preparar várias turmas no formulário de curso | Acrescentar, corrigir e remover rascunhos não duplica dados. | P/T |
| CUR-05 | Nome, sigla e turma vazios, duplicados ou com espaços | Normalização e validação claras, sem criação parcial. | P/T |
| CUR-06 | Ano 10/11/12, datas e lotação nos limites | Valores inválidos rejeitados junto do campo afetado. | P/T |
| CUR-07 | Editar cabeçalho; cancelar; reabrir; guardar | Cancelamento preserva original; gravação persiste. | P/T/D |
| CUR-08 | Associar disciplina antes e depois de preparar competências | Opções coerentes; indisponibilidade de professor explicada. | T/D |
| CUR-09 | Atribuir professor e trocar por outro competente | Seletores e totais refletem a atribuição atual. | T/D |
| CUR-10 | Rever remoção de disciplina, turma e curso | Dependências e impacto comunicados antes da ação. | P/T |
| CUR-11 | Conferir currículo, módulos, previsão e progresso | Mesmos minutos e percentagens nos diferentes consumidores. | P/T |
| CUR-12 | Preparar acerto zero, positivo, negativo e excessivo | Limites claros; motivo e efeito contabilístico verificáveis. | P/T |

### Disciplinas e módulos

| ID | Caso | Resultado esperado | Ambiente |
| --- | --- | --- | --- |
| DIS-01 | Conferir pesquisa, ordenação e requisitos de sala | Labels e opções correspondem aos tipos suportados. | P |
| DIS-02 | Preparar disciplina antes e depois de adicionar módulos | O formulário comunica requisitos e conserva o rascunho. | P/T |
| DIS-03 | Acrescentar, editar e retirar módulos em várias ordens | Ordem, nomes e total de horas permanecem corretos. | P/T/D |
| DIS-04 | Horas nulas, negativas, decimais e nos limites | Conservação de minutos e erros coerentes com o contrato atual. | P/T |
| DIS-05 | Nomes e códigos duplicados; texto longo e acentos | Regra explícita, sem truncamento destrutivo. | P/T |
| DIS-06 | Guardar, navegar e reabrir | Módulos e requisito de sala persistem corretamente. | T/D |
| DIS-07 | Rever remoção com associações ou histórico | Bloqueio ou arquivo explicado; histórico preservado. | P/T |
| DIS-08 | Conferir aula que atravessa vários módulos | Parcelas previstas e executadas distinguíveis. | P/D/T |

### Salas

| ID | Caso | Resultado esperado | Ambiente |
| --- | --- | --- | --- |
| SAL-01 | Filtrar e ordenar salas; conferir os quatro tipos | Sem inconsistência entre nome, badge e seletor. | P |
| SAL-02 | Preparar sala normal, laboratório, ginásio e artes | Campos, limites e exemplos compreensíveis. | P/T/D |
| SAL-03 | Nome vazio, duplicado e longo; lotação inválida | Erro específico; sem gravação parcial. | P/T |
| SAL-04 | Guardar, editar, cancelar e reabrir uma sala própria | Dados persistentes e feedback único. | T/D |
| SAL-05 | Conferir compatibilidade de tipo e lotação | Uma sala inadequada não satisfaz a preparação. | T |
| SAL-06 | Rever remoção de sala livre, histórica e ativa | Efeito comunicado; uso ativo bloqueado. | P/T |

### Equipa e disponibilidade

| ID | Caso | Resultado esperado | Ambiente |
| --- | --- | --- | --- |
| EQP-01 | Conferir lista, contagens, capacidades e acesso | Estado docente distingue perfil, acesso e competências. | P |
| EQP-02 | Alternar arquivados e filtros em diferentes ordens | Contagens e resultados consistentes. | P |
| EQP-03 | Preparar membro com diferentes capacidades | Campos e permissões explicados; erros próximos. | P/T |
| EQP-04 | Email inválido, repetido, espaços e capitalização | Validação coerente; não enviar convites durante exploração. | P/T |
| EQP-05 | Editar competências antes e depois da atribuição | Professor elegível apenas para disciplinas compatíveis. | P/T/D |
| EQP-06 | Conferir acesso `scheduler_only` versus plataforma | Sem promessa de login para perfil sem acesso. | P/T |
| EQP-07 | Rever convites, sincronização, remoção e restauração | Ação, efeito e referência de erro compreensíveis. | P/T |
| EQP-08 | Professor abre a própria disponibilidade | Grelha, legenda e horário local coerentes. | A/D |
| EQP-09 | Pintar células por rato e por teclado | Alteração segue a legenda; setas deslocam o foco. | A/D |
| EQP-10 | Alterar, cancelar e reabrir o rascunho | Estado local distingue alterações ainda não guardadas. | A/D |
| EQP-11 | Guardar e atualizar; repetir uma seleção | Persistência correta; ação repetida não duplica efeitos. | A/D/T |
| EQP-12 | Conferir indisponibilidade versus preferência desfavorável | Apenas indisponibilidade obrigatória impede colocação. | D/T |

### Configuração da escola

| ID | Caso | Resultado esperado | Ambiente |
| --- | --- | --- | --- |
| CFG-01 | Alternar os três separadores e voltar | Conteúdo e foco correspondem ao separador selecionado. | P |
| CFG-02 | Conferir início, preferência, limite e estabilidade | Datas locais claras e limites relacionados. | P |
| CFG-03 | Preparar fim anterior ao início e janela fora dos limites | Validação sem alterar configuração ativa. | P/T |
| CFG-04 | Abrir a mudança ou reinício de ano; cancelar | Impacto claro antes da confirmação; cancelamento sem efeitos. | P/T |
| CFG-05 | Preparar evento de cada tipo; inverter datas | Nome, período e erro específicos. | P/T |
| CFG-06 | Pré-visualizar interrupção ou estágio | Aulas afetadas e ausência de impacto identificadas. | P/T |
| CFG-07 | Estágio sem turmas; com uma; com várias | Só estágio admite associação de turmas. | P/T |
| CFG-08 | Editar estágio e cancelar; mudar o tipo do evento | Campos antigos não contaminam o novo payload. | P/T |
| CFG-09 | Conferir feriados automáticos e o estado manual | Período, efeito e ação de gravação compreensíveis. | P/T |
| CFG-10 | Preparar dias, abertura, duração e intervalos inválidos | Uma grelha impossível tem explicação recuperável. | P/T |
| CFG-11 | Preparar almoço parcial, invertido ou demasiado longo | Pausa contínua validada e mostrada na pré-visualização. | P/T |
| CFG-12 | Conferir alteração de grelha com horário publicado | Pré-visualização e aprovação distinguem proposta de grelha ativa. | P/T |

### Importação CSV

| ID | Caso | Resultado esperado | Ambiente |
| --- | --- | --- | --- |
| IMP-01 | Entrar por cada catálogo e pela rota de importação | Secção preselecionada corresponde à origem. | P |
| IMP-02 | Descarregar os cinco modelos | Nome, cabeçalhos, exemplo, BOM e separador oficiais. | P |
| IMP-03 | Verificar sem ficheiros; adicionar e retirar ficheiro | Ações e resultado correspondem aos ficheiros atuais. | P |
| IMP-04 | Verificar ficheiros sintéticos válidos em ordens diferentes | Referências resolvidas no conjunto, sem escrita. | P/T |
| IMP-05 | Vírgula, ponto e vírgula, BOM, acentos e campos entre aspas | Leitura correta segundo o contrato. | P/T |
| IMP-06 | Cabeçalhos incorretos, conteúdo ilegível e números inválidos | Secção, linha, campo e mensagem acionáveis. | P/T |
| IMP-07 | Duplicados locais, existentes e atribuição com professor ausente | Erros coerentes; gravação desativada. | P/T |
| IMP-08 | Substituir ficheiro após validação; descarregar relatório | Resultado anterior invalidado; relatório coincide com os problemas. | P |
| IMP-09 | Confirmar importação sintética e conferir todos os catálogos | Atomicidade e contagens verificadas, sem docentes convidados. | T |
| IMP-10 | Limites de bytes e linhas | Rejeição clara; não executar carga massiva em produção. | L |

### Horários, propostas e geração

| ID | Caso | Resultado esperado | Ambiente |
| --- | --- | --- | --- |
| HOR-01 | Abrir sem seleção; escolher turma e professor | Vazio útil; dados pertencem à seleção atual. | P |
| HOR-02 | Alternar turma/professor e semana em várias ordens | Sem mistura entre filtros, datas ou respostas. | P |
| HOR-03 | Semana anterior, seguinte, atual e limites do ano | Data e conteúdo coerentes; limites compreensíveis. | P |
| HOR-04 | Abrir uma aula e fechar por botão e Escape | Identidade, sala, professor e parcelas corretos; foco devolvido. | P/D |
| HOR-05 | Conferir legenda, almoço, sobreposições e nomes longos | A grelha representa corretamente os dados visíveis. | P |
| HOR-06 | Conferir motivos de geração e pré-validação | Botão e explicações concordam com o servidor. | P/T |
| HOR-07 | Gerar; atualizar; regressar ao estado do pedido | Uma proposta; fases honestas; pedido não se perde. | D/T |
| HOR-08 | Duplo clique e repetição do mesmo pedido | Sem jobs ou efeitos duplicados. | T/L |
| HOR-09 | Abrir proposta e comparar alterações | Mudanças físicas distinguem atualizações modulares. | P/D/T |
| HOR-10 | Conferir datas de conclusão e excesso preferencial | Alertas persistentes; unidade e significado claros. | P/D/T |
| HOR-11 | Cancelar, rejeitar e aprovar nas condições disponíveis | Cada ação tem efeito próprio e confirmação adequada. | D/T |
| HOR-12 | Alterar dados entre pré-validação, geração e aprovação | Proposta obsoleta rejeitada; recuperação explícita. | T/L |
| HOR-13 | Conferir renovação, rejeição e tentativa incompleta | Renovação aos 28 dias; rejeição não cria geração arbitrária. | P/L |
| HOR-14 | Resultado impossível, inconclusivo, cancelado ou falhado | Mensagens distinguem causa, certeza e próxima ação. | D/T/L |

### Sumários, faltas, substituições, dívida e fecho semanal

| ID | Caso | Resultado esperado | Ambiente |
| --- | --- | --- | --- |
| OPE-01 | Abrir sumário passado, atual e futuro | Elegibilidade temporal clara; aula futura não concluída antes do fim. | P/A/D |
| OPE-02 | Resumo e notas vazios, longos e nos limites | Limites de 2 000 e 1 000 caracteres tratados pelo contrato atual. | P/A/T |
| OPE-03 | Guardar conclusão; repetir; corrigir fora de ordem | Crédito único e evidência histórica preservada. | D/T/A |
| OPE-04 | Criar ocorrência e tentar repeti-la | Uma ocorrência ativa; estado coerente nos consumidores. | D/T |
| OPE-05 | Decidir dada, não dada e substituída | Campos dependem da decisão; versão e confirmação verificadas. | D/T |
| OPE-06 | Substituto elegível, inexistente e seleção incompleta | Erro claro; recomendações e pesquisa utilizáveis. | D/T |
| OPE-07 | Rever decisão e cancelar a ocorrência | Histórico e reservas preservados; sem dívida duplicada. | D/T |
| OPE-08 | Alternar pendentes, histórico e dívidas com filtros | Listas e contagens reconciliadas. | P/D/T |
| OPE-09 | Substituição por outra disciplina | Só a disciplina lecionada recebe execução. | D/T |
| OPE-10 | Planear recuperação; aprovar; executar; cancelar | Reserva, cumprimento e dívida permanecem conceitos separados. | D/T |
| OPE-11 | Abrir fecho semanal com professor sem folha persistida | Linha `OPEN` visível; listar não cria um fecho artificial. | P/T |
| OPE-12 | Tentar submeter semana com sumários pendentes ou futuros | Bloqueio acionável com indicação do trabalho em falta. | A/T |
| OPE-13 | Submeter, aprovar, reabrir e tentar editar semana fechada | Transições corretas; fecho impede edição até reabertura. | D/T/A |
| OPE-14 | Do fecho semanal para o horário e regressar | Professor e semana conservados. | P/D |
| OPE-15 | Conferir progresso e dívida em turma, professor e dashboard | Mesmos saldos, minutos e origens após cada transição. | P/D/T/A |

### Fundação e tutorial

| ID | Caso | Resultado esperado | Ambiente |
| --- | --- | --- | --- |
| INI-01 | Conferir organização já concluída e membro não administrador | Sem reinício acidental; guardas coerentes. | P/A |
| INI-02 | Percorrer os dez passos numa organização incompleta | Valores válidos, calendário e grelha corretamente resumidos. | T |
| INI-03 | Introduzir datas, dias, intervalos e almoço inválidos | Avanço bloqueado com erro compreensível. | T |
| INI-04 | Voltar, atualizar e retomar o rascunho | Dados e passo retomados; autosave visível. | T |
| INI-05 | Editar Fundação em duas abas | Conflito recuperável; sem sobrescrita silenciosa. | T |
| INI-06 | Ignorar opcionais; confirmar; tentar completar novamente | Conclusão idempotente e dashboard estável. | T |
| INI-07 | Percorrer todas as 13 etapas do tutorial | Exemplo e instrução correspondem à etapa. | D |
| INI-08 | Experimentar cada ação simulada permitida | Ação funciona no tutorial; dados reais não mudam. | D |
| INI-09 | Sair, retomar, rever passos e repetir o tutorial | Ponto de retoma correto; revisão impede gravações. | D |
| INI-10 | Atualizar durante a demonstração | Mensagem explica que o exemplo é reposto. | D |

### Páginas públicas

| ID | Caso | Resultado esperado | Ambiente |
| --- | --- | --- | --- |
| PUB-01 | Percorrer páginas, aliases, menu e chamadas para ação | Ligações corretas e contexto coerente. | A |
| PUB-02 | Navegar FAQs e documentos legais | Conteúdo legível e navegação funcional; sem aceitação. | P/A |
| PUB-03 | Preencher contacto; voltar; corrigir; validar | Respostas preservadas e erros claros; sem envio externo. | A |
| PUB-04 | Conferir loading, imagens, motion e mobile | Sem saltos impeditivos, cortes ou animação forçada. | A |

## Sequências alternativas obrigatórias

Não basta clicar em cada funcionalidade uma vez.
Repetir os percursos seguintes nos ambientes em que os estados existirem.

| ID | Sequência | Problema procurado |
| --- | --- | --- |
| SEQ-01 | Curso → turma → disciplinas → professor → sala → horário | Dependências normais, contagens e orientação. |
| SEQ-02 | Disciplinas → módulos → sala → competências → curso → atribuição | Dependência artificial da ordem de criação. |
| SEQ-03 | Turma sem professor → horário → voltar → completar atribuição | Recuperação após configuração incompleta. |
| SEQ-04 | Criar → editar → cancelar → editar outro → reabrir o primeiro | Rascunhos e erros contaminados entre registos. |
| SEQ-05 | Validação inválida → fechar → abrir novo formulário → corrigir | Erros antigos, valores antigos e feedback duplicado. |
| SEQ-06 | Filtrar → ordenar → mudar página → trocar filtro → voltar | Resultados e paginação incompatíveis. |
| SEQ-07 | Turma A → semana seguinte → professor B → semana atual → turma C | Seleção e semana obsoletas. |
| SEQ-08 | Verificar CSV → substituir ficheiro → verificar → conferir relatório | Gravação autorizada por uma validação anterior. |
| SEQ-09 | Abrir detalhe → voltar → atualizar → abrir por ligação direta | Dependência do histórico e estado perdido. |
| SEQ-10 | Tutorial → ação simulada → sair → página real → retomar | Confusão entre simulação e operação. |
| SEQ-11 | Ocorrência → substituição → dívida → recuperação → execução | Minutos e reservas contados duas vezes. |
| SEQ-12 | Concluir aula → submeter semana → tentar editar → reabrir → editar | Fecho ignorado ou bloqueio que não se remove. |
| SEQ-13 | Pré-validar → alterar configuração → tentar gerar ou aprovar | Snapshot obsoleto aceite. |
| SEQ-14 | Operação numa aba → mesma ação noutra → atualizar ambas | Concorrência e cache incoerentes. |
| SEQ-15 | Organização A → detalhe → organização B → voltar no browser | Dados do tenant anterior ainda expostos. |
| SEQ-16 | Desktop → modal aberto → mobile → teclado → fechar | Foco perdido, botão inacessível e overflow. |

Para interações comuns, cobrir pares válidos de estado, ordem e largura.
Acrescentar triplos críticos: filtros × paginação × retorno; modal × erro × mobile; semana × professor × fecho.
Não multiplicar casos incompatíveis ou sem significado funcional.

## Verificações UI/UX transversais

Aplicar estas verificações às páginas, formulários, modais, propostas e estados de erro.

| ID | Verificação | Critério |
| --- | --- | --- |
| UX-01 | Alinhamento, espaçamento e hierarquia | Botões, campos, cabeçalhos e badges mantêm uma ordem visual clara. |
| UX-02 | Texto duplicado e feedback | Uma ação produz mensagens necessárias, coerentes e próximas. |
| UX-03 | Linguagem escolar | Unidades e estados compreensíveis; códigos internos não substituem explicações. |
| UX-04 | Descoberta de ações | Criar, editar, importar, voltar e cancelar têm locais previsíveis. |
| UX-05 | Número de interações | Contar ações e mudanças de contexto em tarefas reais; propor simplificação concreta. |
| UX-06 | Contraste de texto | Medir pares reais; alvo 4,5:1 para texto normal e 3:1 para texto grande. |
| UX-07 | Contraste de controlos e estados | Alvo 3:1; cor não é a única forma de transmitir o estado. |
| UX-08 | Teclado e foco | Tab, Shift+Tab, Enter, Espaço, setas e Escape funcionam conforme o controlo. |
| UX-09 | Modal e retorno de foco | Sem fuga de foco; o botão que abriu o modal continua identificável ao fechar. |
| UX-10 | Labels e nome acessível | Inputs, ícones, grelhas e regiões têm descrições específicas. |
| UX-11 | Feedback acessível | Erros anunciados e sucesso compreensível sem deslocação inesperada. |
| UX-12 | Desktop 1440, tablet 768 e mobile 375 | Sem conteúdo essencial cortado; overflow das grelhas fica contido. |
| UX-13 | Texto longo, acentos e zoom | Botões, nomes e mensagens não sobrepõem nem desaparecem. |
| UX-14 | Alvos de interação | Rever controlos pequenos; procurar dimensões próximas de 44 × 44 px. |
| UX-15 | Carregamento, vazio e erro | Estado distinto e próxima ação útil; sem falso sucesso. |
| UX-16 | Alterações pendentes | O utilizador distingue rascunho, gravação, proposta e publicação. |

A avaliação visual de contraste não substitui uma medição.
Se não for possível determinar o fundo efetivo, registar a limitação.
A inspeção da árvore acessível não equivale a um teste completo com leitor de ecrã.

## Limites e condições de cobertura

| Condição | Consequência |
| --- | --- |
| Apenas sessão de Diretor | Fluxos reais exclusivos de professor ficam condicionados à sessão adequada. |
| Fundação concluída | Os dez passos exigem uma organização incompleta própria do ensaio. |
| Sem proposta pendente | Revisão real exige gerar uma proposta com alvos controlados. |
| Sem sumários, ocorrências ou semanas submetidas | Estados reais exigem dados próprios; o tutorial fornece só cobertura simulada. |
| Apenas uma organização acessível | Troca e isolamento observável entre tenants ficam condicionados. |
| Produção em funcionamento | Não induzir falhas de Redis, worker, memória, CPU ou transporte. |
| Renovação de 28 dias e mudança de hora | Fronteiras exatas exigem relógio controlado em L. |

Testes de infraestrutura e campanhas matemáticas C01–C20 não serão executados indiscriminadamente em produção.
O plano reutiliza os seus invariantes para avaliar a UI e as operações disponíveis.
O browser demonstra o comportamento do produto. Não demonstra sozinho toda a integridade da base de dados ou do solver.

## Registo de evidência e defeitos

Cada achado terá:

- ID e prioridade: P0 crítico; P1 alto; P2 moderado; P3 baixo.
- Classificação: bug funcional, problema UI/UX, sugestão ou comportamento por confirmar.
- Rota, largura, perfil e estado inicial.
- Passos exatos e dados mínimos necessários à reprodução.
- Resultado esperado e observado.
- Captura de ecrã e referência de erro, quando disponíveis.
- Frequência de reprodução e impacto no trabalho do utilizador.
- Sugestão concreta, sem assumir uma causa técnica ainda não verificada.
- Relação com outros achados para evitar contar o mesmo problema várias vezes.

Não guardar credenciais, tokens, códigos de autenticação ou ficheiros completos da escola no relatório.
Usar apenas o contexto necessário para reproduzir o problema.
Se uma captura contiver dados pessoais desnecessários, usar uma evidência alternativa.

## Critério de conclusão

Cada caso recebe um estado: **passou**, **falhou**, **bloqueado**, **não aplicável** ou **pendente**.
Registar o ambiente efetivamente usado e distinguir cobertura real de cobertura simulada.
Informar casos executados sobre casos aplicáveis. Listar os bloqueados e justificar os não aplicáveis.
Não declarar cobertura total enquanto existirem casos pendentes ou bloqueados.

Reproduzir os achados com o menor percurso útil antes de fechar o relatório.
Não repetir uma operação de impacto apenas para obter outra captura.
Registar todas as alterações do ensaio e o estado final dos registos próprios.
Não apagar esses registos silenciosamente quando a remoção não tiver recuperação normal.

A auditoria termina com o relatório, a matriz de execução e as evidências disponíveis.
Não inclui correções de código, commits, pushes ou deployments nesta fase.

## Resultado da execução — 2 de outubro de 2026

A sessão cobriu navegação, páginas administrativas, formulários com registos sintéticos, importação CSV, tutorial e amostras responsivas. A matriz detalhada, os achados e os limites estão em [RELATORIO.md](RELATORIO.md). O inventário de 154 casos deste plano foi usado como mapa de cobertura; não foi executado na totalidade nem deve ser interpretado como 154 testes aprovados.

| Área | Resultado observado |
| --- | --- |
| Dashboard, cursos, detalhes, salas, disciplinas e membros | Percursos de leitura, pesquisa/filtros e estados principais exercitados. Curso, turmas, sala e disciplina sintéticos foram criados/alterados/removidos. |
| Importação CSV | Validação sem erros, commit de uma sala sintética, confirmação na lista e remoção concluídos. |
| Configuração escolar | Campos, eventos e modal de intervalos inspecionados; não foram gravadas alterações nem regenerada a grelha. |
| Horários | Semanas e vistas de turma/professor inspecionadas; diálogo de registo aberto e cancelado. Uma geração foi iniciada inadvertidamente ao testar o botão, cancelada e não publicada. A semana 12–16/10 falhou intermitentemente em TAS 10/11, mas carregou para TCO 10; persistem limitações de disponibilidade na organização (F15, F17). |
| Faltas, ocorrências e folhas de horas | Ocorrências futuras criadas/revertidas; “Furo” e “Dada” decididos; quatro tentativas de substituição sem elegíveis, incluindo um professor QA sem sessão e associação temporária a outra disciplina da turma; bloqueio de duplicação no mesmo bloco; cancelar decisão; filtros de data/turma; limites de 2 000/1 000 caracteres; reversões e dívida conferidas. Quatro ocorrências aparecem revertidas, sem pendentes nem dívida nova. A substituição ficou bloqueada pela falta de disponibilidade configurada; F17 regista a limitação da UI e os dados que permanecem. Foram ainda observados overflow da tabela, avisos repetidos, contraste baixo nas linhas revertidas e erro genérico para datas invertidas. Uma aula futura permaneceu concluída com 50 min creditados. Folhas semanais continuam sem submissão/aprovação. |
| Tutorial | Os 13 passos foram percorridos no modo de demonstração. |
| Responsividade e acessibilidade | Amostras a 375, 768 e 1280 px. Sem medição sistemática de contraste, leitor de ecrã ou percurso completo por teclado. |
| Perfis, tenants, infraestrutura e fronteiras temporais | Condicionados por uma sessão de Diretor, uma organização, produção e relógio real. |

Os registos sintéticos de catálogo e importação foram removidos. Quatro ocorrências operacionais foram revertidas e aparecem no histórico; a fila pendente está vazia e não há dívida nova. Uma ocorrência conserva no histórico o sumário sintético de 2 000 caracteres usado para testar o limite. O perfil “Professor QA UI 2026-10-02” permanece como professor ativo sem acesso, sem convite e sem turma associada; as associações temporárias em TCO 10 foram restauradas. Uma aula futura da TAS 10 (Matemática, 12/10/2026 às 09:00) foi marcada como dada e acrescentou 50 minutos ao progresso; não encontrei reversão pela interface e o registo permanece. Os totais de catálogo voltaram aos indicadores de referência. A cobertura remanescente e estes efeitos estão descritos no [RELATORIO.md](RELATORIO.md); os casos pendentes não são considerados aprovados.
## Fontes e rastreabilidade

- [Onboarding](../../documentation/00_getting_started/ONBOARDING.md).
- [Percurso técnico](../../documentation/00_getting_started/TECHNICAL_WALKTHROUGH.md).
- [Modelo de dados](../../documentation/01_system_architecture/DATA_MODEL.md).
- [Domínio profissional](../../documentation/02_domain_model/PROFESSIONAL_EDUCATION.md).
- [Equipa e acesso](../../documentation/02_domain_model/MEMBERS_AND_ACCESS.md).
- [Configuração escolar](../../documentation/02_domain_model/SCHOOL_CONFIGURATION.md).
- [Scheduler: especificação](../../documentation/03_scheduler_engine/SCHEDULER_V1_TECH_SPEC_V2.md).
- [Scheduler: plano](../../documentation/03_scheduler_engine/SCHEDULER_V1_REVAMP_PLAN_V2.md).
- [Scheduler: WBS](../../documentation/03_scheduler_engine/SCHEDULER_V1_WBS_V2.md).
- [Sumários](../../documentation/04_operational_features/LESSON_EXECUTION.md).
- [Ocorrências](../../documentation/04_operational_features/OCCURRENCES_AND_SUBSTITUTIONS.md).
- [Fecho e progresso](../../documentation/04_operational_features/TIMESHEETS_AND_PROGRESS.md).
- [API](../../documentation/05_backend_api/API_REFERENCE.md).
- [Erros e transações](../../documentation/05_backend_api/ERRORS_AND_TRANSACTIONS.md).
- [Remoção de recursos](../../documentation/05_backend_api/RESOURCE_REMOVAL.md).
- [Rotas e permissões](../../documentation/06_frontend_ux/ROUTES_AND_PERMISSIONS.md).
- [Design](../../documentation/06_frontend_ux/DESIGN_SYSTEM.md).
- [Acessibilidade](../../documentation/06_frontend_ux/ACCESSIBILITY.md).
- [CSV](../../documentation/07_data_and_seed/BULK_IMPORT_CSV.md).
- [Segurança](../../documentation/08_security_quality/SECURITY_AND_TENANT_ISOLATION.md).
- [Testes](../../documentation/08_security_quality/TESTING_AND_CI.md).
- [Observabilidade](../../documentation/09_ops_observability/OBSERVABILITY_AND_RECOVERY.md).
- [Norma documental](../../documentation/00_getting_started/DOCUMENTATION_STANDARD.md).
- [Rotas implementadas](../../frontend/src/App.jsx).
- [Configuração implementada](../../frontend/src/pages/SchoolConfig.jsx).
- [Tutorial implementado](../../frontend/src/features/tutorial/tutorialContent.js).
