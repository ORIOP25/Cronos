# W12 — Candidate local: remoção, baseline e gate (registo as-built)

> Revisão independente e correções: [SCHEDULER_V1_W10_W12_REVIEW_CORRECTION_STATUS.md](SCHEDULER_V1_W10_W12_REVIEW_CORRECTION_STATUS.md). O veredicto atual do gate é o do registo de correção (fechado em 27/09/2026); este documento permanece como o registo original de W12.

Data: 26 de setembro de 2026.
Branch: `codex/scheduler-v1-revamp`.
Estado: W12.1–W12.5 concluídos no âmbito corrigido. Nenhum push, reset remoto ou ensaio Railway/Cloudflare foi executado.
Documentos de referência: [plano v2](SCHEDULER_V1_REVAMP_PLAN_V2.md), [WBS v2](SCHEDULER_V1_WBS_V2.md), [especificação v2](SCHEDULER_V1_TECH_SPEC_V2.md), [consolidação Alembic](SCHEDULER_V1_ALEMBIC_CONSOLIDATION_PLAN.md), [W10–W11](SCHEDULER_V1_W10_W11_STATUS.md).

## 1. Resultado

- O motor legado, a fronteira legada de domínio, o adaptador CP-SAT do avaliador antigo, o worker antigo, a seed operacional antiga e o endpoint de reset antigo foram removidos, com consumidores atualizados.
- A migração provisória `0011` foi consolidada numa única baseline Alembic que instala o estado final v1 numa base vazia; a cadeia histórica deixou de existir e a revisão provisória não é alcançável.
- Instalação vazia, ciclo `downgrade base`/`upgrade head`, `alembic check`, auditorias de integridade/RLS e o checkpoint de baseline passam.
- A avaliação reservada da candidate congelada usou topologias e seeds não usados na calibração: 2 replays anuais completos e conservados, 1 reparação válida e 2 impossibilidades provadas.
- As limitações remanescentes estão declaradas e não são escondidas por médias.

## 2. W12.1 — Remoção

Removidos (motores, escadas e serviços legados):

```text
app/services/scheduler_adaptation_ladder.py      app/services/scheduler_lifecycle_service.py
app/services/scheduler_adaptive_engine.py        app/services/scheduler_near_optimizer.py
app/services/scheduler_approval_service.py       app/services/scheduler_observability.py
app/services/scheduler_candidates.py             app/services/scheduler_quality_service.py
app/services/scheduler_complete_demand.py        app/services/scheduler_recovery_ladder.py
app/services/scheduler_complete_engine.py        app/services/scheduler_recovery_service.py
app/services/scheduler_constraint_rules.py       app/services/scheduler_recovery_validation.py
app/services/scheduler_curriculum_validation.py  app/services/scheduler_repair_trigger.py
app/services/scheduler_debt_service.py           app/services/scheduler_request_service.py
app/services/scheduler_diff_service.py           app/services/scheduler_status_service.py
app/services/scheduler_disruption.py             app/services/scheduler_target_validator.py
app/services/scheduler_draft_service.py          app/services/operational_seed_service.py
app/services/scheduler_editable_boundary.py      app/scheduler_worker.py
app/services/scheduler_far_fill.py               app/scheduler/domain/contracts.py
app/services/scheduler_generation_service.py     app/scheduler/domain/validation.py
app/services/scheduler_horizon.py                app/scheduler/domain/constraints.py
app/services/scheduler_incremental_demand.py     app/scheduler/infrastructure/cp_sat_quality.py
app/services/scheduler_job_runtime.py            seed_data.py
app/services/scheduler_job_service.py
```

Fronteira de domínio substituída: `domain/constraint_policy.py` (`SchoolConstraintPolicy`) concentra a análise de regras que a v1 honra (salas específicas e indisponibilidade/preferência de docentes); `lock_time` continua recusado com `LOCKED_TIMESLOT_UNSUPPORTED`. `snapshot.py` e `schemas.py` passaram a consumir a nova fronteira.

Wiring atualizado: `celery_worker.py` (fim da tarefa e agenda antigas), `scheduler_recovery_worker.py` (só `scheduler.v1.supervise`), `docker-compose*.yml` e `railway/worker.json` (apenas `app.scheduler_v1_worker`), endpoint `POST /scheduler/reset-year` e respetivos schemas. Testes e fixtures que apenas cristalizavam a implementação removida foram eliminados; invariantes válidos foram reescritos (política de restrições, isolamento de tenant, contratos de migração).

Consumidores verificados por pesquisa exaustiva (`rg`) em `backend/app`, `backend/tests`, `backend/scripts`, `scripts`, `frontend/src` e `frontend/e2e`: sem referências funcionais aos módulos removidos.

### Limitação declarada (carve-out)

A superfície operacional legada partilhada — `ScheduleGenerationJob`, `ScheduleDraft*`, `ActiveScheduleBlock`, `PlannedRecoveryLink`, `LessonLog` e os ramos legados de `occurrence_service`, `dashboard_service`, `preflight_service`, `scheduler_state_service` e `schedule_service` — permanece, porque ainda serve sumários, ocorrências, timesheets e o painel escolar, e a sua migração total exige trabalho funcional fora do motor. Não é usada pelo motor v1 nem pela fila/propostas/aprovação. Não foi transportado qualquer dado antigo: a baseline instala só o esquema final e a instalação limpa não contém registos legados. A remoção final desta superfície fica registada para a limpeza da W14, sem bloquear o gate local.

## 3. W12.2 — Baseline Alembic consolidada

- Ficheiro único: `alembic/versions/0001_scheduler_v1_baseline.py` (`down_revision=None`), com o estado final de 52 tabelas, funções `app_security`, RLS forçada, policies, grants, índices, checks e triggers.
- A cadeia histórica (`0001`–`0014`) foi removida; a revisão provisória `0011_scheduler_v1_curricular` não é alcançável.
- `downgrade()` remove tabelas/tipos de `public` sem tocar em `alembic_version` e elimina `app_security`; o ciclo CI `downgrade base` → `upgrade head` é reproduzível.
- `check_scheduler_baseline.py` passou a exigir a baseline consolidada e falha com orientação de reset perante qualquer outro head.

Evidência (base temporária `cronos_baseline_v1`, PostgreSQL 16 do Docker local):

| Verificação | Resultado |
| :--- | :--- |
| `alembic upgrade head` em base vazia | OK; `alembic current` = `0001_scheduler_v1_baseline` |
| `alembic check` | “No new upgrade operations detected” |
| `alembic downgrade base` → `upgrade head` (2 ciclos) | OK, sem resíduos |
| `scripts.audit_database_integrity` | Tabelas, chaves e FKs consistentes |
| `scripts.audit_triggers` | Triggers monotónicos e append-only verificados |
| `scripts.check_scheduler_baseline` | Passa sem `SCHEDULER_BASELINE_ACCEPTED` |
| Suites de integração/contratos na baseline | 295 + 47 verdes |

## 4. W12.3 — Instalação limpa e checks completos

| Verificação | Resultado |
| :--- | :--- |
| `pytest tests/unit` | 687 passed |
| `node scripts/test.mjs integration` (Docker, PostgreSQL real, 4 workers, migrações a partir de base vazia) | 295 passed |
| Contratos de infraestrutura | 47 passed |
| `ruff check` e `ruff format --check` (app, tests, scripts) | limpos |
| Frontend `npm run lint` | verde |
| Frontend `npm run test` | 73 ficheiros, 411 testes verdes |
| Matrizes W10 | `w10-combined` e `w10-boundaries` com `complete=True problems=0` |
| E2E Playwright com Clerk | executado localmente e na CI; backend, frontend, E2E e capacity smoke verdes (`9582ff4`, `99f0340`) |

## 5. W12.4 — Avaliação reservada

Casos e seeds não utilizados na calibração (`reserved_manifest.json`, `reserved_annual_manifest.json`), executados no Docker com a mesma política (`v1-uncalibrated`) e o mesmo estado de código:

| Campanha | Resultado |
| :--- | :--- |
| `w12-reserved-repair` (3 casos, 20 s) | 1 `VALID`, 2 `INFEASIBLE` provado pelo oráculo, 0 erros |
| `w12-reserved-annual` (20 turmas `loose` 3 eventos; 15 turmas `connected` 2 eventos, 60 s/passo) | 2/2 `VALID`, `completed=True`, `conserved=True` |

A falha inicial da fixture reservada 03 (base sem testemunho) foi reduzida com `lab/reduce.py`, corrigida no gerador e repetida; nenhuma expectativa foi enfraquecida.

## 6. Dossier do gate local (plano §17.1)

| # | Condição | Estado | Evidência/limitação |
| :--- | :--- | :--- | :--- |
| 1 | Instalação vazia e reset da baseline reproduzíveis | Cumprida | Base temporária vazia, ciclos downgrade/upgrade, auditorias. |
| 2 | Domínio, validação independente, integração e E2E locais | Cumprida | 713 unitários, 313 integração, 47 contratos; E2E e capacity smoke verdes na CI (`9582ff4`, `99f0340`). |
| 3 | Geração anual completa em várias instâncias, incluindo 60 turmas | Cumprida | Campanhas anuais W04–W11 e replays 10/30/45/60 W10/W12. |
| 4 | Recuperações de volumes e dificuldades diferentes | Cumprida | `repair_manifest`, `combined_manifest`, `reserved_manifest` (incl. recursos críticos e impossibilidades provadas). |
| 5 | Simulações longitudinais sem perda de minutos | Cumprida | 4 + 2 replays anuais `completed`/`conserved` com validação por passo. |
| 6 | Comparação local de qualidade/tempo, workers, CPU e memória | Cumprida (local) | Relatórios W11; pico de memória é Python-level (sem RSS C++). Railway é da W13. |
| 7 | Política de paragem avaliada com referências longas e dados reservados | Fechada com decisão | Avaliação reservada a 300 s em três famílias longas e três pequenas; `eager` sem poupança e com perda de vetor; política conservadora mantida ([avaliação](SCHEDULER_V1_W12_R2_STOP_POLICY_EVALUATION.md)). |
| 8 | Fila única, cancelamento, falhas, proposta desatualizada e aprovação testados | Cumprida | W08/W09 + integração na baseline. |
| 9 | Legado removido e candidata identificada | Cumprida no âmbito | Remoção do motor/fronteira; carve-out operacional declarado na secção 2. |
| 10 | Horários locais satisfatórios para o proprietário | Aceite em 27/09/2026 | Aceitação registada no [registo de correção](SCHEDULER_V1_W10_W12_REVIEW_CORRECTION_STATUS.md) §6.4; gate local fechado. |

## 7. Limitações conhecidas

- O ensaio remoto (Railway/Cloudflare), o corpus de 60 turmas no hardware remoto e a configuração final de workers são da W13.
- A política de paragem não foi calibrada por falta de trajetórias com melhorias múltiplas; a exploração completa dentro do orçamento de segurança mantém-se explícita.
- O pico de memória medido é de alocação Python; a memória nativa do OR-Tools não é capturada.
- A stack local de desenvolvimento não foi recriada com a baseline nova nesta W12; a instalação limpa foi demonstrada em bases temporárias e nos containers de teste. O reset/instalação final é da W14.
- E2E Playwright corre com Clerk de teste localmente e na CI; o percurso completo do proprietário fica coberto pelo gate fechado.
