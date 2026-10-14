---
name: cronos-backend
description: Cronos backend skill. Use for FastAPI endpoints, services, Pydantic schemas, SQLAlchemy models, Alembic migrations, Clerk authentication on the backend, RLS, and backend tests.
---

# Cronos Backend

Load `cronos-base` and `ponytail` first.

## Start here

- Router wiring: `backend/app/api/api.py` (mounted under `/api/v1` in `backend/app/main.py`).
- Endpoints: `backend/app/api/v1/endpoints/<area>.py`. Services: `backend/app/services/<area>_service.py`.
- Auth and actors: `backend/app/api/deps.py` (`AdminActor`, `ActiveActor`, `get_db`).
- Errors: `backend/app/core/exceptions.py` (`AppError` and the error envelope).
- Models: `backend/app/models.py`; scheduler models: `backend/app/scheduler/infrastructure/models.py`. Schemas: `backend/app/schemas.py`.

## Reference implementation

Copy the Rooms resource for a new CRUD feature:
`backend/app/api/v1/endpoints/rooms.py` -> `backend/app/services/room_service.py` -> `backend/tests/integration/committed/test_rooms_crud.py`.
Keep the endpoint thin: authorize with an actor dependency, call one service function, map errors to `AppError`.

## Minimal proof

- Pure logic: `node scripts/test.mjs fast --scope backend -- -k <area>`.
- Endpoint, service, query, or migration: add `node scripts/test.mjs integration -- -k <area>`.
- Migration: also run the drift and audit checks in the [Command Reference](../../../documentation/00_getting_started/COMMAND_REFERENCE.md#backend-checks-outside-the-runner).

## Boundaries

- Tests run only against `cronos_test_db`, `cronos_ci_db`, `cronos_test_gw<N>`, or `cronos_ci_gw<N>`. `backend/tests/db.py` refuses every other name.
- Every tenant query filters by `organization_id`. New tenant tables need `organization_id`, forced RLS, and policies in the migration.
- Add migrations on top of `0001_scheduler_v1_baseline`. One linear chain; no branches or merges.
- `get_db` commits after the handler returns. Do not commit inside a handler unless the pattern already does so for provider side effects.
- The API process never imports `app.scheduler_v1_worker` or OR-Tools.
- Clerk role or invitation changes go through `backend/app/services/member_access_operation_service.py` (saga with compensation), never a direct Clerk call.

## Pitfalls

- `models.py`, `schemas.py`, and `services/member_service.py` are each about 2,000 lines. Read only the class or function you need; search by name.
- Static routes such as `/me/...` must stay above `/{id}/...` routes in the same router.
- Two error styles exist: `AppError` directly, and domain errors translated in the endpoint (for example `OperationsError` in `schedule.py`). Follow the style of the file you edit.
- New frontend-visible endpoints may need an entry in `frontend/src/features/tutorial/tutorialApiAdapter.js`.
- Stale `.pyc` files under `backend/alembic/versions/__pycache__/` can mislead text search. Only `.py` files are revisions.

## Done when

- A failing test existed first and now passes, at the right level (unit for rules, integration for queries and endpoints).
- The proof above passed and is named in the pull request.
- The relevant guide under `documentation/05_backend_api/` or the feature guide is updated.

## Documentation

- [Backend Architecture](../../../documentation/05_backend_api/BACKEND_ARCHITECTURE.md)
- [API Reference](../../../documentation/05_backend_api/API_REFERENCE.md)
- [Errors and Transactions](../../../documentation/05_backend_api/ERRORS_AND_TRANSACTIONS.md)
- [Resource Removal](../../../documentation/05_backend_api/RESOURCE_REMOVAL.md)
- [Security and Tenant Isolation](../../../documentation/08_security_quality/SECURITY_AND_TENANT_ISOLATION.md)
