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

The consolidated baseline includes explicit decisions on v1 lesson logs and v1 origins on operational blocks.
The schema classifies no historical records automatically.

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

SELECT r.id, r.debt_id, d.assignment_id, r.origin, r.revision, r.delta_minutes, r.author_membership_id, r.reason
FROM curricular_debt_revision r
JOIN curricular_debt d ON d.id = r.debt_id AND d.organization_id = r.organization_id
WHERE r.organization_id = :organization_id
ORDER BY r.id;

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
- A concluded substitution keeps one substitute credit. The original debt stays open unless separately settled on its assignment.
- Totals before and after explain every difference.

## Failure Modes

- Ambiguous records stop the procedure.
- A missing reference leaves the record open.
- A failed transaction changes nothing.
- A baseline downgrade removes all application data. It is not a reconciliation action.

## Reconciliation of Historical Residue

Historical test-data inventories remain in Git history. Their identifiers do not describe a database installed from the consolidated baseline.
Inventory the target database before any correction.
The dashboard and debt page read the same v1 ledger. Each claim contributes its remaining balance.
Cancellation reverses execution before cancelling reopened debt, following published lesson lineage.
For an already revoked log, repeat cancellation in an open week through the administrative endpoint.
This preserves revocation metadata and appends only missing debt revisions.
When older publications lack source links, reconciliation can match stable identity and the exact UTC interval.
The match stays within organization, school year, and curricular assignment.
Verify that the affected debt closes and unrelated claims remain unchanged.
Do not classify future debt as invalid solely from its date. An explicit gap decision can create future debt.

## Source Map

- Baseline: `backend/alembic/versions/0001_scheduler_v1_baseline.py`
- Occurrence consumer: `backend/app/scheduler/infrastructure/occurrences.py`
- Progress ledger: `backend/app/scheduler/infrastructure/progress.py`

## Related Documents

- [Occurrences and Substitutions](../04_operational_features/OCCURRENCES_AND_SUBSTITUTIONS.md)
- [Observability and Recovery](OBSERVABILITY_AND_RECOVERY.md)
