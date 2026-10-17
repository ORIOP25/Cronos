# School Configuration

## Purpose

This document describes school-year settings, lunch rules, calendar events, rooms, and timeslot generation.

## Intended Reader

This document targets backend engineers and frontend engineers maintaining configuration features.

## Prerequisites

Read [Data Model](../01_system_architecture/DATA_MODEL.md) and the [Scheduler Engine](../03_scheduler_engine/README.md).

## What the System Does

Administrators configure dates, repair stability, lunch rules, calendar events, rooms, and the weekly timeslot grid.

The scheduler reads these values during preflight and generation.

## Why the Behavior Exists

The configuration defines the legal planning interval and available resources for each organization.
State-version events detect changes that can invalidate a published schedule.

## Components and Ownership

| Area | Implementation |
| :--- | :--- |
| School settings | `organization_settings`, `backend/app/services/settings_service.py` |
| Grid settings | `organization_grid_settings`, `backend/app/api/v1/endpoints/org_settings.py` |
| Calendar events | `school_calendar_event`, `org_settings.py` |
| Internship flows | `school_calendar_event_class`, `backend/app/services/internship_flow_service.py` |
| Foundation status | `organization.foundation_status`, `backend/app/services/foundation_service.py` |
| Foundation draft | `organization_foundation_draft` (payload, version, current step) |
| Rooms | `backend/app/api/v1/endpoints/rooms.py` |
| Room types | `room_type`, `backend/app/services/room_type_service.py`, `backend/app/api/v1/endpoints/room_types.py` |
| Timeslots | `backend/app/api/v1/endpoints/timeslots.py` |
| Class availability | `class_availability`, `backend/app/services/class_availability_service.py`, `backend/app/api/v1/endpoints/classes.py` |
| Configuration UI | `frontend/src/pages/SchoolConfig.jsx` |

## Data or Request Flow

1. An administrator opens `/config`.
2. The frontend reads school, grid, calendar, room, and timeslot data.
3. The administrator changes a validated value.
4. The API persists the value and records scheduler impact.
5. Grid regeneration replaces timeslots atomically when preflight permits it.

## Contracts and Invariants

- `school_hard_end_date` cannot precede `school_start_date`.
- The school-year start, preferred end, and hard end persist together before scheduler audit events flush the transaction.
- Calendar changes preserve `start <= preferred <= hard end` without an invalid intermediate write.
- `repair_stability_window_days` stays between 0 and 60.
- `automatic_holidays_enabled` refreshes national holidays for the school period.
- Lunch start and end must appear together.
- Lunch end must follow lunch start.
- Lunch minimum duration cannot exceed the configured window.
- The requirement of a room or subject still uses the legacy `normal`, `lab`, `gym`, or `art` enum until the room-type slices migrate those readers.
- Each school owns its room types in `room_type`; foundation completion creates the initial ones defined by `DEFAULT_ROOM_TYPES` in `backend/app/services/room_type_service.py`.
- Exactly one active Normal type exists per school and it can neither be renamed nor removed.
- A room type name is unique per school ignoring case and accents.
- A room type in use by an active room or subject cannot be removed; one kept only by archived objects is archived and restored by creating the same name.
- Calendar events use `national_holiday`, `school_break`, `exam_period`, `other`, or `internship_flow`.
- Only an `internship_flow` event can link classes.
- Internship impact previews reference published v1 `lesson_id` values and protect completed execution.
- Applying an internship flow withdraws affected lessons durably through `SchedulerLessonLogV1.withdrawn_at`.
- Withdrawn lessons remain in version history and are excluded from operational scheduling and weekly submission requirements.
- Each withdrawn lesson also receives an `OCCURRENCE` log with a `GAP` decision, so the absence appears in `/absences`.
- Withdrawn lessons are not carried into a new version. Their absences stay listed on the version that withdrew them.
- Foundation status is `NOT_STARTED`, `IN_PROGRESS`, or `COMPLETED`.
- A `class_availability` row stores a level different from Neutral; a missing row means Neutral.
- Saving class availability replaces the class grid in the version visible on `on_date`.
- Grid regeneration and grid changes copy class rows by block signature, like teacher rows.

## States and Transitions

Configuration changes produce scheduler state scopes: `FUTURE_IMPACTING`, `PAST_ONLY`, `NO_OP`, or `INACTIVE_RESOURCE`.
Grid replacement is blocked when scheduler lifecycle rules do not permit it.
Foundation moves from `NOT_STARTED` to `IN_PROGRESS` on the first draft write and to `COMPLETED` on completion.

## Failure Modes

- Invalid date or lunch payload returns `422`.
- A protected grid cannot regenerate.
- A missing hard end date blocks scheduler preflight.
- A room or timeslot outside the tenant is rejected.

## Verification Procedure

1. Open `/config` as an administrator.
2. Save valid school dates and lunch settings.
3. Add a calendar event.
4. Regenerate the grid only when preflight allows it.
5. Run configuration and scheduler preflight tests.

## Source Map

- Models: `backend/app/models.py`
- Schemas: `backend/app/schemas.py`
- Settings router: `backend/app/api/v1/endpoints/org_settings.py`
- Room router: `backend/app/api/v1/endpoints/rooms.py`
- Timeslot router: `backend/app/api/v1/endpoints/timeslots.py`
- Class availability service: `backend/app/services/class_availability_service.py`
- Tests: `backend/tests/integration/committed/test_org_settings_endpoints.py`, `backend/tests/integration/committed/test_timeslots_crud.py`

## Foundation and School Configuration Boundary

Foundation is the first configuration boundary for a new organization.
It collects the calendar period, active weekdays, opening and closing times, slot duration, breaks, and lunch interval.
A new organization starts from the proposed default grid defined in [`foundationModel.js`](../../frontend/src/features/foundation/foundationModel.js).
A saved draft and an existing configured grid keep their stored values.
The first step includes the optional `Data preferencial de fim` beside the school start and hard end dates.
When provided, the preferred date must fall within the school period.
Drafts preserve this date. The confirmation summary displays it, and completion persists it in the scheduler school year.
Completion validates the complete snapshot and generates the initial timeslot grid.

The `/config` pages manage later operational configuration, such as school years, curriculum, staff, rooms, and other resources.
Do not use `/config` as a replacement for Foundation when `foundation_status` is not `COMPLETED`.

The readiness service then checks the cumulative bases needed for generation:

1. active class;
2. module with positive required minutes;
3. active teacher membership with teaching capability;
4. valid class-subject link with an active competent teacher;
5. compatible room;
6. possible teacher availability.

Foundation creates the weekly timeslot grid. It is not a public readiness step;
final prevalidation still blocks generation with `MISSING_TIMESLOTS` when the grid
is missing.

## Class Availability

Administrators set a weekly availability grid for each class, like the teacher grid.
The four levels are Preferencial, Neutro, Evitar, and Impossível.
A missing row means Neutro, so the service stores only rows that differ from Neutro.
Only an administrator reads or writes the class grid.

The scheduler reads the class grid as hard and soft unavailability.
An Impossível block is hard; an Evitar block is soft.
A class with one Preferencial block treats its other blocks as Evitar, like a teacher.

Saving, copying, and CSV import replace the whole grid of a class in the visible grid version.
A changed save bumps the planning revision, so a pending proposal becomes stale.
That happens only for a class with at least one class-subject link (`active_resource`).
A class without links does not invalidate the proposal.

Grid regeneration and grid changes treat class rows like teacher rows.
A block with the same signature keeps the class level.
A changed block requires an administrator decision.
See the [Class Availability Tech Spec](CLASS_AVAILABILITY_TECH_SPEC.md) and the [Scheduler Engine](../03_scheduler_engine/README.md).

## Tipos de sala da escola

Each school owns the list of room types it uses. Foundation completion creates the
initial types defined in `backend/app/services/room_type_service.py`, with exactly
one Normal type. Only an administrator reads or writes the list, through
`/api/v1/room-types` (see the [API Reference](../05_backend_api/API_REFERENCE.md)).

The administrator creates a type, renames one, or removes one. Names are compared
ignoring case and accents, so `laboratorio` collides with `Laboratório`. The Normal
type is fixed: it can neither be renamed nor removed. A type still used by an active
room or subject cannot be removed, and the response names the blocking rooms and
subjects. A type kept only by archived objects is archived; creating the same name
again restores it with the same identity and name. Editing the types records no
scheduler change.

Rooms and subjects name a school type through `room_type_id`, and the reads return
the type they use (see the [API Reference](../05_backend_api/API_REFERENCE.md)).
The legacy requirement enum stays in the database only as a bridge for the scheduler
engine until the final slice removes it; the migration backfilled both columns.

## Presença dos professores

The administrator sets an optional presence rule on each teacher.
The rule has three parts: whether the teacher must have a lunch break, a minimum
of whole hours per presence, and a maximum gap inside a presence.
A presence is the morning or the afternoon, split by the lunch break the engine
chooses for that teacher on that day; without lunch the whole day is one presence.
`lunch_required` defaults to `true` and is independent of the minimum.
`minimum_hours` and `max_gap_hours` are either both empty or both set.
The minimum is between 1 and 12 hours and the maximum gap is between 0 and 12
hours; the 12-hour ceiling is technical, not a product limit.
The rule is optional and a new teacher starts without a minimum (D01, D05, D06).

The rule belongs to the teacher and stays across school years and grid versions.
Only an administrator changes it, with `PUT /api/v1/teachers/{teacher_id}/presence`.
The value lives on the `teacher` table (`lunch_required`,
`minimum_presence_hours`, `maximum_presence_gap_hours`) with the paired and
range checks.
A real change counts as an availability change: if the teacher has an assignment,
it bumps the input revision and the readiness fingerprint, so a pending proposal
becomes stale.
Changing the rule of a teacher without assignments does not stale a proposal
(D15).
Write the rule through the API; the columns are the source of truth.

The "Presença na escola" section of the Equipa "Editar disponibilidade" modal
edits the rule, above the availability grid. It reads
`GET /api/v1/teachers/{teacher_id}/presence` by the `teacher.id`, not the
membership id. The section stays disabled until that read finishes, so a default
value never overwrites the stored rule (T08). "Guardar disponibilidade" saves
each changed part in its own request, the presence rule and the grid. A part
that succeeds stops being pending even when the other fails, and the message
names the part that was not saved. The Equipa list shows "Sem almoço" and
"Mín. {N}h · furo {M}h" when they apply.

## Related Documents

- [Professional Education](PROFESSIONAL_EDUCATION.md)
- [Scheduler Engine](../03_scheduler_engine/README.md)
- [Scheduler V1 Technical Specification](../03_scheduler_engine/SCHEDULER_V1_TECH_SPEC_V2.md)
