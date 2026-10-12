# WBS técnico — Índice dos quatro planos

Revisão: 2026-10-07. Versão: 2.0.
Main revista: `91a9d28bcb9c9a829a8578872156a6b90fa04bcf`.
A main remota e o checkout tinham a mesma revisão durante a inspeção.
Reconciliação W12.4: 2026-10-09. Estado do W12: em curso. Consulte a [reconciliação das 80 tarefas](#reconciliação-w124).
Estado: 2026-10-12. A `main` publicada é `d4f6269` (#71); o ramo `codex/reduce-ci-runtime` está no [PR 72](https://github.com/ORIOP25/Cronos/pull/72) em `878e03b`, público e não fundido; [run 38282501310](https://github.com/ORIOP25/Cronos/actions/runs/38282501310) ficou totalmente verde e a execução mais recente falhou só no browser.
A referência `fe69` do audit fica preservada, com a execução pública [run 38206152558]; ver o [progresso noturno](REAL_BROWSER_TESTING_IMPLEMENTATION.md#progresso-noturno--2026-10-12).
Seleção crítica de CI validada em GHA; falta a mediana de três. Ver a [redução consolidada](REAL_BROWSER_TESTING_IMPLEMENTATION.md#redução-consolidada--2026-10-12).

## Objetivo e leitor

Coordenar a implementação do [PRD](REAL_BROWSER_TESTING_PLAN.md) em quatro partes menores.
Destina-se ao proprietário e aos implementadores.
Manter o âmbito aceite e os 80 IDs originais.
Reconciliar o estado observado sem remover gates aceites nem aumentar o âmbito.
Os IDs W00–W12 pertencem à iniciativa de testes, não ao WBS entregue do scheduler.

## Pré-requisitos e recuperação dos documentos

Os seis documentos anteriores não estavam no checkout nem no histórico Git consultado.
Esta revisão repõe o PRD, o índice e as quatro partes a partir das decisões desta conversa.
A revisão atualiza contratos e fontes; não certifica percursos ainda não executados.
Preservar alterações externas, incluindo o relatório de revalidação já existente em outputs.

## Quatro partes

| Parte | Pacotes | Tarefas |
| :--- | :--- | ---: |
| [1 — Base técnica, Gmail e evidências](REAL_BROWSER_TESTING_WBS_PART_1_FOUNDATION.md) | W00–W03 | 22 |
| [2 — Deployments, escola e geração](REAL_BROWSER_TESTING_WBS_PART_2_SCHOOL_AND_SCHEDULING.md) | W04–W06 | 19 |
| [3 — Operação histórica e restantes percursos](REAL_BROWSER_TESTING_WBS_PART_3_REAL_JOURNEYS.md) | W07–W08 | 15 |
| [4 — Limpeza dos testes, CI e verificação final](REAL_BROWSER_TESTING_WBS_PART_4_CLEANUP_AND_CI.md) | W09–W12 | 24 |

## Comportamento atual e motivo da revisão

| Alteração observada na main | Evidência | Ajuste neste WBS |
| :--- | :--- | :--- |
| Feedback, submit real e contexto assíncrono | b07c488, c245862, 27f4ffc, d753988 | W08.1/3/8 e W09.5 preservam interação, contexto e anúncios. |
| Preferências semanais e recuperação adaptativa | 13faa17, 8e3699f | W06.2 e W07.6 usam o motor atual e distinguem preferências de regras obrigatórias. |
| Decisões de ocorrência, reservas e fecho semanal | 7550fac, d962e65 | W07.4–6 e W09.3 preservam as novas transições e reservas. |
| Calendário atómico e QA de contabilidade | 4f30bc4, 5efba01 | W05.8 e W09.2/3 conferem datas e saldos coerentes. |
| Linhagem e dívida residual histórica | 95406f2 | W07.6 e W09.3 conferem origem e compensações entre versões. |
| Proteção incompleta de erros de aprovação/rejeição | `Schedules.jsx`, handlers atuais | W09.5 exige prova do chamador antes de remover testes. |
| Data preferencial na Fundação | fd91719 | W05.8 prova draft, limites, resumo e persistência. |
| Ícones de calendário dentro do campo | 8e94c0b | W08.8 prova calendário, teclado, foco e ajuda acessível. |
| Atribuições retiradas da página Cursos | 91a9d28 | W05.4 entra em /imports; não procura o botão removido. |
| Sessão Clerk e origem local corrigidas | 6190498, c01f95e | Reutilizar esperas; auth e preparação artificiais continuam por substituir. |
| Telemetria externa ignorada | c9ad291 | W03.7 não pode ignorar backend ou autenticação fora da origem frontend. |
| Relatório de capacity-smoke publicado em falha | 1415ecd, 4d493e7 | Reutilizar diagnóstico; não o contar como aceitação humana. |

Funcionalidades implementadas não significam tarefas de aceitação concluídas.
O runner local `e2e` ainda usa Compose, chaves de teste e `clerk.signIn` até ao cutover.
Gmail readonly, revisão do frontend, proteção de binários e limpeza por execução estão implementados no registo atual.
A aceitação real continua bloqueada. Ver a [reconciliação W12.4](#reconciliação-w124).

## Baseline e componentes

| Medida local | Valor |
| :--- | ---: |
| Backend: ficheiros test_*.py | 162 |
| Backend: unit / integration / contracts | 95 / 55 / 12 |
| Backend: definições estáticas test_* | 1192 |
| Frontend: ficheiros src/test/*.test.* | 87 |
| E2E: ficheiros *.spec.* | 27 |

Não confundir definições estáticas com casos recolhidos pelo pytest.
Não confundir contagem de ficheiros com redução efetiva de testes.

Reutilizar runner, Playwright, sanitizador, serviços de domínio, solver e CLI de privacidade.
A parte 1 define adaptadores e contratos do registo.
A parte 2 define revisão e helpers UI.
A parte 3 define expectativas operacionais.
A parte 4 define limpeza, núcleo e CI.

## Contratos e invariantes

- Usar Clean Architecture: domínio e políticas puros, efeitos nos adaptadores e composição no ponto de entrada.
- Passar dados e funções explícitos. Não criar interfaces com uma implementação ou frameworks internos.
- Aplicar Ponytail full: reutilizar código e biblioteca padrão antes de adicionar dependências.
- Usar nomes claros e unidades pequenas. Extrair helpers apenas perante repetição concreta.
- Escrever RED antes de uma alteração não trivial; implementar o mínimo, confirmar GREEN e refatorar.
- Reutilizar testes de comportamentos já corretos. Não criar RED artificial nem reimplementar correções existentes.
- Manter testes essenciais determinísticos, focados em comportamento.
- Testes de políticas/adaptadores podem controlar entradas; essa prova não substitui E2E real.
- E2E usa ações humanas na UI, sem auth programática, respostas falsas ou seeds de negócio.
- Preservar RLS, transações, segurança, acessibilidade, histórico e integridade.
- Registar IDs de caso concretos, revisão, organizações, RED/GREEN e referências de provas.
- Preservar erro primário; falhas auxiliares e dependências não podem produzir verde.

## Ordem e dependências

| Pacote | Dependências principais |
| :--- | :--- |
| W00 | Nenhuma |
| W01 | W00 |
| W02 | W01; acessos W00.4 |
| W03 | W00 e W01 |
| W04 | W01; acessos W00.4 |
| W05 | W02, W03 e W04 |
| W06 | W05 |
| W07 | W05, W06 e tempo real |
| W08 | W05; W06 quando depender de horários |
| W09 | W00 e prova substituta de cada grupo |
| W10 | W03/W04; W05 para limpeza; matriz completa para ativação final |
| W11 | W00 e núcleo de jobs |
| W12 | W01–W11 |

Executar W00 e a base da parte 1.
Avançar W04 quando os acessos estiverem disponíveis.
Preparar W10.1 após W01/W03/W04.
Verificar cedo o canal administrativo; concluir W10.4–6 depois de W05.
Passar G1 antes dos percursos de negócio.

Preparar W07.1 cedo para formar história real.
Avançar tarefas independentes enquanto o calendário amadurece.
Ativar W10.7 só depois da matriz completa.

## Mapeamento ao PRD

| Requisito | Tarefas |
| :--- | :--- |
| E2E-01 | W05.1, W05.8 |
| E2E-02 | W05.2 |
| E2E-03 | W05.3 |
| E2E-04 | W05.6–7 |
| E2E-05 | W01.1–3, W05.4–5 |
| E2E-06 | W08.1–2 |
| E2E-07 | W05.8 |
| E2E-08 | W06.1–4 |
| E2E-09 | W06.4–5, W08.2 |
| E2E-10 | W07.2–3 |
| E2E-11 | W07.4 |
| E2E-12 | W07.5 |
| E2E-13 | W07.6 |
| E2E-14 | W08.3 |
| E2E-15 | W08.4, W09.1 |
| E2E-16 | W08.5, W08.8 |
| E2E-17 | W08.6 |
| E2E-18 | W08.7 |
| NFR-01 | W01.4–5, W10.1 |
| NFR-02 | W10.1–2 |
| NFR-03 | W05.1–8, W10.8 |
| NFR-04 | W04.1–6 |
| NFR-05 | W07.1–2, W07.7 |
| NFR-06 | W08.3–4, W10.4–6 |
| NFR-07 | W03.1–2, W03.6–7, W10.7 |
| NFR-08 | W02.4–6, W04.6, W06.3 |
| NFR-09 | W03.3–6 |
| NFR-10 | W07.7, W10.3, W10.6 |
| NFR-11 | W09.1–4, W11.1–3 |
| NFR-12 | W09.5–8, W10.8, W12.4 |

## Condições de passagem

| Condição | Prova exigida |
| :--- | :--- |
| G1 | W01–W04: dados completos, Gmail, evidências protegidas e revisão. |
| G2 | W05: contas, convite e escola pela interface. |
| G3 | W06: candidato completo, aprovação, restrições e persistência. |
| G4 | W07: aulas reais, semanas, minutos e história. |
| G5 | W08 e matriz E2E-01–18 completa. |
| G6 | W09–W10: núcleo essencial, CI obrigatória e limpeza limitada. |
| G7 | W11–W12: recuperação isolada, campanha e documentação reconciliadas. |

Uma condição parcial não certifica produção.
A suite antiga é apenas baseline durante a migração.
Retirar o grafo antigo no cutover.
Não manter duas suites permanentes de aceitação.
Não reduzir critérios para cumprir uma data de entrada de clientes.

## Estados, falhas e riscos

A implementação avança por pacote; a aceitação real permanece pendente.
Esta revisão regista inspeção de código e uma seleção de testes locais.
Não marca Gmail, fornecedores, histórico ou campanha como concluídos.
Classificar bloqueios de autenticação, email, calendário, deployments, artefactos e limpeza explicitamente.
Ver a [reconciliação W12.4](#reconciliação-w124).
Falhas reais dos fornecedores impedem aceitação verde.

## Verificação realizada nesta revisão

- `git ls-remote origin refs/heads/main`: mesma revisão que o checkout.
- `node --test scripts/test.test.mjs`: 18 testes passaram.
- Frontend selecionado: 60 testes passaram em cinco ficheiros.
- Seleção: `foundationModel`, `useAttemptScope`, `AppToaster`, `apiErrors` e `PortugueseDateInput`.

Comando frontend:

```powershell
node scripts/test.mjs fast --scope frontend -- src/test/foundationModel.test.js src/test/useAttemptScope.test.jsx src/test/AppToaster.test.jsx src/test/apiErrors.test.js src/test/PortugueseDateInput.test.jsx
```

Não foram executados testes backend de dados, campanhas completas ou E2E em produção nesta revisão.
Os [comandos comuns](REAL_BROWSER_TESTING_WBS_PART_4_CLEANUP_AND_CI.md#comandos-e-checks-comuns) definem a verificação durante a implementação.

## Reconciliação W12.4

Reconciliação: 2026-10-09.
Base de implementação: PR 66, fundida na `main` como `804a2dd`.
A `main` publicada é agora `6140da6` (PR 68).
O equivalente local desta revisão é `b11a04c`.
O [registo de implementação](REAL_BROWSER_TESTING_IMPLEMENTATION.md) é a fonte principal.

Esta secção reconcilia as 80 tarefas W00–W12 com o estado observado.
Separa a implementação de código da aceitação real.
Nenhum percurso de negócio tem estado `validated`.

Veredicto global: uma estimativa global de progresso, cerca de 60%.
Não é uma percentagem de código implementado nem uma auditoria por pesos.
Os 69 IDs de caso estão definidos na fonte, não 69 validados.
A certificação completa de produção permanece zero.
Quatro casos públicos `@public-readonly` passaram numa execução real.
Os restantes percursos dependem de fornecedores e de história real.

A certificação dos 69 casos depende de calendário real e de fornecedores externos.
Esse bloqueio não impede a entrega do código nem a revisão documental.
A atualização noturna de 2026-10-12 identifica a causa raiz do registo como o desafio Cloudflare do Clerk SignUp.
Mantém a estimativa de cerca de 60%, sem pesos objetivos.
A `main` publicada é `6140da6`, com a CI [run 38192706792](https://github.com/ORIOP25/Cronos/actions/runs/38192706792).
A execução nativa [run 38193441985](https://github.com/ORIOP25/Cronos/actions/runs/38193441985) deu prova física aos quatro casos readonly e à cadeia de verificação assinada.

Base histórica e estado atual:

| Momento | Revisão | Observação |
| :--- | :--- | :--- |
| Histórico | `91a9d28` | Baseline dos quatro planos; o runner local usava Compose, chaves de teste e `clerk.signIn`. |
| Intermédio (2026-10-09) | `804a2dd` | Infraestrutura de aceitação implementada; comandos novos coexistem com o legado até ao cutover. |
| Atual (2026-10-12) | `d4f6269` | A `main` publicada é o #71, uma correção de edge sem relação; a referência de audit `fe69` fica preservada. O lote de redução vive no [PR 72](https://github.com/ORIOP25/Cronos/pull/72), em `878e03b`, público e não fundido; uma execução ficou totalmente verde e a mais recente falhou só no browser. A seleção crítica foi validada em GHA; falta a mediana de três. |

A tabela não contradiz o registo histórico; marca a evolução.

Estados das duas colunas:

- `CONCLUÍDO`: código e testes nativos verificados, ou percurso real validado.
- `EM_CURSO`: trabalho parcial observado.
- `DEPENDÊNCIA`: bloqueado por fornecedor, calendário ou histórico em falta.
- `PENDENTE`: não iniciado.
- `N/A`: pré-requisito sem percurso humano próprio.

Marcadores de evidência:

- `[M]` [Registo de implementação](REAL_BROWSER_TESTING_IMPLEMENTATION.md)
- `[P]` [acceptance-policy.js](../../frontend/e2e/utils/acceptance-policy.js)
- `[R]` [acceptance-reporter.js](../../frontend/e2e/acceptance-reporter.js)
- `[G]` [gmail.js](../../frontend/e2e/utils/gmail.js)
- `[E]` [protect-test-evidence.mjs](../../scripts/protect-test-evidence.mjs)
- `[F]` [finalize-real-browser-run.mjs](../../scripts/finalize-real-browser-run.mjs)
- `[D]` [deployments.js](../../frontend/e2e/utils/deployments.js)
- `[K]` [write-build-revision.mjs](../../frontend/scripts/write-build-revision.mjs)
- `[S]` [validate-e2e-schedule.py](../../scripts/validate-e2e-schedule.py)
- `[I]` [inspect-e2e-data.py](../../scripts/inspect-e2e-data.py)
- `[C]` [cleanup_e2e_run.py](../../backend/scripts/cleanup_e2e_run.py)
- `[W]` [test_worker_process_recovery.py](../../backend/tests/integration/committed/test_worker_process_recovery.py)
- `[Y]` [acceptance.yml](../../.github/workflows/acceptance.yml)
- `[B]` [public.spec.js](../../frontend/e2e/acceptance/public.spec.js)
- `[Id]` [identity.spec.js](../../frontend/e2e/acceptance/identity.spec.js)
- `[H]` [history.spec.js](../../frontend/e2e/acceptance/history.spec.js)
- `[Uc]` [ui-identity-campaign.js](../../frontend/e2e/utils/ui-identity-campaign.js)
- `[U]` [ui-school.js](../../frontend/e2e/utils/ui-school.js)
- `[V]` [expected-results.js](../../frontend/e2e/utils/expected-results.js)
- `[O]` [test_scheduler_v1_occurrences.py](../../backend/tests/integration/committed/test_scheduler_v1_occurrences.py)
- `[T]` [test_timesheets_v1.py](../../backend/tests/integration/committed/test_timesheets_v1.py)

Execuções citadas:

- [run 37951385146](https://github.com/ORIOP25/Cronos/actions/runs/37951385146): diagnóstico público; quatro casos readonly passaram.
- [run 37985882509](https://github.com/ORIOP25/Cronos/actions/runs/37985882509): CI da `main` após a PR 65.
- [run 37985892978](https://github.com/ORIOP25/Cronos/actions/runs/37985892978): listagem Gmail devolveu `invalid_json` (histórico, já corrigido).
- [run 37988240397](https://github.com/ORIOP25/Cronos/actions/runs/37988240397): CI da `main` após a PR 66.
- [run 37988249779](https://github.com/ORIOP25/Cronos/actions/runs/37988249779): verificação admin; `no_messages`.
- [run 37988345512](https://github.com/ORIOP25/Cronos/actions/runs/37988345512): verificação teacher; `no_messages`.
- [run 37988345830](https://github.com/ORIOP25/Cronos/actions/runs/37988345830): reset teacher; `no_messages`.
- [run 37998099499](https://github.com/ORIOP25/Cronos/actions/runs/37998099499): CI da `main` em `4e62573`; backend, frontend, E2E e capacidade passaram (histórico).
- [run 38191885411](https://github.com/ORIOP25/Cronos/actions/runs/38191885411): CI da PR 68; todos os jobs passaram, incluindo o Sonar.
- [run 38192706792](https://github.com/ORIOP25/Cronos/actions/runs/38192706792): CI da `main` em `6140da6`; backend, frontend, E2E e capacidade passaram.
- [run 38193441985](https://github.com/ORIOP25/Cronos/actions/runs/38193441985): `diagnose-public` nativo em `6140da6`; quatro casos públicos passaram à primeira tentativa (histórico).
- [run 38206152558](https://github.com/ORIOP25/Cronos/actions/runs/38206152558): `diagnose-public` nativo em `fe69`; quatro casos públicos passaram à primeira tentativa com os cinco SHAs iguais.

[run 37951385146]: https://github.com/ORIOP25/Cronos/actions/runs/37951385146
[run 37985882509]: https://github.com/ORIOP25/Cronos/actions/runs/37985882509
[run 37985892978]: https://github.com/ORIOP25/Cronos/actions/runs/37985892978
[run 37988240397]: https://github.com/ORIOP25/Cronos/actions/runs/37988240397
[run 37988249779]: https://github.com/ORIOP25/Cronos/actions/runs/37988249779
[run 37988345512]: https://github.com/ORIOP25/Cronos/actions/runs/37988345512
[run 37988345830]: https://github.com/ORIOP25/Cronos/actions/runs/37988345830
[run 38191885411]: https://github.com/ORIOP25/Cronos/actions/runs/38191885411
[run 38192706792]: https://github.com/ORIOP25/Cronos/actions/runs/38192706792
[run 38193441985]: https://github.com/ORIOP25/Cronos/actions/runs/38193441985
[run 38206152558]: https://github.com/ORIOP25/Cronos/actions/runs/38206152558

### Parte 1 — W00–W03

| ID | Implementação | Aceitação real | Evidência e fronteira |
| :--- | :--- | :--- | :--- |
| W00.1 | CONCLUÍDO | N/A | Baseline registada; [M]. |
| W00.2 | CONCLUÍDO | N/A | [P] mapeia E2E-01–18 em 69 IDs de caso. |
| W00.3 | EM_CURSO | N/A | Classificação em curso; Knip na CI; remoção em W09. |
| W00.4 | EM_CURSO | DEPENDÊNCIA | Gmail readonly, Cloudflare e Railway observados; remetente Clerk e encaminhamento Hostinger não observados. |
| W01.1 | CONCLUÍDO | N/A | Manifesto dos cinco CSV e `.gitattributes`; [M]. |
| W01.2 | CONCLUÍDO | N/A | [I] usa `csv` e `Decimal`. |
| W01.3 | CONCLUÍDO | N/A | 48 salas, 40 professores, 52 disciplinas, 208 módulos, 48 turmas, 16 cursos e 336 atribuições; [I]. |
| W01.4 | CONCLUÍDO | N/A | [P] exige `https://cronos.pt` e SHA completo. |
| W01.5 | CONCLUÍDO | N/A | Validação pura separada da composição; [P]. |
| W02.1 | CONCLUÍDO | N/A | Cliente OAuth Desktop readonly; quatro secrets; [M]. |
| W02.2 | CONCLUÍDO | N/A | PKCE e callback loopback; [M]. |
| W02.3 | CONCLUÍDO | CONCLUÍDO | Renovação e perfil das duas caixas observados; a listagem passou com `no_messages` em [run 37988249779] e [run 37988345512]. A entrega W02.4–6 continua pendente. |
| W02.4 | CONCLUÍDO | DEPENDÊNCIA | Leitor de mensagem implementado; nenhuma mensagem do remetente observada. |
| W02.5 | CONCLUÍDO | DEPENDÊNCIA | Parser MIME e testes Gmail; sem prova real de remetente. |
| W02.6 | CONCLUÍDO | DEPENDÊNCIA | Validação de ligações; [G]. |
| W03.1 | CONCLUÍDO | N/A | [P] agrega IDs, elegibilidade e proveniência. |
| W03.2 | CONCLUÍDO | N/A | Resultado estruturado e código não zero; [R]. |
| W03.3 | CONCLUÍDO | N/A | Redação de segredos; [F]. |
| W03.4 | CONCLUÍDO | N/A | AES-256-GCM e mascaramento; [E]. |
| W03.5 | CONCLUÍDO | N/A | Recuperação íntegra e confinamento; [E]. |
| W03.6 | CONCLUÍDO | N/A | Falha primária preservada; [F]. |
| W03.7 | CONCLUÍDO | EM_CURSO | Quatro casos públicos readonly passaram em [run 38193441985] à primeira tentativa. As três asserções fortes do spec público ficaram provadas. A cadeia de verificação assinada e o upload foram físicos. Não certifica os 69 casos. |

### Parte 2 — W04–W06

| ID | Implementação | Aceitação real | Evidência e fronteira |
| :--- | :--- | :--- | :--- |
| W04.1 | CONCLUÍDO | N/A | [K] escreve `dist/revision.json`. |
| W04.2 | CONCLUÍDO | N/A | SHA completo do build Cloudflare; [M]. |
| W04.3 | CONCLUÍDO | N/A | [D] pagina deployments; 25 observados. |
| W04.4 | CONCLUÍDO | EM_CURSO | Os quatro serviços estiveram alinhados em `aa5ab8b` (histórico). A produção está agora em `6140da6`, com os quatro serviços Railway `SUCCESS` e a revisão do frontend verificável. O instantâneo real confirma as cinco revisões iguais. O supervisor mantém o autodeploy ligado à `main`. |
| W04.5 | CONCLUÍDO | N/A | Schema e readiness normalizados; [D]. |
| W04.6 | CONCLUÍDO | EM_CURSO | Fixture por grupo; as revisões estavam misturadas antes do novo alinhamento. Não implica flakiness. |
| W05.1 | EM_CURSO | DEPENDÊNCIA | [Uc] implementa o registo. A submissão real observou sete pedidos ao host `challenges.cloudflare.com` e zero `sign_up`; o desafio Cloudflare do Clerk SignUp bloqueia o registo. |
| W05.2 | EM_CURSO | DEPENDÊNCIA | [Uc] cobre login e logout; execução real pendente. |
| W05.3 | EM_CURSO | DEPENDÊNCIA | [Uc] cobre a recuperação; a base local devolveu `form_identifier_not_found`. |
| W05.4 | CONCLUÍDO | DEPENDÊNCIA | [U] implementa a importação e tem teste; exige escola real pela UI. |
| W05.5 | CONCLUÍDO | DEPENDÊNCIA | [V] valida as relações importadas e tem teste; [S] não cobre importações. Execução real pendente. |
| W05.6 | EM_CURSO | DEPENDÊNCIA | [Uc] preserva o consentimento do convite; execução real pendente. |
| W05.7 | EM_CURSO | DEPENDÊNCIA | Prova de proteção da identidade pendente. |
| W05.8 | EM_CURSO | DEPENDÊNCIA | Fundação pela UI depende de W05.4–7. |
| W06.1 | CONCLUÍDO | DEPENDÊNCIA | [S] expande a exigência independente. |
| W06.2 | CONCLUÍDO | DEPENDÊNCIA | [S] confere restrições; [Id] cobre o caso. |
| W06.3 | EM_CURSO | DEPENDÊNCIA | Job real exige escola persistente. |
| W06.4 | EM_CURSO | DEPENDÊNCIA | Aprovação real exige candidato completo. |
| W06.5 | EM_CURSO | DEPENDÊNCIA | Nova sessão exige horários aprovados. |

### Parte 3 — W07–W08

| ID | Implementação | Aceitação real | Evidência e fronteira |
| :--- | :--- | :--- | :--- |
| W07.1 | EM_CURSO | DEPENDÊNCIA | O registo assinado de escolas do teste está vazio; nenhuma escola real criada. |
| W07.2 | EM_CURSO | DEPENDÊNCIA | [H] exige aulas terminadas; calendário real indisponível. |
| W07.3 | EM_CURSO | DEPENDÊNCIA | Sumário real exige aula terminada. |
| W07.4 | EM_CURSO | DEPENDÊNCIA | Núcleo de ocorrências preservado; execução real pendente. |
| W07.5 | EM_CURSO | DEPENDÊNCIA | Fecho semanal exige semana elegível. |
| W07.6 | EM_CURSO | DEPENDÊNCIA | Reparação exige história futura real. |
| W07.7 | EM_CURSO | DEPENDÊNCIA | Segunda campanha sem estado elegível. |
| W08.1 | EM_CURSO | DEPENDÊNCIA | [Id] cobre CRUD; execução real pendente. |
| W08.2 | EM_CURSO | DEPENDÊNCIA | [Id] cobre disponibilidade. |
| W08.3 | EM_CURSO | DEPENDÊNCIA | [Id] cobre isolamento; duas escolas reais em falta. |
| W08.4 | EM_CURSO | DEPENDÊNCIA | [Id] cobre recusa de rotas administrativas. |
| W08.5 | EM_CURSO | DEPENDÊNCIA | [B] implementa o contacto. A entrega ao destinatário e o encaminhamento Hostinger continuam pendentes. |
| W08.6 | EM_CURSO | DEPENDÊNCIA | [Id] cobre o guia; execução real pendente. |
| W08.7 | EM_CURSO | DEPENDÊNCIA | [Id] cobre o ano escolar; escola real em falta. |
| W08.8 | CONCLUÍDO | EM_CURSO | [B] quatro casos readonly passaram nativamente em [run 38193441985]; a prova física do foco de teclado e as três asserções fortes ficaram registadas. O 404 autenticado continua pendente. Não certifica os 69 casos. |

### Parte 4 — W09–W12

| ID | Implementação | Aceitação real | Evidência e fronteira |
| :--- | :--- | :--- | :--- |
| W09.1 | CONCLUÍDO | N/A | Núcleo JWT, RLS e webhooks preservado; [M]. |
| W09.2 | CONCLUÍDO | N/A | Transações, migrations e rollback preservados; [M]. |
| W09.3 | CONCLUÍDO | N/A | Ocorrências, dívida e fecho preservados no núcleo backend; [O] e [T]. |
| W09.4 | CONCLUÍDO | N/A | Solver e validador independentes; [S]. |
| W09.5 | EM_CURSO | N/A | Redução consolidada: sete ficheiros frontend removidos e um novo, saldo menos seis; cinco regressões de domínio backend duplicadas removidas e uma paridade nova. A seleção crítica de CI foi entregue e validada em GHA (`6d861ce` verde; `878e03b` falhou só no browser); falta a mediana de três execuções. O cutover da maioria continua bloqueado. Ver a [redução consolidada](REAL_BROWSER_TESTING_IMPLEMENTATION.md#redução-consolidada--2026-10-12). |
| W09.6 | EM_CURSO | N/A | Medição (estado do PR 72): frontend 579/81; backend 1 416; os 80 casos legacy de UI passam na CI em `0fb3594`. Seleção crítica validada em GHA: backend 225+62 local (22,26 s e 61,90 s; escopo 81,03, política 100, validador 90,18) e frontend 24 ficheiros/254 casos local (20,33 s; cobertura 67,2/70,65/56,53/69,39); full opcional 82/587. Primeira execução completa em `6d861ce`: backend 1 m 55 s, frontend 57 s, `e2e-runtime` 1 m 20 s; a mais recente em `878e03b` deu frontend 73 s e backend 120 s, pelo que a consistência não está provada e a mediana de três continua pendente. Gates e retries não mudaram. Ver a [redução consolidada](REAL_BROWSER_TESTING_IMPLEMENTATION.md#redução-consolidada--2026-10-12). |
| W09.7 | EM_CURSO | N/A | Knip na CI; remoção de dependências pendente. |
| W09.8 | EM_CURSO | N/A | Thresholds e gates em conjunto; pendente. |
| W10.1 | EM_CURSO | DEPENDÊNCIA | `acceptance`, `prepare-history`, `diagnose-public` e `inspect-code-sender` coexistem com o `e2e` legado (Compose e CI legado) até ao cutover W10.8. A campanha está inativa com `E2E_ACCEPTANCE_ENABLED=false`. |
| W10.2 | CONCLUÍDO | N/A | PRs sem segredos live; [Y]. O workflow verifica o resultado selado antes do upload e mantém só diagnósticos seguros; o passo passou no GHA. |
| W10.3 | CONCLUÍDO | N/A | `cancel-in-progress: false` mantém a execução ativa. O GitHub cancela pedidos pendentes anteriores na fila, como no dispatch readonly paralelo. A configuração de CI não muda; [Y]. |
| W10.4 | CONCLUÍDO | EM_CURSO | Política de propriedade e registo assinado implementados e testados. As intenções de criação assinadas são escritas antes das criações nativas; a eliminação real não foi executada. |
| W10.5 | CONCLUÍDO | EM_CURSO | Export e erasure implementados; uma intenção por resolver mantém a campanha `failed`; eliminação real não verificada; [C]. |
| W10.6 | CONCLUÍDO | DEPENDÊNCIA | Canal SSH validado; a execução remota não interativa ainda não foi executada. |
| W10.7 | CONCLUÍDO | DEPENDÊNCIA | Resultado obrigatório, verificação de integridade assinada e upload seguro, provados no GHA. Exige a matriz completa. |
| W10.8 | EM_CURSO | N/A | Remoção de helpers pendente do cutover. |
| W11.1 | CONCLUÍDO | N/A | Recursos e nomes de base de teste exatos; [M]. |
| W11.2 | CONCLUÍDO | CONCLUÍDO | Recuperação real do worker com PostgreSQL e Redis; [W]. |
| W11.3 | CONCLUÍDO | CONCLUÍDO | Idempotência com serviços reais; [W]. |
| W11.4 | PENDENTE | DEPENDÊNCIA | O ambiente Railway isolado não existe nem foi ensaiado. Qualquer recurso depende de planeamento isolado, sem novos custos. A integridade e a privacidade mantêm-se mesmo sem clientes. |
| W12.1 | PENDENTE | DEPENDÊNCIA | Campanha completa não executada. |
| W12.2 | EM_CURSO | DEPENDÊNCIA | A CI da `main` em `6140da6` ([run 38192706792]) e a CI da PR 68 ([run 38191885411]) estão verdes, incluindo o Sonar. A campanha completa e a maioria dos percursos de negócio continuam pendentes. |
| W12.3 | PENDENTE | DEPENDÊNCIA | Antes/depois, duração, fila e custos pendentes. |
| W12.4 | EM_CURSO | N/A | Reconciliação documental entregue e atualizada em 2026-10-12; o fecho do W12 depende de W12.1–3 e da campanha completa. |

### Condições globais G1–G7

| Condição | Estado | Prova observada e fronteira |
| :--- | :--- | :--- |
| G1 | DEPENDÊNCIA | W01–W04: dados completos e evidências protegidas; Gmail readonly observado; Cloudflare/Railway observados; alinhamento de revisão confirmado em `6140da6`; remetente Clerk pendente. |
| G2 | DEPENDÊNCIA | W05: registo pela UI bloqueado pelo desafio Cloudflare do Clerk SignUp, agora observado. |
| G3 | DEPENDÊNCIA | W06: candidato completo depende de escola persistente. |
| G4 | DEPENDÊNCIA | W07: sem aulas terminadas nem semanas elegíveis. |
| G5 | DEPENDÊNCIA | W08 e matriz E2E-01–18: 4 de 69 casos readonly passaram nativamente; cobertura completa pendente. |
| G6 | EM_CURSO | W09–W10: núcleo preservado, verificação de integridade assinada e upload verificados no GHA; cutover e campanha inativos. |
| G7 | EM_CURSO | W11–W12: recuperação de worker local provada; Railway isolado, campanha e verificação final pendentes. |

### Fronteiras abertas

- Os 80 IDs deste WBS são tarefas; os 80 casos legacy de UI browser são uma suite distinta e já passam nativamente na CI no perfil atual (`38269061278` em `0fb3594` e `38262965438` em `1e18315`).
- Uma seleção crítica de CI, com o job `e2e-runtime` e a matriz reduzida, foi entregue e validada em GHA; falta a mediana de três execuções.
- O remetente do código Clerk não está observado; `E2E_GMAIL_CODE_SENDER` não está configurada.
- O encaminhamento de contacto na Hostinger não está provado.
- O desafio anti-bot Cloudflare não é resolúvel por browser automatizado.
- O bloqueio do registo tem como causa raiz observada o desafio Cloudflare do Clerk SignUp.
- As contas de base devolvem `form_identifier_not_found` na recuperação local.
- O registo assinado de escolas do teste está vazio; não há prova de escola persistente, aula terminada ou semana elegível.
- A campanha está inativa com `E2E_ACCEPTANCE_ENABLED=false`.
- A exportação e a eliminação reais de produção não estão verificadas.
- O ambiente Railway isolado de W11.4 não existe nem foi ensaiado; qualquer recurso depende de planeamento isolado.
- A campanha completa e a maioria dos percursos de negócio continuam nativos por provar; a redução W09 é parcial.

### Métricas históricas

O baseline de 1 192 definições `test_*` é histórico.
Está na [tabela de baseline](#baseline-e-componentes).
Não é a contagem atual e não mede casos recolhidos.
As reduções não são quotas.
A primeira redução parcial removeu um ficheiro unitário.
Na altura, a contagem total subiu 51, porque a infraestrutura aumentou de 216 para 268.
O lote consolidado no PR 72 tem agora frontend 579 casos em 81 ficheiros e backend 1 416 casos.
Face a `91a9d28`, mantêm-se +8 casos frontend e +46 casos backend.
As metas 30–45 e 8–12 foram retiradas; passa a contar o tempo por job e a cobertura crítica.
Nenhuma contagem é uma quota nem certifica a libertação; a última CI ficou verde e a seleção crítica foi validada; falta a mediana de três.

## Fontes e documentos relacionados

- [Registo da implementação e provas observadas](REAL_BROWSER_TESTING_IMPLEMENTATION.md)
- [Guia atual de testes](TESTING_AND_CI.md)
- [Configuração escolar](../02_domain_model/SCHOOL_CONFIGURATION.md)
- [Scheduler atual](../03_scheduler_engine/README.md)
- [Ocorrências](../04_operational_features/OCCURRENCES_AND_SUBSTITUTIONS.md)
- [Fecho semanal](../04_operational_features/TIMESHEETS_AND_PROGRESS.md)
- [Feedback](../06_frontend_ux/FEEDBACK_MESSAGE_MATRIX.md)
- [Rotas atuais](../06_frontend_ux/ROUTES_AND_PERMISSIONS.md)
- [Importação CSV](../07_data_and_seed/BULK_IMPORT_CSV.md)
- [Privacidade](../09_ops_observability/PRIVACY_OPERATIONS.md)
- [Padrão de documentação](../00_getting_started/DOCUMENTATION_STANDARD.md)
