---
name: cronos-scheduler
description: Specialist solver engine skill for Cronos. Use when working on Google OR-Tools CP-SAT models, schedule generation jobs, repair workflows, or draft diffs.
argument-hint: Requires cronos-base.
---

# Cronos Scheduler Skill

> ⚠️ **IMPORTANT**: Load `.agents/skills/cronos-base/SKILL.md` before using this skill.

You are the scheduling engine architect for Cronos.

## Engine Guidelines
- **Solver Engine**: Google OR-Tools CP-SAT, with complete generation and adaptive recovery.
- **Strategies**: `SchedulingStrategy` in `backend/app/scheduler/domain/candidate.py` defines `COMPLETE_GENERATION` and `ADAPTIVE_RECOVERY`.
- **Frozen Lessons**: Repair keeps approved recovery reservations attached to frozen lessons.
- **Proposals**: Approval is atomic and revalidates the proposal. Rejection is audited.

## Relevant Documentation
- [Scheduler Engine](../../../documentation/03_scheduler_engine/README.md)
- [Scheduler V1 Tech Spec](../../../documentation/03_scheduler_engine/SCHEDULER_V1_TECH_SPEC_V2.md)
