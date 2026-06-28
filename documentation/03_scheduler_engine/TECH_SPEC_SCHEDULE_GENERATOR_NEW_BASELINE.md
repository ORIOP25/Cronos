# Technical Architecture Spec - Schedule Generator New Baseline

## Status And Authority
- Type: technical architecture specification.
- Source of product truth: `PRD_SCHEDULE_GENERATOR_NEW_BASELINE.md`.
- Scope: implementation architecture for the new schedule generator baseline.
- Legacy policy: legacy scheduler behavior must be rewritten, adapted, or retired when it conflicts with this spec and the PRD.
- Stack target: FastAPI, SQLAlchemy, Alembic, Celery, PostgreSQL-compatible relational storage, existing tenant context helpers, and existing OR-Tools/CP-SAT capability where useful.

This document does not redefine product behavior. It translates the closed PRD into buildable backend, database, algorithm, API, frontend, reliability, and test design.

## 1. Architecture Overview

### 1.1 Architectural Principles
The scheduler must be:
- draft-first: generation never publishes directly;
- state-machine driven: publication state, draft state, generation job state, and debt lifecycle are explicit;
- tenant-scoped: every read/write is constrained by `organization_id`;
- school-year scoped: generation, versions, drafts, and active schedules belong to one active school year;
- fingerprint-protected: stale drafts cannot be approved after relevant inputs change;
- bounded: every generation respects the 5-minute hard cap;
- honest: impossible and partial outputs are reported clearly instead of pretending success;
- PRD-driven: implementation completion is measured against the PRD acceptance matrix.

### 1.2 Bounded Contexts
The implementation should be split into these service boundaries:

1. `SchedulerStateService`
   - owns `school_year_publication_state`;
   - owns `scheduler_state_version`;
   - stores `approved_scheduler_state_version`;
   - applies the scheduler-relevant change allowlist.

2. `SchedulerFingerprintService`
   - computes `generation_input_fingerprint`;
   - computes `debt_basis_fingerprint`;
   - computes `repair_policy_snapshot`.

3. `SchedulerPreflightService`
   - validates configuration completeness;
   - validates hard feasibility before queueing expensive generation;
   - returns operational messages, not solver jargon.

4. `ScheduleGenerationOrchestrator`
   - receives the single `Generate Schedule` command;
   - chooses Complete Generation or Adaptive Repair automatically;
   - creates and tracks generation jobs;
   - enforces the one-pending-draft rule.

5. `CompleteGenerationEngine`
   - builds the first full concrete schedule draft for an `UNPUBLISHED` school year;
   - runs progressive optimization and capacity-aware far-future fill.

6. `AdaptiveRepairEngine`
   - resolves operational triggers for a `PUBLISHED` school year;
   - uses debt recovery escalation, scheduler-change adaptation, or both;
   - can produce Complete Success, Partial Recovery, or No Valid Output.

7. `ScheduleDraftService`
   - persists draft metadata and draft blocks;
   - exposes summary and detailed diff;
   - marks drafts stale, invalidated, rejected, replaced, or approved.

8. `ScheduleApprovalService`
   - revalidates fingerprints and hard constraints;
   - publishes Complete drafts;
   - reconciles Adaptive Repair drafts into the active future schedule;
   - reconciles recovery links.

9. `DebtAccountingService`
   - computes unresolved explicit debt;
   - manages declared, planned, delivered, and residual debt;
   - links debt occurrences to planned/delivered recovery blocks.

10. `SchedulerAuditService`
    - stores generation summaries;
    - stores changed-block diff snapshots;
    - stores decision records.

### 1.3 High-Level Flow
```text
Admin clicks Generate Schedule
  -> API authorizes admin and tenant
  -> Orchestrator loads school-year scheduler state
  -> Preflight validates required data
  -> Strategy is selected automatically
  -> Fingerprints/snapshots are computed
  -> Celery job runs generation under 5-minute cap
  -> Result is validated
  -> Existing pending draft is replaced atomically if needed
  -> New draft and audit summary are persisted
  -> Admin reviews summary or optional detail
  -> Approval revalidates fingerprints and hard constraints
  -> Approval publishes or reconciles active schedule atomically
```

### 1.4 Legacy Behavior To Remove Or Rewrite
The implementation must remove or neutralize:
- user-facing `mode=full|repair` selection;
- `school_target_end_date` and target-end optimization;
- fixed 8-week rolling horizon as product behavior;
- target-drift objective;
- raw churn as the primary repair objective;
- automatic debt inference from pending/unregistered lessons;
- multiple pending drafts;
- rejection that deletes audit history;
- direct generation-to-published writes;
- repair triggered only by changing the stability window.

## 2. Domain Model And Schema

### 2.1 Schema Strategy
Prefer explicit new tables over overloading existing `ScheduleOutput` fields for all lifecycle semantics. Existing tables can be reused only if they cleanly support the new baseline.

The architecture may continue using `ScheduleOutput` for active and draft blocks during migration, but the logical model below is authoritative. If existing fields conflict with these concepts, migrations should add new columns/tables and deprecate old behavior.

### 2.2 `scheduler_school_year_state`
One row per `(organization_id, school_year_id)`.

Required fields:
- `id`
- `organization_id`
- `school_year_id`
- `school_year_publication_state`: `UNPUBLISHED` or `PUBLISHED`
- `active_schedule_version_id`: nullable
- `pending_draft_id`: nullable
- `scheduler_state_version`: integer, starts at `0`
- `approved_scheduler_state_version`: integer, nullable until first approval
- `timezone`: IANA timezone string, for example `Europe/Lisbon`
- `reset_at`, nullable
- `reset_by_user_id`, nullable
- `created_at`, `updated_at`
- `lock_version` for optimistic concurrency

Invariants:
- unique `(organization_id, school_year_id)`;
- at most one pending draft per `(organization_id, school_year_id)`;
- `PUBLISHED` requires `active_schedule_version_id`;
- `UNPUBLISHED` may still have a pending Complete Generation draft.

### 2.3 `schedule_generation_jobs`
Tracks asynchronous generation execution.

Required fields:
- `id`
- `organization_id`
- `school_year_id`
- `requested_by_user_id`
- `strategy`: `COMPLETE_GENERATION` or `ADAPTIVE_REPAIR`
- `trigger_type`: `FIRST_GENERATION`, `EXPLICIT_DEBT`, `SCHEDULER_CHANGE`, `MIXED`, nullable for early failures
- `job_status`: `QUEUED`, `RUNNING`, `CANCEL_REQUESTED`, `CANCELED`, `SUCCEEDED`, `FAILED`, `NO_VALID_OUTPUT`
- `result_category`: `COMPLETE_SUCCESS`, `PARTIAL_RECOVERY`, `NO_VALID_OUTPUT`, nullable until final
- `generation_input_fingerprint`
- `debt_basis_fingerprint`, nullable
- `scheduler_state_version_used`, nullable
- `repair_policy_snapshot_hash`, nullable
- `started_at`, `finished_at`
- `deadline_at`
- `duration_ms`
- `failure_code`, nullable
- `failure_message`, nullable
- `idempotency_key`, nullable

Invariants:
- no more than one non-terminal generation job per `(organization_id, school_year_id)`;
- `deadline_at` must be no later than 5 minutes after actual generation start;
- terminal jobs must not mutate active schedules unless a draft approval later occurs.

### 2.4 `schedule_drafts`
Stores one proposed schedule state.

Required fields:
- `id`
- `organization_id`
- `school_year_id`
- `generation_job_id`
- `strategy`
- `draft_state`: `PENDING`, `APPROVED`, `REJECTED`, `REPLACED`, `STALE`, `INVALIDATED`
- `result_category`
- `trigger_type`
- `generation_input_fingerprint`
- `scheduler_state_version_used`, nullable
- `debt_basis_fingerprint`, nullable
- `repair_policy_snapshot_json`, nullable
- `repair_policy_snapshot_hash`, nullable
- `editable_start_date`, nullable for Complete Generation
- `recovery_escalation_level`, nullable
- `adaptation_level`, nullable
- `projected_completion_date`
- `hard_end_date`
- `summary_json`
- `stale_reason`, nullable
- `invalidated_reason`, nullable
- `created_by_user_id`
- `created_at`
- `decided_by_user_id`, nullable
- `decided_at`, nullable

Invariants:
- at most one `PENDING` draft per `(organization_id, school_year_id)`;
- stale and invalidated drafts cannot be approved;
- rejected/replaced/approved drafts remain auditable.

### 2.5 `schedule_draft_blocks`
Stores the proposed target schedule blocks.

This table must represent the future schedule as it should exist after approval. It is not a patch list.

If a currently active future block should disappear after approval, that active block is absent from `schedule_draft_blocks` and represented as `REMOVED` only in `schedule_diff_entries`.

Required fields:
- `id`
- `organization_id`
- `school_year_id`
- `draft_id`
- `source_active_block_id`, nullable
- `stable_block_key`
- `class_id`
- `subject_id`
- `teacher_id`
- `room_id`
- `room_type_id`, nullable
- `date`
- `timeslot_id`
- `duration_minutes`
- `module_sequence_index`, nullable diagnostic/accounting metadata only
- `is_recovery_block`
- `recovery_source_occurrence_id`, nullable
- `recovery_source_occurrence_revision`, nullable
- `change_type`: `UNCHANGED`, `ADDED`, `MOVED`, `ROOM_ONLY`, `REPLACED`
- `reason_code`, nullable
- `created_at`

Invariants:
- draft blocks satisfy all hard constraints when considered as a full draft schedule;
- `is_recovery_block=true` requires recovery source references;
- `REMOVED` is invalid in `schedule_draft_blocks`;
- module metadata must not drive future block placement. Future scheduling is subject-level; module/UFCD assignment is sequential accounting only.

### 2.6 Active Schedule Storage
The current implementation uses `ScheduleOutput`. The new baseline may either:
- adapt `ScheduleOutput` into `active_schedule_blocks`; or
- create a new `active_schedule_blocks` table and migrate use sites gradually.

Required logical fields:
- `id`
- `organization_id`
- `school_year_id`
- `schedule_version_id`
- `class_id`
- `subject_id`
- `teacher_id`
- `room_id`
- `date`
- `timeslot_id`
- `duration_minutes`
- `source_draft_block_id`
- `is_recovery_block`
- `status`: `ACTIVE`, `REMOVED`, `CANCELED`
- `created_at`, `updated_at`

Past/executed active blocks must not be mutated by generation or approval.

### 2.7 `planned_recovery_links`
Links unresolved debt to approved planned recovery blocks.

Required fields:
- `id`
- `organization_id`
- `school_year_id`
- `debt_occurrence_id`
- `debt_occurrence_revision`
- `planned_active_block_id`
- `planned_draft_block_id`, nullable after approval
- `planned_recovery_minutes`
- `delivered_recovery_minutes`
- `delivered_lesson_log_id`, nullable
- `delivered_at`, nullable
- `class_id`
- `subject_id`
- `teacher_id`, nullable
- `status`: `PLANNED`, `DELIVERED`, `CANCELED`, `REPLACED`
- `created_at`, `updated_at`

Invariants:
- planned links must point to an active block or approved draft transition target;
- deleting/replacing a planned recovery block must cancel or replace the link;
- residual debt is recomputed from declared minus delivered minus active planned recovery;
- delivered recovery must be backed by delivery evidence such as `delivered_lesson_log_id` and `delivered_at`;
- delivery marking must be idempotent for the same lesson log.

### 2.8 `scheduler_state_version_events`
Audits scheduler-relevant mutations.

Required fields:
- `id`
- `organization_id`
- `school_year_id`
- `version_after`
- `entity_type`
- `entity_id`
- `operation`: `CREATE`, `UPDATE`, `DELETE`, `BULK_IMPORT`
- `change_scope`: `FUTURE_IMPACTING`, `PAST_ONLY`, `NO_OP`, `INACTIVE_RESOURCE`
- `changed_by_user_id`
- `changed_at`
- `metadata_json`

Version increment rules are defined in Section 6.

### 2.9 Audit Tables
Use either dedicated tables or existing audit structures with equivalent fields:

`schedule_generation_audits`:
- generation id;
- draft id;
- strategy;
- result category;
- trigger type;
- generation input fingerprint;
- scheduler state version used;
- debt basis fingerprint;
- repair policy snapshot hash;
- projected completion date;
- hard end date;
- recovered debt minutes;
- residual debt minutes;
- affected future block count;
- disruption category/score;
- warnings;
- duration.

`schedule_diff_entries`:
- generation id;
- draft id;
- class/subject/teacher;
- before date/time/room;
- after date/time/room;
- change type, including `REMOVED` when an active block is absent from the target draft;
- affected/related/unrelated scope;
- reason;
- recovery link impact.

### 2.10 Fields To Remove Or Deprecate
Remove from active product contracts:
- `school_target_end_date`;
- generation request `mode`;
- solver V2 fixed rolling week configuration as product behavior;
- target-drift metrics as acceptance metrics;
- draft deletion semantics that erase audit history.

Existing database columns can be left temporarily only if:
- they are ignored by the new scheduler;
- they are hidden from UI/API contracts;
- a later cleanup migration is planned in the WBS.

## 3. State Machines

### 3.1 School-Year Publication State
```text
UNPUBLISHED
  Generate Complete -> Complete draft PENDING
  Approve Complete draft -> PUBLISHED
  Reject Complete draft -> UNPUBLISHED
  Regenerate Complete draft -> UNPUBLISHED + new PENDING draft
  Reset-year -> UNPUBLISHED

PUBLISHED
  Generate Adaptive Repair when trigger exists -> Repair draft PENDING
  Approve Repair draft -> PUBLISHED
  Reject Repair draft -> PUBLISHED
  Regenerate Repair draft when trigger exists -> PUBLISHED + new PENDING draft
  Reset-year -> UNPUBLISHED
```

Pending draft state is separate from publication state.

### 3.2 Draft State
```text
PENDING
  Approve -> APPROVED
  Reject -> REJECTED
  Regenerate request -> remains PENDING until successful replacement commit
  Successful replacement commit -> REPLACED + new PENDING draft
  Input changed -> STALE
  Trigger disappeared -> INVALIDATED

STALE
  Regenerate request -> remains STALE until successful replacement commit
  Successful replacement commit -> REPLACED + new PENDING draft
  Reject -> REJECTED

INVALIDATED
  Reject -> REJECTED

APPROVED, REJECTED, REPLACED
  terminal for that draft record
```

Rules:
- only `PENDING` and current-valid drafts can be approved;
- `STALE` drafts cannot be approved;
- `INVALIDATED` drafts cannot be approved;
- rejected/replaced/invalidated drafts remain as audit records.

### 3.3 Generation Job State
```text
QUEUED -> RUNNING -> SUCCEEDED
QUEUED -> RUNNING -> NO_VALID_OUTPUT
QUEUED -> RUNNING -> FAILED
QUEUED -> RUNNING -> CANCEL_REQUESTED -> CANCELED
```

Rules:
- `SUCCEEDED` creates a validated draft;
- `NO_VALID_OUTPUT` creates audit summary but no approvable draft;
- `FAILED` and `CANCELED` create no draft and no active schedule changes;
- no job writes active schedule blocks directly.

### 3.4 Debt Lifecycle
```text
Declared Debt
  Approved recovery block linked -> Planned Recovery
  Occurrence corrected to GIVEN -> no unresolved debt

Planned Recovery
  Recovery block delivered -> Delivered Recovery
  Recovery block canceled/removed/missed -> Residual Debt

Delivered Recovery
  terminal for delivered minutes

Residual Debt
  Generate repair -> Planned Recovery or Partial Recovery residual
```

Unresolved debt is:

```text
declared_debt_minutes - delivered_recovery_minutes - active_planned_recovery_minutes
```

### 3.5 Reset-Year State
Reset-year is destructive and explicit.

Required reset behavior:
- cancel or block running generation jobs;
- remove pending draft state;
- mark current active schedule inactive or deleted according to reset implementation;
- clear `active_schedule_version_id`;
- set `school_year_publication_state = UNPUBLISHED`;
- reset or archive approval snapshots used for generation selection;
- preserve audit records unless reset policy explicitly says development data can be wiped.

## 4. Generation Pipeline

### 4.1 API Entry
`POST /api/v1/scheduler/generate`

Request body should not include `mode`.

Optional fields:
- `idempotency_key`;
- `replace_pending_draft`: boolean, required when a pending draft exists and the admin confirms replacement.

### 4.2 Strategy Selection
The orchestrator loads `scheduler_school_year_state`.

Selection:
- `UNPUBLISHED` -> Complete Generation;
- `PUBLISHED` + unresolved explicit debt -> Adaptive Repair;
- `PUBLISHED` + scheduler change version newer than approved -> Adaptive Repair;
- `PUBLISHED` + both triggers -> Adaptive Repair with trigger type `MIXED`;
- `PUBLISHED` + no trigger -> blocked message.

### 4.3 Preflight
Preflight must run before queueing expensive generation.

Required checks:
- tenant context exists;
- active school year exists;
- school timezone exists;
- start date and hard end date exist;
- no preferred/target end date is required or read;
- timetable grid exists;
- classes, subjects, teachers, rooms, room types, assignments, and hour requirements are complete;
- hard end date is not before start date;
- lunch settings are internally consistent;
- theoretical calendar capacity exists;
- room type requirements have compatible room capacity;
- no pending draft unless replacement is confirmed.

Failure messages:
- no operational trigger;
- incomplete configuration;
- no valid capacity;
- stability window blocker;
- resource/hard-end blocker;
- scheduler-change adaptation impossibility.

### 4.4 Snapshot And Fingerprints
Before the Celery job starts solving:
- compute `generation_input_fingerprint`;
- compute `debt_basis_fingerprint` if unresolved debt exists;
- capture `scheduler_state_version`;
- capture `repair_policy_snapshot` for Adaptive Repair;
- store all snapshots on the job and draft.

The job must solve from this immutable snapshot, not live mutable rows.

### 4.5 Complete Generation Pipeline
```text
1. Build annual demand ledger.
2. Build candidate calendar from start date to hard end date.
3. Apply hard-constraint pruning.
4. Compute school complexity score.
5. Select automatic near-future optimization horizon.
6. Optimize near future.
7. Fill far future with capacity-aware bottleneck-first provisional scheduling.
8. Validate full draft.
9. Persist draft blocks, summary, and audit.
```

If no full valid draft is produced within the cap:
- result category is `NO_VALID_OUTPUT`;
- no draft is created;
- active schedule remains unchanged.

### 4.6 Adaptive Repair Pipeline
```text
1. Load active published schedule snapshot.
2. Compute editable_start_date.
3. Freeze past, executed, and protected-window blocks.
4. Compute unresolved debt and/or scheduler-change affected future blocks.
5. Try lowest sufficient recovery/adaptation scope.
6. Escalate only when lower scope cannot resolve the trigger.
7. Validate result against preserved blocks and hard constraints.
8. Persist Complete Success or Partial Recovery draft.
9. If no useful valid draft exists, persist No Valid Output audit only.
```

Adaptive Repair may produce Partial Recovery only for unresolved debt scenarios.

### 4.7 Pending Draft Replacement
If a pending draft exists:
- generation is blocked unless the request explicitly confirms replacement;
- the existing pending draft remains `PENDING` while the replacement generation is queued/running;
- if replacement generation fails, is canceled, times out, or returns No Valid Output, the existing pending draft remains unchanged;
- the existing pending draft becomes `REPLACED` only in the same final transaction that persists the new validated draft as `PENDING`;
- the old draft audit record remains;
- after the final replacement transaction commits, the new draft is the only pending draft.

### 4.8 Transaction Boundaries
Generation job transaction:
- may write job progress;
- may write draft and audit only after final validation;
- when replacing a pending draft, must mark the old draft `REPLACED` and persist the new draft `PENDING` in the same final transaction;
- must not write active schedule blocks.

Approval transaction:
- revalidates draft;
- reconciles active schedule;
- reconciles recovery links;
- updates publication state/version snapshots;
- marks draft approved.

## 5. Algorithm Design

### 5.1 Solver Architecture
Use a hybrid engine:
- exact or CP-SAT optimization for the near future and constrained repair scopes;
- deterministic heuristic scheduling for far-future provisional fill;
- deterministic validation over the full candidate output.

Existing OR-Tools/CP-SAT components may be reused only after removing legacy target-end, fixed rolling-window, manual mode, and raw-churn assumptions.

### 5.2 Hard Constraints
Every candidate output must satisfy:
- no teacher conflict;
- no class conflict;
- no room conflict;
- class/subject/teacher assignment compatibility;
- teacher eligibility for the assigned subject/class;
- required room type;
- `IMPOSSIBLE` teacher availability;
- valid timetable grid;
- blocked dates and calendar events;
- configured minimum lunch protection;
- hard end date;
- demand-ledger satisfaction for Complete Generation;
- declared result category consistency for Adaptive Repair, including residual debt accounting;
- tenant isolation;
- no mutation of past or executed history.

### 5.3 Complete Generation Objective
Lexicographic objective:
1. Full valid schedule before hard end date.
2. Earliest projected completion date.
3. Fair class completion spread when it does not materially delay completion.
4. Workload sanity.
5. Fewer timetable gaps and undesirable soft availability slots.
6. Room/time consistency tie-breakers.

Complete Generation must not reserve artificial future recovery capacity.

### 5.4 Complexity Score
Complexity score should consider:
- active class count;
- active teacher count;
- room and room-type count;
- valid weekly timeslot count;
- candidate count after hard pruning;
- scarce teacher availability;
- scarce room type capacity;
- blocked calendar density;
- total remaining instructional minutes;
- distance from start date to hard end date;
- previous runtime telemetry when available.

The score selects internal horizons and phase budgets. It is never admin-configurable.

### 5.5 Near-Future Optimization
Near-future optimization:
- is deeper than far-future fill;
- uses exact or high-quality search;
- includes all hard constraints;
- optimizes the Complete Generation hierarchy;
- must leave enough wall-clock budget for far-future fill and validation.

Internal example guidance:
- simple school: larger near horizon;
- large/constrained school: smaller near horizon.

These are implementation heuristics, not product guarantees.

### 5.6 Far-Future Provisional Fill
Far-future fill is deterministic, concrete, valid, and capacity-aware.

Ordering:
1. Compute bottleneck score for remaining demand.
2. Place hardest demand first.
3. Use weekly pace as a secondary distribution guide.
4. Preserve workload sanity when possible.
5. Validate after every placement batch.

Bottleneck score inputs:
- teacher scarcity;
- room type scarcity;
- class timetable scarcity;
- subject remaining minutes;
- blocked date compression;
- distance to hard end;
- number of feasible candidate placements.

The far future may be less polished, but it cannot violate hard constraints or consume scarce capacity carelessly.

### 5.7 Adaptive Repair Recovery Ladder
For unresolved explicit debt:
1. Append-only recovery.
2. Affected class recovery.
3. Affected teacher/class recovery.
4. Controlled school-wide repair.
5. Deadline rescue.
6. No Valid Output with explanation.

Each level:
- preserves frozen blocks;
- validates hard constraints;
- records why lower levels failed when escalating.

### 5.8 Scheduler-Change Adaptation Ladder
For scheduler-relevant changes without debt:
1. Same-time resource adaptation.
2. Affected resource/class/teacher refit.
3. Calendar/grid reflow.
4. Controlled school-wide adaptation.
5. No Valid Output with affected-block explanation.

Mixed triggers combine the recovery ladder and adaptation ladder and report both levels when used.

### 5.9 Disruption Score
Adaptive Repair disruption score should include:
- what changed;
- who was affected;
- how soon the change occurs;
- ripple scope;
- stakeholder category: affected, related, unrelated;
- room-only vs date/time changes;
- workload and gap side effects.

Disruption score selects between valid candidates. It never overrides hard constraints.

### 5.10 Partial Recovery
Partial Recovery is Adaptive Repair only.

Optimization:
1. Maximize recovered minutes.
2. Minimize residual debt.
3. Minimize disruption.
4. Preserve earliest feasible completion when possible.

Complete Generation must not produce a partial first schedule draft.

### 5.11 Five-Minute Cap
Every job has a hard cap of 5 minutes.

The 5-minute cap starts when the worker transitions the generation job from `QUEUED` to `RUNNING` and captures the immutable generation snapshot.

Synchronous API preflight before queueing is request-gating preflight. It is outside the 5-minute generation cap, must remain fast, and must not perform expensive solving.

Snapshot verification inside the worker is generation preflight. It is inside the 5-minute cap and must reserve enough time for candidate preparation, solving/fill, final validation, summary creation, and persistence.

Recommended internal budget:
- snapshot verification and candidate preparation: up to 30 seconds;
- near-future optimization or repair attempts: majority of remaining time;
- provisional far-future fill: bounded reserve;
- final validation, summary, and persistence: reserved minimum.

The exact phase allocations belong in implementation constants and may use telemetry, but the total cap is not optional.

## 6. Versioning And Fingerprints

### 6.1 Scheduler State Version
`scheduler_state_version` is scoped to `(organization_id, school_year_id)`.

It increments when a material scheduler-relevant mutation is committed.

Scheduler-relevant entities:
- teacher availability;
- rooms;
- room types;
- timetable grid;
- blocked dates and calendar events;
- lunch rules;
- hard end date;
- class/subject/teacher assignments;
- lesson, module, or hour requirements.

Not standalone triggers:
- repair stability window;
- school name;
- logo;
- admin profile;
- UI preferences;
- non-scheduler text fields.

### 6.2 Version Edge Rules
No-op saves:
- if canonical before/after scheduler inputs are equal, do not increment;
- if equality cannot be proven cheaply, prefer incrementing to preserve safety.

Bulk imports:
- increment once per committed bulk operation;
- store item count and affected entity types in version event metadata.

Deletes:
- deleting active/future-impacting scheduler data increments;
- deleting inactive, unreferenced data may be classified as `INACTIVE_RESOURCE` and not increment.

Inactive resources:
- changes to inactive resources do not increment unless the resource is referenced by future schedule blocks, assignments, requirements, or draft inputs.

Past-only changes:
- do not unlock schedule generation unless they alter active-year future capacity, unresolved debt, or scheduler-relevant configuration.

Pending drafts:
- any version increment after draft creation stales drafts whose generation input fingerprint changes;
- Adaptive Repair drafts also compare trigger basis and repair policy snapshots.

### 6.3 Generation Input Fingerprint
Computed for every draft.

Canonical input should include:
- organization id;
- school year id;
- timezone;
- start date;
- hard end date;
- timetable grid;
- blocked dates and calendar events;
- lunch rules;
- active classes;
- active subjects;
- class-subject hour requirements;
- teacher assignments;
- teacher availability;
- rooms and room types;
- module sequence data used for accounting;
- scheduler state version;
- relevant active schedule snapshot for Adaptive Repair.

Implementation:
- normalize to stable JSON;
- sort arrays by stable identifiers;
- omit volatile fields such as updated timestamps unless semantically relevant;
- hash with SHA-256 or equivalent stable digest.

### 6.4 Debt Basis Fingerprint
Computed when unresolved debt exists.

Canonical input per debt item:
- occurrence id;
- occurrence revision;
- debt status;
- source planned block id;
- class id;
- subject id;
- teacher id when applicable;
- original planned date/timeslot;
- declared debt minutes;
- delivered recovery minutes;
- active planned recovery minutes;
- unresolved debt minutes.

The fingerprint changes if the same occurrence changes revision, minutes, status, subject, teacher, class, or recovery coverage.

### 6.5 Repair Policy Snapshot
Computed for every Adaptive Repair draft.

Fields:
- `repair_stability_window_days`;
- school timezone;
- computed `editable_start_date`;
- any future repair-policy settings added later.

Changing the stability window stales pending Adaptive Repair drafts but does not create a standalone generation trigger.

### 6.6 Approval Snapshot Rules
Complete draft approval requires:
```text
current_generation_input_fingerprint == draft.generation_input_fingerprint
school_year_publication_state == UNPUBLISHED
```

Adaptive Repair draft approval requires:
```text
current_generation_input_fingerprint == draft.generation_input_fingerprint
current_repair_policy_snapshot == draft.repair_policy_snapshot
```

For debt-triggered repair:
```text
current_debt_basis_fingerprint == draft.debt_basis_fingerprint
```

For scheduler-change repair:
```text
current_scheduler_state_version == draft.scheduler_state_version_used
```

For mixed repair, both debt and scheduler state checks must pass.

## 7. Approval And Reconciliation

### 7.1 Approval Preconditions
Approval must verify:
- tenant and school-year ownership;
- draft state is `PENDING`;
- draft is current and valid;
- generation input fingerprint matches;
- hard constraints still pass;
- no active generation job is writing a replacement draft;
- user has admin permission.

### 7.2 Complete Draft Approval
Complete approval:
1. Lock organization/school-year scheduler state.
2. Recompute generation input fingerprint.
3. Validate full draft hard constraints.
4. Promote draft blocks to active schedule version.
5. Set `school_year_publication_state = PUBLISHED`.
6. Set `active_schedule_version_id`.
7. Store `approved_scheduler_state_version`.
8. Mark draft `APPROVED`.
9. Store approval audit.

No active schedule exists before this approval.

### 7.3 Adaptive Repair Approval
Repair approval:
1. Lock organization/school-year scheduler state.
2. Recompute generation input fingerprint, trigger basis, and repair policy snapshot.
3. Compute editable boundary from school timezone and calendar days.
4. Preserve past/executed/protected blocks.
5. Reconcile future blocks on or after editable boundary to equal the target draft blocks.
6. Preserve unchanged block identity where safe.
7. Add/move/replace/remove changed blocks.
8. Reconcile planned recovery links.
9. Validate final active schedule.
10. Update approved scheduler version if scheduler-change trigger was handled.
11. Mark draft `APPROVED`.
12. Store approval audit.

Removed active future blocks are determined by set difference between editable active future blocks and target draft blocks. They must not be represented as target draft blocks.

### 7.4 Recovery Link Reconciliation
Rules:
- unchanged recovery block keeps link;
- moved recovery block updates link to new active block id/date/timeslot;
- replaced recovery block cancels old link and creates replacement link;
- removed recovery block cancels planned link;
- canceled link minutes return to residual debt unless another active planned/delivered recovery covers them.

Approval must not leave links to deleted, stale, or cross-tenant blocks.

### 7.5 Reject
Reject:
- marks draft `REJECTED`;
- clears pending draft pointer;
- leaves active schedule unchanged;
- preserves summary, diff, and details as audit history.

### 7.6 Regenerate
Regenerate:
- requires explicit replacement confirmation;
- creates a new generation job from current state;
- keeps the current pending draft unchanged while the replacement job runs;
- on successful replacement commit, marks the previous draft `REPLACED` and creates the new draft as `PENDING` in the same transaction;
- if replacement generation fails, is canceled, times out, or returns No Valid Output, leaves the previous pending draft unchanged.

### 7.7 Reset-Year
Reset-year:
- requires explicit destructive confirmation;
- cancels/blocks running generation jobs;
- clears active schedule and pending draft state for the school year;
- resets publication state to `UNPUBLISHED`;
- clears active approval snapshots used for strategy selection;
- retains or wipes development data according to implementation choice, but must not leave mixed active/draft state.

## 8. API And Frontend Contracts

### 8.1 API Endpoints
Recommended endpoints:

```text
GET    /api/v1/scheduler/status
POST   /api/v1/scheduler/generate
GET    /api/v1/scheduler/jobs/{job_id}
POST   /api/v1/scheduler/jobs/{job_id}/cancel
GET    /api/v1/scheduler/drafts/current
GET    /api/v1/scheduler/drafts/{draft_id}
GET    /api/v1/scheduler/drafts/{draft_id}/diff
POST   /api/v1/scheduler/drafts/{draft_id}/approve
POST   /api/v1/scheduler/drafts/{draft_id}/reject
POST   /api/v1/scheduler/drafts/{draft_id}/regenerate
POST   /api/v1/scheduler/reset-year
```

The former `/api/v1/schedule/generate` compatibility route is retired. The only
active generation entry point is `/api/v1/scheduler/generate`.

### 8.2 `GET /scheduler/status`
Response:
```json
{
  "school_year_publication_state": "PUBLISHED",
  "pending_draft_id": 123,
  "primary_action": "REVIEW_PENDING_DRAFT",
  "can_generate_new_draft": false,
  "can_regenerate_with_confirmation": true,
  "blocked_reason": null,
  "trigger_type": "MIXED",
  "unresolved_debt_hours": 8,
  "scheduler_state_version": 42,
  "approved_scheduler_state_version": 40
}
```

When `pending_draft_id` is present, the primary UI action is review. Generation is available only as a confirmed regeneration/replacement flow, represented by `can_regenerate_with_confirmation`.

### 8.3 `POST /scheduler/generate`
Request:
```json
{
  "idempotency_key": "optional-client-generated-key",
  "replace_pending_draft": false
}
```

Response:
```json
{
  "job_id": 987,
  "strategy": "ADAPTIVE_REPAIR",
  "trigger_type": "MIXED",
  "status": "QUEUED"
}
```

### 8.4 Draft Summary Response
```json
{
  "draft_id": 123,
  "strategy": "ADAPTIVE_REPAIR",
  "draft_state": "PENDING",
  "result_category": "PARTIAL_RECOVERY",
  "trigger_type": "EXPLICIT_DEBT",
  "recovery_escalation_level": "DEADLINE_RESCUE",
  "adaptation_level": null,
  "projected_completion_date": "2026-06-24",
  "hard_end_date": "2026-07-15",
  "debt_hours_before": 18,
  "debt_hours_recovered": 8,
  "debt_hours_remaining": 10,
  "partial_recovery_blocker_type": "STABILITY_WINDOW",
  "main_blocker_message": "The stability window protects too much of the remaining schedule before the hard end date.",
  "recommended_actions": [
    "Reduce the stability window.",
    "Allow broader future schedule changes.",
    "Generate the schedule again."
  ],
  "changed_blocks": 32,
  "affected_classes": 4,
  "affected_teachers": 3,
  "warnings": [
    "Partial recovery generated."
  ],
  "can_approve": true
}
```

### 8.5 Frontend States
The UI should show:
- Generate Schedule enabled for `UNPUBLISHED`;
- Generate Schedule enabled for `PUBLISHED` only with operational trigger;
- blocked state when no trigger exists;
- pending draft review as the primary action when one exists;
- regenerate confirmation when replacing a draft;
- stale/invalid draft warning when approval is blocked;
- summary approval actions for valid current drafts;
- optional detailed diff.

### 8.6 Required User Messages
No trigger:
```text
No schedule generation needed.

There are no declared missed hours to recover and no schedule-relevant changes since the last approved schedule.
```

Partial recovery:
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

Scheduler-change impossibility:
```text
Schedule adaptation could not be generated.

24 future blocks are affected by the changed schedule conditions.

Main blocker:
The changed calendar, timetable grid, or blocked dates leave no valid placement for affected future blocks.

Recommended actions:
- Adjust calendar or timetable availability.
- Add compatible resources or availability.
- Generate the schedule again.
```

Stale draft:
```text
This draft is no longer current.

Schedule conditions changed after it was generated. Regenerate the draft to continue.
```

## 9. Reliability, Concurrency, And Security

### 9.1 Locks
Use organization/school-year scoped locks for:
- generation start;
- pending draft replacement;
- approval;
- reset-year.

Implementation options:
- database advisory locks;
- transactional row lock on `scheduler_school_year_state`;
- queue-level uniqueness plus database validation.

Approval must always use database transaction locks, even if queue uniqueness exists.

### 9.2 Idempotency
Generation requests should support `idempotency_key`.

Same key and same org/school-year:
- returns existing queued/running job if still active;
- returns existing successful draft if completed;
- rejects conflicting payloads.

Approval/reject/regenerate endpoints should also be idempotent when safe.

### 9.3 Atomicity
Generation:
- no partial draft visible;
- no active schedule mutation;
- failed/canceled jobs leave active state unchanged.

Approval:
- one transaction;
- all schedule block and recovery link changes commit together;
- rollback on any validation failure.

### 9.4 Tenant Isolation
Every query must include `organization_id`.

Every persisted row must carry `organization_id`.

Approval must reject if any draft block, active block, occurrence, recovery link, teacher, class, room, or schedule state belongs to another tenant.

### 9.5 Cancellation And Timeout
Celery generation job must check cancellation:
- before solving;
- between solver phases;
- before draft persistence.

Timeout:
- hard stop 5 minutes after the worker marks the job `RUNNING` and captures the immutable generation snapshot;
- Complete Generation timeout without full valid draft -> No Valid Output;
- Adaptive Repair timeout may produce a validated partial draft only if the engine completed validation before deadline.

### 9.6 Timezone
Use the school's configured timezone for:
- `today`;
- editable boundary;
- date comparisons;
- calendar-day stability window.

Store dates as dates and timestamps with timezone-aware UTC instants.

### 9.7 Observability
Required logs/metrics:
- generation duration;
- phase durations;
- strategy;
- trigger type;
- result category;
- changed block count;
- residual debt;
- affected future block count;
- validation failures;
- stale approval attempts;
- timeout/cancel counts.

Logs may expose technical solver terms. Admin summaries should not.

### 9.8 Permissions
Only admin-equivalent roles may:
- generate;
- approve;
- reject;
- regenerate;
- reset year.

Teachers may contribute availability and occurrence data but do not choose generation strategy.

## 10. Testing Strategy

### 10.1 Test Layers
Unit tests:
- fingerprint computation;
- debt lifecycle;
- scheduler state version increments;
- editable boundary calculation;
- hard-constraint validation;
- bottleneck scoring;
- draft state transitions.

Integration tests:
- generate Complete draft;
- approve Complete draft;
- stale Complete draft after config change;
- generate Adaptive Repair from debt;
- generate Adaptive Repair from scheduler change;
- mixed trigger draft;
- partial recovery;
- scheduler-change No Valid Output;
- replacement generation failure/cancel/timeout/No Valid Output preserves previous pending draft;
- recovery link reconciliation;
- reset-year.

End-to-end tests:
- admin generates first schedule;
- admin approves;
- teacher absence creates unresolved debt;
- admin generates repair;
- admin approves partial/complete repair;
- planned recovery suppresses repeat trigger;
- missed recovery reopens residual debt.

### 10.2 Required Scenario Matrix
At minimum:
1. No published schedule -> Complete draft.
2. Complete draft stale after teacher availability change.
3. Complete draft approval publishes first schedule.
4. Published schedule and no trigger -> generation blocked.
5. GAP creates unresolved debt -> repair enabled.
6. Planned recovery covers debt -> repeat generation blocked.
7. SUBSTITUTED creates original lesson debt and operational substitute block remains independent.
8. Scheduler-relevant room deletion -> scheduler-change repair.
9. Stability-window-only change without debt -> generation blocked.
10. Mixed debt plus scheduler change -> one mixed draft.
11. Frozen window 0 permits today-forward edits but not past/executed edits.
12. Partial Recovery reports one approved blocker message.
13. Scheduler-change impossibility reports affected-block message.
14. Rejected draft preserves audit details.
15. Regenerate replaces exactly one pending draft.
16. Replacement generation fails, cancels, times out, or returns No Valid Output and the previous pending draft remains pending.
17. Approval fails after fingerprint mismatch.
18. Tenant isolation rejects cross-tenant draft approval.
19. Reset-year returns publication state to `UNPUBLISHED`.

### 10.3 Legacy Regression Tests To Remove Or Rewrite
Rewrite tests that assert:
- request `mode` defaults to `full`;
- repair mode is user-selected;
- target end date drift is an objective;
- fixed 8-week rolling horizon is product behavior;
- rejected drafts are permanently deleted;
- generation writes directly to active schedule;
- pending/unregistered lessons create automatic debt.

### 10.4 Acceptance Gate
Implementation is complete only when:
- all PRD acceptance areas have tests or direct verification;
- no legacy scheduler behavior contradicts the PRD;
- docs and API contracts expose only the new baseline;
- failed/canceled/stale workflows are covered;
- large-school scenarios remain under the 5-minute cap or return honest No Valid Output/Partial Recovery behavior.
