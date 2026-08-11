# Frontend Architecture

## Purpose
This document details React 19 application structure, Vite build configuration, React Query cache management, and UI component hierarchy.

## Intended Reader
This document targets frontend React engineers and UI designers.

## Prerequisites
Read the [Project Overview](../00_getting_started/PROJECT_OVERVIEW.md).

## What the System Does
The frontend is a React 19 and Vite 8 SPA. It uses TanStack React Query and an Axios API client.

## Component Hierarchy Structure

```text
main.jsx (Clerk, Query, and User Providers)
└── App.jsx (Lazy Route Definitions)
    ├── DefaultLayout (Navigation Sidebar & Header)
    │   ├── PageHeader (Breadcrumbs & Action Buttons)
    │   └── Page Components (/dashboard, /schedules, /members, etc.)
    │       ├── SmartTable (Reusable Data Table)
    │       ├── GenericModalForm (Create/Edit Modal Dialogs)
    │       └── Feature Widgets (KPISidebar, DraftPanel, AlertBar)
    └── MarketingSite (Public Landing Page Assembler)
        ├── MarketingHeader & MarketingFooter
        ├── HeroSection & ServiceStrip
        ├── ProductValueSection & ProcessStepperSection
        ├── GeneratorSection & RoutineSection
        ├── RolesSection & AboutFounderSection
        └── TestimonialsMarquee & ContactQuestionnaire
```

## State Management and Caching Strategy
- **Server State**: Managed via TanStack React Query (`queryClient.js`). Key invalidations trigger automatic refetching after mutations.
- **Client UI State**: Component-local React `useState` and `useReducer` hooks. Section-local state isolated within memoized marketing components.
- **Static Content**: Extracted static data arrays maintained in `frontend/src/data/marketingData.js`.
- **Auth & Session State**: Managed via Clerk `@clerk/react` hooks and `UserQueryProvider.jsx`.

## Performance and Rendering Optimization
- **Hardware Acceleration**: Marquee rows use GPU layer promotion (`will-change: transform; transform: translate3d(0,0,0)`). Edge masks use fixed CSS pseudo-elements instead of continuous gradient mask recalculations.
- **Off-Screen Content**: Below-the-fold marketing sections use `content-visibility: auto; contain-intrinsic-size: 800px;` to defer rendering until scrolled into view.
- **Asset Strategy**: Marketing graphics use optimized WebP formats (`<picture>` elements with PNG fallbacks). Below-the-fold images use `loading="lazy"` and `decoding="async"`. The Hero LCP asset uses `loading="eager"`.

## Contracts and Invariants
- All authenticated API requests must include the Clerk Bearer JWT fetched via `useAuth().getToken()`.
- Public landing page (`MarketingSite.jsx`) uses isolated CSS namespaces (`cronos-*`) to prevent style bleeding.

## Failure Modes
- Network Failure: Queries retry at most twice for network, `408`, `429`, and server errors. Mutations do not retry.

## Verification Procedure
Run frontend test suite: `cd frontend && npm run test`. Verify zero failing Vitest components.

## Source Map
- App Entry: `frontend/src/main.jsx`
- Layout Router: `frontend/src/App.jsx`
- Query Client: `frontend/src/queryClient.js`
- API Client: `frontend/src/apiClient.js`
- Marketing Page Assembler: `frontend/src/pages/MarketingSite.jsx`
- Marketing Components: `frontend/src/components/marketing/`
- Marketing Data: `frontend/src/data/marketingData.js`

## Related Documents
- [Routes and Permissions](ROUTES_AND_PERMISSIONS.md)
- [Design System](DESIGN_SYSTEM.md)
