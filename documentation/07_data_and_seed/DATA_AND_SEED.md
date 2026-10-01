# Data and Seed Specifications

## Purpose
This document specifies how Cronos creates application data: session bootstrap, foundation setup, bulk CSV import, and test-data preparation.

## Intended Reader
This document targets developers, QA engineers, and automated test runners.

## Prerequisites
Set up backend environment variables, start PostgreSQL, and run the current migrations.

## What the System Does
Cronos does not ship a standalone seed script.
The application creates data through the authenticated session and through administrator actions.
Test and E2E environments prepare their own disposable data.

## Data Creation Paths

| Path | Trigger | Result |
| :--- | :--- | :--- |
| Session bootstrap | First admin visit for an active organization | Local organization, membership, and account rows |
| Foundation completion | Admin completes the wizard | Operational school configuration and `COMPLETED` status |
| Bulk CSV import | Admin uses `/imports` | Rooms, subjects, courses, classes, teachers, and assignments |
| E2E preparation | `prepare_e2e_clerk_state.py` | A disposable organization with legal acceptance and a default foundation |
| Test reset | `reset_test_data.py` | Deleted scheduler test targets on a test database |

## Session Bootstrap
The frontend calls `POST /api/v1/session/bootstrap` with an active Clerk organization.
`SessionBootstrapService` requires an administrator role in the Clerk token.
The service reconciles the local organization, account, and membership from Clerk claims and directory data.
It returns the organization, the current member, and the foundation status.
The frontend then reads `GET /api/v1/members/me` for the current member.
The bootstrap reconciles existing rows and is safe to repeat.

## Foundation Draft and Completion
The foundation wizard uses `GET /api/v1/foundation/draft`, `PUT /api/v1/foundation/draft`, and `POST /api/v1/foundation/complete`.
`FOUNDATION_STEP_COUNT` is 10 in `frontend/src/features/foundation/foundationModel.js`.
The draft stores a version. A stale version causes a conflict state.
Completion sets the organization foundation status to `COMPLETED`.
Completion invalidates the foundation, member, dashboard, and readiness queries.

## Bulk CSV Import
Administrators add data through `/imports`.
The backend renders the templates and validates the files.
See [Administrative CSV import](BULK_IMPORT_CSV.md) for the templates and endpoints.

## Test and E2E Data Preparation
`backend/scripts/prepare_e2e_clerk_state.py` prepares the shared E2E organization.
It creates the Clerk-linked accounts and memberships.
It also seeds current legal acceptance and a default foundation through `FoundationService`.
The CI workflow and the local test runner invoke this script before E2E execution.

```bash
cd backend
python scripts/prepare_e2e_clerk_state.py
```

`backend/scripts/reset_test_data.py` deletes named scheduler test targets.
The command refuses any database that is not an owned test database.
It deletes children before parents and never contacts an external provider.

```bash
cd backend
python -m scripts.reset_test_data --database-url <test-url> --target scheduler-v1
```

## Contracts and Invariants
- No source file named `seed_data.py` exists.
- Bootstrap requires an active organization and an administrator token role.
- Each organization receives its own `organization_id` and forced RLS context.
- Foundation completion requires the current draft version.
- The bulk import commit is atomic. A failure prevents partial writes.
- Test preparation scripts are idempotent and never contact external providers, except the Clerk directory for E2E state.

## Failure Modes
- Missing Clerk configuration blocks bootstrap.
- A stale foundation draft version raises a conflict.
- A database without current migrations raises schema or security-function errors.
- The reset command raises an error for a non-test database.

## Verification Procedure
Run the focused backend tests for bootstrap, foundation, and imports.
Then run `pytest backend/tests/integration/committed/test_prepare_e2e_clerk_state.py -v`.

## Source Map
- Session bootstrap: `backend/app/services/session_bootstrap_service.py`
- Foundation service: `backend/app/services/foundation_service.py`
- E2E state service: `backend/app/services/e2e_clerk_state.py`
- E2E preparation script: `backend/scripts/prepare_e2e_clerk_state.py`
- Test reset script: `backend/scripts/reset_test_data.py`
- Bulk import policy: `backend/app/services/bulk_import_policy.py`
- Bulk import service: `backend/app/services/bulk_import_service.py`

## Related Documents
- [Local Runtime](../09_ops_observability/LOCAL_RUNTIME.md)
- [Testing and CI](../08_security_quality/TESTING_AND_CI.md)
- [Administrative CSV import](BULK_IMPORT_CSV.md)
