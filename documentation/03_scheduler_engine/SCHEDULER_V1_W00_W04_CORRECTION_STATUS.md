# Scheduler v1 — Correction and closure work record (W00–W04)

Date: 24 September 2026. Branch: `codex/scheduler-v1-revamp`.
Base commit: `facd1d93bead7fc6ed481de6761644afd2e0be81`.
Origin: [review](SCHEDULER_V1_W00_W04_REVIEW.md) and
[correction WBS](SCHEDULER_V1_W00_W04_CORRECTION_WBS.md).

This is a work record. It documents the corrections, the W04 implementation
and its limits. All evidence comes from local Docker and temporary test
databases. No production, Railway, Cloudflare or development-volume action was
performed.

## 1. RC package status

| Package | Status | Notes |
| :--- | :--- | :--- |
| RC00 | Done | States reclassified; probes converted to conventional regressions. |
| RC01 | Done | Strategy, concrete grid, intervals, timezone/reference instant, editable window, debt ownership, deep immutability, boundary validation. |
| RC02 | Done | Chronology, partial-credit rule, grid/strategy limits, overlap unavailability, physical-only protection, editable-window inserts, reservations, independent metrics. |
| RC03 | Done | Protected credit subtracted, fixed occupancies, explicit budget exception, optimum scope documented. |
| RC04 | Done | Provenance resume key, selection validation, strict expectations, expected violation codes, atomic/ERROR results, expectation-aware comparator, coverage duplicates. |
| RC05 | **Done** | RC05.1–RC05.7 implemented with PostgreSQL tests. |
| RC06 | **Done** | Reset, administrative erasure, Alembic checkpoint and scale fixtures implemented and tested. |
| RC07 | Partial | RC07.1, RC07.4, RC07.5, RC07.6 done. RC07.2 and the quota-feedback part of RC07.3 are documented limits. |
| RC08 | Partial | Loops A–E and G pass. Loop F (annual quota aggregation) is tied to RC07.2 and is not implemented. |

## 2. Defect corrections and regressions

| Defect | Correction | Regression test |
| :--- | :--- | :--- |
| F01 chronology | `_check_curriculum` walks lessons in school chronology and module sequence | `test_module_chronology_is_enforced_not_only_totals`, `test_non_final_partial_credit_is_rejected` |
| F02 calendar | Concrete grid slots, timezone, reference instant, strategy limits, interval unavailability | `test_period_outside_the_grid_is_rejected`, `test_initial_generation_rejects_dates_after_preference`, `test_adaptive_recovery_allows_dates_up_to_the_hard_end`, `test_overlapping_unavailability_is_rejected_but_boundary_contact_is_allowed` |
| F03 protection | Physical-only protection and editable window for every non-protected lesson | `test_protection_ignores_modular_projection_but_keeps_physical_identity`, `test_new_lesson_inside_the_editable_window_is_rejected`, `test_protected_lesson_inside_the_window_is_allowed` |
| F04 oracle | Protected credit subtracted, fixed periods excluded, explicit budget exception | `test_oracle_accepts_a_fully_protected_witness_without_duplicating_it`, `test_oracle_subtracts_half_protected_credit_before_enumerating`, `test_oracle_raises_an_explicit_budget_limit_not_infeasibility` |
| F05 immutability | Deep-copied mappings inside `PlanningSnapshot` | `test_snapshot_deep_copies_executed_minutes_so_aliases_cannot_mutate_it` |
| F06 resume | Full provenance key, atomic writes, truncated files ignored | `test_resume_reuses_only_identical_provenance`, `test_resume_does_not_reuse_stale_evidence_after_inputs_change`, `test_truncated_result_files_are_not_reused` |
| F07 campaign | Strict selection and expectations, required violation codes, per-case `ERROR` | `test_unknown_or_empty_selection_is_an_explicit_error`, `test_valid_data_declared_as_invalid_input_fails_the_campaign`, `test_mutation_must_be_detected_by_the_declared_code`, `test_case_exceptions_become_error_results_without_aborting_the_campaign` |
| F08 comparator | Expectation-aware regression, incomparable inputs, missing metrics, policy changes | `test_regression_is_detected_against_the_case_expectation`, `test_changed_inputs_without_version_change_are_incomparable`, `test_disappearing_metrics_and_policy_changes_are_visible` |

## 3. RC05 completed slices

| Item | Implementation | Test |
| :--- | :--- | :--- |
| RC05.1 | Retroactive compensation fills the earliest free curricular interval | `test_w02_retroactive_reversal_leaves_a_free_interval_for_new_credit` (offsets `[0, 50, 25, 25]`) |
| RC05.2 | Active reservations loaded into the settlement transaction; excess reservations released | `test_record_execution_releases_reserved_debt` |
| RC05.3 | `revise_debt` and `cancel_recovery` with replay and no duplicated debt | `test_revise_debt_appends_audited_revision_and_rejects_negative_open`, `test_cancel_recovery_releases_without_duplicating_debt` |
| RC05.4/05.5 | `preferred_end_date` column and `configure_school_year` under the state lock | `test_configuration_change_updates_preference_and_consumes_revisions`, `test_rollback_preserves_the_previous_configuration` |
| RC05.6 | Reservation assignment column with composite foreign keys to lesson and debt | `test_reservation_cannot_mix_assignments_or_debts`, `test_plan_recovery_is_idempotent_and_respects_bounds` |
| RC05.7 | Physical-minutes check constraint and `ensure_no_physical_collisions` boundary | `test_physical_minutes_must_match_the_interval`, `test_collision_boundary_rejects_overlapping_resources`, `test_collision_boundary_rejects_slices_outside_the_curriculum`, `test_collision_boundary_accepts_coherent_versions` |

## 4. RC06 completed slices

- RC06.1: `scripts/reset_test_data.py` deletes named targets (child first, row
  security off as owner), refuses wrong databases and unknown targets and is
  repeatable.
- RC06.2: `scripts/privacy.py` erases through a table-owner session created at
  call time. The runtime role keeps no `DELETE` on append-only evidence, which
  the test proves.
- RC06.3: `scripts/check_scheduler_baseline.py` fails while the installed head
  is the provisional revision, and the consolidation plan is fixed in
  [SCHEDULER_V1_ALEMBIC_CONSOLIDATION_PLAN.md](SCHEDULER_V1_ALEMBIC_CONSOLIDATION_PLAN.md).
- RC06.4: `lab/scale.py` builds 10/30/45/60-class fixtures with constructed
  witnesses (shared teachers, disjoint blocks) without the exponential oracle.

## 5. RC07 — W04 implementation

- `infrastructure/capacity.py`: aggregate necessary-condition check. Only a
  proven lower-bound deficit is reported.
- `infrastructure/placement_model.py`: CP-SAT model over eligible
  assignment/period/room facts. Exact credit per assignment (last lesson may be
  partial), pairwise class/teacher/room conflicts, room choice per lesson,
  objective on the latest completion day. `INFEASIBLE`, `INCONCLUSIVE` and
  `COMPLETE` are distinct.
- `application/generation.py`: orchestrates capacity check, placement and
  independent validation. A solver candidate rejected by the validator returns
  `FAILED`; a bounded search never returns `INFEASIBLE`.
- `lab/campaign.py --mode generator`: the runner executes the generator over
  fixtures and the witness stays only as oracle/baseline.

## 6. RC08 — acceptance evidence

Command:

```text
node scripts/test.mjs campaign --manifest backend/tests/scheduler_lab/generation_manifest.json --mode generator --time-limit 30
```

Result: 19 cases, `{VALID: 16, INFEASIBLE: 3}`, exit 0. Coverage:

| Family | Cases |
| :--- | :--- |
| C01 | clean, crossing 75+75/50, partial, exact fit, infeasible |
| C02 | few hours in many spaces |
| C03 | many hours in little space |
| C04 | single position, shared-teacher chain |
| C05 | many hours in many spaces |
| C06 | independent teachers |
| C07 | shared room |
| C08 | apparent teacher capacity with proven infeasibility |
| C10 | preference limit respected, exact preference fit |
| G (scale) | 10, 30, 45 and 60 classes complete and validated |

The 60-class fixture completes in about 1.7 s with one worker and the
generated candidates pass the independent validator.

## 7. Gate A verification

| Criterion | State |
| :--- | :--- |
| F01–F08 corrected with regressions | Demonstrated |
| R01–R12 no longer reproduce | Demonstrated (diagnostic file no longer passes; corrected tests pass) |
| Oracle limited during enumeration and correct with protected credit | Demonstrated |
| Lab rejects stale evidence, empty selection and unmet expectations | Demonstrated |
| RC05 concluded in rules feeding snapshots, demand and validation | Demonstrated |
| Install/reset demonstrated; Alembic checkpoint tracked | Demonstrated (checkpoint script and plan; consolidation owned by W12) |
| Suites green on the same revision | Demonstrated (565 unit, 321 integration, 47 contracts, 17 runner) |
| W04 fixtures classified before the solve | Demonstrated (manifest expectations) |

Gate A is demonstrated. This does not close W00–W03 integrally; their own WBS
items remain tracked (for example, the final Alembic consolidation).

## 8. Evidence

| Check | Result |
| :--- | :--- |
| Backend unit suite | 565 passed; `.test-artifacts/1790277802166-17940/backend-unit.xml` |
| Integration suite (full) | 321 passed; `.test-artifacts/1790277873504-26232/backend-integration.xml` |
| Infrastructure contracts | 47 passed; `.test-artifacts/1790277873504-26232/backend-contracts.xml` |
| Runner unit tests | 17 passed |
| W03 witness campaign | 3 cases `{VALID: 1, INFEASIBLE: 1, INVALID: 1}`, exit 0 |
| W04 generation campaign | 19 cases `{VALID: 16, INFEASIBLE: 3}`, exit 0; `.test-artifacts/1790277777425-14044/scheduler-lab/` |
| Ruff format and lint on changed paths | Clean |

## 9. Remaining work and limits

- RC07.2 and RC07.3 were implemented after this record in
  [SCHEDULER_V1_W04_W05_STATUS.md](SCHEDULER_V1_W04_W05_STATUS.md): the annual
  quota decomposition returns candidate distributions, a detail proven
  infeasible becomes a no-good cut, and a timeout never cuts. RC08 loop F is
  covered by the `gen-t11-reopen-weeks` campaign case.
- W05 quality (completion vector, teacher gaps, class gaps, preferences and
  rooms) is implemented and recorded in the same document.
- Quality calibration, workers and safety limits remain in W11.
- No frontend E2E, Railway, Cloudflare, production migration or development
  volume reset was executed.
