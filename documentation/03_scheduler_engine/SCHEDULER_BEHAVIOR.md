# Scheduler Behavior

## Purpose
This document specifies the operational behavior, constraint rules, and optimization objectives of the Solver V2 engine.

## Intended Reader
This document targets scheduler engineers, backend developers, and QA automation engineers.

## Prerequisites
Read [Professional Education](../02_domain_model/PROFESSIONAL_EDUCATION.md).

## What the System Does
The Cronos scheduler generates dated schedules with Google OR-Tools CP-SAT. The lifecycle selects one of two strategies:

1. **Complete Generation (`COMPLETE_GENERATION`)**: Places all remaining demand before the hard end date for an unpublished school year.
2. **Adaptive Repair (`ADAPTIVE_REPAIR`)**: Repairs explicit debt or scheduler-relevant changes after publication.

## Hard Constraints vs. Soft Objectives

### Mandatory Hard Constraints
The solver must satisfy all hard constraints. Conflicting constraints can prevent valid output:

| Constraint Name | Description | Violation Consequence |
| :--- | :--- | :--- |
| **No Teacher Overlap** | A teacher cannot teach two classes simultaneously | Invalid selection |
| **No Class Overlap** | A class cannot attend two subjects simultaneously | Invalid selection |
| **No Room Overlap** | A room cannot host two classes simultaneously | Invalid selection |
| **Teacher Availability** | `IMPOSSIBLE` availability excludes a candidate | Candidate removed |
| **Room Type Match** | Candidate rooms must match the subject room type | Candidate removed |
| **Explicit Constraints** | Specific-room, locked-time, and unavailable rules restrict candidates | Candidate removed |
| **Lunch Break** | The configured lunch rule influences candidate validation and quality | Invalid selection |

### Soft Optimization Objectives
The solver minimizes penalty scores for soft objectives to maximize timetable quality:

| Objective Name | Target Preference | Penalty Weight |
| :--- | :--- | :--- |
| **Curriculum Coverage** | Place required demand before the hard end date | Hard target |
| **Completion Date** | Reduce projected completion date and spread | Quality metric |
| **Workload Quality** | Reduce daily, consecutive, late, and recovery excess | Quality metric |
| **Gaps and Availability** | Reduce gaps and availability disutility | Quality metric |
| **Room Consistency** | Reduce room changes for class and subject | Quality metric |

## Contracts and Invariants
- Generation requires explicit confirmation before replacing a pending draft.
- Adaptive repair preserves past blocks, completed or occurrence logs, and the stability window.
- Published state requires an approved scheduler state version.
- `IMPOSSIBLE` availability removes a candidate; `PREFERRED`, `NEUTRAL`, and `AVOID` affect quality.

## Failure Modes
- No Valid Output: Candidate or solve failure records `NO_VALID_OUTPUT` with blocker metadata and recommendations.

## Verification Procedure
Run scheduler tests or POST to `/api/v1/scheduler/generate`. Poll `/api/v1/scheduler/jobs/{job_id}`.

## Source Map
- Complete Engine: `backend/app/services/scheduler_complete_engine.py`
- Adaptive Engine: `backend/app/services/scheduler_adaptive_engine.py`
- Constraint Policy: `backend/app/scheduler/domain/constraints.py`
- Quality Policy: `backend/app/scheduler/domain/quality.py`

## Related Documents
- [Scheduler Architecture](SCHEDULER_ARCHITECTURE.md)
- [Scheduler Operations](SCHEDULER_OPERATIONS.md)
