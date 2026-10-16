# WBS — Presença dos professores

## Purpose

Decompõe o [Tech Spec — Presença dos professores](TEACHER_PRESENCE_TECH_SPEC.md) em slices verticais.
As decisões (D), as decisões técnicas (T), os invariantes (I) e os cenários de risco (R) vivem no spec.

## Intended Reader

Agentes que implementam com o skill `cronos-plan-execution`, e o responsável de produto.

## Prerequisites

O spec aprovado pelo responsável de produto. Base `main` em `e787aa5`, Alembic `0004_joint_lesson_groups`.

## What the System Does

### Estado

| PR | Slices | Estado | Ligação |
| :--- | :--- | :--- | :--- |
| PR 0 | spec e WBS | incluído no PR 2 | [#147](https://github.com/ORIOP25/Cronos/pull/147) |
| PR 1 | S1 | merged | [#146](https://github.com/ORIOP25/Cronos/pull/146) |
| PR 2 | S2–S7 | merged | [#147](https://github.com/ORIOP25/Cronos/pull/147) |
| PR 3 | S8–S9 | merged | [#148](https://github.com/ORIOP25/Cronos/pull/148) |
| PR 4 | S10 | merged | [#149](https://github.com/ORIOP25/Cronos/pull/149) |

Seguimento do QA: a pré-verificação passa a abranger a atualização de horários publicados e a admissão na fila rejeita mínimos comprovadamente impossíveis antes de criar o job. O motor repete a verificação antes da pesquisa. O cancelamento interrompe a pesquisa nativa, mantém o estado pendente na interface e preserva `CANCELLED` quando o worker termina após o pedido. A construção só verifica cancelamento nas suas fronteiras; instâncias grandes viáveis ainda podem esgotar memória. Ver [comportamentos e limitações do motor](../03_scheduler_engine/README.md#key-behaviors).

Provas e limitações do PR 2, medidas na árvore de trabalho `teacher-presence-impl`:

- S2–S7 estão implementados e provados; o PR 2 entrou em `main` no [#147](https://github.com/ORIOP25/Cronos/pull/147). O PR 1 (S1) entrou em `main` no [#146](https://github.com/ORIOP25/Cronos/pull/146). O PR 3 (S8–S9) entrou em `main` no [#148](https://github.com/ORIOP25/Cronos/pull/148). O PR 4 (S10) entrou em `main` no [#149](https://github.com/ORIOP25/Cronos/pull/149).
- Fixture de 48 turmas com regras de presença (professor 1001, mínimo 3 h, furo 2 h): a construção rápida devolve `None` em 6,2 s e o caminho exato devolve `COMPLETE` com um candidato válido em **848,4 s**. É uma limitação de desempenho perto do orçamento de 900 s, não um bloqueio; a regra e o validador não foram enfraquecidos.
- Desvio de TDD no S6: a heurística de continuação de presença foi implementada antes do teste de falha na primeira passagem. Na correção, o teste de falha (grelha 60 min + intervalo de 5 min) foi escrito primeiro e a heurística passou a usar posições de bloco. Não há "red" retroativo.

### Slices

Tamanhos: **S** até 30 minutos, **M** até 90 minutos.
Os caminhos de teste sem pasta estão em `backend/tests/unit/`.

| ID | PR | Comportamento | Write set | Teste primeiro | Prova | Depende | Tamanho |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| S1 | PR 1 | O assistente inicial propõe 09:00–18:00, aulas de 60 minutos, intervalos de 5 e almoço 12:00–14:00/60 (D19). | `frontend/src/features/foundation/foundationModel.js`, `frontend/src/features/foundation/components/OpeningStep.jsx`, `LunchStep.jsx`, `SlotDurationStep.jsx`, `frontend/src/features/timetable/breakTimeline.js`, `frontend/src/test/foundationModel.test.js`, `documentation/02_domain_model/SCHOOL_CONFIGURATION.md` | R21 em `foundationModel.test.js` | `fast --scope frontend -- src/test/foundationModel.test.js`; `npm run verify:checks`; reconstrução do contentor do frontend | — | S |
| S2 | PR 2 | O administrador grava e lê a presença de um professor por API; a Equipa recebe-a; a alteração regista a revisão do motor e muda o fingerprint (D01, D02, D05, D06, D14, D15, T01, T02). | `backend/alembic/versions/0005_teacher_presence.py` (novo), `backend/app/models.py`, `backend/app/schemas.py`, `backend/app/services/teacher_service.py`, `backend/app/api/v1/endpoints/teachers.py`, `backend/app/services/member_service.py`, `backend/app/services/scheduler_fingerprint_service.py`, `backend/tests/integration/committed/test_teacher_presence.py` (novo), `backend/tests/integration/committed/test_scheduler_fingerprint_service.py`, `documentation/05_backend_api/API_REFERENCE.md`, `documentation/02_domain_model/SCHOOL_CONFIGURATION.md`, `documentation/00_getting_started/GLOSSARY.md` | R01, R02, R09 (revisão e fingerprint), R11, R12, R19, R20, R25 (fingerprint) em `test_teacher_presence.py` | `fast --scope backend`; `integration -- -k "teacher_presence or fingerprint"`; provas de migração (R17) | — | M |
| S3 | PR 2 | O snapshot transporta as regras; o validador recusa uma presença abaixo do mínimo ou com furo acima do máximo e dispensa o almoço de quem não o exige (D03, D04, D06, D07, T03, T04, T07). | `backend/app/scheduler/domain/candidate.py`, `backend/app/scheduler/domain/teacher_presence.py` (novo), `backend/app/scheduler/domain/candidate_validation.py`, `backend/app/scheduler/domain/serialization.py`, `backend/app/scheduler/infrastructure/snapshot.py`, `backend/app/scheduler/infrastructure/placement_model.py` (só a importação de `lunch_options`), `backend/tests/critical_manifest.json`, `test_scheduler_teacher_presence_v1.py` (novo), `test_scheduler_lunch_break_v1.py`, `test_scheduler_candidate_contracts.py`, `backend/tests/integration/committed/test_teacher_presence.py`, `documentation/03_scheduler_engine/SCHEDULER_V1_TECH_SPEC_V2.md` | R04–R07, R03 e R08 (validação) em `test_scheduler_teacher_presence_v1.py`; R25 (digest) em `test_scheduler_candidate_contracts.py`; R09 (digest) em `test_teacher_presence.py` | `fast --scope backend -- -k "scheduler and (presence or lunch or validation or contracts)"`; `integration -- -k teacher_presence` | S2 | M |
| S4 | PR 2 | O motor coloca aulas de um professor dispensado na janela de almoço, nas três rotas (D06). | `backend/app/scheduler/infrastructure/placement_model.py`, `backend/app/scheduler/infrastructure/constructive.py`, `backend/app/scheduler/infrastructure/recovery_construction.py`, `test_scheduler_lunch_solver_v1.py`, `test_scheduler_recovery_construction_v1.py`, `documentation/03_scheduler_engine/SCHEDULER_V1_TECH_SPEC_V2.md` | R03 (motor) em `test_scheduler_lunch_solver_v1.py` | `fast --scope backend -- -k "scheduler and lunch"` | S3 | S |
| S5 | PR 2 | O caminho exato cumpre o mínimo e o furo por presença, com a divisão pelo almoço; o plano anual aplica a T05 (D03, D04, D05, D10, T05). | `backend/app/scheduler/infrastructure/placement_model.py`, `backend/app/scheduler/infrastructure/annual_model.py`, `test_scheduler_teacher_presence_v1.py`, `test_scheduler_annual_planning_v1.py`, `documentation/03_scheduler_engine/SCHEDULER_V1_TECH_SPEC_V2.md` | R22 e R08 (solver) em `test_scheduler_teacher_presence_v1.py`; R14 em `test_scheduler_annual_planning_v1.py` | `fast --scope backend -- -k scheduler` | S4 | M |
| S6 | PR 2 | A construção rápida e a reparação respeitam a regra ou desistem; a pesquisa termina pelo caminho exato; a fixture de 48 turmas com regras é medida (D07, D16, T10). Só importa de `teacher_presence.py`. | `backend/app/scheduler/infrastructure/constructive.py`, `backend/app/scheduler/infrastructure/recovery_construction.py`, `backend/app/scheduler/lab/typology.py`, `test_scheduler_constructive_progress_v1.py`, `test_scheduler_search_fallback_v1.py`, `test_scheduler_recovery_solver_v1.py`, `test_scheduler_typology_v1.py`, `documentation/03_scheduler_engine/README.md` | R13 em `test_scheduler_search_fallback_v1.py`; R08 (reparação) e R18 em `test_scheduler_recovery_solver_v1.py` | `fast --scope backend -- -k scheduler`; `fast --scope backend -- -m slow_solver` | S5 | M |
| S7 | PR 2 | A pré-verificação bloqueia e nomeia o professor sem presença possível; a falha da geração ou da reparação lista os professores com mínimo; o painel mostra a mensagem (D08, D09, T09). | `backend/app/scheduler/domain/teacher_presence.py`, `backend/app/services/preflight_service.py`, `backend/app/scheduler/domain/diagnostics.py`, `backend/app/scheduler/application/generation.py`, `backend/app/scheduler/application/recovery.py`, `backend/app/scheduler/application/publishing.py`, `backend/app/scheduler/infrastructure/queries.py`, `backend/app/scheduler/infrastructure/jobs.py`, `backend/app/schemas.py`, `frontend/src/components/schedules/GenerationStatusPanel.jsx`, `backend/tests/contracts/test_preflight_service.py`, `test_scheduler_diagnostics_v1.py`, `test_scheduler_generation_v1.py`, `test_scheduler_recovery_v1.py`, `frontend/src/test/GenerationStatusPanel.test.jsx`, `documentation/06_frontend_ux/FEEDBACK_MESSAGE_MATRIX.md`, `documentation/03_scheduler_engine/SCHEDULER_V1_TECH_SPEC_V2.md` | R15 em `test_preflight_service.py`; R16 em `test_scheduler_diagnostics_v1.py`, `test_scheduler_recovery_v1.py` e `GenerationStatusPanel.test.jsx` | `fast --scope backend -- -k "preflight or diagnostics or generation or recovery"`; `integration -- -k "preflight or scheduler"`; `fast --scope frontend -- src/test/GenerationStatusPanel.test.jsx`; reconstrução do contentor do frontend | S3 | M |
| S8 | PR 3 | O administrador edita a presença na secção "Presença na escola" do modal; a Equipa mostra as etiquetas (D05, D06, D11, D12, T08). | `frontend/src/components/AvailabilityEditorModal.jsx`, `frontend/src/components/TeacherAvailabilityModal.jsx`, `frontend/src/components/TeacherPresenceSection.jsx` (novo), `frontend/src/features/operations/data.js`, `frontend/src/pages/Members.jsx`, `frontend/src/test/TeacherAvailabilityModal.test.jsx`, `frontend/src/test/Members.test.jsx`, `frontend/src/test/ClassAvailabilityModal.test.jsx`, `documentation/06_frontend_ux/FEEDBACK_MESSAGE_MATRIX.md`, `documentation/02_domain_model/SCHOOL_CONFIGURATION.md` | R11, R23 e R24 em `TeacherAvailabilityModal.test.jsx`; etiquetas em `Members.test.jsx` | `fast --scope frontend -- src/test/TeacherAvailabilityModal.test.jsx src/test/Members.test.jsx src/test/ClassAvailabilityModal.test.jsx`; `npm run verify:checks`; reconstrução do contentor do frontend | S2 | M |
| S9 | PR 3 | O professor vê a regra só em leitura em "Minhas Preferências", também no tutorial (D13). | `frontend/src/pages/MyAvailability.jsx`, `frontend/src/features/operations/data.js`, `frontend/src/features/tutorial/tutorialApiAdapter.js`, `frontend/src/test/MyAvailability.test.jsx`, `frontend/src/test/tutorialApiAdapter.test.js` | cartão só de leitura em `MyAvailability.test.jsx` | `fast --scope frontend -- src/test/MyAvailability.test.jsx src/test/tutorialApiAdapter.test.js`; `npm run verify:checks` | S8 | S |
| S10 | PR 4 | O administrador descarrega o modelo "Presença dos professores" preenchido e importa-o em massa (D18). | `backend/app/services/bulk_import_policy.py`, `backend/app/services/bulk_import_service.py`, `backend/app/services/teacher_service.py`, `backend/app/schemas.py`, `frontend/src/features/imports/data.js`, `frontend/src/pages/BulkImport.jsx`, `test_bulk_import_policy.py`, `backend/tests/integration/committed/test_bulk_import.py`, `frontend/src/test/BulkImport.test.jsx`, `frontend/src/test/importFiles.test.js`, `frontend/src/test/importInvalidations.test.jsx`, `documentation/07_data_and_seed/BULK_IMPORT_CSV.md`, `documentation/05_backend_api/API_REFERENCE.md` | R10 em `test_bulk_import_policy.py`; R02 (CSV) em `test_bulk_import.py` | `fast --scope backend -- -k bulk_import`; `integration -- -k bulk_import`; `fast --scope frontend -- src/test/BulkImport.test.jsx src/test/importFiles.test.js src/test/importInvalidations.test.jsx` | S2 | M |

Os comandos estão na [Command Reference](../00_getting_started/COMMAND_REFERENCE.md) (`node scripts/test.mjs <perfil>`).
As provas de migração do S2 são as de [Backend checks outside the runner](../00_getting_started/COMMAND_REFERENCE.md#backend-checks-outside-the-runner).
A reconstrução do contentor do frontend é a do [AGENTS.md](../../AGENTS.md#mandatory-practices-on-every-task).

## Why the Behavior Exists

Cada slice entrega comportamento observável com os seus testes. Cada pull request entra sozinho e mantém `main` publicável.

## Components and Ownership

### Lanes

| Lane | Slices | Ficheiros quentes |
| :--- | :--- | :--- |
| A | S1 | `SCHOOL_CONFIGURATION.md` (S1, S2, S8) |
| B | S2 → S3 → S4 → S5 → S6 | `placement_model.py` (S3, S4, S5), `constructive.py` e `recovery_construction.py` (S4, S6), `schemas.py` (S2, S7, S10), `SCHEDULER_V1_TECH_SPEC_V2.md` (S3, S4, S5, S7), `API_REFERENCE.md` (S2, S10) |
| C | S7, depois do S3 | `teacher_presence.py` (S3, S7; o S6 só importa), `schemas.py`, `FEEDBACK_MESSAGE_MATRIX.md` (S7, S8) |
| D | S8 → S9, depois do S2 | `features/operations/data.js` (S8, S9), `FEEDBACK_MESSAGE_MATRIX.md`, `SCHOOL_CONFIGURATION.md` |
| E | S10, depois do S2 | `teacher_service.py` (S2, S10), `schemas.py`, `API_REFERENCE.md` |

Os slices de lanes diferentes correm em paralelo, cada um na sua worktree.
A lane A não depende de nada. As lanes D e E podem trabalhar sobre o ramo do PR 2, mas só abrem pull request depois de o PR 2 entrar.
Num ficheiro quente partilhado entre lanes, cada slice escreve na sua própria classe, função ou secção; quem entra depois faz rebase.

### Pull requests

| PR | Merge sozinho porque | Prova local antes do PR |
| :--- | :--- | :--- |
| PR 1 | Só muda os valores propostos a escolas novas; as grelhas configuradas ficam iguais. | perfil de componente frontend; reconstrução do contentor do frontend |
| PR 2 | Não tem ecrã de edição: sem PR 3 ou PR 4, ninguém altera a regra e o motor comporta-se como hoje. | perfis de solver (com `slow_solver`), de endpoint, de migração e de jobs do motor; perfil de componente frontend e reconstrução do contentor do frontend; medição da fixture de 48 turmas no pull request |
| PR 3 | Usa só a API do PR 2. | perfil de componente frontend; reconstrução do contentor do frontend |
| PR 4 | Usa só o serviço do PR 2. | perfis de endpoint e de componente frontend |

## Data or Request Flow

Caminho crítico: S2 → S3 → S4 → S5 → S6 → merge do PR 2 → PR 3 e PR 4.
O S1 e o PR 1 podem entrar a qualquer momento.

## Contracts and Invariants

### Rastreabilidade

| Decisão ou risco | Slices |
| :--- | :--- |
| D01, D02, D14, T01, T02 | S2 |
| D03, D04 | S3, S5 |
| D05 | S2, S5, S8 |
| D06 | S2, S3, S4, S8 |
| D07 | S3, S6 |
| D08, D09, T09 | S7 |
| D10, T05 | S5 |
| D11, D12, T08 | S8 |
| D13 | S9 |
| D15 | S2 |
| D16, T04 | S3, S6 |
| D17 | fora de âmbito; nenhum slice toca nas substituições |
| D18 | S10 |
| D19 | S1 |
| T03, T06, T07 | S3 |
| T10 | S6 |
| R01, R12, R17, R19, R20 | S2 |
| R02 | S2, S10 |
| R03 | S3, S4 |
| R04–R07 | S3 |
| R08 | S3, S5, S6 |
| R09, R25 | S2, S3 |
| R10 | S10 |
| R11 | S2, S8 |
| R23, R24 | S8 |
| R13, R18 | S6 |
| R14, R22 | S5 |
| R15, R16 | S7 |
| R21 | S1 |

## Failure Modes

Se o S6 mostrar que a construção rápida desiste quase sempre com regras, a geração ainda termina pelo caminho exato, só que mais devagar.
Registe a medição no pull request e diga ao responsável de produto o tempo observado. Não enfraqueça a regra nem o validador.

## Verification Procedure

Cada slice passa a sua prova antes do commit. Cada pull request passa os checks obrigatórios da CI antes do merge (ver [AGENTS.md](../../AGENTS.md#git-ci-and-delivery)).
Atualize a tabela de estado nas fronteiras de pull request.

## Related Documents

- [Tech Spec — Presença dos professores](TEACHER_PRESENCE_TECH_SPEC.md)
- [Command Reference](../00_getting_started/COMMAND_REFERENCE.md)
- [Scheduler V1 Tech Spec](../03_scheduler_engine/SCHEDULER_V1_TECH_SPEC_V2.md)
