# Beta Baseline Readiness Audit - July 2026

Status: closed for this hardening pass
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

## Finding Register

| ID | Area | Evidence | User Impact | Severity | Decision | Verification | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| BB-001 | UI | `frontend/src/App.jsx` defined `/login` and `/register`, but no `/sign-in` or `/sign-up` aliases. | Clerk/default links or external links to common auth paths could miss the intended auth screen. | P0 blocker | Added redirects from `/sign-in/*` to `/login` and `/sign-up/*` to `/register`. | `frontend/src/test/AppRoutes.test.jsx`; `npm run test`; `npm run test:coverage`. | Fixed |
| BB-002 | UI | `frontend/src/App.jsx` had no `*` catch-all route. | Unknown URLs could show a blank app shell instead of a helpful recovery path. | P0 blocker | Added `NotFoundPage` with recovery links. | `frontend/src/test/AppRoutes.test.jsx`; `npm run test`; `npm run build`. | Fixed |
| BB-003 | UI | Native confirms existed in `CourseDetails.jsx`, `ClassSubjects.jsx`, `Schedules.jsx`, and `Occurrences.jsx`. | Destructive or important actions used browser-native UI inconsistent with the app design and PT copy. | P1 beta polish | Replaced native confirms with existing `ConfirmationModal` flows. | `rg "window\\.confirm|globalThis\\.confirm|confirm\\(" frontend/src frontend/e2e` now only finds the explanatory comment inside `ConfirmationModal.jsx`; scheduler flow test updated. | Fixed |
| BB-004 | UI | `frontend/src/apiClient.js` response interceptor toggled `globalThis._403_toast_shown` but never rendered or dispatched a toast. | Permission failures had dead behavior and inconsistent feedback. | P1 beta polish | Removed dead global side effect and kept rejection behavior explicit. | `frontend/src/test/apiClient.test.js`; `npm run test`. | Fixed |
| BB-005 | UI | API error parsing was duplicated across modal, table, CRUD, onboarding, schedule, occurrence, and timesheet surfaces. | Users could receive inconsistent messages; maintenance risk when backend error shapes evolve. | P1 beta polish | Added `frontend/src/utils/apiErrors.js` and adopted it in focused high-traffic surfaces. | `frontend/src/test/apiErrors.test.js`; `npm run test`; `npm run test:coverage`. | Fixed |
| BB-006 | CI | Backend CI wrote coverage XML, but did not enforce a backend coverage threshold. | Coverage could regress without CI failure. | P2 maintenance | Added `--cov-fail-under=35` to backend CI after measuring current baseline. | Full backend suite: `538 passed, 2 skipped`, coverage `73.03%`, gate passed. | Fixed |
| BB-007 | CI | CI installed `@vitest/coverage-v8`, but frontend tests ran without coverage enforcement. | Frontend coverage was invisible and unenforced. | P1 beta polish | Added `test:coverage` and modest V8 thresholds: statements 54, branches 56, functions 40, lines 56. | `npm run test:coverage`: 25 files, 151 tests, coverage 54.57/56.68/41.01/56.68. | Fixed |
| BB-008 | CI/DB | CI ran migrations and DB tests, but no `alembic check` gate existed. | SQLAlchemy metadata and migrations could drift. | P0 blocker | Added `alembic check` to CI and fixed detected drift. | `alembic current` at `20260706_repair_tenant_refs`; `alembic check` reports no new upgrade operations. | Fixed |
| BB-009 | CI/DB | `backend/scripts/audit_triggers.py` existed, but CI did not call it. | Tenant trigger contract regressions could miss the beta gate. | P1 beta polish | Added trigger audit to CI after migrations. | `python scripts/audit_triggers.py` passed against migrated test DB. | Fixed |
| BB-010 | Backend/DB | `backend/tests/conftest.py` refuses destructive tests unless the DB name contains `test` or `ci`. | Safe behavior was good, but local backend testing was not discoverable. | P1 beta polish | Replaced backend README with concise safe local test, Alembic, trigger-audit, and coverage instructions. | Docs review plus successful disposable-DB test run. | Fixed |
| BB-011 | Docs | Root README listed stale frontend/quality-gate facts, including Zustand and SonarQube. | New maintainers got stale stack and CI information. | P2 maintenance | Updated stack and CI quality-gate description to current beta baseline facts. | Docs review; targeted stale-term search. | Fixed |
| BB-012 | Docs | `documentation/README.md` described implementation priority as the new scheduler, while the codebase already treats it as baseline. | Project status was misleading during launch-readiness work. | P1 beta polish | Updated documentation index to beta hardening phase and made the audit register canonical for this pass. | Docs review. | Fixed |
| BB-013 | Docs | `backend/README.md` only said `# horario-zen` and `CI/CD Ativo`. | Backend setup, test safety, Alembic, and trigger-audit commands were not discoverable. | P1 beta polish | Replaced with current backend operations README. | Docs review. | Fixed |
| BB-014 | Cleanup | Repo root contained tracked patch/log/report artifacts: `all_changes.patch`, `diff_*.patch`, `backend_logs.txt`, `worker_logs.txt`, `thermo_nuclear_report.txt`. | Noise obscured the actual baseline and could confuse future audits. | P2 maintenance | Deleted historical artifacts after confirming they were not runtime/source inputs. | `git status --short` shows deletions only for those artifacts; no replacement artifacts added. | Fixed |
| BB-015 | Cleanup | `backend/.coverage` existed as an untracked generated artifact. | Local coverage output could accidentally become baseline source. | P2 maintenance | Removed generated artifact and ignored coverage outputs. | `.gitignore` includes `.coverage`, `coverage.xml`, `htmlcov/`, `coverage/`, and `frontend/coverage/`; status no longer shows generated coverage files. | Fixed |

## Baseline Command Log

| Command | Result | Notes |
| --- | --- | --- |
| `git status --short --branch` | Passed | Branch was `codex/new-baseline-complete-review`; initial inventory found generated `backend/.coverage` and tracked root artifacts. |
| `rg --files` | Passed | Repo inventory collected for frontend, backend, docs, CI, and root artifacts. |
| `rg "window\\.confirm|confirm\\(" frontend/src frontend/e2e` | Passed before fixes | Native confirmations listed in BB-003. |
| `npm run lint` | Passed | Only dependency freshness warning from `baseline-browser-mapping`. |
| `npm run test` | Passed | 25 test files, 151 tests. |
| `npm run test:coverage` | Passed | Coverage thresholds enforced: statements 54.57, branches 56.68, functions 41.01, lines 56.68. |
| `npm run build` | Passed | Build succeeded with Vite chunk-size warning for the main bundle. |
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

## Deferred or Guarded Items

- Database row cleanup remains limited to read-only duplicate/orphan reports unless a backup and rollback path are explicitly reviewed.
- Large service splits, framework migrations, and broad redesigns remain out of scope for this beta hardening pass.
- Vite still warns that the main production bundle is larger than 500 kB after minification. This is a P2/P3 performance follow-up, not a beta blocker, because the build succeeds and the request explicitly avoided complex new work.
