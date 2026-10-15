# Safe Resource Removal

## Purpose

Remove rooms, subjects, classes, and courses from current management.
Preserve schedules, lesson records, and progress history.

## Proven cause

The DELETE routes removed rows directly. A resource with history caused a
foreign-key violation. The API returned HTTP 500.

Starlette renders an unexpected exception in the outermost server-error
middleware. That middleware sits outside the CORS middleware. The response had
no `Access-Control-Allow-Origin` header. The browser reported a network error.

## Required behaviour

Apply these rules to each resource:

1. Block the removal when the resource is used by the active schedule or by a
   running operation. Return HTTP 409 with the `resource_in_use` code.
2. Archive the resource when history exists. Set `is_archived` to `true`.
   Keep the row, the modules, and the progress ledger.
3. Delete the row physically when no reference exists.
4. Remove configuration associations in the same transaction. This includes
   constraints and class or course links.
5. Keep the course rule. Remove current classes first. Archive a course whose
   classes are archived.
6. Block a resource used by a joint lesson. A class/subject link in a
   `joint_lesson_group_member`, a member class, and a `joint_lesson_group_module`
   return HTTP 409 with the `resource_in_use` code. See
   [Professional Education](../02_domain_model/PROFESSIONAL_EDUCATION.md).

## HTTP contract

The DELETE routes keep HTTP 200 and the `message` field. They add the
`remove_effect` field.

```json
{ "message": "Sala removida com sucesso", "remove_effect": "archive" }
```

`remove_effect` is `archive` or `hard_delete`.

Recognised integrity violations become HTTP 409 with the `conflict` code.
Unknown errors stay HTTP 500.

## Database migration

The consolidated baseline defines `is_archived` on `room`, `subject`, `course`, and `class`.
The column is `NOT NULL` and defaults to `false`.

## Current management

Lists, selectors, readiness, fingerprints, snapshots, and dashboard counts
exclude archived resources. Historical queries still resolve archived rows.
The API rejects new associations and edits on archived resources.

## Tests

- `backend/tests/integration/committed/test_resource_removal.py` proves the
  archive, hard-delete, block, filtering, and CORS behaviours.
- `frontend/src/test/SmartTable.test.jsx` covers archive and hard-delete
  feedback.
- `frontend/src/test/apiErrors.test.js` maps the `resource_in_use` code.

## Limits of this delivery

This change does not purge history, restore archived resources, or refactor the
general architecture.
