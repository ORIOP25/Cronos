# Scheduler v1 — W02 relational work record

Date: 23 September 2026. State: **in execution**, not complete.

Review 24 September 2026: an installed schema is not a fully persisted
domain. RC05.2, RC05.3, RC05.6 and RC05.7 remain open, and the baseline and
reset path remain provisional. Do not treat W02 as closed. The correction
work record lists the completed and pending slices.

The first W02.1 slice adds relational assignment, requirement, execution,
execution-credit, debt, debt-revision and debt-settlement tables. Every table
has an organization column, forced RLS with the existing school-context
function, and grants limited to its intended mutability. Tenant-scoped foreign
keys cover school years, classes, subjects, teachers, memberships, modules and
the new records. Execution and debt evidence is append-only for the runtime
role. The database stores signed minute changes as integers.

The schema is installed by the provisional migration
`0011_scheduler_v1_curricular.py` on a fresh **temporary** PostgreSQL test
database. It must be consolidated into the requested new Alembic baseline
after the remaining v1 tables and application consumers are ready. It is not
an old-data compatibility path and has not been applied to development or
production databases.

| Evidence | Result |
| :--- | :--- |
| Missing-table integration test before implementation | Failed as expected; JUnit in `.test-artifacts/1790194432230-26148/` |
| Fresh Alembic install, seven tables and forced RLS | Passed; JUnit in `.test-artifacts/1790194655411-20308/` |
| Cross-school class reference rejected by PostgreSQL and runtime role sees only its school's assignment | Passed; JUnit in `.test-artifacts/1790194912202-22860/` |
| Existing backend infrastructure contracts | 47 passed alongside each green integration run |
| Alembic history and privacy table-classification unit contracts | 11 passed after registering the new migration and tables |
| Locked execution transaction, idempotent replay, invalid adjustment, two concurrent replays and two competing adjustments | Passed; JUnit in `.test-artifacts/1790195499499-7412/` |
| Retroactive reversal retains the original curricular offset | Failed before correction at `.test-artifacts/1790195607944-6096/`; passed afterward at `.test-artifacts/1790195699129-25088/` |
| Replay with changed planning semantics | Failed before correction at `.test-artifacts/1790195885365-14908/`; passed afterward at `.test-artifacts/1790195965090-34168/` |
| Debt would exceed residual demand; explicit settlement and replay | Failed before reconciliation at `.test-artifacts/1790196119365-7184/`; passed after implementation and refactor at `.test-artifacts/1790196511914-3104/` |
| Two debts in one execution and one debt across two executions | Passed in PostgreSQL; JUnit in `.test-artifacts/1790197008314-20884/` |
| ORM columns, runtime append-only privileges and RLS | Three integration checks passed; JUnit in `.test-artifacts/1790196758134-27056/` |
| Full backend unit suite after migration, privacy registry and domain changes | 457 passed; JUnit in `.test-artifacts/1790196661937-24284/` |
| Automatic oldest-first settlement of positive corrections | Red at `.test-artifacts/1790197292895-28436/`; green with PostgreSQL and 47 contracts at `.test-artifacts/1790197367915-16504/` |
| Automatic reversal of associated settlements | Red at `.test-artifacts/1790197484851-1808/`; green at `.test-artifacts/1790197567410-25340/` |
| Multiple partial reversals across two debts | Five W02 PostgreSQL checks and 47 contracts passed at `.test-artifacts/1790197888976-19424/` |
| Alembic metadata drift and empty-database downgrade/reinstall | `alembic check` and roundtrip passed; JUnit at `.test-artifacts/1790198062117-15816/` |
| Backend unit suite and runner tests before debt creation | 457 backend unit tests and 16 runner tests passed; JUnit at `.test-artifacts/1790197997548-5156/` |
| Full backend integration and infrastructure contracts after W02 changes | 299 integration and 47 contract tests passed; JUnit at `.test-artifacts/1790198281572-19368/` |
| Audited debt creation under the state lock; concurrent replay and residual limit | Import failed before implementation at `.test-artifacts/1790198552695-9660/`; six W02 PostgreSQL checks and 47 contracts passed at `.test-artifacts/1790198929397-17080/` |
| Backend unit suite after debt-origin validation | 458 passed; JUnit at `.test-artifacts/1790198864335-6112/` |
| W02.2 job and proposal persistence slice before implementation | Failed as expected at `.test-artifacts/1790201905364-8720/` (`ImportError: cannot import name 'SchedulerJobV1'`) |
| W02.2 job and proposal tables, one active job per year, one current proposal per year, job idempotency, proposal-per-job uniqueness and tenant-scoped foreign keys | Passed in PostgreSQL; 300 integration and 47 contract tests at `.test-artifacts/1790202064831-17468/` |
| Backend unit suite after the W02.2 schema slice | 458 passed in the locked Docker `ci` image; Alembic metadata check and empty-database roundtrip included in the 300 integration run |
| W02.3 installed schema passes the read-only structural and relational integrity audit | Passed; 8 W02 PostgreSQL checks at `.test-artifacts/1790202572631-23676/` |

The execution command locks the school-year state row first, checks its
assignment's module subject, validates the complete ledger with the pure
domain, writes execution and slices, then increments `input_revision` and
optionally `planning_revision` within the caller's transaction. A replay does
not increment either revision. Two concurrent requests for the same event
returned the same record; competing final credits accepted one and rejected
the other without exceeding Q. The same transaction now validates existing
debt plus proposed settlements against the new residual demand before writing.
An event cannot silently reduce R below its open debt. A settlement replay
checks the recorded associations and does not write a second settlement.

W02.1 remains open: historical compensation when retroactive corrections shift
later confirmed slices, recovery reservations, and complete cross-row
conservation are still needed. Positive corrections now liquidate debt in
oldest-first order, and a negative reversal reopens its associated settlement.
Both paths passed scoped PostgreSQL tests.

W02.2 now installs job and proposal records on top of the earlier version and
lesson tables. `scheduler_job_v1` stores the request origin and revision, the
attempt token, the observed input and planning revisions, the snapshot digest,
the heartbeat, the cancellation instant and the typed result. A partial unique
index keeps one non-terminal job per organization and school year, and
`(organization_id, origin, revision)` makes a transport replay idempotent.
`scheduler_proposal_v1` stores one proposal per job, its baseline and candidate
versions, the policy version, product metrics, diff and decision. A partial
unique index keeps one current pending proposal per organization and school
year. The school-year state now records the last completed planning revision
and the last successful generation instant so the 28-day eligibility clock can
be evaluated without scanning jobs. All foreign keys are tenant scoped, and
both tables force RLS with the existing school-context function. W02.2 remains
open for its persistence adapters and transaction wiring.

W02.4 and W02.5 are demonstrated through the RC05/RC06 correction packages:
recovery planning, cancellation, debt revision, reservation reconciliation,
the annual preferred date, the local reset procedure and the administrative
erasure path all have PostgreSQL tests. W02.3 remains open only for the final
Alembic consolidation, which is tracked as a mandatory W12 checkpoint in
[SCHEDULER_V1_ALEMBIC_CONSOLIDATION_PLAN.md](SCHEDULER_V1_ALEMBIC_CONSOLIDATION_PLAN.md).
C13 and C17 have not run end to end in PostgreSQL. No reset of the existing
development volumes or external services was performed.
Debt creation now uses the same school-year lock and records author, reason and
UTC audit time. Concurrent replays return one debt ID without consuming a
second revision; a new claim is rejected if it exceeds `Q-E`.

The local `ruff format --check .` currently reports two untouched, pre-existing
CRLF-format deviations in `app/core/exceptions.py` and
`app/services/course_service.py`; the 29 Scheduler-related Python files passed
the scoped format check. The full lint check passed after correcting the new
test's import order. This does not satisfy the whole-project format gate yet.

The privacy erasure command currently uses the runtime application role, while
the append-only execution/debt tables deliberately deny that role `DELETE`.
The older progress ledger has the same permission pattern. W02/W12 must add an
explicit, tested administrative erasure path before claiming the RGPD workflow
works with the new schema. Broad `DELETE` grants to the runtime role would
undermine the audit contract.
