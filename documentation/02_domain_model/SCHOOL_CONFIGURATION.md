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
| **Shift Start Time** | Time | `08:30` | Earliest daily slot start time |
| **Shift End Time** | Time | `18:30` | Latest daily slot end time |
| **Slot Duration** | Integer | `45` minutes | Standard lesson duration unit |
| **Max Daily Hours** | Integer | `8` hours | Maximum daily hours per teacher or class |
| **Active School Year** | Foreign Key | `2025/2026` | Target active academic year |

## Room Categories and Specifications
Rooms (`Room`) have types (`RoomType`):
- `STANDARD`: Standard theoretical classroom.
- `LABORATORY`: Computer lab or technical workshop.
- `GYMNASIUM`: Physical education sports facility.

Each subject assignment (`ClassSubjectLink`) can specify a required room type or explicit room.

## Calendar Events and Holidays
School calendar events (`SchoolCalendarEvent`) represent non-instructional days:
- National Holidays
- School Breaks / Vacations
- Institutional Events

The scheduler ignores calendar holiday slots during timetable generation.

## Contracts and Invariants
- Regenerating timeslot grids invalidates existing draft schedules if slot durations change.
- Deleting an active room removes it from future scheduler availability choices.

## Failure Modes
- Invalid Shift Configuration: Setting shift start time after shift end time returns HTTP `422 Unprocessable Entity`.

## Verification Procedure
Navigate to `/config`. Update shift duration or add a holiday event. Verify configuration persistence.

## Source Map
- Settings Router: `backend/app/api/v1/endpoints/org_settings.py`
- Rooms Router: `backend/app/api/v1/endpoints/rooms.py`
- Frontend Page: `frontend/src/pages/SchoolConfig.jsx`

## Related Documents
- [Professional Education](PROFESSIONAL_EDUCATION.md)
- [Scheduler Architecture](../03_scheduler_engine/SCHEDULER_ARCHITECTURE.md)
