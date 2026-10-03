# Occurrence Reconciliation

## Purpose

This document describes the reconciliation procedure for occurrences, debts, and
substitutions created before the occurrence-decision correction.

## Intended Reader

This document targets backend engineers and school administrators with database
access.

## Prerequisites

Read [Occurrences and Substitutions](../04_operational_features/OCCURRENCES_AND_SUBSTITUTIONS.md)
and [Observability and Recovery](OBSERVABILITY_AND_RECOVERY.md).

## What the Procedure Does

The correction adds explicit decisions to v1 lesson logs and v1 origins to
operational blocks. The migration classifies nothing automatically.

The procedure inventories affected records, classifies them with evidence, and
applies explicit compensations. Each step is read-only until the operator
applies it.

## Why the Behavior Exists

Historical debt can be provisional. A debt row alone does not prove a decision.
A name or a balance is never sufficient evidence.

## Step 1: Inventory

Run the read-only queries for each organization.

```sql
SELECT id, lesson_id, status, decision, decided_at, revoked_at, revoked_reason
FROM scheduler_lesson_log_v1
WHERE organization_id = :organization_id
  AND (
    status IN ('OCCURRENCE', 'REVOKED', 'COMPLETED')
    OR decision IS NOT NULL
    OR revoked_at IS NOT NULL
    OR revoked_reason IS NOT NULL
  )
ORDER BY id;

SELECT id, assignment_id, origin, origin_revision, created_minutes, origin_date, reason
FROM curricular_debt
WHERE organization_id = :organization_id
  AND (origin LIKE 'lesson-occurrence:%' OR origin LIKE 'occurrence-debt:%')
ORDER BY id;

SELECT id, assignment_id, origin, revision, delta_minutes, author_membership_id, reason
FROM curricular_debt_revision
WHERE organization_id = :organization_id
ORDER BY id;

SELECT id, debt_id, execution_id, minutes, reversal_of_id
FROM curricular_debt_settlement
WHERE organization_id = :organization_id
ORDER BY id;

SELECT id, source_occurrence_id, source_occurrence_revision, origin_kind,
       source_v1_lesson_log_id, substitute_curricular_assignment_id, status, execution_status
FROM operational_schedule_block
WHERE organization_id = :organization_id
ORDER BY id;
```

A `COMPLETED` log without a decision is a candidate, not a proven decision.
The v1 normal lesson flow also produces `COMPLETED` logs, so classify those
records with additional evidence.

Record the counts and the referenced identifiers in the reconciliation
worksheet. Do not change data in this step.

## Step 2: Classify

Classify each occurrence with at least one evidence source.

| Evidence | Classification |
| :--- | :--- |
| Substitute execution credit exists on the substitute assignment | Substitution, preserve execution |
| Completed lesson log exists with an explicit decision or audit event | Given, preserve credit |
| Operational block exists without execution | Substitution planned, create the v1 link |
| Debt exists without other evidence | Ambiguous, keep open |

A substitution credit belongs to the substitute curricular assignment. It never
settles the original debt by itself. The original claim closes only through a
debt revision or a settlement on the same assignment.

Ambiguous records block the reconciliation close. Do not infer a decision from
the debt balance.

## Step 3: Apply Explicit Corrections

Apply one correction per record, with an audit reason and author.

1. Link existing operational blocks to their v1 origin when the source lesson
   and substitute assignment are provable.
2. Revise provisional debt of records proven pending with a negative debt
   revision and a distinct origin.
3. Preserve valid execution and settlements. Never edit earlier ledger rows.
4. Rebuild historic substitutions without crediting minutes twice.

Run the corrections inside one transaction per organization.

## Step 4: Verify

Repeat the Step 1 queries and compare results.

- The open debt of a pending occurrence is zero.
- A planned substitution has no execution credit.
- A concluded substitution keeps one credit and one settlement.
- Totals before and after explain every difference.

## Failure Modes

- Ambiguous records stop the procedure.
- A missing reference leaves the record open.
- A failed transaction changes nothing.
- A downgrade of migration 0018 is refused while any decision, revocation
  metadata, or v1 operational block exists.

## Known Residue

The report describes a synthetic TAS 10 future lesson decided as given and a
synthetic QA teacher. Revert the lesson through the corrected reversal flow.
Verify the 50-minute compensation and the preserved history. Archive or remove
the teacher with the normal administrative operation after checking
references.

## Source Map

- Migration: `backend/alembic/versions/0018_occurrence_decisions.py`
- Occurrence consumer: `backend/app/scheduler/infrastructure/occurrences.py`
- Progress ledger: `backend/app/scheduler/infrastructure/progress.py`

## Related Documents

- [Occurrences and Substitutions](../04_operational_features/OCCURRENCES_AND_SUBSTITUTIONS.md)
- [Observability and Recovery](OBSERVABILITY_AND_RECOVERY.md)
