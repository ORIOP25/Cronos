# Scheduler Operations

## Purpose
This document specifies operational workflows for schedule repair, frozen horizons, draft diff auditing, and backlog recovery.

## Intended Reader
This document targets site reliability engineers, support teams, and system administrators.

## Prerequisites
Read [Scheduler Architecture](SCHEDULER_ARCHITECTURE.md).

## What the System Does
When disruptions occur during the academic year (e.g., long-term teacher sick leave), Cronos computes adaptive schedule repairs without discarding past execution history.

## Frozen Horizon Rules
- **Frozen Horizon Window**: Past blocks and blocks before the computed editable start date are immutable.
- Blocks with `COMPLETED` or `OCCURRENCE` lesson logs are immutable.
- The solver cannot move, delete, or alter frozen schedule blocks.
- Unexecuted future blocks beyond the frozen horizon can be re-allocated.

## Draft Diff Auditing
Before approving a repair draft, administrators inspect persisted diffs via `GET /api/v1/scheduler/drafts/{id}/diff`:

```text
+--------------------------------------+--------------------+
| REPAIR DRAFT COMPARISON              | VALUE              |
+--------------------------------------+--------------------+
| Added Blocks                         | 14                 |
| Removed Blocks                       | 14                 |
| Unchanged Blocks                     | 112                |
| Projected End Date Delta (Days)      | +2 Days            |
| Gap Variation Metric                 | -3 Gaps            |
+--------------------------------------+--------------------+
```

## Backlog Management
The engine reports residual debt when a repair cannot recover all required minutes before the hard end date. The draft stores blocker data and recommendations.

## Failure Modes and Recovery Runbook

| Failure Symptom | Cause | Recovery Action |
| :--- | :--- | :--- |
| **Job Status NO_VALID_OUTPUT** | Candidate or solve constraints block output | Inspect blocker metadata and recommended actions |
| **High Backlog Hours** | Capacity cannot recover all debt | Review blockers, resources, and school-year dates |
| **Stuck Job Status** | Worker interruption | Request cancellation with `POST /api/v1/scheduler/jobs/{id}/cancel` |
| **Timed-out Adaptive Job** | Construction or search used the solve budget | Inspect phase durations, candidate count, and solver status |

## Deadline Diagnostics

Inspect `construction_duration_ms`, `solve_duration_ms`, `candidate_count`, and `solver_status`.
Inspect feasibility status, quality stage, and independent validation timing when present.
When present, inspect `draft_persistence_duration_ms`, `variable_count`, `constraint_count`,
`quality_scope`, and `residual_repair_status`. Missing phases intentionally have no fabricated
zero timing.
The job cap remains 300 seconds. Runtime reserves engine return time and final persistence time.
Do not increase the cap to handle candidate growth.

`SEARCH_EXHAUSTED` does not prove annual infeasibility. Retry with changed capacity or dates.
Protected assignment removal identifies the class, subject, and immutable block.
Approval repeats debt identity checks against current tenant-scoped data.

## Verification Procedure
Run scheduler change, disruption, diff, and recovery tests from `backend/tests/`. Inspect one generated draft through the API.

## Source Map
- Repair Logic: `backend/app/services/scheduler_adaptive_engine.py`, `backend/app/services/scheduler_editable_boundary.py`
- Diff Engine: `backend/app/services/scheduler_diff_service.py`
- Ops Runbook: `documentation/09_ops_observability/OBSERVABILITY_AND_RECOVERY.md`

## Related Documents
- [Scheduler Behavior](SCHEDULER_BEHAVIOR.md)
- [Occurrences and Substitutions](../04_operational_features/OCCURRENCES_AND_SUBSTITUTIONS.md)
