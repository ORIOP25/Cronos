# API Reference

## Purpose
This document provides a comprehensive REST API endpoint reference for the Cronos backend service.

## Intended Reader
This document targets API consumers, frontend developers, and backend engineers.

## Prerequisites
Read [Backend Architecture](BACKEND_ARCHITECTURE.md) and [Glossary](../00_getting_started/GLOSSARY.md).

## Endpoint Families Table

### 1. Public, Session, and Health

| Method | Endpoint Route | Required Role | Summary Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/health` | Public | System health check and status verification |
| `GET` | `/health/live` | Public | Process liveness check |
| `GET` | `/health/ready` | Public | Database and Redis readiness check |
| `POST` | `/api/v1/contact` | Public | Submit the marketing contact form |
| `POST` | `/api/v1/session/bootstrap` | Signed In | Resolve or bootstrap session state |
| `GET` | `/api/v1/onboarding/status` | Admin | Read onboarding state |
| `POST` | `/api/v1/onboarding` | Admin | Configure the first school state |

### 2. Analytics and Dashboard

| Method | Endpoint Route | Required Role | Summary Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/analytics/availability-heatmap` | Authenticated | Availability distribution heatmap metrics |
| `GET` | `/api/v1/dashboard` | Admin | Administrative dashboard data |

### 3. Classes and Curriculum (`/api/v1/classes`)

| Method | Endpoint Route | Required Role | Summary Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/classes/` | Admin | List all classes (*Turmas*) for organization |
| `POST` | `/api/v1/classes/` | Admin | Create a new class cohort |
| `GET` | `/api/v1/classes/{class_id}` | Admin | Fetch class detail by ID |
| `PATCH` | `/api/v1/classes/{class_id}` | Admin | Update class parameters |
| `DELETE` | `/api/v1/classes/{class_id}` | Admin | Delete class cohort |
| `GET` | `/api/v1/classes/{class_id}/curriculum` | Admin | Fetch course subjects for the class |
| `PATCH` | `/api/v1/classes/{class_id}/progress` | Admin | Append manual progress adjustments |
| `GET` | `/api/v1/classes/{class_id}/subjects` | Authenticated | Fetch class subject assignments |
| `POST` | `/api/v1/classes/{class_id}/subjects` | Admin | Assign subject to class with primary teacher |
| `PATCH` | `/api/v1/classes/{class_id}/subjects/{subject_id}` | Admin | Change the assigned teacher |
| `DELETE` | `/api/v1/classes/{class_id}/subjects/{subject_id}` | Admin | Remove a subject assignment |
| `GET` | `/api/v1/classes/{class_id}/available-subjects` | Authenticated | List assignable subjects |
| `GET` | `/api/v1/classes/subjects/{subject_id}/eligible-teachers` | Authenticated | List eligible teachers |

### 4. Courses and Catalogs

| Method | Endpoint Route | Required Role | Summary Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/courses/` | Authenticated | List all vocational courses |
| `POST` | `/api/v1/courses/` | Admin | Create new course entity |
| `GET` | `/api/v1/courses/{course_id}` | Authenticated | Fetch course details |
| `GET` | `/api/v1/courses/{course_id}/classes` | Authenticated | List course classes |
| `POST` | `/api/v1/courses/{course_id}/classes` | Admin | Create a class inside a course |
| `PATCH` | `/api/v1/courses/{course_id}/classes/{class_id}` | Admin | Update a class inside a course |
| `DELETE` | `/api/v1/courses/{course_id}/classes/{class_id}` | Admin | Delete a class inside a course |
| `PATCH` | `/api/v1/courses/{course_id}` | Admin | Update course metadata |
| `DELETE` | `/api/v1/courses/{course_id}` | Admin | Delete course entity |
| `GET/POST` | `/api/v1/subjects/` | Authenticated / Admin | List or create subjects and modules |
| `PATCH/DELETE` | `/api/v1/subjects/{subject_id}` | Admin | Update or delete a subject |
| `GET/POST` | `/api/v1/rooms/` | Authenticated / Admin | List or create rooms |
| `PATCH/DELETE` | `/api/v1/rooms/{room_id}` | Admin | Update or delete a room |
| `GET` | `/api/v1/timeslots/` | Authenticated | List grid slots |
| `POST` | `/api/v1/timeslots/generate` | Admin | Replace the timeslot grid after preflight |

### 5. Organization Members (`/api/v1/members`)

| Method | Endpoint Route | Required Role | Summary Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/members/` | Admin | List all team members (`Equipa`) |
| `GET` | `/api/v1/members/me` | Authenticated | Fetch active user membership context |
| `POST` | `/api/v1/members/` | Admin | Invite new organization team member |
| `PATCH` | `/api/v1/members/{member_id}` | Admin | Update member role or status |
| `POST` | `/api/v1/members/{member_id}/remove` | Admin | Remove member from organization |
| `POST` | `/api/v1/members/{member_id}/resend-invitation` | Admin | Resend a pending invite |
| `POST` | `/api/v1/members/{member_id}/retry-sync` | Admin | Retry provider synchronization |
| `POST` | `/api/v1/members/{member_id}/restore` | Admin | Restore member access |

### 6. Teacher Self-Service

| Method | Endpoint Route | Required Role | Summary Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/teachers/me/availability` | Teacher | Read personal availability |
| `POST` | `/api/v1/teachers/{teacher_id}/availability` | Self or Admin | Replace teacher availability |
| `GET` | `/api/v1/teachers/me/progress` | Teacher | Read assigned class progress |
| `GET` | `/api/v1/teachers/` | Admin | List teachers |
| `GET` | `/api/v1/teachers/observability/summary` | Admin | Read teacher endpoint telemetry |

### 7. Occurrences and Substitutions (`/api/v1/occurrences`)

| Method | Endpoint Route | Required Role | Summary Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/occurrences/` | Admin | List lesson occurrences |
| `POST` | `/api/v1/occurrences/` | Admin | Create an occurrence from an active block |
| `GET` | `/api/v1/occurrences/debts` | Admin | Fetch hour debt summaries |
| `GET` | `/api/v1/occurrences/observability/summary` | Admin | Read occurrence endpoint telemetry |
| `GET` | `/api/v1/occurrences/substitutes` | Admin | List free teachers for a date and timeslot |
| `GET` | `/api/v1/occurrences/{occurrence_id}` | Admin | Read one occurrence |
| `GET` | `/api/v1/occurrences/{occurrence_id}/substitutes/recommendations` | Admin | Rank eligible substitute assignments |
| `PATCH` | `/api/v1/occurrences/{occurrence_id}` | Admin | Decide or revise occurrence status |
| `POST` | `/api/v1/occurrences/{occurrence_id}/cancel` | Admin | Revoke an occurrence through a new revision |

### 8. Scheduler and Solver Engine (`/api/v1/scheduler`)

| Method | Endpoint Route | Required Role | Summary Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/scheduler/generate` | Admin | Trigger full or repair schedule generation job |
| `GET` | `/api/v1/scheduler/jobs/{job_id}` | Authenticated | Read one generation job |
| `POST` | `/api/v1/scheduler/jobs/{job_id}/cancel` | Admin | Request job cancellation |
| `GET` | `/api/v1/scheduler/status` | Authenticated | Read scheduler lifecycle status |
| `GET` | `/api/v1/scheduler/drafts/current` | Authenticated | Fetch the current pending draft |
| `GET` | `/api/v1/scheduler/drafts/{draft_id}` | Authenticated | Fetch one draft summary |
| `GET` | `/api/v1/scheduler/drafts/{draft_id}/diff` | Authenticated | Fetch persisted draft diff entries |
| `POST` | `/api/v1/scheduler/drafts/{draft_id}/approve` | Admin | Promote draft schedule to active timetable |
| `POST` | `/api/v1/scheduler/drafts/{draft_id}/reject` | Admin | Discard schedule draft |
| `POST` | `/api/v1/scheduler/reset-year` | Admin | Reset scheduler publication state |

### 9. Weekly Schedule, Constraints, and Logs (`/api/v1/schedule`)

| Method | Endpoint Route | Required Role | Summary Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/schedule/week` | Authenticated | Fetch weekly schedule grid blocks |
| `GET` | `/api/v1/schedule/me/horizon` | Teacher | Read personal schedule bounds |
| `PUT` | `/api/v1/schedule/active-blocks/{active_schedule_block_id}/log` | Assigned Teacher or Admin | Set status, summary, and notes |
| `PUT` | `/api/v1/schedule/operational-blocks/{operational_block_id}/log` | Assigned Teacher or Admin | Log a substitute operational block |
| `GET/POST` | `/api/v1/schedule/constraints/` | Authenticated / Admin | List or create scheduler constraints |
| `DELETE` | `/api/v1/schedule/constraints/{constraint_id}` | Admin | Delete a scheduler constraint |
| `DELETE` | `/api/v1/schedule/reset` | Admin | Destructively reset schedule data |

### 10. School Settings and Timesheets

| Method | Endpoint Route | Required Role | Summary Description |
| :--- | :--- | :--- | :--- |
| `GET/POST` | `/api/v1/school/settings/` | Admin | Read or update school dates and repair window |
| `POST` | `/api/v1/school/settings/soft-reset` | Admin | Reset the school year while preserving history |
| `GET/POST` | `/api/v1/school/grid-settings/` | Admin | Read or update lunch settings |
| `POST` | `/api/v1/school/grid-settings/regenerate` | Admin | Save lunch settings and replace the grid atomically |
| `GET/POST` | `/api/v1/school/calendar-events/` | Authenticated / Admin | List or create school calendar events |
| `DELETE` | `/api/v1/school/calendar-events/{event_id}` | Admin | Delete a school calendar event |
| `POST` | `/api/v1/school/settings/sync-holidays` | Admin | Import Portuguese national holidays |
| `GET` | `/api/v1/timesheets/` | Admin | List weekly timesheets |
| `GET` | `/api/v1/timesheets/me/{week_start_date}` | Teacher | Get or create the personal week |
| `POST` | `/api/v1/timesheets/me/{week_start_date}/submit` | Teacher | Submit the personal week |
| `GET` | `/api/v1/timesheets/{timesheet_id}/pending-occurrences` | Admin | List open occurrences in the week |
| `PATCH` | `/api/v1/timesheets/{timesheet_id}/status` | Admin | Approve or reopen a week |

### 11. Webhooks (`/api/v1/webhooks`)

| Method | Endpoint Route | Required Role | Summary Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/webhooks/clerk` | Public (Signed) | Process Clerk user and organization webhooks |

### 9. Public contact (`/api/v1/contact`)

| Method | Endpoint Route | Required Role | Summary Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/contact` | Public (Turnstile) | Deliver a website contact request through Resend |

## Standard Request and Response Formats
Requests and responses use JSON. Success responses serialize Pydantic schemas directly or wrap items in list envelopes.

## Source Map
- Endpoint Routers: `backend/app/api/v1/endpoints/`
- Schema Models: `backend/app/schemas.py`

## Related Documents
- [Backend Architecture](BACKEND_ARCHITECTURE.md)
- [Errors and Transactions](ERRORS_AND_TRANSACTIONS.md)

## Health Endpoints

`GET /api/v1/health` is a constant response. `/health/ready` checks PostgreSQL and Redis and returns `503` when either dependency fails.
