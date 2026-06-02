# Database Audit - 2026-05-29

Scope: SQLAlchemy models, Alembic migrations, service-layer queries, tenant isolation, and Postgres readiness.

## Executive Summary

The app uses PostgreSQL through SQLAlchemy with async sessions for FastAPI and sync sessions for Celery. Most business tables are filtered by `organization_id` in service code, and there is a meaningful tenant-isolation test suite.

The database is not yet protected by Postgres Row-Level Security (RLS). Tenant isolation currently depends on application code and tests. This is workable for an alpha, but it is not enough for a high-confidence multi-tenant production system because one missed filter, raw SQL query, admin script, or future endpoint can bypass isolation.

## Tables Without Direct `organization_id`

Expected exception:

- `organization`: root tenant table.

Tables that currently infer tenant through parent rows:

- `availability`: via `teacher_id` and `timeslot_id`.
- `course_subject_link`: via `course_id` and `subject_id`.
- `teacher_subject_link`: via `teacher_id` and `subject_id`.
- `class_subject_link`: via `class_id`, `subject_id`, and optional `teacher_id`.
- `module`: via `subject_id`.
- `class_progress`: via `class_id` and `module_id`.

This is the main schema cleanliness gap. Direct `organization_id` columns on these tables would make RLS policies, indexes, orphan checks, and bulk cleanup much safer. Adding them should be done as a dedicated migration because relationship insert paths must populate the tenant column consistently.

## RLS Status

RLS is not implemented. No migrations were found with:

- `ALTER TABLE ... ENABLE ROW LEVEL SECURITY`
- `CREATE POLICY`
- `current_setting('app.current_organization_id')`
- `SET LOCAL app.current_organization_id`

Recommended production path:

1. Add direct `organization_id` to the relationship/derived tables listed above.
2. Backfill from trusted parent tables.
3. Add non-null constraints and composite indexes.
4. Set `app.current_organization_id` per request/worker transaction.
5. Enable and force RLS on tenant-owned tables.
6. Keep service-layer filters as defense in depth.

## Query Integration

Good patterns:

- API reads and writes generally use SQLAlchemy `select()`, `delete()`, `update()`, and ORM relationships.
- Async API code uses `AsyncSession`; Celery/solver code uses a sync engine.
- Many read paths use `selectinload`/`joinedload` to avoid async lazy-loading and common N+1 problems.
- Tenant-isolation tests cover important endpoints and IDOR scenarios.

Fixed during this audit:

- Clerk token org is now checked against the local user organization before returning `current_user`.
- Existing users now get token role changes applied consistently.
- Room creation now persists `capacity` instead of silently using the model default.
- Dependency checks for rooms, teachers, courses, and modules now include tenant-scoped filters.
- Teacher progress now validates the teacher belongs to the authenticated organization and joins through `Class.organization_id`.

## Remaining Risks

- Application-level isolation is still the primary control until RLS exists.
- Link/derived tables without `organization_id` make it possible for bad data to exist if inserted outside guarded services.
- Alembic baseline and current models are not perfectly aligned; for example historical migration contents include fields no longer present in the model and later migrations alter earlier table assumptions. Use Alembic autogenerate/check against a clean database before the next release.
- Some direct ORM relationships can still load related rows without tenant criteria. That is acceptable only while parent rows are strongly validated and data integrity is trusted.

## Recommended Next Migration

Create a migration named something like `tenant_hardening_org_columns_and_rls` that:

- Adds nullable `organization_id` columns to `availability`, `course_subject_link`, `teacher_subject_link`, `class_subject_link`, `module`, and `class_progress`.
- Backfills each from parent records.
- Adds `NOT NULL` and foreign keys to `organization.id`.
- Adds indexes that start with `organization_id`.
- Adds composite uniqueness where helpful, e.g. `availability(organization_id, teacher_id, timeslot_id)`.
- Adds consistency checks/triggers or service updates so parent IDs cannot cross organizations.
- Enables RLS only after app sessions reliably set the current tenant.

## Planning Documents

Follow-up planning for this audit:

- `PRD_DATABASE_TENANT_HARDENING_RLS.md`: complete product and technical requirements for tenant hardening and RLS.
- `WBS_DATABASE_TENANT_HARDENING_RLS.md`: implementation work breakdown for the PRD.
## Implementation Update: Tenant Hardening And RLS

The hardening implementation introduces direct tenant ownership for the
previously indirect tables identified by the audit:
`availability`, `course_subject_link`, `teacher_subject_link`,
`class_subject_link`, `module`, and `class_progress`.

The Alembic RLS migration adds:

- `app_security.current_organization_id()` with fail-closed parsing;
- transaction-local tenant context contract through
  `app.current_organization_id`;
- forced RLS policies for tenant-owned tables;
- an `organization` self-tenant policy;
- same-tenant validation triggers for the highest-risk references;
- a narrow `app_security.resolve_auth_context(...)` bootstrap function.

Application writes and fixtures must now populate `organization_id` directly on
tenant-owned link and derived rows. The tenant table registry lives in
`backend/app/db/tenant.py` and should be kept aligned with future schema
changes.
