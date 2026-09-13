# LOC Reduction and Architecture Reset

Implementation details: [LOC Reduction Implementation WBS](LOC_REDUCTION_WBS.md).

## Decision

Reduce code by deleting duplication and obsolete paths while preserving every supported product capability.

Keep the tutorial interactive. Do not replace it with a read-only product.

Use existing architectural seams before adding new abstractions.

Treat LOC as evidence. Do not trade behavior, safety, readability, or tests for a numerical target.

## Baseline

This baseline uses commit `4290ad13d7ebbbdd54ea49605a85959198bb89e1` from 2026-09-12.

Count nonblank Python, JavaScript, JSX, and CSS lines.

Exclude documentation, migrations, lockfiles, generated artifacts, build outputs, and dependencies.

| Scope | Files | Nonblank lines |
| :--- | ---: | ---: |
| Backend application | 128 | 32,790 |
| Backend services | 63 | 22,854 |
| Frontend production | 198 | 18,700 |
| Backend tests | 107 | 19,219 |
| Frontend unit tests | 64 | 5,772 |
| Frontend E2E tests | 31 | 3,217 |

The measured production baseline is 51,490 lines.

The measured test baseline is 28,208 lines.

Current evidence shows these concentration points:

- Tutorial production code contains 1,841 nonblank lines.
- `index.css` contains 1,384 nonblank lines.
- Backend services contain 78 functions longer than 80 physical lines.
- The backend constructs `HTTPException` at 116 sites.
- Services return uppercase string values at 51 sites.
- Eleven uppercase returns represent scheduler categories, not errors.
- Static reference checks found 597 physical lines in zero-reference service candidates.
- Only one of six tenant-scoped feature data modules uses the existing organization query helpers.

### Initial deletion candidates

Treat this list as an audit queue, not an automatic deletion list.

| Area | Candidate functions | Physical lines |
| :--- | :--- | ---: |
| Availability | `is_impossible`, `has_possible_slot` | 51 |
| Classes | `get_class_details`, `get_classes_by_org_sync` | 23 |
| Clerk sync | `parse_role`, `sync_organization_from_clerk_api` | 32 |
| Member reconciliation | `reconcile_first_login`, `confirm_provider_membership` | 79 |
| Rooms | `get_rooms_by_org_sync` | 2 |
| Schedule sync reads | Nine organization-scoped sync wrappers | 83 |
| Scheduler constraints | `violation_for_block` | 3 |
| Scheduler planning | Five unused planning helpers | 112 |
| Subjects | `get_subjects_by_org_sync` | 2 |
| Teachers | Five unused read, replacement, sync, and invite helpers | 125 |
| Timeslots | `update_timeslot`, `delete_timeslot` | 85 |
| Total | 32 candidates | 597 |

Check Celery registration and indirect dispatch before deleting scheduler or worker functions.

## Target

Forecast a net reduction of 4,000 to 7,400 nonblank lines.

Target 2,950 to 5,000 production lines and 1,050 to 2,400 test lines.

Treat 7,400 lines as a stretch result. Stop earlier when further deletion risks quality.

Do not count moved code, generated code, formatting changes, or documentation changes.

Report production and test changes separately. Never offset production growth with deleted tests.

## Architecture Rules

Apply this dependency direction for changed code:

`HTTP or UI -> application workflow -> domain policy -> infrastructure adapter`

Use each layer for one purpose:

- Endpoints validate transport input, enforce actor access, and return application results.
- Application services own transactions, tenant scope, locks, auditing, and orchestration.
- Domain policies calculate transitions and invariants without FastAPI, SQLAlchemy, Clerk, or React.
- Infrastructure adapters isolate Clerk, Celery, database execution details, and browser storage.
- Frontend feature hooks remain the public data interface for pages.

Do not add generic repositories around SQLAlchemy.

Keep `organization_id` explicit in every tenant-owned query.

Use PostgreSQL RLS as defense in depth, not as a replacement for query scope.

Do not add universal CRUD pages, state-machine frameworks, or scheduler kernels.

Extract shared code only after three equivalent call sites remain.

## Protected Contracts

Preserve these contracts throughout the program:

- Preserve every current successful API response shape.
- Preserve the standard error envelope and public error codes.
- Preserve Clerk role and organization authorization.
- Preserve tenant filters and installed tenant session context.
- Preserve append-only progress entries and idempotency keys.
- Preserve occurrence versions, revisions, cancellation, and compensation behavior.
- Preserve member operation durability, compensation, and `support_required` states.
- Preserve scheduler fingerprints byte-for-byte.
- Preserve deterministic candidate ordering and selected golden blocks.
- Preserve the frozen horizon and protected historical blocks.
- Preserve draft replacement, validation, approval, and recovery reconciliation.
- Preserve all 13 tutorial steps, local-only execution, progress, review, and permitted interactions.
- Preserve accessibility, responsive layouts, and cache invalidation behavior.

## Delivery Sequence

### Phase 0: Freeze behavior and measurement

Add a dependency-free LOC report under `scripts/`.

Make the report classify production, unit tests, integration tests, and E2E tests.

Save the current OpenAPI document as a temporary comparison artifact.

Record every frontend and backend caller of each deletion candidate.

Run existing tests before adding characterization tests.

Add characterization tests only where a protected contract lacks coverage.

Capture tutorial screenshots for all 13 steps at desktop and mobile widths.

Capture scheduler fingerprints, selected blocks, result categories, and approval results.

Exit criteria:

- The baseline report is reproducible on Windows and CI.
- Every protected contract has an existing test or a new characterization test.
- The full baseline suite is green.

### Phase 1: Delete certain waste

Remove the flat class mutation routes.

Keep flat class read routes and class-subject operations.

Keep course-nested class creation, update, and deletion as the only class write API.

Remove `POST /api/v1/timeslots/generate` and `create_bulk_timeslots`.

Keep atomic grid regeneration through `POST /api/v1/school/grid-settings/regenerate`.

Audit the 32 zero-reference service candidates.

Delete a candidate only after checking imports, task registration, string dispatch, and external API exposure.

Delete schemas, tests, hooks, branches, and documentation that serve only removed operations.

Do not introduce helpers during this phase.

Expected reduction: 850 to 1,300 total lines.

Exit criteria:

- Removed methods are absent from OpenAPI.
- Requests use the framework's correct rejection status, usually `405` when reads remain.
- Nested writes preserve authorization, tenant isolation, response shapes, and scheduler change records.
- Atomic grid regeneration preserves rollback behavior.

### Phase 2: Collapse tutorial duplication without removing interactions

Keep the production pages as tutorial screens.

Replace path-matching branches with a declarative route table.

Normalize tutorial entities once when creating the scenario.

Store relationships by stable IDs instead of repeated name searches.

Use small route handlers for the permitted mutations.

Keep step authorization data in one source.

Keep review mode read-only and keep current-step mutations available.

Reject undeclared routes and prevent all external requests.

Delete duplicated snapshots, lookup helpers, mutation branches, and overlapping tests.

Expected reduction: 500 to 900 total lines.

Exit criteria:

- All 13 steps render and advance correctly.
- Every permitted interaction changes the local scenario correctly.
- Review mode cannot mutate state.
- The tutorial makes no network request.
- Visual and accessibility baselines remain stable.

### Phase 3: Consolidate frontend data and styles

Adopt `orgQueryKey` and `invalidateOrgQueries` across existing feature hooks.

Keep domain exports such as `useOccurrences` and `useUpdateCourseClass`.

Centralize invalidation groups only where identical groups repeat.

Add no generic query hook during the first pass.

Reassess remaining boilerplate after all tenant-scoped data modules use existing helpers.

Keep rooms and subjects direct. Add no generic CRUD page shell yet.

Extract a shared view only when three consumers have equivalent behavior.

Audit CSS by route group using browser coverage and visual baselines.

Move tokens and global resets out of feature rules.

Delete unused selectors and merge equivalent component states.

Expected reduction: 550 to 1,050 total lines.

Exit criteria:

- Every mutation invalidates the same resources as before.
- Organization changes cannot reuse another tenant's cache.
- Knip, ESLint, Vitest, build, Playwright, and accessibility checks pass.
- Supported viewport screenshots show no unintended change.

### Phase 4: Establish one backend error path

Use the existing `AppError` and global handler.

Remove uppercase error sentinels and router translation ladders together.

Keep scheduler result categories as typed domain values.

Remove `DomainError` and `OccurrenceServiceError` after migrating their callers.

Keep `HTTPException` only in transport and authentication boundaries.

Do not expose provider text or exception text to clients.

Migrate one bounded context per change:

1. Classes, courses, rooms, subjects, and timeslots.
2. Timesheets and lesson logs.
3. Occurrences.
4. Scheduler endpoints.

Add error constructors only after three equivalent `AppError` constructions remain.

Expected reduction: 550 to 1,000 total lines.

Exit criteria:

- Every failure retains its HTTP status and public code.
- Every error retains the standard envelope and request reference.
- Routers contain no business outcome translation ladders.
- Services return values or raise typed application errors.

### Phase 5: Simplify member and occurrence workflows

Refactor member operations through the existing `MemberAccessSagaCoordinator`.

Process create, update, remove, restore, resend, and retry separately.

Consolidate durable operation creation, provider effects, local writes, compensation, and terminal recording.

Do not add `AccessCommand`, `ProviderEffect`, or another workflow class initially.

Extract types only when they remove repeated branches.

For occurrences, extract one pure `plan_transition` policy.

Return one immutable plan containing state, ledger deltas, block changes, and audit facts.

Keep locks, version checks, persistence, revisions, and audits in one application workflow.

Hide `run_sync` inside the occurrence application service.

Expected reduction: 750 to 1,350 total lines.

Exit criteria:

- Member provider and local failure combinations retain durable terminal states.
- Failed compensation still sets `support_required` correctly.
- Every occurrence transition retains optimistic version checks.
- Ledger totals, revision history, operational blocks, and audit events remain identical.
- Concurrent decisions cannot apply a transition twice.

### Phase 6: Simplify the scheduler last

Freeze scheduler golden behavior before changing the engine.

Simplify adaptive repair before complete generation.

Reuse existing candidates, constraint policies, quality policies, deadlines, and cancellation signals.

Remove duplicated indexing, metrics, blocker construction, and result summarization.

Derive persisted metrics from selected blocks in one authoritative location.

Keep canonical snapshot serialization unchanged.

Do not rewrite the 442-line snapshot loader merely to split the file.

Do not create a shared solver kernel initially.

Consider a kernel only after three identical constraint implementations remain.

Expected reduction: 650 to 1,200 total lines.

Exit criteria:

- Fingerprints and canonical JSON remain byte-identical.
- Golden selected blocks and deterministic ordering remain identical.
- Cancellation, timeout, and incumbent handling remain correct.
- Frozen blocks and recovery links remain correct.
- Draft approval remains atomic and rejects stale inputs.
- Quality metrics do not regress on the fixed benchmark set.

### Phase 7: Consolidate tests and install permanent controls

Consolidate tests continuously after each production slice.

Use parameterized matrices for roles, tenants, errors, transitions, and provider failures.

Use scenario builders for organization, curriculum, scheduler, and member setup.

Delete duplicate setup and duplicate assertions, not behavioral scenarios.

Add architecture checks for these regressions:

- New unreferenced production exports.
- New business string sentinels.
- New router business translation ladders.
- New cross-tenant queries without explicit organization scope.
- New feature query keys outside the shared helper.
- New tutorial external requests.
- New duplicate solver result derivation.

Add a PR LOC report without arbitrary file-size limits.

Require refactors and bug fixes to remain production-LOC neutral or negative.

Allow feature work to add justified production LOC.

Require a short exception when non-feature work adds production LOC.

Expected reduction: 250 to 600 additional test lines.

## TDD Rule

Use this cycle for every behavioral slice:

1. Identify one public outcome or invariant.
2. Add one failing characterization test only when coverage is missing.
3. Make the smallest production change.
4. Run the focused unit or component test.
5. Run the relevant integration or E2E test.
6. Delete obsolete production code and duplicate tests.
7. Run the complete gate before merge.

Test behavior, state transitions, persistence effects, and public contracts.

Do not test the proposed class structure.

## Commit and Rollout Policy

Deliver small, independently green commits.

Keep deletion, behavior preservation, and abstraction changes in separate commits.

Deploy API route removals and frontend caller removals together.

Use feature flags only for risky workflow replacements, not for dead-code deletion.

Monitor API error codes, member support operations, ledger reconciliation, scheduler outcomes, and generation quality.

Rollback a phase when any protected invariant changes unexpectedly.

## Verification Gates

Run these gates before every phase merge:

- Run `node scripts/test.mjs fast --scope all`.
- Run `node scripts/test.mjs integration`.
- Run the relevant Playwright projects.
- Run `npm run audit:production` and `npm run verify` in `frontend/`.
- Run Ruff format and lint checks in `backend/`.
- Run `alembic check` with the migrator role.
- Run `python -m scripts.audit_triggers`.
- Run `python -m scripts.audit_database_integrity`.
- Run the root runner tests.
- Run the LOC report and compare production and test deltas separately.

Use only databases whose names contain `test` or `ci`.

## Explicit Rejections

Do not make the tutorial read-only.

Do not promise an 8,000 to 12,000 line reduction without removing product scope.

Do not create another member workflow beside the existing coordinator.

Do not create another scheduler change recorder beside `SchedulerStateService.record_change`.

Do not create generic query hooks before adopting existing query-key helpers.

Do not create generic CRUD repositories or pages from two examples.

Do not create a shared scheduler kernel before duplication remains proven.

Do not split `models.py` or `schemas.py` solely to improve line counts.

Do not use file-size or function-size limits as architecture substitutes.

Do not delete tests to manufacture a reduction.

## Source Map

- [System architecture](../01_system_architecture/SYSTEM_ARCHITECTURE.md)
- [Professional education](../02_domain_model/PROFESSIONAL_EDUCATION.md)
- [Scheduler architecture](../03_scheduler_engine/SCHEDULER_ARCHITECTURE.md)
- [Scheduler behavior](../03_scheduler_engine/SCHEDULER_BEHAVIOR.md)
- [Occurrences and substitutions](../04_operational_features/OCCURRENCES_AND_SUBSTITUTIONS.md)
- [Timesheets and progress](../04_operational_features/TIMESHEETS_AND_PROGRESS.md)
- [Backend architecture](../05_backend_api/BACKEND_ARCHITECTURE.md)
- [Errors and transactions](../05_backend_api/ERRORS_AND_TRANSACTIONS.md)
- [Frontend architecture](../06_frontend_ux/FRONTEND_ARCHITECTURE.md)
- [Testing and CI](TESTING_AND_CI.md)
