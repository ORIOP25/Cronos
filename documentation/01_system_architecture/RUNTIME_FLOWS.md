# Runtime Flows

## Purpose

This document describes authenticated requests, contact delivery, scheduler jobs, and Clerk webhook processing.

## Intended Reader

This document targets backend engineers and security engineers.

## Prerequisites

Read [System Architecture](SYSTEM_ARCHITECTURE.md) and [Backend Architecture](../05_backend_api/BACKEND_ARCHITECTURE.md).

## What the System Does

FastAPI handles request validation and orchestration.
Services perform database work.
Celery handles generation and repair outside the request process.

## Why the Behavior Exists

Explicit boundaries prevent provider adapters, authentication, and solver work from leaking into unrelated handlers.

## Components and Ownership

| Flow | Implementation |
| :--- | :--- |
| Authentication and tenant context | `backend/app/api/deps.py`, `backend/app/db/tenant.py` |
| Contact request | `backend/app/api/v1/endpoints/contact.py`, `backend/app/contact/` |
| Scheduler job | `backend/app/api/v1/endpoints/scheduler.py`, `backend/app/scheduler/infrastructure/task_dispatcher.py`, `backend/app/scheduler_worker.py` |
| Clerk webhook | `backend/app/api/v1/endpoints/webhooks.py`, `backend/app/services/member_webhook_service.py` |

## Data or Request Flow

### Authenticated API request

1. The client sends a Clerk Bearer token.
2. The API verifies the token and authorized party.
3. The API resolves the local user and active membership.
4. The database dependency sets `app.current_organization_id`.
5. The handler calls a service and returns a response.

### Public contact request

1. The body limit middleware checks `POST /api/v1/contact`.
2. Pydantic validates the `ContactSubmission` payload.
3. The application service checks the honeypot.
4. The Turnstile adapter validates `action` and `hostname`.
5. The Resend adapter sends text and escaped HTML.

### Scheduler request

1. The admin endpoint selects the strategy from school-year state.
2. The API records a `QUEUED` job.
3. The lightweight dispatcher calls `celery_app.send_task` with `scheduler.run_generation_job`.
4. The worker starts with `app.scheduler_worker`, registers the task, and creates an independent session and tenant context.
5. The selected engine builds candidates and runs CP-SAT.
6. The runtime stores a draft, diff data, and result category.

### Clerk webhook

1. Clerk sends `POST /api/v1/webhooks/clerk` with Svix headers.
2. Shared ASGI middleware enforces the 256 KiB webhook body budget before signature verification.
3. The service stores the event by Svix ID.
4. Reconciliation processes supported events idempotently.

## Onboarding Runtime Flow

1. Clerk supplies the authenticated subject and active organization claim.
2. `POST /api/v1/session/bootstrap` reconciles the provider organization, membership, and local member.
3. The route guard reads `/members/me` and `foundation_status` before it selects an authenticated route.
4. An administrator reads and saves the Foundation draft with an optimistic `expected_version`.
5. Foundation completion validates the snapshot, writes settings, regenerates timeslots, flushes the state, and commits before returning.
6. The frontend invalidates `foundation-status`, `foundation-draft`, `current-member`, dashboard, and readiness queries before navigating to `/dashboard`.
7. The optional tutorial runs in local browser state. Its API boundary prevents simulated page actions from changing operational data.
8. Readiness and prevalidation expose the bases required before schedule generation.

The route gate allows only Foundation status and Foundation administration while the Foundation is incomplete.
Normal admin and teacher routes require `COMPLETED`.

## Contracts and Invariants

- A worker task creates its own database session.
- A webhook cannot process an invalid signature.
- Contact delivery does not occur before Turnstile validation.
- The contact service does not import FastAPI or provider clients.

## States and Transitions

Clerk webhook events use `received`, `processing`, `processed`, `ignored`, `retryable_failed`, `sync_error`, or `dead_letter`.

Scheduler jobs use `QUEUED`, `RUNNING`, `CANCEL_REQUESTED`, `CANCELED`, `SUCCEEDED`, `FAILED`, or `NO_VALID_OUTPUT`.

## Failure Modes

- Body size above the shared 1 MiB default returns `413`; contact retains a 16 KiB budget and
  Clerk webhooks retain a 256 KiB budget.
- Invalid Turnstile data returns `400`.
- Provider timeout or provider failure returns `503`.
- Invalid webhook signatures return `401`.
- Worker failures remain visible in job fields and logs.

## Verification Procedure

1. Run contact service tests without network access.
2. Run webhook tests with signed fixtures.
3. Run scheduler job runtime tests.
4. Inspect health and worker tasks in the local stack.

## Source Map

- `backend/app/middleware/request_body_limit.py`
- `backend/app/contact/service.py`
- `backend/app/contact/turnstile_verifier.py`
- `backend/app/contact/resend_gateway.py`
- `backend/app/api/v1/endpoints/webhooks.py`
- `backend/app/scheduler/infrastructure/task_dispatcher.py`
- `backend/app/celery_worker.py`
- `backend/app/scheduler_worker.py`

## Related Documents

- [System Architecture](SYSTEM_ARCHITECTURE.md)
- [API Reference](../05_backend_api/API_REFERENCE.md)
- [Security and Tenant Isolation](../08_security_quality/SECURITY_AND_TENANT_ISOLATION.md)
