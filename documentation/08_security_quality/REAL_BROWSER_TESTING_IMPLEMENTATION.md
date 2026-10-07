# Implementação dos testes reais — registo de execução

Revisão: 2026-10-07. Estado: implementação parcial; aceitação de produção pendente.

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
Não ocorreu push desta implementação nem campanha completa de aceitação.
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

A aprovação e rejeição de propostas ignoram erros tardios após troca de escola, logout ou desmontagem.
Os testes demonstraram a falha antes da correção.
O container frontend local foi reconstruído e atualizado com essa correção.

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
| W05–8 | Percursos do plano permanecem pendentes. | Execução pela UI, persistência, scheduler e história real elegível. |
| W09 | Regressão do chamador corrigida com testes determinísticos. | Inventário e redução após provas substitutas; manter regressões únicas. |
| W10.4–6 | Registo HMAC, wrapper administrativo, exportação cifrada e erasure com bloqueio de jobs; canal SSH remoto respondeu. | Executar o wrapper remoto sobre o registo real produzido pela UI e comprovar eliminação real no fornecedor. |
| W10 restante, W11 e W12 | Cutover e aceitação final permanecem pendentes. | CI, recuperação isolada, matriz completa e documentação final. |

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
Os 43 testes Node da infraestrutura de aceitação passaram após as últimas alterações.
Ruff passou nos ficheiros Python alterados.
Os testes focados de política, wrapper e contratos de privacidade passaram: 21 casos e 19 subtests.

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

O Railway recusou associar `/backend/railway/supervisor.json`, indicando que Config as Code foi descontinuado.
A associação não foi alterada.
O comando existente do supervisor coincide com o ficheiro revisto.

A API respondeu com a revisão baseline e PostgreSQL/Redis ligados.
O endpoint frontend `/revision.json` ainda respondeu 404 em produção.
O token Cloudflare disponível respondeu com estado `expired`.
Não foram encontrados os quatro valores OAuth Gmail exigidos pelo preflight.
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
- [Política de limpeza](../../backend/scripts/e2e_cleanup_policy.py)
- [Wrapper administrativo](../../backend/scripts/cleanup_e2e_run.py)
- [Guia de testes](TESTING_AND_CI.md)
