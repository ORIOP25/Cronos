# Beta Scheduler Remediation Implementation - 2026-07-15

## Scope

This change set implements SCHED-001 through SCHED-007 and APP-001 from the beta
audit remediation plan. It introduces a pure scheduler domain boundary for
contracts, custom constraints, target validation, and quality evaluation, while
keeping FastAPI, SQLAlchemy, Clerk, Celery, and OR-Tools in outer layers.

## Finding map

| Finding | Implemented boundary |
|---|---|
| SCHED-001 | Shared immutable constraint policy in Adaptive impact analysis, candidate pruning, preference scoring, runtime, and approval. |
| SCHED-002 | `baseline-v1` duration-aware quality policy, CP-SAT/evaluator parity, staged near and Adaptive objectives, incremental far-fill ranking and post-pass, final-target metrics, workload modes, comfort protection, rescue warning, and summary fields. |
| SCHED-003 | Four-rule discriminated write contract, tenant-aware semantic validation, legacy read diagnostics, and generation preflight. |
| SCHED-004 | Domain-owned result DTOs and shared pure envelope, hard-target, and lunch validation invoked independently by runtime and approval. |
| SCHED-005 | Feature-scoped SchoolConfig sections, pure serializers, timer-safe transient messages, sequential frontend verification, and ten-run stability gate. |
| SCHED-006 | Named `use_alter` cycle break plus warning-as-error metadata coverage and isolated migration gates. |
| SCHED-007 | Nonempty custom-rule Adaptive tests and a mandatory real-Clerk/worker Complete-to-Adaptive browser journey. |
| APP-001 | Exact authorized parties, explicit activate-to-fresh-token-to-bootstrap orchestration, idempotent founder bootstrap, retry persistence, and guard state machine. |

## Local verification

- Backend pure unit suite: 152 passed.
- Pure constraint and target-validation modules: 100% statement and branch coverage.
- Selected PostgreSQL scheduler, solver, runtime, and bootstrap suite: 101 passed.
- Frontend verification: ESLint, Knip, 164 tests with coverage, and production build passed.
- SchoolConfig stability: 10 consecutive runs passed.
- Alembic downgrade to base, upgrade to head, and metadata check passed.
- ORM metadata create/drop cycle passed against isolated PostgreSQL.
- Persisted scheduler constraint audit passed on the isolated test database.
- Playwright discovery lists 20 real-stack tests, including the fresh-founder Complete-to-Adaptive journey.

## Release gates

The repository gates now include backend Ruff, dependency/database audits,
PostgreSQL branch coverage with the 70% floor, Alembic downgrade/upgrade/check,
persisted constraint audit, sequential frontend lint-to-Knip-to-coverage-to-build,
SchoolConfig stability, and the real-stack Playwright profile.

Before deployment, drain old scheduler jobs, verify the exact visible origin in
CORS and Clerk authorized parties, require zero incompatible stored constraints,
and build fresh backend, worker, and frontend images. A release remains blocked
until the complete backend coverage job and credentialed real-stack Playwright
profile pass in CI.
