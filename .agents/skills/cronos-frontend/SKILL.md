---
name: cronos-frontend
description: Cronos frontend skill. Use for React 19 pages, routes and guards, TanStack Query data hooks, Clerk UI flows, forms, components, the tutorial, the marketing site, and frontend tests.
---

# Cronos Frontend

Load `cronos-base` and `ponytail` first. Load `cronos-frontend-designer` for visual work.

## Start here

- Routes: `frontend/src/App.jsx`. Guards: `frontend/src/routeGuards.jsx` (`RequireAdmin`, `RequireTeacher`, `MemberGate`). Role helpers: `frontend/src/roleAccess.js`.
- Navigation: `frontend/src/components/appNavigation.js`.
- Data hooks: `frontend/src/features/<area>/data.js`. Query keys and invalidation: `frontend/src/features/queryKeys.js`.
- API client: `useApiClient()` from `frontend/src/ApiClientContext.jsx` attaches the organization-scoped Clerk token.
- Error messages: `frontend/src/utils/apiErrors.js` (`getApiErrorMessage`) and the [Feedback Message Matrix](../../../documentation/06_frontend_ux/FEEDBACK_MESSAGE_MATRIX.md).

## Reference implementation

Copy Rooms for a new list-and-form feature:
`frontend/src/pages/Rooms.jsx` + `frontend/src/components/Forms/RoomForm.jsx` + the `useRooms`, `useCreateRoom`, `useUpdateRoom`, and `useDeleteRoom` hooks in `frontend/src/features/catalog/data.js` + `frontend/src/test/RoomForm.test.jsx`.
Drop the tutorial props (`allowedActions`, `readOnly`, `data-tutorial-target`) unless the tutorial uses the page.

## Minimal proof

- `node scripts/test.mjs fast --scope frontend -- <test file>` during TDD.
- `npm run verify:checks` in `frontend/` before the pull request.
- `node scripts/test.mjs e2e --project <name> -- -g <test title>` for a changed user journey, when Clerk test inputs exist.
- Rebuild the local stack from the worktree that holds the change. See [Local stack in a worktree](../../../documentation/00_getting_started/COMMAND_REFERENCE.md#local-stack-in-a-worktree).

## Boundaries

- Pages and components never call `apiClient` or `fetch` directly. ESLint and architecture tests enforce this; use a `data.js` hook.
- The client guard is UX only. The backend enforces permissions; never rely on the frontend for security.
- Keep exact Portuguese UI labels and domain terms.
- Every query key is organization-scoped through `orgQueryKey`.

## Pitfalls

- Mutations list the query roots they invalidate by hand. A new query key must join every related invalidation list.
- The tutorial reuses real pages and mocks the API in `frontend/src/features/tutorial/tutorialApiAdapter.js`. New endpoints used by tutorial pages need adapter entries.
- A new public page must be added to `App.jsx`, `features/marketing/renderPublicRoute.jsx`, `features/marketing/content/metadata.js`, and `features/marketing/content/navigation.js`.
- The contact form uses native `fetch` in `features/contact/data.js`, not `apiClient`.
- Large files: `features/schoolConfig/SchoolConfigSections.jsx`, `pages/Occurrences.jsx`, and `index.css`. Read only the section you need.
- Some page tests mock the data hooks, so they cannot detect a wrong endpoint. Cover new hooks in `frontend/src/test/featureDataHooks.test.jsx` or with MSW in the `dom-network` project.

## Done when

- A failing Vitest test existed first and now passes.
- `npm run verify:checks` passes, and the pull request names it.
- The local frontend container is rebuilt.
- [Routes and Permissions](../../../documentation/06_frontend_ux/ROUTES_AND_PERMISSIONS.md) and [Frontend Architecture](../../../documentation/06_frontend_ux/FRONTEND_ARCHITECTURE.md) reflect any route or data-ownership change.

## Documentation

- [Frontend Architecture](../../../documentation/06_frontend_ux/FRONTEND_ARCHITECTURE.md)
- [Routes and Permissions](../../../documentation/06_frontend_ux/ROUTES_AND_PERMISSIONS.md)
- [Accessibility](../../../documentation/06_frontend_ux/ACCESSIBILITY.md)
