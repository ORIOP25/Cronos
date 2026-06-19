# Historical - Solver V2 Adaptativo

## Status
This document is superseded.

The previous contents were removed because they described a legacy Solver V2
approach that conflicts with the new baseline, including:
- fixed 8-week rolling horizon behavior;
- target-end drift;
- backlog-as-normal-hours repair semantics;
- aggressive churn as an acceptable repair profile;
- rejected-draft deletion.

## Current Authority
Use these documents instead:
- `PRD_SCHEDULE_GENERATOR_NEW_BASELINE.md`
- `TECH_SPEC_SCHEDULE_GENERATOR_NEW_BASELINE.md`

## Current Rule
The new generator uses automatic strategy selection, draft-first publication,
generation input fingerprints, debt basis fingerprints, progressive
optimization with capacity-aware provisional far-future scheduling, and
operational-triggered Adaptive Repair.

This file remains only as a historical pointer so old links do not silently
resolve to obsolete implementation guidance.
