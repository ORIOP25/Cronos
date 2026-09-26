# Scheduler v1 — Alembic consolidation plan (checkpoint before P11)

Date: 24 September 2026. Owner: W12. State: **mandatory checkpoint**.

## Current situation

The scheduler v1 schema is installed by the provisional revision
`0011_scheduler_v1_curricular` on top of the historical chain. That revision
has not been applied to development or production databases. The chain is
acceptable while the branch is under construction, but it is not the final
baseline.

`python -m scripts.check_scheduler_baseline` fails while the installed head is
the provisional revision, unless `SCHEDULER_BASELINE_ACCEPTED=1` marks a local
experiment. This keeps the checkpoint visible in every run.

## Consolidation steps (execute in W12)

1. Freeze the v1 tables, constraints, RLS policies and grants in the current
   branch. No new scheduler tables after this point without updating the plan.
2. Create a new single baseline revision that installs the complete schema on
   an empty database, replacing the historical chain for fresh installs.
3. Rebuild the runtime role, RLS, grants, indexes and required triggers in the
   new baseline. Keep the runtime role without `DELETE` on append-only evidence.
4. Install the new baseline on an empty temporary PostgreSQL database and run
   the read-only integrity audit.
5. Reinstall from the new baseline and repeat the scheduler integration and
   contract suites.
6. Update `scripts/test.mjs doctor` and the runbooks if the database bootstrap
   changes.

## Acceptance

- Empty-database install from the new baseline passes `alembic check` and the
  integrity audit.
- Scheduler integration and contract suites pass on the new baseline.
- The provisional revision is no longer reachable from the installed head.
- The privacy erasure path and the local reset procedure still pass.

## Non-goals

- No migration of test or legacy data.
- No compatibility columns for the old frontend.
- No production or development database reset inside this checkpoint document.
