# PRD — Testes reais no browser e limpeza da suite

Revisão: 2026-10-07. Versão: 2.0.
Baseline de código: `91a9d28bcb9c9a829a8578872156a6b90fa04bcf`.
Responsável pelo produto: proprietário do Cronos.

## Objetivo e leitor

Este PRD reúne as decisões da entrevista anterior e atualiza a implementação prevista para a main atual.
Destina-se ao proprietário, implementadores e responsáveis pela publicação.
A CI deve comprovar percursos humanos completos no site publicado.
Ver uma página, um toast ou HTTP 200 não comprova o resultado.
Conferir persistência após recarregar ou abrir nova sessão.

## Pré-requisitos e estado atual

Os documentos anteriores não estavam no checkout nem no histórico Git consultado.
Esta revisão repõe o PRD e os quatro planos a partir das decisões desta conversa.
As correções de produto existentes são componentes reutilizáveis.
A aceitação em produção permanece por implementar.
Configuração de Gmail, Clerk, Cloudflare e Railway permanece por verificar.
Não assumir que uma escola atual pertence aos testes.

## Âmbito e decisões

| Tema | Decisão |
| :--- | :--- |
| Ambiente decisivo | Produção em `https://cronos.pt`, com frontend Cloudflare Pages e backend Railway. |
| Browser | Google Chrome desktop, `channel: 'chrome'`. Sem mobile, Firefox ou WebKit nesta fase. |
| Executor | Runners GitHub Actions alojados pelo GitHub; não abrir browsers no PC nas campanhas normais. |
| Ações de negócio | Executar pela interface, com autenticação, email, persistência, filas e solver reais. |
| APIs auxiliares | Apenas provas de leitura, identificação de deployments e limpeza limitada. |
| Autenticação | Usar métodos apresentados. Excluir helpers, tokens de teste e tickets de login fabricados por API. |
| Email | Mensagens realmente entregues, lidas via Gmail API readonly. |
| Dados | Usar sempre os cinco moldes completos fornecidos; não reduzir o conjunto. |
| Escolas | Combinar descartáveis e persistentes, construídas pela interface e identificadas por proveniência. |
| Publicação | Autodeploy da main; validar a revisão nos cinco componentes antes dos percursos. |
| Falha | CI vermelha, provas preservadas e recuperação decidida conforme a causa. Sem rollback automático. |
| Redução dos testes | Substituir toda a aceitação E2E antiga; remover redundância backend/frontend após prova substituta. |

Consentimento OAuth inicial e diagnóstico assistido podem exigir o browser local.
Não guardar segredos na conversa.
Um bloqueio Google, Clerk ou Turnstile deve conservar evidência e impedir aceitação verde.
Não usar bypass, CAPTCHA resolvido artificialmente ou reprodução assistida para apagar uma falha da CI.
Links de convite realmente recebidos pertencem ao percurso humano.

## Contas, dados e persistência

Usar `admincronos100@gmail.com` e `professorcronos100@gmail.com`.
Usar aliases exclusivos nas identidades descartáveis.
Conferir o estado atual das contas antes de as utilizar.
Não assumir que continuam vazias.

Os originais continuam em `C:\Users\Hp\Downloads` e foram lidos em 2026-10-07:

| Ficheiro original | Linhas de dados |
| :--- | ---: |
| `Folha de cálculo sem nome - Cronos_Salas_Template_Maior.csv` | 48 |
| `Cronos_ProfessoresECompetencias_Template_Maior.csv` | 72 |
| `Cronos_DisciplinasEModulos_Template_Maior.csv` | 208 |
| `Cronos_CursosETurmas_Template_Maior.csv` | 48 |
| `Cronos_Atribuicoes_Template_Maior.csv` | 336 |

Expectativas: 40 professores distintos, 52 disciplinas, quatro módulos por disciplina e 16 cursos.
Preservar os bytes, nomes, separadores e relações.
Salas usa vírgula; os restantes usam ponto e vírgula.
Gerar SHA-256 durante W01.1.
Expandir exigência curricular por turma/disciplina, sem confundir o total das disciplinas distintas com a procura escolar.

Preparar escolas persistentes cedo, com horários reais e proveniência UI.
Esperar pelo calendário real para sumários e fechos.
GAP futuro autorizado não é execução antecipada.
Não alterar relógio, retrodatá-lo ou inserir aulas antigas nos E2E.
Falta de estado elegível significa `incomplete`, não verde.
Preservar escolas e contas persistentes durante a limpeza.

## Percursos obrigatórios

Cada ID contém casos concretos com atores, estados e provas próprios.
Não esconder uma variante omitida atrás de um único teste com esse ID.

| ID | Percurso | Resultado exigido |
| :--- | :--- | :--- |
| E2E-01 | Registo e fundação | Registar fundador real, verificar email e concluir a organização pela interface. |
| E2E-02 | Login e logout | Provar métodos apresentados, identidade, saída e nova entrada de administrador/professor. |
| E2E-03 | Recuperação de acesso | Receber mensagem, mudar credencial e voltar a entrar; concluir o percurso. |
| E2E-04 | Convite e conversão | Enviar e aceitar convite entregue; preservar relações e isolamento da identidade pendente. |
| E2E-05 | Importação completa | Importar os cinco originais; conferir entidades, relações, relatórios e persistência. |
| E2E-06 | Recursos e disponibilidades | CRUD, arquivo autorizado, turma inicial e disponibilidades com efeitos persistidos. |
| E2E-07 | Configuração e preparação | Fundação, período, data preferencial, grelha, calendário e prevalidação reais. |
| E2E-08 | Geração completa | Confirmar geração, processar a fila e obter candidato completo dos dados fornecidos. |
| E2E-09 | Revisão e publicação | Rever proposta, aprovar/rejeitar nos casos concretos, conferir horários e progresso em nova sessão. |
| E2E-10 | Sumários e execução | Usar aulas terminadas; conferir minutos, repetição e proteção contra execução antecipada. |
| E2E-11 | Ocorrências e substituições | Conferir decisões, reservas, execução substituta, dívida original, reversões e diagnósticos. |
| E2E-12 | Fecho semanal | Completar, submeter, aprovar e reabrir semanas; conferir bloqueios operacionais. |
| E2E-13 | Reparação e histórico | Reparar alterações futuras; preservar origem, história e cobertura residual. |
| E2E-14 | Várias organizações | Alternar escolas diferentes; impedir mistura de dados, cache ou feedback. |
| E2E-15 | Permissões | Impedir funções e dados administrativos ao professor; verificar ausência de efeitos. |
| E2E-16 | Percursos públicos | Navegação, legal, contacto entregue, 404, segurança e acessibilidade no site publicado. |
| E2E-17 | Guia e tutorial | Concluir/retomar guia e manter tutorial separado do estado operacional. |
| E2E-18 | Ano escolar e eliminação | Executar ações autorizadas em escola descartável; preservar história e isolamento. |

## Requisitos técnicos e operacionais

| ID | Requisito | Critério |
| :--- | :--- | :--- |
| NFR-01 | Destino real | Exigir https://cronos.pt; recusar fallback local ou outro destino na aceitação. |
| NFR-02 | Chrome real | Instalar Google Chrome desktop e usar channel: 'chrome' em GitHub Actions. |
| NFR-03 | Sem atalhos | Excluir mocks, auth programática, tickets fabricados e preparação de negócio por API. |
| NFR-04 | Versão comprovada | Exigir revisão do frontend, API, worker, supervisor e Beat; detetar alterações. |
| NFR-05 | Tempo real | Exigir aulas e semanas elegíveis; não alterar relógio ou inserir história nos E2E. |
| NFR-06 | Isolamento | Limitar efeitos a organizações identificadas do teste; preservar clientes e escolas persistentes. |
| NFR-07 | Rigor | Zero retries; omissões, inconclusivos e provas ausentes impedem verde. |
| NFR-08 | Esperas limitadas | Definir prazos para deployments, email e jobs com base em medições reais. |
| NFR-09 | Evidência segura | Redigir texto, mascarar imagens e cifrar binários sensíveis; manter chave separada. |
| NFR-10 | Concorrência | Serializar mutações e respeitar a fila global do solver. |
| NFR-11 | Núcleo determinístico | Preservar segurança, integridade, minutos e solver; usar PostgreSQL real quando necessário. |
| NFR-12 | Manutenção reduzida | Eliminar casos redundantes, consumidores, fixtures e configuração sem uso. |

## Núcleo essencial e limpeza

Baseline atual: 162 ficheiros backend, 87 frontend e 27 specs E2E.
Os 1192 métodos backend são definições estáticas, sem expansão de parametrizações.
Os ficheiros frontend referem-se a `frontend/src/test/`, não a todos os checks Node.

Alvos de triagem: 8–12 ficheiros frontend e 30–45 backend.
Não tratar esses números como quotas.
Reduzir casos e parametrizações reais, fixtures, helpers, linhas e duração.
Preservar regressões únicas, mesmo quando justificarem um desvio.
Contar também os testes novos da infraestrutura de aceitação.

Manter segurança/RLS, JWT, webhooks, imports atómicos, migrations, relações e privacidade.
Manter minutos exatos, decisões, dívida residual, histórico, fonte das aulas e fecho semanal.
Manter solver real, validação independente, almoço, exclusividade, recuperação e filas.
Manter datas, CSV, payloads, token/cache, contexto assíncrono, feedback e recuperação frontend críticos.
Preservar os checks de build, lint, dependências e migrations.
A [parte 4](REAL_BROWSER_TESTING_WBS_PART_4_CLEANUP_AND_CI.md) identifica os ficheiros candidatos ao núcleo.

## Publicação, resultados e evidências

Conferir SHA completo no frontend, API, worker, supervisor e Beat.
Falhar perante deployment incompleto, revisão misturada ou publicação nova durante a campanha.
Serializar campanhas com estado partilhado.
Não transferir silenciosamente a aceitação para outra revisão.

Guardar relatório, screenshots, trace e vídeo pertinentes às falhas.
Redigir credenciais, códigos e tokens do texto.
Mascarar screenshots e cifrar traces/vídeos sensíveis antes do upload.
Preservar os binários com cifragem autenticada e chave separada.
Não publicar storage state ou versões brutas.
Guardar resumo também em sucesso.

Os resultados são `validated`, `failed`, `dependency_unavailable` e `incomplete`.
Só a matriz completa `validated` certifica produção.
PRs continuam a ter checks anteriores à publicação.
Os percursos reais decorrem após autodeploy da main.
Uma falha pode identificar uma regressão já publicada; decidir recuperação conforme a evidência.

## Limites de dados e falhas

Validar propriedade por IDs e proveniência, não apenas pelo nome da escola.
Limpar apenas alvos descartáveis pertencentes à execução.
Exportar, confirmar eliminação Clerk e reutilizar erasure local por ID.
Preservar clientes, contas partilhadas e histórico.
Não criar endpoint de reset nem usar DELETE amplo ou reset global.

Ensaiar falhas de worker, Redis e PostgreSQL apenas em infraestrutura real isolada.
Esses ensaios pertencem ao núcleo técnico.
Não interromper serviços partilhados com clientes.
Não aplicar reconciliações QA históricas de terceiros durante esta iniciativa.

## Marcos e medição

| Marco | Prova de saída |
| :--- | :--- |
| M1 | Dados, Gmail, evidências, revisão e canal administrativo verificados. |
| M2 | Registo, entrada, saída e recuperação reais. |
| M3 | Escola completa, relações e convite real. |
| M4 | Geração completa, revisão, aprovação e persistência. |
| M5 | Operação, histórico e restantes percursos completos. |
| M6 | Aceitação obrigatória ligada ao SHA publicado, com provas seguras. |
| M7 | Núcleo essencial, limpeza, contagens e documentação reconciliados. |

Medir duração, filas, consumo Railway, minutos Actions, armazenamento e duração do solver.
Registar custos observados, sem inventar estimativas.
Acompanhar cada push até a CI terminar; corrigir falhas de código e repetir a verificação pertinente.

## Verificação e documentos relacionados

Não declarar conclusão sem matriz completa, versão comprovada, dados elegíveis e limpeza limitada.
O [índice WBS](REAL_BROWSER_TESTING_WBS.md) distribui as 80 tarefas em quatro partes.
O [guia atual](TESTING_AND_CI.md) descreve o funcionamento existente até ao cutover.
Consultar [configuração escolar](../02_domain_model/SCHOOL_CONFIGURATION.md), [scheduler](../03_scheduler_engine/README.md) e [ocorrências](../04_operational_features/OCCURRENCES_AND_SUBSTITUTIONS.md).
