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

## Conflict resolution

User requirements take precedence. When instructions conflict, preserve correctness, security, data integrity, and explicit requirements first; then apply these repository rules.
