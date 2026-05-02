# Zen Scheduler Skill

> ⚠️ **IMPORTANT**: This skill REQUIRES `.agents/skills/SKILL_BASE.md` to be loaded first.
> The base skill contains shared rules (4 pillars, delivery protocol, documentation workflow, safety rules).
> Always load SKILL_BASE.md + this skill together.

You are the scheduling engine expert for Horario Zen, operating under **Solver V2**.

## 1. Solver V2 Baseline
- **Rolling Window**: Hybrid horizon. Principal rolling window of 8 weeks + validation of feasibility up to the absolute `hard_end_date`.
- **Target vs Hard End Date**: The `target_end_date` is a soft objective. The `school_hard_end_date` is absolute (no classes allowed after it).
- **Single Backlog**: There is a single backlog of hours to allocate. Overdue and non-overdue debt are treated the same.

## 2. Hard Constraints (Inviolable)
1. No teacher conflicts.
2. No class conflicts.
3. No room conflicts.
4. Required room type must match subject requirement.
5. `IMPOSSIBLE` availability slots are forbidden.
6. Lunch constraints are hard when configured.
7. Absolute hard end date.

## 3. Soft Objectives (V2)
The solver optimizes following a strict hierarchy:
1. **Makespan Global**: Minimize drift from `school_target_end_date` (minimize global end date).
2. **End Date Spread**: Improve fairness between classes (reduce dispersion).
3. **Target Drift**: Reduce total deviation from school target end date.
4. **Churn**: Minimize churn outside the frozen window (secondary).
5. **Gaps**: Reduce gaps (furos) for classes and teachers as the last priority.
- **Repair Mode**: Keep stability in repair mode when possible.

**Hard constraints always win over soft goals.**

## 4. Draft Lifecycle
1. `POST /api/v1/schedule/generate` generates a draft without violating hard constraints.
2. Pending draft blocks new generation.
3. Approval uses a statistical panel rather than mandatory lesson-by-lesson review.
4. Rejecting the draft removes it completely without side effects on the published plan.

## 5. Key Files
- `app/core/solver_engine_v2.py` — V2 lexicographic engine (CP-SAT)
- `app/core/solver_v2_candidates.py` — Candidate universe + pruning
- `app/core/solver_v2_expansion.py` — Weekly pattern → absolute dates + fill-opportunistic
- `app/solver_tasks.py` — Celery task orchestrator (FETCH → SOLVE → EXPAND → SAVE)
- `app/services/schedule_service.py` — Draft lifecycle + sync helpers
