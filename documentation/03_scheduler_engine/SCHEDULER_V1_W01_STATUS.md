# Scheduler v1 — W01 domain work record

Date: 23 September 2026. State: **in validation**, not complete.
Starting commit: `facd1d93bead7fc6ed481de6761644afd2e0be81`.

Review 24 September 2026: the rules and examples are useful, but the snapshot
and protection contracts were insufficient. W01 is not integrally accepted.
The corrected contracts and validator are recorded in the correction work
record.

| WBS item | Implemented pure rule | Executed evidence | Remaining work |
| :--- | :--- | :--- | :--- |
| W01.1 | Immutable minute values, positive physical duration, semiopen UTC overlap checks and strict local timezone normalization | Calendar and projection tests | Check every value type and persistence boundary |
| W01.2 | Exact module projection by school date, start and stable lesson ID; partial progress and mixed durations | T01, T02, partial progress tests | Complete C01 and integrate with generated lessons |
| W01.3 | Append-only execution entries, explicit UTC audit instant, idempotent replay, bounded signed adjustments and audited reversal references | Focused T04–T07 and T29–T30 examples | Complete application flow and retroactive compensation |
| W01.4 | Open debt, many-to-many reservations, executed settlements, linked reversal and oldest-first positive-adjustment allocation | Reservation, cancellation, conservation and ordered-allocation tests | Full event sequence and transactional application |
| W01.5 | Grid-day counting, N=0 started-period protection, holiday count and daylight saving rejection | Focused T08 and T09 examples | Revalidation during approval and more boundary fixtures |
| W01.6 | Pure initial and adaptive quality vectors; explicit experimental slopes; manual eligibility and 28-day clock | Focused T15–T19 and T21–T22 examples | Oracles, calibration and longitudinal quality evidence |

The first tests failed before their domain modules existed. The focused domain
set passed. The complete backend unit run passed **458 tests** with 10 existing
dependency deprecation warnings; its JUnit is under
`.test-artifacts/1790198864335-6112/`. Ruff lint and the scoped formatting
check for the 29 Scheduler-related Python files passed. The whole-project
format check still reports two untouched, pre-existing files, as recorded in
the W02 status.

JUnit evidence is under `.test-artifacts/w01/`, including red and green runs.
The date-order and oldest-first adjustment changes have separate red/green XML
results in that directory.
The earlier runner unit result is in `.test-artifacts/1790179759481-1864/`.
The values in `test_scheduler_adaptive_quality_v1.py` are examples for ordering.
They are not production policy coefficients.

Four small domain examples extracted from C01, C09, C13 and C14 passed in
`.test-artifacts/w01/w01-small-campaigns.xml`. C01 covers one module, a
75+75 crossing, three modules in one mixed-duration lesson, and zero residual.
C09 covers protection for N=0/1/9 on one grid. C13 covers reservation,
cancellation, settlement, replay, adjustment and reversal. C14 replays a few
weeks of projection, execution and debt. These do **not** complete the full
campaigns: C09 still needs all horizons and grid variants; C13 needs
substitution and database rollback; C14 needs a full seeded annual replay.

W01 remains in validation. The first W02 database slice is installed only in
temporary PostgreSQL test databases; application consumers still use old
contracts. No development or production migration has occurred.
