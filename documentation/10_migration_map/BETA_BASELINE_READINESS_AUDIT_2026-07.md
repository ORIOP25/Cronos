# Beta Baseline Readiness Audit - July 2026

Status: closed after follow-up verification on 2026-07-08
Branch: `codex/new-baseline-complete-review`
Goal: make this rework the beta baseline through low-complexity UI/UX, CI, DB,
documentation, and cleanup hardening.

## Operating Rules

- Inventory first, categorize second, change third.
- P0 beta blockers must be closed before calling the baseline finished.
- P1 beta polish must be fixed or explicitly accepted.
- P2 maintenance can be fixed when low-risk and clearly useful.
- P3 work is deferred when it implies large refactors or new product scope.
- No destructive database cleanup happens without a reviewed report and rollback path.

## Outcome Summary

- Closed all P0 and P1 findings identified in this pass.
- Removed tracked root patch/log artifacts that were historical noise, not baseline source.
- Added route recovery, uniform confirmation UX, shared API error-message handling, and Clerk PT localization.
- Added CI gates for backend coverage, frontend coverage, Alembic schema drift, and trigger auditing.
- Fixed SQLAlchemy metadata drift by removing a redundant model-level unique constraint that duplicated an existing composite primary key.
- Updated root/backend/documentation README files to reflect the beta hardening baseline.
- Verified frontend lint, unit tests, coverage, and build.
- Verified backend migrations, Alembic check, trigger audit, unit subset, migration contract tests, and the full backend test suite.
- Follow-up verification corrected an incomplete coverage gate, removed additional
  unreachable legacy paths, secured the global 500 contract, added static and
  dependency gates, and added a read-only database integrity audit.

## Finding Register

| ID | Area | Evidence | User Impact | Severity | Decision | Verification | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| BB-001 | UI | `frontend/src/App.jsx` defined `/login` and `/register`, but no `/sign-in` or `/sign-up` aliases. | Clerk/default links or external links to common auth paths could miss the intended auth screen. | P0 blocker | Added redirects from `/sign-in/*` to `/login` and `/sign-up/*` to `/register`. | `frontend/src/test/AppRoutes.test.jsx`; `npm run test`; `npm run test:coverage`. | Fixed |
| BB-002 | UI | `frontend/src/App.jsx` had no `*` catch-all route. | Unknown URLs could show a blank app shell instead of a helpful recovery path. | P0 blocker | Added `NotFoundPage` with recovery links. | `frontend/src/test/AppRoutes.test.jsx`; `npm run test`; `npm run build`. | Fixed |
| BB-003 | UI | Native confirms existed in `CourseDetails.jsx`, `ClassSubjects.jsx`, `Schedules.jsx`, and `Occurrences.jsx`. | Destructive or important actions used browser-native UI inconsistent with the app design and PT copy. | P1 beta polish | Replaced native confirms with existing `ConfirmationModal` flows. | `rg "window\\.confirm|globalThis\\.confirm|confirm\\(" frontend/src frontend/e2e` now only finds the explanatory comment inside `ConfirmationModal.jsx`; scheduler flow test updated. | Fixed |
| BB-004 | UI | `frontend/src/apiClient.js` response interceptor toggled `globalThis._403_toast_shown` but never rendered or dispatched a toast. | Permission failures had dead behavior and inconsistent feedback. | P1 beta polish | Removed dead global side effect and kept rejection behavior explicit. | `frontend/src/test/apiClient.test.js`; `npm run test`. | Fixed |
| BB-005 | UI | API error parsing was duplicated across modal, table, CRUD, onboarding, schedule, occurrence, and timesheet surfaces. | Users could receive inconsistent messages; maintenance risk when backend error shapes evolve. | P1 beta polish | Added `frontend/src/utils/apiErrors.js` and adopted it in focused high-traffic surfaces. | `frontend/src/test/apiErrors.test.js`; `npm run test`; `npm run test:coverage`. | Fixed |
| BB-006 | CI | Backend CI wrote coverage XML, but did not enforce a backend coverage threshold. | Coverage could regress without CI failure. | P2 maintenance | Enforced a 70% backend floor after measuring the full suite above 73%. | Full database-backed suite with `--cov-fail-under=70`. | Fixed |
| BB-007 | CI | The first coverage configuration measured only files imported by tests, so its reported 54.57% statement coverage omitted many zero-coverage source files. | The gate could pass while whole screens and hooks were unmeasured. | P1 beta polish | Added `coverage.include` for all `src/**/*.{js,jsx}` and set honest whole-source floors to 31/28/24/32. | `npm run test:coverage`: 24 files, 143 tests, coverage 31.21/28.22/24.44/32.00. | Fixed |
| BB-008 | CI/DB | CI ran migrations and DB tests, but no `alembic check` gate existed. | SQLAlchemy metadata and migrations could drift. | P0 blocker | Added `alembic check` to CI and fixed detected drift. | `alembic current` at `20260706_repair_tenant_refs`; `alembic check` reports no new upgrade operations. | Fixed |
| BB-009 | CI/DB | `backend/scripts/audit_triggers.py` existed, but CI did not call it. | Tenant trigger contract regressions could miss the beta gate. | P1 beta polish | Added trigger audit to CI after migrations. | `python scripts/audit_triggers.py` passed against migrated test DB. | Fixed |
| BB-010 | Backend/DB | `backend/tests/conftest.py` refuses destructive tests unless the DB name contains `test` or `ci`. | Safe behavior was good, but local backend testing was not discoverable. | P1 beta polish | Replaced backend README with concise safe local test, Alembic, trigger-audit, and coverage instructions. | Docs review plus successful disposable-DB test run. | Fixed |
| BB-011 | Docs | Root README listed stale frontend/quality-gate facts, including Zustand and SonarQube. | New maintainers got stale stack and CI information. | P2 maintenance | Updated stack and CI quality-gate description to current beta baseline facts. | Docs review; targeted stale-term search. | Fixed |
| BB-012 | Docs | `documentation/README.md` described implementation priority as the new scheduler, while the codebase already treats it as baseline. | Project status was misleading during launch-readiness work. | P1 beta polish | Updated documentation index to beta hardening phase and made the audit register canonical for this pass. | Docs review. | Fixed |
| BB-013 | Docs | `backend/README.md` only said `# horario-zen` and `CI/CD Ativo`. | Backend setup, test safety, Alembic, and trigger-audit commands were not discoverable. | P1 beta polish | Replaced with current backend operations README. | Docs review. | Fixed |
| BB-014 | Cleanup | Repo root contained tracked patch/log/report artifacts: `all_changes.patch`, `diff_*.patch`, `backend_logs.txt`, `worker_logs.txt`, `thermo_nuclear_report.txt`. | Noise obscured the actual baseline and could confuse future audits. | P2 maintenance | Deleted historical artifacts after confirming they were not runtime/source inputs. | `git status --short` shows deletions only for those artifacts; no replacement artifacts added. | Fixed |
| BB-015 | Cleanup | `backend/.coverage` existed as an untracked generated artifact. | Local coverage output could accidentally become baseline source. | P2 maintenance | Removed generated artifact and ignored coverage outputs. | `.gitignore` includes `.coverage`, `coverage.xml`, `htmlcov/`, `coverage/`, and `frontend/coverage/`; status no longer shows generated coverage files. | Fixed |
| BB-016 | Backend/API | The global exception handler returned `str(exc)` and wrote tracebacks to a developer-specific absolute Windows path. | Internal details could leak through HTTP 500 responses and logging was non-portable. | P0 blocker | Return stable PT-PT copy and emit a structured traceback through the configured logger. | `backend/tests/test_error_handlers.py`. | Fixed |
| BB-017 | Backend quality | No Python static-analysis gate existed; Ruff found 39 production findings, including duplicated and unused imports plus exception variables captured unsafely by nested callbacks. | Dead code and latent name/scope mistakes could reach CI. | P1 beta polish | Cleaned all production findings and added `ruff check app scripts` to CI. | Ruff and `compileall` pass. | Fixed |
| BB-018 | Frontend cleanup | Unrouted `Classes` and `Timeslots` pages remained. `Timeslots` imported a missing modal and called CRUD routes the backend does not expose. Orphan forms, tests, skeletons, toast provider, and utilities also had no production consumers. | Misleading dead code could not be built or exercised through the application. | P1 beta polish | Removed the unreachable pages and their exclusive dependencies, plus other zero-consumer UI utilities. | ESLint, whole-source coverage, build, and import scans pass. | Fixed |
| BB-019 | Backend cleanup | Legacy admin teacher POST/PATCH/DELETE routes, guard-only service methods, and `TeacherCreate`/`TeacherUpdate` schemas remained after the Equipa cutover. | Two staff-management contracts still appeared in OpenAPI and maintenance paths. | P1 beta polish | Removed legacy writes and contracts; teacher reads and self-service availability remain. | OpenAPI regression test in `test_members_api.py`. | Fixed |
| BB-020 | Error UX | Network failures and empty 401/403/500 responses fell back to Axios/English or generic text. A shared operational label and membership validation messages were double-encoded. | Users could see technical, vague, or corrupted messages. | P1 beta polish | Added actionable status/network copy, corrected frontend and backend PT-PT strings, and added encoding-aware regression coverage. | `apiErrors.test.js`; `terminology.test.js`; `TestMemberValidationMessages`. | Fixed |
| BB-021 | Database | No reusable read-only report checked model/table parity, duplicate unique keys, or orphaned foreign keys. | Data integrity could only be inferred indirectly from migrations. | P1 beta polish | Added `scripts/audit_database_integrity.py` and a CI gate; partial unique indexes are left to PostgreSQL enforcement. | Audit passed against the current development DB and migrated test DB. | Fixed |
| BB-022 | Dependencies | `npm audit` found 19 frontend advisories (2 critical); `pip-audit` found 30 backend advisories. `xlsx` and FullCalendar were unused. | Known vulnerable runtime and development packages remained in the baseline. | P0 blocker | Removed unused packages, upgraded frontend tool/runtime packages and compatible backend framework/solver/security pins, and added npm/pip audit gates. | Both dependency audits report zero known vulnerabilities. | Fixed |
| BB-023 | Performance | The initial production chunk was 509.77 kB and triggered Vite's warning. | Slower initial download and weaker browser caching. | P2 maintenance | Added stable vendor chunking. | Largest JS chunk is Clerk at 312.63 kB; build has no chunk warning. | Fixed |
| BB-024 | CI | PostgreSQL tests were run up to three times and the skipped-test gate parsed `--collect-only`, which cannot observe runtime skips. | CI was slow while its skip regression guard was ineffective. | P1 beta polish | Run the full backend suite once, emit JUnit XML, and sum `skipped` across child `testsuite` elements. | The real report contains 2 runtime skips and the corrected parser returns 2. | Fixed |
| BB-025 | Dashboard | `schedule_health` was returned by the dashboard API and had a finished card component, but the page never rendered it. | A meaningful operational metric silently disappeared from the command center. | P1 beta polish | Restored the card and added unit plus E2E assertions. | `Dashboard.test.jsx`; `dashboard.spec.js`. | Fixed |
| BB-026 | Cleanup/docs | Empty root npm manifests, destructive one-off DB script, obsolete repro script, and documentation for removed toast/skeleton code remained. | Repository entry points and documentation were misleading; one script could erase the public schema without a guard. | P1 beta polish | Removed artifacts and marked historical inventories explicitly; current indexes now point to this audit. | Reference scan and Markdown link validation pass. | Fixed |
| BB-027 | Test isolation | Backend tests inherited the developer's configured Sentry DSN and attempted to report intentional test failures externally. | Tests could create noise or disclose test traces to an external project. | P1 beta polish | Clear `SENTRY_DSN` before importing the app in `conftest.py`. | Focused and full backend runs emit no Sentry delivery attempt. | Fixed |
| BB-028 | Architecture debt | Ruff's McCabe scan reports 27 functions above the default complexity limit: 12 scheduler, 7 operational, 4 member/webhook, and 4 other functions. | These workflows are harder to change safely, although their current behavior is covered by the backend regression suite. | P3 deferred | Keep behavior stable for the beta baseline; extract cohesive domain steps in separately reviewed refactors with characterization tests. The new database audit was split so this pass adds no new complexity finding. | `ruff check app scripts --select C901 --output-format json`; normal Ruff and full tests remain the beta gates. | Deferred |

## Initial Pass Command Log (preserved)

These results describe the first pass committed before the follow-up findings
BB-016 through BB-027. Superseded measurements are labelled below.

| Command | Result | Notes |
| --- | --- | --- |
| `git status --short --branch` | Passed | Branch was `codex/new-baseline-complete-review`; initial inventory found generated `backend/.coverage` and tracked root artifacts. |
| `rg --files` | Passed | Repo inventory collected for frontend, backend, docs, CI, and root artifacts. |
| `rg "window\\.confirm|confirm\\(" frontend/src frontend/e2e` | Passed before fixes | Native confirmations listed in BB-003. |
| `npm run lint` | Passed | Only dependency freshness warning from `baseline-browser-mapping`. |
| `npm run test` | Passed | 25 test files, 151 tests. |
| `npm run test:coverage` | Superseded | The first 54.57% result omitted unimported source files; BB-007 records the corrected gate. |
| `npm run build` | Passed | Initial build had a chunk warning; BB-023 records the resolved build. |
| `alembic upgrade head` | Passed | Disposable Postgres test DB migrated successfully. |
| `alembic current` | Passed | Current revision `20260706_repair_tenant_refs (head)`. |
| `alembic check` | Failed, then passed | Initial metadata drift was the redundant `uq_org_membership_capability`; after model cleanup, no new upgrade operations detected. |
| `python scripts/audit_triggers.py` | Passed | Trigger contract audit succeeded against migrated test DB. |
| `pytest tests/test_migration_tenant_ref_contract.py -q` | Passed | 3 migration contract tests passed. |
| `pytest -m unit -q` | Passed | 21 passed, 519 deselected. |
| `pytest tests/ -v --cov=app --cov-report=xml:coverage.xml --cov-fail-under=35 --tb=short` | Passed | 538 passed, 2 skipped, coverage 73.03%, runtime 33:12. |
| `rg "window\\.confirm|globalThis\\.confirm|confirm\\(" frontend/src frontend/e2e` | Passed after fixes | Only remaining match is the comment inside `ConfirmationModal.jsx`. |
| `docker stop cronos-audit-pg` | Passed | Disposable Postgres container stopped and removed. |
| Generated coverage artifact cleanup | Passed | Removed `backend/coverage.xml`, `backend/.coverage`, and `frontend/coverage` after verification. |

## Follow-up Validation (2026-07-08)

| Gate | Result |
| --- | --- |
| Backend full database-backed suite | 538 passed, 2 skipped; 73.01% coverage; 70% floor passed. |
| Backend focused follow-up | 22 member/onboarding/error-handler tests passed; 3 PT-PT member validation-message tests passed. Current collection: 543 tests. |
| Backend static and dependency checks | Ruff, `compileall`, `pip check`, and `pip-audit` passed; zero known dependency vulnerabilities. |
| Database and migrations | One Alembic head; `alembic check`, tenant-trigger audit, and read-only table/unique-key/foreign-key integrity audit passed. |
| Frontend tests and coverage | 24 files and 143 tests passed; whole-source coverage 31.21/28.22/24.44/32.00. |
| Frontend quality and build | ESLint, Knip, production build, `npm audit`, and runtime-only `npm audit` passed; zero known vulnerabilities and no chunk warning. |
| CI contracts | Workflow YAML and Compose files parse; the JUnit skip gate reads child `testsuite` totals and reports the real 2 runtime skips. |
| UX and documentation | Public landing page rendered correctly in the local browser; protected dashboard redirected through Clerk as designed; tracked-source encoding and Markdown-link scans passed. |

## Deferred or Guarded Items

- Database row cleanup remains limited to read-only duplicate/orphan reports unless a backup and rollback path are explicitly reviewed.
- Large service splits, framework migrations, and broad redesigns remain out of scope for this beta hardening pass.
- The 27 branch-heavy functions inventoried in BB-028 require characterization-led
  refactors, not opportunistic edits during a release-hardening pass.
- Alembic emits a table-sort warning for the intentional cyclic scheduler foreign
  keys. Migrations and drift checks pass; changing those constraints requires a
  separately reviewed migration and is not beta-polish work.
