# Scheduler Correctness and Reliability WBS

## Purpose

This plan implements findings A through H from the scheduler review dated 11 September 2026.
It uses test-driven development and preserves the current branch changes.

## Required Outcome

Every accepted draft must pass independent hard, curriculum, and debt validation.
Every failed job must preserve the active schedule and report its actual terminal state.
A completed incumbent must remain usable when optional refinement reaches its deadline.

## Delivery Rules

- Keep changes inside existing scheduler services and domain helpers.
- Reuse the current demand ledgers, candidate builders, and constraint policy.
- Add no dependency, migration, generic solver framework, or speculative abstraction.
- Add each counterexample as a failing regression before its production fix.
- Keep explicit debt separate from curriculum demand.
- Preserve immutable historical and protected blocks.
- Validate against the immutable snapshot during runtime.
- Validate against current tenant-scoped inputs during approval.
- Keep cancellation authoritative at every persistence boundary.

## Work Package Dependencies

| Package | Depends on | Findings |
| :--- | :--- | :--- |
| 0. Baseline and red tests | None | A-H |
| 1. Curriculum and debt integrity | 0 | B, F, H |
| 2. Deadline and status reliability | 0, 1 | A, C |
| 3. Complete-generation feasibility | 0, 1 | D, E |
| 4. Assignment change lifecycle | 0, 1 | G |
| 5. Evidence and performance | 1-4 | Review gates |
| 6. Documentation and release | 1-5 | All |

## 0. Baseline and Regression Harness

### 0.1 Protect the starting state

- Confirm branch `codex/fix-adaptive-new-subject-demand`.
- Record the starting revision and working-tree paths.
- Preserve all existing uncommitted scheduler changes.
- Exclude `.ci-artifacts-*` and generated test artifacts from commits.

### 0.2 Establish the focused baseline

- Run the existing scheduler unit selection.
- Run the existing scheduler integration selection.
- Save failing output before changing production code.
- Stop if failures do not match the review baseline.

### 0.3 Promote probes into maintained regressions

- Move probe logic into existing test modules.
- Use shared fixture builders where they already exist.
- Keep tests deterministic and independent of wall-clock timing.
- Replace real sleeps with controlled clocks and synchronization events.

### 0.4 Required red tests

| Finding | Test location | Required failing assertion |
| :--- | :--- | :--- |
| A | `test_scheduler_job_runtime.py` | Runtime persists a valid cleanup incumbent. |
| B | `test_scheduler_target_validation.py` | Wrong module totals and chronology fail. |
| C | `test_scheduler_adaptive_engine.py` | Interrupted quality reports incomplete refinement. |
| C | `test_scheduler_near_optimizer.py` | `UNKNOWN` never maps to infeasible. |
| D | `test_scheduler_complete_engine.py` | An empty near window continues into later dates. |
| E | `test_scheduler_far_fill.py` | Residual repair finds the two-subject witness. |
| F | `test_scheduler_complete_demand.py` | Existing assignments produce changed residual demand. |
| F | `test_scheduler_adaptive_engine.py` | Added modules and hours create curriculum blocks. |
| G | `test_scheduler_adaptive_engine.py` | Removed assignments omit editable future blocks. |
| G | `test_scheduler_job_runtime.py` | Protected removal returns an actionable blocker. |
| H | `test_scheduler_job_runtime.py` | Cross-class and cross-subject recovery targets fail. |
| H | `test_scheduler_recovery_runtime_permissions.py` | Approval rejects forged debt identity. |

## 1. Curriculum and Debt Integrity

### 1.1 Add one pure curriculum coverage validator

Create `backend/app/services/scheduler_curriculum_validation.py`.
Keep it independent from database sessions and solver objects.

Inputs:

- A complete or incremental demand ledger.
- Target block specifications.
- A predicate selecting curriculum blocks.
- Timetable slot start values from the snapshot.

Validation algorithm:

1. Index demand by class and subject.
2. Index each required module by its sequence.
3. Reject blocks outside the demand ledger.
4. Reject missing or unknown module sequences.
5. Sum target minutes by class, subject, and module.
6. Require exact module totals, including zero remaining demand.
7. Sort blocks by date, slot start, and stable key.
8. Require nondecreasing module sequences per class and subject.
9. Return specific violations without mutating inputs.

Reuse this validator from `SchedulerTargetValidator` and `SchedulerJobRuntime`.
Remove the duplicated subject-only completeness loop after tests pass.

### 1.2 Strengthen complete target validation

Update `SchedulerTargetValidator._validate_complete`.

- Build the complete demand ledger once.
- Keep complete-generation block semantic checks.
- Delegate module totals and chronology to the shared validator.
- Keep teacher and room checks in hard-constraint validation.
- Reject overfilled, omitted, reversed, and unknown modules.

Update `SchedulerJobRuntime._validate_complete_demand`.

- Delegate to the same shared validator.
- Translate its error into `GenerationValidationError`.
- Delete its duplicate subject-total implementation.

### 1.3 Reconcile adaptive curriculum demand

Update `IncrementalDemandLedgerBuilder.build`.

For every current class-subject assignment:

1. Build remaining module demand after completed progress.
2. Count active, non-recovery, still-planned minutes by module.
3. Ignore completed or occurrence-backed blocks already represented in progress.
4. Match planned minutes using class, subject, and module sequence.
5. Subtract planned minutes from each module independently.
6. Emit only positive residual modules.
7. Keep resource blockers for every positive residual item.

Never subtract explicit recovery blocks from curriculum demand.
Never infer module completion from subject presence alone.

### 1.4 Cover curriculum change variants

Add tests for these cases:

- Add a new assignment.
- Add a module to an existing subject.
- Increase an existing module's required minutes.
- Reduce an existing module's required minutes.
- Keep a partially delivered module.
- Complete one module and add demand to the next.
- Retain an unchanged fully planned subject.
- Keep explicit debt separate from curriculum residuals.

### 1.5 Bind recovery blocks to debt identity

Add one pure identity check beside the recovery service.

For each recovery block:

- Match occurrence ID and revision.
- Match the debt source class.
- Match the debt source subject.
- Require the target teacher's current assignment and eligibility.
- Do not require the originally absent teacher.
- Enforce the unresolved minute ceiling.

Use the check from `SchedulerJobRuntime._validate_adaptive_repair`.
Use the same check before `SchedulerRecoveryService.plan_draft_recovery` creates a link.
Repeat the identity check during approval against current tenant-scoped debt.

### 1.6 Package acceptance

- The original validation probe rejects both invalid module targets.
- The curriculum increase schedules exactly the missing minutes.
- Added modules schedule their complete residual demand.
- Forged cross-class and cross-subject recovery targets fail.
- Valid reassigned recovery teachers remain accepted.

## 2. Deadline and Status Reliability

### 2.1 Separate runtime deadlines

Keep the existing five-minute job cap.
Keep the existing final persistence reserve.
Add a small engine-return reserve before the runtime solve cutoff.

Use these boundaries:

- Refinement cutoff stops optional objective stages.
- Solver cutoff requests cooperative engine termination.
- Final deadline bounds validation, cleanup, and persistence.

Do not extend the five-minute cap.

### 2.2 Preserve a returned incumbent

Update `SchedulerJobRuntime.execute`.

1. Wait for the engine until the solver cutoff.
2. Set the cooperative stop signal at that cutoff.
3. Wait only within the final reserve.
4. Capture a normal engine result returned during cleanup.
5. Recheck user cancellation before validation.
6. Independently validate the captured incumbent.
7. Persist only before the final deadline.
8. Report timeout only when no valid result returns.

Never publish after a cancellation request.
Never accept an unvalidated partial engine object.

### 2.3 Derive status from completed work

Update adaptive stage tracking.

- Set `quality_completed_stage` after each successful stage.
- Set `quality_optimization_complete` only after the final required stage proves optimal.
- Clear completeness when construction or any later stage stops.
- Report the feasibility solver status separately.
- Report curriculum completeness separately.
- Describe optimality as scope-level only.

Update near optimizer status mapping.

- Map `OPTIMAL` to `optimal`.
- Map `FEASIBLE` to `feasible`.
- Map `INFEASIBLE` to `infeasible`.
- Map `UNKNOWN` to `search_exhausted`.
- Treat `MODEL_INVALID` as a system validation failure.
- Preserve the raw CP-SAT status name in metrics.

### 2.4 Worker coverage

Test `scheduler_worker._generation_engine` through the runtime boundary.
Prove cleanup returns a valid incumbent to the worker.
Prove cancellation prevents draft persistence.
Prove cleanup overrun produces `FAILED / TIMED_OUT`.

### 2.5 Package acceptance

- The deadline probe finishes successfully with a validated incumbent.
- Interrupted quality reports `quality_optimization_complete=false`.
- Unknown search reports exhaustion, not infeasibility.
- Cancellation remains terminal and publishes no draft.

## 3. Complete-Generation Feasibility

### 3.1 Continue after an empty near window

Update `CompleteGenerationEngine.generate`.

- Classify near-window blockers before returning.
- Return immediately for configuration, size, or deadline blockers.
- Continue when hard pruning only removes local candidates.
- Pass an empty near selection into the far stage.
- Build the far universe through the annual hard end date.
- Let final residual validation decide annual failure.

Do not treat an empty local window as annual infeasibility.

### 3.2 Calculate real scarcity

Update `FarFutureFiller` ranking.

- Count distinct usable time opportunities per demand item.
- Ignore duplicate room variants for scarcity counts.
- Include current class and teacher contention.
- Recalculate affected scarcity after each placement.
- Keep deterministic tie-breaking.

This ranking improves choices but does not provide completeness.

### 3.3 Add bounded residual CP-SAT repair

Run repair only when greedy filling leaves residual demand.
Keep the implementation inside `scheduler_far_fill.py` unless extraction reduces duplication.

Repair algorithm:

1. Treat optimized near blocks as fixed intervals.
2. Reconsider every provisional far placement.
3. Create one Boolean variable per far candidate.
4. Enforce exact remaining minutes per class and subject.
5. Enforce class, teacher, and room non-overlap.
6. Enforce lunch and existing hard candidate constraints.
7. Maximize scheduled curriculum minutes first.
8. Use deterministic placement order as the final tie-break.
9. Replace greedy far blocks only with a complete hard-valid result.
10. Preserve the greedy result when repair exhausts its budget.

Allocate repair only from the remaining solver budget.
Do not report infeasibility for an unknown repair status.

### 3.4 Package acceptance

- The delayed-availability probe places the August witness.
- A blocked full year returns no valid output.
- The greedy counterexample places both subjects.
- An exhausted residual search reports search exhaustion.
- Every successful assembly passes shared target validation.

## 4. Assignment Change Lifecycle

### 4.1 Classify removed assignments

Update adaptive task construction.

- Build the current assignment index once.
- Detect active blocks whose class-subject link disappeared.
- Omit editable, unexecuted future blocks from repair tasks.
- Keep those source IDs absent from the target.
- Let approval mark omitted active rows as removed.

### 4.2 Protect historical boundaries

Before solving, inspect removed assignments against immutable blocks.

- Return an actionable configuration blocker for a protected conflict.
- Include the class, subject, and protected block identity.
- Preserve every protected block and the active schedule.
- Never fabricate a removed assignment to satisfy validation.

Apply the same rule to reduced demand that conflicts with protected minutes.

### 4.3 Validate the full workflow

- Test editable assignment removal through draft creation.
- Test approval removes the obsolete active block.
- Test protected removal produces no draft.
- Test history and lesson evidence remain unchanged.
- Test stale fingerprints still reject approval.

### 4.4 Package acceptance

- The editable removal probe produces a valid target.
- Approval removes only the intended active rows.
- Protected conflicts return a clear blocker.
- No runtime validation failure follows a successful engine result.

## 5. Evidence, Properties, and Performance

### 5.1 Add small exhaustive oracle tests

Use standard-library enumeration for small candidate sets.
Add no property-testing dependency.

For each generated small case:

- Enumerate every candidate subset.
- Validate hard constraints and exact demand.
- Determine whether any complete assignment exists.
- Compare engine feasibility with the oracle.
- Compare quality only when both searches prove their scopes optimal.

Use fixed seeds and bounded case counts.

### 5.2 Add metamorphic tests

Verify these relations:

- Added capacity cannot turn a proven feasible case infeasible.
- Reduced demand cannot require more scheduled minutes.
- Reordered input cannot change feasibility.
- Remapped stable IDs cannot change feasibility or quality vectors.

### 5.3 Publish non-overlapping metrics

Measure these phases separately:

- Candidate construction.
- Feasibility solving.
- Quality construction.
- Quality solving.
- Result extraction.
- Independent validation.
- Draft persistence.

Add these fields to scheduler lifecycle events.
Keep absent metrics absent rather than inventing zero values.

### 5.4 Guard performance

- Preserve the 3,868-candidate job 13 regression.
- Preserve current quality indexing.
- Replace repeated full quality evaluation during ranking with maintained deltas.
- Run the full evaluator once on the final target.
- Record candidate, variable, constraint, and phase counts.
- Add a stable runtime ceiling only for controlled fixtures.
- Document that local timings do not prove production capacity.

Defer peak-memory and multi-school load gates until a stable harness exists.

## 6. Documentation and Release

### 6.1 Update behavior documentation

Update `SCHEDULER_BEHAVIOR.md`.

- Define exact module coverage and chronology.
- Define residual curriculum reconciliation.
- Define debt identity rules.
- Define feasible, optimal, infeasible, exhausted, and canceled states.

### 6.2 Update architecture documentation

Update `SCHEDULER_ARCHITECTURE.md`.

- Document the shared curriculum validator.
- Document refinement, solver, and persistence deadlines.
- Document residual far-horizon repair.
- Document assignment removal handling.

### 6.3 Update operations documentation

Update `SCHEDULER_OPERATIONS.md`.

- List every phase timing and status field.
- Explain actionable protected-removal blockers.
- Explain search exhaustion without claiming infeasibility.
- Explain scope-level optimality limits.

### 6.4 Verification sequence

Run these commands in order:

```powershell
node scripts/test.mjs fast --scope backend -- -k 'scheduler or cp_sat or candidate or far_fill or near_optimizer'
node scripts/test.mjs integration -- -k 'scheduler or schedule_generate or schedule_constraints or debt_basis or draft_approval'
node scripts/test.mjs fast --scope backend
node scripts/test.mjs integration
node scripts/test.mjs all --scope all
```

Then run backend integrity checks:

```powershell
Set-Location backend
./.venv/Scripts/python.exe -m alembic check
./.venv/Scripts/python.exe -m scripts.audit_triggers
./.venv/Scripts/python.exe -m scripts.audit_database_integrity
```

### 6.5 Commit and CI loop

1. Review the final diff for unrelated changes and generated files.
2. Commit tests, implementation, and documentation together.
3. Push the current branch without rewriting history.
4. Follow every required GitHub Actions job.
5. Capture exact failing job names and logs.
6. Fix root causes with a new test when applicable.
7. Push again and repeat until every required job passes.

## Definition of Done

- Every confirmed counterexample is a maintained regression.
- All eight findings pass their package acceptance criteria.
- Runtime and approval share curriculum coverage behavior.
- Runtime and recovery services enforce debt identity.
- Valid incumbents survive optional refinement deadlines.
- Solver states retain their precise meanings.
- Empty local windows do not become annual failures.
- Residual repair resolves the greedy counterexample.
- Removed assignments respect editable and protected boundaries.
- Focused, full backend, integrity, and complete project gates pass.
- The current branch is pushed without generated artifacts.
- Every required CI job is green.

## Deliberate Limits

The implementation does not promise global annual optimality under a fixed deadline.
It guarantees independent validation for every accepted draft.
It reports bounded search outcomes without overstating proof.

## Implementation Status (2026-09-12)

Packages 0 through 6 are implemented on `codex/fix-adaptive-new-subject-demand`:

- Findings A-H have maintained unit and integration regressions, including exact module
  identity, reduced-demand excess handling, deadline cleanup, precise solver statuses,
  cancellation polling, recovery identity, cross-subject recovery rejection, and approval.
- Complete and adaptive runtime validation use the shared module coverage and chronology
  validator; active module identity is joined from each source draft block.
- Exhaustive small-case oracle and deterministic metamorphic tests are maintained without new
  dependencies. Job 13 retains its candidate-count guarantee without a wall-clock assertion.
- Peak-memory and multi-school load harnesses remain deferred because this repository has no
  stable deterministic harness for those measurements.
- Remaining release actions are the commit/push and required CI monitoring. The local Alembic
  check is environment-blocked until the configured development database is upgraded to the
  repository migration head; no migration is part of this WBS.

`ponytail:` Add broader solver architecture only when measured cases exceed these bounded repairs.
