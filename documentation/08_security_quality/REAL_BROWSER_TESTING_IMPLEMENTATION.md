# Implementação dos testes reais — registo de execução

Revisão: 2026-10-08. Estado: implementação parcial; percursos, integração final e aceitação de produção pendentes.

Estado atual da matriz: 69 IDs concretos definidos e recolhidos, sem erros de discovery.
O âmbito do WBS mantém os 80 IDs originais. Anotar um caso não é executá-lo.
Esta contagem não certifica execução nem aprovação dos percursos em produção.
Os 69 casos anotados não equivalem a cobertura da matriz. Nenhum caso recebe `validated` sem execução real.

## Objetivo

Registar provas observadas durante a implementação dos [quatro planos](REAL_BROWSER_TESTING_WBS.md).
Não usar este registo como certificado de produção.

## Leitor e pré-requisitos

Destina-se a quem implementa, revê ou executa a campanha.
Ler o [PRD](REAL_BROWSER_TESTING_PLAN.md) e o [guia de privacidade](../09_ops_observability/PRIVACY_OPERATIONS.md).

## Comportamento observado

O baseline é `91a9d28bcb9c9a829a8578872156a6b90fa04bcf`.
A branch de implementação é `codex/real-browser-testing`, num checkout isolado.
As alterações externas do checkout original permanecem preservadas.
A implementação foi publicada na branch; os três jobs da CI passaram em `e37716623b0c72da3927b7bcb52c2e4822ea4080`.
Não ocorreu uma campanha completa de aceitação.
Um diagnóstico público no Chrome real passou contra `https://cronos.pt`.
Conferiu os canonicals de `/about`, `/contact` e `/privacy`, e uma página inexistente com resposta 404.
O trace e a screenshot foram cifrados; a recuperação autenticada dos dois ficheiros passou.
O diagnóstico não usou autenticação, seeds ou mutações, e não certifica a matriz completa.
Um diagnóstico posterior executou 36 testes públicos: 34 passaram e 2 falharam.
Os testes detetaram assets versionados com resposta 404 e imagens em falta sem JavaScript.
`/logo.png` respondeu 200; `/logo.png?v=20260921` respondeu 404.
O worker agora retira os parâmetros da consulta apenas do lookup interno dos ficheiros.
O teste focado reproduziu o 404 antes da correção e passou depois.
A correção permanece por publicar e por revalidar em produção.

Os cinco CSV originais têm um manifesto de nomes, bytes e SHA-256.
O inspetor independente usa `csv` e `Decimal`, sem importar o parser do produto.
Confirma 48 salas, 40 professores, 52 disciplinas, 208 módulos, 48 turmas, 16 cursos e 336 atribuições.
A procura expandida contém 1 209 600 minutos.
O `.gitattributes` marca os originais como `-text`; os blobs preservam CRLF exatamente como os ficheiros do proprietário.
Sem essa marca, a normalização de line endings falhava a integridade na CI.

O comando `node scripts/test.mjs acceptance` compõe o preflight, o projeto Playwright `acceptance` em Chrome, o finalizador de artefactos e a avaliação da matriz.
Com dependências em falta termina com código `3` e registra os nomes em `acceptance-plan.json`, sem abrir o browser.
A assembleia da campanha (identidade, snapshots anterior/posterior, casos, limpeza) é uma função pura coberta por testes; só `validated` da matriz completa certifica produção.
`.github/workflows/acceptance.yml` executa o comando no SHA da `main`, serializado e sem cancelamento automático, com upload sanitizado em sucesso e falha, ativado pela variável `E2E_ACCEPTANCE_ENABLED`.

A recuperação de um worker perdido é agora provada com infraestrutura real: uma mensagem real no broker Redis é consumida por um processo Celery próprio que reconcilia a tentativa abandonada para `FAILED/WORKER_STALLED`, e uma entrega duplicada não cria proposta adicional.

A aprovação e rejeição de propostas ignoram erros tardios após troca de escola, logout ou desmontagem.
Os testes demonstraram a falha antes da correção.
O container frontend local foi reconstruído e atualizado com essa correção.

## Continuação: acessos e percursos públicos

Foram geradas duas chaves aleatórias de 32 bytes.
Os secrets GitHub `E2E_ARTIFACT_KEY` e `E2E_REGISTRY_HMAC_KEY` estão configurados.
Os seis IDs Railway estão configurados nos secrets correspondentes.
A chave SSH administrativa dedicada foi registada pela API nativa.
Uma ligação real ao serviço API confirmou o canal sem alterar dados.
O secret `E2E_ADMIN_SSH_KEY` contém essa chave dedicada.

O registo persistente foi inicializado com assinatura válida e zero escolas.
Esse registo declara `history_verified=false`; não comprova histórico nem elegibilidade operacional.
O registo dinâmico de segredos começa vazio.
O runner junta os secrets separados do ambiente em memória antes da censura.
Não agrega a chave SSH com outros segredos num secret adicional.

O Railway recusou criar tokens sem o contexto do workspace com `Not Authorized`.
A criação com o `workspaceId` do projeto produziu um token dedicado válido.
Uma consulta ao projeto, autenticada exclusivamente com esse token, passou.
Os secrets `E2E_RAILWAY_TOKEN` e `E2E_RAILWAY_TOKEN_TYPE=account` estão configurados.
A cópia local permanece no ficheiro privado de acessos, fora do Git.
O refresh OAuth Cloudflare respondeu `invalid_grant`.
O browser isolado da ferramenta falhou antes de arrancar.
O Chrome headless isolado chegou à verificação de segurança Cloudflare, sem sessão autenticada.
A pesquisa Gmail direcionada não encontrou anexos com as configurações OAuth exigidas.

O projeto `acceptance` agora contém três percursos públicos concretos.
Cobrem rotas e canonicals, documentos legais e a resposta pública 404 com regresso ao início.
O diagnóstico Chrome de rotas e documentos falhou nos assets versionados ainda não publicados.
Após corrigir o locator, um diagnóstico 404 passou antes da carga completa da página de destino.
A revisão acrescentou a espera pelo evento `load`; o diagnóstico final falhou nos assets 404.
Esse caso permanece sem prova de aceitação válida.
As imagens, traces e restantes binários dos diagnósticos foram cifrados.
Estes diagnósticos não passam G1 nem certificam a matriz completa.

O observador acumula falhas de runtime sem lançar exceções dos callbacks.
As exceções HTTP usam a ação, método, origem, caminho e estado do pedido observado.
Um pedido novo invalida a exceção anterior para a mesma URL.
Os quatro testes do observador e o teste da censura em memória passaram após RED.
Os 58 testes de infraestrutura passaram após corrigir também a censura CLI; a CI confirmou a verificação frontend da revisão anterior.
O projeto de aceitação só entra na configuração quando o runner fornece `E2E_ACCEPTANCE_REPORT`.
O comando E2E local continua a selecionar apenas os projetos locais.
O contexto Docker exclui `.auth/`, que contém as credenciais locais.
Uma verificação da imagem real confirmou a ausência dessa pasta no estágio de build.
A imagem local foi reconstruída e o serviço frontend atualizado.
O comando de aceitação confirmou nove dependências em falta e terminou com código `3`, sem browser.

Os restantes 66 casos concretos ainda precisam de implementação ou adaptação e execução real.
Credenciais configuradas não substituem esses percursos.
Os quatro planos permanecem incompletos.

## Continuação: registo UI e identidade da limpeza

O runner inicializa um registo UI assinado depois do preflight e antes de abrir Chrome.
A fixture observa a identidade Clerk atual, sem criar utilizadores ou alterar autenticação.
Regista apenas aliases descartáveis criados dentro da execução.
Escreve atualizações assinadas por substituição atómica e recusa registos adulterados, identidades alteradas e diretórios redirecionados.
O registo permanece fora do upload de artefactos.
Os futuros percursos devem chamar `provenance.recordCurrentActor()` depois da criação e antes de logout.
A observação no teardown não recupera uma identidade depois do fim da sessão.

A revisão reproduziu aceitação indevida de uma limpeza de outra execução.
A política agora exige o mesmo `run_id` e listas conhecidas, vazias, de escolas e contas pendentes.
Os 62 testes de infraestrutura passaram, incluindo RED/GREEN da proveniência e da vinculação da limpeza.
Não foram criadas contas ou escolas reais nesta etapa.
As observações de escolas, os percursos de identidade e a composição remota da limpeza continuam pendentes.

## Componentes e estado das tarefas

| Tarefas | Implementação observada | Prova restante |
| :--- | :--- | :--- |
| W00.1 | Baseline, branch isolada e preservação das alterações externas. | Nenhuma para esta preparação. |
| W00.2–4 | Consumidores mapeados; acessos externos configurados e confirmados por leitura. | Manter a conferência durante a campanha real. |
| W01.1–3 | Originais completos, manifesto, inspetor independente e preservação de bytes na CI. | Conferir os resultados depois da importação pela UI. |
| W01.4–5 | Política pura exige produção, SHA completo e caixas dedicadas; runner ligado ao preflight. | Confirmar em execução real. |
| W02.1–6 | Helpers OAuth/Gmail com PKCE readonly; os quatro secrets Gmail e os perfis das duas caixas confirmados. | Observar o remetente do código (`E2E_GMAIL_CODE_SENDER`) e entregar mensagens reais nos percursos. |
| W03.1–7 | Matriz de 69 casos, avaliação pura, reporter, checkpoints explícitos por caso, cifragem, recuperação confinada, guards e composição fail-closed. | Execução real com registo dinâmico de segredos e upload protegido. |
| W04 | Writer da revisão frontend e adaptadores de deployments; Cloudflare e Railway confirmados; produção alinhada em `c850235` com `/revision.json` verificável; o fixture W04.6 verifica deployments vivos por grupo. | Publicar o diff atual e reobservar a revisão de produção. |
| W05 e W06.3–W08 | Historicamente, os três specs anotavam os 69 casos concretos; atualmente cada caso exige checkpoint explícito, prova materializada e proveniência de UI. | Execução real pela UI: contas, escola, geração, operação e história elegível. |
| W06.1–2 | Verificador independente de procura, crédito modular e recursos. | Ligar às leituras autenticadas e ao horário real. |
| W09 | Regressão do chamador corrigida com testes determinísticos; nenhuma remoção de testes foi executada e o cutover W09 continua bloqueado. | Inventário e redução após provas substitutas executadas. |
| W10.1–3, W10.7 | Comandos `acceptance` e `prepare-history` fail-closed, workflow serializado e upload sanitizado em falha; `E2E_ACCEPTANCE_ENABLED` está `false`. | Ativar a variável e executar a campanha real com os segredos e a matriz de percursos. |
| W10.4–6 | Registo HMAC, wrapper administrativo, exportação cifrada, erasure com bloqueio de jobs e transporte SSH separado. | Executar o wrapper remoto sobre o registo real produzido pela UI e comprovar eliminação no fornecedor. |
| W11.1–3 | Recuperação com broker real, worker próprio terminado e supervisor real por Redis; entrega duplicada sem proposta adicional. | W11.4: repetir num ambiente Railway isolado quando a prova exigir o fornecedor. |
| W12 | Documentação e comandos reconciliados com o comportamento comprovado; os 69 casos anotados usam agora checkpoints explícitos por caso. | Campanha completa no SHA publicado e limpeza por execução. |

O sanitizador preserva o modo legado enquanto não ocorre o cutover.
Nesse modo, a expectativa antiga de eliminar traces permanece ativa.
Com chave e run ID explícitos, cifra binários e autentica envelopes existentes.
Não retirar testes antigos sem uma prova substituta equivalente.

## Fluxo dos dados e evidências

O preflight valida configuração, dependências, registo assinado, originais, Gmail e deployments.
O reporter exporta casos, tentativas, elegibilidade, proveniência e referências relativas de evidências.
A avaliação recusa casos ausentes, duplicados, repetidos, sem provas ou sem limpeza concluída.
O reporter não certifica produção por si só.

O registo usa HMAC-SHA256 com chave separada de 32 bytes.
Node e Python autenticam o payload antes de interpretar os IDs.
A política preserva escolas persistentes e recusa propriedade desconhecida ou jobs ativos.
Confere também os emails observados dos atores contra os aliases do registo.
A política pura não executa operações destrutivas.
O wrapper `cleanup_e2e_run.py` recebe o envelope assinado por stdin e começa em dry-run.
Exige credenciais administrativas explícitas, separadas das credenciais do browser.
Confere todos os alvos antes de qualquer exportação ou eliminação.
Revalida cada alvo com bloqueio da organização antes dos efeitos externos.
Reutiliza o export de privacidade na mesma sessão e cifra o ZIP antes de eliminar no fornecedor.
Só executa erasure local após uma resposta de eliminação com o ID confirmado e `deleted=true`.

Mantém o bloqueio até ao commit e recusa jobs ativos nas duas gerações do scheduler.
As contas sem identidade Clerk pertencentes ao domínio também constam do export; não são atores de login.
Remove contas Clerk apenas quando foram criadas durante a campanha e não têm memberships locais nem no fornecedor.
O registo pode incluir `actors` na raiz para contas criadas pela UI antes de existir uma escola.
Exige alias da execução, proveniência UI e identidade/data de criação iguais à observação real do fornecedor.
Confere também a data de criação de todos os membros das escolas antes da primeira eliminação.
Uma conta sem escola recebe um export de identidade cifrado antes da eliminação Clerk confirmada.
Se existir um registo local dessa conta, recusa a eliminação externa até os dados serem exportados e apagados pelo fluxo administrativo adequado.
Os novos testes foram observados em RED antes da implementação; passaram 17 testes focados e 15 testes PostgreSQL de limpeza administrativa, além dos 61 contratos.
Após esta correção, `node scripts/test.mjs all --scope backend` passou com 1 403 casos, 82% de cobertura global e 100% na política crítica do scheduler.
Estas provas de infraestrutura usam respostas Clerk controladas; não comprovam uma eliminação de conta em produção.
Uma falha conserva os alvos pendentes e não publica o texto da resposta do fornecedor.

O finalizador confere que cada referência de evidência existe depois da proteção.
O sanitizador CLI reutiliza a lista de credenciais separadas e lê o registo dinâmico privado antes de alterar artefactos.
O workflow só faz upload depois de sanitização bem-sucedida.
Inclui a pasta protegida, o resultado final e o plano de dependências; exclui relatórios Playwright e JUnit não protegidos.
Autentica os envelopes, calcula bytes e SHA-256 e assina o resultado com HMAC.
A verificação posterior recusa alterações, ficheiros extra e ficheiros removidos.
Uma falha de proteção preserva a falha primária e impede `validated`.
O registo privado de segredos e o relatório final ficam fora da raiz dos artefactos.

## Verificações observadas

O último `npm run verify` passou 587 casos Vitest em 87 ficheiros e os checks frontend exigidos.
O inventário do baseline contém 571 casos nos mesmos 87 ficheiros.
Os 16 casos adicionais cobrem a regressão de tentativas e os guards de produção.
Ainda não ocorreu redução dos testes de aplicação.
Os 49 testes Node da infraestrutura de aceitação passaram após as últimas alterações, incluindo a composição pura do comando de aceitação.
Ruff passou nos ficheiros Python alterados.
Os testes focados de política, wrapper e contratos de privacidade passaram: 21 casos e 19 subtests.

O teste de recuperação de worker passou com PostgreSQL e Redis reais, um processo Celery próprio e uma mensagem real no broker: 1 caso em 29,6 segundos, sem proposta duplicada.

O runner isolado executou 10 testes PostgreSQL de privacidade e 61 contratos de infraestrutura, todos com sucesso.
Após acrescentar o wrapper, passaram mais três variantes PostgreSQL e os mesmos 61 contratos.
Estas variantes usam o fornecedor simulado apenas para verificar a transação administrativa.
Não constituem prova de eliminação no fornecedor real.
O ensaio PostgreSQL comprovou o bloqueio de um novo job durante a eliminação e a preservação local quando a confirmação do fornecedor é negativa.

O check completo `node scripts/test.mjs all --scope backend` passou.
Executou 888 testes unitários, 444 de integração e 61 contratos: 1 393 casos.
Ruff verificou os 353 ficheiros Python do backend.
A cobertura global foi 82%; a política crítica de constraints manteve 100%.
O runner removeu apenas os recursos de teste que criou.

O verificador `validate-e2e-schedule.py` não importa o domínio, o solver nem o validador do produto.
O comando lê sempre os cinco originais completos, com a verificação dos bytes e hashes.
Confere procura residual, offsets e sequência dos módulos, crédito parcial final, referências, capacidades, competências, datas, grelha e indisponibilidades.
Confere sobreposições para turma, professor e sala; períodos adjacentes permanecem válidos.
O almoço exige um intervalo contínuo por turma e professor nos dias com atividade.

Os oito testes independentes passaram, incluindo os quatro testes do inspetor CSV.
A CI tem um passo explícito para executar estes testes com a biblioteca standard.
A entrada materializada usa nomes dos CSV e ainda exige um adaptador das leituras autenticadas.
O verificador atual abrange horários futuros editáveis; a recuperação com posições protegidas permanece por ligar à baseline histórica.

## Contratos e invariantes

- Usar apenas `https://cronos.pt` na aceitação.
- Conferir os cinco componentes antes e depois da campanha.
- Percorrer as páginas Railway para identificar processos antigos ainda ativos.
- Manter credenciais administrativas separadas das credenciais do navegador.
- Não publicar storage state, códigos recebidos ou binários sem proteção.
- Não atribuir `validated` a diagnósticos parciais.
- Limitar exceções de produção por origem, método, caminho, estado e ação atual; recusar exceções para respostas 500.

## Estados externos e falhas

O supervisor Railway tinha uma revisão anterior à API, ao worker e ao Beat.
O utilizador autorizou explicitamente a configuração e o deploy desse serviço.
O deployment `688a5d29-feb7-4468-b1c4-34be0c527101` terminou em `SUCCESS`, na revisão baseline.
A versão anterior terminou em `REMOVED`, com `deploymentStopped=true`.
A consulta de leitura de 2026-10-07 confirmou os quatro serviços ativos em `91a9d28bcb9c9a829a8578872156a6b90fa04bcf`, todos `SUCCESS` e `deploymentStopped=false`:
`api` (`6bd62644-1d3b-4631-af46-3a275a6dd484`), `worker` (`bc9b44db-927a-4540-ab6b-2d0d61e09fae`), `scheduler-supervisor` (`65d601ed-1833-448b-8f50-74ec743898df`) e `beat` (`edb4e714-690c-471d-86f1-616f12ace288`).
O ambiente é `d6e36451-87ee-4e83-a7be-94738366c6fb`; a `main` remota coincidia com essa revisão.
A verificação da revisão frontend continua bloqueada: o token Cloudflare disponível está expirado e `/revision.json` ainda responde 404 porque as alterações do frontend desta branch não foram publicadas.

O Railway recusou associar `/backend/railway/supervisor.json`, indicando que Config as Code foi descontinuado.
A associação não foi alterada.
O comando existente do supervisor coincide com o ficheiro revisto.

A API respondeu com a revisão baseline e PostgreSQL/Redis ligados.
O endpoint frontend `/revision.json` ainda respondeu 404 em produção.
O token Cloudflare disponível respondeu com estado `expired`.
Não foram encontrados os quatro valores OAuth Gmail exigidos pelo preflight.
A lista de segredos do repositório contém apenas `CLERK_SECRET_KEY`, `POSTGRES_TEST_PASSWORD` e `SONAR_TOKEN`; a variável pública é `VITE_CLERK_PUBLISHABLE_KEY`.
O comando `acceptance` devolveu `dependency_unavailable` (código 3) com os 19 nomes em falta, sem abrir browser.
O workflow `.github/workflows/acceptance.yml` permanece inativo até `E2E_ACCEPTANCE_ENABLED` ser `true` e os segredos documentados existirem.
O controlo manual do navegador falhou na inicialização com `setup refresh had errors`.
O utilizador autorizou o login Cloudflare com `account:read`, `user:read` e `pages:write`, guardado no keychain.
O módulo nativo do keychain foi instalado, e o login abriu o consentimento.
O utilizador depois exigiu apenas o browser isolado da tarefa.
O processo de login foi interrompido; não foi confirmada uma nova sessão Cloudflare.
Estes estados impedem G1 e a aceitação completa.

## Procedimento de verificação

Execute os testes da infraestrutura:

```powershell
cd frontend
npm run test:acceptance-infrastructure
```

Execute as políticas independentes:

```powershell
python -m unittest discover -s scripts -p test_inspect_e2e_data.py
cd backend
python -m unittest discover -s tests/unit -p test_e2e_cleanup_policy.py
```

Execute o verificador independente sobre a representação materializada da campanha:

```powershell
python scripts/validate-e2e-schedule.py <materialized-snapshot.json>
python -m unittest discover -s scripts -p "test_*e2e*.py"
```

Recupere uma evidência com a chave separada em `E2E_ARTIFACT_KEY`:

```powershell
node scripts/protect-test-evidence.mjs recover <source.enc> <output-directory> <run-id> <original-relative-path>
```

Use o caminho original relativo à raiz de artefactos, sem o sufixo `.enc`.
A recuperação autentica antes de escrever e recusa sobrescrita, caminhos indevidos e junctions dentro da saída.

## Continuação — percursos de identidade

Acrescentado `identity.spec.js` com cinco IDs concretos, além dos três percursos públicos existentes.
O fluxo usa registo, consentimento, códigos entregues, recuperação e entradas em contextos novos pela interface.
Os rótulos iniciais de registo/login foram observados num Chrome próprio headless em produção, sem submissão.
As palavras-passe e os códigos entram no registo privado antes de serem utilizados no browser.
O teste do registo dinâmico passou de RED para GREEN; inclui corrupção, duplicados e uma junction real.
O preflight exige o remetente de código observado antes de criar contas.
Nenhum destes cinco casos recebeu prova de execução real: Gmail OAuth e o remetente dos códigos continuam pendentes.
O remetente dos convites foi confirmado por metadados de mensagens reais como `invitations@cronos.pt`.
A consulta da instância Clerk confirmou produção e o domínio `clerk.cronos.pt`, distintos da configuração local de desenvolvimento.

Continuação local: o produtor de escolas liga IDs local/Clerk, criação, fundador e membros aos atores observados na campanha.
O teste RED/GREEN recusa IDs trocados, aliases externos, membros duplicados, datas anteriores e alterações do tipo de escola.
O ficheiro mantém HMAC, substituição atómica e recusa de diretórios redirecionados.
O adaptador consulta os IDs locais e memberships através da sessão obtida na UI; não cria dados por API.
O percurso de identidade cria a escola pelos controlos de seleção Clerk antes de gravar a proveniência.
Estas alterações locais ainda não comprovam uma escola real nem a conclusão dos dez passos da Fundação.
Após orientação do proprietário, os próximos lotes ficam locais até à implementação e revisão finais, sem pushes individuais.

O lote local seguinte percorre os dez passos da Fundação e verifica datas no resumo, no draft e na configuração após reload.
O percurso avança com a data preferencial vazia e recusa valores antes do início ou depois do limite final.
A escola começa depois do dia real de criação em Lisboa; não usa datas passadas para simular histórico.
A espera de autosave identifica o PUT da UI com as três datas antes de recarregar.
A importação envia os cinco originais completos, confere os sete totais na UI e no resultado do commit, e guarda ambos os relatórios.
O fluxo termina a sessão pelo botão visível e confirma o redirecionamento de uma rota administrativa.
Estão definidos 68 IDs de aceitação, incluindo os cinco públicos; definição não significa prova real.
Os 74 testes locais de infraestrutura e os nove testes Python independentes passaram.
Os 13 testes da API scheduler e os 61 contratos backend passaram após adicionar a leitura materializada.
O endpoint administrativo pagina aulas persistidas e inclui os intervalos, recursos, créditos e módulos reais.
Os testes conferem cada campo com PostgreSQL, recusam outros tenants e professores, e validam os limites de paginação.
A campanha lê todas as páginas antes da aprovação e exige uma versão, escola, ano e total estáveis.
A conversão independente preserva os horários de Lisboa e recusa IDs desconhecidos, duplicações e durações incoerentes.
O teste RED/GREEN inclui datas antes e depois da mudança para o horário de inverno.
A campanha liga estas leituras ao calendário, grelha por data e disponibilidade dos 40 professores.
As consultas abrangem todo o horizonte escolar, em blocos de 31 dias, sem reduzir os originais.
O adaptador exige todos os dias, versões, blocos e professores; recusa lacunas, duplicações e referências desconhecidas.
Eventos gerais excluem datas letivas. Fluxos de estágio bloqueiam apenas as turmas observadas.
Só a disponibilidade `-1` bloqueia aulas; as preferências `0`, `1` e `2` mantêm a sua natureza.
O calendário independente conserva a regra de almoço real, quando configurada.
O teste RED/GREEN cobre feriados, estágio, transição de grelha e indisponibilidades, sem importar regras do produto.
O comparador confere conteúdo, competências, módulos, currículos, anos letivos e todas as 336 atribuições.
Também recusa turmas aninhadas ou metadados incoerentes, mesmo com IDs e totais corretos.
O percurso visita todas as turmas e confere os professores selecionados antes de verificar persistência após reload.
O convite converte um professor importado para o alias dedicado, preservando IDs, competências e atribuições.
O teste lê a mensagem entregue e utiliza o seu link; não consulta tickets pela API administrativa.
Uma mensagem real confirmou o destino `https://clerk.cronos.pt/v1/tickets/accept`; nenhum ticket dessa mensagem foi utilizado.
O registo privado inclui o link e os valores dos seus parâmetros antes de abrir o browser.
O teste RED/GREEN cobre a exposição do ticket isolado ou codificado depois de um redirecionamento.
O professor entra numa sessão nova, guarda uma preferência e verifica o mesmo bloco depois de voltar a entrar.
O administrador consulta essa disponibilidade pela UI, incluindo após reload.
As tentativas de rotas administrativas exigem redirecionamento e ausência de pedidos de escrita.
O arquivo/restauro seleciona exclusivamente o ID e alias do professor criado nesta campanha.
O teste preserva os IDs locais, as competências e todas as relações importadas após o restauro.
O CRUD usa recursos temporários adicionais; não reduz a procura original antes de gerar.
O curso inclui a turma preenchida sem clicar `Adicionar turma`.
Os cinco modelos são descarregados realmente; os cabeçalhos são comparados com os originais.
O 404 autenticado usa navegação real, confirma HTTP 404 e testa o regresso ao painel.
O filtro `Mostrar arquivados` não tinha nome acessível nem associação entre rótulo e input.
Uma correção de ID passou de RED para GREEN nos sete testes focados de `Members`.
O frontend local foi reconstruído e recriado; o bundle ativo contém a correção e responde HTTP 200.
O `npm run verify` local terminou com código zero; passou os 588 testes frontend, lint, contratos e build.
A Fundação termina antes da recuperação; o fundador sai pela UI antes de serem invalidadas sessões anteriores.
O projeto de aceitação conserva traces em sucesso e falha para proteção e assinatura finais.
O percurso seguinte confere os seis critérios reais de Bases e a pré-validação após reload.
Exige confirmação visível antes do único POST de geração e acompanha o job até um estado terminal.
Um estado terminal diferente de `SUCCEEDED` falha; a proposta deve estar atual e disponível para revisão.
A aprovação pela UI ocorre apenas depois da validação Python das aulas materializadas contra todos os CSV originais.
A primeira geração exige cobertura integral dos minutos originais, sem atribuir créditos executados hipotéticos.
O teste guarda o snapshot e relatório, verifica novamente as revisões, e confirma a publicação após reload.
Esta composição está implementada; a prova real de produção continua pendente da campanha e credenciais.
Uma nova sessão docente confere todas as semanas do horizonte com as aulas e módulos aprovados.
A UI mostra a versão publicada e as células da primeira semana ocupada, após navegação nativa quando necessária.
O comparador recusa aulas extra, aulas omitidas, outros professores, recursos trocados e créditos executados inesperados.
O progresso docente exige todas as atribuições e módulos originais, com zero execução ou dívida antes das aulas.
O percurso confere os cartões e a persistência após reload, sem importar verificadores do produto.
Uma aula futura mantém `Aula Dada` desativado e a semana incompleta mantém `Submeter Semana` desativado.
Abrir o modal e preencher um sumário temporário não envia writes; cancelar conserva os dados observados.
Estes percursos estão definidos. Não constituem prova real de produção enquanto a campanha não for executada.
O guia acrescenta os casos `guide-complete-resume` e `tutorial-isolation`.
O percurso edita uma disciplina na demonstração e exige ausência de escritas reais e telemetria.
Sai no segundo passo, recarrega, retoma e revê o primeiro exemplo sem conservar a edição simulada.
Conclui os 13 passos e confere o mesmo ID de execução e o estado concluído após reload.
Os catálogos reais e as configurações da escola devem manter os valores anteriores.
Os sete testes existentes de `Guide` e `TutorialWorkspace` passaram; não substituem a campanha real.
O percurso de rejeição conserva as revisões e exige ausência de publicação e de elegibilidade para reroll.
Uma alteração administrativa de uma única preferência permite nova geração com IDs novos.
A comparação conserva todas as outras células e os dados originais de procura.
Os seis testes existentes de elegibilidade passaram.
O contacto público tinha erros associados, mas não focava o primeiro campo inválido nem anunciava os erros.
Um teste de componente provou a falha de foco antes da correção; os cinco testes focados passaram depois.
O percurso por teclado exige anúncios, associação ao campo e zero pedidos de escrita com detalhes inválidos.
O diagnóstico no Chrome headless próprio passou contra o container local atualizado.
Confirmou foco no campo inválido, anúncio, zero violações Axe, zero erros de página e zero escritas de negócio.
O `npm run verify` terminou com código zero após esta correção.
O frontend Docker foi reconstruído a partir do worktree e o container foi recriado.
Esta observação local não certifica a revisão publicada nem a campanha completa de produção.
Após a recuperação, uma sessão nova tenta a palavra-passe antiga pela UI e exige recusa.
O percurso exige HTTP 422, código de palavra-passe incorreta, mensagem visível e ausência de utilizador ou sessão.
A exceção fica ligada ao pedido observado, à sua origem e à ação que iniciou a tentativa.
Pedidos posteriores para a mesma URL, ações diferentes e erros de servidor continuam a falhar.
Dois testes novos provaram RED/GREEN desta composição; os 76 testes de infraestrutura passaram.
O login seguinte com a nova palavra-passe conserva a prova positiva já existente.
O reinício anual usa exclusivamente a escola descartável criada pela UI nesta campanha.
Antes da ação, o produtor assinado reconfirma propriedade, identidades e tipo descartável.
O percurso exige checkbox e a frase exata, recusa `confirmo` e observa um único POST confirmado.
Confere perda da publicação, revisões a zero, Fundação concluída e todos os dados originais preservados.
Define o período seguinte pela UI, confirma as três datas juntas e verifica persistência após reload.
Este caso não comprova preservação de créditos históricos: a escola descartável tem aulas futuras.
As três regressões selecionadas de soft reset e os 61 contratos passaram com PostgreSQL/Redis isolados.
O layout autenticado agora expõe o seletor nativo Clerk, que antes só aparecia sem escola ativa.
O teste de layout provou RED/GREEN; o tutorial continua sem controlo de troca real.
O percurso cria uma segunda escola pela UI e importa novamente todos os CSV originais.
Confere os IDs distintos, as datas diferentes e a diferença docente criada pelo convite na primeira escola.
Alterna primeira, segunda e primeira pela UI e compara os catálogos completos, as datas e os docentes visíveis.
Estes dois casos não certificam feedback de respostas tardias; essa prova continua em falta.
O frontend passou `npm run verify`, com 590 testes, e a auditoria de dependências de produção.
O container local foi reconstruído com a imagem `48ebf0bfe0b3ba9dbeb7c3c62fc055572d3490bc0c3a9973e61b16ef6419b710`.
O percurso de ocorrência futura exige confirmação pela UI e verifica zero crédito e zero dívida no estado pendente.
A decisão `GAP` exige confirmação e acrescenta exatamente os minutos da aula à dívida, sem execução antecipada.
Confere persistência após reload e reverte pela UI, conservando o histórico de auditoria e restaurando os saldos iniciais.
Os estados concluídos e as substituições históricas continuam por provar; estes dois casos não os substituem.
Esta composição revelou que o progresso docente consultava apenas o ledger antigo.
A regressão RED observou zero dívida onde o ledger v1 tinha 50 minutos, apresentados como 0,8 horas.
A correção reutiliza a projeção v1 da página da turma e conserva o fallback das escolas sem atribuições v1.
O GREEN passou 20 regressões de ocorrências, progresso e permissões docentes, mais 61 contratos com PostgreSQL/Redis isolados.
Ruff, recolha Playwright e os 76 contratos de infraestrutura de aceitação passaram; nenhum destes resultados certifica a campanha em produção.

A composição seguinte planeia uma substituição futura por confirmação na UI.
Valida atribuição original do substituto, ausência de conflito docente e reserva exata de turma, sala e intervalo.
Confere `PENDING_LOG`, zero crédito, dívida original inalterada, persistência e libertação da reserva após reversão.

Uma segunda sessão administrativa mantém o formulário antigo enquanto a primeira decide `GAP`.
O envio antigo exige um único 409, mensagem de atualização e ausência de bloco, dívida ou revisão adicional.
O runtime isenta exclusivamente o pedido observado nessa ação; outros pedidos e estados continuam fatais.
Três regressões selecionadas de reservas, candidatos e conflito v1 passaram, mais 61 contratos backend.
Estes dois novos casos continuam sem prova nativa em produção.

O runner agora chama a limpeza administrativa após qualquer resultado Playwright e antes do snapshot final.
Eliminou a dependência do resultado externo `E2E_CLEANUP_RESULT`, que não era produzido pela CI.
O canal SSH nativo foi reconfirmado em produção com uma leitura de stdin, sem mutações.
O novo adaptador envia registo assinado e chaves de proteção pelo stdin; conserva a chave SSH fora dos argumentos.
O comando remoto recusa uma revisão diferente e reutiliza o wrapper administrativo existente.

As exportações AES-GCM são autenticadas por execução e caminho antes de serem guardadas nos artefactos.
O registo UI também fica cifrado antes da limpeza, permitindo reconciliar uma falha com a proveniência original.
Uma falha de cifragem do registo não evita a tentativa de limpeza, mas impede aceitação verde.
Os backups remotos cifrados ficam num diretório privado de `/tmp`, indicado por `remote_export_directory`.
Conservá-los até confirmar recuperação local, upload protegido e reconciliação dos alvos pendentes.

Os 37 contratos selecionados do adaptador e runner passaram, incluindo escola persistente e diretório aliased.
Não foram criadas nem eliminadas escolas de produção nesta verificação.
O teste RED seguinte demonstrou que o marcador público de tipo de token `account` alterava a chave `account_id` na evidência.
A correção exclui apenas `E2E_RAILWAY_TOKEN_TYPE` da lista de segredos; o token e as credenciais reais continuam expurgados.
Gmail OAuth, campanha publicada, horários, operação histórica e limpeza real continuam pendentes.

A revisão seguinte conserva resultados remotos autenticados quando a gravação local das exportações falha.
O teste demonstrou RED/GREEN para uma exportação existente, sem a sobrescrever nem declarar aceitação verde.
O canal administrativo real confirmou a chave Clerk de produção e a presença de uma credencial de base de dados separada.
Esta verificação leu apenas disponibilidade, separação de papéis e revisão; não executou eliminação.

O novo percurso histórico define os três casos de sumário terminado, delta exato e repetição sem duplicação.
Exige escola persistente assinada com proveniência UI e o login real do docente convidado durante a sua criação.
Seleciona uma aula terminada no relógio real, ainda sem registo e no frontier curricular atual.
Confere parcelas modulares exatas, identidade física, persistência e edição posterior sem crédito adicional.
A credencial persistente tem configuração própria; nenhum percurso usa autenticação programática ou relógio artificial.
Existem agora 68 variantes concretas definidas. A recolha não certifica execução histórica em produção.
Os 86 contratos de infraestrutura passaram; lint, Knip e recolha Playwright também passaram.
Continua por implementar uma variante; a preparação e execução das escolas persistentes permanecem pendentes.

A preparação tem agora comando próprio: `node scripts/test.mjs prepare-history`.
Reutiliza o percurso UI existente, conserva a escola e não declara IDs de aceitação.
O projeto separado prepara Fundação, dados originais completos, docente convidado e publicação validada.
As credenciais geradas ficam cifradas antes de criar as contas, permitindo recuperação administrativa posterior.
O gate recusa revisões diferentes, evidência não protegida, dados incompletos, publicação pendente e limpeza falhada.
Acrescenta metadados observados ao registo persistente assinado, sem substituir escolas anteriores.
Os testes provaram RED/GREEN do comando, gate, revisão antecipada e conservação atómica do histórico.
Passaram 92 contratos de infraestrutura, lint e Knip; Playwright recolheu uma preparação separada.
Este comando continua sem execução em produção. Não existem ainda escolas persistentes preparadas ou história elegível comprovada.

A composição histórica inclui agora decisão `GIVEN`, execução terminada pelo substituto e reversão com compensações explícitas.
O percurso confere os minutos exatos em parcelas semanais e no recibo líquido da ocorrência.
A reversão exige confirmação explícita e restaura os saldos iniciais, preservando a auditoria.
O login administrativo usa a credencial cifrada do fundador preparado pela UI.
Os seletores de registo conferem data, turma e intervalo, evitando escolher outra aula da mesma disciplina.
Passaram duas regressões backend destes percursos e os 61 contratos obrigatórios, com PostgreSQL e Redis isolados.

O fecho semanal seleciona uma semana realmente terminada, aberta e sem ocorrências, depois regista as aulas restantes pela UI.
Submete pelo docente, aprova pela direção e confere os campos bloqueados e a ausência de ações de edição.
Reabre por confirmação administrativa e confere novamente a edição disponível.
Cada transição preserva os IDs de registo, parcelas modulares, sumários, notas e progresso docente.
O inventário de escritas exige apenas os registos esperados e as três transições de estado.
Este percurso exige outra semana elegível; não altera o relógio nem cria história artificial.
Passaram duas regressões existentes de semanas v1 e os 61 contratos obrigatórios.
Lint, Knip e recolha Playwright passaram. Foram recolhidos 61 IDs distintos.
Estas verificações locais não certificam os percursos nativos em produção.

O verificador independente distingue agora história física de crédito planeado residual.
Exige origens observadas, preservação da história e das posições protegidas, sem contar crédito histórico duas vezes.
As reservas históricas entram na verificação de exclusividade de turma, docente e sala.
Uma aula parcial protegida pode anteceder a última aula editável; as regras das restantes aulas continuam iguais.
Sete testes Python passaram, incluindo RED/GREEN para estas regras de reparação.
A leitura materializada expõe origem, estado operacional e minutos efetivos por atribuição e módulo.
Reutiliza a projeção existente do ledger e mantém filtros explícitos de escola e ano.
A regressão API observou execução real e compensação na base isolada, sem arredondamento dos minutos.
Passaram essa regressão e os 61 contratos backend; Ruff e a verificação de formatação também passaram.
O manifesto persistente conserva agora o ID observado da proposta aprovada, necessário para reler a baseline materializada.
O gate recusa ausência ou valor inválido desse ID. Os 18 contratos selecionados provaram RED/GREEN e preservação do registo.
A composição seguinte liga os quatro casos E2E-13; não comprova reparação em produção.
Cria uma interrupção futura pela UI, fora da fronteira protegida, e exige uma proposta de recuperação completa.
Reutiliza geração, paginação e aprovação; valida história e crédito residual antes de publicar.
Depois confere a versão publicada, os minutos efetivos e os registos históricos do docente.
O inventário exige apenas criação do evento, geração e aprovação, sem comandos de negócio por API.
A consulta da proposta ativa suporta campanhas consecutivas sem reler uma versão antiga.
Essa referência passou RED/GREEN no contrato API, juntamente com os 61 contratos backend.
A conversão independente associa atribuições curriculares pelos recursos reais; não presume igualdade com IDs das relações importadas.
A regressão demonstrou RED/GREEN quando esses IDs diferem. Os oito testes de conversão passaram.
Lint, Knip e recolha Playwright passaram, com 65 IDs distintos.
Continua em falta a proteção histórica nessa alteração de ano.

### Contacto entregue ao destinatário original

O caso `E2E-16/contact-delivered` percorre o questionário público com respostas identificadas pela execução.
O browser espera pelo token do widget Turnstile real; não injeta tokens nem altera respostas.
O token observado entra no registo privado antes da submissão.
O teste exige um único POST nativo, HTTP 204 e o ecrã de receção.
Depois observa a mensagem entregue através do encaminhamento autorizado para a caixa Gmail dedicada.
O leitor exige To original, Delivered-To autorizado, Reply-To da execução, remetente, intervalo e todos os sete campos.
O marcador limita a pesquisa às mensagens da execução.
O destinatário global permanece `contacto@cronos.pt`.
O contrato teve RED por rejeitar esse destinatário; oito testes Gmail passaram após a implementação.
Os 95 testes de infraestrutura passaram; lint e Knip passaram.
A recolha confirmou 67 IDs válidos, distintos e pertencentes à matriz.
O encaminhamento, OAuth e Turnstile em produção permanecem por verificar.

### Exportação protegida antes da eliminação pela UI

O dry-run existente verifica titularidade, mas não produz cópias de segurança.
O wrapper aceita agora `--export-only`; esta opção não pode ser combinada com `--execute`.
A exportação reutiliza as verificações de proveniência, membros atuais, jobs e a cifragem existente.
O resultado `exported` mantém todos os alvos de eliminação pendentes.
O transporte exige cópias autenticadas de todos os alvos exportados e rejeita resultados de eliminação neste modo.
Este contrato passou de RED para GREEN em Node e Python.
Passaram nove testes do adaptador e 20 testes backend, com 31 subtestes de titularidade.
Ruff passou e os 97 testes de infraestrutura passaram.
Os casos de eliminação nativa e história protegida continuam pendentes.
Não foi executada exportação ou eliminação em produção nesta verificação.

### Titularidade autenticada na cópia anterior à eliminação

A cópia de organização inclui agora a observação de titularidade capturada sob o bloqueio administrativo.
O recibo `e2e_ownership` fica dentro do ZIP cifrado; não altera as linhas originais da aplicação.
A recuperação autentica AES-GCM, manifesto, inventário, contagens, hashes e o âmbito da execução e organização.
São rejeitados tags alterados, execuções estrangeiras, organizações diferentes e tabelas com manifesto incoerente.
Os dois testes novos tiveram RED por faltar esta observação e recuperação.
Passaram 22 testes backend, com 31 subtestes, após a implementação.
O recibo não substitui a confirmação da eliminação no Clerk.
A integração da reconciliação e os dois casos E2E-18 continuam pendentes.

### Reconciliação backend após eliminação nativa

O wrapper aceita cópias anteriores apenas para alvos descartáveis do mesmo registo assinado.
Autentica o ZIP e valida a titularidade completa antes de abrir a ligação administrativa.
Só um 404 Clerk permite recuperar a observação anterior; 401, 403 e 500 continuam a falhar.
Confere contas locais, emails e datas reais dos atores e jobs atuais, novamente sob o bloqueio da organização.
Antes de apagar dados locais, conserva a cópia anterior intacta e evita repetir a eliminação no fornecedor.
Os testes novos tiveram RED por faltar o reconhecimento condicionado e a entrada das cópias anteriores.
Passaram 30 testes backend, com 31 subtestes de titularidade; Ruff passou.
O transporte browser/SSH dessas cópias e os dois casos E2E-18 permanecem pendentes.
Esta prova isolada não certifica reconciliação ou eliminação em produção.

### Eliminação descartável pela UI e transferência da cópia anterior

O caso `E2E-18/disposable-school-deletion` seleciona a segunda escola criada pela UI nesta execução.
A composição verifica a organização ativa, o fundador e o tipo descartável antes de exportar.
Um registo assinado limita a exportação administrativa à escola selecionada.
O teste exige a cópia protegida antes de abrir os controlos de eliminação Clerk.
Confere o bloqueio da confirmação vazia ou incorreta, escreve o nome e envia o DELETE nativo.
Confere HTTP 200, ausência da organização nos membros e preservação do catálogo completo da primeira escola.
O runner transfere a cópia autenticada por SSH para a reconciliação final.
A cópia deve regressar com bytes idênticos; uma substituição ou alteração local impede aceitação.
Os testes do transporte tiveram RED antes da implementação; 46 testes selecionados passaram após GREEN.
Passaram os 99 testes de infraestrutura, lint e Knip.
A recolha confirmou 68 IDs distintos, válidos e pertencentes à matriz.
Naquele lote, o caso `E2E-18/protected-history` permanecia por implementar.
Não foi executada esta eliminação nem a sua reconciliação em produção.

### Feedback de uma resposta tardia entre escolas

O caso `E2E-14/stale-feedback-blocked` inicia um download nativo na primeira escola.
Chrome suspende a resposta real no estágio `Response`; o teste exige HTTP 200.
O teste seleciona a segunda escola pela UI antes de continuar a resposta original.
Nenhum status, header ou conteúdo é substituído.
O download deve preservar os bytes observados antes da troca.
Um observador DOM deteta também feedback que aparece apenas durante um instante.
O toast da primeira escola não pode aparecer na segunda.
Uma resposta cancelada ou perdida não passa esta prova.

Os testes locais do chamador conferem sucesso e erro tardios após mudar a organização.
Onze testes de importação e contexto passaram; o lint dos três ficheiros alterados passou.
Chrome próprio headless confirmou a pausa HTTP real e a continuação com bytes inalterados.
A recolha Playwright confirmou 66 IDs distintos, sem erros.
Esta verificação local do mecanismo não certifica a seleção Clerk nem o percurso em produção.

### História real preservada durante a mudança de ano

O percurso descartável agora conserva a testemunha da ocorrência criada e revertida pela UI.
A proposta materializada deve conter essa aula com registo `REVOKED` e fatias curriculares não vazias.
O teste compara todas as aulas antes do reset, depois do reset e depois das novas datas.
Compara versão, referências, intervalos físicos, fatias curriculares e estados dos registos.
Os créditos líquidos também devem permanecer iguais; esta escola ainda não executou aulas futuras.
Uma história vazia, desconhecida ou alterada falha o teste.
A prova inclui os três snapshots e a testemunha operacional, protegidos pelo finalizador existente.

O teste puro falhou por ausência da validação e passou após a implementação mínima.
Os nove testes de expectativas independentes passaram; o lint dos ficheiros alterados passou.
A recolha Playwright confirmou 69 IDs distintos e zero erros.
A campanha real, a história de aulas terminadas e os gates finais continuam pendentes.

### Verificação local do lote completo

`npm run verify` terminou com código zero: 88 ficheiros e 592 testes de produto passaram.
Lint, Knip, contratos, infraestrutura de aceitação, assets, cobertura e build também passaram.
A comparação da recolha com a matriz confirmou 69 IDs, sem casos desconhecidos nem casos em falta.

A execução backend recolheu 906 testes unitários: 905 passaram e um falhou.
O caso de 12 turmas devolveu `INCONCLUSIVE` após esgotar o orçamento curto de construção.
Esse teste agora usa a política de produção já aplicada ao caso de 48 turmas.
Mantém completude, validação independente e conclusão anterior à data preferencial.
O caso corrigido passou com cobertura em 8,48 segundos.
Na repetição, os 906 testes unitários passaram; o JUnit inclui também 31 subtestes, sem falhas nem erros.
A repetição completa terminou com código zero: 454 testes de integração e 61 contratos também passaram.
A cobertura backend foi 82%; o gate crítico de `constraint_policy.py` atingiu 100%.
Os audits de migrations, triggers e integridade permanecem obrigatórios na CI antes da entrega.
Os 12 testes independentes de CSV e horários passaram.

A revisão restringiu as permissões dos registos privados criados pela CI com `umask 077`.
Uma verificação em Linux confirmou diretórios `0700` e ficheiros `0600`.
Os 26 testes dos contratos do runner passaram após essa alteração.
Estes resultados locais não certificam produção.

### Revisão de qualidade após publicação da branch

A [PR 55](https://github.com/ORIOP25/Cronos/pull/55) permanece em draft.
Os três jobs de CI passaram no commit `9a0821d4cc76fb8158c3c629d2a0bfb7167d2f70`, no push e na PR.
O Sonar rejeitou as classificações de segurança e fiabilidade do código novo.
A entrega permanece pendente até corrigir ou justificar os problemas com provas.

O parser Gmail agora exige um endereço completo por token.
O teste reproduziu a aceitação incorreta de um destinatário com sufixo inválido antes da correção.
Também confere um endereço válido após um cabeçalho longo, sem limiares de tempo.
Os nove testes Gmail e o lint passaram.
O preflight escreve detalhes no relatório; stdout contém apenas estado controlado e localização.

A CI de aceitação instala o binário Railway oficial `5.62.1` após verificar o SHA-256 fixado.
Uma verificação Linux confirmou o digest do arquivo e a versão do executável.
Os 101 testes de infraestrutura de aceitação passaram neste lote local.
O diagnóstico Sonar privado respondeu HTTP 401 ao secret existente no runner.
O passo temporário falhou nessa consulta e foi removido; os gates originais permanecem obrigatórios.
A revisão continua pelas anotações nativas disponíveis, sem declarar resolvidas as classificações C e E.

O exportador administrativo agora rejeita componentes `..` antes de criar diretórios ou ficheiros.
O novo teste falhou antes da correção; os 22 testes do wrapper passaram depois.
O transporte SSH continua a criar o destino num diretório temporário próprio.
As identidades assinadas continuam limitadas a IDs de organização numéricos e IDs Clerk sem separadores.
A resposta administrativa também rejeita um ator declarado removido e pendente em simultâneo.
O teste reproduziu a contradição antes da correção; os 12 testes do transporte passaram depois.
Nenhum efeito remoto nem export local é certificado a partir dessa resposta contraditória.
A revisão separa configuração, resultados, autenticação de backups, leitura anterior e persistência do transporte SSH.
As validações de resultados e envelopes continuam puras; operações de ficheiros permanecem nos adaptadores.
Os 102 testes de infraestrutura passaram após a extração, sem novos efeitos de produção.
A expectativa independente agora rejeita datas preferenciais inválidas ou fora do horizonte escolar.
Os casos negativos falharam antes da correção; os nove testes de expectativas passaram depois.
Esta validação usa o helper independente de datas, sem importar schemas ou regras do produto.
A CI censura as passwords aleatórias antes de as publicar no ambiente dos passos seguintes.

O check nativo Cloudflare revelou os IDs reais da conta e do projeto.
Os dois secrets correspondentes estão configurados.
Na primeira consulta, o token Cloudflare disponível estava expirado.
A revisão do preview coincide com o commit publicado; a resposta de produção não comprova essa revisão.

### Acessos reais e preparação inicial

O proprietário forneceu o cliente OAuth Desktop e um novo token Cloudflare.
O script existente confirmou os perfis Gmail das duas contas após os consentimentos readonly.
Guardou os refresh tokens nos secrets GitHub; não imprimiu nem guardou tokens locais.
Os quatro secrets Gmail estão configurados e os dois scripts terminaram com código zero.

O novo token Cloudflare respondeu HTTP 200, com estado `active`.
A consulta autenticada do projeto Pages também respondeu HTTP 200.
O secret usado pelo workflow é `E2E_CLOUDFLARE_API_TOKEN`.
A listagem real rejeitou `per_page=100` com HTTP 400.
O adaptador agora usa a paginação padrão aceite; a consulta real devolveu 25 deployments.
O teste reproduziu a rejeição antes da correção; os quatro testes de deployments passaram depois.
O deployment de produção mais recente mantém o SHA `91a9d28bcb9c9a829a8578872156a6b90fa04bcf`, com estágio `deploy` concluído.
A resposta `https://cronos.pt/revision.json` foi HTTP 404; o alinhamento final continua pendente.

A consulta Clerk autenticada confirmou a instância de produção e o domínio `cronos.pt`.
Os templates `verification_code` e `reset_password_code` são entregues pelo Clerk.
A API consultada não devolveu os remetentes desses templates; a configuração do leitor permanece pendente de observação.

O workflow permite dispatch manual `prepare-history` sem ativar a campanha completa.
Ambos os modos exigem o ref `main` e preservam os gates de revisão, Gmail, proteção e limpeza.
O novo teste do gate falhou antes da correção.
A preparação continua sem execução real; esta opção não certifica uma escola nem história operacional.

No commit `5a78e925c8f920e8c2372a5720a5461345e1b009`, os três jobs passaram no push e na PR.
No commit `763eeac4f78268ac3f0b2012bc855cd14bdbac1b`, os três jobs também passaram no push e na PR.
O gate Sonar continua rejeitado; campanha real, história operacional e entrega final permanecem pendentes.

### Proteção partilhada dos exports e revisão de responsabilidades

O teste do export de privacidade reproduziu a aceitação de componentes `..` antes da correção.
Um segundo teste Linux confirmou que o ZIP era criado com permissões `0644`.
Os dois exportadores agora reutilizam a criação privada e exclusiva de ficheiros.
A política rejeita parent traversal e diretórios simbólicos; mantém permissões `0600` e diretórios novos `0700`.
O teste também confere o conteúdo integral do arquivo e recusa sobrescrever um export existente.
Os 26 testes do wrapper passaram após a correção; Ruff passou nos três ficheiros backend alterados.

O leitor independente separa recursos CSV, disciplinas, professores e atribuições em funções puras.
Os 12 testes independentes passaram antes e depois da refatoração, sem alterar bytes, contagens ou critérios.
A recuperação do backup separa a autenticação do envelope da validação das tabelas do ZIP.
A integração com PostgreSQL e Redis reais passou: 15 casos de limpeza e os 61 contratos obrigatórios.
A política de timestamps rejeita dias impossíveis que JavaScript normalizava silenciosamente.
O teste reproduziu aceitação de 30 de fevereiro antes da correção.
A política também recusa IDs com traversal, separadores ou valores não textuais.
O novo teste reproduziu a certificação indevida antes da correção.
Os oito testes da política passaram, incluindo um dia bissexto válido com offset UTC explícito.
O diagnóstico do Chrome próprio observou um iframe de desafio Cloudflare e nenhum input de verificação.
Não observou pedidos de criação de conta nem uma sessão autenticada; o remetente permanece por observar.
A campanha real e o gate Sonar continuam pendentes.

### Verificação pelo plugin Cloudflare

O plugin autenticado confirmou a conta do proprietário e a zona ativa `cronos.pt`.
O Email Routing está desativado, com estado `unconfigured`; não existem destinos verificados.
Os MX do domínio apontam para `mx1.hostinger.com` e `mx2.hostinger.com`.
O MX de `send.forms.cronos.pt` pertence ao envio Amazon SES e não recebe a caixa de contacto.
O encaminhamento deve ser configurado na Hostinger; os MX e a entrega existente foram preservados.
A conta contém dois widgets Turnstile do contacto, ambos em modo `managed`.
A listagem de rulesets não revelou uma regra personalizada de desafio para o registo.
A documentação Cloudflare declara que browsers automatizados não são suportados para resolver desafios de produção.
A resolução manual noutro browser não comprova aceitação autónoma na CI.

A verificação backend integral terminou com código zero: 911 unidades, 454 integrações e 61 contratos.
O gate de cobertura passou com 82%; a política crítica do scheduler manteve 100%.
Ruff e a limpeza da stack própria passaram.
Os 106 testes da infraestrutura de aceitação passaram após a refatoração da política pura.
Estes resultados não certificam a campanha de produção ainda pendente.

### Gate de qualidade da PR 55

O check `SonarCloud Code Analysis` da PR 55 falhava em duas condições no código novo: fiabilidade e segurança.
Na revisão de 2026-10-08, a fiabilidade estava em `E` e a segurança em `C`, com 4 bugs e 6 vulnerabilidades.

As correções provadas eliminaram os quatro bugs: o intervalo de datas usa um cursor numérico que avança de dia,
e os dois validadores de caminhos deixaram de conter uma sequência de escape de controlo.
Os testes das expectativas independentes e dos contratos do runner passaram após as alterações.

O caminho de exportação administrativo foi canonicalizado com `os.path.realpath` depois de rejeitar traversal e
diretórios simbólicos; a lista de vulnerabilidades caiu para quatro falsos positivos de ferramentas administrativas de CLI.
Cada um foi revisto e transicionado com um comentário registado no SonarCloud: os três `pythonsecurity:S8707` como riscos
aceites (o operador escolhe o caminho, não há entrada não fidedigna, e o destino é validado e canonicalizado antes de
qualquer escrita ou remoção) e o `yaml:S2068` do `ci.yml` como falso positivo (a palavra-passe é gerada em execução com
`openssl rand`, mascarada e nunca armazenada).
Após a revisão, o gate da PR 55 respondia `OK`: fiabilidade, segurança e manutenibilidade em `A`.

O projeto SonarCloud não recebia análises desde junho; a branch principal mantém um passivo histórico de avisos
antigos fora do âmbito desta iniciativa. A análise automática atualiza-se com cada push da PR.

### Publicação, alinhamento e ativação

A PR 55 foi fundida na `main` em squash como `c850235807475d83149e2b7220e144f63d3354d0`, com autorização explícita do proprietário.
A CI da `main` passou nos três jobs nesse commit.
O gate Sonar da PR passou (`OK`, ratings `A`) e o `Cloudflare Pages` publicou o frontend.

A produção ficou alinhada na revisão fundida: `/revision.json` respondeu `c850235...` com `verifiable: true`,
e `/health/ready` respondeu `ok` com PostgreSQL e Redis ligados na mesma revisão.
No Railway, `api`, `worker` e `beat` atualizaram pelo evento de publicação; o `scheduler-supervisor` não tinha deploy automático
e foi publicado para o commit explícito através da API, ficando os quatro serviços `SUCCESS` na revisão fundida.

No momento desta publicação, a variável `E2E_ACCEPTANCE_ENABLED` estava ativa; a campanha corria no SHA da `main` e a preparação preservou o modo manual.
A leitura atual mostra `E2E_ACCEPTANCE_ENABLED=false`; a secção de continuação regista esta correção.
A PR 60 acrescenta o modo `protect` ao CLI de evidências e protege os registos atualizados da preparação antes do upload,
para que a escola persistente e o registo privado possam ser recuperados com a chave de artefactos.
Quatro testes Node cobrem a escrita exclusiva, a recusa de sobrescrita e a recuperação autenticada.

O diagnóstico aos dois mailboxes dedicados não encontrou nenhuma mensagem do Clerk; só existem mensagens do Google.
O remetente de produção do código de verificação permanece por observar e tem de ser lido no painel do Clerk.
Sem esse valor, `prepare-history` e os percursos de identidade falham antes do registo; o desafio de bot na página pública
também não é resolúvel por um browser automatizado na CI.

## Continuação — checkpoints por caso e recuperação real do worker

As secções anteriores mantêm-se como registo histórico. Esta secção descreve a continuação local atual.
No início desta continuação, o checkout era local e o diff ainda não estava publicado nem executado pela CI.

O reporter usa agora checkpoints explícitos por caso, em vez de anotações automáticas.
Historicamente, o reporter anexava uma prova por anotação de caso; essa anotação não era prova de execução.
Cada checkpoint declara IDs concretos, provas materializadas e a proveniência de UI observada.
O schema `PROOF_SCHEMA_VERSION = 2` exige instantes UTC exatos e recusa provas sem evidência.
Um teste aprovado sem o checkpoint do seu caso permanece incompleto.
Um checkpoint não reclamante partilha a janela de observação e o início com o checkpoint seguinte do mesmo bloco.

A raiz das provas é a pasta de saída configurada do projeto; o reporter recebe a mesma raiz.

A proveniência de uma escola persistente exige o ator Clerk vivo e a organização ativa iguais aos assinados.
A observação nunca escreve o ator antigo como registo novo.

Os corpos de prova não JSON são materializados como binários (`.bin`), com os bytes originais.
A ordem da assinatura final foi corrigida: as falhas primárias ficam dentro do payload assinado.
O finalizador regista a fase que falhou e preserva a falha primária, impedindo `validated` falso.
Os registos persistentes e privados da preparação são protegidos antes do upload, dentro de `finalizeRun`.
A promoção da escola persistente só ocorre depois de uma primeira avaliação `prepared`.
Uma falha de promoção entra nas falhas assinadas e mantém a preparação falhada.

A recuperação de worker passa a terminar um processo Celery próprio real.
O teste bloqueia a transação de persistência numa lock PostgreSQL só de teste, ligada ao PID detentor.
O teste confirma que o worker próprio está bloqueado, mata-o e liberta a lock.
Um supervisor próprio separado consome a mensagem real `scheduler.v1.supervise` no Redis.
O supervisor reconcilia a tentativa abandonada para `FAILED/WORKER_STALLED`, sem proposta nem versão.
O ensaio não deixa recursos de teste: a limpeza removeu 0 recursos sobrantes.

Passaram 9 casos deste ficheiro e 61 contratos backend.

### Verificação local desta continuação

A nova `npm run verify` terminou com sucesso até ao build: 592 testes de produto em 88 ficheiros e 74,06% de cobertura de statements.
A execução inclui 140 testes de infraestrutura, após o estágio e a prova explícita, e 13 testes diretos do edge worker.
Nenhuma remoção de testes foi executada; o cutover W09 continua bloqueado.
Estes resultados locais não certificam a campanha de produção.

A execução completa do backend está no artefacto aprovado `.test-artifacts/1791500097167-13744/run.json`.
Correu na revisão `99d752b` com a árvore suja, comando `all` e âmbito `backend`.
Terminou com código 0 e limpeza 0.
Passaram 1 434 casos: 911 unitários, 462 de integração e 61 contratos, sem falhas, skips ou erros.
A cobertura global foi 82% e a política crítica manteve 100%, conforme o relatório do worker revisto.

O frontend local foi reconstruído a partir da fonte temporária com o SHA exato do worker `aad548ef511f6dc5a10bcd8d50d07ff9fef627270bfb2258bc8f77daa40c93b3`.
Só o frontend foi recriado, com a imagem nova `3201ceb8...`, e respondeu HTTP 200 em `:5173`.
A etiqueta de rollback anterior foi conservada e o resto da stack permaneceu inalterado.

O fixture de W04.6 verifica agora os deployments vivos antes de cada um dos sete grupos de percursos e antes da preparação.
O instantâneo por grupo é seguro e entra no inventário final.
Nenhuma asserção de fornecedor vivo é afirmada a partir de testes unitários.

O dispatch nativo `prepare-history` correu em `main` `c850235`, como [run 37848687151](https://github.com/ORIOP25/Cronos/actions/runs/37848687151).
Terminou com código 3 e `Acceptance dependencies unavailable: E2E_GMAIL_CODE_SENDER`.
A falha ocorreu antes de qualquer ação de browser ou de negócio.
As chaves existem nos metadados do GitHub; nenhum valor foi lido.

A variável de repositório `E2E_ACCEPTANCE_ENABLED` está atualmente `false`, confirmada por `gh variable get`.
O workflow de aceitação permanece inativo para o modo de campanha; a ativação anterior fica como registo cronológico.

A [PR 60](https://github.com/ORIOP25/Cronos/pull/60) foi fundida em 2026-10-09T10:26:52Z como `ec7e2ccf2c3e499ca7eb3a8ed22f2ed84bf6bcbb`.
A CI final da PR [run 37916132020](https://github.com/ORIOP25/Cronos/actions/runs/37916132020) passou os três jobs, com Sonar e preview Cloudflare aprovados; a CI da `main` [run 37917656713](https://github.com/ORIOP25/Cronos/actions/runs/37917656713) passou.
A produção ficou alinhada em `ec7e2cc`: frontend e API mais os quatro serviços Railway `SUCCESS`, cada um com uma revisão ativa e não parada.
Numa repetição independente, os 9 casos reais do worker e os 61 contratos voltaram a passar, com limpeza 0.

Com a fusão, a produção deixou de mostrar o bug condicional 304: os 404 de assets já não aparecem nos erros.
O `prepare-history` autenticado continua bloqueado com código 3 pelo remetente em falta; os gates de contacto e história continuam por provar.
W11.4 continua não certificado no Railway.
Os quatro planos não estão concluídos e W09.5 permanece pendente.

### Estado anterior à fusão (histórico)

O push anterior `64e13bd` tem Sonar `SUCCESS` com duplicação 1,1 (< 3, inalterada) após o fixture partilhado `scripts/preparation-test-fixture.mjs`, e o preview Cloudflare passou; as CI de backend e E2E passaram no push e na PR.
A fonte frontend passou no push [run 37863829281](https://github.com/ORIOP25/Cronos/actions/runs/37863829281) mas a PR [run 37863833225](https://github.com/ORIOP25/Cronos/actions/runs/37863833225) falhou 1/592 em `FeedbackContext` por metadados lazy de marketing em falta e `members/me` sem tratamento.
A causa raiz é uma folha de fixture irrelevante e o acerto de mocks numa fronteira assíncrona; a correção é só no ficheiro de teste.
Os 67 testes relacionados em 7 ficheiros passaram independentemente e o `npm run verify` do worker passou 592, sem alterar MSW estrito, consola ou metadados de produto.

O novo modo `diagnose-public` corre quatro casos explícitos só de leitura e compara os cinco componentes antes, por grupo e depois, com SHAs completos iguais, HMAC+AES protegidos e diário vazio, sem Gmail, história, SSH ou negócio; os gates de aceitação e preparação não mudam.
A avaliação assinada do diagnóstico permanece incompleta e só o resumo derivado seguro é carregado, nunca a execução bruta; os testes locais de modo, leitura e erro de processo passaram (57 focados), sem modo público em produção.
O trigger da CI foi otimizado para `push` só na `main`, todas as PRs e `workflow_dispatch` manual para branches sem PR, mantendo jobs, auditorias, cobertura e condições de fork.

### Estado após a fusão da PR 60 (histórico)

O workflow público só de leitura [run 37919213244](https://github.com/ORIOP25/Cronos/actions/runs/37919213244) correu após o alinhamento com quatro casos, um worker e zero retries; as quatro asserções principais e as verificações de fornecedor passaram, mas os testes falharam apenas no script injetado `static.cloudflareinsights.com/beacon.min.js/v...` bloqueado por CSP, os 404 de assets já não aparecem nos erros, e os artefactos protegidos foram carregados com o trace de falha cifrado pelo workflow existente, sem afirmar decifragem manual.
A correção local de W03.7 restringe a exceção ao script observado com GET, host HTTPS exato, caminho de versão hexadecimal e gramática CSP ancorada, cobre navegação, novos pedidos e invalidação por resposta, e nunca isenta 4xx/5xx servidos, API, Clerk, pedidos não observados ou acrescentos de texto; a telemetria ignorada é só metadados e a CSP não muda.
Passaram os 19 testes de runtime e os 32 guards determinísticos mais recentes; uma sonda local respondeu 200 ao contacto mas não injetou o beacon, pelo que a ordenação da CI continua por verificar e não há prova falsa.
Naquele momento, a correção de W03.7 estava por publicar e aguardava um checkpoint de CI; o remetente E2E em falta mantinha o bloqueio total e não havia remoção de testes.

### Estado após a fusão da PR 61 (histórico)

A [PR 61](https://github.com/ORIOP25/Cronos/pull/61) foi fundida como `7be9ee1bee1c73b46af0b7353b29ab96e6d386c3`.
A CI da PR [run 37925178812](https://github.com/ORIOP25/Cronos/actions/runs/37925178812) passou os três jobs, com Sonar e preview Cloudflare aprovados.
A CI da `main` [run 37928274790](https://github.com/ORIOP25/Cronos/actions/runs/37928274790) passou.
Os cinco componentes de produção ficaram alinhados em `7be9ee1`.
Os quatro serviços Railway ficaram `SUCCESS`, não parados e com uma revisão ativa.
A revisão do frontend coincide e `/health/ready` responde `ok`.

O diagnóstico público real [run 37935721500](https://github.com/ORIOP25/Cronos/actions/runs/37935721500) falhou nos quatro casos apenas por consola precoce de CSP Cloudflare.
O `requestfailed` de rede é agora classificado como ignorado seguro e estreito.
As asserções de UI, assets e revisões passam.

Os registos mostram que a consola do Chrome chega antes do pedido.
Um Chrome real instalado localmente reproduziu o script bloqueado por CSP: consola, depois GET do script, depois `requestfailed` por CSP.
A correção causal do getter continua por publicar; passaram 25 testes Node e 33 guards, com lint limpo.
A correção registra cada evento de consola duplicado e mantém o erro pendente visível até existir o GET correspondente com falha CSP.
A navegação principal, as respostas reais e o flush de pedidos não-GET foram confirmados e nunca apagam o erro.
Não houve novas alterações de CSP, anti-bot, autenticação ou dados.

A revalidação pública real continua necessária após a publicação.
O remetente Gmail do código, o encaminhamento do contacto, a história de W09 e o cutover da CI continuam bloqueados.

### Estado atual — consentimento e diagnóstico público (aa5ab8b)

A CI nativa [run 37949419112](https://github.com/ORIOP25/Cronos/actions/runs/37949419112) passou os três jobs; frontend 598, backend 1434, legado 88 e capacidade verdes.
Os cinco componentes ficaram alinhados em `aa5ab8b`; os quatro serviços Railway ficaram `SUCCESS`, um ativo e não parado, com `/health/ready` `ok`.
O diagnóstico público real [run 37951385146](https://github.com/ORIOP25/Cronos/actions/runs/37951385146) passou os quatro casos à primeira tentativa.
O relatório assinado tem as cinco revisões iguais antes e depois, sem falhas, e provas protegidas.
A limpeza é `public_readonly` com `not_needed=true` e listas pendentes vazias.
O estado derivado é `passed` com `certifies_production=false`; a avaliação completa fica `incomplete` e `data_verified=false`.
Logo, não certifica os 69 casos nem prova remoção de testes.
O coordenador inspecionou JSON não secreto; não se afirma verificação HMAC nem decifragem local.
Passaram 25 testes de runtime, 33 guards e 31 de rota assíncrona, com CSP e consentimento controlados.
Nenhuma alteração de CSP de produto, anti-bot, autenticação ou dados foi feita.
O From real deve ser observado no painel ou em mail recebido; a variável GitHub `E2E_GMAIL_CODE_SENDER` deve então ser configurada.
O inventário Railway observado contém apenas produção; W11.4 exige ambiente isolado legítimo, sem novo custo sem autorização.

### Diagnóstico público parcial e correção do 304 (histórico)

Um diagnóstico público parcial correu num Chrome headless isolado contra a produção `c850235`, com o test HEAD `99d752b` num checkout sujo.
As asserções de rota pública, canonical, documentos legais, 404 e teclado passaram.
Os quatro testes de runtime gate falharam com 404 nos assets versionados.
O diagnóstico não é `validated` nem comprova um caso aprovado.
Vinte corpos e traces foram cifrados; não existe binário em texto simples nos artefactos.

A sonda HEAD pública de `/logo.png` e `/favicon.png` respondeu 200 com ETag na produção `c850235`.
A revalidação condicional seguinte devolveu 404 na mesma produção.
O edge worker tratava `304 Not Modified` como `!ok` e servia o documento HTML 404.
O teste local reproduziu 404 em vez de 304 antes da correção.
Depois da correção, os 13 testes do edge worker passaram.
Com a fusão da PR 60, a correção está em produção; não se afirma causa única nem redeploy.

### Procedimento de verificação desta continuação

Execute a verificação de produto:

```powershell
cd frontend
npm run verify
```

Execute a infraestrutura de aceitação atualizada:

```powershell
cd frontend
npm run test:acceptance-infrastructure
```

Execute a recuperação real do worker e os contratos:

```powershell
node scripts/test.mjs integration -- -k test_an_owned_worker
```

## Plano de fecho acelerado

| Ordem | Grupo | Dependências | Concluído observável |
| :--- | :--- | :--- | :--- |
| 1 | Observar o From real e configurar a variável GitHub | Nenhuma | From observado (painel ou mail recebido) e `E2E_GMAIL_CODE_SENDER` configurada. |
| 2 | Preparar a escola pela UI o quanto antes | 1 | Cinco CSV completos, docente, geração publicada e assinada, início futuro preservado. |
| 3 | Encaminhamento Hostinger e desafios legítimos | Paralelo a 2 | Entrega de contacto observada e desafio anti-bot legítimo concluído. |
| 4 | Percursos elegíveis, revisão de regressões e W11.4 isolado | Nenhuma para auditoria/W11 isolado; 2 para jornadas | Regressões revistas; W11.4 isolado com recursos próprios. |
| 5 | Aula terminada real e primeira semana letiva completa | 2 e calendário real | W07 com sumário, minutos exatos e fecho semanal; não duas semanas, data real condicional. |
| 6 | Matriz completa de 69 casos e limpeza | 3 e 5 | 69 casos validados com limpeza por execução. |
| 7 | Redução segura W09 e helpers W10.8 | Prova substituta de cada grupo | Nenhuma remoção antes da prova substituta; cutover de CI. |
| 8 | Verificação final W12 e documentos | 1–7 | Quatro planos reconciliados e checks finais. |

W09.1–4 mantêm o núcleo essencial e o Knip já verificado na CI; não repetir.
Cada grupo avança apenas com as suas dependências comprovadas.

## Fontes e documentos relacionados

- [Política de aceitação](../../frontend/e2e/utils/acceptance-policy.js)
- [Checkpoints e proveniência das provas](../../frontend/e2e/utils/acceptance-proof.js)
- [Reporter](../../frontend/e2e/acceptance-reporter.js)
- [Preflight](../../scripts/real-browser-preflight.mjs)
- [Proteção e recuperação](../../scripts/protect-test-evidence.mjs)
- [Finalização e verificação dos artefactos](../../scripts/finalize-real-browser-run.mjs)
- [Runner e composição da preparação](../../scripts/test.mjs)
- [Recuperação real do worker](../../backend/tests/integration/committed/test_worker_process_recovery.py)
- [Edge worker](../../frontend/public/_worker.js)
- [Testes do edge worker](../../frontend/scripts/edge-worker.test.mjs)
- [Workflow de aceitação](../../.github/workflows/acceptance.yml)
- [Verificação independente do horário](../../scripts/validate-e2e-schedule.py)
- [Política de limpeza](../../backend/scripts/e2e_cleanup_policy.py)
- [Wrapper administrativo](../../backend/scripts/cleanup_e2e_run.py)
- [Transporte administrativo SSH](../../scripts/cleanup-production-campaign.mjs)
- [Guia de testes](TESTING_AND_CI.md)

## Observação readonly do remetente do código (metadata-only)

O remetente E2E do código continua por observar; `prepare-history` permanece bloqueado por `E2E_GMAIL_CODE_SENDER`.
A observação segura reutiliza o leitor readonly e pede apenas metadados.
Restringe-se a uma das duas caixas dedicadas e ao destinatário base ou alias autorizado.
A janela UTC é explícita: sete dias por omissão e 30 dias no máximo.
Uma janela acima de sete dias exige `E2E_INSPECT_WINDOW_REASON`.
As mensagens, as páginas e o tempo do pedido são limitados.
Lê apenas os cabeçalhos From, To e Subject; o subject é testado em memória.
Nunca imprime subject, código, corpo, cabeçalhos brutos, tokens, IDs de mensagens nem endereços dos aliases.
Devolve apenas `observed`, `incomplete`, `dependency_unavailable` ou `failed`, os remetentes distintos e a contagem, as datas limitadas e `certifies_production: false`.
Uma ambiguidade de remetentes, um remetente incompatível ou a ausência de mensagens termina com código não zero.
Não envia correio, não altera etiquetas, não autentica por API, não muda contas e não configura variáveis.
O preflight e o percurso de identidade partilham um validador puro, pelo que um remetente malformado falha antes de qualquer efeito.

Invocação local exata:

```powershell
node scripts/inspect-e2e-code-sender.mjs
```

O [workflow de aceitação](../../.github/workflows/acceptance.yml) disponibiliza `mode=inspect-code-sender` num job readonly dedicado.
Esse job corre apenas em `main` por `workflow_dispatch`, sem navegador, sem Railway e sem segredos administrativos, de deployment ou de provas.
Invocação manual exata:

```powershell
gh workflow run acceptance.yml --ref main -f mode=inspect-code-sender -f mailbox=admin -f purpose=verification
```

`purpose` é `verification` ou `reset`; `recipient` é opcional e aceita a base ou um alias autorizado.
O job expõe um único token de refresh da caixa escolhida (`E2E_GMAIL_REFRESH_TOKEN`), nunca as duas em simultâneo.
A evidência de metadados não autentica a origem do correio nem certifica a matriz de 69 casos.
Estes testes locais não certificam produção.
