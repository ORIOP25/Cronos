# Errors and Transactions

## Purpose
This document specifies standard error response envelopes, HTTP status codes, and database transaction rollback rules.

## Intended Reader
This document targets API consumers and backend developers.

## Prerequisites
Read [API Reference](API_REFERENCE.md).

## What the System Does
FastAPI handlers capture exceptions and return standard JSON error structures.

## Standard Error Envelope Schema
All error responses return JSON matching this structure:

```json
{
  "detail": "Descriptive error message text",
  "code": "ERROR_CATEGORY_CODE",
  "meta": {}
}
```

## Standard HTTP Status Codes

| HTTP Status Code | Name | Scenario |
| :--- | :--- | :--- |
| `200 OK` | Success | Request executed successfully |
| `201 Created` | Created | Resource created successfully |
| `400 Bad Request` | Client Error | Malformed request or business logic failure |
| `401 Unauthorized` | Auth Error | Missing or invalid Clerk JWT token |
| `403 Forbidden` | Permission Error | Insufficient role capability |
| `404 Not Found` | Resource Missing | Target record ID does not exist |
| `422 Unprocessable` | Validation Error | Pydantic payload validation failure |
| `500 Internal Error` | Server Failure | Unhandled backend exception |

## Transaction Rollback Rules
- FastAPI handlers manage database transactions via SQLAlchemy async sessions.
- If an exception occurs inside a transaction block, SQLAlchemy automatically triggers a `ROLLBACK`.
- Complex multi-step operations (e.g., draft promotion) execute inside explicit nested transaction blocks (`async with session.begin():`).

## Failure Modes
- Database Integrity Conflict: Attempting to delete a record linked to active foreign keys raises a database error. Handler returns HTTP `400 Bad Request`.

## Verification Procedure
Send an invalid payload to `/api/v1/classes/`. Verify that response returns HTTP `422 Unprocessable Entity` with validation detail details.

## Source Map
- Exception Handlers: `backend/app/main.py`
- API Errors Utility: `frontend/src/utils/apiErrors.js`

## Related Documents
- [Backend Architecture](BACKEND_ARCHITECTURE.md)
- [API Reference](API_REFERENCE.md)
