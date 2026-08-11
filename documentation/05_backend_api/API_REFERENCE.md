# API Reference

## Purpose

This document lists the implemented HTTP routes, access requirements, and public provider contracts.

## Intended Reader

This document targets API consumers, frontend engineers, backend engineers, and QA engineers.

## Prerequisites

Read [Backend Architecture](BACKEND_ARCHITECTURE.md) and [Errors and Transactions](ERRORS_AND_TRANSACTIONS.md).

## What the System Does

FastAPI mounts application routes under `/api/v1`.
Protected routes resolve an active organization membership.
The liveness and readiness routes remain outside that prefix.

## Why the Behavior Exists

Stable route families keep frontend features and provider webhooks independent from implementation modules.

## Components and Ownership

| Area | Source |
| :--- | :--- |
| Router assembly | `backend/app/api/api.py` |
| Endpoint modules | `backend/app/api/v1/endpoints/` |
| Pydantic contracts | `backend/app/schemas.py` |
| Authentication dependencies | `backend/app/api/deps.py` |

## Data or Request Flow

1. Send JSON to an `/api/v1` route.
2. Include a Clerk Bearer token for protected routes.
3. Include an active organization in the Clerk session.
4. Provide route-specific IDs and payloads.
5. Read the JSON response or standard error detail.

## Endpoint Inventory

`Public` routes do not require a membership. `Active` routes require active access.
`Admin` routes require the `admin` capability. `Teacher` routes also require a linked teacher profile.

### Public, health, session, and onboarding

| Method | Route | Access |
| :--- | :--- | :--- |
| `GET` | `/health/live` | Public |
| `GET` | `/health/ready` | Public; returns `503` when dependencies fail |
| `GET` | `/api/v1/health` | Public |
| `POST` | `/api/v1/contact` | Public; Turnstile and rate limits |
| `POST` | `/api/v1/session/bootstrap` | Signed in |
| `GET` | `/api/v1/onboarding/status` | Admin |
| `POST` | `/api/v1/onboarding` | Admin |

### Dashboard, analytics, and catalog

| Method | Route | Access |
| :--- | :--- | :--- |
| `GET` | `/api/v1/dashboard` | Admin |
| `GET` | `/api/v1/analytics/availability-heatmap` | Active |
| `GET` | `/api/v1/courses/` | Active |
| `POST` | `/api/v1/courses/` | Admin |
| `GET` | `/api/v1/courses/{course_id}` | Active |
| `PATCH` | `/api/v1/courses/{course_id}` | Admin |
| `DELETE` | `/api/v1/courses/{course_id}` | Admin |
| `GET` | `/api/v1/courses/{course_id}/classes` | Active |
| `POST` | `/api/v1/courses/{course_id}/classes` | Admin |
| `PATCH` | `/api/v1/courses/{course_id}/classes/{class_id}` | Admin |
| `DELETE` | `/api/v1/courses/{course_id}/classes/{class_id}` | Admin |
| `GET` | `/api/v1/classes/` | Admin |
| `POST` | `/api/v1/classes/` | Admin |
| `GET` | `/api/v1/classes/{class_id}` | Admin |
| `PATCH` | `/api/v1/classes/{class_id}` | Admin |
| `DELETE` | `/api/v1/classes/{class_id}` | Admin |
| `GET` | `/api/v1/classes/{class_id}/curriculum` | Admin |
| `PATCH` | `/api/v1/classes/{class_id}/progress` | Admin |
| `GET` | `/api/v1/classes/{class_id}/subjects` | Active |
| `POST` | `/api/v1/classes/{class_id}/subjects` | Admin |
| `PATCH` | `/api/v1/classes/{class_id}/subjects/{subject_id}` | Admin |
| `DELETE` | `/api/v1/classes/{class_id}/subjects/{subject_id}` | Admin |
| `GET` | `/api/v1/classes/{class_id}/available-subjects` | Active |
| `GET` | `/api/v1/classes/subjects/{subject_id}/eligible-teachers` | Active |
| `GET` / `POST` | `/api/v1/subjects/` | Active / Admin |
| `PATCH` / `DELETE` | `/api/v1/subjects/{subject_id}` | Admin |
| `GET` / `POST` | `/api/v1/rooms/` | Active / Admin |
| `PATCH` / `DELETE` | `/api/v1/rooms/{room_id}` | Admin |
| `GET` | `/api/v1/timeslots/` | Active |
| `POST` | `/api/v1/timeslots/generate` | Admin |

### Members and teachers

| Method | Route | Access |
| :--- | :--- | :--- |
| `GET` | `/api/v1/members/` and `/api/v1/members` | Admin |
| `GET` | `/api/v1/members/me` | Active |
| `POST` | `/api/v1/members/` and `/api/v1/members` | Admin |
| `GET` | `/api/v1/members/{member_id}` | Admin |
| `PATCH` | `/api/v1/members/{member_id}` | Admin |
| `POST` | `/api/v1/members/{member_id}/remove` | Admin |
| `POST` | `/api/v1/members/{member_id}/resend-invitation` | Admin |
| `POST` | `/api/v1/members/{member_id}/retry-sync` | Admin |
| `POST` | `/api/v1/members/{member_id}/restore` | Admin |
| `GET` | `/api/v1/teachers/` | Admin |
| `GET` | `/api/v1/teachers/me/availability` | Teacher |
| `POST` | `/api/v1/teachers/{teacher_id}/availability` | Active; self or admin |
| `GET` | `/api/v1/teachers/me/progress` | Teacher |
| `GET` | `/api/v1/teachers/observability/summary` | Admin |

### School configuration

| Method | Route | Access |
| :--- | :--- | :--- |
| `GET` / `POST` | `/api/v1/school/settings/` | Admin |
| `POST` | `/api/v1/school/settings/soft-reset` | Admin |
| `POST` | `/api/v1/school/settings/sync-holidays` | Admin |
| `GET` / `POST` | `/api/v1/school/grid-settings/` | Admin |
| `POST` | `/api/v1/school/grid-settings/regenerate` | Admin |
| `GET` / `POST` | `/api/v1/school/calendar-events/` | Active / Admin |
| `DELETE` | `/api/v1/school/calendar-events/{event_id}` | Admin |

### Scheduler and schedule operations

| Method | Route | Access |
| :--- | :--- | :--- |
| `POST` | `/api/v1/scheduler/generate` | Admin |
| `GET` | `/api/v1/scheduler/status` | Active |
| `GET` | `/api/v1/scheduler/jobs/{job_id}` | Active |
| `POST` | `/api/v1/scheduler/jobs/{job_id}/cancel` | Admin |
| `GET` | `/api/v1/scheduler/drafts/current` | Active |
| `GET` | `/api/v1/scheduler/drafts/{draft_id}` | Active |
| `GET` | `/api/v1/scheduler/drafts/{draft_id}/diff` | Active |
| `POST` | `/api/v1/scheduler/drafts/{draft_id}/approve` | Admin |
| `POST` | `/api/v1/scheduler/drafts/{draft_id}/reject` | Admin |
| `POST` | `/api/v1/scheduler/reset-year` | Admin |
| `GET` / `POST` | `/api/v1/schedule/constraints/` | Active / Admin |
| `DELETE` | `/api/v1/schedule/constraints/{constraint_id}` | Admin |
| `GET` | `/api/v1/schedule/week` | Active; teacher scope is restricted |
| `GET` | `/api/v1/schedule/me/horizon` | Teacher |
| `PUT` | `/api/v1/schedule/active-blocks/{id}/log` | Active; assigned teacher or admin |
| `PUT` | `/api/v1/schedule/operational-blocks/{id}/log` | Active; assigned teacher or admin |
| `DELETE` | `/api/v1/schedule/reset` | Admin |

### Occurrences, timesheets, and webhooks

| Method | Route | Access |
| :--- | :--- | :--- |
| `GET` / `POST` | `/api/v1/occurrences/` | Admin |
| `GET` | `/api/v1/occurrences/{occurrence_id}` | Admin |
| `PATCH` | `/api/v1/occurrences/{occurrence_id}` | Admin |
| `POST` | `/api/v1/occurrences/{occurrence_id}/cancel` | Admin |
| `GET` | `/api/v1/occurrences/debts` | Admin |
| `GET` | `/api/v1/occurrences/substitutes` | Admin |
| `GET` | `/api/v1/occurrences/{occurrence_id}/substitutes/recommendations` | Admin |
| `GET` | `/api/v1/occurrences/observability/summary` | Admin |
| `GET` | `/api/v1/timesheets/` | Admin |
| `GET` | `/api/v1/timesheets/me/{week_start_date}` | Teacher |
| `POST` | `/api/v1/timesheets/me/{week_start_date}/submit` | Teacher |
| `GET` | `/api/v1/timesheets/{timesheet_id}/pending-occurrences` | Admin |
| `PATCH` | `/api/v1/timesheets/{timesheet_id}/status` | Admin |
| `POST` | `/api/v1/webhooks/clerk` | Public; Svix signature required |

## Contracts and Invariants

- Protected routes derive `organization_id` from the active membership.
- The API does not accept a client-supplied tenant ID as authority.
- The contact route returns `204` on accepted or honeypot submissions.
- Production hides FastAPI documentation routes through settings.

## States and Transitions

Route-specific state values are defined by `backend/app/models.py` and `backend/app/schemas.py`.
Do not infer state names from UI labels.

## Failure Modes

- `400`: domain or provider validation failure.
- `401`: missing or invalid authentication or webhook signature.
- `403`: insufficient capability or ownership.
- `404`: tenant-scoped resource not found.
- `409`: state or version conflict.
- `413`: protected body exceeds its route limit.
- `422`: invalid JSON or Pydantic payload.
- `429`: rate limit exceeded.
- `503`: provider or dependency unavailable.

## Verification Procedure

1. Start the API in `local` mode.
2. Open `http://localhost:8000/docs`.
3. Run endpoint tests with a dedicated test database.
4. Run frontend feature tests against the route contracts.

## Source Map

- Router assembly: `backend/app/api/api.py`
- Endpoint source: `backend/app/api/v1/endpoints/`
- Schemas: `backend/app/schemas.py`
- API tests: `backend/tests/`

## Related Documents

- [Backend Architecture](BACKEND_ARCHITECTURE.md)
- [Errors and Transactions](ERRORS_AND_TRANSACTIONS.md)
