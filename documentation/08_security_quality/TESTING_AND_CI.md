# Testing and CI

The [production-browser acceptance PRD](REAL_BROWSER_TESTING_PLAN.md) and its [four-part WBS](REAL_BROWSER_TESTING_WBS.md) describe the agreed redesign.
The [implementation record](REAL_BROWSER_TESTING_IMPLEMENTATION.md) lists which parts are already proven and which dependencies remain.
This guide describes the implemented behaviour.

Cronos runs backend, frontend, and end-to-end suites through one root runner.
GitHub Actions enforces the same gates on every push and pull request.

## Quick start

The supported entry point is the root runner:

```powershell
node scripts/test.mjs setup --scope all
node scripts/test.mjs doctor --profile all
node scripts/test.mjs fast --scope all
node scripts/test.mjs integration
node scripts/test.mjs e2e --project public
node scripts/test.mjs capacity-smoke
node scripts/test.mjs acceptance
node scripts/test.mjs all --scope all
node scripts/test.mjs benchmark --profile fast
node scripts/test.mjs campaign --manifest backend/tests/scheduler_lab/manifest.json
```

The runner exposes `setup`, `doctor`, `fast`, `integration`, `e2e`, `capacity`, `capacity-smoke`, `acceptance`, `all`, `benchmark`, and `campaign`. The `e2e` command accepts `--project public|auth|app|provider|faults|capacity`. E2E starts its own stack on port `5174`.

`fast` never starts Docker or installs packages. Forwarded arguments are accepted only after `--` by `fast` and `integration`, and are passed as separate process arguments. Run artefacts are written to `.test-artifacts/`.

## Backend suites

| Suite | Location | Execution |
| :--- | :--- | :--- |
| Unit | `backend/tests/unit/` | no database or external network; loopback-only socket policy |
| Transactional integration | `backend/tests/integration/transactional/` | real PostgreSQL/Redis stack |
| Committed integration | `backend/tests/integration/committed/` | real PostgreSQL/Redis stack, xdist=4 |
| Contracts | `backend/tests/contracts/` | real PostgreSQL/Redis stack, serial |

Suite membership is structural. PostgreSQL migrations always run through Alembic; SQLite and `metadata.create_all` are not valid substitutes. The runner creates `cronos_test_gw0` through `cronos_test_gw3` for xdist and uses separate migrator/runtime credentials. Destructive operations are accepted only for exact test database names.

Integration runs with `-n 4 --dist=loadscope`. Contracts run serially with rate limiting enabled. The coverage gate requires 70 percent overall, 100 percent for `app/scheduler/domain/constraint_policy.py`, and 90 percent for `app/scheduler/domain/candidate_validation.py`. Any skipped test fails the run.

## Frontend suites

The 48-class correctness test uses the production 900-second safety budget and stops at the first complete candidate.
It validates curricular coverage and completion dates. Short optimization deadlines must not make correctness depend on host load.

Vitest is configured in `frontend/vitest.config.js` with isolated `node` and `dom` projects, thread pooling, MSW server setup and strict unhandled-request failures. Coverage uses V8 and enforces thresholds of 45 percent statements, 40 percent branches, 35 percent functions, and 45 percent lines. React interactions that cross async boundaries use Testing Library `user-event`.

Playwright is configured in `frontend/playwright.config.js`. The `setup` project feeds `public`, `auth`, and `auth-state`. The `app` project depends on `auth-state`, the `provider` project depends on `app`, and the `faults` project depends on `app` and `provider`. The `capacity` project runs only when `CAPACITY_ENABLED=1`. The `acceptance` project matches `frontend/e2e/acceptance/*.spec.js`, uses the installed Chrome channel, one worker, no setup dependency and no test credentials. The `app`, `provider`, and `faults` projects use one worker because they mutate shared E2E state. Retries are disabled; traces are retained on failure and screenshots are captured on failure.

All projects use the shared `E2E_BASE_URL`, which defaults to `http://127.0.0.1:5174`.
This address matches the owned Docker stack's IPv4 binding and avoids other processes listening on `localhost` over IPv6.
The runner supplies `http://localhost:5173` for an external stack.

After sign-in, the E2E helper waits for the loaded Clerk session and expected identity before activating the organization.
This prevents organization activation during a sign-in navigation while the browser reloads Clerk.

## CI gates

The owned local E2E stack builds the frontend `ci` target, which permits the dedicated Clerk test domain.
Its Nginx application routes include `/imports`. Production keeps its runtime browser policy.

GitHub Actions keeps backend, frontend and E2E in separate jobs. The backend job has a 45-minute timeout, the frontend job has a 20-minute timeout, and the E2E job has a 30-minute timeout.

Backend gates use Python 3.14 with `postgres:16` and `redis:7` services. The job provisions `cronos_migrator`, `cronos_app`, and `cronos_auth_definer`, installs locked dependencies with `--require-hashes`, runs `pip check` and `pip-audit`, checks Ruff formatting and linting, runs Alembic upgrade/check/downgrade/upgrade, runs the database integrity audits, runs unit then integration then contract tests, applies the coverage gates, and builds the hardened runtime image.

Frontend gates use Node 24 with `npm ci --ignore-scripts`, `npm run audit:production`, and `npm run verify`. The job also runs `node scripts/loc-report.mjs` against `documentation/08_security_quality/loc-baseline.json`.

E2E uses `docker-compose.ci.yml`. The job prepares dedicated Clerk test identities, runs `node scripts/test.mjs e2e` and `node scripts/test.mjs capacity-smoke`, sanitizes `.test-artifacts/` and Playwright output, and always cleans Compose resources and revokes Clerk invitations. The E2E job is skipped for Dependabot.

Skipped tests, retries, missing artifacts and migration drift are release failures. E2E credentials must be dedicated Clerk test identities; they are not generated or persisted by local test setup.

## Production acceptance

`node scripts/test.mjs acceptance` is the entry point for the real-browser campaign against `https://cronos.pt`.
It runs the reporter-backed Playwright `acceptance` project in Chrome, verifies the Gmail mailboxes and the deployment revisions before and after the run, protects every binary artifact with the campaign key, and evaluates the case matrix with `frontend/e2e/utils/acceptance-policy.js`.
The runner exits `3` while any campaign dependency is missing, and writes the missing names to `.test-artifacts/<run>/acceptance-plan.json`.
The result document is `.test-artifacts/<run>/acceptance-result.json`; only `validated` for the complete matrix can certify production.

The campaign is fail-closed: a failed or missing reporter, an unprotected artifact, a revision mismatch, an unfinished cleanup or a retried case cannot produce green.
The runner invokes the administrative wrapper (`backend/scripts/cleanup_e2e_run.py`) through native Railway SSH after the browser phase.
The wrapper consumes the dedicated `ui-run-registry.json` envelope, not the signed result manifest.
The transport authenticates encrypted exports before accepting deletion results; unfinished cleanup fails the campaign.
Actual production exports and deletion remain unverified.
The native Clerk deletion case exports its selected disposable school before confirming deletion through visible controls.
Final cleanup authenticates that prior backup locally and remotely before reconciling Clerk 404 with the current local ownership.
The returned archive must preserve its original bytes; changed or missing evidence prevents green.
Acceptance rejects cleanup from another `run_id` and requires empty `pending` and `pending_actors` arrays.
The legacy local `e2e` command remains a diagnostic until each substituted group has real proof.

`.github/workflows/acceptance.yml` runs the same command on the `main` SHA, serialized without automatic cancellation.
After success or failure, it uploads only the protected evidence directory, final result and dependency plan, provided sanitization succeeds.
Raw Playwright reports, JUnit output and other files outside this upload list remain excluded.
The sanitizer reads separated environment credentials and the private dynamic registry; an invalid registry prevents artifact changes and upload.
It activates only when the `E2E_ACCEPTANCE_ENABLED` repository variable is `true` and the documented `E2E_*` secrets and variables exist; PRs never receive them.
The real campaign still requires the two Gmail OAuth consents, the Cloudflare and Railway read tokens, the browser/admin credentials, the signed persistent registry and the protected secret registry.
Isolated worker recovery is verified with real PostgreSQL, Redis, a real broker message and an owned Celery worker process in `backend/tests/integration/committed/test_worker_process_recovery.py`.

### Credential and provenance registries

Keep credentials in separate GitHub secrets.
The runner collects sensitive environment values in memory for artifact redaction.
`E2E_SECRET_REGISTRY_JSON` initializes the private file named by `E2E_SECRET_REGISTRY`.
The workflow creates registry directories with mode `0700` and files with mode `0600`.
The running campaign appends observed verification codes and generated passwords to that file, without changing the GitHub secret.
It can start as `[]`; it must grow when the campaign observes new secrets.
The identity journey persists generated passwords and delivered codes before using them in the browser.
`E2E_GMAIL_CODE_SENDER` identifies the observed production verification/recovery sender; configure it as a repository variable.
Preflight requires this value before account creation. Do not derive it from the development Clerk instance.
The contact journey requires an authorized forward from `contacto@cronos.pt` to `admincronos100@gmail.com`.
Keep the production contact recipient unchanged. Configure forwarding separately; these tests do not provision it.
The reader checks the original To, Delivered-To, Reply-To, sender, bounded delivery time and all seven submitted answers.
Discovery includes the unique contact run marker. Other contact messages cannot satisfy the case.
`E2E_CONTACT_SENDER` optionally identifies a configured production sender; its default is `website@forms.cronos.pt`.
The browser uses the real Turnstile widget. Missing verification or missing delivered email fails the case.
OAuth profile verification does not prove that the forward exists; actual message observation provides that proof.
The current identity spec covers registration, verification, fresh-context login and delivered recovery through visible controls.
Its real execution remains pending Gmail OAuth and production deployment alignment; no new identity is certified by these code changes.
Logout, old-password rejection, teacher invitation and school setup have concrete UI journeys.
Their real production execution remains pending the complete campaign prerequisites.
The old-password journey accepts only the documented Clerk HTTP 422 password error for the observed request.
Other authentication failures, network failures and server errors fail the campaign.
Do not duplicate the administrative SSH private key in that JSON registry.

`E2E_PERSISTENT_REGISTRY_JSON` contains the signed campaign school inventory.
An empty signed inventory permits initial preparation; it does not prove eligible historical schools.
Historical cases require observed UI provenance, ended lessons and the required consecutive campaigns.

Run `node scripts/test.mjs prepare-history` to create a persistent full school through the production UI.
This command requires Gmail, matching published revisions, protected evidence and administrative access, but no existing historical password.
It reuses registration, Foundation, five original imports, invitation, generation, independent validation and native approval.
It stores registration, recovered administrator and teacher passwords in an encrypted recovery attachment before creating accounts.
The separate `preparation` project declares no acceptance case IDs and is excluded from default local E2E.
The runner protects evidence, checks the final deployments, preserves persistent identities and authenticates the prepared result.
Successful preparation atomically appends the school and preparation metadata to the signed persistent registry without replacing prior schools.
The metadata retains the observed approved proposal ID for later independent comparison of the materialized baseline.
Retain the protected artifact directory for credential recovery. Update the private GitHub persistent registry secret from the resulting signed file.
Configure the recovered persistent teacher credential as `E2E_HISTORY_TEACHER_PASSWORD` after successful preparation.
Configure the recovered founder credential as `E2E_HISTORY_ADMIN_PASSWORD` for native historical decisions and weekly approval.
The school starts after its actual creation day. Preparation neither backdates lessons nor certifies ended history.

`E2E_HISTORY_TEACHER_PASSWORD` holds the UI login credential of the first registered persistent school's invited teacher.
The history spec derives its dedicated alias from the signed school creation run and verifies the actual Clerk actor and organization.
It selects an ended, unregistered lesson at the actual curricular frontier and reads exact minute balances from weekly slices.
Editing the completed summary must preserve its log identity, minute balances and teacher progress.
Historical preflight requires both passwords; preparation requires neither. The runner and CI sanitizer redact both.

After preflight, the runner creates `.test-artifacts/<run>/ui-run-registry.json` with an authenticated empty actor inventory.
Acceptance fixtures can record the current Clerk identity through `provenance.recordCurrentActor()` and also observe it during teardown.
Identity observation reads the session; it does not create users or alter authentication.
The journal accepts only fresh dedicated aliases and preserves previous data when validation fails.
Call the recorder immediately after account creation and before logout; teardown alone cannot recover an identity after its session ends.
The plaintext journal stays outside the artifact upload list. The runner encrypts a recovery copy before automatic administrative cleanup.

The `acceptance` project currently implements three public cases.
They use Chrome, semantic locators and the runtime observer without programmatic authentication or business seeds.
The remaining case matrix still requires implementation and real execution.
A green legacy CI run does not certify this production matrix.

## References

- [Contributing Guidelines](../00_getting_started/CONTRIBUTING.md)
- [Security and Tenant Isolation](SECURITY_AND_TENANT_ISOLATION.md)
- [Local Runtime](../09_ops_observability/LOCAL_RUNTIME.md)
- [Real browser testing WBS](REAL_BROWSER_TESTING_WBS.md)
- Workflows: `.github/workflows/ci.yml`, `.github/workflows/acceptance.yml`
