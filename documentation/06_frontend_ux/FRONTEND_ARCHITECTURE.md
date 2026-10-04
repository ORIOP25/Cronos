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
- Marketing styles use the `cronos-*` namespace.
- `metadata.js` is the single source for public route metadata.
- The build emits one HTML file for each route in `metadata.js`, plus `404.html`.
- Marketing pages render on the client and as build-time static HTML.
- Nginx serves pre-rendered marketing pages with `try_files $uri $uri.html =404`.
- Nginx serves application routes from `app-shell.html`.
- The tutorial uses `TUTORIAL_VERSION` 3 and a 13-step guide.

## States and Transitions

Route guards move through loading, signed-out, organization selection, member error, or authorized states.
Contact submission moves through questionnaire steps, pending, error, and success states.
Foundation moves through ten validated steps, draft persistence, conflict, and completion states.
Availability keeps persisted server data separate from a local paint draft.
The team action opens administrative availability with the member's teacher identifier.
Occurrence links include their school date. Availability queries keep each date's grid in a separate cache entry.
Unknown teacher links show an explicit error instead of an unidentified grid.
Course creation includes a filled initial class draft. Incomplete edited drafts block submission and retain their values.
Import downloads show preparation on the selected model and success or failure through a visible toast.
Mobile debt cards show the class, subject, teacher, gaps, and duration without a wide table.

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
- `frontend/nginx.conf`

## Onboarding Frontend Architecture

The onboarding path is split into independent features:

- `routeGuards.jsx` waits for Clerk, the active organization, and `/members/me` before routing.
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

- [Routes and Permissions](ROUTES_AND_PERMISSIONS.md)
- [Design System](DESIGN_SYSTEM.md)
- [Accessibility](ACCESSIBILITY.md)
