# Revalidação do relatório Cronos — 4 de outubro de 2026

**Ambiente:** produção, [cronos.pt](https://cronos.pt)  
**Sessão:** organização Rodrigo's Organization, perfil Diretor  
**Referência:** [plano original](PLANO.md) · [relatório original](RELATORIO.md)

## Resultado

Repeti os percursos centrais do plano na sessão autenticada, incluindo dashboard, horários, faltas/ocorrências, histórico e dívidas, cursos/turmas, membros, configuração, importações, folhas de horas, tutorial e vistas responsivas. Voltei a verificar as correções reportadas e fiz novos ensaios com dados identificados como QA.

Não considero os 154 casos do plano integralmente aprovados: alguns dependem de outra função/perfil, de uma organização de teste limpa ou de um serviço operacional estável. A evidência desta passagem confirma várias correções, mantém problemas importantes de produção e acrescenta um defeito reproduzível no formulário de criação de cursos. A grelha semanal falhou novamente durante a passagem, limitando os cenários operacionais e a substituição.

## Revalidação dos achados anteriores

| ID | Estado nesta passagem | Evidência e observação |
| --- | --- | --- |
| F01 | Não retestado | O estado atual não permitia iniciar uma geração; a página indicava que não havia alterações a aplicar e a ação não estava disponível. Não foi publicada nem iniciada uma nova geração. |
| F02 | Continua presente, causa por confirmar | Dashboard: 54 turmas e 46 professores no horário aprovado; catálogo e seletor de turma continuam a indicar 48 turmas. A diferença do denominador persiste. |
| F03 | Parcialmente confirmado como corrigido | Nova criação do curso sintético terminou em ~0,86 s e criação separada de turma em ~0,67 s. Não reproduziu as demoras de ~24 s/~18 s anteriormente observadas. A edição/gravação de curso não foi medida nesta passagem. |
| F04 | Corrigido | O campo obrigatório vazio em Salas apresentou validação em português (“Preencha este campo.”); nenhum registo foi criado. |
| F05 | Corrigido | A lista de membros mostrou “1 selecionada” e “3 selecionadas”. |
| F06 | Parcialmente corrigido | “Pausa Escolar” está legível por inteiro. “Adicionar evento” ainda quebra em duas linhas em larguras tablet/desktop; em 375 px aparece numa linha. |
| F07 | Corrigido nas vistas verificadas | A matriz de disponibilidade passou a indicar “Deslize horizontalmente para ver todos os dias.” |
| F08 | Inconclusivo | “Descarregar modelo” continuou sem feedback visível e o browser de teste não observou o evento de download em 10 s. Não é possível distinguir falha da aplicação de limitação do browser de teste. |
| F09 | Continua presente; risco P1 | Numa ocorrência futura de 19/10/2026, a opção “Dada” estava disponível no diálogo de decisão, embora o diálogo normal da aula desative a conclusão antes do fim. Não confirmei esta opção nesta passagem. O registo sintético de 12/10, concluído numa passagem anterior, ainda consta no progresso como 0,8 h/60 h; a interface não ofereceu reversão normal. |
| F10 | Corrigido | O Furo existente de 23/12/2026 surge no Histórico como Furo, com ação “Reverter”, e não como decisão pendente. |
| F11 | Corrigido | A dívida mostra “50 min”, sem casas decimais técnicas; o total também é apresentado em minutos. |
| F12 | Corrigido no mobile; tabela desktop continua compacta | No histórico a viewport móvel usa cartões e não tem overflow horizontal de página. A tabela desktop ainda merece atenção à densidade, embora esteja melhor que na primeira passagem. |
| F13 | Não retestado | A grelha semanal voltou a falhar antes de ser possível reabrir o bloco e avaliar os avisos duplicados. |
| F14 | Corrigido | Datas invertidas produziram validação explícita: “A data ‘De’ tem de ser anterior ou igual à data ‘Até’.” A lista ficou vazia sem erro de ligação. |
| F15 | Continua presente; causa por confirmar | A semana 19–23/10 falhou agora também para Nuno Ramos; “Tentar novamente” falhou com novas referências `90C34AFA24E7` e `A1F52D24113C`. A seleção foi preservada. A semana com falha já tinha ocorrido na passagem anterior para 12–16/10. |
| F16 | Corrigido | As cores observadas nas linhas revertidas mediram 4,53:1 para o sumário e 4,64:1 para o badge branco, acima de 4,5:1 para texto normal. |
| F17 | Parcialmente corrigido; substituição bloqueada | “Sem elegíveis” agora explica conflito de horário e oferece “Editar disponibilidade”. Abri o editor administrativo do perfil QA #684 também a 1280 px: continua sem grelha, identifica o docente como “Professor por identificar” e mantém “Guardar disponibilidade” desativado. Não alterei permissões nem convidei o professor. Assim, não foi possível concluir uma substituição bem-sucedida. |
| F18 | Corrigido | Os controlos da turma têm nomes acessíveis específicos: “Abrir turma TCO 10”, “Editar TCO 10” e “Remover TCO 10”. |

## Achados novos e ainda relevantes

### F19 — Tabela de dívidas exige deslocamento horizontal no telemóvel

**Prioridade:** P3 · **Rota:** `/absences?tab=debts`

Na viewport de 451 px, a tabela de dívidas tinha 331 px de área visível e 383 px de conteúdo rolável. A coluna “Horas em Dívida” ficava parcialmente fora da área visível. A página não tinha overflow exterior e a barra horizontal estava visível, mas a comparação de dados exige um gesto adicional.

**Sugestão:** usar cartões no mobile, como já acontece no Histórico, ou fixar um indicador de scroll e a coluna de valor.

### F20 — A criação de curso ignora silenciosamente as “Turmas iniciais” preenchidas

**Prioridade:** P2 · **Rota:** `/courses`

**Reprodução:** criei `QA Revalidacao 2026-10-04` com sigla `QA26` e preenchi a secção “Turmas iniciais” com `QA26 10`, ano 10, início 2026, fim 2029 e 25 alunos. O curso foi criado, mas a lista mostrou “Turmas 0”; o detalhe confirmou “0 disciplinas · 0 turmas” e “Nenhuma turma criada para este curso”. Não apareceu aviso de validação ou de que a turma não tinha sido incluída. A criação pela ação separada “Nova Turma” funcionou em ~0,67 s.

**Impacto:** os campos apresentados como parte da criação são descartados sem explicação, levando a um curso incompleto e a trabalho repetido. O curso e a turma usados no ensaio foram removidos pela interface; a lista voltou às 16 entradas e três turmas por curso.

**Sugestão:** persistir a turma inicial no mesmo fluxo ou retirar/desativar essa secção. Se a turma não puder ser criada, preservar os campos e explicar o erro antes de fechar o formulário.

## Cobertura e estado dos dados

Foram revistos dashboard e filtros, navegação, turmas e cursos, membros, configuração, modelos CSV, folhas de horas, tutorial e as vistas responsivas já indicadas no relatório original. Também foram revistos os estados pendente/histórico/dívida, intervalo de datas, Furo revertível e a decisão “Dada” em aula futura. Não se alteraram atribuições de docentes, configurações de acesso, disponibilidade, folha de horas, horários publicados ou versão de horário nesta passagem.

Criei uma ocorrência sintética futura em 19/10/2026 (TAS 10, Matemática, Nuno Ramos, 09:00–09:50) para verificar as guardas temporais. Reverti-a pela ação normal; desapareceu das pendentes e passou ao histórico como “Revertida”. O total de dívida permaneceu em 50 min, correspondente ao Furo já existente em TCONT 10/Fiscalidade. Criei também um curso e uma turma com prefixo QA e removi ambos. O professor de teste `Professor QA UI 2026-10-02` permanece na organização, ativo, sem acesso à plataforma e sem convite; já existia da passagem anterior.

## Limitações desta revalidação

- Não foi possível voltar a testar geração de horário porque não havia alterações disponíveis para aplicar.
- Não foi possível percorrer criação/reabertura de ocorrência na grelha, a duplicação de avisos ou uma substituição concluída: a semana falhou duas vezes com referências de apoio diferentes. Não alterei o estado de decisão “Dada” para testar.
- A grelha de disponibilidade do professor sintético não carregou em mobile nem em 1280 px; o botão de gravação ficou desativado. Não concedi acesso nem enviei convite.
- O download CSV permanece inconclusivo no browser automatizado.
- A auditoria visual e de contraste é amostral; não é uma certificação WCAG nem cobre todas as combinações dos 154 casos do plano.
- O registo sintético de 12/10/2026 que foi marcado “Dada” na passagem anterior continua a contar 0,8 h no progresso. Não encontrei uma ação de reversão normal e não o alterei.

Para revisão rápida, os pontos que continuam a merecer correção/verificação são F02, F06, F09, F15, F17, F19 e F20. As correções de F04, F05, F07, F10, F11, F14, F16 e F18 foram confirmadas nesta passagem; F03 e F06 melhoraram, mas não ficaram integralmente retestados/corrigidos.
