# PRD: Database Tenant Hardening and Row-Level Security

## 1. Purpose

This PRD defines the target database architecture for tenant isolation, referential integrity, query safety, and PostgreSQL Row-Level Security (RLS).

The current system is still in development. Therefore, the implementation must optimize for the correct long-term design, not compatibility with weak or legacy patterns. Existing code, tests, migrations, fixtures, seed data, and docs may be updated or deleted when they conflict with this target state.

## 2. Background

The database audit from 2026-05-29 found that most business logic already filters by `organization_id`, but the database itself does not enforce RLS. Several link or derived tables infer the tenant through parent tables instead of carrying a direct `organization_id`.

Current main risks:

- A missed `organization_id` filter can expose cross-tenant data.
- Raw SQL, maintenance scripts, Celery tasks, or future endpoints can bypass service-layer assumptions.
- Link tables without direct tenant columns are harder to protect with simple RLS policies.
- Migrations and SQLAlchemy models are not fully aligned, making schema drift more likely.

Target state:

- Every tenant-owned table has an explicit, non-null `organization_id`.
- PostgreSQL enforces tenant isolation with RLS.
- Application code still filters by tenant as defense in depth.
- Tests prove that RLS blocks leaks even when application filters are missing.

## 3. 5Ws

### What

Implement a database-level tenant isolation model based on direct `organization_id` ownership, PostgreSQL RLS policies, strict relational consistency, and application session tenant context.

### Who

- Admin users: access data only inside their authenticated organization.
- Teacher users: access only the permitted subset of their organization and personal scope.
- Backend API: sets tenant context for every authenticated request.
- Celery/solver workers: set tenant context for every tenant-scoped job.
- Migration/maintenance tools: use privileged execution intentionally, never accidentally.
- Developers: use tests and schema checks to prevent regressions.

### Where

- PostgreSQL schema and migrations.
- SQLAlchemy models and relationships.
- FastAPI DB dependency/session lifecycle.
- Sync DB sessions used by Celery and solver code.
- Test fixtures, seed scripts, bootstrap/admin scripts.
- Documentation and release gates.

### When

Before production or any pilot with real multi-organization data.

This work should be implemented as a dedicated schema/security project, not mixed into feature work.

### Why

Cronos is a multi-tenant school operations platform. A data leak between schools is a critical security failure. Tenant isolation must not depend only on developer discipline in query construction.

## 4. Goals

1. Enforce tenant isolation at the database layer with RLS.
2. Make all tenant-owned tables directly tenant-scoped by `organization_id`.
3. Eliminate ambiguous cross-tenant relationships.
4. Keep application filters as defense in depth.
5. Align models, migrations, tests, and seed data with the target schema.
6. Make database access patterns predictable for async API and sync workers.
7. Add regression tests that intentionally attempt cross-tenant access and prove denial.
8. Avoid legacy compatibility compromises while the project is still in development.

## 5. Non-Goals and Out of Scope

- No UI redesign.
- No new business features.
- No billing/plan enforcement changes.
- No Clerk organization redesign beyond what is needed to set tenant context safely.
- No temporary compatibility layer for old rows without tenant ownership.
- No support for cross-organization shared teachers, subjects, classes, rooms, schedules, or modules.
- No multi-org user switching inside one authenticated request. A request has exactly one active organization.
- No superuser bypass in normal API endpoints.
- No production data migration playbook for legacy customer data, because the project is still in development.

## 6. Core Product Requirements

### 6.1 Tenant Ownership

Every table containing organization-owned data must have:

- `organization_id INTEGER NOT NULL`, matching the current `organization.id` type.
- Foreign key to `organization.id`.
- Index beginning with `organization_id` where the table is queried by tenant.
- RLS policy based on the current tenant context.

Expected exception:

- `organization`: root tenant table. It is tenant-scoped by its own `id`.

Tables that must gain direct `organization_id`:

- `availability`
- `course_subject_link`
- `teacher_subject_link`
- `class_subject_link`
- `module`
- `class_progress`

Tables that already have `organization_id` must be reviewed for nullability, indexes, foreign keys, and policies.

Known existing tenant-owned tables include, but are not limited to, `teacher_weekly_timesheet`, `lesson`, `schedule_output`, `lesson_occurrence`, `lesson_log`, `operational_schedule_block`, `progress_ledger_entry`, `substitutions`, `organization_settings`, `organization_grid_settings`, `school_calendar_event`, and operational event tables. These do not need a new tenant column when already non-null, but they still need RLS, tenant-leading indexes where useful, same-tenant reference checks, and uniqueness review.

### 6.2 Relationship Consistency

All foreign keys inside one tenant-owned row must point to rows in the same organization.

Examples:

- `availability.organization_id` must equal both `teacher.organization_id` and `timeslot.organization_id`.
- `course_subject_link.organization_id` must equal both `course.organization_id` and `subject.organization_id`.
- `teacher_subject_link.organization_id` must equal both `teacher.organization_id` and `subject.organization_id`.
- `class_subject_link.organization_id` must equal `class.organization_id`, `subject.organization_id`, and `teacher.organization_id` when `teacher_id` is not null.
- `module.organization_id` must equal `subject.organization_id`.
- `class_progress.organization_id` must equal `class.organization_id` and `module.organization_id`.
- `schedule_output.organization_id` must equal `lesson.organization_id`, `timeslot.organization_id`, and `room.organization_id`.
- `lesson.organization_id` must equal `class.organization_id`, `subject.organization_id`, and `teacher.organization_id`.
- operational and occurrence tables must enforce same-tenant references for all class, teacher, subject, room, timeslot, module, user, and schedule references.

Implementation must acknowledge the cost of composite foreign keys. A composite FK such as `(organization_id, teacher_id) -> teacher(organization_id, id)` requires a matching `UNIQUE(organization_id, id)` or composite primary key on the referenced table. The default target is:

- keep simple integer primary keys;
- add `UNIQUE(organization_id, id)` only where composite FKs are chosen;
- prefer same-tenant validation triggers where composite FKs would create excessive schema churn;
- test every trigger/composite-FK rule with direct SQL.

Silent cross-tenant references are forbidden.

### 6.3 User and Organization Rules

The target auth/data model:

- A normal application user must belong to exactly one active `organization_id` for each request.
- `organization_id` on non-superuser users must not be null.
- Users without a valid organization must not access tenant-owned endpoints.
- Superuser/system behavior, if kept, must be isolated from normal API dependencies and tested separately.
- Clerk token organization must match the local user organization before data access.

### 6.4 PostgreSQL RLS

RLS must be enabled and forced on every tenant-owned table.

Supported PostgreSQL target:

- Local Docker currently uses PostgreSQL 15.
- CI currently uses PostgreSQL 16.
- The implementation target is PostgreSQL 15+.
- If deployment target changes below PostgreSQL 15, implementation must stop and verify that `FORCE ROW LEVEL SECURITY`, policy syntax, and session setting behavior are supported before proceeding.

Canonical tenant context:

- Setting name: `app.current_organization_id`.
- Setting must be transaction-local via `set_config(..., is_local := true)`.
- Policies must not call `current_setting('app.current_organization_id')` without `missing_ok = true`, because that raises when unset.
- Policies must not directly cast arbitrary setting text to integer, because invalid values can raise instead of failing closed.

Canonical helper function:

```sql
CREATE SCHEMA IF NOT EXISTS app_security;

CREATE OR REPLACE FUNCTION app_security.current_organization_id()
RETURNS integer
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog
AS $$
DECLARE
    raw_value text := current_setting('app.current_organization_id', true);
    parsed_value bigint;
BEGIN
    IF raw_value IS NULL OR raw_value !~ '^[0-9]{1,10}$' THEN
        RETURN NULL;
    END IF;

    parsed_value := raw_value::bigint;
    IF parsed_value < 1 OR parsed_value > 2147483647 THEN
        RETURN NULL;
    END IF;

    RETURN parsed_value::integer;
EXCEPTION
    WHEN invalid_text_representation OR numeric_value_out_of_range THEN
        RETURN NULL;
END;
$$;
```

This function must never raise for unset, empty, negative, non-numeric, or out-of-range values. Returning `NULL` is the required fail-closed behavior because comparisons such as `organization_id = NULL` do not pass RLS policies.

Canonical policy shape:

- Tenant-owned tables with `organization_id`:
  - `USING (organization_id = app_security.current_organization_id())`
  - `WITH CHECK (organization_id = app_security.current_organization_id())`
- `organization` table:
  - `USING (id = app_security.current_organization_id())`, except explicitly privileged migration/admin/bootstrap contexts.

Policy expressions must handle missing tenant context safely:

- Missing tenant context returns no rows for reads and rejects writes.
- Invalid tenant context returns no rows for reads and rejects writes.
- Empty tenant context returns no rows for reads and rejects writes.

Database write rejection may surface as a PostgreSQL RLS error. The API must prevent expected missing/mismatched tenant context before data access and map unexpected RLS write denials to a controlled security response, never an unhandled HTTP 500.

RLS must not depend on client-supplied request bodies, query params, or path params.

### 6.5 Application Tenant Context

FastAPI async sessions must set the current tenant in the database transaction after authentication and before any tenant-owned query.

Sync worker sessions must set the current tenant before any tenant-owned query or mutation.

Required behavior:

- Public/anonymous endpoints, such as health checks and docs, must not set tenant context and must not query tenant-owned data.
- Any endpoint that needs tenant-owned data must be authenticated and tenant-bound.
- Authenticated tenant endpoints must fail closed when `current_user.organization_id` is missing.
- Tenant context must be scoped to the current transaction, not leaked across pooled connections.
- After commit/rollback, the context must not affect another request/job.

Auth bootstrap problem:

- Normal RLS on `user` and `organization` creates a bootstrapping problem: the API must validate Clerk user/org membership before it can set the numeric tenant context.
- The target design requires a narrow bootstrap path, not broad RLS bypass.
- Preferred implementation: a restricted `SECURITY DEFINER` function such as `app_security.resolve_auth_context(clerk_user_id text, clerk_org_id text)` that returns only the local `user_id`, `organization_id`, role, and active status after validating the Clerk IDs match local records.
- After bootstrap resolution, the API sets `app.current_organization_id` transaction-locally and performs normal ORM reads under RLS.
- The bootstrap function must not expose general tenant data and must be covered by security tests.

Bootstrap privilege model:

- The resolver is an intentional privileged escape hatch for authentication bootstrap only.
- The function owner must be a dedicated no-login role, for example `cronos_auth_definer`.
- The function owner may have `BYPASSRLS` or equivalent table-owner access only for the minimum tables needed to resolve auth context (`organization` and `user`), because otherwise RLS on those tables blocks the bootstrap read before tenant context exists.
- The API role must not have direct bypass privileges and must receive only `EXECUTE` on the resolver.
- `EXECUTE` must be revoked from `PUBLIC`.
- The function body must be static SQL only, with no dynamic SQL.
- The function must schema-qualify all table references, for example `public.organization` and `public."user"`.
- The function must define a safe `SET search_path`, for example `SET search_path = pg_catalog, public`.
- Parameters must be validated for null/empty/excessive length before querying.
- The resolver must return a single row or no row; it must not return arbitrary organization/user records.
- Tests must prove the API role can execute the resolver but cannot directly read `organization` or `user` without tenant context.

The phrase "narrow bootstrap path" means the caller has access only to this audited resolver, not general bypass privileges. The function owner is privileged; therefore the function body, grants, owner, and search path are security-critical implementation details.

### 6.6 Query Standards

Even with RLS, application queries must continue to filter by `organization_id` where applicable.

Why:

- Better query plans.
- Clear code review surface.
- Defense in depth.
- Easier reasoning in tests and logs.

Requirements:

- New queries must use SQLAlchemy structured APIs unless raw SQL is clearly required.
- Raw SQL touching tenant-owned tables must set and use tenant context.
- Bulk deletes/updates must include tenant filters.
- Relationship loads must not rely on untrusted cross-tenant data.
- Tests must cover eager loading and relationship paths, not only direct table reads.

### 6.7 Migration Strategy

Because the project is in development, prefer a clean final schema over compatibility scaffolding.

Allowed:

- Rewriting or replacing existing Alembic migrations if that is the cleanest path for development.
- Dropping and recreating dev databases.
- Updating seed data and fixtures to satisfy final constraints.
- Removing old helper paths that create unscoped rows.

Not allowed:

- Nullable tenant columns on tenant-owned tables as a permanent state.
- Policies that allow access when tenant context is missing.
- Long-term compatibility triggers to support old unscoped insert paths.
- Duplicate old/new schemas.

Required migration qualities:

- Upgrade path produces the target schema from a clean database.
- Downgrade path is defined for development, or the migration is explicitly declared irreversible with justification.
- SQLAlchemy model metadata matches database schema after Alembic upgrade.
- PostgreSQL-specific DDL is guarded where test environments require it, but production target remains PostgreSQL.
- Downgrade, when supported, must explicitly remove RLS policies, `ENABLE/FORCE ROW LEVEL SECURITY`, helper functions, triggers, grants, and migration-created roles/privileges where they are owned by the migration.
- If downgrade is declared irreversible, the migration must state why and provide the supported development reset path.

### 6.8 Observability and Auditability

Security-relevant failures must be observable without leaking sensitive data.

Required logging:

- Missing tenant context.
- Clerk token/local org mismatch.
- Cross-tenant reference validation failures.
- RLS-related failures during tests or runtime.
- Worker job started without tenant context.

Logs must include:

- `organization_id` when known.
- `actor_user_id` when known.
- endpoint/task name.
- request/job correlation id when available.

Logs must not include:

- full JWTs;
- secrets;
- database credentials;
- unrelated tenant data.

### 6.9 Clean Architecture Boundaries

Tenant hardening must preserve clean architecture boundaries:

- API/dependency layer owns authentication, Clerk token validation, auth bootstrap, and setting database tenant context.
- Database/infrastructure layer owns RLS helper SQL, policies, grants, triggers, Alembic migrations, and low-level session context helpers.
- Service/application layer receives an already resolved `organization_id` and performs business use cases with explicit tenant filters.
- Domain logic must not import FastAPI dependencies, Clerk SDK objects, JWT payloads, request objects, or raw RLS SQL.
- Solver/worker entrypoints set tenant context at job boundaries before calling domain/application services.
- Pydantic schemas must not accept trusted `organization_id` from client payloads for tenant-owned writes; tenant ownership comes from authenticated context.
- Tests should reflect these layers: auth/bootstrap tests in API/infrastructure suites, same-tenant business behavior in service tests, RLS policy behavior in database integration tests.

Security plumbing must not become business logic. Business services may validate tenant ownership for clear errors, but database RLS remains an infrastructure backstop.

## 7. Data Model Requirements

### 7.1 Required Tenant Columns

Add direct `organization_id` to:

| Table | Source for organization_id | Notes |
|---|---|---|
| `availability` | `teacher.organization_id` and `timeslot.organization_id` | Must reject mismatched teacher/timeslot orgs. |
| `course_subject_link` | `course.organization_id` and `subject.organization_id` | Join table becomes tenant-owned, not neutral. |
| `teacher_subject_link` | `teacher.organization_id` and `subject.organization_id` | Must reject teacher/subject from different orgs. |
| `class_subject_link` | `class.organization_id`, `subject.organization_id`, optional `teacher.organization_id` | Teacher may be null, but when present must match. |
| `module` | `subject.organization_id` | Modules are organization-owned curriculum units. |
| `class_progress` | `class.organization_id` and `module.organization_id` | Must reject class/module mismatches. |

Insert interaction with RLS:

- Application code sets `organization_id` from authenticated tenant context, not from client payload.
- Parent rows are looked up under the same tenant context and should be invisible if they belong to another tenant.
- RLS `WITH CHECK` rejects any inserted row whose `organization_id` does not match `app_security.current_organization_id()`.
- Same-tenant FK/trigger checks reject rows whose parent IDs do not belong to the row's `organization_id`.
- Both layers must pass: session context must match the row tenant, and parent references must match the row tenant.

### 7.2 Unique Constraints

Unique constraints must include `organization_id` where tenant-local uniqueness is intended.

Required review:

- `availability`: unique `(organization_id, teacher_id, timeslot_id)`.
- `course_subject_link`: primary or unique `(organization_id, course_id, subject_id)`.
- `teacher_subject_link`: primary or unique `(organization_id, teacher_id, subject_id)`.
- `class_subject_link`: unique `(organization_id, class_id, subject_id, grade_level)`.
- `module`: unique `(organization_id, subject_id, order)`.
- `class_progress`: unique `(organization_id, class_id, module_id)`.
- `teacher_weekly_timesheet`: already tenant-owned; review/update to unique `(organization_id, teacher_id, week_start_date)`.
- Existing tenant tables must be reviewed for global uniqueness that should be tenant-local.

Global uniqueness is allowed only for external identity fields that are truly global, such as Clerk IDs.

### 7.3 Indexes

Indexes must match common tenant-scoped queries.

Minimum expectations:

- Every tenant-owned table: index on `organization_id`.
- Frequent list/order queries: composite indexes such as `(organization_id, name)` or `(organization_id, date)`.
- Operational schedule reads: indexes beginning with `organization_id` and including date, teacher, class, timeslot, or generation as needed.
- RLS policy columns must be index-friendly.

Avoid redundant indexes that duplicate composite index prefixes without a query need.

### 7.4 Cascades and Deletes

Delete behavior must be explicit.

Requirements:

- Organization deletion may cascade in development/admin cleanup contexts only.
- Business deletes must preserve immutable history where the domain requires it.
- Operational history tables must not be casually cascade-deleted by normal workflows.
- Hard deletes of schedule/class/teacher/subject records must be blocked when historical records depend on them, unless the workflow is a deliberate development reset.

## 8. Validation Rules

### 8.1 Insert Validation

Any insert into tenant-owned tables must satisfy:

- `organization_id` is present.
- `organization_id` matches all referenced tenant-owned rows.
- Current RLS tenant context matches `organization_id`.

### 8.2 Update Validation

Any update must satisfy:

- Row is visible under the current tenant.
- New `organization_id` cannot move a row between tenants.
- Referenced IDs cannot be changed to another tenant.
- `WITH CHECK` policy blocks writes outside the current tenant.

### 8.3 Delete Validation

Any delete must satisfy:

- Row is visible under the current tenant.
- Bulk deletes include tenant filtering in application code.
- RLS blocks accidental cross-tenant deletes.

### 8.4 Session Validation

Before any tenant-owned query:

- API session has tenant context set after auth.
- Worker session has tenant context set from job ownership.
- Missing context fails closed.

### 8.5 API Error Semantics

RLS is a database backstop, not the primary API contract. Expected security outcomes must be handled before unstructured database errors reach the client.

Required API semantics:

- Missing authenticated tenant context: `403`.
- Clerk token organization does not match local user organization: `403`.
- Role does not permit action: `403`.
- Path resource belongs to another tenant: `404`, to avoid confirming existence.
- Path resource that does not exist and path resource that exists in another tenant must be indistinguishable to the caller: same `404` shape and generic message.
- Body reference that is missing, invalid, or not visible in the current tenant, such as `teacher_id`, `subject_id`, or `timeslot_id`: same generic `422` invalid-reference response, or existing endpoint-specific `400` only where already documented.
- Body reference responses must not distinguish "does not exist" from "exists in another tenant".
- RLS write denial that reaches the database unexpectedly: controlled `403` with generic message and structured security log.
- RLS read denial: empty/not-found result, then normal endpoint behavior such as `404` for detail routes or empty list for list routes.
- Missing/invalid tenant context must never become an unhandled `500`.

## 9. Edge Cases

### Authentication and Tenant Context

- Token has no organization claim.
- Token organization does not exist locally.
- Token organization exists but user belongs to another organization.
- User exists but `organization_id` is null.
- User is inactive.
- User role changed in Clerk.
- Teacher user points to a teacher profile in another organization.
- Superuser/system user tries to access normal tenant endpoint.

Expected result: no tenant-owned data is returned unless there is exactly one valid tenant context.

### Database and RLS

- Query runs without setting `app.current_organization_id`.
- Query sets invalid tenant context.
- Query sets tenant context for org A and attempts to read org B.
- Insert with `organization_id` A references parent row from org B.
- Bulk update/delete forgets tenant filter.
- Lazy/eager relationship load crosses tenant boundaries.
- Celery worker reuses a pooled connection after a previous tenant job.
- Migration/admin connection runs RLS DDL.

Expected result: normal app/worker access fails closed; privileged migration access is explicit.

### Data Integrity

- Course and subject from different organizations are linked.
- Teacher and subject from different organizations are linked.
- Class and module from different organizations are linked through progress.
- Schedule output references lesson/timeslot/room from different organizations.
- Lesson occurrence references class/subject/teacher/module/schedule from different organizations.
- User references teacher from another organization.

Expected result: database rejects the write, and tests prove rejection.

### Testing and Fixtures

- Existing fixtures create records without `organization_id`.
- Tests use SQLite-like assumptions while target is PostgreSQL.
- `Base.metadata.create_all()` bypasses Alembic-only SQL such as RLS policies.
- Tests accidentally run with table owner privileges and bypass RLS.

Expected result:

- fixtures are updated to the target schema;
- RLS tests run against PostgreSQL with Alembic-applied schema;
- RLS tests use a database role that does not bypass policies;
- `Base.metadata.create_all()` may remain only for fast tests that do not claim RLS coverage.
- non-PostgreSQL test environments may run non-RLS tests only; RLS, trigger, grant, policy, and migration-object tests must be marked PostgreSQL-required and must be mandatory in CI.

## 10. Test Strategy

RLS-specific tests must use a PostgreSQL database created through Alembic migrations, not `Base.metadata.create_all()`. This is a resolved requirement, not an open decision, because `create_all()` does not create policies, helper functions, triggers, grants, or `FORCE ROW LEVEL SECURITY`.

Test environment boundaries:

- PostgreSQL-backed RLS tests are mandatory in CI.
- Local developers may skip PostgreSQL-required tests only when explicitly running a fast unit-test subset.
- A skipped local RLS test run is not acceptable release evidence.
- Non-PostgreSQL databases must not be used to claim tenant isolation or RLS compliance.

### 10.1 Unit Tests

Cover:

- Tenant context helper sets and clears transaction-local context.
- `app_security.current_organization_id()` returns null, not an error, for unset, empty, negative, non-numeric, zero, integer-overflow, and bigint-overflow settings.
- `app_security.current_organization_id()` returns the expected integer for valid values including `1` and `2147483647`.
- Missing organization in authenticated user fails closed.
- Clerk token/local organization mismatch fails closed.
- Worker tenant context helper requires organization id.
- Validation helpers reject cross-tenant parent IDs before DB mutation where applicable.

### 10.2 Integration Tests

Cover:

- Alembic upgrade creates all required columns, constraints, indexes, and RLS policies.
- SQLAlchemy metadata matches migrated schema.
- Insert/update/delete succeed for same-tenant data.
- Insert/update/delete fail for cross-tenant references.
- Direct SQL without tenant context cannot read tenant-owned tables.
- Direct SQL with org A context cannot read org B rows.
- Direct SQL with org A context cannot insert org B rows.
- API endpoints still return correct data under RLS.
- Celery/solver sync sessions work under tenant context.

### 10.3 Regression Tests

Cover all major business surfaces:

- Organizations and users.
- Teachers and teacher availability.
- Subjects, modules, and teacher competencies.
- Courses, classes, class subjects, and class progress.
- Timeslots and rooms.
- Lessons and schedule outputs.
- Draft schedule lifecycle.
- Occurrences, substitutions, operational blocks, lesson logs.
- Timesheets.
- Dashboard and analytics.
- Seed/import endpoints.
- Webhooks and onboarding.

### 10.4 Security Tests

Required negative tests:

- Cross-tenant IDOR by path id.
- Cross-tenant IDOR by request body id.
- Cross-tenant relationship insert.
- Cross-tenant bulk delete/update attempt.
- Missing tenant context.
- Invalid tenant context.
- Role with insufficient authorization.
- Teacher profile from another organization.
- Worker job with mismatched organization ownership.

### 10.5 Performance Tests

Measure:

- Common list endpoints before/after tenant indexes.
- Schedule weekly reads.
- Solver data loading.
- Dashboard aggregate queries.
- Occurrence recommendation queries.

Acceptance thresholds:

- No material regression on existing performance tests.
- Query plans use tenant-leading indexes for common tenant-scoped reads.
- RLS policy overhead is acceptable for expected tenant data sizes.

### 10.6 Migration Tests

Cover:

- Clean database upgrade to head.
- Downgrade path if supported.
- RLS policies present after upgrade.
- Required constraints reject invalid data.
- Seed scripts work from a clean database.
- Test fixtures work without bypassing final invariants.

## 11. Acceptance Criteria

This project is complete when all criteria are met:

1. Every tenant-owned table has direct `organization_id`, except `organization`.
2. Every tenant-owned table has RLS enabled and forced.
3. Missing tenant context returns no tenant-owned rows and permits no tenant-owned writes.
4. Cross-tenant relationships are rejected by the database.
5. FastAPI requests set transaction-local tenant context before tenant-owned DB access.
6. Celery/solver jobs set transaction-local tenant context before tenant-owned DB access.
7. Application queries still include tenant filters where applicable.
8. All seed data and fixtures produce valid tenant-scoped rows.
9. Alembic migrations and SQLAlchemy models are aligned.
10. Existing tenant isolation tests pass.
11. New RLS-specific tests pass against PostgreSQL.
12. Documentation explains the final architecture and developer rules.
13. No permanent nullable tenant columns or compatibility-only paths remain.
14. RLS expected denials never surface as unhandled HTTP 500 responses.
15. RLS coverage is verified through Alembic-created PostgreSQL schemas using a non-bypass role.

## 12. Release Gates

Gate 1: Design approval

- PRD accepted.
- WBS accepted.
- Final table ownership matrix accepted.

Gate 2: Schema readiness

- Migration reviewed.
- Model/schema diff reviewed.
- Clean database upgrade succeeds.
- PostgreSQL version target verified as 15+ or implementation explicitly adjusted before proceeding.

Gate 3: RLS readiness

- Policies present.
- Tenant context helpers implemented.
- Direct SQL negative tests pass.

Gate 4: App readiness

- API and worker tests pass.
- Tenant isolation regression suite passes.
- Performance checks pass.

Gate 5: Documentation readiness

- Security baseline updated.
- Endpoint/database standards updated.
- Operational notes for migrations/admin scripts updated.

## 13. Resolved Implementation Decisions

These decisions seal the PRD for implementation:

1. Normal users must have non-null `organization_id`; users without a valid organization have no tenant data access.
2. Superuser/system behavior, if retained, must use explicit isolated dependencies and must not bypass normal API tenant rules.
3. Because the project is still in development, the preferred implementation is a clean Alembic baseline/schema reset if there is no real production data. If production data exists, implementation must stop for a separate migration plan.
4. Same-tenant consistency will use direct `organization_id`, tenant-aware uniqueness, and validation triggers by default. Composite FKs may be used only after WBS 1.4 confirms the required `UNIQUE(organization_id, id)` ripple is acceptable for the referenced tables.
5. API and worker database roles must be non-superuser and non-owner roles that do not bypass RLS.
6. Migration role must be separate and privileged.
7. RLS-specific tests must use Alembic-created PostgreSQL schemas and a non-bypass role.
8. A central tenant-table registry must be created and used by migrations/tests/docs to reduce policy drift.
9. Auth bootstrap must use a narrow, tested resolver path before setting transaction-local tenant context.
10. Supported PostgreSQL target is 15+ based on current local Docker and CI configuration.

No critical open decision may remain before WBS 1.1 implementation begins.

## 14. Review Workflow

The PRD and WBS are iterative planning artifacts. "PRD approval" in the WBS means approval of the reviewed PRD version after reviewer findings have been dispositioned. Reviewer disposition sections are part of reaching approval; they do not imply implementation has started.

## 15. Reviewer Findings Disposition

The review findings were handled as follows:

| Finding | Disposition |
|---|---|
| RLS fail-closed vs error behavior undefined | Relevant; canonical helper and API error behavior are now specified. |
| PostgreSQL version / `FORCE ROW LEVEL SECURITY` concern | Relevant in spirit; target PostgreSQL 15+ is now explicit and version verification is a gate. |
| RLS tests depended on open decision | Relevant; Alembic-created PostgreSQL RLS tests are now mandatory. |
| Composite FK ripple effect | Relevant; ripple is now documented and triggers are the default unless composite FKs are justified. |
| Non-SQL policy placeholder | Relevant; canonical SQL policy shape is now included. |
| Missing HTTP response code behavior | Relevant; API security error semantics are now specified. |
| Missing WBS dependencies | Relevant; WBS updated. |
| `teacher_weekly_timesheet` ambiguity | Relevant; clarified as already tenant-owned but requiring review. |
| "Alembic model metadata" wording | Relevant wording fix; changed to SQLAlchemy metadata. |
| Public/tenant-bound endpoint contradiction | Relevant wording fix; clarified public endpoints do not query tenant data. |
| `organization_id` type not cross-referenced | Relevant wording fix; `organization_id` must match `organization.id`. |
| WBS decision log absent | Relevant; WBS now includes decision-log template. |
| `organization` RLS bootstrap problem | Relevant; auth bootstrap resolver requirement added. |

## 16. Second Reviewer Findings Disposition

The second review findings were handled as follows:

| Finding | Disposition |
|---|---|
| Integer overflow in canonical helper function | Relevant; helper now uses bounded input, bigint intermediate, and exception-safe null return. |
| Auth bootstrap circular dependency unresolved | Relevant; bootstrap now explicitly uses a dedicated privileged definer role with tightly granted resolver function. |
| Non-PostgreSQL test environments | Relevant; RLS tests are PostgreSQL-required and mandatory in CI; non-PostgreSQL tests cannot claim RLS coverage. |
| `SECURITY DEFINER` restrictions unspecified | Relevant; owner, grants, search path, static SQL, schema qualification, and parameter validation are now specified. |
| Canonical helper not tested | Relevant; helper edge cases are now required in tests. |
| Decision log incomplete | Relevant; WBS decision log expanded to cover all resolved decisions. |
| 404 vs 422 existence leak | Relevant; response semantics now require identical responses for nonexistent and cross-tenant references within each channel. |
| RLS on `organization` blocks bootstrap | Relevant; resolved through explicit auth bootstrap resolver mechanism. |
| WBS/PRD approval flow ambiguity | Relevant; review workflow clarified. |
| Downgrade tests for RLS objects | Relevant; migration requirements and WBS tests now enumerate RLS objects. |
| Positive access controls missing in WBS 4.4 | Relevant; WBS now requires same-tenant positive controls under RLS. |
| Session context vs same-tenant reference checks | Relevant; layered insert validation order is now documented. |
| WBS 3.0 missing dependency on RLS policies | Relevant; dependency updated to include WBS 2.2. |
| Clean architecture | Relevant; PRD now defines layer boundaries and WBS includes clean architecture verification. |

## 17. Documentation Deliverables

The implementation must update:

- `documentation/08_security_quality/SECURITY_BASELINE.md`
- `documentation/05_backend_api/ENDPOINT_STANDARDS.md`
- `documentation/BEST_PRACTICES_ENDPOINTS.md`
- `documentation/08_security_quality/DATABASE_AUDIT_2026-05-29.md`
- Any operational runbook that mentions migrations, seed data, or tenant isolation.
