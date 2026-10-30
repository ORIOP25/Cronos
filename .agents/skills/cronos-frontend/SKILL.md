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

## UI and copy consistency

- Read the [Design System](../../../documentation/06_frontend_ux/DESIGN_SYSTEM.md) before adding page-specific controls or styles. Reuse the existing pattern for equivalent actions.
- Use `PageHeader` for the compact page title and action group. Do not add a second hero, greeting or section label above it.
- Reuse the existing table, form modal, confirmation, feedback and disclosure components. Keep optional explanations collapsed; keep actions, validation and required warnings visible.
- Use PT-PT and sentence case. Reuse common action labels from `frontend/src/utils/terminology.js`; follow the [copy contract](../../../documentation/06_frontend_ux/FRONTEND_ARCHITECTURE.md#contracts-and-invariants).
- Distinguish opening a form, creating a record, saving edits and applying a local draft. Keep removal, archival and restoration distinct.
- Use Cancelar for unsaved edits and Fechar for consultation or a clean availability editor. Preserve the existing close and partial-save behavior.
- Name the action in confirmations and busy states. Keep impact warnings and specific recovery guidance; do not promise behavior the code does not guarantee.
- Translate technical terms in the presentation layer. Preserve API/CSV field names, error codes and validation rules.
- Update tooltips, accessible names, tutorial instructions and test selectors with the visible copy. Shared test helpers must target the correct creation or editing action.

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

- For behavior changes, a failing Vitest test existed first and now passes.
- `npm run verify:checks` passes, and the pull request names it.
- The local frontend container is rebuilt.
- [Routes and Permissions](../../../documentation/06_frontend_ux/ROUTES_AND_PERMISSIONS.md) and [Frontend Architecture](../../../documentation/06_frontend_ux/FRONTEND_ARCHITECTURE.md) reflect any route or data-ownership change.
- New UI patterns and terminology follow the linked contracts. Update the owning guide when a new convention is necessary.

## Documentation

- [Frontend Architecture](../../../documentation/06_frontend_ux/FRONTEND_ARCHITECTURE.md)
- [Routes and Permissions](../../../documentation/06_frontend_ux/ROUTES_AND_PERMISSIONS.md)
- [Accessibility](../../../documentation/06_frontend_ux/ACCESSIBILITY.md)
