# W14 — Corte e entrega (concluída)

Data: 28 de setembro de 2026.
Estado: W14.1–W14.4 concluídos. A v1 está ativa.
Documentos de referência: [plano v2](SCHEDULER_V1_REVAMP_PLAN_V2.md), [WBS v2](SCHEDULER_V1_WBS_V2.md), [especificação v2](SCHEDULER_V1_TECH_SPEC_V2.md), [W13](SCHEDULER_V1_W13_STATUS.md).

## 1. Release e CI (W14.1)

- Revisão candidata de código: `f8ce03681a936e815f6ad493f54f4fed4c39a29e`. Inclui o merge `a9c6f34`, as correções do W13.4 (`53f0e43`) e os registos.
- A `main` passou CI verde em dois pushes: run `36361438796` (`f8ce036`) e run `36364367621` (commit de documentação). As tarefas `backend`, `frontend` e `e2e` passaram em ambos.
- Os quatro serviços Railway (`api`, `worker`, `supervisor`, `beat`) servem a revisão final da `main`.
- O frontend público em `https://cronos.pt` foi publicado com o mesmo código. O bundle contém a proteção da data preferencial de fim e a lista de turmas ativas.
- `https://api.cronos.pt/health/ready` responde `ok` com `revision=f8ce036`, PostgreSQL e Redis ligados.

## 2. Limpeza e baseline final (W14.2)

- Nenhum job antigo estava ativo. Os workers foram mantidos parados durante a reinstalação.
- A baseline final foi reinstalada com o ciclo testado `alembic downgrade base && alembic upgrade head`, aplicado pelo `preDeployCommand` do serviço `api` numa revisão temporária. O `preDeployCommand` da `main` voltou a `alembic upgrade head`.
- O ciclo correu duas vezes: uma para remover os dados do W13 e outra como corte final, após o smoke. A base de dados fica vazia.
- O `SCHEDULER_V1_NUM_WORKERS` do serviço `worker` está a `2`, conforme a decisão do W13.
- O registo DNS temporário `w13.cronos.pt` não existe. O `CORS_ORIGINS` da API é `https://cronos.pt`. Não há proxies TCP.
- Limitação: o token de projeto Railway não autoriza a criação manual de backups de volume. O Railway mantém a recuperação point-in-time. Não foi criado um backup manual antes do reset.

## 3. Smoke funcional em produção (W14.3)

O smoke criou uma organização de verificação no Clerk e executou o percurso completo contra `https://cronos.pt` e `https://api.cronos.pt`:

| Passo | Resultado |
| :--- | :--- |
| Fundação escolar (onboarding) | Concluída pela interface |
| Geração completa | Job `COMPLETE_GENERATION` `SUCCEEDED`, resultado `COMPLETE` |
| Aprovação da proposta | `APPROVED`, versão ativa publicada |
| Publicação | Semana com 2 aulas publicadas |
| Ocorrência (aula dada em falta) | `OCCURRENCE`, dívida de 60 minutos |
| Reparação adaptativa | Job `ADAPTIVE_RECOVERY` `SUCCEEDED`, resultado `COMPLETE` |

A organização e o utilizador de verificação foram removidos. O reset final removeu os dados de verificação. A API, o worker e o frontend servem a mesma revisão `f8ce036`.

## 4. Entrega (W14.4)

- O runbook de deployment foi atualizado com o serviço `supervisor`, a configuração de workers CP-SAT e o procedimento de corte.
- Limitações conhecidas:
  - As gerações param no limite de segurança e reportam qualidade `NOT_MEASURED`; isso não é prova de impossibilidade.
  - Não existe rollback para o motor antigo. A recuperação usa apenas artefactos v1 compatíveis.
  - Após um reset de dados, a identidade local é reconstruída no primeiro login de um administrador através do bootstrap de sessão. Convidados pendentes precisam de reconciliação.
  - A superfície operacional legada partilhada (sumários, ocorrências, timesheets, painel) permanece; não pertence ao motor v1.

## 5. Critério de fecho

- [x] Revisão candidata identificada e CI verde.
- [x] Serviços compatíveis publicados na mesma revisão.
- [x] Dados de ensaio removidos e baseline final vazia instalada.
- [x] Smoke de geração, aprovação, execução e reparação aprovado.
- [x] Runbook, relatórios e limitações conhecidas entregues.