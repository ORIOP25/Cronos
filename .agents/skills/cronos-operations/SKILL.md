---
name: cronos-operations
description: Cronos operational workflows skill. Use for lesson logs (Sumários), teacher absences and occurrences (Faltas), substitutions, weekly timesheets (Fecho Semanal), hour debt, and module progress. Not for cloud or infrastructure operations; use cronos-infra for those.
---

# Cronos Operations

Load `cronos-base`, `ponytail`, and `cronos-backend` or `cronos-frontend` first.

## Start here

- Lesson logs: `PUT /api/v1/schedule/lessons/{id}/log` and `/operational-blocks/{id}/log` in `backend/app/api/v1/endpoints/schedule.py`, implemented in `backend/app/scheduler/infrastructure/operations.py` (`record_lesson_log`, `record_operational_lesson_log`).
- Occurrences: `backend/app/api/v1/endpoints/occurrences.py` -> `backend/app/scheduler/infrastructure/occurrences.py` (`update_occurrence`, `cancel_occurrence`, `get_debts`).
- Timesheets: `backend/app/api/v1/endpoints/timesheets.py` -> `backend/app/services/timesheet_service.py`.
- Debt and progress rules: `backend/app/scheduler/domain/debt.py`, `backend/app/scheduler/infrastructure/progress.py`.
- Frontend hooks: `frontend/src/features/operations/data.js`. Pages: `Occurrences.jsx` (`/absences`), `Timesheets.jsx`, `MySchedules.jsx`, `MyProgress.jsx`.

## Reference implementation

- Pure rule plus test: `backend/app/scheduler/domain/lesson_time.py` with `backend/tests/unit/test_lesson_time_rule.py`.
- Thin endpoint: `backend/app/api/v1/endpoints/occurrences.py`.
- Frontend pure helper: `frontend/src/features/operations/weekSubmission.js` with `frontend/src/test/weekSubmission.test.js`.

## Minimal proof

- `node scripts/test.mjs fast --scope backend -- -k "debt or progress or lesson_time"` for rules.
- `node scripts/test.mjs integration -- -k "occurrences or timesheets or progress"` for service changes.
- `node scripts/test.mjs e2e --project app` covers `frontend/e2e/operations/weekly-operations.spec.js`.

## Invariants

- A pending occurrence creates no debt and no execution. Only `GAP` or `SUBSTITUTED` decisions create debt.
- A lesson can be executed only at or after its end time (`lesson_time.execution_allowed`).
- Occurrence decisions use optimistic versioning; a stale version returns `409 OCCURRENCE_STALE_VERSION` with no partial effect.
- A `SUBMITTED` or `APPROVED` week freezes logs and decisions.
- Timesheets move `OPEN` -> `SUBMITTED` -> `APPROVED`; only admins approve or reopen (`ALLOWED_TIMESHEET_TRANSITIONS`).
- Execution and debt history is append-only; settlement is oldest-origin-first and never exceeds the claim.

## Pitfalls

- An occurrence `id` is the `scheduler_lesson_log_v1.id`, not the lesson id. The list item also carries `lesson_db_id`.
- `PENDING` for a v1 lesson means "no log row"; the v1 table rejects the value.
- The week-lock rule exists in four places (`assert_week_open`, `_locked_weeks`, `record_operational_lesson_log`, the timesheet service). Change them together.
- `week_schedule` in `operations.py` returns about 30 keys that `WeekGrid` and `LessonLogModal` read. Renaming one breaks the UI.
- `Occurrences.jsx` and `Timesheets.jsx` are embedded in the tutorial. Run the tutorial tests after changing them.
- No frontend test covers `Timesheets.jsx` or `MyProgress.jsx`. Add one when you change them.

## Done when

- The proof above passed and the pull request names it.
- The guides below describe any changed rule or state.

## Documentation

- [Lesson Execution](../../../documentation/04_operational_features/LESSON_EXECUTION.md)
- [Occurrences and Substitutions](../../../documentation/04_operational_features/OCCURRENCES_AND_SUBSTITUTIONS.md)
- [Timesheets and Progress](../../../documentation/04_operational_features/TIMESHEETS_AND_PROGRESS.md)
- [Occurrence Reconciliation](../../../documentation/09_ops_observability/OCCURRENCE_RECONCILIATION.md)
