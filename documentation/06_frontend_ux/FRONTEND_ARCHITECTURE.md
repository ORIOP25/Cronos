# Frontend Architecture

## Purpose
This document details React 19 application structure, Vite build configuration, React Query cache management, and UI component hierarchy.

## Intended Reader
This document targets frontend React engineers and UI designers.

## Prerequisites
Read the [Project Overview](../00_getting_started/PROJECT_OVERVIEW.md).

## What the System Does
The frontend is a single-page application (SPA) built with React 19 and Vite 8. It communicates with the backend REST API using `@tanstack/react-query` and standard `fetch` API calls.

## Component Hierarchy Structure

```text
App.jsx (Layout Router & Clerk Provider)
├── DefaultLayout (Navigation Sidebar & Header)
│   ├── PageHeader (Breadcrumbs & Action Buttons)
│   └── Page Components (/dashboard, /schedules, /members, etc.)
│       ├── SmartTable (Paginated & Filterable Data Grid)
│       ├── GenericModalForm (Create/Edit Modal Dialogs)
│       └── Feature Widgets (KPISidebar, DraftPanel, AlertBar)
```

## State Management and Caching Strategy
- **Server State**: Managed via TanStack React Query (`queryClient.js`). Key invalidations trigger automatic refetching after mutations.
- **Client UI State**: Component-local React `useState` and `useReducer` hooks.
- **Auth & Session State**: Managed via Clerk `@clerk/clerk-react` hooks (`useAuth`, `useUser`, `useClerk`).

## Contracts and Invariants
- All authenticated API requests must include the Clerk Bearer JWT fetched via `useAuth().getToken()`.
- Public landing page (`MarketingSite.jsx`) uses isolated CSS namespaces (`cronos-*`) to prevent style bleeding.

## Failure Modes
- Network Failure: React Query automatically retries failed requests based on configured retry parameters. Displays error callout widget on total failure.

## Verification Procedure
Run frontend test suite: `cd frontend && npm run test`. Verify zero failing Vitest components.

## Source Map
- App Entry: `frontend/src/main.jsx`
- Layout Router: `frontend/src/App.jsx`
- Query Client: `frontend/src/queryClient.js`
- API Client: `frontend/src/apiClient.js`

## Related Documents
- [Routes and Permissions](ROUTES_AND_PERMISSIONS.md)
- [Design System](DESIGN_SYSTEM.md)
