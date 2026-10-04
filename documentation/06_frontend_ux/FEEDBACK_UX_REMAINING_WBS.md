# WBS — Trabalho Restante da Modernização do Feedback

## Purpose

Este documento decompõe o trabalho restante da modernização do feedback visual.
A revisão confirma uma implementação parcial, com CI aprovada e contratos ainda por cumprir.
Este WBS substitui o plano inicial de execução para esta iniciativa.
Não substitui as decisões de produto do [tech spec](FEEDBACK_UX_TECH_SPEC.md).

**Data da revisão:** 3 de outubro de 2026.
**Estado:** planeamento do trabalho restante; esta revisão não implementa correções.

## Intended Reader

Este documento destina-se a engenheiros frontend, revisores e responsáveis pela aceitação da experiência do Cronos.

## Prerequisites

Leia o tech spec, a [arquitetura frontend](FRONTEND_ARCHITECTURE.md) e o [design system](DESIGN_SYSTEM.md).
Consulte a [acessibilidade](ACCESSIBILITY.md) e os [gates de qualidade](../08_security_quality/TESTING_AND_CI.md).
Aplique clean code, Clean Architecture, TDD para mudanças não triviais e Ponytail em intensidade `full`.

### Base auditada

| Elemento | Evidência |
| :--- | :--- |
| Worktree | `C:\Users\Hp\AppData\Local\Temp\opencode\feedback-ux` |
| Branch | `feat/feedback-ux-modernization` |
| Commit | `4c18cde5e917969a6cb99f9fea8937c9bbfb5878` |
| Estado Git da worktree | Limpo durante a revisão. |
| Histórico | Sete commits desde `ccbae96`; o resumo recebido indica seis. |
| Dependência instalada | `react-hot-toast`, versão declarada `^2.6.1`. |
| Repositório principal | Contém alterações concorrentes, incluindo formulários e páginas abrangidos por esta iniciativa. |

As observações de implementação referem-se ao commit auditado.
Os guias do repositório principal ainda podem descrever a versão anterior.
Os links de código na secção Source Map apontam para o commit auditado.

## What the System Does

A implementação acrescenta um host global de toasts e migra várias confirmações e falhas pontuais.
Também associa validações a campos e altera a apresentação de `FeedbackBanner`.
As alterações preservam vários conteúdos estruturados, como propostas, progresso e listas de problemas.

### Estado dos pacotes originais

| WBS original | Estado observado | Trabalho restante |
| :--- | :--- | :--- |
| 1 — Inventário | Matriz inicial disponível; a revisão encontra consumidores ainda não migrados. | Completar a classificação por mensagem e operação. |
| 2 — Host global | Implementado; testes focados passam. | Verificar os limites temporais exatos e a acessibilidade com modais reais. |
| 3 — Fluxos de referência | `MyAvailability` e `SmartTable` migrados. | Impedir efeitos de respostas de contextos anteriores. |
| 4 — Restantes ações manuais | Parcial. | Migrar falhas genéricas remanescentes e eliminar duplicação. |
| 5 — Validação local | Associação e foco implementados em três formulários. | Verificar submissão real, restrições nativas e aparência inválida. |
| 6 — Avisos persistentes | `FeedbackBanner` modernizado; consumidores antigos permanecem. | Modernizar as mensagens persistentes restantes. |
| 7 — Painéis e erros de página | Parte das caixas exteriores foi removida. | Rever os restantes painéis sem perder ações ou informação. |
| 8 — Contexto e acessibilidade | Limpeza de toasts existentes implementada; proteção de respostas pendentes ausente. | Cumprir o isolamento de contexto e verificar anúncios com modais. |
| 9 — Limpeza e documentação | Hook temporário e `.zen-toast` removidos; guias parcialmente atualizados. | Corrigir o estado do spec, referências obsoletas e links. |
| 10 — Gates e entrega | CI do commit auditado aprovada; Docker local aponta para a worktree. | Validar novamente o commit final após correções e integração. |

### Evidência de verificação

| Verificação | Resultado e limite |
| :--- | :--- |
| CI consultada | [Run 37138386948](https://github.com/ORIOP25/Cronos/actions/runs/37138386948), no commit auditado; frontend, backend e E2E aprovados. |
| Testes repetidos nesta revisão | Nove ficheiros, 45 testes aprovados. |
| Ficheiros repetidos | `AppToaster`, `FeedbackContext`, `FeedbackBanner`, `SmartTable`, `MyAvailability`, `CourseForm`, `ClassInCourseForm`, `SubjectForm` e `TimeField`. |
| Docker inspecionado | `cronos-frontend-1` monta `feedback-ux/frontend` em `/app`; mantém o volume de dependências. |
| Inventário estático | 54 aberturas de `<CAlert>` em 12 ficheiros de produção. |
| Screenshot consultado | `feedback-browser.png` mostra a página pública; não demonstra toasts sobre modais. |
| Evidência recebida | 523 testes, audit, verify, Knip e 14 verificações browser aprovados. Estes totais completos não foram repetidos nesta revisão. |

A CI usa o target `ci` do Dockerfile frontend, derivado do runtime Nginx.
As quatro falhas locais em Vite não demonstram quatro defeitos de produção.
Pré-renderização, respostas 404 e MIME de assets dependem do servidor correto.
Não acrescente um pacote de correção Nginx sem reproduzir uma falha nesse runtime.

## Why the Behavior Exists

O canal de feedback depende da utilidade da mensagem depois da tentativa.
Confirmações e falhas pontuais usam toasts temporários.
Validações, bloqueios e informação necessária para decidir permanecem junto do conteúdo afetado.
Uma CI verde confirma os testes existentes; não confirma requisitos que esses testes ainda não exercitam.

## Components and Ownership

### Lacunas observadas

| ID | Evidência | Lacuna | Pacote |
| :--- | :--- | :--- | :--- |
| F01 | `App.jsx:61`, `TutorialShell.jsx:7`, `MyAvailability.jsx:66–70`. | A limpeza remove mensagens existentes. Não impede emissões após uma resposta pendente de outro contexto. | R03 |
| F02 | `LessonLogModal.jsx:64`, `Timesheets.jsx:68`, `MySchedules.jsx:161`, `Members.jsx:142/306`. | Falhas de ações manuais ainda aparecem em alertas inline. Nem todas as falhas são genéricas; classifique os códigos. | R01, R02 |
| F03 | `SchoolConfigSections.jsx:103–109/339–342`. | Uma falha genérica de atualização pode emitir toast e apresentar `updateMutation.isError` em banner. | R02 |
| F04 | `ClassSubjects.jsx:210`, `apiErrors.js:34/61`, `class_service.py:814`. | A atribuição trata qualquer erro como toast, incluindo `teacher_competency_missing`, que exige correção contextual. | R01, R02 |
| F05 | `CourseForm.jsx:110`, `ClassInCourseForm.jsx:73`, `SubjectForm.jsx:104`. | A validação nativa pode impedir `onSubmit`; os novos testes com `fireEvent.submit` contornam esse percurso. | R04 |
| F06 | Campos dos três formulários; implementação instalada de `CFormInput`. | `aria-invalid` não ativa automaticamente a classe visual `is-invalid` do CoreUI. Falta verificar e ligar o estado visual. | R04 |
| F07 | 54 `<CAlert>`; regras `.alert-*` em `index.css:930–948`. | A modernização de `FeedbackBanner` não alcança os alertas antigos, que conservam caixas e fundos. | R01, R05 |
| F08 | `AppToaster.test.jsx:34–76`, `FeedbackContext.test.jsx`. | Os testes de duração avançam além dos limites; os testes de contexto não exercitam pedidos pendentes. | R03, R06 |
| F09 | Spec da branch, cabeçalho e Source Map. | O documento declara implementação concluída, conserva texto proposto e liga ao hook removido. | R07 |

Estas lacunas resultam da leitura de código, consumidores, testes e configuração.
As corridas de contexto e a experiência de submissão ainda precisam de reprodução comportamental.
Não foi confirmada uma falha de sobreposição ou de anúncio com modais.
Essa verificação permanece pendente.

### Inventário de alertas restantes

| Ficheiro | Aberturas de `<CAlert>` |
| :--- | ---: |
| `components/LessonLogModal.jsx` | 11 |
| `pages/Occurrences.jsx` | 9 |
| `features/schoolConfig/SchoolConfigSections.jsx` | 8 |
| `pages/Members.jsx` | 5 |
| `pages/MySchedules.jsx` | 4 |
| `pages/BulkImport.jsx` | 3 |
| `pages/CourseDetails.jsx` | 3 |
| `pages/Schedules.jsx` | 3 |
| `pages/Timesheets.jsx` | 3 |
| `pages/ClassSubjects.jsx` | 2 |
| `pages/MyProgress.jsx` | 2 |
| `pages/ClassDetails.jsx` | 1 |

A contagem mede consumidores visuais, não defeitos individuais nem quantidade de toasts a criar.
O inventário também deve incluir feedback escrito diretamente em HTML ou noutras classes.

### Responsabilidades de arquitetura

- Mantenha validações de domínio independentes de React, CoreUI e toasts.
- Mantenha pedidos, cache e invalidação nos feature data hooks existentes.
- Escolha o canal e emita feedback na página ou componente responsável pela tentativa.
- Centralize apenas posição, tema e duração no host existente.
- Reutilize `FeedbackBanner`, `StatePanel`, validadores e helpers existentes quando cumprirem o contrato.
- Acrescente abstrações apenas quando uma duplicação concreta justificar a mudança.

## Data or Request Flow

1. Valide os campos ou grupos afetados.
2. Capture o contexto da tentativa quando iniciar a operação.
3. Execute o pedido através do feature hook existente.
4. Confirme que o contexto continua válido antes de aplicar efeitos locais.
5. Emita uma confirmação ou falha pontual pelo dono da tentativa.
6. Mantenha validações e bloqueios no conteúdo apropriado.
7. Preserve os dados necessários para corrigir ou repetir a operação.

Não suprima resultados relevantes apenas porque o utilizador mudou de rota dentro da mesma organização.
Uma guarda de contexto trata identidade e âmbito; não altera os contratos de autorização da API.

## Contracts and Invariants

- Sucessos e informação temporária duram 4000 ms ativos.
- Falhas pontuais duram 6000 ms ativos.
- Separe a expiração do tempo adicional de animação e remoção do DOM.
- Preserve a pausa de leitura e o tempo restante depois da pausa.
- Use `top-right` a partir de 768 px e `top-center` abaixo desse limite.
- Uma tentativa produz uma mensagem de resultado; não duplica toast e banner com o mesmo erro.
- Preserve rascunho, estado por guardar e possibilidade de nova tentativa após falha pontual.
- Associe validações ao campo ou grupo; não acrescente resumo nem toast de validação.
- Mantenha bloqueios de negócio, ações de recuperação, progresso e listas no contexto.
- Respostas de utilizadores, organizações ou sessões de tutorial anteriores não apresentam feedback no contexto atual.
- Não elimine validação, acessibilidade ou prevenção de perda de dados para reduzir código.

O tech spec exige explicitamente a proteção contra respostas atrasadas.
Apenas limpar o store de toasts não cumpre esse requisito.
Ponytail também não permite simplificar requisitos explícitos ou prevenção de perda de dados.

## States and Transitions

Cada pacote segue `pendente → teste de reprodução → implementação mínima → refactor → verificado`.
Para documentação e mudanças apenas visuais, use revisão de conteúdo, links e browser conforme aplicável.
Não crie testes que apenas reproduzem detalhes da implementação.

### WBS restante

| ID | Entregável | Prioridade | Dependências | Estado inicial |
| :--- | :--- | :--- | :--- | :--- |
| R01 | Matriz final de mensagens e donos por operação. | P1 | Nenhuma | Inventário iniciado nesta revisão. |
| R02 | Migração das falhas pontuais e classificação dos bloqueios. | P1 | R01 | Pendente |
| R03 | Proteção contra respostas de contextos anteriores. | P1 | Nenhuma; coordenar alterações com R02. | Pendente |
| R04 | Validação acessível na submissão real. | P1 | Nenhuma; coordenar com alterações concorrentes nos formulários. | Pendente |
| R05 | Modernização do feedback persistente restante. | P2 | R01, R02 | Pendente |
| R06 | Verificação temporal, visual e acessível dos toasts. | P1 | R02, R03, R04, R05 | Parcial; testes existentes aprovados. |
| R07 | Documentação reconciliada com a implementação. | P2 | R01–R06 | Pendente |
| R08 | Integração, gates finais, runtime atualizado e CI aprovada. | P1 | R01–R07 | Pendente |

P1 identifica contratos necessários para aceitar a implementação.
P2 identifica acabamento visual e documental que também integra o âmbito pedido.
A prioridade não retira os pacotes P2 da entrega final.

### R01 — Fechar a matriz de mensagens

**Objetivo:** escolher o canal correto para cada mensagem restante.

1. Parta dos 12 ficheiros inventariados e da matriz do tech spec.
2. Procure outros consumidores de banners, classes de alerta e mensagens locais.
3. Registe operação, gatilho, código conhecido, canal, dono e comportamento de recuperação.
4. Distinga falhas de carregamento, falhas manuais, validações, bloqueios e resultados estruturados.

Inclua sumários, timesheets, submissão de semanas, equipa, ocorrências, geração, configuração escolar e importação.
Registe os fluxos já migrados para evitar regressões na mesma iniciativa.

**Aceitação:** cada mensagem encontrada tem destino e dono explícitos.
Nenhuma lista, proposta ou bloqueio desaparece por uma substituição indiscriminada por toast.

### R02 — Completar as falhas manuais e eliminar duplicação

**Objetivo:** aplicar os toasts aos erros genéricos acordados e preservar correções contextuais.

**R02.1:** migre as falhas pontuais em `LessonLogModal`, `Timesheets`, `MySchedules` e `Members`.
Reveja os handlers de `Occurrences`, `Schedules` e configuração escolar com a matriz R01.

**R02.2:** elimine a dupla apresentação no fluxo de atualização de estágio.
Mantenha `CALENDAR_EVENT_STALE` no contexto, com a ação de repetir a pré-visualização.

**R02.3:** trate `teacher_competency_missing` junto da atribuição afetada.
Reveja os restantes códigos efetivamente devolvidos; não crie uma taxonomia especulativa de erros.
Uma falha de campo deve usar a associação sustentada pelo contrato existente.

**TDD:** simule uma falha de rede e confirme um único toast, rascunho preservado e nova tentativa funcional.
Simule um bloqueio conhecido e confirme mensagem contextual, sem toast duplicado.
Cubra criação e atualização do fluxo de estágio, incluindo a pré-visualização desatualizada.

**Aceitação:** os fluxos da matriz usam os canais acordados.
Uma falha genérica não deixa um banner persistente nem fecha indevidamente o formulário.
Uma condição que exige correção permanece consultável enquanto existir.

### R03 — Proteger os efeitos de respostas atrasadas

**Objetivo:** impedir mensagens e efeitos locais de uma tentativa cujo contexto terminou.

**R03.1:** escreva testes com uma Promise controlada, iniciada no contexto A.
Mude para B antes de resolver ou rejeitar o pedido.
Verifique organização, utilizador, saída de sessão e saída do tutorial.

**R03.2:** implemente a menor guarda de identidade ou de ciclo de vida que cubra os handlers reais.
Reutilize os contextos existentes e capture a identidade ao iniciar cada tentativa.
Compare essa identidade com o contexto atual antes do toast ou de efeitos locais destrutivos.
Não pressupõe estado global, event bus ou um novo serviço de notificações.

**R03.3:** mantenha a limpeza dos toasts visíveis já implementada.
Confirme que operações concluídas no mesmo contexto continuam a apresentar o resultado.

**TDD:** resolva e rejeite pedidos após mudar o contexto.
Confirme ausência de mensagem antiga e preservação de um novo rascunho em B.
Exercite handlers com `await` e callbacks de mutação quando tiverem ciclos de vida diferentes.

**Aceitação:** nenhuma resposta antiga emite feedback no contexto atual ou limpa o rascunho atual.
Os testes não dependem de atrasos reais.

### R04 — Completar a validação na interação real

**Objetivo:** garantir que o utilizador recebe a validação local através do botão ou da tecla Enter.

**R04.1:** reproduza submissões vazias, valores fora dos limites e erros entre campos nos três formulários alterados.
Use `user-event` e verificação browser quando a validação nativa for relevante.
Não use apenas `fireEvent.submit` para provar o percurso de submissão.

**R04.2:** integre a validação nativa com a mensagem local e o foco acordados.
Caso use `noValidate`, preserve todas as restrições existentes no percurso controlado.
Não replique regras de negócio nem remova `required`, limites ou validações necessárias.

**R04.3:** ligue o estado inválido à apresentação existente do CoreUI, além dos atributos ARIA.
Confirme mensagem junto ao campo ou grupo, associação válida e foco no primeiro inválido.
Confirme a recuperação da aparência e da associação depois da correção.

**TDD:** falhe primeiro numa submissão real sem mensagem inline ou sem foco correto.
Cubra nome vazio, sigla curta, limites da turma, intervalo de anos e dados inválidos dos módulos.

**Aceitação:** submissão inválida não chama `onSubmit`, não emite toast e identifica o campo ou grupo.
A submissão válida mantém o payload e as regras existentes.
Coordene o resultado com as alterações de formulários do [WBS de remediação UX](UI_UX_REMEDIATION_WBS_V2.md).

### R05 — Modernizar as mensagens persistentes restantes

**Objetivo:** concluir a substituição das caixas antigas sem retirar informação necessária.

**R05.1:** use ícone decorativo, texto e eventual ação para avisos simples da matriz.
Reutilize `FeedbackBanner` quando corresponder ao conteúdo.

**R05.2:** mantenha listas, progresso, decisões e recuperação em secções ou painéis adequados.
Retire caixas de alerta exteriores apenas quando o painel conservar a sua hierarquia e todas as ações.

**R05.3:** elimine estilos e imports apenas depois de verificar os consumidores restantes.
Não altere globalmente todas as classes `.alert-*` para esconder uma migração incompleta.

**Verificação:** confira estados representativos de sumários, equipa, horários, ocorrências e importação no browser.
Teste comportamento apenas quando mudar ações, foco, persistência ou recuperação.

**Aceitação:** cada consumidor inventariado recebe o tratamento visual acordado ou uma justificação documentada.
Os avisos persistentes não têm timer e as ações permanecem utilizáveis por teclado.

### R06 — Fechar a verificação temporal e dos modais

**Objetivo:** demonstrar os contratos que os testes e a evidência atuais não fecham.

**R06.1:** corrija as asserções temporais existentes com fake timers.
Verifique presença antes de 4000/6000 ms e expiração nesses limites.
Verifique separadamente a remoção do DOM após o atraso de saída da biblioteca.
Confirme pausa e retoma pelo tempo restante.

**R06.2:** abra um `CModal` real com sucesso, falha pontual e validação local.
Confirme toast visível acima do overlay e ausência de interferência com os controlos.
Confirme que o foco permanece apropriado e que Escape mantém o comportamento do modal.

**R06.3:** confirme anúncios acessíveis de sucesso e erro com o modal aberto.
Não considere uma simples asserção de `role` suficiente para provar leitura por tecnologia assistiva.
Use uma fixture com dados simulados se faltarem credenciais; ela pode renderizar os componentes CoreUI reais.

**R06.4:** registe evidência em 375, 767, 768 e 1440 px, zoom de 200% e movimento reduzido.
Reutilize as verificações browser existentes quando forem reprodutíveis e cobrirem o mesmo contrato.

**Aceitação:** os testes falham se os limites temporais mudarem indevidamente.
A evidência identifica cenário, viewport e commit.
A sobreposição e os anúncios com modais ficam verificados ou registados como impedimento concreto de aceitação.

### R07 — Reconciliar documentação e critérios de aceitação

**Objetivo:** fazer os documentos descreverem a versão entregue e as limitações reais.

1. Separe a base histórica do comportamento implementado no tech spec.
2. Atualize estados e critérios sem declarar requisitos pendentes como concluídos.
3. Remova o link para `useTransientMessage.js`, eliminado na branch.
4. Corrija referências que descrevem `AppToaster` e os seus testes como ficheiros ainda propostos.
5. Atualize arquitetura, design system e acessibilidade conforme o resultado final.
6. Valide todos os links e caminhos alterados.

**Aceitação:** não existem links para ficheiros removidos nem declarações contraditórias de conclusão.
Cada limitação contém evidência, consequência e estado de resolução.

### R08 — Integrar e entregar a versão final

**Objetivo:** conservar o trabalho concorrente e validar a versão realmente integrada.

**R08.1:** compare a branch corrigida com o destino antes de integrar.
Resolva sobreposições nos formulários, modais, configuração escolar e páginas de operações.
Preserve as mudanças independentes; não copie a worktree inteira sobre o repositório principal.

**R08.2:** execute testes focados após cada mudança comportamental.
Execute audit e verify frontend, os gates obrigatórios e E2E relevantes na versão final.
Use a stack de testes dedicada ou CI para evitar interferência na stack partilhada.
O comando `all --scope all` não substitui os comandos E2E separados.

**R08.3:** atualize o frontend Docker a partir da fonte final escolhida após a integração.
Confirme mounts, modo Vite/Nginx e uma alteração observável da versão entregue.
Nesta revisão, o contentor já serve a worktree auditada; não é necessário mudá-lo para executar o WBS documental.

**R08.4:** após cada push, acompanhe a CI associada até aprovação.
Corrija falhas e repita o acompanhamento depois do novo push.
Registe o SHA final, o run aprovado e a evidência browser correspondente.

**Aceitação:** a versão integrada passa os gates e aparece no runtime previsto.
Não existem conflitos por resolver nem trabalho concorrente perdido.
Todos os contratos deste WBS têm evidência de fecho.

## Failure Modes

| Risco | Tratamento |
| :--- | :--- |
| Substituir todos os alertas por toasts. | Classifique as mensagens; preserve bloqueios, listas e recuperação. |
| Adicionar uma infraestrutura global para resolver callbacks antigos. | Comece pelos contextos e ciclos de vida existentes; extraia apenas duplicação demonstrada. |
| Desativar validação nativa sem conservar restrições. | Reproduza submissões reais e verifique as regras atuais antes de alterar o percurso. |
| Considerar limpeza do store como isolamento completo. | Teste a resolução e rejeição de pedidos iniciados no contexto anterior. |
| Declarar modais acessíveis apenas porque a CI passa. | Exercite os cenários de feedback e o anúncio com o modal aberto. |
| Confundir falhas Vite com defeitos Nginx. | Execute verificações de produção no runtime apropriado. |
| Integrar sobre ficheiros concorrentes sem comparar. | Revise os diffs e preserve os comportamentos de ambas as iniciativas. |

O capacity smoke anterior falhou com GET p95 de 1634 ms perante um limite inferior a 1000 ms.
A reexecução passou e a CI final também passou.
Esta revisão não demonstra relação causal com a migração de feedback.
Preserve o limiar; investigue uma recorrência através de traces e métricas, em vez de considerar apenas a reexecução como diagnóstico.

## Verification Procedure

### Verificação focada já executada

Execute na pasta `frontend` da worktree:

```powershell
npm.cmd test -- src/test/AppToaster.test.jsx src/test/FeedbackContext.test.jsx src/test/FeedbackBanner.test.jsx src/test/SmartTable.test.jsx src/test/MyAvailability.test.jsx src/test/CourseForm.test.jsx src/test/ClassInCourseForm.test.jsx src/test/SubjectForm.test.jsx src/test/TimeField.test.jsx
```

Resultado desta revisão: nove ficheiros e 45 testes aprovados.
Este resultado não equivale à repetição dos 523 testes reportados.

### Gates da implementação final

Execute na pasta `frontend`:

```powershell
npm run audit:production
npm run verify
```

Execute na raiz, conforme a documentação de testes:

```powershell
node scripts/test.mjs all --scope all
node scripts/test.mjs e2e --project public
node scripts/test.mjs e2e --project app
node scripts/test.mjs e2e --project faults
```

Os projetos E2E executam as dependências definidas no Playwright.
A CI final também deve manter os restantes gates existentes, incluindo provider e capacidade.
Não inicie estas suites sobre a stack partilhada sem verificar o isolamento definido pelo runner.

1. Confirme os novos testes de R02–R04 e os limites de R06.
2. Registe os cenários browser e o commit verificado.
3. Confira o inventário de feedback e as decisões de R01.
4. Valide links dos documentos alterados.
5. Execute `git diff --check` para o conjunto de alterações da iniciativa.
6. Confirme a CI e o runtime da versão final.

## Source Map

Os seguintes links fixam a implementação auditada, independentemente das alterações locais concorrentes:

- [Tech spec no commit auditado](https://github.com/ORIOP25/Cronos/blob/4c18cde5e917969a6cb99f9fea8937c9bbfb5878/documentation/06_frontend_ux/FEEDBACK_UX_TECH_SPEC.md).
- [Host global](https://github.com/ORIOP25/Cronos/blob/4c18cde5e917969a6cb99f9fea8937c9bbfb5878/frontend/src/components/AppToaster.jsx).
- [Limpeza de contexto](https://github.com/ORIOP25/Cronos/blob/4c18cde5e917969a6cb99f9fea8937c9bbfb5878/frontend/src/App.jsx#L47).
- [Disponibilidade e resposta de gravação](https://github.com/ORIOP25/Cronos/blob/4c18cde5e917969a6cb99f9fea8937c9bbfb5878/frontend/src/pages/MyAvailability.jsx#L60).
- [Sumários e falhas manuais](https://github.com/ORIOP25/Cronos/blob/4c18cde5e917969a6cb99f9fea8937c9bbfb5878/frontend/src/components/LessonLogModal.jsx#L51).
- [Configuração escolar e atualização de estágio](https://github.com/ORIOP25/Cronos/blob/4c18cde5e917969a6cb99f9fea8937c9bbfb5878/frontend/src/features/schoolConfig/SchoolConfigSections.jsx#L103).
- [Atribuição de professor](https://github.com/ORIOP25/Cronos/blob/4c18cde5e917969a6cb99f9fea8937c9bbfb5878/frontend/src/pages/ClassSubjects.jsx#L202).
- [Formulário de curso](https://github.com/ORIOP25/Cronos/blob/4c18cde5e917969a6cb99f9fea8937c9bbfb5878/frontend/src/components/Forms/CourseForm.jsx).
- [Testes do host](https://github.com/ORIOP25/Cronos/blob/4c18cde5e917969a6cb99f9fea8937c9bbfb5878/frontend/src/test/AppToaster.test.jsx).
- [Testes de contexto](https://github.com/ORIOP25/Cronos/blob/4c18cde5e917969a6cb99f9fea8937c9bbfb5878/frontend/src/test/FeedbackContext.test.jsx).
- [Imagem frontend e targets Nginx](https://github.com/ORIOP25/Cronos/blob/4c18cde5e917969a6cb99f9fea8937c9bbfb5878/frontend/Dockerfile).
- [CI aprovada](https://github.com/ORIOP25/Cronos/actions/runs/37138386948).

## Related Documents

- [Feedback UX Tech Spec](FEEDBACK_UX_TECH_SPEC.md).
- [Frontend Architecture](FRONTEND_ARCHITECTURE.md).
- [Design System](DESIGN_SYSTEM.md).
- [Accessibility](ACCESSIBILITY.md).
- [UI/UX Remediation WBS V2](UI_UX_REMEDIATION_WBS_V2.md).
- [Testing and CI](../08_security_quality/TESTING_AND_CI.md).
- [Documentation Standard](../00_getting_started/DOCUMENTATION_STANDARD.md).
