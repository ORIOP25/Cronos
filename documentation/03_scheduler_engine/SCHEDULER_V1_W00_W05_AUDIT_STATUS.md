# Estado da consolidação W00–W05

Data: 25 de setembro de 2026.
Referência: [plano desta revisão](SCHEDULER_V1_W00_W05_AUDIT_PLAN.md) e [WBS desta revisão](SCHEDULER_V1_W00_W05_AUDIT_WBS.md).

## 1. Identidade da revisão

- Branch: `codex/scheduler-v1-revamp`.
- Base commit: `facd1d93bead7fc6ed481de6761644afd2e0be81`, com alterações locais não commitadas.
- Hash combinado de fontes, testes e manifests do scheduler: `7efe4667c063edc20fc5a3f8210b054c329937428b95c8ef758e897aaae96a1b`.
- Imagem Docker de testes: `cronos-backend-test:local` (`883b32a8614b`).
- Não houve push, deployment nem alteração às bases de desenvolvimento.
- O frontend não foi alterado.

## 2. Correções A01–A12

As correções anteriores mantêm-se. As regressões adversariais estão em
`backend/tests/unit/test_scheduler_w05_audit.py` (51 testes no ficheiro).
Nenhuma regressão A01–A12 falhou na revisão final.

## 3. Defeitos residuais B01–B05

| ID | Correção | Código | Testes |
| :--- | :--- | :--- | :--- |
| B01 | Identidades novas evitam IDs protegidos e já atribuídos. | `domain/candidate.py` (`allocate_lesson_identity`), `infrastructure/placement_model.py` (`_build_candidate`), `domain/oracle.py` (`_assignment_options`). | `test_audit_new_identity_does_not_collide_with_a_protected_lesson`, `test_audit_oracle_identity_does_not_collide_with_a_protected_lesson`. |
| B02 | Execução, módulos, aulas protegidas, dívida e reservas validados antes dos modelos. | `domain/candidate.py` (`_validate_executed_minutes`, `_validate_protected_lessons`, `_validate_protected_chronology`, `_validate_accountability`), `domain/calendar.py` (`Period.__post_init__`). | `test_audit_invalid_executed_input_is_rejected_at_the_snapshot`, `test_audit_protected_lesson_references_are_validated`, `test_audit_protected_slices_must_reference_known_modules`, `test_audit_protected_slices_must_form_a_chronological_prefix`, `test_audit_debt_references_must_belong_to_the_snapshot`, `test_audit_direct_period_construction_rejects_incoherent_instants`. |
| R55.01.6 | Aulas novas só ocupam períodos após a última aula protegida da atribuição. | `domain/capacity.py` (`eligible_periods`). | `test_audit_new_lessons_follow_protected_lessons_chronologically`. |
| B03 | Refinamento temporal limitado dentro da mesma semana quando existe mudança de sala evitável. | `infrastructure/placement_model.py` (`_refine_room_positions`). | `test_audit_room_refinement_reopens_positions_without_degrading_priorities`. |
| B04 | Deadline monotónico partilhado; construção, ambos os solves e pré-checks contam para o orçamento. | `infrastructure/annual_model.py` (deadline, `build_ms`, `solve_ms`), `application/generation.py` (desconto do precheck e da recuperação). | `test_audit_annual_second_solve_respects_the_monotonic_deadline`, `test_audit_generation_stops_when_the_precheck_consumes_the_budget`. |
| B05 | Corpus anual conectado com docentes por disciplina, alternativas de sala e indisponibilidade assimétrica. | `lab/annual.py` (`PROFILE_CONNECTED`, `annual_topology`), `tests/scheduler_lab/annual_manifest.json`. | `test_connected_profile_adds_alternatives_and_transversal_teachers`, `test_connected_annual_fixture_has_a_proven_impossible_variant`. |

A correção de salas entre janelas continua heurística.
Um custo positivo no matching não prova o ótimo global.
A heurística aceita uma troca apenas quando o vetor completo de qualidade melhora.

## 4. R55.03 e R55.06

- SAFETY_LIMIT tem prioridade sobre uma janela FEASIBLE anterior.
- Uma janela interrompida não entra na cache nem certifica etapas seguintes.
- A cache não reutiliza janelas entre modos com e sem otimização conjunta de salas.
- O pós-passo preserva o incumbente quando o solver devolve UNKNOWN.
- O oráculo compara os cinco componentes do vetor em 16 microinstâncias com seeds fixas.
- A permutação de entidades e de períodos não altera viabilidade nem ótimo.

## 5. Hipóteses da secção 5 do plano

| Hipótese | Conclusão | Evidência |
| :--- | :--- | :--- |
| Prioridade de SAFETY_LIMIT | Confirmada e corrigida. | Teste dedicado. |
| Certificados atravessam etapa omitida | Não atravessam. A política conservadora certifica zero após interrupção. | `test_audit_safety_limit_has_priority_over_a_feasible_window`, regressões F06/A07. |
| Semântica dos bounds após cortes | Cada bound pertence à relaxação anual com scope declarado. Sem alteração. | `SearchEvidence.relaxation_scope`. |
| Pós-passo piora o incumbente | Não piora; UNKNOWN mantém o candidato anterior. | `test_audit_room_postpass_preserves_the_incumbent_on_unknown`. |
| Cache após otimização de salas | Reutilização condicionada ao modo; sem mistura. | `test_audit_cache_does_not_reuse_room_optimized_windows_in_multi_window_mode`. |
| Projeção com protegidas intercaladas | Corrigida: prefixo protegido validado e aulas novas depois do prefixo. | `test_audit_new_lessons_follow_protected_lessons_chronologically`. |
| `Period` construído diretamente | Validado na construção. | `test_audit_direct_period_construction_rejects_incoherent_instants`. |

## 6. Evidência executada

| Verificação | Resultado |
| :--- | :--- |
| Unitários | 665 passaram. Uma falha pré-existente e intermitente em `test_error_handlers.py::test_lowercase_request_id_is_not_accepted`; passa isolada e não pertence ao scheduler. |
| Integração PostgreSQL | 321 passaram, 0 falhas (`backend-integration.xml`). |
| Contratos | 47 passaram (`backend-contracts.xml`). |
| Runner | 17 passaram (`node --test scripts/test.test.mjs`). |
| Ruff | `check` e `format --check` limpos nos ficheiros do scheduler. |
| Campanha de geração | 26 casos: 20 VALID, 6 INFEASIBLE. |
| Campanha anual | 15 casos: 14 VALID, 1 INCONCLUSIVE. |

Artefactos:

- Integração e contratos: `.test-artifacts/1790353689548-7820/`.
- Campanha de geração: `.test-artifacts/r55-generation/scheduler-lab/`.
- Campanha anual: `.test-artifacts/r55-annual-connected/scheduler-lab/`.

## 7. Limites e decisão

- O caso `gen-annual-60-connected` é exploratório e terminou INCONCLUSIVE dentro de 100 segundos.
  Fica visível na amostra; não é caso obrigatório.
- O ótimo global entre janelas não está provado; o matching de salas mantém esse limite explícito.
- A baseline de hashes inclui ficheiros não commitados; a revisão não foi publicada.
- G2 não é reconfirmado automaticamente.
  Os critérios técnicos do WBS estão demonstrados nos casos obrigatórios; a aceitação funcional pertence ao proprietário.
- Pendências legítimas de W07–W12 mantêm os seus responsáveis.
