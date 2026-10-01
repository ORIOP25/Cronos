# Errors and Transactions

## Purpose
This document specifies standard error response envelopes, HTTP status codes, and database transaction rollback rules.

## Intended Reader
This document targets API consumers and backend developers.

## Prerequisites
Read [API Reference](API_REFERENCE.md).

## What the System Does
FastAPI handlers return one safe error shape. Clients may use `code` for control flow and `message` for display.

## Standard Error Envelope Schema
All non-success responses use this envelope:

```json
{
  "detail": {
    "code": "generation_dispatch_failed",
    "message": "Não foi possível iniciar a geração do horário. Tente novamente.",
    "reference": "7A31D98FC2E4",
    "retryable": true,
    "support_required": false,
    "fields": {},
    "context": {}
  }
}
```

`reference` is opaque and has 12 characters. The same value is present in
`X-Request-ID`. Clients must not display backend exception text. The `fields`
and `context` objects contain only safe business guidance.

The request ID comes from `X-Request-ID` when it matches `^[A-Z0-9]{12}$`.
Otherwise the backend creates a new reference. CORS exposes `X-Request-ID` to
allowed browser origins.

## Standard HTTP Status Codes

| HTTP Status Code | Name | Scenario |
| :--- | :--- | :--- |
| `200 OK` | Success | Request executed successfully |
| `201 Created` | Created | Resource created successfully |
| `400 Bad Request` | Client Error | Malformed request or business logic failure |
| `401 Unauthorized` | Auth Error | Missing or invalid Clerk JWT token |
| `403 Forbidden` | Permission Error | Insufficient role capability |
| `404 Not Found` | Resource Missing | Target record ID does not exist |
| `409 Conflict` | State Conflict | Stale version, active lifecycle conflict, or duplicate action |
| `422 Unprocessable` | Validation Error | Pydantic or domain validation failure |
| `413 Payload Too Large` | Body Limit | Protected route body exceeds its configured limit |
| `429 Too Many Requests` | Rate Limit | SlowAPI limit is exceeded |
| `503 Unavailable` | Dependency Failure | Readiness, webhook retry, rate-limit storage, or unavailable service |
| `500 Internal Error` | Server Failure | Unhandled backend exception |

The shared response builder handles HTTP, validation, domain, application,
rate-limit, body-size, and unexpected exceptions. CORS exposes `X-Request-ID`.

## Public Error Codes

`backend/app/core/exceptions.py` defines the message catalog. `AppError.kind`
selects the status: `bad_request` -> `400`, `validation` -> `422`,
`not_found` -> `404`, `conflict` -> `409`, `forbidden` -> `403`,
`unauthorized` -> `401`, `too_many_requests` -> `429`, `unavailable` -> `503`,
and unknown kinds -> `500`.

| Code | HTTP | Notes |
| :--- | :--- | :--- |
| `validation_error` | `422` | Pydantic or payload validation |
| `resource_not_found` | `404` | Tenant-scoped lookup miss |
| `conflict` | `409` | State or version conflict |
| `resource_in_use` | `409` | Active schedule or operation blocks removal |
| `authentication_required` | `401` | Missing or invalid session |
| `access_forbidden` | `403` | Insufficient capability or ownership |
| `LEGAL_ACCEPTANCE_REQUIRED` | `409` | Organization must accept legal documents |
| `FOUNDATION_REQUIRED` | `409` | Foundation is not `COMPLETED` |
| `request_body_too_large` | `413` | Protected body exceeds its limit |
| `too_many_requests` | `429` | Rate limit exceeded |
| `service_unavailable` | `503` | Dependency unavailable |
| `unexpected_error` | `500` | Unhandled exception |

Foundation and scheduler terminal codes keep their own catalog messages.
`FOUNDATION_DRAFT_VERSION_CONFLICT` and `FOUNDATION_ALREADY_COMPLETED` return
`409`; `FOUNDATION_INCOMPLETE` returns `422`. The scheduler terminal codes
`CANCELED`, `TIMED_OUT`, `NO_VALID_OUTPUT`, `FAILED_VALIDATION`, `SYSTEM_ERROR`,
`DISPATCH_STALLED`, and `WORKER_STALLED` have catalog entries.
`RATE_LIMIT_UNAVAILABLE` returns `503` when rate-limit storage fails.

## Transaction Rollback Rules

- The `get_db` dependency commits after a successful request.
- The dependency rolls back and re-raises any request exception.
- Services use row locks and flushes inside the request transaction for multi-step lifecycle changes.
- The contact route returns `204` without a response body on accepted submissions.

The database dependency uses function scope, so the commit completes before FastAPI sends the response.
An error during commit therefore returns an error instead of a false successful response.

Foundation draft writes and completion use optimistic version checks.
Return `409 FOUNDATION_DRAFT_VERSION_CONFLICT` when `expected_version` is stale.
Return `422 FOUNDATION_INCOMPLETE` when the complete snapshot fails validation.
Return `409 FOUNDATION_ALREADY_COMPLETED` when a completed organization receives another draft write.

## Failure Modes
- Database Integrity Conflict: Services map known dependency conflicts to domain-specific `400` or `409` responses.

## Verification Procedure
Send an invalid payload to `POST /api/v1/subjects/` with an admin session.
Verify HTTP `422`, the standard envelope, a Portuguese message, and matching
`detail.reference` and `X-Request-ID`.

## Source Map
- Exception Handlers: `backend/app/main.py`
- API Errors Utility: `frontend/src/utils/apiErrors.js`

## Related Documents
- [Backend Architecture](BACKEND_ARCHITECTURE.md)
- [API Reference](API_REFERENCE.md)
