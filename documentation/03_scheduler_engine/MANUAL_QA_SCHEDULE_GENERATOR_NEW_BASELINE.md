# Schedule Generator New Baseline - Manual QA

## Purpose

Validate the administrator workflow from school setup through first publication,
debt repair, schedule adaptation, and school-year reset. Record the date, tester,
environment, organization, browser, and result for every section.

## Preconditions

- Use a dedicated QA organization and an administrator account.
- Ensure the worker and database migrations are running for the same environment.
- Prepare at least one course, class, subject with positive module hours, eligible
  teacher, compatible room, and Monday-Friday timetable slots.
- Give the school year enough future capacity to schedule all required module hours.
- Keep a second room or teacher availability change ready for the adaptation test.
- Open browser developer tools and fail the run if scheduler requests expose a
  manual strategy, mode, preferred end date, or target end date.

## 1. Configure The School Year

1. Open **Configuration** (`/config`).
2. Set the school start date and hard end date.
3. Set the repair stability window to `0` and save.
4. Configure lunch, calendar/blocked dates, timetable grid, rooms, teachers,
   availability, classes, assignments, and module hours.

Expected:

- settings save successfully;
- no preferred or target end date field exists;
- the payload contains the start date, hard end date, and stability window `0`;
- no solver strategy control exists.

## 2. Generate The First Schedule

1. Open **Schedules** (`/schedules`).
2. Confirm there is one **Generate Schedule** action and no complete/repair choice.
3. Start generation and keep the page open until the durable job reaches a terminal state.
4. Reload during generation once and confirm job progress resumes.

Expected:

- the job moves through queued/running to **Draft ready for review**;
- failure, cancellation, timeout, or No Valid Output is explained without publishing;
- success creates one pending draft and does not change the active schedule yet.

## 3. Review And Approve The First Draft

1. Review the summary counts, warnings, completion date, and hard end date.
2. Confirm **Approve** is available from the summary.
3. Open **View changes** and inspect the optional detailed diff.
4. Approve the draft.
5. Select a class and teacher in `/schedules` and inspect several weeks.

Expected:

- the diff is fetched only when opened;
- approval publishes exactly the draft target blocks;
- no duplicate class, teacher, or room slot exists;
- the pending-draft banner disappears and the published schedule is visible.

## 4. Verify Generation Is Blocked Without A Trigger

1. Return to `/schedules` without changing scheduler inputs or declaring debt.

Expected:

- no generation command is available;
- the page states that there are no declared missed hours and no schedule-relevant changes.

## 5. Declare Human-Controlled Debt

1. Open **Absences** (`/absences`).
2. Choose a past planned lesson and leave it undecided first.
3. Confirm no repair action becomes available while it is undecided.
4. Mark it as a missed lesson (`GAP`) with a reason.
5. Return to `/schedules`.

Expected:

- debt appears only after the explicit status decision;
- generation becomes available automatically, with no strategy selector.

## 6. Generate And Review Repair

1. Start generation.
2. Review the resulting draft summary.
3. Inspect recovered and remaining hours, selected recovery/adaptation level,
   changed blocks, affected stakeholders, disruption score, and warnings.
4. Open the optional diff.

Expected:

- past, executed, and immutable blocks are unchanged;
- with stability window `0`, today-forward eligible blocks may change;
- recovery blocks identify the exact debt occurrence/revision;
- a partial result shows one main blocker and recommended actions;
- approval remains possible only for a current, hard-valid draft.

## 7. Verify Atomic Replacement

1. Leave the repair draft pending.
2. Select **Generate again** and reject the confirmation once.
3. Repeat, accept the confirmation, then cancel the new job if the environment allows.
4. Repeat with a successful replacement generation.

Expected:

- rejecting confirmation starts no job;
- failure, cancellation, timeout, or No Valid Output preserves the old pending draft;
- success marks the old draft replaced and leaves exactly one new pending draft.

## 8. Approve Repair

1. Approve the current repair draft.
2. Inspect the affected weeks and the debt view.

Expected:

- editable future active blocks reconcile to the target draft;
- immutable and executed blocks remain unchanged;
- approved planned recovery covers only its declared debt minutes;
- fully covered debt no longer enables another repair;
- partially covered debt leaves only the residual amount eligible.

## 9. Generate Schedule Adaptation

1. Change one active scheduling input, such as room capacity/type, teacher
   availability, timetable grid, blocked date, or hard end date.
2. Return to `/schedules` and generate again without declaring new debt.
3. Review the summary and diff, then approve.

Expected:

- the scheduler-relevant change enables Adaptive Repair automatically;
- the smallest valid adaptation is preferred;
- unrelated text/profile edits do not enable generation;
- changing only the stability policy stales a pending repair draft but does not
  create a standalone generation trigger.

## 10. Stale Draft Check

1. Generate a draft and leave it pending.
2. Change teacher availability or another schedule-shaping input.
3. Attempt approval.

Expected:

- approval is blocked;
- the UI states that the draft is no longer current and instructs regeneration;
- no active schedule mutation is committed.

## 11. Reset The School Year

1. Invoke the administrator reset-year action with explicit confirmation.
2. Return to `/schedules`.

Expected:

- active jobs are canceled;
- pending drafts are retained for audit but invalidated;
- active blocks and planned recovery links are canceled;
- publication returns to `UNPUBLISHED`;
- the next available action is first schedule generation.

## Completion Record

The run passes only when every expected result above is observed and no console,
network, worker, or database error contradicts it. Attach screenshots for the
first draft summary, optional diff, partial-recovery message, stale warning,
published repair, adaptation diff, and post-reset first-generation state.
