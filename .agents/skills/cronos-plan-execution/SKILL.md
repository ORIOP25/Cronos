---
name: cronos-plan-execution
description: Cronos plan execution skill. Use when you implement a tech spec and WBS, or any feature that spans several slices or pull requests. Covers worktree setup, the slice loop, test budgets, parallel agents, early review, delivery, and progress reports to the owner.
---

# Cronos Plan Execution

Load `cronos-base`, `ponytail`, `cronos-infra`, and the specialist skills for the slices.
Speed comes from fewer hand-offs, strong first proofs, and no duplicated test runs. Never from weaker proof.
Do not add rules that are stricter than [AGENTS.md](../../../AGENTS.md) or this skill. Past slowdowns came from invented rules.

## 1. Preflight (at most 15 minutes)

1. Create a new worktree and branch from a fresh `origin/main`. Never work in a checkout that another session uses.
2. Prepare the worktree once: the runner `setup` for the scopes you need, and the local environment files (see [Local stack in a worktree](../../../documentation/00_getting_started/COMMAND_REFERENCE.md#local-stack-in-a-worktree)).
3. Read the spec and the WBS once. If the plan has an open decision or a slice larger than M, stop and ask the owner. Do not improvise product behavior.
4. Check coexistence: `git worktree list`, open pull requests, and the latest Alembic revision on `origin/main`. Rename your migration now if it collides.
5. Use CI on `main` as the baseline. Do not run full local suites as a baseline.
6. Tell the owner the plan in one message: pull requests, lanes, timeboxes, and the start time.

## 2. Lanes and hand-offs

A lane is a chain of slices that one implementer runs from start to end without stopping.

- The implementer of a lane writes the tests, implements, runs the slice proof, and commits each slice. It does not wait for approval between slices.
- A slice that depends on another lane starts from that lane's branch, or waits until that branch is on `main`. Never copy files between worktrees by hand.
- Run the hot-file slice of the WBS first, alone. Start the parallel lanes from its commit.
- You stay the coordinator. Review only at two points: when a lane ends, and before a pull request.

## 3. Slice loop

For each slice, in lane order:

1. Write the slice's risk scenarios (`R..`) with the exact expected result from the spec. Run them and see them fail for the expected reason.
2. Implement the smallest change that passes.
3. Run only the slice proof: one test file, a `-k` filter, or one E2E scenario.
4. Commit with the slice id, for example `feat(classes): accept module_ids (S2)`.
5. Record the proof for the slice (see the proof record below).

**Stop rule:** when a slice takes twice its timebox, stop. Report the cause and the options to the owner before you continue.

### Proof record

Each slice ends with this record, in the lane report or the commit body:

- The failing command, its exit code, and the failure reason.
- The passing command and its exit code.
- The exact assertion that proves the risk scenario, for example `outcome == "COMPLETE"`.

Reject a slice when an assertion accepts more than one outcome without a reason in the spec, or when a test can pass without the new code.
A slice must never raise a limit, a budget, a timeout, or a coverage threshold, or remove an assertion. Stop and ask the owner instead.

## 4. Test budget

The [Command Reference](../../../documentation/00_getting_started/COMMAND_REFERENCE.md#verification-by-change-type) names the commands. Use them at these points only:

| Moment | Proof |
| :--- | :--- |
| Inside a slice | One test file, a `-k` filter, or one E2E scenario. |
| End of a lane with database changes | `integration` with `-k <area>`. A filtered run skips the infrastructure contracts. |
| Before a pull request | Each broad proof that the WBS names for the pull request, once. Add the unfiltered `integration` run only for a migration or RLS change. |
| Full corpus and `slow_solver` | CI on the pull request. Do not repeat it locally. |

- Run the `slow_solver` tests locally only to diagnose a failure of the `e2e-runtime` CI job.
- Never rerun a passing proof on the same commit. Rerun only after the tested files or the environment change.
- When a broad run fails, rerun only the failing tests until they pass, then rerun the broad command once.
- Never run tests while any agent edits the same worktree. The results are not valid.
- Run long commands in the background. While they run, review or plan. Do not edit files that the run imports.

## 5. Parallel agents

- One writer per worktree. Start each implementer with worktree isolation.
- Run at most three implementers at a time, one per lane.
- Give each implementer one closed brief for its whole lane:
  - The four mandatory practices of [AGENTS.md](../../../AGENTS.md) and the skills to load.
  - The slices, spec sections, write set, and the files it must not change.
  - The base branch or commit to start from.
  - The risk scenarios with the exact expected results, and the proof command for each slice.
  - "Commit each slice. Do not stop between slices. Finish the lane or return BLOCKED with the cause. Do not run full suites. Do not change a limit, budget, threshold, or assertion."
  - Return format: status, commits, the proof record of each slice, and deviations from the spec.
- Read the returned diff and proof records. Do not rerun a proof that the record shows on the same commit.

## 6. Review

- Review once per pull request, before the first push. Use a fresh reviewer on the whole diff, with the spec risk table and the proof records as the checklist.
- Fix every confirmed finding with a failing test first.

## 7. Delivery

Push a pull request only when it is complete: code, tests, the E2E proof that the WBS names, the documentation, and the review fixes.
One complete push gives one CI cycle. Each later push repeats the full CI.

- Follow the delivery loop in `cronos-infra` for each pull request.
- Put status notes in the pull request description or comments, not in repository files.
- Merge each pull request when its checks are green. Start the next pull request from the updated `main`.
- Rebase onto `main` at each pull request boundary, not in the middle of a lane.
- For manual checks, rebuild the local stack from the worktree that holds the change. Tell the owner which branch and commit it serves.

## 8. Report

Send the owner a plain-language report at each pull request boundary and at the end:

- What changed for users.
- What was proven, with the exact commands or CI jobs.
- Time used per lane and per pull request against the plan, and the cause of any overrun.
- What remains, and any open product question.

## Anti-patterns

These caused past features to take three to nine hours:

- A stop, review, and approval between every slice.
- A ban on commits in worktrees, then files copied by hand between worktrees that went stale.
- Weak first proofs: a test that accepts an impossible outcome, an assertion that never reaches the new path, a raised query budget.
- `slow_solver` and unfiltered `integration` runs repeated locally, although CI runs them.
- A pull request pushed before its E2E proof or documentation was ready, so CI ran twice.
- Manual checks on a local stack built from an old checkout.
- Two agents in one worktree, so tests ran against half-edited files.
