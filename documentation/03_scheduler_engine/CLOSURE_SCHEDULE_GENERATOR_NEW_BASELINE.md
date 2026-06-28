# Schedule Generator New Baseline - Closure Notes

Date: 2026-06-24

Authority:
- `PRD_SCHEDULE_GENERATOR_NEW_BASELINE.md`
- `TECH_SPEC_SCHEDULE_GENERATOR_NEW_BASELINE.md`
- `WBS_SCHEDULE_GENERATOR_NEW_BASELINE_IMPLEMENTATION.md`

## Closure Decision

The new scheduler baseline is implemented as the only active generation path.
Generation is draft-first, strategy selection is automatic, approval is atomic,
and approved `ActiveScheduleBlock` rows drive the operational weekly schedule.

No known failure contradicts the PRD. The manual product walkthrough remains
documented in `MANUAL_QA_SCHEDULE_GENERATOR_NEW_BASELINE.md` for release QA.

## PRD Acceptance Evidence

| Acceptance area | Implemented evidence | Validation evidence |
|---|---|---|
| Strategy and product model | One `/scheduler/generate` action; state, debt, and scheduler changes select the internal strategy | `test_scheduler_state_service.py`, `test_scheduler_change_integration.py`, `test_schedule_generate_preflight.py` |
| Date configuration | Start and hard-end boundaries only; target/preferred end date rejected and absent from UI | `test_schemas_validation.py`, onboarding/config frontend tests, legacy scans |
| Complete generation | Full demand ledger, hard-pruned candidates, adaptive near horizon, near optimization, far provisional fill | complete-demand, candidates, horizon, near-optimizer, far-fill, complete-engine tests |
| Effort and horizon | Five-minute deadline, checkpoints, cancellation, bounded large-school effort | `test_scheduler_job_runtime.py`, `test_scheduler_large_school.py` |
| Adaptive repair | Editable boundary, trigger impact, recovery/adaptation ladders, disruption score, partial/no-output rules | editable-boundary, disruption, recovery-ladder, adaptation-ladder, adaptive-engine tests |
| Debt accounting | Explicit operational debt, sequential module accounting, planned recovery lifecycle | debt fingerprint, sequential accounting, recovery service, lesson registration tests |
| Draft workflow | One pending draft, atomic replacement, summary/diff, stale/invalid checks, approve/reject/reset | job runtime, diff, status, lifecycle and permission tests |
| Partial recovery | Residual debt, blocker type/message/actions, useful partial drafts only | adaptive-engine, job-runtime, golden-scenario tests |
| Constraints and quality | Teacher/grid/calendar/room/lunch constraints are hard; valid soft ranking remains bounded | candidate, near-optimizer, complete-engine and golden fixture tests |
| Metrics and audit | Snapshots, fingerprints, versions, diff, diagnostics and lifecycle events persisted | fingerprint, observability, status and runtime tests |
| Reliability and security | Atomic outcomes, tenant scoping, RLS, permissions, idempotency and concurrency | tenant isolation, permissions, RLS, runtime concurrency and full backend suite |

## Technical Scenario Matrix

All 19 required scenarios are automated:

1. First unpublished year creates a Complete draft.
2. Teacher availability change makes a Complete draft stale.
3. Complete approval publishes the first schedule.
4. Published year without a trigger blocks generation.
5. Explicit GAP debt enables repair.
6. Planned recovery coverage suppresses repeat repair.
7. SUBSTITUTED debt and its operational block remain independent.
8. Scheduler-relevant room/resource changes trigger adaptation.
9. Stability-window-only changes do not unlock generation.
10. Mixed debt and scheduler change produce one mixed draft.
11. Window zero permits today-forward edits and preserves past/executed blocks.
12. Partial Recovery uses an approved blocker message.
13. Scheduler-change impossibility reports affected-block language.
14. Rejection preserves audit details.
15. Successful regeneration atomically replaces one pending draft.
16. Failure, cancellation, timeout and No Valid Output preserve the old draft.
17. Fingerprint mismatch blocks approval.
18. Cross-tenant draft approval is rejected.
19. Reset returns the year to `UNPUBLISHED`.

Primary evidence: `test_alpha_release_gate.py`,
`test_scheduler_job_runtime.py`, `test_scheduler_golden_fixtures.py`,
`test_scheduler_tenant_isolation.py`, and `test_scheduler_permissions.py`.

## WBS Closure

| Phase | Result |
|---|---|
| 0. Cutover guardrails | Legacy modes, target date, rolling-horizon product rule and conflicting routes removed |
| 1. Domain and migrations | School-year state, jobs, drafts, target blocks, diffs, recovery links and version events added |
| 2. State and strategy | Monotonic versions, fingerprints, repair policy and automatic strategy selection added |
| 3. Debt and recovery | User-controlled debt, sequential accounting and recovery links added |
| 4. Runtime | Persisted jobs, five-minute cap, locks, idempotency, atomic replacement and terminal outcomes added |
| 5. Complete engine | Full demand through valid complete draft implemented |
| 6. Adaptive engine | Editable boundary and both escalation ladders implemented |
| 7. Lifecycle | Status, summary, diff, approval reconciliation, rejection and reset implemented |
| 8. API and UX | One generate/review/approve flow and cleaned configuration implemented |
| 9. Reliability | Tenant isolation, permissions, concurrency, cancellation, observability and integrity validated |
| 10. Acceptance | Scenario, scale, golden-data, manual-QA, legacy and final verification gates closed |

## Operational Cutover

- Approved schedule versions publish `ActiveScheduleBlock` rows.
- Weekly schedule reads active rows and suppresses overlapping legacy outputs.
- Lesson logs, occurrences, substitutions, timesheets and recovery delivery accept
  active block identity.
- `ScheduleOutput` remains only for historical operational records and explicit
  compatibility reads; it is not an alternate generation or publication path.
- Old generator routes, workers, draft models and conflicting tests were removed.

## Final Verification

- Backend: `563 passed, 7 skipped`.
- Frontend: `132 passed` across 22 files.
- Frontend lint: passed (dependency-data freshness warning only).
- Frontend production build: passed.
- Python compile: passed.
- Alembic empty-schema upgrade: passed to `d3a7e5b9c2f1 (head)`.
- Alembic downgrade to `c2f6a8d4e1b9` and re-upgrade: passed.
- `git diff --check`: passed.
- Required legacy scans: runtime/UI clear; remaining matches are negative rules,
  migrations, rejection tests, or documents explicitly marked historical.

## Release Notes

- Apply Alembic through `d3a7e5b9c2f1` before deploying backend workers.
- Deploy API and scheduler worker from the same revision.
- Execute the manual QA script in the release environment with a representative
  tenant before enabling generation for pilot users.
