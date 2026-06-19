# WBS Alpha V1 - Entrega para escola piloto

> STATUS: HISTORICAL / SUPERSEDED FOR SCHEDULER IMPLEMENTATION.
>
> This WBS predates the new schedule generator baseline. Any item mentioning
> repair mode, fixed repair windows, target/preferred end date, or legacy
> scheduler behavior must be ignored or revalidated against:
> - `documentation/03_scheduler_engine/PRD_SCHEDULE_GENERATOR_NEW_BASELINE.md`
> - `documentation/03_scheduler_engine/TECH_SPEC_SCHEDULE_GENERATOR_NEW_BASELINE.md`

## Objetivo
Este WBS define, com detalhe operacional, o que falta implementar para entregar uma Alpha V1 utilizavel por uma escola real.

Foco desta fase:
- gestao de substituicoes;
- ajuste de horarios com correcao de faltas;
- consistencia de progresso/divida;
- estabilidade operacional para piloto.

Fora de escopo nesta fase:
- tracking comportamental de utilizadores;
- analytics comercial avancado;
- monitorizacao enterprise multi-canal.

## Principios obrigatorios
Cada entrega deste WBS deve cumprir SEMPRE os 4 pilares:
1. Otimizacao.
2. Estabilidade.
3. Escalabilidade.
4. Seguranca.

## Criterios de saida da Alpha V1
A Alpha V1 e considerada pronta quando:
1. faltas e substituicoes funcionam end-to-end com historico imutavel;
2. ranking de recomendacao e apresentado e a decisao final e do admin;
3. regra de elegibilidade por turma e respeitada sem excecao;
4. regras hard nao sao violadas apos correcao operacional;
5. repair mode respeita janela fixa por escola;
6. testes criticos (unitarios, integracao e regressao) passam com cobertura dos cenarios obrigatorios;
7. uma escola piloto consegue operar uma semana real sem bloqueio funcional critico.

## WBS detalhado

### 1.0 Regras de negocio nucleares de ocorrencias

#### 1.1 Fechar maquina de estados de ocorrencias
Implementacao:
- formalizar transicoes validas entre estados GAP, GIVEN e SUBSTITUTED;
- garantir que transicoes invalidas devolvem erro explicito;
- impedir alteracao destrutiva de ocorrencias ja executadas sem trilho de auditoria.

Testes obrigatorios:
- transicao valida de evento planeado para GAP;
- transicao valida de evento planeado para SUBSTITUTED;
- tentativa de transicao invalida deve falhar com status adequado;
- tentativa de sobrescrever historico deve falhar.

Edge cases:
- dupla submissao do mesmo evento (idempotencia);
- repeticao de pedido por latencia de rede;
- pedido com estado desconhecido;
- pedido de alteracao de ocorrencia de outro tenant.

#### 1.2 Contabilizacao oficial de progresso e divida
Implementacao:
- aplicar formula oficial definida em documentacao para GIVEN, GAP e SUBSTITUTED;
- atualizar progresso/divida de forma transacional;
- bloquear resultados negativos e percentagens acima de 100 no calculo final.

Testes obrigatorios:
- GIVEN soma horas ao modulo planeado e nao cria divida;
- GAP cria divida e nao soma progresso;
- SUBSTITUTED soma progresso no modulo executado e divida no modulo originalmente planeado;
- recomputo apos multiplas ocorrencias no mesmo modulo.

Edge cases:
- bloco com horas fracionadas;
- modulo com hours_total pequeno e arredondamentos;
- modulo ja com 100% de progresso e nova ocorrencia;
- ocorrencias concorrentes no mesmo modulo.

#### 1.3 Integridade historica e auditoria
Implementacao:
- garantir trilho completo: quem decidiu, quando decidiu, estado final, docente previsto, docente executante;
- nunca apagar historico para ajustar metricas;
- usar transacao atomica para decisao + contabilizacao.

Testes obrigatorios:
- rollback completo quando uma parte da operacao falha;
- leitura de historico consistente apos erro intermedio;
- tentativa de remover ocorrencia historica deve falhar.

Edge cases:
- falha de base de dados apos atualizar parte dos registos;
- timeout entre decisao e persistencia;
- conflitos de concorrencia em escrita simultanea.

### 2.0 Substituicoes assistidas com decisao humana

#### 2.1 Motor de elegibilidade
Implementacao:
- aplicar filtro obrigatorio por tenant;
- permitir apenas docente de outra disciplina da mesma turma afetada;
- bloquear docente da mesma disciplina de turma diferente;
- bloquear docente com conflito de slot;
- validar coerencia com regras hard de professor/turma/sala.

Testes obrigatorios:
- caso valido de substituicao por disciplina diferente da mesma turma;
- caso invalido com docente da mesma disciplina de outra turma;
- caso invalido por conflito de slot;
- caso invalido por tenant diferente.

Edge cases:
- turma sem nenhum docente elegivel;
- todos elegiveis ocupados no mesmo slot;
- alteracao de disponibilidade no meio da decisao;
- docente elegivel desativado durante o fluxo.

#### 2.2 Ranking de recomendacao (abordagem 3 com criterios da abordagem 1)
Implementacao:
- ordenar candidatos por criterios deterministas ja definidos:
  1) menor numero de substituicoes acumuladas na turma no periodo;
  2) menor carga letiva no dia;
  3) maior tempo desde ultima substituicao na turma;
  4) desempate por identificador estavel;
- expor justificativa objetiva por candidato no retorno da recomendacao.

Testes obrigatorios:
- ranking reproduzivel com mesmo input;
- desempate final estavel e previsivel;
- ordenacao correta quando criterios 1 e 2 empatam;
- retorno vazio quando nao ha elegiveis.

Edge cases:
- candidatos sem historico de substituicao;
- diferencas minimas de carga no dia;
- grande numero de elegiveis na mesma turma;
- dados incompletos em um dos candidatos.

#### 2.3 Confirmacao humana do admin
Implementacao:
- frontend apresenta top recomendacoes e motivo;
- admin confirma explicitamente um candidato;
- backend valida novamente elegibilidade no momento da confirmacao (double-check).

Testes obrigatorios:
- confirmacao valida regista SUBSTITUTED com trilho completo;
- candidato deixa de ser elegivel entre sugestao e confirmacao deve falhar com mensagem clara;
- admin sem permissao deve ser bloqueado.

Edge cases:
- duas admins confirmam simultaneamente candidatos diferentes;
- refresh da pagina antes da confirmacao;
- tentativa de confirmar candidato fora da lista elegivel.

### 3.0 Ajuste de horarios com correcao de faltas (repair mode)

#### 3.1 Janela fixa configuravel por escola
Implementacao:
- usar parametro global por organizacao para janela de estabilidade;
- para testes, seed_data define 14 dias (2 semanas);
- em producao, valor e configurado por escola nas configuracoes (onboarding obrigatorio fica para fase posterior);
- bloquear regeneracao dentro da janela.

Testes obrigatorios:
- pedido de regeneracao dentro da janela deve falhar;
- pedido fora da janela deve seguir fluxo normal;
- validacao do limite exato no dia fronteira da janela.

Edge cases:
- mudanca de timezone/dia de horario de verao;
- alteracao da configuracao da janela durante operacao;
- janela nula ou valor invalido.

#### 3.2 Interacao entre repair mode e ocorrencias
Implementacao:
- ocorrencias dentro da janela resolvidas por GAP/GIVEN/SUBSTITUTED, nao por remocao do publicado;
- regeneracao apenas no futuro permitido;
- manter compatibilidade com hard end date.

Testes obrigatorios:
- falta dentro da janela gera ocorrencia sem alterar publicado;
- falta fora da janela permite replaneamento conforme regras;
- tentativa de aula apos hard end date permanece bloqueada.

Edge cases:
- multiplas faltas no mesmo dia e turma;
- falta em ultima semana antes do hard end date;
- evento que exige sala especifica sem alternativa.

### 4.0 API backend e consistencia transacional

#### 4.1 Contratos de API para operacao diaria
Implementacao:
- padronizar endpoints de ocorrencias e substituicoes com requests/responses tipados;
- erros com mensagens operacionais claras para admin;
- documentar status de erro esperados.

Testes obrigatorios:
- validacao de payload invalido;
- autorizacao por role (admin permitido, professor bloqueado nas acoes operacionais);
- cobertura dos principais HTTPException documentados.

Edge cases:
- payload parcial;
- campos extras nao previstos;
- retries de cliente apos erro 5xx.

#### 4.2 Transacoes atomicas e concorrencia
Implementacao:
- agrupar decisao operacional + contabilizacao + auditoria numa transacao unica;
- proteger contra race conditions em confirmacoes simultaneas;
- garantir isolamento por tenant em todas as queries.

Testes obrigatorios:
- simular concorrencia de duas confirmacoes no mesmo evento;
- rollback total em falha forçada no meio da operacao;
- teste de nao vazamento entre tenants.

Edge cases:
- deadlock de base de dados;
- latencia alta em commit;
- leitura stale apos escrita concorrente.

### 5.0 Frontend admin para operacao real

#### 5.1 Painel de ocorrencias
Implementacao:
- listar ocorrencias pendentes e resolvidas;
- mostrar estado atual, docente previsto, candidatos recomendados, decisao final;
- estados claros de loading, erro e empty.

Testes obrigatorios:
- visualizacao correta de lista por tenant;
- feedback claro quando nao ha elegiveis;
- bloqueio de acoes para role professor.

Edge cases:
- trocas de filtros com dados stale;
- perda temporaria de ligacao;
- retorno parcial da API.

#### 5.2 Fluxo de decisao simplificado
Implementacao:
- reduzir passos para confirmar substituicao;
- manter confirmacao explicita para evitar erro humano;
- mostrar justificativa do ranking de forma objetiva.

Testes obrigatorios:
- tempo medio de conclusao do fluxo (benchmark interno);
- validacao de confirmacao com candidato invalido;
- reacao da UI a erro transacional backend.

Edge cases:
- confirmacao em duplicado por click rapido;
- refresh apos sugestao e antes da confirmacao;
- conflito detectado apos abertura da modal.

### 6.0 Dados, seeds e cenarios de validacao

#### 6.1 Seeds para cenarios operacionais
Implementacao:
- criar cenarios baseline com faltas reais e multiplos elegiveis;
- incluir ao menos dois tenants para validar isolamento;
- incluir cenarios sem elegivel para validar fallback GAP.

Testes obrigatorios:
- reproduzir os cenarios em ambiente local e CI;
- validar consistencia dos resultados em execucoes repetidas.

Edge cases:
- dados incompletos de docente;
- calendario com feriados e indisponibilidades combinadas;
- turmas com distribuicoes de carga muito diferentes.

### 7.0 Qualidade, seguranca e release alpha

#### 7.1 Suite minima de regressao
Implementacao:
- consolidar bateria de testes criticos da alpha;
- garantir que alteracoes de ocorrencias nao quebram hard constraints;
- manter testes focados por organizacao como default.

Testes obrigatorios:
- regressao funcional de geracao base;
- regressao de ocorrencias e substituicoes;
- regressao de autorizacao e tenant isolation.

Edge cases:
- combinacao de reparacao + falta + substituicao no mesmo periodo;
- operacao perto do hard end date;
- rollback apos erro inesperado.

#### 7.2 Go/no-go para escola piloto
Implementacao:
- checklist de readiness tecnica e funcional;
- plano de suporte reativo durante piloto;
- plano de recolha de feedback funcional do admin da escola.

Testes obrigatorios:
- teste de uma semana operacional simulada;
- teste de carga moderada em horario critico de operacao;
- validacao final de trilho de auditoria.

Edge cases:
- escola piloto com regras de disponibilidade muito restritivas;
- semana com faltas acima do normal;
- alteracoes operacionais em cima da hora.

## Plano de testes por nivel

### A. Unitarios
- regras de elegibilidade;
- ranking deterministico;
- formula de progresso/divida;
- validacoes de janela de repair mode.

### B. Integracao
- endpoint de ocorrencia com persistencia real;
- endpoint de recomendacao + confirmacao;
- transacoes atomicas e rollback;
- isolamento por tenant.

### C. End-to-end funcional (admin)
- registar falta;
- receber recomendacao;
- confirmar substituicao;
- verificar impacto em progresso/divida;
- verificar historico e estado final.

### D. Regressao hard constraints
- sem conflito professor/turma/sala;
- sem aula apos hard end date;
- sem violacao de tipo de sala;
- sem vazamento entre organizacoes.

## Riscos principais e mitigacoes

1. Risco: conflito entre recomendacao e estado real no momento da confirmacao.
Mitigacao: revalidacao obrigatoria no backend no instante da confirmacao.

2. Risco: regressao no calculo de progresso/divida.
Mitigacao: testes unitarios dedicados + snapshots de casos canonicos.

3. Risco: quebra de tenant isolation em queries novas.
Mitigacao: checklist de seguranca por PR + testes multi-tenant obrigatorios.

4. Risco: complexidade excessiva no frontend da decisao.
Mitigacao: fluxo curto com texto objetivo e justificativa clara.

## Entregaveis documentais obrigatorios por pacote

Para cada pacote concluido, atualizar:
1. documentacao funcional impactada;
2. regras de negocio impactadas;
3. evidencias de testes executados;
4. confirmacao explicita de que nao existem pontos em aberto no escopo Alpha V1.

## Confirmacoes necessarias contigo (fechadas)

Confirmacao fechada:
- Janela fixa de 2 semanas e apenas valor de testes no seed; em producao e configuracao por escola.
- Ranking de recomendacao usa periodo baseado na janela de repair mode (Opcao C).
- Escopo do piloto: 1 organizacao real (a escola piloto), sem limite artificial de turmas/disciplina para testes; a escola deve poder usar cenarios reais em escala.

### Detalhe da opcao 1 (periodo para contagem de substituicoes)

Opcao A - Semanal:
- Como funciona: o contador reinicia todas as semanas (segunda a domingo).
- Exemplo pratico: professor B substituiu 2 vezes esta semana e professor D substituiu 0 vezes; na proxima decisao, D sobe no ranking.
- Vantagem: resposta rapida a desbalanceamentos curtos.
- Risco: pode ignorar acumulado historico do mes.

Opcao B - Mensal:
- Como funciona: o contador reinicia no inicio de cada mes civil.
- Exemplo pratico: durante abril, professor B acumulou 6 substituicoes e professor D 2; o ranking favorece D ate equilibrar no proprio mes.
- Vantagem: distribuicao mais estavel ao longo de um ciclo administrativo comum.
- Risco: menos sensivel a picos semanais.

Opcao C - Janela de repair mode:
- Como funciona: o contador considera apenas o intervalo definido em repair_stability_window_days.
- Exemplo pratico: com janela de 14 dias para testes, o ranking usa apenas substituicoes ocorridas nos ultimos 14 dias.
- Vantagem: coerencia total com a logica temporal de estabilidade do sistema.
- Risco: comportamento muda quando a escola altera a janela.

### Escopo inicial do piloto (decisao final)

Definicao simples de "piloto":
- Piloto e uma fase de teste real com uma escola real, antes de venda ampla.
- Nao significa que o sistema cria automaticamente uma turma de teste quando alguem cria conta.
- Significa operar em contexto real com recolha estruturada de feedback e correcao continua.

Decisao final para esta alpha:
- Manter 1 organizacao piloto (uma escola real) com liberdade total para configurar as turmas e disciplinas necessarias para os testes reais (ex.: 20-30+ turmas).
- Nao impor limite tecnico artificial de 1-2 ou 3-4 turmas durante o piloto.
- Controlar risco por operacao (triagem diaria, prioridade por impacto e checklist go/no-go), e nao por bloqueio de escala funcional.

Impacto operacional da decisao:
- Otimizacao: feedback mais representativo da operacao real da escola.
- Estabilidade: suporte orientado por prioridade critica e regressao diaria.
- Escalabilidade: validacao precoce com volume real de turmas e disciplinas.
- Seguranca: mantem-se obrigatorio o cumprimento de tenant isolation, auditoria e hard constraints em toda a escala.

Historico de alternativas consideradas e nao adotadas:

Opcao A - 1 organizacao, 1-2 turmas:
- Exemplo pratico: uma escola real usa a app com 1 ou 2 turmas reais durante 2-3 semanas.
- Nao ha criacao automatica obrigatoria de "turma de teste" no registo.
- Vantagem: risco operacional muito baixo e correcoes rapidas.
- Risco: feedback menos representativo de escala real.

Opcao B - 1 organizacao, 3-4 turmas:
- Exemplo pratico: incluir um curso completo (10o, 11o, 12o) e uma turma adicional.
- Vantagem: valida melhor conflitos reais de professores/salas.
- Risco: maior carga de suporte no arranque.

Opcao C - 2 organizacoes pequenas em paralelo:
- Exemplo pratico: 2 escolas com 1-2 turmas cada, em paralelo.
- Vantagem: valida cedo isolamento multi-tenant em contexto real.
- Risco: complexidade de acompanhamento cresce bastante na alpha.

## Revisao final de prontidao (fechada)

## Estado de execucao tecnica (atualizacao 2026-04-11)

Status por pacote WBS:
- 1.0 concluido (maquina de estados, contabilizacao, auditoria imutavel).
- 2.0 concluido (elegibilidade, ranking deterministico, confirmacao humana com revalidacao backend).
- 3.0 concluido (janela fixa por escola, repair mode compativel com hard end date).
- 4.0 concluido (contratos API tipados, transacao atomica e cobertura de concorrencia).
- 5.0 parcial (painel admin de ocorrencias entregue, mas sem fluxo end-to-end iniciado no bloco da grelha semanal e sem criacao guiada de ocorrencia futura).
- 6.0 concluido (seed operacional deterministico com 2 tenants e cenarios multi-elegivel/sem elegivel).
- 7.0 concluido (suite minima de regressao alpha + pacote go/no-go piloto).

Evidencias de validacao executadas:
- backend regressao completa: `211 passed`.
- frontend regressao completa: `34 passed`.
- suite dedicada passo 6: `2 passed`.
- suite dedicada passo 7 (alpha release gate): `6 passed`.

Nota de escopo:
- o piloto funcional continua fechado para 1 organizacao real em escala real;
- os cenarios multi-tenant do passo 6 sao para validacao tecnica de isolamento e nao alteram o escopo comercial do piloto.

Estado atual para implementacao da Alpha V1:
- sem decisoes de negocio em aberto no escopo desta versao;
- regras de faltas/substituicoes, repair mode, tenant isolation e hard constraints documentadas;
- escopo de piloto fechado para 1 escola real em escala real (sem limite artificial de turmas);
- criterios minimos de validacao, risco e gate de release definidos.

Conclusao:
- plano pronto para implementacao tecnica por pacotes do WBS.

## Atualizacao de conformidade (2026-04-12)

### Confirmacao factual do estado atual

O sistema tem interatividade parcial para ocorrencias/substituicoes, mas ainda nao cumpre o workflow operacional completo solicitado para Alpha:

- existe pagina dedicada de faltas/ocorrencias com acao de decisao (`Decidir`) por ocorrencia existente;
- existe ranking e confirmacao de substituicao por `occurrence_id`;
- nao existe interacao direta na grelha semanal para abrir o fluxo de falta/substituicao ao clicar no bloco;
- nao existe endpoint dedicado para criar ocorrencia operacional a partir de um bloco futuro;
- a criacao automatica de ocorrencias GIVEN ocorre por tarefa diaria as 23:59, o que nao cobre falta comunicada antes da aula.

Impacto direto:
- o admin consegue decidir quando a ocorrencia ja existe;
- o admin nao consegue iniciar o workflow completo exatamente no ponto onde opera (bloco do horario), que e o comportamento alvo do piloto.

### 5 Ws do gap de interatividade

What:
- falta o fluxo UI/API "bloco semanal -> abrir acao operacional -> criar/decidir ocorrencia -> refletir resultado no proprio bloco e nas visoes dos envolvidos".

Who:
- admin: principal impactado (nao consegue iniciar operacao no bloco).
- professores: impactados na visibilidade rapida da alteracao apos decisao.

Where:
- camada Interface (grelha semanal), camada Regras de negocio (orquestracao de criacao/decisao), camada Base de dados (vinculo seguro ao ScheduleOutput futuro).

When:
- no momento operacional em que a falta e comunicada, antes da aula ocorrer.

Why:
- sem este fluxo, a Alpha nao entrega a experiencia operacional premium prometida para escola piloto em escala real.

## WBS Delta para concluir a feature (sem alterar escopo de dominio)

### 8.0 Interface (camada Interface)

#### 8.1 Acao operacional no bloco da grelha semanal
Implementacao:
- tornar cada bloco elegivel da grelha semanal acionavel para admin;
- abrir modal contextual com dados do bloco (turma, disciplina, docente previsto, data, slot);
- expor acao explicita: "Criar Ocorrencia";
- apos criacao, encaminhar para a pagina de faltas para triagem/decisao detalhada.

Testes obrigatorios:
- click no bloco abre modal correta para admin;
- acao "Criar Ocorrencia" gera ocorrencia unica vinculada ao bloco;
- professor permanece em modo leitura sem acao operacional;
- bloco sem contexto valido mostra erro orientado ao utilizador.

Edge cases:
- click repetido rapido no mesmo bloco;
- abertura de modal com dados stale apos refresh parcial;
- tentativa de acao em bloco bloqueado por janela/configuracao.

#### 8.2 Top 3 recomendacoes no momento da decisao
Implementacao:
- na pagina de faltas, ao escolher "Substituicao", mostrar ranking limitado ao top 3 com justificativa curta;
- permitir expandir para lista completa apenas quando necessario;
- manter confirmacao explicita de decisao final.

Testes obrigatorios:
- ordem deterministica mantida no top 3;
- fallback para GAP quando nao ha elegiveis;
- mensagem de conflito superveniente refletida na UI sem ocultacao.

Edge cases:
- menos de 3 elegiveis;
- empate total nos criterios de ranking;
- candidato deixa de ser elegivel entre abertura e confirmacao.

#### 8.3 Reflexo imediato nas visoes relevantes
Implementacao:
- apos confirmacao, atualizar o proprio bloco na grelha semanal;
- refletir alteracao na pagina de ocorrencias, na vista por professor e na vista por turma;
- invalidar caches React Query de forma granular (sem refresh total da app).

Testes obrigatorios:
- admin ve o novo estado no bloco sem recarregar pagina;
- professor previsto e professor substituto veem alteracao na semana certa;
- turma envolvida ve alteracao coerente no mesmo contexto temporal;
- sem ghost state ao alternar entre vista turma/professor.

Edge cases:
- mudanca de semana imediatamente apos confirmacao;
- rede instavel com retries;
- duas sessoes admin abertas em paralelo.

Estado de execucao (2026-04-12):
- 8.1 implementado: bloco semanal acionavel para admin com modal contextual e acao Criar Ocorrencia;
- 8.2 implementado: decisao em faltas com top 3 por defeito e opcao de expandir lista completa;
- 8.3 implementado: invalidacao granular de cache para refletir alteracoes em grelha semanal e vistas relacionadas.

### 9.0 Regras de negocio (camada Regras de negocio)

#### 9.1 Comando unico de operacao por bloco
Implementacao:
- introduzir comando de aplicacao orientado a bloco (`schedule_output_id` + acao=CREATE_OCCURRENCE);
- garantir que este comando apenas cria/reusa ocorrencia e nao decide estado final;
- manter decisao final (GAP/SUBSTITUTED/GIVEN) na pagina de faltas via fluxo de ocorrencias ja existente;
- preservar maquina de estados existente (GIVEN/GAP/SUBSTITUTED) sem atalho inseguro.

Testes obrigatorios:
- bloco futuro com falta comunicada permite criar ocorrencia e encaminhar para decisao com seguranca;
- bloco passado continua compativel com fluxo atual de ocorrencias;
- resposta de erro padronizada para conflito, elegibilidade e permissao.

Edge cases:
- acao em bloco removido por regeneracao concorrente;
- tentativa de criar ocorrencia duplicada para o mesmo bloco/data;
- tentativa cross-tenant por manipulacao de id.

#### 9.2 Coerencia entre workflow novo e contratos atuais
Implementacao:
- mapear fluxo novo para os contratos ja existentes de recomendacao e update;
- garantir backward compatibility da pagina de ocorrencias atual;
- manter idempotencia e lock transacional para evitar dupla contabilizacao.

Testes obrigatorios:
- chamadas antigas continuam funcionais;
- nova orquestracao nao duplica ocorrencias;
- race condition entre dois admins bloqueada com erro deterministico.

Edge cases:
- retry automatico do frontend apos timeout;
- confirmacao duplicada com payload identico;
- confirmacao concorrente com payload diferente.

Estado de execucao (2026-04-12):
- 9.1 implementado: comando de bloco formalizado com `action=CREATE_OCCURRENCE` + `schedule_output_id`, limitado a criar/reusar ocorrencia;
- 9.2 implementado: fluxo novo validado com contratos existentes de recomendacao (`GET`) e decisao (`PATCH`) sem duplicar ocorrencias/accounting;
- concorrencia e idempotencia validadas para criacao e decisao, com comportamento deterministico sob race condition.

### 10.0 Base de dados (camada Base de dados)

#### 10.1 Registo operacional iniciado por bloco futuro
Implementacao:
- suportar criacao controlada de ocorrencia vinculada ao bloco alvo quando ainda nao existir registro;
- manter unicidade e imutabilidade conforme invariantes atuais;
- garantir que decisao + contabilizacao permanecem atomicas.

Testes obrigatorios:
- criar e decidir ocorrencia para bloco futuro no mesmo fluxo;
- impedir duplicacao para o mesmo bloco/data;
- rollback completo em erro intermedio.

Edge cases:
- bloco com ocorrencia ja existente no momento do commit;
- indisponibilidade temporaria de BD durante a transacao;
- latencia de escrita elevada sob carga moderada.

#### 10.2 Observabilidade minima para piloto
Implementacao:
- registrar evento operacional com actor, bloco, decisao e resultado;
- disponibilizar contadores basicos por organizacao (decisoes, falhas de validacao, conflitos);
- manter trilho auditavel sem dados sensiveis em excesso.

Testes obrigatorios:
- log emitido em sucesso e em falha de negocio;
- correlacao de evento com occurrence_id/schedule_output_id;
- sem vazamento de dados entre tenants nos eventos.

Edge cases:
- alto volume de operacoes no mesmo periodo;
- erro no emissor de log sem comprometer transacao principal;
- retries de observabilidade nao podem reexecutar decisao de negocio.

Estado de execucao (2026-04-12):
- 10.1 implementado: criacao controlada por bloco, unicidade por (`schedule_output_id`, `date`) e fluxo criar+decidir validado em testes;
- 10.2 implementado: trilho de observabilidade operacional persistido por tenant com correlacao `occurrence_id`/`schedule_output_id`;
- contadores basicos por organizacao expostos em endpoint admin (`/occurrences/observability/summary`);
- emissao de evento operacional em sucesso/falha com modo seguro (falha de emissor nao bloqueia operacao principal).

## Criterio de saida revisado para "feature completa"

A feature de faltas/substituicoes so deve ser marcada como concluida quando os 5 pontos abaixo estiverem verdadeiros em producao piloto:

1. admin inicia o fluxo diretamente no bloco da grelha semanal.
2. sistema apresenta ate 3 recomendacoes principais com justificativa objetiva.
3. admin confirma substituicao e a alteracao reflete no bloco e nas visoes dos docentes envolvidos.
4. contabilizacao e auditoria permanecem consistentes com a regra oficial GIVEN/GAP/SUBSTITUTED.
5. testes de regressao de UI + API + concorrencia passam para o novo workflow.

## Notas de prioridade

Prioridade imediata para fechar Alpha:
1. 8.1 + 9.1 + 10.1 (fluxo operacional minimo end-to-end).
2. 8.2 + 8.3 (usabilidade premium e reflexo imediato).
3. 10.2 (observabilidade operacional para piloto real).

Regra de arranque de implementacao:
- a execucao funcional comeca no ponto 8 (Interface), em paralelo com 9 e 10 para fechar verticalmente o workflow;
- os pontos 11 a 15 sao plano tecnico de garantia, compatibilidade e criterios de pronto para executar 8-10 sem ambiguidade.

Item "a definir" (nao bloquear implementacao inicial):
- formato exato da acao no bloco (click simples vs botao contextual) conforme teste de usabilidade com admin da escola piloto.

## Plano tecnico de implementacao e compatibilidade total (verificacao reexecutada 2026-04-12)

### 11.0 Registo factual revalidado (sem assumir)

Factos confirmados em codigo (legacy + atual):
1. A API publica expone simultaneamente os routers `/substitutions` e `/occurrences`.
  Evidencia: `backend/app/api/api.py`.
2. O dominio de ocorrencias atualmente exposto possui criacao operacional por bloco (`POST /occurrences`), listagem, detalhe, decisao (`PATCH`) e resumo de observabilidade.
  Evidencia: `backend/app/api/v1/endpoints/occurrences.py` e `backend/app/schemas.py`.
3. O nascimento automatico de ocorrencias GIVEN esta ativo por tarefa diaria as 23:59.
  Evidencia: `backend/app/celery_worker.py` e `backend/app/services/occurrence_service.py`.
4. O payload semanal retorna `schedule_output_id`, `occurrence_status`, `hours_given` e os campos operacionais additive (`occurrence_id`, `occurrence_decided_at`, `can_create_occurrence`, `can_decide_occurrence`).
  Evidencia: `backend/app/services/schedule_service.py`.
5. A grelha semanal inicia fluxo operacional por clique no bloco para admin, abre modal contextual e permite criar ocorrencia com navegacao para faltas.
  Evidencia: `frontend/src/components/WeekGrid.jsx`, `frontend/src/pages/Schedules.jsx` e `frontend/src/hooks/useSchoolData.js`.
6. A pagina de faltas decide ocorrencias existentes com ranking por `occurrence_id`, top 3 por defeito e opcao de expandir lista completa.
  Evidencia: `frontend/src/pages/Occurrences.jsx` e `frontend/src/hooks/useSchoolData.js`.
7. Endpoints e servico legacy de substituicoes continuam ativos e gravam na tabela `substitutions`.
  Evidencia: `backend/app/api/v1/endpoints/substitutions.py` e `backend/app/services/substitution_service.py`.
8. Artefactos legacy no frontend existem, mas estao orfaos de uso no fluxo principal atual.
  Evidencia: `frontend/src/components/ReplacementModal.jsx` e hooks declarados sem consumidores.
9. Regressao focada dos pontos 8-13 esta verde em backend e frontend.
  Evidencia: `backend/tests/test_occurrences.py` (cenarios create/idempotencia/compatibilidade/payload semanal) e `frontend/src/test/WeekGrid.test.jsx` + `frontend/src/test/Schedules.test.jsx` + `frontend/src/test/Occurrences.test.jsx` (10 passed).

Conclusao factual:
- a lacuna bloqueante de criacao operacional por bloco foi fechada nos pontos 8-10;
- coexistencia legacy + atual permanece controlada por adaptador, com consolidacao tecnica ate ao ponto 13 e base pronta para fechamento formal do ponto 14.

Estado do ponto 11 (2026-04-12):
- concluido com revalidacao factual pos 8-10 e sem divergencias criticas entre codigo, testes e documentacao canonica.

### 12.0 Contrato de compatibilidade "100% Alpha"

Objetivo de compatibilidade desta entrega:
1. Nenhuma quebra no fluxo atual de ocorrencias (pagina de faltas).
2. Nenhuma quebra de contrato para clientes/rotas legacy de `substitutions` durante Alpha.
3. Fonte de verdade funcional passa a ser `LessonOccurrence` para operacao diaria.
4. Tenant isolation, autorizacao e contabilizacao continuam deterministicas.

Regras de compatibilidade obrigatorias:
1. Mudancas de contrato devem ser additive-first (sem remover campos/rotas existentes na mesma entrega).
2. Campos novos em respostas devem ser opcionais no frontend ate adocao completa.
3. Endpoints legacy devem manter shape de resposta esperado durante fase de coexistencia.
4. Fluxo novo nao pode duplicar registos ou accounting quando coexistir com chamadas legacy.

Matriz de compatibilidade (alvo de implementacao):
1. `POST /api/v1/occurrences` (ativo): cria ocorrencia operacional por bloco.
2. `PATCH /api/v1/occurrences/{id}` (existente): continua como etapa de decisao final.
3. `GET /api/v1/occurrences/*` (existente): sem quebra.
4. `GET/POST /api/v1/substitutions*` (legacy): mantidos por adaptador de compatibilidade na Alpha.

Estado de execucao (2026-04-12):
- compatibilidade legacy/new ativa: `POST /api/v1/substitutions/` passou a orquestrar internamente o fluxo canónico de `LessonOccurrence`;
- resposta legacy (`SubstitutionResponse`) preservada para clientes existentes;
- escrita em `substitutions` mantida de forma idempotente para consultas legacy durante coexistencia;
- validado que chamadas legacy e novas convergem para estado final consistente sem duplicar accounting em retries identicos;
- sem regressao detectada no gate de auth/tenant do pacote Alpha.

### 13.0 WBS tecnico detalhado para implementacao

#### 13.1 Pacote A - Contrato API de criacao por bloco (Interface)

Objetivo:
- permitir inicio do fluxo no bloco da grelha semanal sem decidir estado final no mesmo passo.

Contrato alvo (fechado para implementacao):
1. Rota: `POST /api/v1/occurrences`.
2. Request minimo:
  - `schedule_output_id` (obrigatorio);
  - `mode` (opcional, default `manual_admin`);
  - `reason` (opcional, texto curto de contexto operacional).
3. Semantica:
  - cria ocorrencia vinculada ao bloco quando inexistente;
  - se ja existir para bloco/data, retorna a existente (idempotencia).
4. Response:
  - `201` quando criou;
  - `200` quando reutilizou existente;
  - payload inclui `id`, `schedule_output_id`, `date`, `status`, `decided_at`.
5. Erros:
  - `404` bloco inexistente ou fora do tenant;
  - `409` bloco sem contexto operacional valido para criacao;
  - `422` payload invalido.

Ficheiros-alvo provaveis:
1. `backend/app/api/v1/endpoints/occurrences.py`.
2. `backend/app/schemas.py`.
3. `documentation/05_backend_api/ENDPOINT_STANDARDS.md`.

Testes obrigatorios:
1. cria ocorrencia nova por bloco futuro valido (`201`).
2. chamada repetida no mesmo bloco retorna mesma ocorrencia (`200`, sem duplicar).
3. bloqueio cross-tenant (`404`).
4. payload invalido (`422`).

#### 13.2 Pacote B - Servico de orquestracao de criacao (Regras de negocio)

Objetivo:
- encapsular criacao idempotente, auditavel e sem contabilizacao prematura.

Regras tecnicas:
1. Criacao nao altera progresso/divida.
2. Accounting continua concentrado no `PATCH` de decisao.
3. Ocorrencia inicial deve entrar em estado "pendente de decisao" (controlado por `decided_at = null`).
4. Estado inicial operacional deve manter compatibilidade com maquina existente (sem criar novo enum na Alpha).

Decisao tecnica para Alpha:
1. manter estados `GIVEN|GAP|SUBSTITUTED`;
2. representacao de pendencia por `decided_at = null`.

Ficheiros-alvo provaveis:
1. `backend/app/services/occurrence_service.py`.
2. `backend/app/services/schedule_service.py` (helpers de contexto por bloco, se necessario).

Testes obrigatorios:
1. criacao manual nao altera ClassProgress.
2. `PATCH` posterior aplica accounting exatamente uma vez.
3. concorrencia de criacao no mesmo bloco nao gera duplicado.

#### 13.3 Pacote C - Enriquecimento do contrato semanal para interatividade (Interface + Dados)

Objetivo:
- permitir que a UI saiba se um bloco pode criar ocorrencia e/ou abrir ocorrencia existente.

Mudancas additive no payload semanal:
1. `occurrence_id` (nullable).
2. `occurrence_decided_at` (nullable).
3. `can_create_occurrence` (bool).
4. `can_decide_occurrence` (bool).

Regra de compatibilidade:
- campos antigos mantidos sem alteracao;
- consumidores antigos continuam funcionais.

Ficheiros-alvo provaveis:
1. `backend/app/schemas.py` (`WeekSlotRead`).
2. `backend/app/services/schedule_service.py` (`_build_week_slot`).
3. `backend/app/api/v1/endpoints/schedule.py` (se validacoes adicionais forem necessarias).

Testes obrigatorios:
1. payload semanal inclui novos campos sem remover antigos.
2. `occurrence_id` presente quando existir ocorrencia para o bloco.
3. `can_create_occurrence` falso quando ocorrencia ja existir.

#### 13.4 Pacote D - Interacao no bloco da grelha semanal (Frontend)

Objetivo:
- iniciar operacao diretamente no bloco conforme workflow aprovado.

Implementacao tecnica:
1. tornar celula de bloco acionavel para admin.
2. abrir modal contextual no `Schedules` com acoes:
  - Criar Ocorrencia;
  - Ir para Faltas (com foco na ocorrencia, quando ja existir).
3. criar hook `useCreateOccurrence` no `useSchoolData`.
4. invalidar queries relevantes (`weekSchedule`, `occurrences`, `debts`) apos sucesso.

Ficheiros-alvo provaveis:
1. `frontend/src/components/WeekGrid.jsx`.
2. `frontend/src/pages/Schedules.jsx`.
3. `frontend/src/hooks/useSchoolData.js`.

Testes obrigatorios:
1. admin consegue criar ocorrencia a partir do bloco.
2. professor nao ve acao operacional.
3. erro API de criacao aparece com mensagem operacional clara.

#### 13.5 Pacote E - Orquestracao com pagina de faltas (Frontend)

Objetivo:
- manter pagina de faltas como centro de triagem em escala, com entrada rapida pela grelha.

Implementacao tecnica:
1. navegar para `/absences` com query params de contexto (`occurrence_id` ou `schedule_output_id`).
2. pagina de faltas aplica foco/filtro inicial ao contexto recebido.
3. opcional Alpha: abrir modal de decisao automaticamente quando contexto for univoco.

Ficheiros-alvo provaveis:
1. `frontend/src/pages/Occurrences.jsx`.
2. `frontend/src/App.jsx` (apenas se necessario para parsing/navegacao especifica).

Testes obrigatorios:
1. ocorrencia criada na grelha aparece na listagem de faltas.
2. contexto de navegacao abre item correto.
3. sem regressao dos filtros existentes de data/turma.

#### 13.6 Pacote F - Ponte de compatibilidade legacy `substitutions` (Regras de negocio + Interface)

Objetivo:
- manter contratos legacy sem dupla logica divergente.

Estrategia Alpha (fechada):
1. `occurrences` continua fluxo principal de negocio.
2. endpoints `substitutions` passam por adaptador:
  - tentativa de localizar bloco (`lesson_id`, `timeslot_id`, `date`, tenant);
  - cria/reusa ocorrencia;
  - aplica decisao `SUBSTITUTED` via servico de ocorrencias.
3. resposta legacy preservada para compatibilidade externa.

Sincronizacao de dados legacy:
1. enquanto `Substitution` existir na Alpha, manter escrita idempotente de compatibilidade para consultas legacy.
2. regra de unicidade funcional em servico (sem depender de migration estrutural nesta fase).

Ficheiros-alvo provaveis:
1. `backend/app/api/v1/endpoints/substitutions.py`.
2. `backend/app/services/substitution_service.py`.
3. `backend/app/services/occurrence_service.py` (helper de compatibilidade, se necessario).

Testes obrigatorios:
1. `POST /substitutions` continua funcional e sem duplicar ocorrencias/accounting.
2. chamadas legacy e novas produzem estado final consistente.
3. teste de cascata continua valido para classe apagada.

Item "a definir" (explicito):
- estrategia de retirada definitiva da tabela `substitutions` apos Alpha (manter, migrar totalmente ou remover com migration dedicada).

#### 13.7 Pacote G - Bateria de testes de compatibilidade cruzada

Backend:
1. unitarios de criacao idempotente por bloco.
2. integracao API para novo `POST /occurrences`.
3. regressao cruzada legacy-vs-novo (`substitutions` + `occurrences`).
4. concorrencia em criacao + decisao.
5. tenant isolation em todas as rotas novas/legacy.

Frontend:
1. testes de interacao em `WeekGrid` e `Schedules`.
2. testes de navegacao/foco entre `Schedules` e `Occurrences`.
3. regressao da pagina de faltas existente.

Gate final obrigatorio:
1. suite dedicada alpha;
2. regressao backend completa;
3. regressao frontend completa;
4. sem P0/P1 aberto em fluxo de ocorrencias/substituicoes.

Estado de execucao (2026-04-12):
- Pacote A implementado: contrato `POST /occurrences` ativo com semantica 201/200 e validacoes de erro.
- Pacote B implementado: criacao idempotente por bloco sem contabilizacao prematura (decisao continua no `PATCH`).
- Pacote C implementado: payload semanal enriquecido com `occurrence_id`, `occurrence_decided_at`, `can_create_occurrence`, `can_decide_occurrence`.
- Pacote D implementado: grelha semanal usa flags operacionais para distinguir criar ocorrencia vs ir para faltas.
- Pacote E implementado: navegacao para `/absences` preserva contexto de ocorrencia/turma/data.
- Pacote F implementado: ponte legacy `POST /substitutions` orquestra fluxo canonico de ocorrencias mantendo resposta legacy.
- Pacote G validado (escopo atual):
  - backend: testes de criacao idempotente, regressao legacy-vs-novo e tenant isolation;
  - frontend: testes de interacao em `WeekGrid`, `Schedules` e navegacao contextual para `Occurrences`, alem da regressao da pagina de faltas.

### 14.0 Ordem de implementacao (sem ambiguidades)

Ordem obrigatoria para evitar retrabalho:
1. Pacote A (contrato API) -> fecha shape de entrada/saida.
2. Pacote B (servico de criacao) -> garante semantica idempotente e accounting correto.
3. Pacote C (payload semanal) -> habilita UI por bloco.
4. Pacote D (acao na grelha) -> habilita criacao operacional.
5. Pacote E (orquestracao com faltas) -> fecha workflow aprovado.
6. Pacote F (ponte legacy) -> garante compatibilidade externa.
7. Pacote G (testes e gate) -> valida estabilidade total.

Condicao de entrada para iniciar codigo:
1. aprovar contrato final do `POST /occurrences`.
2. aprovar semantica de pendencia (`decided_at = null`) sem novo enum.
3. aprovar estrategia de ponte legacy durante Alpha.
4. aprovar criterio de focagem da ocorrencia na pagina de faltas.

Estado de execucao (2026-04-12):
- ordem A -> G executada e validada sem retrabalho estrutural entre pacotes;
- condicoes de entrada cumpridas com evidencia objetiva:
  1. contrato `POST /occurrences` ativo com semantica 201/200 e validacoes tipadas;
  2. semantica de pendencia aplicada por `decided_at = null` na criacao operacional;
  3. ponte legacy ativa em `POST /substitutions`, convergindo para fluxo canonico de ocorrencias;
  4. focagem da ocorrencia na pagina de faltas ativa por `occurrence_id` em query params (`Schedules` -> `Occurrences`).
- validacao focada executada para fecho do passo:
  - backend: `5 passed, 62 deselected` em suite direcionada de `tests/test_occurrences.py`;
  - frontend: `10 passed` em `WeekGrid` + `Schedules` + `Occurrences`.

Conclusao do passo 14:
- concluido, com pre-condicoes satisfeitas e rastreabilidade tecnica/documental sincronizada.

### 15.0 Definicao de pronto (DoD) para este delta

DoD tecnico:
1. admin cria ocorrencia pelo bloco sem sair do contexto operacional.
2. ocorrencia aparece e e gerivel na pagina de faltas.
3. substituicao/GAP atualiza grelha, faltas e visoes associadas.
4. fluxo legacy de substituicoes nao quebra durante Alpha.
5. testes obrigatorios aprovados sem regressao de tenant/auth/accounting.

DoD de arquitetura (4 pilares):
1. Otimizacao: menos cliques e menor tempo de triagem operacional.
2. Estabilidade: idempotencia, transacao atomica e regressao cruzada aprovadas.
3. Escalabilidade: pagina de faltas mantida como hub para volume alto.
4. Seguranca: tenant isolation e role enforcement preservados em todos os caminhos.

Estado de execucao (2026-04-12):
- DoD tecnico validado (5/5):
  1. admin cria ocorrencia no bloco e segue para faltas sem sair do contexto operacional;
  2. ocorrencia criada aparece e e gerivel na pagina de faltas com focagem por `occurrence_id`;
  3. decisoes GAP/SUBSTITUTED refletem em grelha semanal e listagens operacionais com invalidacao de cache;
  4. fluxo legacy `POST /substitutions` permanece funcional via adaptador sem quebra de compatibilidade;
  5. testes obrigatorios aprovados sem regressao de tenant/auth/accounting.
- DoD de arquitetura validado (4/4 pilares):
  - Otimizacao: fluxo operacional reduzido (entrada no bloco + triagem central em faltas).
  - Estabilidade: idempotencia e concorrencia validadas em backend e regressao focada frontend.
  - Escalabilidade: hub unico de operacao em faltas preservado para volume real de escola piloto.
  - Seguranca: isolamento por `organization_id` e autorizacao admin-only mantidos nos caminhos novo e legacy.
- Validacao final executada para encerramento do passo:
  - backend: `73 passed` em `tests/test_occurrences.py` + `tests/test_alpha_release_gate.py`;
  - frontend: `10 passed` em `WeekGrid` + `Schedules` + `Occurrences`.

Status do criterio de saida revisado da feature (secao "feature completa"):
- 5/5 criterios cumpridos no escopo implementado desta Alpha.

Item ainda "a definir" (nao bloqueante da Alpha):
- estrategia de retirada definitiva da tabela `substitutions` apos Alpha (manter, migrar totalmente ou remover com migration dedicada).

Conclusao do passo 15:
- concluido.
- implementacao do delta 8-15 encerrada com validacao tecnica e documental sincronizada.

### 16.0 Hardening pos-review final (2026-04-12)

Objetivo:
- fechar riscos de arquitetura/operacao encontrados na revisao final especializada (bug-hunter), sem romper compatibilidade Alpha.

#### 16.1 5 Ws da decisao de hardening

What:
- reforco de imutabilidade de ocorrencias fechadas;
- bloqueio de conflito de substituto considerando tambem substituicoes ja confirmadas no mesmo slot/data;
- descontinuacao explicita de endpoint legado inseguro de sugestoes;
- reforco de isolamento tenant em leitura semanal;
- sincronizacao de deep-link operacional no frontend de faltas.

Who:
- admin: ganha previsibilidade e evita alteracoes retroativas destrutivas;
- professores/turmas: beneficiam de estado executado mais confiavel;
- equipa tecnica: reduz superficie de regressao e ambiguidade operacional.

Where:
- Interface: pagina de faltas (sincronizacao por query params);
- Regras de negocio: servico de ocorrencias e endpoint legado de substituicoes;
- Base de dados: validacoes tenant-scoped e deteccao de conflito operacional.

When:
- aplicado imediatamente apos o fecho tecnico dos pontos 8-15.

Why:
- preservar os 4 pilares ao mesmo tempo (otimizacao, estabilidade, escalabilidade e seguranca)
  em operacao real da escola piloto.

#### 16.2 Decisoes de arquitetura (estado fechado)

1. Fonte canonica operacional:
- `LessonOccurrence` e a unica fonte de verdade para decisoes de faltas/substituicoes.

2. Imutabilidade forte:
- ocorrencia com `decided_at != null` e considerada fechada e nao e reaberta por PATCH.

3. Correcao excecional de historico:
- nao alterar registo fechado in-place;
- se necessario por requisito legal/auditoria, criar fluxo append-only de retificacao.
- estado: desenho detalhado a definir (nao bloqueante da Alpha).

4. Legado:
- `GET /api/v1/substitutions/suggestions` descontinuado (`410 Gone`);
- `POST /api/v1/substitutions/` permanece temporariamente como adaptador de compatibilidade.

#### 16.3 Execucao tecnica (resultado esperado)

Backend:
1. `occurrence_service._teacher_is_busy_in_slot` passa a bloquear conflito por:
  - aula planeada no slot;
  - substituicao ja confirmada no mesmo slot/data.
2. `occurrence_service._validate_state_transition` passa a impor imutabilidade de ocorrencias fechadas.
3. `schedule_service.get_week_schedule_sync` inclui filtro explicito por `org_id` ao carregar ocorrencias.
4. `substitutions.py` marca `/suggestions` como deprecated e devolve `410` com instrucoes de migracao.

Frontend:
1. `Occurrences.jsx` sincroniza filtros com query params em navegacoes repetidas;
2. reabre foco por `occurrence_id` quando o deep-link muda.

#### 16.4 Criterio de aceite do passo 16

1. Nao e possivel alterar estado de ocorrencia fechada via PATCH.
2. Nao e possivel confirmar substituto em slot/data onde ja exista substituicao confirmada para o mesmo docente.
3. Endpoint legado de sugestoes responde `410` e aponta para fluxo canonico.
4. Navegacao repetida `Schedules -> Absences` respeita novos query params sem estado stale.
5. Testes focados backend/frontend aprovados apos hardening.
