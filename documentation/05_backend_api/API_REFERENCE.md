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

`Public` routes do not require a membership.
`Signed in` routes require a Clerk session and an active organization membership.
`Active` routes also require accepted legal documents and a `COMPLETED` Foundation.
`Admin` routes require the `admin` capability.
`Teacher` routes also require a linked teacher profile.
`Foundation admin` routes require the `admin` capability but not a completed Foundation.

### Public, health, session, Foundation, and legal

| Method | Route | Access |
| :--- | :--- | :--- |
| `GET` | `/health/live` | Public |
| `GET` | `/health/ready` | Public; returns `503` when dependencies fail |
| `GET` | `/api/v1/health` | Public; rate-limit exempt |
| `POST` | `/api/v1/contact` | Public; Turnstile; body limit 16 KiB |
| `POST` | `/api/v1/client-errors` | Public; body limit 4 KiB |
| `POST` | `/api/v1/session/bootstrap` | Signed in |
| `GET` | `/api/v1/foundation/status` | Signed in |
| `GET` | `/api/v1/foundation/draft` | Foundation admin |
| `PUT` | `/api/v1/foundation/draft` | Foundation admin |
| `POST` | `/api/v1/foundation/complete` | Foundation admin |
| `GET` | `/api/v1/legal/status` | Signed in |
| `POST` | `/api/v1/legal/acceptance` | Legal admin |

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
| `GET` | `/api/v1/classes/{class_id}` | Admin |
| `PATCH` | `/api/v1/classes/{class_id}/progress` | Admin |
| `GET` | `/api/v1/classes/{class_id}/subjects` | Active |
| `POST` | `/api/v1/classes/{class_id}/subjects` | Admin |
| `PATCH` | `/api/v1/classes/{class_id}/subjects/{subject_id}` | Admin |
| `DELETE` | `/api/v1/classes/{class_id}/subjects/{subject_id}` | Admin |
| `GET` | `/api/v1/classes/{class_id}/available-subjects` | Active |
| `GET` | `/api/v1/classes/subjects/{subject_id}/eligible-teachers` | Active |
| `GET` | `/api/v1/classes/{class_id}/availability` | Admin |
| `PUT` | `/api/v1/classes/{class_id}/availability` | Admin |
| `POST` | `/api/v1/classes/{class_id}/availability/copy` | Admin |
| `GET` / `POST` | `/api/v1/subjects/` | Active / Admin |
| `PATCH` / `DELETE` | `/api/v1/subjects/{subject_id}` | Admin |
| `GET` | `/api/v1/subjects/{subject_id}/joint-candidates` | Admin |
| `POST` | `/api/v1/joint-lesson-groups` | Admin; returns `201` |
| `PUT` / `DELETE` | `/api/v1/joint-lesson-groups/{group_id}` | Admin |
| `GET` / `POST` | `/api/v1/rooms/` | Active / Admin |
| `PATCH` / `DELETE` | `/api/v1/rooms/{room_id}` | Admin |
| `GET` / `POST` | `/api/v1/room-types/` | Admin; `POST` returns `201` |
| `PATCH` / `DELETE` | `/api/v1/room-types/{room_type_id}` | Admin |
| `GET` | `/api/v1/timeslots/` | Active |
| `GET` | `/api/v1/timeslots/range` | Active |

Each subject in `GET /api/v1/classes/{class_id}/subjects` carries `modules`, ordered by `order`, with `selected` per module. `POST` selects every module of the subject (D03). `PATCH /api/v1/classes/{class_id}/subjects/{subject_id}` accepts `module_ids`: an empty list is valid, repeated IDs or a module of another subject return `400 bad_request`, and a module of another organization returns `404 resource_not_found`. The write stores the selection on `class_subject_module` and records a scheduler change. `GET /api/v1/classes/{class_id}` and `PATCH /api/v1/classes/{class_id}/progress` count only the selected modules.

A joint lesson group joins two or more classes of one subject for a set of modules. `POST /api/v1/joint-lesson-groups` creates it, `PUT` replaces its classes, modules and teacher, and `DELETE` undoes it. `GET /api/v1/subjects/{subject_id}/joint-candidates?class_id={id}` lists the classes that can join the given class; the optional `group_id` includes the current members of that group (and the source class) so the editor can show the current selection and started modules, while the default excludes the source class and every joined class. In create mode, `include_source=true` adds the source class to the result so its selected, started and teacher facts are available; the default still excludes it. A source class without a current link in the organization returns `404`. Configuration rules return `400` with a `JOINT_*` code, except `JOINT_MODULE_STARTED` and `JOINT_CLASS_STARTED`, which return `409`. A group, teacher or module of another organization returns `404 resource_not_found`. `teacher_id` is required and positive; repeated `class_ids` or `module_ids` return `400`. Each subject in `GET /api/v1/classes/{class_id}/subjects` carries `joint_group` (or `null`). Changing the teacher of a member link changes every member link in one transaction. Removing a joint module from the checklist returns `409 JOINT_MODULE_LOCKED`, and removing a member link, archiving a member class, removing a joint module or deleting a subject in a joint group returns `409 resource_in_use`.

Every `/api/v1/room-types` route, including the list, is administrator-only. The list returns the active types of the caller's school, with `room_count` and `subject_count` of the active rooms and subjects that use each type. `POST` creates a type with a name of 1 to 60 characters, `PATCH` renames it, and `DELETE` removes it. A name already used by another type of the same school returns `409 room_type_name_taken` (compared ignoring case and accents); a blank or over-long name returns `422`. Renaming or removing the fixed Normal type returns `409 room_type_fixed`. Removing a type used by an active room or subject returns `409 resource_in_use` with the names in `context.rooms` and `context.subjects`; a type kept only by archived objects is archived, and creating the same name again restores it with the same `id` and name. A type of another school returns `404 resource_not_found`. A non-administrator returns `403`.

A class takes an optional home room as `home_room_id` in `PATCH /api/v1/courses/{course_id}/classes/{class_id}`. The value is an active room of the same school; a room type id, a room of another school or an archived room returns `404 resource_not_found` and changes nothing. `null` makes the class Automática, and an absent field keeps the current room. A room with fewer seats than the class size returns `422` with code `home_room_capacity` and `context` `room_name`, `room_capacity` and `class_size`. Growing the class above its room later is accepted. Every change records a `CLASS_DEMAND` scheduler change. `ClassRead` returns `home_room_id`, and `GET /api/v1/classes/{class_id}` returns `home_room` (`id`, `name`, `capacity`, `room_type`) or `null`. `GET /api/v1/rooms/` returns `home_classes` (`id`, `name`) with the active classes that have the room as home room. Archiving or deleting a room sets those classes back to Automática in the same transaction, and each one records a `CLASS_DEMAND` change.

A room or a subject takes the school type it needs as `room_type_id`. `POST /api/v1/rooms/` and `POST /api/v1/subjects/` without the field, or with `null`, use the school's Normal type; `PATCH` without the field keeps the current type, and an explicit `null` goes back to Normal. The write bodies reject unknown fields with `422`, so the removed `type` (rooms) and `required_room_type` (subjects) keys never save a Normal room or subject silently. Every room and subject read returns the nested `room_type` (`id`, `name`, `is_normal`), including `GET /api/v1/courses/{course_id}`, `GET /api/v1/classes/{class_id}`, the subject list of `GET /api/v1/classes/{class_id}/subjects` and the teacher progress reads. An identifier that does not exist, belongs to another school or is archived returns `404 resource_not_found` and changes nothing.

### Members and teachers

| Method | Route | Access |
| :--- | :--- | :--- |
| `GET` | `/api/v1/members/` and `/api/v1/members` | Admin |
| `GET` | `/api/v1/members/me` | Signed in |
| `POST` | `/api/v1/members/` and `/api/v1/members` | Admin; returns `201` |
| `GET` | `/api/v1/members/{member_id}` | Admin |
| `PATCH` | `/api/v1/members/{member_id}` | Admin |
| `POST` | `/api/v1/members/{member_id}/remove` | Admin |
| `POST` | `/api/v1/members/{member_id}/resend-invitation` | Admin |
| `POST` | `/api/v1/members/{member_id}/retry-sync` | Admin |
| `POST` | `/api/v1/members/{member_id}/restore` | Admin |
| `GET` | `/api/v1/teachers/` | Admin |
| `GET` | `/api/v1/teachers/me/availability` | Teacher |
| `PUT` | `/api/v1/teachers/me/availability` | Teacher; rate limit `30/minute` |
| `GET` | `/api/v1/teachers/{teacher_id}/availability` | Active; self or admin |
| `PUT` | `/api/v1/teachers/{teacher_id}/availability` | Admin |
| `GET` | `/api/v1/teachers/me/presence` | Teacher |
| `GET` | `/api/v1/teachers/{teacher_id}/presence` | Active; self or admin |
| `PUT` | `/api/v1/teachers/{teacher_id}/presence` | Admin |
| `GET` | `/api/v1/teachers/me/progress` | Teacher |

### Administrative CSV import

| Method | Route | Access |
| :--- | :--- | :--- |
| `GET` | `/api/v1/imports/templates/{resource}` | Admin |
| `POST` | `/api/v1/imports/validate` | Admin; body limit 8 MiB |
| `POST` | `/api/v1/imports/commit` | Admin; body limit 8 MiB; returns `201` |

See [Bulk Import CSV](../07_data_and_seed/BULK_IMPORT_CSV.md) for the exact templates, limits, issues and atomicity rules.
The `class_availability`, `teacher_availability` and `teacher_presence` resources accept `files.class_availability`, `files.teacher_availability` and `files.teacher_presence`.

### School configuration

| Method | Route | Access |
| :--- | :--- | :--- |
| `GET` / `POST` | `/api/v1/school/settings/` | Admin |
| `POST` | `/api/v1/school/settings/soft-reset` | Admin |
| `GET` / `POST` | `/api/v1/school/grid-settings/` | Admin |
| `POST` | `/api/v1/school/grid-settings/regenerate` | Admin |
| `GET` | `/api/v1/school/grid-configuration/` | Admin |
| `POST` | `/api/v1/school/grid-changes/preview` | Admin |
| `POST` | `/api/v1/school/grid-changes` | Admin |
| `GET` | `/api/v1/school/grid-changes/pending` | Admin |
| `GET` | `/api/v1/school/calendar-events/` | Active |
| `POST` | `/api/v1/school/calendar-events/preview` | Admin |
| `POST` | `/api/v1/school/calendar-events/` | Admin |
| `PUT` | `/api/v1/school/calendar-events/{event_id}` | Admin |
| `DELETE` | `/api/v1/school/calendar-events/{event_id}` | Admin |

School settings validate the combined stored and submitted dates.
When the calendar and `preferred_end_date` change together, the scheduler year persists all three dates before recording the calendar change.
Valid calendar replacements do not produce a constraint conflict. Invalid date combinations return `422`.
Each `affected_availabilities` entry of `POST /school/grid-changes/preview` includes a `classes` list.

### Scheduler and schedule operations

| Method | Route | Access |
| :--- | :--- | :--- |
| `POST` | `/api/v1/scheduler/generate` | Admin; rate limit `5/minute`; returns `202` |
| `GET` | `/api/v1/scheduler/status` | Active |
| `GET` | `/api/v1/scheduler/jobs/{job_id}` | Active |
| `POST` | `/api/v1/scheduler/jobs/{job_id}/cancel` | Admin |
| `GET` | `/api/v1/scheduler/drafts/current` | Active |
| `GET` | `/api/v1/scheduler/drafts/{proposal_id}/diff` | Active |
| `POST` | `/api/v1/scheduler/drafts/{proposal_id}/approve` | Admin |
| `POST` | `/api/v1/scheduler/drafts/{proposal_id}/reject` | Admin |
| `POST` | `/api/v1/schedule/constraints/` | Admin |
| `GET` | `/api/v1/schedule/week` | Active; teacher scope is restricted; rate limit `60/minute;600/hour` |
| `GET` | `/api/v1/schedule/me/horizon` | Teacher; rate limit `300/hour` |
| `PUT` | `/api/v1/schedule/operational-blocks/{id}/log` | Active; assigned teacher or admin |
| `PUT` | `/api/v1/schedule/lessons/{lesson_id}/log` | Active; assigned teacher or admin |

Scheduler status exposes `active_proposal_id` for the approved proposal linked to the active version, or `null` when absent.
`GET /scheduler/jobs/{job_id}` returns a `diagnostics` list with one proven entry per affected class. A proven joint isolation (`JOINT_NO_COMMON_TIME`) returns one entry per member class, each with the current class name and subject name, so the client can name every class and the subject. A class or subject deleted before the read keeps a null name and the client shows the generic message.
Weekly schedule reads return published lesson intervals, resource identifiers, module projections, and operational log state.
There is no separate proposal-lesson listing route.
The API has no observability summary routes, no `POST /api/v1/occurrences/` create route, and no `GET /api/v1/scheduler/drafts/{id}/lessons` route.
`POST /api/v1/schedule/constraints/` remains because the E2E adaptive repair test triggers it.

### Occurrences, timesheets, and webhooks

| Method | Route | Access |
| :--- | :--- | :--- |
| `GET` | `/api/v1/occurrences/` | Admin |
| `GET` | `/api/v1/occurrences/{occurrence_id}` | Admin |
| `PATCH` | `/api/v1/occurrences/{occurrence_id}` | Admin |
| `POST` | `/api/v1/occurrences/{occurrence_id}/cancel` | Admin |
| `GET` | `/api/v1/occurrences/debts` | Admin |
| `GET` | `/api/v1/occurrences/{occurrence_id}/substitutes/recommendations` | Admin |
| `GET` | `/api/v1/occurrences/{occurrence_id}/substitutes/diagnostics` | Admin |
| `GET` | `/api/v1/timesheets/` | Admin |
| `GET` | `/api/v1/timesheets/me/{week_start_date}` | Teacher |
| `POST` | `/api/v1/timesheets/me/{week_start_date}/submit` | Teacher |
| `PATCH` | `/api/v1/timesheets/{timesheet_id}/status` | Admin |
| `POST` | `/api/v1/webhooks/clerk` | Public; Svix signature required; body limit 256 KiB |

## Onboarding API Contract

All paths below are relative to `/api/v1`.

| Method | Path | Actor | Purpose |
| :--- | :--- | :--- | :--- |
| `POST` | `/session/bootstrap` | Authenticated Clerk organization administrator | Reconcile the provider organization and current member. |
| `GET` | `/foundation/status` | Signed-in organization member | Read Foundation status and completion timestamps. |
| `GET` | `/foundation/draft` | Foundation administrator | Read the current draft, version, step, and data. |
| `PUT` | `/foundation/draft` | Foundation administrator | Validate and save a draft with `expected_version`. |
| `POST` | `/foundation/complete` | Foundation administrator | Validate, persist, and complete the Foundation. |
| `GET` | `/legal/status` | Signed-in organization member | Read the current Terms, DPA, and Privacy acceptance status. |
| `POST` | `/legal/acceptance` | Organization administrator | Record the current combined legal acceptance idempotently. |
| `GET` | `/readiness/bases` | Active administrator | Read cumulative readiness depth and issues. |
| `GET` | `/readiness/prevalidation` | Active administrator | Check blockers and warnings before generation. |
| `GET` | `/dashboard` | Active administrator | Read `PREPARATION` or `OPERATIONAL` dashboard data. |

`GET /readiness/prevalidation` accepts the optional `strategy` query parameter from
[`ScheduleGenerationStrategy`](../../backend/app/models.py). It defaults to
`COMPLETE_GENERATION`; timetable updates request `ADAPTIVE_REPAIR` so the report
matches the operation that will run.
For adaptive repair, presence blockers use the snapshot's residual demand.
Teachers with only protected or completed lessons retain their presence exemption.

`GET /readiness/bases` returns exactly six cumulative public step codes, in this
order: `ACTIVE_CLASSES`, `MODULES`, `TEACHERS`, `TEACHER_ASSIGNMENT`,
`COMPATIBLE_ROOM`, and `TEACHER_AVAILABILITY`. `CLASS_SUBJECTS` and `TIMESLOTS`
are not public readiness steps. Foundation owns the weekly grid and final
prevalidation continues to report `MISSING_TIMESLOTS` when it is absent.
Prevalidation reports `CLASS_SUBJECT_WITHOUT_MODULES` when an active class subject has no selected module.

`GET /readiness/prevalidation` adds the `CLASS_WITHOUT_AVAILABILITY` blocker
when every visible block of an eligible class is marked Impossível.

For `NO_ELIGIBLE_ROOM` blockers, the issue context exposes
  `required_room_type_name` as the school’s room-type label. Compatibility is
  checked against the room-type catalogue ID, so custom room types remain distinct
  even when their labels are similar.

`PUT /foundation/draft` accepts `expected_version`, `current_step` from 1 to 10, and a strict Foundation data object.
The response returns the new version.
`POST /foundation/complete` accepts the expected version and `confirmed: true`.
It returns `COMPLETED`, the completion timestamp, and the generated timeslot count.

`POST /legal/acceptance` accepts only the following command:

```json
{
  "acceptance_confirmed": true,
  "terms_version": "2026-01",
  "dpa_version": "2026-01",
  "privacy_version": "2026-01"
}
```

The response contains the evidence ID, organization ID, accepting membership snapshot,
authority confirmation, three document versions, and the server timestamp.
Historical legal identity fields remain nullable and are never required for new records.

The database dependency uses function scope for endpoint transactions.
The dependency commits after the handler returns and rolls back on error.
Therefore a successful write response confirms a committed state.

Important error codes are `FOUNDATION_DRAFT_VERSION_CONFLICT`, `FOUNDATION_INCOMPLETE`, `FOUNDATION_ALREADY_COMPLETED`, `ACTIVE_SCHOOL_YEAR_REQUIRED`, and `PREFLIGHT_STALE`.

## Contracts and Invariants

- Protected routes derive `organization_id` from the active membership.
- The API does not accept a client-supplied tenant ID as authority.
- The contact route returns `204` on accepted or honeypot submissions.
- Production hides FastAPI documentation routes through settings.

### Occurrence payload compatibility

The public occurrence update and cancel payloads no longer accept the
free-text `reason` field. Clients that still send it receive `422`; this is an
intentional incompatible contract change. Consumers must remove the field
before rollout.

### Occurrence decisions and lesson execution

A pending occurrence creates no debt and no execution. The decision stores the
decision, instant, author, and reversal reason on the v1 lesson log. Clients
must not infer the decision from a debt balance.

- `GIVEN` requires the lesson end instant. Before it the API returns `422` with
  code `lesson_not_finished` and persists no effect.
- `GAP` creates the debt claim once for the original subject.
- `SUBSTITUTED` creates the same debt claim and a planned operational block.
  Planning credits no execution and reports `hours_given` as zero.
- Completing the operational block credits only the substitute subject.
- Reversing a completed substitute block requires
  `cancel_completed_substitute_log=true`; otherwise the API returns `409`.

The occurrence read exposes `substitute_block_id`,
`substitute_execution_status`, `ends_at`, `can_complete`, and
`blocked_reason`. The weekly read returns operational substitution slots with
`block_source="operational"` and hides the original lesson.

`GET /api/v1/occurrences/{id}/substitutes/diagnostics` returns every candidate
with `eligible`, structured `exclusions`, and `setup_actions`.
`PUT /api/v1/teachers/{teacher_id}/availability` lets an administrator update a
teacher availability grid without sending an invite.
The administrative availability reads and writes accept optional `on_date`.
Both requests select the grid valid on that school date.
Saving replaces that grid's preferences and preserves other grid versions.
The route uses `teacher_id`, not the organization membership identifier.

### Teacher presence

`GET /api/v1/teachers/{teacher_id}/presence` and
`PUT /api/v1/teachers/{teacher_id}/presence` read and write one teacher's optional
presence rule.
`PUT` requires the `admin` capability; `GET` allows the administrator or the
teacher themselves, and returns `403` for another teacher.
`GET /api/v1/teachers/me/presence` returns the rule of the teacher linked to the
caller, and `403` when the caller has no teacher profile.
Every route uses `teacher_id`, never the organization membership identifier, and
filters by `organization_id`; another organization's teacher returns
`404 resource_not_found`.

The rule is stored on `teacher` and survives grid versions and school years.
`TeacherPresence` carries `lunch_required`, `minimum_hours` and `max_gap_hours`.
`minimum_hours` and `max_gap_hours` are either both `null` or both set;
`minimum_hours` is between 1 and 12, `max_gap_hours` between 0 and 12.
Out-of-range values and an unpaired range return `422`.
Writing an unchanged rule records no scheduler change event.
A real change records `record_scheduler_change` with `entity_type="TEACHER_PRESENCE"`
and `active_resource` equal to whether the teacher has an assignment, so the
readiness fingerprint and the input revision follow the rule (D15).
`MemberRead.teacher_presence` exposes the same object for the Equipa list, or
`null` for a member without a teacher profile.

The server rejects decisions, revisions, and reversals that would change a
submitted or approved weekly timesheet. The normal summary route cannot change
the state of a lesson with an active occurrence decision.

The `schedule_health` widget exposes `annual_class_average`,
`annual_teacher_average`, `classes_total`, `teachers_total`, `period_start`, and
`period_end`. The annual denominator is the population present in the approved
schedule version. The weekly indicators use a closed Monday-to-Sunday window.
`classes_archived` counts archived classes still present in that approved version.
Archiving a catalog class does not remove its approved lessons or change the annual denominator.

### Class module selection

A class-subject link selects the modules the class takes for its grade level.

`GET /api/v1/classes/{class_id}/subjects` returns `modules`, sorted by `order`, each with a `selected` flag.
`POST /api/v1/classes/{class_id}/subjects` selects every module of the subject.
`PATCH /api/v1/classes/{class_id}/subjects/{subject_id}` accepts an optional `module_ids` list.
An empty list clears the selection.
An omitted or `null` `module_ids` leaves the selection unchanged.

The `PATCH` route validates the whole list before it writes.
Duplicate IDs and modules from another subject return `400`.
A module from another organization returns `404`.
An archived class returns the current archived-class error.

`GET /api/v1/classes/{class_id}` and the progress reads count only the selected modules.
`PATCH /api/v1/classes/{class_id}/progress` rejects an unselected module with the existing `400` curriculum error, on both the v1 and the legacy path.
Prevalidation and a generation or grid-change request return `CLASS_SUBJECT_WITHOUT_MODULES` when an active link has no selected module.

### Rate limits

SlowAPI enforces a default of `200 per day` and `50 per hour` per client.
The fail-closed middleware returns `503 RATE_LIMIT_UNAVAILABLE` when Redis
storage fails. Endpoint-specific limits are:

| Route | Limit |
| :--- | :--- |
| `POST /api/v1/contact` | `20/day` and `5/hour` |
| `POST /api/v1/client-errors` | `5/minute` |
| `PUT /api/v1/teachers/me/availability` | `30/minute` |
| `POST /api/v1/scheduler/generate` | `5/minute` |
| `GET /api/v1/schedule/week` | `60/minute` and `600/hour` |
| `GET /api/v1/schedule/me/horizon` | `300/hour` |

`GET /api/v1/health` is rate-limit exempt.

### Request body limits

`RequestBodyLimitMiddleware` bounds the body before parsing. The default limit is
`1 MiB`. Route overrides are:

| Route | Limit |
| :--- | :--- |
| `POST /api/v1/contact` | `16 KiB` |
| `POST /api/v1/webhooks/clerk` | `256 KiB` |
| `POST /api/v1/client-errors` | `4 KiB` |
| `POST /api/v1/imports/validate` | `8 MiB` |
| `POST /api/v1/imports/commit` | `8 MiB` |

A body over its limit returns `413 request_body_too_large`.

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
- `503`: provider, dependency, or rate-limit storage unavailable.

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
