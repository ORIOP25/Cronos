# Frontend Architecture

## Purpose

This document describes the React SPA, route composition, client state, authentication, and API transport.

## Intended Reader

This document targets React engineers and UI maintainers.

## Prerequisites

Read [Routes and Permissions](ROUTES_AND_PERMISSIONS.md) and [Design System](DESIGN_SYSTEM.md).

## What the System Does

The frontend uses React 19, Vite 8, React Router, Clerk, Axios, and TanStack React Query.
One Vite entry point serves the public marketing routes and authenticated application.

## Why the Behavior Exists

Lazy route loading keeps the initial bundle small.
React Query manages server state while component state handles form and view state.

## Components and Ownership

| Area | Implementation |
| :--- | :--- |
| Entry and providers | `frontend/src/main.jsx`, `UserQueryProvider.jsx` |
| Routes | `frontend/src/App.jsx` |
| Auth guards | `frontend/src/routeGuards.jsx`, `roleAccess.js` |
| API transport | `frontend/src/apiClient.js` |
| Server state | `frontend/src/queryClient.js`, `frontend/src/features/*/data.js` |
| Feature directories | `frontend/src/features/` |
| Authenticated layout | `frontend/src/components/DefaultLayout.jsx` |
| Global transient feedback | `frontend/src/components/AppToaster.jsx` |
| Shared application states | `frontend/src/components/FeedbackBanner.jsx`, `StatePanel.jsx` |
| Guided forms | `frontend/src/components/GuidedFormShell.jsx`, `GuidedFormProgress.jsx` |
| Marketing layout | `frontend/src/features/marketing/components/layout/MarketingLayout.jsx` |
| Marketing content | `frontend/src/features/marketing/` and `frontend/src/pages/marketing/` |
| Marketing metadata | `frontend/src/features/marketing/content/metadata.js` |

## Data or Request Flow

1. `main.jsx` mounts `ClerkProvider`, `ErrorBoundary`, `UserQueryProvider`, and one `AppToaster`.
2. `App.jsx` selects public, signed-in, admin, or teacher routes.
3. Clerk provides an organization-scoped token getter.
4. `apiClient` attaches the token to authenticated Axios requests.
5. Feature hooks read or mutate API data through React Query.
6. Pages and components emit short results with `react-hot-toast` after an attempt.
7. Public contact uses `fetch` and does not use the Clerk interceptor.

## Contracts and Invariants

- `VITE_API_BASE_URL` defaults to `/api/v1`.
- Class header edits use the course-scoped mutation in [catalog data hooks](../../frontend/src/features/catalog/data.js).
- Mutations do not retry.
- Queries retry at most twice for network, `408`, `429`, and `5xx` errors.
- Teacher routes require a teacher capability and linked profile.
- Pages and components must not import TanStack hooks or `apiClient` directly.
  They compose feature data hooks. The ESLint configuration enforces this rule.
- Feature data hooks live in the feature directories, for example `frontend/src/features/*/data.js`.
- One `AppToaster` instance owns durations, position, and theming for transient feedback.
- Success and information toasts last 4000 ms. Transient error toasts last 6000 ms.
- The toast position is `top-right` from 768 px and `top-center` below that width.
- `App.jsx` removes visible toasts when the user or organization changes.
- `hooks/useAttemptScope.js` guards async results with the identity that started them.
- A stale result emits no feedback and changes no draft.
- Field validation stays next to the field or group. Validation never uses a toast.
- The [Feedback Message Matrix](FEEDBACK_MESSAGE_MATRIX.md) records the channel and owner per operation.
- Toasts carry short Portuguese text. Errors use `role="alert"`; other toasts use `role="status"`. A toast never holds a required action.
- Field errors use `aria-invalid` and `aria-describedby`, keep existing descriptions, and focus the first invalid field after a failed submit.
- Classify API errors with `getApiErrorCode` and `getApiErrorPresentation`, never by searching message text.
- Failures of polling or autosave stay in a readable state near the indicator, not in a toast sequence.
- Marketing styles use the `cronos-*` namespace.
- `metadata.js` is the single source for public route metadata.
- The build emits one HTML file for each route in `metadata.js`, plus `404.html`.
- Marketing pages render on the client and as build-time static HTML.
- Nginx serves pre-rendered marketing pages with `try_files $uri $uri.html =404`.
- Nginx serves application routes from `app-shell.html`.
- The tutorial uses `TUTORIAL_VERSION` 3 and a 13-step guide.

## States and Transitions

Bulk removal lets administrators select visible courses, classes, subjects, rooms, or eligible members.
It asks for one confirmation, then calls the existing removal action for each selected record.
The operation reports individual failures and keeps those records selected. Successful removals do not roll back.
Room confirmations include the effects on fixed-room assignments. Changing organization clears the selection and feedback.

Route guards move through loading, signed-out, organization selection, member error, or authorized states.
Contact submission moves through questionnaire steps, pending, error, and success states.
Foundation moves through ten validated steps, draft persistence, conflict, and completion states.
Availability keeps persisted server data separate from a local paint draft.
The member editor opens administrative availability with the member's teacher identifier and preserves its profile draft on return.
Successful access actions update the editor's optimistic version without discarding edited fields. Removal closes the editor.
Occurrence links include their school date. Availability queries keep each date's grid in a separate cache entry.
Unknown teacher links show an explicit error instead of an unidentified grid.
Course creation includes a filled initial class draft. Incomplete edited drafts block submission and retain their values.
Import downloads show preparation on the selected model and success or failure through a visible toast.
Mobile debt cards show the class, subject, teacher, gaps, and duration without a wide table.
Dashboard debt values use the same duration formatter and debt tab as the occurrence page.
Published schedule conflicts require attention. An expandable schedule health list identifies affected blocks and links to each teacher week.
Class progress keeps its existing filters and starts with a compact preview. The expansion control exposes the full filtered list.
Teacher progress starts with collapsed class disclosures. Class module details open automatically while editing progress.
Proposal priority analysis is optional disclosure content. Generation warnings and approval actions stay outside that disclosure.
Generation job polling keeps the last known job state and retries a transient poll failure on the fixed interval. The indicator shows the inline error meanwhile. Polling stops on a terminal status or a permanent client error. See [scheduling data hooks](../../frontend/src/features/scheduling/data.js).
Rejecting a draft refreshes the active organization's status, current-draft, diff, and preparation caches without invalidating the published `weekSchedule`. Another organization's caches stay untouched, and the pending-draft prevalidation warning clears once the preparation query refetches.
The Horários grid can preview the pending proposal in read-only mode. The "Horário publicado / Proposta pendente" toggle appears only when the proposal is not stale and the user can generate. The preview adds `proposal_id` to the week query and disables lesson logging. The mode is held in memory, so approval or rejection returns the grid to the published week.

## Failure Modes

- Missing Clerk configuration blocks authenticated startup.
- A `401` member request offers organization-session recovery.
- A `403` member request displays an access message.
- API errors use normalized messages from `frontend/src/utils/apiErrors.js`.
- Shared state panels render loading, error, and empty states.
- Persistent warnings and business blocks use `FeedbackBanner` near the affected content.
- Business blocks stay in context. Transient recoverable failures use toasts.

## Verification Procedure

1. Run `npm ci` inside `frontend/`.
2. Run `npm run audit:production`.
3. Run `npm run verify`.
4. Run the complete verification command before integration.

## Source Map

- `frontend/src/main.jsx`
- `frontend/src/App.jsx`
- `frontend/src/components/AppToaster.jsx`
- `frontend/src/hooks/useAttemptScope.js`
- `frontend/src/apiClient.js`
- `frontend/src/queryClient.js`
- `frontend/src/styles/brand.tokens.css`
- `frontend/src/styles/app-shell.css`
- `frontend/src/routeGuards.jsx`
- `frontend/Dockerfile`
- `frontend/nginx.conf` (production)
- `frontend/nginx.ci.conf` (CI and the Dockerfile `local` target)

## Onboarding Frontend Architecture

The onboarding path is split into independent features:

- `routeGuards.jsx` waits for Clerk, the active organization, and `/members/me` before routing.
- For an incomplete organization, `/members/me` exposes `can_manage_foundation` after the backend verifies the active administrator against Clerk's organization creator.
  Completed organizations route by member role without another creator lookup.
- `useOnboardingCompletion.js` waits for the Clerk organization, bootstraps the local member, and completes legal acceptance without an intermediate route.
- `FoundationWizard.jsx` owns the ten-step interaction, autosave queue, version conflict state, and completion navigation.
- `foundationModel.js` contains pure step and validation rules.
- `foundationData.js` owns React Query keys and invalidation.
- `features/tutorial/` owns local scenario state, reducer transitions, normalization, expiring storage, and the API boundary.
  It renders a 13-step guide under `TUTORIAL_VERSION` 3 and uses a mock Axios adapter.

Foundation completion invalidates `foundation-status`, `foundation-draft`, `current-member`, dashboard, and readiness queries as one mutation lifecycle.
The real dashboard passes `autoStartGuide={false}` so the post-completion destination is stable.
The tutorial can still be opened explicitly from the dashboard or `/guide`.

## Related Documents

- [Feedback Message Matrix](FEEDBACK_MESSAGE_MATRIX.md)
- [Routes and Permissions](ROUTES_AND_PERMISSIONS.md)
- [Design System](DESIGN_SYSTEM.md)
- [Accessibility](ACCESSIBILITY.md)
