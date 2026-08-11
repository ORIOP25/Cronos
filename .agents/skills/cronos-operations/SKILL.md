---
name: cronos-operations
description: Specialist operational workflow skill for Cronos. Use when working on lesson logs (Sumários), teacher absences (Faltas), substitutions, timesheets, or hour debt.
argument-hint: Requires cronos-base.
---

# Cronos Operations Skill

> ⚠️ **IMPORTANT**: Load `.agents/skills/cronos-base/SKILL.md` before using this skill.

You are the operational workflows engineer for Cronos.

## Domain Guidelines
- **Lesson Logs (*Sumários*)**: Teachers record `PENDING`, `COMPLETED`, or `OCCURRENCE` for active and operational blocks.
- **Occurrences and Absences (*Faltas*)**: Administrators decide `GIVEN`, `GAP`, or `SUBSTITUTED`, with revision and revoke support.
- **Teacher Timesheets**: Weekly records move through `OPEN`, `SUBMITTED`, and `APPROVED`.

## Relevant Documentation
- [Lesson Execution](../../../documentation/04_operational_features/LESSON_EXECUTION.md)
- [Occurrences and Substitutions](../../../documentation/04_operational_features/OCCURRENCES_AND_SUBSTITUTIONS.md)
- [Timesheets and Progress](../../../documentation/04_operational_features/TIMESHEETS_AND_PROGRESS.md)
