# Cronos Frontend Workspace

React 19 single-page application (SPA) for Cronos, built with Vite 8.

## Technology Stack
- React 19
- Vite 8
- React Router 7 (`react-router-dom`)
- Clerk Authentication (`@clerk/react`)
- CoreUI
- TanStack React Query (`@tanstack/react-query`)
- Axios
- Vitest
- Playwright E2E

## Development Commands

```bash
# Install dependencies
npm install

# Start local dev server
npm run dev

# Build production bundle and pre-render marketing HTML pages
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

# Run the fast critical subset (legal contract, marketing build, edge worker, assets, critical tests)
npm run verify:critical:fast

# Check production-only source rules
npm run audit:production
```

`npm run build` runs `vite build` and `node scripts/build-marketing-pages.mjs`.
`npm run verify` runs lint, both Knip checks, the legal contract check, the marketing build test, the root script tests, the edge worker test, the marketing asset check, coverage, and the build.

## Public Marketing Site
The public marketing site resides in `src/features/marketing/`:
- Layout: `src/features/marketing/components/layout/MarketingLayout.jsx`
- Sections: `src/features/marketing/components/`
- Content and metadata: `src/features/marketing/content/`
- Page components: `src/pages/marketing/`
- Styles: `src/features/marketing/styles/` and `src/pages/MarketingSite.css`
- Optimized WebP graphics: `public/marketing/*.webp`

Marketing pages render on the client and as build-time static HTML.
The build renders one HTML file per route in `src/features/marketing/content/metadata.js`.
Marketing CSS classes use the `cronos-*` namespace to isolate styles from authenticated application pages. Continuous animations use GPU hardware layer promotion (`translate3d`). Below-the-fold sections use `content-visibility: auto`.

## Route Summary Table

| Path | View Component | Access Requirement |
| :--- | :--- | :--- |
| `/` | `pages/marketing/HomePage.jsx` | Public |
| `/vantagens`, `/como-funciona`, `/ajuda` | `VantagensPage.jsx`, `HowItWorksPage.jsx`, `HelpPage.jsx` | Public |
| `/sobre`, `/about` | `pages/marketing/AboutPage.jsx` | Public |
| `/contacto`, `/contact` | `pages/marketing/ContactPage.jsx` | Public |
| `/privacidade`, `/privacy`, `/termos`, `/dpa`, `/cookies` | `features/legal/LegalDocumentLayout.jsx` | Public |
| `/login/*` | `SignInPage.jsx` | Public |
| `/register/*` | `SignUpPage.jsx` | Public |
| `/recuperar-palavra-passe` | `ForgotPasswordPage.jsx` | Public |
| `/foundation/waiting` | `FoundationWaiting.jsx` | Signed in |
| `/foundation` | `Foundation.jsx` | Foundation admin |
| `/guide` | `Guide.jsx` | Foundation admin |
| `/dashboard`, `/schedules`, `/rooms`, `/subjects`, `/config`, `/imports` | `Dashboard.jsx`, `Schedules.jsx`, `Rooms.jsx`, `Subjects.jsx`, `SchoolConfig.jsx`, `BulkImport.jsx` | Admin |
| `/members` | `Members.jsx` | Admin (`Equipa`) |
| `/absences`, `/timesheets` | `Occurrences.jsx`, `Timesheets.jsx` | Admin |
| `/courses`, `/courses/:id` | `Courses.jsx`, `CourseDetails.jsx` | Admin |
| `/courses/:courseId/classes/:classId` | `ClassDetails.jsx` | Admin |
| `/courses/:courseId/classes/:classId/subjects` | `ClassSubjects.jsx` | Admin |
| `/my-availability`, `/my-schedules`, `/my-progress` | `MyAvailability.jsx`, `MySchedules.jsx`, `MyProgress.jsx` | Teacher |
| `/sign-in/*`, `/sign-up/*` | Redirects | Public |

The runtime image serves the compiled SPA with Nginx.
Nginx proxies `/api/` to the backend.
Nginx serves pre-rendered marketing pages with `try_files $uri $uri.html =404` and application routes from `app-shell.html`.
