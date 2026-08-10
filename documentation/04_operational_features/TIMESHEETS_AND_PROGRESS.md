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
| `OPEN` | Weekly timesheet accepts lesson log changes | `SUBMITTED` |
| `SUBMITTED` | Teacher submits the resolved week | `APPROVED`, `OPEN` |
| `APPROVED` | Administrator approves and locks the week | `OPEN` |

## Hour Debt Calculation
Hour debt (*Dívida de Horas*) occurs when scheduled lessons are missed (`GAP`):
- **Curriculum Debt**: Planned module minutes not delivered by a `GAP` or substituted decision.
- **Recovery Delivery**: A completed recovery block reduces debt through ledger entries.

The system displays debt statistics on the administrative Command Center Dashboard (`/dashboard`).

## Contracts and Invariants
- Submitting requires at least one published block, no future blocks, and no missing or `PENDING` logs.
- Reopening clears approval fields but preserves the submission timestamp.

## Failure Modes
- Unlogged Blocks Pending: Submitting a week with missing or `PENDING` logs returns HTTP `400 Bad Request`.

## Verification Procedure
Navigate to `/timesheets`. Inspect teacher weekly hour totals, pending summaries, and approval status buttons.

## Source Map
- Timesheet Router: `backend/app/api/v1/endpoints/timesheets.py`
- Service: `backend/app/services/timesheet_service.py`
- Frontend Page: `frontend/src/pages/Timesheets.jsx`

## Related Documents
- [Lesson Execution](LESSON_EXECUTION.md)
- [Occurrences and Substitutions](OCCURRENCES_AND_SUBSTITUTIONS.md)
