# PRD - Schedule Generator New Baseline

## Status
- Type: product and technical PRD.
- Scope: new baseline for schedule generation behavior.
- Legacy policy: existing implementation must be adapted to this PRD or removed.
- User-facing model: the user has one generation action; internal strategy is automatic.
- Baseline audit: `documentation/10_migration_map/BETA_BASELINE_LEGACY_CLEANUP_AUDIT.md`.
- Implementation note: solver V2 modules, legacy schedule compatibility routes, and schedule audit UI are removed from the beta baseline.

## Supersession
This PRD is the source of truth for the schedule generator baseline.

Older scheduler documents, solver V2 plans, reports, and WBS files in this folder are historical unless explicitly revalidated against this PRD. If an older document mentions target/preferred end dates, fixed 8-week rolling horizons, user-selectable repair modes, target-end optimization, or legacy repair accounting that conflicts with this PRD, this PRD wins.

The technical architecture spec and implementation WBS created after this PRD must reference this document as their behavioral authority.

## Canonical Terminology

### Generation Strategies
- `Complete Generation`: first schedule generation for an `UNPUBLISHED` school year.
- `Adaptive Repair`: post-publication generation when an operational trigger exists.

### School-Year Publication States
- `UNPUBLISHED`: no approved active schedule exists for the active school year.
- `PUBLISHED`: an approved active schedule exists for the active school year.

Pending drafts are tracked separately from publication state. A school year may be `UNPUBLISHED` with an initial Complete Generation draft pending, or `PUBLISHED` with an Adaptive Repair draft pending.

### Draft States
- `PENDING`: one generated draft exists and awaits approval, rejection, or replacement.
- `APPROVED`: the draft was approved and committed as the active schedule/future schedule.
- `REJECTED`: the admin rejected the draft.
- `REPLACED`: a regeneration discarded the draft and created a newer proposal.
- `STALE`: the trigger basis or generation policy changed after draft generation.
- `INVALIDATED`: the trigger no longer exists or the draft can never be approved.

### Result Categories
- `Complete Success`: a full valid draft was generated.
- `Partial Recovery`: Adaptive Repair generated a useful valid draft, but unresolved debt remains.
- `No Valid Output`: no valid draft could be generated under the current constraints and cap.

`Impossible With Explanation` is a diagnostic/escalation outcome that maps to `No Valid Output`; it is not a fourth result category.

### Debt Lifecycle States
- `Declared Debt`: user-declared missed required minutes not yet covered.
- `Planned Recovery`: approved future recovery blocks cover some or all declared debt.
- `Delivered Recovery`: linked recovery blocks were delivered and credited.
- `Residual Debt`: required minutes remain neither delivered nor covered by active planned recovery.

## 1. Step 1 - Generation Strategy Baseline

This step defines the product-level generation model and the internal repair strategy baseline.

### 1.1 Product Rule
The user must not choose between "complete" and "repair" generation.

The product exposes one action:

```text
Generate Schedule
```

The system decides the internal strategy automatically from the school-year schedule publication state:

1. If `school_year_publication_state = UNPUBLISHED`, run **Complete Generation**.
2. If `school_year_publication_state = PUBLISHED` and explicit unresolved debt exists, run **Adaptive Repair Generation**.
3. If `school_year_publication_state = PUBLISHED` and scheduler-relevant configuration/resources changed since the last approved schedule, run **Adaptive Repair Generation**.
4. If `school_year_publication_state = PUBLISHED` and neither trigger exists, block generation.

Every successful generation creates a validated schedule draft. No generated schedule becomes published/active until the admin approves the draft.

### 1.2 Complete Generation
Complete Generation is used only for the first schedule of the school year.

Primary behavior:
- build the full year plan from scratch;
- optimize the operationally near future deeply;
- fill the far future with a valid capacity-aware provisional schedule;
- complete all required curricular hours as early as reasonably possible within the bounded-effort generation model;
- use the configured hard end date as an absolute limit;
- treat stability against previous schedules as irrelevant because no published baseline exists yet.

### 1.3 Adaptive Repair Generation
Adaptive Repair Generation is used after a schedule has been published when an operational trigger exists.

Primary behavior:
- preserve the published operational reality as much as possible;
- recover missed mandatory hours before the hard end date when explicit debt exists;
- adapt the future schedule when scheduler-relevant configuration/resources changed;
- escalate disruption only when lighter repair strategies cannot recover all required hours;
- never mutate past or executed history;
- never violate hard constraints.

### 1.4 Repair Escalation Ladder
Adaptive Repair is a staged internal process. Levels are not exposed as user-selectable modes.

#### Level 1 - Append-Only Recovery
Adds missed lessons into future compatible free slots without moving existing scheduled blocks.

Use when:
- debt is small;
- compatible class, teacher, room, and timeslot capacity exists;
- no existing schedule needs to move.

Expected impact:
- only the affected class and teacher receive additional blocks;
- no unrelated class is disrupted.

#### Level 2 - Affected Class Recovery
May move future blocks within the affected class to create space for missed hours.

Use when:
- append-only recovery cannot fit all debt;
- the debt is primarily attached to one class;
- recovery can be solved by reorganizing that class without broad school disruption.

Expected impact:
- the affected class changes;
- unrelated classes remain protected.

#### Level 3 - Affected Teacher/Class Recovery
May move future blocks linked to the affected teacher and affected classes.

Use when:
- the bottleneck is teacher availability;
- one teacher missed hours across multiple classes;
- class-only repair cannot fit the missing hours.

Expected impact:
- the affected teacher schedule may change;
- other classes may be touched only when they share the bottleneck teacher.

#### Level 4 - Controlled School-Wide Repair
May rebalance future schedules across the school while strongly penalizing disruption.

Use when:
- debt is spread across multiple classes or teachers;
- local repair cannot recover all hours;
- the hard end date is not yet in emergency risk but broader rebalancing is required.

Expected impact:
- multiple classes may change;
- the repair remains conservative and avoids unnecessary movement.

#### Level 5 - Deadline Rescue
Prioritizes completing mandatory hours before the hard end date over timetable comfort.

Use when:
- lighter repair levels leave residual debt;
- the projected completion date is at risk of exceeding the hard end date;
- broader disruption is necessary to preserve curricular completion.

Expected impact:
- high disruption outside protected history and stability windows;
- denser weeks, less ideal preferences, and more gaps may be accepted;
- hard constraints still remain inviolable.

#### Level 6 - Impossible With Explanation
Reports that no valid plan exists under the current constraints.

Use when:
- even Deadline Rescue cannot schedule all required hours before the hard end date.

Expected output:
- residual unscheduled hours;
- main blockers, such as teacher availability, room capacity, calendar capacity, hard end date, or blocked dates;
- recommended operational interventions, such as extending the hard end date, increasing availability, adding substitute capacity, adding compatible rooms, or opening additional school slots.

### 1.5 Scheduler-Change Adaptation Ladder
When Adaptive Repair is triggered only by scheduler-relevant configuration/resource changes, the debt recovery ladder is not sufficient by itself.

The system must use the least disruptive adaptation scope that makes the future schedule compatible with the new scheduling conditions.

#### Adaptation Level A - Same-Time Resource Adaptation
Keeps dates and timeslots stable and changes only the affected resource assignment.

Use when:
- a room becomes unavailable but another compatible room can cover the same block;
- a room type or resource attribute changed and a same-time reassignment solves the issue.

#### Adaptation Level B - Affected Resource/Class/Teacher Refit
May move future blocks tied to the affected room, teacher, class, subject, assignment, or resource.

Use when:
- same-time reassignment is impossible;
- the change is localized to a specific resource, teacher, class, or assignment.

#### Adaptation Level C - Calendar/Grid Reflow
May reorganize affected future blocks across the changed calendar, blocked dates, lunch rules, or timetable grid.

Current implementation limitation: live structural timetable-grid changes after
publication are blocked and require an explicit school-year reset. Supporting
this reflow live requires versioned grids and historical timeslot preservation;
that work is outside the current grid-regeneration bugfix.

Use when:
- the scheduling surface itself changed;
- affected blocks no longer fit in their previous dates/timeslots.

#### Adaptation Level D - Controlled School-Wide Adaptation
May rebalance the future schedule across the school while minimizing disruption.

Use when:
- local adaptation cannot produce a valid future schedule;
- the change affects broad capacity, such as hard end date, timetable grid, room capacity, or major assignment changes.

#### Adaptation Level E - Impossible With Explanation
Reports that no valid adapted future schedule exists under the current conditions.

Use when:
- even controlled school-wide adaptation cannot satisfy hard constraints before the hard end date.

For mixed-trigger drafts, the generator combines debt recovery and scheduler-change adaptation, then reports the effective recovery level and adaptation level used.

### 1.6 Draft And Approval Rule
Generation can calculate strategy, repair scope, and escalation automatically, but publication remains governed.

Complete Generation and Adaptive Repair both produce drafts that require admin approval before becoming the active published schedule.

The admin does not select the repair level before generation. When repair escalation is used, the generated draft must explain the effective escalation level used and why lighter levels were insufficient.

Example:

```text
This repair required Controlled School-Wide Repair because Append-Only Recovery and Affected Class Recovery could not fit all mandatory hours before the configured hard end date.
```

### 1.7 Core Decision
The baseline decision is:

```text
Complete Generation produces a full concrete schedule draft through progressive optimization.
Adaptive Repair is operational-triggered only.
It protects stability first, then escalates only as needed to recover mandatory hours or adapt to scheduler-relevant changes.
```

### 1.8 Operational Scenarios

#### Scenario A - One occasional missed lesson
Context:
- one teacher misses one class in October;
- missing debt is small, for example 1-2 hours;
- there are compatible future free slots.

Expected behavior:
- Adaptive Repair should resolve this through Level 1 - Append-Only Recovery;
- no existing scheduled block should move;
- only the affected class and teacher should notice the added recovery block.

#### Scenario B - One teacher misses a full week
Context:
- one teacher is absent for several days;
- debt is spread across multiple classes taught by that teacher;
- free slots are insufficient for append-only recovery.

Expected behavior:
- Adaptive Repair should try Level 2 for affected classes;
- if class-only repair is insufficient, it should escalate to Level 3;
- changes should remain concentrated around the affected teacher and classes.

#### Scenario C - Multiple operational disruptions across the school
Context:
- several teachers/classes accumulate debt after illness, strikes, training days, or calendar disruption;
- local repairs are insufficient;
- the school still has meaningful time before the hard end date.

Expected behavior:
- Adaptive Repair may use Level 4 - Controlled School-Wide Repair;
- multiple future schedules may change;
- disruption should still be minimized and explained in the draft summary.

#### Scenario D - Hard end date at risk
Context:
- the school is close to the hard end date;
- accumulated debt cannot fit through conservative repair;
- failing to recover hours would risk curricular completion.

Expected behavior:
- Adaptive Repair may use Level 5 - Deadline Rescue;
- the algorithm may accept denser weeks, less ideal preferences, and more timetable gaps;
- all hard constraints remain inviolable;
- the draft must clearly explain that deadline risk forced a more disruptive repair.

#### Scenario E - Physical impossibility
Context:
- current constraints do not provide enough valid capacity before the hard end date;
- even aggressive repair cannot place all required hours.

Expected behavior:
- Adaptive Repair must stop at Level 6 - Impossible With Explanation;
- the system must report residual unscheduled hours and the main blockers;
- the output should recommend operational interventions instead of pretending success.

## 2. Step 2 - Complete Generation Objective

This step defines how the first schedule of the school year should behave before any operational disruption exists.

### 2.1 Core Rule
Complete Generation must prioritize earliest feasible completion of all mandatory curricular hours within a bounded-effort generation model.

It should not intentionally leave compatible empty capacity unused as a speculative recovery buffer.

### 2.2 Rationale
The first generation solves known mandatory work, not hypothetical future absences.

If the school year starts on September 15 and the hard end date is July 15, the system should use valid capacity to finish the required work as early as possible. If the generated plan finishes on June 10, the natural recovery buffer is the period between June 10 and July 15.

Leaving holes during the active year just in case a teacher later misses classes adds complexity and may produce a less efficient first schedule without solving a real current problem.

However, earliest completion must not be interpreted as a requirement to globally optimize the full school year as one monolithic solver problem. Large schools can exceed the generation cap if every future lesson, room, teacher, class, and timeslot is optimized at once.

The product requirement is a full valid schedule, not a mathematically proven global optimum.

The baseline therefore separates the year into two operational zones:
- near future: deeply optimized because it will become operational reality soon;
- far future: provisionally scheduled with a fast capacity-aware method and revised later only if a legitimate operational trigger allows Adaptive Repair.

### 2.3 Recovery Buffer Definition
The baseline recovery buffer is:

```text
recovery_buffer = school_hard_end_date - projected_completion_date
```

This buffer is not a separate reserved timetable structure. It is the natural unused calendar capacity left after completing all mandatory hours as early as possible.

### 2.4 Out Of Scope For Baseline
Risk-adaptive reserved capacity is out of scope for the baseline.

The system must not preserve artificial empty slots in Complete Generation based only on predicted future absences, scarce rooms, scarce teachers, or hypothetical disruption.

This may be reconsidered only if real operational evidence shows that maximum-compression complete schedules frequently force high-disruption repairs later.

### 2.5 Complete Generation Decision
The baseline decision is:

```text
Complete Generation uses progressive optimization with capacity-aware provisional far-future scheduling.
It fills valid capacity to finish mandatory hours as early as possible within the 5-minute generation cap.
Repair handles real disruption only after disruption exists.
```

## 3. Step 3 - Contextual Ideal Output

This step defines what counts as the best valid schedule after all hard constraints are satisfied.

### 3.1 Core Rule
The definition of ideal output depends on the internal generation strategy.

The system must not use one universal quality ranking for both Complete Generation and Adaptive Repair, because the operational context is different:
- Complete Generation has no published operational reality to protect.
- Adaptive Repair works after teachers, classes, and staff may already be relying on a published schedule.

### 3.2 Hard Constraint Gate
Before applying any objective hierarchy, every candidate output must satisfy all hard constraints.

Hard constraints include, at minimum:
- no teacher conflict;
- no class conflict;
- no room conflict;
- correct required room type;
- no `IMPOSSIBLE` teacher availability slot;
- no scheduling outside the valid timetable grid;
- no scheduling on blocked dates or conflicting calendar events;
- configured minimum lunch protection;
- no scheduled block after the hard end date;
- no mutation of past or executed history;
- tenant isolation for all reads and writes.

If a schedule violates any hard constraint, it is invalid regardless of soft quality.

### 3.3 Complete Generation Objective Hierarchy
For Complete Generation, the ideal output is the valid full concrete schedule that maximizes early completion inside the bounded-effort strategy.

Objective priority:
1. Finish all mandatory curricular hours as early as possible.
2. Keep class completion dates reasonably fair when this does not materially delay global completion.
3. Preserve workload sanity for classes and teachers when this does not materially delay completion.
4. Reduce timetable gaps and undesirable availability usage.
5. Prefer cleaner room/time distributions as the final tie-breaker.

Interpretation:
- earliest feasible completion is the dominant soft objective;
- class fairness and comfort are quality improvements, not reasons to leave mandatory work later without need;
- artificial recovery reserves are not part of Complete Generation;
- a far-future block may be less optimized than a near-future block if the full schedule remains valid and capacity-aware.

### 3.4 Adaptive Repair Objective Hierarchy
For Adaptive Repair, the ideal output is the least disruptive valid schedule that resolves the active operational trigger before the hard end date.

Objective priority:
1. Use the lowest sufficient repair escalation level.
2. Recover all unresolved explicit debt when debt exists.
3. Adapt the future schedule to scheduler-relevant changes when those changes are the trigger.
4. Preserve past, executed, and near-term published schedules.
5. Minimize disruption to unrelated classes, teachers, and rooms.
6. Keep projected completion as early as possible within the selected repair/adaptation level.
7. Improve class fairness, workload sanity, gaps, and undesirable availability usage as secondary quality goals.

Interpretation:
- repair does not blindly optimize earliest completion if a lighter, less disruptive repair can still complete all required hours safely;
- repair may escalate when lighter strategies cannot complete mandatory hours before the hard end date;
- once escalation is necessary, the algorithm should still avoid unnecessary movement inside that level.

### 3.5 Decision
The baseline decision is:

```text
Complete Generation ideal output = earliest valid full concrete schedule within bounded effort.
Adaptive Repair ideal output = least disruptive valid resolution of the active operational trigger before hard end.
```

## 4. Step 4 - Stakeholder-Weighted Disruption Model

This step defines how Adaptive Repair measures disruption.

### 4.1 Core Rule
Adaptive Repair must minimize stakeholder-weighted disruption, not raw block churn.

The system must not treat every changed block as equally disruptive. A room-only change six weeks from now is not equivalent to moving an unrelated class tomorrow.

### 4.2 Disruption Score Dimensions
The disruption score should consider at least four dimensions:

```text
disruption_score =
  what_changed_weight
+ who_was_affected_weight
+ how_soon_it_changes_weight
+ ripple_scope_weight
```

The scoring model is an internal optimization mechanism. The user does not configure weights directly in the baseline.

### 4.3 What Changed
Different change types have different disruption costs.

Low disruption:
- room-only change with same lesson, same date, and same timeslot;
- compatible room replacement due to room availability or maintenance.

Medium disruption:
- added recovery block in a free compatible slot;
- same-day time change;
- moving a block within the same week.

High disruption:
- changing the date of a block;
- changing the teacher assigned to a lesson;
- replacing one subject block with another;
- removing, delaying, or moving a block that students and teachers already expect.

### 4.4 Who Was Affected
The model must distinguish affected, related, and unrelated stakeholders.

Affected stakeholders:
- class, teacher, subject, or room directly linked to the missed or remaining hours being repaired.

Related stakeholders:
- same teacher across other classes;
- same affected class across other subjects;
- same course/year group when dependencies justify it;
- shared bottleneck rooms or room types.

Unrelated stakeholders:
- classes, teachers, subjects, and rooms with no operational relationship to the debt being repaired.

Changing unrelated stakeholders must be more expensive than changing affected stakeholders. The repair engine should only disturb unrelated stakeholders when lower-scope repair cannot recover the required hours.

### 4.5 When The Change Happens
Near-term changes are more disruptive than far-future changes.

Past or executed blocks:
- must never be mutated.

Frozen stability window:
- protects the schedule from all changes for the configured number of days.
- this value is user-configurable and may be `0`.
- when set to `0`, no future day is categorically frozen by this setting.
- a `0` day window does not remove the disruption score; near-term changes can still be penalized by the stakeholder-weighted model.
- when greater than `0`, the window blocks additions, moves, removals, replacements, room-only changes, and any other schedule mutation.

Recommended internal time weighting:
- same day or next day: very high disruption;
- next 7 days: high disruption;
- next 2-3 weeks: medium-high disruption;
- next 1-2 months: medium disruption;
- far future: lower disruption.

### 4.6 Ripple Scope
A repair that changes fewer stakeholders is preferred when it still recovers the required hours.

The model should penalize:
- number of distinct classes affected;
- number of distinct teachers affected;
- number of distinct rooms or room types affected;
- number of distinct school days affected;
- movement of blocks unrelated to the debt being repaired.

### 4.7 Operational Use Cases

#### Use Case A - One missed lesson
Context:
- 10A missed 2h of Mathematics.

Preferred repair:
- add Mathematics to a future compatible free slot for 10A and the Mathematics teacher.

Why:
- affects only the class and teacher linked to the debt;
- moves no existing block;
- has low ripple.

#### Use Case B - Same class rebalance
Context:
- 10A missed 6h of Programming;
- no empty compatible lab slots exist.

Preferred repair:
- move a future 10A block to create space for Programming;
- avoid disturbing unrelated classes.

Why:
- disruption remains inside the affected class;
- unrelated classes remain stable.

#### Use Case C - Teacher absence across multiple classes
Context:
- one Programming teacher misses a full week;
- 10A, 11B, and 12C all have Programming debt with that teacher.

Preferred repair:
- allow changes across that teacher's future schedule and those affected classes;
- avoid changing unrelated teachers and subjects unless escalation requires it.

Why:
- the bottleneck is the teacher;
- affected classes are operationally related through the same missed teacher capacity.

#### Use Case D - Room-only change
Context:
- Lab 1 becomes unavailable for maintenance.

Preferred repair:
- keep the same date and timeslot;
- move the lesson to Lab 2 if compatible.

Why:
- students and teacher keep the same schedule;
- room-only change has low disruption.

#### Use Case E - Bad repair to avoid
Context:
- 10A missed 2h of Mathematics.

Invalid-quality repair, unless no lighter path exists:
- move tomorrow's 12C lesson;
- move an unrelated teacher;
- change multiple rooms;
- insert 10A Mathematics into a convenient but high-ripple slot.

Why:
- the debt is small;
- unrelated stakeholders are affected;
- near-term movement is disproportionately disruptive.

#### Use Case F - Deadline rescue
Context:
- multiple classes have large accumulated debt near the hard end date.

Expected behavior:
- the system may accept higher disruption;
- it still chooses the least disruptive valid plan that prevents curricular failure.

Why:
- hard end risk justifies broader movement;
- stakeholder-weighted scoring still prevents needless chaos.

### 4.8 Decision
The baseline decision is:

```text
Adaptive Repair measures disruption by stakeholder-weighted disruption score.
Raw block churn may be reported as a metric, but it is not sufficient as the optimization definition.
The frozen stability window is user-configurable and may be 0 days.
```

## 5. Step 5 - Human-Controlled Debt Accounting

This step defines what Adaptive Repair must treat as curricular debt.

### 5.1 Core Rule
The schedule generator must not infer debt from silence.

Adaptive Repair only treats a scheduled lesson as debt when the operational state explicitly declares that debt exists.

Pending, unregistered, or unconfirmed past lessons do not automatically become debt. They remain awaiting user action.

### 5.2 State Accounting
The debt model is state-based, but human-controlled.

Operational states must be interpreted as follows:

#### GIVEN
The scheduled lesson was given.

Accounting:
- credited toward curricular progress;
- creates no repair debt.

#### GAP
The scheduled lesson was not given and was not replaced by equivalent curricular delivery.

Accounting:
- creates debt;
- Adaptive Repair must recover the original scheduled curricular content.

#### SUBSTITUTED
The original scheduled lesson was not given as planned.

Accounting:
- the original lesson creates debt and must be recovered;
- the substituted lesson is represented as a new independent `OperationalScheduleBlock`;
- the new substituted operational block is handled independently from the original lesson debt;
- no new structural `Lesson` should be created only because a substitution happened.

#### PENDING / UNREGISTERED
The scheduled lesson has not yet been confirmed by the user.

Accounting:
- does not create debt;
- does not credit progress;
- waits for user action.

#### Future Scheduled Lesson
The scheduled lesson is planned for the future.

Accounting:
- does not create debt;
- represents expected future capacity;
- may be considered by repair as part of the existing published plan.

### 5.3 Rationale
The school remains the source of truth for whether a lesson was actually missed.

This avoids false debt caused by delayed registration, teacher forgetfulness, or pending administrative review. The algorithm reacts to declared operational reality instead of guessing from incomplete logs.

### 5.4 Debt Lifecycle
A debt-producing occurrence is historical evidence. The active repair trigger is the unresolved debt balance, not merely the existence of a historical `GAP` or debt-creating `SUBSTITUTED` occurrence.

Canonical debt lifecycle states:

#### Declared Debt
The user has marked an occurrence as `GAP` or debt-creating `SUBSTITUTED`, and no approved future recovery block fully covers the missed required minutes.

This state creates an Adaptive Repair trigger.

#### Planned Recovery
An approved schedule draft created one or more future recovery blocks linked to the debt-producing occurrence revision.

The planned recovery link must include:
- debt occurrence id;
- debt occurrence revision/version;
- recovery scheduled block id;
- planned recovery minutes;
- class;
- subject;
- teacher when applicable;
- original planned block snapshot or reference.

Planned recovery minutes reduce the unresolved debt balance for trigger purposes, even before the recovery block is delivered.

#### Delivered Recovery
The linked recovery block was actually delivered and logged as given.

Delivered recovery credits curricular progress and closes the corresponding recovered minutes.

#### Residual Debt
Some required minutes remain neither delivered nor covered by active approved planned recovery blocks.

Residual debt creates an Adaptive Repair trigger.

If a planned recovery block is later canceled, removed by an approved repair before delivery, or itself becomes a `GAP`, the linked minutes return to residual debt unless another active planned recovery block covers them.

### 5.5 Active Debt Calculation
Adaptive Repair triggers only on unresolved debt:

```text
unresolved_debt_minutes =
  declared_debt_minutes
- delivered_recovery_minutes
- active_planned_recovery_minutes
```

If `unresolved_debt_minutes <= 0`, the original debt occurrence remains auditable but does not by itself unlock another repair generation.

### 5.6 Repair Implication
Adaptive Repair must calculate debt from explicit operational states before selecting a repair escalation level.

Example:

```text
Past lesson with state GIVEN -> no debt.
Past lesson with state GAP -> debt.
Past lesson with state SUBSTITUTED -> original lesson debt + independent `OperationalScheduleBlock`.
Past lesson with state PENDING -> no debt yet.
Future lesson -> no debt yet.
```

### 5.7 Decision
The baseline decision is:

```text
Debt is explicit, not inferred.
Only user-declared operational states create repair debt.
Pending silence does not trigger repair.
Approved planned recovery prevents the same historical debt from triggering infinite repairs.
```

## 6. Step 6 - Operational Adaptive Repair Triggers

This step defines when Adaptive Repair drafts may be generated after a schedule has already been published.

### 6.1 Core Rule
After the first schedule draft of the year has been approved and published, the admin may generate another schedule only when an operational trigger exists.

Allowed operational triggers:
1. explicit instructional debt exists;
2. scheduler-relevant configuration/resources changed after the last approved schedule.

If neither trigger exists, the `Generate Schedule` action must be unavailable or blocked with a clear explanation.

The system must not create sporadic, monthly, periodic, or quality-only optimization drafts.

Publication still requires admin approval.

### 6.2 Explicit Debt Trigger
Manual `Generate Schedule` after publication is allowed when unresolved explicit debt exists.

Explicit debt comes only from Step 5:
- active `GAP` occurrences;
- active `SUBSTITUTED` occurrences where the original planned lesson still creates debt.

The trigger uses Step 5 unresolved debt calculation, not raw occurrence existence. A historical debt occurrence that is fully covered by delivered recovery or active approved planned recovery remains auditable but does not trigger another repair by itself.

Pending or unregistered lessons may appear in separate operational alerts, but they must not trigger repair debt.

When debt repair is triggered, the generated draft should:
- recover declared debt when possible;
- apply the repair escalation ladder;
- preserve past/executed history;
- respect the frozen stability window, including `0`;
- require admin approval before publication.

### 6.3 Scheduler-Relevant Change Trigger
Manual `Generate Schedule` after publication is also allowed when scheduler-relevant configuration/resources changed after the last approved schedule.

The system does not need to prove that the current schedule is invalid before allowing generation.

The trigger exists because the schedule was generated under older scheduling conditions.

The system tracks this with a monotonic `scheduler_state_version`.

Version rule:
- the backend owns a scheduler-relevant change allowlist;
- every successful save to an allowlisted scheduler-relevant entity increments `scheduler_state_version` immediately;
- non-scheduler changes must not increment `scheduler_state_version`;
- every approved schedule stores `approved_scheduler_state_version`;
- generation is allowed when `scheduler_state_version > approved_scheduler_state_version`;
- approving a generated schedule stores the current `scheduler_state_version` as the new approved version.

The exact versioning mechanics belong in the technical architecture spec, but the design must explicitly define:
- version scope per organization and active school year;
- no-op save behavior;
- bulk import behavior;
- delete behavior;
- inactive resource behavior;
- future-impacting vs past-only changes;
- how version increments interact with pending draft staleness.

There is no separate "apply configuration changes" workflow in the baseline. Saving scheduler-relevant changes is enough to create the repair trigger.

Generation preflight still validates that the configuration is complete and internally consistent. If required scheduling data is missing or contradictory, generation is blocked before solver execution.

Scheduler-relevant changes include:
- teacher availability;
- rooms;
- room types;
- timetable grid;
- blocked dates or calendar events;
- lunch rules;
- school hard end date;
- class/subject/teacher assignments;
- lesson, module, or hour requirements.

Repair-policy changes include:
- repair stability window.

Repair-policy changes affect how the next repair is generated and may invalidate a pending draft, but they are not a standalone operational trigger. Changing only the repair stability window must not unlock generation when there is no unresolved debt and no scheduler-relevant schedule-shaping change.

Not scheduler-relevant:
- school name;
- school logo;
- admin profile;
- UI preferences;
- non-scheduler text fields.

When a scheduler-relevant change repair is triggered, the generated draft should:
- adapt the future schedule to the latest scheduler-relevant conditions;
- preserve past/executed history;
- respect the frozen stability window, including `0`;
- avoid unnecessary disruption;
- require admin approval before publication.

This is not a quality-only optimization trigger. It is an environment-change trigger controlled by real scheduler-relevant data changes.

### 6.4 No-Trigger Behavior
If `school_year_publication_state = PUBLISHED` and there is no unresolved explicit debt and no scheduler-relevant change since the last approved schedule:
- the admin cannot generate another schedule;
- no quality-only draft is generated;
- no automatic periodic optimization is run;
- the existing published schedule remains authoritative.

The UI should explain the blocked state in operational terms.

Example:

```text
No schedule generation needed.

There are no declared missed hours to recover and no schedule-relevant changes since the last approved schedule.
```

### 6.5 User-Facing Surfaces
Required surfaces:
- Dashboard command center;
- Schedules page;
- Occurrences/Debts view;
- pending draft review screen.

Expected behavior:
- debt alerts show declared debt and allow manual repair generation;
- scheduler-relevant change alerts show that schedule conditions changed and allow manual repair generation;
- if no trigger exists after publication, generation controls show a disabled or blocked state;
- if a repair draft is pending, the primary action is to review it;
- if a generation task is running, the UI shows progress or cancellation controls according to permissions.

### 6.6 Operational Use Cases

#### Use Case A - One GAP
Context:
- one 2h lesson is marked as `GAP`.

Expected behavior:
- debt alert appears;
- admin may generate Adaptive Repair immediately;
- generated draft requires review and approval before publication.

#### Use Case B - SUBSTITUTED lesson
Context:
- original lesson was Programming;
- substitute delivered English.

Expected behavior:
- original Programming creates repair debt;
- English substitute is tracked independently;
- admin may generate Adaptive Repair to recover the Programming debt.

#### Use Case C - Scheduler-relevant change without debt
Context:
- `school_year_publication_state = PUBLISHED`;
- no explicit instructional debt exists;
- teacher availability, room data, timetable grid, calendar, lunch, assignment, hour requirement, or hard end data changed after the last approved schedule.

Expected behavior:
- admin may generate Adaptive Repair;
- generated draft adapts the future schedule to the latest scheduling conditions;
- generated draft requires review and approval before publication.

#### Use Case D - No trigger after publication
Context:
- `school_year_publication_state = PUBLISHED`;
- no `GAP` or debt-creating `SUBSTITUTED` occurrence exists;
- no scheduler-relevant change exists since the last approved schedule.

Expected behavior:
- admin cannot generate another schedule;
- no automatic optimization draft is created;
- the existing published schedule remains authoritative.

#### Use Case E - Pending/unregistered lessons
Context:
- lessons are past but not yet registered.

Expected behavior:
- they do not create repair debt;
- generation remains blocked unless the user marks them as `GAP` or `SUBSTITUTED`, or a scheduler-relevant change exists;
- separate registration alerts may prompt users to close pending operational work.

### 6.7 Decision
The baseline decision is:

```text
First schedule generation is allowed when `school_year_publication_state = UNPUBLISHED`.
After publication, generation is allowed when unresolved explicit debt exists.
After publication, generation is also allowed when scheduler-relevant configuration/resources changed since the last approved schedule.
If both triggers exist, one mixed Adaptive Repair draft handles both.
Scheduler-relevant changes are detected through the backend allowlist and immediate `scheduler_state_version` increments.
No trigger means no manual generation and no automatic optimization generation.
No generated draft is published without admin approval.
```

## 7. Step 7 - Summary-Driven Draft Approval With Optional Deep Diff

This step defines how the admin reviews and approves generated drafts.

### 7.1 Core Rule
Draft approval is summary-driven.

The admin must be able to approve or reject any current valid generated draft from the summary view, regardless of draft size, repair escalation level, adaptation level, or number of changed blocks.

Stale, invalidated, incomplete, failed, or canceled generation outputs must not be approvable from either summary or detailed views.

The system must provide optional detailed inspection for transparency, diagnosis, and audit, but detailed inspection is never required before approval.

### 7.2 Approval Summary
Every draft summary should answer the operational approval question:

```text
Is this draft good enough to publish?
```

The summary should include at least:
- generation id;
- internal strategy, such as Complete Generation or Adaptive Repair;
- effective repair escalation level when applicable;
- declared debt before generation;
- debt recovered by the draft;
- debt remaining after the draft;
- projected completion date before and after;
- hard end date;
- affected class count;
- affected teacher count;
- total changed blocks;
- added blocks;
- moved blocks;
- room-only changes;
- removed blocks;
- stakeholder-weighted disruption score;
- concise reason explaining why this output was produced.

Example summary:

```json
{
  "generation_id": "abc123",
  "strategy": "adaptive_repair",
  "escalation_level": "controlled_school_wide_repair",
  "debt_hours_before": 14,
  "debt_hours_recovered": 14,
  "debt_hours_remaining": 0,
  "projected_completion_before": "2026-06-18",
  "projected_completion_after": "2026-06-24",
  "hard_end_date": "2026-07-15",
  "affected_classes": 4,
  "affected_teachers": 3,
  "changed_blocks": 38,
  "added_blocks": 8,
  "moved_blocks": 21,
  "room_only_changes": 6,
  "removed_blocks": 3,
  "disruption_score": 420,
  "summary_reason": "Repair used Controlled School-Wide Repair because affected-class repair could not recover all 14h before hard end."
}
```

### 7.3 Summary Actions
The summary view must provide direct actions:

```text
Approve Draft
Reject Draft
View Details
```

The admin may approve or reject without opening details.

### 7.4 Optional Deep Diff
The detailed view is optional but must be available for every draft.

It should support:
- changed block list;
- before/after comparison;
- grouping by class;
- grouping by teacher;
- grouping by week/day;
- grouping by change type;
- filtering by class, teacher, subject, date range, change type, and high-disruption changes;
- reason per change when available.

Example detailed change:

```json
{
  "change_type": "moved",
  "class": "10A",
  "subject": "Programming",
  "teacher": "Prof. Joao",
  "before": {
    "date": "2026-03-10",
    "time": "10:00-12:00",
    "room": "Lab 1"
  },
  "after": {
    "date": "2026-03-12",
    "time": "14:00-16:00",
    "room": "Lab 1"
  },
  "reason": "Created compatible recovery slot for 10A Programming debt."
}
```

### 7.5 Audit Rule
Optional detail must remain available after approval or rejection as audit history.

The school should be able to answer later:
- what changed;
- what the previous value was;
- what the new value became;
- who or what was affected;
- why the change was produced when this is available.

### 7.6 Operational Use Cases

#### Use Case A - Tiny repair
Context:
- one 2h lesson was marked as `GAP`;
- draft adds one compatible recovery block.

Expected UX:
- summary shows 2h recovered, 1 added block, 1 class, 1 teacher;
- admin approves from summary without opening details.

#### Use Case B - Medium repair
Context:
- 10h debt across two classes;
- draft moves several future blocks and adds recovery blocks.

Expected UX:
- summary exposes affected classes, affected teachers, changed blocks, and projected completion impact;
- admin may inspect details, but is not required to.

#### Use Case C - Deadline rescue
Context:
- large debt near hard end;
- draft changes many blocks but recovers all mandatory hours before the hard end date.

Expected UX:
- summary clearly shows Deadline Rescue, high changed-block count, and hard end risk;
- admin can still approve from summary;
- optional details provide full traceability.

#### Use Case D - Reject from summary
Context:
- draft recovers 6h debt but changes 42 blocks.

Expected UX:
- admin may reject from summary because disruption feels disproportionate;
- detailed review is optional.

### 7.7 Decision
The baseline decision is:

```text
Valid current draft approval is always possible from the summary.
Detailed diff inspection is always available but never mandatory before approval.
Draft details remain available as audit history.
```

## 8. Step 8 - Configuration Dates Simplification

This step defines which school-year dates are meaningful for the schedule generator.

### 8.1 Core Rule
The product must remove the "Preferred end date" field from the schedule configuration model and UI.

The schedule generator should not target a preferred end date when the school has already defined:
- school start date;
- school hard end date.

### 8.2 Rationale
The generator always tries to complete mandatory hours as early as possible.

A preferred end date creates a false product concept: it suggests the algorithm may intentionally delay completion to hit a user-selected target. That conflicts with the new baseline.

The only meaningful end boundary is the hard end date:
- no classes may be scheduled after it;
- completion before it is always better when hard constraints and contextual objectives allow it.

### 8.3 Product Behavior
The configuration flow should ask for:
- school start date;
- school hard end date;
- other operational constraints such as timetable grid, lunch rules, blocked calendar dates, and frozen stability window.

It should not ask for:
- preferred end date;
- target end date;
- soft completion date.

### 8.4 Algorithm Behavior
The algorithm must not optimize toward a preferred target end date.

Complete Generation:
- finishes as early as possible.

Adaptive Repair:
- recovers explicit debt with the least sufficient disruption before the hard end date.

### 8.5 Decision
The baseline decision is:

```text
Remove Preferred end date from the app.
Use school start date and hard end date as the date boundaries.
Never delay completion to match a preferred target.
```

## 9. Step 9 - Full Concrete Schedule Draft And Publication

This step defines what the generator creates after a successful generation and what approval publishes.

### 9.1 Core Rule
The generator creates a full concrete schedule draft.

After approval, the active schedule should contain concrete scheduled blocks from the relevant start date until all mandatory curricular hours are scheduled or until impossibility is reported.

Generation alone must not mutate the active published schedule.

The system must not split the product model into separate commitment, planning, and projection zones in the baseline.

### 9.2 Meaning Of Published
Published means:

```text
visible, active, operational schedule
```

Published does not mean guaranteed forever.

Schools already operate with the understanding that future plans may change. A lesson scheduled six months from now is a real planned lesson, but it may still change if operational reality changes and an approved repair modifies the future schedule.

### 9.3 Mutability Rules
The schedule mutability model is:

```text
past/executed blocks = immutable
future blocks = changeable only through approved Adaptive Repair
frozen stability window = configurable and may be 0 days
```

No generation or repair may mutate past or executed history.

Future blocks are not edited silently. They are changed through the draft and approval workflow.

### 9.4 Complete Generation
Complete Generation creates the first full concrete schedule draft of the school year.

Expected behavior:
- schedule all mandatory hours as early as possible within the progressive optimization model;
- optimize near-future blocks more deeply than provisional far-future blocks;
- create concrete draft blocks until completion;
- expose the full draft to admins for summary approval and optional detailed inspection;
- publish the concrete blocks only after admin approval;
- use the hard end date only as the absolute scheduling boundary.

### 9.5 Adaptive Repair
Adaptive Repair proposes changes to the future published schedule.

Expected behavior:
- generate a draft;
- summarize the proposed changes;
- provide optional detailed diff;
- require admin approval before future published blocks are replaced.

### 9.6 Decision
The baseline decision is:

```text
Generation creates a full concrete schedule draft.
Approval publishes the draft as the active schedule.
Future scheduled blocks are real planned lessons.
Future blocks may change only through approved Adaptive Repair.
Past and executed blocks are immutable.
```

## 10. Step 10 - Result Categories, Partial Recovery, And Residual Reporting

This step defines canonical generation result categories and what happens when Adaptive Repair cannot schedule all debt before the hard end date.

### 10.1 Core Rule
When complete Adaptive Repair recovery is impossible, the generator should produce the best valid partial recovery draft and an explicit residual report.

The system must not discard useful valid recovery work only because some debt remains unscheduled.

Partial Recovery is repair-only. Complete Generation must either create a full valid first schedule draft or return a clear no-valid-output result. It must not create or publish an incomplete first schedule.

### 10.2 Result Categories
Schedule generation uses these canonical result categories:

#### Complete Success
For Complete Generation:
- all required hours were scheduled in a full first schedule draft.

For Adaptive Repair:
- all required debt/adaptation work was handled in a valid repair draft.

#### Partial Recovery
Adaptive Repair scheduled some debt recovery, but residual unscheduled debt remains before the hard end date.

This is a warning state, not a normal success and not a total failure.

Complete Generation must not use this result category.

#### No Valid Output
No valid draft could be generated with the current constraints.

For Complete Generation, this means no full valid first schedule draft could be constructed inside the cap and constraints.

For Adaptive Repair, this means no useful valid repair draft could be generated.

`Impossible With Explanation` is an escalation/diagnostic state, not a separate result category. It maps to `No Valid Output`.

### 10.3 Partial Recovery Optimization
When complete recovery cannot be achieved, partial recovery should optimize in this order:

1. Maximize recovered mandatory minutes.
2. Minimize residual unscheduled debt before the hard end date.
3. Minimize stakeholder-weighted disruption.
4. Preserve earliest feasible completion where possible.
5. Improve gaps, preferences, and other low-priority quality metrics.

### 10.4 Approval Semantics
A partial recovery draft may be approved.

Approval means:

```text
Approve this partial recovery plan.
```

Approval must not imply that all mandatory hours have been recovered.

The summary action should make the partial nature visible, for example:

```text
Approve Partial Repair
```

### 10.5 Admin-Facing Message Format
Partial recovery messages must use a consistent warning format.

Required format:

```text
Partial recovery generated.

{recovered_hours}h were recovered, but {remaining_hours}h remain unscheduled before the hard end date.

Main blocker:
{main_blocker_message}

Recommended actions:
- {action_1}
- {action_2}
- {action_3}
```

### 10.6 Main Blocker Variants
The baseline uses two admin-facing main blocker variants.

#### Stability Window Blocker
Use when the configured stability window protects too much remaining editable schedule.

Message:

```text
The stability window protects too much of the remaining schedule before the hard end date.
```

Recommended actions:

```text
- Reduce the stability window.
- Allow broader future schedule changes.
- Generate the schedule again.
```

Full example:

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

#### Resource And Hard End Blocker
Use when remaining hours cannot fit with the current resources and hard end date.

Message:

```text
The remaining hours cannot fit with the current resources and hard end date.
```

Recommended actions:

```text
- Extend the hard end date.
- Add compatible resources or availability.
- Generate the schedule again.
```

Full example:

```text
Partial recovery generated.

8h were recovered, but 10h remain unscheduled before the hard end date.

Main blocker:
The remaining hours cannot fit with the current resources and hard end date.

Recommended actions:
- Extend the hard end date.
- Add compatible resources or availability.
- Generate the schedule again.
```

### 10.7 Scheduler-Change Adaptation Impossibility Message
When Adaptive Repair is triggered by scheduler-relevant changes without unresolved debt, the admin-facing impossibility message must not use recovered-hours language.

Required format:

```text
Schedule adaptation could not be generated.

{affected_block_count} future blocks are affected by the changed schedule conditions.

Main blocker:
{main_blocker_message}

Recommended actions:
- {action_1}
- {action_2}
- {action_3}
```

Allowed main blocker messages:
- `The future schedule cannot fit with the current resources and hard end date.`
- `The changed calendar, timetable grid, or blocked dates leave no valid placement for affected future blocks.`
- `The required room or teacher capacity is no longer available for affected future blocks.`

Example:

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

### 10.8 Blocker Classification
The system should classify the blocker with a simple diagnostic pass.

Recommended logic:
1. Attempt repair with the configured stability window.
2. If residual hours remain, run a diagnostic feasibility check with the stability window relaxed to `0`.
3. If relaxing the stability window solves or meaningfully improves the residual, classify the blocker as Stability Window Blocker.
4. If residual remains even with stability window `0`, classify the blocker as Resource And Hard End Blocker.

### 10.9 Optional Details
The optional detailed diff/report may include more specific diagnostics, such as:
- affected class;
- affected subject;
- affected teacher;
- missing hours;
- compatible room shortage;
- teacher availability shortage;
- calendar capacity shortage.

These detailed diagnostics are optional for review and audit. The main admin-facing summary should remain limited to the two blocker variants above.

### 10.10 Decision
The baseline decision is:

```text
Adaptive Repair may produce best valid partial recovery when useful.
Partial recovery is a warning-state draft with explicit residual hours.
Complete Generation never produces a partial first schedule.
The summary uses one of two main blocker messages: stability window, or resources/hard end.
Scheduler-change-only impossibility uses affected-block language instead of recovered-hours language.
```

## 11. Step 11 - Opinionated Configuration Model

This step defines which schedule-generator controls should be exposed to the school.

### 11.1 Core Rule
The product should use an opinionated configuration model with limited advanced controls.

Admins configure school reality. They do not tune solver strategy, objective weights, or internal repair behavior.

### 11.2 Configurable School Reality
The school may configure operational inputs that represent real constraints.

Configurable fields include:
- school start date;
- school hard end date;
- timetable grid;
- lunch rule;
- blocked calendar dates;
- teacher availability;
- room inventory and room types;
- frozen stability window, including `0` days.

Potential future advanced controls may be added only when they represent clear operational policy, not solver tuning.

Examples:
- maximum daily blocks per class;
- maximum daily blocks per teacher;
- maximum consecutive blocks;
- allowed extra timetable slots.

These future controls are not part of the baseline unless separately approved.

### 11.3 Non-Configurable Solver Strategy
The following must not be configurable by the admin in the baseline:
- Complete vs Repair generation mode;
- repair escalation level;
- stakeholder-weighted disruption weights;
- objective weights;
- preferred end date;
- target end date;
- soft completion date;
- algorithm engine version.

### 11.4 Required Product Cleanup
The current app already follows a limited-configuration spirit, but several existing controls conflict with the new baseline and must be removed or changed during implementation.

Required changes:
- remove preferred/target end date from backend model, schemas, UI, onboarding, preflight, and solver logic;
- remove user-facing Complete vs Repair mode selector;
- allow frozen stability window to be `0`;
- remove solver optimization toward target-end drift;
- make backend choose Complete Generation or Adaptive Repair automatically.

### 11.5 Rationale
The schedule generator should behave like a product, not a solver cockpit.

Schools should be able to describe their real-world constraints. The system should decide the best schedule under those constraints according to this PRD.

This keeps the UX understandable, reduces impossible self-inflicted configurations, and protects optimization, stability, scalability, and security.

### 11.6 Decision
The baseline decision is:

```text
Expose school-reality constraints.
Hide solver strategy and optimization weights.
Clean up existing fields that conflict with the new baseline.
```

## 12. Step 12 - Workload Sanity As Soft Constraint With Emergency Override

This step defines how the generator treats human workload quality.

### 12.1 Core Rule
Workload sanity is a soft quality layer, not a baseline hard constraint.

The generator should avoid exhausting or unrealistic schedules when valid alternatives exist, but it may accept heavier schedules during Deadline Rescue when required to recover mandatory hours before the hard end date.

### 12.2 Hard Constraints Still Win
Workload sanity must never override hard constraints.

The following remain inviolable:
- no teacher conflict;
- no class conflict;
- no room conflict;
- correct required room type;
- no `IMPOSSIBLE` availability slot;
- configured lunch hard rule;
- no classes after the hard end date;
- no mutation of past or executed history;
- tenant isolation.

### 12.3 Workload Sanity Signals
The generator should calculate workload quality signals such as:
- class daily load;
- teacher daily load;
- consecutive blocks for the same class;
- consecutive blocks for the same teacher;
- late-day blocks;
- repeated heavy days in the same week;
- recovery blocks stacked too aggressively.

These signals should become optimization penalties, not absolute blockers in the baseline.

### 12.4 Normal Scheduling Behavior
In Complete Generation and low-escalation Adaptive Repair, the generator should prefer healthier schedules when completion quality is materially similar.

Example:

```text
Schedule A finishes on June 10 but creates multiple 8-block days.
Schedule B finishes on June 12 and avoids most overload.
```

The generator may prefer the healthier schedule only when the delay is small and does not conflict with the progressive optimization baseline.

The system must not leave large artificial capacity unused only to make the timetable aesthetically lighter.

### 12.5 Small Repair Behavior
For small repairs, workload sanity should usually decide between valid recovery slots.

Example:

```text
10A missed 2h of Mathematics.
Option A adds recovery tomorrow to an already heavy day.
Option B adds recovery next week to a lighter day.
```

If both options recover the debt safely, the generator should prefer Option B.

### 12.6 Deadline Rescue Behavior
During Deadline Rescue, the generator may accept heavier class or teacher loads when the alternative is unrecovered mandatory debt before the hard end date.

This is allowed only after lighter repair strategies are insufficient.

The draft summary must warn the admin when overload is used.

Example warning:

```text
Deadline rescue generated.

All 30h were recovered before the hard end date.

Warning:
This draft creates 4 high-load class days and 2 high-load teacher days.
```

### 12.7 Partial Recovery Behavior
If overload is allowed and the generator still cannot recover all hours, the result becomes Partial Recovery according to Step 10.

Example:

```text
Partial recovery generated.

20h were recovered, but 10h remain unscheduled before the hard end date.

Main blocker:
The remaining hours cannot fit with the current resources and hard end date.
```

### 12.8 Baseline Non-Configuration
Workload sanity weights are not configurable by admins in the baseline.

Schools may later receive operational policy controls such as maximum daily blocks per class or teacher, but only after a separate PRD decision.

### 12.9 Decision
The baseline decision is:

```text
Workload sanity is optimized as a soft constraint.
Deadline Rescue may override workload comfort to recover mandatory hours.
When overload is used, the draft summary must warn the admin.
```

## 13. Step 13 - Teacher Availability Hard/Soft Tiers

This step defines how teacher availability preferences influence scheduling.

### 13.1 Core Rule
Teacher availability must use a tiered hard/soft model.

Only `IMPOSSIBLE` availability is a hard constraint. Other availability levels influence schedule quality but must not dominate completion, repair stability, or hard end recovery.

### 13.2 Availability Tiers
The baseline availability tiers are:

```text
IMPOSSIBLE = hard forbidden
AVOID = soft penalty
NORMAL = neutral
PREFERRED = soft bonus
```

### 13.3 IMPOSSIBLE
`IMPOSSIBLE` means the teacher cannot teach in that slot.

Scheduling a teacher in an `IMPOSSIBLE` slot is invalid in every generation strategy and every repair level.

Deadline Rescue must not override `IMPOSSIBLE`.

### 13.4 AVOID
`AVOID` means the teacher prefers not to teach in that slot, but the slot remains valid.

The generator should avoid this slot when comparable alternatives exist.

`AVOID` may be used when needed to:
- finish earlier in Complete Generation;
- recover debt with less disruption in Adaptive Repair;
- prevent residual debt near the hard end date.

### 13.5 NORMAL
`NORMAL` means the slot is valid and has no preference penalty or bonus.

### 13.6 PREFERRED
`PREFERRED` means the teacher prefers this slot.

The generator may prefer this slot when it does not materially harm higher-priority objectives.

`PREFERRED` must not cause the generator to:
- delay completion unnecessarily;
- increase repair escalation unnecessarily;
- disturb unrelated stakeholders unnecessarily;
- leave mandatory debt unrecovered.

### 13.7 Contextual Priority
Availability soft preferences are ranked differently by generation strategy.

Complete Generation:
- early completion remains the primary soft objective;
- availability preferences improve quality only after hard constraints, early completion, fairness, and workload sanity.

Adaptive Repair:
- debt recovery and disruption minimization outrank availability preferences;
- preferences should help choose between otherwise comparable repair options.

Deadline Rescue:
- `IMPOSSIBLE` remains hard;
- `AVOID` and `PREFERRED` may be mostly ignored when required to recover mandatory hours before the hard end date.

### 13.8 User Communication
The UI should explain that teacher preferences are respected when possible, but only `IMPOSSIBLE` is guaranteed.

Recommended teacher-facing language:

```text
Mark unavailable slots as Impossible. Preferences help the generator choose better schedules, but they are not guarantees.
```

### 13.9 Draft Summary Warning
When a generated draft uses many `AVOID` slots or overrides many `PREFERRED` opportunities, the summary may include a quality warning.

Example:

```text
Warning:
This repair uses 5 avoided teacher slots because lighter alternatives could not recover all declared debt before the hard end date.
```

### 13.10 Decision
The baseline decision is:

```text
Teacher IMPOSSIBLE availability is hard.
AVOID, NORMAL, and PREFERRED are contextual soft quality signals.
Only IMPOSSIBLE is guaranteed.
```

## 14. Step 14 - Room Assignment Hard/Soft Model

This step defines how rooms influence schedule generation and repair.

### 14.1 Core Rule
Room type compatibility is a hard constraint.

Specific room identity is a soft quality preference.

### 14.2 Room Type Compatibility
If a subject or lesson requires a room type, the generated block must use a compatible room.

Examples:
- Programming requiring a lab must be scheduled in a lab-compatible room.
- Physical Education requiring a sports space must be scheduled in a compatible sports room.
- A normal classroom subject may use a normal-compatible room.

Scheduling a lesson in an incompatible room type is invalid.

### 14.3 Specific Room Consistency
When multiple compatible rooms exist, the generator should prefer stable and coherent room usage when this does not materially harm higher-priority objectives.

The generator may consider:
- keeping the same class/subject in the same room when practical;
- avoiding unnecessary room changes inside the same day;
- preferring familiar rooms for specialized subjects;
- reducing room bouncing for teachers and classes.

These are soft quality signals, not hard constraints.

### 14.4 Repair Behavior
In Adaptive Repair, a room-only change should be considered low disruption when:
- the lesson remains on the same date;
- the lesson remains in the same timeslot;
- the teacher remains the same;
- the class remains the same;
- the new room is compatible.

Room-only changes should be preferred over date/time changes when they solve the operational problem.

### 14.5 Deadline Rescue Behavior
During Deadline Rescue, specific room consistency may be sacrificed to recover mandatory hours before the hard end date.

Room type compatibility still remains hard.

### 14.6 Draft Summary
Draft summaries should count room-only changes separately from date/time moves.

Example:

```text
Changed blocks: 38
Room-only changes: 6
Moved date/time blocks: 21
```

This prevents low-disruption room swaps from being confused with more disruptive timetable changes.

### 14.7 Decision
The baseline decision is:

```text
Required room type is hard.
Specific room consistency is soft.
Room-only changes are low disruption when the date/time/class/teacher remain unchanged.
```

## 15. Step 15 - Subject-Level Scheduling With Sequential Module Accounting

This step defines how subjects and modules/UFCDs relate to schedule generation.

### 15.1 Core Rule
The generator schedules subject-level hours.

Modules/UFCDs are not independent scheduling units in the baseline.

The schedule should contain blocks such as:

```text
10A - Mathematics - Prof. Silva - Room 12 - 10:00
```

It should not need to pre-assign each future block to:

```text
Mathematics Module 1
Mathematics Module 2
```

### 15.2 Module Accounting
Modules are handled by sequential progress accounting.

For each class and subject, delivered hours are credited to modules in their configured order.

Example:

```text
Mathematics Module 1 = 30h
Mathematics Module 2 = 25h
Mathematics Module 3 = 20h
```

Accounting:

```text
First 30h of delivered Mathematics -> Module 1
Next 25h of delivered Mathematics -> Module 2
Next 20h of delivered Mathematics -> Module 3
```

The 31st delivered hour of Mathematics naturally belongs to Module 2 without requiring schedule regeneration or module-specific scheduling.

### 15.3 Generator Demand
The generator should calculate demand as total remaining subject hours for each class/subject relationship.

It does not need to create separate scheduling demand per module unless a future PRD explicitly introduces module-specific constraints.

Example:

```text
10A Mathematics remaining = 50h
```

The generator schedules 50h of Mathematics.

Progress accounting later determines how those delivered hours fill the configured modules.

### 15.4 Debt Accounting
If a subject lesson is marked as `GAP` or original lesson debt from `SUBSTITUTED`, the debt is subject-level debt.

Example:

```text
10A missed 2h of Mathematics.
```

The repair engine recovers 2h of Mathematics.

When delivered, those 2h are credited to the next module position according to sequential module accounting.

The user does not need to declare which module was missed for the schedule generator to repair the debt.

### 15.5 Out Of Scope
The baseline does not support:
- module-specific timetable constraints;
- module-specific teacher assignment inside the same subject;
- pre-scheduling exact future blocks to exact modules;
- automatic regeneration when one module ends and the next begins.

These capabilities may be considered later only if real schools require them.

### 15.6 Decision
The baseline decision is:

```text
Schedule generation is subject-level.
Modules/UFCDs are sequential accounting units.
Future schedule blocks are not pre-assigned to modules.
```

## 16. Step 16 - Minimum Protected Lunch Duration

This step defines how lunch rules constrain schedule generation.

### 16.1 Core Rule
Lunch should be modeled as a minimum protected break duration inside a configured lunch window.

The baseline must not block the entire lunch window by default.

### 16.2 Lunch Configuration
The school configures:
- lunch window start;
- lunch window end;
- minimum lunch duration in minutes.

Example:

```text
Lunch window: 12:00-14:00
Minimum lunch duration: 60 minutes
```

### 16.3 Valid Scheduling
Lessons may overlap part of the lunch window as long as each affected class and teacher retains at least the minimum lunch duration free inside that window.

Example:

```text
Class 10A has a lesson from 12:00-13:00.
The 13:00-14:00 period remains free.
The class still has 60 minutes of lunch.
This is valid.
```

### 16.4 Invalid Scheduling
A generated schedule is invalid if a class or teacher does not retain the configured minimum lunch duration inside the lunch window.

Example:

```text
Lunch window: 12:00-14:00
Minimum lunch duration: 60 minutes

Teacher is scheduled 12:00-13:00 and 13:00-14:00.
The teacher has 0 minutes free inside the lunch window.
This is invalid.
```

### 16.5 Scope
Lunch protection must apply at least to:
- classes;
- teachers.

Room lunch is not relevant unless a future PRD introduces room-specific operational break rules.

### 16.6 Repair And Deadline Rescue
Lunch protection remains hard in Complete Generation, Adaptive Repair, and Deadline Rescue.

Deadline Rescue must not remove the minimum lunch break.

### 16.7 Configuration Policy
The baseline does not expose a separate lunch policy selector.

The product uses one opinionated model:

```text
minimum protected lunch duration inside lunch window
```

This supports staggered lunches while preserving human break protection.

### 16.8 Decision
The baseline decision is:

```text
Lunch window is not fully blocked by default.
Every class and teacher must retain the configured minimum lunch duration inside the lunch window.
Lunch protection is hard and cannot be overridden by Deadline Rescue.
```

## 17. Step 17 - Single Pending Draft With Regenerate/Replace

This step defines how many schedule drafts may exist at the same time.

### 17.1 Core Rule
The system must allow only one pending schedule draft at a time.

If a draft exists, the admin must either:
- approve it;
- reject it;
- regenerate it, replacing the existing draft when regeneration is still allowed.

Regeneration is allowed when:
- `school_year_publication_state = UNPUBLISHED`, for an initial Complete Generation draft;
- `school_year_publication_state = PUBLISHED` and an operational trigger still exists, for an Adaptive Repair draft.

### 17.2 Regenerate/Replace Semantics
Regenerating while a draft exists is an explicit replace operation.

It means:

```text
discard the current pending draft
generate a new draft from the current operational reality
keep only the new draft pending
```

This preserves the one-draft rule while allowing the proposal to refresh when explicit debt, settings, availability, or resources change the repair candidate.

For Complete Generation drafts, regeneration refreshes the first schedule draft from the latest school-year configuration.

For Adaptive Repair drafts, regeneration refreshes the repair proposal from the latest operational reality.

### 17.3 User Experience
If the admin clicks Generate Schedule while a draft exists, the system should not create a second draft silently.

Expected UX:

```text
A schedule draft is already pending.

Generating again will discard the current draft and create a new one from the latest data.
```

Actions:

```text
Regenerate Draft
Review Current Draft
Cancel
```

### 17.4 Pending Draft Behavior
If a draft is already pending, the system should show review/regenerate actions for the existing draft instead of creating another draft.

Examples:

```text
Schedule draft pending review.
```

or, if new debt/settings changes appeared after the draft:

```text
Schedule draft may be outdated. Regenerate to include the latest declared debt and constraints.
```

### 17.5 Draft Basis Snapshots
Every generated draft must store a generation input snapshot.

The generation input snapshot must include a stable fingerprint of the scheduling inputs used to generate the draft, including:
- active school year;
- school start date;
- hard end date;
- timetable grid;
- blocked dates and calendar events;
- class, subject, teacher, room, and room-type inputs;
- assignment relationships;
- lesson, module, and hour requirements;
- scheduler-relevant configuration version or equivalent fingerprint.

Approval validity for every draft requires:

```text
current_generation_input_fingerprint == draft.generation_input_fingerprint
```

If scheduler-relevant configuration/resources change after any draft was generated, the draft is stale and blocked from approval until regenerated.

### 17.6 Complete Draft Staleness
Complete Generation drafts are valid only while `school_year_publication_state = UNPUBLISHED` and the generation input snapshot still matches current scheduling inputs.

If teacher availability, rooms, room types, timetable grid, blocked dates, calendar events, lunch rules, hard end date, class/subject/teacher assignments, or hour requirements change before approval, the Complete Generation draft must be marked stale and blocked from approval until regenerated.

### 17.7 Trigger-Changed Repair Draft Invalidation
If the operational trigger that justified a repair draft no longer exists before approval, the draft must be invalidated.

If new explicit debt appears after a repair draft was generated, the draft must also be marked stale and blocked from approval until regenerated.

If scheduler-relevant configuration/resources change after a repair draft was generated, the draft must also be marked stale and blocked from approval until regenerated.

If repair-policy configuration such as the stability window changes after a repair draft was generated, the draft must also be marked stale and blocked from approval until regenerated.

Repair drafts must store a trigger basis snapshot.

Repair drafts must also store the generation policy snapshot used for the draft, including `repair_stability_window_days`.

If explicit debt and scheduler-relevant changes both exist at generation time, the system still creates one Adaptive Repair draft. The draft trigger type is `mixed`, and the trigger basis snapshot must include both:
- the exact debt basis fingerprint;
- the `scheduler_state_version` used to generate the draft.

For explicit debt, the trigger basis snapshot is a debt basis fingerprint for the exact unresolved debt used to generate the draft.

The debt basis fingerprint includes, for every debt-producing occurrence contributing unresolved minutes:
- occurrence id;
- occurrence revision/version;
- debt status (`GAP` or debt-creating `SUBSTITUTED`);
- source planned block id;
- class id;
- subject id;
- teacher id when applicable;
- original planned date/timeslot snapshot;
- debt minutes;
- unresolved debt minutes after delivered and active planned recovery are considered.

It does not need to permanently store aggregate debt totals per class, subject, or teacher as part of validity. Aggregates may be derived from the debt basis fingerprint for summaries and diagnostics.

For scheduler-relevant changes, the trigger basis is the `scheduler_state_version` used to generate the draft.

Approval validity for debt-triggered drafts is determined by comparing:

```text
current_debt_basis_fingerprint == draft.debt_basis_fingerprint
```

Approval validity for scheduler-change-triggered drafts is determined by comparing:

```text
current_scheduler_state_version == draft.scheduler_state_version
```

If the current version is higher, newer scheduler-relevant changes were made after draft generation and the draft is stale.

Approval validity for every repair draft also requires the current repair policy snapshot to match the draft repair policy snapshot:

```text
current_repair_policy_snapshot == draft.repair_policy_snapshot
```

If the repair stability window or another repair-policy parameter changed after draft generation, the draft is stale.

Approval validity for mixed-trigger drafts requires both trigger bases to still match:

```text
current_debt_basis_fingerprint == draft.debt_basis_fingerprint
current_scheduler_state_version == draft.scheduler_state_version
```

If either the debt basis or scheduler state version differs, the mixed-trigger draft is stale.

Invalidation means:
- the draft cannot be approved;
- the active published schedule remains unchanged;
- the draft remains available only as audit/history if the product keeps invalidated drafts visible;
- the admin must not be able to publish a stale or incomplete repair.

This can happen when:
- a `GAP` is corrected to `GIVEN`;
- a `SUBSTITUTED` original debt is resolved or reclassified;
- the underlying debt records are deleted or otherwise no longer active;
- a newer operational correction makes the draft debt basis empty;
- a new `GAP` is declared after the draft was generated;
- a new `SUBSTITUTED` occurrence creates new original-lesson debt after the draft was generated;
- a scheduler-relevant setting, resource, calendar, assignment, or requirement changes after the draft was generated.
- a repair-policy setting such as the stability window changes after the draft was generated.

Expected UI:

```text
Repair draft no longer valid.

The reason for this repair changed after the draft was generated.
The active schedule was not changed.
Regenerate the draft to include the latest schedule conditions.
```

### 17.8 Approval Behavior
Approving a draft publishes that draft and removes the pending draft state.

Rejecting a draft removes only the pending state and leaves the active published schedule unchanged.

The rejected generation summary and draft details remain available as audit history according to Steps 7 and 19.

Regenerating a draft removes the previous pending draft and replaces it with the new proposal.

### 17.9 Rationale
Multiple competing drafts create stale futures, confusing comparisons, and higher approval risk.

A single pending draft keeps the workflow clear:

```text
active schedule + at most one proposed future
```

### 17.10 Decision
The baseline decision is:

```text
Only one pending draft may exist.
Regenerate Draft replaces the current draft.
Complete Generation drafts are stale if scheduling inputs change before approval.
If the trigger for a repair draft is cleared before approval, the draft is invalidated.
If new explicit debt appears before approval, the draft is stale and blocked until regenerated.
If scheduler-relevant data changes before approval, the draft is stale and blocked until regenerated.
Rejected drafts leave audit history but no pending state.
Replacing a draft is equivalent to discarding it and generating a fresh proposal.
```

## 18. Step 18 - Draft Approval Reconciles The Future Schedule

This step defines what happens when an admin approves a draft.

### 18.1 Core Rule
On approval, the approved draft becomes the authoritative future schedule after the editable boundary.

Past and executed blocks remain immutable.

### 18.2 Editable Boundary
Debt repair uses the configured frozen stability window as the editable boundary.

The editable boundary is:

```text
editable_start_date = today + repair_stability_window_days
```

`today` means the current local date in the school's configured timezone.

`repair_stability_window_days` is counted in calendar days, not school days.

Repair may change only blocks on or after `editable_start_date`.

Past and executed blocks remain immutable regardless of the configured window.

The boundary is inclusive:
- blocks with `date >= editable_start_date` may be changed if they are not past/executed;
- blocks with `date < editable_start_date` must not be changed by approval.

The frozen stability window protects against all schedule changes, including:
- adding recovery blocks;
- moving existing blocks;
- removing existing blocks;
- replacing a class/subject/teacher/timeslot/room assignment;
- room-only changes;
- any other mutation that changes what students, teachers, or rooms are expected to do.

If the frozen stability window is `0`, repair may change editable future blocks from today onward, but past and executed blocks still remain immutable.

The system must not use a separate operational-notification lock in the baseline.

If the stability window prevents full recovery before the hard end date, the repair result should follow Step 10 partial recovery and blocker reporting.

### 18.3 Source Of Truth
Approval should not blindly apply a patch list and hope the final schedule matches the draft.

Instead, approval means:

```text
From the editable boundary onward, make the active schedule equal the approved draft.
```

This ensures the approved draft is the source of truth for the future schedule.

### 18.4 Preserve Unchanged Block Identity
When a future block is unchanged between the current active schedule and the approved draft, the system should preserve its database identity where safe.

This protects:
- audit continuity;
- existing references;
- user trust;
- clean diffs.

Unchanged means the relevant operational identity is the same, including:
- class;
- subject;
- teacher;
- date;
- timeslot;
- room;
- duration.

### 18.5 Changed Blocks
Changed future blocks should be reconciled so the active schedule matches the draft.

Depending on the change, this may require:
- adding new blocks;
- removing obsolete future blocks;
- updating room-only changes;
- moving blocks to new date/timeslot;
- replacing blocks that changed operational identity.

### 18.6 Recovery Link Reconciliation
When an approved draft includes planned recovery blocks, approval must reconcile recovery links together with the schedule blocks.

Expected behavior:
- preserved recovery blocks keep their existing recovery links where safe;
- moved or replaced recovery blocks update links to the approved active block ids;
- removed recovery blocks remove or inactivate their planned recovery links;
- any debt minutes no longer covered by delivered or active planned recovery links return to residual debt;
- approval must not leave recovery links pointing to deleted, replaced, stale, or tenant-mismatched blocks.

### 18.7 Safety Rules
Approval must verify before commit that the resulting active future schedule:
- satisfies all hard constraints;
- does not mutate past/executed blocks;
- respects the frozen stability window;
- belongs to the correct tenant;
- current generation input fingerprint still matches the draft generation input fingerprint;
- current operational trigger basis still matches the repair draft trigger basis when the draft is Adaptive Repair;
- current repair policy snapshot still matches the repair draft policy snapshot when the draft is Adaptive Repair;
- planned recovery links are preserved, updated, or removed consistently with approved recovery block changes;
- does not leave conflicts between preserved and draft blocks.

If validation fails, approval must be rejected without partial persistence.

If the draft basis changed after generation, approval must be rejected and the draft must be marked invalid/stale according to Step 17.

For Adaptive Repair, if the operational trigger no longer exists, or if the trigger basis or repair policy snapshot changed after draft generation, approval must also be rejected and the draft must be marked invalid/stale according to Step 17.

### 18.8 Conceptual Example
Current future schedule:

```text
A: 10A Math Monday 10:00 Room 1
B: 10A English Tuesday 10:00 Room 2
C: 11B Programming Wednesday 14:00 Lab 1
```

Approved draft:

```text
A: 10A Math Monday 10:00 Room 1
B: 10A English Friday 09:00 Room 2
D: 11B Programming Thursday 14:00 Lab 1
```

Expected reconciliation:
- preserve A because unchanged;
- reconcile B to Friday;
- remove C because it is not in the approved future;
- add D.

### 18.9 Decision
The baseline decision is:

```text
Approved draft becomes the authoritative future schedule after the editable boundary.
Unchanged future blocks preserve identity where safe.
Approval is atomic and must not mutate past/executed blocks.
Every draft approval requires the current generation input fingerprint to match the draft generation input fingerprint.
Repair draft approval also requires the current operational trigger basis and repair policy snapshot to match the draft.
```

## 19. Step 19 - Operational Generation Audit

This step defines what history the system must keep for schedule generations and draft decisions.

### 19.1 Core Rule
The system should keep an operational audit summary plus changed-block diff snapshot.

It should not permanently store full solver internals, every candidate, every score, or every rejected alternative in the baseline.

### 19.2 Audit Goals
Generation history should answer:
- what was generated;
- why it was generated;
- what strategy was used;
- what changed;
- what debt was recovered;
- whether debt remained;
- what warnings existed;
- who approved or rejected the draft;
- whether a draft was invalidated because the operational trigger changed;
- when the decision happened.

### 19.3 Generation Summary Fields
Each generation should store or expose at least:
- generation id;
- organization id;
- created timestamp;
- created by user id when applicable;
- internal strategy: Complete Generation or Adaptive Repair;
- repair escalation level when applicable;
- result category: Complete Success, Partial Recovery, No Valid Output;
- repair trigger type when applicable: explicit debt, scheduler-relevant change, or mixed;
- generation input fingerprint;
- declared debt hours before generation;
- trigger basis snapshot used for repair generation;
- scheduler state version used for repair generation when applicable;
- debt basis fingerprint when the trigger includes explicit debt;
- repair policy snapshot when the strategy is Adaptive Repair;
- debt hours recovered;
- debt hours remaining;
- hard end date;
- partial recovery blocker type when applicable;
- scheduler-change affected future block count when applicable;
- affected class count;
- affected teacher count;
- changed block count;
- added block count;
- moved block count;
- room-only change count;
- removed block count;
- stakeholder-weighted disruption score;
- workload warnings;
- availability preference warnings;
- solver/runtime duration;
- final decision status: pending, approved, rejected, replaced, invalidated.

### 19.4 Draft Decision Fields
For draft approval, rejection, replacement, or invalidation, the system should keep:
- decision type;
- decided by user id;
- decided timestamp;
- generation id;
- summary shown at decision time;
- residual debt warning shown at decision time, when applicable;
- invalidation reason when applicable.

### 19.5 Changed-Block Diff Snapshot
The system should retain a changed-block diff snapshot for operational transparency.

Each changed-block entry should include, when applicable:
- change type: added, removed, moved, room-only, replaced;
- class;
- subject;
- teacher;
- before date/time/room;
- after date/time/room;
- reason when available;
- whether the stakeholder was affected, related, or unrelated to the debt;
- disruption category.

The diff snapshot should focus on changed blocks, not every unchanged block.

### 19.6 Optional Details After Decision
Draft details should remain available after approval or rejection as audit history.

The school should be able to answer later:

```text
What changed in this generation?
Why did this schedule move?
Who approved it?
Was any debt left unresolved?
```

### 19.7 Solver Internals
Full solver internals are out of scope for permanent operational audit.

Examples of data not required for permanent storage in the baseline:
- every candidate considered;
- every rejected alternative;
- all raw objective scores;
- low-level CP-SAT variables;
- full search logs.

Technical logs may keep temporary diagnostics according to observability and retention policy, but they are not part of the admin-facing generation audit.

### 19.8 Decision
The baseline decision is:

```text
Keep operational generation audit summaries.
Keep changed-block diff snapshots.
Do not permanently store full solver internals in the baseline.
```

## 20. Step 20 - Automatic Strategy Selection

This step defines how the backend chooses Complete Generation or Adaptive Repair.

### 20.1 Core Rule
The backend selects the generation strategy automatically based on the explicit schedule publication state for the active school year.

The user does not choose the strategy.

Canonical school-year publication states:
- `UNPUBLISHED`: no approved active schedule exists for the active school year;
- `PUBLISHED`: an approved active schedule exists for the active school year;
- `RESET_REQUIRED` or equivalent internal transitional state may exist during destructive reset, but must not allow generation until reset completes.

Pending draft state is tracked separately and must not be used as a substitute for publication state.

### 20.2 Complete Generation Selection
If `school_year_publication_state = UNPUBLISHED`, the `Generate Schedule` action runs Complete Generation.

This is the first schedule generation for the active school-year workspace.

### 20.3 Adaptive Repair Selection
If `school_year_publication_state = PUBLISHED` and an operational trigger exists, the `Generate Schedule` action runs Adaptive Repair.

Operational triggers are:
- unresolved explicit debt exists;
- scheduler-relevant configuration/resources changed after the last approved schedule.

If both triggers exist, the backend still produces a single Adaptive Repair draft. The draft must recover explicit debt when possible and adapt the future schedule to the latest scheduler-relevant conditions in the same proposal.

If `school_year_publication_state = PUBLISHED` and no operational trigger exists, generation is blocked.

Manual `Generate Schedule` after publication is allowed only when an operational trigger exists or when Step 17 permits regenerating an existing draft.

### 20.4 Pending Drafts
Pending drafts do not count as published active schedules.

Pending drafts must not change `school_year_publication_state` to `PUBLISHED`. The active state changes only after approval commits successfully.

If a pending draft exists, Step 17 applies:
- review current draft;
- reject current draft;
- regenerate and replace current draft when Step 17 permits regeneration.

The system must not create multiple pending drafts.

### 20.5 Starting Over
If an admin wants a new Complete Generation after a schedule already exists, they must intentionally use the school-year reset flow.

The reset-year flow is a destructive admin action and must require explicit confirmation.

At minimum, reset-year clears:
- the active published schedule for the selected school year;
- pending schedule drafts;
- repair trigger basis state for that school year;
- approval snapshots used to decide whether the next generation is Complete or Adaptive Repair.

The reset flow may also clear other active-year operational data according to its own dedicated safety rules.

After reset, because `school_year_publication_state = UNPUBLISHED`, the next `Generate Schedule` action runs Complete Generation.

### 20.6 Rationale
The product model is one active school-year workspace.

The admin configures the school, generates the first schedule, and then uses Adaptive Repair only when unresolved explicit debt accumulates or scheduler-relevant conditions change. If the setup was wrong or the next year begins, the admin can intentionally reset the year and start over.

This avoids mode confusion while preserving a clear way to fully restart.

### 20.7 Decision
The baseline decision is:

```text
UNPUBLISHED school-year publication state -> Complete Generation.
PUBLISHED school-year publication state and operational trigger exists -> Adaptive Repair.
PUBLISHED school-year publication state and no operational trigger exists -> generation blocked.
To force Complete again, reset the school year first.
```

## 21. Step 21 - Atomic Generation, Cancellation, And Failure

This step defines what happens when generation is canceled or fails.

### 21.1 Core Rule
Generation is atomic from the user perspective.

A generation either completes successfully and produces the intended draft result, or it persists no user-visible schedule changes.

### 21.2 Cancel Behavior
If an admin cancels generation before completion:
- active published schedule remains unchanged;
- pending draft state remains unchanged unless a replacement had already completed atomically;
- no partial generated blocks become visible;
- no partial draft is shown as pending.

The user-facing result should clearly state that generation was canceled.

### 21.3 Failure Behavior
If generation fails due to an exception, timeout, worker crash, validation failure, or solver failure:
- active published schedule remains unchanged;
- existing pending draft remains unchanged unless replacement had already completed atomically;
- no partial generated blocks become visible;
- no partial draft is shown as pending.

The user-facing result should clearly state that generation failed and show the relevant error or impossibility message.

### 21.4 Preflight And Blocked Generation Messages
Preflight and blocked-generation messages must use operational language.

They should not expose solver jargon, internal candidate names, objective functions, or implementation-specific failure labels.

Required message categories:
- no operational trigger exists after publication;
- configuration is incomplete or internally inconsistent;
- no valid scheduling capacity exists with current resources;
- Partial Recovery blocked by the stability window;
- Partial Recovery blocked by current resources and hard end date.

Example no-trigger message:

```text
No schedule generation needed.

There are no declared missed hours to recover and no schedule-relevant changes since the last approved schedule.
```

Example incomplete-configuration message:

```text
Schedule generation cannot start.

Some required scheduling data is missing or inconsistent.

Review teachers, classes, rooms, subject hours, timetable grid, and calendar settings before generating.
```

### 21.5 Partial Recovery Is Not Partial Persistence
Partial Recovery from Step 10 is a valid completed result.

It is different from failed or canceled generation.

Partial Recovery may produce a draft only after the generator has completed, validated, and summarized the best valid partial plan.

### 21.6 Internal Checkpoints
The baseline does not require exposing internal checkpoints.

The system may later use temporary internal checkpoints for performance or diagnostics, but they must not become visible schedules or drafts until final validation succeeds.

Temporary artifacts must be cleaned up after cancellation or failure.

### 21.7 Validation Before Commit
Before persisting a completed result, the system must validate:
- tenant isolation;
- hard constraints;
- immutable past/executed history;
- frozen stability window behavior;
- draft uniqueness;
- result summary integrity.

If validation fails, the generation must fail atomically.

### 21.8 Decision
The baseline decision is:

```text
Canceled or failed generation persists no user-visible schedule changes.
Active schedule and existing drafts remain unchanged.
Only completed, validated generation results may create or replace a draft.
Only draft approval may publish active schedule changes.
```

## 22. Step 22 - Operational Decision Metrics

This step defines which metrics every completed generation should report.

### 22.1 Core Rule
Generation results should report operational decision metrics, not only minimal status and not full solver internals.

Metrics should help the admin understand:
- what happened;
- whether the schedule is complete;
- what changed;
- what risk remains;
- whether approval is reasonable.

### 22.2 Required Metrics
Every completed generation result should include at least:
- result category: Complete Success, Partial Recovery, No Valid Output;
- internal strategy: Complete Generation or Adaptive Repair;
- generation trigger: first generation, manual repair, or manual repair-draft regeneration;
- repair trigger type when applicable: explicit debt, scheduler-relevant change, or mixed;
- repair escalation level when applicable;
- generated block count;
- projected completion date;
- hard end date;
- hard end margin in days;
- declared debt hours before generation;
- debt hours recovered;
- debt hours remaining;
- affected class count;
- affected teacher count;
- changed block count;
- added block count;
- moved block count;
- room-only change count;
- removed block count;
- stakeholder-weighted disruption score or category;
- workload warnings;
- availability preference warnings;
- partial recovery blocker type when applicable;
- generation duration.

### 22.3 Complete Generation Metrics
Complete Generation should emphasize:
- projected completion date;
- hard end margin;
- total generated blocks;
- near-future quality summary;
- far-future provisional quality warning when relevant;
- generation duration against the 5-minute cap;
- class completion spread;
- workload sanity warnings;
- availability preference warnings.

Internal horizon sizes may be stored in technical logs or diagnostics, but they must not be part of the primary admin-facing summary.

### 22.4 Adaptive Repair Metrics
Adaptive Repair should emphasize:
- repair trigger type;
- explicit debt before generation;
- recovered debt;
- remaining debt;
- repair escalation level;
- affected classes and teachers;
- changed blocks by type;
- disruption score or category;
- partial recovery blocker when applicable.

### 22.5 User-Facing Language
Metrics shown to admins should use operational language, not solver jargon.

Preferred terms:
- "recovered hours" instead of "objective value";
- "remaining unscheduled hours" instead of "residual variable";
- "affected classes" instead of "class-set cardinality";
- "changed blocks" instead of "churn";
- "generation duration" instead of "solver wall time" when shown to admins.

Technical diagnostics may exist in logs or technical audit views, but they are not the primary admin-facing summary.

### 22.6 Decision
The baseline decision is:

```text
Every generation reports operational decision metrics.
Admin summaries avoid solver jargon.
Full solver internals are not required in the user-facing result.
```

## 23. Step 23 - Clean Rebuild Implementation Policy

This step defines how implementation should proceed after this PRD is closed.

### 23.1 Core Rule
The new schedule generator baseline is the source of truth.

Existing schedule-generator code has no preservation requirement. It must either be adapted to this PRD or deleted.

Because the app is still in development and there is no production environment to preserve, implementation should prioritize a clean PRD-aligned architecture over backward compatibility with legacy generator behavior.

### 23.2 Implementation Approach
The implementation should rebuild the schedule generator cleanly from this PRD.

This may include:
- deleting obsolete solver code paths;
- removing legacy V1/V2 assumptions;
- removing target-end-date logic;
- removing user-selectable generation modes;
- redesigning generation tasks;
- redesigning draft persistence;
- redesigning diff/audit summaries;
- redesigning debt accounting;
- redesigning repair escalation;
- rewriting tests around the new baseline.

### 23.3 What May Be Reused
Existing code may be reused only when it naturally fits the new baseline.

Reusable candidates may include:
- database connection/session infrastructure;
- tenant isolation helpers;
- stable CRUD services;
- room, class, teacher, subject, timeslot entities;
- occurrence entities if aligned with Step 5;
- UI design components;
- test fixtures that remain domain-correct.

Reused code must not preserve behavior that conflicts with this PRD.

### 23.4 What Must Not Be Preserved
The implementation must not preserve:
- target/preferred end date behavior;
- user-facing Complete vs Repair mode selector;
- target-drift solver objective;
- fixed 8-week rolling horizon as a product rule;
- blind greedy far-future fill that does not protect remaining capacity;
- repair window minimum greater than `0`;
- module-specific future scheduling demand;
- raw churn as the main disruption model;
- automatic debt inference from pending/unregistered lessons;
- sporadic, monthly, periodic, or quality-only generation after publication;
- manual generation after publication when no operational trigger exists;
- multiple pending drafts.

### 23.5 Migration Policy
No production data migration guarantees are required for the schedule-generator behavior in this baseline.

Development data may be reset if needed.

Schema migrations should still be clean and explicit, but they do not need to preserve old generator semantics.

### 23.6 Testing Policy
Tests should be rewritten around the new PRD behavior.

Priority test areas:
- automatic strategy selection;
- complete generation progressive optimization;
- capacity-aware provisional far-future scheduling;
- bounded 5-minute generation behavior;
- no-trigger generation block after publication;
- scheduler-relevant change trigger after publication;
- scheduler-relevant change allowlist behavior;
- generation input fingerprint staleness for Complete Generation and Adaptive Repair drafts;
- immediate `scheduler_state_version` increment on successful scheduler-relevant saves;
- repair stability window changes invalidate pending Adaptive Repair drafts but do not create standalone no-debt generation triggers;
- no periodic quality-only generation;
- explicit debt accounting;
- debt lifecycle from declared to planned, delivered, and residual debt;
- approved planned recovery suppresses repeat generation for already-covered debt;
- draft trigger-basis matching;
- mixed trigger draft generation and approval validation;
- scheduler state version trigger tracking;
- scheduler-change-only adaptation ladder behavior;
- editable boundary from frozen stability window;
- frozen window blocks all schedule mutations;
- debt basis fingerprint snapshot;
- repair policy snapshot validation;
- adaptive repair escalation;
- stakeholder-weighted disruption;
- partial recovery messages;
- single pending draft replacement;
- repair draft invalidation when debt is cleared or new debt appears;
- approval reconciliation;
- recovery link reconciliation on approval;
- scheduler-change-only impossibility messages;
- hard constraints;
- tenant isolation;
- reset-year destructive restart flow;
- operational preflight and blocked-generation messages;
- atomic cancellation/failure.

### 23.7 Decision
The baseline decision is:

```text
Implement a clean schedule-generator rebuild from this PRD.
Delete or rewrite legacy generator behavior that conflicts with the new baseline.
Development reset is acceptable.
```

## 24. Step 24 - Full PRD Acceptance Matrix

This step defines when the new schedule generator is considered done.

### 24.1 Core Rule
The feature is complete only when the implemented behavior satisfies the full PRD acceptance matrix.

Completing a WBS plan is not sufficient by itself. If the WBS tasks are complete but the implementation does not produce the expected PRD behavior, the feature remains unfinished.

### 24.2 Implementation Planning
A WBS plan may be used to organize implementation work.

The WBS may split work into phases, tasks, and validation checkpoints. However, the WBS is an execution tool, not the source of truth for acceptance.

The PRD remains the acceptance authority.

### 24.3 Acceptance Matrix
The final implementation must satisfy at least the following acceptance areas:

#### Strategy And Product Model
- user sees one `Generate Schedule` action;
- no user-facing Complete vs Repair mode selector;
- backend automatically selects Complete Generation when `school_year_publication_state = UNPUBLISHED`;
- backend automatically selects Adaptive Repair when `school_year_publication_state = PUBLISHED` and an operational trigger exists;
- Complete Generation creates a draft requiring admin approval before publication;
- Adaptive Repair creates a draft requiring admin approval before publication;
- every draft stores a generation input fingerprint;
- every draft approval validates the current generation input fingerprint against the draft fingerprint;
- operational triggers are unresolved explicit debt or scheduler-relevant changes since the last approved schedule;
- if explicit debt and scheduler-relevant changes both exist, one mixed Adaptive Repair draft is generated;
- scheduler-relevant changes are tracked with monotonic `scheduler_state_version`;
- `scheduler_state_version` increments immediately on every successful save to an allowlisted scheduler-relevant entity;
- non-scheduler changes do not increment `scheduler_state_version`;
- generation is allowed when `scheduler_state_version > approved_scheduler_state_version`;
- generation is blocked when `school_year_publication_state = PUBLISHED` and no operational trigger exists;
- no sporadic, monthly, periodic, or quality-only optimization drafts are created;
- changing only the repair stability window does not unlock generation when no unresolved debt and no scheduler-relevant schedule-shaping change exists;
- reset-year flow is the only way to intentionally return to Complete Generation after a schedule exists;
- reset-year requires explicit confirmation and clears active-year schedule/draft/repair-trigger state needed to restart.

#### Date Configuration
- preferred/target end date is removed from UI, onboarding, schemas, solver logic, and documentation contracts;
- school start date and hard end date are the only generator date boundaries;
- generator never delays completion to match a preferred target;
- hard end date remains absolute.

#### Complete Generation
- first schedule uses progressive optimization;
- near future is deeply optimized;
- far future is valid, concrete, provisional, and capacity-aware;
- far-future provisional fill uses bottleneck-first ordering with weekly pace as a secondary guide;
- fixed 8-week optimization is not treated as a product rule;
- blind greedy far-future fill is not accepted as baseline behavior;
- no artificial recovery buffer is preserved;
- output is a full concrete schedule draft that becomes published only after approval;
- Complete Generation drafts become stale if scheduler-relevant inputs change before approval;
- all hard constraints are satisfied.

#### Effort And Horizon
- every generation respects the 5-minute hard cap;
- internal horizon/window size is automatic and not admin-configurable;
- window size may shrink or expand based on problem complexity;
- the generator reports when the cap affects output quality or completion;
- Complete Generation may use provisional far-future scheduling to complete the full schedule draft inside the cap;
- Adaptive Repair may use bounded chunks when an operational trigger exists.

#### Adaptive Repair
- repair is used only when an operational trigger exists and `school_year_publication_state = PUBLISHED`;
- repair may change only blocks on or after `today + repair_stability_window_days`;
- frozen stability window blocks all schedule changes, including adding recovery blocks;
- repair stability window `0` allows today-forward repair while preserving past/executed immutability;
- repair uses the escalation ladder;
- scheduler-change-only repair uses the adaptation ladder;
- mixed repair reports both recovery escalation level and adaptation level when both are used;
- repair minimizes stakeholder-weighted disruption;
- repair recovers explicit debt before hard end when possible;
- repair adapts future schedules to scheduler-relevant changes when that is the trigger;
- repair may use Partial Recovery when full recovery is impossible.

#### Debt Accounting
- `GIVEN` credits progress and creates no debt;
- `GAP` creates debt;
- `SUBSTITUTED` creates original lesson debt and independent substituted `OperationalScheduleBlock`;
- `PENDING` and unregistered lessons do not create debt;
- future scheduled lessons do not create debt.
- approved planned recovery links reduce unresolved debt for trigger purposes;
- historical debt occurrences remain auditable after they are fully planned or delivered;
- residual debt reappears if planned recovery is canceled, removed before delivery, or missed.

#### Draft Workflow
- only one pending draft may exist;
- regenerate replaces the existing draft;
- repair draft is invalidated if its explicit debt is cleared before approval;
- repair draft is marked stale if new explicit debt appears before approval;
- repair draft validity is based on the debt basis fingerprint;
- mixed repair draft validity requires both debt basis fingerprint and scheduler state version to match;
- invalidated repair draft cannot be approved;
- stale repair draft cannot be approved until regenerated;
- stale Complete Generation draft cannot be approved until regenerated;
- valid current draft approval is always possible from the summary;
- optional detailed diff is available;
- draft details remain available as audit history;
- rejecting a draft removes pending state but preserves audit history;
- approval reconciles the future active schedule to the approved draft;
- approval reconciles planned recovery links when recovery blocks are preserved, moved, replaced, or removed;
- past/executed blocks are immutable.

#### Partial Recovery
- Adaptive Repair partial recovery produces best valid partial draft when useful;
- Complete Generation never produces a partial first schedule draft;
- residual hours are clearly reported;
- summary uses one of the two approved blocker messages;
- scheduler-change-only impossibility uses affected-block messaging instead of recovered-hours messaging;
- partial repair approval does not imply all hours are recovered.

#### Constraints And Quality
- teacher `IMPOSSIBLE` availability is hard;
- timetable-grid validity is hard;
- blocked dates and calendar events are hard;
- teacher `AVOID`, `NORMAL`, and `PREFERRED` are contextual soft signals;
- room type compatibility is hard;
- room consistency is soft;
- lunch minimum duration is hard for classes and teachers;
- workload sanity is soft with Deadline Rescue override and warning.

#### Metrics And Audit
- operational decision metrics are reported;
- admin-facing summaries avoid solver jargon;
- generation audit summary is stored;
- generation input fingerprint is stored for all drafts;
- trigger basis snapshot is stored for repair generations, including mixed-trigger drafts;
- scheduler state version is stored for schedule approvals and scheduler-change-triggered drafts;
- debt basis fingerprint is stored when the trigger includes explicit debt;
- repair policy snapshot is stored for Adaptive Repair drafts;
- scheduler-change affected future block count is stored when applicable;
- changed-block diff snapshot is stored;
- draft invalidation reason is stored when the operational trigger changes before approval;
- full solver internals are not required for permanent admin-facing audit.

#### Reliability And Security
- generation is atomic from the user perspective;
- canceled generation persists no user-visible changes;
- failed generation persists no user-visible changes;
- tenant isolation is enforced in all reads/writes;
- repair draft approval revalidates that the current operational trigger basis matches the draft trigger basis;
- every draft approval revalidates the generation input fingerprint;
- scheduler-change-triggered repair draft approval compares current `scheduler_state_version` to the draft version;
- debt-triggered repair draft approval compares the current debt basis fingerprint;
- mixed-trigger repair draft approval compares both the current `scheduler_state_version` and current debt basis fingerprint;
- generation preflight blocks incomplete or internally inconsistent scheduling configuration before solver execution;
- blocked generation and failure messages use operational language and avoid solver jargon;
- approval is atomic and validated before commit.

### 24.4 Testing Requirement
The implementation must include focused automated tests and direct sanity checks covering the acceptance matrix.

Tests should prove behavior, not merely implementation details.

### 24.5 Done Definition
The schedule generator is done only when:
- all acceptance areas pass;
- known PRD contradictions are resolved;
- no legacy generator behavior conflicts with the PRD;
- documentation reflects final implemented behavior.

### 24.6 Decision
The baseline decision is:

```text
The PRD acceptance matrix defines completion.
The WBS helps implementation but does not define done.
If the implementation does not satisfy the PRD, the feature is not finished.
```

## 25. Step 25 - Post-PRD Planning Artifacts

This step defines what should be produced after this PRD is closed.

### 25.1 Core Rule
The next artifact after the PRD should be a technical architecture specification.

Before that artifact is produced, the PRD should receive one final contradiction pass and then be treated as closed for implementation planning.

After the architecture is defined, implementation should be organized through a WBS plan.

Sequence:

```text
PRD contradiction pass -> PRD closure -> Technical Architecture Spec -> WBS Implementation Plan -> Implementation -> PRD Acceptance Validation
```

### 25.2 Technical Architecture Spec
The technical architecture spec should translate this PRD into concrete engineering design.

It should define:
- domain model changes;
- tables and migrations to remove obsolete fields and add required audit/draft data;
- service boundaries;
- generation pipeline;
- effort budget and timeout handling;
- complexity scoring and adaptive horizon selection;
- near-future optimization;
- capacity-aware provisional far-future scheduling;
- bottleneck-first provisional fill scoring with weekly pace as a secondary guide;
- repair escalation algorithm;
- scheduler-change adaptation ladder;
- editable boundary calculation from frozen stability window;
- scheduler-relevant change trigger tracking since last approved schedule;
- backend scheduler-relevant change allowlist;
- monotonic `scheduler_state_version` increment and approval snapshot;
- `scheduler_state_version` scope and edge cases for no-op saves, bulk imports, deletes, inactive resources, and future-impacting vs past-only changes;
- generation input fingerprint model for Complete Generation and Adaptive Repair drafts;
- mixed trigger handling when explicit debt and scheduler-relevant changes coexist;
- debt accounting flow;
- debt recovery link model from debt occurrence revisions to planned/delivered recovery blocks;
- repair trigger basis snapshot storage and comparison;
- debt basis fingerprint storage and comparison;
- repair policy snapshot storage and comparison;
- draft lifecycle;
- Complete Generation draft staleness before approval;
- destructive reset-year restart flow;
- approval reconciliation;
- recovery link reconciliation on approval;
- partial recovery diagnostics;
- scheduler-change-only impossibility diagnostics;
- operational preflight and blocked-generation messages;
- operational metrics payloads;
- API contracts;
- frontend surface changes;
- test strategy.

The architecture spec should answer what will be built and how the system will be structured.

### 25.3 WBS Implementation Plan
After the technical architecture spec is closed, a WBS should break the implementation into executable work packages.

The WBS should include:
- task ordering;
- dependencies;
- validation checkpoints;
- test files or test areas;
- documentation updates;
- cleanup/removal tasks for legacy behavior.

The WBS should help execution but must not redefine acceptance.

### 25.4 Acceptance Authority
The PRD remains the source of truth for product behavior.

The architecture spec and WBS must not weaken or contradict this PRD. If contradictions are discovered, they must be resolved by updating the PRD intentionally or changing the downstream artifact.

### 25.5 Decision
The baseline decision is:

```text
After this PRD, produce a technical architecture spec.
Then produce a WBS implementation plan.
Use the PRD acceptance matrix to decide when implementation is done.
```

## 26. Step 26 - Progressive Optimization And Bounded Effort

This step defines how the generator should produce useful schedules under a strict runtime cap.

### 26.1 Core Rule
The scheduler must use **Progressive Optimization With Capacity-Aware Provisional Far-Future Scheduling**.

The system must not attempt to solve the full academic year as one monolithic optimization problem.

The system must also not rely on blind greedy fill as the baseline for the far future.

The product contract is:
- produce a full concrete schedule draft for Complete Generation when a valid one can be constructed inside the generation cap;
- optimize the operationally near future more deeply than the far future;
- use a fast capacity-aware provisional method for far-future blocks;
- revise future blocks only when a later operational trigger allows Adaptive Repair.

### 26.2 Generation Cap
Every generation job has a hard wall-clock cap of 5 minutes.

The cap is a product rule, not a solver suggestion.

The generator must reserve enough time for:
- preflight validation;
- candidate preparation;
- near-future optimization;
- provisional far-future scheduling;
- full hard-constraint validation;
- draft or publication summary creation;
- cleanup on failure or cancellation.

The exact internal time budget per phase should be defined in the technical architecture spec.

### 26.3 Complete Generation Workflow
Complete Generation should run as follows:

1. Build the annual demand ledger.
2. Validate global feasibility against calendar, teacher, room, class, lunch, and hard end constraints.
3. Score scheduling complexity.
4. Select an automatic near-future optimization horizon.
5. Deeply optimize the near-future horizon.
6. Fill the far future with capacity-aware provisional scheduling.
7. Validate the full generated year.
8. Create one full concrete schedule draft if valid.

Complete Generation must not expose the near-future horizon to the admin.

If no full valid schedule can be constructed inside the cap, the system must not create an incomplete first schedule draft and must not publish anything. It must return a clear failure or impossibility result. This should be exceptional for feasible schools because provisional far-future scheduling exists specifically to avoid leaving the school without a usable first plan.

### 26.4 Near-Future Horizon Selection
The near-future optimization horizon is automatic.

It should be selected from school complexity signals such as:
- number of active classes;
- number of teachers;
- number of rooms;
- number of active subjects/lessons;
- number of valid timeslots per week;
- estimated candidate count;
- scarce teacher availability;
- scarce room type capacity;
- blocked calendar density;
- distance to hard end date;
- previous generation runtime telemetry when available.

Example behavior:

```text
small/simple school -> larger optimized horizon, such as 8-12 weeks
medium school -> moderate horizon, such as 4-6 weeks
large school -> smaller horizon, such as 2-4 weeks
very constrained school -> very small horizon, such as 1-2 weeks
```

These week ranges are implementation guidance, not admin-facing configuration.

The technical architecture spec must define the exact scoring model and thresholds.

### 26.5 Capacity-Aware Provisional Far-Future Scheduling
The far future may be filled by a fast heuristic, but it must be capacity-aware.

It must respect all hard constraints:
- no teacher conflict;
- no class conflict;
- no room conflict;
- required room type;
- `IMPOSSIBLE` teacher availability;
- blocked dates;
- lunch minimum duration;
- hard end date;
- subject-level hour requirements and sequential module accounting.

It must also protect scarce future capacity.

The far-future fill must consider:
- remaining subject hours per class;
- remaining teacher capacity;
- remaining room type capacity;
- weekly pace needed to finish before hard end;
- scarce room/teacher bottlenecks;
- workload sanity warnings;
- projected completion date.

### 26.5.1 Provisional Fill Ordering
Far-future provisional scheduling must use **bottleneck-first ordering**, with weekly pace as a secondary guide.

The heuristic should place the hardest-to-schedule demand before easier demand.

Bottleneck score should consider:
- teachers with low remaining compatible availability;
- required room types with limited room capacity;
- subjects/classes with few valid future placement options;
- classes with high remaining hours and limited open timetable capacity;
- lessons affected by blocked dates or compressed calendar periods;
- demands that need scarce time-of-day availability;
- remaining distance to hard end date.

Weekly pace should then guide the distribution of those placements.

The system should avoid scheduling all bottleneck demand immediately if doing so creates unrealistic class or teacher loads. It should use the annual demand ledger to spread hours at a pace that still completes before the hard end date.

Example:

```text
Chemistry requires a lab and has only one compatible teacher.
Portuguese has many compatible ordinary-room slots.

The provisional far-future fill should place Chemistry before Portuguese,
because Chemistry is harder to fit later.

Portuguese should then be placed around its required weekly pace,
instead of consuming scarce early capacity that Chemistry may need.
```

This rule rejects earliest-slot-first provisional fill as the baseline.

This means the far future can be provisional and less polished, but it cannot be careless.

### 26.6 Adaptive Repair Workflow
Adaptive Repair uses the same bounded-effort philosophy, but with different priorities.

Repair should:
- preserve past and executed history;
- respect the configured frozen stability window, including `0`;
- deeply optimize the operationally near future when changes are needed;
- allow far-future provisional blocks to change more freely;
- escalate through the repair ladder when lighter repair cannot recover debt;
- adapt to scheduler-relevant configuration/resource changes when that is the trigger;
- return Complete Success, Partial Recovery, or No Valid Output.

Because a published schedule already exists during repair, the system may safely return a Partial Recovery draft when full recovery is impossible.

### 26.7 Output Quality Contract
The system must be honest about output quality.

A schedule can be:
- valid and optimized in the near future;
- valid but provisional in the far future;
- valid but partially recovered in repair;
- impossible under current resources and hard end date.

The system must not label provisional far-future placement as globally optimal.

Admin-facing summaries may say that future blocks remain subject to later approved repair if operational conditions change, but they should not expose solver jargon or internal window sizes unless needed for diagnostics.

### 26.8 Rejected Alternatives
The baseline rejects:
- full-year monolithic optimization as the required default;
- fixed 8-week rolling optimization as a product rule;
- blind greedy fill as the baseline completion mechanism;
- admin-configurable solver window size.

### 26.9 Decision
The baseline decision is:

```text
Use Progressive Optimization With Capacity-Aware Provisional Far-Future Scheduling.
Respect a 5-minute hard cap for every generation.
Optimize the near future deeply.
Fill the far future with a valid capacity-aware provisional plan.
Do not run later refinement generations without an operational trigger.
Far-future blocks may remain provisional in quality until they are executed or until a later operational trigger allows Adaptive Repair.
Do not expose internal horizon size to the admin.
```
