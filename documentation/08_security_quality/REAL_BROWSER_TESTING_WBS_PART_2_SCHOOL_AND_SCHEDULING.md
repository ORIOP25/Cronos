# WBS técnico — Parte 2: Deployments, escola e geração de horários

Revisão: 2026-10-07. Versão: 2.0. Baseline: `91a9d28bcb9c9a829a8578872156a6b90fa04bcf`.

## Objetivo

Comprovar a revisão publicada e preparar contas, escola e horários pela interface.
W04 pode começar após W01 e os acessos necessários.
W05 exige W02, W03 e W04.
Preparar W10.1 quando essas dependências estiverem disponíveis.
Concluir W10.4–6 depois de W05.
G2 e G3 exigem escola e horário comprovados.

Este plano contém 19 tarefas, com os IDs originais.

## Leitor e pré-requisitos

Destina-se a quem implementa esta parte.
Ler o [índice](REAL_BROWSER_TESTING_WBS.md), o [PRD](REAL_BROWSER_TESTING_PLAN.md) e os guias relevantes.

Aplicar as [regras comuns](REAL_BROWSER_TESTING_WBS.md#contratos-e-invariantes) em todas as tarefas.
Usar Clean Architecture, Clean Code, TDD e Ponytail full.
Preservar os IDs e verificar dependências entre partes.
Um comportamento já correto exige reutilização dos seus testes, sem criar uma falha artificial.
Escrever RED antes de alterar um comportamento não trivial.

## Comportamento atual e motivo da revisão

| Evidência atual | Consequência |
| :--- | :--- |
| Fundação mantém dez passos e inclui `preferred_end_date` opcional. | Provar vazio permitido, limites, draft, resumo e persistência. |
| A geração exige data preferencial e diálogo de confirmação. | Definir a data para a campanha e clicar `Iniciar geração`. |
| Curso preserva a turma inicial preenchida. | Não exigir `Adicionar turma` para essa turma. |
| `/courses` retirou o botão de atribuições. | Importar os cinco recursos em `/imports`; não procurar o botão removido. |
| Recuperação e preferências semanais já estão implementadas. | Usar o motor atual; não criar outro solver ou certificação de optimalidade. |

As correções de produto já existentes não comprovam a aceitação em produção.
Reutilizar essas correções e acrescentar as provas em falta.

## Componentes e tarefas

### W04 — Identidade do build e barreira dos deployments

Ficheiros: Script de revisão frontend, `frontend/package.json`, adaptador de deployments, readiness e `backend/railway/*.json`.

| ID | Dependências | RED / prova inicial | Implementação mínima e DONE |
| :--- | :--- | :--- | :--- |
| W04.1 | W01.4 | API atual com frontend antigo deve impedir aceitação. | Escrever `dist/revision.json` com SHA completo do build. Conferir a resposta pública sem cache. |
| W04.2 | W04.1 | SHA vazio, abreviado ou inventado não pode certificar produção. | Usar a revisão fornecida pelo build Cloudflare. Identificar builds locais sem revisão verificável. |
| W04.3 | W00.4 | Pages preview, falha ou outro commit deve ser recusado. | Consultar deployments de produção. Conferir projeto, commit e conclusão do deployment. |
| W04.4 | W00.4 | API atual com worker, supervisor ou Beat antigos deve impedir execução. | Consultar Railway e exigir a revisão esperada nos quatro serviços ativos. |
| W04.5 | W04.3–4 | HTTP 200 com erros GraphQL ou serviço ausente deve falhar. | Validar o schema atual, autenticação, dados e erros. Normalizar respostas no adaptador. |
| W04.6 | W04.1–5 | Uma publicação nova durante a campanha invalida a revisão anterior. | Conferir revisões antes de cada grupo e no fim. Não mudar silenciosamente o SHA esperado. |

### W05 — Identidades reais, fundação e escola completa

Ficheiros: Specs auth/foundation/members/imports, helpers UI e páginas `SignInPage.jsx`, `SignUpPage.jsx`, `Foundation.jsx`, `BulkImport.jsx`, `Members.jsx`.

| ID | Dependências | RED / prova inicial | Implementação mínima e DONE |
| :--- | :--- | :--- | :--- |
| W05.1 | W02, W03, W04 | Registo sem email entregue ou fundação legítima fica incompleto. | Criar alias fundador pela UI. Concluir verificações e consentimentos apresentados; registar organização e atores observados. |
| W05.2 | W05.1 | Helper Clerk ou sessão pré-fabricada não comprova login real. | Executar login/logout na UI e nova entrada em contexto novo. Esperar sessão e identidade antes da organização. |
| W05.3 | W05.1 | Introduzir o código de recuperação sem terminar o fluxo deixa E2E-03 incompleto. | Recuperar conta descartável, mudar credencial e voltar a entrar. Conferir a credencial anterior quando aplicável. |
| W05.4 | W05.1 | Importação parcial ou apenas mensagem de sucesso deve falhar. | Abrir `/imports`, selecionar os cinco CSV completos, validar e confirmar commit pela UI. |
| W05.5 | W05.4 | Contagens corretas com relações erradas devem falhar. | Conferir competências, módulos, cursos, turmas e atribuições na UI. Usar GET autenticado apenas como prova auxiliar. |
| W05.6 | W05.4 | Utilizador já existente no Clerk pode receber membership sem email. | Converter um recurso pendente para alias professor novo pela UI. Receber e aceitar o convite real. |
| W05.7 | W05.6 | Conversão com perda de competências ou alteração de outra escola deve falhar. | Comparar IDs e relações antes/depois. Provar proteção da identidade pendente partilhada no núcleo backend. |
| W05.8 | W05.4–7 | Datas incompletas ou professor sem aulas impedem geração e operação. | Concluir os dez passos e definir data preferencial válida. Provar draft, resumo, calendário, disponibilidade e persistência. |

### W06 — Geração completa, aprovação e verificações independentes

Ficheiros: Specs scheduler/readiness, expectativas independentes, `Schedules.jsx` e scheduler v1 existente.

| ID | Dependências | RED / prova inicial | Implementação mínima e DONE |
| :--- | :--- | :--- | :--- |
| W06.1 | W01.2–3, W05.8 | Minutos em falta, excesso ou módulos trocados devem falhar. | Expandir as atribuições por turma/disciplina. Conferir exigência total e residual sem importar o validador do produto. |
| W06.2 | W06.1 | Colisão, sala incompatível ou almoço descontínuo deve falhar. | Conferir intervalos, capacidades, competências, calendário e almoço contínuo. Distinguir preferências semanais de restrições obrigatórias. |
| W06.3 | W05.8, W04 | Pedido do job sem conclusão real não satisfaz E2E-08. | Confirmar o diálogo e clicar Iniciar geração. Acompanhar fila, worker e resultado terminal com prazo. |
| W06.4 | W06.1–3 | Proposta parcial ou toast de sucesso não prova horário completo. | Conferir cobertura e restrições. Aprovar pela UI e verificar publicação e horário do professor. |
| W06.5 | W06.4 | Nova sessão sem horários aprovados deve falhar. | Reabrir horários, conferir versão, aulas e progresso. Guardar baseline física e linhagem para comparações futuras. |

## Contratos e ordem de execução

### Reutilização e identidade

Criar `frontend/scripts/write-build-revision.mjs` para produzir `dist/revision.json` no build.
Reutilizar readiness; não criar outro endpoint backend de versão.

Consultar Pages em `/accounts/{account}/pages/projects/{project}/deployments`.
Conferir produção, commit e conclusão.
Consultar Railway via GraphQL e confirmar schema atual antes de fixar a query.
Usar autenticação adequada ao tipo de token.
Esperar readiness da API com PostgreSQL e Redis conectados.
Confirmar retirada de workers antigos e filtros de autodeploy que possam deixar serviços desatualizados.

Reutilizar helpers UI só quando não fizerem seeds, login programático ou mutações de negócio por API.
Criar `ui-auth.js`, `ui-school.js` e `expected-results.js` apenas para responsabilidades concretas.
Preferir locators semânticos e esperas por estado visível.

### Identidades e fundação

Não registar antecipadamente o alias que deve receber um convite.
Converter o professor selecionado antes de criar outra escola com a mesma identidade pendente do CSV.
A edição de email pendente atua sobre uma conta global. Preservar a prova de isolamento de W05.7.
Usar migration nova se a proteção exigir SQL. Não editar a baseline.

O campo preferencial é opcional na Fundação.
Para a geração completa, preencher uma data válida entre início e limite final.
Testar persistência após recarregar e alterar as três datas sem estado intermédio inválido.
Usar o calendário visível e ações de teclado suportadas.
Não substituir ações humanas por `evaluate`, setters ou eventos artificiais.

### Verificação da proposta

Converter horas para minutos com `Decimal`.
Expandir a exigência das 336 atribuições pelos módulos aplicáveis.
Conferir horários adjacentes versus sobrepostos, almoço contínuo e crédito final parcial.
Preferências de padrão semanal e sala não são restrições obrigatórias.
Um candidato completo não prova optimalidade.
Usar o orçamento real; não reduzir turmas, módulos ou procura para obter sucesso.

Aprovar a proposta pela UI após verificar o resultado.
Conservar a prova de rejeição quando esse caso fizer parte da matriz concreta.
GETs auxiliares usam a sessão obtida pela UI.
Manter bearer observado apenas em memória.
Não usar POST/PATCH auxiliares para criar o estado de negócio.

## Estados, falhas e verificação

Registar tarefa, commit, ficheiros, RED, GREEN e referências das provas.
Usar `PENDENTE`, `EM_CURSO`, `CONCLUÍDO` ou `DEPENDÊNCIA`.
Concluir apenas quando DONE estiver comprovado.

Uma falha de fornecedor ou falta de histórico não é RED de uma regra do produto.
Não reduzir critérios nem usar retries para apagar uma falha.
Aplicar os [comandos comuns](REAL_BROWSER_TESTING_WBS_PART_4_CLEANUP_AND_CI.md#comandos-e-checks-comuns).
Conferir as [condições globais](REAL_BROWSER_TESTING_WBS.md#condições-de-passagem) antes de avançar.

## Fontes e documentos relacionados

- [Fundação](../../frontend/src/features/foundation/foundationModel.js)
- [Datas da Fundação](../../frontend/src/features/foundation/components/PeriodStep.jsx)
- [Cursos](../../frontend/src/pages/Courses.jsx)
- [Geração](../../frontend/src/pages/Schedules.jsx)
- [Guia atual de testes](TESTING_AND_CI.md)
- [Padrão de documentação](../00_getting_started/DOCUMENTATION_STANDARD.md)
- [Parte seguinte](REAL_BROWSER_TESTING_WBS_PART_3_REAL_JOURNEYS.md)
