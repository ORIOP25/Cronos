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
| Foundation status | `organization_foundation_draft`, `backend/app/services/foundation_service.py` |
| Rooms | `backend/app/api/v1/endpoints/rooms.py` |
| Timeslots | `backend/app/api/v1/endpoints/timeslots.py` |
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
- Room types are `normal`, `lab`, `gym`, or `art`.
- Calendar events use `national_holiday`, `school_break`, `exam_period`, `other`, or `internship_flow`.
- Only an `internship_flow` event can link classes.
- Foundation status is `NOT_STARTED`, `IN_PROGRESS`, or `COMPLETED`.

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
- Tests: `backend/tests/integration/committed/test_org_settings_endpoints.py`, `backend/tests/integration/committed/test_timeslots_crud.py`

## Foundation and School Configuration Boundary

Foundation is the first configuration boundary for a new organization.
It collects the calendar period, active weekdays, opening and closing times, slot duration, breaks, and lunch interval.
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

## Related Documents

- [Professional Education](PROFESSIONAL_EDUCATION.md)
- [Scheduler Engine](../03_scheduler_engine/README.md)
- [Scheduler V1 Technical Specification](../03_scheduler_engine/SCHEDULER_V1_TECH_SPEC_V2.md)
