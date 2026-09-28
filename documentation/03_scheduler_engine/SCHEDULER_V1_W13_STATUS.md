# W13 — Validação remota (concluída)

Data: 28 de setembro de 2026.
Estado: W13 concluída. W14 por iniciar.
Documentos de referência: [plano v2](SCHEDULER_V1_REVAMP_PLAN_V2.md), [WBS v2](SCHEDULER_V1_WBS_V2.md), [especificação v2](SCHEDULER_V1_TECH_SPEC_V2.md), [W12](SCHEDULER_V1_W12_STATUS.md).

## 1. Candidate e estado remoto confirmado

- A API live em `https://api.cronos.pt/health/ready` respondeu `ok` em 28/09/2026, com revisão `a9c6f342299ce637c0c3ffa2f2dbc8bcc98e300b`, PostgreSQL e Redis ligados.
- O frontend público `https://cronos.pt/` serve a revisão Cloudflare `a9c6f34`, igual à API, e aponta para `https://api.cronos.pt/api/v1`.
- O bundle publicado usa a instância Clerk live (`pk_live_`). A API usa a mesma instância após a rotação descrita na secção 5. Não há chave Clerk de teste em produção.
- A revisão `a9c6f342` é o `HEAD` local. Os ensaios remotos usaram essa revisão.

## 2. Ensaios remotos concluídos

Os artefactos JSON estão em `frontend/.test-artifacts/w13-remote/` (ignorados pelo Git):

| Modo | Workers CP-SAT | Resultado | Espera em fila | Processamento | Publicação |
| :--- | ---: | :--- | ---: | ---: | :--- |
| Job 1 · geração completa, 60 turmas | 1 | `COMPLETE_GENERATION`; `SUCCEEDED`, completa, `SAFETY_LIMIT` | 0,6 s | 900,2 s | Aprovada, versão 1 |
| Job 2 · reparação após ocorrência (50 min) | 1 | `ADAPTIVE_RECOVERY`; `SUCCEEDED`, completa, `NOT_MEASURED` | 0,7 s | 916,1 s | Aprovada, versão 2 |
| Job 3 · reparação após ocorrência (50 min) | 2 | `ADAPTIVE_RECOVERY`; `SUCCEEDED`, completa, `NOT_MEASURED` | 0,5 s | 901,2 s | Aprovada, versão 3 |
| Job 5 · reparação após ocorrência (50 min) | 4 | `ADAPTIVE_RECOVERY`; `SUCCEEDED`, completa, `NOT_MEASURED` | 0,7 s | 919,4 s | Aprovada, versão 4 |

Os ensaios confirmam o percurso autenticado de teste → API → fila global → worker Railway → solver → validação → proposta → aprovação e reparação. Os processamentos pararam ao atingir o limite de segurança; isso não foi tratado como prova de impossibilidade.

### Cenários de resiliência

| Cenário | Evidência | Resultado |
| :--- | :--- | :--- |
| Pedido duplicado / idempotência | Job 4 (`duplicate.json`) | Duas chamadas com a mesma chave devolveram o mesmo job; `same_job=true`. |
| Cancelamento | Job 4 e job 7 (`duplicate.json`, `after-restart-cancel.json`) | O pedido de cancelamento terminou em `CANCELLED`. O job 4 processou 19,1 s antes de parar. |
| Reinício do worker com job em fila | Job 6 (`restart-enqueued.json`, `restart-inspect.json`) | O job ficou `QUEUED` (posição 1); após o reinício, o supervisor marcou-o `FAILED` / `WORKER_STALLED` ao fim de 231,2 s. |
| Wake pelo supervisor e reconciliação de tentativa abandonada | Job 7 pós-reinício (`after-restart-cancel.json`) | Um novo pedido entrou na fila e foi cancelado corretamente. A tentativa interrompida foi reconciliada automaticamente. |

### Métricas Railway retrospetivas

| Execução | CPU média / pico (vCPU) | RAM média / pico (GB) | Amostras por métrica |
| :--- | ---: | ---: | ---: |
| Geração, 1 worker | 1,001 / 1,127 | 0,874 / 1,063 | 15 |
| Reparação, 1 worker | 0,977 / 1,214 | 0,894 / 0,993 | 15 |
| Reparação, 2 workers | 1,080 / 1,733 | 1,006 / 1,487 | 15 |
| Reparação, 4 workers | 1,133 / 1,628 | 1,271 / 1,590 | 15 |

Valores consultados na API Railway com amostragem de 60 s, limitados às janelas `started_at`–`finished_at` de cada job. CPU é medida em vCPU; RAM em GB. As métricas são do serviço `worker` e agregam as réplicas do serviço. Referência: [métricas Railway](https://docs.railway.com/observability/metrics).

### Comparação de workers

A reparação com 4 workers demorou 919,4 s. Não houve ganho face a 1 worker (916,1 s) nem a 2 workers (901,2 s). A configuração final mantém `SCHEDULER_V1_NUM_WORKERS=2` no serviço `worker`.

## 3. Divergências corrigidas (W13.4)

Os ensaios remotos revelaram três divergências. Foram reproduzidas e corrigidas pelo ciclo local, com testes primeiro:

| Divergência | Correção | Teste |
| :--- | :--- | :--- |
| A página oferecia «Gerar horário» sem «Data preferencial de fim». A API devolvia 422. | A UI bloqueia a geração e explica o campo em falta. `frontend/src/pages/Schedules.jsx` | `SchedulesSchedulerFlow.test.jsx` |
| O seletor de fluxo de estágio oferecia turmas arquivadas. | A UI esconde turmas arquivadas. `SchoolConfigSections.jsx` expõe `is_archived`. | `SchoolConfigInternshipFlows.test.jsx` |
| O erro de fluxo inválido não tinha apresentação. | Novo código público `INTERNSHIP_FLOW_INVALID` na API e no frontend. | `test_classes_crud.py`, `apiErrors.test.js` |

O campo `ClassRead.is_archived` é público. A API mantém o contrato anterior (`is_archived` por omissão `False`).

Verificações locais do ciclo W13.4: 1 teste de integração e 19 testes frontend passaram.

## 4. Limpeza

- Os harnesses de ensaio foram removidos do repositório: `w13_remote_probe.py`, `w13_seed_school.py`, `w13.remote.spec.js`, `w13.clerk.setup.js`, `playwright.w13.config.js`, `vite.w13.config.js` e o build `.w13-preview-dist/`.
- O registo DNS temporário `w13.cronos.pt` já não existe na zona Cloudflare `cronos.pt`.
- `CORS_ORIGINS` da API voltou a `https://cronos.pt`.
- A chave Clerk de teste foi substituída pela chave live nos quatro serviços Railway. O proprietário revogou a chave antiga `default`.
- A API não expõe proxies TCP no ambiente de produção. O proxy temporário de ensaio já não está ativo.
- A limpeza dos dados sintéticos da organização E2E pertence a W14.

## 5. Critério de fecho

- [x] Cenários remotos acordados registados.
- [x] Comparação de workers registada; configuração final decidida (2 workers).
- [x] Divergências reproduzidas, corrigidas e cobertas por testes.
- [x] Variáveis temporárias resolvidas.
- [x] Frontend publicado identificado (`a9c6f34`, API `https://api.cronos.pt/api/v1`).
- [x] Regressões relevantes passaram localmente.
- [x] Limpeza de DNS, CORS, Clerk e harnesses concluída.
- [ ] Aceitação da baseline remota pelo proprietário (gate de W14).