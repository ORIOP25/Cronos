# Occurrences and Substitutions

## Purpose

This document describes absences (*Faltas*), occurrence decisions, and substitutions (*Substituições*).

## Intended Reader

This document targets backend engineers, frontend engineers, and school administrators.

## Prerequisites

Read [Lesson Execution](LESSON_EXECUTION.md) and [Scheduler Engine](../03_scheduler_engine/README.md).

## What the System Does

Cronos records an occurrence on a published v1 lesson log when a lesson needs an operational decision.
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
| Scheduler v1 consumer | `backend/app/scheduler/infrastructure/occurrences.py` |
| Substitute execution | `backend/app/scheduler/infrastructure/operations.py` |
| Models | `SchedulerLessonLogV1`, `OperationalScheduleBlock`, and the v1 curricular ledger |
| UI | `frontend/src/pages/Occurrences.jsx` |

Routes under `/api/v1/occurrences`: `GET /` (list), `GET /debts`, `GET /{id}`, `PATCH /{id}` (decision), and `POST /{id}/cancel`.
Substitute routes are `GET /{id}/substitutes/recommendations` and `GET /{id}/substitutes/diagnostics`.
Create a v1 occurrence through the scheduled lesson workflow. There is no standalone create or general substitute listing route.

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
- Debt totals use the active school year timezone for `as_of_date` and overdue classification.
- An open claim is overdue when its origin date is on or before that school date.
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
- The weekly projection reports a revoked lesson log as `PENDING`, with its occurrence state preserved as `REVOKED`.
- Premature historical `COMPLETED` logs appear as `GIVEN` when `logged_at` precedes the lesson end.
- This projection does not invent a historical decision or change the ledger.
- A reversal follows source lessons across published versions and compensates the original execution origin.
- A reversal cancels debt after reversing execution, including reopened settlements from historical provisional claims.
- Debt claims follow source lessons across published versions. Each claim contributes only its remaining balance to debt totals.
- Repeating cancellation can reconcile residual historical debt in an open week. It preserves revocation metadata and adds only needed debt revisions.
- Valid completed lessons without an occurrence decision stay outside occurrence history.
- An internship flow withdraws its lessons and records a `GAP` decision for each. Withdrawn-lesson absences stay listed after a new schedule version.
- A withdrawn lesson accepts only a `GAP` decision; any other decision returns `409`.
- The diagnostics endpoint explains each excluded candidate with a structured reason and a setup path.
- The list groups the sibling logs of a joint lesson into one card. Each item carries `joint_lesson.classes` with `class_id`, `class_name`, `operational_state`, `status`, `version`, and `id` per member class.
- `PATCH /api/v1/occurrences/{id}` accepts `class_ids`. The decision applies to those member classes in one transaction after locking every sibling log by `id`. By default it applies only to the indicated line.
- `GIVEN` and `GAP` can be decided per class. `SUBSTITUTED` applies to every member class and requires every sibling to be a pending occurrence; a completed or already decided sibling returns `409`.
- The payload `version` references the clicked line. Each sibling is decided at its own locked revision, so a joint decision never leaves a partial set.
- A joint substitute must give a subject whose joint group has exactly the same member classes, whose next residual unit for each class is that joint segment, with enough joint residual for the lesson credit. The new exclusions are `joint_classes_mismatch`, `joint_not_in_progress`, and `joint_in_progress` on a single-class lesson.
- Planning a joint substitution creates one operational block per member class. Concluding one block concludes the whole joint substitution. `absent_class_ids` cancels an absent class's block without credit, and every present class receives the same joint-frontier credit.
- An internship flow withdraws every sibling of a joint lesson and records a `GAP` for each: `Turma em estágio` on the blocked class and `Aula conjunta retirada por estágio de {turma}` on the others.

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
8. Use `Reconciliar dívida` on a reverted occurrence with historical residue.
9. Verify that debt closes while revocation metadata and history remain unchanged.

## Source Map

- `backend/app/api/v1/endpoints/occurrences.py`
- `backend/app/scheduler/infrastructure/occurrences.py`
- `backend/app/scheduler/infrastructure/operations.py`
- `backend/app/models.py`
- `frontend/src/pages/Occurrences.jsx`
- Tests: `backend/tests/integration/committed/test_scheduler_v1_occurrences.py`, `backend/tests/integration/committed/test_scheduler_v1_operations.py`, `backend/tests/integration/committed/test_joint_lesson_occurrences.py`, `backend/tests/integration/committed/test_joint_lesson_internship.py`

## Related Documents

- [Lesson Execution](LESSON_EXECUTION.md)
- [Scheduler Engine](../03_scheduler_engine/README.md)
