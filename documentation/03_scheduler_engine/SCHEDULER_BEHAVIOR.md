# Scheduler Behavior

## Purpose
This document specifies the operational behavior, constraint rules, and optimization objectives of the Solver V2 engine.

## Intended Reader
This document targets scheduler engineers, backend developers, and QA automation engineers.

## Prerequisites
Read [Professional Education](../02_domain_model/PROFESSIONAL_EDUCATION.md).

## What the System Does
The Cronos scheduler engine generates optimal weekly timetables using Google OR-Tools CP-SAT solver. The engine operates in two distinct modes:

1. **Full Generation Mode (`full`)**: Computes a complete timetable from scratch for all active classes, subjects, teachers, and rooms.
2. **Adaptive Repair Mode (`repair`)**: Re-optimizes unexecuted future slots while preserving frozen past blocks and past logged lessons.

## Hard Constraints vs. Soft Objectives

### Mandatory Hard Constraints
The solver must satisfy all hard constraints. If a hard constraint fails, the solver returns `Impossible` status:

| Constraint Name | Description | Violation Consequence |
| :--- | :--- | :--- |
| **No Teacher Overlap** | A teacher cannot teach two classes simultaneously | Impossible solution |
| **No Class Overlap** | A class cannot attend two subjects simultaneously | Impossible solution |
| **No Room Overlap** | A room cannot host two classes simultaneously | Impossible solution |
| **Teacher Availability** | Lessons can only occur during teacher available slots | Impossible solution |
| **Room Type Match** | Lab subjects require laboratory rooms | Impossible solution |
| **Max Daily Workload** | Teacher/Class daily hours cannot exceed max daily limits | Impossible solution |

### Soft Optimization Objectives
The solver minimizes penalty scores for soft objectives to maximize timetable quality:

| Objective Name | Target Preference | Penalty Weight |
| :--- | :--- | :--- |
| **Minimize Student Gaps** | Avoid idle gaps between daily class lessons | High |
| **Minimize Teacher Gaps** | Compact teacher daily schedules | Medium |
| **Teacher Preferences** | Honor preferred working hours | Medium |
| **Balanced Distribution** | Distribute subject hours evenly across week days | Low |

## Contracts and Invariants
- Full generation invalidates previous unapproved drafts.
- Adaptive repair preserves past executed blocks (`GIVEN`, `SUBSTITUTED`).

## Failure Modes
- Unfeasible Model: Conflicting hard constraints (e.g., insufficient rooms) trigger `Impossible` status with detailed diagnostic logs.

## Verification Procedure
Execute `python simulate_user.py` or POST to `/api/v1/scheduler/generate`. Inspect response task status.

## Source Map
- Solver Model: `backend/app/core/solver.py`
- Constraints Module: `backend/app/services/scheduler_constraints.py`

## Related Documents
- [Scheduler Architecture](SCHEDULER_ARCHITECTURE.md)
- [Scheduler Operations](SCHEDULER_OPERATIONS.md)
