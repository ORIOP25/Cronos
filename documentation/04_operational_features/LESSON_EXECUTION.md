# Lesson Execution

## Purpose

This document describes lesson logs (*Sumários*) for published v1 lessons and operational substitute blocks.

## Intended Reader

This document targets frontend and backend engineers.

## Prerequisites

Read [Professional Education](../02_domain_model/PROFESSIONAL_EDUCATION.md) and [Routes and Permissions](../06_frontend_ux/ROUTES_AND_PERMISSIONS.md).

## What the System Does

Teachers and administrators record execution status, summary text, and notes.
The API stores one lesson log for the block target and updates progress evidence through services.

## Why the Behavior Exists

The planned block and execution record have different meanings.
Separating them preserves schedule history and supports occurrence decisions.

## Components and Ownership

| Responsibility | Implementation |
| :--- | :--- |
| API | `backend/app/api/v1/endpoints/schedule.py` |
| Service | `backend/app/scheduler/infrastructure/operations.py` |
| Models | `SchedulerLessonLogV1`, `CurricularExecution`, `CurricularExecutionCredit`, and operational-block `LessonLog` |
| UI | `frontend/src/components/LessonLogModal.jsx`, `frontend/src/components/WeekGrid.jsx` |

## Data or Request Flow

1. The teacher opens `/my-schedules`.
2. The frontend loads `/api/v1/schedule/week`.
3. The teacher selects an eligible block.
4. The frontend sends a `PUT` request to the lesson or operational-block log endpoint.
5. The service validates ownership, week state, and time rules.
6. The service stores the log and related ledger changes.

The write endpoints are `/api/v1/schedule/operational-blocks/{id}/log` and `/api/v1/schedule/lessons/{lesson_id}/log`.
Both use `PUT` and return a lesson log. The operational-block route requires a `V1` origin and uses the v1 ledger.

## Contracts and Invariants

- Lesson log status is `PENDING`, `COMPLETED`, or `OCCURRENCE`.
- Summary text has a maximum length of 2,000 characters.
- Notes have a maximum length of 1,000 characters.
- Teachers can edit only blocks assigned to their linked profile.
- Administrators can edit tenant blocks.
- An operational block cannot produce a new occurrence.
- Submitted or approved weekly timesheets block later edits.
- Execution is registered only when `now_utc >= ends_at_utc`.
- A lesson before its end instant returns `422 lesson_not_finished` and persists no effect.
- The weekly read exposes `ends_at`, `can_complete`, and `blocked_reason` per slot.
- A planned substitution exposes `substitute_execution_status` and `block_source="operational"`.
- The normal summary route cannot change the state of a lesson with an active occurrence decision.
- An open week guard blocks creation, completion, and reversal with `409 week_locked`.

## States and Transitions

`PENDING` -> `COMPLETED` or `OCCURRENCE`.
An occurrence log creates or reuses an active occurrence.
A completed log credits the executed block through the progress service.
Completing a `V1` operational block credits the substitute curricular assignment once.

## Failure Modes

- A future block cannot be marked completed before its timeslot ends.
- A teacher cannot update another teacher's block.
- An inactive block returns not found.
- A closed week rejects changes.
- A completed substitution block needs an explicit reversal confirmation.

## Verification Procedure

1. Sign in with a linked teacher.
2. Open `/my-schedules`.
3. Open an eligible past block.
4. Save `COMPLETED` with a summary.
5. Verify the log and progress response.

## Source Map

- `backend/app/api/v1/endpoints/schedule.py`
- `backend/app/scheduler/infrastructure/operations.py`
- `backend/app/models.py`
- `frontend/src/components/LessonLogModal.jsx`
- Tests: `frontend/src/test/MySchedules.test.jsx`, `frontend/src/test/WeekGrid.test.jsx`, `frontend/src/test/weekSubmission.test.js`

## Related Documents

- [Occurrences and Substitutions](OCCURRENCES_AND_SUBSTITUTIONS.md)
- [Timesheets and Progress](TIMESHEETS_AND_PROGRESS.md)
