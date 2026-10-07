# Implementação dos testes reais — registo de execução

Revisão: 2026-10-07. Estado: infraestrutura de aceitação implementada; aceitação de produção pendente de dependências externas.

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
A implementação foi publicada na branch; a CI passou em `4cc0a2d51069dc06f19cc689e4d8d68663ba0319`.
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

O Railway recusou criar tokens de projeto e de conta com `Not Authorized`.
Um token de projeto existente apresentou apenas uma representação que não autentica.
Não foi exportado como credencial válida.
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
Os 55 testes de infraestrutura passaram; `npm run verify` passou antes da última alteração do runner.
O contexto Docker exclui `.auth/`, que contém as credenciais locais.
Uma verificação da imagem real confirmou a ausência dessa pasta no estágio de build.
A imagem local foi reconstruída e o serviço frontend atualizado.
O comando de aceitação confirmou nove dependências em falta e terminou com código `3`, sem browser.

Os restantes 66 casos concretos ainda precisam de implementação ou adaptação e execução real.
Credenciais configuradas não substituem esses percursos.
Os quatro planos permanecem incompletos.

## Componentes e estado das tarefas

| Tarefas | Implementação observada | Prova restante |
| :--- | :--- | :--- |
| W00.1 | Baseline, branch isolada e preservação das alterações externas. | Nenhuma para esta preparação. |
| W00.2–4 | Inspeção dos consumidores e de parte dos acessos externos. | Inventário completo de regressões, contas, email e contacto. |
| W01.1–3 | Originais completos, manifesto e inspetor independente. | Conferir os resultados depois da importação pela UI. |
| W01.4–5 | Política pura exige produção, SHA completo e caixas dedicadas. | Ligar ao runner definitivo antes de qualquer efeito. |
| W02.1–6 | Helper OAuth com PKCE e leitor Gmail com testes focados. | Consentimentos reais, tokens e mensagens das duas caixas. |
| W03.1–2 | Matriz por caso concreto, avaliação pura e reporter estruturado. | Composição do runner e percursos reais com provas. |
| W03.3–5 | Redação de segredos curtos, AES-256-GCM, recuperação confinada e manifesto assinado dos ficheiros reais. | Registo dinâmico dos segredos durante os percursos e upload real protegido. |
| W03.6–7 | Guards observam erros da API e Clerk; verificações locais passaram. | Composição das falhas auxiliares e exceções por ação, método e caminho. |
| W04 | Adaptadores de revisão e writer da revisão frontend. | Publicar frontend e obter snapshot completo dos dois fornecedores. |
| W06.1–2 | Verificador independente de procura, crédito modular e recursos, com oito testes junto do inspetor. | Ligar às leituras autenticadas e aos resultados da geração real; conferir o horário completo. |
| W05 e W06.3–W08 | Percursos do plano permanecem pendentes. | Execução pela UI, persistência, scheduler e história real elegível. |
| W09 | Regressão do chamador corrigida com testes determinísticos. | Inventário e redução após provas substitutas; manter regressões únicas. |
| W10.1–3, W10.7 | Comando `acceptance` fail-closed, projeto Playwright em Chrome, workflow manual/`main` serializado, upload sanitizado em falha. | Executar a campanha real com os segredos e a matriz de percursos. |
| W10.4–6 | Registo HMAC, wrapper administrativo, exportação cifrada e erasure com bloqueio de jobs; canal SSH remoto respondeu. | Executar o wrapper remoto sobre o registo real produzido pela UI e comprovar eliminação real no fornecedor. |
| W11.1–3 | Recuperação com broker real e processo Celery próprio; entrega duplicada sem proposta adicional. | W11.4: repetir num ambiente Railway isolado quando a prova exigir o fornecedor. |
| W12 | Documentação e comandos reconciliados com o comportamento comprovado. | Campanha completa no SHA publicado e limpeza por execução. |

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
Uma falha conserva os alvos pendentes e não publica o texto da resposta do fornecedor.

O finalizador confere que cada referência de evidência existe depois da proteção.
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

## Fontes e documentos relacionados

- [Política de aceitação](../../frontend/e2e/utils/acceptance-policy.js)
- [Reporter](../../frontend/e2e/acceptance-reporter.js)
- [Preflight](../../scripts/real-browser-preflight.mjs)
- [Proteção e recuperação](../../scripts/protect-test-evidence.mjs)
- [Finalização e verificação dos artefactos](../../scripts/finalize-real-browser-run.mjs)
- [Verificação independente do horário](../../scripts/validate-e2e-schedule.py)
- [Política de limpeza](../../backend/scripts/e2e_cleanup_policy.py)
- [Wrapper administrativo](../../backend/scripts/cleanup_e2e_run.py)
- [Guia de testes](TESTING_AND_CI.md)
