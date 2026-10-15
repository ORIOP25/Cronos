# Cronos Scheduler v1 Technical Specification (Revision 2)

Updated: 14 October 2026.

## Purpose

This specification defines scheduler contracts, product decisions, mathematical rules, persistence, and verification.
Code, configuration, migrations, and tests are the source of truth.
Historical execution plans remain in Git history. This document does not certify an external deployment.

## Intended Reader

This document targets scheduler engineers, reviewers, and operators.

## Prerequisites

Read the [Glossary](../00_getting_started/GLOSSARY.md), [Data Model](../01_system_architecture/DATA_MODEL.md), and [Testing and CI](../08_security_quality/TESTING_AND_CI.md).

## What the System Does

The scheduler generates complete proposals and repairs published schedules.
An administrator approves each proposal before publication. A partial candidate never represents success.
The engine preserves execution, curricular minutes, debt, and protected physical positions.

### Binding product decisions

| ID | Decision |
| :--- | :--- |
| D01 | Use a new baseline without compatibility with the previous generator. |
| D02 | Existing test data can be removed before real school use. |
| D03 | Run one schedule job globally. Queue other requests. |
| D04 | A job can use multiple internal CP-SAT workers. Compare 1, 2, 4, and 8 workers by manual measurement when tuning is required. |
| D05 | There is no fixed p95 target. Previous 15-minute and two-minute values are not targets. |
| D06 | Measure performance by size and difficulty family. Initially, p95 is an observed result. |
| D07 | Search stops through proof, sufficient certified proximity, or low estimated additional return. A p95 never stops search. |
| D08 | Apply a separate safety timeout. Interruption never proves infeasibility. |
| D09 | The school defines the start, preferred completion, and absolute end dates. |
| D10 | Initial generation must finish by the preferred date and seek earlier completion. |
| D11 | Adaptive recovery progressively protects available margin. After the preferred date, reducing excess takes priority over editable-future disruption. |
| D12 | Improve the latest class completions first. Earlier classes can release capacity to help later classes. |
| D13 | Do not delay a class merely to equalize dates without helping another class. |
| D14 | The school defines the stability window. Count days present in the weekly grid, not calendar days. |
| D15 | Protect all physical changes inside the window, including recovery insertions. Preserve past lessons and execution. |
| D16 | A module is not a permanent identity of a future lesson. It follows the subject's minute sequence. |
| D17 | One lesson can finish a module and start subsequent modules. Exact minute credits never overlap. |
| D18 | Recalculate future modular projection automatically, including inside the window. Never rewrite execution evidence. |
| D19 | The grid defines maximum capacity. The engine adds no implicit daily, weekly, or consecutive-load limit; it applies only the presence rules the school defines per teacher. |
| D20 | Mandatory unavailability excludes periods. An unfavorable preference still permits placement. |
| D21 | Between equivalent higher-priority solutions, reduce teacher gaps first, then class gaps. |
| D22 | The school assigns each class subject's teacher. The solver does not allocate teaching service. |
| D23 | An administrator always starts generation. Events never start the solver automatically. |
| D24 | Allow initial generation, justified updates, retries without a complete result, or eligible periodic renewal. |
| D25 | Offer manual optimization after 28 calendar days without a completed generation. |
| D26 | A validated, persisted complete generation resets the clock. Failure, cancellation, and queue residence do not. |
| D27 | Explain proven infeasibility and suggest basic actions. The administrator changes inputs or conditions. |
| D28 | Manual progress corrections recalculate demand and can justify repair. The solver never invents execution. |
| D29 | Use school language in the interface. Keep CP-SAT, scopes, fingerprints, workers, and mathematical gaps in technical evidence. |
| D30 | Preserve proposals and administrative approval. Generation never publishes automatically. |
| D31 | Develop and verify locally first. Verify Railway and Cloudflare after a solid local release candidate. |

Out of scope: simultaneous schedule solves, automatic teacher selection, automatic publication, and compatibility with old database schemas.
Do not introduce new microservices, another broker, another solver, or machine learning without concrete evidence.
Do not invent pedagogical load limits or certify administrative execution decisions as legally correct.
Retain FastAPI, SQLAlchemy, PostgreSQL, Celery, Redis, React, and OR-Tools. Lockfiles define dependency versions.

## Why the Behavior Exists

Complete proposals preserve accounting and make publication reviewable.
Independent validation prevents solver mistakes from becoming published school data.
Explicit priorities prevent aesthetic improvements from delaying curricular completion.
The stability window limits disruption while preserving executed history.

## Components and Ownership

The implementation lives in `backend/app/scheduler/`.

| Layer | Sources and responsibilities |
| :--- | :--- |
| Composition | `composition.py`: `generate_schedule` and `repair_published_schedule` |
| Application | `contracts.py`, `generation.py`, `recovery.py`, `publishing.py`: use cases, ports, and result contracts |
| Domain input | `candidate.py`, `calendar.py`, `capacity.py`, `constraint_policy.py`, `grid_versions.py`, `lesson_time.py` |
| Domain accounting | `demand.py`, `debt.py`, `projection.py`: execution, debt, and modular projection |
| Domain verification | `candidate_validation.py`, `diagnostics.py`, `oracle.py`: validation, capacity evidence, and tiny-instance test oracle |
| Domain policy | `quality.py`, `recovery.py`, `eligibility.py`, `results.py`, `stop.py`, `timetable.py` |
| Domain serialization | `serialization.py`: the only canonical JSON serializer, with the snapshot digest |
| Persistence | `infrastructure/models.py`, `progress.py`, `proposals.py`, `operations.py`, `occurrences.py`, `queries.py` (all operations use the v1 tables) |
| Solver | `infrastructure/annual_model.py`, `constructive.py`, `placement_model.py`, `recovery_construction.py`, `search.py` |
| Runtime | `infrastructure/snapshot.py`, `jobs.py`, `diagnostics.py`, `curriculum.py`, `task_dispatcher.py` |
| Test fixtures | `lab/fixtures.py`, `scale.py`, `annual.py`, `recovery.py`, `typology.py` |

Allowed dependencies:

```text
API/Celery -> composition -> application -> domain
infrastructure --------------------------> domain
```

The domain receives dates and instants explicitly. It never reads clocks, databases, or environment variables.
Use immutable dataclasses, enums, integers, and ordered collections.
Domain contracts contain no ORM models, SQLAlchemy sessions, CP-SAT objects, or untyped `Any` values.
The validator examines materialized blocks independently of solver variables.
The enumerative oracle is a test reference, never a production fallback.
Only the v1 engine runs.

## Data or Request Flow

1. An administrator submits an idempotent generation request.
2. The backend validates eligibility and records the snapshot revisions.
3. The global executor claims the next eligible request.
4. The engine constructs candidates and recalculates quality.
5. Independent validation checks the complete candidate.
6. The backend persists the proposal atomically.
7. An administrator approves or rejects it.
8. Approval revalidates current inputs before activating the version.
9. Sumários and occurrences append accounting evidence.

### Immutable vocabulary

| Contract | Essential fields and meaning |
| :--- | :--- |
| `Assignment` | Class, subject, assigned teacher, eligible rooms, mandatory constraints |
| `ModuleRequirement` | Identifier, stable order, positive minutes |
| `Period` | School date, local start/end, UTC instant, positive physical duration |
| `ScheduledLesson` | Stable identity, assignment, period, room, planned curricular minutes |
| `ModuleSlice` | Lesson, module, curricular offset, minutes; several slices can belong to one lesson |
| `ExecutionEntry` | Execution or correction, signed minutes, origin, revision, author, reason |
| `DebtClaim` | Origin of missing minutes; not additional demand |
| `RecoveryAllocation` | Reservation of future lesson minutes against debt |
| `PlanningSnapshot` | Strategy, dates, timezone, grid, assignments, execution, exclusions, protected lessons, reservations, open debt |
| `CandidateSchedule` | Complete future lessons, preserved identities, assigned rooms |
| `ValidationReport` | Validity, structured violations, recalculated totals |
| `QualityVector` | Ordered components, auxiliary metrics, policy version |
| `SearchEvidence` | Objective, scope, incumbent, bound, tolerance, proven/reused stages, termination reason |

Identifiers retain their native types. Internal dense indices map explicitly to original identifiers.
New lesson identities never reuse published lesson identifiers.
Curricular minutes and durations are integers. Hour conservation never uses `float`.
School dates use the school timezone. Audit instants use timezone-aware UTC.
Search durations use a monotonic clock. Physical intervals are half-open `[start, end)`.
Reject ambiguous or nonexistent local times during timezone transitions. Never silently repair invalid periods.

## Contracts and Invariants

### Curricular conservation

For each assignment `a = (class, subject)`:

```text
Q[a] = sum of required module minutes
E[a] = effective execution credits and audited corrections
R[a] = Q[a] - E[a]

0 <= E[a] <= Q[a]
sum(future lesson credit_minutes for a) = R[a]
0 < credit_minutes[lesson] <= physical_duration[lesson]
```

Reject corrections outside these limits. Do not hide errors with `max(0, R)`.
Execution replaces planned credit once. A pending proposal changes neither execution nor effective debt.
Repeated events cannot add duplicate credit.
The formula `demand = Q - E + debt` is prohibited. Debt identifies minutes already included in `R`.

### Exact modular projection

Represent modules as consecutive curricular-minute intervals.
After effective execution, process future lessons by date, start, and stable identity.
Allocate credits across remaining module intervals. Do not add module-position variables to the temporal solver.

```text
M1 = 75 minutes; M2 = 75 minutes; periods = 50 minutes
Lesson 1: M1 50
Lesson 2: M1 25 + M2 25
Lesson 3: M2 50
```

Cancelling Tuesday and recovering Thursday can change Wednesday's projected module without moving Wednesday.
That change is allowed inside the stability window. Diffs separate physical changes from curricular projection updates.
Late Sumários and retroactive corrections never overwrite original execution evidence.

### Partial credit and variable duration

A lesson with 30 curricular minutes in a 50-minute period occupies all 50 physical minutes.
The remaining 20 minutes cannot host another subject, class, or teacher.
Do not round modules individually. Initial generation permits only the final lesson of each assignment to have partial credit.
Recovery preserves protected lesson credits. Preserve a published partial lesson when stability requires it.
Report conflicts when protected credits exceed `R`. Never delete execution or silently change the window.
Do not assume universal 50-minute periods. Aggregate models distinguish durations; detailed placement checks exact totals.

### Debt reconciliation

```text
open = created + revisions - execution_settlements - correction_settlements
0 <= reserved_in_active_schedule <= open
sum(open assignment debt) <= R[assignment]
```

One lesson can settle several debts. One debt can span several lessons.
Recovery allocations never exceed the lesson's curricular credit.
Reservations belong to a version. Proposals keep separate reservations until approval.
Cancelling recovery releases its reservation. Existing debt minutes never become new duplicate debt.
Positive corrections settle oldest debt first by origin date and identifier, unless an explicit origin is supplied.
Negative corrections reverse linked settlements when that relationship exists.
A substitution credits only the subject actually taught.
Prevent duplicate credit through Sumário, substitution, and recovery for the same execution.

### Calendar and stability

Validate `start_date <= preferred_end_date <= hard_end_date`.
CompleteGeneration uses the preferred date as a mandatory limit.
AdaptiveRecovery uses the absolute limit and penalizes excess beyond the preference.
`grid_dates` contains dates whose weekday exists in the school grid.
Holidays block placement but do not change how grid days count toward stability.
Only a published ACTIVE version creates protected dates. Initial generation has no protected dates.

```text
protected_dates = first N grid_dates from school_today, inclusive
editable_from = first grid_date after those N dates
```

With `N=0`, only unstarted periods are editable. Always preserve execution and past lessons.
Protect insertions, deletions, dates, periods, teachers, rooms, subjects, and confirmed physical/curricular credit.
Future modular projection is the explicit exception.
An occurrence can state that a protected lesson did not happen; it cannot authorize rewriting that past position.
Approval recalculates the boundary. A proposal can become invalid while awaiting approval.

### Persistence and revisions

The Alembic migration chain starts at the frozen baseline `0001_scheduler_v1_baseline`, a PostgreSQL 18 SQL schema dump. The `backend/alembic/versions/` directory owns the current revisions, and new migrations stack linearly on the baseline.
The [Data Model](../01_system_architecture/DATA_MODEL.md) maps retained lifecycle, operational, and v1 tables.
Tenant foreign keys include organization identifiers where required.
Force RLS on school tables and use an explicit organization context with a role that cannot bypass RLS.
Enforce origin/revision idempotency, one active job, one current proposal, and one active version per school year.
Lesson identities are unique within a version. Durations and credits are positive; credit cannot exceed physical duration.
Published class, teacher, and room intervals cannot overlap.

`input_revision` changes whenever snapshot validity changes, including normal execution.
`planning_revision` changes for meaningful inputs that can justify manual generation.
School commands lock the state row first and update data and revisions in one transaction.
Semantic no-ops do not advance planning revision. Normal execution creates no regeneration reason.
Snapshot serialization orders collections and includes mathematically relevant inputs.
Presentation names without mathematical effects are excluded. The canonical representation has a SHA-256 digest.
Requests retain the observed revisions and active version. Queue execution checks freshness again.

### Joint eligibility and exclusivity

```text
A = class/subject/teacher assignments
P = concrete calendar periods
R = concrete rooms
K[a,p] = eligible rooms for assignment a in period p
d[p] = physical period duration
x[a,p] in {0,1} = assignment placed in period
```

`capacity.eligible_periods` supplies prevalidation, annual planning, placement, and oracle eligibility.
Eligibility intersects dates, timezone, grid weekdays, mandatory availability, rooms, and fixed-resource occupancy.
Unfavorable preferences add cost without excluding a placement.
New lessons cannot start before the final protected lesson ends.
The validator independently recomputes eligibility. Never build the full annual assignment-period-room Cartesian product.
Do not invent four-lesson daily, three-consecutive, or two-recovery limits.

Each active class and teacher requires one continuous lunch interval in the configured window.
Separate breaks cannot combine to satisfy lunch.
Partial lunch configuration produces `LUNCH_CONFIGURATION_INCOMPLETE`.
Independent validation reports `LUNCH_BREAK_VIOLATION`.
A teacher whose presence rule dispenses the lunch break is exempt from the lunch check; classes always keep the school lunch rule.

### Teacher presence rules

`domain/teacher_presence.py` holds the pure rules; `domain/candidate.py` carries
`TeacherPresenceRule` and `PlanningSnapshot.teacher_presence`.
The snapshot keeps only rules that differ from the default (lunch required, no
minimum), ordered by teacher id.
With a required lunch and a configured window the day splits at a free lunch
choice into a morning and an afternoon presence; without lunch the whole day is
one presence.
Each presence has zero hours or at least the teacher's minimum, and its gap is
the sum of empty grid blocks between its first and last lesson, never the
wall-clock breaks.
A presence with only protected lessons is exempt; a presence with at least one
editable lesson counts protected and editable lessons together.
A joint lesson counts once for its teacher.
Independent validation reports `TEACHER_PRESENCE_VIOLATION` with
`resource_type="teacher"`; `VALIDATOR_VERSION` is `v6`.
The placement model imports `lunch_options` from the pure module, and the
snapshot loader uses the same active, teaching, assigned teacher filter as the
readiness fingerprint, so an unassigned teacher's rule changes no digest.
A teacher dispensed from lunch may teach inside the school window in all three
routes: the exact CP-SAT placement (`placement_model._add_lunch`), the fast
construction (`constructive.construct_schedule`) and the adaptive recovery
(`recovery_construction.free_rooms`) skip that teacher's lunch option while
every class keeps its own mandatory break. A teacher without an exception keeps
the previous behaviour.

The exact model enforces the minimum and the gap per presence (`placement_model._add_teacher_presence`).
Each presence has zero or at least the minimum physical minutes, and its gap is the sum of empty grid-block durations between its first and last lesson.
A required lunch designates exactly one free option per teacher and day; the designated choice splits the day into a morning and an afternoon presence.
A dispensed teacher, or a school without a configured window, uses the whole day as one presence.
A presence with only protected lessons is exempt; a presence with any editable lesson counts protected and editable minutes, and a substitute protected lesson counts for its own teacher.
The window cache salt includes every presence rule, so a changed rule never reuses a proven window.
The annual plan keeps a teacher's editable weekly load at zero or at least the minimum, except weeks that hold a protected lesson of that teacher (T05).

```text
sum(selected and fixed occupancy for a resource over overlapping periods) <= 1
```

Compact exclusivity groups equal intervals and uses `AddAtMostOne`.
Do not merge groups linked only by transitive overlap. The ends of an overlap chain must remain selectable.

### Teaching units, joint precedence and diagnosis

`domain/teaching_units.py` `build_teaching_units` turns class assignments into teaching units.
`A:{assignment}` is an assignment without a joint group; `S:{assignment}:{module}` is a maximal separate segment;
`J:{group}:{module}` is a shared joint segment; `D:{assignment}:{module}` is a per-class deficit segment.
Keys use module ids, never positions.
A joint module credits every member class with the joint progress (the largest executed minutes).
A class behind gets a `D` unit whose per-module requirement is that joint progress.
Unit identifiers are stable inside a snapshot: the assignment id for `A`, and consecutive ids above the largest assignment id in key order for `S`, `J` and `D`.

Per class the stages are `S0, {J1,D1}, S1, {J2,D2}, ..., Sn`.
Each remaining unit of a stage precedes every remaining unit of the next stage, and `Jk` and `Dk` never precede each other.
A unit with no remaining minutes is skipped and the chain continues.
Construction and recovery only start a unit after its predecessors finish and the last predecessor lesson ends before the period.
A `D` unit is an ordinary residual unit; it competes on the same progress fraction every open debt uses and needs no extra snapshot metadata or `teaching_unit_key`.

A single joint unit left without any eligible shared period is a proven isolation.
`domain/diagnostics.py` reports `JOINT_NO_COMMON_TIME` with the classes and the subject.
Complete generation returns `INFEASIBLE` carrying that code on the result stop reason and the diagnostic message; the search outcome uses the same message.
A general deficit keeps `INSUFFICIENT_INTERSECTION`; a cancellation or interrupted search is never relabelled as joint.
`lab/typology.py` `build_joint_typology_fixture` builds the joint family (general subjects shared, technical subjects separate) for the 48-class pilot.

### Teacher presence preflight and failure diagnosis

Before generation, `services/preflight_service.py` blocks each teacher whose presence minimum cannot fit any visible day.
The pure check `domain/teacher_presence.py` `teacher_can_have_presence` uses the visible grid and the teacher's `Impossible` blocks: a day is feasible when a contiguous span of possible blocks reaches the minimum with the `Impossible` holes inside the maximum gap and, with a required lunch, the span stays on one side of a free lunch option.
The blocker is `TEACHER_PRESENCE_IMPOSSIBLE`, names the teacher and deep-links to `/members?teacher_id={id}&panel=availability`. A stored lunch window that violates its own invariants is an explicit `INVALID_LUNCH_RULE` blocker, never silently treated as no lunch.

A generation or repair that ends without a schedule may have been blocked by a teacher presence rule, but that is never demonstrated.
`domain/diagnostics.py` `diagnose_teacher_presence_rules` returns one `TEACHER_PRESENCE_RULES` diagnosis of kind `ESTIMATE` with `affected_teacher_ids`, naming only the teachers that have a minimum.
`generate_complete` and `repair_schedule` add it to every no-candidate terminal outcome (`INFEASIBLE`, `FAILED`, `INCONCLUSIVE`), never to `CANCELLED` or `INVALID_INPUT`.
`application/publishing.py` `diagnostics_summary` serializes `affected_teacher_ids`, and `infrastructure/queries.py` `_job_diagnostics` returns one row per named teacher even without a class; a teacher deleted after the failure keeps its id and no name.
`infrastructure/jobs.py` stores diagnostics for `INFEASIBLE`, `FAILED` and `INCONCLUSIVE`, and the frontend `GenerationStatusPanel` shows the presence advisory alongside any primary proven diagnosis.

### Exact credits and annual quotas

Subtract protected credits before planning each editable assignment residual.
For a positive residual, select exactly one final placement:

```text
l[a,p] in {0,1}; l[a,p] <= x[a,p]; sum_p l[a,p] = 1
u[a,p] in [0, d[p]-1]; u[a,p] <= (d[p]-1) * l[a,p]
credit[a,p] = d[p] * x[a,p] - u[a,p]
sum_p credit[a,p] = editable_residual[a]
```

No selected placement follows the final placement. All variables are zero when residual demand is zero.
Protected credits remain constant. Calculate modular projection after materialization.
For annual week/duration quotas:

```text
q[a,w,d] = count of periods of duration d in week w
f[a,w,d] = group containing the final placement
q >= f; sum f = 1; 0 <= u[a,w,d] <= (d-1)*f[a,w,d]
sum(w,d)(d*q[a,w,d] - u[a,w,d]) = editable_residual[a]
no positive quota after the selected final week
```

Weekly capacities subtract fixed occupancy for classes, teachers, and eligible room sets.
Enough weekly capacity does not prove joint period feasibility. Detailed placement certifies the quota distribution.
An earliest-week greedy hint seeds search without proving detailed feasibility.
Chronological construction prioritizes less advanced classes through progress fractions and `started_classes`.
The annual master minimizes the latest completion week, then waste.
Incumbent pruning permits the same completion week so later quality components can improve.
Keep the relaxed bound separately from the incumbent.

### Valid feedback and room allocation

Only proven placement infeasibility creates a no-good.
The cut describes the complete excluded combination: positive counts, conditional zero counts, final group, and waste.
Timeout, partial solutions, and failed heuristic matching never justify cuts.
Reopen earlier arbitrary choices or include their conditions explicitly in the cut.
Discard invalid cuts when inputs change. Reopen windows; never permanently freeze arbitrary window choices.
Record finite feedback rounds. Tiny enumerated instances remain the exact test reference.

Rooms are equivalent only when capacity, equipment, reservations, and restrictions produce the same eligibility.
After temporal placement, solve room assignment globally with positions fixed:

```text
choice[(lesson, room)] in {0,1}
sum_room choice = 1 for each lesson with multiple eligible rooms
sum(room occupancy over overlapping periods, including fixed lessons) <= 1
```

Optimize room preferences before excess continuity changes per class/subject.
The room stage is certified only when the final change count is zero.
Return unmatched positions as a temporal conflict. Reopen same-week positions only for strict full-vector improvement.
Single-window mode optimizes continuity inside that window. Validate concrete rooms before accepting completeness.

### Quality priorities, stage evidence, and caching

`C[c]` is the final date required to complete a class. Include relevant execution completion.
An incomplete class has no invented completion date. Sort dates descending as `C↓`.
Measure days from a common origin, never week numbers across year boundaries.
Gaps count unused school minutes between a resource's first and last daily lessons, excluding lunch and nonexistent grid periods.
Teacher gaps precede class gaps. Mandatory unavailability is not a preference violation.
`measure_initial_quality` recalculates metrics independently of the solver.
Progress metrics include `minimum_class_progress_per_mille` and `class_progress_spread_per_mille`.

Initial generation minimizes lexicographically:

```text
(C↓, teacher_gap_minutes, class_gap_minutes, preference_cost, room_change_cost)
```

Completion threshold counts implement the sorted vector:

```text
count_ge[v] = number of classes with completion_day >= v
```

Minimize thresholds from highest to lowest. Tests compare this with the enumerative oracle across seeds.
Never replace the completion vector with sums or averages. Do not use oversized weights to imitate lexicography.
Freeze the achieved value after each stage.
`OPTIMAL` certifies a stage; a feasible heuristic value remains uncertified.
The certified prefix consists only of consecutive proven stages. `SAFETY` removes window stage certification.

Solve windows latest first. Reserve room-finalization time and distribute remaining time across pending windows.
Feasibility presolve has its own limit. Proven infeasibility feeds the master without running quality stages.
Budgets include construction and finalization. Omitted stages never receive certificates.
Cache only windows with every stage `OPTIMAL`.
Cache keys include assignment scopes, completing classes, protected dates, and continuity mode.
Reused stages are marked as reused. Interrupted windows are never cached as optimal.
Protected data, published baseline, or editable-boundary changes invalidate the key.

### Adaptive quality

Let `O[c] = max(0, C[c] - preferred_end_date)` and sort it descending as `O↓`.
Minimize excess before disruption. No objective can cross the absolute date limit.
Within equal excess vectors, use an increasing convex function `g` up to the preferred date.
Physical disruption compares against the published snapshot reference:

```text
D = sum(change_type_cost * urgency * repeated_change_cost for each lesson)
B[i] = g(min(C↓[i], preferred_end_date)) + lambda * D
QualityAdaptive = (O↓, B[1], ..., B[n], C↓, D,
                   teacher_gaps, class_gaps, preferences, rooms)
```

Count insertions, deletions, moves, and room changes once per transformation.
Urgency increases near the editable boundary. Repeated-change cost uses audited history.
Modular-only changes do not increase physical disruption.
`lambda` is positive; `g` has integer coefficients and strictly positive slopes.
`adaptive_quality_vector` implements an experimental comparator. Coefficients require explicit measured calibration, not arbitrary production claims.
Record the quality policy version, coefficients, and ordering examples with measurements.
Policy changes require corresponding specification and oracle updates.
Measure incremental disruption against the previous version and accumulated disruption against the first approval.

### Generation and recovery algorithms

CompleteGeneration normalizes inputs, compiles demand, and applies aggregate capacity prechecks.
Annual quotas feed detailed window placement, room matching, full-vector comparison, and independent validation.
Materialization must match annual quotas exactly.
Generation also evaluates recoverability after cancellation of the last planned lesson.
Preserve incumbents outside solver objects and record stage scopes, bounds, certificates, and termination reasons.
Finite round exhaustion and safety interruption remain honest termination reasons.

With `SCHEDULER_V1_STOP_AT_FIRST_COMPLETE=True`, recovery starts with budgeted constructive search.
It compares retaining valid published positions with a dense reconstruction of editable future lessons.
Both candidates use the global evaluator and independent validation. Neither receives an optimality certificate.
If both constructions fail, placement search uses the remaining budget and stops at the first complete candidate.
If placement finds no complete candidate, recovery returns `INCONCLUSIVE`, never proven infeasibility.
With the setting false, master/detail recovery remains available.

Recovery respects calendars, lunch, availability, room eligibility, preferences, and corrected execution.
Preserve physical protected positions while recalculating future module slices.
Hard availability that overlaps a protected position produces a proven conflict before search.
The administrator reviews availability or the protection window; recovery never relaxes either rule automatically.
`COMPLETED` and `OCCURRENCE` logs remain operational history between versions.
An unperformed lesson leaves uncovered demand and never contributes protected planned credit.
Manual corrections do not classify unlogged future lessons as executed history.
New debt reservations belong after the stability window. Previously frozen reservations remain attached.
Execution settles debt; proposals only reserve recovery.

Master/detail recovery expands affected neighborhoods through class, teacher, room, and period conflicts.
Allow distant-week chains and capacity transfers between classes.
Exterior lessons remain fixed occupancy and contribute to global quality.
Neighborhood number and attempt order never become product priorities.
Reopened windows, exact no-goods, certified stages, budgets, pruning, room matching, and cache keys retain the generation rules.
Neighborhood infeasibility does not prove global infeasibility. Only exhaustive admissible search can support that conclusion.

### Search outcomes and stopping

Keep feasibility, quality, and termination evidence separate.
`INFEASIBLE` requires a proof within its declared scope. Interrupted search without a complete result is inconclusive.
A complete validated candidate can be publishable without an optimality certificate.
The configured first-complete mode stops at a complete candidate; it never claims globally optimal quality.
Alternative stop policies distinguish proof, certified proximity, estimated marginal return, and safety interruption.
Safety limits include construction, solve, memory, and finalization.
Empirical marginal-return decisions require comparable measurements and uncertainty records.
Uncalibrated families require conservative exploration. No p95 enters a stopping rule.

Capacity prechecks can prove resource deficits and report affected classes and minimum missing minutes.
Relaxations provide lower bounds, not exact deficits. Conflict sets need not be minimal.

```json
{
  "code": "INSUFFICIENT_TEACHER_CAPACITY",
  "evidence_kind": "PROVEN_LOWER_BOUND",
  "minimum_missing_minutes": 100,
  "affected_class_ids": [17, 18],
  "suggestions": ["REVIEW_AVAILABILITY", "REVIEW_END_DATE", "REVIEW_RECORDED_PROGRESS"]
}
```

Only report supported quantities. Reviewing recorded progress means correcting actual recognized work, never inventing execution.
Do not promise that later dates resolve room or teacher conflicts without validating that hypothesis.

### Global queue and execution

Use one solver service replica, Celery concurrency one, and prefetch one.
Internal CP-SAT workers do not create simultaneous jobs. Do not solve windows concurrently without measured justification.
The database stores FIFO order. Celery messages wake the executor; the database selects the next eligible request.
Global queue access reads only required operational metadata. Load school data after establishing its RLS organization context.
Never disable RLS globally. Duplicate transport delivery cannot create another execution.

A dedicated PostgreSQL connection holds the global advisory lock during execution.
Do not retain an open write transaction during solving.
Each claim increments `attempt_token`; result writes verify that token.
Heartbeat and cancellation use a separate connection. Process supervision covers construction and finalization stalls.
Recovery cannot depend on a terminated process writing its own final state.
Loss of the lock connection requires solver termination. A token fences writes but does not prove old CPU work stopped.
Confirm previous process termination before another solve. Deployments must prevent solver replica overlap.
Reconcile abandoned jobs before consuming new requests. Failed dispatch remains recoverable.
Re-delivering an authorized request is allowed; generating without administrative action is not.

### Proposal finalization and approval

Finalization:

1. Validate the candidate outside the write transaction.
2. Lock school state, then job.
3. Check revisions, base version, attempt token, and cancellation.
4. Revalidate current temporal boundaries and affected invariants.
5. Persist proposal, lessons, slices, reservations, diff, and evidence.
6. Consume only reasons covered by the snapshot.
7. Update the clock and finish the job atomically.

Cancellation before commit prevents a new proposal.
After confirmed success, cancelling the job has no effect. Rejecting the proposal is a separate action.

Approval:

1. Validate administrator and organization.
2. Lock school state, then proposal.
3. Check pending status, base version, and current revisions.
4. Recalculate demand, debt, calendar, and stability.
5. Independently validate the complete result.
6. Activate the version and reconcile recovery reservations.
7. Append audit evidence and commit atomically.

Never run the solver inside approval. Conflicts roll back the full transaction.
Idempotent repeated approval returns the existing result. Readers never observe mixed old and new schedules.

### API and interface

The server chooses generation or recovery according to whether a published version exists.
Routes under `/api/v1/scheduler`:

| Operation | Contract |
| :--- | :--- |
| `GET /status` | State, eligibility, reasons, current proposal, dates; read-only |
| `POST /generate` | Manual idempotent request; job and approximate queue position |
| `GET /jobs/{id}` | Phase, result, summary; no invented solve percentage |
| `POST /jobs/{id}/cancel` | Idempotent cancellation |
| `GET /drafts/current` | Current proposal, product metrics, warnings |
| `GET /drafts/{id}/diff` | Physical changes and modular projection updates |
| `POST /drafts/{id}/approve` | Atomic approval and expected-revision check |
| `POST /drafts/{id}/reject` | Audited rejection without arbitrary reroll eligibility |

Use existing class, Sumário, and occurrence flows. Never create parallel accounting paths.
Generation accepts idempotency and expected revision, not trusted client organization, worker count, or arbitrary strategy.
Return `202` for acceptance, `409` for state/revision conflicts, and `422` for invalid configuration.
Preserve the error envelope: `code`, `message`, `reference`, `retryable`, `fields`, and `context`.
Never expose tracebacks, complete snapshots, or another school's data.
The interface maps stable codes without parsing prose.
Show understandable queue, preparation, organization, improvement, and review phases.
Keep a persistent warning for completion beyond preference.
Separate open debt, planned recovery, and effective execution. Support multiple module slices in all consumers.
Preserve keyboard navigation, accessibility, and field errors. Keep exact Portuguese UI labels and domain terms.

## States and Transitions

```text
QUEUED -> RUNNING -> VALIDATING -> SUCCEEDED
   |          |           |
   +----------+-----------+-> CANCELLED / STALE / FAILED
              +-------------> INFEASIBLE / INCONCLUSIVE

Proposal: PENDING -> APPROVED / REJECTED / STALE / SUPERSEDED
Version: CANDIDATE -> ACTIVE -> SUPERSEDED
```

Terminal jobs never return to `RUNNING`. An administrative retry records a new identifiable attempt.
Transport redelivery refers to the same attempt and is idempotent.
Eligibility requires no active job plus initial generation, uncovered input changes, an incomplete attempt, or 28 elapsed calendar days.
Count 28 days by the school's local date while retaining the auditable UTC instant.
Persisting a complete proposal resets the clock in the same transaction.
Approval, rejection, failure, and cancellation do not reset it.
Rejection without changed inputs creates no new reason. Submission revalidates eligibility; the frontend is not authoritative.

## Failure Modes

- Invalid inputs fail normalization or prevalidation.
- Proven resource deficits produce scoped infeasibility evidence.
- Timeout or failed construction without proof produces an inconclusive result.
- Changed inputs invalidate queued work or pending proposals.
- Lost locks, stalled heartbeats, or killed processes trigger supervised recovery.
- Migration drift, tenant isolation failures, and invalid accounting block release.
- A database on the pre-baseline migration chain needs the reset rule in the [Deployment Runbook](../09_ops_observability/DEPLOYMENT_RUNBOOK.md#migration-baseline-and-reset-rule).

## Verification Procedure

The independent validator recalculates coverage, identity uniqueness, references, resource collisions, eligibility, dates, and protected history.
It also checks module slices, debt reservations, protected credit, completion metrics, physical gaps, continuous lunch, and teacher presence.
Index intervals by resource/date and sort them; avoid quadratic comparison.
Store validator version and candidate digest. Solver-declared metrics never replace recalculated metrics.
Deliberately corrupted candidates must fail with the correct violation code.

Use TDD for non-trivial rules: observable failing example, smallest correct implementation, then refactor.
Domain tests use values without ORM or solver mocks.
Transactions use PostgreSQL through Alembic, never SQLite. CP-SAT tests assert validity and quality rather than callback order.

| Area | Required observable evidence |
| :--- | :--- |
| Curriculum | 75+75/50 slicing, several modules per lesson, partial credit, mixed durations |
| Progress and debt | Idempotency, reversals, late Sumários, correction bounds, shared debt allocations |
| Stability | Different grid weekdays, N=0, holidays, execution, later approval |
| Resources | Shared teachers, room restrictions, overlapping intervals, soft preferences, lunch |
| Quality | Sorted completion-vector equivalence to tiny-instance oracle; adaptive priority comparisons |
| Diagnostics | Proven impossible inputs, local conflicts with globally feasible alternatives, timeout without proof |
| Lifecycle | Double submission, redelivery, changed inputs during queue, solve, and approval |
| Recovery | Killed processes, lost locks, failed dispatch, cancellation during validation |
| Isolation | Scoped queries and foreign keys, real RLS role, ignored client organization |
| UI | Configure, generate, approve, decide occurrence, repair, execute, correct, renew |

Metamorphic checks cover entity renaming, input permutation, additional availability, and enumerated optimal vectors.
The `lab/` modules provide deterministic test fixtures only.
The 48-class correctness regression uses the configured 900-second safety budget and validates a complete candidate.

For performance comparisons, fix inputs, hardware, policy, versions, and safety limits.
Record seeds, image/commit identity, input digest, CPU/RAM limits, workers, phase durations, outcomes, quality vectors, and bounds.
Separate queue time from processing. Include failures, OOM, and censored runs.
Report sample size and uncertainty. Do not combine local and Railway measurements into one baseline.
Compare validity and completion first, then quality and resources. Avoid averages that conceal difficult-school regressions.
A comparison can use 1/2/4/8 internal workers; eight workers do not guarantee eight CPU cores.
Evaluate stop-policy changes against independent cases and record missed late improvements.
Historical timings are not a current controlled benchmark or universal guarantee.

Run the maintained Docker workflow:

```text
node scripts/test.mjs setup --scope all
node scripts/test.mjs doctor --profile all
node scripts/test.mjs fast --scope all
node scripts/test.mjs critical --scope backend
node scripts/test.mjs integration
node scripts/test.mjs e2e --project app
node scripts/test.mjs capacity-smoke
node scripts/test.mjs all --scope all
```

Retain Ruff, frontend checks, contracts, security, integrity audits, and Alembic checks.
Search callers and documentation before deleting code. Refresh the frontend Docker image after frontend changes.
After every push, monitor associated CI until it passes.
Local test commands never reset or deploy Railway or Cloudflare.

Acceptance requires zero validator violations, duplicated minutes, protected physical changes, or stale approvals.
Concurrency tests must prove one global calculation.
Quality requires small-instance oracles and honest large-instance evidence.
Verify empty installation, process recovery, API, queue, generation, approval, and the frontend.
Record known limitations and selected runtime parameters. Functional acceptance uses concrete reviewable results.
The implementation is complete only when accounting, quality, operations, and publication work together.

## Source Map

- [Scheduler composition](../../backend/app/scheduler/composition.py)
- [Canonical serialization](../../backend/app/scheduler/domain/serialization.py)
- [Independent validator](../../backend/app/scheduler/domain/candidate_validation.py)
- [Quality policy](../../backend/app/scheduler/domain/quality.py)
- [Search orchestration](../../backend/app/scheduler/infrastructure/search.py)
- [Job lifecycle](../../backend/app/scheduler/infrastructure/jobs.py)
- [Proposal transactions](../../backend/app/scheduler/infrastructure/proposals.py)
- [Scheduler API](../../backend/app/api/v1/endpoints/scheduler.py)
- [48-class and fixture regressions](../../backend/tests/unit/test_scheduler_typology_v1.py)
- [Worker process recovery](../../backend/tests/integration/committed/test_worker_process_recovery.py)

## Related Documents

- [Scheduler Overview](README.md)
- [Data Model](../01_system_architecture/DATA_MODEL.md)
- [Occurrences and Substitutions](../04_operational_features/OCCURRENCES_AND_SUBSTITUTIONS.md)
- [Testing and CI](../08_security_quality/TESTING_AND_CI.md)
- [Deployment Runbook](../09_ops_observability/DEPLOYMENT_RUNBOOK.md)
