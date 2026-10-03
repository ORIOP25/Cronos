# Occurrences and Substitutions

## Purpose

This document describes absences (*Faltas*), occurrence decisions, and substitutions (*Substituições*).

## Intended Reader

This document targets backend engineers, frontend engineers, and school administrators.

## Prerequisites

Read [Lesson Execution](LESSON_EXECUTION.md) and [Scheduler Engine](../03_scheduler_engine/README.md).

## What the System Does

Cronos creates an occurrence from an active schedule block when a lesson needs an operational decision.
An administrator records the decision `GIVEN`, `GAP`, or `SUBSTITUTED`.
A substitution creates a planned substitute lesson. Execution starts only when the substitute lesson is concluded.

## Why the Behavior Exists

A pending occurrence signals a problem. It must not change progress or debt.
Debt exists only after the direction decides `GAP` or `SUBSTITUTED`.
Planning a substitution must not anticipate curricular execution.

## Components and Ownership

| Responsibility | Implementation |
| :--- | :--- |
| API | `backend/app/api/v1/endpoints/occurrences.py` |
| Legacy domain service | `backend/app/services/occurrence_service.py` |
| Scheduler v1 consumer | `backend/app/scheduler/infrastructure/occurrences.py` |
| Substitute execution | `backend/app/scheduler/infrastructure/operations.py` |
| Models | `SchedulerLessonLogV1`, `OperationalScheduleBlock`, `LessonOccurrence` |
| UI | `frontend/src/pages/Occurrences.jsx` |

## Data or Request Flow

1. A teacher or administrator registers an occurrence. The system creates no debt and no execution.
2. The administrator decides `GIVEN`, `GAP`, or `SUBSTITUTED`.
3. `GIVEN` requires the lesson end instant, then credits the original subject.
4. `GAP` creates the original-subject debt claim once.
5. `SUBSTITUTED` creates the same debt claim and an active operational block for the substitute.
6. The substitute or an administrator concludes the operational block.
7. The conclusion credits only the substitute subject. The original debt remains.
8. A reversal compensates only the effects of the occurrence.

## Contracts and Invariants

- The API state is `OPEN_PENDING`, `DECIDED_GIVEN`, `DECIDED_GAP`, `DECIDED_SUBSTITUTED`, or `REVOKED`.
- The v1 lesson log stores the decision, instant, author, and reversal reason.
- A pending occurrence has no open debt and no execution.
- A decision repeated with the previous version returns the current state without new writes.
- A stale version returns `409 OCCURRENCE_STALE_VERSION` without partial effects.
- `GIVEN` before the lesson end returns `422 lesson_not_finished`.
- A planned substitution reports `hours_given` as zero.
- Completing the substitute block credits only the substitute curricular assignment.
- Reversing a completed substitute block requires explicit confirmation.
- Submitted or approved weekly timesheets block decisions, revisions, and reversals for the affected teachers.
- The normal summary route cannot change the state of a lesson with an active occurrence decision. Text edits keep the decision.
- `GIVEN → GAP` and `GIVEN → SUBSTITUTED` compensate the original execution in the same transaction.
- A gap compensated by `GIVEN` creates a new debt claim on the next `GAP` cycle.
- A revoked occurrence can start a new pending cycle. The revocation audit stays on the row.
- The diagnostics endpoint explains each excluded candidate with a structured reason and a setup path.

## States and Transitions

`OPEN_PENDING` -> `DECIDED_GIVEN`, `DECIDED_GAP`, `DECIDED_SUBSTITUTED`, or `REVOKED`.
A `DECIDED_SUBSTITUTED` occurrence has its own execution state: `PENDING_LOG` or `COMPLETED`.
A completed substitution can only be re-decided through a confirmed reversal.
`GIVEN -> GAP` and `GAP -> GIVEN` are allowed while the week is open. `SUBSTITUTED -> GIVEN` stays rejected.

## Failure Modes

- A future lesson returns `422 lesson_not_finished`.
- A stale version returns `409`.
- A closed weekly timesheet returns `409 week_locked` without changes.
- A completed substitute block without confirmation returns `409 SUBSTITUTE_LOG_LOCKED`.
- An invalid or unavailable substitute returns `409` with the first exclusion reason.
- No eligible substitute returns an empty recommendation list and a diagnostic with reasons.
- A summary route that tries to change a decided occurrence returns `409 occurrence_active`.

## Solver Integration

A planned substitution occupies the substitute teacher, the room, and the class
in its period. It consumes the substitute subject demand while it is pending.
The scheduler snapshot includes these reservations and the planned minutes in
its fingerprint. Completion moves the minutes to the execution ledger; the
snapshot must not count them twice.

## Verification Procedure

1. Open `/absences` as an administrator.
2. Create an occurrence from a block and confirm that the debt list stays empty.
3. Decide `GAP` and confirm the debt claim.
4. Decide `SUBSTITUTED` and confirm the planned block without execution.
5. Conclude the substitute lesson after its end instant.
6. Verify the substitute credit and the original debt.
7. Revert the occurrence and verify the compensation entries.

## Source Map

- `backend/app/api/v1/endpoints/occurrences.py`
- `backend/app/services/occurrence_service.py`
- `backend/app/scheduler/infrastructure/occurrences.py`
- `backend/app/scheduler/infrastructure/operations.py`
- `backend/app/models.py`
- `frontend/src/pages/Occurrences.jsx`
- Tests: `backend/tests/unit/test_occurrence_transition_plan.py`, `backend/tests/integration/committed/test_occurrence_accounting.py`, `backend/tests/integration/committed/test_scheduler_v1_occurrences.py`

## Related Documents

- [Lesson Execution](LESSON_EXECUTION.md)
- [Scheduler Engine](../03_scheduler_engine/README.md)
