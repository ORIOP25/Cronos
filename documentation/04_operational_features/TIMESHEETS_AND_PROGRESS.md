# Timesheets and Progress

## Purpose

This document describes weekly teacher timesheets, progress ledger accounting, debt, and recovery delivery.

## Intended Reader

This document targets backend engineers, frontend engineers, and reporting owners.

## Prerequisites

Read [Lesson Execution](LESSON_EXECUTION.md) and [Occurrences and Substitutions](OCCURRENCES_AND_SUBSTITUTIONS.md).

## What the System Does

Cronos creates a weekly timesheet for a linked teacher.
It validates lesson coverage before submission and exposes approval actions to administrators.

Progress views aggregate append-only completed and debt minute deltas.
The teacher progress view uses the same v1 execution and open-debt projection as the class dashboard when curricular assignments exist.
Schools without v1 assignments retain the legacy ledger projection.
Progress displays hours rounded to one decimal; debt endpoints retain exact minute totals expressed as hours.

## Why the Behavior Exists

Weekly closure prevents later changes to reviewed execution.
Ledger entries preserve idempotent evidence for progress and recovery.

## Components and Ownership

| Responsibility | Implementation |
| :--- | :--- |
| Timesheet API | `backend/app/api/v1/endpoints/timesheets.py` |
| Timesheet service | `backend/app/services/timesheet_service.py` |
| Progress services | `backend/app/services/teacher_service.py`, `class_service.py`, `backend/app/scheduler/infrastructure/progress.py` |
| Ledger model | `backend/app/models.py` (`ProgressLedgerEntry`) |
| UI | `frontend/src/pages/Timesheets.jsx`, `MyProgress.jsx` |

Routes under `/api/v1/timesheets`: `GET /` (admin list), `GET /me/{week_start_date}`, `POST /me/{week_start_date}/submit` and `PATCH /{timesheet_id}/status` (approve or reopen). The submit route validates lesson coverage itself; there is no separate pending-occurrences route.

## Data or Request Flow

1. A teacher opens `/my-schedules` or `/timesheets`.
2. The API loads the week and creates a record when needed.
3. The teacher records all eligible blocks.
4. The teacher submits the week.
5. An administrator approves or reopens the week.
6. Progress and debt views read ledger and occurrence data.

## Contracts and Invariants

- Timesheet status is `OPEN`, `SUBMITTED`, or `APPROVED`.
- Submission requires a linked teacher and a valid week.
- Missing or `PENDING` lesson logs block submission.
- Active v1 substitute blocks count in the teacher week.
- A planned substitution blocks submission until its lesson is completed.
- Future blocks do not satisfy week closure.
- Approval sets approver identity and freezes later edits.
- Reopening returns the week to `OPEN`.
- [The timesheet service](../../backend/app/services/timesheet_service.py) rejects invalid transitions with a Portuguese message showing the source and target states.
- Ledger entries require non-zero deltas and unique idempotency keys.

## States and Transitions

`OPEN` -> `SUBMITTED` -> `APPROVED`.
An administrator can reopen `SUBMITTED` or `APPROVED` records to `OPEN`.

## Failure Modes

- An unlinked teacher cannot submit a timesheet.
- Missing logs return a validation error.
- A non-admin cannot approve or reopen a timesheet.
- A duplicate ledger source does not apply its delta twice.
- The operational dashboard and debt page use the same v1 occurrence ledger when a v1 schedule is active.
- Reversed settlements retain their history. Debt cancellation validates the remaining balance after all settlement reversals.

## Verification Procedure

The selected weekly admin view uses the active teacher roster. It includes teachers with no persisted timesheet as `OPEN` rows. Loading this view is read-only and does not create `teacher_weekly_timesheet` records.

1. Open `/timesheets` as an administrator.
2. Open a teacher week.
3. Submit a complete week as the teacher.
4. Approve and reopen the week as the administrator.
5. Inspect progress and debt totals.

## Source Map

- `backend/app/api/v1/endpoints/timesheets.py`
- `backend/app/services/timesheet_service.py`
- `backend/app/models.py`
- `frontend/src/pages/Timesheets.jsx`
- `frontend/src/pages/MyProgress.jsx`
- Tests: `backend/tests/integration/committed/test_module_progress.py`, `backend/tests/integration/committed/test_timesheets.py`, `backend/tests/integration/committed/test_timesheets_v1.py`, `frontend/src/test/weekSubmission.test.js`

## Related Documents

- [Lesson Execution](LESSON_EXECUTION.md)
- [Professional Education](../02_domain_model/PROFESSIONAL_EDUCATION.md)
