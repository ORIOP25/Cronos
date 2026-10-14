# Repository Agent Instructions

These instructions apply to every AI agent working in this repository.
The repository owner is a product owner who does not read or write code.
Agents implement, verify, and deliver. The owner decides product behavior.

## Mandatory practices on every task

Apply all four practices to every task, whatever its size or type: feature, fix, refactor, test, documentation, configuration, review, or investigation.
A task delegated to a subagent carries these practices. State them in the subagent prompt.

1. **Clean code**: clear names, small focused units, explicit behavior, no unnecessary duplication.
2. **Clean Architecture**: keep domain rules independent from frameworks, transport, and persistence. Dependencies point toward the domain.
   `backend/app/scheduler/` is the reference layering (`domain`, `application`, `infrastructure`).
   Other backend services still use SQLAlchemy directly. Extract pure rules when a change touches them; do not restructure unrelated code.
3. **TDD**: for any behavior change, write or update a failing test first, implement the smallest change that passes, then refactor.
   For documentation or configuration, verify every claim against the code first, then check links and commands.
4. **Ponytail** at `full` intensity: load `.agents/skills/ponytail/SKILL.md` and apply its ladder.
   Reuse existing code, prefer the standard library and native features, and make the smallest correct change.
   Never simplify away validation, security, accessibility, data-loss prevention, or explicit user requirements.

Also:

- Inspect existing code, callers, tests, and conventions before editing.
- Do not add abstractions, dependencies, configuration, or files without a concrete need.
- Keep tests deterministic and focused on observable behavior.
- After frontend changes, rebuild the local frontend container (`docker compose up -d --build frontend`) so it serves the latest build.

## Skills

Load `cronos-base`, `ponytail`, and the specialist skill for the area.
The skills live in `.agents/skills/`. `.claude/skills/` holds thin adapters so Claude Code discovers the same skills.

| Area | Skill |
| :--- | :--- |
| FastAPI, SQLAlchemy, Alembic, Clerk backend | `cronos-backend` |
| Ensino Profissional rules, modules, hours | `cronos-domain` |
| React pages, hooks, routes | `cronos-frontend` |
| CSS, tokens, visual design | `cronos-frontend-designer` |
| Sumários, Faltas, substituições, timesheets, debt | `cronos-operations` |
| CP-SAT solver, generation, proposals | `cronos-scheduler` |
| Railway, Cloudflare, Clerk dashboard, mail, deploys, production diagnosis | `cronos-infra` |

[.agents/README.md](.agents/README.md) lists the imported third-party skills and how to install them.

## Where to find things

- Change path for each feature: [Repository Map](documentation/00_getting_started/REPOSITORY_MAP.md#feature-change-paths).
- Every setup, test, and inspection command: [Command Reference](documentation/00_getting_started/COMMAND_REFERENCE.md).
- Cloud providers and production: [Cloud Operations](documentation/09_ops_observability/CLOUD_OPERATIONS.md).

Read the relevant guide before editing a subsystem:

| Work area | Read first |
| :--- | :--- |
| Repository layout, onboarding, glossary, conventions | [documentation/00_getting_started/](documentation/00_getting_started/) |
| Architecture, runtime flows, data model | [documentation/01_system_architecture/](documentation/01_system_architecture/) |
| Professional education domain, members, school configuration | [documentation/02_domain_model/](documentation/02_domain_model/) |
| Scheduler engine | [documentation/03_scheduler_engine/README.md](documentation/03_scheduler_engine/README.md) and [SCHEDULER_V1_TECH_SPEC_V2.md](documentation/03_scheduler_engine/SCHEDULER_V1_TECH_SPEC_V2.md) |
| Sumários, faltas, substituições, timesheets, hour debt | [documentation/04_operational_features/](documentation/04_operational_features/) |
| Backend API, errors, transactions, resource removal | [documentation/05_backend_api/](documentation/05_backend_api/) |
| Frontend architecture, routes, permissions, design system, accessibility | [documentation/06_frontend_ux/](documentation/06_frontend_ux/) |
| Data, CSV import, bootstrap, seed | [documentation/07_data_and_seed/](documentation/07_data_and_seed/) |
| Security, tenant isolation, testing, CI | [documentation/08_security_quality/](documentation/08_security_quality/) |
| Local runtime, deployment, observability, privacy | [documentation/09_ops_observability/](documentation/09_ops_observability/) |

## Documentation rules

- Code, tests, migrations, and configuration are the source of truth. Update the guide in the same change when behavior changes.
- Do not copy lists, counts, or states that live in executable files. Link to the file that owns them.
- Follow [DOCUMENTATION_STANDARD.md](documentation/00_getting_started/DOCUMENTATION_STANDARD.md) and keep relative links valid.

## Delivery protocol

1. Restate the request as observable behavior and acceptance criteria. Ask the owner only for product decisions that the code cannot answer.
2. Identify the affected change path, invariants, permissions, and integrations from the Repository Map.
3. Implement with TDD and the four mandatory practices.
4. Verify with the proof that the [Command Reference](documentation/00_getting_started/COMMAND_REFERENCE.md#verification-by-change-type) requires for the change type.
5. Deliver through a pull request (see below). The description states behavior, evidence (exact commands and results), limitations, and open product questions.
6. Report to the owner in plain language: what changed for users, what was proven, and what remains.

Never claim a check passed without naming the exact command or CI job.

## Git, CI, and delivery

The owner grants standing authorization for this workflow. No further confirmation is needed for these steps:

1. Create a branch from `main` (`feat/`, `fix/`, `docs/`, `chore/`, `test/` prefixes).
2. Commit with Conventional Commit messages. Push the branch.
3. Open a pull request. A branch without a pull request gets no automatic CI.
4. Monitor the CI run until every required check passes: `backend`, `frontend`, `e2e-runtime`, `e2e-browser`.
   If a check fails, diagnose it, fix it, push again, and keep monitoring until it passes.
5. Squash-merge the pull request only when every required check is green.
6. Monitor the `Deploy check` workflow on `main` until it passes. If it fails, diagnose and fix it with a new pull request.

Limits:

- Never force-push `main`, rewrite published history, skip hooks, or merge a red or pending pull request.
- Never weaken, skip, or delete a test or gate to make CI pass.
- SonarCloud is not a required check. A Sonar failure blocks the merge only when it reports a bug, vulnerability, or security hotspot in the changed code.
  Complexity or maintainability findings in functions the change did not make worse do not block the merge. Note them in the pull request and merge.
- A merge deploys to production. Production data operations, provider settings, secrets, and DNS still need explicit owner approval.

## Conflict resolution

User requirements take precedence. When instructions conflict, preserve correctness, security, data integrity, and explicit requirements first; then apply these repository rules.
