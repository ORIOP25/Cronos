# WBS — Sala da turma e tipos de sala

## Purpose

Decompõe o [Tech Spec — Sala da turma e tipos de sala](CLASS_HOME_ROOM_TECH_SPEC.md) em slices verticais.
As decisões (D), as decisões técnicas (T), os invariantes (I) e os cenários de risco (R) vivem no spec.

## Intended Reader

Agentes que implementam com o skill `cronos-plan-execution`, e o responsável de produto.

## Prerequisites

O spec aprovado pelo responsável de produto. Base `main` em `e787aa5`, Alembic `0004_joint_lesson_groups`.
O PR 3 começa depois de o PR 2 da presença dos professores entrar (ver [Coexistência](CLASS_HOME_ROOM_TECH_SPEC.md#coexistência)).

## What the System Does

### Estado

| PR | Slices | Estado | Ligação |
| :--- | :--- | :--- | :--- |
| PR 0 | spec e WBS | proposto | — |
| PR 1 | S1–S4 | por iniciar | — |
| PR 2 | S5 | por iniciar | — |
| PR 3 | S6–S9 | por iniciar | — |
| PR 4 | S10–S11 | por iniciar | — |

### Slices

Tamanhos: **S** até 30 minutos, **M** até 90 minutos.
Os caminhos de teste sem pasta estão em `backend/tests/unit/`; `committed/` é `backend/tests/integration/committed/`.
São 11 slices, acima dos 10 habituais, porque o spec junta duas capacidades ligadas: tipos de sala (D14) e sala da turma.

| ID | PR | Comportamento | Write set | Teste primeiro | Prova | Depende | Tamanho |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| S1 | PR 1 | Cada escola tem os seus tipos de sala; o administrador lista, cria, muda o nome e remove por API; salas e disciplinas gravam `room_type_id`; a fundação cria os 4 iniciais (D15, D17, D19, T01–T03). | `backend/alembic/versions/0006_room_types.py` (novo), `backend/app/models.py`, `backend/app/schemas.py` (tipos, salas, disciplinas), `backend/app/services/room_type_service.py` (novo), `backend/app/api/v1/endpoints/room_types.py` (novo), `backend/app/api/api.py`, `backend/app/services/room_service.py`, `backend/app/services/subject_service.py`, `backend/app/services/foundation_service.py`, `backend/app/services/resource_removal.py`, `backend/app/services/bulk_import_policy.py` (só `fold_text`), `committed/test_room_types.py` (novo), `committed/test_room_type_migration.py` (novo), `committed/test_rooms_crud.py`, `committed/test_subjects_crud.py`, `backend/tests/contracts/test_foundation_service.py`, `documentation/02_domain_model/SCHOOL_CONFIGURATION.md`, `documentation/01_system_architecture/DATA_MODEL.md`, `documentation/05_backend_api/API_REFERENCE.md`, `documentation/00_getting_started/GLOSSARY.md` | R02 (API), R04, R05, R06 em `test_room_types.py`; R03 (`0006`) em `test_room_type_migration.py` | `fast --scope backend`; `integration -- -k "room_type or rooms_crud or subjects_crud or foundation"`; provas de migração | — | M |
| S2 | PR 1 | Os restantes leitores do catálogo usam o tipo da escola: disciplinas da turma, painel com salas por nome de tipo, fábricas de teste e CSV (nome conhecido; desconhecido dá erro até ao S11). | `backend/app/schemas.py` (`SubjectSimple`, `SubjectProgressRead`, `ClassSubjectRead`, `TeacherSubjectProgressRead`), `backend/app/services/class_service.py`, `backend/app/services/dashboard_service.py`, `backend/app/services/bulk_import_policy.py`, `backend/app/services/bulk_import_service.py`, `backend/tests/factories.py`, os testes de integração e de contrato que usam `RoomType` (lista no comando de procura do spec), `test_schemas_validation.py`, `test_bulk_import_policy.py`, `committed/test_bulk_import.py`, `documentation/07_data_and_seed/BULK_IMPORT_CSV.md` | R02 (CSV com tipo de outra escola) em `test_bulk_import.py` | `fast --scope backend`; `integration -- -k "class_subjects or dashboard or bulk_import or tenant or internship or soft_reset or query_budgets"` | S1 | M |
| S3 | PR 1 | O motor, a pré-verificação, a prontidão, o fingerprint, as substituições e a regra `specific_room` comparam tipos por id; as mensagens usam o nome (T05, sem sala da turma). | `backend/app/scheduler/infrastructure/snapshot.py`, `backend/app/services/preflight_service.py`, `backend/app/services/school_readiness_service.py`, `backend/app/services/scheduler_fingerprint_service.py`, `backend/app/scheduler/infrastructure/occurrences.py`, `backend/app/services/schedule_service.py`, `backend/tests/contracts/test_preflight_service.py`, `backend/tests/contracts/test_school_readiness_service.py`, `committed/test_scheduler_fingerprint_service.py`, `committed/test_scheduler_v1_occurrences.py`, `committed/test_scheduler_change_integration.py`, `backend/tests/integration/transactional/test_scheduler_state_service.py` | R07 e R08 (por id) | `fast --scope backend -- -k "scheduler and room"`; `integration -- -k "preflight or readiness or fingerprint or occurrences or scheduler_change or scheduler_state"` | S2 | M |
| S4 | PR 1 | O frontend fala o contrato novo: formulários com os tipos da escola, etiqueta neutra com o nome, salas por tipo no painel, mensagem de sala sem tipo, ajuda do CSV, tutorial e fixtures E2E (D19). | `frontend/src/features/catalog/data.js` (`useRoomTypes`), `frontend/src/components/Forms/RoomForm.jsx`, `frontend/src/components/Forms/SubjectForm.jsx`, `frontend/src/components/RoomTypeBadge.jsx`, `frontend/src/utils/presentation.js`, `frontend/src/pages/Rooms.jsx`, `frontend/src/pages/Subjects.jsx`, `frontend/src/pages/ClassSubjects.jsx`, `frontend/src/pages/ClassDetails.jsx` (só a etiqueta), `frontend/src/components/dashboard/ResourceCounts.jsx`, `frontend/src/utils/apiErrors.js`, `frontend/src/features/imports/data.js`, `frontend/src/features/tutorial/tutorialApiAdapter.js`, `frontend/src/features/tutorial/tutorialScenario.js`, `frontend/e2e/utils/scheduler-fixtures.js`, `frontend/e2e/scheduler/generation.spec.js`, `frontend/e2e/readiness/class-module-selection.spec.js`, os testes `RoomForm`, `SubjectForm`, `Subjects`, `ClassSubjects`, `ClassDetails`, `Dashboard`, `apiErrors`, `tutorialApiAdapter`, `tutorialEngine`, `SchedulesSchedulerFlow` em `frontend/src/test/` | formulários com um tipo "Oficina" vindo de `useRoomTypes` em `RoomForm.test.jsx` e `SubjectForm.test.jsx` | `fast --scope frontend -- <ficheiros de teste do write set>`; `npm run verify:checks`; reconstrução do contentor do frontend; `e2e --project app` quando houver entradas Clerk | S1 | M |
| S5 | PR 2 | O administrador gere os tipos na janela "Tipos de sala" da página Salas; Normal aparece como fixo (D15, D16, D17). | `frontend/src/components/RoomTypesModal.jsx` (novo), `frontend/src/features/catalog/data.js` (mutações), `frontend/src/pages/Rooms.jsx`, `frontend/src/utils/apiErrors.js`, `frontend/src/test/RoomTypesModal.test.jsx` (novo), `documentation/06_frontend_ux/FEEDBACK_MESSAGE_MATRIX.md` | R30 em `RoomTypesModal.test.jsx` | `fast --scope frontend -- src/test/RoomTypesModal.test.jsx`; `npm run verify:checks`; reconstrução do contentor do frontend | PR 1 | M |
| S6 | PR 3 | O administrador define a sala da turma por API; a alteração desatualiza a proposta; remover a sala deixa as turmas em Automática; as salas listam as suas turmas (D01, D08, D09, D10, D13, T04, T12). | `backend/alembic/versions/0007_class_home_room.py` (novo), `backend/app/models.py`, `backend/app/schemas.py` (turma e `RoomRead.home_classes`), `backend/app/services/class_service.py`, `backend/app/services/room_service.py`, `backend/app/services/resource_removal.py`, `backend/app/services/scheduler_fingerprint_service.py`, `committed/test_classes_crud.py`, `committed/test_rooms_crud.py`, `committed/test_resource_removal.py`, `committed/test_query_budgets.py`, `committed/test_scheduler_fingerprint_service.py`, `committed/test_room_type_migration.py`, `documentation/05_backend_api/API_REFERENCE.md`, `documentation/02_domain_model/SCHOOL_CONFIGURATION.md`, `documentation/01_system_architecture/DATA_MODEL.md` | R01, R09 (API), R10 em `test_classes_crud.py`; R11 em `test_resource_removal.py`; R29; R03 (`0007`) | `fast --scope backend`; `integration -- -k "classes_crud or rooms_crud or resource_removal or query_budgets or fingerprint or migration"`; provas de migração | PR 1 | M |
| S7 | PR 3 | A sala da turma entra na elegibilidade e no snapshot: disciplinas Normais podem ir para a sala da turma de qualquer tipo; pré-verificação, prontidão e substituições concordam (D02, D06, D12, D13, T05, T06, T13). | `backend/app/scheduler/domain/constraint_policy.py`, `backend/app/scheduler/domain/candidate.py`, `backend/app/scheduler/domain/serialization.py`, `backend/app/scheduler/infrastructure/snapshot.py`, `backend/app/services/preflight_service.py`, `backend/app/services/school_readiness_service.py`, `backend/app/scheduler/infrastructure/occurrences.py`, `test_scheduler_room_eligibility.py`, `test_scheduler_candidate_contracts.py`, `committed/test_scheduler_home_room_snapshot.py` (novo), `backend/tests/contracts/test_preflight_service.py`, `backend/tests/contracts/test_school_readiness_service.py`, `committed/test_scheduler_v1_occurrences.py`, `documentation/03_scheduler_engine/SCHEDULER_V1_TECH_SPEC_V2.md` | R12, R13 em `test_scheduler_room_eligibility.py`; R14; R09 (snapshot); R08 (sala da turma) | `fast --scope backend -- -k "scheduler and (room or contracts or serialization)"`; `integration -- -k "home_room or preflight or readiness or occurrences"`; cobertura de 100% de `constraint_policy.py` | S6 | M |
| S8 | PR 3 | A qualidade mede falhas de sala da turma e mudanças evitáveis; os vetores ordenam-nas depois do tempo; a mudança justificada não conta como perturbação; a proposta traz as métricas (D10, D11, T07, T08). | `backend/app/scheduler/domain/home_rooms.py` (novo), `backend/app/scheduler/domain/quality.py`, `backend/app/scheduler/domain/recovery.py`, `backend/app/scheduler/infrastructure/search.py` (só `_flatten_vector`), `backend/app/scheduler/application/publishing.py`, `test_scheduler_home_rooms_v1.py` (novo), `test_scheduler_quality.py`, `test_scheduler_initial_quality_v1.py`, `test_scheduler_adaptive_quality_v1.py`, `test_scheduler_publishing_v1.py`, `documentation/03_scheduler_engine/SCHEDULER_V1_TECH_SPEC_V2.md`, `documentation/00_getting_started/GLOSSARY.md` | R15, R16; R21 (medição) em `test_scheduler_home_rooms_v1.py` | `fast --scope backend -- -k "scheduler and (quality or publishing or home_rooms or recovery)"` | S7 | M |
| S9 | PR 3 | Todas as rotas escolhem a sala pela política: sala da turma, mesma alternativa no dia, sala habitual, mesma sala especial; as horas nunca mudam (D01, D03–D07, D10, T09–T11). | `backend/app/scheduler/infrastructure/room_assignment.py` (novo), `backend/app/scheduler/infrastructure/search.py`, `backend/app/scheduler/infrastructure/placement_model.py`, `test_scheduler_room_assignment_v1.py` (novo), `test_scheduler_search_fallback_v1.py`, `test_scheduler_generation_quality_v1.py`, `test_scheduler_recovery_construction_v1.py`, `test_scheduler_search_v1.py`, `test_scheduler_typology_v1.py`, `test_scheduler_w05_audit.py` (T14), `documentation/03_scheduler_engine/README.md`, `documentation/03_scheduler_engine/SCHEDULER_V1_TECH_SPEC_V2.md` | R17–R20, R22 em `test_scheduler_room_assignment_v1.py`; R21 (rota); R23 | `fast --scope backend -- -k scheduler`; `fast --scope backend -- -m slow_solver` (R24); `integration -- -k scheduler` | S8 | M |
| S10 | PR 4 | A página da turma edita e mostra a sala da turma com o aviso de lotação; remover uma sala diz que turmas passam a Automática; a proposta mostra as mudanças evitáveis (D01, D05, D08, D09, D11, D13). | `frontend/src/pages/ClassDetails.jsx`, `frontend/src/pages/Rooms.jsx`, `frontend/src/components/SmartTable.jsx`, `frontend/src/components/schedules/DraftPanel.jsx`, `frontend/src/test/ClassDetails.test.jsx`, `frontend/src/test/DraftPanel.test.jsx`, `frontend/src/test/Rooms.test.jsx` (novo), `documentation/06_frontend_ux/FEEDBACK_MESSAGE_MATRIX.md` | R27 em `ClassDetails.test.jsx`; R28 em `DraftPanel.test.jsx`; confirmação com turmas em `Rooms.test.jsx` | `fast --scope frontend -- src/test/ClassDetails.test.jsx src/test/DraftPanel.test.jsx src/test/Rooms.test.jsx`; `npm run verify:checks`; reconstrução do contentor do frontend | PR 3 | M |
| S11 | PR 4 | O CSV cria tipos novos e mostra-os na pré-visualização; "Cursos e turmas" aceita "Sala da turma" (D18, D20, T03). | `backend/app/services/bulk_import_policy.py`, `backend/app/services/bulk_import_service.py`, `frontend/src/features/imports/data.js`, `frontend/src/pages/BulkImport.jsx`, `documentation/07_data_and_seed/sample_import_48_classes/Cronos_CursosETurmas_Template.csv`, `test_bulk_import_policy.py`, `committed/test_bulk_import.py`, `frontend/src/test/BulkImport.test.jsx`, `frontend/src/test/importFiles.test.js`, `documentation/07_data_and_seed/BULK_IMPORT_CSV.md` | R25, R26 em `test_bulk_import_policy.py`; R02 (sala de outra escola) em `test_bulk_import.py` | `fast --scope backend -- -k bulk_import`; `integration -- -k bulk_import`; `fast --scope frontend -- src/test/BulkImport.test.jsx src/test/importFiles.test.js` | PR 3 | M |

O S2 encontra os testes que usam o enum com uma procura por `RoomType` e `required_room_type` em `backend/tests/`.
Os comandos estão na [Command Reference](../00_getting_started/COMMAND_REFERENCE.md) (`node scripts/test.mjs <perfil>`).
As provas de migração são as de [Backend checks outside the runner](../00_getting_started/COMMAND_REFERENCE.md#backend-checks-outside-the-runner).
A reconstrução do contentor do frontend é a do [AGENTS.md](../../AGENTS.md#mandatory-practices-on-every-task).

## Why the Behavior Exists

Cada slice entrega comportamento observável com os seus testes. Cada pull request entra sozinho e mantém `main` publicável.
O S1 tira o enum. Até ao S3, só a prova de cada slice tem de passar; o PR 1 só abre com S1–S4 completos.

## Components and Ownership

### Lanes

| Lane | Slices | Ficheiros quentes |
| :--- | :--- | :--- |
| A | S1 → S2 → S3 | `models.py`, `schemas.py` (S1, S2, S6), `room_service.py` e `resource_removal.py` (S1, S6), `class_service.py` (S2, S6), `bulk_import_policy.py` e `bulk_import_service.py` (S1, S2, S11), `API_REFERENCE.md` (S1, S6) |
| B | S4, depois do S1 | `features/catalog/data.js` e `Rooms.jsx` (S4, S5, S10), `features/imports/data.js` (S4, S11), `apiErrors.js` (S4, S5) |
| C | S5, depois do PR 1 | `features/catalog/data.js`, `Rooms.jsx`, `FEEDBACK_MESSAGE_MATRIX.md` (S5, S10) |
| D | S6 → S7 → S8 → S9, depois do PR 1 | `snapshot.py`, `preflight_service.py`, `school_readiness_service.py`, `occurrences.py` (S3, S7), `scheduler_fingerprint_service.py` (S3, S6), `search.py` (S8, S9), `SCHEDULER_V1_TECH_SPEC_V2.md` (S7, S8, S9) |
| E | S10, depois do PR 3 | `Rooms.jsx`, `FEEDBACK_MESSAGE_MATRIX.md` |
| F | S11, depois do PR 3 | `bulk_import_policy.py`, `bulk_import_service.py`, `features/imports/data.js` |

Os slices de lanes diferentes correm em paralelo, cada um na sua worktree.
A lane B usa o contrato do S1 e testes com respostas simuladas; junta-se ao ramo do PR 1 antes de o abrir.
As lanes C e D correm em paralelo depois do PR 1; as lanes E e F correm em paralelo depois do PR 3.
Num ficheiro quente partilhado entre lanes, cada slice escreve na sua própria função ou secção; quem entra depois faz rebase.

### Pull requests

| PR | Merge sozinho porque | Prova local antes do PR |
| :--- | :--- | :--- |
| PR 1 | Muda o contrato dos tipos no servidor e no frontend ao mesmo tempo. As escolas mantêm os 4 tipos e o motor dá o mesmo resultado. | perfis de migração, de endpoint, de RLS (`integration` completo) e de componente frontend; reconstrução do contentor do frontend |
| PR 2 | Usa só a API do PR 1. | perfil de componente frontend; reconstrução do contentor do frontend |
| PR 3 | Sem o PR 4, nenhuma turma tem sala definida no ecrã: o motor melhora as turmas em Automática e a proposta passa a ter as métricas na API. | perfis de migração (`integration` completo), de endpoint, de solver com `slow_solver` e de jobs do motor; medição da fixture de 48 turmas no pull request |
| PR 4 | Usa só a API do PR 3. | perfis de endpoint e de componente frontend; reconstrução do contentor do frontend |

## Data or Request Flow

Caminho crítico: S1 → S2 → S3 → merge do PR 1 → S6 → S7 → S8 → S9 → merge do PR 3 → PR 4.
O S4 corre ao lado do S2 e do S3. O PR 2 corre ao lado do PR 3.

## Contracts and Invariants

### Rastreabilidade

| Decisão ou risco | Slices |
| :--- | :--- |
| D01 | S6, S9, S10 |
| D02, D12 | S7, S10 |
| D03, D04, D07, T09, T10, T11, T14 | S9 |
| D05 | S9, S10 |
| D06 | S7, S9 |
| D08, D09 | S6, S10 |
| D10 | S6, S8, S9 |
| D11 | S8, S10 |
| D13 | S6, S7, S10 |
| D14 | ordem dos pull requests: PR 1 e PR 2 antes do PR 4 |
| D15, D17 | S1, S5 |
| D16 | S5 |
| D18, D20 | S11 |
| D19 | S1, S2, S4 |
| T01, T02 | S1 |
| T03 | S1, S11 |
| T04, T12 | S6 |
| T05, T06, T13 | S7 |
| T07, T08 | S8 |
| R01, R10, R11, R29 | S6 |
| R02 | S1, S2, S11 |
| R03 | S1, S6 |
| R04, R05, R06 | S1 |
| R07 | S3 |
| R08 | S3, S7 |
| R09 | S6, S7 |
| R12, R13, R14 | S7 |
| R15, R16 | S8 |
| R17–R20, R22, R23, R24 | S9 |
| R21 | S8, S9 |
| R25, R26 | S11 |
| R27, R28 | S10 |
| R30 | S5 |

## Failure Modes

Se a medição do S9 mostrar que o passe de salas pesa no tempo da geração, registe o tempo no pull request e diga-o ao responsável de produto.
Não desligue o passe nem enfraqueça o validador. Reduza só o custo do passe (por exemplo, reutilizar o grafo por grupo de horas).
Se a fixture de 48 turmas com 14 salas Normais mostrar muitas mudanças evitáveis, é um limite das salas da escola, não do motor: diga-o no relatório.

## Verification Procedure

Cada slice passa a sua prova antes do commit. Cada pull request passa os checks obrigatórios da CI antes do merge (ver [AGENTS.md](../../AGENTS.md#git-ci-and-delivery)).
Atualize a tabela de estado nas fronteiras de pull request.

## Related Documents

- [Tech Spec — Sala da turma e tipos de sala](CLASS_HOME_ROOM_TECH_SPEC.md)
- [Command Reference](../00_getting_started/COMMAND_REFERENCE.md)
- [Scheduler V1 Tech Spec](../03_scheduler_engine/SCHEDULER_V1_TECH_SPEC_V2.md)
