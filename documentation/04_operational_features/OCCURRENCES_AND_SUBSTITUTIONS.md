# Occurrences and Substitutions

## Purpose

This document describes absences (*Faltas*), occurrence revisions, and substitutions (*Substituições*).

## Intended Reader

This document targets backend engineers, frontend engineers, and school administrators.

## Prerequisites

Read [Lesson Execution](LESSON_EXECUTION.md) and [Scheduler Engine](../03_scheduler_engine/README.md).

## What the System Does

Cronos creates an occurrence from an active schedule block when a lesson needs an operational decision.
An administrator can mark it given, gap, substituted, or revoked through versioned operations.

## Why the Behavior Exists

Occurrence revisions preserve the original planned block and the latest decision.
Operational blocks separate cover work from the curriculum schedule.

## Components and Ownership

| Responsibility | Implementation |
| :--- | :--- |
| API | `backend/app/api/v1/endpoints/occurrences.py` |
| Domain service | `backend/app/services/occurrence_service.py` |
| Recovery and progress | `backend/app/scheduler/infrastructure/progress.py` |
| Models | `LessonOccurrence`, `OperationalScheduleBlock` |
| UI | `frontend/src/pages/Occurrences.jsx` |

## Data or Request Flow

1. An administrator creates an occurrence from an active block.
2. The API stores an open, versioned occurrence.
3. The administrator chooses `GIVEN`, `GAP`, or `SUBSTITUTED`.
4. Substitution requires a linked teacher and subject.
5. The service creates or updates an operational block.
6. Recovery and progress services record the resulting minutes.

## Contracts and Invariants

- The API state is `OPEN_PENDING`, `DECIDED_GIVEN`, `DECIDED_GAP`, `DECIDED_SUBSTITUTED`, or `REVOKED`.
- The database status values are `GIVEN`, `GAP`, `SUBSTITUTED`, and `REVOKED`.
- A normal update cannot submit `REVOKED`; use the cancel endpoint.
- A substituted decision requires both substitute IDs.
- A decision includes the expected occurrence version.
- A substitute block uses the occurrence revision that created it.

## States and Transitions

`OPEN_PENDING` -> `DECIDED_GIVEN`, `DECIDED_GAP`, `DECIDED_SUBSTITUTED`, or `REVOKED`.
The API can revise a decided occurrence while the revision remains active.

## Failure Modes

- A stale version returns a conflict.
- An invalid substitute returns a validation error.
- No eligible substitute returns an empty recommendation list.
- A duplicate active occurrence is rejected or reused by service rules.

## Verification Procedure

1. Open `/absences` as an administrator.
2. Create an occurrence from a block.
3. Inspect recommendations.
4. Decide `GAP` or `SUBSTITUTED`.
5. Verify the active revision and operational block.

## Source Map

- `backend/app/api/v1/endpoints/occurrences.py`
- `backend/app/services/occurrence_service.py`
- `backend/app/scheduler/infrastructure/progress.py`
- `backend/app/models.py`
- `frontend/src/pages/Occurrences.jsx`
- Tests: `backend/tests/unit/test_occurrence_transition_plan.py`, `backend/tests/integration/committed/test_occurrence_accounting.py`, `backend/tests/integration/committed/test_scheduler_v1_occurrences.py`

## Related Documents

- [Lesson Execution](LESSON_EXECUTION.md)
- [Scheduler Engine](../03_scheduler_engine/README.md)
