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
- **Frozen Horizon Window**: Past schedule blocks and blocks occurring within a configurable short-term window (e.g., next 48 hours) are **frozen**.
- The solver cannot move, delete, or alter frozen schedule blocks.
- Unexecuted future blocks beyond the frozen horizon can be re-allocated.

## Draft Diff Auditing
Before approving a repair draft, administrators inspect statistical diffs via `GET /api/v1/scheduler/drafts/{id}/diff`:

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
If total module hours cannot fit before the academic year end date, remaining hours move to **Backlog**. The repair summary displays remaining backlog hours requiring weekend or extra shift allocation.

## Failure Modes and Recovery Runbook

| Failure Symptom | Cause | Recovery Action |
| :--- | :--- | :--- |
| **Solver Status IMPOSSIBLE** | Over-constrained availability | Relax teacher availability or assign backup teacher |
| **High Backlog Hours** | Insufficient term calendar days | Extend school year end date in `/config` |
| **Stuck Job Status** | Celery worker crash | Run job cancellation endpoint `POST /scheduler/jobs/{id}/cancel` |

## Verification Procedure
Execute `python simulate_user.py`. The script runs a full schedule generation, injects occurrences, runs a repair generation, and audits the diff.

## Source Map
- Repair Logic: `backend/app/services/repair_service.py`
- Diff Engine: `backend/app/services/diff_service.py`
- Ops Runbook: `documentation/09_ops_observability/OBSERVABILITY_AND_RECOVERY.md`

## Related Documents
- [Scheduler Behavior](SCHEDULER_BEHAVIOR.md)
- [Occurrences and Substitutions](../04_operational_features/OCCURRENCES_AND_SUBSTITUTIONS.md)
