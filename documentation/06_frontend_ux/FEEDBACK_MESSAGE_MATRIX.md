# Feedback Message Matrix

## Purpose

This document records the channel and owner for each feedback message.
The feedback contracts live in [Frontend Architecture](FRONTEND_ARCHITECTURE.md) and [Accessibility](ACCESSIBILITY.md).

## Intended Reader

This document targets frontend engineers and reviewers.

## Prerequisites

Read the [Frontend Architecture](FRONTEND_ARCHITECTURE.md).

## Classification Rules

1. Page states and structured content stay in the content area.
2. Field validation stays next to the field or group.
3. Business blocks stay in context while the condition exists.
4. Short action results and transient failures use toasts.

A transient failure is a network error or an HTTP `429` or `5xx` response.
Other client responses stay in context.

## Message Matrix

| Operation | Trigger | Known code | Channel | Owner | Recovery |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Save availability | Success | — | Toast, 4 s | `MyAvailability` | — |
| Save availability | Transient failure | Network, 429, 5xx | Toast, 6 s | `MyAvailability` | Draft stays, retry |
| Save availability | Context changed before the response | — | No feedback | `useAttemptScope` guard | Retry in the new context |
| Remove or archive a row | Success | — | Toast, 4 s | `SmartTable` | — |
| Remove a row | Business block | `resource_in_use`, `course_has_classes` | Banner in context | `SmartTable` | Fix and retry |
| Remove a row | Transient failure | Network, 429, 5xx | Toast, 6 s | `SmartTable` | Retry |
| Create or edit a catalog record | Success | — | Toast, 4 s | Page | — |
| Create or edit a catalog record | Transient failure | Network, 429, 5xx | Toast, 6 s | Page | Form stays open |
| Assign a teacher | Missing competency | `teacher_competency_missing` | Field feedback | `ClassSubjects` | Choose an eligible teacher |
| Assign a teacher | Transient failure | Network, 429, 5xx | Toast, 6 s | `ClassSubjects` | Retry |
| Save an internship flow | Success | — | Toast, 4 s | `CalendarSection` | — |
| Save an internship flow | Stale preview | `CALENDAR_EVENT_STALE` | Persistent banner | `CalendarSection` | Repeat the preview |
| Save an internship flow | Transient failure | Network, 429, 5xx | Toast, 6 s | `CalendarSection` | Retry |
| Save the school period | Success | — | Toast, 4 s | `SettingsEditor` | — |
| Sync automatic holidays | Failure with recovery | `HOLIDAY_SYNC_FAILED` | Banner with action | `SettingsEditor` | Disable holidays and save |
| Validate school dates | Invalid group | Local validator | Banner near the group | `SettingsEditor` | Fix the dates |
| Preview a grid change | Success | — | State in context | `GridEditor` | — |
| Propose a grid change | Stale analysis | `GRID_CHANGE_STALE` | Persistent banner | `GridEditor` | Repeat the preview |
| Validate the grid | Invalid form | Local validator | Banner near the action | `GridEditor` | Fix the values |
| Regenerate the grid | Success | — | Toast, 4 s | `GridEditor` | — |
| Save a lesson log | Success | — | Toast, 4 s | `LessonLogModal` | — |
| Save a lesson log | Transient failure | Network, 429, 5xx | Toast, 6 s | `LessonLogModal` | Retry |
| Save a lesson log | Server block | `lesson_not_finished`, 409 | Banner in the modal | `LessonLogModal` | Fix or consult |
| Reopen a week | Success | — | Toast, 4 s | `LessonLogModal`, `Timesheets` | — |
| Submit a week | Success | — | Toast, 4 s | `MySchedules` | — |
| Submit a week | Transient failure | Network, 429, 5xx | Toast, 6 s | `MySchedules` | Retry |
| Submit a week | Server block | 400 | Banner in context | `MySchedules` | Fix the blockers |
| Approve or reopen a timesheet | Success | — | Toast, 4 s | `Timesheets` | — |
| Change a timesheet state | Server block | 400 | Banner in context | `Timesheets` | Consult the week |
| Decide or revert an occurrence | Success | — | Toast, 4 s | `Occurrences` | — |
| Decide or revert an occurrence | Transient failure | Network, 429, 5xx | Toast, 6 s | `Occurrences` | Retry |
| Decide an occurrence | Server conflict | 409 | Banner in the modal | `Occurrences` | Refresh the data |
| Request generation | Accepted | — | Toast, 4 s | `Schedules` | Follow the panel |
| Approve or reject a proposal | Success | — | Toast, 4 s | `Schedules` | — |
| Approve a proposal | Stale proposal | `proposal_stale` | Persistent banner | `Schedules` | Generate a new proposal |
| Generation failure | Known failure | `NO_ELIGIBLE_ROOM` and others | `FailureState` in context | `Schedules` | Retry or open rooms |
| Validate or commit an import | Success | — | Toast, 4 s | `BulkImport` | — |
| Validate or commit an import | Transient failure | Network, 429, 5xx | Toast, 6 s | `BulkImport` | Retry |
| Import issues | Structured list | — | List panel | `BulkImport` | Consult each issue |
| Invite, sync, or restore a member | Success | — | Toast, 4 s | `Members` | — |
| Member action | Transient failure | Network, 429, 5xx | Toast, 6 s | `Members` | Retry |
| Member action | Access block | `member_sync_error` and others | Banner in context | `Members` | Resolve the sync |
| Load the team | Failure | — | Banner with retry | `Members` | Retry |
| Submit a form | Invalid field or group | Local validator | Field feedback and focus | Form component | Fix the value |
| Prevalidate a generation | Blockers or warnings | — | List panel | `Schedules` | Consult each item |

## Justified Exceptions

`CAlert` remains only in `BulkImport.jsx` and `Schedules.jsx`, for structured lists.
The import issues and warnings in `BulkImport` need per-line reading.
The generation prevalidation list in `Schedules` links to the affected configuration.
These panels keep their hierarchy, actions, and keyboard access.

## Ownership Rules

- One attempt produces one result message.
- The component that starts the request owns the feedback.
- Mutation callbacks are guarded with `useAttemptScope`.
- Visible toasts are cleared when the user or organization changes.
- The guide clears simulated messages when its context ends.

## Related Documents

- [Frontend Architecture](FRONTEND_ARCHITECTURE.md).
- [Accessibility](ACCESSIBILITY.md).
