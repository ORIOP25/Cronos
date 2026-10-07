# WBS técnico — Parte 4: Limpeza dos testes, CI e verificação final

Revisão: 2026-10-07. Versão: 2.0. Baseline: `91a9d28bcb9c9a829a8578872156a6b90fa04bcf`.

## Objetivo

Concluir o núcleo essencial, a limpeza limitada e a CI de aceitação.
Preparar W10.1 cedo. Validar o canal administrativo durante M1.
W10.4–6 mantém a dependência de W05.
W09.1–4 e W11 podem avançar durante a espera pelo calendário.

Remover cada grupo de testes apenas após a sua prova substituta.
G6 e G7 exigem a matriz completa e a verificação final.

Este plano contém 24 tarefas, com os IDs originais.

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
| Frontend tem novo feedback e proteção de tentativas por identidade. | Preservar regressões de logout, troca de escola e desmontagem. |
| Migration `0018_occurrence_decisions.py` preserva decisões e revogações. | Manter verificação de upgrade/downgrade e integridade. |
| Novos E2E de QA usam API para preparar ocorrências e dados. | Reaproveitar verificações finais; reconstruir ações pela UI. |
| CI continua com E2E local e `capacity-smoke`. | Não classificar esses jobs como aceitação real. |
| Relatório de capacidade já aparece nas falhas. | Reutilizar o diagnóstico útil sem o usar como prova de percurso humano. |

As correções de produto já existentes não comprovam a aceitação em produção.
Reutilizar essas correções e acrescentar as provas em falta.

## Componentes e tarefas

### W09 — Núcleo essencial e redução dos testes atuais

Ficheiros: `backend/tests/`, `frontend/src/test/`, fixtures, `frontend/vitest.config.js`, runner e workflow.

| ID | Dependências | RED / prova inicial | Implementação mínima e DONE |
| :--- | :--- | :--- | :--- |
| W09.1 | W00.3 | 405 ou vítima inexistente não comprova autorização. | Preservar JWT, RLS, papéis, webhooks, limitação e isolamento real. Consolidar sem perder regressões únicas. |
| W09.2 | W09.1 | Falha de importação ou calendário não pode deixar escrita parcial. | Preservar PostgreSQL real, rollback, migrations, relações, privacidade e atualização atómica das três datas. |
| W09.3 | W00.3 | Contabilidade incorreta ou origem perdida deve falhar. | Preservar decisões, reversões, dívida residual, fecho semanal e linhagem entre versões. Conferir migration 0018 e compensações. |
| W09.4 | W00.3, W06 | Solver que aceita colisão ou cobertura incompleta deve falhar. | Reutilizar solver e validador independentes existentes. Preservar recuperação, reservas, almoço e exclusividade compacta. |
| W09.5 | Provas W05–W08 correspondentes | Testes artificiais repetidos não acrescentam prova após substituição real. | Eliminar a maioria dos testes de páginas e hooks. Preservar núcleo frontend e regressões novas indispensáveis. |
| W09.6 | W09.1–5 | Mover os mesmos casos para menos ficheiros não demonstra redução. | Medir casos, parametrizações, fixtures, linhas e duração. Separar aplicação e infraestrutura E2E, e publicar total. |
| W09.7 | W09.5–6 | Setup ou dependência sem consumidor deve ser identificado. | Buscar consumidores e executar Knip. Remover MSW/Clerk testing/SDKs apenas quando nenhum uso legítimo permanecer. |
| W09.8 | W09.1–7 | Gates globais incompatíveis podem forçar testes triviais. | Manter relatório global e gates críticos justificados. Atualizar thresholds no runner e workflow em conjunto. |

### W10 — Runner de produção, CI e limpeza administrativa

Ficheiros: `scripts/test.mjs`, `.github/workflows/ci.yml`, Playwright e wrapper de privacidade limitado.

| ID | Dependências | RED / prova inicial | Implementação mínima e DONE |
| :--- | :--- | :--- | :--- |
| W10.1 | W01, W03, W04 | e2e ainda inicia Compose e exige chaves de teste. | Substituir runE2e por Chrome contra produção. Retirar provisionamento e separar diagnóstico parcial de aceitação. |
| W10.2 | W10.1 | PR/fork não deve receber segredos live nem certificar um deployment inexistente. | Manter checks essenciais nas PRs. Exigir aceitação após publicação do SHA da main. |
| W10.3 | W10.2 | Campanhas concorrentes ou canceladas podem perder estado e limpeza. | Serializar mutações e evitar cancelamento automático. Invalidar campanhas ultrapassadas sem mascarar a razão. |
| W10.4 | W03, W05 | IDs estranhos, manifesto adulterado ou escola persistente impedem eliminação. | Conferir propriedade, IDs local/Clerk, atores, criação, proveniência e tipo descartável antes de qualquer ação destrutiva. |
| W10.5 | W10.4 | Apagar apenas Clerk deixa dados locais desativados. | Exportar com privacidade existente; comprovar eliminação no fornecedor e executar erasure por ID confirmado. |
| W10.6 | W10.5 | Sem canal administrativo ou com jobs ativos, a limpeza fica bloqueada. | Validar execução remota não interativa. Recusar jobs ativos e registar alvos pendentes; manter credenciais administrativas separadas. |
| W10.7 | W10.1–6 e matriz completa | Falha de teste, revisão, artefacto ou limpeza não pode produzir verde. | Fechar resultado obrigatório, preservar falha primária e fazer upload seguro também em falha. |
| W10.8 | W10.7 | Helpers obsoletos ainda referidos mantêm a suite artificial. | Remover setup Clerk, storage state artificial, seeds, smokes e suporte sem consumidor. Atualizar comandos e ajuda. |

### W11 — Recuperação de infraestrutura real isolada

Ficheiros: Compose de testes existente e testes reais de jobs/supervisão.

| ID | Dependências | RED / prova inicial | Implementação mínima e DONE |
| :--- | :--- | :--- | :--- |
| W11.1 | W00.3 | Destino de produção deve recusar interrupção de serviços. | Validar recursos próprios e nomes exatos das bases de teste. |
| W11.2 | W11.1 | Chamada direta de função Celery não prova recuperação de processo. | Enfileirar trabalho real e terminar apenas o worker próprio. Conferir supervisor e recuperação reais. |
| W11.3 | W11.2 | Redelivery ou falha após escrita não pode duplicar proposta ou histórico. | Conferir idempotência, estados terminais e ausência de escrita parcial com PostgreSQL/Redis reais. |
| W11.4 | W11.1–3 | Ensaio local não certifica comportamento específico Railway. | Registar ambiente e recursos. Usar Railway isolado quando a prova exigir o fornecedor. |

### W12 — Verificação final e documentação

Ficheiros: PRD, quatro planos, índice, guia atual, ajuda e relatórios do runner.

| ID | Dependências | RED / prova inicial | Implementação mínima e DONE |
| :--- | :--- | :--- | :--- |
| W12.1 | W05–W10 | Matriz ou história inelegível impede conclusão. | Executar campanha completa no SHA publicado. Conferir requisitos, organizações e artefactos. |
| W12.2 | W09–W11 | CI verde só com provas locais não fecha aceitação. | Executar checks exigidos e acompanhar cada push. Conferir produção e núcleo essencial. |
| W12.3 | W12.1–2 | Contagem de ficheiros sem redução real não demonstra limpeza. | Publicar antes/depois, casos removidos, duração, consumo, fila e custos observados. |
| W12.4 | W12.1–3 | Guia que descreve plano futuro como já implementado induz execução errada. | Reconciliar PRD, partes, índice e implementação. Atualizar TESTING_AND_CI apenas com comportamentos comprovados. |

## Contratos e ordem de execução

### Núcleo frontend proposto

Preservar casos úteis, sem transformar o número de ficheiros numa quota:

| Grupo | Ficheiros atuais |
| :--- | :--- |
| Datas, horas e CSV | `formatUtils.test.js`, `timeOfDay.test.js`, `importFiles.test.js` |
| Semana e configuração | `weekSubmission.test.js`, `schoolConfigPayloads.test.js`, `foundationModel.test.js` |
| Autenticação e contexto | `apiClient.test.js`, `UserQueryProvider.test.jsx`, `useAttemptScope.test.jsx` |
| Erros, feedback e recuperação | `apiErrors.test.js`, `AppToaster.test.jsx`, `vitePreloadRecovery.test.js` |

Manter `PortugueseDateInput.test.jsx` e `ConfirmationModal.test.jsx` até existir prova equivalente no Chrome.
O alvo continua a ser 8–12 ficheiros frontend e 30–45 backend.
Uma regressão única pode justificar um desvio.
Medir casos reais removidos; não reunir os mesmos casos em menos ficheiros.
Contar infraestrutura E2E adicionada separadamente e apresentar o total.

### Regressões do chamador

Em `Schedules.jsx`, aprovação/rejeição verificam contexto apenas após sucesso.
Os blocos `catch` podem emitir feedback sem verificar a tentativa.
Provar erro tardio após troca de escola, logout ou desmontagem.
Escrever RED no chamador e corrigir o guard mínimo se a prova falhar.
Não eliminar essa regressão apenas porque `useAttemptScope.test.jsx` passa.
Estas provas determinísticas pertencem ao núcleo; não usam respostas falsas para certificar E2E.

### Núcleo backend atual

Preservar as provas de `test_scheduler_v1_occurrences.py`, `test_timesheets_v1.py` e contabilidade.
Preservar linhagem, dívida residual, reservas, versões obsoletas e bloqueios de semanas.
Preservar `test_scheduler_recovery_construction_v1.py` e `test_scheduler_v1_adaptive_changes.py`.
Preservar configurações atómicas e `test_lesson_time_rule.py`.
Preservar RLS, imports, migrations e exclusividade de recursos.

Consolidar casos sobrepostos depois de demonstrar equivalência.
Usar os manifestos do laboratório apenas onde houver consumidor e prova concreta.

### Runner e CI

Instalar Chrome com `npx --no-install playwright install --with-deps chrome`.
Configurar `channel: 'chrome'`, `retries: 0` e um worker inicial para estado partilhado.
Não manter o grafo antigo como uma segunda aceitação permanente.

O SHA esperado vem de `github.sha` no push da `main`.
O checkout dos testes corresponde ao SHA na certificação final.
Diagnóstico de branch identifica ambos os SHAs e permanece parcial.
O comando `all` identifica checks anteriores à publicação.
Ativar o job obrigatório apenas com matriz implementada e histórico real elegível.
Dimensionar prazos pelo conjunto completo e fila real; não reaproveitar cegamente o timeout local de 30 minutos.

Não executar falhas destrutivas na infraestrutura partilhada.
Recuperação isolada pertence ao núcleo técnico, não à cobertura humana certificada.

### Limpeza limitada

Criar `backend/scripts/cleanup_e2e_run.py` como wrapper do comando existente.
Separar validação pura em `e2e_cleanup_policy.py` quando a responsabilidade justificar o ficheiro.

Reutilizar `backend/scripts/privacy.py`:

```text
python -m scripts.privacy export --organization-id <id> --output <ficheiro-protegido.zip>
python -m scripts.privacy erase --organization-id <id> --confirm-clerk-org-id <org-id>
python -m scripts.privacy erase --organization-id <id> --confirm-clerk-org-id <org-id> --execute --provider-deleted
```

O segundo comando é dry-run.
Executar erasure apenas depois de comprovar eliminação no fornecedor.
Validar IDs e propriedade antes da exportação e da eliminação.
Preservar tombstones e aceitação legal conforme o contrato existente.
Não dar DELETE amplo ao papel runtime nem expor endpoint de reset.

Remover contas Clerk apenas quando criadas pelo teste e sem outras memberships.
Preservar contas base, escolas persistentes e identidades partilhadas.
Bloquear limpeza com jobs ativos.
Não colocar `MIGRATION_DATABASE_URL` no job normal de browser.

Validar execução administrativa Railway não interativa em M1.
Não pressupor que o token de consulta de projeto autoriza SSH ou registo de chave.
Usar argumentos separados e manifesto por stdin ou ficheiro protegido.
Não construir shell a partir de nomes ou conteúdo da aplicação.
Se faltar canal autorizado, registar dependência e alvos pendentes.

### Comandos e checks comuns

```powershell
node --test scripts/test.test.mjs
node scripts/test.mjs fast --scope backend -- -k scheduler_candidate_validation
node scripts/test.mjs fast --scope frontend -- -t getWeekSubmissionBlockers
node scripts/test.mjs integration -- -k occurrence_accounting
node scripts/test.mjs all --scope all
```

O comando `integration` também executa contratos no runner atual.
Confirmar bases isoladas e papéis migrator/runtime antes dos testes de dados.
Adicionar testes Node explícitos para os novos módulos; evitar descoberta acidental de specs Playwright.
Após a implementação segura do destino, manter `node scripts/test.mjs e2e` como entrada da aceitação.
Não executar a futura campanha antes de configurar limites de propriedade.

- Backend: Ruff, testes relevantes, Alembic, audits de integridade/triggers, dependências e imagem quando aplicável.
- Frontend: `npm run audit:production`, `npm run verify` e refresh/rebuild Docker após alterações frontend.
- Publicação: acompanhar cada push; corrigir falhas e repetir checks pertinentes.
- Produção: conferir SHA, matriz completa e evidências protegidas.

Preservar volumes de desenvolvimento.
Não usar `down -v` fora dos recursos exatos do teste.

## Estados, falhas e verificação

Registar tarefa, commit, ficheiros, RED, GREEN e referências das provas.
Usar `PENDENTE`, `EM_CURSO`, `CONCLUÍDO` ou `DEPENDÊNCIA`.
Concluir apenas quando DONE estiver comprovado.

Uma falha de fornecedor ou falta de histórico não é RED de uma regra do produto.
Não reduzir critérios nem usar retries para apagar uma falha.
Aplicar os [comandos comuns](REAL_BROWSER_TESTING_WBS_PART_4_CLEANUP_AND_CI.md#comandos-e-checks-comuns).
Conferir as [condições globais](REAL_BROWSER_TESTING_WBS.md#condições-de-passagem) antes de avançar.

## Fontes e documentos relacionados

- [Workflow](../../.github/workflows/ci.yml)
- [Privacidade](../../backend/scripts/privacy.py)
- [Migration 0018](../../backend/alembic/versions/0018_occurrence_decisions.py)
- [Escopo assíncrono](../../frontend/src/hooks/useAttemptScope.js)
- [Guia atual de testes](TESTING_AND_CI.md)
- [Padrão de documentação](../00_getting_started/DOCUMENTATION_STANDARD.md)
- [Runtime local](../09_ops_observability/LOCAL_RUNTIME.md)
