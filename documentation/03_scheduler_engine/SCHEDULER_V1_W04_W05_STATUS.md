# Scheduler v1 — W04/W05 correction and closure record

Later audit, 25 September 2026: additional defects were reproduced after this record.
The [audit plan](SCHEDULER_V1_W00_W05_AUDIT_PLAN.md) distinguishes local fixes from remaining work.
Use its [WBS](SCHEDULER_V1_W00_W05_AUDIT_WBS.md) before reconfirming G2.

Date: 25 September 2026. Branch: `codex/scheduler-v1-revamp`.
Base commit: `facd1d93bead7fc6ed481de6761644afd2e0be81` plus the working-tree changes.

Authority: [plan](SCHEDULER_V1_REVAMP_PLAN.md), [tech spec](SCHEDULER_V1_TECH_SPEC.md),
[WBS](SCHEDULER_V1_WBS.md), the [independent review](SCHEDULER_V1_W04_W05_REVIEW.md)
and the [correction WBS](SCHEDULER_V1_W04_W05_CORRECTION_WBS.md).

This record supersedes the acceptance claims of the previous W04/W05 work record.
The previous executions remain valid as history; their conclusion was contested
by the review and is replaced by the evidence below.

All evidence comes from the local Docker test image and temporary test
databases. No Railway, Cloudflare, production or development-volume action was
performed. No frontend file changed.

## 1. Correction packages

| Package | Status | Evidence |
| :--- | :--- | :--- |
| R45.00 | Done | Probes F01–F09 converted to `test_scheduler_w04_w05_regressions_v1.py` (15 tests). |
| R45.01 | Done | Canonical chronological periods, protected dates and `now_utc` eligibility, same-assignment conflicts. |
| R45.02 | Done | `QuotaDistribution` carries counts and the final group; the detail materializes exactly that subproblem. |
| R45.03 | Done | Annual incumbent loop over distributions; full completion vector through threshold counts for every class. |
| R45.04 | Done | Contiguous certified prefix, real relaxation bounds, separate scopes for relaxation and detail. |
| R45.05 | Done | One preference definition in the domain and the model; recovery assessment separates margin from capacity. |
| R45.06 | Done | Weekly reopenable detail with a reuse cache, overlap sweep, window loop reused across rounds, and an application boundary. |
| R45.07 | Done | Stored candidate/validation/quality/evidence payload, revalidation command, seed-dependent topologies, duplicate detection. |
| R45.08 | Done | Annual corpus 10/30/45/60 × 3 profiles, adversarial regressions, campaign evidence. |
| R45.09 | Done | This record, full checks and campaign artifacts. |

## 2. Defect corrections

| Defect | Correction | Regression |
| :--- | :--- | :--- |
| F01 same-assignment collision | Conflict generation no longer skips equal assignments; the model forbids any physical overlap. | `test_f01_...` |
| F02 input-order partial credit | `eligible_periods` returns canonical chronological periods; `last` is the chronological last lesson. | `test_f02_...` |
| F03 protected dates and past | `is_physically_protected` feeds eligibility in capacity, placement and oracle. | `test_f03_...` |
| F04 waste delays completion | The search keeps an annual incumbent measured by the domain vector and reopens distributions instead of returning the first. | `test_f04_...` |
| F05 truncated completion vector | Threshold-count stages from the latest day downwards for every class; the vector freezes before subordinate objectives. | `test_f05_...` (2/6/7/8/9 classes, oracle equality) |
| F06 misleading certificates | `certified_stages` is the contiguous proven prefix; the master records `BestObjectiveBound` with its own week scope. | `test_f06_...` |
| F07 detail ignored quotas | Counts include implicit zeros; the final group is enforced; materialization is verified before validation. | `test_f07_...` |
| F08 metric disagreement | One dispreferred lesson costs its duration once, matching the recalculated domain metric. | `test_f08_...` |
| F09 margin as recoverability | `CompletionReport` reports margin days and a defined recovery scenario; no boolean promise. | `test_f09_...`, `recovery_assessment` |
| F10 evidence reach | Payload stores snapshot, periods, candidate, validation, quality, evidence, statistics and limits; `revalidate` rechecks without the solver. | `test_scheduler_lab_annual_v1.py`, `lab/revalidate.py` |
| F11 decomposition and boundary | Weekly windows with reuse; overlap sweep instead of quadratic pairs; `application` no longer imports infrastructure. | architecture contract test, `test_scale_fixture_seed_changes_...` |

## 3. Verification evidence

| Check | Result | Artifact |
| :--- | :--- | :--- |
| Backend unit suite in Docker | 613 passed, 0 failures | `.test-artifacts/1790295531545-35560/backend-unit.xml` |
| Integration suite in Docker | 321 passed, 0 failures | `.test-artifacts/1790295234915-27544/backend-integration.xml` |
| Infrastructure contracts | 47 passed | `.test-artifacts/1790295234915-27544/backend-contracts.xml` |
| Generation campaign (26 cases) | `{VALID: 20, INFEASIBLE: 6}`, no duplicate inputs, exit 0 | `.test-artifacts/1790294213799-26232/scheduler-lab/` |
| Annual campaign (12 cases) | `{VALID: 12}`, no duplicate inputs, exit 0 | `.test-artifacts/1790294303847-35956/scheduler-lab/` |
| W03 witness campaign | 3 cases `{VALID: 1, INFEASIBLE: 1, INVALID: 1}`, exit 0 | `.test-artifacts/w04w05-w03-witness/scheduler-lab/` |
| Ruff format and lint (scheduler paths) | Clean | local runner |

Campaign commands:

```text
node scripts/test.mjs campaign --manifest backend/tests/scheduler_lab/generation_manifest.json --mode generator --time-limit 30
node scripts/test.mjs campaign --manifest backend/tests/scheduler_lab/annual_manifest.json --mode generator --time-limit 100
python -m app.scheduler.lab.revalidate <case.json>
```

## 4. Annual corpus

Each class carries three subjects and six modules, the demand spans the school
year (34 available weeks, four blocked holiday weeks) and the witness is
constructed, then validated by the independent validator. The three problem
profiles change the resource topology and the seed changes the sharing groups.

| Profile | Sharing | Demand per class | 60-class result |
| :--- | :--- | :--- | :--- |
| `loose` | 2–3 classes per teacher, dedicated room | 204 lessons / 10200 min | VALID, bound week 23, 94 s |
| `shared-teacher` | 3–4 classes per teacher | 238 lessons / 11900 min | VALID, bound week 26, 108 s |
| `scarce-rooms` | teacher and room shared by the pair | 204 lessons / 10200 min | VALID, bound week 23, 100 s |

All 12 annual cases returned `COMPLETE`, validated by the independent validator,
within the declared 100 s laboratory limit. The certified prefix, the proven
relaxation bound and the stop reason are stored per case in the payload.

## 5. Corrected generator semantics

- One school week is the reopenable detail unit. A distribution fixes the
  periods per week and duration, the final group and the waste; windows are
  solved from the latest to the earliest and reused when a proven-optimal window
  plan repeats across rounds.
- The completion vector is minimized exactly through threshold counts for every
  class in scope. The counts freeze before teacher gaps, class gaps,
  preferences and room changes, so no subordinate objective can degrade a
  completion day (the previous 6/8-class policy limit is removed).
- Room changes are optimized globally after positions are fixed, preserving the
  preference value achieved by the stages.
- The annual relaxation starts from a greedy earliest-week hint, so the 60-class
  master falls from more than 90 s to about 22 s with one worker.
- The annual search keeps an incumbent, bounds proposals by the incumbent's
  latest week and stops with `PROPOSALS_EXHAUSTED`, `ROUND_LIMIT` or
  `SAFETY_LIMIT`; it never calls a conditional optimum a global one.

## 6. Remaining limits

- Annual 30/45/60 cases certify only the first windows' stages under the 100 s
  laboratory budget; the stored evidence states the prefix and the stop reason.
- Competitiveness below one worker and the full 1/2/4/8 comparison remain W11.
- Recovery assessment tests one defined perturbation (cancel the latest planned
  lesson); longitudinal recovery belongs to W06.
- The window cache only reuses proven windows, so hard instances reuse little.
- No p95 or production duration target is claimed; the limits are laboratory
  parameters.
