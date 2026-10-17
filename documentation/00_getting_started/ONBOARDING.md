# Director Onboarding

## Purpose

This document is the canonical guide for the current Cronos onboarding flow.
It explains organization activation, Foundation configuration, the local tutorial, readiness, permissions, and recovery.

Use the source code and automated tests as the final authority when this guide differs from an implementation detail.

## Intended Reader

This document targets developers, QA engineers, support engineers, and school administrators who need to understand the first authenticated session.

## Prerequisites

- Start the local stack or use the deployed environment.
- Configure Clerk with a test user and an active organization.
- Use the active administrator who created the Clerk organization for the Foundation flow.
- Read [Routes and Permissions](../06_frontend_ux/ROUTES_AND_PERMISSIONS.md) for the complete access matrix.

## What the System Does

Cronos guides a new organization from Clerk activation to a committed school grid and the first real schedule approval.
It keeps the optional product tutorial separate from operational data.

## Why the Behavior Exists

The route gate protects operational features until the organization has a valid calendar grid.
The draft protocol protects against stale writes from concurrent tabs or requests.
The local tutorial lets users learn the product without mutating the tenant.

## Components and Ownership

| Area | Owner |
| :--- | :--- |
| Clerk activation and tenant bootstrap | Clerk provider, session endpoint, organization feature |
| Legal acceptance | Clerk `<SignUp />`, the onboarding completion gate, and legal status/acceptance endpoints |
| Foundation validation and persistence | Foundation wizard, Foundation service, organization tables |
| Tutorial simulation | Tutorial reducer, scenario, expiring local storage, and API boundary |
| Readiness and dashboard mode | Readiness service and dashboard service |
| Route access | `MemberGate` React route guards and FastAPI actor dependencies |

## Data or Request Flow

The route decision and the six onboarding phases below describe the request flow.

## Contracts and Invariants

Cronos uses four separate milestones:

1. Clerk authenticates the user and selects an organization.
2. The active Clerk organization creator completes the Foundation.
3. The administrator may use the local tutorial to learn the product.
4. The school configures the operational bases and approves the first real schedule.

Foundation completion is required before normal authenticated features become available.
`MemberGate` enforces legal acceptance first and the Foundation gate second for normal authenticated routes.
The tutorial is optional and does not replace Foundation or create operational data.

## States and Transitions

The frontend waits for Clerk and the current member before it selects a route.
Do not interpret a loading screen as a missing permission.

| Condition | Destination | Reason |
| :--- | :--- | :--- |
| User is signed out | `/login` | Authentication is required. |
| User has a pending Clerk organization task | `/login/tasks/choose-organization` | The user must create or select an organization. |
| User has no organization or membership after the task | Organization selector or Foundation route guard | The gate waits for the active organization and bootstraps it. |
| User has memberships but no active organization | Organization selector | The user must choose the tenant context. |
| Active organization, Foundation founder, Foundation incomplete | `/foundation` | Only the founder can complete the required setup. |
| Active organization, member who is not the Foundation founder, Foundation incomplete | `/foundation/waiting` | Only the founder can complete setup. |
| Active organization, Foundation complete, administrator | `/dashboard` | The signed-in landing uses the role default; school parameters stay at `/config`. |
| Active organization, Foundation complete, teacher | `/my-availability` | The default teacher route is teacher availability. |

The Foundation founder is the active administrator whose Clerk user id matches the Clerk organization's `created_by` value.
The local membership inviter marker does not establish the founder.
Legacy self-markers may belong to an invited administrator, and the creator may have joined later.
The backend exposes the verified founder capability as `can_manage_foundation` on the current member.

Foundation completes once per organization.
After completion, the wizard never opens again.
Administrators land on `/dashboard`, and school parameters remain at `/config`.

`/guide` is an explicit tutorial route. The real dashboard does not redirect to it automatically after Foundation completion.
The dashboard provides **Repetir guia** and **Retomar guia** actions when applicable.

## Phase 1: Create or Select the Organization

### Clerk environment configuration

In both the Clerk Development and Production instances, enable **Require express consent to legal documents** under the Clerk Dashboard's legal-compliance settings. The prebuilt `<SignUp />` then renders and enforces the mandatory checkbox. Keep this setting enabled for every environment that serves Cronos; it is provider configuration and cannot be safely enabled from browser code.

Cronos passes the current Terms, DPA, and Privacy versions as `unsafeMetadata` only to correlate the Clerk consent with the server status. Authorization remains enforced by the backend legal endpoints.

### Start the session

1. Open the application.
2. Sign in with Clerk.
3. Wait for Clerk to load the organization list.
4. Complete the Clerk organization task when Clerk requests it.

The task page is owned by Clerk and only handles organization selection or creation.
Clerk collects the mandatory legal consent during registration. After the active organization
is available, Cronos correlates the Clerk document versions and records the organization acceptance
in the background.

### Create an organization

When the user has no membership:

1. Enter the school name in the Clerk organization task.
2. Select or create the organization.
3. Wait for Clerk to activate the organization and membership.
4. Wait for the route guard to bootstrap the local member in the background.
5. Read `/legal/status`.
6. If the Clerk consent matches the current versions, the administrator acceptance is submitted
   automatically; future version changes use the in-app reacceptance dialog.

The bootstrap and acceptance actions are idempotent and can be retried after a transient
failure; no legal proof is kept in browser storage.
The backend bootstrap requires the Clerk subject, the active organization claim, and an administrator role.
It reconciles the provider organization and membership with the tenant database.
When the organization still needs its first local membership, the backend founds it only for the Clerk organization's creator.

### Bootstrap response

`POST /api/v1/session/bootstrap` returns:

- the local organization;
- the current member, including `can_manage_foundation`;
- the current `foundation_status`.

The backend returns `503` when the Clerk provider directory is unavailable.
An administrator who is not the Clerk organization's creator receives `403` when the organization is not founded yet.
The frontend must show a recoverable session error and allow the user to retry.

## Phase 2: Complete the Foundation

### Access and state

The Foundation has three states:

| State | Meaning | Admin access |
| :--- | :--- | :--- |
| `NOT_STARTED` | No completed setup exists. | The founder opens `/foundation`. |
| `IN_PROGRESS` | A draft exists. | The founder resumes the draft. |
| `COMPLETED` | The grid and settings are committed. | Administrators land on `/dashboard`; school parameters stay at `/config`. |

Only the Foundation founder can open the draft before completion.
Other members see `/foundation/waiting` until the founder completes it.
After completion, no member is sent back to the wizard.

### Ten wizard steps

The wizard uses ten ordered steps:

1. **Period** — set `school_start_date`, `school_hard_end_date`, and `repair_stability_window_days`.
2. **Days** — select one or more `days_of_week` values from `0` to `6`.
3. **Opening** — set `opening_time` and `closing_time`.
4. **Slot duration** — set `slot_duration_minutes` from `15` to `120`.
5. **Break duration** — set `break_duration_minutes` from `0` to `60` and optional break overrides.
6. **Lunch** — set lunch start, end, and minimum duration.
7. **Preview** — inspect the calculated grid.
8. **Calendar** — confirm the calendar period, available days, and automatic holidays.
9. **Internship** — add optional internship flows with a name, a start date, and an end date.
10. **Confirmation** — confirm the complete snapshot.

The backend rejects an incomplete snapshot.
It also rejects duplicate or empty weekdays, an end time before the opening time, invalid lunch intervals, and a grid that cannot contain one slot.

### Draft persistence

The frontend loads status and draft data through React Query.
It autosaves changes after a short debounce and serializes writes so only one `PUT` is active at a time.
The destination step is persisted before navigation.

The API contract is:

| Operation | Endpoint | Permission | Result |
| :--- | :--- | :--- | :--- |
| Read status | `GET /api/v1/foundation/status` | Signed-in organization member | Current status and completion timestamps. |
| Read draft | `GET /api/v1/foundation/draft` | Foundation founder | Version, current step, and data. |
| Save draft | `PUT /api/v1/foundation/draft` | Foundation founder | New version and saved snapshot. |
| Complete | `POST /api/v1/foundation/complete` | Foundation founder | Committed settings and generated timeslot count. |

A non-founder administrator receives `403` from the draft and complete endpoints.

Every draft write includes `expected_version`.
The server locks the draft row, checks the version, validates the data, and flushes the new version.
The function-scoped database dependency commits before the HTTP response is sent.

### Version conflict

If another tab or request updates the draft first, the API returns `409` with code `FOUNDATION_DRAFT_VERSION_CONFLICT`.

Recover as follows:

1. Keep the conflict dialog open.
2. Reload the remote draft.
3. Compare the remote version with the local changes.
4. Continue from the remote draft, or manually re-enter the intended changes.
5. Save again with the new version.

The client does not overwrite a newer remote draft automatically.

### Complete the Foundation

The confirmation request contains `expected_version` and `confirmed: true`.
The server then:

1. locks the organization and draft;
2. checks the expected version;
3. validates the complete snapshot;
4. upserts organization settings;
5. regenerates the timeslot grid;
6. requires at least one generated timeslot;
7. sets `foundation_status` to `COMPLETED`;
8. records `foundation_completed_at`;
9. commits before returning success.

Completion is idempotent after the organization is already complete.
An incomplete request returns `422` with code `FOUNDATION_INCOMPLETE`.
A write after completion returns `409` with code `FOUNDATION_ALREADY_COMPLETED`.

## Phase 3: Stable Post-Completion Navigation

After a successful completion mutation, the frontend waits for these caches to reconcile:

- `foundation-status`;
- `foundation-draft`;
- `current-member`;
- preparation dashboard data;
- readiness data and prevalidation.

Only after that invalidation finishes does the wizard navigate to `/dashboard`.
The current dashboard consumer disables automatic tutorial navigation, so Foundation completion lands on a stable dashboard.

This sequencing matters because the route guard reads `current-member` and the dashboard reads the Foundation status.
Navigating before both caches update can display an old state or send the administrator back to the wizard.

## Phase 4: Local Tutorial

### Purpose and boundary

The tutorial at `/guide` is a local product simulation.
It uses real page components where useful, but `TutorialApiBoundary` intercepts simulated actions.
The tutorial does not create subjects, modules, teachers, rooms, schedules, occurrences, or repairs in the operational database.
It does not call the solver.

Use the tutorial to explain the product sequence.
Use the real administrative pages to create operational data.

### Scenario

The current scenario has version `3`, two chapters, and 13 feature steps.

| Chapter | Scope | Steps |
| :--- | :--- | :---: |
| 1 | Curriculum, classes, teachers, rooms, class plan, availability, and schedule | 1–7 |
| 2 | Occurrences, substitutions, weekly close, debt, recovery, and history | 8–13 |

The scenario contains demo courses, classes, subjects, modules, teachers, rooms, a five-day grid, a schedule proposal, occurrences, debt, recovery, and history.
Demo identifiers start with `demo-`.

Every step is a feature checkpoint. The user may continue without changing a form.
The schedule step can generate, review, and approve its complete example.
The recovery step starts with a prepared partial draft and permits approval only.

### Tutorial state

The tutorial uses these statuses:

- `NOT_STARTED` — no run has started;
- `IN_PROGRESS` — the current run can be resumed;
- `COMPLETED` — all mandatory progress is complete;
- `SKIPPED` — the user skipped the tutorial.

The browser stores the state under `cronos:tutorial:v3:user:<userId>:org:<orgId>`.
The persisted object contains only `version`, `tutorialRunId`, `status`, and `stepId`.
The tutorial does not persist chapter data, form values, skipped steps, or demo records.

Opening, exiting, and resuming do not create a new run.
Repeating the tutorial creates a new run identifier.
Invalid or unreadable local state is discarded and replaced with a valid initial state.

### Local actions

The real pages remain mounted inside `TutorialApiBoundary`.
The boundary serves local API-shaped data and applies only the action allowed by the current step.
Reads and permitted writes update the in-memory snapshot before returning a response.
Review mode is read-only and rejects mutating requests.

### Tutorial privacy boundary

The tutorial is local-only. It stores only the resumable checkpoint in browser storage with a 30-day expiry.
It sends no tutorial telemetry and creates no backend record.

## Phase 5: Readiness

After Foundation, the administrator builds the operational bases.
`GET /api/v1/readiness/bases` reports cumulative progress in six depths:

| Depth | Required base | Percentage |
| :---: | :--- | :---: |
| 0 | No base | 0% |
| 1 | Active non-archived class | 17% |
| 2 | Module with positive required minutes | 33% |
| 3 | Active teacher membership with teaching capability | 50% |
| 4 | Valid current-grade class-subject link with an active competent teacher | 67% |
| 5 | Compatible room type and capacity | 83% |
| 6 | At least one possible teacher availability score | 100% |

Depth 6 also requires an active school year.
Without one, the report is blocked with `ACTIVE_SCHOOL_YEAR_REQUIRED`.

Foundation creates the weekly timeslot grid before this chain is evaluated.
The public chain therefore does not expose a separate `TIMESLOTS` step; final prevalidation still blocks generation with `MISSING_TIMESLOTS` if that grid is absent.

`GET /api/v1/readiness/prevalidation?fingerprint=...` performs a pure preflight before generation.
It returns `BLOCKED`, `READY_WITH_WARNINGS`, or `READY` and includes blocker or warning issues.
The fingerprint binds the preflight result to the current bases.
An obsolete fingerprint returns `409` with code `PREFLIGHT_STALE`; run prevalidation again.

## Phase 6: Operational Transition

`GET /api/v1/dashboard` returns a discriminated response:

- `PREPARATION` while `first_real_schedule_approved_at` is empty;
- `OPERATIONAL` after the first real schedule is approved.

Foundation completion does not mean that the school has an operational schedule.
The administrator must configure the bases, generate a real schedule, review it, and approve it.
Only the first real approval changes the dashboard mode.

## Failure Modes

The following matrix maps the visible symptom to the first recovery action.

### Failure and Recovery Matrix

| Symptom | Cause to check | Recovery |
| :--- | :--- | :--- |
| Organization form appears and disappears | Clerk memberships are still loading | Wait for the organization selector to settle, then retry. |
| `503` during bootstrap | Clerk provider directory is unavailable | Retry session activation. Check Clerk configuration and logs. |
| Non-founder cannot open Foundation | Expected permission boundary | Ask the active Clerk organization creator to complete Foundation. |
| `409 FOUNDATION_DRAFT_VERSION_CONFLICT` | Another writer changed the draft | Reload the remote version and save again. |
| `422 FOUNDATION_INCOMPLETE` | Required Foundation field or interval is invalid | Correct the highlighted data and submit again. |
| `409 FOUNDATION_ALREADY_COMPLETED` | A completed organization received another draft write | Refresh member and Foundation status. |
| Dashboard shows preparation after Foundation | Expected until first real schedule approval | Complete readiness, generate, review, and approve a real schedule. |
| Tutorial loses progress | Browser storage was cleared, invalid, or expired, or the user changed scope | Start a new local run. The tutorial never owns operational data. |

## Security and Data Integrity

- Every tenant-owned Foundation, member, readiness, and dashboard record is scoped by `organization_id`.
- PostgreSQL RLS protects tenant rows for the application role.
- Clerk provides identity and organization claims; the backend resolves the local member before protected operations.
- Foundation draft and completion routes allow an uncompleted organization only after Clerk confirms that the active administrator is the organization creator.
- Normal admin and teacher routes require a completed Foundation.
- Draft writes use optimistic versioning and row locks.
- The API commits database writes before it returns a successful response.
- Tutorial demo data stays in browser state and cannot bypass operational authorization.

## Verification Procedure

Use the [Command Reference](COMMAND_REFERENCE.md) for every command below.
Run these checks when you change onboarding behavior:

1. Run `node scripts/test.mjs fast --scope all` during the TDD cycle.
2. Run `node scripts/test.mjs integration` for Foundation, session, or readiness services.
3. Run `node scripts/test.mjs e2e --project isolated` for Foundation journeys and `--project readonly` for tutorial journeys.
4. Open a pull request and wait for the required CI checks.

CI runs the critical selections, the native runtime proof, and the browser E2E journeys.
It does not run the full backend corpus.
Playwright keeps a trace on failure, retains screenshots on failure, and publishes `playwright-report` and `test-results` even when the E2E job fails.
Retries remain disabled (`retries: 0`) so a failed test remains visible.

## Source Map

| Concern | Implementation |
| :--- | :--- |
| Route definitions | [`frontend/src/App.jsx`](../../frontend/src/App.jsx) |
| Route guards | [`frontend/src/routeGuards.jsx`](../../frontend/src/routeGuards.jsx) |
| Organization activation | [`frontend/src/features/onboarding/useOnboardingCompletion.js`](../../frontend/src/features/onboarding/useOnboardingCompletion.js) and [`frontend/src/features/organization/useCreateActiveOrganization.js`](../../frontend/src/features/organization/useCreateActiveOrganization.js) |
| Foundation wizard | [`frontend/src/features/foundation/components/FoundationWizard.jsx`](../../frontend/src/features/foundation/components/FoundationWizard.jsx) |
| Foundation model | [`frontend/src/features/foundation/foundationModel.js`](../../frontend/src/features/foundation/foundationModel.js) |
| Foundation data hooks | [`frontend/src/features/foundation/foundationData.js`](../../frontend/src/features/foundation/foundationData.js) |
| Tutorial scenario | [`frontend/src/features/tutorial/tutorialScenario.js`](../../frontend/src/features/tutorial/tutorialScenario.js) |
| Tutorial reducer and storage | [`frontend/src/features/tutorial/tutorialModel.js`](../../frontend/src/features/tutorial/tutorialModel.js) and [`frontend/src/features/tutorial/tutorialStorage.js`](../../frontend/src/features/tutorial/tutorialStorage.js) |
| Tutorial boundary | [`frontend/src/features/tutorial/TutorialWorkspace.jsx`](../../frontend/src/features/tutorial/TutorialWorkspace.jsx) |
| Session bootstrap | [`backend/app/api/v1/endpoints/session.py`](../../backend/app/api/v1/endpoints/session.py) |
| Foundation API | [`backend/app/api/v1/endpoints/foundation.py`](../../backend/app/api/v1/endpoints/foundation.py) |
| Foundation service | [`backend/app/services/foundation_service.py`](../../backend/app/services/foundation_service.py) |
| Readiness service | [`backend/app/services/school_readiness_service.py`](../../backend/app/services/school_readiness_service.py) |
| Dashboard service | [`backend/app/services/dashboard_service.py`](../../backend/app/services/dashboard_service.py) |
| Database transaction scope | [`backend/app/api/deps.py`](../../backend/app/api/deps.py) |
| CI workflow | [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) |

## Related Documents

- [Getting Started Index](README.md)
- [Technical Walkthrough](TECHNICAL_WALKTHROUGH.md)
- [Data Model](../01_system_architecture/DATA_MODEL.md)
- [Runtime Flows](../01_system_architecture/RUNTIME_FLOWS.md)
- [School Configuration](../02_domain_model/SCHOOL_CONFIGURATION.md)
- [API Reference](../05_backend_api/API_REFERENCE.md)
- [Frontend Architecture](../06_frontend_ux/FRONTEND_ARCHITECTURE.md)
- [Routes and Permissions](../06_frontend_ux/ROUTES_AND_PERMISSIONS.md)
- [Testing and CI](../08_security_quality/TESTING_AND_CI.md)
