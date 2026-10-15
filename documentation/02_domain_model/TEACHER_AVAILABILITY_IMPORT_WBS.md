# WBS — Importação CSV da Disponibilidade dos Professores

## Purpose

Decompõe o [tech spec](TEACHER_AVAILABILITY_IMPORT_TECH_SPEC.md) em slices verticais.
As decisões (D), os riscos (R) e os contratos vivem no spec. Este documento só os referencia.

## Intended Reader

Agentes que executam o plano com o skill `cronos-plan-execution`.

## Estado

| PR | Slices | Estado | Ligação |
| :--- | :--- | :--- | :--- |
| PR 1 | S1 | por iniciar | — |
| PR 2 | S2–S6 | por iniciar | — |

## Slices

| ID | PR | Comportamento | Write set | Teste primeiro | Prova | Depende | Tamanho |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| S1 | PR 1 | Os textos dos níveis usam só Impossível, Evitar, Neutro e Preferencial (D13). | `backend/app/services/preflight_service.py`, `backend/app/services/school_readiness_service.py`, `backend/app/scheduler/infrastructure/occurrences.py`, `backend/app/models.py`, `frontend/src/features/marketing/content/home.js`, `frontend/src/features/marketing/content/workflow.js`, `frontend/src/features/tutorial/tutorialContent.js`, `frontend/src/components/AvailabilityGrid.jsx`, `documentation/00_getting_started/GLOSSARY.md`; testes em `backend/tests/contracts/test_preflight_service.py`, `backend/tests/contracts/test_school_readiness_service.py`, `frontend/src/test/MarketingSections.test.jsx`, `frontend/src/test/tutorialEngine.test.js`, `frontend/src/test/MyAvailability.test.jsx` | R17; textos novos em `MarketingSections.test.jsx` e `tutorialEngine.test.js`; `Sem bloco` em `MyAvailability.test.jsx` | `integration -- -k "preflight or readiness"`; `fast --scope frontend -- src/test/MarketingSections.test.jsx src/test/tutorialEngine.test.js src/test/MyAvailability.test.jsx`; `npm run verify:checks` | — | M |
| S2 | PR 2 | O parser e o modelo servem os dois recursos de grelha; o modelo dos professores é gerado (D02, D03). | `backend/app/services/bulk_import_policy.py`, `backend/app/services/bulk_import_service.py` (só importações e chamadas), `backend/tests/unit/test_bulk_import_policy.py` | R09 e R15 (só cabeçalho) em `test_bulk_import_policy.py` | `fast --scope backend -- -k bulk_import` | — | M |
| S3 | PR 2 | O validador partilhado resolve professores e calcula blocos alterados, aviso e ordem (D04, D05, D07–D10, D12, D14, D15). | `backend/app/services/bulk_import_policy.py`, `backend/app/services/bulk_import_service.py` (só chamadas), `backend/tests/unit/test_bulk_import_policy.py` | R02, R03, R05, R10, R11, R12, R14 em `test_bulk_import_policy.py` | `fast --scope backend -- -k bulk_import` | S2 | M |
| S4 | PR 2 | O pedido do modelo e a validação usam professores ativos e as grelhas atuais (D03, D06, D07). | `backend/app/services/bulk_import_service.py`, `backend/app/schemas.py`, `backend/tests/integration/committed/test_bulk_import.py`, `documentation/05_backend_api/API_REFERENCE.md` | R05, R08 (modelo), R15 (sem blocos) em `test_bulk_import.py` | `fast --scope backend`; `integration -- -k bulk_import` | S3 | M |
| S5 | PR 2 | O `commit` grava as grelhas dos professores, tudo ou nada (D05, D08, D11). | `backend/app/services/bulk_import_service.py`, `backend/tests/integration/committed/test_bulk_import.py`, `backend/tests/integration/committed/test_tenant_isolation_business.py`, `documentation/07_data_and_seed/BULK_IMPORT_CSV.md` | R01, R03 (`commit`), R04, R06, R07, R08 (`commit`), R13, R16 | `integration -- -k "bulk_import or tenant_isolation"` | S4 | M |
| S6 | PR 2 | O cartão, as tabelas "Blocos que mudam" e as invalidações aparecem no ecrã (D01, D10, D14, D15). | `frontend/src/features/imports/data.js`, `frontend/src/pages/BulkImport.jsx`, `frontend/src/test/BulkImport.test.jsx`, `frontend/src/test/importInvalidations.test.jsx`, `frontend/src/test/importFiles.test.js`, `documentation/06_frontend_ux/FEEDBACK_MESSAGE_MATRIX.md`, `documentation/00_getting_started/REPOSITORY_MAP.md` | R18, R19; sete modelos em `importFiles.test.js` | `fast --scope frontend -- src/test/BulkImport.test.jsx src/test/importInvalidations.test.jsx src/test/importFiles.test.js`; `npm run verify:checks` | Contrato do spec | M |

Todos os comandos de prova são do runner `node scripts/test.mjs`, descritos na [Command Reference](../00_getting_started/COMMAND_REFERENCE.md#verification-by-change-type).

### Notas por slice

- **S1:** escreva primeiro o teste do preflight com um professor atribuído e todos os blocos em Impossível. Ainda não há teste para esta mensagem. Acrescente a mensagem nova ao caso 4 de `test_school_readiness_service.py`. Os textos novos estão na tabela "Uniformização dos nomes" do spec. O filtro `-k` só reduz `integration`; os testes `contracts` correm todos.
- **S2:** a tabela de recursos de grelha substitui as constantes `CLASS_AVAILABILITY_*`. Os testes atuais das turmas mudam só nos nomes das constantes e na chamada do renderizador partilhado. O comportamento não muda. Atualize as importações de `bulk_import_service.py` no mesmo slice; a recolha dos testes unitários carrega `app.main`.
- **S3:** o validador das turmas passa a ser o validador partilhado. Os testes das turmas mudam só no campo `non_neutral_blocks`, que passa a `changed_blocks`. Acrescente aqui os campos novos de `ExistingTeacher` e `ImportSnapshot`, com valores por omissão; o S4 preenche-os.
- **S4:** preencha o indicador de professor ativo com o membro que `load_snapshot` já carrega (`lifecycle_status`, `can_teach`); não acrescente consultas para isso. Mantenha os professores arquivados em `snapshot.teachers`. Carregue as grelhas atuais só quando o lote traz um ficheiro de disponibilidade. Reutilize a consulta de níveis de `_class_availability_template`.
- **S5:** chame `set_teacher_availability` uma vez por professor. Não escreva na tabela `availability` diretamente (I04).
- **S6:** escreva o componente da tabela uma vez e use-o para turmas e professores. Use o email como chave das linhas dos professores. Nos testes, escolha o botão "Descarregar modelo" pelo cartão, não pela posição. Use dados simulados com a forma do contrato. A integração real fica provada quando S5 entra no mesmo ramo.

## Lanes

| Lane | Slices | Ficheiros quentes |
| :--- | :--- | :--- |
| A | S2 → S3 → S4 → S5 | `bulk_import_policy.py`, `bulk_import_service.py`, `test_bulk_import_policy.py`, `test_bulk_import.py` |
| B | S6 | — |
| C | S1 | — |

Os slices de lanes diferentes correm em paralelo, cada um na sua worktree.
A lane C é um pull request próprio e pode entrar em `main` antes ou depois do PR 2.
A lane B junta-se à lane A no ramo do PR 2 antes de abrir o pull request.

## Pull requests

| PR | Merge sozinho porque | Prova local antes do PR |
| :--- | :--- | :--- |
| PR 1 (`fix/uniform-availability-levels`) | Só muda textos e uma mensagem. Não muda contratos. | Provas do S1. |
| PR 2 (`feat/teacher-availability-import`) | Sem migração. O recurso novo, a troca de `non_neutral_blocks` e o ecrã entram juntos. | `fast --scope all`; `integration -- -k "bulk_import or tenant_isolation"`; `npm run verify:checks`. Depois, reconstrua o contentor `frontend`. |

Depois do merge do PR 2, faça a verificação manual do passo 6 do [spec](TEACHER_AVAILABILITY_IMPORT_TECH_SPEC.md#verification-procedure).

## Rastreabilidade

| Decisão ou risco | Slices |
| :--- | :--- |
| D01 | S6 |
| D02 | S2 |
| D03 | S2, S4 |
| D04 | S3 |
| D05 | S3, S5 |
| D06 | S4 |
| D07 | S3, S4 |
| D08 | S3, S5 |
| D09 | S3 |
| D10 | S3, S6 |
| D11 | S5 |
| D12 | S3 |
| D13 | S1 |
| D14 | S3, S6 |
| D15 | S3, S6 |
| R01, R04, R07, R13, R16 | S5 |
| R02, R10, R11, R12, R14 | S3 |
| R03 | S3, S5 |
| R05 | S3, S4 |
| R06 | S5 |
| R08 | S4, S5 |
| R09 | S2 |
| R15 | S2, S4 |
| R17 | S1 |
| R18, R19 | S6 |

## Related Documents

- [Tech spec](TEACHER_AVAILABILITY_IMPORT_TECH_SPEC.md)
- [Bulk Import CSV](../07_data_and_seed/BULK_IMPORT_CSV.md)
- [Command Reference](../00_getting_started/COMMAND_REFERENCE.md)
