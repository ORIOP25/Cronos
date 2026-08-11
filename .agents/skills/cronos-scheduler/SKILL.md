---
name: cronos-scheduler
description: Specialist solver engine skill for Cronos. Use when working on Google OR-Tools CP-SAT models, schedule generation jobs, repair workflows, or draft diffs.
argument-hint: Requires cronos-base.
---

# Cronos Scheduler Skill

> ⚠️ **IMPORTANT**: Load `.agents/skills/cronos-base/SKILL.md` before using this skill.

You are the scheduling engine architect for Cronos.

## Engine Guidelines
- **Solver Engine**: Google OR-Tools CP-SAT, with complete generation and adaptive repair services.
- **Execution Modes**: The API selects `COMPLETE_GENERATION` or `ADAPTIVE_REPAIR` from school-year state.
- **Frozen Horizon**: Repair preserves past blocks and blocks before the computed editable boundary.
- **Draft Promotion**: Approval promotes draft blocks and reconciles recovery links in one transaction.

## Relevant Documentation
- [Scheduler Behavior](../../../documentation/03_scheduler_engine/SCHEDULER_BEHAVIOR.md)
- [Scheduler Architecture](../../../documentation/03_scheduler_engine/SCHEDULER_ARCHITECTURE.md)
- [Scheduler Operations](../../../documentation/03_scheduler_engine/SCHEDULER_OPERATIONS.md)
