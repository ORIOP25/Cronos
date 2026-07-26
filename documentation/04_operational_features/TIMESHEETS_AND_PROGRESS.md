# Timesheets and Progress

## Purpose
This document details teacher weekly timesheet submission, hour debt accounting, and course progress ledgers.

## Intended Reader
This document targets developers maintaining reporting and payroll metrics.

## Prerequisites
Read [Lesson Execution](LESSON_EXECUTION.md) and [Occurrences and Substitutions](OCCURRENCES_AND_SUBSTITUTIONS.md).

## What the System Does
Cronos aggregates daily lesson logs into weekly teacher timesheets (`TeacherWeeklyTimesheet`) and computes course progress statistics.

## Teacher Weekly Timesheet Lifecycle

| State | Description | Next State |
| :--- | :--- | :--- |
| `DRAFT` | Weekly timesheet accumulating daily lesson logs | `SUBMITTED` |
| `SUBMITTED` | Teacher submits timesheet for administrative review | `APPROVED`, `REJECTED` |
| `APPROVED` | Administrator approves timesheet for payroll | None (Terminal) |
| `REJECTED` | Returned to teacher for summary corrections | `SUBMITTED` |

## Hour Debt Calculation
Hour debt (*Dívida de Horas*) occurs when scheduled lessons are missed (`GAP`):
- **Teacher Debt**: Missed hours owed by a teacher due to unexcused absence.
- **Class Debt**: Missed curriculum hours required by a class cohort to complete a module.

The system displays debt statistics on the administrative Command Center Dashboard (`/dashboard`).

## Contracts and Invariants
- Submitting a timesheet requires all past weekly blocks to have explicit status (`GIVEN`, `GAP`, `SUBSTITUTED`, or `CANCELLED`).

## Failure Modes
- Unlogged Blocks Pending: Submitting a timesheet with unlogged past blocks returns HTTP `400 Bad Request`.

## Verification Procedure
Navigate to `/timesheets`. Inspect teacher weekly hour totals, pending summaries, and approval status buttons.

## Source Map
- Timesheet Router: `backend/app/api/v1/endpoints/timesheets.py`
- Models: `backend/app/models.py` (`TeacherWeeklyTimesheet`, `ProgressLedgerEntry`)
- Frontend Page: `frontend/src/pages/Timesheets.jsx`

## Related Documents
- [Lesson Execution](LESSON_EXECUTION.md)
- [Occurrences and Substitutions](OCCURRENCES_AND_SUBSTITUTIONS.md)
