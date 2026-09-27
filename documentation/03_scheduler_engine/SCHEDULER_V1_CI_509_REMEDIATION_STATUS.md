# Scheduler v1 — CI #509: estado da remediação

Data: 27 de setembro de 2026. Branch: `codex/scheduler-v1-revamp`. Commit de partida: `fa86e41`.

Documentos de referência: [WBS da remediação](SCHEDULER_V1_CI_509_REMEDIATION_WBS.md), [plano v2](SCHEDULER_V1_REVAMP_PLAN_V2.md), [WBS v2](SCHEDULER_V1_WBS_V2.md), [especificação v2](SCHEDULER_V1_TECH_SPEC_V2.md).

## 1. Reprodução local (CI509.1)

Os três testes falhados da CI #509 foram reproduzidos na stack Docker local com as chaves Clerk `*_test_` do ambiente. A reprodução usou a base de desenvolvimento e o banco `horario_zen_db`; confirmou as falhas F1–F3 antes das correções. Os três testes voltaram a passar depois das correções (execução de 5 Playwright: `setup`, `auth-state`, dashboard, admin e fresh founder).

Evidência da base de dados depois da aprovação do teste admin:

| Observação | Valor |
| :--- | :--- |
| Organização aprovada | `organization_id = 81` (estado final da organização) |
| Marco de operação | `first_real_schedule_approved_at` nulo depois da aprovação |
| Versão ativa | `scheduler_version_v1` id 2, estado `ACTIVE` |
| Aulas publicadas | 2 aulas, todas em `2026-09-28` |
| Semana consultada pelo teste | `2026-09-07` (início do ano letivo, duas semanas antes da execução) |

## 2. Causas confirmadas

| ID | Causa | Prova |
| :--- | :--- | :--- |
| F1 | `approve_proposal` ativava a versão e publicava o ano, mas nunca escrevia `Organization.first_real_schedule_approved_at`. O dashboard decide o modo por esse marco, por isso ficava em `PREPARATION`. | Reprodução local falhou em `first-schedule-approval-dashboard.spec.js:133`; a coluna ficou nula depois da aprovação. Teste de integração vermelho antes da correção. |
| F2 | O cenário do teste consultava a semana do início do ano letivo, duas semanas no passado. O motor protege períodos já iniciados e só publica no futuro. A publicação funcionou: a versão ativa continha 2 aulas em `2026-09-28`. O defeito era o pressuposto do teste. | Reprodução local falhou em `generation.spec.js:494` com 0 aulas; a consulta SQL confirmou 2 aulas publicadas na semana seguinte. |
| F3 | As mutações de regras chamam `record_scheduler_change`, que incrementava apenas `scheduler_state_version` (motor legado). A elegibilidade v1 compara `planning_revision` com `last_completed_planning_revision`, que nunca mudava. | Reprodução local falhou em `generation.spec.js:647`; quatro testes de integração vermelhos antes da correção. |

## 3. Correções aplicadas

| ID | Correção | Ficheiros |
| :--- | :--- | :--- |
| CI509.2 | `approve_proposal` escreve `first_real_schedule_approved_at` uma única vez, na transação da aprovação, apenas quando a fundação está concluída. A repetição da aprovação e uma nova versão mantêm o marco original; outra organização não é afetada; o rollback preserva o valor nulo. | `backend/app/scheduler/infrastructure/proposals.py`; testes em `backend/tests/integration/committed/test_scheduler_v1_lifecycle.py` |
| CI509.3 | O ensaio usa o início do ano letivo na segunda-feira seguinte e consulta a semana com aulas publicadas. O registo de aula concluída usa o mesmo endpoint do modal (a UI bloqueia `Aula Dada` no futuro por desenho); a ocorrência continua a passar pela UI. As asserções verificam identidade da aula, crédito, dívida, estados na grelha e semanas publicadas. O helper de geração aceita `Gerar horário` e `Atualizar horário`. | `frontend/e2e/scheduler/generation.spec.js`, `frontend/e2e/utils/scheduler-fixtures.js` |
| CI509.4 | `record_change` incrementa `input_revision` e `planning_revision` nas alterações `FUTURE_IMPACTING`, e apenas `input_revision` nas `PAST_ONLY`. Regras com data passada não geram `PLANNING_CHANGE`. A criação, a remoção, a invalidação de proposta pendente e a ausência de efeito ficam cobertas por testes de integração. | `backend/app/services/scheduler_state_service.py`, `backend/app/services/schedule_service.py`; testes em `backend/tests/integration/committed/test_scheduler_v1_rule_revisions.py` |

## 4. Verificação local (CI509.5, parte local)

| Verificação | Resultado |
| :--- | :--- |
| Testes de integração afetados (vermelho antes, verde depois) | `test_scheduler_v1_lifecycle.py`, `test_scheduler_v1_rule_revisions.py` |
| E2E Playwright local (dashboard + generation) | 5 testes verdes (setup, auth-state e os três casos) |
| `pytest tests/unit` | 713 passed |
| `pytest tests/integration` | 307 passed |
| `pytest tests/contracts` | 47 passed |
| `ruff format --check` / `ruff check` | limpos |
| Cobertura | 80% global; `constraint_policy.py` 100% |
| Frontend (`lint`, `test`, `build`, auditoria) | 411 testes verdes; build e auditoria verdes |

## 5. Pendente

- CI desta revisão no GitHub (backend, frontend e E2E no mesmo commit).
- Gate W12: `W12.R1` (percurso de produto para data preferencial e projeção curricular), `W12.R2` (avaliação reservada da política de paragem) e `W12.R3` (aceitação do proprietário).
