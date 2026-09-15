# LOC Reduction Phase 2: Complete Implementation WBS

## Purpose

This WBS covers every remaining area after the first LOC reduction branch.

It turns four unfinished themes into test-driven, releasable work:

1. CSS measurement and deletion.
2. `AppError` convergence.
3. Member and occurrence workflow simplification.
4. Scheduler simplification.

The plan preserves product behavior, tenant isolation, durable evidence, and scheduler quality.

LOC reduction is an outcome of removing duplication. It never overrides a behavior gate.

## Starting Point

Start from branch `codex/loc-reduction-implementation` at revision `3808dc1`.

The first phase already removed obsolete APIs, wrappers, and frontend duplication.

The current reporter produces this phase-two baseline:

| Scope | Nonblank lines | Change from stored baseline |
| :--- | ---: | ---: |
| Backend production | 32,431 | -359 |
| Frontend production | 18,457 | -49 |
| Backend tests | 19,192 | -27 |
| Frontend tests | 5,966 | 0 |
| E2E tests | 3,217 | 0 |
| Total production | 50,888 | -408 |
| Total tests | 28,375 | -27 |

Run `node scripts/loc-report.mjs` again before the first phase-two commit.

Do not overwrite `loc-baseline.json` until the final release gate passes.

## Decisions

These decisions are final for this WBS.

- Keep every supported feature.
- Keep the existing public routes and response models.
- Keep the current Clerk operation ledger and saga coordinator.
- Do not add a member command framework.
- Add one small occurrence transition plan.
- Keep the append-only progress ledger.
- Keep the current scheduler result contracts.
- Keep near and far solver stages separate.
- Do not build a shared scheduler kernel without measured proof.
- Add no CSS dependency or automatic selector remover.
- Keep FastAPI `HTTPException` only at authentication and webhook boundaries.
- Preserve explicit `organization_id` filters and PostgreSQL RLS.
- Accept necessary characterization-test growth.

## Expected Result

The credible phase-two production target is 2,000 to 3,800 removed lines.

The stretch target reaches the original plan's 4,000-line total reduction.

The upper original forecast is not a release requirement.

Test LOC may grow before consolidation because occurrence coverage is incomplete.

Report these figures separately:

- production lines removed;
- test lines added for missing behavior;
- test lines removed through safe parameterization;
- final production and test totals.

Never delete a distinct assertion to improve the total.

## Clean Architecture Boundary

Changed code must follow this dependency direction:

`HTTP or UI -> application workflow -> domain policy -> infrastructure adapter`

The responsibilities are fixed:

| Boundary | Responsibility |
| :--- | :--- |
| Endpoint | Parse transport data, inject actor and session, return results |
| Application service | Tenant scope, locks, transactions, orchestration, audit |
| Domain policy | Pure transition and validation decisions |
| Infrastructure adapter | Clerk, database execution, Celery, browser storage |
| Frontend feature data | Query keys, requests, invalidation, server state |

Do not introduce generic repositories, units of work, service locators, or CRUD frameworks.

## TDD Contract

Every leaf package follows one cycle.

1. Add or identify a focused failing test.
2. Confirm the failure represents the intended change.
3. Make the smallest production change.
4. Run the focused test.
5. Run the package gate.
6. Measure production and test LOC.
7. Commit only a green slice.

Characterization tests may begin green. They must fail when the protected behavior is deliberately broken.

Use real PostgreSQL for tenant, transaction, ledger, and scheduler persistence tests.

Mocks may isolate Clerk and dispatch adapters. They must not replace database invariants.

## Dependency Order

| Package | Depends on | May proceed independently |
| :--- | :--- | :--- |
| P2-0 Controls | Phase 1 | No |
| P2-1 Common errors | P2-0 | CSS characterization |
| P2-2 Member workflow | P2-1 | CSS deletion |
| P2-3 Occurrence characterization | P2-0 | P2-1 and CSS |
| P2-4 Occurrence workflow | P2-1, P2-3 | CSS deletion |
| P2-5 CSS deletion | P2-0 | Backend packages |
| P2-6 Scheduler | P2-1, P2-4 | No |
| P2-7 Consolidation | P2-2 through P2-6 | No |
| P2-8 Release | P2-7 | No |

P2-1 leaves member, occurrence, and scheduler errors for their owning packages.

That prevents repeated edits to the largest files.

## Scope Traceability

| Remaining request | Complete coverage |
| :--- | :--- |
| CSS coverage | P2-5.1 through P2-5.7 |
| `AppError` migration | P2-1, P2-2.2, P2-4.2, P2-6.2, P2-7.1 |
| Member redesign | P2-2.1 through P2-2.7 |
| Occurrence redesign | P2-3 and P2-4 |
| Scheduler simplification | P2-6.1 through P2-6.8 |
| Future LOC control | P2-7.2 and P2-8.3 |

---

## P2-0 Controls and Characterization Baseline

### P2-0.1 Create the phase-two branch

Create `codex/loc-reduction-phase-2` from the clean implementation branch.

Do not mix unrelated working-tree changes into phase two.

Record these commands in the pull request description:

```powershell
git rev-parse HEAD
git status --short
node scripts/loc-report.mjs
```

Acceptance:

- The starting revision is recorded.
- The working tree is clean.
- The LOC report completes.
- No baseline file changes.

### P2-0.2 Freeze cross-cutting contracts

Create one phase-two evidence directory:

`documentation/08_security_quality/loc-phase-2-evidence/`

Store small machine-readable reports only.

Required reports:

- `errors-before.json`;
- `errors-after.json`;
- `css-scenarios.json`;
- `css-coverage-before.json`;
- `css-coverage-after.json`;
- `css-selector-decisions.json`;
- `scheduler-golden-before.json`;
- `scheduler-golden-after.json`;
- `loc-before.json`;
- `loc-after.json`.

Do not store generated bundles, databases, traces, or videos.

The reports must contain commands and revision identifiers.

### P2-0.3 Add package-level stop rules

Stop the active package when any condition occurs:

- a public response changes without a recorded decision;
- tenant scope becomes implicit;
- a ledger or audit fact disappears;
- a Clerk operation becomes untracked;
- a scheduler fingerprint changes unexpectedly;
- a visual or accessibility state regresses;
- an extraction fails to reduce production LOC;
- tests become broader but less specific.

Revert only the failing leaf package. Keep earlier green packages.

---

## P2-1 Complete `AppError` Convergence

### Current evidence

The application contains 112 explicit `HTTPException` constructions.

| Endpoint module | Sites |
| :--- | ---: |
| `api/deps.py` | 9 |
| `endpoints/classes.py` | 15 |
| `endpoints/schedule.py` | 15 |
| `endpoints/courses.py` | 12 |
| `endpoints/scheduler.py` | 11 |
| `endpoints/org_settings.py` | 10 |
| `endpoints/teachers.py` | 9 |
| `endpoints/foundation.py` | 6 |
| `endpoints/occurrences.py` | 6 |
| `endpoints/timesheets.py` | 5 |
| `endpoints/legal.py` | 3 |
| `endpoints/rooms.py` | 3 |
| `endpoints/subjects.py` | 3 |
| `endpoints/webhooks.py` | 3 |
| `endpoints/readiness.py` | 1 |
| `endpoints/session.py` | 1 |

Services contain 47 uppercase string returns.

Ten are valid scheduler disruption categories. The other 37 are business error sentinels.

### P2-1.1 Capture the public error contract

Primary tests:

- `backend/tests/unit/test_error_handlers.py`;
- existing committed endpoint tests;
- frontend API error tests.

Create a parameterized response matrix covering every migrated failure.

Each row records:

- route and method;
- triggering condition;
- HTTP status;
- public `detail.code`;
- public context keys;
- public field keys;
- `retryable`;
- `support_required`;
- request-reference behavior.

Capture actual responses through the ASGI application.

Do not infer the public code from an internal exception string.

This matters because raw string details currently use status fallback codes.

Add tests proving these properties:

- `X-Request-ID` equals `detail.reference`;
- provider exception text remains private;
- SQL exception text remains private;
- unknown failures use `unexpected_error`;
- validation fields remain stable.

Deliverable: `errors-before.json` generated from the matrix.

### P2-1.2 Define the allowed transport boundary

Keep explicit `HTTPException` construction only in:

- `backend/app/api/deps.py`;
- `backend/app/api/v1/endpoints/webhooks.py`.

These sites represent authentication, authorization, and webhook transport failures.

Keep the global `HTTPException` handler for framework and third-party exceptions.

Do not create a service solely for the readiness endpoint.

That endpoint may raise `AppError` directly for its transport-level availability result.

Add an AST allowlist test in `test_backend_foundation_contracts.py`.

The initial test must list every non-allowed site and fail.

### P2-1.3 Migrate CRUD sentinel services

Process one service and its endpoint together.

Order:

1. `room_service.py` and `rooms.py`.
2. `subject_service.py` and `subjects.py`.
3. `timeslot_service.py` and its schedule endpoint callers.
4. `course_service.py` and `courses.py`.
5. `class_service.py` and `classes.py`.
6. `teacher_service.py` and `teachers.py`.

For each failure branch:

1. Add a service test expecting `AppError`.
2. Preserve the recorded public status and code.
3. Replace the uppercase return with `raise AppError(...)`.
4. Return the normal domain result on success.
5. Delete the endpoint string comparison.
6. Delete the endpoint `HTTPException` branch.
7. Run the service and endpoint tests.

Use these rules:

- `kind` controls status.
- `code` preserves the public contract.
- `detail` contains safe diagnostic context.
- `public_fields` contains field-level guidance.
- `public_context` contains approved UI state only.
- never place raw provider data in public fields.

Do not add a generic error factory during the first three services.

After three services, extract only an identical construction repeated three times.

Keep all ten values in `scheduler_disruption.py` unchanged.

### P2-1.4 Migrate operational domain exceptions

Files:

- `backend/app/services/lesson_log_service.py`;
- `backend/app/services/timesheet_service.py`;
- `backend/app/api/v1/endpoints/timesheets.py`;
- related endpoint modules.

Replace `DomainError`, `NotFoundError`, `ConflictError`, and `ForbiddenError` at public service paths.

Preserve lesson accounting and timesheet state transitions.

Test these cases before removal:

- missing lesson log;
- invalid completion state;
- stale or conflicting timesheet;
- forbidden actor;
- cross-tenant identifier;
- duplicate completion retry.

Do not delete the exception classes yet.

P2-7.1 removes them after all callers migrate.

### P2-1.5 Migrate remaining small endpoints

Process these endpoint families separately:

- foundation;
- legal;
- organization settings;
- readiness;
- session;
- active schedule reads and mutations.

Move business decisions into an existing application service.

Raise `AppError` directly in an endpoint only for a transport-only condition.

Do not add pass-through service methods.

Preserve response models, success codes, and OpenAPI route shapes.

### P2-1.6 Focused verification

Run after every endpoint family:

```powershell
node scripts/test.mjs fast --scope backend -- -k "error or foundation or class or course or room or subject or teacher or timeslot or timesheet"
node scripts/test.mjs integration -- -k "classes or courses or rooms or subjects or teachers or schedule or timesheets or lesson"
```

Package acceptance:

- All 37 business sentinels are gone.
- Ten scheduler categories remain.
- Common endpoints contain no business error mapping.
- Public error responses match the recorded matrix.
- Member, occurrence, and scheduler exceptions remain assigned to later packages.

Expected production reduction: 350 to 700 lines.

---

## P2-2 Simplify the Member Access Workflow

### Architecture decision

Reuse these existing components:

- `MemberAccessOperationService` for durable operation state;
- `MemberAccessSagaCoordinator` for concrete compensations;
- `ClerkAccessService` for provider calls;
- `member_service.py` for application orchestration.

Do not add `AccessCommand`, `ProviderEffect`, a workflow engine, or another coordinator.

Keep operation-ledger commits independent from the membership transaction.

### Protected state machine

The refactor must preserve these paths:

| Path | Required transitions |
| :--- | :--- |
| Success | `pending -> clerk_succeeded -> local_committed` |
| Provider rejection | `pending -> failed` |
| Local failure, compensation succeeds | `clerk_succeeded -> compensated` |
| Local failure, compensation fails | `clerk_succeeded -> support_required` |
| Retriable prior operation | terminal reusable state to new `pending` attempt |
| Unresolved prior operation | reject without another provider mutation |

### P2-2.1 Complete the member failure matrix

Extend these tests first:

- `backend/tests/unit/test_member_saga_coordinator.py`;
- `backend/tests/integration/committed/test_members_api.py`;
- `backend/tests/contracts/test_preflight_service.py`.

Parameterize by provider effect:

- invitation creation;
- organization membership creation;
- role change;
- invitation revocation;
- membership revocation.

Parameterize by failure point:

- lookup failure;
- provider mutation failure;
- local flush failure;
- local commit failure;
- compensation failure;
- operation transition failure;
- retry with failed operation;
- retry with unresolved operation.

Every row asserts:

- provider call count;
- operation type and idempotency key;
- complete status history;
- local membership state;
- provider identifiers;
- support reference visibility;
- tenant scope;
- returned `AppError` contract.

The matrix must exercise all seven `MemberAccessOperationType` values.

It must also observe every reachable operation status.

Keep unused persisted enum values unless a separate migration proves safe deletion.

Also preserve:

- last-admin protection;
- self-admin protection;
- scheduler-only teacher access;
- active identity email locking;
- teacher subject competency;
- scheduler change recording;
- archive versus hard-delete behavior.

### P2-2.2 Remove HTTP status knowledge from member services

Change `member_error(status_code, ...)` to accept an `AppError.kind` value.

Do not pass integers through application services.

Keep existing public codes and approved context.

Update all calls before deleting the integer mapping.

Add a source contract test rejecting integer status literals passed to `member_error`.

### P2-2.3 Consolidate capability policy

`create_member`, `update_member`, and `restore_member` repeat capability rules.

Add one pure private function in `member_service.py`.

Inputs:

- requested capabilities;
- requested teacher access mode;
- whether platform restoration is allowed.

Output:

- normalized capability set;
- normalized teacher access mode;
- expected Clerk role.

It raises `AppError` for invalid combinations.

Table-test these combinations:

- administrator with platform access;
- teacher with platform access;
- teacher with scheduler-only access;
- non-teacher without a teacher mode;
- teacher without a mode;
- administrator with scheduler-only mode;
- restore without platform access.

Delete the three repeated validation branches after parity passes.

Keep subject-ID validation in the database-facing application path.

### P2-2.4 Reuse one provider grant path

The current `create_member` duplicates most of `_send_invitation`.

Make the local membership draft first and flush it once.

Then call one provider-grant helper for create, update, restore, and resend.

Rename `_send_invitation` only if the broader name improves accuracy.

The helper must:

1. Create one durable operation.
2. Locate the Clerk user once.
3. Locate the current membership once.
4. Reuse or create the required provider access.
5. Persist `clerk_succeeded` once.
6. Apply provider identifiers to the local member.
7. Commit the local transaction once.
8. Attach local identifiers through `local_committed`.
9. Compensate the exact created or changed resource on failure.

A small frozen `ProviderGrant` value is allowed inside `member_service.py`.

It may contain only:

- provider user identifier;
- membership identifier;
- invitation identifier and expiry;
- created resource kind;
- previous role.

Keep it only when replacing unclear multi-value tuples and reducing net LOC.

Pass `draft_payload` only for create recovery. Do not generalize it.

### P2-2.5 Keep revoke and role change explicit

Simplify `_change_provider_role` and `_revoke_provider_access` separately.

Share operation-finalization code only after three identical sequences remain.

Each helper must retain:

- one provider mutation;
- one durable operation;
- exact compensation;
- provider request reference;
- safe diagnostic category;
- one local commit;
- one terminal operation status.

Do not combine grant, role change, and revocation into a switch statement.

### P2-2.6 Slim public member operations

Process one function per green commit:

1. `create_member`;
2. `update_member`;
3. `remove_member`;
4. `restore_member`;
5. `resend_invitation`;
6. `retry_sync`.

Each function should read as this sequence:

1. Load tenant-owned state.
2. Validate domain policy.
3. Apply local draft changes.
4. Invoke one explicit provider helper when required.
5. Record scheduler impact when required.
6. Return the existing schema.

Delete duplicated provider discovery, transition, and compensation branches.

Do not split the file merely to reduce its size.

Move code only when a second production caller needs that boundary.

### P2-2.7 Member verification

```powershell
node scripts/test.mjs fast --scope backend -- -k "member or clerk or preflight"
node scripts/test.mjs integration -- -k "members_api or tenant_isolation or preflight"
node scripts/test.mjs e2e --project provider
```

Acceptance:

- Each intended provider effect runs at most once.
- Every effect has one durable operation.
- Every operation reaches the correct terminal state.
- Compensation failure remains visible to support.
- No operation crosses organizations.
- Scheduler-relevant teacher changes remain recorded.
- Public member error responses remain stable.

Expected production reduction: 450 to 850 lines.

---

## P2-3 Characterize Occurrence Behavior

The occurrence service has no focused committed integration suite.

Add that evidence before changing its 2,026-line implementation.

### P2-3.1 Build committed occurrence fixtures

Create:

`backend/tests/integration/committed/test_occurrences.py`

Reuse existing factories and scheduler fixtures.

Do not create a second fixture framework.

The minimal fixture graph contains:

- two organizations;
- one administrator per organization;
- one published active schedule block;
- planned class, subject, module, teacher, room, and timeslot;
- one valid substitute;
- one invalid substitute for each eligibility rule.

Keep timestamps and identifiers deterministic.

### P2-3.2 Characterize creation and reads

Test:

- create from an active published block;
- idempotent reuse of the same active block;
- missing block;
- inactive block;
- cross-tenant block identifier;
- missing schedule context;
- list filters and pagination;
- invalid status filter;
- detail not found;
- debt and observability reads.

Assert occurrence events for success and failure.

### P2-3.3 Characterize decisions

Create a table for `GIVEN`, `GAP`, and `SUBSTITUTED`.

For every state, assert:

- occurrence status and reason;
- version and revision;
- planned and executed teacher;
- planned and executed module;
- hours given;
- operational block result;
- exact ledger minute deltas;
- idempotency keys;
- actor and organization identifiers;
- audit event.

Test an identical retry with current and immediately previous versions.

Assert that neither retry applies accounting twice.

### P2-3.4 Characterize invalid transitions

Test:

- stale version;
- inactive occurrence;
- terminal revoked occurrence;
- illegal redecision;
- missing planned module;
- missing executed module;
- substitute equals planned teacher;
- substitute lacks subject competence;
- substitute room mismatch;
- impossible availability;
- slot conflict;
- completed substitute log lock.

Each test asserts the public response and unchanged persistence state.

### P2-3.5 Characterize cancellation and recovery evidence

Test cancellation from open and decided states.

For decided states, assert compensating ledger entries.

For substituted states, assert operational block cancellation.

Test both allowed and blocked completed-log cancellation.

Assert that historical ledger rows are never updated or deleted.

Run scheduler recovery validation against the resulting debt.

Package acceptance:

- Every occurrence mutation path has committed database evidence.
- Tests fail when accounting, versioning, or audit writes are removed.
- No production code changes occur in this package.

Expected test growth: 250 to 500 lines.

---

## P2-4 Simplify the Occurrence Workflow

### P2-4.1 Define one minimal transition plan

Start inside `backend/app/services/occurrence_service.py`.

Add one frozen `OccurrenceTransitionPlan`.

It contains only facts needed by the mutation executor:

- target status;
- executed teacher and module identifiers;
- hours given;
- reason;
- zero or one reversal accounting intent;
- zero or one decision accounting intent;
- operational-block action.

An accounting intent contains status, module identifiers, hours, direction, and source type.

The pure planner receives already-resolved identifiers and current occurrence facts.

It must not import FastAPI, SQLAlchemy, Clerk, or Celery.

It decides:

- legal state transition;
- idempotent result;
- previous-state reversal requirement;
- new-state accounting requirement;
- operational block create, keep, or cancel;
- public failure kind and diagnostic reason.

Database lookups remain outside the planner.

Table-test the full transition matrix.

Keep the planner in the current module unless another production caller needs it.

### P2-4.2 Replace `OccurrenceServiceError`

Replace `OccurrenceServiceError(status_code, detail)` with `AppError`.

Use the captured public status and code from P2-1.1.

Keep uppercase occurrence reason tokens diagnostic when they were not public codes.

Do not accidentally expose `SUBSTITUTE_LOG_LOCKED` or SQL details.

Remove endpoint translation blocks only after service tests pass.

Delete `OccurrenceServiceError` after `rg` finds no references.

### P2-4.3 Add async application entry points

Add one async entry point for each endpoint use case:

- list occurrences;
- create or reuse occurrence;
- list debts;
- read observability summary;
- list available substitutes;
- rank substitute recommendations;
- get occurrence;
- decide occurrence;
- cancel occurrence.

Each entry point performs one `db.run_sync` call.

Mutation entry points also record their success or failure event.

Keep safe observability logging non-fatal.

Return existing schema-compatible objects and created-state flags.

Do not add repositories or a unit-of-work wrapper.

### P2-4.4 Collapse decision execution

Refactor `update_occurrence_sync` in this order:

1. Load and lock the occurrence once.
2. Return an allowed idempotent retry.
3. Validate version once.
4. Resolve planned context once.
5. Validate substitute resources once when required.
6. Build one transition plan.
7. Apply its reversal accounting intent.
8. Apply its decision accounting intent.
9. Append ledger entries for applied deltas.
10. Apply its operational-block action.
11. Set occurrence fields once.
12. Append revision and audit evidence once.
13. Increment the version once.
14. Hydrate the response once.

Delete `_validate_state_transition` after the planner owns that rule.

Delete `_ledger_deltas_for_state` when applied deltas always drive ledger rows.

Remove the no-op `try/except` that only re-raises exceptions.

Preserve sequential module accounting for `GIVEN`.

### P2-4.5 Collapse cancellation execution

Use the same accounting-intent executor for cancellation reversals.

Keep cancellation policy explicit.

The cancellation path must:

- lock and version-check once;
- reverse prior accounting once;
- append compensating ledger rows;
- cancel related operational blocks;
- restore eligible lesson logs to pending;
- preserve completed-log protection;
- append occurrence revision and audit evidence;
- increment the version once.

Do not physically delete occurrences, logs, ledger entries, or revisions.

### P2-4.6 Thin the endpoint module

Replace endpoint-local closures with direct async service calls.

Keep only:

- route metadata;
- request and response schemas;
- dependency injection;
- the create-versus-reuse response status adjustment.

Move success and failure event recording into application entry points.

Remove the endpoint error constant when no route metadata uses it.

### P2-4.7 Occurrence verification

```powershell
node scripts/test.mjs fast --scope backend -- -k "occurrence or lesson_log or module_progress"
node scripts/test.mjs integration -- -k "occurrence or debt or module_progress or scheduler_recovery"
node scripts/test.mjs e2e --project app
```

Acceptance:

- State, version, revision, ledger, block, and audit results match characterization.
- Concurrent stale requests cannot apply twice.
- Idempotent retries never duplicate accounting.
- Revocation preserves immutable evidence.
- Recovery debt remains scheduler-compatible.
- Occurrence endpoints contain no error translation or `run_sync` closures.

Expected production reduction: 350 to 650 lines.

---

## P2-5 Measure and Delete CSS Safely

### Current evidence

`index.css` contains 1,384 nonblank lines.

Marketing styles contain approximately 1,000 nonblank lines.

The existing coverage script visits only `/` and `/login`.

Its byte coverage cannot prove an individual source selector is unused.

Therefore, the current low percentages are not deletion authority.

### P2-5.1 Define the supported scenario manifest

Create `css-scenarios.json` with route, role, viewport, state, and action fields.

Required public routes:

- `/`;
- `/vantagens`;
- `/como-funciona`;
- `/sobre`;
- `/ajuda`;
- `/contacto`;
- `/privacidade`;
- `/termos`;
- `/dpa`;
- `/cookies`;
- `/login`;
- `/register`;
- `/recuperar-palavra-passe`;
- not found.

Required administrator routes:

- `/dashboard`;
- `/members`;
- `/rooms`;
- `/subjects`;
- `/courses`;
- course details;
- class details;
- class subjects;
- `/config`;
- `/schedules`;
- `/absences`;
- `/timesheets`;
- `/foundation`;
- `/foundation/waiting`;
- `/guide`.

Required teacher routes:

- `/my-schedules`;
- `/my-progress`;
- `/my-availability`.

Required states:

- default;
- loading or skeleton;
- empty;
- populated;
- validation error;
- API error;
- modal open;
- dropdown open;
- disabled control;
- keyboard focus;
- hover where it changes layout;
- tutorial step overlays;
- responsive navigation.

Required viewports are 375, 768, and 1440 pixels wide.

Use one representative route when several routes share identical layout styles.

Keep a written equivalence entry for every skipped route.

### P2-5.2 Upgrade coverage collection without dependencies

Reuse Playwright and existing Clerk helpers.

Add a conditional Chromium-only coverage project or script.

It must run only when `CSS_COVERAGE_ENABLED=1`.

The runner must:

1. Start CSS coverage before navigation.
2. Use existing admin and teacher sessions.
3. Execute the scenario actions.
4. Capture used byte ranges.
5. Capture a screenshot for each scenario and viewport.
6. Record failed or skipped scenarios.
7. Merge results by built stylesheet URL.
8. Write a deterministic JSON report.

Write reports into `loc-phase-2-evidence` and screenshots into the existing visual-baseline area.

Do not add Puppeteer, PurgeCSS, UnCSS, or a CSS parser dependency.

Keep the existing public-only script until the new runner proves parity.

Delete it only when the new runner covers its routes and output.

### P2-5.3 Build a selector evidence table

For each deletion candidate, record:

- source file and selector;
- source-search result;
- runtime scenario result;
- dynamic class prefix search;
- pseudo-state relevance;
- responsive or print relevance;
- deletion decision.

A selector is deletable only when all conditions hold:

- no JSX, JavaScript, HTML, or test reference exists;
- no dynamic prefix or third-party contract can create it;
- no supported scenario uses its declaration range;
- it is not a required pseudo-state;
- it is not a browser, Clerk, CoreUI, or component-library override.

Coverage alone never authorizes deletion.

### P2-5.4 Delete by isolated route group

Use this order:

1. marketing and legal;
2. authentication;
3. application shell and dashboard;
4. catalog and member forms;
5. schedules;
6. occurrences and timesheets;
7. teacher pages;
8. tutorial.

For each group:

1. Capture before screenshots and coverage.
2. Delete only evidence-approved selectors.
3. Merge declaration blocks only when state semantics match.
4. Run source search again.
5. Build the frontend.
6. Capture after screenshots and coverage.
7. Compare layout and state behavior.
8. Commit the green group separately.

Do not move CSS between files unless the move enables actual deletion.

Do not rename selectors unless all references change in the same commit.

### P2-5.5 Preserve design and accessibility contracts

Keep:

- warm-white, brown, and amber tokens;
- Playfair headings and Outfit body typography;
- marketing namespace isolation;
- visible keyboard focus;
- disabled and invalid states;
- `prefers-reduced-motion` behavior;
- mobile tap targets;
- readable legal content;
- responsive table and navigation behavior.

Run Axe on public, admin, and teacher representatives.

Test keyboard navigation through dialogs, menus, tabs, and forms.

### P2-5.6 Remove duplicate declarations

After dead selector deletion, compare repeated declaration blocks.

Merge only exact semantic duplicates.

Prefer existing tokens and utility classes.

Do not create a utility class used once.

Do not merge selectors with different focus, error, or responsive behavior.

Do not change specificity to save lines.

### P2-5.7 CSS verification

```powershell
Set-Location frontend
npm run lint
npm run lint:dead-code
npm run test:coverage
npm run build
npm run verify
$env:CSS_COVERAGE_ENABLED='1'
npx playwright test --project css-coverage
Remove-Item Env:CSS_COVERAGE_ENABLED
```

Acceptance:

- Every supported route maps to a captured or equivalent scenario.
- Every removed selector has source and runtime evidence.
- Before and after screenshots show no unintended change.
- Axe reports no new violations.
- Keyboard and reduced-motion behavior remain correct.
- No new frontend dependency is added.

Expected production reduction: 300 to 700 lines.

---

## P2-6 Simplify the Scheduler

### Protected behavior

Use the implemented [Scheduler Reliability WBS](../03_scheduler_engine/SCHEDULER_RELIABILITY_WBS.md) as the contract.

Protect:

- canonical input fingerprints;
- deterministic selected blocks;
- frozen-horizon behavior;
- debt recovery links;
- result categories and blockers;
- cancellation and deadlines;
- atomic draft persistence and approval;
- job 13 candidate-count regression;
- current quality vectors;
- complete, near, and far stage boundaries.

### P2-6.1 Record deterministic golden outputs

Run the scheduler suite twice before production changes.

Store these fields for representative complete, near, far, and repair cases:

- generation fingerprint;
- debt-basis fingerprint;
- ordered stable block keys;
- result category;
- projected and hard end dates;
- recovery escalation level;
- adaptation level;
- blocker type and message code;
- warnings and recommended action codes;
- summary and metrics keys;
- candidate count;
- quality vector;
- persisted draft state.

The second run must match the first byte-for-byte where canonical output applies.

### P2-6.2 Finish scheduler `AppError` migration

Keep internal typed exceptions used by worker execution.

Convert them at existing public application methods.

Do not translate them in `endpoints/scheduler.py`.

Process routes by use case:

1. preflight and request creation;
2. job read and cancellation;
3. draft read and selection;
4. draft approval and rejection;
5. lifecycle and recovery actions.

Use existing `scheduler_request_service.py` patterns.

Do not add a scheduler facade.

Preserve worker cancellation and failure categories.

### P2-6.3 Establish one owner for every result field

Files:

- `scheduler_adaptive_engine.py`;
- `scheduler_job_runtime.py`;
- `scheduler/domain/contracts.py`;
- current quality and validation helpers.

Create a temporary field-consumer table.

Classify each `summary` and `metrics` field as:

- externally returned;
- persisted;
- runtime validated;
- telemetry only;
- unused.

Assign exactly one producer to every retained derived field.

Use these ownership rules:

- engine owns solve facts and stage instrumentation;
- existing pure quality evaluators own block-derived quality facts;
- runtime owns phase timing and persistence facts;
- runtime independently validates hard invariants from blocks;
- API reads persisted contracts without recalculation.

Delete unused fields and duplicate calculations after consumer tests pass.

Do not add `SolveRequest`, `SolveOutcome`, or another result hierarchy.

Keep `ValidatedGenerationResult` and `NoValidGenerationOutput`.

### P2-6.4 Simplify `scheduler_adaptive_engine.py`

Process one method per commit:

1. `generate`;
2. `_solve_scope`;
3. `_build_tasks`;
4. `_build_placements`;
5. `_specs`;
6. `_result`;
7. `_combined_scopes`.

For each method:

1. Identify repeated loops, branches, or dictionaries.
2. Reuse an existing candidate, constraint, quality, or deadline helper.
3. Add a focused parity test.
4. Delete the duplicate block.
5. Compare ordered output and metrics.
6. Keep the change only when production LOC falls.

Preserve iteration order and tie-breaking.

Do not share code with complete generation during this package.

Do not hide solver decisions behind generic pipeline steps.

### P2-6.5 Simplify runtime validation and commit

Refactor `_validate_adaptive_repair` before `_commit_validated_draft`.

Validation must recompute protected invariants from selected blocks.

It must not demand the same derived value in two redundant dictionaries.

Group checks by existing domain concepts:

- tenant and scope;
- frozen blocks;
- collisions and availability;
- curriculum minutes;
- debt recovery;
- horizon and dates;
- quality acceptance;
- cancellation.

Use current validator functions. Do not create a validation framework.

Then simplify draft persistence:

- persist each retained summary field once;
- persist each retained metrics field once;
- write draft blocks once;
- keep transaction and failure transitions atomic;
- preserve canonical ordering.

### P2-6.6 Simplify the near optimizer

Keep the existing CP-SAT model and objective sequence.

Replace repeated stage-result construction with one local result builder.

Keep one ordered table describing each stage:

- objective;
- bound or constraint added;
- stage number;
- timeout or cancellation outcome.

Do not make objectives data-driven when it obscures CP-SAT expressions.

Preserve raw solver statuses and existing status mapping.

Evaluate final selected blocks once.

Run near optimizer tests after every stage change.

### P2-6.7 Simplify far fill

Keep greedy fill and residual repair separate.

Consolidate only repeated feasibility checks and final result assembly.

Preserve:

- frozen and occupied slots;
- teacher, class, and room collision checks;
- availability scoring;
- recovery linkage;
- residual repair fallback;
- deadline and cancellation checks;
- deterministic candidate order.

Use the existing quality evaluator once for the final block set.

Do not merge far fill with the near optimizer.

### P2-6.8 Audit fingerprint snapshot builders

Do not rewrite canonical snapshot formats.

For `generation_input_snapshot` and `debt_basis_snapshot`:

1. Trace repeated query and serialization blocks.
2. Add byte-identical snapshot tests.
3. Extract a section loader only when three blocks are semantically identical.
4. Require negative net production LOC.
5. Reject the extraction otherwise.

No key, ordering, numeric normalization, or null representation may change.

### P2-6.9 Decide the shared-kernel question

Run this decision only after P2-6.4 through P2-6.8.

A shared kernel is allowed only when:

- three solver stages retain identical mechanics;
- the mechanics have identical semantics;
- a prototype reduces net production LOC;
- golden output remains identical;
- the abstraction shortens each caller.

The expected decision is rejection.

Record the evidence either way.

### P2-6.10 Scheduler verification

```powershell
node scripts/test.mjs fast --scope backend -- -k "scheduler or cp_sat or far_fill or near_optimizer"
node scripts/test.mjs integration -- -k "scheduler or schedule_generate or debt_basis or draft"
node scripts/test.mjs benchmark --profile fast --scope backend
```

Run deterministic scheduler tests twice after the final scheduler commit.

Acceptance:

- Canonical JSON and fingerprints remain byte-identical.
- Golden ordered blocks remain identical.
- Quality vectors do not worsen.
- Runtime validation remains independent.
- Cancellation remains authoritative.
- Frozen and recovery blocks remain correct.
- Draft approval remains atomic.
- Candidate count and runtime do not regress materially.

Expected production reduction: 550 to 1,100 lines.

---

## P2-7 Consolidation and Permanent Guards

### P2-7.1 Complete error cleanup

Run repository-wide searches:

```powershell
rg -n "DomainError|NotFoundError|ConflictError|ForbiddenError|OccurrenceServiceError" backend/app
rg -n 'return "[A-Z_]+"' backend/app/services
rg -n "HTTPException\(" backend/app
```

Expected results:

- no legacy domain exception callers;
- no occurrence service exception;
- only ten scheduler category returns;
- explicit `HTTPException` only in the two allowlisted boundary files.

Delete unused legacy exception classes and their handler.

Keep the global `HTTPException` handler.

Activate the final AST guards.

### P2-7.2 Consolidate tests without losing behavior

Review only test code touched by phase two.

Parameterize repeated setup and expected-result tables.

Reuse existing factories before adding helpers.

Keep one assertion source for every distinct invariant.

Delete obsolete tests for:

- uppercase sentinel translation;
- endpoint-local occurrence exception mapping;
- duplicated member provider branches;
- removed scheduler result fields;
- removed selectors or class names.

Do not delete a distinct failure scenario.

Reject any helper that increases total test LOC or hides expected values.

### P2-7.3 Add narrow regression guards

Extend existing tools only.

Backend guards:

- no FastAPI imports from services;
- no non-allowlisted explicit `HTTPException`;
- no business sentinel returns;
- no legacy occurrence exception;
- no tenant query without explicit organization scope in changed services.

Frontend guards:

- Knip owns unused export detection;
- ESLint owns source correctness;
- CSS evidence lists every deleted selector;
- the tutorial network boundary remains local-only.

Do not build a general-purpose custom linter.

### P2-7.4 Review architecture and LOC

Review every changed production file.

Confirm:

- endpoints contain transport logic only;
- application services own orchestration and transactions;
- pure policies have no infrastructure imports;
- adapters own Clerk and worker effects;
- no new pass-through layers exist;
- no moved code is claimed as deletion;
- future feature code has one obvious home.

Run `node scripts/loc-report.mjs`.

If a leaf package adds production LOC, revert it unless quality requires the growth.

Document every accepted exception.

---

## P2-8 Complete Release Gate

### P2-8.1 Run all automated verification

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

Run database commands only against test or CI databases.

### P2-8.2 Perform manual risk checks

Verify these workflows in the staged application:

- administrator and teacher login;
- member create, role change, remove, restore, resend, and retry;
- provider failure and support-required presentation;
- occurrence create, decide, redecide, and cancel;
- debt appearance and recovery;
- schedule generation, cancellation, draft review, and approval;
- public, legal, authentication, admin, teacher, and tutorial layouts;
- keyboard navigation and reduced motion.

Observe logs without exposing private provider details.

### P2-8.3 Rebaseline only after success

After every gate passes:

```powershell
node scripts/loc-report.mjs --write-baseline
```

Commit the new baseline with the final evidence summary.

The summary must state:

- starting and final revisions;
- production reduction by work package;
- test change by work package;
- protected behavior evidence;
- rejected abstractions;
- any target shortfall;
- deployment and rollback order.

Future policy:

- feature work may add justified production LOC;
- refactors should remain neutral or negative;
- fixes should reuse existing seams first;
- non-feature growth requires a written explanation;
- CI reports LOC but does not infer product intent.

## Commit Plan

Use one green commit per leaf package.

Recommended order:

1. `test(quality): record phase two contracts`
2. `refactor(api): converge catalog errors`
3. `refactor(operations): converge application errors`
4. `test(members): complete access failure matrix`
5. `refactor(members): reuse provider grant workflow`
6. `refactor(members): simplify public operations`
7. `test(occurrences): characterize operational transitions`
8. `refactor(occurrences): introduce transition plan`
9. `refactor(occurrences): move orchestration from endpoints`
10. `test(styles): capture supported CSS scenarios`
11. `refactor(styles): delete measured unused selectors`
12. `refactor(styles): merge duplicate declarations`
13. `test(scheduler): record phase two golden outputs`
14. `refactor(scheduler): converge public errors`
15. `refactor(scheduler): remove duplicate result derivation`
16. `refactor(scheduler): simplify adaptive repair`
17. `refactor(scheduler): simplify near and far stages`
18. `test(repository): enforce phase two boundaries`
19. `docs(quality): record phase two result`

Split a commit when focused tests cannot isolate one behavior.

## Definition of Done

Phase two is complete only when every statement is true.

- Every CSS route group has runtime and source evidence.
- Every deleted selector has a recorded justification.
- Accessibility and responsive behavior remain correct.
- Business services raise `AppError` instead of returning sentinels.
- Explicit `HTTPException` use matches the narrow allowlist.
- Legacy domain and occurrence exceptions are removed.
- Member operations reuse one durable provider-grant path.
- Member compensation and support states remain recoverable.
- Occurrence mutations use one transition plan and one application boundary.
- Occurrence accounting remains append-only and idempotent.
- Scheduler fields have one producer and known consumers.
- Scheduler output, fingerprints, quality, and persistence remain stable.
- No generic workflow, repository, CSS, or scheduler framework was added.
- Production and test LOC are reported separately.
- Every focused, integration, E2E, audit, and benchmark gate passes.
- The stored LOC baseline reflects the released implementation.

## Deliberate Limits

This WBS does not delete features to meet a numerical target.

It does not remove tests that protect distinct behavior.

It does not promise a shared scheduler kernel.

It does not treat CSS byte coverage as proof of selector safety.

It does not normalize public error codes without contract evidence.
