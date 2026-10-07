# Security and Quality Index

This section documents tenant isolation mechanisms, security controls, testing frameworks, and CI/CD pipelines.

## Documents

- [SECURITY_AND_TENANT_ISOLATION.md](SECURITY_AND_TENANT_ISOLATION.md): Clerk authentication, forced PostgreSQL RLS, CORS, and security headers.
- [TESTING_AND_CI.md](TESTING_AND_CI.md): Pytest, Vitest, Playwright E2E testing, and GitHub Actions workflows.
- [REAL_BROWSER_TESTING_PLAN.md](REAL_BROWSER_TESTING_PLAN.md): Production-browser acceptance requirements, reviewed against main on 7 October 2026.
- [REAL_BROWSER_TESTING_WBS.md](REAL_BROWSER_TESTING_WBS.md): Review findings, baseline, dependencies, and coverage for the four implementation plans.
- [REAL_BROWSER_TESTING_WBS_PART_1_FOUNDATION.md](REAL_BROWSER_TESTING_WBS_PART_1_FOUNDATION.md): Baseline, complete data, Gmail, and protected evidence.
- [REAL_BROWSER_TESTING_WBS_PART_2_SCHOOL_AND_SCHEDULING.md](REAL_BROWSER_TESTING_WBS_PART_2_SCHOOL_AND_SCHEDULING.md): Deployment revisions, real accounts, school import, and generation.
- [REAL_BROWSER_TESTING_WBS_PART_3_REAL_JOURNEYS.md](REAL_BROWSER_TESTING_WBS_PART_3_REAL_JOURNEYS.md): Real operation, decisions, history, isolation, and remaining journeys.
- [REAL_BROWSER_TESTING_WBS_PART_4_CLEANUP_AND_CI.md](REAL_BROWSER_TESTING_WBS_PART_4_CLEANUP_AND_CI.md): Essential coverage, scoped cleanup, CI, recovery, and final verification.
- [REAL_BROWSER_TESTING_IMPLEMENTATION.md](REAL_BROWSER_TESTING_IMPLEMENTATION.md): Observed implementation evidence and remaining external dependencies.
- [loc-baseline.json](loc-baseline.json): Measured line-of-code baseline consumed by `scripts/loc-report.mjs`.
