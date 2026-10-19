# WBS — Prioridades do horário

## Purpose

Decompõe o [Tech Spec — Prioridades do horário](SCHEDULE_PRIORITIES_TECH_SPEC.md) em slices verticais. As decisões, os contratos e os cenários de risco vivem no spec.

## Intended Reader

Agentes que implementam o spec com o skill `cronos-plan-execution`.

## Slices

Os comandos usam o [Test Runner](../00_getting_started/COMMAND_REFERENCE.md); `fast` e `integration` são `node scripts/test.mjs fast` e `node scripts/test.mjs integration`.

| ID | PR | Comportamento | Write set | Teste primeiro | Prova | Depende | Tamanho |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| S1 | PR 1 | Contratos partilhados: coluna, esquemas, chaves, níveis, valores recomendados e campo do snapshot | `backend/alembic/versions/0008_schedule_priorities.py` (novo), `backend/app/models.py`, `backend/app/schemas.py`, `backend/app/scheduler/domain/priorities.py` (novo), `domain/candidate.py`, `domain/serialization.py`, `backend/tests/unit/test_scheduler_priorities_v1.py` (novo), `test_scheduler_candidate_contracts.py` | R01, R02, R03 | `fast --scope backend -- -k "priorities or candidate_contracts"`; depois `integration` e o drift do Alembic (perfil de migração) | — | M |
| S2 | PR 1 | O administrador lê e grava os níveis; mudar deixa a proposta desatualizada; o motor e o fingerprint leem os níveis | `services/settings_service.py`, `api/v1/endpoints/org_settings.py`, `services/scheduler_fingerprint_service.py`, `scheduler/infrastructure/snapshot.py`, `backend/tests/integration/committed/test_schedule_priorities_api.py` (novo), `test_scheduler_fingerprint_service.py` | R17, R18, R19, R20 | `integration -- -k "schedule_priorities or fingerprint"`; depois `integration -- -k scheduler` | S1 | M |
| S3 | PR 1 | A proposta grava as 11 métricas da proposta e do horário publicado | `domain/priority_metrics.py` (novo), `application/publishing.py`, `application/generation.py`, `application/recovery.py`, `backend/tests/unit/test_scheduler_priority_metrics_v1.py` (novo), `test_scheduler_publishing_v1.py` | R11, R12, R13, R14, R21 | `fast --scope backend -- -k "priority_metrics or publishing"` | S1 | M |
| S4 | PR 2 | A construção inicial com pesos: valor das opções, hora vazia, opções necessárias, seleção | `domain/priority_value.py` (novo), `infrastructure/constructive.py`, `backend/tests/unit/test_scheduler_weighted_construction_v1.py` (novo) | R04, R05, R06, R07, R10; R08 continua verde | `fast --scope backend -- -k "weighted_construction or typology or availability_priority or presence"` | S1 | M |
| S5 | PR 2 | A geração e a atualização usam os pesos: repetição sem pesos, escolha entre reparação e reconstrução, salas em Ignorar | `infrastructure/recovery_construction.py`, `infrastructure/search.py`, `test_scheduler_search_fallback_v1.py`, `test_scheduler_recovery_construction_v1.py`, `test_scheduler_weighted_construction_v1.py` | R09, R15, R16 | `fast --scope backend -- -k scheduler`; depois `integration -- -k scheduler` | S3, S4 | M |
| S6 | PR 2 | Ciclo de medição: cenários × perfis × 3 repetições, com tempo, memória e métricas | `backend/app/scheduler/lab/priority_bench.py` (novo), `backend/tests/unit/test_scheduler_priority_bench_v1.py` (novo), [Command Reference](../00_getting_started/COMMAND_REFERENCE.md) | o ciclo numa fixture de 3 turmas e 1 perfil escreve uma linha por repetição com `outcome == "COMPLETE"` e as 11 métricas | `fast --scope backend -- -k priority_bench` | S5 | M |
| S7 | PR 2 | Calibração: custos unitários, otimizações e escolha do responsável de produto | `domain/priorities.py` (só os custos unitários), `infrastructure/constructive.py` e `recovery_construction.py` (só otimizações medidas), `test_scheduler_typology_v1.py`, `.github/workflows/ci.yml` (ids dos testes `slow_solver`) | R24, R25 | `fast --scope backend -- -k typology`; o `e2e-runtime` corre o teste de 48 turmas | S6 | M, repetida |
| S8 | PR 3 | Separador "Prioridades do horário": 11 critérios, 5 botões por critério, textos, guardar e repor | `frontend/src/pages/SchoolConfig.jsx`, `frontend/src/features/schoolConfig/SchedulePrioritiesSection.jsx` (novo), `schedulePriorities.js` (novo), `features/schoolConfig/data.js`, `frontend/src/test/SchedulePrioritiesSection.test.jsx` (novo) | R22 | `fast --scope frontend -- src/test/SchedulePrioritiesSection.test.jsx`; `npm run verify:checks` | S2 | M |
| S9 | PR 3 | A proposta mostra o resumo por critério face ao publicado e o aviso de prioridades não seguidas; guias atualizados | `frontend/src/components/schedules/DraftPanel.jsx`, `frontend/src/test/DraftPanel.test.jsx`, `frontend/e2e/scheduler/priorities.spec.js` (novo), [School Configuration](../02_domain_model/SCHOOL_CONFIGURATION.md), [Scheduler Engine](README.md), [Scheduler V1 Tech Spec](SCHEDULER_V1_TECH_SPEC_V2.md), [Glossary](../00_getting_started/GLOSSARY.md), [Feedback Message Matrix](../06_frontend_ux/FEEDBACK_MESSAGE_MATRIX.md) | R23 | `fast --scope frontend -- src/test/DraftPanel.test.jsx`; `e2e --project app -- -g "schedule priorities"` | S3, S8 | M |

### Notas por slice

- **S1:** a migração só junta a coluna nula; não há valores por escola a migrar. `PriorityWeights` valida as 11 chaves e os níveis; `schemas.py` reutiliza a validação. `snapshot_to_dict` não escreve o campo quando é `None` (R03). O turno da T10 (`shift_of`) também nasce em `priorities.py`, porque a S3 e a S4 o usam.
- **S2:** o `PUT` usa `deps.AdminActor` e `record_scheduler_change(entity_type="SCHEDULE_PRIORITIES")`, como `_sync_school_year_and_record_settings_changes`. `before` e `after` são os níveis resolvidos; iguais dão `NO_OP`.
- **S3:** as métricas reutilizam `_gap_minutes` de `quality.py`, `avoidable_room_changes` de `home_rooms.py` e o turno da T10. `preference_cost_minutes` fica como está; as duas métricas de Evitar são novas e separadas.
- **S4:** com `weights=None`, `_construct_pass` e `_select_period` não mudam. A chave de disponibilidade (`AvailabilityLedger.priority`) só ordena as opções necessárias (T09).
- **S5:** `search.py` chama primeiro com `snapshot.priority_weights`; se dá `None` sem cancelamento nem fim de prazo, chama sem pesos (T11). `_constructive_outcome` grava `objective_scope` `CONSTRUCTIVE_PRIORITIES` (geração) ou `CONSTRUCTIVE_RECOVERY_PRIORITIES` (atualização) quando seguiu os pesos, e o de hoje quando não; `publishing.py` deriva daí `priorities_followed`.
- **S6:** cenários: `build_typology_fixture` (12 e 48), `build_availability_typology_fixture` (12 e 48), `build_joint_typology_fixture` (12), a reparação de `lab/recovery.py` e, por argumento, um ficheiro exportado da escola piloto. Perfis: Recomendado; todos em Importante; Acabar cedo em Ignorar; Tempos livres das turmas em Prioridade máxima com Acabar cedo em Pouco importante; Evitar dos professores em Prioridade máxima; Estabilidade semanal em Prioridade máxima; Mesma sala em Prioridade máxima. A Command Reference ganha o comando do ciclo, no contentor de testes do backend.
- **S7:** cada volta corre o ciclo inteiro, regista os números no pull request, muda um custo unitário ou faz uma otimização medida, e repete. Para quando R24 e R25 passam e duas voltas seguidas melhoram o tempo e o custo menos de 5%. O relatório final propõe o limite de tempo (D17). Antes de abrir o PR 2, o agente mostra ao responsável de produto 3 horários da escola piloto (Recomendado, Acabar cedo em Ignorar, Tempos livres das turmas em Prioridade máxima) com o resumo por critério, e regista a escolha (D16). O teste de 48 turmas entra no `e2e-runtime` pelo id do teste em `ci.yml`.
- **S8:** os botões são `input type="radio"` nativos dentro de `fieldset` com `legend`, com o aspeto de botões lado a lado. "Repor valores recomendados" usa `defaults` do `GET`; só "Guardar prioridades" grava.
- **S9:** o resumo é uma tabela com Critério, Horário publicado e Proposta, e só mostra a coluna do publicado quando `priority_summary.published` existe. O cenário E2E: o administrador abre o separador, muda um nível, guarda e vê a mensagem de sucesso; recarrega e vê o nível gravado.

## Testes existentes que guardam o comportamento

Continuam verdes sem mudança, porque correm sem pesos (I02): `test_scheduler_typology_v1.py` (`TWELVE_CLASS_CONSTRUCTION_DIGEST`), `test_scheduler_availability_priority_v1.py`, `test_scheduler_recovery_construction_v1.py`, `test_scheduler_room_assignment_v1.py`, `test_scheduler_search_fallback_v1.py`, os testes de presença dos professores e os de sala da turma.
Uma slice que precise de mudar um destes testes para e pergunta: a mudança tem de vir de uma decisão do spec.

## Lanes

| Lane | Slices | Ficheiros quentes |
| :--- | :--- | :--- |
| 0 | S1 | `models.py`, `schemas.py`, migração, `candidate.py`, `serialization.py`, `priorities.py` |
| A | S2 → S8 → S9 | — |
| B | S3 | — |
| C | S4 → S5 → S6 → S7 | `search.py` só na S5; `priorities.py` só na S7 (custos unitários) |

A lane 0 corre primeiro e sozinha. As lanes A, B e C partem do seu commit e correm em paralelo, cada uma na sua worktree.
A S5 espera pela S3 (a proposta lê `objective_scope`). A S9 espera pela S3 (o resumo).

## Pull requests

| PR | Merge sozinho porque | Prova local antes do PR | Cenários E2E |
| :--- | :--- | :--- | :--- |
| PR 1 (S1–S3) | coluna nula e API nova sem ecrã; a construção ainda não lê os pesos, por isso os horários não mudam | `integration` completo (migração e contratos), `fast --scope backend`, drift do Alembic | nenhum |
| PR 2 (S4–S7) | os valores recomendados estão calibrados (R24) e o responsável de produto escolheu (D16); sem ecrã, todas as escolas usam os valores recomendados | `fast --scope backend -- -k scheduler`, `integration -- -k scheduler`, relatório do ciclo | nenhum |
| PR 3 (S8–S9) | entra depois do PR 2, para o separador nunca gravar valores sem efeito | `npm run verify:checks`, `e2e --project app` completo, stack local reconstruída na worktree | `schedule priorities` |

## Rastreabilidade

| Decisão ou risco | Slices |
| :--- | :--- |
| D01, D14 | S4, S5, S9 |
| D02, D03, D05, D06, D08, D13 | S1, S8 |
| D04 | S4, S5 |
| D07, D09 | S2, S8 |
| D10, D11 | S2, S5 |
| D12 | S3, S9 |
| D15 | S5, S9 |
| D16, D17 | S6, S7 |
| T01, T02, T03, T04, T15 | S1, S7 |
| T06, T07, T08, T09, T10 | S3, S4 |
| T11, T12, T13, T14, T16 | S3, S5 |
| T17 | S6 |
| R01, R02, R03 | S1 |
| R17, R18, R19, R20 | S2 |
| R11, R12, R13, R14, R21 | S3 |
| R04, R05, R06, R07, R08, R10 | S4 |
| R09, R15, R16 | S5 |
| R24, R25 | S7 |
| R22 | S8 |
| R23 | S9 |

## Related Documents

- [Tech Spec — Prioridades do horário](SCHEDULE_PRIORITIES_TECH_SPEC.md)
- [Command Reference](../00_getting_started/COMMAND_REFERENCE.md)
- [Scheduler Engine](README.md)
