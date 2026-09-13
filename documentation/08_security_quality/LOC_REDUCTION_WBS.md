# LOC Reduction Implementation WBS

## Purpose

Implement the [LOC reduction plan](LOC_REDUCTION_PLAN.md) without removing supported behavior.

This WBS defines the work order, exact code areas, test sequence, and acceptance gates.

## Required Outcome

Reduce 4,000 to 7,400 measured lines when every protected contract remains green.

Keep all current product capabilities, including the interactive tutorial.

Leave simpler dependency direction and fewer ways to implement the same operation.

Reserve future production LOC growth for real features, not parallel infrastructure.

## Ponytail Rule

Apply this decision ladder before every extraction:

1. Delete the need when the behavior is obsolete.
2. Reuse an existing helper or service when it already owns the behavior.
3. Use Python, JavaScript, CSS, PostgreSQL, or React platform features.
4. Use an installed dependency only when it already solves the exact problem.
5. Write the smallest local helper only after the earlier choices fail.

Add no dependency, migration, generic repository, universal CRUD shell, or solver framework.

Keep a helper only when the completed diff removes more code than it adds.

`ponytail:` Add broader abstractions only after three equivalent implementations remain.

## TDD Execution Contract

Use this sequence for every leaf package:

1. Run the narrow existing test selection.
2. Add one failing behavior test only when coverage is missing.
3. Confirm the new test fails for the expected reason.
4. Make the smallest production change.
5. Run the narrow test until it passes.
6. Delete the superseded production path.
7. Consolidate duplicate tests without removing scenarios.
8. Run the package integration gate.
9. Record production and test LOC deltas.
10. Commit only the green package.

Do not write tests for proposed class names or file layouts.

Test public responses, persisted state, domain invariants, and observable side effects.

## Architecture Contract

Use this dependency direction in changed code:

`endpoint or page -> application workflow -> pure policy -> adapter`

Apply these boundaries:

- Keep FastAPI and HTTP status knowledge in endpoints and global handlers.
- Raise `AppError` from request-oriented application services.
- Keep SQLAlchemy sessions, locks, tenant scope, and auditing in application services.
- Keep pure calculations independent from sessions, FastAPI, Clerk, Celery, and React.
- Keep Clerk calls inside the existing access service and saga coordinator.
- Keep scheduler dispatch behind the existing dispatcher protocol.
- Keep pages dependent on domain-named feature hooks.
- Keep query keys organization-scoped through the existing helpers.

Do not move code only to create architectural-looking folders.

## Work Package Dependencies

| Package | Depends on | Release boundary |
| :--- | :--- | :--- |
| 0. Baseline and controls | None | Tooling only |
| 1. Certain deletions | 0 | API and callers together |
| 2. Tutorial reduction | 0 | Frontend only |
| 3. Frontend data and CSS | 0, 2 | Frontend only |
| 4. Backend error convergence | 0, 1 | One bounded context per merge |
| 5. Member workflow | 4 | Member context only |
| 6. Occurrence workflow | 4 | Operations context only |
| 7. Scheduler reduction | 0, 4, 6 | Scheduler only |
| 8. Test consolidation and policy | 1-7 | Repository-wide |
| 9. Release and rebaseline | 8 | Atomic release |

Packages 2 and 4 can proceed independently after package 0.

Do not overlap packages that edit the same file.

## 0. Baseline and Controls

### 0.1 Prepare a valid test environment

Files changed: none.

- [ ] Create the backend virtual environment and install locked dependencies.
- [ ] Install frontend dependencies with the lockfile.
- [ ] Run the environment doctor.
- [ ] Confirm every database name contains `test` or `ci`.
- [ ] Record the starting commit and dirty paths.

Commands:

```powershell
node scripts/test.mjs setup --scope all
node scripts/test.mjs doctor --profile all
git status --short --branch
git rev-parse HEAD
```

Stop when the baseline fails for an unexplained reason.

### 0.2 Add one LOC reporter

Files:

- `scripts/loc-report.mjs`
- `scripts/test.test.mjs`
- `documentation/08_security_quality/loc-baseline.json`
- `.github/workflows/ci.yml`

Implementation:

- [ ] Enumerate tracked and untracked non-ignored files with `git ls-files`.
- [ ] Count nonblank lines with Node standard-library functions.
- [ ] Classify backend application, frontend production, backend tests, frontend tests, and E2E tests.
- [ ] Exclude migrations, documentation, lockfiles, generated files, dependencies, and build outputs.
- [ ] Print current counts and deltas from `loc-baseline.json`.
- [ ] Support `--write-baseline` for deliberate baseline updates.
- [ ] Add reporter unit cases to the existing root runner test file.
- [ ] Run the report in one existing CI job.
- [ ] Keep the CI report informational during the reduction program.

Do not add a LOC package or a second test runner.

Acceptance:

- Windows and CI return identical counts for the same revision.
- Production deletions cannot be hidden by test deletions.
- An untracked source file appears in the local report.
- Documentation and migration changes do not change measured totals.

### 0.3 Freeze API and behavioral contracts

Files:

- `.test-artifacts/loc-reset/openapi-before.json`
- Existing backend and frontend tests only when coverage is missing.

Implementation:

- [ ] Export the current OpenAPI document into the ignored artifact directory.
- [ ] Record route methods for classes, timeslots, courses, and school settings.
- [ ] Run all current unit, integration, contract, frontend, and E2E suites.
- [ ] Capture tutorial pages at 375, 768, and 1440 pixels.
- [ ] Record scheduler fingerprints and golden selected blocks.
- [ ] Record global and critical-module coverage.

Do not commit the OpenAPI or screenshot artifacts.

Gate:

```powershell
node scripts/test.mjs all --scope all
node scripts/test.mjs e2e
node scripts/loc-report.mjs
```

Definition of done:

- The complete baseline is green.
- The LOC report reproduces the approved baseline.
- Every later package can compare against saved evidence.

## 1. Certain Deletions

### 1.1 Remove flat class writes

Production files:

- `backend/app/api/v1/endpoints/classes.py`
- `backend/app/services/class_service.py`
- `backend/app/schemas.py`
- `documentation/05_backend_api/API_REFERENCE.md`

Test and fixture files:

- `backend/tests/integration/committed/test_classes_crud.py`
- `backend/tests/unit/test_class_service_validation.py`
- `backend/tests/factories.py`
- `backend/tests/unit/test_backend_foundation_contracts.py`

Keep these operations:

- `GET /api/v1/classes/`
- `GET /api/v1/classes/{class_id}`
- Class curriculum, progress, subject, and eligible-teacher operations.
- All course-nested class writes.

Delete these operations:

- `POST /api/v1/classes/`
- `PATCH /api/v1/classes/{class_id}`
- `DELETE /api/v1/classes/{class_id}`

TDD sequence:

- [ ] Add a route-contract test proving flat class paths expose only supported methods.
- [ ] Change test creation helpers to `POST /courses/{course_id}/classes`.
- [ ] Change update tests to `PATCH /courses/{course_id}/classes/{class_id}`.
- [ ] Change delete tests to `DELETE /courses/{course_id}/classes/{class_id}`.
- [ ] Preserve invalid year, missing course, tenant, role, and scheduler-change assertions.
- [ ] Remove the three flat endpoint functions.
- [ ] Remove `create_class`, `update_class`, and `delete_class` from `class_service.py`.
- [ ] Remove `ClassCreate` and `ClassUpdate` only after `rg` finds no caller.
- [ ] Keep `ClassCreateInCourse` and `ClassUpdateInCourse`.
- [ ] Remove duplicate mutation cases after nested equivalents pass.
- [ ] Update the API reference.

Required checks:

```powershell
node scripts/test.mjs fast --scope backend -- -k 'class_service_validation or backend_foundation_contracts'
node scripts/test.mjs integration -- -k 'classes_crud or courses_endpoints or tenant_isolation'
```

Acceptance:

- Flat reads retain their current response shapes.
- Flat writes return `405` when the path still supports `GET`.
- Nested writes preserve organization scope and audit facts.
- No frontend production caller changes because it already uses nested writes.

### 1.2 Remove legacy timeslot generation

Production files:

- `backend/app/api/v1/endpoints/timeslots.py`
- `backend/app/services/timeslot_service.py`
- `documentation/05_backend_api/API_REFERENCE.md`

Test files:

- `backend/tests/integration/committed/test_timeslots_crud.py`
- `backend/tests/integration/committed/test_org_settings_endpoints.py`
- `backend/tests/integration/committed/test_teacher_role_regression.py`
- `backend/tests/integration/committed/test_tenant_isolation_complete.py`
- `backend/tests/unit/test_backend_foundation_contracts.py`

Implementation:

- [ ] Add a route-contract assertion that `/timeslots/generate` is absent.
- [ ] Prove grid regeneration covers valid, invalid, role, tenant, and rollback scenarios.
- [ ] Move missing scenarios into `test_org_settings_endpoints.py`.
- [ ] Remove tests that exist only for the legacy wrapper.
- [ ] Remove `generate_timeslots` from the endpoint module.
- [ ] Remove `create_bulk_timeslots` from the service.
- [ ] Keep `TimeslotBulkCreate`; Foundation and grid regeneration still use it.
- [ ] Keep the lower-level validation and regeneration functions used by school settings.
- [ ] Update the API reference.

Required checks:

```powershell
node scripts/test.mjs integration -- -k 'timeslot or org_settings or teacher_role or tenant_isolation'
```

Acceptance:

- `/school/grid-settings/regenerate` remains atomic.
- Invalid grids leave the previous grid unchanged.
- Teacher access remains forbidden.
- Cross-organization data remains invisible.

### 1.3 Delete zero-reference services

Files: the service modules listed in the parent plan.

Audit each candidate with this exact order:

1. Search Python, frontend, tests, scripts, and documentation with `rg -w`.
2. Search Celery task names and string-based registries.
3. Search FastAPI route functions and dependency factories.
4. Search `__all__`, dynamic imports, and reflection.
5. Delete only when the definition is the sole runtime reference.
6. Run the owning package tests immediately.

Deletion batches:

- [ ] Delete unused catalog and schedule sync wrappers.
- [ ] Delete unused availability and scheduler-planning helpers.
- [ ] Delete unused teacher read, replacement, sync, and invite helpers.
- [ ] Delete unused Clerk and member-reconciliation helpers.
- [ ] Delete unused timeslot update and delete helpers.

Keep batches separate so one bad candidate has a small rollback.

Acceptance:

- Ruff, imports, worker registration, backend unit tests, and integration collection pass.
- The production dependency graph has no new cycle.
- The batch removes more code than its tests add.

## 2. Tutorial Reduction

### 2.1 Lock the tutorial contract

Production files: none initially.

Test files:

- `frontend/src/test/tutorialEngine.test.js`
- `frontend/src/test/tutorialApiAdapter.test.js`
- `frontend/src/test/TutorialWorkspace.test.jsx`
- `frontend/e2e/tutorial/tutorial-local.spec.js`
- `frontend/e2e/tutorial/tutorial-network-boundary.spec.js`
- `frontend/e2e/foundation/tutorial-13steps-navigation.spec.js`

Add only missing assertions for:

- [ ] Every declared step renders its production page.
- [ ] Every permitted action changes only local scenario state.
- [ ] Every forbidden action returns the current tutorial error envelope.
- [ ] Review mode rejects every mutation.
- [ ] Unknown routes and methods fail locally.
- [ ] No tutorial request reaches the network.
- [ ] Progress, skip, resume, repeat, and review remain stable.

### 2.2 Normalize the scenario once

Production files:

- `frontend/src/features/tutorial/tutorialScenario.js`
- `frontend/src/features/tutorial/tutorialApiAdapter.js`

Implementation:

- [ ] Keep `createTutorialScenario` as the only scenario constructor.
- [ ] Build API IDs and relationship indexes once in `createTutorialApiSnapshot`.
- [ ] Index classes, courses, subjects, teachers, rooms, blocks, and timeslots by stable ID.
- [ ] Replace repeated name-based `.find()` calls with index lookups.
- [ ] Keep the returned API shapes unchanged.
- [ ] Delete `numericId`, `internalId`, or lookup helpers only when indexes replace every caller.

Do not add a client database, schema library, or normalized-state dependency.

### 2.3 Replace adapter branching with local route data

Production file: `frontend/src/features/tutorial/tutorialApiAdapter.js`.

Implementation:

- [ ] Keep `createTutorialApiAdapter` and the Axios adapter contract.
- [ ] Keep one dispatcher over ordered route entries.
- [ ] Store each entry's method, path matcher, required action, and handler.
- [ ] Reuse the existing `read`, `write`, and `fail` behavior.
- [ ] Keep complex schedule and occurrence projections as named local functions.
- [ ] Keep exact routes as string entries and parameter routes as regular expressions.
- [ ] Stop at the first route-table form that produces a smaller file.
- [ ] Delete the old conditional ladder only after route-parity tests pass.

Do not create route classes, middleware, controllers, or another adapter file.

### 2.4 Consolidate tutorial state changes

Production file: `frontend/src/features/tutorial/tutorialScenario.js`.

- [ ] Keep current small action functions.
- [ ] Replace the action switch with a handler map only when it reduces net lines.
- [ ] Keep `ensureAction` as the single permission check.
- [ ] Keep immutable updates and current error codes.
- [ ] Delete duplicated setup between scenario and adapter.
- [ ] Parameterize route and action tests after all behavior passes.

Gate:

```powershell
Set-Location frontend
npm test -- tutorialEngine.test.js tutorialApiAdapter.test.js TutorialWorkspace.test.jsx
npx playwright test e2e/tutorial e2e/foundation/tutorial-13steps-navigation.spec.js
npm run verify
```

Acceptance:

- All 13 steps retain the same visible behavior.
- Review mode remains read-only.
- Current-step interactions remain writable.
- Network-boundary tests observe zero external tutorial requests.
- Supported screenshots show no unintended change.

## 3. Frontend Data and CSS

### 3.1 Adopt existing tenant query keys

Production files:

- `frontend/src/features/catalog/data.js`
- `frontend/src/features/legal/data.js`
- `frontend/src/features/members/data.js`
- `frontend/src/features/operations/data.js`
- `frontend/src/features/scheduling/data.js`
- `frontend/src/features/schoolConfig/data.js`
- `frontend/src/features/queryKeys.js`

Test file: `frontend/src/test/featureDataHooks.test.jsx`.

Implementation order:

1. Catalog.
2. Members.
3. Operations.
4. Scheduling.
5. Legal.
6. School settings verification only.

For each module:

- [ ] Replace literal organization roots with `orgQueryKey`.
- [ ] Replace repeated invalidation calls with `invalidateOrgQueries`.
- [ ] Keep scoped suffixes for IDs, dates, filters, and paging.
- [ ] Preserve every existing `enabled` condition.
- [ ] Preserve authentication token acquisition for `useCurrentMember`.
- [ ] Preserve polling rules for scheduler jobs.
- [ ] Preserve mutation completion timing when callers await invalidation.
- [ ] Keep public hook names unchanged.
- [ ] Run `featureDataHooks.test.jsx` before the next module.

Do not modify `contact/data.js`; it is public and not organization-scoped.

Do not turn `readiness/data.js` into a hook; it is already a small helper.

Do not add `useOrgQuery` or `useOrgMutation` during this pass.

After all modules pass, count remaining repeated setup.

Add one tiny helper only when three unchanged blocks remain and net LOC falls.

### 3.2 Delete unused CSS by measured route group

Production files:

- `frontend/src/index.css`
- `frontend/src/styles/*.css`
- `frontend/src/features/marketing/styles/*.css`
- `frontend/src/styles/tutorial.css`

Evidence files:

- `frontend/scripts/capture-css-coverage.mjs`
- `documentation/06_frontend_ux/visual-baselines/css-coverage.json`
- Existing visual baseline images.

Process one route group at a time:

1. Marketing and authentication.
2. Application shell and dashboard.
3. Catalog and forms.
4. Scheduling and operations.
5. Tutorial.

For each group:

- [ ] Capture CSS coverage at 375, 768, and 1440 pixels.
- [ ] Search JSX, JavaScript, and generated class names before deletion.
- [ ] Remove selectors unused in coverage and source search.
- [ ] Merge selectors only when declarations and state semantics match.
- [ ] Keep focus, hover, disabled, error, loading, and reduced-motion states.
- [ ] Compare screenshots and run accessibility checks.
- [ ] Revert the group when a supported view changes unexpectedly.

Do not split stylesheets merely to reduce file size.

Gate:

```powershell
Set-Location frontend
npm test -- featureDataHooks.test.jsx
npm run lint
npm run lint:dead-code
npm run test:coverage
npm run build
npm run verify
```

## 4. Backend Error Convergence

### 4.1 Freeze the public error matrix

Test files:

- `backend/tests/unit/test_error_handlers.py`
- `backend/tests/integration/committed/test_classes_crud.py`
- `backend/tests/integration/committed/test_courses_endpoints.py`
- `backend/tests/integration/committed/test_rooms_crud.py`
- `backend/tests/integration/committed/test_subjects_crud.py`
- `backend/tests/integration/committed/test_timesheets.py`

- [ ] Parameterize status, code, message source, reference, fields, and context checks.
- [ ] Assert provider exception text never crosses the boundary.
- [ ] Preserve `X-Request-ID` equality with `detail.reference`.
- [ ] Keep authentication and webhook `HTTPException` behavior unchanged.

### 4.2 Migrate catalog services

Production files:

- `backend/app/services/class_service.py`
- `backend/app/services/course_service.py`
- `backend/app/services/room_service.py`
- `backend/app/services/subject_service.py`
- `backend/app/services/timeslot_service.py`
- Their endpoint modules.

Process one service per commit:

- [ ] Replace each uppercase error return with `raise AppError(...)`.
- [ ] Give each failure a stable public code from the existing catalog.
- [ ] Put diagnostic detail in `AppError.detail`.
- [ ] Remove the matching endpoint comparison and `HTTPException` branch.
- [ ] Return the unchanged success object or success message.
- [ ] Add no error constructor until three identical constructions remain.

Keep scheduler disruption categories unchanged because they are domain values.

### 4.3 Migrate lesson logs and timesheets

Production files:

- `backend/app/services/lesson_log_service.py`
- `backend/app/services/timesheet_service.py`
- `backend/app/api/v1/endpoints/timesheets.py`
- `backend/app/core/exceptions.py`
- `backend/app/main.py`

- [ ] Replace `DomainError`, `NotFoundError`, and `ConflictError` with `AppError`.
- [ ] Preserve not-found, validation, and conflict status mappings.
- [ ] Preserve timesheet state and lesson-log accounting.
- [ ] Remove the old domain handler only after `rg` finds no remaining caller.
- [ ] Delete the old exception subclasses after their final caller moves.

### 4.4 Migrate occurrence transport errors

Production files:

- `backend/app/services/occurrence_service.py`
- `backend/app/api/v1/endpoints/occurrences.py`

- [ ] Replace `OccurrenceServiceError(status_code, detail)` with `AppError`.
- [ ] Preserve every existing occurrence error code and status.
- [ ] Move failure-event recording into the application service.
- [ ] Remove repeated endpoint `run_sync` closures when package 6 provides service entry points.
- [ ] Delete the exception class and endpoint translation blocks last.

### 4.5 Migrate scheduler endpoint errors

Production files:

- `backend/app/api/v1/endpoints/scheduler.py`
- Existing scheduler request, draft, lifecycle, job, and approval services.

- [ ] Keep internal scheduler exceptions where worker logic uses them.
- [ ] Convert them to `AppError` at existing public application methods.
- [ ] Remove endpoint exception ladders after public methods return one error contract.
- [ ] Preserve worker-facing typed exceptions and cancellation semantics.
- [ ] Add no scheduler facade.

### 4.6 Add narrow architecture guards

Test file: `backend/tests/unit/test_backend_foundation_contracts.py`.

- [ ] Reject uppercase error returns in migrated service modules with an AST check.
- [ ] Reject FastAPI imports from services.
- [ ] Allow documented scheduler category returns.
- [ ] Assert removed endpoint methods stay absent.
- [ ] Keep the guard scoped to proven violations.

Gate:

```powershell
node scripts/test.mjs fast --scope backend -- -k 'error or backend_foundation or class or timesheet or lesson'
node scripts/test.mjs integration -- -k 'classes or courses or rooms or subjects or timesheets or occurrence or scheduler'
```

Acceptance:

- Public error shapes remain byte-compatible except deliberate code corrections.
- Services contain no HTTP status logic.
- Endpoints contain no business sentinel translation.
- Authentication and webhook boundaries may still use `HTTPException`.

## 5. Member Workflow

### 5.1 Freeze provider and local failure behavior

Test files:

- `backend/tests/unit/test_member_saga_coordinator.py`
- `backend/tests/integration/committed/test_members_api.py`
- `backend/tests/contracts/test_preflight_service.py`

Create a parameterized matrix for:

- Provider success and local success.
- Provider failure before local mutation.
- Local failure after invitation creation.
- Local failure after membership creation.
- Local failure after role change.
- Compensation success.
- Compensation failure with `support_required`.
- Retry of failed and unresolved operations.
- Last-admin removal protection.
- Tenant and actor isolation.

Add only missing rows.

### 5.2 Simplify existing provider helpers

Production file: `backend/app/services/member_service.py`.

Process these helpers in order:

1. `_send_invitation`.
2. `_change_provider_role`.
3. `_revoke_provider_access`.

For each helper:

- [ ] Keep provider calls in `ClerkAccessService`.
- [ ] Keep durable state in `MemberAccessOperationService`.
- [ ] Return one existing result type or raise `AppError`.
- [ ] Remove repeated operation transitions from callers.
- [ ] Keep provider references and diagnostic categories.
- [ ] Preserve independent operation-ledger commits.

Do not introduce `AccessCommand` or `ProviderEffect`.

### 5.3 Simplify public member operations

Process one public function per commit:

1. `create_member`.
2. `update_member`.
3. `remove_member`.
4. `restore_member`.
5. `resend_invitation`.
6. `retry_sync`.

For each function:

- [ ] Keep validation before provider effects.
- [ ] Create one durable operation before the first provider mutation.
- [ ] Apply the provider effect once.
- [ ] Apply the local membership mutation once.
- [ ] Use `MemberAccessSagaCoordinator` for compensation.
- [ ] Record exactly one terminal operation state.
- [ ] Preserve scheduler change recording for teacher changes.
- [ ] Delete branches made unreachable by the consolidated path.
- [ ] Run the complete failure matrix before the next operation.

Extend `MemberAccessSagaCoordinator` only when three public operations repeat the same completion sequence.

Gate:

```powershell
node scripts/test.mjs fast --scope backend -- -k 'member_saga or member'
node scripts/test.mjs integration -- -k 'members_api or preflight or tenant_isolation'
```

Acceptance:

- Each request produces at most one provider mutation per intended effect.
- Each durable operation reaches one correct terminal state.
- Failed compensation remains visible to support.
- No cross-tenant operation can reuse a bound operation service.

## 6. Occurrence Workflow

### 6.1 Add missing backend characterization coverage

New test file: `backend/tests/integration/committed/test_occurrences.py`.

Reuse existing database factories and scheduler fixtures.

Cover these public outcomes before refactoring:

- [ ] Create or reuse an occurrence from an active block.
- [ ] Reject a missing or protected block.
- [ ] Decide `GIVEN`, `GAP`, and `SUBSTITUTED`.
- [ ] Reject invalid substitutes, subjects, rooms, availability, and conflicts.
- [ ] Reject stale versions.
- [ ] Cancel open and decided occurrences.
- [ ] Preserve completed substitute-log protection.
- [ ] Append exact completed and debt minute deltas.
- [ ] Apply each idempotency key once.
- [ ] Persist occurrence revisions and operational events.
- [ ] Enforce admin role and tenant isolation.

This package may add test LOC. Quality has priority over the test-reduction forecast.

### 6.2 Extract one pure transition plan

Production file: `backend/app/services/occurrence_service.py`.

Start locally in the existing module.

- [ ] Define one frozen transition result with only required fields.
- [ ] Implement `plan_transition(current_state, command)` without database access.
- [ ] Compute target status, ledger deltas, operational-block action, and audit facts.
- [ ] Keep substitute eligibility and database lookups outside the pure function.
- [ ] Table-test every legal and illegal transition.
- [ ] Delete `_validate_state_transition` and `_ledger_deltas_for_state` after parity passes.

Move the policy into another module only when a second production caller needs it.

### 6.3 Create async application entry points

Production file: `backend/app/services/occurrence_service.py`.

- [ ] Add async entry points matching the existing endpoint use cases.
- [ ] Keep synchronous SQLAlchemy helpers private.
- [ ] Run one `db.run_sync` call inside each application entry point.
- [ ] Keep failure and success event recording inside the same service boundary.
- [ ] Keep row locks and version checks inside the transaction.
- [ ] Keep the append-only ledger unchanged.
- [ ] Return existing schema-compatible objects.

Do not create repositories or a generic unit-of-work wrapper.

### 6.4 Collapse mutation execution

Production files:

- `backend/app/services/occurrence_service.py`
- `backend/app/api/v1/endpoints/occurrences.py`

- [ ] Make `update_occurrence_sync` load and lock once.
- [ ] Validate resource eligibility once.
- [ ] Generate one transition plan.
- [ ] Apply operational-block changes from that plan.
- [ ] Append ledger entries from that plan.
- [ ] Append one revision and one audit event.
- [ ] Touch the version once.
- [ ] Remove duplicate endpoint logging and translation.
- [ ] Convert endpoint functions into direct application-service calls.

Gate:

```powershell
node scripts/test.mjs fast --scope backend -- -k 'occurrence'
node scripts/test.mjs integration -- -k 'occurrence or debt or module_progress or scheduler_recovery'
node scripts/test.mjs e2e --project app
```

Acceptance:

- State, version, ledger, revision, block, and audit results match the baseline.
- Concurrent stale updates cannot apply twice.
- Revocation preserves immutable evidence.
- Recovery debt remains compatible with scheduler validation.

## 7. Scheduler Reduction

### 7.1 Protect current reliability work

Use the implemented [scheduler reliability WBS](../03_scheduler_engine/SCHEDULER_RELIABILITY_WBS.md) as the behavior contract.

Test files:

- `backend/tests/unit/test_scheduler_adaptive_engine.py`
- `backend/tests/unit/test_scheduler_near_optimizer.py`
- `backend/tests/unit/test_scheduler_far_fill.py`
- `backend/tests/unit/test_scheduler_properties.py`
- `backend/tests/unit/test_scheduler_job_13_regression.py`
- `backend/tests/integration/committed/test_scheduler_job_runtime.py`

- [ ] Record exact fingerprints, selected blocks, statuses, metrics, and blockers.
- [ ] Run deterministic tests twice before production edits.
- [ ] Keep the job 13 candidate-count guarantee.
- [ ] Keep the existing exhaustive oracle and metamorphic tests.

### 7.2 Remove duplicate result derivation

Production files:

- `backend/app/services/scheduler_adaptive_engine.py`
- `backend/app/services/scheduler_job_runtime.py`
- `backend/app/scheduler/domain/contracts.py`
- Existing scheduler quality and validation helpers.

Implementation:

- [ ] Trace every `summary` and `metrics` field to its API or persisted consumer.
- [ ] Mark fields as observed, validated, or unused.
- [ ] Delete unused fields and their tests.
- [ ] Choose one existing function as the source for each derived field.
- [ ] Keep engine-owned solve metrics in the engine.
- [ ] Keep persisted phase timing in the runtime.
- [ ] Keep independent runtime validation; do not trust engine claims.
- [ ] Remove duplicate calculations after equality tests pass.

Do not add `SolveRequest`, `SolveOutcome`, or another result hierarchy.

### 7.3 Simplify adaptive repair locally

Production file: `backend/app/services/scheduler_adaptive_engine.py`.

Process these methods separately:

1. `generate`.
2. `_solve_scope`.
3. `_build_tasks`.
4. `_build_placements`.
5. `_specs`.
6. `_result`.
7. `_combined_scopes`.

For each method:

- [ ] Identify exact repeated loops or result branches.
- [ ] Reuse existing candidate, constraint, quality, deadline, and cancellation helpers.
- [ ] Replace repeated dictionaries with an existing typed result when available.
- [ ] Delete redundant recalculation and defensive comparisons covered by runtime validation.
- [ ] Preserve deterministic iteration and tie-breaking.
- [ ] Keep the extraction only when net LOC decreases.
- [ ] Run adaptive unit tests after each method.

Do not share code with complete generation during this package.

### 7.4 Simplify near and far solver stages

Production files:

- `backend/app/services/scheduler_near_optimizer.py`
- `backend/app/services/scheduler_far_fill.py`

- [ ] Keep the current CP-SAT models and objective order.
- [ ] Consolidate repeated stage-result construction into one local function.
- [ ] Keep raw CP-SAT statuses and current mappings.
- [ ] Keep the residual repair and greedy fallback.
- [ ] Remove duplicate final quality evaluation when one authoritative evaluation exists.
- [ ] Preserve deadline checks at model construction, solve, extraction, and return boundaries.

Do not combine near and far solvers.

### 7.5 Decide whether any kernel is justified

Run this gate only after packages 7.2 through 7.4.

- [ ] Compare remaining overlap, lunch, deadline, and quality code.
- [ ] Require three semantically identical implementations before extraction.
- [ ] Require a negative net LOC prototype.
- [ ] Reject the kernel when either condition fails.

Expected decision: reject the kernel.

Gate:

```powershell
node scripts/test.mjs fast --scope backend -- -k 'scheduler or cp_sat or far_fill or near_optimizer'
node scripts/test.mjs integration -- -k 'scheduler or schedule_generate or debt_basis or draft'
node scripts/test.mjs benchmark --profile fast --scope backend
```

Acceptance:

- Canonical JSON and fingerprints remain byte-identical.
- Golden blocks remain identical.
- Quality vectors do not worsen.
- Cancellation remains authoritative.
- Frozen blocks, recovery links, and approval remain correct.
- Runtime and candidate counts do not regress materially.

## 8. Test Consolidation and Permanent Policy

### 8.1 Consolidate setup, not behavior

Candidate files:

- `backend/tests/factories.py`
- `backend/tests/conftest.py`
- `backend/tests/_support/db_fixtures.py`
- `frontend/src/test/featureDataHooks.test.jsx`
- Tutorial test files.

- [ ] Count repeated fixture setup after production refactors finish.
- [ ] Reuse existing factories before adding one.
- [ ] Parameterize role, tenant, error, transition, and provider matrices.
- [ ] Keep one assertion source for each public invariant.
- [ ] Delete obsolete route and sentinel tests.
- [ ] Preserve every distinct failure and success scenario.
- [ ] Reject helper extraction when it increases total test lines.

### 8.2 Add regression guards

Backend test file: `backend/tests/unit/test_backend_foundation_contracts.py`.

Frontend guard locations: existing Knip, ESLint, and feature-hook tests.

- [ ] Reject reintroduced flat class write methods.
- [ ] Reject the legacy timeslot generation route.
- [ ] Reject business sentinel returns in migrated services.
- [ ] Reject FastAPI imports from services.
- [ ] Reject tenant query helpers without explicit organization input.
- [ ] Reject organization query keys outside `orgQueryKey` in migrated feature modules.
- [ ] Keep Knip responsible for unused frontend exports.
- [ ] Keep the tutorial network-boundary E2E as the external-request guard.

Do not build a custom general-purpose linter.

### 8.3 Set the future LOC policy

Files:

- `documentation/00_getting_started/CONTRIBUTING.md`
- `.github/workflows/ci.yml`
- `documentation/08_security_quality/loc-baseline.json`

- [ ] Run the LOC report in CI and publish its table in logs.
- [ ] State that feature changes may add justified production LOC.
- [ ] Require refactors and fixes to remain neutral or negative.
- [ ] Require a written exception when non-feature production LOC grows.
- [ ] Keep enforcement review-based because CI cannot infer product intent.
- [ ] Update the stored baseline only after this WBS completes.

Do not enforce arbitrary function, file, or feature line limits.

## 9. Release and Rebaseline

### 9.1 Run the complete gate

```powershell
node scripts/test.mjs doctor --profile all
node scripts/test.mjs fast --scope all
node scripts/test.mjs integration
node scripts/test.mjs e2e
node scripts/test.mjs benchmark --profile fast --scope all

Set-Location frontend
npm run audit:production
npm run verify

Set-Location ../backend
./.venv/Scripts/python.exe -m ruff format --check .
./.venv/Scripts/python.exe -m ruff check .
./.venv/Scripts/python.exe -m alembic check
./.venv/Scripts/python.exe -m scripts.audit_triggers
./.venv/Scripts/python.exe -m scripts.audit_database_integrity

Set-Location ..
node --test scripts/test.test.mjs
node scripts/loc-report.mjs
```

Run all database commands only against test or CI databases.

### 9.2 Review the final architecture

- [ ] Confirm endpoints contain transport logic only.
- [ ] Confirm application services own transactions and orchestration.
- [ ] Confirm pure policies have no infrastructure dependency.
- [ ] Confirm adapters own Clerk, Celery, and browser-storage details.
- [ ] Confirm no duplicate write API remains.
- [ ] Confirm no new generic abstraction or dependency was added.
- [ ] Confirm documentation matches implementation and tests.

### 9.3 Rebaseline and release

- [ ] Record final production and test LOC separately.
- [ ] Explain every target shortfall caused by a protected quality gate.
- [ ] Write the final counts with `node scripts/loc-report.mjs --write-baseline`.
- [ ] Commit the new baseline only after every test passes.
- [ ] Deploy backend route removals and frontend compatibility changes together.
- [ ] Monitor error codes, member support states, ledger totals, and scheduler outcomes.
- [ ] Roll back the smallest release package when an invariant regresses.

## Commit Sequence

Use one green commit for each leaf package.

Recommended subjects:

1. `test(tooling): record LOC and behavior baseline`
2. `refactor(classes): remove flat mutation API`
3. `refactor(timeslots): remove legacy generation route`
4. `refactor(backend): delete unused service functions`
5. `refactor(tutorial): normalize local scenario data`
6. `refactor(tutorial): simplify local API routing`
7. `refactor(frontend): standardize tenant query keys`
8. `refactor(styles): delete measured unused CSS`
9. `refactor(api): converge catalog errors`
10. `refactor(operations): converge application errors`
11. `refactor(members): simplify durable access workflow`
12. `test(occurrences): characterize operational transitions`
13. `refactor(occurrences): apply one transition plan`
14. `refactor(scheduler): remove duplicate result derivation`
15. `refactor(scheduler): simplify adaptive repair stages`
16. `test(repository): consolidate matrices and guards`
17. `docs(quality): record final LOC baseline`

Split a subject further when its focused tests cannot isolate one behavior.

## Package Stop Rules

Stop a package when any condition occurs:

- A public behavior changes without explicit product approval.
- Tenant scope becomes implicit or depends only on RLS.
- A ledger, revision, audit, or compensation fact disappears.
- Scheduler fingerprints or golden blocks change unexpectedly.
- Visual or accessibility behavior regresses.
- The proposed abstraction produces non-negative LOC savings.
- Tests become broader but less specific.
- The full gate fails outside the expected red test.

Fix the root cause before continuing.

## Definition of Done

- Every supported behavior remains available.
- Every protected contract has automated evidence.
- Production LOC falls independently from test LOC.
- The tutorial remains interactive and local-only.
- Class writes have one API path.
- Timeslot regeneration has one atomic API path.
- Services no longer return business error sentinels.
- Member operations use one durable saga path.
- Occurrence mutations use one transition plan and one application workflow.
- Scheduler result derivation has one source per field.
- Tenant isolation remains explicit and RLS-backed.
- All required test, lint, migration, audit, build, E2E, and benchmark gates pass.
- The final baseline and contribution policy prevent infrastructure LOC regrowth.

## Deliberate Limits

This WBS does not remove features to hit a number.

It does not promise a shared scheduler kernel.

It does not split large files without deletion.

It does not create reusable infrastructure for hypothetical future consumers.
