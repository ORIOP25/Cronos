# WBS - Schedule Generator New Baseline Implementation

## Status And Authority

This WBS is the execution plan for implementing the closed scheduler baseline.

Authoritative inputs:
- `PRD_SCHEDULE_GENERATOR_NEW_BASELINE.md`
- `TECH_SPEC_SCHEDULE_GENERATOR_NEW_BASELINE.md`

This WBS is not the acceptance authority. The feature is done only when the PRD acceptance matrix and the technical spec behavior are satisfied in the running product. Completing every task below is necessary but not sufficient if the expected product behavior is still missing.

## Implementation Rule

The new baseline replaces the legacy scheduler implementation. Legacy behavior that conflicts with the PRD must be removed, rewritten, or quarantined behind historical documentation. It must not survive as an alternate runtime path.

Conflicting legacy concepts include:
- user-selectable `full` / `repair` generation modes;
- `school_target_end_date`, preferred end date, target end date, and target-end optimization;
- fixed 8-week rolling horizon as a product rule;
- target drift as a solver objective;
- patch-style draft persistence where the draft is a list of changes instead of the target future schedule;
- immediate pending-draft replacement before the new draft is validated and committed;
- debt inferred automatically from absences before the user declares the operational state;
- generation that directly publishes future schedule blocks without draft approval.

## Delivery Principles

1. Build draft-first. Generation creates a validated draft. Approval publishes.
2. Keep one pending draft per school year. Replacement is atomic on successful replacement commit.
3. Treat complete and adaptive repair as internal strategies selected automatically.
4. Optimize near future, provisionally fill far future, and respect the five-minute job cap.
5. Preserve past and immutable blocks. Approval reconciles only editable future schedule.
6. Treat hard constraints as non-negotiable. Soft objectives only rank valid candidates.
7. Prefer clean replacement over compatibility with legacy scheduler paths.

## Current Legacy Collision Inventory

This inventory was produced before WBS creation and must be resolved during implementation.

Backend collisions:
- `backend/app/solver_tasks.py` contains `DEFAULT_SOLVER_V2_ROLLING_WEEKS`, target-end planning, direct draft/full generation concepts, and `school_target_end_date` usage.
- `backend/app/core/solver_engine_v2.py` contains target drift as a solver objective and accepts `school_target_end_date`.
- `backend/app/services/preflight_service.py` derives hard-end behavior from `school_target_end_date` and imports old rolling-week helpers.
- `backend/app/services/settings_service.py` and `backend/app/services/organization_service.py` persist `school_target_end_date`.
- `backend/app/api/v1/endpoints/schedule.py` still contains repair-mode wording and target-end fallback.
- `backend/app/models.py` and `backend/app/schemas.py` expose `school_target_end_date`.
- Existing backend tests assert the old settings, preflight, rolling-week, target-drift, and mode behavior.

Frontend collisions:
- `frontend/src/pages/Onboarding.jsx` exposes `school_target_end_date`.
- `frontend/src/pages/SchoolConfig.jsx` exposes and validates `school_target_end_date`.
- `frontend/src/test/Onboarding.test.jsx` asserts the old onboarding payload.

Documentation collisions already marked historical or rewritten:
- older scheduler docs in `documentation/03_scheduler_engine`;
- `documentation/05_backend_api/ENDPOINT_STANDARDS.md`;
- legacy product, regression, and UX planning docs that mention old scheduler behavior.

## Phase 0 - Cutover Guardrails And Legacy Removal

Goal: make it impossible for engineers to accidentally implement the old scheduler contract.

### 0.1 Baseline Confirmation

Tasks:
- Re-read the PRD and technical spec before code changes.
- Confirm the latest spec audit corrections are present:
  - pending draft replacement happens only on successful replacement commit;
  - target draft blocks do not contain removed blocks;
  - partial recovery exposes blocker type, main blocker message, and recommended actions;
  - hard constraints include assignment eligibility and demand/result consistency;
  - five-minute cap boundary is explicit;
  - replacement failure keeps the previous pending draft.

Deliverables:
- implementation branch or work session note;
- baseline confirmation in the implementation PR description.

Validation:
- no implementation task starts from older solver docs as source of truth.

### 0.2 Remove Public Generation Mode Selection

Tasks:
- Remove request fields, UI controls, and tests that let users choose `full`, `repair`, complete, or repair.
- Replace them with one generate action.
- Implement automatic strategy selection from publication state, unresolved explicit debt, and scheduler-relevant schedule-shaping changes.

Likely files:
- `backend/app/api/v1/endpoints/schedule.py`
- `backend/app/schemas.py`
- frontend schedule generation components/pages
- schedule generation tests

Acceptance:
- the public API does not accept `mode`;
- the UI does not expose complete/repair choices;
- the response may explain the selected internal strategy after generation.

### 0.3 Remove Preferred/Target End Date

Tasks:
- Remove `school_target_end_date` from active product schemas, UI forms, onboarding, validation, preflight, solver input, and settings update logic.
- Keep only school start date and hard end date as active scheduling boundaries.
- Add a migration strategy for the old database column:
  - either drop it in the clean rebuild path;
  - or mark it deprecated and unused until the schema cleanup migration removes it.

Likely files:
- `backend/app/models.py`
- `backend/app/schemas.py`
- `backend/app/services/settings_service.py`
- `backend/app/services/organization_service.py`
- `backend/app/services/preflight_service.py`
- `frontend/src/pages/Onboarding.jsx`
- `frontend/src/pages/SchoolConfig.jsx`
- affected tests

Acceptance:
- no active runtime code reads preferred/target end date;
- generated schedules optimize to finish as early as reasonably possible within the hard end, not to hit a target date.

### 0.4 Remove Or Rewrite Legacy Solver V2 Contract

Tasks:
- Decide whether old Solver V2 files are deleted, replaced, or reduced to internal helpers.
- Remove target drift and fixed rolling-week product behavior.
- Replace the fixed 8-week concept with adaptive near-future horizon selection from the new spec.
- Remove metrics that imply target-end drift is an objective.

Likely files:
- `backend/app/core/solver_engine_v2.py`
- `backend/app/solver_tasks.py`
- `backend/app/services/preflight_service.py`
- `backend/tests/test_solver_v2_lexicographic.py`
- `backend/tests/test_solver_helpers.py`

Acceptance:
- old solver target drift cannot affect output;
- fixed 8-week behavior exists only, if at all, as a non-authoritative fallback constant inside adaptive horizon logic.

### 0.5 Rewrite Legacy Tests

Tasks:
- Delete or rewrite tests that prove old behavior.
- Keep valuable fixtures only when they can be adapted to the new baseline.
- Add negative tests proving removed behaviors are absent.

Acceptance:
- no test expects `school_target_end_date`;
- no test expects public `mode=full` or `mode=repair`;
- no test treats fixed rolling weeks as the generation contract.

### 0.6 Documentation Sweep

Tasks:
- Ensure active docs point to the PRD, spec, and this WBS.
- Mark remaining legacy docs historical when they contain obsolete scheduler rules.
- Delete legacy docs only when they create active ambiguity and have no historical value.

Acceptance scan:

```powershell
rg -n "school_target_end_date|mode=full|mode=repair|target_drift|preferred end date|target end date|rolling_weeks" documentation backend frontend
```

Expected result:
- hits are either removed;
- or intentionally retained in PRD/spec/WBS as superseded behavior, negative tests, or migration notes.

## Phase 1 - Domain Schema And Migrations

Goal: create the persistence model required by the new lifecycle.

### 1.1 School-Year Scheduler State

Tasks:
- Add `scheduler_school_year_state`.
- Scope it by tenant and school year.
- Track `school_year_publication_state` only:
  - `UNPUBLISHED`
  - `PUBLISHED`
- Track state version, active publication, and timestamps.
- Track pending drafts separately in `schedule_drafts`; pending draft existence must not become a publication state.

Acceptance:
- one state row governs one tenant/school-year scheduler lifecycle;
- reset-year returns the publication state to `UNPUBLISHED`;
- publication state controls strategy selection, while pending draft presence controls review/replace workflow.

### 1.2 Generation Jobs

Tasks:
- Add `schedule_generation_jobs`.
- Track status, strategy, trigger reason, queued/started/finished timestamps, cap deadline, cancellation, timeout, error category, and result category.
- Store input snapshots and fingerprints needed for audit and stale protection.

Acceptance:
- every generation attempt has an auditable job row;
- failure/cancel/timeout does not publish or replace drafts.

### 1.3 Drafts

Tasks:
- Add `schedule_drafts`.
- Track draft state:
  - `PENDING`
  - `APPROVED`
  - `REJECTED`
  - `REPLACED`
  - `STALE`
  - `INVALIDATED`
- Store strategy, summary, result category, recovery/adaptation levels, blocker fields, warnings, metrics, and basis fingerprints.
- Enforce one pending draft per tenant/school-year.

Acceptance:
- a second pending draft cannot exist after final commit;
- replacement is atomic and old draft remains pending if replacement generation fails;
- failed, canceled, timed-out, or No Valid Output generation jobs do not create approvable drafts.

### 1.4 Draft Target Blocks

Tasks:
- Add `schedule_draft_blocks`.
- Store the concrete proposed future schedule as target state.
- Do not store removed blocks as draft blocks.
- Keep module sequence metadata only as accounting/diagnostic metadata, not as a scheduling driver.

Acceptance:
- approval can make active editable future equal the draft target blocks;
- removed active blocks are represented only in diff entries.

### 1.5 Draft Diff Entries

Tasks:
- Add `schedule_diff_entries`.
- Store optional detailed comparison:
  - `ADDED`
  - `MOVED`
  - `CHANGED`
  - `REMOVED`
  - `UNCHANGED_IMPACTED` if useful for explaining ripple scope.
- Store before/after block references and human-readable reason codes.

Acceptance:
- summary approval does not require inspecting diff;
- deep diff is available and audit-safe.

### 1.6 Planned Recovery Links

Tasks:
- Add or rewrite `planned_recovery_links`.
- Link debt source to proposed recovery draft block and, after publication/delivery, active block/log evidence.
- Include delivery evidence fields such as `delivered_lesson_log_id` and `delivered_at`.
- Make delivery idempotent.

Acceptance:
- delivered recovery can be audited;
- repeated status processing does not double-count recovered debt.

### 1.7 Version Events

Tasks:
- Add `scheduler_state_version_events`.
- Track scheduler-relevant changes and why they incremented the school-year state version.
- Include actor, entity type, entity ID, change type, and before/after metadata where practical.

Acceptance:
- drafts can be invalidated or blocked by comparing their snapshot to current version/fingerprint state.

### 1.8 Migration Integrity

Tasks:
- Add indexes and uniqueness constraints for tenant/year isolation.
- Add foreign keys with correct delete behavior.
- Write migration upgrade/downgrade tests where project convention supports them.
- Decide and implement cleanup for obsolete columns and tables.

Acceptance:
- migrations run on an empty database;
- migrations run on an existing development database with legacy scheduler data;
- tenant data cannot leak across school-year state, jobs, drafts, blocks, or links.

## Phase 2 - State Versioning, Fingerprints, And Strategy Selection

Goal: make generation eligibility deterministic and auditable.

### 2.1 Scheduler State Service

Tasks:
- Implement service methods to load/create school-year state.
- Centralize transitions between publication states.
- Centralize pending draft lookup.

Acceptance:
- endpoints do not hand-roll state transitions.

### 2.2 Version Increment Rules

Tasks:
- Implement scheduler-relevant change detection.
- Increment version for any change that changes scheduling conditions:
  - teacher availability;
  - teacher assignment;
  - class/subject demand;
  - rooms and room compatibility;
  - timeslots;
  - blocked dates;
  - calendar settings;
  - hard end date;
  - lunch settings.
- Track repair-policy changes such as stability window separately for draft staleness; changing only repair policy must not unlock generation.
- Track debt-producing or debt-resolving operational status changes separately in the debt basis fingerprint; they may enable repair through unresolved explicit debt, but they must not masquerade as scheduler-condition version changes unless they also change schedule-shaping inputs.
- Do not require complex violation detection. If schedule-shaping conditions changed, allow a new generation.

Acceptance:
- after a relevant change, the admin can generate again;
- irrelevant profile/text-only changes do not create scheduler work unless they affect scheduling input;
- changing only the repair stability window does not allow generation when there is no unresolved explicit debt and no scheduler-relevant schedule-shaping change.

### 2.3 Input Fingerprints

Tasks:
- Implement `generation_input_fingerprint`.
- Include all scheduler-relevant configuration and resource data.
- Use stable serialization and hashing.

Acceptance:
- identical inputs produce identical fingerprint;
- relevant changed inputs produce a different fingerprint.

### 2.4 Debt Basis Fingerprint

Tasks:
- Implement `debt_basis_fingerprint`.
- Include debt sources, amounts, statuses, and recovery links that affect repair.
- Include debt-producing and debt-resolving operational status changes such as `GAP`, debt-creating `SUBSTITUTED`, reclassification to `GIVEN`, missed recovery, canceled recovery, and delivered recovery evidence.
- Include active approved planned recovery links as debt coverage so already-covered minutes do not remain unresolved.

Acceptance:
- repair drafts become stale or blocked when the debt basis changes before approval;
- approved planned recovery coverage suppresses repeat repair generation for the covered debt unless that recovery is canceled, missed, invalidated, or only partially covers the debt.

### 2.5 Repair Policy Snapshot

Tasks:
- Snapshot repair stability window and policy settings at generation time.
- Treat policy changes as repair-policy changes: they stale pending Adaptive Repair drafts but do not create standalone generation triggers.

Acceptance:
- approval validates the draft against the expected snapshot rules;
- changing only repair policy never unlocks generation when no unresolved explicit debt or scheduler-relevant schedule-shaping change exists.

### 2.6 Automatic Strategy Selection

Tasks:
- Implement one public generate command.
- Select complete generation when no schedule has been published for the school year.
- Select adaptive repair when a schedule exists and there is unresolved explicit debt or a scheduler-relevant schedule-shaping change.
- Reject generation when a schedule exists and there is no unresolved explicit debt and no scheduler-relevant schedule-shaping change.
- If a pending draft exists, require explicit replacement confirmation from UI/API; the old draft remains pending until successful replacement commit.

Acceptance:
- the admin cannot manually choose complete/repair;
- the system explains why generation is available or unavailable.

## Phase 3 - Debt Accounting And Recovery Links

Goal: make debt human-controlled and recovery auditable.

### 3.1 Operational Status Accounting

Tasks:
- Implement accounting semantics:
  - `GIVEN` is credited and creates no debt;
  - `GAP` creates debt that must be recovered;
  - `SUBSTITUTED` creates original-lesson debt and creates an independent `OperationalScheduleBlock` for the substituted delivery, separate from structural `Lesson` demand;
  - `PENDING` / unregistered waits for user action and is not debt yet;
  - future scheduled lessons are expected capacity and not debt yet.

Acceptance:
- the system does not infer debt from missing status alone;
- the user controls when a missed class becomes debt.

### 3.2 Active Debt Ledger

Tasks:
- Build a demand/debt ledger by class, subject, and source block.
- Track remaining minutes/hours.
- Exclude delivered or fully recovered debt.
- Subtract active approved planned recovery links from unresolved debt.
- Treat debt with active approved planned recovery coverage as not eligible to trigger repeat repair for the covered minutes.
- Include residual debt from failed, canceled, partially covered, invalidated, or missed recovery blocks.

Acceptance:
- adaptive repair starts from unresolved explicit debt only;
- a debt source fully covered by active approved planned recovery does not unlock generation by itself;
- partial planned recovery leaves only the uncovered residual eligible for repair.

### 3.3 Sequential Module Accounting

Tasks:
- Implement subject-level scheduling with sequential module accounting.
- Do not split scheduling demand into UFCD/module-specific future placement.
- Assign delivered subject hours to module sequence during accounting:
  - first 30h of mathematics can count toward module 1;
  - hour 31 naturally starts module 2.

Acceptance:
- the generator schedules subject demand;
- module progress is derived from delivered subject hours.

### 3.4 Recovery Planning

Tasks:
- When repair schedules debt, create planned recovery links from source debt to draft blocks.
- On approval, reconcile links to active future blocks.
- On delivery, write delivery evidence.

Acceptance:
- a recovered debt source cannot be recovered twice;
- partial recovery clearly reports recovered and remaining hours.

## Phase 4 - Generation Orchestrator And Job Runtime

Goal: provide a reliable bounded generation pipeline.

### 4.1 API Entry

Tasks:
- Implement `POST /scheduler/generate`.
- Keep request payload minimal:
  - school year/context;
  - optional replace-pending confirmation;
  - optional idempotency key if adopted.
- Do request-gating preflight only for cheap, non-solving checks.

Acceptance:
- request does not accept target end date or strategy mode;
- response creates or references a generation job.

### 4.2 Five-Minute Cap Boundary

Tasks:
- Start the five-minute generation cap when the worker begins the generation job snapshot/verification phase.
- Keep synchronous request-gating preflight outside the cap, but fast and non-solving.
- Keep snapshot verification, solver work, validation, and draft persistence inside the cap.
- Reserve time for final validation and commit.

Acceptance:
- timeout/cancel returns no partial persistence;
- a valid draft is committed only after final validation inside the job boundary.

### 4.3 Job Locking And Idempotency

Tasks:
- Lock per tenant/school-year generation.
- Prevent concurrent active generation jobs for the same school year.
- Support safe retry where possible.

Acceptance:
- concurrent clicks do not create duplicate jobs or drafts.

### 4.4 Atomic Pending Draft Replacement

Tasks:
- If replacing a pending draft, generate and validate the new draft without changing the old draft.
- In one final transaction:
  - mark old pending draft `REPLACED`;
  - insert the new validated draft as `PENDING`;
  - update school-year state.

Acceptance:
- if replacement fails, cancels, times out, or produces No Valid Output, the previous draft remains `PENDING`.

### 4.5 Failure And Cancellation

Tasks:
- Implement failure categories:
  - `CANCELED`
  - `TIMED_OUT`
  - `NO_VALID_OUTPUT`
  - `FAILED_VALIDATION`
  - `SYSTEM_ERROR`
- Ensure no invalid draft is visible.

Acceptance:
- failure is auditable;
- active schedule and pending draft remain unchanged unless final commit succeeds.

## Phase 5 - Complete Generation Engine

Goal: generate the first schedule for the school year.

### 5.1 Complete Demand Ledger

Tasks:
- Build full annual demand from class-subject assignments and required hours.
- Apply subject-level scheduling and sequential module accounting rules.
- Validate teacher/class/room eligibility before candidate generation.

Acceptance:
- complete generation cannot pass while missing required demand.

### 5.2 Candidate Generation And Hard Pruning

Tasks:
- Generate candidate placements for class, teacher, room, day, and timeslot.
- Prune candidates that violate hard constraints:
  - class conflict;
  - teacher conflict;
  - room conflict;
  - room type compatibility;
  - teacher/class/subject assignment eligibility;
  - blocked dates;
  - hard end date;
  - timeslot grid;
  - protected lunch;
  - tenant isolation.

Acceptance:
- solver never ranks candidates that are structurally invalid.

### 5.3 Adaptive Near-Future Horizon

Tasks:
- Compute complexity score from number of classes, teachers, rooms, timeslots, demand, conflicts, availability density, and remaining days.
- Choose near-future optimization horizon adaptively.
- Use a small school/lower complexity horizon larger than a large school/higher complexity horizon.
- Respect the five-minute cap.

Acceptance:
- horizon is not a fixed product rule;
- large schools still receive a usable draft inside the cap.

### 5.4 Near-Future Optimization

Tasks:
- Optimize near future with a constraint solver or equivalent deterministic optimization engine.
- Prioritize:
  - earliest feasible completion;
  - class completion fairness;
  - workload sanity;
  - teacher availability preferences;
  - room consistency;
  - stable rhythm where it does not delay completion.
- Report the natural hard-end margin created by early completion; do not reserve artificial recovery capacity as an objective.

Acceptance:
- output is hard-valid;
- near future is higher quality than a naive greedy fill.

### 5.5 Far-Future Provisional Fill

Tasks:
- Fill the remaining year capacity-aware and bottleneck-first.
- Preserve hard constraints.
- Use provisional placement quality sufficient for publication after approval.
- Avoid pretending the far future is globally optimal.

Acceptance:
- first generation produces a complete concrete draft for the year;
- far-future schedule is valid, even if less optimized than near future.

### 5.6 Complete Result Rules

Tasks:
- Complete generation must return either:
  - valid full draft;
  - No Valid Output with actionable blockers.
- It must not return partial first schedule as a publishable draft.

Acceptance:
- a school never starts with half a first schedule.

## Phase 6 - Adaptive Repair Engine

Goal: recover unresolved explicit debt and adapt to changed conditions after the first schedule exists.

### 6.1 Editable Boundary

Tasks:
- Calculate immutable past and protected present.
- Enforce user-configurable frozen stability window, including value `0`.
- Preserve blocks outside editable scope.

Acceptance:
- past blocks are never modified;
- stability window can protect zero days when the admin chooses it.

### 6.2 Trigger Classification

Tasks:
- Classify repair reason:
  - unresolved explicit debt only;
  - scheduler-relevant change only;
  - mixed debt and scheduler change.
- Select recovery/adaptation ladder accordingly.

Acceptance:
- draft summary explains why generation ran.

### 6.3 Recovery Escalation Ladder

Tasks:
- Implement the six recovery levels defined in the PRD.
- Escalate only as required to recover unresolved explicit debt before hard end.
- Track selected level and why lower levels were insufficient.

Acceptance:
- small unresolved explicit debt creates small disruption;
- larger or late unresolved explicit debt can broaden changes as necessary.

### 6.4 Scheduler-Change Adaptation Ladder

Tasks:
- Implement the scheduler-change adaptation ladder.
- Handle resource/config changes even when no unresolved explicit debt exists.
- When scheduler-relevant conditions changed, adapt to the latest conditions with the smallest valid scope, even if the current future is still technically valid.
- If no valid adaptation exists, return No Valid Output with blockers.

Acceptance:
- changed resources/configurations allow generation;
- no generation is allowed when nothing relevant changed and no unresolved explicit debt exists.

### 6.5 Disruption Score

Tasks:
- Implement stakeholder-weighted disruption scoring:
  - what changed;
  - who was affected;
  - when the change happens;
  - ripple scope.
- Use it to rank valid repair candidates.

Acceptance:
- repair favors least disruptive valid schedules;
- disruption metrics are visible in draft summary/audit.

### 6.6 Partial Recovery

Tasks:
- If full recovery is impossible, generate the best valid partial recovery draft.
- Report recovered hours and remaining unscheduled hours.
- Expose `partial_recovery_blocker_type`, `main_blocker_message`, and `recommended_actions`.

Required blocker message variants:

```text
The stability window protects too much of the remaining schedule before the hard end date.
```

```text
The remaining hours cannot fit with the current resources and hard end date.
```

Required user-facing format:

```text
Partial recovery generated.

8h were recovered, but 10h remain unscheduled before the hard end date.

Main blocker:
The stability window protects too much of the remaining schedule before the hard end date.

Recommended actions:
- Reduce the stability window.
- Allow broader future schedule changes.
- Generate the schedule again.
```

Acceptance:
- partial recovery is a valid draft, not partial persistence;
- residual debt remains visible after approval.

### 6.7 No Valid Output For Scheduler Changes

Tasks:
- When changed conditions cannot produce any valid future schedule, return No Valid Output with blockers.
- Do not persist a new draft.

Acceptance:
- admin receives actionable explanation;
- previous active schedule/pending draft remains unchanged.

## Phase 7 - Draft Lifecycle, Approval, And Reconciliation

Goal: make draft review simple while preserving technical detail and auditability.

### 7.1 Status Endpoint

Tasks:
- Implement `GET /scheduler/status`.
- Distinguish:
  - primary action is review pending draft;
  - generation is available;
  - regeneration requires replacing pending draft confirmation;
  - generation unavailable because there is no unresolved explicit debt or scheduler-relevant change.

Acceptance:
- UI cannot confuse pending draft review with ordinary generation.

### 7.2 Draft Summary

Tasks:
- Implement concise summary:
  - result category;
  - selected strategy;
  - recovered/remaining debt;
  - affected classes/teachers/days;
  - disruption score;
  - recovery/adaptation level;
  - warnings;
  - main blocker and recommended actions when partial.

Acceptance:
- admin can approve from summary without mandatory deep diff.

### 7.3 Optional Deep Diff

Tasks:
- Implement detailed diff view.
- Show added, moved, changed, removed blocks and reasons.
- Keep it optional.

Acceptance:
- details are available but do not block summary approval.

### 7.4 Approval Preconditions

Tasks:
- Validate current fingerprints/state before approval.
- Complete drafts become stale if complete inputs changed.
- Repair drafts become stale/blocked based on trigger and debt basis rules from PRD.

Acceptance:
- stale drafts cannot publish silently.

### 7.5 Complete Approval

Tasks:
- Publish the complete target draft as the active future schedule.
- Transition school-year state to published.
- Preserve audit trail.

Acceptance:
- no active future schedule exists before first approval;
- after approval, active schedule equals the draft target.

### 7.6 Repair Approval

Tasks:
- Reconcile editable future schedule to equal draft target blocks.
- Preserve unchanged block identity where possible.
- Create new active blocks for changed/added blocks.
- Remove active editable blocks absent from draft target.
- Reconcile recovery links.

Acceptance:
- active future equals approved target draft;
- removed blocks exist only in diff/audit, not as target draft blocks.

### 7.7 Reject, Replace, And Reset

Tasks:
- Reject keeps audit history and clears pending status.
- Regenerate/replace follows atomic replacement semantics: the old pending draft is marked `REPLACED` only in the final successful replacement commit that creates the new validated draft.
- Reset-year is the only supported start-over path after admin confirmation.

Acceptance:
- rejected drafts are not deleted;
- replacement failure preserves previous pending draft;
- reset-year returns admin to first-generation flow.

## Phase 8 - API And Frontend UX

Goal: expose the new baseline without leaking internal complexity to the admin.

### 8.1 API Schemas

Tasks:
- Add/update Pydantic schemas for status, generation jobs, drafts, summaries, diffs, approval, rejection, and reset-year.
- Remove obsolete request/response fields.

Acceptance:
- API docs do not expose manual mode or target end date.

### 8.2 Generate/Review Flow

Tasks:
- Show one generation action when allowed.
- Show pending draft review as primary action when a draft exists.
- Show regenerate/replace only as explicit secondary action with confirmation.
- Show unavailable state when schedule exists and there is no unresolved explicit debt or scheduler-relevant change.

Acceptance:
- admin workflow matches automatic strategy selection.

### 8.3 Configuration Cleanup

Tasks:
- Remove preferred end date from onboarding and configuration page.
- Keep school start and hard end dates.
- Keep repair stability window configurable and allow `0`.
- Keep school reality settings configurable.
- Do not expose solver strategy knobs.

Acceptance:
- target/preferred end date field is gone from UI and payloads.

### 8.4 Draft Summary UI

Tasks:
- Build summary-first draft review.
- Include warnings and partial recovery blocker/actions.
- Make deep diff optional.
- Keep approve/reject actions clear.

Acceptance:
- admin can approve from summary;
- admin can inspect details when desired.

### 8.5 Error And Blocked States

Tasks:
- Implement user-facing messages for:
  - no unresolved explicit debt or scheduler-relevant change, generation unavailable;
  - pending draft exists, review first;
  - replacement confirmation;
  - stale draft;
  - partial recovery;
  - No Valid Output;
  - timeout/cancel/failure.

Acceptance:
- messages use the PRD-approved language where specified.

### 8.6 Frontend Tests

Tasks:
- Rewrite tests for onboarding/config payloads.
- Add status-driven generation flow tests.
- Add pending draft review/regenerate tests.
- Add partial recovery message tests.

Acceptance:
- frontend test suite proves the old controls are absent and the new flow works.

## Phase 9 - Reliability, Security, And Observability

Goal: make the generator safe to run repeatedly in a multi-tenant app.

### 9.1 Tenant Isolation

Tasks:
- Audit every query for tenant and school-year scope.
- Add tests for cross-tenant drafts, jobs, schedule blocks, and recovery links.

Acceptance:
- no tenant can read or mutate another tenant's generation state.

### 9.2 Permissions

Tasks:
- Restrict generation, approval, rejection, replacement, and reset-year to admin.
- Preserve professor schedule read-only/self-service rules.

Acceptance:
- professor role cannot trigger scheduler mutations.

### 9.3 Concurrency

Tasks:
- Add database locks or equivalent transactional guards.
- Handle duplicate requests and browser retries.

Acceptance:
- concurrent generation/approval cannot create split-brain state.

### 9.4 Timeout And Cancellation

Tasks:
- Make solver phases cooperative with cancellation/time budget.
- Reserve final time for validation and commit.
- Mark jobs timed out without persisting invalid drafts.

Acceptance:
- five-minute cap is enforced under load.

### 9.5 Observability

Tasks:
- Emit structured events for generation lifecycle.
- Track metrics:
  - job duration;
  - selected strategy;
  - result category;
  - recovery/adaptation level;
  - hard constraint failures;
  - recovered/remaining debt;
  - disruption score;
  - timeout/failure categories.

Acceptance:
- support can diagnose why a generation did or did not produce a draft.

### 9.6 Data Integrity Checks

Tasks:
- Add validation queries or service checks for:
  - duplicate teacher/class/room time conflicts;
  - draft target consistency;
  - recovery link consistency;
  - demand/result consistency;
  - stale fingerprints.

Acceptance:
- invalid schedules cannot be approved.

## Phase 10 - Acceptance Matrix, Cutover, And Closure

Goal: prove the feature works as defined, not merely that the work packages were touched.

### 10.1 Scenario Test Suite

Tasks:
- Implement PRD acceptance scenarios as automated tests.
- Cover:
  - first complete generation;
  - no manual strategy selection;
  - no preferred/target end date;
  - human-controlled debt;
  - repair with small unresolved explicit debt;
  - repair with late unresolved explicit debt;
  - active approved planned recovery suppresses repeat repair generation for covered debt;
  - partial planned recovery leaves only uncovered residual debt eligible for repair;
  - repair with stability window `0`;
  - partial recovery blocker variants;
  - scheduler-relevant change with no unresolved explicit debt;
  - no generation when no unresolved explicit debt or scheduler-relevant change exists;
  - pending draft replacement success;
  - pending draft replacement failure/cancel/timeout/No Valid Output preserves previous draft;
  - stale complete draft;
  - stale/blocked repair draft;
  - reset-year flow.

Acceptance:
- tests demonstrate the baseline end to end.

### 10.2 Large-School Bounded Effort Tests

Tasks:
- Add representative large-school fixtures.
- Verify generation returns inside the five-minute cap.
- Use controlled/mocked solver timing where unit tests need deterministic speed.
- Add integration/performance test separately if project runtime allows.

Acceptance:
- large schools receive a complete draft or valid failure within bounded time;
- no all-year global optimization attempt can exceed the cap unchecked.

### 10.3 Golden Data Fixtures

Tasks:
- Create small, medium, and large school fixtures.
- Include teacher constraints, room constraints, lunch, blocked dates, debt, and scheduler changes.

Acceptance:
- fixtures are reusable for regression and manual QA.

### 10.4 Manual QA Script

Tasks:
- Write a manual QA script for admin workflow:
  - configure school year;
  - generate first schedule;
  - approve draft;
  - declare debt;
  - repair;
  - inspect summary/diff;
  - approve;
  - change resource/config;
  - generate adaptation;
  - reset year.

Acceptance:
- a human can validate the intended experience without reading the implementation.

### 10.5 Final Legacy Sweep

Tasks:
- Run repository scans for removed concepts.
- Delete unreachable legacy scheduler code.
- Update docs that still point to old behavior.
- Confirm old tests were removed or rewritten.

Required scans:

```powershell
rg -n "school_target_end_date|mode=full|mode=repair|target_drift|preferred end date|target end date|DEFAULT_SOLVER_V2_ROLLING_WEEKS|rolling_weeks" backend frontend documentation
```

```powershell
rg -n "Repair mode|Full mode|target date|preferred date|8-week|8 week|rolling horizon" backend frontend documentation
```

Acceptance:
- remaining hits are historical docs, PRD/spec/WBS negative rules, migrations, or explicit compatibility cleanup notes only.

### 10.6 Final Verification Commands

Tasks:
- Run backend targeted scheduler tests.
- Run full backend tests if feasible.
- Run frontend tests.
- Run lint/type checks used by the project.
- Run migration checks.

Acceptance:
- failures are fixed or explicitly documented with owner and reason;
- no known failure contradicts the PRD.

### 10.7 Closure Review

Tasks:
- Review implementation against:
  - PRD acceptance matrix;
  - technical spec scenario matrix;
  - this WBS;
  - final user workflow.
- Produce closure notes.

Acceptance:
- feature is closed only when expected behavior is achieved in the app.

## Dependency Map

| Phase | Depends On | Blocks |
| --- | --- | --- |
| 0 | Closed PRD/spec | All implementation |
| 1 | Phase 0 decisions | Phases 2-7 |
| 2 | Phase 1 | Phases 4, 7, 8 |
| 3 | Phase 1 | Phases 5, 6, 7 |
| 4 | Phases 1-2 | Phases 5-8 |
| 5 | Phases 1-4 | Phase 7 complete approval |
| 6 | Phases 1-4 and debt ledger | Phase 7 repair approval |
| 7 | Phases 1-6 | Phase 8 draft UX |
| 8 | Phases 2, 4, 7 | Phase 10 manual QA |
| 9 | Phases 1-8 | Phase 10 closure |
| 10 | All prior phases | Release/closure |

## Risk Register

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Legacy solver code survives and conflicts with baseline | Engineers unknowingly keep old behavior | Phase 0 removal, final legacy scans, negative tests |
| Generation cap causes incomplete first schedule | School cannot start with a valid draft | Near-future optimization plus valid far-future provisional fill |
| Repair changes too much future schedule | Admin loses trust in the tool | Recovery/adaptation ladders plus disruption scoring |
| Repair changes too little and misses hard end | Debt remains hidden or impossible too late | Partial recovery reporting with blocker/actions |
| Draft replacement is not atomic | Existing pending draft can be lost | Final transaction semantics and replacement-failure tests |
| Patch-style draft model returns | Approval becomes fragile and hard to reason about | Target draft blocks plus diff entries only for comparison |
| Debt is inferred without user decision | Schedule changes surprise the admin | Human-controlled debt accounting |
| Fingerprints are too narrow | Stale drafts get approved | Include all scheduler-relevant state and version events |
| Fingerprints are too broad | Admin gets unnecessary stale drafts | Separate scheduler-relevant changes from irrelevant metadata |
| Large-school optimization is slow | Jobs time out often | Adaptive horizon, capacity-aware fill, cooperative cancellation |

## Definition Of Done

The schedule generator new baseline is done when:
- the public app exposes one generation action and no complete/repair mode choice;
- preferred/target end date is absent from UI, API contracts, active schemas, and solver logic;
- first generation creates a complete concrete draft for the school year or a clear No Valid Output;
- later generations are allowed only for unresolved explicit debt or scheduler-relevant schedule-shaping changes;
- debt accounting follows the user-controlled statuses from the PRD;
- repair uses escalation/adaptation levels and reports selected levels;
- partial recovery uses the approved blocker/action format;
- pending draft replacement is atomic and failure preserves the old pending draft;
- approval reconciles editable future schedule to the target draft blocks;
- hard constraints include assignment eligibility and demand/result consistency;
- the five-minute cap is enforced from job snapshot/verification start through validation/commit;
- large-school, small-school, partial-recovery, stale-draft, and replacement-failure scenarios pass;
- final legacy scans show no active conflicting behavior.
