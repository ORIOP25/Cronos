# School Configuration

## Purpose
This document specifies school parameters, shift configurations, slot definitions, room categories, and calendar events.

## Intended Reader
This document targets backend developers and UI engineers working on configuration features.

## Prerequisites
Read [Data Model](../01_system_architecture/DATA_MODEL.md).

## What the System Does
Administrators configure school operational boundaries through the **Configuração da Escola** section (`/config`). These parameters dictate scheduler constraints.

## Configuration Parameters Table

| Setting | Type | Example | Purpose |
| :--- | :--- | :--- | :--- |
| **School Start Date** | Date | `2025-09-15` | First instructional date |
| **Hard End Date** | Date | `2026-07-31` | Last date available to the scheduler |
| **Repair Stability Window** | Integer | `14` days | Future interval protected during repair |
| **Grid Window** | Time range | `08:30`-`18:30` | Bounds for generated timeslots |
| **Slot and Break Duration** | Integer | `50` / `10` minutes | Generated lesson and break lengths |
| **Lunch Window** | Time range | `12:00`-`14:00` | Required lunch-break search window |

## Room Categories and Specifications
Rooms (`Room`) have types (`RoomType`):
- `normal`: Standard theoretical classroom.
- `lab`: Computer lab or technical workshop.
- `gym`: Physical education sports facility.
- `art`: Art room.

Each subject specifies a required room type. A `specific_room` constraint can restrict a class and subject.

## Calendar Events and Holidays
School calendar events (`SchoolCalendarEvent`) represent non-instructional days:
- National Holidays
- School Breaks / Vacations
- Exam Periods and Other Events

The scheduler ignores calendar holiday slots during timetable generation.

## Contracts and Invariants
- Grid regeneration is blocked after publication or while protected scheduler data exists.
- Settings, grid, and calendar changes record scheduler state-version events.

## Failure Modes
- Invalid Grid Configuration: An invalid time range or lunch window returns HTTP `422 Unprocessable Entity`.

## Verification Procedure
Navigate to `/config`. Update shift duration or add a holiday event. Verify configuration persistence.

## Source Map
- Settings Router: `backend/app/api/v1/endpoints/org_settings.py` under `/api/v1/school`
- Rooms Router: `backend/app/api/v1/endpoints/rooms.py`
- Frontend Page: `frontend/src/pages/SchoolConfig.jsx`

## Related Documents
- [Professional Education](PROFESSIONAL_EDUCATION.md)
- [Scheduler Architecture](../03_scheduler_engine/SCHEDULER_ARCHITECTURE.md)
