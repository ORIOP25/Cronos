# WBS: Database Tenant Hardening and RLS

## 1. Objective

Implement the target state defined in `PRD_DATABASE_TENANT_HARDENING_RLS.md`: direct tenant ownership on all tenant-owned tables, same-tenant relationship enforcement, PostgreSQL RLS, transaction-local tenant context, and full regression coverage.

This WBS is documentation only. It intentionally does not implement code.

## 2. Delivery Principles

1. Prefer the correct final design over compatibility with current development data.
2. No permanent legacy adapters.
3. No nullable tenant columns as final state.
4. No RLS policy that permits access without tenant context.
5. App-level tenant filters remain required even after RLS.
6. Tests must prove both intended access and denied access.
7. Alembic, models, fixtures, seed scripts, and docs must end aligned.

## 3. Work Breakdown Structure

### WBS 0.1 - Confirm Final Scope and Record Decisions

Depends on: reviewed PRD accepted for implementation planning.

Tasks:

- Confirm there is no production data to preserve. If production data exists, stop and create a separate migration plan.
- Confirm PostgreSQL target remains 15+.
- Confirm clean Alembic baseline/schema reset is acceptable for development.
- Confirm normal users require non-null `organization_id`.
- Confirm production API and worker roles are non-owner/non-superuser roles.
- Confirm migration role is separate and privileged.
- Record all confirmations in the decision log.

Decision log template:

| Decision | Chosen Option | Rationale | Owner | Date | Reversal Cost |
|---|---|---|---|---|---|
| PostgreSQL target version | 15+ | Docker uses PG15; CI uses PG16 | TBD | TBD | High |
| RLS test schema setup | Alembic-created PostgreSQL | `create_all()` cannot create policies | TBD | TBD | Medium |
| Normal user organization ownership | Non-null `organization_id` | Tenant endpoints require one active org | TBD | TBD | High |
| Superuser/system behavior | Isolated dependencies only | Must not bypass normal API tenant rules | TBD | TBD | Medium |
| Alembic strategy | Clean baseline/schema reset if no production data | Development stage favors correct final schema | TBD | TBD | High |
| Same-tenant enforcement default | Validation triggers + tenant-aware uniqueness | Avoid broad composite-FK churn by default | TBD | TBD | Medium |
| Composite FK usage | Per-table only after ripple review | Requires `UNIQUE(organization_id, id)` on referenced tables | TBD | TBD | Medium |
| API/worker DB role | Non-owner, non-superuser, no RLS bypass | RLS must apply to app traffic | TBD | TBD | High |
| Migration DB role | Separate privileged role | Migrations need DDL/grant control | TBD | TBD | Medium |
| Tenant table registry | Required | Prevent policy drift | TBD | TBD | Low |
| Auth bootstrap mechanism | Restricted `SECURITY DEFINER` resolver | Solves user/org bootstrap before tenant context | TBD | TBD | High |

Current implementation decisions recorded on 2026-05-29:

| Decision | Chosen Option | Rationale | Owner | Date | Reversal Cost |
|---|---|---|---|---|---|
| PostgreSQL target version | 15+ | Existing local/CI target supports forced RLS and transaction-local settings | Codex | 2026-05-29 | High |
| RLS test schema setup | Alembic-created PostgreSQL | RLS objects are migration-only and cannot be proven by `create_all()` | Codex | 2026-05-29 | Medium |
| Normal user organization ownership | Non-null `organization_id` | Tenant endpoints require exactly one active organization | Codex | 2026-05-29 | High |
| Alembic strategy | Forward hardening migration for dev schema | Keeps current migration history while moving to final schema | Codex | 2026-05-29 | Medium |
| Same-tenant enforcement default | Validation triggers | Avoids composite-FK churn while still rejecting direct SQL mismatches | Codex | 2026-05-29 | Medium |
| Tenant table registry | `backend/app/db/tenant.py` | Shared source for app helpers and drift tests/docs | Codex | 2026-05-29 | Low |
| Auth bootstrap mechanism | Restricted resolver function | Provides narrow pre-context user/org resolution path | Codex | 2026-05-29 | High |

Acceptance criteria:

- No critical implementation decision remains open.
- Final decision log is added to this WBS or a linked architecture note before WBS 1.1 starts.

### WBS 0.2 - Build Table Ownership Matrix

Depends on: WBS 0.1.

Tasks:

- List every table in SQLAlchemy metadata.
- Classify as:
  - root tenant table;
  - tenant-owned table;
  - pure lookup enum/static table;
  - operational/audit table;
  - system table.
- Document whether each table has `organization_id`.
- Document required RLS policy for each table.
- Document required same-tenant references for each table.
- Explicitly include tables that already have `organization_id`, such as `teacher_weekly_timesheet`, so they are reviewed for RLS, indexes, uniqueness, and FK consistency rather than accidentally skipped.

Acceptance criteria:

- Matrix covers 100% of tables.
- Every tenant-owned table has a policy decision.
- No ambiguous "inherits tenant indirectly" rows remain without an explicit remediation.

### WBS 0.3 - Inventory Current Query Paths

Depends on: WBS 0.2.

Tasks:

- Search async API services for tenant-owned queries.
- Search sync worker/solver services for tenant-owned queries.
- Search seed scripts, bootstrap scripts, webhooks, and imports.
- Identify raw SQL statements touching tenant-owned tables.
- Identify relationship loads that rely on parent validation.

Acceptance criteria:

- Query inventory exists.
- Every query path has an owner and remediation note.
- Bulk update/delete paths are explicitly listed.

## 4. Schema Hardening

### WBS 1.1 - Add Direct Tenant Columns to Derived and Link Tables

Depends on: WBS 0.2.

Target tables:

- `availability`
- `course_subject_link`
- `teacher_subject_link`
- `class_subject_link`
- `module`
- `class_progress`

Tasks:

- Add `organization_id` to SQLAlchemy models.
- Add `organization_id` to Alembic migration or clean baseline.
- Make the final column non-null.
- Add FK to `organization.id`.
- Update ORM relationship definitions where helpful.
- Update schemas only if API contracts intentionally expose these fields.

Acceptance criteria:

- All target tables have non-null `organization_id`.
- Model metadata and migrated DB schema match.
- No insert path can create these rows without tenant ownership.

### WBS 1.2 - Update Unique Constraints and Primary Keys

Depends on: WBS 1.1.

Tasks:

- Update `availability` uniqueness to include `organization_id`.
- Update link table primary/unique constraints to include `organization_id`.
- Update `module` uniqueness to include `organization_id`.
- Update `class_progress` uniqueness to include `organization_id`.
- Review all other global uniqueness constraints.

Acceptance criteria:

- Tenant-local uniqueness is enforced per tenant.
- Truly global identifiers remain globally unique only when justified.
- Tests cover duplicate names/links/orders in different organizations where allowed.

### WBS 1.3 - Add Tenant-Leading Indexes

Depends on: WBS 1.1.

Tasks:

- Add `organization_id` index to every tenant-owned table if missing.
- Add composite indexes for common query paths:
  - organization + name;
  - organization + date;
  - organization + teacher/date/timeslot;
  - organization + class/date;
  - organization + generation/is_draft;
  - organization + source identifiers for ledgers/events.
- Remove redundant single-column indexes if a composite index fully replaces them and no query requires them.

Acceptance criteria:

- Query plans for common endpoints use tenant-leading indexes.
- No redundant index bloat is introduced without reason.

### WBS 1.4 - Enforce Same-Tenant Foreign References

Depends on: WBS 1.1.

Tasks:

- Define same-tenant rules for every tenant-owned FK.
- Analyze the composite-FK ripple for each candidate FK.
- If composite FKs are used, add required `UNIQUE(organization_id, id)` constraints to referenced tables.
- Prefer validation triggers where composite FKs would require broad schema churn.
- Implement database enforcement through the selected per-table strategy.
- Cover nullable references, especially optional teacher/module/user/schedule links.
- Make validation fail with clear DB errors.
- Update service-level prevalidation for better API errors where useful.

Acceptance criteria:

- Database rejects cross-tenant references even through direct SQL.
- Tests cover every high-risk cross-tenant reference type.
- Service-level validation remains helpful but is not the only protection.
- Implementation notes state whether each table uses trigger enforcement or composite FK enforcement.

### WBS 1.5 - Align Cascades, Deletes, and History Rules

Depends on: WBS 1.4.

Tasks:

- Review `ondelete` behavior across all FKs.
- Preserve immutable history where required.
- Decide which development reset operations can hard-delete data.
- Ensure normal business deletes cannot orphan operational records.
- Update reset/seed workflows to use deliberate admin/development paths.

Acceptance criteria:

- Delete rules are documented and implemented.
- Historical operational data cannot be accidentally erased by normal API flows.
- Development reset behavior is explicit.

## 5. RLS Implementation

### WBS 2.1 - Define Tenant Context Contract

Depends on: WBS 0.1.

Tasks:

- Use final PostgreSQL setting name `app.current_organization_id`.
- Create canonical helper function `app_security.current_organization_id()` that uses `current_setting(..., true)` and returns null for missing/empty/invalid values.
- Ensure helper handles integer overflow safely and never raises for malformed settings.
- Define helper SQL for setting transaction-local context.
- Define behavior for clearing/no context.
- Define app, worker, migration, and test roles.
- Define API mapping for RLS denials: expected denials must not become unhandled HTTP 500 responses.

Acceptance criteria:

- Missing context denies tenant-owned access.
- Invalid context denies tenant-owned access without cast errors.
- Context is transaction-local and safe with pooled connections.
- Contract is documented for API and worker developers.

### WBS 2.2 - Implement RLS Policies

Depends on: WBS 1.1, WBS 2.1.

Tasks:

- Enable RLS on all tenant-owned tables.
- Force RLS on all tenant-owned tables for PostgreSQL 15+.
- Add `USING` and `WITH CHECK` policies for tables with `organization_id`.
- Add policy for `organization` based on `id`.
- Add explicit privileged/migration role behavior.
- Ensure policies fail closed on missing/invalid context.

Acceptance criteria:

- Every tenant-owned table has RLS enabled and forced.
- RLS policy tests verify read/write denial without context.
- RLS policy tests verify org A cannot access org B.

### WBS 2.3 - Add Policy Drift Tests

Depends on: WBS 2.2.

Tasks:

- Create test that compares metadata table list with RLS policy table list.
- Fail when a tenant-owned table lacks RLS.
- Fail when a tenant-owned table lacks direct `organization_id`, except `organization`.
- Fail when a policy name or expression is missing.

Acceptance criteria:

- Future tenant tables cannot be added without an explicit RLS decision.
- Test failure message identifies the missing table/policy.

## 6. Application Integration

### WBS 3.0 - Implement Auth Bootstrap Resolver

Depends on: WBS 2.1, WBS 2.2.

Tasks:

- Add narrow auth bootstrap path before tenant context is available.
- Preferred implementation: restricted `SECURITY DEFINER` function `app_security.resolve_auth_context(clerk_user_id text, clerk_org_id text)`.
- Use dedicated no-login function owner.
- Revoke `EXECUTE` from `PUBLIC`; grant only to API role.
- Use static SQL only.
- Set safe function `search_path`.
- Schema-qualify all table references.
- Validate parameter null/empty/length.
- Return only local `user_id`, `organization_id`, role, and active status.
- Validate Clerk user/org match local records.
- Deny missing/mismatched organization before tenant-owned ORM access.
- Add tests proving the resolver does not expose general tenant data.

Acceptance criteria:

- API can resolve authenticated tenant context without broad RLS bypass.
- Organization/user RLS bootstrapping problem is solved explicitly.
- Clerk token/local organization mismatch fails with controlled `403`.

### WBS 3.1 - FastAPI Tenant Context Setup

Depends on: WBS 2.1, WBS 2.2, WBS 3.0.

Tasks:

- Set DB tenant context after authenticated user and organization are validated.
- Ensure context is set before tenant-owned queries.
- Fail closed when authenticated user has no valid organization.
- Keep public/health endpoints separate from tenant context.
- Ensure commit/rollback does not leak tenant context to another request.

Acceptance criteria:

- API requests under org A cannot read/write org B even if a service query is missing a filter.
- Auth errors happen before tenant data access.
- Tests cover inactive users, missing org, and org mismatch.

### WBS 3.2 - Sync Worker Tenant Context Setup

Depends on: WBS 2.1, WBS 2.2.

Tasks:

- Add sync helper for setting tenant context.
- Require `organization_id` in every tenant-scoped worker job.
- Validate task ownership before setting context.
- Ensure context is transaction-local for worker DB sessions.

Acceptance criteria:

- Solver and repair tasks run successfully under RLS.
- Worker task without tenant context fails before data access.
- Worker task for org A cannot read/write org B.

### WBS 3.3 - Update Service Queries

Depends on: WBS 0.3, WBS 1.1.

Tasks:

- Add direct `organization_id` filters to queries on newly tenant-owned tables.
- Update inserts to populate direct `organization_id`.
- Update upserts to include new tenant-aware constraints.
- Update deletes/updates to use tenant-leading filters.
- Update relationship queries to avoid accidental cross-tenant assumptions.

Acceptance criteria:

- No service inserts unscoped rows.
- No bulk mutation lacks tenant scoping.
- Tests pass under RLS.

### WBS 3.4 - Update Seed, Fixture, Import, and Bootstrap Paths

Depends on: WBS 1.1, WBS 3.1.

Tasks:

- Update `seed_data.py` and `seed_data_small_realistic.py`.
- Update `operational_seed_service.py`.
- Update test fixtures in `conftest.py`.
- Update bootstrap admin script.
- Update import endpoints to set tenant ownership on all created rows.

Acceptance criteria:

- Clean database can be seeded without constraint/RLS errors.
- Test fixtures create valid tenant-owned rows only.
- Import endpoints reject cross-tenant IDs.

### WBS 3.5 - Clean Architecture Verification

Depends on: WBS 3.1, WBS 3.2, WBS 3.3.

Tasks:

- Verify API/dependency layer owns Clerk/auth bootstrap and tenant context setup.
- Verify infrastructure layer owns RLS SQL, policies, triggers, grants, and low-level DB context helpers.
- Verify service/application layer receives resolved `organization_id` and does not import Clerk SDK, FastAPI request objects, JWT payloads, or RLS SQL.
- Verify domain logic does not read `app.current_organization_id` directly.
- Verify worker entrypoints set tenant context before calling services.
- Add import-boundary or focused static checks if practical.

Acceptance criteria:

- Security plumbing remains outside domain/business logic.
- No service layer uses client-provided `organization_id` as trusted tenant ownership.
- Architecture violations are documented or fixed before release gate review.

## 7. Tests

### WBS 4.1 - Schema and Migration Tests

Depends on: WBS 1.x.

Tasks:

- Test clean Alembic upgrade to head.
- Test downgrade if supported.
- Test metadata/schema alignment.
- Test required columns, constraints, and indexes.
- Verify RLS-specific schema tests do not use `Base.metadata.create_all()`.
- Mark RLS/policy/grant/trigger tests as PostgreSQL-required and mandatory in CI.
- Allow local non-PostgreSQL or metadata-created fast tests only when they do not claim RLS coverage.
- If downgrade is supported, verify removal of RLS policies, `ENABLE/FORCE ROW LEVEL SECURITY`, helper functions, validation triggers, grants, and migration-owned roles/privileges.
- If downgrade is irreversible, verify the migration explicitly states the supported development reset path.

Acceptance criteria:

- Schema tests pass on PostgreSQL.
- Any missing tenant column causes a clear test failure.
- Alembic-created schema is the source of truth for RLS coverage.

### WBS 4.2 - RLS Negative Tests

Depends on: WBS 2.2.

Tasks:

- Test no context: select/insert/update/delete denied.
- Test org A context cannot read org B.
- Test org A context cannot write org B.
- Test invalid context denies access.
- Test relationship/eager loads are RLS-filtered.
- Test `app_security.current_organization_id()` returns null and does not raise for unset, empty, non-numeric, negative, zero, integer overflow, and bigint overflow values.
- Test `app_security.current_organization_id()` returns valid ids for `1` and `2147483647`.

Acceptance criteria:

- RLS tests prove database-level isolation independent of service filters.
- Helper-function edge cases cannot produce unhandled database errors.

### WBS 4.3 - Same-Tenant Integrity Tests

Depends on: WBS 1.4.

Tasks:

- Test `availability` rejects teacher/timeslot mismatch.
- Test course/subject links reject mismatches.
- Test teacher/subject links reject mismatches.
- Test class/subject/teacher links reject mismatches.
- Test module/subject mismatch is impossible.
- Test class progress class/module mismatch is rejected.
- Test lesson and schedule output mismatches are rejected.
- Test occurrence and operational block mismatches are rejected.

Acceptance criteria:

- Each high-risk cross-tenant reference has a failing test before valid same-tenant control case.

### WBS 4.4 - API Regression Tests Under RLS

Depends on: WBS 2.2, WBS 3.1, WBS 3.3.

Tasks:

- Add positive controls proving legitimate same-tenant list/detail/create/update/delete flows still work under RLS.
- Run existing CRUD tests under RLS.
- Run tenant isolation tests under RLS.
- Run role regression tests under RLS.
- Add IDOR tests using path IDs and body IDs for newly hardened tables.
- Verify nonexistent body references and cross-tenant body references return the same generic invalid-reference response within each endpoint contract.

Acceptance criteria:

- Existing functional behavior remains correct.
- Same-tenant access works correctly under RLS.
- Cross-tenant attempts return expected 403/404/422 without data leakage.

### WBS 4.5 - Worker and Solver Tests Under RLS

Depends on: WBS 2.2, WBS 3.2.

Tasks:

- Run solver data-loading tests under tenant context.
- Run schedule generation and draft lifecycle tests under RLS.
- Test task ownership mismatch.
- Test cancellation/status paths under tenant context.

Acceptance criteria:

- Sync sessions work under RLS.
- Missing/mismatched worker context fails closed.

### WBS 4.6 - Performance and Query Plan Tests

Depends on: WBS 1.3, WBS 3.3.

Tasks:

- Run existing performance tests.
- Add representative EXPLAIN checks for high-volume queries.
- Compare key endpoints before/after where possible.
- Validate index use on tenant-leading predicates.

Acceptance criteria:

- No unacceptable regression.
- High-volume queries use expected tenant-leading indexes.

## 8. Documentation and Developer Experience

### WBS 5.1 - Update Security Baseline

Depends on: WBS 2.2.

Tasks:

- Document RLS as mandatory.
- Document transaction-local tenant context.
- Document direct `organization_id` rule.
- Document fail-closed behavior.

Acceptance criteria:

- Security baseline reflects final architecture.

### WBS 5.2 - Update Endpoint and Query Standards

Depends on: WBS 3.3.

Tasks:

- Update endpoint standards with RLS context rules.
- Update best practices for tenant-leading filters.
- Add raw SQL rules.
- Add worker/session rules.

Acceptance criteria:

- Developers know how to add a tenant-owned query safely.

### WBS 5.3 - Update Database Audit

Depends on: WBS 5.1.

Tasks:

- Replace "remaining risks" with implemented controls.
- Link final PRD and WBS.
- Record final table ownership matrix.

Acceptance criteria:

- Audit no longer describes RLS as missing after implementation.

### WBS 5.4 - Add Operational Notes

Depends on: WBS 2.1.

Tasks:

- Document migration DB role.
- Document API DB role.
- Document how to run seed scripts safely.
- Document how to debug RLS denial.

Acceptance criteria:

- Local development and CI can run migrations/tests predictably.

## 9. Release and Verification

### WBS 6.1 - Full Backend Verification

Depends on: WBS 4.x.

Tasks:

- Run full backend pytest suite.
- Run Alembic upgrade/downgrade checks.
- Run lint/type checks if configured.
- Run seed scripts on clean database.

Acceptance criteria:

- Full backend verification passes.

### WBS 6.2 - Frontend Smoke Verification

Depends on: WBS 6.1.

Tasks:

- Start backend and frontend locally.
- Verify admin flows still load.
- Verify teacher self-service flows still load.
- Verify auth/org mismatch cannot leak data.

Acceptance criteria:

- No user-facing regression caused by DB hardening.

### WBS 6.3 - Release Gate Review

Depends on: WBS 6.1, WBS 6.2, WBS 5.x.

Tasks:

- Review PRD acceptance criteria one by one.
- Review test evidence.
- Review schema diff.
- Review policy drift test.
- Review remaining risks.

Acceptance criteria:

- All PRD acceptance criteria are met or explicitly deferred with approval.
- No P0/P1 tenant isolation risk remains open.

## 10. Dependency Map

```text
WBS 0.1 -> WBS 0.2 -> WBS 1.1 -> WBS 1.2
                  \              -> WBS 1.3
                   \             -> WBS 1.4 -> WBS 1.5
                    \
                     -> WBS 0.3 -> WBS 3.3 -> WBS 4.4
                                           \-> WBS 4.6

WBS 0.1 -> WBS 2.1 -> WBS 2.2 -> WBS 2.3
                         \        \
                          \        -> WBS 3.0 -> WBS 3.1 -> WBS 4.4
                           \       -> WBS 3.2 -> WBS 4.5
                            \
                             -> WBS 4.2

WBS 3.1 + WBS 3.2 + WBS 3.3 -> WBS 3.5 -> WBS 6.3

WBS 1.x -> WBS 4.1 -> WBS 6.1
WBS 1.4 -> WBS 4.3 -> WBS 6.1
WBS 1.3 -> WBS 4.6 -> WBS 6.1

WBS 5.x -> WBS 6.3
WBS 6.1 + WBS 6.2 -> WBS 6.3
```

## 11. Risk Register

| Risk | Probability | Impact | Mitigation |
|---|---:|---:|---|
| RLS bypassed by table owner role | Medium | Critical | Use non-owner API role and verify `FORCE ROW LEVEL SECURITY`. |
| Deployment PostgreSQL version differs from target | Low | High | Gate implementation on PostgreSQL 15+ verification or explicit redesign. |
| Expected RLS denial becomes HTTP 500 | Medium | High | Prevalidate tenant context and map unexpected RLS write denials to controlled 403. |
| Test setup bypasses Alembic RLS DDL | High | High | Add Alembic-based PostgreSQL integration tests. |
| Developer skips PostgreSQL-only RLS tests locally | Medium | Medium | Permit local fast subsets, but make PostgreSQL RLS tests mandatory in CI/release evidence. |
| Pooled connection leaks tenant context | Medium | Critical | Use transaction-local setting and tests across sequential tenants. |
| Cross-tenant FK still possible in a complex table | Medium | Critical | Same-tenant integrity test matrix. |
| Query performance regresses under RLS | Medium | Medium | Tenant-leading indexes and EXPLAIN checks. |
| Seed scripts fail after strict constraints | High | Medium | Update seeds in dedicated WBS before full regression. |
| Migration drift persists | Medium | High | Metadata/schema alignment tests. |

## 12. Definition of Done

The implementation is done only when:

1. PRD acceptance criteria pass.
2. Every WBS item is complete or formally removed from scope.
3. Full backend test suite passes under PostgreSQL.
4. RLS negative tests pass.
5. Same-tenant integrity tests pass.
6. Seed/import/bootstrap paths create only valid tenant-owned data.
7. Documentation is updated.
8. Clean architecture verification passes.
9. No known P0/P1 tenant isolation issue remains.
