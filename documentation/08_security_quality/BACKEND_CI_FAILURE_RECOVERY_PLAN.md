# Backend CI Failure Recovery Plan

## Purpose

This plan updates the original CI recovery plan after a second, stricter review of the attached GitHub Actions backend log.

The goal is not only to make the current 43 backend failures pass. The goal is to remove the failure class that produced them:

- stale database security objects drifting from SQLAlchemy models;
- RLS/helper SQL contracts not being tested before the full suite;
- asyncpg connections crossing pytest event loops;
- test data that violates production response schemas;
- CI ordering that lets one migration bug explode into many noisy scheduler failures.

The correction must be implemented in a way that preserves clean architecture:

- database invariants stay in Alembic/security SQL and are verified by focused DB contract tests;
- application services do not weaken public schemas to accommodate invalid fixtures;
- test infrastructure owns test-only async pooling choices;
- scheduler business logic is not changed until the database contract is clean and remaining scheduler failures are proven independent.

## Evidence From CI

The backend CI log reports:

- `523` tests collected.
- `478` passed.
- `2` skipped.
- `43` failed.

The failures cluster into a small number of root causes.

### Cluster A: Stale tenant-ref trigger definitions

Visible log errors:

- `record "new" has no field "approved_by_user_id"`
- `validate_active_schedule_blocks_tenant_refs references missing columns: ['draft_block_id', 'draft_id', 'module_id', 'source_occurrence_id']`

The visible log does not show every stale reference. A static metadata audit of `SAME_TENANT_REFS` against SQLAlchemy metadata found additional mismatches:

| Table | Stale refs in migration map | Correct direction |
| --- | --- | --- |
| `schedule_drafts` | `approved_by_user_id` | Replace with `decided_by_user_id`. |
| `schedule_draft_blocks` | `module_id`, `source_occurrence_id` | Remove both. `module_sequence_index` is not a FK; recovery lineage uses `recovery_source_occurrence_id`. |
| `schedule_diff_entries` | `room_id`, `timeslot_id` | Replace with actual before/after refs if tenant enforcement is needed: `before_room_id`, `after_room_id`, `before_timeslot_id`, `after_timeslot_id`. |
| `active_schedule_blocks` | `draft_id`, `draft_block_id`, `module_id`, `source_occurrence_id` | Replace draft lineage with `source_draft_block_id`; remove `module_id` and occurrence refs. |
| `planned_recovery_links` | `recovery_block_id` | Replace with `planned_active_block_id` and `planned_draft_block_id`, both nullable. |

Why this happens:

- `SAME_TENANT_REFS` is a hand-maintained duplicate of ORM foreign-key metadata.
- PL/pgSQL trigger bodies are not validated at function creation time.
- The full backend suite reaches trigger execution before a focused contract gate stops the run.

### Cluster B: RLS privileges and missing security helper API

Visible log errors:

- `assert True is False` for append-only table `UPDATE`/`DELETE` privileges.
- `function app_security.ensure_user(unknown, unknown, unknown, unknown, integer, unknown) does not exist`.

Why this happens:

- The migration grants `SELECT, INSERT, UPDATE, DELETE` to `cronos_app` on every public table, but the contract expects append-only scheduler audit tables to deny `UPDATE` and `DELETE`.
- Tests expect an `app_security.ensure_user(...)` helper, but the migration only creates `ensure_organization`, `update_user_profile`, and deactivate helpers.
- Existing `resolve_auth_context` currently returns `true` for `is_active` and does not filter inactive users, which conflicts with `deactivate_user`.

### Cluster C: Scheduler failures caused by DB trigger failures

Visible log errors:

- lifecycle event expected `generation_succeeded`, got `generation_failed`;
- `AttributeError: 'NoneType' object has no attribute 'id'`;
- many scheduler assertions fail after no draft was persisted.

Why this happens:

- Scheduler draft insert fails inside tenant-ref triggers.
- The runtime correctly marks jobs as failed.
- Later assertions assume a draft exists, so failures cascade.

These are not primary scheduler defects until proven after DB contract repair.

### Cluster D: Asyncpg event-loop reuse in tests

Visible log errors:

- `Future ... attached to a different loop`;
- `MissingGreenlet` noise in tests that run after failed transactions or use ORM instances after rollback/expiry.

Why this happens:

- `pytest-asyncio` is configured with function-scoped event loops.
- Application `SessionLocal` uses pooled asyncpg connections by default.
- Some tests import the application session factory directly or use ASGI requests through middleware that can cross task boundaries.
- Local webhook `async_client` is not an async context-managed fixture, so client lifecycle is looser than it should be.

### Cluster E: Invalid fixture email rejected by production schema

Visible log error:

- `MemberRead.email` rejects `fresh.session.admin@test.local`.

Why this happens:

- `EmailStr` correctly treats `.local` as a special-use/reserved name.
- The fixture uses invalid response data for an endpoint whose public schema requires a valid email.

This should be fixed in fixtures, not by weakening the schema.

## Critical Review Of The Previous Plan

The previous plan had the right overall direction but needs these corrections.

### Flaw 1: It planned to fix only the visibly logged trigger refs

The log exposes `schedule_drafts.approved_by_user_id` and the first bad `active_schedule_blocks` trigger body. It does not expose all stale trigger-map entries because the suite stops at the first assertion per trigger audit and many tests fail earlier.

Correction:

- Audit the entire `SAME_TENANT_REFS` map against `Base.metadata`.
- Fix every stale entry in one pass.
- Add a guard that fails with all mismatches before any trigger SQL is generated.

### Flaw 2: It suggested adding `ensure_user` without fully defining the security contract

Adding the function name is insufficient. It must be safe under RLS and identity conflicts.

Correction:

- Define exact function semantics, grants, ownership, validation, role mapping, membership writes, and last-admin behavior.
- Update application code to use the helper only where the helper matches the product flow.
- Keep webhook/member reconciliation service logic as the owner of complex provider reconciliation; do not move all Clerk behavior into SQL.

### Flaw 3: It treated scheduler `MissingGreenlet` as mostly cascade without a cleanup path

Some `MissingGreenlet` traces are indeed downstream of failed draft creation, but tests should still avoid ORM attribute access after rollback/expiry when primitive IDs would be clearer.

Correction:

- First repair DB contract.
- Then rerun scheduler tests.
- Only if `MissingGreenlet` remains, refactor tests/services to keep primitive IDs across commits/rollbacks and avoid lazy attribute loads in async contexts.

### Flaw 4: It did not change CI ordering

A broken migration contract should fail in a small DB contract step before running all backend tests.

Correction:

- Add a fast backend DB contract gate immediately after `alembic upgrade head`.
- Run the full backend suite only after the DB contract gate passes.

### Flaw 5: It allowed a broad test pooling switch without clear ownership

Disabling pooling should be explicit and test-owned.

Correction:

- Add an application setting such as `DATABASE_POOLING_ENABLED`.
- In tests and CI, set it to `false`.
- In production/staging/local default runtime, keep pooling enabled.

## Detailed Implementation Plan

### Phase 1: Add a model-vs-trigger-map contract helper

Implement a small reusable helper that validates tenant-ref map entries before SQL generation.

Preferred location:

- `backend/alembic/versions/20260705_beta_baseline.py` for immediate migration safety.
- Optional later extraction: `backend/scripts/audit_triggers.py` or a dedicated test helper if reuse grows.

Implementation detail:

1. Import/register models before reading `Base.metadata`.
2. Build a set of table names and columns from `Base.metadata.tables`.
3. For each `table, refs` in `SAME_TENANT_REFS`:
   - verify `table` exists;
   - verify each local column exists;
   - normalize quoted ref table names like `"user"` and `"class"`;
   - verify each referenced table exists;
   - verify referenced table has `id`;
   - verify referenced table has `organization_id`, except for `organization` itself.
4. Collect all errors and raise one `RuntimeError` with the complete list.
5. Call this guard before `_install_security_objects()` creates trigger functions.

Acceptance criteria:

- A stale column in `SAME_TENANT_REFS` fails migration/test setup before PL/pgSQL trigger creation.
- The error reports all stale refs, not only the first one.

### Phase 2: Correct `SAME_TENANT_REFS`

Update the map to match actual model columns and intended tenant boundaries.

Exact corrections:

```python
"schedule_drafts": {
    "generation_job_id": "schedule_generation_job",
    "created_by_user_id": '"user"',
    "decided_by_user_id": '"user"',
}
```

```python
"schedule_draft_blocks": {
    "draft_id": "schedule_drafts",
    "class_id": '"class"',
    "subject_id": "subject",
    "teacher_id": "teacher",
    "timeslot_id": "timeslot",
    "room_id": "room",
    "source_active_block_id": "active_schedule_blocks",
    "recovery_source_occurrence_id": "lesson_occurrence",
}
```

```python
"schedule_diff_entries": {
    "draft_id": "schedule_drafts",
    "class_id": '"class"',
    "subject_id": "subject",
    "teacher_id": "teacher",
    "before_room_id": "room",
    "after_room_id": "room",
    "before_timeslot_id": "timeslot",
    "after_timeslot_id": "timeslot",
}
```

```python
"active_schedule_blocks": {
    "source_draft_block_id": "schedule_draft_blocks",
    "class_id": '"class"',
    "subject_id": "subject",
    "teacher_id": "teacher",
    "timeslot_id": "timeslot",
    "room_id": "room",
}
```

```python
"planned_recovery_links": {
    "debt_occurrence_id": "lesson_occurrence",
    "planned_active_block_id": "active_schedule_blocks",
    "planned_draft_block_id": "schedule_draft_blocks",
}
```

Important note:

- Do not add fake columns to models to satisfy old trigger SQL.
- Do not add `module_id` back to `schedule_draft_blocks` or `active_schedule_blocks` unless the domain model explicitly requires module FK persistence. Current model uses `module_sequence_index` for draft blocks.

Acceptance criteria:

- `tests/test_runtime_reality.py::test_tenant_ref_trigger_functions_only_reference_existing_columns` passes.
- Insert/update operations that create scheduler drafts no longer fail with `approved_by_user_id`.

### Phase 3: Tighten tenant trigger SQL generation

Improve `_create_same_tenant_trigger` so it is correct for nullable refs and scoped composite FKs.

Minimum change:

- Keep current `IF NEW.col IS NOT NULL AND NOT EXISTS (...)` pattern.
- Use corrected local columns.
- Keep `organization_id` equality check.

Better proactive change:

- For refs with composite scoped FKs in models, consider a future helper that verifies both `organization_id` and `school_year_id` where the referenced table has `school_year_id`.
- Do not overbuild this now unless tests fail; current contract only validates tenant organization scope.

Acceptance criteria:

- Trigger functions compile and execute.
- Trigger audit tests pass.

### Phase 4: Fix append-only scheduler table privileges

Define:

```python
APPEND_ONLY_TABLES = (
    "schedule_draft_blocks",
    "schedule_diff_entries",
    "scheduler_state_version_events",
)
```

After the blanket `cronos_app` table grant, execute:

```sql
REVOKE UPDATE, DELETE ON public.schedule_draft_blocks FROM cronos_app;
REVOKE UPDATE, DELETE ON public.schedule_diff_entries FROM cronos_app;
REVOKE UPDATE, DELETE ON public.scheduler_state_version_events FROM cronos_app;
```

Also update default privileges strategy:

- Keep default blanket grants if needed for ordinary app tables.
- Explicitly revoke append-only privileges after all tables exist.
- Document this in the migration so future tables are added consciously.

Acceptance criteria:

- `has_table_privilege('cronos_app', ..., 'UPDATE')` is false for append-only scheduler tables.
- `has_table_privilege('cronos_app', ..., 'DELETE')` is false for append-only scheduler tables.
- App-owned service code still writes append-only rows through `INSERT`.

### Phase 5: Implement `app_security.ensure_user(...)`

Create a security-definer helper matching the tested signature:

```sql
app_security.ensure_user(
    p_clerk_user_id text,
    p_email text,
    p_display_name text,
    p_app_role text,
    p_organization_id integer,
    p_teacher_id integer
)
RETURNS TABLE(id integer, organization_id integer)
```

Function responsibilities:

1. Validate required inputs:
   - `p_clerk_user_id` length 1-255;
   - `p_email` present and nonblank;
   - `p_organization_id` exists;
   - `p_app_role` maps to admin or teacher/member.
2. Normalize role:
   - `admin`, `org:admin` -> `public.userrole 'admin'`, capability `admin`, expected Clerk role `org:admin`;
   - `member`, `teacher`, `org:member` -> `public.userrole 'teacher'`, capability `teacher`, expected Clerk role `org:member`.
3. Prevent identity collisions:
   - if another user has same `clerk_user_id`, use that user only;
   - if another user has same email but different `clerk_user_id`, raise an exception or return no row consistently with the product contract;
   - do not silently reassign a Clerk identity across accounts.
4. Upsert `public."user"`:
   - set email, name, role, teacher_id, clerk profile fields, `is_active = true`;
   - set `organization_id` for compatibility columns.
5. Upsert `public.organization_membership`:
   - one active membership for `(organization_id, account_id)`;
   - `organization_display_name = coalesce(nullif(p_display_name, ''), p_email)`;
   - `lifecycle_status = 'active'`;
   - `access_status = 'active'`;
   - `teacher_access_mode = 'platform'` only for teacher/member role if this enum is available and consistent with model values;
   - `expected_clerk_role` from normalized role.
6. Replace capabilities for this membership:
   - ensure exactly the intended capability for this helper call unless product requires mixed capabilities;
   - if mixed admin+teacher is a valid product state, do not delete existing unrelated capability without an explicit policy.
7. Return the user id and organization id.

Required grants:

- `cronos_auth_definer` needs `SELECT, INSERT, UPDATE` on:
  - `organization`;
  - `"user"`;
  - `organization_membership`;
  - `organization_membership_capability`.
- `cronos_auth_definer` needs `USAGE, SELECT` on relevant sequences.
- `cronos_app` gets only `EXECUTE` on the function, not direct escalated table privileges.

Ownership/security:

- Function is `SECURITY DEFINER`.
- Owner is `cronos_auth_definer`.
- `search_path` is pinned to `pg_catalog, public`.
- Revoke from `PUBLIC`; grant execute to `cronos_app`.

Application service alignment:

- Update `backend/app/services/clerk_sync.py::ensure_user_exists` to call `app_security.ensure_user(...)` when `organization_id` is provided and the flow is intended to create/update a user plus membership.
- Preserve the existing `update_user_profile` path for profile-only updates without a membership.
- Do not bypass `member_reconciliation_service` for provider conflict flows unless the helper fully encodes the same conflict rules.

Acceptance criteria:

- `test_auth_definer_helpers_work_without_tenant_context_and_preserve_alembic_table` passes.
- `test_deactivate_user_preserves_last_active_admin` passes.
- `cronos_app` still cannot insert into `alembic_version`.

### Phase 6: Fix `resolve_auth_context` and `deactivate_user`

Update `resolve_auth_context`:

- Return `u.is_active` instead of hardcoded `true`.
- Filter active auth context to `u.is_active = true`, unless callers need inactive context for diagnostics.
- Keep membership filters for active lifecycle/access.

Update `deactivate_user`:

- Find the target user by Clerk id.
- If the user is superuser, return `false`.
- If the user is the last active admin capability in any active organization membership, return `false`.
- Otherwise set `user.is_active = false`.
- Also consider setting active memberships to `blocked` if product semantics require provider-user deletion to revoke access immediately. If that is already handled by webhook service, do not duplicate it here.

Acceptance criteria:

- Last active admin cannot be deactivated by the helper.
- Non-last member/admin can be deactivated.
- Auth resolution does not authenticate inactive users.

### Phase 7: Make async DB pooling test-safe

Add a setting:

```python
DATABASE_POOLING_ENABLED: bool = True
```

In `backend/app/db/database.py`:

- if enabled, keep current pooled async engine with `pool_pre_ping=True`;
- if disabled, create async engine with `poolclass=NullPool`;
- apply the same policy to sync engine only if sync tests show pooled-connection leakage; otherwise leave sync engine as-is.

In test/CI env:

- Set `DATABASE_POOLING_ENABLED=false` before importing app DB modules.
- Add it to GitHub Actions backend test env.
- Add it to docker-compose CI services if E2E uses pytest or app test mode.

In `backend/tests/conftest.py`:

- Set `os.environ["DATABASE_POOLING_ENABLED"] = "false"` before app imports.
- Keep `TestingSessionLocal` based on a `NullPool` test engine.

In `backend/tests/test_scheduler_generation_service.py`:

- Avoid importing app `SessionLocal` for concurrency tests.
- Use `TestingSessionLocal` from `tests.conftest`, or a local test session factory using `NullPool`.

In `backend/tests/test_webhooks.py`:

- Convert the local `async_client` fixture to an async generator:

```python
@pytest_asyncio.fixture
async def async_client():
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
```

Acceptance criteria:

- `Future attached to a different loop` no longer appears.
- Webhook idempotency test passes.
- Scheduler concurrent job test passes or fails only with a real domain/concurrency assertion.

### Phase 8: Clean invalid fixture email data

Replace invalid `.local` emails in `backend/tests/test_runtime_reality.py`:

- `trigger.reality@test.local` -> `trigger.reality@example.com`
- `fresh.session.admin@test.local` -> `fresh.session.admin@example.com`

Optional proactive helper:

- Add a test helper such as `valid_test_email(prefix: str) -> str` returning `f"{prefix}@example.com"`.
- Use it in fixtures that feed API response schemas.

Acceptance criteria:

- `MemberRead.email` remains `EmailStr`.
- `test_fresh_session_requests_cover_core_beta_surfaces` no longer fails on fixture email validation.

### Phase 9: Reduce scheduler-test noise after DB repair

After phases 1-8, rerun scheduler tests. If scheduler failures remain:

1. Identify whether draft creation now succeeds.
2. If draft creation succeeds but `MissingGreenlet` remains:
   - store primitive IDs before operations that may commit/rollback;
   - avoid accessing expired ORM attributes outside awaited SQLAlchemy calls;
   - reload rows explicitly with `await db_session.get(...)` or `select(...)`;
   - avoid shared `db_session` use inside concurrent tasks.
3. Only change scheduler domain services if the failure is a real behavior mismatch.

Acceptance criteria:

- Scheduler tests fail only for genuine scheduler behavior, not infrastructure noise.

### Phase 10: Add fast DB contract gate to CI

Add a backend CI step immediately after `Run Migrations` and before `Run Tests`:

```yaml
- name: Run DB contract tests
  working-directory: backend
  run: pytest tests/test_runtime_reality.py tests/test_rls_database_policies.py -m postgresql -v --tb=short
  env:
    ENVIRONMENT: local
    DATABASE_URL: "postgresql+asyncpg://postgres:ci_pg_pass@localhost:5432/cronos_test_db"
    DATABASE_POOLING_ENABLED: "false"
    SECRET_KEY: ci-test-secret-key-not-for-production
    RATELIMIT_ENABLED: "false"
    CLERK_SECRET_KEY: ${{ secrets.CLERK_SECRET_KEY }}
    CLERK_WEBHOOK_SECRET: ${{ secrets.CLERK_WEBHOOK_SECRET }}
    CLERK_PUBLISHABLE_KEY: ${{ secrets.CLERK_PUBLISHABLE_KEY }}
```

Also add `DATABASE_POOLING_ENABLED=false` to the existing backend `Run Tests` and `Run PostgreSQL reality tests` steps.

Acceptance criteria:

- A stale migration/security contract fails before the full 523-test suite runs.
- Full backend test logs become much shorter and easier to triage.

## Verification Plan

Run in this order.

### 1. Static migration map audit

```bash
cd backend
python scripts/audit_triggers.py
```

If no script exists yet, run the new helper through pytest or a small import check.

Expected:

- no missing local columns;
- no missing referenced tables;
- no missing referenced `organization_id` columns where tenant check is expected.

### 2. Fresh migration

```bash
cd backend
alembic upgrade head
```

Expected:

- migration succeeds from an empty DB;
- app_security functions exist;
- trigger creation succeeds.

### 3. PostgreSQL contract tests

```bash
cd backend
pytest tests/test_runtime_reality.py tests/test_rls_database_policies.py -m postgresql -v --tb=short
```

Expected:

- tenant trigger audit passes;
- append-only privileges are denied;
- `ensure_user`, `update_user_profile`, and deactivation helpers pass;
- fresh session API surface test passes.

### 4. Async loop regression tests

```bash
cd backend
pytest tests/test_webhooks.py::test_webhook_idempotency_uses_svix_event_id tests/test_scheduler_generation_service.py::test_simultaneous_job_admission_reuses_one_active_job -v --tb=short
```

Expected:

- no cross-loop asyncpg errors;
- no unclosed client warnings.

### 5. Scheduler cascade recheck

```bash
cd backend
pytest tests/test_debt_basis_fingerprint.py tests/test_lesson_registration.py::TestActiveBaselineOperationalCutover tests/test_scheduler_generation_service.py tests/test_scheduler_job_runtime.py tests/test_scheduler_state_service.py tests/test_scheduler_status.py tests/test_scheduler_tenant_isolation.py -v --tb=short
```

Expected:

- no `approved_by_user_id` trigger failures;
- no draft `NoneType` cascade from failed inserts;
- lifecycle tests produce `generation_succeeded` when the engine output is valid.

### 6. Full backend CI equivalent

```bash
cd backend
pytest tests/ -v --cov=app --cov-report=xml:coverage.xml --tb=short
pytest tests/ -m postgresql -v --tb=short
```

Expected:

- all backend tests pass, except known intentional skips below the skip threshold.

## Preventive Controls

### Control 1: Metadata-backed trigger contract

Keep the trigger map validated against model metadata every time migrations/tests run.

This prevents:

- renamed columns breaking PL/pgSQL at runtime;
- deleted columns staying in trigger functions;
- future schema drift being discovered only in CI after hundreds of tests.

### Control 2: DB contract CI gate before full tests

Run a small, focused database contract suite immediately after migrations.

This prevents:

- one broken migration becoming dozens of scheduler/API failures;
- noisy CI logs hiding the real root cause.

### Control 3: Explicit append-only privilege policy

Keep append-only table names centralized and tested.

This prevents:

- future blanket grants accidentally giving mutation privileges to audit/history tables.

### Control 4: Test-safe async DB pooling

Use `NullPool` for pytest under function-scoped event loops.

This prevents:

- asyncpg connection reuse across event loops;
- intermittent `Future attached to a different loop` errors.

### Control 5: Valid public-schema test fixtures

Use valid domains for emails that pass through `EmailStr`.

This prevents:

- accidental weakening of API schemas;
- test fixtures diverging from public contract expectations.

### Control 6: Scheduler triage discipline

Do not edit scheduler business logic while DB contract failures exist.

This prevents:

- masking infrastructure defects with domain workarounds;
- introducing regressions into scheduling behavior based on cascade symptoms.

## Out Of Scope

Do not do these as part of this recovery unless follow-up failures prove they are needed:

- weaken `MemberRead.email`;
- add old/stale columns back to scheduler models just to satisfy trigger SQL;
- rewrite scheduler generation/approval logic before DB contract tests pass;
- remove RLS or security-definer helpers to make tests easier;
- disable the PostgreSQL reality tests.

## Done Criteria

The work is complete when:

- all stale trigger-map entries are corrected;
- the trigger-map guard fails fast with complete diagnostics;
- RLS append-only privilege tests pass;
- `app_security.ensure_user(...)`, `resolve_auth_context`, and `deactivate_user` behave consistently;
- async loop errors are gone under CI pytest settings;
- invalid `.local` fixture emails are removed from response-schema tests;
- backend full suite and PostgreSQL reality tests pass;
- CI runs the DB contract gate before the full backend suite.
