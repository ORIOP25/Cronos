# Cronos Frontend Workspace

React 19 single-page application (SPA) for Cronos, built with Vite 8.

## Technology Stack
- React 19
- Vite 8
- React Router
- Clerk Authentication (`@clerk/react`)
- CoreUI
- TanStack React Query (`@tanstack/react-query`)
- Vitest
- Playwright E2E

## Development Commands

```bash
# Install dependencies
npm install

# Start local dev server
npm run dev

# Build production bundle
npm run build

# Run Vitest unit tests
npm run test

# Run test coverage
npm run test:coverage

# Run ESLint check
npm run lint

# Run dead code check (Knip)
npm run lint:dead-code

# Run Playwright E2E tests
npm run test:e2e

# Run the complete local frontend verification
npm run verify

# Check production-only source rules
npm run audit:production

# Check school configuration stability
```

## Public Marketing Site
The public marketing landing page resides in:
- Page Assembler: `src/pages/MarketingSite.jsx`
- Section Components: `src/components/marketing/` (`TestimonialsMarquee.jsx`, `ContactQuestionnaire.jsx`, etc.)
- Static Data: `src/data/marketingData.js`
- Styles: `src/pages/MarketingSite.css`
- Optimized WebP Graphics: `public/marketing/*.webp`

Marketing site CSS classes use the `cronos-*` namespace to isolate styles from authenticated application pages. Continuous animations use GPU hardware layer promotion (`translate3d`). Below-the-fold sections use `content-visibility: auto`.

## Route Summary Table

| Path | View Component | Access Requirement |
| :--- | :--- | :--- |
| `/` | `MarketingSite.jsx` | Public |
| `/login/*` | `SignInPage.jsx` | Public |
| `/register/*` | `SignUpPage.jsx` | Public |
| `/recuperar-palavra-passe` | `ForgotPasswordPage.jsx` | Public |
| `/create-org` | `CreateOrgPage.jsx` | Signed in |
| `/foundation` | `Foundation.jsx` | Foundation admin |
| `/dashboard` | `Dashboard.jsx` | Authenticated |
| `/schedules` | `Schedules.jsx` | Authenticated |
| `/members` | `Members.jsx` | Admin (`Equipa`) |
| `/config` | `SchoolConfig.jsx` | Admin |
| `/my-availability` | `MyAvailability.jsx` | Teacher |
| `/my-schedules` | `MySchedules.jsx` | Teacher |
| `/my-progress` | `MyProgress.jsx` | Teacher |
| `/absences` | `Occurrences.jsx` | Admin |
| `/timesheets` | `Timesheets.jsx` | Admin |
| `/rooms` | `Rooms.jsx` | Admin |
| `/subjects` | `Subjects.jsx` | Admin |
| `/courses/:id` | `CourseDetails.jsx` | Admin |
| `/courses/:courseId/classes/:classId` | `ClassDetails.jsx` | Admin |
| `/courses/:courseId/classes/:classId/subjects` | `ClassSubjects.jsx` | Admin |
| `/sign-in/*`, `/sign-up/*` | Redirects | Public |

## Visual Baseline Generation
Visual snapshot reference graphics reside in `documentation/06_frontend_ux/visual-baselines/`. Run CSS coverage scripts to update execution metrics:

```bash
node scripts/capture-css-coverage.mjs
```

The runtime image serves the compiled SPA with Nginx.
Nginx proxies `/api/` to the backend and falls back to `index.html` for client routes.
