# Repository Agent Instructions

These instructions apply to every AI agent working in this repository.

## Required engineering approach

- Use clean code: clear names, small focused units, explicit behavior, and no unnecessary duplication.
- Follow Clean Architecture: keep domain rules independent from frameworks, infrastructure, transport, and persistence; enforce dependencies toward the domain.
- Use TDD for non-trivial changes: write or update a failing test first, implement the smallest change that passes, then refactor.
- Keep tests deterministic and focused on observable behavior.
- Inspect existing code, callers, tests, and project conventions before editing.
- Do not add abstractions, dependencies, configuration, or files without a concrete need.
- Verify changes with the narrowest relevant tests, then run the required project checks before declaring success.
- After every push to GitHub, monitor the associated CI run until it passes. If CI fails, diagnose the failure, fix it, push again, and continue monitoring until it passes.
- After frontend changes, ensure the frontend Docker container is rebuilt or refreshed as needed so it displays the most recent updates; do not leave the user with a stale frontend image or running container.

## Required skill

- Always use the repository's `ponytail` skill for coding, refactoring, fixing, reviewing, designing, and dependency decisions.
- Keep Ponytail at its default `full` intensity unless the user explicitly changes it.
- Apply its YAGNI ladder: reuse existing code, prefer the standard library and native features, and make the smallest correct change.
- Do not simplify away validation, security, accessibility, data-loss prevention, or explicit user requirements.

## Required documentation context

- Read the relevant guide under `documentation/` before editing a subsystem.
- Code, tests, migrations, and configuration are the source of truth. Update the guide when behavior changes.
- Follow [DOCUMENTATION_STANDARD.md](documentation/00_getting_started/DOCUMENTATION_STANDARD.md) when editing documents and keep relative links valid.

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

## Conflict resolution

User requirements take precedence. When instructions conflict, preserve correctness, security, data integrity, and explicit requirements first; then apply these repository rules.
