# WBS — Prioridade a quem tem pouca disponibilidade

## Purpose

Decompõe o [Tech Spec — Prioridade a quem tem pouca disponibilidade](AVAILABILITY_PRIORITY_TECH_SPEC.md) em slices verticais.
As decisões (D), as decisões técnicas (T), os invariantes (I) e os cenários de risco (R) vivem no spec.

## Intended Reader

Agentes que implementam com o skill `cronos-plan-execution`, e o responsável de produto.

## Prerequisites

O spec aprovado pelo responsável de produto. Base `main` em `01a011e9`, Alembic `0005_teacher_presence`.

## What the System Does

### Slices

Os comandos são perfis do `node scripts/test.mjs` da [Command Reference](../00_getting_started/COMMAND_REFERENCE.md#verification-by-change-type).

| ID | PR | Comportamento | Write set | Teste primeiro | Prova | Depende | Tamanho |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| S1 | PR 1 | O módulo puro calcula capacidade, capacidade neutra, procura, ritmo, chave de prioridade e a regra do Evitar (T01–T06, T08). | `backend/app/scheduler/domain/availability_priority.py` (novo); `backend/tests/unit/test_scheduler_availability_priority_v1.py` (novo) | R04, R18, R19, R20, R21 | `fast --scope backend -- -k availability_priority` | — | M |
| S2 | PR 1 | `construct_schedule` ordena e filtra pelas T07 e T08 e repete pela T09. Os guias descrevem a construção nova. | `constructive.py`; `test_scheduler_availability_priority_v1.py`; `backend/tests/unit/test_scheduler_typology_v1.py` (só R14); [Scheduler Engine](README.md); [Scheduler V1 Tech Spec](SCHEDULER_V1_TECH_SPEC_V2.md); [School Configuration](../02_domain_model/SCHOOL_CONFIGURATION.md) | R14 escrito em `main` antes de mudar o código; depois R01, R02, R03, R05, R06 e R07 | `fast --scope backend -- -k "availability_priority or typology or constructive"`, depois `fast --scope backend -- -k scheduler` e `integration -- -k "scheduler or joint_lesson or class_module_selection"` | S1 | M |
| S3 | PR 1 | `construct_recovery` usa as mesmas T07, T08 e T09 no preenchimento do futuro editável (D10, T14). | `recovery_construction.py`; `backend/tests/unit/test_scheduler_recovery_construction_v1.py` | R11, R12 | `fast --scope backend -- -k recovery` | S1 | M |
| S4 | PR 1 | A fixture da escola piloto prova o cenário com 12 e com 48 turmas (T13). | `backend/app/scheduler/lab/typology.py`; `test_scheduler_typology_v1.py` | R13 | `fast --scope backend -- -k typology`; o teste `slow_solver` corre no job `e2e-runtime` | S2 | S |
| S5 | PR 2 | A prova antes da pesquisa nomeia o professor sem horas suficientes (T11, T12). Os guias descrevem o diagnóstico. | `capacity.py`; `diagnostics.py`; `backend/app/scheduler/application/generation.py`; `backend/tests/unit/test_scheduler_teacher_capacity_v1.py` (novo); [Scheduler Engine](README.md); [Scheduler V1 Tech Spec](SCHEDULER_V1_TECH_SPEC_V2.md) | R08, R09, R10 | `fast --scope backend -- -k "teacher_capacity or capacity or diagnostics or generation"` | — | M |
| S6 | PR 2 | O job devolve uma linha por professor e o painel mostra a lista com ligação (D09). | `backend/app/scheduler/infrastructure/queries.py`; `backend/tests/integration/committed/test_scheduler_v1_lifecycle.py`; `frontend/src/components/schedules/GenerationStatusPanel.jsx`; `frontend/src/test/GenerationStatusPanel.test.jsx`; [Feedback Message Matrix](../06_frontend_ux/FEEDBACK_MESSAGE_MATRIX.md) | R15, R16, R17 | `integration -- -k lifecycle`; `fast --scope frontend -- src/test/GenerationStatusPanel.test.jsx`; `npm run verify:checks` em `frontend/` | S5 | M |

Notas por slice:

- S1: o módulo recebe os períodos elegíveis por atribuição já calculados pela construção. Não importa OR-Tools nem infraestrutura. `backend/tests/unit/test_backend_foundation_contracts.py` guarda esta fronteira.
- S2: capture o digest de R14 em `main` antes de qualquer mudança. Escreva R07 primeiro: passa em `main`, falha depois da T08 e volta a passar com a T09. A reconstrução da atualização (`search.py`, fase `RECOVERY_REBUILD`) também chama `construct_schedule`, por isso a D10 começa aqui. Os textos dos guias seguem as D32 e D33 novas do Scheduler V1 Tech Spec: D32 é a prioridade com ritmo (D01–D04, D06 deste spec); D33 é o Evitar na construção (D08). Atualize também a frase da construção na secção do plano anual e a frase "Unfavorable preferences add cost" da secção de elegibilidade.
- S3: crie o livro depois de conservar as posições publicadas e tire da capacidade os períodos que elas ocupam (T14). Retire as duas chaves Evitar atuais da ordem da reparação (T07). `test_the_class_preference_breaks_a_tie_between_shared_teacher_options` tem de continuar verde sem mudança.
- S4: a fixture usa o calendário de `build_typology_fixture` e o perfil medido no spec: grelha das 9h às 13h e das 14h às 18h; por turma 3 disciplinas de dia inteiro (4,6 h por semana), 2 só de manhã (4,2 h), 1 das 9h às 12h (5 h) e 1 das 9h às 11h (5 h); as disciplinas de dia inteiro com os identificadores menores. R13 não falha primeiro dentro do slice, porque S2 já entrou. A prova de que hoje falha é a medição do spec. Repita-a no pull request com `construct_schedule` de `main`.
- S5: siga a T11 e a T12 à letra. O filtro da T11 vive em `aggregate_capacity_check`, por isso a mensagem e os diagnósticos ficam coerentes.
- S6: siga o padrão de `provenClassDiagnostics` e `DiagnosticLine` do painel. A lista de professores aparece no mesmo ramo da lista de turmas, depois dela. Esse ramo passa a abrir também quando só existem linhas de professor. Reconstrua a stack local na worktree da mudança e diga ao responsável de produto o branch e o commit que ela serve.

### Testes existentes que guardam o comportamento

Estes testes leem a construção ou a prova de capacidade e têm de continuar verdes:
`test_scheduler_constructive_progress_v1.py`, `test_scheduler_recovery_construction_v1.py`, `test_scheduler_search_fallback_v1.py`, `test_scheduler_typology_v1.py`, `test_scheduler_lunch_solver_v1.py`, `test_scheduler_w10_constructed_v1.py`, `test_scheduler_generation_v1.py`, `test_scheduler_teacher_presence_v1.py`, `test_joint_lesson_diagnostics.py`, `test_scheduler_class_capacity_v1.py`, `test_scheduler_w07_diagnostics_v1.py`, `test_scheduler_w05_audit.py` e `test_scheduler_w04_w05_regressions_v1.py` em `backend/tests/unit/`; em `backend/tests/integration/committed/`, `test_joint_lesson_engine.py` e os testes que usam `seed_published_baseline` (`test_scheduler_v1_adaptive_changes.py`, `test_scheduler_v1_baseline_seed.py`, `test_scheduler_v1_occurrences.py`, `test_scheduler_v1_class_module_selection.py`, `test_class_module_selection_readers.py`, `test_class_module_selection_recovery.py`); `GenerationStatusPanel.test.jsx`.
Os testes `w04_w05` e `w05_audit` usam `generate_schedule` sem `stop_at_first_complete`. Ficam verdes porque o caminho exato compete com a construção (T10).

Um teste pode fixar a ordem antiga num caso com disponibilidades diferentes ou com Evitar.
Só mude a expectativa desse teste quando uma decisão do spec (D01–D08) a justificar, e registe a decisão no pull request.
Nunca enfraqueça uma verificação de validade.

### Lanes

| Lane | Slices | Ficheiros quentes |
| :--- | :--- | :--- |
| 0 | S1 | `test_scheduler_availability_priority_v1.py` (S2 acrescenta testes depois) |
| A | S2 → S4 | `test_scheduler_typology_v1.py`; [Scheduler Engine](README.md) e [Scheduler V1 Tech Spec](SCHEDULER_V1_TECH_SPEC_V2.md) |
| B | S3 | — |
| C | S5 → S6 | [Scheduler Engine](README.md) e [Scheduler V1 Tech Spec](SCHEDULER_V1_TECH_SPEC_V2.md) |

A lane 0 corre primeiro. As lanes A e B partem do seu commit e correm em paralelo, cada uma na sua worktree.
A lane C não depende de nenhuma outra e pode começar logo, a partir de `main`.
As lanes A e C mudam parágrafos diferentes dos dois guias do motor. O pull request que entrar depois faz rebase e junta os parágrafos.

### Pull requests

| PR | Merge sozinho porque | Prova local antes do PR | Cenários E2E |
| :--- | :--- | :--- | :--- |
| PR 1 | Só muda a ordem e o filtro da construção. Não há dados, API nem interface novos. O validador não muda. | perfil do solver: `fast --scope backend -- -k scheduler`; `integration -- -k "scheduler or joint_lesson or class_module_selection"` | Nenhum cenário de browser: não muda rotas nem jornadas. O `e2e-runtime` corre o teste `slow_solver` das 48 turmas. |
| PR 2 | O código de diagnóstico é novo e aditivo. Os jobs antigos não o têm e ficam iguais. | perfil do solver; `integration -- -k scheduler`; perfil de componente frontend | Nenhum cenário de browser: a mensagem do painel está coberta pelo teste de componente. |

O PR 1 regista no pull request o tempo de construção das 48 turmas, antes e depois, e o número de aulas em blocos Evitar no cenário do spec.
O PR 2 regista que `test_scheduler_v1_lifecycle.py` correu localmente, porque o CI não o corre.

### Rastreabilidade

| Decisão ou risco | Slices |
| :--- | :--- |
| D01, D02, D03 | S1, S2 |
| D04 | S1, S2, S3 |
| D05 | S2 (nenhuma opção a construir) |
| D06 | S2, S3 |
| D07 | nenhum trabalho: os quatro níveis ficam |
| D08 | S1, S2, S3 |
| D09 | S5, S6 |
| D10 | S2, S3 |
| D11 | S2 (nenhuma distribuição; R14 guarda a ordem atual) |
| D12 | todos (nenhum ficheiro de dados, CSV ou grelha) |
| T01–T06 | S1 |
| T07, T08, T09 | S2, S3 |
| T10 | todos (nenhum ficheiro do caminho exato no write set) |
| T11, T12 | S5 |
| T13 | S4 |
| T14 | S3 |
| I01, I03 | S2, S3, S4 |
| I02 | S2 (R14) |
| I04 | S2, S3 (R07, R12) |
| I05 | S3 |
| I06 | S5 |
| I07 | S6 (R15) |
| R04, R18, R19, R20, R21 | S1 |
| R01, R02, R03, R05, R06, R07, R14 | S2 |
| R11, R12 | S3 |
| R13 | S4 |
| R08, R09, R10 | S5 |
| R15, R16, R17 | S6 |

## Related Documents

- [Tech Spec — Prioridade a quem tem pouca disponibilidade](AVAILABILITY_PRIORITY_TECH_SPEC.md)
- [Scheduler Engine](README.md)
- [Command Reference](../00_getting_started/COMMAND_REFERENCE.md)
