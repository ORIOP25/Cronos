# API Reference

## Purpose
This document provides a comprehensive REST API endpoint reference for the Cronos backend service.

## Intended Reader
This document targets API consumers, frontend developers, and backend engineers.

## Prerequisites
Read [Backend Architecture](BACKEND_ARCHITECTURE.md) and [Glossary](../00_getting_started/GLOSSARY.md).

## Endpoint Families Table

### 1. Analytics & Health (`/api/v1/analytics`, `/api/v1/health`)

| Method | Endpoint Route | Required Role | Summary Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/health` | Public | System health check and status verification |
| `GET` | `/api/v1/analytics/availability-heatmap` | Admin | Availability distribution heatmap metrics |

### 2. Classes & Curriculum (`/api/v1/classes`)

| Method | Endpoint Route | Required Role | Summary Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/classes/` | Authenticated | List all classes (*Turmas*) for organization |
| `POST` | `/api/v1/classes/` | Admin | Create a new class cohort |
| `GET` | `/api/v1/classes/{class_id}` | Authenticated | Fetch class detail by ID |
| `PATCH` | `/api/v1/classes/{class_id}` | Admin | Update class parameters |
| `DELETE` | `/api/v1/classes/{class_id}` | Admin | Delete class cohort |
| `GET` | `/api/v1/classes/{class_id}/curriculum` | Authenticated | Fetch class curriculum module list |
| `GET` | `/api/v1/classes/{class_id}/subjects` | Authenticated | Fetch subject assignments for class |
| `POST` | `/api/v1/classes/{class_id}/subjects` | Admin | Assign subject to class with primary teacher |

### 3. Courses (`/api/v1/courses`)

| Method | Endpoint Route | Required Role | Summary Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/courses/` | Authenticated | List all vocational courses |
| `POST` | `/api/v1/courses/` | Admin | Create new course entity |
| `GET` | `/api/v1/courses/{course_id}` | Authenticated | Fetch course details |
| `PATCH` | `/api/v1/courses/{course_id}` | Admin | Update course metadata |
| `DELETE` | `/api/v1/courses/{course_id}` | Admin | Delete course entity |

### 4. Organization Members (`/api/v1/members`)

| Method | Endpoint Route | Required Role | Summary Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/members/` | Admin | List all team members (`Equipa`) |
| `GET` | `/api/v1/members/me` | Authenticated | Fetch active user membership context |
| `POST` | `/api/v1/members/` | Admin | Invite new organization team member |
| `PATCH` | `/api/v1/members/{member_id}` | Admin | Update member role or status |
| `POST` | `/api/v1/members/{member_id}/remove` | Admin | Remove member from organization |

### 5. Occurrences & Substitutions (`/api/v1/occurrences`)

| Method | Endpoint Route | Required Role | Summary Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/occurrences/` | Authenticated | List lesson occurrences |
| `POST` | `/api/v1/occurrences/` | Authenticated | Create a new occurrence record |
| `GET` | `/api/v1/occurrences/debts` | Admin | Fetch hour debt summaries |
| `GET` | `/api/v1/occurrences/{id}/substitutes/recommendations` | Admin | Get recommended substitute teachers |
| `PATCH` | `/api/v1/occurrences/{id}` | Admin | Update occurrence status or cover teacher |

### 6. Scheduler & Solver Engine (`/api/v1/scheduler`)

| Method | Endpoint Route | Required Role | Summary Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/scheduler/generate` | Admin | Trigger full or repair schedule generation job |
| `GET` | `/api/v1/scheduler/status` | Admin | Poll active solver job status |
| `GET` | `/api/v1/scheduler/drafts/current` | Admin | Fetch current unapproved schedule draft |
| `GET` | `/api/v1/scheduler/drafts/{id}/diff` | Admin | Compute statistical diff between draft and active |
| `POST` | `/api/v1/scheduler/drafts/{id}/approve` | Admin | Promote draft schedule to active timetable |
| `POST` | `/api/v1/scheduler/drafts/{id}/reject` | Admin | Discard schedule draft |

### 7. Weekly Schedule & Logs (`/api/v1/schedule`)

| Method | Endpoint Route | Required Role | Summary Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/schedule/week` | Authenticated | Fetch weekly schedule grid blocks |
| `PUT` | `/api/v1/schedule/active-blocks/{id}/log` | Teacher | Log lesson summary (*Sumário*) and attendance |

### 8. Webhooks (`/api/v1/webhooks`)

| Method | Endpoint Route | Required Role | Summary Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/webhooks/clerk` | Public (Signed) | Process Clerk user and organization webhooks |

## Standard Request and Response Formats
Requests and responses use JSON. Success responses serialize Pydantic schemas directly or wrap items in list envelopes.

## Source Map
- Endpoint Routers: `backend/app/api/v1/endpoints/`
- Schema Models: `backend/app/schemas.py`

## Related Documents
- [Backend Architecture](BACKEND_ARCHITECTURE.md)
- [Errors and Transactions](ERRORS_AND_TRANSACTIONS.md)

## Health endpoints

GET /api/v1/health is a constant-cost liveness endpoint. /health/ready is private readiness.
