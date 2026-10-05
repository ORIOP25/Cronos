# Revalidação do Cronos em produção — 5 de outubro de 2026

**Ambiente:** [cronos.pt](https://cronos.pt), sessão existente de Diretor  
**Organização:** Rodrigo's Organization  
**Plano:** [PLANO.md](PLANO.md) · [Relatório inicial](RELATORIO.md) · [Revalidação de 4 de outubro](REVALIDACAO_2026-10-04.md)

## Resultado executivo

**A produção não fica aprovada para declarar pronta.** O painel apresenta um conflito de turma e um conflito de professor. A vista de dívidas diverge do painel depois de reverter uma ocorrência futura de QA.

Confirmei correções em vários percursos. A grelha semanal carregou para dois professores. O formulário de curso guardou a turma inicial. A disponibilidade guardou e manteve o estado neutro após atualização. Estes resultados não compensam os conflitos e a divergência de saldos ainda sem explicação.

Esta passagem foi uma auditoria manual de delta. Não cobre todos os 154 cenários nem substitui testes com perfis de professor, ambiente isolado, relógio controlado ou observabilidade do servidor. Não alterei código, configuração de produção, geração ou publicação de horário.

## Achados que exigem ação

### F21 — A dívida diverge entre páginas após reverter uma aula futura

**Prioridade:** P1 · **Rotas:** `/absences?tab=debts`, `/absences?tab=historical`, `/dashboard`

Reverti pela interface a ocorrência sintética de 12/10/2026, 09:00–09:50, TAS 10, Matemática, Nuno Ramos. O Histórico passou a mostrar “Revertida”. O progresso da turma regressou a 0/420 h e Matemática a 0/60 h.

Depois da reversão, Dívidas de Horas apresentou 2 furos e 1 h 40 min. Incluiu TAS 10/Matemática/Nuno Ramos com 50 min, apesar de a aula ser futura. O outro registo foi TCONT 10/Fiscalidade/Hugo Fernandes, com 50 min. O relatório de 4 de outubro registava apenas esse segundo saldo, totalizando 50 min.

O painel continuou a apresentar 0 h de dívida. Não determinei se a dívida futura resulta da reversão, de outra ocorrência ou de dados calculados em momentos distintos. Reconciliar o livro de ocorrências e os agregados antes de confiar nos saldos.

### F22 — O painel comunica “Tudo controlado” com conflitos no horário

**Prioridade:** P1 · **Rota:** `/dashboard`

Na vista de 5/10/2026, Saúde do Horário mostrou 1 conflito de professor e 1 conflito de turma. O painel de atenção dizia “Tudo controlado” e “Não há intervenções pendentes neste momento”.

Não encontrei nesta sessão uma ligação que identifique os blocos em conflito. A grelha semanal carregou, mas essa vista individual não reconcilia o total global. Identificar os blocos e verificar se o painel deve indicar uma intervenção necessária.

### F23 — Uma rota desconhecida mostra um erro do browser

**Prioridade:** P2 · **Rota:** `/qa-rota-inexistente-2026`

Abrir diretamente essa rota terminou num ecrã de erro do browser (`ERR_HTTP_RESPONSE_CODE_FAILURE`), antes de surgir uma página Cronos com saída útil. Um detalhe inexistente, `/courses/99999999`, mostrou uma mensagem em português e o botão “Voltar aos Cursos”.

O resultado sugere respostas diferentes para um identificador inexistente e uma rota desconhecida. A origem pode estar na configuração de fallback do alojamento. Confirmar com um navegador normal e rever a resposta HTTP antes de classificar a causa.

## Revalidação de defeitos e correções anteriores

| ID | Estado em 5 de outubro | Evidência |
| --- | --- | --- |
| F02 | Explicação confirmada; contagens influenciadas pelo ensaio | O painel explica que inclui 6 turmas arquivadas no horário aprovado. O curso QA desta passagem acrescentou uma turma ativa sem horário. Removê-lo deverá repor a comparação anterior. |
| F08 | Feedback confirmado | Clicar em “Descarregar modelo” mostrou “Transferência iniciada. Verifique a pasta de transferências.” Não inspecionei os bytes ou os cabeçalhos do ficheiro. |
| F09 | Reversão possível; saldo ainda inconsistente | A ação “Reverter” funcionou e preservou o Histórico. O progresso voltou a zero. A dívida passou a incluir o bloco futuro de TAS 10; ver F21. |
| F15 | Não reproduzido nesta passagem | A semana 12–16/10 carregou para Nuno Ramos e Bruno Gomes. Os seletores conservaram professor e semana ao mudar entre ambos. Isto não prova estabilidade em todas as semanas. |
| F17 | Editor administrativo revalidado | A grelha do professor QA carregou com 45 blocos. Gravei um bloco como “Impossível”, voltei a “Neutro”, guardei e atualizei. O estado guardado continuou neutro, sem alterações pendentes. Não concluí uma substituição. |
| F20 | Corrigido em produção | Criei `QA Cronos Prod E2E 2026-10-05` com a turma inicial `QE251005 10`. A confirmação disse “Curso criado.” O detalhe mostrou uma turma. O curso continua na organização até confirmação da remoção. |
| F19 | Mantém-se por revalidar | A limitação móvel da tabela de dívida permanece descrita na revalidação de 4 de outubro. Esta passagem não alterou a largura da janela. |
| F06 | Parcial, sem nova medição | A quebra de linha do botão em tablet/desktop continua descrita na revalidação anterior. |

## Verificações concluídas nesta passagem

| Área | Resultado observado |
| --- | --- |
| Acesso | `/login` redirecionou para `/dashboard` porque já existia uma sessão de Diretor. Não introduzi credenciais. |
| Cursos | A turma inicial foi criada e persistiu no detalhe do curso. O curso sintético está identificado e continua visível no filtro de turmas e no painel. |
| Salas | O catálogo mostrou tipos Normal, Laboratório, Artes e Ginásio. Tentar criar uma sala sem nome foi bloqueado com “Preencha este campo.” |
| Disciplinas | O catálogo mostrou as 52 disciplinas refletidas no painel. Tentar guardar uma disciplina vazia foi bloqueado com “Nome da disciplina é obrigatório.” |
| Configuração | Consultei período, calendário e grelha. O período é 12/10/2026–30/06/2027, com fim preferencial em 04/06/2027. A grelha usa dias úteis, 09:00–18:00, aulas de 50 minutos, intervalos de 10 minutos e almoço 12:00–14:00. Não guardei alterações. |
| Importação CSV | A página descreve cinco modelos, aceita vírgula ou ponto e vírgula e limita cada ficheiro a 1 MB. O modelo de salas iniciou a transferência. Não carreguei ficheiros nem confirmei importações. |
| Fecho semanal | A semana 05–09/10 mostrou 41 professores e nenhuma aula, antes do início letivo configurado. A semana 12–16/10 mostrou 40 aulas pendentes por professor; alguns professores tinham 38. Não submeti nem aprovei folhas. |
| Ocorrências | A fila de decisões pendentes estava vazia. O Histórico mostrou seis registos de QA revertidos e o furo de 23/12/2026 em TCONT 10/Fiscalidade. |
| Rota de detalhe inválida | `/courses/99999999` mostrou “O item pedido já não existe ou não está disponível.” e “Voltar aos Cursos”. |

## Dados e ações de teste

- Reverti a ocorrência sintética de 12/10/2026 em TAS 10/Matemática. A operação preservou o Histórico e removeu o crédito curricular. A dívida resultante exige reconciliação, conforme F21.
- Alterei e restaurei a disponibilidade de segunda-feira às 10:00 do professor `Professor QA UI 2026-10-02`. Após atualização, o bloco continuou “Neutro”. O professor permanece ativo, sem acesso e sem convite.
- Criei o curso `QA Cronos Prod E2E 2026-10-05` e a turma inicial `QE251005 10`. Ainda não os removi. A interface exige remover a turma primeiro; as associações de configuração serão retiradas e o histórico será preservado.
- A transferência do modelo CSV de salas iniciou. O ficheiro descarregado poderá estar na pasta de transferências do browser.
- Não alterei a configuração base, não criei nova geração, não publiquei horários e não enviei convites ou mensagens externas.

## Limitações e decisão para a reunião

A auditoria visual nesta passagem usou a vista desktop e a interface móvel já registada nas passagens anteriores. Não fiz ensaio completo por teclado, leitor de ecrã, zoom, perfil de professor, sessão sem autenticação ou organização alternativa.

Não declare a produção pronta enquanto F21 e F22 não forem reconciliados. F23 merece confirmação numa navegação normal. A remoção do curso QA exige remover primeiro a turma; ambas as confirmações retiram associações de configuração e preservam o histórico. Consulte também o [relatório inicial](RELATORIO.md) e as [revalidações anteriores](REVALIDACAO_2026-10-04.md) para os restantes cenários pendentes.
