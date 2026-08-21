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
| Server state | `frontend/src/queryClient.js`, `features/*/data.js` |
| Authenticated layout | `frontend/src/components/DefaultLayout.jsx` |
| Shared application states | `frontend/src/components/FeedbackBanner.jsx`, `StatePanel.jsx` |
| Guided forms | `frontend/src/components/GuidedFormShell.jsx`, `GuidedFormProgress.jsx` |
| Marketing layout | `frontend/src/features/marketing/components/layout/MarketingLayout.jsx` |
| Marketing content | `frontend/src/features/marketing/` and `frontend/src/pages/marketing/` |
| Marketing metadata | `frontend/src/features/marketing/content/metadata.js` |

## Data or Request Flow

1. `main.jsx` mounts `ClerkProvider`, `ErrorBoundary`, and `UserQueryProvider`.
2. `App.jsx` selects public, signed-in, admin, or teacher routes.
3. Clerk provides an organization-scoped token getter.
4. `apiClient` attaches the token to authenticated Axios requests.
5. Feature hooks read or mutate API data through React Query.
6. Public contact uses `fetch` and does not use the Clerk interceptor.

## Contracts and Invariants

- `VITE_API_BASE_URL` defaults to `/api/v1`.
- Mutations do not retry.
- Queries retry at most twice for network, `408`, `429`, and `5xx` errors.
- Teacher routes require a teacher capability and linked profile.
- Marketing styles use the `cronos-*` namespace.
- `metadata.js` is the single source for public route metadata.
- The build emits `index.html` and five route HTML files.
- Nginx resolves deep links with `try_files $uri $uri.html $uri/ /index.html`.

## States and Transitions

Route guards move through loading, signed-out, organization selection, member error, or authorized states.
Contact submission moves through questionnaire steps, pending, error, and success states.
Foundation moves through nine validated steps, draft persistence, conflict, and completion states.
Availability keeps persisted server data separate from a local paint draft.

## Failure Modes

- Missing Clerk configuration blocks authenticated startup.
- A `401` member request offers organization-session recovery.
- A `403` member request displays an access message.
- API errors use normalized messages from `frontend/src/utils/apiErrors.js`.
- Shared state panels render loading, error, and empty states.
- Feedback banners render mutation success and error messages near the affected action.

## Verification Procedure

1. Run `npm ci` inside `frontend/`.
2. Run `npm run audit:production`.
3. Run `npm run verify`.
4. Run `npm run test:school-config:stability`.

## Source Map

- `frontend/src/main.jsx`
- `frontend/src/App.jsx`
- `frontend/src/apiClient.js`
- `frontend/src/queryClient.js`
- `frontend/src/styles/brand.tokens.css`
- `frontend/src/styles/app-shell.css`
- `frontend/src/routeGuards.jsx`
- `frontend/Dockerfile`
- `frontend/nginx.conf`

## Related Documents

- [Routes and Permissions](ROUTES_AND_PERMISSIONS.md)
- [Design System](DESIGN_SYSTEM.md)
- [Accessibility](ACCESSIBILITY.md)
