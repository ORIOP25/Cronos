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
- Use an organization administrator for the Foundation flow.
- Read [Routes and Permissions](../06_frontend_ux/ROUTES_AND_PERMISSIONS.md) for the complete access matrix.

## What the System Does

Cronos guides a new organization from Clerk activation to a committed school grid and the first real schedule approval.
It keeps the optional product tutorial separate from operational data.

## Why the Behavior Exists

The route gate protects operational features until the organization has a valid calendar grid.
The draft protocol protects concurrent administrators.
The local tutorial lets users learn the product without mutating the tenant.

## Components and Ownership

| Area | Owner |
| :--- | :--- |
| Clerk activation and tenant bootstrap | Clerk provider, session endpoint, organization feature |
| Foundation validation and persistence | Foundation wizard, Foundation service, organization tables |
| Tutorial simulation | Tutorial reducer, scenario, storage, telemetry, and API boundary |
| Readiness and dashboard mode | Readiness service and dashboard service |
| Route access | React route guards and FastAPI actor dependencies |

## Data or Request Flow

The route decision and the six onboarding phases below describe the request flow.

## Contracts and Invariants

Cronos uses four separate milestones:

1. Clerk authenticates the user and selects an organization.
2. An organization administrator completes the Foundation.
3. The administrator may use the local tutorial to learn the product.
4. The school configures the operational bases and approves the first real schedule.

Foundation completion is required before normal authenticated features become available.
The tutorial is optional and does not replace Foundation or create operational data.

## States and Transitions

The frontend waits for Clerk and the current member before it selects a route.
Do not interpret a loading screen as a missing permission.

| Condition | Destination | Reason |
| :--- | :--- | :--- |
| User is signed out | `/login` | Authentication is required. |
| User has no organization or membership | `/create-org` | The user must create or join an organization. |
| User has memberships but no active organization | Organization selector | The user must choose the tenant context. |
| Active organization, administrator, Foundation incomplete | `/foundation` | The administrator can complete the required setup. |
| Active organization, non-administrator, Foundation incomplete | `/foundation/waiting` | Only a Foundation administrator can complete setup. |
| Active organization, Foundation complete, administrator | `/dashboard` | The user can use administrative features. |
| Active organization, Foundation complete, teacher | `/my-availability` | The default teacher route is teacher availability. |

`/guide` is an explicit tutorial route. The real dashboard does not redirect to it automatically after Foundation completion.
The dashboard provides **Repetir guia** and **Retomar guia** actions when applicable.

## Phase 1: Create or Select the Organization

### Start the session

1. Open the application.
2. Sign in with Clerk.
3. Wait for Clerk to load the organization list.
4. Select an active organization, or open `/create-org` when no membership exists.

The frontend does not render the organization creation form while the Clerk membership list is still loading.
This prevents a transient empty list from replacing the form after the page has started.

### Create an organization

When the user has no membership:

1. Enter the school name.
2. Submit the form.
3. Wait for Clerk to create the organization and the membership.
4. Activate the new organization.
5. Wait for `POST /api/v1/session/bootstrap` to reconcile the local member.

The activation state is kept in session storage so the user can resume after a transient reload.
The backend bootstrap requires the Clerk subject, the active organization claim, and an administrator role.
It reconciles the provider organization and membership with the tenant database.

### Bootstrap response

`POST /api/v1/session/bootstrap` returns:

- the local organization;
- the current member;
- the current `foundation_status`.

The backend returns `503` when the Clerk provider directory is unavailable.
The frontend must show a recoverable session error and allow the user to retry.

## Phase 2: Complete the Foundation

### Access and state

The Foundation has three states:

| State | Meaning | Admin access |
| :--- | :--- | :--- |
| `NOT_STARTED` | No completed setup exists. | Open `/foundation`. |
| `IN_PROGRESS` | A draft exists. | Resume the draft. |
| `COMPLETED` | The grid and settings are committed. | Continue to `/dashboard`. |

The Foundation administrator can open the draft before completion.
Other members see `/foundation/waiting` until an administrator completes it.

### Nine wizard steps

The wizard uses nine ordered steps:

1. **Period** — set `school_start_date` and `school_hard_end_date`.
2. **Days** — select one or more `days_of_week` values from `0` to `6`.
3. **Opening** — set `opening_time` and `closing_time`.
4. **Slot duration** — set `slot_duration_minutes` from `15` to `120`.
5. **Break duration** — set `break_duration_minutes` from `0` to `60`.
6. **Lunch** — set lunch start, end, and minimum duration.
7. **Preview** — inspect the calculated grid.
8. **Calendar** — confirm the calendar period and available days.
9. **Confirmation** — confirm the complete snapshot.

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
| Read draft | `GET /api/v1/foundation/draft` | Foundation administrator | Version, current step, and data. |
| Save draft | `PUT /api/v1/foundation/draft` | Foundation administrator | New version and saved snapshot. |
| Complete | `POST /api/v1/foundation/complete` | Foundation administrator | Committed settings and generated timeslot count. |

Every draft write includes `expected_version`.
The server locks the draft row, checks the version, validates the data, and flushes the new version.
The function-scoped database dependency commits before the HTTP response is sent.

### Version conflict

If another tab or administrator updates the draft first, the API returns `409` with code `FOUNDATION_DRAFT_VERSION_CONFLICT`.

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

### Tutorial telemetry

The frontend emits telemetry to `POST /api/v1/tutorial/telemetry` as the Foundation administrator.
Telemetry is best effort and never blocks the local tutorial.
Each event contains a tutorial run ID, a client event ID, version, event name, and optional chapter or step.
The backend deduplicates the client event ID inside the organization.

Supported event names are:

`tutorial_opened`, `chapter_started`, `tutorial_exited`, `tutorial_completed`, and `tutorial_repeated`.

## Phase 5: Readiness

After Foundation, the administrator builds the operational bases.
`GET /api/v1/readiness/bases` reports cumulative progress in seven depths:

| Depth | Required base | Percentage |
| :---: | :--- | :---: |
| 0 | No base | 0% |
| 1 | Active non-archived class | 14% |
| 2 | Module with positive required minutes | 28% |
| 3 | Valid class-subject link for the current grade on a subject with modules | 42% |
| 4 | Active competent teacher assigned to the class subject | 57% |
| 5 | Compatible room type and capacity | 71% |
| 6 | At least one generated timeslot | 85% |
| 7 | At least one possible teacher availability score | 100% |

Depth 7 also requires an active school year.
Without one, the report is blocked with `ACTIVE_SCHOOL_YEAR_REQUIRED`.

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
| Non-admin cannot open Foundation | Expected permission boundary | Ask an organization administrator to complete Foundation. |
| `409 FOUNDATION_DRAFT_VERSION_CONFLICT` | Another writer changed the draft | Reload the remote version and save again. |
| `422 FOUNDATION_INCOMPLETE` | Required Foundation field or interval is invalid | Correct the highlighted data and submit again. |
| `409 FOUNDATION_ALREADY_COMPLETED` | A completed organization received another draft write | Refresh member and Foundation status. |
| Dashboard shows preparation after Foundation | Expected until first real schedule approval | Complete readiness, generate, review, and approve a real schedule. |
| Tutorial loses progress | Browser storage was cleared or invalid | Start a new local run. The tutorial never owns operational data. |
| Telemetry request fails | Provider or network error | Continue the tutorial. Inspect logs later; telemetry is non-blocking. |

## Security and Data Integrity

- Every tenant-owned Foundation, member, readiness, dashboard, and telemetry record is scoped by `organization_id`.
- PostgreSQL RLS protects tenant rows for the application role.
- Clerk provides identity and organization claims; the backend resolves the local member before protected operations.
- Foundation routes allow an uncompleted organization only through the explicit Foundation administrator allowlist.
- Normal admin and teacher routes require a completed Foundation.
- Draft writes use optimistic versioning and row locks.
- The API commits database writes before it returns a successful response.
- Tutorial demo data stays in browser state and cannot bypass operational authorization.

## Verification Procedure

Run the focused checks when changing onboarding behavior:

```text
cd backend
pytest tests/ -v
alembic check
cd ../frontend
npm run audit:production
npm run verify
npx playwright test e2e/auth e2e/foundation e2e/tutorial
```

The repository CI also runs the full backend, frontend, and E2E suites.
Playwright keeps a trace on failure, retains screenshots on failure, and publishes `playwright-report` and `test-results` even when the E2E job fails.
Retries remain disabled (`retries: 0`) so a failed test remains visible.

## Source Map

| Concern | Implementation |
| :--- | :--- |
| Route definitions | [`frontend/src/App.jsx`](../../frontend/src/App.jsx) |
| Route guards | [`frontend/src/routeGuards.jsx`](../../frontend/src/routeGuards.jsx) |
| Organization activation | [`frontend/src/pages/CreateOrgPage.jsx`](../../frontend/src/pages/CreateOrgPage.jsx) and [`frontend/src/features/organization/useCreateActiveOrganization.js`](../../frontend/src/features/organization/useCreateActiveOrganization.js) |
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
