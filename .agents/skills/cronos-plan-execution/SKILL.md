---
name: cronos-plan-execution
description: Cronos plan execution skill. Use when you implement a tech spec and WBS, or any feature that spans several slices or pull requests. Covers worktree setup, the slice loop, test budgets, parallel agents, early review, delivery, and progress reports to the owner.
---

# Cronos Plan Execution

Load `cronos-base`, `ponytail`, `cronos-infra`, and the specialist skills for the slices.
Speed comes from fewer full test runs, isolated workers, early risk tests, and small pull requests. Never from weaker proof.

## 1. Preflight (at most 10 minutes)

1. Create a new worktree and branch from a fresh `origin/main`. Never work in a checkout that another session uses.
2. Read the spec and the WBS once. If the plan has an open decision or a slice larger than M, stop and ask the owner. Do not improvise product behavior.
3. Check coexistence: `git worktree list`, open pull requests, and the latest Alembic revision on `origin/main`. Rename your migration now if it collides.
4. Use CI on `main` as the baseline (`gh run list --branch main --limit 1`). Do not run full local suites as a baseline.
5. Tell the owner the plan in one message: pull requests, slices, timeboxes, and what runs in parallel.

## 2. Slice loop

For each slice, in WBS order:

1. Write the slice's risk scenarios (`R..`) and first tests. Run them and see them fail.
2. Implement the smallest change that passes.
3. Run only the slice proof: one test file or a `-k` filter.
4. Diff the slice against the spec: identifiers, every listed call site in the write set, and the risk hazards.
5. Commit with the slice id, for example `feat(classes): accept module_ids (S2)`.
6. Send the owner one plain line: slice done, time used against the timebox, next slice.

**Stop rule:** when a slice takes twice its timebox, stop. Report the cause and the options to the owner before you continue.

## 3. Test budget

The [Command Reference](../../../documentation/00_getting_started/COMMAND_REFERENCE.md#verification-by-change-type) names the commands. Use them at these points only:

| Moment | Proof |
| :--- | :--- |
| Inside a slice | One test file or `-k` filter. Seconds to a few minutes. |
| End of a slice with database changes | `integration` with `-k <area>`. |
| Before a pull request | The proof that the WBS names for the pull request, once. Add the full `integration` run only for a migration or RLS change. |
| Full corpus | CI on the pull request. Do not repeat it locally. |

- Never run `fast --scope backend` without `-k`. It includes a CP-SAT test with a 900-second budget.
- Never run tests while any agent edits the same worktree. The results are not valid.
- Run long commands in the background. While they run, read code or plan. Do not edit files that the run imports.
- When a broad run fails, rerun only the failing tests until they pass, then rerun the broad command once.

## 4. Parallel agents

Delegate only slices on different lanes of the WBS. Never delegate a hot file.

- One writer per worktree. Start each subagent with worktree isolation.
- Run at most three agents at a time. You stay the integrator.
- Give each agent a closed brief:
  - The four mandatory practices of [AGENTS.md](../../../AGENTS.md) and the skills to load.
  - Slice ids, spec sections, the write set, and the files it must not change.
  - The risk scenarios to test first, and the exact proof command.
  - "Finish the slice or return BLOCKED with the cause. Do not return partial work. Do not run full suites."
  - Return format: status, commits, commands with results, deviations from the spec.
- Merge each returned branch into your branch, then run the slice proof again.

## 5. Review early

- Review each pull request before you open it. Use a fresh reviewer on the diff, with the spec risk table as the checklist.
- Fix every confirmed finding with a failing test first.
- Do not wait for the last pull request to review the first.

## 6. Delivery

- Follow the delivery loop in `cronos-infra` for each pull request of the WBS.
- Merge each pull request when its checks are green. Start the next pull request from the updated `main`.
- Rebase onto `main` at each pull request boundary, not in the middle of a slice.
- Update the WBS status table in the pull request that changes the status.
- After frontend changes, rebuild the local frontend container as [AGENTS.md](../../../AGENTS.md#mandatory-practices-on-every-task) requires.

## 7. Report

Send the owner a plain-language report at each pull request boundary and at the end:

- What changed for users.
- What was proven, with the exact commands or CI jobs.
- Time used against the plan, and the cause of any overrun.
- What remains, and any open product question.

## Anti-patterns

These caused past features to take more than seven hours:

- Full suites after every small fix.
- Two agents in one worktree, so tests ran against half-edited files.
- One large review at the end that found integration errors late.
- Risk scenarios, such as multi-day imports, tested only after review.
- One pull request for the whole feature, so `main` moved and forced conflict work and migration renumbering.
- Delegations without a write set or done condition, which returned partial work.
