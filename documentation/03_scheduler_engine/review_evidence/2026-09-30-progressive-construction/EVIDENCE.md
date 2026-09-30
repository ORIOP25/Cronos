# Progressive construction experiment

Date: 2026-09-30.
Status: local anticipation correction and required checks passed. Manual production generation validation remains pending.

## Required behavior

All subjects of each class must advance together through the school year.
Compare progress against each subject's required minutes, rather than equal lesson counts.
Advance that balanced curriculum as early as resource restrictions allow.
Reduce gaps while accelerating completion, rather than pacing demand until a fixed June deadline.
Preserve calendar restrictions, teachers, rooms, lunch, module order, and complete curricular coverage.
Return the first schedule that satisfies the required behavior and independent validation.

The user selected the balanced prototype and requested fewer gaps.
The implementation incorrectly interpreted that selection as requiring a fixed June cadence.
The user clarified that earlier completion remains mandatory.
The fixed-calendar measurements below establish a reference; they do not satisfy that complete objective.

## Input provenance

- Environment: Railway production.
- Organization ID: 27.
- School-year ID: 27.
- Reference generation job: 32.
- Input revision: 2.
- First eligible school date: 2026-10-12.
- Snapshot digest matched the reference job exactly.
- Assignments: 348, across 48 classes.
- Raw periods: 7,380. The domain canonicalizes repeated intervals.
- The tested snapshot contained no protected lessons.

Queries used a read-only transaction and the organization's RLS context.
Initial experiments ran in a separate Python process through the worker console.
The user subsequently authorized copying job 32's input into this local project.
The copied snapshot matched the reference job's digest before export.
Final comparisons ran locally with networking disabled, two CPUs, and a one-gigabyte memory limit.
They did not update application source, configuration, jobs, proposals, or published schedules.

## Existing construction failure

The deployed constructor fills one assignment before proceeding to another.
It returned `None` at `constructive.py:153`, after placing 22,443 lessons.
Assignment 6827 retained 1,350 of its required 3,600 minutes.
It had 1,476 eligible periods and 14 eligible rooms.
Its teacher required 32,400 minutes; its class required 25,200 minutes.
This construction failure does not prove infeasibility.

Reordering by assignment demand or teacher workload also failed on the same snapshot.

## Tested construction rule

Walk canonical periods chronologically, rather than completing assignments sequentially.
Maintain remaining minutes, module cursors, occupied resources, and lunch intervals.
Prioritize the least advanced subjects, using exact fractional progress.
Use remaining teacher and class demand to resolve ties.
Prefer eligible rooms with lower shared demand.

The original paced reference limited acceleration using the complete available calendar:

```text
target_minutes = required_minutes * elapsed_eligible_minutes / total_eligible_minutes
```

Calculate each day's target using its final eligible period.
Place the day's permitted lessons consecutively when the resources allow that placement.
A whole lesson can exceed the target by at most its own credited minutes.
The final lesson credits only the required remainder.
Run the existing independent candidate validator before accepting the result.

Focused tests also verify protected credit and executed-history identity preservation.

## Observed results

| Measurement | Progress priority alone | Progress with calendar pacing |
| --- | ---: | ---: |
| Complete and independently valid | Yes | Yes |
| Lessons | 24,558 | 24,558 |
| Missing minutes | 0 | 0 |
| Latest first lesson, days after origin | 2 | 2 |
| Earliest subject completion, days after origin | 7 | 228 |
| Latest subject completion, days after origin | 219 | 235 |
| Maximum weekly progress gap within a class | 72.22 percentage points | 2.82 percentage points |
| Mean weekly progress gap within a class | 14.64 percentage points | 1.01 percentage points |

Calendar pacing completed all subjects between 2027-05-28 and 2027-06-04.
No subject started after another subject of the same class had finished.

The paced experiment took 11.25 seconds to load, prepare, construct, and validate.
Construction and validation took 3.692 seconds after preparation.
The diagnostic Python process reached a peak RSS of 133,566,464 bytes.
The container's sampled peak was 331,526,144 bytes, including its existing worker.
Sampling read `memory.current` every 20 milliseconds. It cannot exclude shorter peaks between samples.

Job 32 previously recorded a container peak of 6,165,458,944 bytes during its first detailed feasibility search.
The sampled experimental peak was approximately 94.6 percent lower than that recorded peak.
This is a case-specific comparison of different generation paths, not a universal memory guarantee.
The experiment excludes job orchestration, proposal persistence, and deployment validation.
Calendar pacing establishes balanced progress for this input; it does not prove globally earliest completion.
Progress priority alone allowed a 72.22-point weekly gap.

## Rejected dense construction trial

A chronological construction also maximized simultaneous placements and favored later projected class completion.
It produced 24,558 independently valid lessons with 1,227,780 credited minutes.
All classes started on the first eligible day.
However, the latest subject started 91 days after origin.
The maximum weekly within-class progress gap reached 100 percentage points.
This trial was rejected because it failed the required pedagogical behavior.

Construction took 262.544 seconds; the sampled container peak reached 521,228,288 bytes.
Local matching used at most 3,139 variables, across 648 small models.
These figures do not describe the selected calendar-paced integration.

## Local implementation and anticipation correction

Construction walks canonical periods and preserves executed and protected credit.
The first patch applied daily targets across the complete eligible calendar.
That patch reduced daily gaps but retained the original completion dates.
The correction derives shared daily progress from cumulative resource capacity divided by residual demand.
It groups assignments connected through classes, teachers, and eligible rooms.
Independent groups advance independently.
Class and teacher capacity estimates preserve occupied intervals and mandatory lunch.
Room-set demand includes every assignment confined to each eligible room set.
These estimates determine pace; they do not prove simultaneous placement or globally earliest completion.
The constructor still allocates concrete resources and independently validates the complete result.
It prioritizes unstarted classes and subjects, then consecutive teacher and class periods.
Consecutive periods follow the configured grid, including its normal ten-minute breaks.
Normalized curricular progress and resource pressure resolve the remaining ties.
Room selection prefers lower shared demand.
Native resource matching repairs greedy choices within one period when needed.
Each local SAT repair receives at most 100 milliseconds.
An inconclusive repair retains the feasible greedy selection; incomplete annual coverage remains inconclusive.
An independent validator checks every completed candidate.

The worker defaults to returning the first complete candidate.
The same mode propagates through annual planning, detailed placement, and unrestricted fallback.
It skips subsequent quality stages, room refinement, and the extra recovery experiment.
Evidence reports zero certified quality stages for that mode.
Explicit quality-search callers retain their existing opt-in behavior.

Tests cover parallel starts, early completion, contiguous lessons, shared resources, and proportional subject loads.
They also cover protected credit, partial overlaps, deterministic ordering, deadlines, and first-complete paths.
The persisted-proposal integration test now expects honest first-complete evidence.

Integration exposed a collision between consumed lesson identities and new lessons.
The snapshot now reserves consumed identities for both construction and detailed placement.
Serialization preserves those reservations and accepts older payloads without them.
The integration test checks that completed logs retain their original lesson date and time.
The occurrence test uses an explicit reference date for overdue debt counts.

A full-suite run exposed an unrelated random request-reference assertion.
Digit-only hexadecimal references are valid; Python's `isupper()` rejects them.
The test now injects a deterministic digit-only reference and checks replacement exactly.

## Measurement approval state

Automatic approval review rejected prolonged background trials on the production worker.
The reviewer cited potential CPU and memory impact on the service.
It also rejected exporting the complete production snapshot into a temporary diagnostic file.
The reviewer cited potentially private organization data outside the authorized read-only investigation scope.
Neither rejected action executed.
The user then explicitly authorized the local snapshot copy.
The read-only export and local comparison completed under that authorization.
Production jobs, proposals, configuration, and published schedules remain unchanged.

## Fixed-calendar real-input reference

The reference uses calendar pacing per period and the simple chronological selection.
It reproduces the selected prototype's starts, completion dates, and weekly progress spread.
The fixed-calendar patch uses daily targets, grid adjacency, and bounded local resource matching.
Both results use the same authorized snapshot and independent validator.

| Measurement | Paced reference | Fixed-calendar patch |
| --- | ---: | ---: |
| Independently valid | Yes | Yes |
| Lessons | 24,558 | 24,558 |
| Credited minutes | 1,227,780 | 1,227,780 |
| Missing minutes | 0 | 0 |
| All classes started | 2026-10-12 | 2026-10-12 |
| Subject start range | 2026-10-12–2026-10-14 | 2026-10-12–2026-10-14 |
| Subject completion range | 2027-05-28–2027-06-04 | 2027-05-28–2027-06-04 |
| Maximum weekly within-class progress spread | 2.8205 percentage points | 2.8205 percentage points |
| Mean weekly within-class progress spread | 1.0089 percentage points | 0.8500 percentage points |
| Class gap minutes | 1,418,350 | 383,250 |
| Teacher gap minutes | 673,200 | 245,500 |
| Extra distinct rooms per class and subject | 1,435 | 2,503 |
| Construction seconds | 43.005 | 132.488 |
| Load, construction, validation, and measurement seconds | 45.403 | 133.660 |
| Diagnostic process peak RSS, bytes | 151,764,992 | 181,960,704 |

Class gap minutes fell by 72.98 percent; teacher gap minutes fell by 63.53 percent.
The existing quality metric counts empty grid periods between each resource's first and last daily lesson.
Normal ten-minute breaks between adjacent grid periods do not count as empty periods.
The metric does not deduct mandatory lunch periods; both columns use the same definition.
Room continuity was not optimized; this schedule uses more distinct eligible rooms.
All hard restrictions, lunch intervals, and curricular minutes passed independent validation.
No annual placement model or optimization after the completed construction ran in this comparison.

These local timings differ from the earlier production-host prototype measurements.
The process RSS values exclude the production worker and do not measure the full production container.
The earlier 94.6-percent container comparison must not be applied to these process-only measurements.

Snapshot digest: `ab2ffeaa65562e6f513839037f7102eaa41424543b46db50e93db8547d586c3f`.
The private copied input and local diagnostic results remain inside ignored `.test-artifacts`.

## Resource-paced anticipation result

The June deadline incorrectly acted as a pacing ceiling in the previous patch.
Daily adjacency shortened gaps inside each day, without advancing lessons from subsequent months.
The correction replaces that ceiling with a shared resource-capacity target.

The snapshot contains 961,200 required minutes confined to one set of fourteen eligible rooms.
Teacher capacity alone substantially understates that room pressure.
A teacher-only pacing trial finished in May but produced a 48.61-point within-class progress spread.
That trial was rejected.
The corrected estimate includes the demand of every subject restricted to each room subset.

| Measurement | Fixed-calendar patch | Resource-paced construction |
| --- | ---: | ---: |
| Independently valid | Yes | Yes |
| Lessons | 24,558 | 24,558 |
| Credited minutes | 1,227,780 | 1,227,780 |
| All classes started | 2026-10-12 | 2026-10-12 |
| Subject start range | 2026-10-12–2026-10-14 | 2026-10-12–2026-10-14 |
| Subject completion range | 2027-05-28–2027-06-04 | 2027-05-12–2027-05-19 |
| Maximum weekly within-class progress spread | 2.8205 percentage points | 3.0769 percentage points |
| Mean weekly within-class progress spread | 0.8500 percentage points | 1.2739 percentage points |
| Maximum weekly class progress spread | 3.2937 percentage points | 3.8889 percentage points |
| Class gap minutes | 383,250 | 313,500 |
| Teacher gap minutes | 245,500 | 239,950 |
| Extra distinct rooms per class and subject | 2,503 | 2,853 |
| Construction seconds | 132.488 | 179.083 |
| Diagnostic process peak RSS, bytes | 181,960,704 | 184,123,392 |

Latest completion advanced by sixteen calendar days.
Class gaps fell another 18.20 percent; teacher gaps fell another 2.26 percent against the fixed-calendar patch.
Against the original paced reference, reductions were 77.90 percent and 64.36 percent, respectively.
Weekly balance remains close but is slightly weaker than the fixed-calendar reference.
Room continuity also remains an explicit tradeoff.
No global optimization ran after constructing the completed schedule.
These results do not prove globally earliest completion or guarantee identical results for other snapshots.

TDD first reproduced three incorrect behaviors: late completion, unused daily capacity, and artificial delay of an independent class.
A further failing test reproduced imbalance from a restricted room subset.
All twenty-two construction tests and the focused fifty-three-test scheduler suite subsequently passed.
The real composition returned `COMPLETE` through the constructive path, with zero certified optimization stages.
Its coverage, dates, progress, gaps, and room counts matched the isolated construction exactly.
The composition trial took 229.079 seconds, including loading, construction, validation, and measurement.
The diagnostic process peaked at 195,186,688 bytes.
These local timings exclude persistence and are not production latency estimates.

The first full check exhausted a fifteen-second synthetic generation budget with coverage enabled.
The isolated forty-eight-class test passed without coverage.
Capacity calculations now reuse identical calendars, protected intervals, and lunch applicability.
The same fifteen-second test then passed with coverage; its limit was not changed.
The complete checks were restarted after this correction.

## Verification before the anticipation correction

Command: `node scripts/test.mjs all --scope backend`. Exit code: 0.

- Unit tests: 838 passed.
- PostgreSQL integration tests: 405 passed.
- Infrastructure contracts: 61 passed.
- Total: 1,304 passed.
- Ruff formatting and lint: passed.
- Backend coverage: 82 percent. Required gate: 70 percent.
- Constraint-policy coverage: 100 percent. Required gate: 100 percent.

The following commands also passed against the owned `cronos_test_gw0` database:

- `python -m alembic check`, using `cronos_migrator`.
- `python -m scripts.audit_triggers`.
- `python -m scripts.audit_database_integrity`.

Earlier test artifacts: `.test-artifacts/1790801220303-20732`.
The runner removed its owned PostgreSQL and Redis stack after verification.
Unrelated CSV deletions and documentation changes remain untouched.

## Final verification after the anticipation correction

Command: `node scripts/test.mjs all --scope backend`. Exit code: 0.

- Unit tests: 839 passed.
- PostgreSQL integration tests: 405 passed.
- Infrastructure contracts: 61 passed.
- Total: 1,305 passed. No failures or skips.
- Ruff formatting and lint: passed.
- Backend coverage: 82 percent. Required gate: 70 percent.
- Constraint-policy coverage: 100 percent. Required gate: 100 percent.

The migrator schema check, trigger audit, and database integrity audit also passed.
They used only the owned `cronos_test_gw0` database.
Artifacts: `.test-artifacts/1790804207710-18864`.
The runner removed its owned PostgreSQL and Redis stack.

## Production delivery checks

1. Push the reviewed implementation to `main`.
2. Monitor its CI run until every required job passes.
3. Fix, push, and monitor again if a required job fails.
4. Validate a normal production generation job and its persisted proposal.

The experiments did not generate or modify production schedules.
The delivery commit and its GitHub CI result are recorded separately after the authorized push.
