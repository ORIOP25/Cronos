# Beta Baseline Legacy Cleanup Audit

Date: 2026-07-05

## Purpose

This audit makes the reworked `Equipa` and schedule-generator implementations the launch baseline. The goal is not feature expansion; it is removal of legacy code, deprecated tests, old migrations, and misleading documentation so the codebase can be trusted for beta demonstrations.

## Decisions Applied

1. `Equipa` is the canonical visible admin staff-management surface.
   - Frontend admin route is `/members`.
   - Visible `/teachers` admin CRUD pages/forms/tests were removed.
   - Teacher-specific self-service/domain routes remain valid: `/teachers/me/availability`, `/teachers/me/progress`, and `/teachers/{teacher_id}/availability`.

2. Local membership capabilities are the authorization baseline.
   - Frontend role routing reads `/members/me`.
   - Backend admin/teacher checks use local `OrganizationMembershipCapability`.
   - Tests create membership-capability fixtures instead of relying on `User.role` alone.

3. Scheduler generation baseline is `/scheduler/generate`.
   - Retired compatibility endpoints under `/schedule/generate`, `/schedule/status`, `/schedule/cancel`, `/schedule/drafts`, and `/schedule/audit/*` were removed.
   - The request orchestration was extracted to `scheduler_request_service`.
   - Solver V2 experiment modules/tests and legacy lesson-assignment snapshot fallback were removed.

4. Migrations were reset for pre-launch beta.
   - Old Alembic revisions were removed.
   - `20260705_beta_baseline.py` is the only launch baseline revision.
   - The baseline creates current SQLAlchemy metadata and installs PostgreSQL RLS/app_security objects explicitly.

5. Repository cache artifacts are not source.
   - Tracked `.pnpm-store` files/junction were removed; `.gitignore` already ignores `.pnpm-store/`.

## How To Continue Verification

Run these checks after any follow-up cleanup:

1. Backend focused beta baseline:
   - `cd backend`
   - `$env:PYTHONPATH='.'`
   - `pytest tests/test_members_api.py tests/test_schedule_generate_preflight.py tests/test_scheduler_permissions.py tests/test_scheduler_status.py -q`
   - `pytest tests/test_availability_paintbrush.py tests/test_teacher_role_regression.py tests/test_teacher_competencies.py tests/test_tenant_isolation_business.py tests/test_rate_limiting.py tests/test_parametrized_error_contracts.py tests/test_onboarding.py -q`

2. Frontend focused beta baseline:
   - `cd frontend`
   - `npm test -- --run src/test/roleAccess.test.js src/test/AppRouteGuards.test.jsx src/test/SignedInRedirect.test.jsx src/test/DefaultLayout.test.jsx src/test/SchedulesSchedulerFlow.test.jsx`
   - `npm run lint -- --quiet`

3. Static scans:
   - No runtime references to removed schedule lifecycle endpoints.
   - No runtime references to solver V2 modules.
   - No staff-management mutation calls to `/api/v1/teachers` outside quarantine tests.

4. Alembic:
   - `cd backend`
   - `$env:PYTHONPATH='.'`
   - `alembic heads`
   - On a disposable database, run `alembic upgrade head`.

## Documentation Rule

Any document that still describes visible admin `/teachers` CRUD, password setup, solver V2, `/schedule/audit/*`, or older Alembic revision ids must be treated as historical unless it has been explicitly updated after this audit.
