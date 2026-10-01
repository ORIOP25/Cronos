# AdaptiveRecovery validation — 1 October 2026

## Behavior

AdaptiveRecovery uses current planning inputs and the published schedule.
It handles operational debt, calendar changes, teacher availability, room eligibility and manual execution corrections.
It preserves frozen physical positions and retains valid future positions when possible.
It compares that repair against a dense reconstruction with the published weekly reference.
The existing recovery vector balances completion impact, disruption, gaps and preferences.

Logged missed lessons remain operational history and contribute no planned credit.
Completed lessons contribute through the execution ledger.
Future curricular slices follow actual execution without fabricating completed history.
New debt reservations use editable lessons after the stability window.
Existing approved reservations remain attached when their lessons enter that window.
Planning does not settle debt; recorded execution does.

CompleteGeneration retains its accepted constructor and default behavior.
Shared capacity lookups now index protected lessons by school date, preserving the same overlap rules.
No dependency, migration or configuration setting was added.

## TDD and regression checks

Failing tests first reproduced missed lessons counted as protected credit and debt reserved inside the frozen window.
Further failures reproduced manual progress consuming hypothetical future lessons and partial-credit snapshot rejection.
The constructive recovery tests initially failed because the production route did not exist.
A structural capacity test initially scanned sixteen unrelated protected lessons; the date index reduced that count to zero.

Run the required backend checks:

```text
node scripts/test.mjs all --scope backend
```

Result: exit 0.

| Check | Result |
| :--- | :--- |
| Unit tests | 861 passed |
| Committed integration tests | 417 passed |
| Contract tests | 61 passed |
| Ruff format and lint | Passed |
| Total coverage | 82%, above the 70% gate |
| Constraint policy coverage | 100% |
| Alembic check | No pending upgrades |
| Tenant trigger audit | Passed |
| Database integrity audit | Passed |

Integration tests use real services, state revisions, snapshot loading, worker execution and proposal approval.
They cover holidays, breaks, teacher constraints, preferences, room addition, withdrawn room eligibility and manual credits.
Occurrence tests verify logged history, frozen lessons, recovery reservations and debt settlement after execution.
All database checks used isolated test databases.

## Isolated organization-scale experiments

The user authorized a local copy of organization 27's job 32 inputs.
These experiments used that private snapshot and the accepted stable schedule containing 24,558 lessons.
They reproduced the current room distribution and simulated execution until 11 November 2026, 18:00 UTC.
The stability window contained ten grid days and 2,880 frozen lessons.
The published future contained 16,836 lessons and ended on 8 February 2027.

Each experiment used an isolated container with two CPUs, a 1 GB memory limit and no network.
The safety budget was 900 seconds; the constructive production route was enabled.
Each candidate passed independent validation and exact curricular coverage checks.
Every frozen lesson matched its original domain value, including physical position and slices.

| Change | Repair | Original positions retained | Last class finishes | Wall time | Container peak bytes |
| :--- | :--- | ---: | :--- | ---: | ---: |
| One teacher missed eight lessons: 400 minutes debt | 8 inserted lessons | 100% | 9 February 2027 | 139.857 s | 221,765,632 |
| Two added closure dates: 30 November and 1 December | 320 moved lessons | 98.099% | 9 February 2027 | 139.264 s | 225,161,216 |
| One teacher became unavailable on 30 November | 8 moved lessons | 99.952% | 9 February 2027 | 172.581 s | 222,584,832 |
| Manual withdrawal of 100 executed minutes | 2 inserted lessons | 100% | 8 February 2027 | 100.973 s | 221,872,128 |

Position retention compares assignment, UTC interval and room against the published future.
The percentage divides retained positions by the original future lesson count.
Inserted lessons do not lower that percentage.
This measures preservation during repair, not repetition between adjacent weeks.
Wall time includes experiment preparation, repair, validation and report preparation.
Container memory uses cgroup `memory.peak`; it is separate from process RSS accounting.

Private inputs, candidates and reports remain outside version control under `.test-artifacts/scheduler-org27-job32`.
The reports are `adaptive-absence-report.json`, `adaptive-calendar-report.json`, `adaptive-teacher-report.json` and `adaptive-manual-report.json`.
No production data or published schedule was changed.

## Limits and delivery

These experiments validate four changes against one organization-scale snapshot.
They do not certify global optimality or guarantee a feasible repair for every input.
The bounded route compares two complete constructions and reports `INCONCLUSIVE` when neither succeeds.
Disabling `SCHEDULER_V1_STOP_AT_FIRST_COMPLETE` retains the existing annual master/detail search.
Frozen positions remain mandatory; contradictory changes require an explicit diagnosis instead of silent movement.
Existing resource deletion guards remain in force.

Validation was completed locally on branch `codex/adaptive-recovery`, based on accepted main commit `13faa1775afe499fd2d28cba68cc743d3558f0af`.
This evidence does not confirm a production deployment or a remote CI run.
