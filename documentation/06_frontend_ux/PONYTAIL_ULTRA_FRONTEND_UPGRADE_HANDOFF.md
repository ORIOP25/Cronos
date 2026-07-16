# Ponytail Ultra Frontend Upgrade — Implementation Handoff

## Scope and acceptance

This document records the reproducible baseline and final evidence for the Ponytail Ultra frontend WBS. The final gate remains:

- production JS/JSX/CSS at or below 16,000 physical lines, excluding tests;
- coverage at or above 45% statements, 40% branches, 35% functions, and 45% lines;
- signed-in static entry graph at or below 200 KiB gzip and five files;
- no new dependency and no direct `prop-types` dependency;
- lint, normal Knip, production Knip, unit tests, coverage, School Config stability, build, relevant Playwright tests, and GitHub CI green.

## Authoritative baseline

Baseline commit: `cd7c932` (`origin/main` when implementation started).

The attached plan recorded 17,384 production lines and 174 tests. The current integration branch is authoritative and measured 17,316 production lines across 71 files and 177 tests. The numerical acceptance limits are unchanged.

Production LOC was measured from `frontend/` with UTF-8 physical lines and the complete test directory excluded:

```powershell
$files = rg --files src -g '*.js' -g '*.jsx' -g '*.css' -g '!src/test/**' -g '!**/*.test.*' -g '!**/*.spec.*' -g '!**/__tests__/**'; $counts = $files | ForEach-Object { (Get-Content -LiteralPath $_ -Encoding UTF8).Count }; ($counts | Measure-Object -Sum).Sum; $files.Count
```

| Gate | Baseline result |
|---|---:|
| Production source | 17,316 lines / 71 files |
| Unit tests | 177 passing / 29 files |
| Statements | 35.69% (1,170/3,278) |
| Branches | 32.84% (851/2,591) |
| Functions | 27.87% (267/958) |
| Lines | 36.48% (1,089/2,985) |
| Static entry graph | 232,949 bytes / 227.49 KiB gzip / 9 files |
| Playwright inventory | 20 tests / 9 files |

Baseline lint and normal Knip passed. A manifest production build passed. The ten-run School Config stability script passed all 50 assertions when run alone.

The static graph was calculated by recursively following the manifest entry's static `imports` and CSS, then summing `zlib.gzipSync` sizes. Its nine files were the entry JS/CSS, API client, five manual vendor JS chunks, and CoreUI CSS.

## WP0 — Ponytail skill

- Scaffolded `.agents/skills/ponytail` with the official skill-creator utility.
- Normalized `SKILL.md` frontmatter to `name` and `description`; moved the argument hint and MIT license into the body.
- Generated the agreed `agents/openai.yaml` interface metadata.
- Added no scripts, references, or assets.
- Official `quick_validate.py` result: `Skill is valid!`
- `.agents/` remains ignored and `skills-lock.json` is unchanged.

## WP1 — Safety net and tooling

- Added an executable ESLint regression fixture for PascalCase and underscore-prefixed unused bindings.
- Enabled React recommended and JSX-runtime flat configs; lint passes with zero warnings.
- Reused the shared QueryClient/router test harness and merged SignedInRedirect scenarios into the route-guard suite.
- Added `src/main.jsx!` and `src/**/*.{js,jsx}!` Knip production markers. Knip 6.25 requires the `!` marker for `--production`; without it only direct entry imports are analyzed.
- Added the production Knip script and included it in `verify`.
- Removed 24 `prop-types` imports, 30 `.propTypes` assignments, and the remaining WeekGrid-only shape declaration.
- Removed the direct `prop-types` dependency. Its lockfile package remains transitively required by CoreUI and eslint-plugin-react.
- Added PageHeader and SmartTable behavior tests; existing WeekGrid, form, and modal tests remain the component contract.

WP1 exit evidence:

| Gate | Result |
|---|---:|
| Lint | Pass, zero warnings |
| Normal Knip | Pass, zero findings |
| Production Knip | Pass, zero findings |
| Unit tests | 179 passing / 31 files |
| Statements | 36.20% (1,169/3,229) |
| Branches | 33.68% (870/2,583) |
| Functions | 28.40% (271/954) |
| Lines | 36.95% (1,086/2,939) |
| Production build | Pass |

## Implemented contracts and architecture

The upgrade now uses these internal contracts:

| Contract | Implemented definition |
|---|---|
| API client | Successful calls resolve payloads directly; Axios errors remain unchanged. |
| Tenant query keys | Organization data uses `[resource, orgId, ...scope]`. |
| Cache lifetime | `UserQueryProvider` creates one QueryClient per Clerk identity and performs a soft tenant reset on organization changes. |
| Data ownership | `features/members`, `catalog`, `operations`, `scheduling`, `onboarding`, and `schoolConfig` own HTTP, queries, mutations, and invalidation. |
| Page/component boundary | Pages and components do not import Axios or React Query query/mutation primitives. |
| Occurrences | The rendered panel is exactly the active `pending` or `historical` mode, with the URL as the source of truth. |
| Course form | Creation-only, one-page form; class editing remains in `ClassInCourseForm`. |
| SmartTable | Deletion awaits the returned Promise; `getRowLabel` supplies accessible interactive-row text. |
| Component contracts | Behavior tests replace inert PropTypes. |
| Backend contract | No endpoint, schema, or request-payload migration was introduced. |

WP2–WP6 also delivered:

- identity and tenant cache isolation with explicit invalidation tests;
- direct-payload API adapters and contract tests;
- route guards with one shared authorization/loading/error gate and one Suspense boundary;
- derived page state for schedules, occurrences, timesheets, onboarding, and school configuration;
- lazy, conditional modal content with the native CoreUI focus implementation;
- flat creation forms and pure helpers for class drafts and subject modules;
- local-calendar date utilities tested across Sunday and Europe/Lisbon DST boundaries;
- one memoized WeekGrid model with tested collision, baseline, date, and lock behavior;
- shared room, grade, timesheet, lesson-log, and week-navigation presentation metadata;
- an accessible async SmartTable and a single-render DefaultLayout profile area;
- simplified dashboard cards without duplicate loading/error/success shells.

WP7 delivered route-lazy marketing, removed manual vendor chunking and polling, removed the unused Vite asset, moved Clerk styling into its supported appearance contract, and deleted CSS only after coverage/static evidence. Responsive marketing and authentication-shell captures plus CSS coverage are stored in `documentation/06_frontend_ux/visual-baselines/`.

## Final local quality evidence

Final production LOC uses the same command as the baseline. The manifest graph is calculated by recursively following only the entry's static imports and CSS and summing maximum-level gzip sizes.

| Gate | Baseline | Final | Limit |
|---|---:|---:|---:|
| Production source | 17,316 lines / 71 files | 10,905 lines / 82 files | ≤16,000 lines |
| Unit tests | 177 / 29 files | 221 / 41 files | All passing |
| Statements | 35.69% | 52.24% | ≥45% |
| Branches | 32.84% | 45.75% | ≥40% |
| Functions | 27.87% | 45.30% | ≥35% |
| Lines | 36.48% | 53.28% | ≥45% |
| Static entry graph | 232,949 bytes / 9 files | 196,515 bytes / 3 files | ≤204,800 bytes / ≤5 files |

Executed release gates:

- `npm run verify`: pass — ESLint with zero warnings, normal Knip, production Knip, 221 tests with thresholded coverage, and production build.
- `npm run test:school-config:stability`: pass — 10 consecutive runs, 6 assertions per run.
- Targeted identity-switch, organization-switch, stale-query, route/auth, tab, modal, table, form, date, WeekGrid, and accessibility contracts: pass.
- Session recovery E2E now mocks `/api/v1/members/me` with 401 and asserts the actual recovery UI instead of accepting either login or dashboard.
- Final static searches: no `useSchoolData`, PropTypes, `useFocusTrap`, dead schedule root, blanket ESLint suppressions, or page/component React Query primitives.
- Dependency review: no dependency added; direct `prop-types` removed.
- `git diff --check`: pass.

## Retained complexity and environment limits

- A few narrow `eslint-disable-next-line` annotations remain beside effects or compiler-sensitive memoization in complex scheduler/detail screens. There are no file-level or blanket hook suppressions; each annotation is local to the line whose lifecycle semantics cannot be expressed more simply without changing behavior.
- CoreUI remains the established component framework and accounts for much of the global CSS payload. Replacing it was an explicit non-goal; the signed-in static entry still meets the WBS budget.
- Real signed-in admin and teacher Playwright smoke workflows require Clerk keys and test credentials. Those values were unavailable in the local environment, so local visual evidence covers marketing and the authentication shell; authenticated smoke coverage is delegated to the configured CI environment where its secrets/services are available.

## GitHub release gate

The implementation is ready for branch publication. The final task is complete only after required GitHub CI checks pass without errors and the pull request is merged into `main`.
