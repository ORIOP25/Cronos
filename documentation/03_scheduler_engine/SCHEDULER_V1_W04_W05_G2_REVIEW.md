# Scheduler v1 — Independent re-review of W04/W05 and G2 decision

Later audit, 25 September 2026: new counterexamples reopen this acceptance decision.
See the [audit plan](SCHEDULER_V1_W00_W05_AUDIT_PLAN.md) and
[remaining correction WBS](SCHEDULER_V1_W00_W05_AUDIT_WBS.md).
The results below remain historical evidence for the cases executed then.

Date: 25 September 2026. Branch: `codex/scheduler-v1-revamp`.
Base commit: `facd1d93bead7fc6ed481de6761644afd2e0be81` plus the working-tree changes.
Authority: [review](SCHEDULER_V1_W04_W05_REVIEW.md),
[correction WBS](SCHEDULER_V1_W04_W05_CORRECTION_WBS.md),
[plan](SCHEDULER_V1_REVAMP_PLAN.md) and [tech spec](SCHEDULER_V1_TECH_SPEC.md).

Authorship note: this re-execution was performed at the owner's request by the
implementer of the correction, not by an external party. It reproduces the
review counterexamples with a separate script and a separate annual sample; the
final acceptance remains the owner's decision.

## 1. Environment and evidence

| Item | Value |
| :--- | :--- |
| Image | `cronos-backend-test:local` built from this working tree |
| Runtime | Python 3.14, OR-Tools 9.15.6755, Docker 29.8, no network in the probe container |
| Probe script | [probes.py](review_evidence/2026-09-25-w04-w05-correction/probes.py) → [probes.json](review_evidence/2026-09-25-w04-w05-correction/probes.json) |
| Annual revalidation | [revalidate_all.py](review_evidence/2026-09-25-w04-w05-correction/revalidate_all.py) → [revalidation.json](review_evidence/2026-09-25-w04-w05-correction/revalidation.json) |
| Annual campaign artifacts | `.test-artifacts/1790294303847-35956/scheduler-lab/` |
| Unit / integration / contracts | 613 / 321 / 47 passed, zero failures |
| Generation campaign | 26 cases `{VALID: 20, INFEASIBLE: 6}`, no duplicate inputs, exit 0 |

The probe script adapts the original scenarios to the corrected API. The
controlled unproven-prefix probe uses a two-day instance because the corrected
solver has no completion threshold on a single-day horizon; the pre-solve is
solver call 1 and the completion threshold is call 2.

## 2. Counterexample results

All F01–F09 scenarios reproduce the expected corrected behavior. The oracle
returns the same verdict for the enumerable instances.

| Scenario | Expected | Observed | Verdict |
| :--- | :--- | :--- | :--- |
| `annual_waste_delays_completion` (F04) | COMPLETE, vector `(0,)` | COMPLETE, vector `(0,)`, bound week 0 | PASS |
| `same_assignment_overlap` (F01) | COMPLETE valid, vector `(1,)` | COMPLETE valid, vector `(1,)` | PASS |
| `period_order` (F02) | both orders COMPLETE, same vector | `COMPLETE/COMPLETE`, `(1,)/(1,)` | PASS |
| `completion_tail_7_classes` (F05) | `(1,1,1,1,1,1,0)` | equals oracle | PASS |
| `completion_tail_9_classes` (F05) | `(1,1,1,1,1,1,1,1,0)` | equals oracle | PASS |
| `preference_metric_disagreement` (F08) | optimized 60, measured 60 | `[60]`, measured 60 | PASS |
| `protected_date` (F03) | COMPLETE on the next day | COMPLETE on the next day | PASS |
| `past_period` (F03) | COMPLETE on the next day | COMPLETE on the next day | PASS |
| `margin_without_recovery_capacity` (F09) | margin 20, recovery `IMPOSSIBLE_PROVEN` | margin 20, `IMPOSSIBLE_PROVEN` | PASS |
| `controlled_unproven_prefix` (F06) | certified prefix 0 with an unproven first stage | `certified_stages=0`; stages `[false, true, true]` | PASS |
| `scale_seed_diversity` (F10) | seeds change the problem | snapshots and assignments differ | PASS |
| `detail_ignores_zero_quotas` (F07) | exactly one 60 and one 90 lesson, full credit | materialization equals the supplied distribution | PASS |
| `annual_10_loose` | COMPLETE and valid | 2040 lessons, 102000 min, gaps 0, prefix 58, 34.7 s | PASS |
| `annual_60_shared_teacher` | COMPLETE and valid | 14280 lessons, 714000 min, gaps 0, prefix 85, 125.3 s | PASS |

No counterexample from the review remains reproducible.

## 3. Stored output verification

All 12 annual campaign candidates were revalidated from their stored payload
without running the solver: the command rebuilds the snapshot, periods and
candidate, re-runs the independent validator and the domain quality measurement,
and compares both with the stored report and digest.

- 12/12 revalidated, 12/12 still valid, zero digest mismatches.
- The stored payload includes snapshot, periods, candidate, validation, quality,
  evidence with certified prefix and relaxation bound, statistics and limits.
- A deliberately tampered candidate fails the digest check (unit test
  `test_a_stored_candidate_revalidates_and_detects_tampering`).

## 4. G2 decision

**G2 is accepted for the corrected W04/W05 scope.** The criteria of the
correction WBS section 12 are demonstrated:

1. F01–F09 corrected with regressions; no known witness-bearing case fails the
   model, and the reusable oracle agrees on every enumerable instance.
2. No divergence from the full optimal completion vector in the enumerable
   corpus; no subordinate objective trades a higher priority.
3. Quotas, final credit, cuts, prefixes and bounds describe the same
   subproblem; interruption never becomes impossibility.
4. Campaigns produce complete, revalidable artifacts with explicit scenario
   lists, including the annual 10/30/45/60 corpus.
5. Directed tests, unit, integration, contracts, runner and Ruff are green on
   this revision.
6. This report and [SCHEDULER_V1_W04_W05_STATUS.md](SCHEDULER_V1_W04_W05_STATUS.md)
   record the evidence, and the previous green record is preserved as history.

Accepted limits (explicit, not hidden):

- Annual 30/45/60 cases certify only the early windows within the 100 s
  laboratory budget; the stored evidence states the certified prefix and the
  stop reason.
- Internal-worker calibration 1/2/4/8 and the stopping policy remain W11.
- Recovery assessment tests one defined perturbation; longitudinal recovery
  belongs to W06.
- The room-continuity optimization is global but the window cache only reuses
  proven windows, so hard instances reuse little.

Accepting G2 does not close W06–W14 and does not authorize Railway/Cloudflare
validation, which remain behind the local gate.
