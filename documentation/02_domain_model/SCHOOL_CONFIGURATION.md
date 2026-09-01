# School Configuration

## Purpose

This document describes school-year settings, lunch rules, calendar events, rooms, and timeslot generation.

## Intended Reader

This document targets backend engineers and frontend engineers maintaining configuration features.

## Prerequisites

Read [Data Model](../01_system_architecture/DATA_MODEL.md) and [Scheduler Behavior](../03_scheduler_engine/SCHEDULER_BEHAVIOR.md).

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
- `repair_stability_window_days` cannot be negative.
- Lunch start and end must appear together.
- Lunch end must follow lunch start.
- Lunch minimum duration cannot exceed the configured window.
- Room types are `normal`, `lab`, `gym`, or `art`.
- Calendar events use `national_holiday`, `school_break`, `exam_period`, or `other`.

## States and Transitions

Configuration changes produce scheduler state scopes: `FUTURE_IMPACTING`, `PAST_ONLY`, `NO_OP`, or `INACTIVE_RESOURCE`.
Grid replacement is blocked when scheduler lifecycle rules do not permit it.

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
- Tests: `backend/tests/test_org_settings_endpoints.py`, `test_timeslots_crud.py`

## Foundation and School Configuration Boundary

Foundation is the first configuration boundary for a new organization.
It collects the calendar period, active weekdays, opening and closing times, slot duration, breaks, and lunch interval.
Completion validates the complete snapshot and generates the initial timeslot grid.

The `/config` pages manage later operational configuration, such as school years, curriculum, staff, rooms, and other resources.
Do not use `/config` as a replacement for Foundation when `foundation_status` is not `COMPLETED`.

The readiness service then checks the cumulative bases needed for generation:

1. active class;
2. valid class-subject link;
3. module with positive required minutes;
4. active competent teacher;
5. compatible room;
6. generated timeslot;
7. possible teacher availability.

## Related Documents

- [Professional Education](PROFESSIONAL_EDUCATION.md)
- [Scheduler Operations](../03_scheduler_engine/SCHEDULER_OPERATIONS.md)
