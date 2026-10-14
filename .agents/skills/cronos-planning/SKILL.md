---
name: cronos-planning
description: Cronos feature planning skill. Use when you write or revise a tech spec and a WBS (work breakdown) for a feature that spans several layers or pull requests, or when the owner asks for a plan before implementation.
---

# Cronos Planning

Load `cronos-base`, `ponytail`, and the specialist skills for the areas that the feature touches.
The plan exists to make implementation fast and correct. A plan is ready only when an agent can execute it without new product decisions and without discovering call sites late.

## Outputs

Write two files in the guide folder of the main area, for example `documentation/02_domain_model/`:

- `<FEATURE>_TECH_SPEC.md`: decisions, contracts, risk scenarios, and affected call sites. At most 400 lines.
- `<FEATURE>_WBS.md`: vertical slices, write sets, lanes, and proof commands. At most 200 lines.

Use the skeletons in [templates.md](templates.md). Write the product text in Portuguese, with the section headings of the [Documentation Standard](../../../documentation/00_getting_started/DOCUMENTATION_STANDARD.md).
Link to code and the [Command Reference](../../../documentation/00_getting_started/COMMAND_REFERENCE.md). Do not paste code or commands.

## Procedure

1. **Close the decisions.** Use the `grill-me` method with the owner: one question at a time, with your recommendation. Record each answer as a numbered decision (`D01`). A spec with an open product question is not ready.
2. **Inventory the call sites.** Search the code for every reader and writer of each changed model, field, or rule. List them in the spec with file paths. Late integration failures came from readers that the plan did not list.
3. **Name the identifiers.** For each id in the contracts, state the table it points to. For example, `class_id` is `classes.id`, never `class_subject_links.id`.
4. **Write the risk scenarios.** Each scenario is a failing test that implementation writes first. Cover every applicable hazard from the list below. Give each an id (`R01`).
5. **Check coexistence.** List open branches and specs that touch the same files (`git worktree list`, open pull requests). Record the base commit of `main` and the latest Alembic revision. State the merge order if another feature must land first.
6. **Slice vertically.** Split the work into 4 to 10 slices. Each slice delivers observable behavior with its tests, and fits in 90 minutes. Split any larger slice.
7. **Group slices into pull requests.** Each pull request merges alone and keeps `main` deployable. Prefer 2 to 4 pull requests over one large one. Hide incomplete UI behind the existing route or permission until its pull request lands.
8. **Assign write sets.** For each slice, list the files it creates or changes. Mark files that more than one slice changes as hot files. Only slices with disjoint write sets can run in parallel lanes.
9. **Set the proof per slice.** Name the narrowest test file or `-k` filter, and the runner profile from [Verification by change type](../../../documentation/00_getting_started/COMMAND_REFERENCE.md#verification-by-change-type).
10. **Review the plan.** Ask a fresh agent to execute slice 1 on paper: does every path exist, is every call site covered by a slice, does every decision and risk map to a slice? Fix gaps before you hand over the plan.

## Risk hazards

Check each hazard. Write a risk scenario for every one that applies.

| Hazard | Example failure from past features |
| :--- | :--- |
| Identifier confusion | A class id used where a link id was expected. |
| Version or date selection | A per-class decision read from the wrong school year or version. |
| Multi-item writes | Importing several days replaced the earlier days instead of merging. |
| Reversal | Unselecting, then selecting again after other records exist. |
| History preservation | A change invalidates past Sumários, Faltas, or credited minutes. |
| Tenant isolation | A query or import without `organization_id`. |
| Empty and boundary states | No items selected, a new item added later, the last item removed. |
| Scheduler readers | Generation, recovery, proposals, progress, and fingerprint read different sources. |
| Migration chain | A revision number that collides with another open branch. |

## Rules

- The spec owns decisions, contracts, and scenarios. The WBS references them by id and never repeats them.
- Do not plan one commit per function. A slice is a behavior, not a layer.
- Do not add a baseline slice that runs full suites. CI on `main` is the baseline.
- Each slice has a timebox: **S** up to 30 minutes, **M** up to 90 minutes. There is no larger size.
- Record execution status only in the WBS status table. Update it at pull request boundaries.

## Done when

- Every decision, call site, and risk scenario maps to at least one slice.
- Every slice has a write set, a first test, a narrow proof command, and a timebox.
- The lanes table shows which slices run in parallel and which hot files force order.
- The plan review found no missing path or call site.
- The documents pass the link check and `git diff --check`.

Implement the plan with the `cronos-plan-execution` skill.
