# Scheduler Hard Constraints and Soft Objectives

## Current authority

This document describes the implemented `baseline-v1` quality policy and the
hard-validity boundary used by Complete Generation, Adaptive Repair, runtime
validation, and approval. The PRD and technical specification remain the product
and architecture authorities.

## Hard constraints

Every persisted or approved target must satisfy all of the following:

- school-year, calendar, timetable-grid, and editable-boundary rules;
- class, teacher, and room interval exclusivity;
- class-subject assignment and teacher qualification;
- room capacity and required room type;
- impossible teacher availability;
- aggregate contiguous lunch breaks for every class and teacher;
- recovery lineage and debt limits;
- the four supported custom rules.

Custom-rule semantics are:

| Rule | Meaning |
|---|---|
| `specific_room` | A class-subject placement uses one of the listed rooms. |
| `lock_time` | A class-subject placement uses one of the listed timetable slots. |
| `teacher_unavailable` | The selected teacher cannot match the configured slot, weekday, date, or exact date-plus-slot selector. |
| `teacher_preferred` | Soft preference only; it raises availability by one tier, capped at preferred. |

Multiple room or time rules form allowed-value unions. Deadline Rescue never
relaxes a hard constraint. Runtime and approval rebuild and invoke the shared
pure target validator independently.

## `baseline-v1` soft quality policy

The standard block is the lower median positive configured slot duration.
Healthy class and teacher daily load is four standard blocks; healthy consecutive
load is three; healthy recovery stacking is two.

The final-target evaluator reports duration-weighted daily excess, consecutive
excess, late-slot minutes, repeated heavy days per ISO week, recovery stacking,
class and teacher gaps with lunch credit, availability disutility, room
inconsistency, completion spread, and per-mille class progress fairness.

Complete Generation preserves lexicographic priority: scheduled demand first,
then completion, fairness, workload, gaps/availability, room consistency, and a
stable deterministic tie break. A lower stage may not weaken a fixed higher
stage.

Adaptive Repair uses three workload modes:

- `QUALITY_ONLY` for scheduler-change-only repair;
- `PROTECT_COMFORT` for recovery levels 1–4, preventing new or worsened daily
  overload relative to the healthy limit or published baseline;
- `DEADLINE_RESCUE`, which removes only the comfort bound.

When Deadline Rescue actually crosses that protected bound, the draft records
`workload_override_used`, overload counts/minutes, and the warning
`DEADLINE_RESCUE_WORKLOAD_OVERRIDE`.

## Compatibility

New constraint writes accept only the four canonical rule types. Historical
`min_gap`, `max_days`, aliases, and malformed stored rows remain readable and
deletable, but generation preflight rejects an incompatible stored configuration.
Historical draft quality fields default safely to zero or `null`.
