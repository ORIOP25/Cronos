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
| PR 0 | spec e WBS | proposto | [#143](https://github.com/ORIOP25/Cronos/pull/143) |
| PR 1 | S1–S6 | por iniciar | — |
| PR 2 | S7 | por iniciar | — |
| PR 3 | S8–S12 | por iniciar | — |
| PR 4 | S13–S14 | por iniciar | — |

### Slices

Tamanhos: **S** até 30 minutos, **M** até 90 minutos.
Os caminhos de teste sem pasta estão em `backend/tests/unit/`; `committed/` é `backend/tests/integration/committed/`; `contracts/` é `backend/tests/contracts/`.
São 14 slices, acima dos 10 habituais: o spec junta duas capacidades (tipos de sala, D14, e sala da turma) e a troca do enum obriga a expandir antes de contrair (T02).
O `integration` corre sempre todos os testes de `contracts/`, com ou sem `-k`. Cada slice deixa-os verdes.

| ID | PR | Comportamento | Write set | Teste primeiro | Prova | Depende | Tamanho |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| S1 | PR 1 | Cada escola tem os seus tipos e o administrador gere-os por API. O enum fica até ao S4 (D15, D17, D19, T01–T04). | `backend/alembic/versions/0006_room_types.py` (novo, parte aditiva), `backend/app/models.py` (`SchoolRoomType`, `room_type_id` nulos), `backend/app/schemas.py` (`RoomTypeRead`, `RoomTypeRef`), `backend/app/services/room_type_service.py` (novo), `backend/app/api/v1/endpoints/room_types.py` (novo), `backend/app/api/api.py`, `backend/app/services/foundation_service.py`, `backend/app/services/resource_removal.py`, `backend/app/services/bulk_import_policy.py` (só `fold_text`), `backend/scripts/privacy.py`, `backend/tests/_support/db_fixtures.py`, `committed/test_room_types.py` (novo), `committed/test_room_type_migration.py` (novo), `contracts/test_foundation_service.py`, `test_rgpd_contracts.py`, `documentation/02_domain_model/SCHOOL_CONFIGURATION.md`, `documentation/01_system_architecture/DATA_MODEL.md`, `documentation/05_backend_api/API_REFERENCE.md`, `documentation/00_getting_started/GLOSSARY.md` | R02 (API), R04, R05, R06 em `test_room_types.py`; R03 (parte aditiva); R31 | `fast --scope backend -- -k "rgpd or privacy or room_type"`; `integration -- -k "room_type or foundation"`; provas de migração | — | M |
| S2 | PR 1 | Salas, disciplinas e os leitores do catálogo usam o tipo da escola; o CSV aceita tipos conhecidos pelo nome (desconhecido dá erro até ao S14). | `backend/app/schemas.py` (as nove utilizações do enum), `backend/app/services/room_service.py`, `backend/app/services/subject_service.py`, `backend/app/services/class_service.py`, `backend/app/services/course_service.py`, `backend/app/services/teacher_service.py`, `backend/app/services/dashboard_service.py`, `backend/app/services/bulk_import_policy.py`, `backend/app/services/bulk_import_service.py`, `backend/tests/factories.py`, `test_schemas_validation.py`, `test_bulk_import_policy.py`, `committed/test_rooms_crud.py`, `committed/test_subjects_crud.py`, `committed/test_class_subjects.py`, `committed/test_courses_endpoints.py`, `committed/test_bulk_import.py`, `committed/test_tenant_isolation_complete.py`, `committed/test_tenant_isolation_business.py`, `committed/test_teacher_competencies.py`, `contracts/test_internship_flow_endpoints.py`, `documentation/05_backend_api/API_REFERENCE.md`, `documentation/07_data_and_seed/BULK_IMPORT_CSV.md` | R02 (CSV com tipo de outra escola) em `test_bulk_import.py`; sala com tipo "Oficina" em `test_rooms_crud.py` | `fast --scope backend -- -k "schemas or bulk_import"`; `integration -- -k "rooms_crud or subjects_crud or class_subjects or courses or bulk_import or tenant or competencies or dashboard"` | S1 | M |
| S3 | PR 1 | O motor, a pré-verificação, a prontidão, o fingerprint, as substituições e `specific_room` comparam tipos por id; as mensagens usam o nome (T06 sem sala da turma). | `backend/app/scheduler/infrastructure/snapshot.py`, `backend/app/services/preflight_service.py`, `backend/app/services/school_readiness_service.py`, `backend/app/services/scheduler_fingerprint_service.py`, `backend/app/scheduler/infrastructure/occurrences.py`, `backend/app/services/schedule_service.py`, `contracts/test_preflight_service.py`, `contracts/test_school_readiness_service.py`, `committed/test_scheduler_fingerprint_service.py`, `committed/test_scheduler_v1_occurrences.py`, `committed/test_scheduler_change_integration.py`, `backend/tests/integration/transactional/test_scheduler_state_service.py` | R07; R08 (por id) | `fast --scope backend -- -k "scheduler and room"`; `integration -- -k "preflight or readiness or fingerprint or occurrences or scheduler_change or scheduler_state"` | S2 | M |
| S4 | PR 1 | O enum sai: `room_type_id` passa a obrigatório e nenhum teste depende do valor por defeito (T01, T02). | `backend/alembic/versions/0006_room_types.py` (parte final), `backend/app/models.py`, `backend/tests/_support/scheduler_v1.py`, `committed/joint_lesson_support.py`, `committed/test_class_module_selection_api.py`, `committed/test_class_module_selection_readers.py`, `committed/test_grid_change_proposal.py`, `committed/test_scheduler_v1_baseline.py`, `committed/test_scheduler_v1_progress.py`, `committed/test_timesheets_v1.py`, `committed/test_joint_lesson_groups.py`, `committed/test_internship_flows.py`, `committed/test_query_budgets.py`, `committed/test_resource_removal.py`, `committed/test_soft_reset.py`, `committed/test_class_availability.py`, `committed/test_joint_lesson_group_migration.py`, `committed/test_class_subject_module_migration.py`, `committed/test_scheduler_v1_api.py`, `contracts/test_rls_database_policies.py`, `committed/test_room_type_migration.py` | R03 (descida e subida completas); R32 | `integration` completo; provas de migração | S3 | M |
| S5 | PR 1 | Os formulários de Sala e Disciplina mostram os tipos da escola; as listas mostram o nome numa etiqueta neutra (D19). | `frontend/src/features/catalog/data.js` (`useRoomTypes`), `frontend/src/components/Forms/RoomForm.jsx`, `frontend/src/components/Forms/SubjectForm.jsx`, `frontend/src/components/RoomTypeBadge.jsx`, `frontend/src/utils/presentation.js`, `frontend/src/pages/Rooms.jsx`, `frontend/src/pages/Subjects.jsx`, `frontend/src/pages/ClassSubjects.jsx`, `frontend/src/pages/ClassDetails.jsx` (só a etiqueta), `frontend/src/test/RoomForm.test.jsx`, `SubjectForm.test.jsx`, `Subjects.test.jsx`, `ClassSubjects.test.jsx`, `ClassDetails.test.jsx` | um tipo "Oficina" vindo de `useRoomTypes` em `RoomForm.test.jsx` e `SubjectForm.test.jsx` | `fast --scope frontend -- <ficheiros de teste do write set>`; `npm run verify:checks` | S2 | M |
| S6 | PR 1 | O painel, as mensagens de pré-verificação, a ajuda do CSV, o tutorial e o E2E usam o contrato novo. | `frontend/src/components/dashboard/ResourceCounts.jsx`, `frontend/src/utils/apiErrors.js`, `frontend/src/features/imports/data.js`, `frontend/src/features/tutorial/tutorialApiAdapter.js`, `frontend/src/features/tutorial/tutorialScenario.js`, `frontend/e2e/utils/scheduler-fixtures.js`, `frontend/e2e/scheduler/generation.spec.js`, `frontend/e2e/readiness/class-module-selection.spec.js`, `frontend/src/test/Dashboard.test.jsx`, `apiErrors.test.js`, `tutorialApiAdapter.test.js`, `tutorialEngine.test.js`, `SchedulesSchedulerFlow.test.jsx`, `BulkImport.test.jsx` | `required_room_type_name` em `apiErrors.test.js`; salas por nome de tipo em `Dashboard.test.jsx` | `fast --scope frontend -- <ficheiros de teste do write set>`; `npm run verify:checks`; reconstrução do contentor do frontend; `e2e --project app` quando houver entradas Clerk | S3, S5 | M |
| S7 | PR 2 | O administrador gere os tipos na janela "Tipos de sala" da página Salas; Normal aparece como fixo (D15, D16, D17). | `frontend/src/components/RoomTypesModal.jsx` (novo), `frontend/src/features/catalog/data.js` (mutações), `frontend/src/pages/Rooms.jsx`, `frontend/src/utils/apiErrors.js`, `frontend/src/test/RoomTypesModal.test.jsx` (novo), `documentation/06_frontend_ux/FEEDBACK_MESSAGE_MATRIX.md` | R30 | `fast --scope frontend -- src/test/RoomTypesModal.test.jsx`; `npm run verify:checks`; reconstrução do contentor do frontend | PR 1 | M |
| S8 | PR 3 | O administrador define a sala da turma por API; a alteração desatualiza a proposta; remover a sala deixa as turmas em Automática; as salas listam as suas turmas (D01, D08, D09, D10, D13, T05, T14). | `backend/alembic/versions/0007_class_home_room.py` (novo), `backend/app/models.py`, `backend/app/schemas.py`, `backend/app/services/class_service.py`, `backend/app/services/room_service.py`, `backend/app/services/resource_removal.py`, `backend/app/services/scheduler_fingerprint_service.py`, `committed/test_classes_crud.py`, `committed/test_rooms_crud.py`, `committed/test_resource_removal.py`, `committed/test_query_budgets.py`, `committed/test_scheduler_fingerprint_service.py`, `committed/test_room_type_migration.py`, `documentation/05_backend_api/API_REFERENCE.md`, `documentation/02_domain_model/SCHOOL_CONFIGURATION.md`, `documentation/01_system_architecture/DATA_MODEL.md` | R01, R09 (API), R10 em `test_classes_crud.py`; R11; R29; R03 (`0007`) | `integration` completo; provas de migração | PR 1 | M |
| S9 | PR 3 | A sala da turma entra na elegibilidade e no snapshot; pré-verificação, prontidão e substituições concordam (D02, D06, D12, D13, T06, T07, T15). | `backend/app/scheduler/domain/constraint_policy.py`, `backend/app/scheduler/domain/candidate.py`, `backend/app/scheduler/domain/serialization.py`, `backend/app/scheduler/infrastructure/snapshot.py`, `backend/app/services/preflight_service.py`, `backend/app/services/school_readiness_service.py`, `backend/app/scheduler/infrastructure/occurrences.py`, `test_scheduler_room_eligibility.py`, `test_scheduler_candidate_contracts.py`, `committed/test_scheduler_home_room_snapshot.py` (novo), `contracts/test_preflight_service.py`, `contracts/test_school_readiness_service.py`, `committed/test_scheduler_v1_occurrences.py`, `documentation/03_scheduler_engine/SCHEDULER_V1_TECH_SPEC_V2.md` | R12, R13, R14; R09 (snapshot); R08 (sala da turma) | `fast --scope backend -- -k "scheduler and (room or contracts or serialization)"`; `integration -- -k "home_room or preflight or readiness or occurrences"`; cobertura de 100% de `constraint_policy.py` | S8 | M |
| S10 | PR 3 | O motor mede falhas de sala da turma e mudanças evitáveis e publica-as na proposta; a mudança justificada não conta como perturbação (D10, D11, T08, T09). | `backend/app/scheduler/domain/home_rooms.py` (novo), `backend/app/scheduler/domain/recovery.py`, `backend/app/scheduler/application/publishing.py`, `test_scheduler_home_rooms_v1.py` (novo), `test_scheduler_publishing_v1.py`, `documentation/03_scheduler_engine/SCHEDULER_V1_TECH_SPEC_V2.md`, `documentation/00_getting_started/GLOSSARY.md` | R15; R21 (medida) | `fast --scope backend -- -k "scheduler and (publishing or home_rooms or recovery)"` | S9 | M |
| S11 | PR 3 | As rotas de produção escolhem a sala pela política: sala da turma, mesma alternativa no dia, sala habitual, mesma sala especial; as horas nunca mudam (D01, D03–D07, T10, T11, T13). | `backend/app/scheduler/infrastructure/room_assignment.py` (novo), `backend/app/scheduler/infrastructure/search.py`, `backend/app/scheduler/infrastructure/placement_model.py`, `test_scheduler_room_assignment_v1.py` (novo), `test_scheduler_search_fallback_v1.py`, `test_scheduler_generation_quality_v1.py`, `test_scheduler_recovery_construction_v1.py`, `test_scheduler_typology_v1.py`, `documentation/03_scheduler_engine/README.md` | R17–R20, R22; R21 e R23 (rotas de produção) | `fast --scope backend -- -k scheduler`; `fast --scope backend -- -m slow_solver` (R24) | S10 | M |
| S12 | PR 3 | O caminho exato aplica o passe com guarda, depois de `_stabilize_recovery` e no incumbente publicado; o resultado certificado nunca piora (T11, T12). | `backend/app/scheduler/infrastructure/search.py`, `backend/app/scheduler/infrastructure/placement_model.py`, `test_scheduler_room_assignment_v1.py`, `test_scheduler_search_v1.py`, `documentation/03_scheduler_engine/SCHEDULER_V1_TECH_SPEC_V2.md` | R16; R21 (incumbente publicado) | `fast --scope backend -- -k scheduler`; `fast --scope backend -- -m slow_solver`; `integration -- -k scheduler` | S11 | M |
| S13 | PR 4 | A página da turma edita e mostra a sala da turma com o aviso de lotação; remover uma sala diz que turmas passam a Automática; a proposta mostra as mudanças evitáveis (D01, D05, D08, D09, D11, D13). | `frontend/src/pages/ClassDetails.jsx`, `frontend/src/pages/Rooms.jsx`, `frontend/src/components/SmartTable.jsx`, `frontend/src/components/schedules/DraftPanel.jsx`, `frontend/src/features/catalog/data.js` (`useUpdateCourseClass` invalida as salas), `frontend/src/test/ClassDetails.test.jsx`, `DraftPanel.test.jsx`, `Rooms.test.jsx` (novo), `documentation/06_frontend_ux/FEEDBACK_MESSAGE_MATRIX.md` | R27, R28; confirmação com turmas em `Rooms.test.jsx` | `fast --scope frontend -- src/test/ClassDetails.test.jsx src/test/DraftPanel.test.jsx src/test/Rooms.test.jsx`; `npm run verify:checks`; reconstrução do contentor do frontend | PR 2, PR 3 | M |
| S14 | PR 4 | O CSV cria tipos novos e mostra-os na pré-visualização; "Cursos e turmas" aceita "Sala da turma" (D18, D20, T04). | `backend/app/services/bulk_import_policy.py`, `backend/app/services/bulk_import_service.py`, `frontend/src/features/imports/data.js`, `frontend/src/pages/BulkImport.jsx`, `documentation/07_data_and_seed/sample_import_48_classes/Cronos_CursosETurmas_Template.csv`, `test_bulk_import_policy.py`, `committed/test_bulk_import.py`, `frontend/src/test/BulkImport.test.jsx`, `frontend/src/test/importFiles.test.js`, `documentation/07_data_and_seed/BULK_IMPORT_CSV.md` | R25, R26; R02 (sala de outra escola) | `fast --scope backend -- -k bulk_import`; `integration -- -k bulk_import`; `fast --scope frontend -- src/test/BulkImport.test.jsx src/test/importFiles.test.js` | PR 3 | M |

Os comandos estão na [Command Reference](../00_getting_started/COMMAND_REFERENCE.md) (`node scripts/test.mjs <perfil>`).
As provas de migração são as de [Backend checks outside the runner](../00_getting_started/COMMAND_REFERENCE.md#backend-checks-outside-the-runner).
A reconstrução do contentor do frontend é a do [AGENTS.md](../../AGENTS.md#mandatory-practices-on-every-task).

## Why the Behavior Exists

Cada slice entrega comportamento observável com os seus testes. Cada pull request entra sozinho e mantém `main` publicável.
O S1 acrescenta sem tirar nada; o S2 e o S3 mudam os leitores; o S4 tira o enum. Por isso cada slice passa a sua prova sozinho (T02).

## Components and Ownership

### Lanes

| Lane | Slices | Ficheiros quentes |
| :--- | :--- | :--- |
| A | S1 → S2 → S3 → S4 | `models.py` (S1, S4, S8), `schemas.py` (S1, S2, S8), `0006_room_types.py` (S1, S4), `resource_removal.py` (S1, S8), `room_service.py` e `class_service.py` (S2, S8), `bulk_import_policy.py` e `bulk_import_service.py` (S1, S2, S14), `scheduler_fingerprint_service.py` (S3, S8), `API_REFERENCE.md` (S1, S2, S8) |
| B | S5 depois do S2; S6 depois do S3 e do S5 | `features/catalog/data.js` (S5, S7, S13), `Rooms.jsx` (S5, S7, S13), `apiErrors.js` (S6, S7), `features/imports/data.js` (S6, S14), `BulkImport.test.jsx` (S6, S14) |
| C | S7, depois do PR 1 | `features/catalog/data.js`, `Rooms.jsx`, `apiErrors.js`, `FEEDBACK_MESSAGE_MATRIX.md` (S7, S13) |
| D | S8 → S9 → S10 → S11 → S12, depois do PR 1 | `snapshot.py`, `preflight_service.py`, `school_readiness_service.py`, `occurrences.py` (S3, S9), `search.py` e `placement_model.py` (S11, S12), `SCHEDULER_V1_TECH_SPEC_V2.md` (S9, S10, S12) |
| E | S13, depois do PR 2 e do PR 3 | `Rooms.jsx`, `features/catalog/data.js`, `FEEDBACK_MESSAGE_MATRIX.md` |
| F | S14, depois do PR 3 | `bulk_import_policy.py`, `bulk_import_service.py`, `features/imports/data.js` |

Os slices de lanes diferentes correm em paralelo, cada um na sua worktree.
A lane B corre ao lado da lane A, com respostas simuladas, e junta-se ao ramo do PR 1 antes de o abrir.
As lanes C e D correm em paralelo depois do PR 1; as lanes E e F correm em paralelo depois do PR 3 (a lane E também espera pelo PR 2).
Num ficheiro quente partilhado entre lanes, cada slice escreve na sua própria função ou secção; quem entra depois faz rebase.

### Pull requests

| PR | Merge sozinho porque | Prova local antes do PR |
| :--- | :--- | :--- |
| PR 1 | Muda o contrato dos tipos no servidor e no frontend ao mesmo tempo. As escolas mantêm os 4 tipos e o motor dá o mesmo resultado. | `integration` completo, provas de migração, perfil de componente frontend, reconstrução do contentor do frontend |
| PR 2 | Usa só a API do PR 1. | perfil de componente frontend; reconstrução do contentor do frontend |
| PR 3 | Sem o PR 4, nenhuma turma tem sala definida no ecrã: o motor melhora as turmas em Automática e a proposta passa a ter as métricas na API. | `integration` completo, provas de migração, perfil de solver com `slow_solver` e de jobs do motor; medição da fixture de 48 turmas no pull request |
| PR 4 | Usa só a API do PR 3. | perfis de endpoint e de componente frontend; reconstrução do contentor do frontend |

## Data or Request Flow

Caminho crítico: S1 → S2 → S3 → S4 → merge do PR 1 → S8 → S9 → S10 → S11 → S12 → merge do PR 3 → PR 4.
O S5 e o S6 correm ao lado do S3 e do S4. O PR 2 corre ao lado do PR 3.

## Contracts and Invariants

### Rastreabilidade

| Decisão ou risco | Slices |
| :--- | :--- |
| D01 | S8, S11, S13 |
| D02, D12 | S9, S13 |
| D03, D04, D07 | S11 |
| D05 | S11, S13 |
| D06 | S9, S11 |
| D08, D09 | S8, S13 |
| D10 | S8, S10, S11, S12 |
| D11 | S10, S13 |
| D13 | S8, S9, S13 |
| D14 | ordem dos pull requests: PR 1 e PR 2 antes do PR 4 |
| D15, D17 | S1, S7 |
| D16 | S7 |
| D18, D20 | S14 |
| D19 | S1, S2, S5 |
| T01, T02 | S1, S4 |
| T03 | S1 |
| T04 | S1, S14 |
| T05, T14 | S8 |
| T06, T07, T15 | S9 |
| T08, T09 | S10 |
| T10, T13 | S11 |
| T11 | S11, S12 |
| T12 | S12 |
| R01, R10, R11, R29 | S8 |
| R02 | S1, S2, S14 |
| R03 | S1, S4, S8 |
| R04, R05, R06, R31 | S1 |
| R07 | S3 |
| R08 | S3, S9 |
| R09 | S8, S9 |
| R12, R13, R14 | S9 |
| R15 | S10 |
| R16 | S12 |
| R17–R20, R22, R24 | S11 |
| R21 | S10, S11, S12 |
| R23 | S11 |
| R25, R26 | S14 |
| R27, R28 | S13 |
| R30 | S7 |
| R32 | S4 |

## Failure Modes

Se a medição do S11 mostrar que o passe de salas pesa no tempo da geração, registe o tempo no pull request e diga-o ao responsável de produto.
Não desligue o passe nem enfraqueça o validador. Reduza só o custo do passe, por exemplo reutilizando o grafo por grupo de horas.
Se a fixture de 48 turmas com 14 salas Normais mostrar muitas mudanças evitáveis, é um limite das salas da escola, não do motor: diga-o no relatório.

## Verification Procedure

Cada slice passa a sua prova antes do commit. Cada pull request passa os checks obrigatórios da CI antes do merge (ver [AGENTS.md](../../AGENTS.md#git-ci-and-delivery)).
Atualize a tabela de estado nas fronteiras de pull request.

## Related Documents

- [Tech Spec — Sala da turma e tipos de sala](CLASS_HOME_ROOM_TECH_SPEC.md)
- [Command Reference](../00_getting_started/COMMAND_REFERENCE.md)
- [Scheduler V1 Tech Spec](../03_scheduler_engine/SCHEDULER_V1_TECH_SPEC_V2.md)
